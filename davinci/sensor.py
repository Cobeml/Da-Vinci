"""Versioned sensor-cradle study, isolated from the original plate/wing evaluator."""

import json
from pathlib import Path

from davinci.models import digest

SANDBOX = Path(__file__).resolve().parents[1] / "sandbox"
SPECIFICATION = {
    "_id": "sensor-cradle-pa12-v1", "material": "PA12 (nominal)",
    "density_g_mm3": .00101, "youngs_modulus_mpa": 1700,
    "load_n": 20, "allowable_stress_mpa": 28, "max_deflection_mm": .65,
    "max_mass_g": 100, "footprint_mm": [100, 72], "bolt_pattern_mm": [80, 52],
    "sensor_diameter_mm": 32, "sensor_width_mm": 48,
}
REFERENCE_SOURCE = '''import cadquery as cq
from sensor_family import build_cradle

def build(parameters, interfaces):
    assembly = cq.Assembly(name="sensor_cradle")
    assembly.add(build_cradle(parameters), name="mount", color=cq.Color(.9, .4, .14))
    return assembly
'''


def evaluator_version():
    return "sensor-" + digest({
        "specification": SPECIFICATION,
        "sources": {name: (SANDBOX / name).read_text() for name in ("sensor_family.py", "evaluate_sensor.py")},
    })[:12]


def evaluate(runner, source, parameters):
    from sandbox.sensor_family import validate

    validate(parameters)
    request = json.dumps({"parameters": parameters, "interfaces": SPECIFICATION, "specification": SPECIFICATION})
    built, _, _ = runner.execute("/input/build.py", {
        "build.py": (SANDBOX / "build.py").read_text(),
        "source.py": source, "sensor_family.py": (SANDBOX / "sensor_family.py").read_text(),
        "request.json": request,
    })
    outputs, _, _ = runner.execute("/input/evaluate_sensor.py", {
        "model.step": built["model.step"], "request.json": request,
        "sensor_family.py": (SANDBOX / "sensor_family.py").read_text(),
        "evaluate_sensor.py": (SANDBOX / "evaluate_sensor.py").read_text(),
    })
    return json.loads(outputs["result.json"]), {"model.step": built["model.step"], "model.glb": outputs["model.glb"]}
