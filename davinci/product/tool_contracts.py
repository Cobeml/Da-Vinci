"""Tool development contracts are separate from design/evaluator contracts."""

import math
from typing import Literal

from pydantic import Field, model_validator

from davinci.product.config import Strict
from davinci.product.contracts import Command, Runtime


class PlateArguments(Strict):
    unit: Literal["mm"] = "mm"
    length: float = Field(ge=5, le=500)
    width: float = Field(ge=5, le=500)
    thickness: float = Field(ge=0.5, le=50)
    radius: float = Field(ge=0.25, le=20)
    holes: list[tuple[float, float]] = Field(min_length=1, max_length=12)
    translation: tuple[float, float, float] = (0, 0, 0)

    @model_validator(mode="after")
    def separated(self):
        if any(abs(x) > 1000 for x in self.translation):
            raise ValueError("Translation exceeds CAD helper scope")
        for i, (x, y) in enumerate(self.holes):
            if abs(x) + self.radius + 0.25 > self.length / 2 or abs(y) + self.radius + 0.25 > self.width / 2:
                raise ValueError("Holes must have at least 0.25 mm edge clearance")
            if any(math.hypot(x - a, y - b) < 2 * self.radius + 0.25 for a, b in self.holes[:i]):
                raise ValueError("Holes overlap or lack 0.25 mm separation")
        return self


class ToolNeed(Strict):
    version: Literal[1] = 1
    operation_id: str = Field(min_length=1, max_length=100)
    actor: str = Field(min_length=1, max_length=100)
    experiment_id: str
    name: str = Field(pattern=r"^[a-z][a-z0-9-]{0,63}$")
    need: str = Field(min_length=10, max_length=4000)
    observations: list[str] = Field(min_length=1, max_length=20)


class ToolDefinition(Command):
    tool_class: Literal["perforated_plate_v1"] = "perforated_plate_v1"
    runtime: Runtime
    applicability: str = Field(min_length=20, max_length=2000)
    # Caller can restrict applicability in prose, never replace trusted tests/limits.
    promotion_policy: Literal["explicit_after_independent_checks"] = "explicit_after_independent_checks"


class ToolProposal(Command):
    source: str = Field(min_length=1, max_length=16000)
    summary: str = Field(min_length=1, max_length=2000)
    parent_version: str | None = None


class ToolVersionCommand(Command):
    version_id: str


class ToolPromotion(ToolVersionCommand):
    reason: str = Field(min_length=10, max_length=2000)


class ToolPin(Command):
    development_id: str
    version_id: str
    contract_id: str


class ToolInvocation(Command):
    experiment_id: str
    arguments: PlateArguments


class ManagedToolProposal(Command):
    development_id: str
    tool_revision: int = Field(ge=0)
