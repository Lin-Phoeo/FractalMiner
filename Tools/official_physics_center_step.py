"""Finite center-producing fragment of Team substep kernel369542/0x5a39fa0.

Consumes ALREADY resolved old/current frame center data and now-world history.
Generates clock interpolation, step transform, local-inertia ratios and angular
state for Start/End. It is NOT the preceding full frame-center/anchor/teleport
kernel369644, nor the remaining scale/gravity/weight/UpdateWind/publication tail.
No Unity/Burst execution, original arrays or full reset lifecycle is claimed.
Single operation order retained; Python trig/sqrt are not native CRT bit oracles.
Finite, positive dt, nonnegative indices/count and localInertia [0,1] restrictions
are ADAPTER policy, not newly discovered native clamps or fault behavior.
"""

import math
from dataclasses import dataclass, replace
from typing import cast

from official_physics_angle_baseline import _integer
from official_physics_angle_cache import (
    _quaternion,
    multiply_quaternions,
    quaternion_inverse,
)
from official_physics_angles import Quaternion, _float3
from official_physics_constraints import (
    Vector3,
    _add,
    _positive,
    _single,
    _sub,
    _vector,
)
from official_physics_particle_step import ResolvedCenter, _single_dot, _single_scale
from official_physics_setter import _dot, _lerp, interpolate_rotation
from official_physics_start_step import ResolvedStartCenter, _normalize_rotation

_ZERO: Vector3 = (0.0, 0.0, 0.0)
_IDENTITY: Quaternion = (0.0, 0.0, 0.0, 1.0)
_ANGLE_CUTOFF = _single(0.9999)
_PI, _TWO_PI = _single(math.pi), _single(2 * math.pi)
_DEGREES = _single(180 / math.pi)
_AXIS_EPSILON, _OMEGA_EPSILON = _single(1e-6), _single(1e-8)


@dataclass(frozen=True)
class CenterStepState:
    old_frame_world_position: Vector3
    old_frame_world_rotation: Quaternion
    frame_world_position: Vector3
    frame_world_rotation: Quaternion
    old_frame_world_scale: Vector3
    frame_world_scale: Vector3
    now_world_position: Vector3
    now_world_rotation: Quaternion


@dataclass(frozen=True)
class CenterStepTeam:
    flag: int
    update_count: int
    time: float
    frame_old_time: float
    now_update_time: float
    frame_interpolation: float


@dataclass(frozen=True)
class LocalInertiaSettings:
    local_inertia: float
    local_movement_speed_limit: float
    local_rotation_speed_limit: float


@dataclass(frozen=True)
class GeneratedStepCenter:
    old_world_position: Vector3
    old_world_rotation: Quaternion
    now_world_position: Vector3
    now_world_rotation: Quaternion
    world_scale: Vector3  # Local temporary; NOT a CenterData.nowWorldScale field.
    step_vector: Vector3
    step_rotation: Quaternion
    step_move_inertia_ratio: float
    step_rotation_inertia_ratio: float
    inertia_vector: Vector3
    inertia_rotation: Quaternion
    angular_velocity: float
    rotation_axis: Vector3

    def for_start(self) -> ResolvedStartCenter:
        return ResolvedStartCenter(
            self.old_world_position,
            self.inertia_vector,
            self.inertia_rotation,
            self.step_vector,
            self.step_rotation,
        )

    def for_end(self) -> ResolvedCenter:
        return ResolvedCenter(
            self.now_world_position, self.rotation_axis, self.angular_velocity
        )


@dataclass(frozen=True)
class CenterStepResult:
    team: CenterStepTeam
    next_state: CenterStepState
    center: GeneratedStepCenter | None
    writes: tuple[str, ...]  # Changed value fragments, NOT NativeArray writes.
    pending_tail: tuple[str, ...]


def quaternion_angle(a: Quaternion, b: Quaternion) -> float:
    """5a2b72c: abs-dot cutoff, signed clamped-dot acos then shortest fold."""
    dot = _dot(_quaternion(a), _quaternion(b))
    if abs(dot) >= _ANGLE_CUTOFF:
        return 0.0
    half = _single(math.acos(min(1.0, max(-1.0, dot))))
    angle = _single(half + half)
    return _single(_TWO_PI - angle) if angle > _PI else angle


def quaternion_angle_axis(q: Quaternion) -> tuple[float, Vector3]:
    """5a2bccc: signed w angle, xyz/sin(half); no shortest-arc sign repair."""
    q = _quaternion(q)
    half = _single(math.acos(q[3])) if abs(q[3]) < _ANGLE_CUTOFF else 0.0
    angle = _single(half + half)
    sine = _single(math.sin(half))
    axis = (
        _ZERO
        if abs(sine) < _AXIS_EPSILON
        else cast(Vector3, tuple(_single(lane / sine) for lane in q[:3]))
    )
    return angle, axis


def _limited_ratio(ratio: float, speed: float, limit: float) -> float:
    if speed > limit >= 0:
        return _single(_single(_single(limit / speed) * _single(ratio - 1)) + 1)
    return ratio


def advance_center_step(
    state: CenterStepState,
    team: CenterStepTeam,
    settings: LocalInertiaSettings,
    *,
    team_id: int,
    update_index: int,
    delta_time: float,
) -> CenterStepResult:
    """Process gate → clock → interpolated center → local inertia → omega/axis.

    Does NOT synthesize missing frame centers, initial matrices or reset data.
    The caller must complete pending_tail before actual Team/Center publication.
    No pending tail is silently omitted/assumed zero or claimed complete.
    """
    team_id = _integer(team_id, 2**31 - 1)
    index = _integer(update_index, 2**31 - 1)
    if team_id == 0:
        return CenterStepResult(team, state, None, (), ())
    flag = _integer(team.flag, 2**64 - 1)
    # IsEnable: low bit2 AND NOT bit61; IsProcess additionally excludes suspend/culling.
    if not flag & 2 or flag & ((1 << 61) | 0x10 | 0x800 | 0x80000):
        return CenterStepResult(team, state, None, (), ())
    active = index < _integer(team.update_count, 2**31 - 1)
    flag = (flag & ~0x80) | (0x80 if active else 0)
    if not active:
        return CenterStepResult(
            replace(team, flag=flag), state, None, ("team_step_flag",), ()
        )
    dt = _positive(delta_time)
    now_time = _single(_single(team.now_update_time) + dt)
    frame_old_time = _single(team.frame_old_time)
    span = _single(_single(team.time) - frame_old_time)
    t = (
        min(1.0, max(0.0, _single(_single(now_time - frame_old_time) / span)))
        if span > 0
        else 1.0
    )
    next_team = replace(
        team, flag=flag, now_update_time=now_time, frame_interpolation=t
    )
    a, b = _vector(state.old_frame_world_position), _vector(state.frame_world_position)
    now_position = _add(
        a, cast(Vector3, tuple((y - x) * t for x, y in zip(a, b, strict=True)))
    )
    now_rotation = _normalize_rotation(
        interpolate_rotation(
            state.old_frame_world_rotation, state.frame_world_rotation, t
        )
    )
    scale = _lerp(
        _float3(state.old_frame_world_scale), _float3(state.frame_world_scale), t
    )
    old_position, old_rotation = (
        _vector(state.now_world_position),
        _quaternion(state.now_world_rotation),
    )
    step_vector = _float3(_sub(now_position, old_position))
    # FromToRotation 5a2b85c: new * inverse(old), NOT inverse(old) * new.
    step_rotation = multiply_quaternions(now_rotation, quaternion_inverse(old_rotation))
    angle = quaternion_angle(old_rotation, now_rotation)
    local = _single(settings.local_inertia)
    if not 0 <= local <= 1:
        raise ValueError("Adapter local inertia must be in [0,1]")
    ratio = _single(1 - local)
    # Retain 1-ratio instead of replacing with local; cancellation can differ.
    weighted = _single_scale(step_vector, _single(1 - ratio))
    moving_speed = _single(_single(math.sqrt(_single_dot(weighted, weighted))) / dt)
    rotating_speed = _single(
        _single(_single(_single(1 - ratio) * angle) / dt) * _DEGREES
    )
    move_ratio = _limited_ratio(
        ratio, moving_speed, _single(settings.local_movement_speed_limit)
    )
    rotation_ratio = _limited_ratio(
        ratio, rotating_speed, _single(settings.local_rotation_speed_limit)
    )
    inertia_vector = _lerp(_ZERO, step_vector, move_ratio)
    inertia_rotation = interpolate_rotation(_IDENTITY, step_rotation, rotation_ratio)
    omega = _single(angle / dt)
    axis = quaternion_angle_axis(step_rotation)[1] if omega > _OMEGA_EPSILON else _ZERO
    center = GeneratedStepCenter(
        old_position,
        old_rotation,
        now_position,
        now_rotation,
        scale,
        step_vector,
        step_rotation,
        move_ratio,
        rotation_ratio,
        inertia_vector,
        inertia_rotation,
        omega,
        axis,
    )
    next_state = replace(
        state, now_world_position=now_position, now_world_rotation=now_rotation
    )
    return CenterStepResult(
        next_team,
        next_state,
        center,
        ("team_clock_fragment", "center_fragment"),
        ("scale_gravity_weight_fades", "UpdateWind", "native_publication"),
    )
