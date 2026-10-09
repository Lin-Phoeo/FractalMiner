"""Finite resolved frame-inertia correction inside kernel369644/0x5a34900.

Region 0x5a36313..0x5a36ab1 consumes the current component transform and an
ALREADY resolved working old-component transform. It restores global following,
speed limits, count/time/velocity compensation, world-history shifts and the
final residual handed to frame motion. Anchor/negative-scale/teleport prelude,
centroid generation, wind-zone selection and native publication are pending.

All Single boundaries and Double add/subtract/lerp order are retained. Python
trig/sqrt are mathematical references, not game CRT/Burst bit oracles. Finite
values, nonnegative counts/timeScale/scale ratio, [0,1] inertia/velocity weights
and nonzero compensation denominator are ADAPTER restrictions.
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
from official_physics_center_step import CenterStepState, quaternion_angle
from official_physics_constraints import (
    Vector3,
    _add,
    _positive,
    _single,
    _sub,
    _vector,
)
from official_physics_frame_motion import FrameMotionResult, reduce_frame_motion
from official_physics_particle_step import _single_dot, _single_scale
from official_physics_setter import interpolate_rotation
from official_physics_writeback import rotate_double

_ZERO: Vector3 = (0.0, 0.0, 0.0)
_IDENTITY: Quaternion = (0.0, 0.0, 0.0, 1.0)
_FOLLOW_EPSILON = _single(1e-8)
_DEGREES = _single(180 / math.pi)


@dataclass(frozen=True)
class FrameInertiaState:
    component_world_position: Vector3  # Current transformPositionArray sample.
    component_world_rotation: Quaternion
    working_old_component_position: Vector3  # After the preceding frame prelude.
    working_old_component_rotation: Quaternion
    old_component_world_position: Vector3  # Resolved prelude's CenterData @152 pivot.
    anchor_shift_vector: Vector3  # Prior local temporary, Single.
    anchor_shift_rotation: Quaternion  # Prior local temporary, Single.
    smoothing_shift_vector: Vector3  # Separate resolved prelude temporary, Single.
    step_state: CenterStepState  # History from the SAME resolved prelude snapshot.
    smoothing_velocity: Vector3


@dataclass(frozen=True)
class FrameInertiaTeam:
    flag: int
    frame_delta_time: float
    now_time_scale: float
    update_count: int
    velocity_weight: float  # @252, not blendWeight @260.
    simulation_delta_time: float  # Kernel's first argument.


@dataclass(frozen=True)
class FrameInertiaSettings:
    world_inertia: float
    movement_speed_limit: float
    rotation_speed_limit: float
    scale_length_ratio: float  # Local prelude result, not Team.scaleRatio @96.


@dataclass(frozen=True)
class FrameInertiaResult:
    flag: int
    corrected_old_component_position: Vector3  # Local temporary, not a field write.
    component_shift_vector: Vector3
    component_shift_rotation: Quaternion
    translation_fraction: float
    rotation_fraction: float
    compensation_fraction: float
    step_state: CenterStepState
    smoothing_velocity: Vector3
    world_history_shifted: bool
    motion: FrameMotionResult


def _length_single(vector: Vector3) -> float:
    return _single(math.sqrt(_single_dot(vector, vector)))


def frame_scale_length_ratio(
    component_world_scale: Vector3, team_initial_scale: Vector3
) -> float:
    """5a34d26..5a34dfd: Single length(current scale)/length(Team.initScale)."""
    numerator = _length_single(_float3(component_world_scale))
    denominator = _positive(_length_single(_float3(team_initial_scale)))
    return _single(numerator / denominator)


def shift_world_position(
    old_position: Vector3,
    old_pivot_position: Vector3,
    shift_vector: Vector3,
    shift_rotation: Quaternion,
) -> Vector3:
    """371221/5a8991c: (shift + rotate(q, old-pivot)) + pivot, all Double."""
    old, pivot, shift = map(_vector, (old_position, old_pivot_position, shift_vector))
    rotated = rotate_double(shift_rotation, _sub(old, pivot))
    return _add(_add(shift, rotated), pivot)


def _lerp_double(a: Vector3, b: Vector3, single_weight: float) -> Vector3:
    # 59eac0c calls double3 subtract -> multiply by widened weight -> add.
    delta = _sub(b, a)
    return _add(a, cast(Vector3, tuple(lane * single_weight for lane in delta)))


def _accumulate_fraction(previous: float, weight: float) -> float:
    return _single(_single(_single(1 - previous) * weight) + previous)


def _speed_limit_weight(speed: float, limit: float) -> float:
    return min(1.0, max(0.0, _single(max(_single(speed - limit), 0.0) / speed)))


def advance_frame_inertia(
    state: FrameInertiaState, team: FrameInertiaTeam, settings: FrameInertiaSettings
) -> FrameInertiaResult:
    """Evaluate the correction region AFTER caller-resolved frame prelude.

    The reset branch here only clears shift/smoothing; the earlier reset prelude
    must already have resolved working transforms and world history. A preexisting
    InertiaShift flag also consumes the supplied anchor/smoothing temporaries.
    The pivot and step_state must come from the same resolved prelude snapshot;
    sign changes may remap that pivot before this region. Smoothing velocity is
    separate state and cannot substitute for the smoothing shift temporary.
    The returned step_state feeds advance_center_step; it changes old-frame/now
    history only. No flag, CenterData or NativeArray is mutated in place.
    """
    flag = _integer(team.flag, 2**64 - 1)
    current, work = map(
        _vector, (state.component_world_position, state.working_old_component_position)
    )
    dt, time_scale = _single(team.frame_delta_time), _single(team.now_time_scale)
    count = _integer(team.update_count, 2**31 - 1)
    if time_scale < 0:
        raise ValueError("Adapter requires nonnegative nowTimeScale")
    move_fraction = rotation_fraction = compensation = 0.0
    step = state.step_state
    smoothing = state.smoothing_velocity
    shifted = False
    if flag & 4:
        shift, shift_rotation, smoothing = _ZERO, _IDENTITY, _ZERO
    else:
        world = _single(settings.world_inertia)
        velocity_weight = _single(team.velocity_weight)
        ratio = _single(settings.scale_length_ratio)
        if not 0 <= world <= 1 or not 0 <= velocity_weight <= 1 or ratio < 0:
            raise ValueError(
                "Adapter requires [0,1] weights and nonnegative scale ratio"
            )
        move_limit = _single(ratio * _single(settings.movement_speed_limit))
        rotation_limit = _single(settings.rotation_speed_limit)
        current_rotation = _quaternion(state.component_world_rotation)
        work_rotation = _quaternion(state.working_old_component_rotation)
        initial_delta = _float3(_sub(current, work))
        initial_rotation = multiply_quaternions(
            current_rotation, quaternion_inverse(work_rotation)
        )
        shift, shift_rotation = initial_delta, initial_rotation
        global_fraction = _single(1 - world)
        if flag & (0x200 | 0x800 | 0x80000):
            global_fraction = 1.0
        if global_fraction > _FOLLOW_EPSILON:
            flag |= 0x400
            move_fraction = rotation_fraction = global_fraction
            work = _lerp_double(work, current, global_fraction)
            work_rotation = interpolate_rotation(
                work_rotation, current_rotation, global_fraction
            )
        delta = _float3(_sub(current, work))
        angle = quaternion_angle(work_rotation, current_rotation)
        move_speed = _single(_length_single(delta) / dt) if dt > 0 else 0.0
        rotation_speed = _single(_single(angle * _DEGREES) / dt) if dt > 0 else 0.0
        if move_speed > move_limit >= 0:
            weight = _speed_limit_weight(move_speed, move_limit)
            flag |= 0x400
            move_fraction = _accumulate_fraction(move_fraction, weight)
            work = _lerp_double(work, current, weight)
        if rotation_speed > rotation_limit >= 0:
            weight = _speed_limit_weight(rotation_speed, rotation_limit)
            flag |= 0x400
            rotation_fraction = _accumulate_fraction(rotation_fraction, weight)
            work_rotation = interpolate_rotation(
                work_rotation, current_rotation, weight
            )
        if count > 0:
            numerator = _single(_single(count) * _single(team.simulation_delta_time))
            denominator = _single(time_scale * dt)
            if denominator == 0:
                raise ValueError("Adapter requires nonzero compensation denominator")
            compensation = min(1.0, max(0.0, _single(numerator / denominator)))
        if velocity_weight < 1:
            compensation = _single(
                _single(_single(1 - velocity_weight) * _single(1 - compensation))
                + compensation
            )
        if time_scale < 1:
            compensation = _single(
                _single(_single(1 - time_scale) * _single(1 - compensation))
                + compensation
            )
        if compensation > 0:
            flag |= 0x400
            move_fraction = _accumulate_fraction(move_fraction, compensation)
            rotation_fraction = _accumulate_fraction(rotation_fraction, compensation)
            work = _lerp_double(work, current, compensation)
            # Source invokes slerp here but doesn't retain its result in xmm11.
            interpolate_rotation(work_rotation, current_rotation, compensation)
        if flag & 0x400:
            shifted = True
            shift = _float3(
                _add(
                    _single_scale(initial_delta, move_fraction),
                    _float3(state.anchor_shift_vector),
                )
            )
            # 5a3689b then 5a36901: two Single adds, not combined offsets.
            shift = _float3(_add(shift, _float3(state.smoothing_shift_vector)))
            shift_rotation = multiply_quaternions(
                state.anchor_shift_rotation,
                interpolate_rotation(_IDENTITY, initial_rotation, rotation_fraction),
            )
            pivot = _vector(state.old_component_world_position)
            step = replace(
                step,
                old_frame_world_position=shift_world_position(
                    step.old_frame_world_position, pivot, shift, shift_rotation
                ),
                old_frame_world_rotation=multiply_quaternions(
                    shift_rotation, step.old_frame_world_rotation
                ),
                now_world_position=shift_world_position(
                    step.now_world_position, pivot, shift, shift_rotation
                ),
                now_world_rotation=multiply_quaternions(
                    shift_rotation, step.now_world_rotation
                ),
            )
    motion = reduce_frame_motion(
        _sub(current, work), frame_delta_time=dt, now_time_scale=time_scale
    )
    return FrameInertiaResult(
        flag,
        work,
        shift,
        shift_rotation,
        move_fraction,
        rotation_fraction,
        compensation,
        step,
        smoothing,
        shifted,
        motion,
    )
