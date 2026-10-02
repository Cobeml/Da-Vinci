"""Small simulation contracts; no solver or model-provider imports."""

from typing import Literal

from pydantic import Field, model_validator

from davinci.product.config import Strict


class RegionRule(Strict):
    """Plan-owned planar face selector, expressed in interface units, never CAD indices."""

    kind: Literal["planar_face"] = "planar_face"
    center: tuple[float, float, float]
    normal: tuple[float, float, float]
    center_tolerance: tuple[float, float, float]
    normal_tolerance_degrees: float = Field(default=1, ge=0, le=45)
    extent_min: tuple[float, float, float]
    extent_max: tuple[float, float, float]
    expected_count: int = Field(default=1, ge=1, le=100)

    @model_validator(mode="after")
    def valid(self):
        if sum(x * x for x in self.normal) < 1e-12:
            raise ValueError("Region normal must be nonzero")
        if any(x < 0 for x in (*self.center_tolerance, *self.extent_min)):
            raise ValueError("Region tolerances and extents must be nonnegative")
        if any(a > b for a, b in zip(self.extent_min, self.extent_max)):
            raise ValueError("Region extent bounds are reversed")
        return self


class ResourceEstimate(Strict):
    cpu_cores: float = Field(default=1, gt=0, le=64)
    memory_mb: int = Field(default=512, ge=1)
    disk_mb: int = Field(default=128, ge=1)
    wall_seconds: float = Field(default=30, gt=0)
    basis: str = "Conservative starting estimate; refine from measured execution"
    uncertainty: str = "Unknown geometry-dependent peak; estimate is not proof of adequacy"


class SimulationSpec(Strict):
    version: Literal[1] = 1
    adapter: Literal[
        "authored-screen", "sensor-screen", "gripper-screen", "vtol-screen", "calculix-static"
    ] = "authored-screen"
    phenomena: list[str] = Field(min_length=1)
    material_model: str = Field(min_length=1)
    geometry_assumptions: str = Field(min_length=1)
    fidelity: str = Field(min_length=1)
    # Execution requires an installed, explicitly scoped adapter; no fidelity substitution.
    stage: Literal["preliminary", "final"] = "final"
    cad_unit: str = "mm"
    solver_length_unit: str = "mm"
    required_software: dict[str, str | None] = Field(default_factory=dict)
    estimate: ResourceEstimate = Field(default_factory=ResourceEstimate)
    required_evidence: list[Literal["mesh", "solver_deck", "fields", "convergence", "uncertainty"]] = Field(
        default_factory=list
    )


class AdapterDescriptor(Strict):
    id: str
    version: Literal[1] = 1
    phenomena: list[str]
    material_models: list[str]
    geometry_assumptions: str
    fidelities: list[str]
    limitations: list[str]
    required_software: dict[str, str | None]
    reference_checks: list[str]
    lifecycle: list[str] = ["validate_setup", "estimate", "prepare", "execute", "extract", "reference_check"]
    routes: list[str]


class ArtifactEntry(Strict):
    name: str
    artifact_id: str
    sha256: str = Field(pattern=r"^[a-f0-9]{64}$")
    size: int = Field(ge=0)
    media_type: str
    kind: Literal[
        "cad",
        "mesh",
        "bindings",
        "solver_deck",
        "log",
        "resources",
        "fields",
        "convergence",
        "uncertainty",
        "result",
        "other",
    ]


class ArtifactManifest(Strict):
    version: Literal[1] = 1
    provenance: dict[str, str]
    entries: list[ArtifactEntry]
    total_bytes: int = Field(ge=0)
    complete: bool = True
    omissions: list[str] = Field(default_factory=list)
