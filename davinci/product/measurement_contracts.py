"""Attributed observations, not client-supplied simulation/acceptance results."""

from datetime import datetime
from typing import Literal

from pydantic import Field, model_validator

from davinci.product.config import Strict
from davinci.product.memory_contracts import PortableArtifact
from davinci.product.units import validate_unit


class ObservedQuantity(Strict):
    value: float
    unit: str
    dimension: str
    uncertainty: float = Field(ge=0)
    uncertainty_basis: str = Field(min_length=10, max_length=2000)
    uncertainty_kind: Literal["standard", "expanded", "interval_half_width"]
    coverage_factor: float | None = Field(default=None, ge=1)

    @model_validator(mode="after")
    def units(self):
        validate_unit(self.unit, self.dimension)
        if (self.uncertainty_kind == "expanded") != (self.coverage_factor is not None):
            raise ValueError("Coverage factor is required only for expanded uncertainty")
        return self


class CADRevision(Strict):
    experiment_id: str
    candidate_id: str
    result_id: str
    geometry_sha256: str = Field(pattern=r"^[a-f0-9]{64}$")
    source_sha256: str = Field(pattern=r"^[a-f0-9]{64}$")


class Specimen(Strict):
    specimen_id: str = Field(min_length=1, max_length=200)
    cad: CADRevision
    material: dict[str, str] = Field(min_length=1, max_length=30)
    process: dict[str, str] = Field(min_length=1, max_length=30)

    @model_validator(mode="after")
    def provenance(self):
        if (
            not {"name", "source", "batch"} <= self.material.keys()
            or not {"method", "source"} <= self.process.keys()
        ):
            raise ValueError("Material needs name/source/batch; process needs method/source")
        if any(not v.strip() or len(v) > 2000 for v in [*self.material.values(), *self.process.values()]):
            raise ValueError("Material/process attribution must be bounded and nonempty")
        return self


class MeasurementSetup(Strict):
    id: str = Field(min_length=1, max_length=200)
    revision: str = Field(min_length=1, max_length=100)
    description: str = Field(min_length=10, max_length=4000)
    instruments: list[str] = Field(min_length=1, max_length=20)
    conditions: dict[str, ObservedQuantity] = Field(default_factory=dict, max_length=30)
    source: str = Field(min_length=1, max_length=2000)


class PredictionLink(Strict):
    test_id: str
    metric: str
    comparability_basis: str = Field(min_length=20, max_length=2000)


class MeasurementInput(Strict):
    version: Literal[1] = 1
    specimen: Specimen
    partition: Literal["calibration", "held_out_validation"]
    evidence_kind: Literal["physical_measurement", "synthetic_fixture"]
    quantity_name: str = Field(min_length=1, max_length=100)
    quantity: ObservedQuantity
    setup: MeasurementSetup
    measured_at: datetime
    attribution: str = Field(min_length=1, max_length=2000)
    source: str = Field(min_length=1, max_length=2000)
    prediction: PredictionLink | None = None
    raw_artifact_ids: list[str] = Field(default_factory=list, max_length=20)
    supersedes: str | None = None

    @model_validator(mode="after")
    def aware(self):
        if self.measured_at.tzinfo is None:
            raise ValueError("Measurement timestamp must include timezone")
        return self


class EvidenceCommand(Strict):
    actor: str = Field(min_length=1, max_length=100)
    operation_id: str = Field(min_length=1, max_length=100)


class RecordMeasurement(EvidenceCommand):
    measurement: MeasurementInput
    artifacts: list[PortableArtifact] = Field(default_factory=list, max_length=20)


class CalibrationFit(EvidenceCommand):
    name: str = Field(min_length=1, max_length=100)
    measurement_ids: list[str] = Field(min_length=3, max_length=100)
    method: Literal["additive_offset_v1"] = "additive_offset_v1"
    applicability: str = Field(min_length=20, max_length=4000)
    predecessor_id: str | None = None


class CalibrationValidation(EvidenceCommand):
    calibration_id: str
    measurement_ids: list[str] = Field(min_length=1, max_length=100)


class EvidenceExport(Strict):
    ids: list[str] = Field(min_length=1, max_length=100)
    include_artifacts: bool = False


class EvidenceBundle(Strict):
    version: Literal[1] = 1
    origin: dict[str, str]
    records: list[dict] = Field(min_length=1, max_length=100)
    artifacts: list[PortableArtifact] = Field(default_factory=list, max_length=100)


class EvidenceRestore(EvidenceCommand):
    bundle: EvidenceBundle
