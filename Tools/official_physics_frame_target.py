"""Finite fixed-point frame target, kernel369644/5a35365..5a357a1.

Consumes original global proxy arrays and Team fixedDataChunk/proxyCommonChunk.
No list generation, allocator, skinning, Job scheduling or NativeArray publication.
Y/Z axes retained; native39d4200 swaps to forward/up ABI, while the existing
rotation value API takes up/forward. Do not swap that API's arguments again. Existing
Single helpers preserve operation grouping. Finite/range/parallel/degenerate
rejection is ADAPTER policy; native unsafe normalize can propagate NaN/Inf.
Python math is not a CRT/Burst/MXCSR live bit oracle.
"""

from collections.abc import Sequence
from dataclasses import dataclass, replace
from typing import cast

from official_physics_angle_baseline import _index, _integer
from official_physics_angle_cache import (
    _quaternion,
    multiply_quaternions,
    rotate_single,
)
from official_physics_angles import Quaternion, _float3
from official_physics_center_step import CenterStepState
from official_physics_constraints import Vector3, _add, _single, _vector
from official_physics_proxy_baseline import (
    _int32,
    _normalization_scale,
    rotation_from_normal_tangent,
)

_ZERO: Vector3 = (0.0, 0.0, 0.0)
_Y: Vector3 = (0.0, 1.0, 0.0)
_Z: Vector3 = (0.0, 0.0, 1.0)


@dataclass(frozen=True)
class ComponentFrameSample:
    position: Vector3  # Double3, current component transform sample.
    rotation: Quaternion  # Single4, no normalization of this input.
    scale: Vector3  # Single3, same sample used by frame matrices.


@dataclass(frozen=True)
class FrameTargetTeam:
    fixed_point_start: int  # Team.fixedDataChunk.startIndex @364, Int32.
    fixed_point_count: int  # Team.fixedDataChunk.dataLength @368, Int32.
    proxy_chunk_start: int  # Team.proxyCommonChunk.startIndex @292, Int32.
    negative_scale_sign: float  # Team @100, distinct from per-axis direction.
    negative_scale_direction: Vector3  # Team @104, fresh preceding scale caches.


@dataclass(frozen=True)
class FrameTargetBuffers:
    fixed_point_data: Sequence[int]  # UInt16 LOCAL proxy slots, original list order.
    proxy_positions: Sequence[Vector3]  # Global Double3.
    proxy_rotations: Sequence[Quaternion]  # Global Single4.
    proxy_bind_rotations: Sequence[Quaternion]  # Global vertexBindPoseRotations.


@dataclass(frozen=True)
class FrameTargetResult:
    position: Vector3
    rotation: Quaternion
    scale: Vector3
    proxy_slots: tuple[int, ...]  # Trace only, not an extra original field.


def _normalize_single(vector: Vector3) -> Vector3:
    scale = _normalization_scale(vector)
    return cast(Vector3, tuple(_single(scale * value) for value in vector))


def _sum_single(a: Vector3, b: Vector3) -> Vector3:
    return cast(Vector3, tuple(_single(x + y) for x, y in zip(a, b, strict=True)))


def produce_frame_target(
    component: ComponentFrameSample,
    team: FrameTargetTeam,
    buffers: FrameTargetBuffers,
) -> FrameTargetResult:
    """Component seed → ordered fixed-point Double mean + Single axis reduction.

    count<=0 preserves raw component position/rotation/scale and reads no list/caches.
    Otherwise pointQuaternion (after optional negative reconstruction) LEFT-multiplies
    bindQuaternion. Accumulated rotated +Y/+Z each receive separate OR-derived signs,
    then normalize independently.39d4200(firstY,secondZ) calls39d4250(forwardZ,upY);
    the existing rotation_from_normal_tangent API instead takes (upY,forwardZ).
    Do not average quaternions, swap these axes back or infer a safe fallback.
    """
    position = _vector(component.position)
    rotation = _quaternion(component.rotation)
    scale = _float3(component.scale)
    count = _int32(team.fixed_point_count)
    if count <= 0:
        return FrameTargetResult(position, rotation, scale, ())
    start = _integer(team.fixed_point_start, 2**31 - 1)
    chunk = _integer(team.proxy_chunk_start, 2**31 - 1)
    if start + count > len(buffers.fixed_point_data):
        raise ValueError("Adapter fixed-point slice exceeds supplied original list")
    size = len(buffers.proxy_positions)
    if (
        len(buffers.proxy_rotations) != size
        or len(buffers.proxy_bind_rotations) != size
    ):
        raise ValueError("Adapter requires parallel global proxy arrays")
    sign = _single(team.negative_scale_sign)
    direction = _float3(team.negative_scale_direction)
    position_sum = up_sum = forward_sum = _ZERO
    slots = []
    for offset in range(count):
        local = _integer(buffers.fixed_point_data[start + offset], 65535)
        slot = _index(_integer(chunk + local, 2**31 - 1), size)
        slots.append(slot)
        position_sum = _add(_vector(buffers.proxy_positions[slot]), position_sum)
        point_rotation = _quaternion(buffers.proxy_rotations[slot])
        if sign < 0:
            up = rotate_single(point_rotation, _Y)  # 5a2bd98 first output.
            forward = rotate_single(point_rotation, _Z)  # Second output.
            neg_up = cast(Vector3, tuple(-value for value in up))
            neg_forward = cast(Vector3, tuple(-value for value in forward))
            # Native ABI forward/up is reversed from this adapter's up/forward API.
            point_rotation = rotation_from_normal_tangent(neg_up, neg_forward)
        combined = multiply_quaternions(
            point_rotation, buffers.proxy_bind_rotations[slot]
        )
        up_sum = _sum_single(up_sum, rotate_single(combined, _Y))  # 39d4430.
        forward_sum = _sum_single(forward_sum, rotate_single(combined, _Z))  # 39d4490.
    up_sign = -1.0 if direction[0] < 0 or direction[2] < 0 else 1.0
    forward_sign = -1.0 if direction[0] < 0 or direction[1] < 0 else 1.0
    up_sum = cast(Vector3, tuple(_single(up_sign * value) for value in up_sum))
    forward_sum = cast(
        Vector3, tuple(_single(forward_sign * value) for value in forward_sum)
    )
    position = _vector(
        cast(Vector3, tuple(value / float(count) for value in position_sum))
    )
    up = _normalize_single(up_sum)
    forward = _normalize_single(forward_sum)
    rotation = rotation_from_normal_tangent(up, forward)  # Adapt native ABI, not axes.
    return FrameTargetResult(position, rotation, scale, tuple(slots))


def resolve_frame_target(
    step_state: CenterStepState, target: FrameTargetResult
) -> CenterStepState:
    """Pass local target to later reference fragments, without resetting history.

    Value adapter only: native local CenterData writes occur at5a36214..5a36250.
    This is NOT actual NativeArray publication or the complete surrounding lifecycle.
    """
    return replace(
        step_state,
        frame_world_position=target.position,
        frame_world_rotation=target.rotation,
        frame_world_scale=target.scale,
    )
