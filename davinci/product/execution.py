"""Independent physical execution and fail-closed scoring shared by lifecycle drivers."""

import json
from importlib.resources import files

from davinci.errors import safe_error
from davinci.models import digest
from davinci.product.contracts import TestResult
from davinci.product.tasks import SANDBOX
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
        for name in ("contracts.py", "execution.py", "lifecycle.py")
    }
    sources["runner.py"] = files("davinci").joinpath("runner.py").read_text()
    sources["build.py"] = SANDBOX.joinpath("build.py").read_text()
    return digest(sources), sources


def failure(test_id, status, reason, message=""):
    return TestResult(test_id=test_id, status=status, reason=reason, message=message[:4000])


def execution_failure(test_id, exc, *, building=False):
    reason = getattr(exc, "reason", None)
    if reason in ("cancelled", "timeout", "resource_exhaustion"):
        return failure(test_id, "not_run", reason, safe_error(exc))
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


def build(runner, candidate, plan, runtime):
    outputs, log, duration = runner.execute(
        "/input/_build.py",
        {
            "_build.py": SANDBOX.joinpath("build.py").read_text(),
            "source.py": candidate.source,
            "request.json": json.dumps(
                {"parameters": candidate.parameters, "interfaces": [i.model_dump() for i in plan.interfaces]}
            ),
        },
        image=runtime.image,
        timeout=runtime.timeout_seconds,
        memory_gb=runtime.memory_gb,
    )
    if not outputs.get("model.step"):
        raise SandboxError("Builder did not produce STEP", reason="build_failed")
    # Never forward builder-supplied result.json, Python files, or solver artifacts.
    return outputs["model.step"], log, duration


def evaluate_test(runner, step, plan, test, evaluator, runtime):
    request = {
        "test": test.model_dump(),
        "materials": [m.model_dump() for m in plan.materials],
        "interfaces": [i.model_dump() for i in plan.interfaces],
        "assumptions": [a.model_dump() for a in plan.assumptions],
    }
    try:
        outputs, log, duration = runner.execute(
            "/input/_evaluate.py",
            {
                **evaluator.resources,
                "_evaluate.py": EVALUATE,
                "model.step": step,
                "request.json": json.dumps(request),
            },
            image=runtime.image,
            timeout=runtime.timeout_seconds,
            memory_gb=runtime.memory_gb,
        )
        try:
            result = score(test, plan, json.loads(outputs["result.json"]))
        except (ValueError, KeyError, TypeError) as exc:
            result = failure(test.id, "invalid_setup", "invalid_result", safe_error(exc))
        return result, outputs, log, duration
    except (SandboxError, OSError) as exc:
        return execution_failure(test.id, exc), {}, safe_error(exc), 0
