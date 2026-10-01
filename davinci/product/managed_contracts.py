"""Typed managed authoring protocol. No output field can certify physical evidence."""

from typing import Literal

from pydantic import Field, model_validator

from davinci.product.config import Strict
from davinci.product.contracts import (
    Assumption,
    Command,
    Evaluator,
    OpenExperiment,
    Plan,
    Requirement,
    Runtime,
)


class SearchPolicy(Strict):
    max_candidates: int = Field(default=6, ge=1, le=20)
    min_candidates: int = Field(default=2, ge=1, le=20)
    patience: int = Field(default=3, ge=1, le=20)
    min_improvement: float = Field(default=0.001, ge=0)
    optimize: bool = True
    stop_on_target: bool = True
    max_repairs: int = Field(default=1, ge=0, le=3)
    # Conservative reservations include failed/interrupted jobs; no automatic refunds.
    solver_compute_seconds: float = Field(default=100000, ge=1, le=1000000)
    max_solver_jobs: int = Field(default=40, ge=1, le=100)
    search: Literal["agent", "coordinate"] = "agent"

    @model_validator(mode="after")
    def ordered(self):
        if self.min_candidates > self.max_candidates:
            raise ValueError("min_candidates exceeds max_candidates")
        return self


class ManagedRequest(OpenExperiment):
    driver: Literal["managed"] = "managed"
    runtime: Runtime
    policy: SearchPolicy = Field(default_factory=SearchPolicy)
    # Optional inspected part is scoped to the same workspace; imported bytes use public fixtures.
    existing_experiment_id: str | None = None
    existing_candidate_id: str | None = None

    @model_validator(mode="after")
    def existing_pair(self):
        if bool(self.existing_experiment_id) != bool(self.existing_candidate_id):
            raise ValueError("Existing experiment and candidate IDs must be supplied together")
        return self


class BeamInputs(Strict):
    """Canonical recipe units, converted explicitly during request authoring."""

    length_mm: float = Field(gt=0, le=10000)
    width_mm: float = Field(gt=0, le=10000)
    thickness_min_mm: float = Field(gt=0)
    thickness_max_mm: float = Field(gt=0)
    force_n: float = Field(gt=0)
    youngs_mpa: float = Field(gt=0)
    density_g_mm3: float = Field(gt=0)
    stress_limit_mpa: float = Field(gt=0)
    deflection_limit_mm: float = Field(gt=0)
    material: str = Field(min_length=1)
    material_provenance: str = Field(min_length=1)
    input_provenance: dict[str, str] = Field(min_length=1)
    # Model must state applicability, not silently approximate unspecified physics.
    phenomena: list[str] = Field(min_length=1)
    material_model: str
    geometry: Literal["rectangular_prismatic_cantilever"]
    objective_target_g: float | None = Field(default=None, gt=0)

    @model_validator(mode="after")
    def bounds(self):
        if self.thickness_min_mm >= self.thickness_max_mm:
            raise ValueError("Thickness interval must be increasing")
        required = {
            "length_mm",
            "width_mm",
            "thickness_min_mm",
            "thickness_max_mm",
            "force_n",
            "youngs_mpa",
            "density_g_mm3",
            "stress_limit_mpa",
            "deflection_limit_mm",
        }
        if not required <= self.input_provenance.keys() or any(
            not x.strip() for x in self.input_provenance.values()
        ):
            raise ValueError("Every physical input and limit needs request/answer provenance")
        return self


class RequirementsOutput(Strict):
    requirements: list[Requirement] = Field(min_length=1, max_length=30)
    assumptions: list[Assumption] = Field(default_factory=list, max_length=30)
    questions: dict[str, str] = Field(default_factory=dict, max_length=10)
    recipe: Literal["rectangular-beam-v1", "unavailable"]
    inputs: BeamInputs | None = None
    unavailable_reason: str = ""


class TestPlanOutput(Strict):
    plan: Plan
    applicability_explanation: str = Field(min_length=1, max_length=4000)


class SetupOutput(Strict):
    evaluator: Evaluator


class DiagnosisOutput(Strict):
    lesson: str = Field(min_length=1, max_length=4000)
    action: Literal["design", "numerical", "evaluator_defect", "capability", "stop"]
    explanation: str = Field(min_length=1, max_length=4000)


class Answers(Command):
    answers: dict[str, str] = Field(min_length=1, max_length=10)


class StageInput(Strict):
    version: Literal[1] = 1
    stage: str
    description: str
    answers: list[dict] = Field(default_factory=list)
    requirements: dict | None = None
    plan: dict
    experience: list[dict] = Field(default_factory=list)
    candidates: list[dict] = Field(default_factory=list)
    results: list[dict] = Field(default_factory=list)
    existing: dict | None = None
    output_schema: dict
    guidance: dict = Field(default_factory=dict)
