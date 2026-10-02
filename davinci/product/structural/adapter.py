"""Trusted adapter metadata/setup validation. Gmsh/NumPy are sandbox-only."""

from importlib.resources import files

from davinci.product.simulation_contracts import AdapterDescriptor
from davinci.product.structural.contracts import StructuralSettings
from davinci.product.units import convert

DESCRIPTOR = AdapterDescriptor(
    id="calculix-static",
    phenomena=["mass", "linear_static"],
    material_models=["linear_isotropic"],
    geometry_assumptions="One valid connected solid; finite features, planar clamp/load faces; holes, ribs, tapers and fillets allowed subject to mesh checks",
    fidelities=["converged_linear_solid"],
    required_software={"cadquery": None, "numpy": None, "gmsh": "4.15.2", "calculix": "2.23"},
    limitations=[
        "Small displacement/strain, homogeneous isotropic elasticity, no contact, nonlinear material, fatigue, buckling or dynamics",
        "Full translational clamps and uniform traction on disjoint planar faces only; no bolt/joint compliance",
        "Straight-sided quadratic tetrahedra; mesh volume and convergence checked against actual STEP",
        "Acceptance stress is a predeclared spatial-volume mean von Mises; peaks are diagnostic, not certified strength",
        "Empirical two-step mesh convergence and declared uncertainty allowance are not rigorous error bounds",
        "Optional tested runtime is Linux amd64, CPU SPOOLES; no automatic remote provisioning",
    ],
    reference_checks=[
        "Uniform uniaxial solid displacement/stress",
        "Slender cantilever compliance",
        "Force/moment equilibrium",
        "C3D10 ordering and connected constrained mesh",
    ],
    routes=["v2"],
)

METRICS = {"mass_g": "g", "load_displacement_mm": "mm", "gauge_von_mises_mpa": "MPa"}


def setup(plan, test):
    if set(test.fixed_inputs) != {"structural"}:
        raise ValueError("calculix-static fixed_inputs must contain only the versioned structural setup")
    settings = StructuralSettings.model_validate(test.fixed_inputs["structural"])
    if test.simulation.solver_length_unit != "mm":
        raise ValueError("calculix-static uses explicit mm-N-MPa units only")
    if test.metrics != METRICS:
        raise ValueError("Declare all structural measured metrics with canonical units")
    if not {"mesh", "solver_deck", "fields", "convergence", "uncertainty"} <= set(
        test.simulation.required_evidence
    ):
        raise ValueError("All structural evidence types are required")
    interfaces = {i.id: i for i in plan.interfaces}
    if set(interfaces) != {*settings.clamped_interfaces, settings.load_interface}:
        raise ValueError("Every structural interface must be a clamp or the loaded face")
    if any(i.unit != "mm" or not i.region or i.region.expected_count != 1 for i in interfaces.values()):
        raise ValueError("Structural regions require single planar faces in mm")
    materials = [m for m in plan.materials if m.name == settings.material]
    if len(materials) != 1 or len(plan.materials) != 1:
        raise ValueError("Exactly one homogeneous material is supported")
    material = materials[0]
    if set(material.properties) != {"young_modulus", "poisson_ratio", "density"}:
        raise ValueError("Material needs only young_modulus, poisson_ratio and density")

    def q(name, unit, dim):
        p = material.properties[name]
        return convert(p.value, p.unit, unit, dim)

    elastic = {
        "young_mpa": q("young_modulus", "MPa", "pressure"),
        "poisson": q("poisson_ratio", "1", "dimensionless"),
        "density_g_mm3": q("density", "g/mm3", "density"),
    }
    if elastic["young_mpa"] <= 0 or elastic["density_g_mm3"] <= 0 or not 0 <= elastic["poisson"] <= 0.45:
        raise ValueError("Positive elastic modulus/density and Poisson ratio in [0,0.45] required")
    if len(test.load_cases) != 1 or test.load_cases[0].id != settings.load_case:
        raise ValueError("One specified load case per structural test is required")
    quantities = test.load_cases[0].quantities
    if set(quantities) != {"force_x", "force_y", "force_z"}:
        raise ValueError("Declare only the total uniform face force vector; no point loads/gravity/moments")
    force = [
        convert(quantities[k].value, quantities[k].unit, "N", "force")
        for k in ("force_x", "force_y", "force_z")
    ]
    if sum(v * v for v in force) <= 0:
        raise ValueError("Nonzero total load is required")
    return {
        "settings": settings.model_dump(),
        "material": elastic,
        "material_source": material.model_dump(),
        "force_n": force,
    }


def source():
    return files("davinci.product.structural").joinpath("solver.py").read_text()
