"""Portable engineering experience is data, never a transferable acceptance score."""

from typing import Literal

from pydantic import Field, model_validator

from davinci.product.config import Strict


class ApplicabilityRange(Strict):
    minimum: float
    maximum: float
    unit: str
    dimension: str

    @model_validator(mode="after")
    def ordered(self):
        from davinci.product.units import validate_unit

        if self.minimum > self.maximum:
            raise ValueError("Applicability bounds are reversed")
        validate_unit(self.unit, self.dimension)
        return self


class Applicability(Strict):
    domain: str = ""
    phenomena: list[str] = Field(default_factory=list, max_length=30)
    materials: list[str] = Field(default_factory=list, max_length=30)
    quantities: dict[str, ApplicabilityRange] = Field(default_factory=dict)
    material_models: list[str] = Field(default_factory=list, max_length=30)
    processes: list[str] = Field(default_factory=list, max_length=30)
    load_regimes: list[str] = Field(default_factory=list, max_length=30)
    assumptions: list[str] = Field(default_factory=list, max_length=30)


class SourceReference(Strict):
    run_id: str
    candidate_id: str | None = None
    result_id: str | None = None
    test_ids: list[str] = Field(default_factory=list)
    tool_ids: list[str] = Field(default_factory=list)


class EvidenceArtifact(Strict):
    artifact_id: str = Field(pattern=r"^artifact-[a-f0-9]{64}$")
    sha256: str = Field(pattern=r"^[a-f0-9]{64}$")
    size: int = Field(ge=0)
    name: str
    media_type: str


class ExactInputs(Strict):
    geometry_sha256: str = Field(pattern=r"^[a-f0-9]{64}$")
    source_sha256: str = Field(pattern=r"^[a-f0-9]{64}$")
    suite_id: str = Field(min_length=1)
    evaluator_id: str = Field(min_length=1)
    runtime_id: str = Field(min_length=1)
    execution_id: str = Field(min_length=1)
    physical_inputs_hash: str = Field(min_length=1)
    numerical_settings_hash: str = Field(min_length=1)
    parameters_hash: str = Field(min_length=1)
    solver_observation_hash: str = Field(min_length=1)


class Experience(Strict):
    version: Literal[1] = 1
    id: str
    created_at: str
    workspace_id: str
    project_id: str
    access_scope: Literal["project", "workspace"] = "project"
    object_id: str
    kind: Literal["lesson", "observation", "test_recipe", "procedure", "tool_reference"]
    source: SourceReference
    request: str
    requirements: list[dict] = Field(default_factory=list)
    applicability: Applicability
    material_inputs: list[dict] = Field(default_factory=list)
    load_inputs: list[dict] = Field(default_factory=list)
    test_recipes: list[dict] = Field(default_factory=list)
    tested_tools: list[dict] = Field(default_factory=list)
    failure_modes: list[str] = Field(default_factory=list)
    attempted_change: str = ""
    measured_outcomes: list[dict] = Field(default_factory=list)
    claim: str = Field(min_length=1, max_length=12000)
    support: Literal["hypothesis", "simulation_supported", "measurement_supported"] = "hypothesis"
    confidence_basis: str
    local_evidence_status: Literal["unverified", "harness_observed", "imported_unverified"] = "unverified"
    artifacts: list[EvidenceArtifact] = Field(default_factory=list, max_length=300)
    origin: dict[str, str]
    provenance: dict[str, str] = Field(default_factory=dict)
    import_history: list[dict] = Field(default_factory=list)
    evidence_issues: list[str] = Field(default_factory=list)
    superseded_by: str | None = None
    supersession_reason: str | None = None
    revision: int = 0
    exact_inputs: ExactInputs | None = None
    transfers_acceptance: Literal[False] = False


class MemoryNote(Strict):
    operation_id: str = Field(min_length=1, max_length=100)
    actor: str = Field(min_length=1, max_length=100)
    experiment_id: str
    source: SourceReference | None = None
    kind: Literal["lesson", "test_recipe", "procedure", "tool_reference"] = "lesson"
    claim: str = Field(min_length=1, max_length=12000)
    applicability: Applicability | None = None


class MemorySearch(Strict):
    query: str = Field(default="", max_length=12000)
    experiment_id: str | None = None
    applicability: Applicability | None = None
    limit: int = Field(default=8, ge=1, le=50)
    cursor: str | None = Field(default=None, max_length=1000)
    include_incompatible: bool = True
    include_superseded: bool = False
    record_ids: list[str] | None = Field(default=None, max_length=100)


class Supersession(Strict):
    actor: str
    operation_id: str
    revision: int = Field(ge=0)
    replacement_id: str
    reason: str = Field(min_length=1, max_length=4000)


class PortableArtifact(EvidenceArtifact):
    data_base64: str = Field(max_length=24_000_000)


class MemoryBundle(Strict):
    version: Literal[1] = 1
    origin: dict[str, str]
    records: list[Experience] = Field(max_length=100)
    artifacts: list[PortableArtifact] = Field(default_factory=list, max_length=300)


class MemoryImport(Strict):
    operation_id: str
    actor: str
    bundle: MemoryBundle


class MemoryExport(Strict):
    ids: list[str] = Field(min_length=1, max_length=100)
    include_artifacts: bool = False
