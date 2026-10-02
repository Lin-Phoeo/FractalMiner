"""Finite registration fields, not native allocation, Unity or full physics."""

import math
import struct
import sys
from dataclasses import replace
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from official_physics_proxy_baseline import LocalPose
from official_physics_read_restore import (
    CapturedTransform,
    ReadRestoreTeam,
    compute_restore_writes,
    read_transform_values,
)
from official_physics_registration import (
    RegisteredSlot,
    RegistrationCapture,
    copy_registered_transform,
    enable_registered_flag,
    set_registered_transform,
)
from official_physics_setter import TransformPose

Q = (0, 0, 0, 1)
M = ((2, 0, 0, 0), (0, -3, 0, 0), (0, 0, 4, 0), (9, 8, 7, 1))
OLD_HANDLE, NEW_HANDLE = object(), object()
OLD = RegisteredSlot(
    flag=0x11,
    initial_local_position=(1, 2, 3),
    initial_local_rotation=Q,
    world_position=(4, 5, 6),
    world_rotation=Q,
    last_world_position=(7, 8, 9),
    last_world_rotation=Q,
    scale=(1, 1, 1),
    local_position=(10, 11, 12),
    local_rotation=Q,
    last_local_position=(13, 14, 15),
    last_local_rotation=Q,
    local_to_world_matrix=M,
    transform_handle=OLD_HANDLE,
    team_id=2,
)
CAPTURE = RegistrationCapture(
    initial_local_position=(20, 21, 22),
    initial_local_rotation=(0, 0, 0, 2),
    world_position=(30, 31, 32),
    world_rotation=(3, 0, 0, 0),
    last_world_position=(40, 41, 42),
    last_world_rotation=(0, 4, 0, 0),
    local_scale=(-2, 3, -4),
    local_position=(50, 51, 52),
    local_rotation=(0, 0, 5, 0),
    last_local_position=(60, 61, 62),
    last_local_rotation=(0, 0, 0, 6),
)


def register(**kwargs):
    args = {
        "manager_valid": True,
        "transform_valid": True,
        "previous": OLD,
        "flag": 0x19,
        "team_id": 1,
        "transform_handle": NEW_HANDLE,
        "captured": CAPTURE,
    }
    return set_registered_transform(**(args | kwargs))


def test_set_preserves_eleven_separately_captured_getters_and_existing_matrix():
    result = register()
    slot = result.slot
    assert slot.flag == 0x19 and slot.team_id == 1
    for name in (
        "initial_local_position",
        "initial_local_rotation",
        "world_position",
        "world_rotation",
        "last_world_position",
        "last_world_rotation",
        "local_position",
        "local_rotation",
        "last_local_position",
        "last_local_rotation",
    ):
        assert getattr(slot, name) == getattr(CAPTURE, name)
    assert slot.scale == (-2, 3, -4)
    assert slot.local_to_world_matrix is M
    assert slot.transform_handle is NEW_HANDLE
    assert result.write_order == (
        "flag",
        "initial_local_position",
        "initial_local_rotation",
        "world_position",
        "world_rotation",
        "last_world_position",
        "last_world_rotation",
        "scale",
        "local_position",
        "local_rotation",
        "last_local_position",
        "last_local_rotation",
        "team_id",
        "transform_access",
    )
    assert result.animator_call.method == "AddAnimatorTransform"
    assert result.animator_call.team_id == 1
    assert result.animator_call.transform_handle is NEW_HANDLE
    assert OLD.transform_handle is OLD_HANDLE  # No mutation of caller snapshot.


@pytest.mark.parametrize("flag", [0, 1, 8, 0x10, 0x80, 0xFF])
def test_set_does_not_add_enable_bit_or_skip_flag_zero(flag):
    result = register(flag=flag)
    assert result.slot.flag == flag
    assert result.slot.initial_local_position == CAPTURE.initial_local_position


@pytest.mark.parametrize(
    "team_id,stored",
    [
        (0, 0),
        (32767, 32767),
        (32768, -32768),
        (65535, -1),
        (65536, 0),
        (-1, -1),
        (-65536, 0),
        (2**31 - 1, -1),
        (-(2**31), 0),
    ],
)
def test_team_buffer_stores_signed_low_word_but_animator_call_keeps_int32(
    team_id, stored
):
    result = register(team_id=team_id)
    assert result.slot.team_id == stored
    assert result.animator_call.team_id == team_id


def test_single_world_getters_widen_after_rounding_and_not_copy_current_to_last():
    cap = replace(
        CAPTURE,
        world_position=(16777217, 0.1, -0.0),
        last_world_position=(16777219, 0.2, 2),
    )
    slot = register(captured=cap).slot
    assert slot.world_position == (
        16777216,
        struct.unpack("<f", struct.pack("<f", 0.1))[0],
        -0.0,
    )
    assert slot.last_world_position[0] == 16777220
    assert math.copysign(1, slot.world_position[2]) == -1
    assert slot.last_world_position != slot.world_position


def test_zero_and_nonunit_quaternions_are_not_normalized_or_rejected():
    cap = replace(CAPTURE, initial_local_rotation=(0, 0, 0, 0))
    slot = register(captured=cap).slot
    assert slot.initial_local_rotation == (0, 0, 0, 0)
    assert slot.local_rotation == (0, 0, 5, 0)


def test_set_does_not_read_or_rebuild_existing_matrix():
    previous = replace(OLD, local_to_world_matrix=object())
    assert (
        register(previous=previous).slot.local_to_world_matrix
        is previous.local_to_world_matrix
    )


@pytest.mark.parametrize("handle", [None, OLD_HANDLE])
def test_unity_null_or_destroyed_resets_only_flag_team_and_access(handle):
    result = register(
        transform_valid=False, flag=None, captured=None, transform_handle=handle
    )
    assert result.slot == replace(OLD, flag=0, team_id=0, transform_handle=None)
    assert result.write_order == ("flag", "transform_access", "team_id")
    assert result.animator_call.method == "MarkAnimatorTransformDirty"
    assert result.animator_call.team_id == 1
    assert result.animator_call.transform_handle is handle
    assert result.animator_call_before_writes is True


def test_success_animator_call_is_after_writes_not_before():
    assert register().animator_call_before_writes is False


def test_inactive_manager_skips_all_other_inputs():
    assert (
        register(
            manager_valid=False,
            transform_valid=None,
            previous=None,
            flag=None,
            team_id=None,
            transform_handle=None,
            captured=None,
        )
        is None
    )
    assert (
        copy_registered_transform(manager_valid=False, source=None, target=None) is None
    )
    assert (
        enable_registered_flag(manager_valid=False, slot=None, flag=None, enabled=None)
        is None
    )


def test_copy_copies_pose_init_flag_handle_team_but_retains_target_matrix():
    source = register().slot
    target = replace(OLD, local_to_world_matrix=((0, 0, 0, 0),) * 4)
    result = copy_registered_transform(manager_valid=True, source=source, target=target)
    assert result.slot == replace(
        source, local_to_world_matrix=target.local_to_world_matrix
    )
    assert result.slot.local_to_world_matrix is target.local_to_world_matrix
    assert result.slot.transform_handle is NEW_HANDLE
    assert result.animator_call is None
    assert result.write_order[-2:] == ("transform_access", "team_id")
    assert "local_to_world_matrix" not in result.write_order


def test_copy_disabled_or_null_slot_has_no_extra_gates():
    source = replace(OLD, flag=0, team_id=-32768, transform_handle=None)
    result = copy_registered_transform(manager_valid=True, source=source, target=OLD)
    assert result.slot == source


def test_copy_is_raw_no_float_re_rounding_or_validation_of_old_buffers():
    source = replace(
        OLD, world_position=(16777217.125, 0, -0.0), local_position=object()
    )
    result = copy_registered_transform(manager_valid=True, source=source, target=OLD)
    assert result.slot.world_position is source.world_position
    assert result.slot.local_position is source.local_position


def test_copy_self_is_supported_and_input_not_mutated():
    result = copy_registered_transform(manager_valid=True, source=OLD, target=OLD)
    assert result.slot == OLD


def test_enable_all_byte_flags_preserves_other_bits_and_does_not_resurrect_zero():
    for flag in range(256):
        for enabled in (False, True):
            actual = enable_registered_flag(
                manager_valid=True, slot=0, flag=flag, enabled=enabled
            )
            expected = 0 if flag == 0 else (flag | 0x10 if enabled else flag & 0xEF)
            assert actual == expected


def test_enable_flag10_can_become_zero_and_cannot_then_be_enabled_again():
    assert (
        enable_registered_flag(manager_valid=True, slot=1, flag=0x10, enabled=False)
        == 0
    )
    assert enable_registered_flag(manager_valid=True, slot=1, flag=0, enabled=True) == 0


@pytest.mark.parametrize("index", [-1, -(2**31)])
def test_negative_enable_index_skips_flag_buffer_and_switch(index):
    assert (
        enable_registered_flag(manager_valid=True, slot=index, flag=None, enabled=None)
        is None
    )


def test_zero_enable_flag_skips_switch_validation():
    assert enable_registered_flag(manager_valid=True, slot=0, flag=0, enabled=None) == 0


def test_register_read_restore_keeps_initial_pose_distinct_from_latest_animation():
    registered = register().slot
    pose = TransformPose((100, 200, 300), Q, (400, 500, 600), Q)
    output = read_transform_values(
        slot=0,
        transform_valid=True,
        flags=(registered.flag,),
        team_ids=(1,),
        teams=(None, ReadRestoreTeam(0)),
        captured=CapturedTransform(pose, M),
    )
    assert output.local_position == (400, 500, 600)
    restore = compute_restore_writes(
        slot=0,
        transform_valid=True,
        flags=(registered.flag,),
        team_ids=(1,),
        teams=(None, ReadRestoreTeam(0)),
        initial_local=LocalPose(
            (registered.initial_local_position,), (registered.initial_local_rotation,)
        ),
    )
    assert restore[0].value == (20, 21, 22)
    assert restore[1].value == (0, 0, 0, 2)
    assert registered.last_local_position == (60, 61, 62)
    assert registered.scale == (-2, 3, -4) and output.scale == (2, -3, 4)


def test_reregister_replaces_init_with_new_getter_not_mesh_bindpose_guess():
    first = register().slot
    second = register(
        previous=first, captured=replace(CAPTURE, initial_local_position=(90, 91, 92))
    ).slot
    assert second.initial_local_position == (90, 91, 92)
    assert first.initial_local_position == (20, 21, 22)


@pytest.mark.parametrize("value", [None, 0, 1])
@pytest.mark.parametrize("which", ["set", "copy", "enable"])
def test_manager_validity_adapter_requires_actual_bool(value, which):
    with pytest.raises(ValueError, match="bool"):
        if which == "set":
            register(manager_valid=value)
        elif which == "copy":
            copy_registered_transform(manager_valid=value, source=OLD, target=OLD)
        else:
            enable_registered_flag(manager_valid=value, slot=0, flag=1, enabled=True)


@pytest.mark.parametrize("value", [None, 0, 1])
def test_transform_validity_adapter_requires_actual_bool(value):
    with pytest.raises(ValueError, match="bool"):
        register(transform_valid=value)


@pytest.mark.parametrize(
    "field,value",
    [
        ("flag", -1),
        ("flag", 256),
        ("flag", True),
        ("team_id", -(2**31) - 1),
        ("team_id", 2**31),
        ("team_id", True),
        ("captured", None),
        ("transform_handle", None),
    ],
)
def test_active_set_adapter_rejects_bad_range_or_missing_sample(field, value):
    with pytest.raises(ValueError):
        register(**{field: value})


@pytest.mark.parametrize("field", list(RegistrationCapture.__dataclass_fields__))
def test_every_selected_getter_is_finite_and_correct_shape(field):
    old = getattr(CAPTURE, field)
    value = tuple(float("nan") if i == 0 else v for i, v in enumerate(old))
    with pytest.raises(ValueError):
        register(captured=replace(CAPTURE, **{field: value}))


@pytest.mark.parametrize("value", [True, 2**31, -(2**31) - 1])
def test_enable_index_int32_adapter_validation(value):
    with pytest.raises(ValueError):
        enable_registered_flag(manager_valid=True, slot=value, flag=1, enabled=True)


@pytest.mark.parametrize(
    "field,value",
    [("flag", 256), ("flag", -1), ("flag", True), ("enabled", None), ("enabled", 1)],
)
def test_enable_selected_values_adapter_validation(field, value):
    args = {"manager_valid": True, "slot": 0, "flag": 1, "enabled": True}
    with pytest.raises(ValueError):
        enable_registered_flag(**(args | {field: value}))
