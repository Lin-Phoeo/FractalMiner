"""Finite source Read/RestoreTransform values; NOT Unity hierarchy or physics.

Restore369464/0x5a1ed50 uses manager INITIAL local buffers, mask0x08 gate, then
enable OR Team0x100000, culling pair(0x800 AND 0x1000) OR0x80000. No weights,
rotation norm filtering or world writes. Read369465/0x5a1e6d8 instead needs
enable AND read mask0x01, skips culling OR0x800 OR0x80000 and Team (1<<61).

Read scale is diagonal(R(inverse(worldQuaternion))*localToWorldMatrix), NOT
localScale/lossyScale/column lengths. World getter position is Single, widened
to Double AFTER optional relative inverse-matrix transform. Local buffers and
scale stay in original getter space. Relative inverse TRS and Quaternion(matrix)
construction remain caller-resolved boundaries, distinct from forward setter.

Finite/index/zero-norm rejection is adapter policy, not native exceptions.
One successful stable slot; captured getters stand in for actual getter calls.
No Animator buffer job, native scheduler, hierarchy feedback or full solver.
"""

from collections.abc import Sequence
from dataclasses import dataclass
from typing import cast

from official_physics_angle_baseline import _index, _integer
from official_physics_angle_cache import (
    _quaternion,
    multiply_quaternions,
    quaternion_inverse,
)
from official_physics_angles import Quaternion, _float3
from official_physics_constraints import Vector3, _single
from official_physics_proxy_baseline import LocalPose
from official_physics_setter import (
    RelativeWriteContext,
    TransformPose,
    TransformWrite,
    _point,
)
from official_physics_writeback import Double3, _double3

Matrix = tuple[Quaternion, ...]  # Four Single4 COLUMN vectors.


@dataclass(frozen=True)
class ReadRestoreTeam:
    flag: int
    use_relative_transform: int = 0


@dataclass(frozen=True)
class CapturedTransform:
    pose: TransformPose
    local_to_world_matrix: Matrix


@dataclass(frozen=True)
class RelativeReadContext:
    inverse_matrix: Matrix
    inverse_matrix_rotation: Quaternion


@dataclass(frozen=True)
class ReadTransformValues:
    world_position: Double3
    world_rotation: Quaternion
    local_position: Vector3
    local_rotation: Quaternion
    scale: Vector3
    local_to_world_matrix: Matrix
    write_order: tuple[str, ...]


def _matrix(value: Matrix) -> Matrix:
    if len(value) != 4 or any(len(col) != 4 for col in value):
        raise ValueError("Adapter requires four matrix columns of four Singles")
    return tuple(_quaternion(col) for col in value)


def rotation_translation_matrix(q: Quaternion, translation: Vector3) -> Matrix:
    """305d4c0 + a1f3910: source swizzle signs/groups; nonunit input retained.

    NOT UnityEngine.Matrix4x4.TRS; its native construction remains unported.
    """
    x, y, z, w = _quaternion(q)
    twice_x, twice_y, twice_z = (_single(v + v) for v in (x, y, z))
    left = ((-y, x, -w), (-w, -z, y), (z, -w, -x))
    right = ((z, -w, -x), (-y, x, -w), (-w, -z, y))
    factors = ((twice_y, twice_z), (twice_z, twice_x), (twice_x, twice_y))
    columns: list[Quaternion] = []
    for col, (a, b) in enumerate(factors):
        lanes = tuple(
            _single(
                _single(_single(a * left[col][row]) - _single(b * right[col][row]))
                + (1.0 if row == col else 0.0)
            )
            for row in range(3)
        )
        columns.append(cast(Quaternion, lanes + (0.0,)))
    return tuple(columns) + (cast(Quaternion, _float3(translation) + (1.0,)),)


def multiply_matrices(a: Matrix, b: Matrix) -> Matrix:
    """305d9c0: each result column = ((a0*bx+a1*by)+a2*bz)+a3*bw.

    All four lanes including w; no affine-only simplification/FMA/NumPy dot.
    """
    a, b = _matrix(a), _matrix(b)
    return tuple(
        cast(
            Quaternion,
            tuple(
                _single(
                    _single(
                        _single(_single(a[0][i] * col[0]) + _single(a[1][i] * col[1]))
                        + _single(a[2][i] * col[2])
                    )
                    + _single(a[3][i] * col[3])
                )
                for i in range(4)
            ),
        )
        for col in b
    )


def _valid(valid: bool) -> bool:
    if type(valid) is not bool:
        raise ValueError("Adapter requires bool Transform validity")
    return valid


def _team_flag(
    slot: int, team_ids: Sequence[int], teams: Sequence[ReadRestoreTeam | None]
) -> tuple[ReadRestoreTeam, int]:
    team_id = _integer(team_ids[_index(slot, len(team_ids))], 32767)
    team = teams[_index(team_id, len(teams))]
    if team is None:
        raise ValueError("Adapter requires source TeamData even for selected team0")
    return team, _integer(team.flag, 2**64 - 1)


def compute_restore_writes(
    *,
    slot: int,
    transform_valid: bool,
    flags: Sequence[int],
    team_ids: Sequence[int],
    teams: Sequence[ReadRestoreTeam | None],
    initial_local: LocalPose,
) -> tuple[TransformWrite, ...]:
    """Read ONLY manager initLocalPositionArray/initLocalRotationArray.

    Ordered local position then local rotation; no norm check or normalization.
    Caller supplies true init arrays, not latest ReadTransform's local snapshot.
    """
    if not _valid(transform_valid):
        return ()
    flag = _integer(flags[_index(slot, len(flags))], 255)
    if not flag & 8:
        return ()
    _, team_flag = _team_flag(slot, team_ids, teams)
    if not flag & 0x10 and not team_flag & 0x100000:
        return ()
    if (team_flag & 0x800 and team_flag & 0x1000) or team_flag & 0x80000:
        return ()
    p = _float3(initial_local.positions[_index(slot, len(initial_local.positions))])
    q = _quaternion(initial_local.rotations[_index(slot, len(initial_local.rotations))])
    return TransformWrite("local_position", p), TransformWrite("local_rotation", q)


def read_transform_values(
    *,
    slot: int,
    transform_valid: bool,
    flags: Sequence[int],
    team_ids: Sequence[int],
    teams: Sequence[ReadRestoreTeam | None],
    captured: CapturedTransform | None,
    relative: RelativeReadContext | None = None,
) -> ReadTransformValues | None:
    """Successful gated slot values; None means preserve existing output slots.

    Source getters: position, rotation, localToWorldMatrix, localPosition,
    localRotation. Returned write order includes initial and final matrix writes.
    Native inverse TRS/matrix-quaternion are NOT rebuilt from relative Team fields.
    """
    if not _valid(transform_valid):
        return None
    flag = _integer(flags[_index(slot, len(flags))], 255)
    if not flag & 0x10 or not flag & 1:
        return None
    team, team_flag = _team_flag(slot, team_ids, teams)
    if team_flag & (0x800 | 0x80000 | (1 << 61)):
        return None
    if captured is None:
        raise ValueError("Adapter requires captured Transform getter values")
    p = _float3(captured.pose.world_position)
    q = _quaternion(captured.pose.world_rotation)
    matrix = _matrix(captured.local_to_world_matrix)
    local_p = _float3(captured.pose.local_position)
    local_q = _quaternion(captured.pose.local_rotation)
    unrotated = multiply_matrices(
        rotation_translation_matrix(quaternion_inverse(q), (0, 0, 0)), matrix
    )
    scale = _float3((unrotated[0][0], unrotated[1][1], unrotated[2][2]))
    if _integer(team.use_relative_transform, 2**32 - 1):
        if relative is None:
            raise ValueError(
                "Adapter requires resolved source relative inverse matrix/quaternion"
            )
        inverse = _matrix(relative.inverse_matrix)
        inverse_q = _quaternion(relative.inverse_matrix_rotation)
        p = _point(RelativeWriteContext(inverse, inverse_q), p)
        q = multiply_quaternions(inverse_q, q)
        matrix = multiply_matrices(inverse, matrix)
    return ReadTransformValues(
        _double3(p),
        q,
        local_p,
        local_q,
        scale,
        matrix,
        (
            "local_position",
            "local_rotation",
            "scale",
            "local_to_world_matrix",
            "world_position",
            "world_rotation",
            "local_to_world_matrix",
        ),
    )


def read_component_position(
    *, transform_valid: bool, position: Vector3
) -> Vector3 | None:
    """ReadComponentTransformJob369495: Single position only, validity gate.

    None preserves the existing slot; no Team/flag/weight/relative processing.
    """
    return _float3(position) if _valid(transform_valid) else None
