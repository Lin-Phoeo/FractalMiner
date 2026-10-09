"""Finite teleport/smoothing/history prelude, kernel369644/5a35eba..5a36313.

Requires the preceding anchor/sign-remap inputs AND already generated frameWorld
target. Produces working-old and smoothing offset for advance_frame_inertia.
Only fields represented by FrameInertiaState are returned: not full CenterData,
NativeArray publication, sampling, anchor, TRS inverse or complete reset lifecycle.
Single operation order preserved; Python pow/sqrt are not native bit oracles.
Finite inputs, [0,1] smoothing, nonnegative ratio and modes0..2 are adapter policy.
"""

import math
from dataclasses import dataclass, replace
from typing import cast

from official_physics_angle_baseline import _integer
from official_physics_angle_cache import _quaternion
from official_physics_angles import _float3
from official_physics_center_step import quaternion_angle
from official_physics_constraints import Vector3, _single, _sub, _vector
from official_physics_frame_inertia import (
    FrameInertiaState,
    FrameInertiaTeam,
    _length_single,
)
from official_physics_particle_step import _single_scale
from official_physics_setter import _lerp

_ZERO: Vector3 = (0.0, 0.0, 0.0)
_SMOOTH_EPSILON = _single(1e-6)
_LENGTH_EPSILON = _single(1e-9)
_DEGREES = _single(180 / math.pi)


@dataclass(frozen=True)
class FramePreludeSettings:
    movement_inertia_smoothing: float
    movement_speed_limit: float
    scale_length_ratio: float  # The same source-local ratio used by frame correction.
    teleport_mode: int  # Numeric source modes 0/1/2; no enum-name guessing.
    teleport_distance: float
    teleport_rotation: float  # Degrees, comparison includes equality.


@dataclass(frozen=True)
class FramePreludeResult:
    state: FrameInertiaState
    team: FrameInertiaTeam
    teleport_triggered: bool
    velocity_updated: bool
    smoothing_applied: bool
    history_reinitialized: bool


def smoothing_gain(amount: float) -> float:
    """5a36094..5a360e2: clamp01(Single(Single(powF(1-s,3)*.99f)+.01f))."""
    amount = _single(amount)
    if not 0 <= amount <= 1:
        raise ValueError("Adapter smoothing must be in [0,1]")
    power = _single(math.pow(_single(1 - amount), 3.0))
    return min(1.0, max(0.0, _single(_single(power * _single(0.99)) + _single(0.01))))


def _clamp_velocity(vector: Vector3, limit: float) -> Vector3:
    # 5a2b7b0 mutates the input; adapter returns a value instead.
    length = _length_single(vector)
    if length > _LENGTH_EPSILON and length > limit:
        return _single_scale(vector, _single(limit / length))
    return vector


def prepare_frame_inertia(
    state: FrameInertiaState, team: FrameInertiaTeam, settings: FramePreludeSettings
) -> FramePreludeResult:
    """Anchor-resolved inputs → teleport flags → smoothing → history reset fragment.

    Incoming smoothing_shift_vector is overwritten (native temporary is zeroed).
    step_state.frame_world_* must be the SAME frame's resolved center target;
    this function cannot generate it from a scene root. Reset copies only the
    component/history fields represented here. A later frame-correction reset
    branch clears shift/smoothing; do not omit that subsequent call.
    """
    flag = _integer(team.flag, 2**64 - 1)
    current, work = map(
        _vector, (state.component_world_position, state.working_old_component_position)
    )
    current_rotation = _quaternion(state.component_world_rotation)
    work_rotation = _quaternion(state.working_old_component_rotation)
    delta = _float3(_sub(current, work))
    angle = quaternion_angle(work_rotation, current_rotation)
    dt = _single(team.frame_delta_time)
    ratio = _single(settings.scale_length_ratio)
    if ratio < 0:
        raise ValueError("Adapter scale length ratio must be nonnegative")
    triggered = updated = active = False
    if not flag & (0x200 | 4):
        mode = _integer(settings.teleport_mode, 2)
        if mode:
            distance_limit = _single(ratio * _single(settings.teleport_distance))
            rotation_limit = _single(settings.teleport_rotation)
            if (
                _length_single(delta) >= distance_limit
                or _single(angle * _DEGREES) >= rotation_limit
            ):
                flag |= 4 if mode == 1 else 0x200
                triggered = True
    smoothing = _single(settings.movement_inertia_smoothing)
    if not 0 <= smoothing <= 1:
        raise ValueError("Adapter smoothing must be in [0,1]")
    velocity = state.smoothing_velocity
    shift = _ZERO
    if smoothing >= _SMOOTH_EPSILON:
        active = True
        velocity = _float3(velocity)
        if flag & 0x20:
            target = (
                _float3(cast(Vector3, tuple(_single(v / dt) for v in delta)))
                if dt > 0
                else _ZERO
            )
            limit = _single(ratio * _single(settings.movement_speed_limit))
            if limit >= 0:
                target = _clamp_velocity(target, limit)
            velocity = _lerp(velocity, target, smoothing_gain(smoothing))
            updated = True
        displacement = _single_scale(velocity, dt)
        new_work = _sub(current, displacement)  # Widen each Single displacement lane.
        shift = _float3(
            _sub(new_work, work)
        )  # SECOND Double subtraction before narrowing.
        work = new_work
        flag |= 0x400
    history = state.step_state
    pivot = state.old_component_world_position
    reinitialized = bool(flag & (4 | 0x40000))
    if flag & 4:
        work, work_rotation, pivot = current, current_rotation, current
    if reinitialized:
        position = _vector(history.frame_world_position)
        rotation = _quaternion(history.frame_world_rotation)
        history = replace(
            history,
            old_frame_world_position=position,
            old_frame_world_rotation=rotation,
            old_frame_world_scale=_float3(history.frame_world_scale),
            now_world_position=position,
            now_world_rotation=rotation,
        )
    resolved = replace(
        state,
        working_old_component_position=work,
        working_old_component_rotation=work_rotation,
        old_component_world_position=pivot,
        smoothing_shift_vector=shift,
        smoothing_velocity=velocity,
        step_state=history,
    )
    return FramePreludeResult(
        resolved, replace(team, flag=flag), triggered, updated, active, reinitialized
    )
