"""Finite offline reference for the managed Point collider-consumer kernel.

Source: method368740/RVA0x59f47cc, actual Sphere/Capsule/Plane callees
0x59f5774/0x59f4494/0x59f5670. Explicit, already-produced WorkData is required.
This does NOT produce ColliderManager buffers, dispatch Jobs/Burst, allocate
native arrays, resolve original component identities, or write Unity bones.
The observed managed AABB helper's asymmetric z lane is preserved deliberately;
it is NOT a claim that a separately dispatched Burst implementation has it.
Single boundaries are explicit; Python sqrt is a mathematical CRT reference.
Invalid/unsupported/nonfinite input rejection is adapter policy, not game logic.
"""

import math
from collections.abc import Sequence
from dataclasses import dataclass, replace

from official_physics_angle_cache import rotate_single
from official_physics_angles import Quaternion, _dot, _float3, _normalized
from official_physics_constraints import (
    Vector3,
    _add,
    _finite,
    _length,
    _scale,
    _single,
    _sub,
    _vector,
    evaluate_curve,
)

_ZERO: Vector3 = (0.0, 0.0, 0.0)
_RADIUS_FLOOR = _single(1e-4)
_NORMAL_EPSILON = _single(1e-8)
_NEAR_NORMAL_SQUARED_EPSILON = _single(1e-6)


@dataclass(frozen=True)
class ColliderWork:
    """Resolved flags plus the 184-byte WorkData's consumed typed fields.

    AABB@0, radii@48, oldPos@56, nextPos@104, inverseOldRot@152, rot@168.
    flag is the separate Byte flagArray value: valid0x10, enabled0x20,
    shape low nibble. Original Team chunk order must be preserved.
    """

    flag: int
    aabb_min: Vector3
    aabb_max: Vector3
    radii: tuple[float, float]
    old_points: tuple[Vector3, Vector3]
    next_points: tuple[Vector3, Vector3]
    inverse_old_rotation: Quaternion
    rotation: Quaternion


@dataclass(frozen=True)
class PointCollisionParameters:
    mode: int
    radius_curve: Sequence[float]
    limit_distance_curve: Sequence[float]


@dataclass(frozen=True)
class PointCollisionState:
    next_position: Vector3
    velocity_position: Vector3
    base_position: Vector3
    friction: float
    collision_normal: Vector3


@dataclass(frozen=True)
class PointCollisionTeam:
    flag: int
    scale_ratio: float
    collider_chunk_start: int
    collider_count: int


@dataclass(frozen=True)
class PointCollisionResult:
    state: PointCollisionState
    penetrating_contacts: int
    writes: tuple[str, ...]


def _integer(value: int, maximum: int = 0x7FFFFFFF) -> int:
    if type(value) is not int or not 0 <= value <= maximum:
        raise ValueError("Adapter requires an in-range unsigned integer")
    return value


def _single_add(a: Vector3, b: Vector3) -> Vector3:
    return (_single(a[0] + b[0]), _single(a[1] + b[1]), _single(a[2] + b[2]))


def _single_dot(a: Vector3, b: Vector3) -> float:
    return _single(
        _single(_single(a[1] * b[1]) + _single(a[0] * b[0])) + _single(a[2] * b[2])
    )


def _lerp(a: Vector3, b: Vector3, fraction: float) -> Vector3:
    # Native Double3 lerp helper: a + (b-a)*t, not weighted a/b terms.
    return _add(a, _scale(_sub(b, a), fraction))


def _overlap(min_a: Vector3, max_a: Vector3, work: ColliderWork) -> bool:
    min_b, max_b = _vector(work.aabb_min), _vector(work.aabb_max)
    # Actual helpers0x59ea6b4/0x59ea630: first z condition is maxB.z>=maxB.z.
    # The complete finite result therefore lacks minA.z<=maxB.z. Do not fix it.
    return (
        max_b[0] >= min_a[0]
        and max_b[1] >= min_a[1]
        and max_a[0] >= min_b[0]
        and max_a[1] >= min_b[1]
        and max_a[2] >= min_b[2]
    )


def _plane_distance(
    position: Vector3, surface: Vector3, normal: Vector3
) -> tuple[float, Vector3]:
    delta = _sub(position, surface)
    signed_dot = _dot(delta, normal)
    projected = _scale(normal, signed_dot)  # No division by squared normal.
    distance = _length(projected)
    if signed_dot >= 0:
        return distance, position
    return -distance, _sub(position, projected)


def _contact(
    position: Vector3,
    base: Vector3,
    radius: float,
    limit: float,
    work: ColliderWork,
    shape: int,
    aabb_min: Vector3,
    aabb_max: Vector3,
) -> tuple[float, Vector3, Vector3]:
    if shape == 8:
        # OldPos.c0 stores a normal here; its c1, rotations and AABB are unread.
        normal = _vector(work.old_points[0])
        surface = _add(_vector(work.next_points[0]), _scale(normal, radius))
        published_normal = _float3(normal)
        distance, corrected = _plane_distance(position, surface, published_normal)
        return distance, corrected, published_normal
    if not _overlap(aabb_min, aabb_max, work):
        # Actual helper sentinels differ: Sphere Double.Max; Capsule Single.Max.
        maximum = 1.7976931348623157e308 if shape == 1 else 3.4028234663852886e38
        return maximum, position, _ZERO
    old_a, next_a = _vector(work.old_points[0]), _vector(work.next_points[0])
    radius_a = _single(work.radii[0])
    if shape == 1:
        normal = _normalized(_sub(position, old_a))
        surface = _add(next_a, _scale(normal, _single(radius + radius_a)))
    else:
        old_b, next_b = _vector(work.old_points[1]), _vector(work.next_points[1])
        axis = _sub(old_b, old_a)
        squared = _dot(axis, axis)
        fraction = (
            _single(min(1.0, max(0.0, _dot(_sub(position, old_a), axis) / squared)))
            if squared != 0
            else 0.0
        )
        radial = _float3(_sub(position, _lerp(old_a, old_b, fraction)))
        local = rotate_single(work.inverse_old_rotation, radial)
        normal = _normalized(rotate_single(work.rotation, local))
        radius_b = _single(work.radii[1])
        interpolated = _single(
            _single(_single(radius_b - radius_a) * fraction) + radius_a
        )
        combined = _single(interpolated + radius)
        surface = _add(_lerp(next_a, next_b, fraction), _scale(normal, combined))
    # Surface uses normalized Double normal. All actual shape helpers then
    # narrow it to their float3 output and widen that output for projection.
    published_normal = _float3(normal)
    distance, corrected = _plane_distance(position, surface, published_normal)
    if shape == 1 and limit > 0:
        # Sphere-only spring clamp and return lerp; Capsule has neither operation.
        offset = _sub(corrected, base)
        length = _length(offset)
        if length > limit:
            corrected = _lerp(base, corrected, limit / length)
        if radius <= 0:
            raise ValueError("Adapter requires positive sphere spring radius")
        motion = _length(_sub(base, corrected))
        fraction = min(1.0, max(0.0, motion / radius)) * _single(0.85)
        corrected = _lerp(corrected, position, fraction)
        distance = _finite(distance * 3.0)
    return distance, corrected, published_normal


def point_collision_particle(
    state: PointCollisionState,
    team: PointCollisionTeam,
    parameters: PointCollisionParameters,
    *,
    attribute: int,
    depth: float,
    colliders: Sequence[ColliderWork],
) -> PointCollisionResult:
    """One already-selected global particle with resolved Team/vertex/depth.

    The caller resolves stepParticleIndexArray, signed teamId, and proxy-vertex
    offset. There is no IsProcess gate inside this kernel. Mode1, shapes1/2..7/8
    only are supported. Do not manufacture WorkData from guessed prefab fields.
    All helpers read ORIGINAL next_position, then their corrections are averaged.
    Dynamic/static friction coefficients are consumed elsewhere, not here.
    Unwritten buffers (including their original numeric representation) survive.
    """
    count = _integer(team.collider_count)
    if count == 0:
        return PointCollisionResult(state, 0, ())
    if _integer(parameters.mode) != 1:
        raise ValueError("Adapter supports only Point collision mode 1")
    position = _vector(state.next_position)
    attr = _integer(attribute, 0xFF)
    spring = bool(_integer(team.flag, 0xFFFFFFFFFFFFFFFF) & 0x2000)
    if attr & 3 == 0 or attr & 0x10 or not (attr & 2 or spring):
        return PointCollisionResult(state, 0, ())
    start = _integer(team.collider_chunk_start)
    if start + count > len(colliders):
        raise ValueError("Adapter collider chunk exceeds explicit WorkData")
    scale = _single(team.scale_ratio)
    if scale < 0:
        raise ValueError("Adapter requires nonnegative Single scale ratio")
    radius = _single(
        scale * max(_RADIUS_FLOOR, evaluate_curve(parameters.radius_curve, depth))
    )
    base = _vector(state.base_position) if spring else _ZERO
    limit = (
        _single(
            scale
            * max(_RADIUS_FLOOR, evaluate_curve(parameters.limit_distance_curve, depth))
        )
        if spring
        else -1.0
    )
    extent: Vector3 = (radius, radius, radius)
    aabb_min = _sub(_sub(position, extent), extent)
    aabb_max = _add(_add(position, extent), extent)
    total = _ZERO
    hit_normal = near_normal = _ZERO
    hits = 0
    near = False
    minimum = 1.7976931348623157e308
    for work in colliders[start : start + count]:
        flag = _integer(work.flag, 0xFF)
        if not flag & 0x10 or not flag & 0x20:
            continue
        shape = flag & 0xF
        if shape not in range(1, 9):
            raise ValueError("Adapter does not support enabled collider shape")
        distance, corrected, normal = _contact(
            position, base, radius, limit, work, shape, aabb_min, aabb_max
        )
        if distance <= 0:
            total = _add(total, _sub(corrected, position))
            hit_normal = _single_add(hit_normal, normal)
            hits += 1
        if distance <= radius:
            near_normal = _single_add(near_normal, normal)
            near = True
            minimum = min(minimum, distance)
    correction = _ZERO
    final_position = position
    if hits:
        denominator = _single(hits)
        average_normal: Vector3 = (
            _single(hit_normal[0] / denominator),
            _single(hit_normal[1] / denominator),
            _single(hit_normal[2] / denominator),
        )
        normal_length = _single(math.sqrt(_single_dot(average_normal, average_normal)))
        if normal_length >= _NORMAL_EPSILON:
            averaged: Vector3 = (total[0] / hits, total[1] / hits, total[2] / hits)
            correction = _scale(averaged, min(1.0, normal_length))
            final_position = _add(position, correction)
    writes: tuple[str, ...] = ()
    friction = state.friction
    near_squared = _single_dot(near_normal, near_normal) if near and radius > 0 else 0.0
    if near_squared > _NEAR_NORMAL_SQUARED_EPSILON:
        friction = _single(
            max(_single(state.friction), 1.0 - min(1.0, max(0.0, minimum / radius)))
        )
        reciprocal = _single(1.0 / _single(math.sqrt(near_squared)))
        near_normal = _float3(_scale(near_normal, reciprocal))
        writes = ("friction",)
    writes += ("collision_normal", "next_position")
    velocity = state.velocity_position
    if spring and hits:
        velocity = _add(_vector(velocity), correction)
        writes += ("velocity_position",)
    return PointCollisionResult(
        replace(
            state,
            next_position=final_position,
            velocity_position=velocity,
            friction=friction,
            collision_normal=near_normal,
        ),
        hits,
        writes,
    )
