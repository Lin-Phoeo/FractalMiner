"""Finite Add/Clear Team Animator membership, not runtime disposal proof."""

import sys
from pathlib import Path
from typing import Any, cast

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from official_physics_animator_lifecycle import (
    AnimatorBindingCapture,
    AnimatorObject,
    add_team_animator_data,
    clear_team_animator_data,
    update_team_animator_data,
)
from official_physics_animator_write import AnimatorRecord

Q = (0, 0, 0, 1)
RECORD = AnimatorRecord(((0, 0, 0),), (Q,), ((1, 2, 3),), (Q,), (0,))
A = AnimatorObject(101, -42)
B = AnimatorObject(102, 43)


def add(**updates):
    args = {
        "team_id": 1,
        "resolved_animator": A,
        "global_team_to_animator_instance": {2: 43},
        "local_team_to_animator": {2: B},
        "dirty_teams": {2},
    }
    return add_team_animator_data(**(args | updates))


def clear(**updates):
    args = {
        "team_id": 1,
        "team_to_animator_instance": {1: -42, 2: 43},
        "team_to_animator": {1: A, 2: B},
    }
    return clear_team_animator_data(**(args | updates))


def test_add_uses_global_instance_map_local_object_map_and_marks_dirty():
    result = add()
    assert result.global_team_to_animator_instance == {1: -42, 2: 43}
    assert result.local_team_to_animator == {1: A, 2: B}
    assert result.dirty_teams == frozenset({1, 2})
    assert result.operations == (
        "set-global-instance",
        "set-local-animator",
        "add-dirty",
    )


def test_replacement_does_not_remove_old_animator_records_or_other_shared_teams():
    result = add(
        global_team_to_animator_instance={1: 43, 2: 43},
        local_team_to_animator={1: B, 2: B},
    )
    assert result.global_team_to_animator_instance == {1: -42, 2: 43}
    assert result.local_team_to_animator == {1: A, 2: B}


def test_resolved_unity_null_still_marks_dirty_and_leaves_stale_maps_unchanged():
    result = add(
        resolved_animator=None,
        global_team_to_animator_instance={1: 43},
        local_team_to_animator={1: B},
    )
    assert result.global_team_to_animator_instance == {1: 43}
    assert result.local_team_to_animator == {1: B}
    assert result.dirty_teams == frozenset({1, 2})
    assert result.operations == ("add-dirty",)


def test_null_route_does_not_require_unselected_global_instance_map_capture():
    result = add(resolved_animator=None, global_team_to_animator_instance=None)
    assert result.global_team_to_animator_instance is None
    assert result.local_team_to_animator == {2: B}


def test_valid_route_requires_global_manager_instance_map_without_local_alias_default():
    with pytest.raises(ValueError, match="global"):
        add(global_team_to_animator_instance=None)


def test_add_copies_inputs_without_mutating_them_or_the_animator_object():
    instances, objects, dirty = {2: 43}, {2: B}, {2}
    result = add(
        global_team_to_animator_instance=instances,
        local_team_to_animator=objects,
        dirty_teams=dirty,
    )
    assert instances == {2: 43} and objects == {2: B} and dirty == {2}
    assert result.local_team_to_animator[1] == A


@pytest.mark.parametrize("team", [-(2**31), -32769, -1, 0, 32768, 2**31 - 1])
def test_add_and_clear_use_int32_team_ids_without_extra_zero_or_int16_gate(team):
    result = add(
        team_id=team,
        global_team_to_animator_instance={},
        local_team_to_animator={},
        dirty_teams=set(),
    )
    assert result.global_team_to_animator_instance == {team: -42}
    assert result.local_team_to_animator == {team: A}
    assert result.dirty_teams == frozenset({team})
    removed = clear(
        team_id=team,
        team_to_animator_instance=result.global_team_to_animator_instance,
        team_to_animator=result.local_team_to_animator,
    )
    assert removed.team_to_animator_instance == {} and removed.team_to_animator == {}


@pytest.mark.parametrize("function", [add, clear])
@pytest.mark.parametrize("team", [None, True, 1.0, -(2**31) - 1, 2**31])
def test_selected_team_id_requires_int32(function, team):
    with pytest.raises(ValueError):
        function(team_id=team)


def test_clear_removes_only_selected_team_from_both_maps():
    result = clear()
    assert result.team_to_animator_instance == {2: 43}
    assert result.team_to_animator == {2: B}
    assert result.operations == ("remove-instance", "remove-animator")


def test_clear_missing_one_map_key_does_not_skip_the_other_removal():
    result = clear(team_to_animator_instance={2: 43})
    assert result.team_to_animator_instance == {2: 43}
    assert result.team_to_animator == {2: B}


def test_clear_missing_both_keys_still_records_both_source_remove_operations():
    result = clear(team_to_animator_instance={}, team_to_animator={})
    assert result.operations == ("remove-instance", "remove-animator")


def test_add_clear_then_rebuild_keeps_shared_records_stale_slot_and_surviving_team():
    registered = add(
        global_team_to_animator_instance={2: -42},
        local_team_to_animator={2: A},
        dirty_teams=set(),
    )
    assert registered.global_team_to_animator_instance is not None
    removed = clear(
        team_to_animator_instance=registered.global_team_to_animator_instance,
        team_to_animator=registered.local_team_to_animator,
    )
    # Dirty team1 remains pending. Clear does not implicitly dispose the old RW
    # record or clear handler0, nor remove team2 sharing the same Animator.
    rebuilt = update_team_animator_data(
        dirty_teams=registered.dirty_teams | {2},
        temp_animators=set(),
        team_to_animator_instance=removed.team_to_animator_instance,
        team_to_animator=removed.team_to_animator,
        team_ids=(1, 2),
        transforms=(1001, 1002),
        animator_order=(-42,),
        binding_captures={-42: AnimatorBindingCapture(RECORD, (0,))},
        animator_records={-42: RECORD, 43: RECORD},
        transform_to_handler={0: 9},
    )
    assert rebuilt.transform_to_handler == {0: 9, 1: 0}
    assert rebuilt.animator_records[43] == RECORD
    assert [operation.action for operation in rebuilt.operations] == [
        "disable",
        "create",
        "enable",
    ]


def test_null_registration_without_mapping_rebuilds_no_animator_and_clears_dirty():
    registered = add(
        resolved_animator=None,
        global_team_to_animator_instance={},
        local_team_to_animator={},
        dirty_teams=set(),
    )
    rebuilt = update_team_animator_data(
        dirty_teams=registered.dirty_teams,
        temp_animators=set(),
        team_to_animator_instance=registered.global_team_to_animator_instance,
        team_to_animator=registered.local_team_to_animator,
        team_ids=cast(Any, None),
        transforms=None,
        animator_order=(),
        binding_captures=None,
        animator_records={-42: RECORD},
        transform_to_handler={0: 9},
    )
    assert rebuilt.dirty_teams == frozenset()
    assert rebuilt.animator_records == {-42: RECORD}
    assert rebuilt.transform_to_handler == {0: 9}
