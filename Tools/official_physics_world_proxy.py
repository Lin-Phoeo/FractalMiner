"""Finite supplied-input PreProxy world skinning, not live official physics.

Managed kernel369736/0x5a3fab0; list producer369695/0x5a3bec8. Keep raw
weight prefixes, separate bindpose/world applications and all homogeneous lanes.
Actual current float4x4 columns must be supplied, not reconstructed from TRS.
No native Team/allocator/TransformRead/Burst/scheduling or Unity writes occur.
Finite shapes, positive Int16 Teams, bounds and degenerate rejection are adapter
policy, not native guards. Caller previous slots and explicit block order are
preserved; returning immutable values does not establish a native publication.
"""

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import cast

from official_physics_angle_baseline import _index, _integer
from official_physics_angle_cache import _quaternion
from official_physics_angles import Quaternion, _float3
from official_physics_bindpose import ImportedBoneWeight
from official_physics_bone_import import Matrix4
from official_physics_constraints import Vector3, _single
from official_physics_proxy_baseline import (
    _normalization_scale,
    rotation_from_normal_tangent,
)
from official_physics_snapshot import multiply_matrices_single
from official_physics_work_lists import _chunk

FrameColumns = tuple[Quaternion, Quaternion, Quaternion]
_INT32_MAX = 2**31 - 1


def weight_prefix_count(weights: Sequence[float]) -> int:
    """get_Count371651: last strictly-positive Single lane + 1, not popcount."""
    values = _quaternion(cast(Quaternion, weights))
    for lane in range(3, -1, -1):
        if values[lane] > 0:
            return lane + 1
    return 0


def multiply_frame_columns_single(
    matrix: Sequence[Sequence[float]], columns: Sequence[Sequence[float]]
) -> FrameColumns:
    """helper0x5a44068: three float4 columns with left-associated Single sums.

    Reuse certified four-column multiply, with an unused finite zero column.
    Preserve all intermediate w values; no projective division or affine fixup.
    """
    if len(columns) != 3:
        raise ValueError("Adapter requires three float4 frame columns")
    validated = tuple(_quaternion(cast(Quaternion, c)) for c in columns)
    return cast(
        FrameColumns, multiply_matrices_single(matrix, validated + ((0, 0, 0, 0),))[:3]
    )


def _normalize(value: Vector3) -> Vector3:
    scale = _normalization_scale(value)
    return cast(Vector3, tuple(_single(lane * scale) for lane in value))


def skin_proxy_vertex(
    position: Vector3,
    normal: Vector3,
    tangent: Vector3,
    bone_weight: ImportedBoneWeight,
    bindposes: Sequence[Matrix4],
    skin_transform_indices: Sequence[int],
    transform_local_to_world: Sequence[Matrix4],
    *,
    skin_start: int = 0,
    transform_start: int = 0,
) -> tuple[Vector3, Quaternion]:
    """One finite selected mesh slot -> Double world point and Single frame.

    Weight zero/negative PREFIX slots still read their bindpose/current matrix.
    Unconsumed trailing indices are not inspected. Count0/degenerate/overflow
    refuse atomically instead of inventing previous/identity native fallbacks.
    Single accumulation ends before widening position to Python Double.
    """
    skin_start = _integer(skin_start, _INT32_MAX)
    transform_start = _integer(transform_start, _INT32_MAX)
    weights = _quaternion(bone_weight.weights)
    count = weight_prefix_count(weights)
    if len(bone_weight.bone_indices) != 4:
        raise ValueError("Adapter requires four bone indices")
    if not count:
        raise ValueError("Adapter refuses a degenerate zero-weight frame")
    source = (
        _float3(position) + (1.0,),
        _float3(normal) + (0.0,),
        _float3(tangent) + (0.0,),
    )
    accumulator = cast(FrameColumns, ((0, 0, 0, 0),) * 3)
    for lane in range(count):
        bone = _integer(bone_weight.bone_indices[lane], _INT32_MAX)
        slot = _integer(skin_start + bone, _INT32_MAX)
        _index(slot, len(bindposes))
        _index(slot, len(skin_transform_indices))
        mapped = _integer(skin_transform_indices[slot], _INT32_MAX)
        transform = _index(
            _integer(transform_start + mapped, _INT32_MAX),
            len(transform_local_to_world),
        )
        bound = multiply_frame_columns_single(bindposes[slot], source)
        world = multiply_frame_columns_single(
            transform_local_to_world[transform], bound
        )
        weighted = tuple(
            tuple(_single(v * weights[lane]) for v in column) for column in world
        )
        accumulator = cast(
            FrameColumns,
            tuple(
                tuple(_single(a + b) for a, b in zip(left, right, strict=True))
                for left, right in zip(accumulator, weighted, strict=True)
            ),
        )
    up = _normalize(cast(Vector3, accumulator[1][:3]))
    forward = _normalize(cast(Vector3, accumulator[2][:3]))
    rotation = rotation_from_normal_tangent(up, forward)
    return cast(Vector3, accumulator[0][:3]), rotation


@dataclass(frozen=True)
class ProxyUpdateTeam:
    flag: int
    proxy_transform_start: int  # TeamData @284.
    proxy_common_start: int  # @292.
    proxy_common_count: int  # @296.
    proxy_mesh_start: int  # @324.
    proxy_skin_bone_start: int  # @340.


@dataclass(frozen=True)
class WorldProxyBuffers:
    local_positions: Sequence[Vector3]
    local_normals: Sequence[Vector3]
    local_tangents: Sequence[Vector3]
    bone_weights: Sequence[ImportedBoneWeight]
    skin_bone_transform_indices: Sequence[int]
    skin_bone_bindposes: Sequence[Matrix4]
    transform_local_to_world: Sequence[Matrix4]


@dataclass(frozen=True)
class WorldProxyUpdate:
    positions: tuple[Vector3, ...]
    rotations: tuple[Quaternion, ...]
    written_vertices: tuple[int, ...]  # Supplied list order, including duplicates.


def _team_id(value: int) -> int:
    value = _integer(value, 32767)
    if not value:
        raise ValueError("Adapter selected proxy vertex requires a positive Int16 Team")
    return value


def update_world_proxy(
    vertex_indices: Sequence[int],
    teams: Mapping[int, ProxyUpdateTeam],
    team_ids: Sequence[int],
    buffers: WorldProxyBuffers,
    previous_positions: Sequence[Vector3],
    previous_rotations: Sequence[Quaternion],
) -> WorldProxyUpdate:
    """Resolve four distinct Team windows, then selected world position/frame.

    Kernel consumes an already produced list: no second flag/attribute gate.
    Output capacities parallel; selected indices must belong to their supplied
    Team common chunk. These are safe-adapter checks, not original comparisons.
    Unlisted previous outputs are copied verbatim, not Single-rounded/normalized.
    No deduplication, native aliasing or cross-Team ordering proof is implied.
    """
    count = _integer(len(previous_positions), _INT32_MAX)
    if len(previous_rotations) != count:
        raise ValueError("Adapter requires parallel previous world output buffers")
    positions, rotations = list(previous_positions), list(previous_rotations)
    written = []
    for vertex in vertex_indices:
        vertex = _index(vertex, count)
        identifier = _team_id(team_ids[_index(vertex, len(team_ids))])
        if identifier not in teams:
            raise ValueError("Adapter requires the selected sparse Team")
        team = teams[identifier]
        start, size = _chunk(team.proxy_common_start, team.proxy_common_count)
        if not start <= vertex < start + size:
            raise ValueError(
                "Adapter selected vertex is outside its Team common window"
            )
        mesh = _integer(
            _integer(team.proxy_mesh_start, _INT32_MAX) + vertex - start, _INT32_MAX
        )
        for arena in (
            buffers.local_positions,
            buffers.local_normals,
            buffers.local_tangents,
            buffers.bone_weights,
        ):
            _index(mesh, len(arena))
        positions[vertex], rotations[vertex] = skin_proxy_vertex(
            buffers.local_positions[mesh],
            buffers.local_normals[mesh],
            buffers.local_tangents[mesh],
            buffers.bone_weights[mesh],
            buffers.skin_bone_bindposes,
            buffers.skin_bone_transform_indices,
            buffers.transform_local_to_world,
            skin_start=team.proxy_skin_bone_start,
            transform_start=team.proxy_transform_start,
        )
        written.append(vertex)
    return WorldProxyUpdate(tuple(positions), tuple(rotations), tuple(written))


def build_proxy_update_vertices(
    teams: Mapping[int, ProxyUpdateTeam],
    *,
    team_order: Sequence[int],
    output_capacity: int,
) -> tuple[int, ...]:
    """Finite cleared-counter prefix; not Simulation's Running/Step list gate.

    Team0 precedes lookup; require flag2, reject bit61/800/80000. Do NOT reject
    bit10 or require Running20/Step80. Each native reservation appends a whole
    ascending common block; cross-Team block order is caller supplied here.
    Validate total explicit capacity BEFORE materializing; tails are not cleared.
    Positive Int16 domain, chunk/counter bounds and nonnegative capacity are
    adapter policies; negative native counts/wrap/races are not simulated.
    """
    capacity = _integer(output_capacity, _INT32_MAX)
    chunks = []
    for identifier in team_order:
        identifier = _integer(identifier, 32767)
        if identifier == 0:
            continue
        if identifier not in teams:
            raise ValueError("Adapter requires every selected sparse Team")
        team = teams[identifier]
        flag = _integer(team.flag, 2**64 - 1)
        if flag & 2 and not flag & ((1 << 61) | 0x800 | 0x80000):
            chunks.append(_chunk(team.proxy_common_start, team.proxy_common_count))
    total = sum(size for _, size in chunks)
    if total > capacity or total > _INT32_MAX:
        raise ValueError(
            "Adapter proxy list exceeds explicit output capacity/Int32 counter"
        )
    return tuple(start + local for start, size in chunks for local in range(size))
