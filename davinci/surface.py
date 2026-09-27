"""Versioned, isolated surface-tool API. Never imports secrets in CAD containers."""

import json
from pathlib import Path

from davinci.models import digest
from sandbox.surface_geometry import validate

SANDBOX = Path(__file__).resolve().parents[1] / "sandbox"
IMAGE = "da-vinci-vtol:local"
FILES = (
    "surface_geometry.py",
    "surface_physics.py",
    "surface_tools.py",
    "surface_xfoil.py",
    "evaluate_surface.py",
    "vtol_family.py",
    "vtol_physics.py",
    "vtol_spec.py",
)


def inputs():
    return {name: (SANDBOX / name).read_bytes() for name in FILES} | {
        "vtol_data/" + p.name: p.read_bytes() for p in (SANDBOX / "vtol_data").glob("*")
    }


def evaluator_version():
    return "surface-" + digest({k: digest(v.decode()) for k, v in inputs().items()})[:16]


def tool(runner, action, arguments):
    if "geometry" in arguments:
        validate(arguments["geometry"])
    files, log, seconds = runner.execute(
        "/input/surface_tools.py",
        inputs() | {"request.json": json.dumps({"action": action, "arguments": arguments})},
        timeout=240,
        image=IMAGE,
    )
    result = json.loads(files.pop("result.json"))
    result["elapsed_seconds"] = seconds
    return result, files


def evaluate(runner, geometry, resolution=6, nonlinear=False):
    validate(geometry)
    preview, built = tool(runner, "preview", {"geometry": geometry})
    files, log, seconds = runner.execute(
        "/input/evaluate_surface.py",
        inputs()
        | {
            "model.step": built["model.step"],
            "request.json": json.dumps(
                {"geometry": geometry, "resolution": resolution, "nonlinear": nonlinear}
            ),
        },
        timeout=3600 if nonlinear else 900,
        image=IMAGE,
    )
    result = json.loads(files.pop("result.json"))
    result["elapsed_seconds"] = seconds + preview["elapsed_seconds"]
    return result, {"model.step": built["model.step"], **files}


def crosscheck(runner, geometry, audit):
    files, _, _ = runner.execute(
        "/input/surface_xfoil.py",
        inputs() | {"request.json": json.dumps({"geometry": geometry, "audit": audit})},
        timeout=240,
        image=IMAGE,
    )
    return json.loads(files["result.json"])
