"""Trusted evaluator. Receives STEP + frozen inputs, never imports candidate code."""

import json
import math
from pathlib import Path

import cadquery as cq

root = Path("/input")
request = json.loads((root / "request.json").read_text())
spec = request["specification"]
subsystem = request["subsystem"]
shape = cq.importers.importStep(str(root / "model.step"))
solids = shape.solids().vals()
bounds = shape.val().BoundingBox()
violations = []
metrics = {}


def fail(code, message):
    violations.append({"code": code, "message": message})


def metric(name, value, unit):
    metrics[name] = {"value": value, "unit": unit, "fidelity": "analytic_screening"}


if not solids or any(not s.isValid() or s.Volume() <= 0 for s in solids):
    fail("INVALID_SOLID", "Expected valid positive-volume solids")
volume = sum(s.Volume() for s in solids) * 1e-9

if subsystem == "structural":
    material = spec["material"]
    mount = spec["mount"]
    mass = volume * material["density_kg_m3"]
    metric("mass_kg", mass, "kg")
    thickness = bounds.zlen
    metric("thickness_mm", thickness, "mm")
    # This evaluator only accepts the intact uniform plate with two mounting holes.
    reference = cq.Workplane("XY").box(80, 40, thickness)
    reference = reference.faces(">Z").workplane().pushPoints([(-30, -14), (-30, 14)]).hole(4)
    difference = reference.cut(shape).val().Volume() + shape.cut(reference).val().Volume()
    supported = (
        len(solids) == 1
        and difference < 0.1
        and abs(bounds.xlen - 80) < 0.01
        and abs(bounds.ylen - 40) < 0.01
    )
    if not supported:
        fail(
            "UNSUPPORTED_ANALYSIS",
            "Analytic evaluator requires the fixed uniform plate and mounting-hole pattern",
        )
    if thickness < mount["minimum_thickness_mm"]:
        fail("MINIMUM_THICKNESS", "Plate is below the fixed minimum thickness")
    if mass > mount["max_mass_kg"]:
        fail("MASS_LIMIT", "Mount exceeds its mass allocation")
    if supported:
        length = 0.06
        width = 0.04
        t = thickness / 1000
        inertia = width * t**3 / 12
        stress = mount["load_n"] * length * t / (2 * inertia)
        deflection = mount["load_n"] * length**3 / (3 * material["youngs_modulus_pa"] * inertia)
        metric("bending_stress_pa", stress, "Pa")
        metric("deflection_mm", deflection * 1000, "mm")
        if stress > material["allowable_stress_pa"]:
            fail("STRESS_LIMIT", "Nominal beam stress exceeds the screening allowable")
        if deflection * 1000 > mount["max_deflection_mm"]:
            fail("DEFLECTION_LIMIT", "Cantilever deflection exceeds the screening limit")
    objective = mass / (0.08 * 0.04 * 0.006 * material["density_kg_m3"])
else:
    wing = spec["wing"]
    # Demo airfoil uses a homogeneous foam model, separate from mount material.
    metric("mass_kg", volume * 60.0, "kg")
    span, chord = bounds.ylen / 1000, bounds.xlen / 1000
    metric("span_mm", span * 1000, "mm")
    supported = len(solids) == 2 and 0.45 <= span <= 0.75 and abs(chord - 0.12) < 0.0001
    if not supported:
        fail("UNSUPPORTED_ANALYSIS", "Expected two surface bodies, 120 mm chord, 450–750 mm span")
    if supported:
        main, flap = sorted(solids, key=lambda s: s.Center().x)
        gap = flap.BoundingBox().xmin - main.BoundingBox().xmax
        metric("hinge_gap_mm", gap, "mm")
        flap_fraction = (bounds.xmax - flap.BoundingBox().xmin) / bounds.xlen
        metric("flap_fraction", flap_fraction, "ratio")
        if not 0.18 <= flap_fraction <= 0.32:
            fail("CONTROL_EFFECTIVENESS", "Control surface must occupy 18–32% chord")
        if gap < wing["min_hinge_gap_mm"] - 1e-6:
            fail("HINGE_CLEARANCE", "Hinge gap is below the fixed clearance limit")
        hinge = (flap.BoundingBox().xmin + main.BoundingBox().xmax) / 2
        for angle in wing["travel_deg"]:
            moved = flap.rotate((hinge, 0, 0), (hinge, 1, 0), angle)
            if main.intersect(moved).Volume() > 0.001:
                fail("TRAVEL_COLLISION", f"Control surface collides at {angle} degrees")
                break
    area = span * chord
    dynamic_pressure = 0.5 * wing["density_kg_m3"] * wing["airspeed_m_s"] ** 2
    cl = wing["required_lift_n"] / (dynamic_pressure * area)
    induced_drag = wing["required_lift_n"] ** 2 / (
        dynamic_pressure * math.pi * wing["oswald_efficiency"] * span**2
    )
    metric("required_cl", cl, "ratio")
    metric("induced_drag_n", induced_drag, "N")
    metric("projected_area_m2", span * chord, "m2")
    if cl > wing["max_cl"]:
        fail("LIFT_SCREENING", "Required lift coefficient exceeds the attached-flow screening range")
    if volume * 60.0 > wing["max_mass_kg"]:
        fail("MASS_LIMIT", "Surface exceeds its mass allocation")
    baseline_drag = wing["required_lift_n"] ** 2 / (
        dynamic_pressure * math.pi * wing["oswald_efficiency"] * 0.6**2
    )
    objective = induced_drag / baseline_drag

assembly = cq.Assembly(name=subsystem)
for i, solid in enumerate(solids):
    assembly.add(
        solid,
        name=f"body_{i}",
        color=cq.Color(0.83, 0.49, 0.27) if subsystem == "structural" else cq.Color(0.38, 0.7, 0.62),
    )
assembly.export("/output/model.glb")
result = {
    "outcome": "passed" if not violations else "failed",
    "metrics": metrics,
    "violations": violations,
    "objective": objective,
    "fidelity": "analytic_screening",
    "bounds_mm": {"x": bounds.xlen, "y": bounds.ylen, "z": bounds.zlen},
    "limitations": ["Nominal beam screening excludes bolt bearing and stress concentrations"]
    if subsystem == "structural"
    else ["Induced drag estimate excludes profile drag, stall and VTOL rotor interaction"],
}
Path("/output/result.json").write_text(json.dumps(result, allow_nan=False))
