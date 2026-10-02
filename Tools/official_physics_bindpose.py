"""Finite bone-vertex weight/bindpose reference; not full proxy/Unity backend.

Original Job371578/0x34e00c0: one-hot float4 weight/int4 bone index; then
inverse(TRS(worldPosition, rawWorldQuaternion, recoveredWorldScale)) * LtoW.
Inverse0x34e0d80 uses packed minors, paired signed determinant reciprocal, and
explicit Single arithmetic; NOT fastinverse, transpose, pseudoinverse or WtoL.
Caller order/space/scale must be ORIGINAL inputs. No hierarchy/world getter,
normalAxis, saved-selection branch, Team allocation, solver or bone writes here.
Input/singularity/overflow rejection is adapter policy, not native exceptions.
"""

from collections.abc import Sequence
from dataclasses import dataclass
from typing import cast

from official_physics_angle_baseline import _integer
from official_physics_angles import Quaternion, _float3
from official_physics_bone_import import (
    ImportedBoneFrames,
    Matrix4,
    _matrix,
    import_bone_frames,
)
from official_physics_constraints import Vector3, _single
from official_physics_snapshot import (
    RenderTransformSnapshot,
    SnapshotBoneInputs,
    TransformGetterValues,
    multiply_matrices_single,
    prepare_snapshot_bone_inputs,
    rotation_matrix_single,
)


def _mul(a: Quaternion, b: Quaternion) -> Quaternion:
    return cast(Quaternion, tuple(_single(x * y) for x, y in zip(a, b, strict=True)))


def _add(a: Quaternion, b: Quaternion) -> Quaternion:
    return cast(Quaternion, tuple(_single(x + y) for x, y in zip(a, b, strict=True)))


def _sub(a: Quaternion, b: Quaternion) -> Quaternion:
    return cast(Quaternion, tuple(_single(x - y) for x, y in zip(a, b, strict=True)))


def _split_pairs(packed: Quaternion) -> tuple[Quaternion, Quaternion]:
    x, y, z, w = packed
    return (x, z, z, x), (y, w, w, y)


def inverse_matrix_single(matrix: Sequence[Sequence[float]]) -> Matrix4:
    """Original inverse helper0x34e0d80, finite/nonsingular scalar domain.

    Packing below collapses only copying/shuffles, never floating arithmetic.
    Each product/subtraction/addition and each of four divisions rounds Single.
    Two reciprocal lanes have positive determinant sign, two have negative sign.
    """
    c0, c1, c2, c3 = _matrix(matrix)
    lo_yx = (c1[0], c1[1], c0[0], c0[1])
    lo_zw = (c2[0], c2[1], c3[0], c3[1])
    hi_yx = (c1[2], c1[3], c0[2], c0[3])
    hi_zw = (c2[2], c2[3], c3[2], c3[3])
    mid_yx = (c1[1], c1[2], c0[1], c0[2])
    mid_zw = (c2[1], c2[2], c3[1], c3[2])
    wrap_yx = (c1[3], c1[0], c0[3], c0[0])
    wrap_zw = (c2[3], c2[0], c3[3], c3[0])
    rows = tuple((c3[k], c2[k], c1[k], c0[k]) for k in range(4))
    r0, r1, r2, r3 = rows
    p12, p23 = _split_pairs(_sub(_mul(mid_yx, hi_zw), _mul(mid_zw, hi_yx)))
    p02, p13 = _split_pairs(_sub(_mul(lo_yx, hi_zw), _mul(lo_zw, hi_yx)))
    p30, p01 = _split_pairs(_sub(_mul(wrap_zw, lo_yx), _mul(wrap_yx, lo_zw)))
    minor0 = _add(_sub(_mul(r3, p12), _mul(r2, p13)), _mul(r1, p23))
    determinant = _mul((c0[0], c1[0], c2[0], c3[0]), minor0)
    x, y, z, w = determinant
    determinant = _add(determinant, (y, x, w, z))
    x, _, z, _ = determinant
    determinant = _sub(determinant, (z, z, x, x))
    if any(v == 0 for v in determinant):
        raise ValueError("Adapter refuses singular or Single-underflow determinant")
    reciprocal = cast(Quaternion, tuple(_single(1 / v) for v in determinant))
    minor1 = _sub(_sub(_mul(r2, p30), _mul(r0, p23)), _mul(r3, p02))
    minor2 = _sub(_sub(_mul(r0, p13), _mul(r1, p30)), _mul(r3, p01))
    minor3 = _add(_sub(_mul(r1, p02), _mul(r0, p12)), _mul(r2, p01))
    return cast(
        Matrix4,
        tuple(_mul(minor, reciprocal) for minor in (minor0, minor1, minor2, minor3)),
    )


def bone_trs_single(position: Vector3, rotation: Quaternion, scale: Vector3) -> Matrix4:
    """helper0x305d310: quaternion columns * respective scale, xyz translation, w1."""
    point, factors = _float3(position), _float3(scale)
    rotation_matrix = rotation_matrix_single(rotation)
    columns = tuple(
        tuple(_single(rotation_matrix[col][lane] * factors[col]) for lane in range(3))
        + (0.0,)
        for col in range(3)
    )
    return cast(Matrix4, columns + (point + (1.0,),))


@dataclass(frozen=True)
class ImportedBoneWeight:
    weights: Quaternion
    bone_indices: tuple[int, int, int, int]


@dataclass(frozen=True)
class ImportedBoneVertices:
    frames: ImportedBoneFrames
    bone_weights: tuple[ImportedBoneWeight, ...]
    skin_bone_bindposes: tuple[Matrix4, ...]


def import_bone_vertices(
    world_to_local: Sequence[Sequence[float]],
    local_to_world: Sequence[Sequence[float]],
    world_positions: Sequence[Vector3],
    world_rotations: Sequence[Quaternion],
    world_scales: Sequence[Vector3],
) -> ImportedBoneVertices:
    """All five finite bone vertex Job outputs, not whole ImportBoneType.

    WtoL affects frame/position outputs; LtoW is the bindpose RIGHT operand.
    No extra influence, bone-name sort, skin/render slot or scale normalization.
    Native Job writes incrementally; this offline API returns only on success.
    """
    count = _integer(len(world_positions), 65536)
    if len(world_rotations) != count or len(world_scales) != count:
        raise ValueError("Adapter requires parallel position/rotation/scale buffers")
    ltow = _matrix(local_to_world)
    frames = import_bone_frames(world_to_local, world_positions, world_rotations)
    weights, bindposes = [], []
    for index, (p, q, s) in enumerate(
        zip(world_positions, world_rotations, world_scales, strict=True)
    ):
        weights.append(ImportedBoneWeight((1.0, 0.0, 0.0, 0.0), (index, 0, 0, 0)))
        bindposes.append(
            multiply_matrices_single(
                inverse_matrix_single(bone_trs_single(p, q, s)), ltow
            )
        )
    return ImportedBoneVertices(frames, tuple(weights), tuple(bindposes))


@dataclass(frozen=True)
class BoundBoneInputs:
    inputs: SnapshotBoneInputs
    vertices: ImportedBoneVertices


def prepare_bound_bone_inputs(
    skin_getters: Sequence[TransformGetterValues | None],
    world_to_local: Sequence[Sequence[float]],
    local_to_world: Sequence[Sequence[float]],
    parents_excluding_render: Sequence[int],
    fixed_root_indices: Sequence[int | None],
    previous: Sequence[RenderTransformSnapshot | None] | None = None,
) -> BoundBoneInputs:
    """Explicit new-selection snapshot -> frames/weights/bindposes composition.

    Does not choose actual saved-selection path or create full proxy/solver data.
    Both render matrices are original caller-supplied matrices, not derived from
    each other with a guessed inverse or silently forced to identity.
    """
    inputs = prepare_snapshot_bone_inputs(
        skin_getters,
        world_to_local,
        parents_excluding_render,
        fixed_root_indices,
        previous,
    )
    snapshots = inputs.snapshots
    vertices = import_bone_vertices(
        world_to_local,
        local_to_world,
        tuple(s.position for s in snapshots),
        tuple(s.rotation for s in snapshots),
        tuple(s.scale for s in snapshots),
    )
    return BoundBoneInputs(inputs, vertices)
