"""Task snapshots contain only explicit CAD inputs, never workspace secrets."""

import json
import math
from importlib.resources import files
from pathlib import Path

from jsonschema import Draft202012Validator, validate

from davinci.models import digest
from davinci.product.config import RunConfig
from davinci.runner import SandboxError

RESOURCES = files("davinci.product").joinpath("resources")
SANDBOX = files("sandbox")


def builtin(name):
    if name not in ("sensor", "gripper", "vtol"):
        raise ValueError("Unknown template")
    return json.loads(RESOURCES.joinpath(f"templates/{name}.json").read_text())


def template_config(name):
    return {
        "version": 1,
        "object": {
            "slug": f"my-{name}",
            "name": {
                "sensor": "Sensor mount",
                "gripper": "Parallel gripper",
                "vtol": "Survey VTOL",
                "custom": "Custom component",
            }[name],
        },
        "task": {
            "template": name,
            "description": "Increase estimated range while preserving speed and payload."
            if name == "vtol"
            else "Reduce mass while preserving the fixed interfaces and passing all engineering checks.",
            **({"path": "task"} if name == "custom" else {}),
        },
        "objective": {
            "metric": "range_km" if name == "vtol" else "mass_g",
            "direction": "maximize" if name == "vtol" else "minimize",
        },
        "constraints": [],
        "run": {"iterations": 6, "budget_usd": 10, "mode": "live"},
    }


def snapshot(config: RunConfig, workspace: Path):
    name = config.task.template
    if name != "custom":
        if config.task.path:
            raise ValueError("task.path is only supported for custom tasks")
        task = builtin(name)
        sources = {f: SANDBOX.joinpath(f).read_text() for f in task["files"]}
        if name == "vtol":
            sources.update(
                {
                    "vtol_data/" + p.name: p.read_text()
                    for p in SANDBOX.joinpath("vtol_data").iterdir()
                    if p.is_file()
                }
            )
        task["resources"] = sources
        task["tool_test_source"] = RESOURCES.joinpath("tool_check.py").read_text()
    else:
        folder = (workspace / (config.task.path or "task")).resolve()
        if not folder.is_relative_to(workspace.resolve()):
            raise ValueError("Custom task must be inside the workspace")
        task = json.loads((folder / "task.json").read_text())
        required = {"name", "baseline", "parameters_schema", "metrics", "specification", "image"}
        if not required.issubset(task):
            raise ValueError("Custom manifest requires " + ", ".join(sorted(required)))
        sources = {}
        if task.get("tool_contract") and "tool_check.py" not in task.get("files", []):
            raise ValueError("Custom tool_contract requires trusted tool_check.py in files")
        for name in ["build.py", "evaluate.py", *task.get("files", [])]:
            path = (folder / name).resolve()
            if (
                not path.is_relative_to(folder)
                or path.suffix not in (".py", ".json", ".txt")
                or path.name.startswith(".")
            ):
                raise ValueError("Invalid custom resource path")
            sources[name] = path.read_text()
        if sum(len(v.encode()) for v in sources.values()) > 2_000_000:
            raise ValueError("Custom task exceeds 2 MB source limit")
        if task.get("tool_contract"):
            task["tool_test_source"] = sources["tool_check.py"]
        task.update(
            source=sources.pop("build.py"), resources=sources, entrypoint="_evaluate_custom.py", timeout=180
        )
        task["resources"]["_evaluate_custom.py"] = RESOURCES.joinpath("evaluate_custom.py").read_text()
    Draft202012Validator.check_schema(task["parameters_schema"])
    validate(task["baseline"], task["parameters_schema"])
    json.dumps(task, allow_nan=False)
    if not task["metrics"] or not all(isinstance(v, str) for v in task["metrics"].values()):
        raise ValueError("Metric definitions map names to unit strings")
    task["resources"]["_build.py"] = SANDBOX.joinpath("build.py").read_text()
    if config.objective.metric not in task["metrics"]:
        raise ValueError("Unknown objective metric")
    for c in config.constraints:
        if task["metrics"].get(c.metric) != c.unit:
            raise ValueError(f"Unknown metric or wrong unit: {c.metric}")
    task["version"] = digest(task)
    return task


def check_parameters(task, parameters):
    json.dumps(parameters, allow_nan=False)
    validate(parameters, task["parameters_schema"])


def score_evaluation(task, config, evaluation):
    """Fail closed: geometry failures and missing metrics cannot win."""
    if evaluation.get("outcome") not in ("passed", "failed") or not isinstance(
        evaluation.get("violations"), list
    ):
        raise ValueError("Evaluator must return outcome and violations")
    metrics = evaluation.get("metrics", {})
    for key, m in metrics.items():
        if key not in task["metrics"]:
            continue
        if (
            type(m.get("value")) not in (int, float)
            or not math.isfinite(m["value"])
            or m.get("unit") != task["metrics"][key]
        ):
            raise ValueError(f"Invalid evaluator metric: {key}")
    required = {config.objective.metric, *(c.metric for c in config.constraints)}
    for key in required - metrics.keys():
        evaluation["violations"].append({"code": "MISSING_METRIC", "message": f"No valid {key} result"})
    for c in config.constraints:
        v = metrics.get(c.metric, {}).get("value")
        if v is not None and (v > c.value if c.operator == "<=" else v < c.value):
            evaluation["violations"].append(
                {"code": "USER_CONSTRAINT", "message": f"{c.metric} must be {c.operator} {c.value} {c.unit}"}
            )
    if evaluation["violations"]:
        evaluation["outcome"] = "failed"
    return evaluation


def evaluate(runner, task, parameters, source, image):
    check_parameters(task, parameters)
    request = json.dumps(
        {
            "parameters": parameters,
            "interfaces": task["specification"],
            "specification": task["specification"],
            "resolution": 10,
        }
    )
    resources = task["resources"]
    built, _, _ = runner.execute(
        "/input/_build.py",
        resources | {"source.py": source, "request.json": request},
        image=image,
        timeout=180,
    )
    try:
        measured, _, _ = runner.execute(
            "/input/" + task["entrypoint"],
            resources | {"model.step": built["model.step"], "request.json": request},
            image=image,
            timeout=task["timeout"],
        )
    except SandboxError as exc:
        return {
            "outcome": "failed",
            "metrics": {},
            "violations": [{"code": "EVALUATION_ERROR", "message": str(exc)[:2000]}],
            "fidelity": "not_evaluated",
        }, {"model.step": built["model.step"]}
    return json.loads(measured.pop("result.json")), {"model.step": built["model.step"], **measured}
