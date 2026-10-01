"""Public, provider-independent experiment protocol (version 2).

No executable builder or baseline is needed to author a Plan. Extension metadata
is descriptive only; acceptance is computed from the explicit fields below.
"""

from pathlib import PurePosixPath
from typing import Any, Literal

from jsonschema import Draft202012Validator
from pydantic import Field, model_validator

from davinci.product.config import ObjectConfig, Objective, Strict
from davinci.product.simulation_contracts import ArtifactManifest, RegionRule, SimulationSpec

Status = Literal[
    "pass", "physical_failure", "invalid_setup", "numerical_failure", "not_run", "unsupported_capability"
]
Reason = Literal[
    "ok",
    "acceptance_limit",
    "build_failed",
    "timeout",
    "cancelled",
    "resource_exhaustion",
    "invalid_geometry",
    "invalid_binding",
    "invalid_result",
    "missing_evidence",
    "solver_error",
    "unavailable_runtime",
    "unsupported_physics",
    "interrupted",
    "verification_failed",
    "invalid_units",
    "unsupported_material",
    "missing_solver",
    "artifact_quota",
]


class Contract(Strict):
    version: Literal[2] = 2
    metadata: dict[str, Any] = Field(default_factory=dict)


class Quantity(Strict):
    value: float = Field(strict=True)
    unit: str = Field(min_length=1)
    dimension: str = Field(min_length=1)


class Requirement(Strict):
    id: str = Field(min_length=1)
    description: str = Field(min_length=1)
    critical: bool = True
    resolved: bool = True
    quantity: Quantity | None = None
    source: str = Field(min_length=1)


class Assumption(Strict):
    description: str = Field(min_length=1)
    source: str = Field(min_length=1)
    applicability: str = Field(min_length=1)


class Material(Strict):
    name: str = Field(min_length=1)
    provenance: str = Field(min_length=1)
    properties: dict[str, Quantity]


class Interface(Strict):
    id: str
    description: str
    # The independent evaluator must validate this selector/binding, never the builder.
    binding_rule: str = Field(min_length=1)
    unit: str = Field(min_length=1)
    tolerance: float = Field(ge=0)
    region: RegionRule | None = None


class LoadCase(Strict):
    id: str
    description: str
    quantities: dict[str, Quantity]
    boundary_conditions: str = Field(min_length=1)


class Criterion(Strict):
    metric: str
    operator: Literal["<=", ">="]
    limit: float
    unit: str


class Accuracy(Strict):
    method: str = Field(min_length=1)
    max_numerical_error: float = Field(ge=0)
    max_uncertainty: float = Field(ge=0)


class Test(Contract):
    id: str = Field(pattern=r"^[a-z][a-z0-9_-]{0,63}$")
    requirements: list[str] = Field(min_length=1)
    required: bool = True
    capability: str = Field(min_length=1)
    applicability: str = Field(min_length=1)
    fixed_inputs: dict[str, Any] = Field(default_factory=dict)
    load_cases: list[LoadCase] = Field(default_factory=list)
    metrics: dict[str, str] = Field(min_length=1)
    criteria: list[Criterion] = Field(default_factory=list)
    accuracy: dict[str, Accuracy]
    mesh_rule: str = Field(min_length=1)
    simulation: SimulationSpec | None = None

    @model_validator(mode="after")
    def consistent(self):
        if set(self.metrics) != set(self.accuracy):
            raise ValueError("Every metric needs numerical accuracy and uncertainty requirements")
        if any(self.metrics.get(c.metric) != c.unit for c in self.criteria):
            raise ValueError("Criterion metric/unit mismatch")
        return self


class Plan(Contract):
    requirements: list[Requirement] = Field(default_factory=list)
    assumptions: list[Assumption] = Field(default_factory=list)
    materials: list[Material] = Field(default_factory=list)
    interfaces: list[Interface] = Field(default_factory=list)
    tests: list[Test] = Field(default_factory=list, max_length=30)
    objective: Objective | None = None
    # Editable variables are validated independently of fixed physical test inputs.
    design_schema: dict[str, Any] = Field(
        default_factory=lambda: {"type": "object", "additionalProperties": False}
    )
    design_units: dict[str, str] = Field(default_factory=dict)

    @model_validator(mode="after")
    def consistent(self):
        Draft202012Validator.check_schema(self.design_schema)

        def local_schema(value):
            if isinstance(value, dict):
                for key, child in value.items():
                    if key == "$id" or (
                        key in ("$ref", "$dynamicRef", "$recursiveRef")
                        and (not isinstance(child, str) or not child.startswith("#/"))
                    ):
                        raise ValueError(
                            "Design schemas may only reference local JSON pointers; no external resources"
                        )
                    local_schema(child)
            elif isinstance(value, list):
                for child in value:
                    local_schema(child)

        local_schema(self.design_schema)
        if (
            self.design_schema.get("type") != "object"
            or self.design_schema.get("additionalProperties") is not False
        ):
            raise ValueError("Design schema must be a closed object")
        if set(self.design_schema.get("properties", {})) != set(self.design_units):
            raise ValueError("Every editable variable needs a unit (use '1' for dimensionless)")
        if any(not unit.strip() for unit in self.design_units.values()):
            raise ValueError("Editable variable units cannot be blank")
        for rows in (self.requirements, self.interfaces, self.tests):
            if len({r.id for r in rows}) != len(rows):
                raise ValueError("Duplicate contract identifier")
        requirements = {r.id for r in self.requirements}
        for test in self.tests:
            if not set(test.requirements) <= requirements:
                raise ValueError("Test references unknown requirement")
            if set(test.fixed_inputs) & set(self.design_units):
                raise ValueError("Fixed inputs cannot also be editable variables")
        if self.objective and not any(self.objective.metric in t.metrics for t in self.tests):
            raise ValueError("Objective requires a declared test metric")
        units = {}
        for test in self.tests:
            for metric, unit in test.metrics.items():
                if metric in units and units[metric] != unit:
                    raise ValueError("Inconsistent metric units across tests")
                units[metric] = unit
        return self


class Evaluator(Contract):
    # Trusted task-author code, not a candidate contribution. No dynamic imports on the host.
    resources: dict[str, str] = Field(min_length=1)
    provenance: str = Field(min_length=1)

    @model_validator(mode="after")
    def paths(self):
        if "evaluate.py" not in self.resources:
            raise ValueError("Evaluator needs evaluate.py")
        for name in self.resources:
            p = PurePosixPath(name)
            if (
                p.is_absolute()
                or ".." in p.parts
                or str(p) != name
                or name.startswith("_")
                or p.suffix not in (".py", ".json", ".txt")
            ):
                raise ValueError("Invalid evaluator resource path")
        if sum(len(v.encode()) for v in self.resources.values()) > 2_000_000:
            raise ValueError("Evaluator exceeds 2 MB")
        return self


class Runtime(Contract):
    image: str = Field(pattern=r"^sha256:[a-f0-9]{64}$")
    solver: str = Field(min_length=1)
    provenance: str = Field(min_length=1)
    timeout_seconds: int = Field(default=180, ge=1, le=600)
    memory_gb: int = Field(default=4, ge=1, le=12)
    backend: Literal["docker", "remote"] = "docker"
    accelerator: Literal["none", "gpu"] = "none"
    cpu_cores: float = Field(default=2, ge=0.25, le=8)
    job_seconds: int = Field(default=1800, ge=1, le=3600)
    compute_seconds: float = Field(default=3600, ge=1, le=28800)
    artifact_bytes: int = Field(default=64_000_000, ge=1024, le=256_000_000)
    file_bytes: int = Field(default=32_000_000, ge=1024, le=128_000_000)
    log_bytes: int = Field(default=8_000_000, ge=1024, le=16_000_000)


class CapabilityReport(Contract):
    runtime_id: str
    test_id: str
    status: Literal["verified", "unavailable", "unverified"]
    reason: str
    verification_ids: list[str] = Field(default_factory=list)
    simulation: dict[str, Any] = Field(default_factory=dict)


class Coverage(Contract):
    requirement_tests: dict[str, list[str]]
    uncovered_critical: list[str]
    complete: bool


class Candidate(Contract):
    title: str = Field(min_length=1, max_length=100)
    change: str = Field(default="", max_length=2000)
    source: str = Field(min_length=1, max_length=40000)
    parameters: dict[str, Any]


class Measurement(Strict):
    value: float = Field(strict=True)
    unit: str
    numerical_error: float = Field(ge=0, strict=True)
    uncertainty: float = Field(ge=0, strict=True)


class TestResult(Contract):
    test_id: str
    status: Status
    reason: Reason
    message: str = Field(default="", max_length=4000)
    metrics: dict[str, Measurement] = Field(default_factory=dict)
    bindings: dict[str, bool] = Field(default_factory=dict)
    mesh_valid: bool = False
    applicable: bool = False

    @model_validator(mode="after")
    def reason_matches_status(self):
        reasons = {
            "pass": {"ok"},
            "physical_failure": {"acceptance_limit"},
            "invalid_setup": {
                "build_failed",
                "invalid_geometry",
                "invalid_binding",
                "invalid_result",
                "verification_failed",
                "invalid_units",
            },
            "numerical_failure": {"solver_error", "missing_evidence"},
            "not_run": {
                "timeout",
                "cancelled",
                "resource_exhaustion",
                "artifact_quota",
                "missing_evidence",
                "interrupted",
            },
            "unsupported_capability": {
                "unavailable_runtime",
                "unsupported_physics",
                "unsupported_material",
                "missing_solver",
            },
        }
        if self.reason not in reasons[self.status]:
            raise ValueError("Reason code does not match result status")
        return self


class SimulationJob(Contract):
    id: str
    candidate_id: str
    suite_id: str
    runtime_id: str
    owner: str
    status: Literal["running", "completed", "interrupted", "cancelled"]
    operation_id: str


class EvaluationResult(Contract):
    id: str
    candidate_id: str
    job: SimulationJob
    suite_id: str
    plan_id: str
    evaluator_id: str
    runtime_id: str
    execution_id: str
    source_artifact: str
    candidate_version: str
    tests: list[TestResult]
    artifacts: dict[str, str]
    manifest: ArtifactManifest | None = None
    duration_seconds: float = Field(ge=0)
    at: str
    actor: Literal["harness"] = "harness"
    execution_completed: bool
    evidence_complete: bool
    design_accepted: bool
    objective_target_attained: bool | None

    @model_validator(mode="after")
    def accepted_requires_evidence(self):
        if self.design_accepted and (not self.execution_completed or not self.evidence_complete):
            raise ValueError("Acceptance requires completed execution and evidence")
        return self


class ExperienceReference(Contract):
    experiment_id: str
    candidate_id: str
    result_id: str | None = None
    lesson: str = Field(min_length=1, max_length=4000)
    support: Literal["hypothesis", "linked_observation"] = "hypothesis"
    # Explicitly false even when retrieving experience from a matching suite.
    transfers_acceptance: Literal[False] = False


class OpenExperiment(Contract):
    object: ObjectConfig
    description: str = Field(min_length=1, max_length=12000)
    driver: Literal["external", "managed"] = "external"
    mode: Literal["live", "replay"] = "live"
    actor: str = Field(min_length=1, max_length=100)
    operation_id: str = Field(min_length=1, max_length=100)
    parent_experiment_id: str | None = None
    budget_usd: float = Field(default=10, gt=0, le=1000)


class Command(Strict):
    actor: str = Field(min_length=1, max_length=100)
    revision: int = Field(ge=0)
    operation_id: str = Field(min_length=1, max_length=100)


class Verification(Strict):
    test_id: str
    fixture_artifact: str
    expected_status: Literal["pass", "physical_failure", "invalid_setup"]
    # Independent reference values and tolerances, not evaluator-generated expected values.
    reference_metrics: dict[str, Quantity]
    tolerances: dict[str, float]
    provenance: str = Field(min_length=1)

    @model_validator(mode="after")
    def tolerances_match(self):
        if set(self.reference_metrics) != set(self.tolerances) or any(
            v < 0 for v in self.tolerances.values()
        ):
            raise ValueError("Reference metrics need nonnegative tolerances")
        return self


class ReferenceBuild(Strict):
    candidate: Candidate
    provenance: str = Field(min_length=1, max_length=4000)


class OperationStatus(Strict):
    version: Literal[2] = 2
    id: str
    experiment_id: str
    kind: Literal["evaluate", "verify", "reference_build"]
    owner: str
    operation_id: str
    status: Literal["queued", "running", "completed", "interrupted", "cancelled"]
    created_at: str
    started_at: str | None = None
    plan_id: str | None = None
    evaluator_id: str | None = None
    execution_id: str | None = None
    runtime_id: str
    suite_id: str | None = None
    candidate_id: str | None = None
    reason: str | None = None
    error_type: str | None = None
    result_ids: list[str] = Field(default_factory=list)
    verification_ids: list[str] = Field(default_factory=list)
    fixture_artifacts: list[str] = Field(default_factory=list)
    failures: list[dict[str, Any]] = Field(default_factory=list)
    next_actions: list[str] = Field(default_factory=list)


class PlanReadiness(Strict):
    version: Literal[2] = 2
    experiment_id: str
    revision: int
    issues: list[str]
    capabilities: list[CapabilityReport]
    ready_to_freeze: bool
    ready_for_draft: bool


class ReportExport(Strict):
    version: Literal[2] = 2
    experiment: dict[str, Any]
    report: dict[str, Any]
    artifacts_base_url: Literal["/api/v1/artifacts/"] = "/api/v1/artifacts/"
    contains_geometry_bytes: Literal[False] = False


class CLIEnvelope(Strict):
    version: Literal[2] = 2
    ok: bool
    data: Any
