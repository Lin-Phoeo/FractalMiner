"""Finite Team substep tail and wind STATE update, not a full wind/physics solver.

Tail of 369542/0x5a39fa0; UpdateWind managed369544/0x5a3af10 and
fallback0x5a2d8a8; UpdateWindTime managed369545/0x5a2d84c restricted entry.
Consumes already generated substep center, resolved zone list and FRAME moving
speed/direction. No wind-zone selection, turbulence/noise/particle-force helper,
frame-center/teleport/reset, NativeArray publication or Unity/Burst execution.
Single operation order retained; Python sqrt is not a CRT/Burst bit oracle.
Finite/positive dt and nonzero initial scale rejection are adapter safety only.
Values named writes are returned fragments, not actual native buffer mutation.
"""

import math
from dataclasses import dataclass, replace
from typing import cast

from official_physics_angle_cache import rotate_single
from official_physics_angles import _float3
from official_physics_center_step import CenterStepResult
from official_physics_constraints import Vector3, _positive, _single
from official_physics_particle_step import _single_dot

_EPSILON = _single(1e-6)
_DIRECTION_EPSILON = _single(1e-8)
_MOVING_WIND_EPSILON = _single(0.01)


@dataclass(frozen=True)
class TeamDynamicsState:
    init_scale: Vector3
    negative_scale_direction: Vector3
    velocity_weight: float
    distance_weight: float
    scale_ratio: float
    gravity_dot: float
    gravity_ratio: float
    blend_weight: float


@dataclass(frozen=True)
class TeamStepSettings:
    gravity: float
    world_gravity_direction: Vector3
    gravity_falloff: float
    stabilization_time_after_reset: float  # Metadata spells stablizationTimeAfterReset.
    blend_weight: float


@dataclass(frozen=True)
class WindInfo:
    wind_id: int
    time: float
    main: float
    direction: Vector3


@dataclass(frozen=True)
class TeamWindState:
    zones: tuple[WindInfo, ...]  # Caller-resolved active zone list, in source order.
    moving: WindInfo


@dataclass(frozen=True)
class WindStepSettings:
    influence: float
    frequency: float
    moving_wind: float


@dataclass(frozen=True)
class FrameWindState:
    frame_moving_speed: float  # CenterData @232; NOT stepVector.length / dt.
    frame_moving_direction: Vector3  # @236; do not replace with current step axis.


@dataclass(frozen=True)
class WindStepResult:
    state: TeamWindState
    writes: tuple[str, ...]


@dataclass(frozen=True)
class TeamTailResult:
    step: CenterStepResult
    dynamics: TeamDynamicsState
    wind: TeamWindState
    writes: tuple[str, ...]
    pending_tail: tuple[str, ...]
    pending_pipeline: tuple[str, ...]


def _clamp01(value: float) -> float:
    return min(1.0, max(0.0, value))


def advance_wind_time(
    info: WindInfo, *, frequency: float, delta_time: float
) -> WindInfo:
    """89-byte branch-complete0x5a2d84c: capped rate, one signed time wrap.

    ((main/7.5)*.5+.2)*frequency, min(rate,1.5), then time += rate*dt.
    If time>10000 subtract20000 ONCE, no modulo or lower-bound repair.
    ID/direction copied but never interpreted/validated in this source helper.
    """
    dt = _positive(delta_time)
    rate = _single(
        _single(
            _single(_single(_single(info.main) / _single(7.5)) * 0.5) + _single(0.2)
        )
        * _single(frequency)
    )
    rate = min(_single(1.5), rate)
    time = _single(_single(info.time) + _single(rate * dt))
    if time > _single(10000):
        time = _single(time - _single(20000))
    return replace(info, time=time)


def advance_wind_state(
    state: TeamWindState,
    settings: WindStepSettings,
    *,
    frame: FrameWindState | None,
    scale_ratio: float,
    delta_time: float,
) -> WindStepResult:
    """UpdateWind state only, resolved list snapshot; never returns particle force.

    influence<=1e-8 preserves previous WHOLE state, rather than clearing zones.
    Enabled updates every selected zone clock; movingWind<=.01 clears only its
    main, preserves old ID/time/direction, and skips frame/scale inputs entirely.
    Upstream membership/capacity and actual array slot writes remain caller work.
    """
    if _single(settings.influence) <= _DIRECTION_EPSILON:
        return WindStepResult(state, ())
    dt = _positive(delta_time)
    zones = tuple(
        advance_wind_time(info, frequency=settings.frequency, delta_time=dt)
        for info in state.zones
    )
    moving = replace(state.moving, main=0.0)
    factor = _single(settings.moving_wind)
    if factor > _MOVING_WIND_EPSILON:
        if frame is None:
            raise ValueError(
                "Adapter requires resolved source frame wind speed/direction"
            )
        main = _single(
            _single(_single(frame.frame_moving_speed) * factor) / _positive(scale_ratio)
        )
        direction = cast(
            Vector3, tuple(-lane for lane in _float3(frame.frame_moving_direction))
        )
        moving = advance_wind_time(
            replace(moving, main=main, direction=direction),
            frequency=settings.frequency,
            delta_time=dt,
        )
    return WindStepResult(TeamWindState(zones, moving), ("team_wind_state",))


def complete_team_step(
    step: CenterStepResult,
    team: TeamDynamicsState,
    settings: TeamStepSettings,
    *,
    init_local_gravity_direction: Vector3,
    wind: TeamWindState,
    wind_settings: WindStepSettings,
    frame_wind: FrameWindState | None,
    delta_time: float,
) -> TeamTailResult:
    """Center-produced active step → scale/gravity/weight → wind-state update.

    No LOD fade mutation: source computes blendWeight with velocity/distance,
    NOT clothSimulateWeight*clothLodFadeWeight. No reset flag consumption here.
    dt must be the same source substep input supplied to advance_center_step.
    pending_tail describes this Team fragment; pending_pipeline records major
    remaining upstream/force/solver boundaries, never cleared by this function.
    """
    center = step.center
    if center is None:
        return TeamTailResult(step, team, wind, (), (), ())
    dt = _positive(delta_time)
    initial = _float3(team.init_scale)
    initial_length = _positive(_single(math.sqrt(_single_dot(initial, initial))))
    scale = _float3(center.world_scale)
    scale_ratio = max(
        _EPSILON,
        _single(_single(math.sqrt(_single_dot(scale, scale))) / initial_length),
    )
    gravity_direction = _float3(settings.world_gravity_direction)
    gravity_dot = 1.0
    if _single_dot(gravity_direction, gravity_direction) > _DIRECTION_EPSILON:
        local = _float3(init_local_gravity_direction)
        local = (
            local[0],
            _single(local[1] * _single(team.negative_scale_direction[1])),
            local[2],
        )
        rotated = rotate_single(center.now_world_rotation, local)
        gravity_dot = _clamp01(
            _single(_single(_single_dot(rotated, gravity_direction) * 0.5) + 0.5)
        )
    gravity_ratio = 1.0
    if (
        _single(settings.gravity) > _EPSILON
        and _single(settings.gravity_falloff) > _EPSILON
    ):
        fall = _clamp01(_single(1 - _single(settings.gravity_falloff)))
        gravity_ratio = _single(
            _single(_clamp01(_single(1 - gravity_dot)) * _single(1 - fall)) + fall
        )
    weight = _single(team.velocity_weight)
    if weight < 1:
        stabilization = _single(settings.stabilization_time_after_reset)
        increment = _single(dt / stabilization) if stabilization > _EPSILON else 1.0
        weight = _clamp01(_single(weight + increment))
    blend = _clamp01(
        _single(
            _single(_single(settings.blend_weight) * weight)
            * _single(team.distance_weight)
        )
    )
    next_team = replace(
        team,
        scale_ratio=scale_ratio,
        gravity_dot=gravity_dot,
        gravity_ratio=gravity_ratio,
        velocity_weight=weight,
        blend_weight=blend,
    )
    next_wind = advance_wind_state(
        wind, wind_settings, frame=frame_wind, scale_ratio=scale_ratio, delta_time=dt
    )
    return TeamTailResult(
        step,
        next_team,
        next_wind.state,
        ("team_dynamics_fragment",) + next_wind.writes,
        ("native_publication",),
        (
            "frame_center_and_zone_selection",
            "particle_wind_force",
            "constraints_reset_and_publication",
        ),
    )
