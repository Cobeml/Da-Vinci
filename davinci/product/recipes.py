"""Small trusted test-recipe library, not a generic physics solver.

The closed-form reference oracle is host-owned. Generated evaluators run only in
sandbox verification/execution, and never supply their own reference answers.
"""

from davinci.product.contracts import Candidate, Plan
from davinci.product.managed_contracts import BeamInputs, RequirementsOutput

BUILDER = """import cadquery as cq

def build(parameters, interfaces):
    return cq.Assembly(cq.Workplane('XY').box(LENGTH, WIDTH, parameters['thickness']))
"""
EVALUATOR = """import cadquery as cq
import numpy as np

def evaluate(step, request):
    p = request['test']['fixed_inputs']
    shape = cq.importers.importStep(step)
    solid = shape.val()
    bb = solid.BoundingBox()
    L, w, t = p['length_mm'], p['width_mm'], bb.zlen
    valid = (len(shape.solids().vals()) == 1 and solid.isValid() and
             abs(bb.xlen-L) < 1e-5 and abs(bb.ylen-w) < 1e-5 and
             abs(solid.Volume()-L*w*t) < 1e-4 and
             p['thickness_min_mm'] <= t+1e-6 and t <= p['thickness_max_mm']+1e-6)
    if not valid:
        return {'test_id': request['test']['id'], 'status': 'invalid_setup',
                'reason': 'invalid_geometry', 'message': 'Outside rectangular beam recipe'}
    F, E, rho = p['force_n'], p['youngs_mpa'], p['density_g_mm3']
    I = w*t**3/12
    K = E*I / L**3 * np.array([[12., -6*L], [-6*L, 4*L**2]])
    displacement = float(np.linalg.solve(K, np.array([F, 0.]))[0])
    values = {'mass_g': (solid.Volume()*rho, 'g'),
              'stress_mpa': (6*F*L/(w*t*t), 'MPa'),
              'deflection_mm': (displacement, 'mm')}
    return {'test_id': request['test']['id'], 'status': 'pass', 'reason': 'ok',
            'applicable': True, 'mesh_valid': True, 'bindings': {'root': True},
            'metrics': {k: {'value': v, 'unit': u, 'numerical_error': 0.00001, 'uncertainty': 0.}
                        for k, (v, u) in values.items()}}
"""


def catalog():
    return [
        {
            "id": "rectangular-beam-v1",
            "adapter": "authored-screen",
            "fidelity": "analytic_screen",
            "phenomena": ["mass", "linear_static", "geometry"],
            "material_model": "linear_isotropic",
            "geometry": "Rectangular prismatic cantilever; fixed length/width, editable thickness",
            "verification": "Independent closed-form mass/stress/deflection; passing, failing and displaced-root CAD fixtures",
            "limitations": "Small-deflection static beam screen only; no joints, fatigue, contact, anisotropy or certification",
            "input_schema": BeamInputs.model_json_schema(),
        }
    ]


def applicable(requirements):
    r = RequirementsOutput.model_validate(requirements)
    if r.recipe != "rectangular-beam-v1" or r.inputs is None:
        raise ValueError(r.unavailable_reason or "No trusted reference recipe for this request")
    p = r.inputs
    if (
        not set(p.phenomena) <= {"mass", "linear_static", "geometry"}
        or p.material_model != "linear_isotropic"
    ):
        raise ValueError("Recipe cannot test requested physics/material; no approximation substituted")
    if p.thickness_max_mm > p.length_mm / 4 or p.deflection_limit_mm > p.length_mm / 20:
        raise ValueError(
            "Beam screen requires slender geometry (L/t >= 4) and small accepted deflection (<= L/20)"
        )
    return p


def metrics(p, t):
    # Independent algebraic solution, separate from the matrix solver in evaluator.
    return {
        "mass_g": p.length_mm * p.width_mm * t * p.density_g_mm3,
        "stress_mpa": 6 * p.force_n * p.length_mm / (p.width_mm * t * t),
        "deflection_mm": 4 * p.force_n * p.length_mm**3 / (p.youngs_mpa * p.width_mm * t**3),
    }


def make_plan(requirements):
    r = RequirementsOutput.model_validate(requirements)
    p = applicable(r)
    lo, hi = p.thickness_min_mm, p.thickness_max_mm
    units = {"mass_g": "g", "stress_mpa": "MPa", "deflection_mm": "mm"}
    return Plan.model_validate(
        {
            "requirements": [x.model_dump() for x in r.requirements],
            "assumptions": [x.model_dump() for x in r.assumptions],
            "materials": [
                {
                    "name": p.material,
                    "provenance": p.material_provenance,
                    "properties": {
                        "youngs": {"value": p.youngs_mpa, "unit": "MPa", "dimension": "pressure"},
                        "density": {"value": p.density_g_mm3, "unit": "g/mm3", "dimension": "density"},
                    },
                }
            ],
            "interfaces": [
                {
                    "id": "root",
                    "description": "Fixed clamped root plane",
                    "binding_rule": "Independent planar location, normal, extent and selection check",
                    "unit": "mm",
                    "tolerance": 1e-5,
                    "region": {
                        "center": [-p.length_mm / 2, 0, 0],
                        "normal": [-1, 0, 0],
                        "center_tolerance": [1e-5] * 3,
                        "extent_min": [0, p.width_mm - 1e-5, lo - 1e-5],
                        "extent_max": [1e-5, p.width_mm + 1e-5, hi + 1e-5],
                    },
                }
            ],
            "objective": {"metric": "mass_g", "direction": "minimize", "target": p.objective_target_g},
            "design_schema": {
                "type": "object",
                "additionalProperties": False,
                "required": ["thickness"],
                "properties": {"thickness": {"type": "number", "minimum": lo, "maximum": hi}},
            },
            "design_units": {"thickness": "mm"},
            "tests": [
                {
                    "id": "beam",
                    "requirements": [x.id for x in r.requirements],
                    "capability": "linear_beam_screen",
                    "applicability": catalog()[0]["limitations"],
                    "fixed_inputs": p.model_dump(),
                    "load_cases": [
                        {
                            "id": "tip",
                            "description": "Transverse tip force",
                            "quantities": {"force": {"value": p.force_n, "unit": "N", "dimension": "force"}},
                            "boundary_conditions": "Clamped root, free tip; static transverse force",
                        }
                    ],
                    "metrics": units,
                    "accuracy": {
                        k: {
                            "method": "Closed-form reference and BRep checks",
                            "max_numerical_error": 0.001,
                            "max_uncertainty": 0.0,
                        }
                        for k in units
                    },
                    "mesh_rule": "Exact single rectangular Euler-Bernoulli element; verify BRep independently",
                    "criteria": [
                        {
                            "metric": "stress_mpa",
                            "operator": "<=",
                            "limit": p.stress_limit_mpa,
                            "unit": "MPa",
                        },
                        {
                            "metric": "deflection_mm",
                            "operator": "<=",
                            "limit": p.deflection_limit_mm,
                            "unit": "mm",
                        },
                    ],
                    "simulation": {
                        "adapter": "authored-screen",
                        "phenomena": p.phenomena,
                        "material_model": p.material_model,
                        "geometry_assumptions": catalog()[0]["geometry"],
                        "fidelity": "analytic_screen",
                        "stage": "final",
                        "solver_length_unit": "mm",
                    },
                }
            ],
            "metadata": {
                "recipe": "rectangular-beam-v1",
                "uncertainty_scope": "Zero model-form uncertainty is an analytic-screen assumption, not physical certification",
            },
        }
    )


def fixtures(requirements):
    p = applicable(requirements)
    source = BUILDER.replace("LENGTH", repr(p.length_mm)).replace("WIDTH", repr(p.width_mm))
    rows = []
    for t in (p.thickness_min_mm, p.thickness_max_mm):
        values = metrics(p, t)
        passed = (
            values["stress_mpa"] + 1e-5 <= p.stress_limit_mpa
            and values["deflection_mm"] + 1e-5 <= p.deflection_limit_mm
        )
        rows.append(
            {
                "candidate": Candidate(
                    title="Trusted reference only", source=source, parameters={"thickness": t}
                ).model_dump(),
                "expected_status": "pass" if passed else "physical_failure",
                "values": values,
            }
        )
    if {r["expected_status"] for r in rows} != {"pass", "physical_failure"}:
        raise ValueError(
            "Thickness bounds must bracket a passing and failing trusted reference; clarify limits/bounds, never relax acceptance"
        )
    bad = source.replace("cq.Workplane('XY')", "cq.Workplane('XY').transformed(offset=(0, 100, 0))")
    rows.append(
        {
            "candidate": Candidate(
                title="Displaced-root invalid reference",
                source=bad,
                parameters={"thickness": p.thickness_max_mm},
            ).model_dump(),
            "expected_status": "invalid_setup",
            "values": {},
        }
    )
    return rows


def verification(plan, fixture, artifact):
    dimensions = {"mass_g": "mass", "stress_mpa": "pressure", "deflection_mm": "length"}
    return {
        "test_id": "beam",
        "fixture_artifact": artifact,
        "expected_status": fixture["expected_status"],
        "reference_metrics": {
            k: {"value": v, "unit": plan["tests"][0]["metrics"][k], "dimension": dimensions[k]}
            for k, v in fixture["values"].items()
        },
        "tolerances": {k: max(0.0001, abs(v) * 1e-8) for k, v in fixture["values"].items()},
        "provenance": "Shipped rectangular-beam-v1 independent algebraic reference; displaced root must be rejected",
    }


def check_geometry(plan, geometry):
    """Host checks independent BRep inspection, never evaluator/candidate hints."""
    p = BeamInputs.model_validate(plan.tests[0].fixed_inputs)
    extent = geometry["extent"]
    t = extent[2]
    return (
        geometry["solids"] == 1
        and geometry["planar_faces"] == 6
        and abs(extent[0] - p.length_mm) <= 1e-5
        and abs(extent[1] - p.width_mm) <= 1e-5
        and all(abs(x) <= 1e-5 for x in geometry["center"])
        and p.thickness_min_mm - 1e-6 <= t <= p.thickness_max_mm + 1e-6
        and abs(geometry["volume"] - p.length_mm * p.width_mm * t) <= 1e-4
    )


def check_measurements(plan, geometry, result):
    p = BeamInputs.model_validate(plan.tests[0].fixed_inputs)
    expected = metrics(p, geometry["extent"][2])
    return all(
        k in result.metrics and abs(result.metrics[k].value - v) <= max(0.0001, abs(v) * 1e-8)
        for k, v in expected.items()
    )
