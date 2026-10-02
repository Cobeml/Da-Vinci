"""Explicit SI dynamics with CAD selection in mm. No arbitrary MJCF from candidates."""

from typing import Literal

from pydantic import Field, model_validator

from davinci.product.config import Strict


class Body(Strict):
    name: Literal["base", "carriage"]
    interface: str
    material: str
    role: Literal["fixed", "moving"]
    frame: Literal["CAD_world_axes_at_BRep_COM"] = "CAD_world_axes_at_BRep_COM"
    inertia: Literal["homogeneous_STEP_volume_integral"] = "homogeneous_STEP_volume_integral"
    collision: Literal["axis_aligned_envelope_bottom_plane_only"] = "axis_aligned_envelope_bottom_plane_only"


class SliderSettings(Strict):
    version: Literal[1] = 1
    bodies: list[Body] = Field(min_length=2, max_length=2)
    joint: Literal["ideal_prismatic_world_z"] = "ideal_prismatic_world_z"
    joint_axis: tuple[Literal[0], Literal[0], Literal[1]] = (0, 0, 1)
    joint_damping: Literal[0] = 0
    actuator: Literal["gravity_compensated_force_limited_motor_PD"] = (
        "gravity_compensated_force_limited_motor_PD"
    )
    force_limit_n: float = Field(default=0.4, gt=0, le=100)
    kp_n_m: float = Field(default=40, gt=0, le=1000)
    kd_ns_m: float = Field(default=2, gt=0, le=100)
    gravity_m_s2: float = Field(default=9.81, gt=0, le=20)
    # Piecewise-linear target: zero at t=0, target at ramp_seconds, then hold.
    target_m: float = Field(default=0.03, gt=0, le=0.1)
    ramp_seconds: float = Field(default=0.5, ge=0.1, le=2)
    duration_seconds: float = Field(default=2, ge=1, le=5)
    timestep_seconds: float = Field(default=0.00025, ge=0.0001, le=0.002)
    integrator: Literal["implicitfast"] = "implicitfast"
    refinement_levels: Literal[3] = 3
    max_position_difference_m: float = Field(default=0.0001, gt=0, le=0.001)
    max_force_difference_n: float = Field(default=0.002, gt=0, le=0.01)
    contact: Literal["frictionless_soft_normal"] = "frictionless_soft_normal"
    friction: tuple[Literal[0], Literal[0], Literal[0]] = (0, 0, 0)
    solref: tuple[Literal[0.01], Literal[1]] = (0.01, 1)
    solimp: tuple[Literal[0.95], Literal[0.99], Literal[0.001]] = (0.95, 0.99, 0.001)
    scenarios: tuple[Literal["lift"], Literal["settle"]] = ("lift", "settle")
    approximation: str = Field(min_length=30, max_length=2000)

    @model_validator(mode="after")
    def topology(self):
        if {b.name: b.role for b in self.bodies} != {"base": "fixed", "carriage": "moving"}:
            raise ValueError("Exactly one fixed base and one moving carriage required")
        if len({b.interface for b in self.bodies}) != 2:
            raise ValueError("Body interfaces must be distinct")
        if self.ramp_seconds >= self.duration_seconds:
            raise ValueError("Scenario needs a target hold interval")
        if self.duration_seconds / (self.timestep_seconds / 4) > 80000:
            raise ValueError("Refined workload exceeds 80000 steps per scenario")
        return self
