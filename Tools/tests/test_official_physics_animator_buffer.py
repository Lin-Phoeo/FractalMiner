"""Source animator read branch values; no custom Unity animator or Job runtime."""

import struct
import sys
from dataclasses import replace
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from official_physics_animator_buffer import read_animator_buffer_values
from official_physics_read_restore import (
    CapturedTransform,
    ReadRestoreTeam,
    RelativeReadContext,
)
from official_physics_setter import TransformPose

Q = (0, 0, 0, 1)
I = ((1, 0, 0, 0), (0, 1, 0, 0), (0, 0, 1, 0), (0, 0, 0, 1))
BUFFER_MATRIX = I[:3] + ((10, 20, 30, 1),)
BUFFER = CapturedTransform(
    TransformPose((10, 20, 30), Q, (1, 2, 3), (0, 0, 0, 2)), BUFFER_MATRIX
)
FALLBACK_MATRIX = ((-2, 0, 0, 0), (0, 3, 0, 0), (0, 0, 4, 0), (40, 50, 60, 1))
FALLBACK = CapturedTransform(
    TransformPose((40, 50, 60), Q, (4, 5, 6), Q), FALLBACK_MATRIX
)
NAMES = ("transformID2RWHandlerID", "teamId2AnimatorInstanceId", "animatorID2RWHandler")


def read(**kwargs):
    args = {
        "slot": 0,
        "transform_valid": True,
        "flags": (0x11,),
        "team_ids": (1,),
        "teams": (None, ReadRestoreTeam(0)),
        "transform_to_handler": {0: 1},
        "team_to_animator": {1: -42},
        "animator_buffers": {-42: (FALLBACK, BUFFER)},
        "fallback": FALLBACK,
    }
    return read_animator_buffer_values(**(args | kwargs))


def test_three_lookups_use_global_slot_team_and_signed_animator_id_in_order():
    result = read()
    assert result.used_buffer
    assert result.lookups == (
        (NAMES[0], 0, True),
        (NAMES[1], 1, True),
        (NAMES[2], -42, True),
    )
    assert result.values.world_position == (10, 20, 30)
    assert result.values.local_position == (1, 2, 3)
    assert result.values.local_rotation == (0, 0, 0, 2)
    assert result.values.local_to_world_matrix == BUFFER_MATRIX
    assert result.scale_writes == ((1, 1, 1), (1, 1, 1))
    assert result.values.write_order == (
        "local_position",
        "local_rotation",
        "scale",
        "scale",
        "world_position",
        "world_rotation",
        "local_to_world_matrix",
    )


def test_buffer_branch_does_not_query_fallback_transform_getters():
    assert read(fallback=None).used_buffer


@pytest.mark.parametrize("missing", [0, 1, 2])
def test_any_missing_map_uses_getters_and_stops_later_lookups(missing):
    kwargs = {}
    fields = ("transform_to_handler", "team_to_animator", "animator_buffers")
    kwargs[fields[missing]] = {}
    for field in fields[missing + 1 :]:
        kwargs[field] = None
    result = read(**kwargs)
    assert not result.used_buffer
    assert tuple(x[0] for x in result.lookups) == NAMES[: missing + 1]
    assert result.lookups[-1][2] is False
    assert result.values.world_position == (40, 50, 60)
    assert result.values.scale == (-2, 3, 4)
    assert result.scale_writes == ((-2, 3, 4),)
    assert result.values.write_order == (
        "local_position",
        "local_rotation",
        "scale",
        "world_position",
        "world_rotation",
        "local_to_world_matrix",
    )


def test_buffer_scale_diagonal_is_computed_then_overwritten_to_one():
    # Deliberately unconstrained resolved-matrix fixture; NOT proof of native TRS.
    cap = CapturedTransform(BUFFER.pose, FALLBACK_MATRIX)
    result = read(animator_buffers={-42: (cap, cap)})
    assert result.scale_writes == ((-2, 3, 4), (1, 1, 1))
    assert result.values.scale == (1, 1, 1)


def test_buffer_still_computes_inverse_rotation_before_scale_one_overwrite():
    cap = replace(BUFFER, pose=replace(BUFFER.pose, world_rotation=(0, 0, 0, 0)))
    with pytest.raises(ValueError):
        read(animator_buffers={-42: (cap, cap)})


def test_team_id_buffer_is_read_before_transform_validity():
    with pytest.raises(ValueError):
        read(transform_valid=False, team_ids=())
    assert (
        read(transform_valid=False, flags=None, teams=None, transform_to_handler=None)
        is None
    )


@pytest.mark.parametrize("flag", [0, 1, 8, 0x10, 0x18])
def test_requires_enabled_and_read_bits_before_team_struct_and_maps(flag):
    assert read(flags=(flag,), teams=None, transform_to_handler=None) is None


@pytest.mark.parametrize("flag", [0x800, 0x80000, 0x80800, 0x1800])
def test_culling_helper_skips_before_maps_and_getters(flag):
    assert read(teams=(None, ReadRestoreTeam(flag)), transform_to_handler=None) is None


@pytest.mark.parametrize("flag", [0x1000, 0x2000, 1 << 61, 1 << 63])
def test_animator_read_does_not_inherit_ordinary_read_high_bit_gate(flag):
    assert read(teams=(None, ReadRestoreTeam(flag))).used_buffer


def test_team_zero_is_not_an_invented_read_skip():
    assert read(
        team_ids=(0,), teams=(ReadRestoreTeam(0),), team_to_animator={0: -42}
    ).used_buffer


@pytest.mark.parametrize("buffer_path", [True, False])
@pytest.mark.parametrize("relative_gate", [1, 2, 2**31, 2**32 - 1])
def test_relative_inverse_changes_world_only_after_original_space_scale(
    buffer_path, relative_gate
):
    inverse = I[:3] + ((-1, -2, -3, 1),)
    result = read(
        transform_to_handler={0: 1} if buffer_path else {},
        teams=(None, ReadRestoreTeam(0, relative_gate)),
        relative=RelativeReadContext(inverse, Q),
    )
    assert result.values.world_position == (
        (9, 18, 27) if buffer_path else (39, 48, 57)
    )
    assert result.values.local_position == ((1, 2, 3) if buffer_path else (4, 5, 6))
    assert result.values.scale == ((1, 1, 1) if buffer_path else (-2, 3, 4))
    assert result.values.local_to_world_matrix[3] == (*result.values.world_position, 1)


def test_relative_quaternion_left_multiplies_world_not_local():
    pose = replace(BUFFER.pose, world_rotation=(0, 1, 0, 0))
    cap = CapturedTransform(pose, BUFFER_MATRIX)
    result = read(
        animator_buffers={-42: (cap, cap)},
        teams=(None, ReadRestoreTeam(0, 1)),
        relative=RelativeReadContext(I, (1, 0, 0, 0)),
    )
    assert result.values.world_rotation == (0, 0, 1, 0)
    assert result.values.local_rotation == (0, 0, 0, 2)


def test_single_world_position_then_double_widening():
    cap = replace(
        BUFFER, pose=replace(BUFFER.pose, world_position=(16777217, 0.1, -0.0))
    )
    result = read(animator_buffers={-42: (cap, cap)})
    assert result.values.world_position[0] == 16777216
    assert (
        result.values.world_position[1]
        == struct.unpack("<f", struct.pack("<f", 0.1))[0]
    )


def test_captured_buffer_index_is_not_manager_slot_or_team_index():
    result = read(
        slot=2,
        flags=(0, 0, 0x11),
        team_ids=(1, 1, 1),
        transform_to_handler={2: 0},
        animator_buffers={-42: (BUFFER,)},
    )
    assert result.values.world_position == (10, 20, 30)


def test_bad_selected_handler_index_is_not_a_missing_map_fallback():
    with pytest.raises(ValueError):
        read(transform_to_handler={0: 100})


def test_selected_null_capture_is_not_a_fallback():
    with pytest.raises(ValueError, match="capture"):
        read(animator_buffers={-42: (BUFFER, None)})


def test_found_but_null_record_is_not_a_missing_map_fallback():
    with pytest.raises(ValueError, match="record"):
        read(animator_buffers={-42: None})


def test_missing_fallback_capture_is_explicit_adapter_error():
    with pytest.raises(ValueError, match="capture"):
        read(transform_to_handler={}, fallback=None)


def test_nonrelative_does_not_read_relative_context():
    assert read(relative=object()).values.world_position == (10, 20, 30)


def test_relative_needs_resolved_context_not_identity_fallback():
    with pytest.raises(ValueError, match="relative"):
        read(teams=(None, ReadRestoreTeam(0, 1)))


@pytest.mark.parametrize("value", [None, 0, 1])
def test_transform_validity_bool_adapter(value):
    with pytest.raises(ValueError, match="bool"):
        read(transform_valid=value)


@pytest.mark.parametrize(
    "field,value",
    [
        ("slot", -1),
        ("slot", True),
        ("flags", (256,)),
        ("team_ids", (-1,)),
        ("team_ids", (32768,)),
        ("teams", (None, None)),
        ("team_to_animator", {1: True}),
        ("team_to_animator", {1: 2**31}),
        ("transform_to_handler", {0: -1}),
        ("transform_to_handler", {0: True}),
    ],
)
def test_selected_range_policy_is_not_native_invalid_exception_equivalence(
    field, value
):
    with pytest.raises(ValueError):
        read(**{field: value})


@pytest.mark.parametrize("flag", [-1, 2**64, True])
def test_team_flag_uint64_adapter(flag):
    with pytest.raises(ValueError):
        read(teams=(None, ReadRestoreTeam(flag)))


@pytest.mark.parametrize("gate", [-1, 2**32, True])
def test_relative_switch_uint32_adapter(gate):
    with pytest.raises(ValueError):
        read(teams=(None, ReadRestoreTeam(0, gate)))


def test_selected_matrix_and_pose_finiteness_rejected():
    with pytest.raises(ValueError):
        read(
            animator_buffers={-42: (BUFFER, replace(BUFFER, local_to_world_matrix=()))}
        )
    with pytest.raises(ValueError):
        read(
            animator_buffers={
                -42: (
                    BUFFER,
                    replace(
                        BUFFER,
                        pose=replace(BUFFER.pose, local_position=(0, float("nan"), 0)),
                    ),
                )
            }
        )
