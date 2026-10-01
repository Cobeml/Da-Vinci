import json
import os
import subprocess
import tempfile
import threading
import time
from pathlib import Path

from davinci.models import identity


class SandboxError(RuntimeError):
    def __init__(self, message, *, reason="solver_error", outputs=None, log="", duration=0):
        super().__init__(message)
        self.reason = reason
        self.outputs = outputs or {}
        self.log = log
        self.duration = duration


_slots = threading.BoundedSemaphore(2)


class Runner:
    def __init__(self, settings, cancelled=lambda: False, concurrency=None):
        if concurrency is not None and (type(concurrency) is not int or not 1 <= concurrency <= 4):
            raise ValueError("Sandbox concurrency must be an integer from 1 to 4")
        self.settings = settings
        self.slots = _slots if concurrency is None else threading.BoundedSemaphore(concurrency)
        self.cancelled = cancelled
        self.root = settings.root / "sandboxes"
        self.root.mkdir(exist_ok=True)
        self._image_digest = None

    def image_digest(self):
        if self._image_digest is None:
            self._image_digest = subprocess.check_output(
                ["docker", "image", "inspect", "--format={{.Id}}", self.settings.davinci_sandbox_image],
                text=True,
                stderr=subprocess.PIPE,
                timeout=10,
            ).strip()
        return self._image_digest

    def available(self):
        try:
            result = subprocess.run(
                ["docker", "image", "inspect", self.settings.davinci_sandbox_image],
                capture_output=True,
                timeout=10,
            )
            return result.returncode == 0
        except (OSError, subprocess.TimeoutExpired):
            return False

    def probe(self, runtime):
        from davinci.product.adapters import probe_runtime

        return probe_runtime(self, runtime)

    def execute(
        self,
        entrypoint,
        files,
        timeout=120,
        image=None,
        executable="python",
        memory_gb=4,
        cpu_cores=2,
        artifact_bytes=64_000_000,
        file_bytes=32_000_000,
        log_bytes=8_000_000,
    ):
        if type(memory_gb) is not int or not 1 <= memory_gb <= 12:
            raise ValueError("Sandbox memory must be an integer from 1 to 12 GB")
        if not 0 < timeout <= 600 or not 0.25 <= cpu_cores <= 8:
            raise ValueError("Invalid sandbox time/CPU limit")
        if not (
            1024 <= file_bytes <= 128_000_000
            and 1024 <= artifact_bytes <= 256_000_000
            and 1024 <= log_bytes <= 16_000_000
        ):
            raise ValueError("Invalid artifact limits")
        # A cancelled job must not wait indefinitely for a sandbox slot.
        while not self.slots.acquire(timeout=0.15):
            if self.cancelled():
                raise SandboxError("Run stopped", reason="cancelled")
        try:
            return self._execute(
                entrypoint,
                files,
                timeout,
                image,
                executable,
                memory_gb,
                cpu_cores,
                artifact_bytes,
                file_bytes,
                log_bytes,
            )
        finally:
            self.slots.release()

    def _execute(
        self,
        entrypoint,
        files,
        timeout,
        image,
        executable,
        memory_gb,
        cpu_cores,
        artifact_bytes,
        file_bytes,
        log_bytes,
    ):
        if self.cancelled():
            raise SandboxError("Run stopped", reason="cancelled")
        try:
            endpoint = (
                os.environ.get("DOCKER_HOST")
                or subprocess.check_output(
                    ["docker", "context", "inspect", "--format", "{{.Endpoints.docker.Host}}"],
                    text=True,
                    stderr=subprocess.PIPE,
                    timeout=5,
                ).strip()
            )
        except (OSError, subprocess.SubprocessError) as exc:
            raise SandboxError("Local Docker backend unavailable", reason="unavailable_runtime") from exc
        if not endpoint.startswith("unix://"):
            raise SandboxError(
                "Remote Docker execution requires an explicit executor", reason="unavailable_runtime"
            )
        name = identity("davinci")
        with tempfile.TemporaryDirectory(dir=self.root) as folder:
            base = Path(folder)
            incoming, outgoing = base / "input", base / "output"
            incoming.mkdir()
            outgoing.mkdir(mode=0o777)
            outgoing.chmod(0o777)
            for filename, data in files.items():
                path = incoming / filename
                if not path.resolve().is_relative_to(incoming):
                    raise ValueError("Invalid sandbox input path")
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_bytes(data if isinstance(data, bytes) else data.encode())
                path.chmod(0o644)
            command = [
                "docker",
                "run",
                "--rm",
                "--name",
                name,
                "--network",
                "none",
                "--cpus",
                str(cpu_cores),
                "--memory",
                f"{memory_gb}g",
                "--memory-swap",
                f"{memory_gb}g",
                "--pids-limit",
                "128",
                "--read-only",
                "--cap-drop",
                "ALL",
                "--security-opt",
                "no-new-privileges",
                "--user",
                "65534:65534",
                "--tmpfs",
                "/tmp:rw,nosuid,size=256m",
                "--ulimit",
                f"fsize={file_bytes}:{file_bytes}",
                "--mount",
                f"type=bind,src={incoming},dst=/input,readonly",
                "--mount",
                f"type=bind,src={outgoing},dst=/output",
                image or self.image_digest(),
                executable,
                entrypoint,
            ]
            started = time.monotonic()

            def paths_and_size():
                total, count = 0, 0
                for path in outgoing.rglob("*"):
                    count += 1
                    if count > 1024:
                        raise SandboxError("Too many output entries", reason="artifact_quota")
                    if path.is_symlink() or not path.is_file():
                        raise SandboxError(
                            "Only flat regular output files are supported", reason="invalid_result"
                        )
                    total += path.stat().st_size
                    if total > artifact_bytes:
                        raise SandboxError("Sandbox output quota exceeded", reason="artifact_quota")
                return total

            def collect():
                result, omitted, total = {}, [], 0
                for index, path in enumerate(outgoing.iterdir()):
                    if index >= 1024:
                        omitted.append("additional output entries")
                        break
                    if path.is_symlink() or not path.is_file():
                        omitted.append(path.name)
                        continue
                    size = path.stat().st_size
                    if size > file_bytes or total + size > artifact_bytes:
                        omitted.append(path.name)
                        continue
                    result[path.name] = path.read_bytes()
                    total += size
                return result, omitted

            with (base / "execution.log").open("w+b") as log:
                process = subprocess.Popen(command, stdout=log, stderr=subprocess.STDOUT)
                error = None
                try:
                    while process.poll() is None:
                        if self.cancelled():
                            raise SandboxError("Run stopped", reason="cancelled")
                        if time.monotonic() - started > timeout:
                            raise SandboxError("Sandbox timed out", reason="timeout")
                        if log.tell() > log_bytes:
                            raise SandboxError("Sandbox log limit exceeded", reason="artifact_quota")
                        paths_and_size()
                        time.sleep(0.15)
                    if process.returncode:
                        reason = (
                            "resource_exhaustion"
                            if process.returncode in (137, 153)
                            else "unavailable_runtime"
                            if process.returncode == 125
                            else "solver_error"
                        )
                        raise SandboxError(f"Sandbox exited with code {process.returncode}", reason=reason)
                    paths_and_size()
                    if log.tell() > log_bytes:
                        raise SandboxError("Sandbox log limit exceeded", reason="artifact_quota")
                except SandboxError as exc:
                    error = exc
                finally:
                    if process.poll() is None:
                        try:
                            subprocess.run(["docker", "rm", "-f", name], capture_output=True, timeout=15)
                        finally:
                            process.kill()
                            process.wait()
                duration = time.monotonic() - started
                log.seek(0)
                logs = log.read(log_bytes).decode(errors="replace")
                result, omitted = collect()
                usage = {
                    "wall_seconds": duration,
                    "allocated_cpu_seconds_upper_bound": duration * cpu_cores,
                    "cpu_cores_limit": cpu_cores,
                    "memory_gb_limit": memory_gb,
                    "peak_memory_bytes": None,
                    "peak_memory_note": "Not measured; allocation is not usage",
                    "artifact_bytes_limit": artifact_bytes,
                    "omitted_outputs": omitted,
                    "estimate_refinement": "Measured wall time/output bytes; no claim of mesh convergence or memory adequacy",
                    "output_bytes": sum(len(v) for v in result.values()),
                    "image": image or self.image_digest(),
                    "reason": error.reason if error else "ok",
                }
                # Host-owned names overwrite any attempted solver forgery.
                result["resources.json"] = json.dumps(usage).encode()
                if omitted and error is None:
                    error = SandboxError("Artifact collection incomplete", reason="artifact_quota")
                if error:
                    error.outputs, error.log, error.duration = result, logs, duration
                    raise error
                return result, logs, duration

    def evaluate(self, source, parameters, subsystem, specification):
        request = json.dumps(
            {
                "parameters": parameters,
                "interfaces": specification,
                "specification": specification,
                "subsystem": subsystem,
            }
        )
        built, build_log, build_time = self.execute(
            "/opt/build.py", {"source.py": source, "request.json": request}
        )
        if "model.step" not in built:
            raise SandboxError("Build did not produce STEP geometry")
        measured, log, duration = self.execute(
            "/opt/evaluate.py", {"model.step": built["model.step"], "request.json": request}, timeout=60
        )
        result = json.loads(measured["result.json"])
        return (
            result,
            {
                "model.step": built["model.step"],
                "model.glb": measured["model.glb"],
                "execution.log": (build_log + log).encode(),
            },
            build_time + duration,
        )

    def invoke(self, source, arguments):
        result, _, _ = self.execute(
            "/opt/invoke.py", {"tool.py": source, "arguments.json": json.dumps(arguments)}, timeout=60
        )
        return json.loads(result["result.json"])

    def integrate(self, mount_step, wing_step, specification):
        outputs, _, _ = self.execute(
            "/opt/integrate.py",
            {
                "structural.step": mount_step,
                "aerodynamic.step": wing_step,
                "specification.json": json.dumps(specification),
            },
            timeout=60,
        )
        return json.loads(outputs["result.json"]), {k: v for k, v in outputs.items() if k != "result.json"}

    def adapt(self, files, cases):
        result, _, _ = self.execute(
            "/opt/adapt.py",
            {
                "orchestrator.py": files["orchestrator.py"],
                "policy.json": files["policy.json"],
                "request.json": json.dumps({"cases": cases}),
            },
            timeout=30,
        )
        return json.loads(result["result.json"])
