"""Frozen isolated VTOL study interface."""

import json
from pathlib import Path

from davinci.models import digest
from sandbox.vtol_family import validate
from sandbox.vtol_spec import SPECIFICATION

SANDBOX = Path(__file__).resolve().parents[1] / "sandbox"
IMAGE = "da-vinci-vtol:local"
REFERENCE_SOURCE = "from vtol_family import build_vtol\n\ndef build(parameters, interfaces):\n    return build_vtol(parameters)\n"
FILES = ("vtol_family.py", "vtol_physics.py", "vtol_spec.py", "evaluate_vtol.py")


def evaluator_version():
    return (
        "vtol-"
        + digest(
            {n: (SANDBOX / n).read_text() for n in FILES}
            | {p.name: p.read_text() for p in (SANDBOX / "vtol_data").glob("*")}
        )[:16]
    )


def evaluate(runner, source, parameters, resolution=10):
    validate(parameters)
    req = json.dumps({"parameters": parameters, "interfaces": SPECIFICATION, "resolution": resolution})
    built, _, _ = runner.execute(
        "/input/build.py",
        {
            "build.py": (SANDBOX / "build.py").read_text(),
            "source.py": source,
            "vtol_family.py": (SANDBOX / "vtol_family.py").read_text(),
            "request.json": req,
        },
        timeout=180,
        image=IMAGE,
    )
    files = {n: (SANDBOX / n).read_text() for n in FILES}
    files.update({"vtol_data/" + p.name: p.read_bytes() for p in (SANDBOX / "vtol_data").glob("*")})
    measured, _, _ = runner.execute(
        "/input/evaluate_vtol.py",
        files | {"model.step": built["model.step"], "request.json": req},
        timeout=600,
        image=IMAGE,
    )
    return json.loads(measured.pop("result.json")), {"model.step": built["model.step"], **measured}
