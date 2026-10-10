"""Finite value references for the distinct managed Double collider Jobs.

Start.Execute(int)370378/5a66a3c, End.Execute(int)370382/4a474a0,
Post.Execute(int)370386/5a5faa0 use Double3 positions. Start's shape dimensions,
quaternions and rotated offsets remain Single; only offsets are widened before
Double world-position arithmetic. These are NOT the Single UnsafeDo kernels.
Explicit buffers/maps replace native storage. No native execution, scheduling,
Burst parity, allocation, external component identity or Unity output is claimed.
Finite/type/bounds checks are adapter policy, not original exception behavior.
"""

from collections.abc import Mapping, Sequence
from dataclasses import dataclass, replace

from official_physics_angle_cache import _quaternion, quaternion_inverse, rotate_single
from official_physics_angles import _float3
from official_physics_collider_frame import ColliderFrameState, _process
from official_physics_collider_step import (
    ColliderStepCenter,
    ColliderStepTeam,
    _bounds3,
    _dot3,
    _normalize4,
    _scale3,
    _slerp,
)
from official_physics_constraints import Vector3, _add, _scale, _single, _sub, _vector
from official_physics_point_collision import ColliderWork, _integer
from official_physics_proxy_baseline import _int32

_ZERO: Vector3 = (0.0, 0.0, 0.0)


@dataclass(frozen=True)
class ColliderJobState(ColliderFrameState):
    """Pre-compatible Double histories with explicit Single size and WorkData."""

    size: Vector3
    work: ColliderWork | None


@dataclass(frozen=True)
class ColliderJobResult:
    state: ColliderJobState
    writes: tuple[str, ...]


@dataclass(frozen=True)
class ColliderJobVisit:
    slot: int
    collider_index: int
    team_id: int | None
    result: ColliderJobResult


@dataclass(frozen=True)
class ColliderJobRangeResult:
    states: tuple[ColliderJobState, ...]
    visits: tuple[ColliderJobVisit, ...]


def _typed(state: ColliderJobState) -> None:
    if not isinstance(state, ColliderJobState):
        raise TypeError("Adapter requires explicit Double collider Job state")


def _lerp_double(a: Vector3, b: Vector3, fraction: float) -> Vector3:
    # 59eac0c: a + ((b-a) * widened Single fraction), no clamp or position cast.
    return _add(a, _scale(_sub(b, a), fraction))


def _expanded_bounds(a: Vector3, b: Vector3, radius: float) -> tuple[Vector3, Vector3]:
    low, high = _bounds3(a, b)
    expansion: Vector3 = (radius, radius, radius)
    return _sub(low, expansion), _add(high, expansion)


def start_collider_job(
    state: ColliderJobState, team: ColliderStepTeam, center: ColliderStepCenter
) -> ColliderJobResult:
    """Already-selected sparse Job collider; gate only its Byte bits10 and20.

    now quaternion is normalized Slerp. old quaternion's stored version is
    normalized, but geometry/inverse use the raw second Slerp result. All active
    shape nibbles overwrite WorkData; unsupported shapes retain zero geometry.
    """
    _typed(state)
    flag = _integer(state.flag, 0xFF)
    if flag & 0x30 != 0x30:
        return ColliderJobResult(state, ())
    fraction = _single(team.frame_interpolation)
    next_position = _lerp_double(
        _vector(state.old_frame_position), _vector(state.frame_position), fraction
    )
    next_rotation = _normalize4(
        _slerp(
            _quaternion(state.old_frame_rotation),
            _quaternion(state.frame_rotation),
            fraction,
        )
    )
    old_position = _lerp_double(
        _vector(state.old_position),
        next_position,
        _single(center.step_move_inertia_ratio),
    )
    raw_old_rotation = _slerp(
        _quaternion(state.old_rotation),
        next_rotation,
        _single(center.step_rotation_inertia_ratio),
    )
    stored_old_rotation = _normalize4(raw_old_rotation)
    inverse_old_rotation = quaternion_inverse(raw_old_rotation)
    size, scale = _float3(state.size), _float3(state.frame_scale)
    shape = flag & 0xF
    radii = (0.0, 0.0)
    old_points = next_points = (_ZERO, _ZERO)
    aabb_min = aabb_max = _ZERO
    if shape == 1:
        radius = _single(size[0] * abs(scale[0]))
        radii = (radius, radius)
        old_points, next_points = (old_position, _ZERO), (next_position, _ZERO)
        aabb_min, aabb_max = _expanded_bounds(old_position, next_position, radius)
    elif 2 <= shape <= 7:
        axis: Vector3 = (
            (1.0, 0.0, 0.0)
            if shape in (2, 5)
            else (0.0, 1.0, 0.0)
            if shape in (3, 6)
            else (0.0, 0.0, 1.0)
        )
        axial_scale = _dot3(scale, axis)
        sign = 1.0 if axial_scale > 0 else -1.0 if axial_scale < 0 else 0.0
        direction = _scale3(axis, sign)
        if flag & 0x80:
            direction = (-direction[0], -direction[1], -direction[2])
        radius0, radius1, height = _scale3(size, abs(axial_scale))
        if shape <= 4:
            height0 = _single(_single(height * 0.5) - radius0)
            height1 = _single(_single(height * 0.5) - radius1)
        else:
            height0 = _single(0 - radius0)
            height1 = _single(_single(height - radius0) - radius1)
        height0 = height0 if height0 > 0 else 0.0
        height1 = height1 if height1 > 0 else 0.0
        offset0, offset1 = _scale3(direction, height0), _scale3(direction, height1)
        # rotate_single's result is widened, NEVER the complete world endpoint.
        old0 = _add(old_position, rotate_single(raw_old_rotation, offset0))
        old1 = _sub(old_position, rotate_single(raw_old_rotation, offset1))
        next0 = _add(next_position, rotate_single(next_rotation, offset0))
        next1 = _sub(next_position, rotate_single(next_rotation, offset1))
        low0, high0 = _expanded_bounds(old0, next0, radius0)
        low1, high1 = _expanded_bounds(old1, next1, radius1)
        aabb_min = _bounds3(low0, low1)[0]
        aabb_max = _bounds3(high0, high1)[1]
        radii = (radius0, radius1)
        old_points, next_points = (old0, old1), (next0, next1)
    elif shape == 8:
        sign = 1.0 if scale[1] > 0 else -1.0 if scale[1] < 0 else 0.0
        normal = rotate_single(next_rotation, _scale3((0.0, 1.0, 0.0), sign))
        old_points, next_points = (normal, _ZERO), (next_position, _ZERO)
    work = ColliderWork(
        flag,
        aabb_min,
        aabb_max,
        radii,
        old_points,
        next_points,
        inverse_old_rotation,
        next_rotation,
    )
    return ColliderJobResult(
        replace(
            state,
            now_position=next_position,
            now_rotation=next_rotation,
            old_position=old_position,
            old_rotation=stored_old_rotation,
            work=work,
        ),
        ("now_position", "now_rotation", "old_position", "old_rotation", "work"),
    )


def start_collider_jobs(
    states: Sequence[ColliderJobState],
    teams: Mapping[int, ColliderStepTeam],
    centers: Mapping[int, ColliderStepCenter],
    *,
    step_collider_indices: Sequence[int],
    team_ids: Sequence[int],
    index_count: int,
) -> ColliderJobRangeResult:
    """Serial Execute() ordering: ordinal → sparse global collider → signed Team.

    Inactive collider flags return before Team lookup. No IsProcess/Team0 gate.
    Signed Int16 IDs retain sign in explicit maps; this does not establish safe
    negative native indexing. Duplicate entries consume earlier serial writes.
    Count is a signed snapshot independent of backing-list capacity. Returned
    private states do not publish arrays or represent scheduled JobHandle work.
    """
    count = _int32(index_count)
    if count <= 0:
        return ColliderJobRangeResult(tuple(states), ())
    if count > len(step_collider_indices):
        raise ValueError("Adapter collider list count exceeds explicit capacity")
    current = list(states)
    visits = []
    for slot in range(count):
        index = _integer(step_collider_indices[slot])
        if index >= len(current):
            raise ValueError("Adapter selected collider exceeds explicit states")
        value = current[index]
        _typed(value)
        if _integer(value.flag, 0xFF) & 0x30 != 0x30:
            visits.append(
                ColliderJobVisit(slot, index, None, ColliderJobResult(value, ()))
            )
            continue
        if index >= len(team_ids):
            raise ValueError("Adapter selected collider has no explicit Team ID")
        team_id = _int32(team_ids[index])
        if not -32768 <= team_id <= 32767:
            raise ValueError("Adapter collider Team ID must be signed Int16")
        if team_id not in teams or team_id not in centers:
            raise ValueError("Adapter requires selected collider Team/Center data")
        result = start_collider_job(value, teams[team_id], centers[team_id])
        current[index] = result.state
        visits.append(ColliderJobVisit(slot, index, team_id, result))
    return ColliderJobRangeResult(tuple(current), tuple(visits))


def end_collider_job(state: ColliderJobState) -> ColliderJobResult:
    """End.Execute selected entry: copy now→old without collider or Team gates."""
    _typed(state)
    return ColliderJobResult(
        replace(
            state,
            old_position=_vector(state.now_position),
            old_rotation=_quaternion(state.now_rotation),
        ),
        ("old_position", "old_rotation"),
    )


def end_collider_jobs(
    states: Sequence[ColliderJobState],
    *,
    step_collider_indices: Sequence[int],
    index_count: int,
) -> tuple[ColliderJobState, ...]:
    """Serial sparse End selection, not all colliders or native scheduling."""
    count = _int32(index_count)
    if count <= 0:
        return tuple(states)
    if count > len(step_collider_indices):
        raise ValueError("Adapter collider End count exceeds explicit list capacity")
    current = list(states)
    for slot in range(count):
        index = _integer(step_collider_indices[slot])
        if index >= len(current):
            raise ValueError("Adapter collider End index exceeds explicit states")
        current[index] = end_collider_job(current[index]).state
    return tuple(current)


def finish_collider_job_frame(
    state: ColliderJobState, *, team_flag: int
) -> ColliderJobResult:
    """Post.Execute direct global entry: IsProcess AND Team20, frame→oldFrame."""
    _typed(state)
    flag = _integer(team_flag, 2**64 - 1)
    if not _process(flag) or not flag & 0x20:
        return ColliderJobResult(state, ())
    return ColliderJobResult(
        replace(
            state,
            old_frame_position=_vector(state.frame_position),
            old_frame_rotation=_quaternion(state.frame_rotation),
        ),
        ("old_frame_position", "old_frame_rotation"),
    )
