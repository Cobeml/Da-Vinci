"""Independent STEP measurement plus conservative cradle screening. Never imports agent source."""

import json
from pathlib import Path

import cadquery as cq
from sensor_family import build_cradle, validate

request = json.loads(Path("/input/request.json").read_text())
p, spec = request["parameters"], request["specification"]
validate(p)
model = cq.importers.importStep("/input/model.step")
solids = model.solids().vals()
reference = build_cradle(p)
violations = []


def fail(code, message):
    violations.append({"code": code, "message": message})


if len(solids) != 1 or not all(s.isValid() for s in solids):
    fail("INVALID_SOLID", "Cradle must be one connected valid solid")
residual = reference.cut(model).val().Volume() + model.cut(reference).val().Volume()
if residual > .1:
    fail("UNSUPPORTED_GEOMETRY", "STEP differs from the fixed cradle geometry contract")
volume = sum(s.Volume() for s in solids)
mass = volume * spec["density_g_mm3"]
# Two wall strips share transverse sensor load. Use only uninterrupted end webs;
# give diagonal ribs/gussets no stiffness credit. Uniform cantilever approximation.
width = 88 - (p["window_mm"] if p["window_style"] else 0)
force, height, modulus = spec["load_n"] / 2, 35, spec["youngs_modulus_mpa"]
inertia = width * p["wall_mm"] ** 3 / 12
stress = force * height * p["wall_mm"] / (2 * inertia)
deflection = force * height**3 / (3 * modulus * inertia)
if mass > spec["max_mass_g"]:
    fail("MASS_LIMIT", "Mount mass exceeds allocation")
if stress > spec["allowable_stress_mpa"]:
    fail("STRESS_LIMIT", "Wall-strip stress exceeds screening limit")
if deflection > spec["max_deflection_mm"]:
    fail("DEFLECTION_LIMIT", "Wall-strip deflection exceeds screening limit")
metrics = {
    "mass_g": {"value": mass, "unit": "g", "fidelity": "STEP_volume"},
    "volume_cm3": {"value": volume / 1000, "unit": "cm³", "fidelity": "STEP_volume"},
    "stress_mpa": {"value": stress, "unit": "MPa", "fidelity": "wall_strip_screen"},
    "deflection_mm": {"value": deflection, "unit": "mm", "fidelity": "wall_strip_screen"},
    "safety_factor": {"value": spec["allowable_stress_mpa"] / stress, "unit": "ratio", "fidelity": "wall_strip_screen"},
}
bounds = model.val().BoundingBox()
assembly = cq.Assembly(name="sensor_cradle")
for index, solid in enumerate(solids):
    assembly.add(solid, name=f"cradle_{index}", color=cq.Color(.90, .40, .14))
assembly.export("/output/model.glb")
Path("/output/result.json").write_text(json.dumps({
    "outcome": "passed" if not violations else "failed", "metrics": metrics,
    "violations": violations, "reference_residual_mm3": residual,
    "bounds_mm": [bounds.xlen, bounds.ylen, bounds.zlen],
    "fidelity": "wall_strip_screen",
    "limitations": "Nominal PA12 properties. Strip model excludes joint compliance, stress concentrations, print anisotropy and vibration. Ribs receive no stiffness credit. Not FEA or flight validation.",
}, allow_nan=False))
