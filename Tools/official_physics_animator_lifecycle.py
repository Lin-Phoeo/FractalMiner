"""Finite TeamManager.UpdateTeamAnimatorData lifecycle, not Unity bindings.

369500/0x5a2283c consumes ExNativeArray<Int16> team IDs and a
TransformAccessArray.  A non-empty dirty-team HashSet is mapped to a unique
temporary HashSet of Animator instance IDs.  For each Animator ID, every team
sharing that ID is selected, transforms are deduplicated in global-slot order,
and a Dictionary<uniqueTransformIndex,List<globalSlot>> is built. The captured
duplicate branch tests ContainsKey using the current unique-list Count, then
writes using IndexOf. Since Count is absent in this freshly built dictionary,
each duplicate replaces its group with the latest slot; prior slots are dropped.

The first selected non-null Animator supplies the binding target; a matching
Transform whose team has a null Animator causes lookup to retry later. Existing
RW records cause DisableClothBindings, then CreateClothBindings receives the
unique Transform array, the record is replaced, and EnableClothBindings runs.
The returned record's UInt16 transform-index order maps each handler back to the
retained global slots. Missing returned indices log errors; stale map keys are
not cleared by this method.  Dirty and temporary HashSets clear only after a
non-empty dirty pass; an empty dirty set returns immediately.

This adapter requires caller-resolved Transform identity, Animator objects,
native HashSet iteration order, and CreateClothBindings captures.  It does not
construct Unity AnimationTransformRWBufferHandle, call Animator, reproduce
native container allocation/lifetime, execute jobs, or complete scheduling.
Immutable copies avoid side effects and do not model source partial writes on
exceptions.  Range/shape rejection is adapter policy, not native equivalence.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from collections.abc import Set as AbstractSet
from dataclasses import dataclass
from typing import Literal

from official_physics_animator_write import AnimatorRecord
from official_physics_registration import _int32


@dataclass(frozen=True)
class AnimatorObject:
    object_identity: int
    instance_id: int


@dataclass(frozen=True)
class AnimatorBindingCapture:
    record: AnimatorRecord
    # For each created handler, index into the unique Transform array supplied
    # to CreateClothBindings. This is the UInt16 array read at handle offset8.
    source_transform_indices: tuple[int, ...]


@dataclass(frozen=True)
class BindingOperation:
    action: Literal["disable", "create", "enable"]
    animator_object_identity: int
    animator_instance_id: int
    unique_transforms: tuple[int, ...] = ()


@dataclass(frozen=True)
class AnimatorBindingPlan:
    mapped_animator_id: int
    team_ids: frozenset[int]
    animator: AnimatorObject | None
    unique_transforms: tuple[int, ...]
    source_slots_by_unique_index: tuple[tuple[int, ...], ...]


@dataclass(frozen=True)
class AnimatorLifecycleResult:
    animator_records: dict[int, AnimatorRecord]
    transform_to_handler: dict[int, int]
    dirty_teams: frozenset[int]
    temp_animators: frozenset[int]
    plans: tuple[AnimatorBindingPlan, ...]
    operations: tuple[BindingOperation, ...]
    # (actual Animator instance ID, handler index, missing unique Transform index)
    errors: tuple[tuple[int, int, int], ...]


def _int16(value: int) -> int:
    value = _int32(value)
    if not -32768 <= value <= 32767:
        raise ValueError("Adapter requires signed Int16 Team ID")
    return value


def _record_count(record: AnimatorRecord) -> int:
    lengths = {
        len(record.local_positions),
        len(record.local_rotations),
        len(record.world_positions),
        len(record.world_rotations),
        len(record.statuses),
    }
    if len(lengths) != 1:
        raise ValueError("Adapter requires equal Animator record array lengths")
    count = next(iter(lengths))
    if count > 65535:
        raise ValueError("Adapter requires UInt16 Animator binding count")
    return count


def _capture(
    captures: Mapping[int, AnimatorBindingCapture] | None, instance_id: int
) -> AnimatorBindingCapture:
    if captures is None or instance_id not in captures:
        raise ValueError("Adapter requires caller-resolved CreateClothBindings capture")
    capture = captures[instance_id]
    count = _record_count(capture.record)
    if count != len(capture.source_transform_indices):
        raise ValueError("Adapter binding count must match every record array")
    for value in capture.source_transform_indices:
        value = _int32(value)
        if not 0 <= value <= 65535:
            raise ValueError("Adapter requires UInt16 binding transform index")
    return capture


def _animator(
    mapping: Mapping[int, AnimatorObject | None] | None, team_id: int
) -> AnimatorObject | None:
    if mapping is None or team_id not in mapping:
        raise ValueError("Adapter requires selected team-to-Animator entry")
    value = mapping[team_id]
    if value is None:
        return None
    return AnimatorObject(_int32(value.object_identity), _int32(value.instance_id))


def update_team_animator_data(
    *,
    dirty_teams: AbstractSet[int],
    temp_animators: AbstractSet[int],
    team_to_animator_instance: Mapping[int, int] | None,
    team_to_animator: Mapping[int, AnimatorObject | None] | None,
    team_ids: Sequence[int] | None,
    transforms: Sequence[int | None] | None,
    animator_order: Sequence[int] | None,
    binding_captures: Mapping[int, AnimatorBindingCapture] | None,
    animator_records: Mapping[int, AnimatorRecord],
    transform_to_handler: Mapping[int, int],
) -> AnimatorLifecycleResult:
    """Apply one completed finite dirty-Animator rebuild.

    `animator_order` is the caller-observed enumeration order of the temporary
    HashSet.  It must contain exactly the unique Animator IDs collected from
    dirty teams, preventing Python ordering from being mistaken for native
    HashSet order.
    """
    dirty = frozenset(_int32(value) for value in dirty_teams)
    original_temp = frozenset(_int32(value) for value in temp_animators)
    records = dict(animator_records)
    handler_map = dict(transform_to_handler)
    if not dirty:
        return AnimatorLifecycleResult(
            records, handler_map, dirty, original_temp, (), (), ()
        )

    if team_to_animator_instance is None:
        raise ValueError("Adapter requires team-to-Animator-instance map")
    temporary = {
        _int32(team_to_animator_instance[team])
        for team in dirty
        if team in team_to_animator_instance
    }
    if animator_order is None:
        raise ValueError("Adapter requires caller-resolved animator order")
    order = tuple(_int32(value) for value in animator_order)
    if len(order) != len(set(order)) or set(order) != temporary:
        raise ValueError("Adapter animator order must match unique temporary IDs")

    plans: list[AnimatorBindingPlan] = []
    operations: list[BindingOperation] = []
    errors: list[tuple[int, int, int]] = []
    for mapped_animator_id in order:
        selected_teams = frozenset(
            _int32(team)
            for team, animator_id in team_to_animator_instance.items()
            if _int32(animator_id) == mapped_animator_id
        )
        unique_transforms: list[int] = []
        slots_by_unique: list[list[int]] = []
        transform_index: dict[int, int] = {}
        selected_animator: AnimatorObject | None = None

        if selected_teams:
            if team_ids is None or transforms is None:
                raise ValueError("Adapter requires team/Transform arrays")
            if len(team_ids) != len(transforms):
                raise ValueError("Adapter requires parallel team/Transform arrays")
            for slot, (raw_team_id, raw_transform) in enumerate(
                zip(team_ids, transforms, strict=True)
            ):
                team_id = _int16(raw_team_id)
                if team_id not in selected_teams or raw_transform is None:
                    continue
                transform = _int32(raw_transform)
                unique_index = transform_index.get(transform)
                if unique_index is None:
                    unique_index = len(unique_transforms)
                    transform_index[transform] = unique_index
                    unique_transforms.append(transform)
                    slots_by_unique.append([slot])
                else:
                    # 0x5a22fa8 checks Count, but 0x5a23000 stores at IndexOf.
                    # Keys are always below Count, so this source branch always
                    # creates a replacement List<int>{slot} for the duplicate.
                    slots_by_unique[unique_index] = [slot]
                if selected_animator is None:
                    selected_animator = _animator(team_to_animator, team_id)

        plan = AnimatorBindingPlan(
            mapped_animator_id,
            selected_teams,
            selected_animator,
            tuple(unique_transforms),
            tuple(tuple(slots) for slots in slots_by_unique),
        )
        plans.append(plan)
        if selected_animator is None:
            continue

        actual_instance_id = selected_animator.instance_id
        if actual_instance_id in records:
            operations.append(
                BindingOperation(
                    "disable",
                    selected_animator.object_identity,
                    actual_instance_id,
                )
            )
        capture = _capture(binding_captures, actual_instance_id)
        operations.append(
            BindingOperation(
                "create",
                selected_animator.object_identity,
                actual_instance_id,
                tuple(unique_transforms),
            )
        )
        records[actual_instance_id] = capture.record
        operations.append(
            BindingOperation(
                "enable",
                selected_animator.object_identity,
                actual_instance_id,
            )
        )
        for handler, raw_unique_index in enumerate(capture.source_transform_indices):
            unique_index = _int32(raw_unique_index)
            if unique_index not in range(len(slots_by_unique)):
                errors.append((actual_instance_id, handler, unique_index))
                continue
            for global_slot in slots_by_unique[unique_index]:
                handler_map[global_slot] = handler

    return AnimatorLifecycleResult(
        records,
        handler_map,
        frozenset(),
        frozenset(),
        tuple(plans),
        tuple(operations),
        tuple(errors),
    )
