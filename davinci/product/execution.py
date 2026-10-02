"""Independent physical execution and fail-closed scoring shared by lifecycle drivers."""

import json
import time
from importlib.resources import files

from davinci.errors import safe_error
from davinci.models import digest
from davinci.product.adapters import assess
from davinci.product.contracts import TestResult
from davinci.product.evidence import ensure_output_budget
from davinci.product.regions import bind_regions
from davinci.product.tasks import SANDBOX
from davinci.product.units import convert
from davinci.runner import SandboxError

EVALUATE = """import json
from pathlib import Path
from evaluate import evaluate
request = json.loads(Path('/input/request.json').read_text())
result = evaluate('/input/model.step', request)
Path('/output/result.json').write_text(json.dumps(result, allow_nan=False))
"""


def execution_identity():
    """Pin host scoring/wrapper and sandbox implementation along with task code."""
    sources = {
        name: files("davinci.product").joinpath(name).read_text()
        for name in (
            "contracts.py",
            "execution.py",
            "lifecycle.py",
            "adapters.py",
            "simulation_contracts.py",
            "units.py",
            "regions.py",
            "evidence.py",
            "recipes.py",
            "managed_contracts.py",
            "structural/contracts.py",
            "structural/adapter.py",
            "structural/solver.py",
        )
    }
    sources["inspect_regions.py"] = (
        files("davinci.product").joinpath("resources/inspect_regions.py").read_text()
    )
    sources["preview.py"] = files("davinci.product").joinpath("resources/preview.py").read_text()
    sources["runner.py"] = files("davinci").joinpath("runner.py").read_text()
    sources["build.py"] = SANDBOX.joinpath("build.py").read_text()
    return digest(sources), sources


def failure(test_id, status, reason, message=""):
    return TestResult(test_id=test_id, status=status, reason=reason, message=message[:4000])


def execution_failure(test_id, exc, *, building=False):
    reason = getattr(exc, "reason", None)
    if reason in ("cancelled", "timeout", "resource_exhaustion", "artifact_quota"):
        return failure(test_id, "not_run", reason, safe_error(exc))
    if reason in ("invalid_binding", "invalid_units", "invalid_result"):
        return failure(test_id, "invalid_setup", reason, safe_error(exc))
    if reason == "unavailable_runtime" or isinstance(exc, OSError):
        return failure(test_id, "unsupported_capability", "unavailable_runtime", safe_error(exc))
    return failure(
        test_id,
        "invalid_setup" if building else "numerical_failure",
        "build_failed" if building else "solver_error",
        safe_error(exc),
    )


def score(test, plan, raw):
    """The evaluator measures; the host enforces frozen limits and completeness."""
    result = TestResult.model_validate(raw)
    if result.test_id != test.id:
        raise ValueError("Result test identity mismatch")
    if result.status not in ("pass", "physical_failure"):
        return result
    if not result.applicable:
        return failure(test.id, "unsupported_capability", "unsupported_physics")
    if not result.mesh_valid or any(result.bindings.get(i.id) is not True for i in plan.interfaces):
        return failure(test.id, "invalid_setup", "invalid_binding")
    if not set(test.metrics) <= result.metrics.keys():
        return failure(test.id, "not_run", "missing_evidence")
    for name, unit in test.metrics.items():
        measured, required = result.metrics[name], test.accuracy[name]
        if measured.unit != unit:
            if test.simulation:
                try:
                    measured.value = convert(measured.value, measured.unit, unit)
                    measured.numerical_error = convert(measured.numerical_error, measured.unit, unit)
                    measured.uncertainty = convert(measured.uncertainty, measured.unit, unit)
                    measured.unit = unit
                except ValueError:
                    return failure(test.id, "invalid_setup", "invalid_units", "Metric dimension mismatch")
            else:
                return failure(test.id, "invalid_setup", "invalid_result", "Metric unit mismatch")
        if (
            measured.numerical_error > required.max_numerical_error
            or measured.uncertainty > required.max_uncertainty
        ):
            return failure(
                test.id, "numerical_failure", "missing_evidence", "Accuracy/uncertainty requirement unmet"
            )
    for criterion in test.criteria:
        m = result.metrics[criterion.metric]
        # Conservative bounds: uncertainty cannot create a pass at the threshold.
        error = m.uncertainty + m.numerical_error
        if (
            m.value + error > criterion.limit
            if criterion.operator == "<="
            else m.value - error < criterion.limit
        ):
            result.status, result.reason = "physical_failure", "acceptance_limit"
    return result


def limits(runtime):
    if runtime.backend != "docker" or runtime.accelerator != "none":
        raise SandboxError(
            "Requested execution backend/accelerator is not configured", reason="unavailable_runtime"
        )
    return dict(
        image=runtime.image,
        timeout=min(
            runtime.timeout_seconds, runtime.job_seconds, runtime.compute_seconds / runtime.cpu_cores
        ),
        memory_gb=runtime.memory_gb,
        cpu_cores=runtime.cpu_cores,
        artifact_bytes=runtime.artifact_bytes,
        file_bytes=runtime.file_bytes,
        log_bytes=runtime.log_bytes,
    )


def build(runner, candidate, plan, runtime, evidence=None):
    outputs, log, duration = runner.execute(
        "/input/_build.py",
        {
            "_build.py": SANDBOX.joinpath("build.py").read_text(),
            "source.py": candidate.source,
            "request.json": json.dumps(
                {"parameters": candidate.parameters, "interfaces": [i.model_dump() for i in plan.interfaces]}
            ),
        },
        **limits(runtime),
    )
    if evidence is not None:
        evidence.update(outputs)
    ensure_output_budget(outputs, runtime)
    if not outputs.get("model.step"):
        raise SandboxError("Builder did not produce STEP", reason="build_failed")
    # Never forward builder-supplied result.json, Python files, or solver artifacts.
    return outputs["model.step"], log, duration


def evaluate_test(runner, step, plan, test, evaluator, runtime):
    started = time.monotonic()
    outputs, logs = {}, []
    elapsed = 0
    request = {
        "test": test.model_dump(),
        "materials": [m.model_dump() for m in plan.materials],
        "interfaces": [i.model_dump() for i in plan.interfaces],
        "assumptions": [a.model_dump() for a in plan.assumptions],
    }
    assessment = assess(runner, plan, test, runtime)
    outputs["capability.json"] = json.dumps(assessment).encode()
    if assessment["issues"]:
        issue = assessment["issues"][0]
        reason = issue["reason"]
        status = (
            "invalid_setup"
            if reason in ("invalid_units", "invalid_binding")
            else "not_run"
            if reason in ("resource_exhaustion", "cancelled", "timeout", "artifact_quota")
            else "unsupported_capability"
        )
        return failure(test.id, status, reason, issue["needed"]), outputs, "", 0
    bindings = None
    prepared = {}

    def execute(entry, inputs):
        nonlocal elapsed
        remaining = min(runtime.job_seconds, runtime.compute_seconds / runtime.cpu_cores) - max(
            elapsed, time.monotonic() - started
        )
        if remaining <= 0:
            raise SandboxError("Job time/compute budget exhausted", reason="resource_exhaustion")
        options = limits(runtime)
        options["timeout"] = min(options["timeout"], remaining)
        out, log, seconds = runner.execute(entry, inputs, **options)
        logs.append(log)
        elapsed += seconds
        return out

    try:
        if test.simulation:
            spec = test.simulation
            scale = convert(1, spec.cad_unit, spec.solver_length_unit, "length")
            prepared = execute(
                "/input/_regions.py",
                {
                    "_regions.py": files("davinci.product")
                    .joinpath("resources/inspect_regions.py")
                    .read_text(),
                    "model.step": step,
                    "preparation.json": json.dumps({"cad_to_solver_scale": scale}),
                },
            )
            # Independently inspected CAD; neither candidate hints nor evaluator selections are consulted.
            faces = json.loads(prepared["faces.json"])
            bindings, bound = bind_regions(plan.interfaces, faces, spec.cad_unit)
            outputs.update({"prepare-" + k: v for k, v in prepared.items()})
            outputs["bindings.json"] = json.dumps(bound).encode()
            request["geometry"] = {
                "cad_step": "/input/model.step",
                "solver_step": "/input/solver.step",
                "cad_unit": spec.cad_unit,
                "solver_length_unit": spec.solver_length_unit,
                "cad_to_solver_scale": scale,
            }
            request["validated_bindings"] = bound
            if spec.adapter == "calculix-static":
                request["measured_geometry"] = json.loads(prepared["geometry.json"])
            recipe_geometry = None
            if plan.metadata.get("recipe") == "rectangular-beam-v1":
                from davinci.product.recipes import check_geometry

                recipe_geometry = json.loads(prepared["geometry.json"])
                if not check_geometry(plan, recipe_geometry):
                    return (
                        failure(
                            test.id,
                            "invalid_setup",
                            "invalid_geometry",
                            "Independent BRep recipe check failed",
                        ),
                        outputs,
                        "\n".join(logs),
                        elapsed,
                    )
            if not all(bindings.values()):
                return (
                    failure(
                        test.id, "invalid_setup", "invalid_binding", "Missing or ambiguous semantic region"
                    ),
                    outputs,
                    "\n".join(logs),
                    elapsed,
                )
        inputs = {
            **evaluator.resources,
            "_evaluate.py": EVALUATE,
            "model.step": step,
            **({"solver.step": prepared["solver.step"]} if prepared else {}),
            "request.json": json.dumps(request),
        }
        if test.simulation and test.simulation.adapter == "calculix-static":
            from davinci.product.structural.adapter import setup, source

            request["structural"] = setup(plan, test)
            request["runtime_limits"] = {"memory_gb": runtime.memory_gb}
            # Host-owned solver/deck generation only. Authored evaluators cannot override it.
            inputs = {"_structural.py": source(), "model.step": step, "request.json": json.dumps(request)}
            entrypoint = "/input/_structural.py"
        else:
            entrypoint = "/input/_evaluate.py"
        measured = execute(entrypoint, inputs)
        # Preserve raw output, including solver decks/fields. Raw reported scores are not trusted scores.
        outputs.update(measured)
        # Host-owned capability/binding provenance must not be overwritten by evaluator output.
        outputs["capability.json"] = json.dumps(assessment).encode()
        if bindings is not None:
            outputs["bindings.json"] = json.dumps(bound).encode()
        try:
            raw = json.loads(measured["result.json"])
            if bindings is not None:
                raw["bindings"] = bindings
            result = score(test, plan, raw)
            if plan.metadata.get("recipe") == "rectangular-beam-v1" and result.status in (
                "pass",
                "physical_failure",
            ):
                from davinci.product.recipes import check_measurements

                if not check_measurements(plan, recipe_geometry, result):
                    result = failure(
                        test.id,
                        "invalid_setup",
                        "verification_failed",
                        "Evaluator differs from independent analytic recipe",
                    )
        except (ValueError, KeyError, TypeError) as exc:
            result = failure(test.id, "invalid_setup", "invalid_result", safe_error(exc))
        if test.simulation:
            # Host stamps the actual prescribed stage/fidelity, never a candidate-provided assertion.
            result.metadata = {
                "adapter": test.simulation.adapter,
                "fidelity": test.simulation.fidelity,
                "stage": test.simulation.stage,
                "cad_to_solver_scale": scale,
            }
            expected = {
                "mesh": (".msh",),
                "solver_deck": (".inp", ".dat"),
                "fields": (".vtk", ".vtu", ".npz", ".csv"),
                "convergence": ("convergence.json",),
                "uncertainty": ("uncertainty.json",),
            }
            missing = [
                kind
                for kind in test.simulation.required_evidence
                if not any(name.endswith(expected[kind]) and data for name, data in measured.items())
            ]
            if missing and result.status in ("pass", "physical_failure"):
                result = failure(
                    test.id, "not_run", "missing_evidence", "Missing required evidence: " + ", ".join(missing)
                )
        outputs["timing.json"] = json.dumps(
            {
                "duration_seconds": elapsed,
                "allocated_cpu_seconds_upper_bound": elapsed * runtime.cpu_cores,
                "estimated": test.simulation.estimate.model_dump() if test.simulation else None,
                "refinement": "Measured wall time and output size; memory peak and convergence not inferred",
            }
        ).encode()
        ensure_output_budget(outputs, runtime)
        return result, outputs, "\n".join(logs), elapsed
    except (SandboxError, OSError) as exc:
        outputs.update(getattr(exc, "outputs", {}))
        logs.append(getattr(exc, "log", "") or safe_error(exc))
        return (
            execution_failure(test.id, exc),
            outputs,
            "\n".join(logs),
            elapsed + getattr(exc, "duration", 0),
        )
    except (ValueError, KeyError, TypeError) as exc:
        return (
            failure(test.id, "invalid_setup", "invalid_binding", safe_error(exc)),
            outputs,
            "\n".join(logs),
            elapsed,
        )


def preview(runner, step, runtime, *, elapsed=0):
    """Optional display artifact; failure is retained but cannot supply physical scores."""
    remaining = min(runtime.job_seconds, runtime.compute_seconds / runtime.cpu_cores) - elapsed
    if remaining <= 0:
        return {"preview-error.txt": b"Preview skipped: execution budget exhausted"}, "", 0
    options = limits(runtime)
    options["timeout"] = min(options["timeout"], remaining)
    try:
        outputs, log, duration = runner.execute(
            "/input/_preview.py",
            {
                "_preview.py": files("davinci.product").joinpath("resources/preview.py").read_text(),
                "model.step": step,
            },
            **options,
        )
        ensure_output_budget(outputs, runtime)
        return {k: v for k, v in outputs.items() if k == "model.glb"}, log, duration
    except (SandboxError, OSError) as exc:
        return {"preview-error.txt": safe_error(exc).encode()}, "", getattr(exc, "duration", 0)
