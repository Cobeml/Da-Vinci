"""Frozen example contract and CAD proposals; no claimed laboratory data."""

from davinci.product.contracts import Plan
from davinci.product.mechanism.adapter import METRICS, estimate
from davinci.product.mechanism.contracts import SliderSettings

BUILDER = """import cadquery as cq

def build(parameters, interfaces):
    h=parameters['height_mm']; d=parameters['pocket_depth_mm']
    base=cq.Workplane('XY').box(100,100,5).translate((0,0,-2.5))
    moving=cq.Workplane('XY').box(40,30,h).translate((0,0,20+h/2))
    if d:
        moving=moving.cut(cq.Workplane('XY').box(32,22,d).translate((0,0,20+h-d/2)))
    return cq.Assembly().add(base,name='base').add(moving,name='carriage')
"""


def candidate(variant):
    source = BUILDER
    p = {
        "height_mm": 6 if variant == "reference-light" else 20,
        "pocket_depth_mm": 18 if variant == "pocketed" else 0,
    }
    if variant == "ambiguous":
        source = source.replace(
            ".add(moving,name='carriage')", ".add(moving,name='carriage').add(moving,name='duplicate')"
        )
    if variant == "misplaced":
        source = source.replace(
            ".add(moving,name='carriage')", ".add(moving.translate((50,0,0)),name='carriage')"
        )
    return dict(
        title=variant,
        source=source,
        parameters=p,
        change="Fixed actuator/loads/interfaces; remove material from carriage interior"
        if variant == "pocketed"
        else "Reference or deliberately heavy/invalid carriage",
    )


def q(v, u, d):
    return dict(value=v, unit=u, dimension=d)


def plan():
    s = SliderSettings(
        bodies=[
            dict(name="base", interface="stop", material="aluminium", role="fixed"),
            dict(name="carriage", interface="foot", material="aluminium", role="moving"),
        ],
        approximation="Ideal z guide and gravity-compensated force motor. AABB collision fills internal pockets; full rectangular bottom is independently checked. Soft frictionless contact is numerical, not calibrated material compliance.",
    )
    interfaces = []
    for name, z, normal, xy in [("stop", 0, 1, [100, 100]), ("foot", 20, -1, [40, 30])]:
        interfaces.append(
            dict(
                id=name,
                description="Frozen horizontal contact interface",
                binding_rule="Independent planar location, normal, area and body ownership",
                unit="mm",
                tolerance=1e-5,
                region=dict(
                    center=[0, 0, z],
                    normal=[0, 0, normal],
                    center_tolerance=[1e-5] * 3,
                    extent_min=[*xy, 0],
                    extent_max=[*xy, 1e-5],
                ),
            )
        )
    return Plan.model_validate(
        dict(
            requirements=[
                dict(
                    id="motion",
                    description="Reach 30 mm relative lift within 1 mm at 2 s under fixed 0.4 N force cap; retain floor equilibrium and bounded penetration",
                    source="Explicit nominal mechanism request",
                )
            ],
            assumptions=[
                dict(
                    description="Homogeneous rigid aluminium; ideal guide; normal soft contact; no stresses or fatigue",
                    source="Declared scope",
                    applicability="This two-body nominal rigid slider only",
                )
            ],
            materials=[
                dict(
                    name="aluminium",
                    provenance="Nominal 2700 kg/m3, no measured batch",
                    properties={"density": q(2700, "kg/m3", "density")},
                )
            ],
            interfaces=interfaces,
            objective=dict(metric="mass_g", direction="minimize"),
            design_schema=dict(
                type="object",
                additionalProperties=False,
                required=["height_mm", "pocket_depth_mm"],
                properties={
                    "height_mm": dict(type="number", minimum=6, maximum=20),
                    "pocket_depth_mm": dict(type="number", minimum=0, maximum=18),
                },
            ),
            design_units={"height_mm": "mm", "pocket_depth_mm": "mm"},
            tests=[
                dict(
                    id="mechanism",
                    requirements=["motion"],
                    capability="MuJoCo 3.4.0 rigid slider CPU",
                    applicability="Validated two-solid vertical guide, normal contact only",
                    fixed_inputs={"mechanism": s.model_dump()},
                    load_cases=[
                        dict(
                            id="lift-and-settle",
                            description="Gravity-compensated PD ramp/hold then independent zero-actuation drop-to-stop scenario",
                            quantities={
                                "gravity": q(9.81, "m/s2", "acceleration"),
                                "actuator_limit": q(0.4, "N", "force"),
                                "target": q(0.03, "m", "length"),
                            },
                            boundary_conditions="Fixed base, ideal world-z guide; two separate trajectories reset to CAD pose and zero velocity",
                        )
                    ],
                    metrics=METRICS,
                    criteria=[
                        dict(metric="tracking_error_m", operator="<=", limit=0.001, unit="m"),
                        dict(metric="settled_penetration_m", operator="<=", limit=0.0005, unit="m"),
                        dict(metric="equilibrium_error_n", operator="<=", limit=0.002, unit="N"),
                        dict(metric="peak_actuation_n", operator="<=", limit=0.400001, unit="N"),
                    ],
                    accuracy={
                        k: dict(
                            method="Independent motion/equilibrium references and both timestep refinements; nominal uncalibrated allowance",
                            max_numerical_error=0.0001 if u == "m" else 0.002 if u == "N" else 0.00001,
                            max_uncertainty=0.0001 if u == "m" else 0.001 if u == "N" else 0,
                        )
                        for k, u in METRICS.items()
                    },
                    mesh_rule="Exact BRep volume inertia in SI; AABB contact restricted to full bottom-plane motion; no triangle-mesh contact approximation",
                    simulation=dict(
                        adapter="mujoco-slider",
                        phenomena=["mass", "rigid_motion", "normal_contact"],
                        material_model="homogeneous_rigid",
                        geometry_assumptions="Two solids with full horizontal contact planes and contained vertical path",
                        fidelity="timestep_checked_rigid_slider",
                        stage="final",
                        cad_unit="mm",
                        solver_length_unit="m",
                        estimate=estimate(s),
                        required_evidence=["solver_deck", "fields", "convergence", "uncertainty"],
                    ),
                )
            ],
        )
    )


def bundle(image):
    return dict(
        plan=plan().model_dump(mode="json"),
        evaluator=dict(
            resources={"evaluate.py": "raise RuntimeError('Must not execute authored evaluator')\n"},
            provenance="Trusted packaged MuJoCo adapter; independent predeclared references",
        ),
        runtime=dict(
            image=image,
            solver="MuJoCo 3.4.0 CPU",
            provenance="Pinned optional solver runtime",
            cpu_cores=1,
            memory_gb=2,
            timeout_seconds=180,
            job_seconds=900,
            compute_seconds=1800,
            artifact_bytes=64000000,
        ),
    )
