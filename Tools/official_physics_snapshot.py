"""Finite RenderSetupData.ReadTransformJob reference, not Unity transform getters.

Method370212/RVA0x5a631e4 copies WORLD/LOCAL position and raw quaternion;
scale is diag(float4x4(inverse(worldQuaternion), float3.zero) * worldLtoW).
This is NOT localScale, lossyScale, column length or absolute scale. Unity matrix
conversion reads GetColumn(0..3); no transpose or quaternion normalization.
None represents invalid TransformAccess: original skips all six buffer writes.
An existing slot is required to preserve it; refusing absent storage is policy.

Caller provides actual getter outputs in original coordinates/order. This does
not reconstruct Unity hierarchy, sample live transforms, resolve saved-selection
branches, import skin weights/bindposes, schedule Jobs or write Unity bones.
All finite/shape/size/degeneracy rejection is adapter policy, not native guards.
"""

from collections.abc import Sequence
from dataclasses import dataclass
from typing import cast

from official_physics_angle_baseline import _integer
from official_physics_angle_cache import _quaternion, quaternion_inverse
from official_physics_angles import Quaternion, _float3
from official_physics_bone_import import (
    ImportedBoneFrames,
    Matrix4,
    _matrix,
    import_bone_frames,
)
from official_physics_constraints import Vector3, _single
from official_physics_selection import GeneratedBoneSelection, generate_bone_selection


def rotation_matrix_single(rotation: Quaternion) -> Matrix4:
    """float3x3 quaternion ctor0x305d4c0, then float4x4 ctor0xa1f3910.

    q+q, sign-bit XOR via negation, products, subtraction, THEN basis addition.
    No norm division, reassociation, fused multiply-add or sqrt shortcuts.
    Translation is original float3.zero; fourth component constant is 1.
    """
    x, y, z, w = _quaternion(rotation)
    dx, dy, dz = (_single(v + v) for v in (x, y, z))
    yxw, zwx, wzy = (-y, x, -w), (z, -w, -x), (-w, -z, y)
    terms = (
        (dy, yxw, dz, zwx, (1, 0, 0)),
        (dz, wzy, dx, yxw, (0, 1, 0)),
        (dx, zwx, dy, wzy, (0, 0, 1)),
    )
    columns = tuple(
        tuple(
            _single(_single(_single(a * u) - _single(b * v)) + basis)
            for u, v, basis in zip(first, second, unit, strict=True)
        )
        + (0.0,)
        for a, first, b, second, unit in terms
    )
    return cast(Matrix4, columns + ((0.0, 0.0, 0.0, 1.0),))


def multiply_matrices_single(
    left: Sequence[Sequence[float]], right: Sequence[Sequence[float]]
) -> Matrix4:
    """helper0x305d9c0: each column (((a.c0*b.x+a.c1*b.y)+a.c2*b.z)+a.c3*b.w)."""
    a, b = _matrix(left), _matrix(right)
    return cast(
        Matrix4,
        tuple(
            tuple(
                _single(
                    _single(
                        _single(_single(a[0][lane] * c[0]) + _single(a[1][lane] * c[1]))
                        + _single(a[2][lane] * c[2])
                    )
                    + _single(a[3][lane] * c[3])
                )
                for lane in range(4)
            )
            for c in b
        ),
    )


@dataclass(frozen=True)
class TransformGetterValues:
    position: Vector3
    rotation: Quaternion
    local_to_world: Sequence[Sequence[float]]
    local_position: Vector3
    local_rotation: Quaternion


@dataclass(frozen=True)
class RenderTransformSnapshot:
    position: Vector3
    rotation: Quaternion
    scale: Vector3
    local_position: Vector3
    local_rotation: Quaternion
    inverse_rotation: Quaternion


def read_transform_snapshot(
    values: TransformGetterValues | None,
    previous: RenderTransformSnapshot | None = None,
) -> RenderTransformSnapshot:
    """One original six-buffer slot. Invalid access retains previous, never zeros."""
    if values is None:
        if previous is None:
            raise ValueError(
                "Adapter requires previous storage for invalid TransformAccess"
            )
        return previous
    position, rotation = _float3(values.position), _quaternion(values.rotation)
    matrix = _matrix(values.local_to_world)
    local_position = _float3(values.local_position)
    local_rotation = _quaternion(values.local_rotation)
    inverse = quaternion_inverse(rotation)
    unrotated = multiply_matrices_single(rotation_matrix_single(inverse), matrix)
    scale = cast(Vector3, tuple(unrotated[lane][lane] for lane in range(3)))
    return RenderTransformSnapshot(
        position, rotation, scale, local_position, local_rotation, inverse
    )


def read_transform_snapshots(
    values: Sequence[TransformGetterValues | None],
    previous: Sequence[RenderTransformSnapshot | None] | None = None,
) -> tuple[RenderTransformSnapshot, ...]:
    """Ordered slots only; no hierarchy traversal, implicit render slot or Job schedule."""
    count = _integer(len(values), 65536)
    if previous is None:
        previous = (None,) * count
    if len(previous) != count:
        raise ValueError("Adapter requires parallel previous snapshot storage")
    return tuple(
        read_transform_snapshot(v, p) for v, p in zip(values, previous, strict=True)
    )


@dataclass(frozen=True)
class SnapshotBoneInputs:
    snapshots: tuple[RenderTransformSnapshot, ...]
    selection: GeneratedBoneSelection
    frames: ImportedBoneFrames


def prepare_snapshot_bone_inputs(
    skin_getters: Sequence[TransformGetterValues | None],
    world_to_local: Sequence[Sequence[float]],
    parents_excluding_render: Sequence[int],
    fixed_root_indices: Sequence[int | None],
    previous: Sequence[RenderTransformSnapshot | None] | None = None,
) -> SnapshotBoneInputs:
    """Explicit NEW-selection branch: getter slots -> selection + frame inputs.

    SKIN slots only, excluding appended render transform. Do not overwrite edited
    selection with this branch. Selection/frame positions share supplied WtoL;
    scales are retained for future bindpose import, NOT yet used by frame-only API.
    Actual Unity getter capture and selection/proxy branch choice remain gates.
    """
    snapshots = read_transform_snapshots(skin_getters, previous)
    positions = tuple(slot.position for slot in snapshots)
    rotations = tuple(slot.rotation for slot in snapshots)
    selection = generate_bone_selection(
        world_to_local, positions, parents_excluding_render, fixed_root_indices
    )
    frames = import_bone_frames(world_to_local, positions, rotations)
    return SnapshotBoneInputs(snapshots, selection, frames)
