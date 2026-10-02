"""Offline proxy ID/ordered-child/local-pose references, NOT live Unity physics.

Source-bound evidence: official-physics-proxy-chain-20261002 docs. Int32 runtime
transform IDs are NOT serialized Int64 PPtr path IDs. Reverse child enumeration
applies ONLY to a fresh, serial, no-delete/no-resize head-inserted map. No runtime
import, complete proxy generation, normal adjustment, root-depth or Job scheduler.
Finite/range/degenerate/duplicate checks are adapter policy, not native exceptions.
"""

import math
import struct
from collections.abc import Sequence
from dataclasses import dataclass
from typing import cast

from official_physics_angle_baseline import _index, _integer
from official_physics_angle_cache import (
    _quaternion,
    multiply_quaternions,
    quaternion_inverse,
    rotate_single,
)
from official_physics_angles import Quaternion, _float3
from official_physics_constraints import Vector3, _positive, _single


def _int32(value: int) -> int:
    if type(value) is not int or not -(2**31) <= value < 2**31:
        raise ValueError("Adapter requires an Int32 runtime transform ID/parent")
    return value


@dataclass(frozen=True)
class TransformIndexMap:
    parents: tuple[int, ...]
    roots: tuple[int, ...]


def map_transform_ids(
    ids: Sequence[int], parent_ids: Sequence[int], ordered_root_ids: Sequence[int]
) -> TransformIndexMap:
    """Missing parent -> -1; missing root -> adapter error, root order retained."""
    _integer(len(ids), 65536)
    if len(ids) != len(parent_ids):
        raise ValueError("Adapter requires parallel transform ID buffers")
    index = {_int32(identity): slot for slot, identity in enumerate(ids)}
    if len(index) != len(ids):
        raise ValueError("Adapter refuses duplicate transform IDs")
    parents = tuple(index.get(_int32(parent), -1) for parent in parent_ids)
    roots = []
    for identity in ordered_root_ids:
        identity = _int32(identity)
        if identity not in index:
            raise ValueError("Adapter root ID is absent from the vertex ID map")
        roots.append(index[identity])
    return TransformIndexMap(parents, tuple(roots))


def reverse_inserted_children_no_resize(
    parents: Sequence[int],
) -> tuple[tuple[int, ...], ...]:
    """Ascending vertex insert + bucket-head chain -> descending matching children.

    Explicit PRECONDITION: empty original map, serial Add, no remove/reallocation.
    Hash collisions do not change matching-key relative order under these rules.
    This is NOT a universal NativeMultiHashMap order rule: rehash may reverse it.
    Original builder passes 3*vertexCount to map construction before insertion;
    actual allocation/import/Job path still needs separate runtime verification.
    """
    count = _integer(len(parents), 65536)
    children: list[list[int]] = [[] for _ in parents]
    for child, parent in enumerate(parents):
        parent = _int32(parent)
        if parent >= 0:
            children[_index(parent, count)].append(child)
    return tuple(tuple(reversed(row)) for row in children)


def _cross_single(a: Vector3, b: Vector3) -> Vector3:
    return (
        _single(_single(a[1] * b[2]) - _single(a[2] * b[1])),
        _single(_single(a[2] * b[0]) - _single(a[0] * b[2])),
        _single(_single(a[0] * b[1]) - _single(a[1] * b[0])),
    )


def _normalization_scale(values: Sequence[float]) -> float:
    # Native float3/float4 dot: ((y*y + x*x) + z*z) [+ w*w].
    norm = _single(
        _single(_single(values[1] * values[1]) + _single(values[0] * values[0]))
        + _single(values[2] * values[2])
    )
    if len(values) == 4:
        norm = _single(norm + _single(values[3] * values[3]))
    return _single(1 / _positive(_single(math.sqrt(_positive(norm)))))


def _bits(value: float) -> int:
    return struct.unpack("<I", struct.pack("<f", value))[0]


def _signed(value: float, flip: int) -> float:
    return struct.unpack("<f", struct.pack("<I", _bits(value) ^ flip))[0]


def _matrix_quaternion(u: Vector3, v: Vector3, w: Vector3) -> Quaternion:
    """Observed matrix helper0x305c840, corroborated by local Mathematics1.2.6.

    Keep IEEE sign-bit decisions and swizzle order, including negative zero.
    No arbitrary quaternion sign canonicalization or reassociated normalization.
    """
    sign = 0x80000000
    u_sign = _bits(u[0]) & sign
    t = _single(v[1] + _signed(w[2], u_sign))
    t_sign = _bits(t) & sign
    u_mask, t_mask = (0xFFFFFFFF if u_sign else 0), (0xFFFFFFFF if t_sign else 0)
    base, u_flips, t_flips = (
        (0, sign, sign, sign),
        (0, sign, 0, sign),
        (sign, sign, sign, 0),
    )
    flips = tuple(
        a ^ (u_mask & b) ^ (t_mask & c)
        for a, b, c in zip(base, u_flips, t_flips, strict=True)
    )
    left, right = (_single(1 + abs(u[0])), u[1], w[0], v[2]), (t, v[0], u[2], w[1])
    value = tuple(
        _single(a + _signed(b, f)) for a, b, f in zip(left, right, flips, strict=True)
    )
    if u_sign:
        value = (value[2], value[3], value[0], value[1])
    if not t_sign:
        value = (value[3], value[2], value[1], value[0])
    scale = _normalization_scale(value)
    return cast(Quaternion, tuple(_single(lane * scale) for lane in value))


def rotation_from_normal_tangent(normal: Vector3, tangent: Vector3) -> Quaternion:
    """Native helper0x39d4250: normal=up, tangent=forward (not swapped).

    right=normalize(cross(normal,tangent)); up=cross(tangent,right).
    The original tangent length is retained; neither input is auto-normalized.
    Degenerate cross is rejected rather than inventing LookRotationSafe fallback.
    """
    normal, tangent = _float3(normal), _float3(tangent)
    right = _cross_single(normal, tangent)
    scale = _normalization_scale(right)
    right = cast(Vector3, tuple(_single(lane * scale) for lane in right))
    return _matrix_quaternion(right, _cross_single(tangent, right), tangent)


@dataclass(frozen=True)
class LocalPose:
    positions: tuple[Vector3, ...]
    rotations: tuple[Quaternion, ...]


def evaluate_baseline_local_pose(
    baseline_data: Sequence[int],
    parents: Sequence[int],
    positions: Sequence[Vector3],
    normals: Sequence[Vector3],
    tangents: Sequence[Vector3],
    initial_local_positions: Sequence[Vector3],
    initial_local_rotations: Sequence[Quaternion],
) -> LocalPose:
    """Execute selected data slots of method371608; parent<0 -> zero/identity.

    Not first-slot gating. For every nonnegative parent (even a baseline root):
    inverse(parentFrame) rotates child-parent Single delta and multiplies childFrame.
    Read ORIGINAL frame inputs, never earlier local outputs. Unlisted outputs are
    retained; caller supplies initial buffers instead of guessing allocation state.
    Sequential offline writes do not certify original Job alias/race behavior.
    """
    count = _integer(len(parents), 65536)
    if any(
        len(buffer) != count
        for buffer in (
            positions,
            normals,
            tangents,
            initial_local_positions,
            initial_local_rotations,
        )
    ):
        raise ValueError("Adapter requires equally sized local-pose buffers")
    for parent in parents:
        if _int32(parent) >= 0:
            _index(parent, count)
    local_positions = [_float3(value) for value in initial_local_positions]
    local_rotations = [_quaternion(value) for value in initial_local_rotations]
    for vertex in baseline_data:
        vertex = _index(_integer(vertex, 65535), count)
        parent = parents[vertex]
        if parent < 0:
            local_positions[vertex], local_rotations[vertex] = (0, 0, 0), (0, 0, 0, 1)
            continue
        inverse = quaternion_inverse(
            rotation_from_normal_tangent(normals[parent], tangents[parent])
        )
        child_frame = rotation_from_normal_tangent(normals[vertex], tangents[vertex])
        child, parent_position = _float3(positions[vertex]), _float3(positions[parent])
        delta = cast(
            Vector3,
            tuple(_single(a - b) for a, b in zip(child, parent_position, strict=True)),
        )
        local_positions[vertex] = rotate_single(inverse, delta)
        local_rotations[vertex] = multiply_quaternions(inverse, child_frame)
    return LocalPose(tuple(local_positions), tuple(local_rotations))
