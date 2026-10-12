"""Finite registration release boundaries, not live native storage/free proof."""

import sys
from dataclasses import replace
from pathlib import Path
from typing import Any, cast

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from official_physics_registration import RegisteredSlot, set_registered_transform
from official_physics_transform_release import (
    apply_animator_transform_dirty,
    release_registered_transform_range,
)

Q = (0, 0, 0, 1)
M = ((1, 0, 0, 0), (0, 1, 0, 0), (0, 0, 1, 0), (0, 0, 0, 1))
SLOT = RegisteredSlot(
    0x1F,
    (1, 2, 3),
    Q,
    (4, 5, 6),
    Q,
    (7, 8, 9),
    Q,
    (-1, 2, 3),
    (10, 11, 12),
    Q,
    (13, 14, 15),
    Q,
    M,
    object(),
    7,
)


def release(**updates):
    return release_registered_transform_range(
        **(
            {
                "manager_valid": True,
                "start": 1,
                "length": 2,
                "slots": (SLOT,) * 4,
            }
            | updates
        )
    )


def test_removed_window_clears_only_known_flag_team_access_fields_not_all_pose():
    result = release()
    assert result is not None
    assert result.slots == (
        SLOT,
        replace(SLOT, flag=0, team_id=0, transform_handle=None),
        replace(SLOT, flag=0, team_id=0, transform_handle=None),
        SLOT,
    )
    assert result.arena_operations == (
        ("flagArray", "RemoveAndFill", 0),
        ("initLocalPositionArray", "Remove", None),
        ("initLocalRotationArray", "Remove", None),
        ("positionArray", "Remove", None),
        ("rotationArray", "Remove", None),
        ("lastpositionArray", "Remove", None),
        ("lastrotationArray", "Remove", None),
        ("scaleArray", "Remove", None),
        ("localPositionArray", "Remove", None),
        ("localRotationArray", "Remove", None),
        ("lastlocalPositionArray", "Remove", None),
        ("lastlocalRotationArray", "Remove", None),
        ("localToWorldMatrixArray", "Remove", None),
        ("teamIdArray", "RemoveAndFill", 0),
    )
    assert result.transform_access_clears == (1, 2)
    assert result.native_allocator_applied is False


@pytest.mark.parametrize("length", [-(2**31), -1, 0])
def test_nonpositive_length_does_not_read_start_or_slot_capture(length):
    assert release(length=length, start=cast(Any, object()), slots=None) is None


def test_inactive_manager_does_not_read_any_chunk_or_slot_input():
    assert release(manager_valid=False, start=None, length=None, slots=None) is None


@pytest.mark.parametrize(
    "field,value",
    [
        ("manager_valid", 1),
        ("length", True),
        ("length", 1.0),
        ("length", 2**31),
        ("start", -1),
        ("start", True),
        ("start", 2**31),
        ("start", 4),
    ],
)
def test_adapter_rejects_bad_flags_integer_bounds_or_selected_window(field, value):
    with pytest.raises(ValueError):
        release(**{field: value})


def test_active_range_needs_slot_capture_not_empty_default():
    with pytest.raises(ValueError, match="slot"):
        release(slots=None)


def test_full_window_and_repeated_removal_preserve_shape_and_old_pose_cells():
    first = release(start=0, length=4)
    assert first is not None
    second = release(start=0, length=4, slots=first.slots)
    assert second is not None and second.slots == first.slots
    assert len(second.slots) == 4 and second.transform_access_clears == (0, 1, 2, 3)


def test_unselected_slot_payload_is_not_validated_and_pose_is_not_rerounded():
    bad = cast(Any, object())
    slot = replace(
        SLOT,
        world_position=(16777217, -0.0, 1),
        local_to_world_matrix=cast(Any, object()),
    )
    result = release(start=1, length=1, slots=(bad, slot, bad))
    assert result is not None and result.slots[0] is bad and result.slots[2] is bad
    assert result.slots[1].world_position is slot.world_position
    assert result.slots[1].local_to_world_matrix is slot.local_to_world_matrix


@pytest.mark.parametrize(
    "method", ["AddAnimatorTransform", "MarkAnimatorTransformDirty"]
)
@pytest.mark.parametrize("valid", [False, True])
def test_dirty_helpers_add_only_for_resolved_unity_valid_transform(method, valid):
    result = apply_animator_transform_dirty(
        method=method, team_id=7, transform_valid=valid, dirty_teams={2}
    )
    assert result == frozenset({2, 7} if valid else {2})


def test_null_dirty_helper_does_not_require_selected_team_id():
    assert apply_animator_transform_dirty(
        method="MarkAnimatorTransformDirty",
        team_id=cast(Any, object()),
        transform_valid=False,
        dirty_teams={2},
    ) == frozenset({2})


@pytest.mark.parametrize("team", [-(2**31), 0, 32768, 2**31 - 1])
def test_dirty_uses_original_int32_not_stored_int16_team_id(team):
    assert apply_animator_transform_dirty(
        method="AddAnimatorTransform",
        team_id=team,
        transform_valid=True,
        dirty_teams=set(),
    ) == frozenset({team})


@pytest.mark.parametrize(
    "updates",
    [
        {"method": "RemoveTransform"},
        {"transform_valid": 1},
        {"team_id": True},
        {"team_id": 2**31},
    ],
)
def test_dirty_adapter_rejects_unknown_method_or_selected_input(updates):
    with pytest.raises(ValueError):
        apply_animator_transform_dirty(
            **(
                {
                    "method": "AddAnimatorTransform",
                    "team_id": 7,
                    "transform_valid": True,
                    "dirty_teams": set(),
                }
                | updates
            )
        )


def test_failed_set_dirty_call_keeps_original_argument_and_null_outcome_no_fake_rebuild():
    result = set_registered_transform(
        manager_valid=True,
        transform_valid=False,
        previous=SLOT,
        flag=0x11,
        team_id=65543,
        transform_handle=None,
        captured=None,
    )
    assert result is not None and result.animator_call is not None
    assert result.animator_call_before_writes and result.slot.team_id == 0
    dirty = apply_animator_transform_dirty(
        method=result.animator_call.method,
        team_id=result.animator_call.team_id,
        transform_valid=False,
        dirty_teams={2},
    )
    assert dirty == frozenset({2})


def test_range_remove_itself_does_not_invent_dirty_team_or_binding_cleanup():
    result = release()
    assert result is not None
    assert all("Animator" not in op[0] for op in result.arena_operations)
    assert all("component" not in op[0] for op in result.arena_operations)
