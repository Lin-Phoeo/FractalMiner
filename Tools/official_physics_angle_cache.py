"""Offline non-root edge cache arithmetic; NOT a baseline/Job/Unity solver.

Recovered helper boundaries: docs/implementation/official-physics-angle-cache-20261002.
Single arithmetic grouping is explicit. Eligibility, root skipping, baseline
ordering, clock, collision and actual Burst dispatch remain caller/pending work.
Input rejection is adapter policy, not a claim about native NaN/error behavior.
"""

from collections.abc import Sequence
from dataclasses import dataclass

from official_physics_angles import (
    PairResult,
    Quaternion,
    _float3,
    _normalized,
    from_to_rotation,
    limit_pair,
    rotate_double,
)
from official_physics_constraints import (
    Vector3,
    _length,
    _positive,
    _single,
    _sub,
)


def _quaternion(value: Quaternion) -> Quaternion:
    if len(value) != 4:
        raise ValueError("Expected four Single quaternion components")
    return (_single(value[0]), _single(value[1]), _single(value[2]), _single(value[3]))


def quaternion_inverse(value: Quaternion) -> Quaternion:
    """helper0x39d3e70; Single reciprocal dot * q * (-1,-1,-1,+1)."""
    x, y, z, w = _quaternion(value)
    norm = _single(
        _single(_single(_single(y * y) + _single(x * x)) + _single(z * z))
        + _single(w * w)
    )
    reciprocal = _single(1 / _positive(norm))
    return (
        _single(_single(reciprocal * x) * -1),
        _single(_single(reciprocal * y) * -1),
        _single(_single(reciprocal * z) * -1),
        _single(reciprocal * w),
    )


def multiply_quaternions(a: Quaternion, b: Quaternion) -> Quaternion:
    """helper0x305d080, observed swizzle grouping; NOT reassociated Hamilton form."""
    ax, ay, az, aw = _quaternion(a)
    bx, by, bz, bw = _quaternion(b)

    def lane(wb: float, xw: float, yz: float, zx: float, sign: float) -> float:
        middle = _single(_single(xw) + _single(yz))
        return _single(_single(_single(wb) + _single(middle * sign)) - _single(zx))

    return (
        lane(aw * bx, ax * bw, ay * bz, az * by, 1),
        lane(aw * by, ay * bw, az * bx, ax * bz, 1),
        lane(aw * bz, az * bw, ax * by, ay * bx, 1),
        lane(aw * bw, ax * bx, ay * by, az * bz, -1),
    )


def rotate_single(value: Quaternion, direction: Vector3) -> Vector3:
    """helper0x2cd4520: v + w*(2*cross(xyz,v)) + cross(xyz,2*cross(xyz,v))."""
    x, y, z, w = _quaternion(value)
    direction = _float3(direction)
    xyz: Vector3 = (x, y, z)

    def cross(a: Vector3, b: Vector3) -> Vector3:
        return (
            _single(_single(a[1] * b[2]) - _single(a[2] * b[1])),
            _single(_single(a[2] * b[0]) - _single(a[0] * b[2])),
            _single(_single(a[0] * b[1]) - _single(a[1] * b[0])),
        )

    c = cross(xyz, direction)
    twice: Vector3 = (_single(2 * c[0]), _single(2 * c[1]), _single(2 * c[2]))
    final = cross(xyz, twice)
    return (
        _single(_single(direction[0] + _single(w * twice[0])) + final[0]),
        _single(_single(direction[1] + _single(w * twice[1])) + final[1]),
        _single(_single(direction[2] + _single(w * twice[2])) + final[2]),
    )


@dataclass(frozen=True)
class EdgeCache:
    local_direction: Vector3 | None
    local_rotation: Quaternion | None
    cached_length: float | None
    restoration_world_vector: Vector3 | None


def initialize_edge_cache(
    child_basic_position: Vector3,
    parent_basic_position: Vector3,
    child_next_position: Vector3,
    parent_next_position: Vector3,
    parent_basic_rotation: Quaternion,
    child_basic_rotation: Quaternion,
    *,
    use_limit: bool,
    use_restoration: bool,
) -> EdgeCache:
    """One resolved NON-ROOT edge; root/all-node rotation copies belong to caller.

    Optional None means that cache isn't initialized/read in this selected path,
    not a claim the native buffer is cleared. Disabled paths need no input math.
    """
    if type(use_limit) is not bool or type(use_restoration) is not bool:
        raise ValueError("Adapter angle enable flags must be bool")
    local_direction = local_rotation = length = world = None
    if use_limit or use_restoration:
        delta = _sub(child_basic_position, parent_basic_position)
        if use_limit:
            inverse = quaternion_inverse(parent_basic_rotation)
            local_direction = _float3(rotate_double(inverse, _normalized(delta)))
            local_rotation = multiply_quaternions(inverse, child_basic_rotation)
            length = _positive(_length(_sub(child_next_position, parent_next_position)))
        if use_restoration:
            world = _float3(delta)
    return EdgeCache(local_direction, local_rotation, length, world)


@dataclass(frozen=True)
class CachedLimitResult:
    pair: PairResult
    child_rotation: Quaternion
    used_world_basis: Vector3


def limit_cached_edge(
    child_position: Vector3,
    parent_position: Vector3,
    child_velocity: Vector3,
    parent_velocity: Vector3,
    parent_rotation_cache: Quaternion,
    cache: EdgeCache,
    *,
    limit_curve: Sequence[float],
    depth: float,
    limit_stiffness: float,
    child_friction: float,
    parent_friction: float,
    parent_movable: bool,
    ordinary_job: bool = False,
) -> CachedLimitResult:
    """Eligible child limit -> updated position difference -> child rotation.

    Default is managed math. ordinary_job is an adapter numeric route selector,
    not an official flag: Job368722 narrows the post-limit alignment target.
    Does NOT write shared arrays, initialize all-node rotation caches, perform
    restoration, or recursively update ancestors. Caller passes CURRENT parent
    rotation, not the original basic rotation. No quaternion renormalization.
    """
    if type(ordinary_job) is not bool:
        raise ValueError("Adapter ordinary_job selector must be bool")
    if (
        cache.local_direction is None
        or cache.local_rotation is None
        or cache.cached_length is None
    ):
        raise ValueError("Limit requires initialized local direction/rotation/length")
    basis = rotate_single(parent_rotation_cache, cache.local_direction)
    pair = limit_pair(
        child_position,
        parent_position,
        child_velocity,
        parent_velocity,
        basis,
        cached_length=cache.cached_length,
        limit_curve=limit_curve,
        depth=depth,
        limit_stiffness=limit_stiffness,
        child_friction=child_friction,
        parent_friction=parent_friction,
        parent_movable=parent_movable,
    )
    basic_product = multiply_quaternions(parent_rotation_cache, cache.local_rotation)
    target = _sub(pair.child_position, pair.parent_position)
    if ordinary_job:
        target = _float3(target)
    align = from_to_rotation(basis, target, 1)
    rotation = multiply_quaternions(align, basic_product)
    return CachedLimitResult(pair, rotation, basis)
