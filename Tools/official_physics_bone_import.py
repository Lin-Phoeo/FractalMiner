"""Original bone Job's position/frame outputs only; NOT a full proxy importer.

Source: method371578/RVA0x34e00c0, official-physics-bone-import-20261002 docs.
Caller supplies original ordered WORLD transform snapshots and column-major WtoL.
No hierarchy collection, IDs, selection, attributes, scale/bindpose outputs, Team
allocation, alignment Job scheduling, runtime updates or final bone writes here.
Single intermediate grouping and length-compensated directions are preserved.
Finite/shape/degeneracy/size rejection is adapter policy, not native exceptions.
"""

import math
from collections.abc import Sequence
from dataclasses import dataclass
from typing import cast

from official_physics_angle_baseline import _integer
from official_physics_angle_cache import _quaternion, rotate_single
from official_physics_angles import Quaternion, _float3
from official_physics_constraints import Vector3, _positive, _single

Matrix4 = tuple[Quaternion, Quaternion, Quaternion, Quaternion]


def _matrix(value: Sequence[Sequence[float]]) -> Matrix4:
    if len(value) != 4:
        raise ValueError("Adapter requires four column-major float4 matrix columns")
    return cast(
        Matrix4, tuple(_quaternion(cast(Quaternion, column)) for column in value)
    )


def _point(matrix: Matrix4, point: Vector3) -> Vector3:
    # helper0x34e0ba0: (((c0*x + c1*y) + c2*z) + c3). No w division.
    return cast(
        Vector3,
        tuple(
            _single(
                _single(
                    _single(
                        _single(matrix[0][lane] * point[0])
                        + _single(matrix[1][lane] * point[1])
                    )
                    + _single(matrix[2][lane] * point[2])
                )
                + matrix[3][lane]
            )
            for lane in range(3)
        ),
    )


def transform_point_single(
    matrix: Sequence[Sequence[float]], point: Vector3
) -> Vector3:
    """Original float4x4 transform(float3); column-major, no perspective divide."""
    return _point(_matrix(matrix), _float3(point))


def _length_single(value: Vector3) -> float:
    squared = _single(
        _single(_single(value[1] * value[1]) + _single(value[0] * value[0]))
        + _single(value[2] * value[2])
    )
    return _single(math.sqrt(squared))


def _direction(matrix: Matrix4, direction: Vector3) -> Vector3:
    original_length = _length_single(direction)
    if original_length <= 0:
        return direction
    # helper0x34e0540 -> 0x2cd11e0 mul(matrix,float4(v,0)) groups this way.
    # Keep c3*0 and its addition rather than dropping signed-zero arithmetic.
    transformed = cast(
        Vector3,
        tuple(
            _single(
                _single(matrix[2][lane] * direction[2])
                + _single(
                    _single(matrix[3][lane] * 0)
                    + _single(
                        _single(matrix[0][lane] * direction[0])
                        + _single(matrix[1][lane] * direction[1])
                    )
                )
            )
            for lane in range(3)
        ),
    )
    reciprocal = _single(1 / _positive(_length_single(transformed)))
    return cast(
        Vector3,
        tuple(
            _single(_single(lane * reciprocal) * original_length)
            for lane in transformed
        ),
    )


def transform_direction_preserve_length(
    matrix: Sequence[Sequence[float]], direction: Vector3
) -> Vector3:
    """helper0x34e0410: normalize(WtoL*v)*length(v); zero input is retained.

    Not an inverse-transpose normal matrix, not plain matrix rotation. Collapsed
    nonzero direction is rejected by adapter instead of modeling original NaNs.
    """
    return _direction(_matrix(matrix), _float3(direction))


@dataclass(frozen=True)
class ImportedBoneFrames:
    positions: tuple[Vector3, ...]
    normals: tuple[Vector3, ...]
    tangents: tuple[Vector3, ...]


def import_bone_frames(
    world_to_local: Sequence[Sequence[float]],
    world_positions: Sequence[Vector3],
    world_rotations: Sequence[Quaternion],
) -> ImportedBoneFrames:
    """Position and frame portion of original Import_BoneVertexJob.Execute.

    Each index reads its world position/rotation: WtoL*position, compensated
    WtoL*rotate(q,UP), compensated WtoL*rotate(q,FORWARD). No auto-normalizing q,
    swapping axes, applying normalAxis here or inferring forward from children.
    Original Job also writes weights and skin bindposes using scales/LtoW; those
    outputs are NOT implemented or required inputs to this limited frame API.
    Caller/import order, actual world snapshots and downstream tasks remain gates.
    """
    _integer(len(world_positions), 65536)
    if len(world_positions) != len(world_rotations):
        raise ValueError("Adapter requires parallel bone world snapshot buffers")
    matrix = _matrix(world_to_local)
    positions, normals, tangents = [], [], []
    for position, rotation in zip(world_positions, world_rotations, strict=True):
        position, rotation = _float3(position), _quaternion(rotation)
        positions.append(_point(matrix, position))
        normals.append(_direction(matrix, rotate_single(rotation, (0, 1, 0))))
        tangents.append(_direction(matrix, rotate_single(rotation, (0, 0, 1))))
    return ImportedBoneFrames(tuple(positions), tuple(normals), tuple(tangents))
