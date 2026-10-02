"""Offline references for recovered curve/mass/distance arithmetic, not a solver.

Source trace: docs/implementation/official-physics-constraints-20261002.
Single intermediates are rounded explicitly; positions remain Double. No Job
dispatch, vertex eligibility/Team flags, neighbor ordering, in-place scheduling,
Burst equivalence, cloth rotation, collision or Unity bone writes are claimed.
Finite/positive input rejection is adapter policy, NOT native error behavior.
The distance function receives an immutable eligible particle's neighbor snapshot.
"""

import math
import struct
from collections.abc import Sequence
from dataclasses import dataclass

Vector3 = tuple[float, float, float]


def _finite(value: float) -> float:
    if type(value) not in (int, float):
        raise ValueError("Adapter requires finite numeric input, not bool/string")
    try:
        number = float(value)
    except OverflowError as exc:
        raise ValueError("Adapter requires finite representable numeric input") from exc
    if not math.isfinite(number):
        raise ValueError("Adapter requires finite numeric input")
    return number


def _single(value: float) -> float:
    value = _finite(value)
    if abs(value) > 3.4028234663852886e38:
        raise ValueError("Adapter requires representable finite Single")
    return struct.unpack("<f", struct.pack("<f", value))[0]


def _positive(value: float) -> float:
    value = _single(value)
    if value <= 0:
        raise ValueError("Adapter requires positive Single mass/denominator")
    return value


def _vector(value: Vector3) -> Vector3:
    if len(value) != 3:
        raise ValueError("Expected three Double position components")
    return (_finite(value[0]), _finite(value[1]), _finite(value[2]))


def _add(a: Vector3, b: Vector3) -> Vector3:
    return _vector((a[0] + b[0], a[1] + b[1], a[2] + b[2]))


def _sub(a: Vector3, b: Vector3) -> Vector3:
    return _vector((a[0] - b[0], a[1] - b[1], a[2] - b[2]))


def _scale(a: Vector3, factor: float) -> Vector3:
    return _vector((a[0] * factor, a[1] * factor, a[2] * factor))


def _length(a: Vector3) -> float:
    # Native dot's addition order: (y*y + x*x) + z*z; no hypot rescaling/FMA.
    return math.sqrt(_finite((a[1] * a[1] + a[0] * a[0]) + a[2] * a[2]))


def inverse_mass(
    friction: float, depth: float, *, fixed: bool = False, fixed_mass: float = 50
) -> float:
    """CalcInverseMass method371225; actual first argument friction, second depth."""
    friction, depth = _single(friction), _single(depth)
    if type(fixed) is not bool:
        raise ValueError("Adapter fixed policy must be bool")
    fixed_mass = _positive(fixed_mass)
    if fixed:
        return _single(1 / fixed_mass)
    depth_gap = _single(1 - depth)
    depth_term = _single(_single(depth_gap * depth_gap) * 5)
    friction_term = _single(_single(friction * 3) + 1)
    return _single(1 / _positive(_single(depth_term + friction_term)))


def evaluate_curve(samples: Sequence[float], time: float) -> float:
    """EvaluateCurve method370882: flat float4x4, 15 intervals, original-t fraction.

    Only the index uses clamp01(time). Negative t therefore extrapolates sample
    0->1; replacing this with a clamped lerp changes the recovered method.
    """
    if len(samples) != 16:
        raise ValueError("Expected sixteen float4x4 samples in memory order")
    values = tuple(_single(value) for value in samples)
    time = _single(time)
    index = math.trunc(_single(min(1, max(0, time)) * 15))
    interval = _single(1 / 15)
    fraction = _single(_single(time - _single(index * interval)) / interval)
    i0, i1 = min(15, max(0, index)), min(15, max(0, index + 1))
    delta = _single(values[i1] - values[i0])
    return _single(values[i0] + _single(delta * fraction))


@dataclass(frozen=True)
class DistanceNeighbor:
    next_position: Vector3
    base_position: Vector3
    signed_rest_length: float
    inverse_mass: float


@dataclass(frozen=True)
class DistanceResult:
    next_position: Vector3
    velocity_position: Vector3
    correction: Vector3
    contributing_neighbors: int


def distance_particle(
    next_position: Vector3,
    base_position: Vector3,
    velocity_position: Vector3,
    neighbors: Sequence[DistanceNeighbor],
    *,
    center_inverse_mass: float,
    stiffness_curve: Sequence[float],
    depth: float,
    simulation_power_y: float,
    rest_scale: float,
    animation_pose_ratio: float,
    velocity_attenuation: float,
) -> DistanceResult:
    """Managed distance kernel arithmetic after eligibility/adjacency resolution.

    rest_scale is the caller's Single(initScale.x * scaleRatio). This function
    does not decide fixed flags/masses, unpack buffers or write shared arrays.
    Eligible zero-length edges do not enter the contribution count; valid
    zero-stiffness edges DO. Preserve input neighbor order.
    """
    position, base, velocity = (
        _vector(next_position),
        _vector(base_position),
        _vector(velocity_position),
    )
    mass = _positive(center_inverse_mass)
    scale, pose_ratio, attenuation, power = (
        _single(rest_scale),
        _single(animation_pose_ratio),
        _single(velocity_attenuation),
        _single(simulation_power_y),
    )
    stiffness = _single(min(1, max(0, evaluate_curve(stiffness_curve, depth))) * power)
    total: Vector3 = (0.0, 0.0, 0.0)
    count = 0
    for neighbor in neighbors:
        other, other_base = (
            _vector(neighbor.next_position),
            _vector(neighbor.base_position),
        )
        other_mass = _positive(neighbor.inverse_mass)
        rest = _single(neighbor.signed_rest_length)
        edge_stiffness = _single(stiffness * 0.5) if rest < 0 else stiffness
        rest_length = _single(abs(rest) * scale)
        delta = _sub(other, position)
        length = _length(delta)
        if length < 9.99999993922529e-9:  # converted 1e-8f, actual Double constant
            continue
        direction = _scale(delta, 1 / length)
        correction = _scale(direction, min(1, max(0, edge_stiffness)))
        target = (
            rest_length + (_length(_sub(other_base, base)) - rest_length) * pose_ratio
        )
        correction = _scale(correction, length - target)
        denominator = _positive(_single(mass + other_mass))
        # Native divides each Double component first, then multiplies center mass.
        correction = _vector(
            (
                correction[0] / denominator * mass,
                correction[1] / denominator * mass,
                correction[2] / denominator * mass,
            )
        )
        total = _add(total, correction)
        count += 1
    average = (
        _vector((total[0] / count, total[1] / count, total[2] / count))
        if count
        else total
    )
    return DistanceResult(
        _add(position, average),
        _add(velocity, _scale(average, attenuation)),
        average,
        count,
    )
