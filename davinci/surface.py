"""Versioned, isolated surface-tool API. Never imports secrets in CAD containers."""

import json
import subprocess
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


def evaluator_version(bundle=None):
    return "surface-" + digest({k: digest(v.decode()) for k, v in (bundle or inputs()).items()})[:16]


def image_digest():
    return subprocess.check_output(
        ["docker", "image", "inspect", "--format={{.Id}}", IMAGE], text=True
    ).strip()


def tool(runner, action, arguments, *, bundle=None, image=None):
    if "geometry" in arguments:
        validate(arguments["geometry"])
    files, log, seconds = runner.execute(
        "/input/surface_tools.py",
        (bundle or inputs()) | {"request.json": json.dumps({"action": action, "arguments": arguments})},
        timeout=240,
        image=image or image_digest(),
    )
    result = json.loads(files.pop("result.json"))
    result["elapsed_seconds"] = seconds
    return result, files


def evaluate(runner, geometry, resolution=6, nonlinear=False):
    validate(geometry)
    bundle = inputs()
    image = image_digest()
    execution = dict(
        geometry_digest=digest(geometry),
        evaluator_version=evaluator_version(bundle),
        image_digest=image,
        resolution=resolution,
        nonlinear=nonlinear,
    )
    preview, built = tool(runner, "preview", {"geometry": geometry}, bundle=bundle, image=image)
    files, log, seconds = runner.execute(
        "/input/evaluate_surface.py",
        bundle
        | {
            "model.step": built["model.step"],
            "request.json": json.dumps(
                {"geometry": geometry, "resolution": resolution, "nonlinear": nonlinear}
            ),
        },
        timeout=3600 if nonlinear else 900,
        image=image,
    )
    result = json.loads(files.pop("result.json"))
    result["elapsed_seconds"] = seconds + preview["elapsed_seconds"]
    result["execution"] = execution
    return result, {"model.step": built["model.step"], **files}


def crosscheck(runner, geometry, audit):
    files, _, _ = runner.execute(
        "/input/surface_xfoil.py",
        inputs() | {"request.json": json.dumps({"geometry": geometry, "audit": audit})},
        timeout=240,
        image=image_digest(),
    )
    return json.loads(files["result.json"])
