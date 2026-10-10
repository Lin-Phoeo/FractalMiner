"""Finite typed Pre/Post ColliderManager references from the managed kernels.

Pre370274/5a57f68 uses Double3 histories; Post370346/5a596a0 uses Single3.
These phases deliberately expose separate input types. UnsafeDo passes raw
Double-buffer pointers to Single kernels without numeric conversion; ordinary
Job Start/Post have separate Double bodies. This module deliberately does not
reinterpret that storage, silently convert histories, allocate native
arrays, dispatch Burst/Jobs, resolve component classes, or write Unity bones.
Input validation, bounded indices and degenerate-basis rejection are adapter
policy. Python arithmetic is not a native CRT/Burst bitwise oracle.
"""

from collections.abc import Mapping, Sequence
from dataclasses import dataclass, replace

from official_physics_angle_baseline import _integer
from official_physics_angle_cache import (
    _quaternion,
    multiply_quaternions,
    rotate_single,
)
from official_physics_angles import Quaternion, _float3
from official_physics_constraints import Vector3, _add, _scale, _single, _vector
from official_physics_frame_inertia import shift_world_position
from official_physics_matrix import Matrix4, transform_double_point
from official_physics_proxy_baseline import _int32, rotation_from_normal_tangent
from official_physics_scale_remap import transform_double_vector

_FRAME_WRITES = ("frame_position", "frame_rotation", "frame_scale")
_HISTORY_WRITES = (
    "old_frame_position",
    "old_frame_rotation",
    "now_position",
    "now_rotation",
    "old_position",
    "old_rotation",
)


@dataclass(frozen=True)
class ColliderFrameState:
    flag: int
    frame_position: Vector3  # Double3, Pre framePositions.
    frame_rotation: Quaternion
    frame_scale: Vector3  # Single3.
    old_frame_position: Vector3  # Double3.
    old_frame_rotation: Quaternion
    now_position: Vector3  # Double3.
    now_rotation: Quaternion
    old_position: Vector3  # Double3.
    old_rotation: Quaternion


@dataclass(frozen=True)
class ColliderFrameTeam:
    flag: int  # UInt64.
    collider_chunk_start: int  # Team @380.
    collider_transform_chunk_start: int  # @388; not proxyTransformChunk.
    negative_scale_change: Vector3  # @116, Single sign multiplier.


@dataclass(frozen=True)
class ColliderFrameCenter:
    old_component_world_position: Vector3  # @152, Double3 pivot.
    frame_component_shift_vector: Vector3  # @204, Single3.
    frame_component_shift_rotation: Quaternion  # @216.
    negative_scale_matrix: Matrix4  # @568, SAME resolved frame matrix.


@dataclass(frozen=True)
class ColliderFrameResult:
    state: ColliderFrameState
    writes: tuple[str, ...]
    transform_index: int | None
    reset_applied: bool


@dataclass(frozen=True)
class ColliderPostState:
    frame_position: Vector3  # Single3, explicit Post input; no Pre storage alias.
    frame_rotation: Quaternion
    old_frame_position: Vector3  # Single3.
    old_frame_rotation: Quaternion


@dataclass(frozen=True)
class ColliderPostResult:
    state: ColliderPostState
    writes: tuple[str, ...]


def _process(flag: int) -> bool:
    # TeamData.get_IsProcess5a3b644 → IsEnable343b650 and IsCulling5a3b5e8.
    return bool(flag & 2) and not bool(flag & ((1 << 61) | 0x10 | 0x800 | 0x80000))


def remap_collider_rotation(
    rotation: Quaternion, matrix: Matrix4, negative_scale_change: Vector3
) -> Quaternion:
    """5a593a8: rotated Y/Z → matrix*w0 → respective sign → Single → basis.

    The x sign is unread. Each sign multiplication is Double AFTER the matrix
    products and BEFORE narrowing. Native LookRotation forward/up arguments map
    to this project's normal/tangent API in reversed order.
    """
    if len(negative_scale_change) != 3:
        raise ValueError("Adapter requires three collider scale sign components")
    sign_y, sign_z = (
        _single(negative_scale_change[1]),
        _single(negative_scale_change[2]),
    )
    up = _float3(
        _scale(
            transform_double_vector(matrix, rotate_single(rotation, (0, 1, 0))),
            sign_y,
        )
    )
    forward = _float3(
        _scale(
            transform_double_vector(matrix, rotate_single(rotation, (0, 0, 1))),
            sign_z,
        )
    )
    return rotation_from_normal_tangent(up, forward)


def prepare_collider_frame(
    state: ColliderFrameState,
    team: ColliderFrameTeam,
    *,
    collider_index: int,
    centers: Sequence[Vector3],
    transform_positions: Sequence[Vector3],
    transform_rotations: Sequence[Quaternion],
    transform_scales: Sequence[Vector3],
    frame_center: ColliderFrameCenter | None = None,
) -> ColliderFrameResult:
    """Original global collider slot: flags → IsProcess → current → history.

    center is rotated THEN component-scaled in Single, widened, and added to
    Double transformPosition. Reset (Team4 or collider40) wins over history remap.
    Otherwise40000 remaps oldFrame/now/old histories, then400 shifts all three.
    Current frame values are always written before history processing.
    """
    flag = _integer(state.flag, 0xFF)
    if flag & 0x30 != 0x30:
        return ColliderFrameResult(state, (), None, False)
    team_flag = _integer(team.flag, 2**64 - 1)
    if not _process(team_flag):
        return ColliderFrameResult(state, (), None, False)
    index = _integer(collider_index, 2**31 - 1)
    start = _integer(team.collider_chunk_start, 2**31 - 1)
    transform_start = _integer(team.collider_transform_chunk_start, 2**31 - 1)
    transform_index = _integer(transform_start - start + index, 2**31 - 1)
    if index >= len(centers) or any(
        transform_index >= len(buffer)
        for buffer in (transform_positions, transform_rotations, transform_scales)
    ):
        raise ValueError(
            "Adapter collider transform/center index exceeds explicit buffers"
        )
    q = _quaternion(transform_rotations[transform_index])
    scale = _float3(transform_scales[transform_index])
    rotated = rotate_single(q, centers[index])
    scaled: Vector3 = (
        _single(rotated[0] * scale[0]),
        _single(rotated[1] * scale[1]),
        _single(rotated[2] * scale[2]),
    )
    p = _add(_vector(transform_positions[transform_index]), scaled)
    current = replace(state, frame_position=p, frame_rotation=q, frame_scale=scale)
    if team_flag & 4 or flag & 0x40:
        return ColliderFrameResult(
            replace(
                current,
                flag=flag & ~0x40,
                old_frame_position=p,
                old_frame_rotation=q,
                now_position=p,
                now_rotation=q,
                old_position=p,
                old_rotation=q,
            ),
            _FRAME_WRITES + _HISTORY_WRITES + ("flag",),
            transform_index,
            True,
        )
    if not team_flag & 0x40400:
        return ColliderFrameResult(current, _FRAME_WRITES, transform_index, False)
    if frame_center is None:
        raise ValueError("Adapter requires resolved collider history center")
    positions = [
        _vector(state.old_frame_position),
        _vector(state.now_position),
        _vector(state.old_position),
    ]
    rotations = [
        _quaternion(state.old_frame_rotation),
        _quaternion(state.now_rotation),
        _quaternion(state.old_rotation),
    ]
    if team_flag & 0x40000:
        positions = [
            transform_double_point(frame_center.negative_scale_matrix, value)
            for value in positions
        ]
        rotations = [
            remap_collider_rotation(
                value, frame_center.negative_scale_matrix, team.negative_scale_change
            )
            for value in rotations
        ]
    if team_flag & 0x400:
        pivot = _vector(frame_center.old_component_world_position)
        shift = _float3(frame_center.frame_component_shift_vector)
        shift_q = _quaternion(frame_center.frame_component_shift_rotation)
        positions = [
            shift_world_position(value, pivot, shift, shift_q) for value in positions
        ]
        rotations = [multiply_quaternions(shift_q, value) for value in rotations]
    return ColliderFrameResult(
        replace(
            current,
            old_frame_position=positions[0],
            old_frame_rotation=rotations[0],
            now_position=positions[1],
            now_rotation=rotations[1],
            old_position=positions[2],
            old_rotation=rotations[2],
        ),
        _FRAME_WRITES + _HISTORY_WRITES,
        transform_index,
        False,
    )


def prepare_collider_frames(
    states: Sequence[ColliderFrameState],
    team_ids: Sequence[int],
    teams: Mapping[int, ColliderFrameTeam],
    *,
    centers: Sequence[Vector3],
    transform_positions: Sequence[Vector3],
    transform_rotations: Sequence[Quaternion],
    transform_scales: Sequence[Vector3],
    index_count: int,
    frame_centers: Mapping[int, ColliderFrameCenter] | None = None,
) -> tuple[ColliderFrameResult, ...]:
    """Pre range: ascending original global indices0..count-1; no compaction.

    Team0 is not specially skipped in this native phase. The explicit bounded
    adapter supports nonnegative signed-short IDs with supplied TeamData entries.
    Private returned values do not publish native buffers.
    """
    count = _int32(index_count)
    if count <= 0:
        return ()
    if count > len(states) or count > len(team_ids):
        raise ValueError("Adapter collider range exceeds explicit buffers")
    results = []
    for index in range(count):
        state = states[index]
        if _integer(state.flag, 0xFF) & 0x30 != 0x30:
            results.append(ColliderFrameResult(state, (), None, False))
            continue
        team_id = _integer(team_ids[index], 32767)
        if team_id not in teams:
            raise ValueError("Adapter collider slot has no corresponding TeamData")
        results.append(
            prepare_collider_frame(
                state,
                teams[team_id],
                collider_index=index,
                centers=centers,
                transform_positions=transform_positions,
                transform_rotations=transform_rotations,
                transform_scales=transform_scales,
                frame_center=None
                if frame_centers is None
                else frame_centers.get(team_id),
            )
        )
    return tuple(results)


def finish_collider_frame(
    state: ColliderPostState, *, team_flag: int
) -> ColliderPostResult:
    """Post Single fields: Team IsProcess AND20 → copy frame into oldFrame.

    This phase has no collider-flag gate or reset; it only advances frame history.
    A Pre Double state cannot be passed here. The separate Double Job Post value
    path is finish_collider_job_frame in official_physics_collider_job; this API
    does not reinterpret UnsafeDo's raw buffer pointers as numeric conversions.
    """
    if not isinstance(state, ColliderPostState):
        raise TypeError("Adapter requires explicit typed Single collider Post state")
    flag = _integer(team_flag, 2**64 - 1)
    if not _process(flag) or not flag & 0x20:
        return ColliderPostResult(state, ())
    return ColliderPostResult(
        replace(
            state,
            old_frame_position=_float3(state.frame_position),
            old_frame_rotation=_quaternion(state.frame_rotation),
        ),
        ("old_frame_position", "old_frame_rotation"),
    )
