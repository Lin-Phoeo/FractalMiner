"""Finite UpdateTeamAnimatorData lifecycle tests; no Unity Animator calls."""

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from official_physics_animator_lifecycle import (
    AnimatorBindingCapture,
    AnimatorObject,
    update_team_animator_data,
)
from official_physics_animator_write import AnimatorRecord

Q = (0, 0, 0, 1)


def record(count, marker=0):
    return AnimatorRecord(
        local_positions=tuple((marker + i, 0, 0) for i in range(count)),
        local_rotations=(Q,) * count,
        world_positions=tuple((0, marker + i, 0) for i in range(count)),
        world_rotations=(Q,) * count,
        statuses=(0,) * count,
    )


CAPTURE_10 = AnimatorBindingCapture(record(2, 10), (1, 0))


def run(**kwargs):
    values = {
        "dirty_teams": {1, 2},
        "temp_animators": {999},
        "team_to_animator_instance": {1: 10, 2: 10, 3: 20},
        "team_to_animator": {1: AnimatorObject(101, 10), 2: AnimatorObject(101, 10)},
        "team_ids": (1, 2, 1, 3),
        "transforms": (1001, 1002, 1001, 1003),
        "animator_order": (10,),
        "binding_captures": {10: CAPTURE_10},
        "animator_records": {},
        "transform_to_handler": {99: 7},
    }
    return update_team_animator_data(**(values | kwargs))


def test_dirty_empty_returns_without_clearing_existing_temp_or_reading_inputs():
    result = run(
        dirty_teams=set(),
        temp_animators={88},
        team_to_animator_instance=None,
        team_to_animator=None,
        team_ids=None,
        transforms=None,
        animator_order=None,
        binding_captures=None,
        animator_records={5: record(1)},
        transform_to_handler={9: 3},
    )
    assert result.temp_animators == frozenset({88})
    assert result.dirty_teams == frozenset()
    assert result.animator_records == {5: record(1)}
    assert result.transform_to_handler == {9: 3}
    assert result.operations == ()


def test_duplicate_transform_replaces_previous_slot_group_and_binding_reorder():
    result = run()
    assert result.plans[0].mapped_animator_id == 10
    assert result.plans[0].animator == AnimatorObject(101, 10)
    assert result.plans[0].unique_transforms == (1001, 1002)
    assert result.plans[0].source_slots_by_unique_index == ((2,), (1,))
    assert result.transform_to_handler == {99: 7, 1: 0, 2: 1}
    assert result.animator_records[10] == CAPTURE_10.record
    assert result.dirty_teams == frozenset()
    assert result.temp_animators == frozenset()


def test_each_duplicate_replaces_group_with_last_global_slot_only():
    result = run(
        team_ids=(1, 2, 1),
        transforms=(1001, 1001, 1001),
        binding_captures={10: AnimatorBindingCapture(record(1), (0,))},
        transform_to_handler={0: 7, 1: 8},
    )
    assert result.plans[0].unique_transforms == (1001,)
    assert result.plans[0].source_slots_by_unique_index == ((2,),)
    # The rebuild does not clear dropped slots: prior handlers remain stale.
    assert result.transform_to_handler == {0: 7, 1: 8, 2: 0}


def test_all_teams_sharing_dirty_animator_are_rebound_not_only_dirty_teams():
    result = run(
        dirty_teams={1},
        team_to_animator_instance={1: 10, 4: 10},
        team_to_animator={1: AnimatorObject(101, 10), 4: AnimatorObject(101, 10)},
        team_ids=(4, 1),
        transforms=(4004, 1001),
        binding_captures={10: AnimatorBindingCapture(record(2), (0, 1))},
    )
    assert result.plans[0].team_ids == frozenset({1, 4})
    assert result.plans[0].unique_transforms == (4004, 1001)
    assert result.transform_to_handler[0] == 0
    assert result.transform_to_handler[1] == 1


def test_existing_record_disables_before_create_replace_and_enable():
    old = record(1, 99)
    result = run(animator_records={10: old})
    assert [(op.action, op.animator_instance_id) for op in result.operations] == [
        ("disable", 10),
        ("create", 10),
        ("enable", 10),
    ]
    assert result.animator_records[10] != old


def test_missing_old_record_skips_disable_but_still_creates_and_enables():
    result = run()
    assert [op.action for op in result.operations] == ["create", "enable"]


def test_null_transforms_are_skipped_before_animator_lookup_and_capture():
    result = run(
        team_ids=(1,),
        transforms=(None,),
        team_to_animator=None,
        binding_captures=None,
    )
    assert result.plans[0].animator is None
    assert result.plans[0].unique_transforms == ()
    assert result.operations == ()


def test_first_matching_transform_selects_animator_object_once():
    first = AnimatorObject(201, 77)
    second = AnimatorObject(202, 88)
    capture = AnimatorBindingCapture(record(2), (0, 1))
    result = run(
        team_to_animator={1: second, 2: first},
        team_ids=(2, 1, 2, 3),
        binding_captures={77: capture},
        animator_records={},
    )
    assert result.plans[0].animator == first
    assert 77 in result.animator_records
    assert 10 not in result.animator_records


def test_null_selected_animator_retries_lookup_on_next_matching_transform():
    result = run(
        team_to_animator={1: None, 2: AnimatorObject(202, 10)},
        team_ids=(1, 2),
        transforms=(1001, 1002),
        binding_captures={10: AnimatorBindingCapture(record(2), (0, 1))},
    )
    assert result.plans[0].animator == AnimatorObject(202, 10)
    assert [op.animator_object_identity for op in result.operations] == [202, 202]


def test_missing_binding_source_index_logs_error_and_continues_handlers():
    capture = AnimatorBindingCapture(record(3), (1, 9, 0))
    result = run(binding_captures={10: capture})
    assert result.errors == ((10, 1, 9),)
    assert result.transform_to_handler[1] == 0
    assert 0 not in result.transform_to_handler
    assert result.transform_to_handler[2] == 2


def test_repeated_binding_source_index_later_handler_overwrites_map_values():
    capture = AnimatorBindingCapture(record(2), (0, 0))
    result = run(binding_captures={10: capture})
    assert 0 not in result.transform_to_handler
    assert result.transform_to_handler[2] == 1


def test_dirty_team_without_instance_mapping_does_not_create_temp_animator():
    result = run(
        dirty_teams={8},
        team_to_animator_instance={},
        animator_order=(),
        team_to_animator=None,
        team_ids=None,
        transforms=None,
        binding_captures=None,
    )
    assert result.plans == ()
    assert result.temp_animators == frozenset()


@pytest.mark.parametrize("order", [(10, 10), (), (20,), (10, 20)])
def test_caller_resolved_hashset_order_must_match_unique_temp_ids(order):
    with pytest.raises(ValueError, match="animator order"):
        run(animator_order=order)


def test_missing_team_animator_entry_raises_only_for_selected_nonnull_transform():
    with pytest.raises(ValueError, match="team-to-Animator"):
        run(team_to_animator={2: AnimatorObject(101, 10)})
    assert run(transforms=(None, 1002, None, 1003)).plans[0].animator is not None


def test_stale_transform_handler_entries_are_preserved_not_implicitly_cleared():
    result = run(transform_to_handler={0: 8, 50: 9})
    assert result.transform_to_handler[50] == 9
    assert result.transform_to_handler[0] == 8


def test_nonempty_dirty_set_clears_temp_even_when_no_animator_is_found():
    result = run(
        dirty_teams={8},
        temp_animators={123},
        team_to_animator_instance={},
        animator_order=(),
        team_to_animator=None,
        team_ids=None,
        transforms=None,
        binding_captures=None,
    )
    assert result.temp_animators == frozenset()


def test_binding_capture_count_must_match_every_record_array():
    bad = AnimatorBindingCapture(record(1), (0, 1))
    with pytest.raises(ValueError, match="binding count"):
        run(binding_captures={10: bad})


def test_binding_capture_count_cannot_exceed_source_uint16_count():
    with pytest.raises(ValueError, match="UInt16 Animator binding count"):
        run(binding_captures={10: AnimatorBindingCapture(record(65536), (0,) * 65536)})


def test_binding_capture_accepts_maximum_source_uint16_count():
    result = run(
        binding_captures={10: AnimatorBindingCapture(record(65535), (0,) * 65535)}
    )
    assert result.transform_to_handler == {99: 7, 2: 65534}


def test_all_selected_animators_null_clears_dirty_without_replacing_records():
    old = record(1, 99)
    result = run(
        team_to_animator={1: None, 2: None},
        binding_captures=None,
        animator_records={10: old},
    )
    assert result.plans[0].animator is None
    assert result.operations == ()
    assert result.dirty_teams == result.temp_animators == frozenset()
    assert result.animator_records == {10: old}
    assert result.transform_to_handler == {99: 7}


def test_empty_created_record_still_replaces_and_enables_without_handler_writes():
    result = run(binding_captures={10: AnimatorBindingCapture(record(0), ())})
    assert result.animator_records[10] == record(0)
    assert result.transform_to_handler == {99: 7}
    assert [op.action for op in result.operations] == ["create", "enable"]


def test_caller_observed_animator_order_controls_multiple_binding_operations():
    result = run(
        dirty_teams={1, 3},
        team_to_animator={1: AnimatorObject(101, 10), 3: AnimatorObject(303, 20)},
        team_ids=(1, 3),
        transforms=(1001, 3003),
        animator_order=(20, 10),
        binding_captures={
            10: AnimatorBindingCapture(record(1, 10), (0,)),
            20: AnimatorBindingCapture(record(1, 20), (0,)),
        },
    )
    assert [plan.mapped_animator_id for plan in result.plans] == [20, 10]
    assert [(op.action, op.animator_instance_id) for op in result.operations] == [
        ("create", 20),
        ("enable", 20),
        ("create", 10),
        ("enable", 10),
    ]
    assert result.transform_to_handler == {99: 7, 1: 0, 0: 0}


def test_source_inputs_and_records_are_not_mutated():
    old = record(1, 99)
    records = {10: old}
    handlers = {99: 7}
    dirty = {1, 2}
    temp = {999}
    run(
        animator_records=records,
        transform_to_handler=handlers,
        dirty_teams=dirty,
        temp_animators=temp,
    )
    assert records == {10: old}
    assert handlers == {99: 7}
    assert dirty == {1, 2}
    assert temp == {999}
