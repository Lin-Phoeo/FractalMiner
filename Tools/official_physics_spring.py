"""Finite, source-ordered fixed-particle Spring reference; not a Unity solver.

Static source: BeyondDynamicBone StartSimulationStepJobKernels.Spring,
managed370470/0x5a649e0, Burst body370475/0x5a644dc and the normalized-address
equivalent DirectCall fallback0x5a69c6c.  It consumes already resolved fixed
particle inputs only; it does not select particles, publish NativeArrays,
schedule jobs or mutate a Unity transform.  Python libm is a mathematical
reference for the original double trigonometry, not a Burst/CRT bit oracle.
"""

import math
from dataclasses import dataclass
from enum import IntEnum
from typing import cast

from official_physics_angles import Quaternion, rotate_double
from official_physics_constraints import (
    Vector3,
    _add,
    _finite,
    _length,
    _scale,
    _single,
    _sub,
    _vector,
)


class ClothNormalAxis(IntEnum):
    """Verified ClothNormalAxis ordinal order used by Spring's six-way switch."""

    Right = 0
    Up = 1
    Forward = 2
    InverseRight = 3
    InverseUp = 4
    InverseForward = 5


@dataclass(frozen=True)
class SpringConstraintSettings:
    """Unboxed SpringConstraintParams: offsets 0, 4, 8 and 12 respectively."""

    spring_power: float
    limit_distance: float
    normal_limit_ratio: float
    spring_noise: float


_AXES: tuple[Vector3, ...] = (
    (1.0, 0.0, 0.0),
    (0.0, 1.0, 0.0),
    (0.0, 0.0, 1.0),
    (-1.0, 0.0, 0.0),
    (0.0, -1.0, 0.0),
    (0.0, 0.0, -1.0),
)


def _double_dot(left: Vector3, right: Vector3) -> float:
    """Recovered helper0x59d7a44 lane order: y+x, then z."""
    return _finite((left[1] * right[1] + left[0] * right[0]) + left[2] * right[2])


def _require_axis(value: ClothNormalAxis) -> ClothNormalAxis:
    if type(value) is not ClothNormalAxis:
        raise ValueError("Adapter requires a ClothNormalAxis member")
    return value


def _settings(value: SpringConstraintSettings) -> tuple[float, float, float, float]:
    if not isinstance(value, SpringConstraintSettings):
        raise TypeError("Adapter requires SpringConstraintSettings")
    return (
        _single(value.spring_power),
        _single(value.limit_distance),
        _single(value.normal_limit_ratio),
        _single(value.spring_noise),
    )


def apply_spring(
    *,
    spring_params: SpringConstraintSettings,
    normal_axis: ClothNormalAxis,
    next_position: Vector3,
    base_position: Vector3,
    base_rotation: Quaternion,
    noise_time: float,
    scale_ratio: float,
) -> Vector3:
    """Apply Spring to one resolved fixed-particle next position.

    The source first bounds `next-base` to a sphere, then (only when ratio<1)
    bounds its normal component to the corresponding elliptical cross-section.
    It finally performs `base + (delta - delta * effective_power)` in the
    observed order, rather than simplifying the two vector operations.
    A non-positive scaled limit selects the native zero-vector path, so the
    return is base rather than an unconstrained position.
    """
    power, limit_distance, normal_ratio, noise = _settings(spring_params)
    axis = _require_axis(normal_axis)
    next_position, base_position = _vector(next_position), _vector(base_position)
    if len(base_rotation) != 4:
        raise ValueError("Adapter requires four base rotation components")
    rotation = cast(
        Quaternion,
        tuple(_single(_finite(component)) for component in base_rotation),
    )
    noise_time, scale_ratio = _finite(noise_time), _finite(scale_ratio)

    # helper0x59d77a4 receives base then next and returns next-base.
    delta = _sub(next_position, base_position)
    normal = rotate_double(rotation, _AXES[int(axis)])
    limit = _finite(limit_distance * scale_ratio)
    if limit <= 0:
        # 0x5a646a5 selects the registered float3 zero constant and jumps past
        # both length and normal-limit work.
        delta = (0.0, 0.0, 0.0)
    else:
        length = _length(delta)
        if length > limit:
            delta = _scale(delta, limit / length)
        if normal_ratio < 1:
            normal_component = _double_dot(normal, delta)
            tangent = _sub(delta, _scale(normal, normal_component))
            tangent_length = _length(tangent)
            # The call target 0x1b39a0 enters the asin path whose exact-bounded
            # implementation is recorded at 0x1b39c0; 0x1b4380 is cos.
            normal_limit = math.cos(math.asin(tangent_length / limit))
            normal_limit *= normal_ratio * limit
            if abs(normal_component) > normal_limit:
                sign = (
                    0.0
                    if normal_component == 0
                    else (1.0 if normal_component > 0 else -1.0)
                )
                correction = _scale(normal, abs(normal_component) - normal_limit)
                delta = _sub(delta, _scale(correction, sign))

    if noise > 0:
        amplitude = _single(noise * _single(0.6))
        power = _finite(((math.sin(noise_time) * amplitude) * power) + power)
        power = power if power > 0 else 0.0
    delta = _sub(delta, _scale(delta, power))
    return _add(base_position, delta)
