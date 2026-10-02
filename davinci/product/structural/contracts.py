"""Frozen structural setup. No optional numerical imports on the host."""

from typing import Literal

from pydantic import Field, model_validator

from davinci.product.config import Strict


class StressRegion(Strict):
    lower_mm: tuple[float, float, float]
    upper_mm: tuple[float, float, float]
    exclusion_distance_mm: float = Field(gt=0)
    justification: str = Field(min_length=20)

    @model_validator(mode="after")
    def ordered(self):
        if any(a >= b for a, b in zip(self.lower_mm, self.upper_mm)):
            raise ValueError("Stress gauge must be a nonempty fixed spatial box")
        return self


class Refinement(Strict):
    initial_size_mm: float = Field(gt=0)
    factor: float = Field(default=0.7, ge=0.4, le=0.8)
    max_levels: int = Field(default=4, ge=3, le=5)
    relative_tolerance: float = Field(default=0.025, gt=0, le=0.05)
    # Two consecutive changes must satisfy tolerance; error reported is twice their maximum.
    displacement_floor_mm: float = Field(default=1e-7, gt=0, le=1e-5)
    stress_floor_mpa: float = Field(default=1e-5, gt=0, le=1e-3)
    max_nodes: int = Field(default=45000, ge=10, le=100000)
    max_elements: int = Field(default=30000, ge=1, le=80000)
    min_quality: float = Field(default=0.01, ge=0.001, le=0.5)
    max_volume_error: float = Field(default=0.01, gt=0, le=0.02)


class StructuralSettings(Strict):
    version: Literal[1] = 1
    element: Literal["C3D10"] = "C3D10"
    material: str
    clamped_interfaces: list[str] = Field(min_length=1, max_length=10)
    load_interface: str
    load_case: str
    stress_region: StressRegion
    mesh: Refinement
    equilibrium_tolerance: float = Field(default=0.001, gt=0, le=0.005)
    max_displacement_span_ratio: float = Field(default=0.02, gt=0, le=0.02)
    max_strain: float = Field(default=0.01, gt=0, le=0.01)
    relative_uncertainty: float = Field(default=0.05, ge=0, le=1)
    uncertainty_basis: str = Field(min_length=20)

    @model_validator(mode="after")
    def disjoint(self):
        if self.load_interface in self.clamped_interfaces or len(set(self.clamped_interfaces)) != len(
            self.clamped_interfaces
        ):
            raise ValueError("Load and unique clamp interfaces must be disjoint")
        return self
