"""Trusted setup/estimation; MuJoCo and CAD imports exist only in the sandbox."""

from importlib.resources import files

from davinci.product.mechanism.contracts import SliderSettings
from davinci.product.simulation_contracts import AdapterDescriptor
from davinci.product.units import convert

DESCRIPTOR = AdapterDescriptor(
    id="mujoco-slider",
    phenomena=["mass", "rigid_motion", "normal_contact"],
    material_models=["homogeneous_rigid"],
    fidelities=["timestep_checked_rigid_slider"],
    geometry_assumptions="Two valid separate solids, horizontal base top and full rectangular carriage bottom, contained vertical envelope path; ideal z guide",
    required_software={"cadquery": None, "numpy": None, "mujoco": "3.4.0"},
    limitations=[
        "Single translating carriage; ideal massless frictionless guide, no hinges or general robot assemblies",
        "Homogeneous STEP volume mass/inertia; box collision envelope fills pockets; only validated horizontal stop contact is supported",
        "Soft frictionless normal contact with fixed numerical solref/solimp, not measured surface compliance",
        "No stress, deformation, fatigue, wear, thermal or fluid evidence",
        "Linux CPU native MuJoCo only; no GPU/MJX/Warp or remote executor",
        "Empirical timestep sensitivity and declared model allowance are not rigorous error bounds",
    ],
    reference_checks=[
        "CAD box and pocket mass/inertia",
        "Force/mass motion",
        "Static normal equilibrium",
        "Contact gap/penetration",
        "Three timestep levels",
        "Unforced free-motion kinetic energy",
    ],
    routes=["v2"],
)
METRICS = {
    "mass_g": "g",
    "tracking_error_m": "m",
    "settled_penetration_m": "m",
    "equilibrium_error_n": "N",
    "peak_actuation_n": "N",
}


def setup(plan, test):
    if set(test.fixed_inputs) != {"mechanism"}:
        raise ValueError("mujoco-slider needs only the versioned mechanism setup")
    s = SliderSettings.model_validate(test.fixed_inputs["mechanism"])
    if test.simulation.cad_unit != "mm" or test.simulation.solver_length_unit != "m":
        raise ValueError("Explicit CAD mm to MuJoCo m conversion required")
    if test.metrics != METRICS:
        raise ValueError("Declare all mechanism metrics in canonical SI/g units")
    if not {"solver_deck", "fields", "convergence", "uncertainty"} <= set(test.simulation.required_evidence):
        raise ValueError(
            "Mechanism configuration, trajectories, convergence and uncertainty evidence required"
        )
    interfaces = {i.id: i for i in plan.interfaces}
    if set(interfaces) != {b.interface for b in s.bodies}:
        raise ValueError("Every mechanism body needs exactly one test-defined semantic interface")
    for body in s.bodies:
        i = interfaces[body.interface]
        expected = (0, 0, 1) if body.role == "fixed" else (0, 0, -1)
        if (
            not i.region
            or i.region.expected_count != 1
            or tuple(i.region.normal) != expected
            or i.unit != "mm"
        ):
            raise ValueError("Use one horizontal oriented planar base top/carriage bottom in mm")
    densities = {}
    if {m.name for m in plan.materials} != {b.material for b in s.bodies}:
        raise ValueError("Materials must exactly cover the assembly bodies")
    for m in plan.materials:
        if set(m.properties) != {"density"}:
            raise ValueError(
                "Rigid-body material requires density only; elastic properties imply unsupported physics"
            )
        q = m.properties["density"]
        rho = convert(q.value, q.unit, "kg/m3", "density")
        if not 1 <= rho <= 30000:
            raise ValueError("Density outside validated range 1..30000 kg/m3")
        densities[m.name] = rho
    if len(test.load_cases) != 1 or test.load_cases[0].id != "lift-and-settle":
        raise ValueError("Declare the prescribed lift-and-settle load scenario")
    quantities = test.load_cases[0].quantities
    if set(quantities) != {"gravity", "actuator_limit", "target"}:
        raise ValueError("Only gravity, actuator_limit and target loads are supported")
    for key, unit, dim, expected in [
        ("gravity", "m/s2", "acceleration", s.gravity_m_s2),
        ("actuator_limit", "N", "force", s.force_limit_n),
        ("target", "m", "length", s.target_m),
    ]:
        q = quantities[key]
        if abs(convert(q.value, q.unit, unit, dim) - expected) > 1e-12:
            raise ValueError("Load scenario contradicts mechanism settings: " + key)
    return {
        "settings": s.model_dump(),
        "density_kg_m3": densities,
        "material_sources": [m.model_dump() for m in plan.materials],
    }


def estimate(settings):
    steps = int(14 * settings.duration_seconds / settings.timestep_seconds)
    return dict(
        cpu_cores=1,
        memory_mb=768,
        disk_mb=32,
        wall_seconds=15 + steps / 2000,
        basis=f"Two scenarios, three timestep levels: {steps} steps plus CAD import and references",
        uncertainty="Conservative initial CPU throughput estimate; actual timing/steps/RSS archived, no adequacy guarantee",
    )


def source():
    return files("davinci.product.mechanism").joinpath("solver.py").read_text()
