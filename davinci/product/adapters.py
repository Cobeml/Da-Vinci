"""Scoped simulation adapters shared by managed and external lifecycle callers.

Registry discovery imports no optional numerical packages. Existing legacy entrypoints
retain their formulas and exact unit strings; this registry does not supply generic FEA.
"""

import json
import os
import shutil
import subprocess
from pathlib import Path

from davinci.product.mechanism.adapter import DESCRIPTOR as MECHANISM
from davinci.product.simulation_contracts import AdapterDescriptor
from davinci.product.structural.adapter import DESCRIPTOR as STRUCTURAL
from davinci.product.units import convert, validate_plan_units

REGISTRY = {
    "mujoco-slider": MECHANISM,
    "calculix-static": STRUCTURAL,
    "sensor-screen": AdapterDescriptor(
        id="sensor-screen",
        phenomena=["mass", "linear_static"],
        material_models=["nominal_isotropic_PA12"],
        geometry_assumptions="Single fixed cradle family; symmetric STEP/reference difference <= 0.1 mm3",
        fidelities=["wall_strip_screen"],
        required_software={"cadquery": None},
        limitations=[
            "Two conservative uniform wall strips; ribs receive no stiffness credit",
            "No joints, stress concentrations, print anisotropy, vibration or FEA",
        ],
        reference_checks=[
            "Independent cradle symmetric-difference check",
            "Closed-form cantilever strip stress and deflection",
        ],
        routes=["legacy"],
    ),
    "gripper-screen": AdapterDescriptor(
        id="gripper-screen",
        phenomena=["mass", "linear_static", "sampled_clearance", "member_buckling"],
        material_models=["nominal_isotropic_aluminium"],
        geometry_assumptions="Fixed three-part jaw graph and carriage; independently reconstructed STEP reference",
        fidelities=["linear_3d_frame_and_BRep_travel"],
        required_software={"cadquery": None, "numpy": None},
        limitations=[
            "Rigid beam joints; normal stress only; pinned Euler member buckling",
            "Nine travel positions, not continuous collision or dynamics",
            "No fatigue, joint or bearing analysis",
        ],
        reference_checks=["Graph/STEP symmetric difference", "Beam cantilever force/displacement reference"],
        routes=["legacy"],
    ),
    "vtol-screen": AdapterDescriptor(
        id="vtol-screen",
        phenomena=["mass", "attached_flow", "mission_energy", "beam_screen"],
        material_models=["nominal_component_properties"],
        geometry_assumptions="Fixed parametric VTOL family, validated component envelopes and fixed propeller data",
        fidelities=["coupled_engineering_estimate"],
        required_software={"cadquery": None, "numpy": None, "aerosandbox": "4.2.6", "scipy": None},
        limitations=[
            "VLM/XFOIL attached flow only",
            "No rotor interference, transition dynamics, flutter or fatigue",
            "Fixed speed grid and measured propeller-map support; no flight validation",
        ],
        reference_checks=[
            "STEP/reference symmetric difference",
            "VLM resolution study and existing aerodynamic references",
        ],
        routes=["legacy"],
    ),
    "authored-screen": AdapterDescriptor(
        id="authored-screen",
        phenomena=["mass", "linear_static", "geometry"],
        material_models=["linear_isotropic"],
        geometry_assumptions="Task-authored evaluator must independently reject unsupported geometry; positive and negative fixtures required",
        fidelities=["analytic_screen"],
        required_software={"cadquery": None, "numpy": None},
        limitations=[
            "Task-authored analytic screening, not a general structural solver",
            "No nonlinear materials, contact, fatigue, dynamics or certified uncertainty",
        ],
        reference_checks=[
            "Task-specific positive and negative reference fixtures; no transferable passing score"
        ],
        routes=["v2", "legacy-custom"],
    ),
}


def catalog():
    return [a.model_dump() for a in REGISTRY.values()]


def legacy_descriptor(task):
    entry = task["entrypoint"]
    key = {
        "evaluate_sensor.py": "sensor-screen",
        "evaluate_gripper.py": "gripper-screen",
        "evaluate_vtol.py": "vtol-screen",
    }.get(entry)
    if key:
        return REGISTRY[key]
    return REGISTRY["authored-screen"].model_copy(
        update={
            "phenomena": ["task_declared"],
            "material_models": ["task_declared"],
            "geometry_assumptions": "Legacy custom evaluator supplies applicability checks; coverage is unverified",
            "fidelities": ["task_declared"],
            "required_software": {"cadquery": None},
            "limitations": [
                "Opaque legacy custom evaluator; no generic physics capability or verified final coverage is implied"
            ],
            "routes": ["legacy-custom"],
        }
    )


def effective_capacity(root):
    """Host/cgroup upper bounds, including remaining RAM. Remote daemon limits are separate."""
    cpus = (
        float(len(os.sched_getaffinity(0)))
        if hasattr(os, "sched_getaffinity")
        else float(os.cpu_count() or 1)
    )
    memory = None
    try:
        rows = dict(line.split(":", 1) for line in Path("/proc/meminfo").read_text().splitlines())
        memory = int(rows["MemAvailable"].split()[0]) * 1024
    except (OSError, KeyError, ValueError):
        pass
    # Walk from the process' unified cgroup through parents, taking every effective quota.
    base = Path("/sys/fs/cgroup")
    paths = [base]
    try:
        relative = next(
            line.split(":", 2)[2]
            for line in Path("/proc/self/cgroup").read_text().splitlines()
            if line.startswith("0::")
        )
        current = base / relative.lstrip("/")
        if current.is_relative_to(base):
            paths = [current, *[p for p in current.parents if p.is_relative_to(base)]]
    except (OSError, StopIteration):
        pass
    for path in paths:
        try:
            quota, period = (path / "cpu.max").read_text().split()
            if quota != "max":
                cpus = min(cpus, int(quota) / int(period))
        except (OSError, ValueError):
            pass
        try:
            limit = (path / "memory.max").read_text().strip()
            used = int((path / "memory.current").read_text())
            if limit != "max":
                available = max(0, int(limit) - used)
                memory = min(memory, available) if memory is not None else available
        except (OSError, ValueError):
            pass
    try:
        groups = [line.split(":", 2) for line in Path("/proc/self/cgroup").read_text().splitlines()]
        for _, controllers, relative in groups:
            controllers = controllers.split(",")
            for controller in ("cpu", "memory"):
                if controller not in controllers:
                    continue
                mount = base / controller
                if not mount.exists() and controller == "cpu":
                    mount = base / "cpu,cpuacct"
                current = mount / relative.lstrip("/")
                if not current.is_relative_to(mount):
                    continue
                for path in [current, *[p for p in current.parents if p.is_relative_to(mount)]]:
                    try:
                        if controller == "cpu":
                            quota = int((path / "cpu.cfs_quota_us").read_text())
                            period = int((path / "cpu.cfs_period_us").read_text())
                            if quota > 0:
                                cpus = min(cpus, quota / period)
                        else:
                            available = max(
                                0,
                                int((path / "memory.limit_in_bytes").read_text())
                                - int((path / "memory.usage_in_bytes").read_text()),
                            )
                            memory = min(memory, available) if memory is not None else available
                    except (OSError, ValueError):
                        pass
    except OSError:
        pass
    return {
        "cpu_cores": cpus,
        "memory_bytes": memory,
        "disk_bytes": shutil.disk_usage(root).free,
        "accelerators": [],
        "accelerator_probe": "not requested; all shipped adapters use CPU",
        "backend": "docker",
        "remote_provisioning": False,
    }


PROBE = """import importlib, importlib.metadata, json, platform, shutil, subprocess, re
from pathlib import Path
software = {"python": platform.python_version()}
for name in ("cadquery", "numpy", "scipy", "aerosandbox", "gmsh", "mujoco"):
    try:
        importlib.import_module(name)
        software[name] = importlib.metadata.version(name)
    except Exception:
        software[name] = None
software["xfoil"] = "present-version-unreported" if shutil.which("xfoil") else None
software["calculix"] = None
if shutil.which("ccx"):
    text = subprocess.run(["ccx", "-v"], capture_output=True, text=True, timeout=5)
    match = re.search(r"Version\\s+([0-9.]+)", text.stdout + text.stderr, re.I)
    if match:
        software["calculix"] = match.group(1).rstrip('.')
Path("/output/probe.json").write_text(json.dumps({"software": software}))
"""


def probe_runtime(runner, runtime):
    """A bounded sandbox probe in the pinned image; no host numerical imports or provider."""
    capacity = effective_capacity(runner.root)
    if runtime.backend != "docker":
        return {
            **capacity,
            "available": False,
            "reason": "Configured remote backend has no installed executor",
        }
    # Refuse implicit remote Docker contexts. Remote execution needs a future explicit executor.
    try:
        endpoint = subprocess.check_output(
            ["docker", "context", "inspect", "--format", "{{.Endpoints.docker.Host}}"],
            text=True,
            timeout=5,
            stderr=subprocess.PIPE,
        ).strip()
        endpoint = os.environ.get("DOCKER_HOST", endpoint)
        if not endpoint.startswith("unix://"):
            return {
                **capacity,
                "available": False,
                "reason": "Only a local Unix-socket Docker backend is supported",
            }
        daemon = json.loads(
            subprocess.check_output(
                ["docker", "info", "--format", "{{json .}}"], text=True, timeout=5, stderr=subprocess.PIPE
            )
        )
        capacity["cpu_cores"] = min(capacity["cpu_cores"], daemon["NCPU"])
        if capacity["memory_bytes"] is not None:
            capacity["memory_bytes"] = min(capacity["memory_bytes"], daemon["MemTotal"])
        cache = getattr(runner, "_software_probes", {})
        if runtime.image not in cache:
            out, _, _ = runner.execute(
                "/input/probe.py",
                {"probe.py": PROBE},
                image=runtime.image,
                timeout=20,
                memory_gb=runtime.memory_gb,
            )
            cache[runtime.image] = json.loads(out["probe.json"])["software"]
            runner._software_probes = cache
        return {**capacity, "available": True, "software": cache[runtime.image], "image": runtime.image}
    except Exception as exc:
        return {
            **capacity,
            "available": False,
            "reason": f"Runtime probe failed: {type(exc).__name__}",
            "failure_reason": getattr(exc, "reason", None)
            if getattr(exc, "reason", None)
            in ("cancelled", "timeout", "resource_exhaustion", "artifact_quota")
            else "unavailable_runtime",
        }


def assess(runner, plan, test, runtime):
    """No model fallback: return specific blockers and the explicitly available approximation."""
    spec = test.simulation
    descriptor = REGISTRY[spec.adapter] if spec else REGISTRY["authored-screen"]
    issues = []
    if spec:
        try:
            validate_plan_units(plan)
            convert(1, spec.cad_unit, spec.solver_length_unit, "length")
            if spec.cad_unit != "mm":
                raise ValueError("CadQuery/OCP STEP adapter uses millimetres; declare cad_unit mm")
        except ValueError as exc:
            issues.append({"reason": "invalid_units", "needed": str(exc)})
        if "v2" not in descriptor.routes:
            issues.append(
                {
                    "reason": "unsupported_physics",
                    "needed": "Use this fixed-family adapter through its legacy task; v2 bundle binding is not implemented",
                }
            )
        if not set(spec.phenomena) <= set(descriptor.phenomena) or spec.fidelity not in descriptor.fidelities:
            issues.append(
                {
                    "reason": "unsupported_physics",
                    "needed": "An independently verified adapter for the requested phenomena/fidelity",
                }
            )
        if spec.material_model not in descriptor.material_models:
            issues.append(
                {
                    "reason": "unsupported_material",
                    "needed": f"Adapter for material model {spec.material_model}",
                }
            )
        if any(i.region is None for i in plan.interfaces):
            issues.append(
                {
                    "reason": "invalid_binding",
                    "needed": "Fixed structured region rule for every physical interface",
                }
            )
        if spec.adapter == "mujoco-slider":
            from davinci.product.mechanism.adapter import estimate, setup
            from davinci.product.mechanism.contracts import SliderSettings

            try:
                prepared = setup(plan, test)
                computed = estimate(SliderSettings.model_validate(prepared["settings"]))
                for key in ("cpu_cores", "memory_mb", "disk_mb", "wall_seconds"):
                    if getattr(spec.estimate, key) < computed[key]:
                        issues.append(
                            {
                                "reason": "resource_exhaustion",
                                "needed": f"Declared estimate {key} below adapter workload estimate {computed[key]}",
                            }
                        )
            except ValueError as exc:
                issues.append({"reason": "invalid_binding", "needed": str(exc)})
        if spec.adapter == "calculix-static":
            from davinci.product.structural.adapter import setup

            try:
                setup(plan, test)
            except ValueError as exc:
                issues.append({"reason": "invalid_binding", "needed": str(exc)})
    # Deterministic fixture runners explicitly implement this seam; no host solver is inferred.
    probe = (
        runner.probe(runtime)
        if hasattr(runner, "probe")
        else {"available": True, "fixture": True, "software": {}}
    )
    if not probe.get("available"):
        issues.append(
            {
                "reason": probe.get("failure_reason", "unavailable_runtime"),
                "needed": probe.get("reason", "Available pinned runtime"),
            }
        )
    if runtime.accelerator != "none":
        issues.append(
            {
                "reason": "unsupported_physics",
                "needed": "An explicitly configured accelerator adapter/executor; GPU presence alone is insufficient",
            }
        )
    if runtime.backend != "docker":
        issues.append(
            {
                "reason": "unavailable_runtime",
                "needed": "An explicitly configured remote executor (not shipped)",
            }
        )
    software = {**(spec.required_software if spec else {}), **descriptor.required_software}
    if spec:
        for name, version in spec.required_software.items():
            pinned = descriptor.required_software.get(name)
            if pinned is not None and version != pinned:
                issues.append(
                    {
                        "reason": "missing_solver",
                        "needed": f"Adapter requires {name} {pinned}; a test cannot override that pin",
                    }
                )
            elif pinned is None:
                software[name] = version
    if not probe.get("fixture") and probe.get("available"):
        for name, version in software.items():
            actual = probe.get("software", {}).get(name)
            if actual is None or (version is not None and version != actual):
                issues.append(
                    {
                        "reason": "missing_solver",
                        "needed": f"{name} {version or '(importable/available)'} in pinned runtime",
                        "observed": actual,
                    }
                )
    if spec:
        estimate = spec.estimate
        limits = {
            "cpu_cores": min(runtime.cpu_cores, probe.get("cpu_cores", runtime.cpu_cores)),
            "memory_mb": min(
                runtime.memory_gb * 1024,
                (
                    probe["memory_bytes"]
                    if probe.get("memory_bytes") is not None
                    else runtime.memory_gb * 1024**3
                )
                / 1024**2,
            ),
            "disk_mb": probe.get("disk_bytes", estimate.disk_mb * 1024**2) / 1024**2,
            "wall_seconds": min(
                runtime.timeout_seconds, runtime.job_seconds, runtime.compute_seconds / runtime.cpu_cores
            ),
        }
        for key, limit in limits.items():
            if getattr(estimate, key) > limit:
                issues.append(
                    {
                        "reason": "resource_exhaustion",
                        "needed": f"Estimated {key}={getattr(estimate, key)} exceeds available {limit}",
                    }
                )
    return {
        "adapter": descriptor.model_dump(),
        "requirements": test.requirements,
        "test_id": test.id,
        "issues": issues,
        "available": not issues,
        "probe": probe,
        "estimate": spec.estimate.model_dump() if spec else None,
        "approximation_available": descriptor.fidelities,
        "substitution_performed": False,
        "adequacy": "Reference checks, per-geometry setup and actual execution still required",
    }
