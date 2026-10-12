"""Finite ReadAnimatorBufferDataJob._Do branch values, NOT a live animator.

369459/0x5a1dc98: teamIdArray is read BEFORE Transform validity/slot flags.
Enabled AND read flags required; IsCullingInvisible skips mask0x800|0x80000,
NOT the ordinary read job's extra bit61 gate. Three short-circuit map lookups:
manager slot -> handler index, team -> animator instance ID, animator -> buffers.
Any missing lookup falls back to Transform getter captures; invalid selected
buffers do not count as a missing lookup. Team0 is not an extra skip.

Mapped world matrix is source native TRS(world p,q,Vector3.one), CALLER-RESOLVED.
Inverse-q diagonal scale is computed then overwritten with (1,1,1) for mapped
buffers only. Getter fallback retains its signed diagonal. Relative inverse TRS
and matrix quaternion are likewise caller-resolved, not invented identity.

Stable typed maps/captures are adapter inputs, NOT runtime native hash maps or
serialized PPtr IDs. The record reader consumes selected raw record arrays and
requires an explicit native unit-scale TRS resolver; it never builds all records
eagerly or gates reads on writer status. No native record/TRS construction,
incremental NativeArray writes, writer Job, hierarchy or complete physics.
Finite/range/shape rejection is adapter policy, not native fault equivalence.
"""

from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from typing import TypeVar, cast

from official_physics_angle_baseline import _index, _integer
from official_physics_angle_cache import (
    _quaternion,
    multiply_quaternions,
    quaternion_inverse,
)
from official_physics_angles import Quaternion, _float3
from official_physics_animator_write import AnimatorRecord
from official_physics_constraints import Vector3
from official_physics_read_restore import (
    CapturedTransform,
    Matrix,
    ReadRestoreTeam,
    ReadTransformValues,
    RelativeReadContext,
    _matrix,
    _valid,
    multiply_matrices,
    rotation_translation_matrix,
)
from official_physics_registration import _int32
from official_physics_setter import RelativeWriteContext, TransformPose, _point
from official_physics_writeback import _double3

Lookup = tuple[str, int, bool]
T = TypeVar("T")
NativeUnitTrsResolver = Callable[[int, int, Vector3, Quaternion], Matrix]


@dataclass(frozen=True)
class AnimatorReadResult:
    values: ReadTransformValues
    used_buffer: bool
    lookups: tuple[Lookup, ...]
    scale_writes: tuple[Vector3, ...]


def _lookup(
    mapping: Mapping[int, T], key: int, name: str, trace: list[Lookup]
) -> tuple[bool, T | None]:
    found = key in mapping
    trace.append((name, key, found))
    return (True, mapping[key]) if found else (False, None)


def _read_animator_values(
    *,
    slot: int,
    transform_valid: bool,
    flags: Sequence[int],
    team_ids: Sequence[int],
    teams: Sequence[ReadRestoreTeam | None],
    transform_to_handler: Mapping[int, int],
    team_to_animator: Mapping[int, int],
    animator_buffers: Mapping[int, T],
    resolve_sample: Callable[[T, int, int], CapturedTransform | None],
    fallback: CapturedTransform | None = None,
    relative: RelativeReadContext | None = None,
) -> AnimatorReadResult | None:
    """Successful finite selected-slot output; None preserves previous buffers.

    Buffer CapturedTransform matrices MUST be resolved native unit-scale TRS;
    fallback matrices are actual getter matrices. Matrix/pose consistency remains
    a caller precondition, not something these finite arithmetic tests establish.
    """
    team_id = _integer(team_ids[_index(slot, len(team_ids))], 32767)
    if not _valid(transform_valid):
        return None
    flag = _integer(flags[_index(slot, len(flags))], 255)
    if not flag & 0x10 or not flag & 1:
        return None
    team = teams[_index(team_id, len(teams))]
    if team is None:
        raise ValueError("Adapter requires source TeamData including selected team0")
    if _integer(team.flag, 2**64 - 1) & 0x80800:
        return None
    trace: list[Lookup] = []
    captured, used_buffer = fallback, False
    found, handler = _lookup(
        transform_to_handler, slot, "transformID2RWHandlerID", trace
    )
    if found:
        handler = _int32(cast(int, handler))
        found, animator = _lookup(
            team_to_animator, team_id, "teamId2AnimatorInstanceId", trace
        )
        if found:
            animator = _int32(cast(int, animator))
            found, samples = _lookup(
                animator_buffers, animator, "animatorID2RWHandler", trace
            )
            if found:
                if samples is None:
                    raise ValueError("Adapter requires resolved animator buffer record")
                captured = resolve_sample(samples, animator, handler)
                used_buffer = True
    if captured is None:
        raise ValueError("Adapter requires selected buffer/getter capture")
    p = _float3(captured.pose.world_position)
    q = _quaternion(captured.pose.world_rotation)
    matrix = _matrix(captured.local_to_world_matrix)
    local_p = _float3(captured.pose.local_position)
    local_q = _quaternion(captured.pose.local_rotation)
    unrotated = multiply_matrices(
        rotation_translation_matrix(quaternion_inverse(q), (0, 0, 0)), matrix
    )
    scale = _float3((unrotated[0][0], unrotated[1][1], unrotated[2][2]))
    scale_writes = (scale,)
    if used_buffer:
        scale = (1, 1, 1)
        scale_writes += (scale,)
    if _integer(team.use_relative_transform, 2**32 - 1):
        if relative is None:
            raise ValueError("Adapter requires resolved relative inverse context")
        inverse = _matrix(relative.inverse_matrix)
        inverse_q = _quaternion(relative.inverse_matrix_rotation)
        p = _point(RelativeWriteContext(inverse, inverse_q), p)
        q = multiply_quaternions(inverse_q, q)
        matrix = multiply_matrices(inverse, matrix)
    order = ("local_position", "local_rotation") + ("scale",) * len(scale_writes)
    order += ("world_position", "world_rotation", "local_to_world_matrix")
    return AnimatorReadResult(
        ReadTransformValues(_double3(p), q, local_p, local_q, scale, matrix, order),
        used_buffer,
        tuple(trace),
        scale_writes,
    )


def _sample_from_captures(
    samples: Sequence[CapturedTransform], animator: int, handler: int
) -> CapturedTransform | None:
    return samples[_index(handler, len(samples))]


def read_animator_buffer_values(
    *,
    slot: int,
    transform_valid: bool,
    flags: Sequence[int],
    team_ids: Sequence[int],
    teams: Sequence[ReadRestoreTeam | None],
    transform_to_handler: Mapping[int, int],
    team_to_animator: Mapping[int, int],
    animator_buffers: Mapping[int, Sequence[CapturedTransform]],
    fallback: CapturedTransform | None = None,
    relative: RelativeReadContext | None = None,
) -> AnimatorReadResult | None:
    """Legacy capture API, preserving selected-map and fallback behavior."""
    return _read_animator_values(
        slot=slot,
        transform_valid=transform_valid,
        flags=flags,
        team_ids=team_ids,
        teams=teams,
        transform_to_handler=transform_to_handler,
        team_to_animator=team_to_animator,
        animator_buffers=animator_buffers,
        resolve_sample=_sample_from_captures,
        fallback=fallback,
        relative=relative,
    )


def _sample_from_record(
    record: AnimatorRecord,
    animator: int,
    handler: int,
    native_unit_trs: NativeUnitTrsResolver | None,
) -> CapturedTransform:
    if native_unit_trs is None:
        raise ValueError("Adapter requires explicit native unit-scale TRS resolver")
    world_p = _float3(
        record.world_positions[_index(handler, len(record.world_positions))]
    )
    world_q = _quaternion(
        record.world_rotations[_index(handler, len(record.world_rotations))]
    )
    local_p = _float3(
        record.local_positions[_index(handler, len(record.local_positions))]
    )
    local_q = _quaternion(
        record.local_rotations[_index(handler, len(record.local_rotations))]
    )
    matrix = _matrix(native_unit_trs(animator, handler, world_p, world_q))
    # Necessary affine/translation contract, not proof of native rotational TRS
    # arithmetic. The resolver remains responsible for the selected quaternion.
    if matrix[3] != (*world_p, 1.0) or any(matrix[col][3] != 0 for col in range(3)):
        raise ValueError("Adapter requires matching affine native unit-scale TRS")
    return CapturedTransform(TransformPose(world_p, world_q, local_p, local_q), matrix)


def read_animator_record_values(
    *,
    slot: int,
    transform_valid: bool,
    flags: Sequence[int],
    team_ids: Sequence[int],
    teams: Sequence[ReadRestoreTeam | None],
    transform_to_handler: Mapping[int, int],
    team_to_animator: Mapping[int, int],
    animator_records: Mapping[int, AnimatorRecord],
    native_unit_trs: NativeUnitTrsResolver | None,
    fallback: CapturedTransform | None = None,
    relative: RelativeReadContext | None = None,
) -> AnimatorReadResult | None:
    """Read the SAME selected record used by binding rebuild and writeback.

    Resolves a sample only after all three maps succeed. Matrix resolver gets
    signed Animator ID, handler and the selected Single world p/q; local values
    come from the same record. No status reads, unused-record conversion, stale
    sample cache or identity-matrix default. Missing maps retain getter fallback.
    Callback/bounds/finite/affine validation is adapter policy, not native fault
    equivalence or proof that the supplied matrix uses native rotation math.
    """

    def resolve(
        record: AnimatorRecord, animator: int, handler: int
    ) -> CapturedTransform:
        return _sample_from_record(record, animator, handler, native_unit_trs)

    return _read_animator_values(
        slot=slot,
        transform_valid=transform_valid,
        flags=flags,
        team_ids=team_ids,
        teams=teams,
        transform_to_handler=transform_to_handler,
        team_to_animator=team_to_animator,
        animator_buffers=animator_records,
        resolve_sample=resolve,
        fallback=fallback,
        relative=relative,
    )
