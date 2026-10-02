"""Finite setter values/order, not actual Unity setters or native trajectories."""

import math
import sys
from dataclasses import replace
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from official_physics_publication import (
    TransformBufferSnapshot,
    select_transform_write_buffers,
)
from official_physics_setter import (
    RelativeWriteContext,
    SetterTeam,
    TransformPose,
    compute_transform_writes,
    interpolate_rotation,
)

Q = (0, 0, 0, 1)
TARGET_Q = (0, 0, 0, 2)
BUFFERS = TransformBufferSnapshot(
    ((8, 12, 16),), (TARGET_Q,), ((4, 6, 8),), (TARGET_Q,)
)
POSE = TransformPose((0, 4, 8), Q, (0, 2, 4), Q)
TEAM = SetterTeam(0x2000, 1, 1)


def writes(flags=0x16, team=TEAM, **kwargs):
    values = {
        "slot": 0,
        "transform_valid": True,
        "flags": (flags,),
        "team_ids": (1,),
        "teams": (None, team),
        "buffers": BUFFERS,
        "current": POSE,
    }
    return compute_transform_writes(**(values | kwargs))


def props(result):
    return [write.property for write in result]


def test_world_has_priority_over_local_and_rotation_is_written_before_position():
    result = writes(0x16)
    assert props(result) == ["world_rotation", "world_position"]
    assert result[0].value == TARGET_Q  # Full weight never normalizes.
    assert result[1].value == (8, 12, 16)


def test_local_position_precedes_local_rotation_and_no_world_position_gate():
    result = writes(0x14, SetterTeam(0, 1, 1))
    assert props(result) == ["local_position", "local_rotation"]
    assert result[0].value == (4, 6, 8)
    assert result[1].value == TARGET_Q


def test_world_position_is_optional_but_rotation_is_not_gated_by_0x2000():
    result = writes(0x12, SetterTeam(0, 1, 1))
    assert props(result) == ["world_rotation"]


@pytest.mark.parametrize("team_flag", [0x800, 0x80000, 0x80800, 0x2000 | 0x800])
def test_either_culling_flag_skips_before_buffer_or_current_reads(team_flag):
    assert writes(team=SetterTeam(team_flag, 1, 1), buffers=None, current=None) == ()


def test_culling_helper_reads_low_uint32_not_high_bits():
    assert props(writes(team=SetterTeam((0x800 << 32) | 0x2000, 1, 1))) == [
        "world_rotation",
        "world_position",
    ]


@pytest.mark.parametrize("flags", [0, 2, 4, 6])
def test_disabled_transform_skips_before_team_reads(flags):
    assert writes(flags, team_ids=None, teams=None, buffers=None, current=None) == ()


def test_invalid_transform_does_not_read_flags_or_index():
    assert (
        writes(
            slot=None,
            transform_valid=False,
            flags=None,
            team_ids=None,
            teams=None,
            buffers=None,
            current=None,
        )
        == ()
    )


def test_enabled_without_world_local_bits_does_not_read_buffers():
    assert writes(0x10, buffers=None, current=None) == ()


def test_team_zero_has_no_invented_early_return():
    assert props(writes(team_ids=(0,), teams=(TEAM,))) == [
        "world_rotation",
        "world_position",
    ]


@pytest.mark.parametrize("a,b", [(0, 1), (1, 0), (-1, 1), (1, -1)])
def test_nonpositive_effective_weight_skips_before_buffer_reads(a, b):
    assert writes(team=SetterTeam(0x2000, a, b), buffers=None, current=None) == ()


def test_weight_is_product_of_simulate_and_lod_weights():
    team = SetterTeam(0x2000, 0.5, 0.5)
    result = writes(team=team, buffers=replace(BUFFERS, world_rotations=(Q,)))
    assert result[1].value == (
        2,
        6,
        10,
    )  # Weight .25, not .5 or an unrelated blendWeight.


@pytest.mark.parametrize("weight", [1, 1.5, 4])
def test_weight_at_or_above_one_bypasses_current_reads_and_interpolation(weight):
    assert writes(team=SetterTeam(0x2000, weight, 1), current=None)[0].value == TARGET_Q


def test_local_fractional_position_and_rotation_use_local_getter_values():
    result = writes(
        0x14, SetterTeam(0, 0.5, 1), buffers=replace(BUFFERS, local_rotations=(Q,))
    )
    assert result[0].value == (2, 4, 6)
    assert result[1].value == Q


@pytest.mark.parametrize("q", [(0, 0, 0, 0), (0, 0, 0, 0.09)])
def test_invalid_small_world_quaternion_does_not_suppress_position(q):
    result = writes(buffers=replace(BUFFERS, world_rotations=(q,)))
    assert props(result) == ["world_position"]


def test_invalid_small_local_quaternion_does_not_roll_back_position():
    result = writes(0x14, buffers=replace(BUFFERS, local_rotations=((0, 0, 0, 0.09),)))
    assert props(result) == ["local_position"]


def test_dot_threshold_is_point01_not_unit_normalization_or_zero_only():
    q = (0, 0, 0, 0.101)
    assert props(writes(buffers=replace(BUFFERS, world_rotations=(q,)))) == [
        "world_rotation",
        "world_position",
    ]


def test_unselected_local_arrays_and_pose_are_not_validated_on_world_full_weight():
    selected = replace(BUFFERS, local_positions=(), local_rotations=())
    assert len(writes(buffers=selected, current=None)) == 2


def test_unselected_world_arrays_and_relative_data_not_read_on_local_route():
    selected = replace(BUFFERS, world_positions=(), world_rotations=())
    team = SetterTeam(0, 1, 1, use_relative_transform=1)
    assert len(writes(0x14, team, buffers=selected, current=None, relative=None)) == 2


def test_relative_context_is_required_only_on_active_world_route():
    with pytest.raises(ValueError, match="relative"):
        writes(team=replace(TEAM, use_relative_transform=1))


def test_relative_uses_supplied_matrix_and_its_rotation_after_blending():
    # Already-resolved forward source matrix from caller: translate -2,-3,-4.
    relative = RelativeWriteContext(
        ((1, 0, 0, 0), (0, 1, 0, 0), (0, 0, 1, 0), (-2, -3, -4, 1)), Q
    )
    result = writes(
        team=SetterTeam(0x2000, 0.5, 1, 1),
        relative=relative,
        buffers=replace(BUFFERS, world_rotations=(Q,)),
    )
    assert result[1].value == (2, 5, 8)  # blend (4,8,12) THEN transform.
    assert result[0].value == Q


def test_relative_rotation_product_order_is_matrix_rotation_then_target():
    qx, qy = (1, 0, 0, 0), (0, 1, 0, 0)
    relative = RelativeWriteContext(
        ((1, 0, 0, 0), (0, 1, 0, 0), (0, 0, 1, 0), (0, 0, 0, 1)), qx
    )
    result = writes(
        team=replace(TEAM, use_relative_transform=1),
        relative=relative,
        buffers=replace(BUFFERS, world_rotations=(qy,)),
    )
    assert result[0].value == (0, 0, 1, 0)


@pytest.mark.parametrize("use_relative", [1, 2, 2**31, 2**32 - 1])
def test_relative_gate_is_uint32_nonzero_not_boolean_one_only(use_relative):
    relative = RelativeWriteContext(
        ((1, 0, 0, 0), (0, 1, 0, 0), (0, 0, 1, 0), (0, 0, 0, 1)), Q
    )
    assert (
        len(
            writes(
                team=replace(TEAM, use_relative_transform=use_relative),
                relative=relative,
            )
        )
        == 2
    )


def test_rotation_slerp_shortest_arc_midpoint():
    q90 = (0, math.sqrt(0.5), 0, math.sqrt(0.5))
    assert interpolate_rotation(Q, q90, 0.5) == pytest.approx(
        (0, math.sin(math.pi / 8), 0, math.cos(math.pi / 8)), abs=2e-7
    )
    assert interpolate_rotation(Q, tuple(-x for x in q90), 0.5) == pytest.approx(
        interpolate_rotation(Q, q90, 0.5), abs=2e-7
    )


def test_rotation_close_dot_uses_normalized_lerp():
    q = (0, 0.01, 0, 1)
    result = interpolate_rotation(Q, q, 0.5)
    expected = (0, 0.005 / math.sqrt(1 + 0.005**2), 0, 1 / math.sqrt(1 + 0.005**2))
    assert result == pytest.approx(expected, abs=2e-7)


def test_current_last_selection_composes_with_setter_not_field_names():
    last = replace(BUFFERS, world_positions=((1, 2, 3),))
    for cross, expected in ((False, (8, 12, 16)), (True, (1, 2, 3))):
        selected = select_transform_write_buffers(BUFFERS, last, cross_frame=cross)
        assert writes(buffers=selected)[1].value == expected


@pytest.mark.parametrize("value", [0, 1, None])
def test_transform_valid_requires_actual_boolean(value):
    with pytest.raises(ValueError, match="bool"):
        writes(transform_valid=value)


@pytest.mark.parametrize(
    "field,value",
    [
        ("slot", True),
        ("slot", -1),
        ("flags", (256,)),
        ("flags", (True,)),
        ("team_ids", (-1,)),
        ("team_ids", (32768,)),
        ("teams", (None, None)),
    ],
)
def test_active_slot_range_and_missing_team_rejections_are_adapter_policy(field, value):
    with pytest.raises(ValueError):
        writes(**{field: value})


@pytest.mark.parametrize(
    "field,value",
    [
        ("flag", -1),
        ("flag", 2**64),
        ("use_relative_transform", -1),
        ("use_relative_transform", True),
    ],
)
def test_team_integer_shape_policy(field, value):
    with pytest.raises(ValueError):
        writes(team=replace(TEAM, **{field: value}))


@pytest.mark.parametrize("value", [float("nan"), float("inf"), True])
def test_nonfinite_or_nonnumeric_active_weights_rejected_as_adapter_policy(value):
    with pytest.raises(ValueError):
        writes(team=SetterTeam(0x2000, value, 1))


def test_fractional_weight_requires_current_pose():
    with pytest.raises(ValueError, match="current"):
        writes(team=SetterTeam(0x2000, 0.5, 1), current=None)


@pytest.mark.parametrize("field", ["world_positions", "world_rotations"])
def test_missing_active_buffer_slot_rejected(field):
    with pytest.raises(ValueError):
        writes(buffers=replace(BUFFERS, **{field: ()}))


def test_invalid_relative_matrix_shape_rejected():
    with pytest.raises(ValueError, match="matrix"):
        writes(
            team=replace(TEAM, use_relative_transform=1),
            relative=RelativeWriteContext((), Q),
        )


def test_zero_relative_rotation_skips_rotation_but_keeps_transformed_position():
    relative = RelativeWriteContext(
        ((1, 0, 0, 0), (0, 1, 0, 0), (0, 0, 1, 0), (0, 0, 0, 1)), (0, 0, 0, 0)
    )
    assert props(
        writes(team=replace(TEAM, use_relative_transform=1), relative=relative)
    ) == ["world_position"]


def test_weight_product_single_overflow_is_adapter_rejection_not_native_nan_policy():
    with pytest.raises(ValueError):
        writes(team=SetterTeam(0x2000, 3e38, 2))


@pytest.mark.parametrize("t", [-0.01, 1.01])
def test_interpolation_outside_finite_adapter_interval_rejected(t):
    with pytest.raises(ValueError, match="weight"):
        interpolate_rotation(Q, Q, t)


def test_wrong_matrix_column_length_rejected():
    context = RelativeWriteContext(((1, 0, 0), Q, Q, Q), Q)
    with pytest.raises(ValueError, match="matrix"):
        writes(team=replace(TEAM, use_relative_transform=1), relative=context)


def test_large_double_not_cast_to_single_on_rotation_only_route():
    buffers = replace(BUFFERS, world_positions=((1e300, 0, 0),))
    assert props(writes(team=SetterTeam(0, 1, 1), buffers=buffers)) == [
        "world_rotation"
    ]
