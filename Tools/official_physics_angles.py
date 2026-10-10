"""Offline angle arithmetic recovered from the managed fallback, not a solver.

Trace: docs/implementation/official-physics-angles-20261002 and angle-pass-20261010.
Default pair functions retain managed math; restoration_job_pair deliberately
uses the separately recovered ordinary Job float3 geometry seam. Positions are
Double; quaternion/curve boundaries round to Single. Python libm is a mathematical
reference, NOT bitwise equivalence to the game's CRT or dispatched Burst code.
Pair APIs require an already eligible movable child and resolved world vectors.
They do not initialize/update rotation caches, schedule baselines or write bones.
Finite/nonzero input rejection is adapter policy, not native exception behavior.
"""

import math
from collections.abc import Sequence
from dataclasses import dataclass

from official_physics_constraints import (
    Vector3,
    _add,
    _finite,
    _length,
    _positive,
    _scale,
    _single,
    _sub,
    _vector,
    evaluate_curve,
)

Quaternion = tuple[float, float, float, float]
_EPSILON = _single(1e-6)
_PI = _single(math.pi)


def _dot(a: Vector3, b: Vector3) -> float:
    return _finite((a[1] * b[1] + a[0] * b[0]) + a[2] * b[2])


def _cross(a: Vector3, b: Vector3) -> Vector3:
    return _vector(
        (
            a[1] * b[2] - a[2] * b[1],
            a[2] * b[0] - a[0] * b[2],
            a[0] * b[1] - a[1] * b[0],
        )
    )


def _normalized(value: Vector3) -> Vector3:
    value = _vector(value)
    length = _length(value)
    if length <= 0:
        raise ValueError("Finite adapter requires nonzero direction/rotation axis")
    # helper0x59d7a98: divsd(1,length), then helper0x59d7700 component mulsd.
    return _scale(value, 1 / length)


def _float3(value: Vector3) -> Vector3:
    value = _vector(value)
    return (_single(value[0]), _single(value[1]), _single(value[2]))


def _opposite_axis(direction: Vector3) -> Vector3:
    # Observed SIGNED comparison, not an absolute-component robust fallback.
    basis: Vector3 = (
        (0.0, 1.0, 0.0)
        if direction[0] > direction[1] and direction[0] > direction[2]
        else (1.0, 0.0, 0.0)
    )
    return _cross(direction, basis)


def _axis_angle(axis: Vector3, radians: float) -> Quaternion:
    axis = _float3(_normalized(axis))
    half = _single(_single(radians) * 0.5)
    sine, cosine = _single(math.sin(half)), _single(math.cos(half))
    return (
        _single(axis[0] * sine),
        _single(axis[1] * sine),
        _single(axis[2] * sine),
        cosine,
    )


def angle_between(a: Vector3, b: Vector3) -> float:
    """MathUtility.Angle, method371135: original Double radian angle."""
    a, b = _vector(a), _vector(b)
    denominator = _finite(_length(a) * _length(b))
    if denominator <= 0:
        raise ValueError("Finite adapter requires nonzero directions")
    return math.acos(min(1.0, max(-1.0, _dot(a, b) / denominator)))


def from_to_rotation(
    source: Vector3, target: Vector3, fraction: float = 1
) -> Quaternion:
    """Method371141; fraction is Double and deliberately NOT clamped."""
    source, target = _normalized(source), _normalized(target)
    fraction = _finite(fraction)
    dot = min(1.0, max(-1.0, _dot(source, target)))
    radians = math.acos(dot)
    axis = _cross(source, target)
    if abs(dot + 1) < _EPSILON:
        radians, axis = _PI, _opposite_axis(source)
    elif abs(1 - dot) < _EPSILON:
        return (0.0, 0.0, 0.0, 1.0)
    return _axis_angle(axis, _single(radians * fraction))


def rotate_double(quaternion: Quaternion, direction: Vector3) -> Vector3:
    """Recovered helper0x59d732c; no quaternion renormalization."""
    if len(quaternion) != 4:
        raise ValueError("Expected four Single quaternion components")
    x, y, z, w = (_single(value) for value in quaternion)
    direction = _vector(direction)
    xyz: Vector3 = (x, y, z)
    twice_cross = _scale(_cross(xyz, direction), 2)
    return _add(_add(direction, _scale(twice_cross, w)), _cross(xyz, twice_cross))


@dataclass(frozen=True)
class ClampResult:
    direction: Vector3
    changed: bool


def clamp_angle(
    direction: Vector3, basis: Vector3, maximum_radians: float
) -> ClampResult:
    """Method371140; rotate original magnitude with observed antiparallel rules."""
    direction = _vector(direction)
    source, target = _normalized(direction), _normalized(basis)
    maximum = _finite(maximum_radians)
    if maximum < 0:
        raise ValueError("Finite adapter requires nonnegative maximum angle")
    dot = min(1.0, max(-1.0, _dot(source, target)))
    radians = math.acos(dot)
    if maximum >= radians:
        return ClampResult(direction, False)
    fraction = (radians - maximum) / radians
    axis = _cross(source, target)
    if abs(dot + 1) < _EPSILON:
        radians, axis = _PI, _opposite_axis(source)
    elif abs(1 - dot) < _EPSILON:
        return ClampResult(direction, False)
    rotation = _axis_angle(axis, _single(fraction * radians))
    return ClampResult(rotate_double(rotation, direction), True)


def iteration_pivot(iteration: int) -> float:
    if type(iteration) is not int or iteration not in (0, 1, 2):
        raise ValueError("Angle kernel has exactly three iterations, indexed 0..2")
    return _single(_single(_single(iteration * 0.5) * _single(0.4)) + _single(0.1))


def friction_weight(friction: float) -> float:
    """Angle weight: independent 1/(1+3f), NOT distance's depth-dependent mass."""
    denominator = _positive(_single(_single(_single(friction) * 3) + 1))
    return _single(1 / denominator)


def restoration_strength(
    converted_curve: Sequence[float],
    depth: float,
    *,
    power_w: float,
    gravity_falloff: float,
    gravity_dot: float,
) -> float:
    """Curve is ALREADY converted (*0.2); preserve power.w and gravity order."""
    curve = min(1, max(0, evaluate_curve(converted_curve, depth)))
    strength = min(1, max(0, _single(curve * _single(power_w))))
    gap = _single(1 - _single(gravity_falloff))
    # Native computes 1-gap, not reuses falloff; cancellation matters in Single.
    gravity = _single(_single(_single(1 - gap) * _single(gravity_dot)) + gap)
    return _single(strength * gravity)  # no final clamp after gravity


@dataclass(frozen=True)
class PairResult:
    child_position: Vector3
    parent_position: Vector3
    child_velocity_position: Vector3
    parent_velocity_position: Vector3
    child_correction: Vector3
    parent_correction: Vector3


def _correct_pair(
    child: Vector3,
    parent: Vector3,
    child_velocity: Vector3,
    parent_velocity: Vector3,
    desired: Vector3,
    *,
    pivot: float,
    complement: float,
    child_friction: float,
    parent_friction: float,
    parent_movable: bool,
    attenuation: float,
    single_geometry: bool = False,
) -> PairResult:
    if type(parent_movable) is not bool:
        raise ValueError("Adapter parent_movable must be bool")
    child_weight, parent_weight = (
        friction_weight(child_friction),
        friction_weight(parent_friction),
    )
    attenuation = _single(attenuation)
    if single_geometry:
        # Job368722: float3 products round before widening and Double targets.
        delta = _float3(_sub(child, parent))
        middle = _add(parent, _float3(_scale(delta, pivot)))
        child_target = _add(middle, _float3(_scale(desired, complement)))
        parent_target = _sub(middle, _float3(_scale(desired, pivot)))
    else:
        middle = _add(parent, _scale(_sub(child, parent), pivot))
        child_target = _add(middle, _scale(desired, complement))
        parent_target = _sub(middle, _scale(desired, pivot))
    child_correction = _scale(_sub(child_target, child), child_weight)
    parent_correction: Vector3 = (
        _scale(_sub(parent_target, parent), parent_weight)
        if parent_movable
        else (0.0, 0.0, 0.0)
    )
    return PairResult(
        _add(child, child_correction),
        _add(parent, parent_correction),
        _add(child_velocity, _scale(child_correction, attenuation)),
        _add(parent_velocity, _scale(parent_correction, attenuation)),
        child_correction,
        parent_correction,
    )


def restoration_pair(
    child_position: Vector3,
    parent_position: Vector3,
    child_velocity: Vector3,
    parent_velocity: Vector3,
    restoration_world_vector: Vector3,
    *,
    converted_stiffness_curve: Sequence[float],
    depth: float,
    power_w: float,
    gravity_falloff: float,
    gravity_dot: float,
    iteration: int,
    child_friction: float,
    parent_friction: float,
    parent_movable: bool,
    velocity_attenuation: float,
) -> PairResult:
    """One eligible edge's restoration, AFTER limit if enabled; no cache writes."""
    child, parent, child_v, parent_v = map(
        _vector, (child_position, parent_position, child_velocity, parent_velocity)
    )
    delta = _sub(child, parent)
    fraction = restoration_strength(
        converted_stiffness_curve,
        depth,
        power_w=power_w,
        gravity_falloff=gravity_falloff,
        gravity_dot=gravity_dot,
    )
    rotation = from_to_rotation(delta, _float3(restoration_world_vector), fraction)
    pivot = iteration_pivot(iteration)
    return _correct_pair(
        child,
        parent,
        child_v,
        parent_v,
        rotate_double(rotation, delta),
        pivot=pivot,
        complement=_single(1 - pivot),
        child_friction=child_friction,
        parent_friction=parent_friction,
        parent_movable=parent_movable,
        attenuation=velocity_attenuation,
    )


def restoration_job_pair(
    child_position: Vector3,
    parent_position: Vector3,
    child_velocity: Vector3,
    parent_velocity: Vector3,
    restoration_world_vector: Vector3,
    *,
    converted_stiffness_curve: Sequence[float],
    depth: float,
    power_w: float,
    gravity_falloff: float,
    gravity_dot: float,
    iteration: int,
    child_friction: float,
    parent_friction: float,
    parent_movable: bool,
    velocity_attenuation: float,
) -> PairResult:
    """Ordinary Job368722: narrow delta, float3 rotate/products, Double writes.

    Not a replacement for managed restoration_pair. Even strength0 retains
    Single geometry operations; no early exit or guessed Double bridge.
    The local import avoids the cache/angles module dependency cycle.
    """
    from official_physics_angle_cache import rotate_single

    child, parent, child_v, parent_v = map(
        _vector, (child_position, parent_position, child_velocity, parent_velocity)
    )
    delta = _float3(_sub(child, parent))
    fraction = restoration_strength(
        converted_stiffness_curve,
        depth,
        power_w=power_w,
        gravity_falloff=gravity_falloff,
        gravity_dot=gravity_dot,
    )
    rotation = from_to_rotation(delta, _float3(restoration_world_vector), fraction)
    pivot = iteration_pivot(iteration)
    return _correct_pair(
        child,
        parent,
        child_v,
        parent_v,
        rotate_single(rotation, delta),
        pivot=pivot,
        complement=_single(1 - pivot),
        child_friction=child_friction,
        parent_friction=parent_friction,
        parent_movable=parent_movable,
        attenuation=velocity_attenuation,
        single_geometry=True,
    )


def limit_pair(
    child_position: Vector3,
    parent_position: Vector3,
    child_velocity: Vector3,
    parent_velocity: Vector3,
    limit_world_basis: Vector3,
    *,
    cached_length: float,
    limit_curve: Sequence[float],
    depth: float,
    limit_stiffness: float,
    child_friction: float,
    parent_friction: float,
    parent_movable: bool,
) -> PairResult:
    """Eligible edge limit arithmetic only; caller still OWNS rotation cache."""
    child, parent, child_v, parent_v = map(
        _vector, (child_position, parent_position, child_velocity, parent_velocity)
    )
    delta = _sub(child, parent)
    length, cached_length = _length(delta), _positive(cached_length)
    desired = _scale(_normalized(delta), length + (cached_length - length) * 0.5)
    basis = _float3(limit_world_basis)
    radians = angle_between(desired, basis)
    maximum = _single(evaluate_curve(limit_curve, depth) * _single(math.pi / 180))
    stiffness = _single(limit_stiffness)
    if radians > maximum:
        softened = radians + (maximum - radians) * stiffness
        desired = clamp_angle(desired, basis, softened).direction
    return _correct_pair(
        child,
        parent,
        child_v,
        parent_v,
        desired,
        pivot=_single(0.4),
        complement=_single(0.6),
        child_friction=child_friction,
        parent_friction=parent_friction,
        parent_movable=parent_movable,
        attenuation=_single(0.9),
    )
