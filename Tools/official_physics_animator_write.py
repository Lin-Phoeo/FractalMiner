"""Finite WriteAnimatorBufferDataJob._Do semantics, not a live Animator job.

The source loop first reads TeamData/culling, then performs three map lookups:
global transform slot -> handler index -> team Animator ID -> Animator RW record.
Missing maps advance one slot.  Culling, a disabled slot, Team bit61, and a
non-positive effective weight end the WHOLE job.  World bit2 has priority over
local bit4.  World rotation marks status2; optional world position (Team 0x2000)
then marks status3.  Local position/rotation marks status1.

Weight is Single(clothSimulateWeight * clothLodFadeWeight).  Fractional writes
blend from the existing Animator record to the solver buffer.  Relative world
writes use a caller-resolved forward LocalToWorld matrix: matrixRotation * q
and matrix * p.  Matrix construction, native maps, record lifecycle, scheduling,
Unity Animator handles and complete physics remain separate/unported boundaries.

Immutable tuples model completed writes without NativeArray aliasing.  Adapter
range/shape/non-finite rejection is stricter than native fault behavior and is
not claimed as exception equivalence.  NaN source positions preserve the
observed per-slot skip before any record write.
"""

from __future__ import annotations

import math
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, replace
from typing import Literal, TypeVar, cast

from official_physics_angle_baseline import _index, _integer
from official_physics_angle_cache import _quaternion, multiply_quaternions
from official_physics_angles import Quaternion, _float3
from official_physics_constraints import Vector3, _single
from official_physics_publication import TransformBufferSnapshot
from official_physics_registration import _int32
from official_physics_setter import (
    RelativeWriteContext,
    _lerp,
    _point,
    _relative,
    interpolate_rotation,
)
from official_physics_writeback import Double3, _double3

Lookup = tuple[str, int, bool]
Control = Literal["continue", "written", "return_job"]
T = TypeVar("T")


@dataclass(frozen=True)
class AnimatorWriteTeam:
    flag: int
    cloth_simulate_weight: float
    cloth_lod_fade_weight: float
    use_relative_transform: int = 0


@dataclass(frozen=True)
class AnimatorRecord:
    local_positions: tuple[Vector3, ...]
    local_rotations: tuple[Quaternion, ...]
    world_positions: tuple[Vector3, ...]
    world_rotations: tuple[Quaternion, ...]
    statuses: tuple[int, ...]


@dataclass(frozen=True)
class AnimatorWriteStep:
    slot: int
    control: Control
    reason: str
    lookups: tuple[Lookup, ...] = ()
    animator_id: int | None = None
    handler: int | None = None
    status: int | None = None
    write_order: tuple[str, ...] = ()


@dataclass(frozen=True)
class AnimatorWriteResult:
    records: dict[int, AnimatorRecord]
    steps: tuple[AnimatorWriteStep, ...]
    terminated_at: int | None


def _lookup(
    mapping: Mapping[int, T] | None,
    key: int,
    name: str,
    trace: list[Lookup],
) -> tuple[bool, T | None]:
    if mapping is None:
        raise ValueError(f"Adapter requires {name} map on selected lookup")
    found = key in mapping
    trace.append((name, key, found))
    return (True, mapping[key]) if found else (False, None)


def _team(
    teams: Sequence[AnimatorWriteTeam | None] | None, team_id: int
) -> AnimatorWriteTeam:
    if teams is None:
        raise ValueError("Adapter requires source TeamData array")
    team = teams[_index(team_id, len(teams))]
    if team is None:
        raise ValueError("Adapter requires source TeamData including selected team0")
    return team


def _required_buffers(
    buffers: TransformBufferSnapshot | None,
) -> TransformBufferSnapshot:
    if buffers is None:
        raise ValueError("Adapter requires solver buffers on selected write route")
    return buffers


def _has_nan(values: Sequence[float], expected: int) -> bool:
    if len(values) != expected:
        raise ValueError(f"Adapter requires {expected} source position lanes")
    for value in values:
        if isinstance(value, bool) or not isinstance(value, (int, float)):
            raise TypeError("Adapter requires numeric source position lanes")
        if math.isnan(float(value)):
            return True
    return False


def _handler(record: AnimatorRecord, handler: int) -> int:
    handler = _int32(handler)
    lengths = (
        len(record.local_positions),
        len(record.local_rotations),
        len(record.world_positions),
        len(record.world_rotations),
        len(record.statuses),
    )
    if handler < 0 or any(handler >= length for length in lengths):
        raise ValueError("Adapter requires handler in every Animator record array")
    return handler


def _replace_at(values: tuple[T, ...], index: int, value: T) -> tuple[T, ...]:
    return values[:index] + (value,) + values[index + 1 :]


def _relative_for(
    team_id: int,
    relative_gate: int,
    relatives: Mapping[int, RelativeWriteContext] | None,
) -> RelativeWriteContext | None:
    if not _integer(relative_gate, 2**32 - 1):
        return None
    if relatives is None or team_id not in relatives:
        raise ValueError("Adapter requires resolved source relative context")
    return _relative(relatives[team_id])


def _step(
    slot: int,
    control: Control,
    reason: str,
    trace: list[Lookup] | None = None,
    *,
    animator_id: int | None = None,
    handler: int | None = None,
    status: int | None = None,
    write_order: tuple[str, ...] = (),
) -> AnimatorWriteStep:
    return AnimatorWriteStep(
        slot,
        control,
        reason,
        tuple(trace or ()),
        animator_id,
        handler,
        status,
        write_order,
    )


def write_animator_buffers(
    *,
    flags: Sequence[int] | None,
    team_ids: Sequence[int],
    teams: Sequence[AnimatorWriteTeam | None] | None,
    buffers: TransformBufferSnapshot | None,
    transform_to_handler: Mapping[int, int] | None,
    team_to_animator: Mapping[int, int] | None,
    animator_records: Mapping[int, AnimatorRecord],
    relatives: Mapping[int, RelativeWriteContext] | None = None,
) -> AnimatorWriteResult:
    """Evaluate the finite source loop over supplied slots and immutable records.

    `terminated_at` distinguishes native whole-job exits from ordinary per-slot
    advances.  The returned dict is a new mapping; selected records are replaced
    rather than mutating caller-owned tuples.
    """
    records = dict(animator_records)
    steps: list[AnimatorWriteStep] = []
    for slot in range(len(team_ids)):
        team_id = _integer(team_ids[slot], 32767)
        team = _team(teams, team_id)
        team_flag = _integer(team.flag, 2**64 - 1)
        if team_flag & 0x80800:
            steps.append(_step(slot, "return_job", "culling"))
            return AnimatorWriteResult(records, tuple(steps), slot)

        # The source copies TeamData and multiplies these fields before its
        # first map lookup, but does not branch on the result until afterward.
        weight = _single(
            _single(team.cloth_simulate_weight) * _single(team.cloth_lod_fade_weight)
        )

        trace: list[Lookup] = []
        found, handler_value = _lookup(
            transform_to_handler,
            slot,
            "transformID2RWHandlerID",
            trace,
        )
        if not found:
            steps.append(_step(slot, "continue", "missing_transform_handler", trace))
            continue
        handler = _int32(cast(int, handler_value))

        found, animator_value = _lookup(
            team_to_animator,
            team_id,
            "teamId2AnimatorInstanceId",
            trace,
        )
        if not found:
            steps.append(_step(slot, "continue", "missing_team_animator", trace))
            continue
        animator_id = _int32(cast(int, animator_value))

        found, record_value = _lookup(
            records,
            animator_id,
            "animatorID2RWHandler",
            trace,
        )
        if not found:
            steps.append(_step(slot, "continue", "missing_animator_record", trace))
            continue
        if record_value is None:
            raise ValueError("Adapter requires resolved Animator record")
        record = cast(AnimatorRecord, record_value)
        handler = _handler(record, handler)

        if flags is None:
            raise ValueError("Adapter requires flag array after successful lookups")
        flag = _integer(flags[_index(slot, len(flags))], 255)
        if not flag & 0x10:
            steps.append(
                _step(
                    slot,
                    "return_job",
                    "disabled",
                    trace,
                    animator_id=animator_id,
                    handler=handler,
                )
            )
            return AnimatorWriteResult(records, tuple(steps), slot)
        if team_flag & (1 << 61):
            steps.append(
                _step(
                    slot,
                    "return_job",
                    "team_bit61",
                    trace,
                    animator_id=animator_id,
                    handler=handler,
                )
            )
            return AnimatorWriteResult(records, tuple(steps), slot)
        if weight <= 0:
            steps.append(
                _step(
                    slot,
                    "return_job",
                    "nonpositive_weight",
                    trace,
                    animator_id=animator_id,
                    handler=handler,
                )
            )
            return AnimatorWriteResult(records, tuple(steps), slot)

        if flag & 2:
            source = _required_buffers(buffers)
            raw_position = source.world_positions[
                _index(slot, len(source.world_positions))
            ]
            if _has_nan(raw_position, 3):
                steps.append(
                    _step(
                        slot,
                        "continue",
                        "invalid_source_position",
                        trace,
                        animator_id=animator_id,
                        handler=handler,
                    )
                )
                continue
            position: Double3 = _double3(raw_position)
            rotation = _quaternion(
                source.world_rotations[_index(slot, len(source.world_rotations))]
            )
            if weight < 1:
                rotation = interpolate_rotation(
                    _quaternion(record.world_rotations[handler]), rotation, weight
                )
            relative = _relative_for(team_id, team.use_relative_transform, relatives)
            if relative is not None:
                rotation = multiply_quaternions(relative.matrix_rotation, rotation)
            updated = replace(
                record,
                world_rotations=_replace_at(record.world_rotations, handler, rotation),
                statuses=_replace_at(record.statuses, handler, 2),
            )
            order = ("world_rotation", "status_2")
            status = 2
            if team_flag & 0x2000:
                world_position = _float3(position)
                if weight < 1:
                    world_position = _lerp(
                        _float3(record.world_positions[handler]),
                        world_position,
                        weight,
                    )
                if relative is not None:
                    world_position = _point(relative, world_position)
                updated = replace(
                    updated,
                    world_positions=_replace_at(
                        updated.world_positions, handler, world_position
                    ),
                    statuses=_replace_at(updated.statuses, handler, 3),
                )
                order += ("world_position", "status_3")
                status = 3
            records[animator_id] = updated
            steps.append(
                _step(
                    slot,
                    "written",
                    "world",
                    trace,
                    animator_id=animator_id,
                    handler=handler,
                    status=status,
                    write_order=order,
                )
            )
            continue

        if flag & 4:
            source = _required_buffers(buffers)
            raw_position = source.local_positions[
                _index(slot, len(source.local_positions))
            ]
            if _has_nan(raw_position, 3):
                steps.append(
                    _step(
                        slot,
                        "continue",
                        "invalid_source_position",
                        trace,
                        animator_id=animator_id,
                        handler=handler,
                    )
                )
                continue
            position = _float3(raw_position)
            rotation = _quaternion(
                source.local_rotations[_index(slot, len(source.local_rotations))]
            )
            if weight < 1:
                position = _lerp(
                    _float3(record.local_positions[handler]), position, weight
                )
                rotation = interpolate_rotation(
                    _quaternion(record.local_rotations[handler]), rotation, weight
                )
            updated = replace(
                record,
                local_positions=_replace_at(record.local_positions, handler, position),
                local_rotations=_replace_at(record.local_rotations, handler, rotation),
                statuses=_replace_at(record.statuses, handler, 1),
            )
            records[animator_id] = updated
            steps.append(
                _step(
                    slot,
                    "written",
                    "local",
                    trace,
                    animator_id=animator_id,
                    handler=handler,
                    status=1,
                    write_order=("local_position", "local_rotation", "status_1"),
                )
            )
            continue

        steps.append(
            _step(
                slot,
                "continue",
                "no_write_bits",
                trace,
                animator_id=animator_id,
                handler=handler,
            )
        )
    return AnimatorWriteResult(records, tuple(steps), None)
