"""Finite value/write-order reference for WriteTransformJob369494/0x5a277d4.

NOT actual TransformAccess setters, native jobs or complete original physics.
Weight is Single(clothSimulateWeight * clothLodFadeWeight), not blendWeight.
World bit2 has priority over local bit4; enable bit0x10 and culling gates apply.
World position additionally needs Team flag0x2000. Relative mode uses caller-
resolved source forward TRS matrix and Quaternion(matrix); building those from Team
relativePos/relativeRot is NOT implemented here, never replaced with identity.

Selected values must be finite: NaN/Inf/overflow rejection is ADAPTER POLICY.
Source vectors check NaN only; source quaternion also checks finite lanes and
dot(q,q)<Single(.01). Do not claim identical native invalid-value exceptions.
Single arithmetic grouping is retained, but Python trig/sqrt is not a bit-exact
oracle for source CRT/Burst implementations. Unselected buffers are not read.
Returned operations preserve setter order and partial quaternion skips, but do
not execute a setter, recompute hierarchy or decide scheduling/buffer age.
"""

import math
from collections.abc import Sequence
from dataclasses import dataclass
from typing import Literal, cast

from official_physics_angle_baseline import _index, _integer
from official_physics_angle_cache import _quaternion, multiply_quaternions
from official_physics_angles import Quaternion, _float3
from official_physics_constraints import Vector3, _single
from official_physics_publication import TransformBufferSnapshot
from official_physics_writeback import _double3


@dataclass(frozen=True)
class SetterTeam:
    flag: int
    cloth_simulate_weight: float
    cloth_lod_fade_weight: float
    use_relative_transform: int = 0


@dataclass(frozen=True)
class TransformPose:
    world_position: Vector3
    world_rotation: Quaternion
    local_position: Vector3
    local_rotation: Quaternion


@dataclass(frozen=True)
class RelativeWriteContext:
    # Four COLUMN vectors, caller must supply actual resolved source results.
    matrix: tuple[Quaternion, ...]
    matrix_rotation: Quaternion


@dataclass(frozen=True)
class TransformWrite:
    property: Literal[
        "world_position", "world_rotation", "local_position", "local_rotation"
    ]
    value: tuple[float, ...]


def _dot(a: Quaternion, b: Quaternion) -> float:
    lanes = [_single(x * y) for x, y in zip(a, b, strict=True)]
    return _single(_single(_single(lanes[1] + lanes[0]) + lanes[2]) + lanes[3])


def _valid_rotation(q: Quaternion) -> bool:
    return _dot(q, q) >= _single(0.01)


def interpolate_rotation(a: Quaternion, b: Quaternion, weight: float) -> Quaternion:
    """5a19748/5a19668: shortest-arc slerp; dot>=.9995 normalized-lerp branch.

    Finite weight in [0,1] only (adapter). Caller setter bypasses this entirely
    at weight>=1. Regular slerp does NOT force normalize input/output; preserving
    source nonunit behavior is different from always-normalized Unity helpers.
    Transcendentals rounded to Single, not a native bit-equivalence claim.
    """
    a, b, t = _quaternion(a), _quaternion(b), _single(weight)
    if not 0 <= t <= 1:
        raise ValueError("Adapter interpolation weight must be in [0,1]")
    dot = _dot(a, b)
    if dot < 0:
        dot = -dot
        b = cast(Quaternion, tuple(-lane for lane in b))
    if dot >= _single(0.9995):
        blended = cast(
            Quaternion,
            tuple(
                _single(x + _single(t * _single(y - x)))
                for x, y in zip(a, b, strict=True)
            ),
        )
        inverse = _single(1 / _single(math.sqrt(_dot(blended, blended))))
        return cast(Quaternion, tuple(_single(x * inverse) for x in blended))
    inverse_sin = _single(1 / _single(math.sqrt(_single(1 - _single(dot * dot)))))
    angle = _single(math.acos(dot))
    wb = _single(_single(math.sin(_single(angle * t))) * inverse_sin)
    wa = _single(_single(math.sin(_single(_single(1 - t) * angle))) * inverse_sin)
    return cast(
        Quaternion,
        tuple(
            _single(_single(x * wa) + _single(y * wb))
            for x, y in zip(a, b, strict=True)
        ),
    )


def _lerp(a: Vector3, b: Vector3, t: float) -> Vector3:
    return cast(
        Vector3,
        tuple(
            _single(x + _single(_single(y - x) * t)) for x, y in zip(a, b, strict=True)
        ),
    )


def _relative(context: RelativeWriteContext | None) -> RelativeWriteContext:
    if context is None:
        raise ValueError("Adapter requires resolved source relative matrix/rotation")
    if len(context.matrix) != 4 or any(len(col) != 4 for col in context.matrix):
        raise ValueError("Adapter requires a 4-column matrix")
    return RelativeWriteContext(
        tuple(_quaternion(col) for col in context.matrix),
        _quaternion(context.matrix_rotation),
    )


def _point(context: RelativeWriteContext, p: Vector3) -> Vector3:
    # 34e0ba0: ((col0*x + col1*y) + col2*z) + col3, xyz, no divide by w.
    c0, c1, c2, c3 = context.matrix
    return cast(
        Vector3,
        tuple(
            _single(
                _single(
                    _single(_single(c0[i] * p[0]) + _single(c1[i] * p[1]))
                    + _single(c2[i] * p[2])
                )
                + c3[i]
            )
            for i in range(3)
        ),
    )


def _current(current: TransformPose | None) -> TransformPose:
    if current is None:
        raise ValueError(
            "Adapter requires current Transform getter values for fractional weight"
        )
    return current


def _at(values: Sequence[tuple[float, ...]], slot: int) -> tuple[float, ...]:
    return values[_index(slot, len(values))]


def compute_transform_writes(
    *,
    slot: int,
    transform_valid: bool,
    flags: Sequence[int],
    team_ids: Sequence[int],
    teams: Sequence[SetterTeam | None],
    buffers: TransformBufferSnapshot,
    current: TransformPose | None,
    relative: RelativeWriteContext | None = None,
) -> tuple[TransformWrite, ...]:
    """One source slot, already supplied current/last arrays chosen by manager.

    No invented team0 gate. Team integer ranges/nonfinite rejection are adapter
    safety, not native index handling. Invalid final finite quaternion skips
    that setter without rolling back another property; no identity repair.
    Matrix construction and actual setters remain external/unported boundaries.
    """
    if type(transform_valid) is not bool:
        raise ValueError("Adapter requires bool Transform validity")
    if not transform_valid:
        return ()
    flag = _integer(flags[_index(slot, len(flags))], 255)
    if not flag & 0x10:
        return ()
    team_id = _integer(team_ids[_index(slot, len(team_ids))], 32767)
    team = teams[_index(team_id, len(teams))]
    if team is None:
        raise ValueError(
            "Adapter requires source TeamData, including team0 if selected"
        )
    team_flag = _integer(team.flag, 2**64 - 1)
    if team_flag & (0x800 | 0x80000):  # Source culling helper reads low UInt32.
        return ()
    weight = _single(
        _single(team.cloth_simulate_weight) * _single(team.cloth_lod_fade_weight)
    )
    if weight <= 0:
        return ()
    output: list[TransformWrite] = []
    if flag & 2:
        # Source checks double world position before rotation even with no pos write.
        position = _double3(_at(buffers.world_positions, slot))
        q = _quaternion(cast(Quaternion, _at(buffers.world_rotations, slot)))
        if weight < 1:
            q = interpolate_rotation(
                _quaternion(_current(current).world_rotation), q, weight
            )
        use_relative = _integer(team.use_relative_transform, 2**32 - 1)
        context = _relative(relative) if use_relative else None
        if context is not None:
            q = multiply_quaternions(context.matrix_rotation, q)
        if _valid_rotation(q):
            output.append(TransformWrite("world_rotation", q))
        if team_flag & 0x2000:
            p = _float3(
                position
            )  # AutoToFloat3 BEFORE interpolation/relative multiply.
            if weight < 1:
                p = _lerp(_float3(_current(current).world_position), p, weight)
            if context is not None:
                p = _point(context, p)
            output.append(TransformWrite("world_position", p))
    elif flag & 4:
        p = _float3(cast(Vector3, _at(buffers.local_positions, slot)))
        if weight < 1:
            p = _lerp(_float3(_current(current).local_position), p, weight)
        output.append(TransformWrite("local_position", p))
        q = _quaternion(cast(Quaternion, _at(buffers.local_rotations, slot)))
        if weight < 1:
            q = interpolate_rotation(
                _quaternion(_current(current).local_rotation), q, weight
            )
        if _valid_rotation(q):
            output.append(TransformWrite("local_rotation", q))
    return tuple(output)
