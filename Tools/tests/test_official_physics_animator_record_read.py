"""Record-to-read dataflow fixtures, not a native TRS/Unity execution oracle."""

import sys
from dataclasses import replace
from pathlib import Path
from typing import Any, cast

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from official_physics_animator_buffer import read_animator_record_values
from official_physics_animator_lifecycle import (
    AnimatorBindingCapture,
    AnimatorObject,
    update_team_animator_data,
)
from official_physics_animator_write import (
    AnimatorRecord,
    AnimatorWriteTeam,
    write_animator_buffers,
)
from official_physics_publication import TransformBufferSnapshot
from official_physics_read_restore import (
    CapturedTransform,
    ReadRestoreTeam,
    RelativeReadContext,
)
from official_physics_setter import TransformPose

Q = (0, 0, 0, 1)
I = ((1, 0, 0, 0), (0, 1, 0, 0), (0, 0, 1, 0), (0, 0, 0, 1))
RECORD = AnimatorRecord(
    local_positions=((1, 2, 3), (4, 5, 6)),
    local_rotations=(Q, (0, 0, 0, 2)),
    world_positions=((10, 20, 30), (40, 50, 60)),
    world_rotations=(Q, Q),
    statuses=(0, 3),
)
FALLBACK_MATRIX = ((-2, 0, 0, 0), (0, 3, 0, 0), (0, 0, 4, 0), (70, 80, 90, 1))
FALLBACK = CapturedTransform(
    TransformPose((70, 80, 90), Q, (7, 8, 9), Q), FALLBACK_MATRIX
)


def identity_rotation_trs_fixture(animator, handler, position, rotation):
    # Synthetic resolved unit-rotation matrices; this does NOT implement native TRS.
    return I[:3] + ((*position, 1),)


def read(**kwargs):
    args = {
        "slot": 0,
        "transform_valid": True,
        "flags": (0x11,),
        "team_ids": (1,),
        "teams": (None, ReadRestoreTeam(0)),
        "transform_to_handler": {0: 1},
        "team_to_animator": {1: -42},
        "animator_records": {-42: RECORD},
        "native_unit_trs": identity_rotation_trs_fixture,
        "fallback": FALLBACK,
    }
    return read_animator_record_values(**(args | kwargs))


def selected_read(**kwargs):
    result = read(**kwargs)
    assert result is not None
    return result


def test_selected_record_handler_supplies_all_four_arrays_and_trs_inputs():
    observed = []

    def resolver(animator, handler, position, rotation):
        observed.append((animator, handler, position, rotation))
        return identity_rotation_trs_fixture(animator, handler, position, rotation)

    result = read(native_unit_trs=resolver, fallback=None)
    assert result is not None and result.used_buffer
    assert observed == [(-42, 1, (40, 50, 60), Q)]
    assert result.values.world_position == (40, 50, 60)
    assert result.values.local_position == (4, 5, 6)
    assert result.values.local_rotation == (0, 0, 0, 2)
    assert result.values.local_to_world_matrix[3] == (40, 50, 60, 1)


@pytest.mark.parametrize(
    "missing", ["transform_to_handler", "team_to_animator", "animator_records"]
)
def test_missing_map_falls_back_without_calling_trs_or_reading_later_maps(missing):
    names = ("transform_to_handler", "team_to_animator", "animator_records")
    updates = {missing: {}, "native_unit_trs": None}
    for name in names[names.index(missing) + 1 :]:
        updates[name] = None
    result = read(**updates)
    assert result is not None and not result.used_buffer
    assert result.values.world_position == (70, 80, 90)
    assert result.values.scale == (-2, 3, 4)


@pytest.mark.parametrize(
    "kwargs",
    [
        {"transform_valid": False},
        {"flags": (1,)},
        {"flags": (0x10,)},
        {"teams": (None, ReadRestoreTeam(0x800))},
    ],
)
def test_unselected_routes_do_not_resolve_records_or_trs(kwargs):
    assert (
        read(
            **(
                kwargs
                | {"animator_records": None, "native_unit_trs": None, "fallback": None}
            )
        )
        is None
    )


def test_selected_record_needs_explicit_trs_resolver_not_identity_default():
    with pytest.raises(ValueError, match="TRS resolver"):
        read(native_unit_trs=None)


@pytest.mark.parametrize(
    "matrix",
    [I, I[:3] + ((40, 50, 60, 2),), ((1, 0, 0, 1),) + I[1:3] + ((40, 50, 60, 1),)],
)
def test_trs_callback_wrong_translation_or_affine_lanes_is_rejected(matrix):
    with pytest.raises(ValueError, match="unit-scale TRS"):
        read(native_unit_trs=lambda *args: matrix)


@pytest.mark.parametrize(
    "field",
    ["local_positions", "local_rotations", "world_positions", "world_rotations"],
)
def test_handler_must_exist_in_each_selected_array_not_become_map_miss(field):
    with pytest.raises(ValueError):
        read(animator_records={-42: replace(RECORD, **{field: ()})})


class UnreadStatuses:
    def __len__(self):
        raise AssertionError("read job must not inspect status array")

    def __getitem__(self, index):
        raise AssertionError("read job must not inspect status values")


def test_reader_does_not_gate_on_or_read_writer_statuses():
    record = replace(RECORD, statuses=cast(Any, UnreadStatuses()))
    assert selected_read(animator_records={-42: record}).used_buffer


def test_unselected_record_and_handler_payloads_stay_unread():
    record = replace(
        RECORD, world_positions=(cast(Any, object()), RECORD.world_positions[1])
    )
    assert selected_read(
        animator_records={-42: record, 100: cast(Any, object())}
    ).values.world_position == (40, 50, 60)


def test_relative_inverse_is_applied_after_record_trs_and_retains_local_values():
    result = selected_read(
        teams=(None, ReadRestoreTeam(0, 1)),
        relative=RelativeReadContext(I[:3] + ((-1, -2, -3, 1),), Q),
    )
    assert result.values.world_position == (39, 48, 57)
    assert result.values.local_position == (4, 5, 6)
    assert result.values.local_to_world_matrix[3] == (39, 48, 57, 1)


def test_world_values_are_narrowed_before_callback_without_normalizing_quaternion():
    observed = []
    record = replace(
        RECORD,
        world_positions=((16777217, 0, -0.0),),
        world_rotations=((0, 0, 0, 2),),
        local_positions=((0, 0, 0),),
        local_rotations=(Q,),
        statuses=(),
    )

    def resolver(animator, handler, p, q):
        observed.append((p, q))
        return identity_rotation_trs_fixture(animator, handler, p, q)

    result = selected_read(
        transform_to_handler={0: 0},
        animator_records={-42: record},
        native_unit_trs=resolver,
    )
    assert observed == [((16777216, 0, -0.0), (0, 0, 0, 2))]
    assert result.values.world_rotation == (0, 0, 0, 2)


def test_binding_reorder_drives_reader_and_writer_without_manually_remapping_records():
    rebuilt = update_team_animator_data(
        dirty_teams={1},
        temp_animators=set(),
        team_to_animator_instance={1: -42},
        team_to_animator={1: AnimatorObject(101, -42)},
        team_ids=(1, 1),
        transforms=(1001, 1002),
        animator_order=(-42,),
        binding_captures={-42: AnimatorBindingCapture(RECORD, (1, 0))},
        animator_records={},
        transform_to_handler={},
    )
    assert rebuilt.transform_to_handler == {1: 0, 0: 1}
    before = selected_read(
        transform_to_handler=rebuilt.transform_to_handler,
        animator_records=rebuilt.animator_records,
    )
    assert before.values.local_position == (4, 5, 6)
    written = write_animator_buffers(
        flags=(0x14, 0x14),
        team_ids=(1, 1),
        teams=(None, AnimatorWriteTeam(0, 1, 1)),
        buffers=TransformBufferSnapshot(
            ((0, 0, 0),) * 2, (Q,) * 2, ((100, 1, 2), (200, 3, 4)), (Q,) * 2
        ),
        transform_to_handler=rebuilt.transform_to_handler,
        team_to_animator={1: -42},
        animator_records=rebuilt.animator_records,
    )
    after = selected_read(
        transform_to_handler=rebuilt.transform_to_handler,
        animator_records=written.records,
    )
    assert written.records[-42].local_positions == ((200, 3, 4), (100, 1, 2))
    assert after.values.local_position == (100, 1, 2)
    assert rebuilt.animator_records[-42] == RECORD  # Prior snapshot remains immutable.


def test_dropped_duplicate_slot_uses_getter_while_last_slot_uses_same_record():
    rebuilt = update_team_animator_data(
        dirty_teams={1},
        temp_animators=set(),
        team_to_animator_instance={1: -42},
        team_to_animator={1: AnimatorObject(101, -42)},
        team_ids=(1, 1),
        transforms=(1001, 1001),
        animator_order=(-42,),
        binding_captures={
            -42: AnimatorBindingCapture(
                replace(
                    RECORD,
                    local_positions=RECORD.local_positions[:1],
                    local_rotations=(Q,),
                    world_positions=RECORD.world_positions[:1],
                    world_rotations=(Q,),
                    statuses=(0,),
                ),
                (0,),
            )
        },
        animator_records={},
        transform_to_handler={},
    )
    zero = selected_read(
        transform_to_handler=rebuilt.transform_to_handler,
        animator_records=rebuilt.animator_records,
        native_unit_trs=None,
    )
    one = selected_read(
        slot=1,
        flags=(0x11, 0x11),
        team_ids=(1, 1),
        transform_to_handler=rebuilt.transform_to_handler,
        animator_records=rebuilt.animator_records,
    )
    assert not zero.used_buffer and zero.values.world_position == (70, 80, 90)
    assert one.used_buffer and one.values.world_position == (10, 20, 30)


def test_world_rotation_only_write_is_read_with_retained_position_and_new_rotation():
    half_turn_y = (0, 1, 0, 0)
    written = write_animator_buffers(
        flags=(0x12,),
        team_ids=(1,),
        teams=(None, AnimatorWriteTeam(0, 1, 1)),
        buffers=TransformBufferSnapshot(
            ((123, 456, 789),), (half_turn_y,), ((0, 0, 0),), (Q,)
        ),
        transform_to_handler={0: 0},
        team_to_animator={1: -42},
        animator_records={-42: RECORD},
    )
    observed = []

    def resolver(animator, handler, p, q):
        observed.append((p, q))
        # Explicit resolved half-turn fixture, not a general native TRS implementation.
        return ((-1, 0, 0, 0), (0, 1, 0, 0), (0, 0, -1, 0), (*p, 1))

    result = selected_read(
        transform_to_handler={0: 0},
        animator_records=written.records,
        native_unit_trs=resolver,
    )
    assert written.records[-42].statuses[0] == 2
    assert observed == [((10, 20, 30), half_turn_y)]
    assert result.values.world_position == (10, 20, 30)
    assert result.values.world_rotation == half_turn_y
    assert result.values.local_position == (1, 2, 3)
    assert result.scale_writes == ((1, 1, 1), (1, 1, 1))


def test_negative_selected_handler_does_not_become_a_getter_fallback():
    with pytest.raises(ValueError):
        read(transform_to_handler={0: -1})


def test_found_null_record_is_not_a_missing_map_fallback():
    with pytest.raises(ValueError, match="record"):
        read(animator_records={-42: None})


def test_selected_trs_failure_propagates_without_using_fallback():
    def resolver(*args):
        raise RuntimeError("TRS capture unavailable")

    with pytest.raises(RuntimeError, match="TRS capture unavailable"):
        read(native_unit_trs=resolver)
