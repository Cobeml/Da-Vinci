"""Trusted STEP/reference validation, mass measurement and coupled VTOL evaluation."""

import json
from pathlib import Path

import cadquery as cq
from vtol_family import parts
from vtol_physics import evaluate_performance
from vtol_spec import SPECIFICATION as S

root = Path("/input")
request = json.loads((root / "request.json").read_text())
p = request["parameters"]
expected = parts(p)
actual = cq.importers.importStep(str(root / "model.step")).solids().vals()
violations = []


def fail(code, msg):
    violations.append({"code": code, "message": msg})


reference_solids = [(o["name"], s) for o in expected for s in o["shape"].Solids()]
if len(actual) != len(reference_solids) or any(not x.isValid() for x in actual):
    fail("INVALID_STEP", "Part count or solid validity differs from reference")
else:
    # STEP order need not match. Pair by center and volume, then compare symmetric differences.
    remaining = list(actual)
    for name, shape in reference_solids:
        a = min(
            remaining,
            key=lambda x: (x.Center() - shape.Center()).Length + abs(x.Volume() - shape.Volume()) ** (1 / 3),
        )
        remaining.remove(a)
        if shape.cut(a).Volume() + a.cut(shape).Volume() > 0.5:
            fail("UNSUPPORTED_GEOMETRY", name)
for o in expected:
    if o["name"].startswith("wing_spar"):
        envelope = next(x["envelope"] for x in expected if x["name"] == o["name"].replace("_spar", ""))
        if o["shape"].cut(envelope).Volume() > 0.5:
            fail("SPAR_ENVELOPE", "Spar protrudes outside the analyzed airfoil")
components = []
for o in expected:
    shape = o["shape"]
    mass = shape.Volume() * 1e-9 * o["density"]
    if o["kind"] == "foam":
        mass += o.get("envelope", shape).Area() * 1e-6 * S["skin_areal_kg_m2"]
    if mass:
        components.append(dict(name=o["name"], mass_kg=mass, cg_x_m=shape.Center().x / 1000))
for name, mass, x in [
    ("battery", S["battery_kg"], p["battery_x"]),
    ("payload", S["payload_kg"], p["payload_x"]),
    ("cruise_drive", S["cruise_motor_mass_kg"] + S["cruise_prop_mass_kg"], -0.035),
    ("avionics_esc_wiring_landing", S["other_hardware_kg"], p["wing_x"]),
]:
    components.append(dict(name=name, mass_kg=mass, cg_x_m=x))
for x in (p["rotor_front_x"], p["rotor_rear_x"]):
    components.append(
        dict(
            name=f"lift_drives_{x}", mass_kg=2 * (S["lift_motor_mass_kg"] + S["lift_prop_mass_kg"]), cg_x_m=x
        )
    )
body = next(o["shape"] for o in expected if o["name"] == "fuselage")
boxes = [o["shape"] for o in expected if o["kind"] == "internal"]
if boxes[0].intersect(boxes[1]).Volume() > 0.1:
    fail("BAY_COLLISION", "Battery and payload overlap")
for box in boxes:
    if box.intersect(body).Volume() > 0.1:
        fail("BAY_FIT", "Battery/payload intersects shell")
    b = box.BoundingBox()
    if b.xmin < 0 or b.xmax > p["fuselage_length"] * 1000:
        fail("BAY_FIT", "Box outside fuselage")
# Four coplanar lift disks. Vertical distance to wing/pods is evaluated as actual BRep distance.
disks = []
for sign in (-1, 1):
    for x in (p["rotor_front_x"], p["rotor_rear_x"]):
        disk = cq.Solid.makeCylinder(
            S["lift_prop_diameter_m"] * 500, 4, cq.Vector(x * 1000, sign * p["boom_y"] * 1000, 146)
        )
        disks.append(disk)
        for o in expected:
            if (
                o["name"].startswith(("wing", "tail", "fin", "fuselage"))
                and disk.distance(o["shape"]) < S["min_prop_clearance_m"] * 1000
            ):
                fail("PROP_CLEARANCE", o["name"])
for i, a in enumerate(disks):
    for b in disks[i + 1 :]:
        if a.distance(b) < S["min_prop_clearance_m"] * 1000:
            fail("PROP_CLEARANCE", "Lift disks overlap")
performance = evaluate_performance(p, components, request.get("resolution", 10))
n = performance["nominal"]
for code in n["violations"]:
    fail(code, "Fixed aircraft screening constraint")
metrics = {}
for key, unit, value in [
    ("range_km", "km", n["range_km"]),
    ("max_speed_m_s", "m/s", n["max_speed_m_s"]),
    ("payload_capacity_kg", "kg", performance["payload_capacity_kg"]),
    ("endurance_min", "min", n["endurance_min"]),
    ("mass_kg", "kg", n["mass_kg"]),
    ("hover_power_w", "W", n["hover_power_w"]),
    ("static_margin", "ratio", n["static_margin"]),
    ("stall_speed_m_s", "m/s", n["stall_speed_m_s"]),
    ("best_range_speed_m_s", "m/s", (n["best"] or {}).get("speed_m_s", 0)),
]:
    metrics[key] = dict(value=value, unit=unit, fidelity="coupled_engineering_estimate")
for filename, selection in [
    ("model.glb", [o for o in expected if o["kind"] != "internal"]),
    ("internal.glb", [o for o in expected if o["name"] != "fuselage"]),
]:
    a = cq.Assembly(name="vtol")
    for o in selection:
        a.add(o["shape"], name=o["name"], color=cq.Color(*o["color"]))
    a.export("/output/" + filename)
result = dict(
    outcome="failed" if violations else "passed",
    metrics=metrics,
    violations=violations,
    components=components,
    performance=performance,
    fidelity="coupled_engineering_estimate",
    limitations=[
        "No flight validation; transition energy allowance, not dynamic simulation.",
        "VLM/XFOIL attached-flow estimates; no rotor interference, flutter, fatigue or control simulation.",
        "Maximum speed is the highest supported passing speed on a 0.25 m/s grid; no propeller-map extrapolation.",
        "Beam screening excludes joints/local shell buckling; hardware properties are assumptions.",
    ],
)
Path("/output/result.json").write_text(json.dumps(result, allow_nan=False))
