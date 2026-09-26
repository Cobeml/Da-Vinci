import json
import subprocess
import tempfile
import time
from pathlib import Path

from davinci.models import identity


class SandboxError(RuntimeError):
    pass


class Runner:
    def __init__(self, settings, cancelled=lambda: False):
        self.settings = settings
        self.cancelled = cancelled
        self.root = settings.root / "sandboxes"
        self.root.mkdir(exist_ok=True)

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

    def execute(self, entrypoint, files, timeout=120, image=None, executable="python"):
        if self.cancelled():
            raise SandboxError("Run stopped")
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
                "2",
                "--memory",
                "4g",
                "--memory-swap",
                "4g",
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
                "--mount",
                f"type=bind,src={incoming},dst=/input,readonly",
                "--mount",
                f"type=bind,src={outgoing},dst=/output",
                image or self.settings.davinci_sandbox_image,
                executable,
                entrypoint,
            ]
            started = time.monotonic()
            # File-backed logs avoid pipe deadlocks; the file lives in the per-job directory.
            with (base / "execution.log").open("w+b") as log:
                process = subprocess.Popen(command, stdout=log, stderr=subprocess.STDOUT)
                try:
                    while process.poll() is None:
                        if self.cancelled() or time.monotonic() - started > timeout:
                            raise SandboxError("Run stopped" if self.cancelled() else "Sandbox timed out")
                        if log.tell() > 8_000_000:
                            raise SandboxError("Sandbox log limit exceeded")
                        time.sleep(0.15)
                    log.seek(0)
                    logs = log.read(32000).decode(errors="replace")
                    if process.returncode:
                        raise SandboxError(logs[-4000:])
                    result = {}
                    for path in outgoing.iterdir():
                        if path.is_symlink() or not path.is_file():
                            raise SandboxError("Unsupported output artifact")
                        if path.stat().st_size > 32_000_000:
                            raise SandboxError("Artifact exceeds 32 MB")
                        result[path.name] = path.read_bytes()
                    return result, logs, time.monotonic() - started
                finally:
                    if process.poll() is None:
                        subprocess.run(["docker", "rm", "-f", name], capture_output=True, timeout=15)
                        process.kill()
                        process.wait()

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
