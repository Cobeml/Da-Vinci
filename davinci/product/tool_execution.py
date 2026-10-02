"""Narrow CAD construction capability; independent checks never execute tool source."""

import ast
import hashlib
import json
import math
import time
from importlib.resources import files

from davinci.models import digest
from davinci.product.tool_contracts import PlateArguments
from davinci.runner import SandboxError

RESOURCES = files("davinci.product").joinpath("resources/tools")


def references():
    # Established analytic plate-minus-cylinders cases, independent of proposed code.
    return [
        PlateArguments.model_validate(a).model_dump(mode="json")
        for a in [
            dict(length=40, width=24, thickness=3, radius=2, holes=[[-10, 0], [10, 0]]),
            dict(
                length=53.5,
                width=31.5,
                thickness=2.5,
                radius=1.25,
                holes=[[-12, 5], [7, -8]],
                translation=[11, -4, 6],
            ),
            dict(length=18, width=12, thickness=0.75, radius=0.75, holes=[[2, -1]], translation=[-8, 3, -2]),
            dict(length=90, width=65, thickness=12, radius=3.5, holes=[[-30, -15], [4, 12], [25, -14]]),
        ]
    ]


def descriptor():
    return {
        "class": "perforated_plate_v1",
        "version": 1,
        "capabilities": [
            "construct a single rectangular solid with circular Z through-holes",
            "translate solid",
            "return STEP via trusted wrapper",
        ],
        "input_schema": PlateArguments.model_json_schema(),
        "output_contract": {
            "model.step": "one valid solid, centered XY, base Z=0 before translation; independently inspected"
        },
        "limitations": [
            "design helper only; no stress/physics results",
            "no evaluator, file, network or process access",
            "no caller dependencies or test replacement",
        ],
        "reference_basis": "V=L*W*t-n*pi*r^2*t; analytic bounds; circular edge centers/radii on both faces; solid topology",
        "tolerance": {"relative_volume": 1e-7, "absolute_geometry_mm": 1e-6},
        "reference_cases": references(),
        "required_software": {"cadquery": "2.8.0"},
    }


def implementation_identity():
    sources = {n: RESOURCES.joinpath(n).read_text() for n in ("construct.py", "inspect_geometry.py")}
    sources["tool_execution.py"] = files("davinci.product").joinpath("tool_execution.py").read_text()
    sources["tool_contracts.py"] = files("davinci.product").joinpath("tool_contracts.py").read_text()
    return digest(sources)


def check_source(source):
    """Capability allowlist, in addition to (never instead of) the Docker boundary."""
    tree = ast.parse(source)
    allowed_nodes = {
        "Module",
        "Import",
        "alias",
        "FunctionDef",
        "arguments",
        "arg",
        "Return",
        "Assign",
        "Expr",
        "Name",
        "Load",
        "Store",
        "Constant",
        "Subscript",
        "Tuple",
        "List",
        "Dict",
        "Call",
        "keyword",
        "Attribute",
        "BinOp",
        "UnaryOp",
        "Add",
        "Sub",
        "Mult",
        "Div",
        "USub",
        "UAdd",
        "If",
        "Raise",
        "Compare",
        "Eq",
        "NotEq",
        "Lt",
        "LtE",
        "Gt",
        "GtE",
        "BoolOp",
        "And",
        "Or",
        "Not",
        "For",
        "IfExp",
        "ListComp",
        "comprehension",
    }
    attrs = {
        "Workplane",
        "box",
        "pushPoints",
        "circle",
        "extrude",
        "cut",
        "translate",
        "union",
        "isfinite",
        "sqrt",
    }
    builtins = {"len", "range", "float", "tuple", "list", "abs", "ValueError"}
    definitions = [n for n in tree.body if isinstance(n, ast.FunctionDef)]
    if (
        len(definitions) != 1
        or definitions[0].name != "run"
        or any(not isinstance(n, (ast.Import, ast.FunctionDef)) for n in tree.body)
    ):
        raise ValueError("Helper must contain imports and exactly one run(arguments) function")
    f = definitions[0]
    if (
        f.decorator_list
        or f.returns
        or f.args.defaults
        or f.args.kwonlyargs
        or f.args.posonlyargs
        or f.args.vararg
        or f.args.kwarg
        or len(f.args.args) != 1
        or f.args.args[0].annotation
    ):
        raise ValueError("Plain run(arguments) signature required")
    for n in ast.walk(tree):
        if type(n).__name__ not in allowed_nodes:
            raise ValueError("Unsupported helper syntax: " + type(n).__name__)
        if isinstance(n, ast.Import) and any(
            (a.name, a.asname) not in {("cadquery", "cq"), ("math", None)} for a in n.names
        ):
            raise ValueError("Only cadquery as cq and math imports allowed")
        if isinstance(n, ast.Attribute) and n.attr not in attrs:
            raise ValueError("Undeclared CAD helper capability: " + n.attr)
        if isinstance(n, ast.Name) and (
            n.id.startswith("_")
            or n.id
            in {
                "open",
                "exec",
                "eval",
                "compile",
                "getattr",
                "setattr",
                "globals",
                "locals",
                "type",
                "print",
                "input",
            }
        ):
            raise ValueError("Forbidden helper name")
        if isinstance(n, ast.Call) and not (
            isinstance(n.func, ast.Attribute) or isinstance(n.func, ast.Name) and n.func.id in builtins
        ):
            raise ValueError("Undeclared callable")
        if isinstance(n, ast.Assign) and any(not isinstance(t, (ast.Name, ast.Tuple)) for t in n.targets):
            raise ValueError("Helper cannot assign attributes or mutate arguments")
    return tree


def check_measurement(args, measured):
    a = PlateArguments.model_validate(args)
    dx, dy, dz = a.translation
    expected_bounds = [
        dx - a.length / 2,
        dy - a.width / 2,
        dz,
        dx + a.length / 2,
        dy + a.width / 2,
        dz + a.thickness,
    ]
    expected_volume = (a.length * a.width - len(a.holes) * math.pi * a.radius**2) * a.thickness
    expected_circles = sorted(
        [[x + dx, y + dy, z, a.radius] for x, y in a.holes for z in (dz, dz + a.thickness)]
    )
    circles = sorted(measured.get("circles", []))
    checks = {
        "valid_connected_solid": measured.get("valid") is True and measured.get("solids") == 1,
        "analytic_volume": math.isclose(
            measured.get("volume", -1), expected_volume, rel_tol=1e-7, abs_tol=1e-7
        ),
        "bounds": len(measured.get("bounds", [])) == 6
        and all(abs(x - y) < 1e-6 for x, y in zip(expected_bounds, measured["bounds"])),
        "hole_edges": len(circles) == len(expected_circles)
        and all(
            len(c) == 4 and all(abs(x - y) < 1e-6 for x, y in zip(c, e))
            for c, e in zip(circles, expected_circles)
        ),
    }
    return {
        "passed": all(checks.values()),
        "checks": checks,
        "expected_volume": expected_volume,
        "measured": measured,
    }


def execute(runner, version, cases):
    check_source(version["source"])
    runtime = version["runtime"]
    started = time.monotonic()
    outputs, logs = {}, []

    def call(entry, payload, prefix):
        remaining = min(
            runtime["timeout_seconds"],
            runtime["job_seconds"] - (time.monotonic() - started),
            runtime["compute_seconds"] / runtime["cpu_cores"] - (time.monotonic() - started),
        )
        if remaining <= 0:
            raise SandboxError("Tool effort exhausted", reason="resource_exhaustion")
        try:
            out, log, _ = runner.execute(
                entry,
                payload,
                timeout=remaining,
                **{
                    k: runtime[k]
                    for k in ("image", "memory_gb", "cpu_cores", "artifact_bytes", "file_bytes", "log_bytes")
                },
            )
        except SandboxError as exc:
            outputs.update({prefix + k: v for k, v in exc.outputs.items()})
            exc.outputs = outputs
            exc.log = "\n".join([*logs, exc.log])
            raise
        logs.append(log)
        outputs.update({prefix + k: v for k, v in out.items()})
        return out

    made = call(
        "/input/construct.py",
        {
            "construct.py": RESOURCES.joinpath("construct.py").read_text(),
            "helper.py": version["source"],
            "arguments.json": json.dumps(cases),
        },
        "built-",
    )
    expected = {f"model-{i}.step" for i in range(len(cases))}
    if set(made) - {"resources.json"} != expected:
        raise SandboxError("Unexpected helper artifacts", reason="invalid_result", outputs=outputs)
    inspected = call(
        "/input/inspect_geometry.py",
        {
            "inspect_geometry.py": RESOURCES.joinpath("inspect_geometry.py").read_text(),
            **{k: made[k] for k in expected},
        },
        "checked-",
    )
    report = json.loads(inspected["measurements.json"])
    if report.get("cadquery") != "2.8.0" or len(report.get("items", [])) != len(cases):
        raise SandboxError("Incompatible CAD runtime/output", reason="invalid_result", outputs=outputs)
    checks = [check_measurement(a, m) for a, m in zip(cases, report["items"])]
    outputs["checks.json"] = json.dumps(
        {"checks": checks, "passed": all(c["passed"] for c in checks)}
    ).encode()
    outputs["resources.json"] = json.dumps(
        {
            "elapsed_seconds": time.monotonic() - started,
            "limits": runtime,
            "software": {"cadquery": report["cadquery"]},
        }
    ).encode()
    if sum(map(len, outputs.values())) > runtime["artifact_bytes"]:
        raise SandboxError("Combined tool evidence quota exceeded", reason="artifact_quota", outputs=outputs)
    return checks, outputs, "\n".join(logs)


def source_hash(source):
    return hashlib.sha256(source.encode()).hexdigest()
