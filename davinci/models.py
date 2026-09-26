import json
from datetime import datetime, timezone
from hashlib import sha256
from typing import Any, Literal
from uuid import uuid4

from pydantic import BaseModel, ConfigDict, Field


def now() -> str:
    return datetime.now(timezone.utc).isoformat()


def identity(prefix: str) -> str:
    return f"{prefix}-{uuid4().hex[:16]}"


def digest(value: Any) -> str:
    return sha256(
        json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False).encode()
    ).hexdigest()


def document(prefix: str, **fields) -> dict:
    return {"_id": identity(prefix), "schema_version": 1, "created_at": now(), **fields}


class RunRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    rounds: int = Field(default=4, ge=1, le=10)
    budget_usd: float = Field(default=10, gt=0, le=50)
    mode: Literal["replay", "live"] = "replay"


class Proposal(BaseModel):
    model_config = ConfigDict(extra="forbid")
    subsystem: Literal["structural", "aerodynamic"]
    parameters: dict[str, float]
    source: str = Field(min_length=1, max_length=40000)
    summary: str = Field(max_length=4000)


class ToolProposal(BaseModel):
    name: str = Field(pattern=r"^[a-z][a-z0-9_]{0,50}$")
    source: str = Field(max_length=40000)
    summary: str = Field(max_length=4000)


class PatchProposal(BaseModel):
    summary: str = Field(max_length=4000)
    files: dict[str, str]


SPECIFICATION = {
    "_id": "spec-demo-v1",
    "schema_version": 1,
    "project_id": "uas-demo",
    "name": "Passive sensor mount / VTOL surface screening fixture",
    "fidelity": "analytic_screening",
    "evaluator_version": "screening-v1",
    "coordinate_frame": "X forward, Y right, Z down; CadQuery mm, metrics SI",
    "material": {
        "id": "aluminum-demo",
        "density_kg_m3": 2700,
        "youngs_modulus_pa": 69e9,
        "allowable_stress_pa": 95e6,
    },
    "mount": {
        "width_mm": 40,
        "length_mm": 80,
        "load_n": 20,
        "minimum_thickness_mm": 2.5,
        "max_deflection_mm": 0.8,
        "max_mass_kg": 0.09,
        "hole_spacing_mm": 28,
    },
    "wing": {
        "span_mm": 600,
        "chord_mm": 120,
        "required_lift_n": 10,
        "airspeed_m_s": 20,
        "density_kg_m3": 1.225,
        "oswald_efficiency": 0.8,
        "min_hinge_gap_mm": 1.5,
        "travel_deg": [-20, -10, 0, 10, 20],
        "max_cl": 0.8,
        "max_mass_kg": 0.65,
    },
    "assembly": {"max_mass_kg": 0.72, "mount_translation_mm": [150, 0, 25]},
    "baseline": {
        "mount_thickness_mm": 6.0,
        "wing_thickness_mm": 2.0,
        "hinge_gap_mm": 2.0,
        "flap_fraction": 0.25,
    },
}
