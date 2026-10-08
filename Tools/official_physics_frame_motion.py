"""Bounded frame-motion reduction from the frame Team kernel.

Static source: the restricted region 0x5a36ab1..0x5a36bd4 inside
CalcCenterAndInertiaAndWindKernel$BurstManaged, method369644/0x5a34900.
The caller supplies the already resolved upstream Double displacement.  This
module only converts that value to float3 and writes the numerical equivalents
of CenterData.frameMovingSpeed/frameMovingDirection.  It does not resolve the
anchor, component/frame transforms, frameComponentShiftVector, teleport/reset,
wind-zone membership, NativeArrays, scheduling or Unity transforms.

Single narrowing and operation order are explicit.  Python sqrt is a finite
mathematical reference, not a bit oracle for the game's CRT/Burst dispatch.
Finite-input rejection is adapter policy, not a recovered native exception.
"""

import math
from dataclasses import dataclass
from typing import cast

from official_physics_angles import _float3
from official_physics_constraints import Vector3, _single, _vector
from official_physics_particle_step import _single_dot

_ZERO: Vector3 = (0.0, 0.0, 0.0)
_EPSILON = _single(1e-6)


@dataclass(frozen=True)
class FrameMotionResult:
    """Finite values produced by the recovered reduction, not array writes."""

    speed: float
    direction: Vector3
    delta_single: Vector3


def reduce_frame_motion(
    upstream_delta: Vector3,
    *,
    frame_delta_time: float,
    now_time_scale: float,
) -> FrameMotionResult:
    """Reduce an upstream Double displacement to frame speed and direction.

    `upstream_delta` deliberately has no stronger semantic name: the preceding
    transform producer is not yet fully decoded, so it must not be substituted
    with frameComponentShiftVector or a scene-root delta by assumption.
    """
    delta = _float3(_vector(upstream_delta))
    delta_time = _single(frame_delta_time)
    time_scale = _single(now_time_scale)

    length = _single(math.sqrt(_single_dot(delta, delta)))
    rate = _single(length / delta_time) if delta_time > 0 else 0.0
    inverse_time_scale = _single(1.0 / time_scale) if time_scale > _EPSILON else 0.0
    speed = _single(inverse_time_scale * rate)
    direction = (
        cast(Vector3, tuple(_single(lane / length) for lane in delta))
        if length > _EPSILON
        else _ZERO
    )
    return FrameMotionResult(speed, direction, delta)
