import cadquery as cq


def evaluate(step_path, parameters, specification):
    s, t = specification, parameters["thickness_mm"]
    model = cq.importers.importStep(step_path)
    expected = cq.Workplane("XY").box(s["length_mm"], s["width_mm"], t)
    difference = expected.cut(model).val().Volume() + model.cut(expected).val().Volume()
    inertia = s["width_mm"] * t**3 / 12
    deflection = s["load_n"] * s["length_mm"] ** 3 / (3 * s["youngs_modulus_mpa"] * inertia)
    stress = s["load_n"] * s["length_mm"] * t / (2 * inertia)
    violations = []
    for fail, code in [
        (difference > 0.1, "UNSUPPORTED_GEOMETRY"),
        (deflection > s["max_deflection_mm"], "DEFLECTION"),
        (stress > s["allowable_stress_mpa"], "STRESS"),
    ]:
        if fail:
            violations.append({"code": code, "message": code.replace("_", " ").lower()})
    return {
        "outcome": "failed" if violations else "passed",
        "violations": violations,
        "metrics": {
            "mass_g": {
                "value": sum(x.Volume() for x in model.solids().vals()) * s["density_g_mm3"],
                "unit": "g",
            },
            "deflection_mm": {"value": deflection, "unit": "mm"},
            "stress_mpa": {"value": stress, "unit": "MPa"},
        },
        "fidelity": "cantilever_screen",
        "limitations": "Fixed-root uniform beam estimate. No holes, joints, fatigue or local stress concentrations.",
    }
