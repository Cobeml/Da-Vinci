"""Independently specified nominal references and a varied-feature bracket example.

Source bundles are proposals only. All dimensions used for scoring come from STEP.
"""

from davinci.product.contracts import Plan
from davinci.product.structural.adapter import METRICS

BUILDER = """import cadquery as cq

def build(parameters, interfaces):
    variant = parameters['variant']
    if variant.startswith('beam'):
        thickness = 4 if variant == 'beam-thin' else 8
        return cq.Assembly(cq.Workplane('XY').box(60,20,thickness,centered=(False,True,False)))
    body = cq.Workplane('XY').box(60,20,4,centered=(False,True,False))
    wall = cq.Workplane('XY').box(4,20,30,centered=(False,True,False))
    body = body.union(wall)
    # Two actual clearance holes in the cantilever shelf, not a baseline-equivalent solid.
    for x in (20,40):
        hole = cq.Workplane('XY').center(x,0).circle(2).extrude(4)
        body = body.cut(hole)
    if variant == 'bracket-ribbed':
        # Two tapered vertical ribs change load path, section topology and mass distribution.
        for y in (-6,8):
            rib = (cq.Workplane('XZ').workplane(offset=-y)
                   .polyline([(4,4),(4,22),(52,4)]).close().extrude(2))
            body = body.union(rib)
    if variant == 'disconnected':
        body = body.union(cq.Workplane('XY').box(2,2,2).translate((80,0,0)))
    return cq.Assembly(body)
"""


def quantity(value, unit, dimension):
    return dict(value=float(value), unit=unit, dimension=dimension)


def interface(name, x, normal, *, fixed_height=None):
    return dict(
        id=name,
        description="Fixed end plane with predeclared rectangular interface envelope",
        binding_rule="Independent planar location, outward normal and extent; no face-index identity",
        unit="mm",
        tolerance=1e-5,
        region=dict(
            center=[x, 0, fixed_height / 2 if fixed_height else 15],
            normal=normal,
            center_tolerance=[0, 0, 0 if fixed_height else 13],
            extent_min=[0, 20, fixed_height or 4],
            extent_max=[0, 20, fixed_height or 30],
            expected_count=1,
        ),
    )


def bracket_plan():
    data = dict(
        requirements=[
            dict(
                id="stiffness",
                description="Carry a distributed 20 N downward shelf load with area-mean load displacement <=0.1 mm and gauge mean von Mises <=50 MPa",
                source="Nominal benchmark, not a certified material specification",
            )
        ],
        assumptions=[
            dict(
                description="Homogeneous nominal aluminium; static load, perfect full clamps, small deformation",
                source="Benchmark assumptions",
                applicability="No bolts, contact, fatigue, plasticity, buckling or dynamic qualification",
            )
        ],
        materials=[
            dict(
                name="nominal-aluminium",
                provenance="Specified benchmark constants E=70000 MPa, nu=0.3, density=2700 kg/m3; no batch certification",
                properties={
                    "young_modulus": quantity(70000, "MPa", "pressure"),
                    "poisson_ratio": quantity(0.3, "1", "dimensionless"),
                    "density": quantity(2700, "kg/m3", "density"),
                },
            )
        ],
        interfaces=[interface("root", 0, [-1, 0, 0]), interface("load", 60, [1, 0, 0])],
        tests=[
            dict(
                id="static",
                requirements=["stiffness"],
                capability="Gmsh 4.15.2 / CalculiX 2.23 small-strain C3D10",
                applicability="One connected solid; planar clamp and uniform loaded end; nominal linear static response",
                fixed_inputs={
                    "structural": dict(
                        material="nominal-aluminium",
                        clamped_interfaces=["root"],
                        load_interface="load",
                        load_case="shelf",
                        stress_region=dict(
                            lower_mm=[20, -10, 0],
                            upper_mm=[40, 10, 4],
                            exclusion_distance_mm=10,
                            justification="Fixed shelf gauge 20 to 40 mm from clamp, at least 20 mm from load; volume mean stress, not local notch or support strength",
                        ),
                        mesh=dict(initial_size_mm=5, max_levels=5, relative_tolerance=0.035),
                        relative_uncertainty=0.05,
                        uncertainty_basis="Declared 5 percent nominal-model allowance; no claim to bound uncertain manufacturing, joints or actual load distributions",
                    )
                },
                load_cases=[
                    dict(
                        id="shelf",
                        description="Uniform end-face resultant 20 N downward, consistently integrated triangle traction",
                        quantities={
                            "force_x": quantity(0, "N", "force"),
                            "force_y": quantity(0, "N", "force"),
                            "force_z": quantity(-20, "N", "force"),
                        },
                        boundary_conditions="All translations clamped on x=0 selected planar root; face force on x=60, no other loads",
                    )
                ],
                metrics=METRICS,
                criteria=[
                    dict(metric="load_displacement_mm", operator="<=", limit=0.1, unit="mm"),
                    dict(metric="gauge_von_mises_mpa", operator="<=", limit=50, unit="MPa"),
                ],
                accuracy={
                    k: dict(
                        method="Two successive mesh changes within 3.5 percent; reported error twice max change; nominal uncertainty allowance",
                        max_numerical_error={
                            "mass_g": 0.01,
                            "load_displacement_mm": 0.02,
                            "gauge_von_mises_mpa": 5,
                        }[k],
                        max_uncertainty={
                            "mass_g": 10,
                            "load_displacement_mm": 0.1,
                            "gauge_von_mises_mpa": 10,
                        }[k],
                    )
                    for k in METRICS
                },
                mesh_rule="Gmsh straight-sided quadratic tetrahedra; h=5 mm refined by 0.7, maximum five levels, positive Jacobians and minSICN >=0.01; two consecutive convergence checks",
                simulation=dict(
                    adapter="calculix-static",
                    phenomena=["mass", "linear_static"],
                    material_model="linear_isotropic",
                    geometry_assumptions="Single connected solid with finite holes/ribs/tapers; no baseline reconstruction",
                    fidelity="converged_linear_solid",
                    required_evidence=["mesh", "solver_deck", "fields", "convergence", "uncertainty"],
                    estimate=dict(cpu_cores=1, memory_mb=1024, disk_mb=180, wall_seconds=100),
                ),
            )
        ],
        objective=dict(metric="load_displacement_mm", direction="minimize", target=0.05),
        design_schema={
            "type": "object",
            "additionalProperties": False,
            "properties": {
                "variant": {
                    "type": "string",
                    "enum": ["beam-thin", "beam-thick", "bracket-base", "bracket-ribbed", "disconnected"],
                }
            },
            "required": ["variant"],
        },
        design_units={"variant": "1"},
    )
    return Plan.model_validate(data)


def candidate(variant):
    return dict(
        title=variant,
        change="Specified geometry variant; measured from exported CAD",
        source=BUILDER,
        parameters={"variant": variant},
    )


def beam_reference(thickness):
    # Euler-Bernoulli end deflection plus Timoshenko shear term. Gauge x=20..40,z=0..4.
    length, width, force, E, nu = 60, 20, 20, 70000, 0.3
    inertia = width * thickness**3 / 12
    displacement = force * length**3 / (3 * E * inertia) + force * length / (
        (5 / 6) * (E / (2 * (1 + nu))) * width * thickness
    )
    # Average absolute bending stress over fixed gauge: mean moment F*(L-30).
    # For t4 mean |z-2|=1; for t8 mean |z-4|=2. Shear is small; tolerance includes it.
    mean_stress = force * (length - 30) * (thickness / 4) / inertia
    return {
        "mass_g": length * width * thickness * 0.0027,
        "load_displacement_mm": displacement,
        "gauge_von_mises_mpa": mean_stress,
    }
