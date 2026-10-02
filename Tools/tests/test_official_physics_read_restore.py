"""Finite source read/restore values, not Unity hierarchy or game execution."""

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
    RelativeReadContext,
    compute_restore_writes,
    multiply_matrices,
    read_component_position,
    read_transform_values,
    rotation_translation_matrix,
)
from official_physics_setter import TransformPose

Q = (0, 0, 0, 1)
IDENTITY = ((1, 0, 0, 0), (0, 1, 0, 0), (0, 0, 1, 0), (0, 0, 0, 1))
MATRIX = ((-2, 0, 0, 0), (0, 3, 0, 0), (0, 0, 4, 0), (11, 12, 13, 1))
CAPTURE = CapturedTransform(TransformPose((5, 6, 7), Q, (1, 2, 3), Q), MATRIX)
INITIAL = LocalPose(((20, 30, 40),), ((0, 0, 0, 2),))


def restore(flags=0x18, team_flag=0, **kwargs):
    args = {
        "slot": 0,
        "transform_valid": True,
        "flags": (flags,),
        "team_ids": (1,),
        "teams": (None, ReadRestoreTeam(team_flag)),
        "initial_local": INITIAL,
    }
    return compute_restore_writes(**(args | kwargs))


def read(flags=0x11, team_flag=0, **kwargs):
    args = {
        "slot": 0,
        "transform_valid": True,
        "flags": (flags,),
        "team_ids": (1,),
        "teams": (None, ReadRestoreTeam(team_flag)),
        "captured": CAPTURE,
    }
    return read_transform_values(**(args | kwargs))


def test_restore_uses_initial_not_current_or_last_local_values_without_normalization():
    output = restore()
    assert [(w.property, w.value) for w in output] == [
        ("local_position", (20, 30, 40)),
        ("local_rotation", (0, 0, 0, 2)),
    ]


@pytest.mark.parametrize("flag", [0, 0x10, 0x16])
def test_restore_requires_bit8_before_team_reads(flag):
    assert restore(flag, team_ids=None, teams=None, initial_local=None) == ()


def test_restore_disabled_slot_allowed_only_by_team_bit0x100000():
    assert restore(8, initial_local=None) == ()
    assert len(restore(8, 0x100000)) == 2


@pytest.mark.parametrize("team_flag", [0x800, 0x1000, 0x2000, 1 << 61])
def test_restore_does_not_reuse_read_or_output_culling(team_flag):
    assert len(restore(team_flag=team_flag)) == 2


@pytest.mark.parametrize("team_flag", [0x1800, 0x80000, 0x81800])
def test_restore_culls_pair800_and1000_or80000_before_buffer_reads(team_flag):
    assert restore(team_flag=team_flag, initial_local=None) == ()


def test_restore_zero_rotation_is_not_filtered_by_output_setter_norm_check():
    output = restore(initial_local=replace(INITIAL, rotations=((0, 0, 0, 0),)))
    assert output[1].value == (0, 0, 0, 0)


def test_restore_team_zero_not_invented_skip():
    assert len(restore(team_ids=(0,), teams=(ReadRestoreTeam(0),))) == 2


@pytest.mark.parametrize("function", [restore, read])
def test_invalid_transform_skips_every_buffer(function):
    assert not function(
        slot=None, transform_valid=False, flags=None, team_ids=None, teams=None
    )


@pytest.mark.parametrize("flag", [0, 1, 0x10, 0x18, 0x16])
def test_read_needs_enable_and_read_bits_before_team_access(flag):
    assert read(flag, team_ids=None, teams=None, captured=None) is None


@pytest.mark.parametrize("team_flag", [0x800, 0x80000, 0x80800, 1 << 61])
def test_read_culling_or_high_bit_skips_before_getters(team_flag):
    assert read(team_flag=team_flag, captured=None) is None


def test_read_bit1000_alone_does_not_skip():
    assert read(team_flag=0x1000) is not None


def test_read_team_zero_is_supported():
    assert read(team_ids=(0,), teams=(ReadRestoreTeam(0),)) is not None


def test_ordinary_read_preserves_local_values_matrix_and_single_then_double_position():
    result = read()
    assert result.world_position == (5, 6, 7)
    assert result.world_rotation == Q
    assert result.local_position == (1, 2, 3)
    assert result.local_rotation == Q
    assert result.scale == (-2, 3, 4)  # Signed diagonal, not column lengths/abs.
    assert result.local_to_world_matrix == MATRIX
    assert result.write_order == (
        "local_position",
        "local_rotation",
        "scale",
        "local_to_world_matrix",
        "world_position",
        "world_rotation",
        "local_to_world_matrix",
    )


def test_read_scale_removes_world_rotation_before_diagonal():
    # 180 deg Z, then scale(-2,3,4); matrix already supplied by native getter.
    matrix = ((2, 0, 0, 0), (0, -3, 0, 0), (0, 0, 4, 0), (11, 12, 13, 1))
    pose = replace(CAPTURE.pose, world_rotation=(0, 0, 1, 0))
    assert read(captured=CapturedTransform(pose, matrix)).scale == (-2, 3, 4)


def test_read_scale_is_signed_diagonal_even_for_shear_not_lossy_scale_guess():
    matrix = ((2, 7, 8, 0), (9, -3, 10, 0), (11, 12, 4, 0), (1, 2, 3, 1))
    assert read(captured=CapturedTransform(CAPTURE.pose, matrix)).scale == (2, -3, 4)


def test_getter_world_position_is_single_before_widening():
    pose = replace(CAPTURE.pose, world_position=(16777217, 0.1, 1))
    result = read(captured=CapturedTransform(pose, MATRIX))
    assert result.world_position[0] == 16777216
    assert result.world_position[1] == struct.unpack("<f", struct.pack("<f", 0.1))[0]


def test_read_relative_requires_resolved_inverse_not_identity_fallback():
    with pytest.raises(ValueError, match="relative"):
        read(teams=(None, ReadRestoreTeam(0, 1)))


@pytest.mark.parametrize("relative_gate", [1, 2, 2**31, 2**32 - 1])
def test_read_relative_inverse_changes_world_not_local_or_scale(relative_gate):
    inverse = ((1, 0, 0, 0), (0, 1, 0, 0), (0, 0, 1, 0), (-2, -3, -4, 1))
    context = RelativeReadContext(inverse, Q)
    result = read(teams=(None, ReadRestoreTeam(0, relative_gate)), relative=context)
    assert result.world_position == (3, 3, 3)
    assert result.local_position == (1, 2, 3)
    assert result.scale == (-2, 3, 4)
    assert result.local_to_world_matrix[3] == (9, 9, 9, 1)


def test_relative_rotation_multiplied_inverse_matrix_then_getter():
    pose = replace(CAPTURE.pose, world_rotation=(0, 1, 0, 0))
    result = read(
        captured=CapturedTransform(pose, MATRIX),
        teams=(None, ReadRestoreTeam(0, 1)),
        relative=RelativeReadContext(IDENTITY, (1, 0, 0, 0)),
    )
    assert result.world_rotation == (0, 0, 1, 0)


def test_read_nonrelative_does_not_read_relative_context():
    assert read(relative=object()).local_to_world_matrix == MATRIX


def test_component_read_only_validity_no_team_or_flag():
    assert read_component_position(
        transform_valid=True, position=(1.1, 2, 3)
    ) == pytest.approx((1.1, 2, 3))
    assert read_component_position(transform_valid=False, position=None) is None


def test_rotation_matrix_identity_and_nonunit_not_normalized():
    assert rotation_translation_matrix(Q, (3, 4, 5)) == IDENTITY[:3] + ((3, 4, 5, 1),)
    assert rotation_translation_matrix((2, 0, 0, 0), (0, 0, 0))[1][1] == -7


def test_matrix_mul_order_affine_columns_and_general_w():
    assert multiply_matrices(IDENTITY, MATRIX) == MATRIX
    swap = ((0, 1, 0, 0), (1, 0, 0, 0), (0, 0, 1, 0), (0, 0, 0, 1))
    assert multiply_matrices(swap, MATRIX)[3] == (12, 11, 13, 1)
    assert multiply_matrices(MATRIX, swap)[3] == (11, 12, 13, 1)
    matrix = IDENTITY[:3] + ((1, 2, 3, 4),)
    assert multiply_matrices(matrix, matrix)[3] == (5, 10, 15, 16)


@pytest.mark.parametrize("function", [restore, read])
@pytest.mark.parametrize("value", [None, 0, 1])
def test_validity_requires_actual_bool(function, value):
    with pytest.raises(ValueError, match="bool"):
        function(transform_valid=value)


@pytest.mark.parametrize("function", [restore, read])
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
def test_index_and_shape_rejection_adapter_policy(function, field, value):
    with pytest.raises(ValueError):
        function(**{field: value})


@pytest.mark.parametrize("function", [restore, read])
@pytest.mark.parametrize("flag", [-1, 2**64, True])
def test_team_flag_adapter_policy(function, flag):
    with pytest.raises(ValueError):
        function(team_flag=flag)


def test_restore_active_missing_buffer_slot_rejected():
    with pytest.raises(ValueError):
        restore(initial_local=LocalPose((), ()))


def test_restore_does_not_read_relative_switch():
    assert len(restore(teams=(None, ReadRestoreTeam(0, -1)))) == 2


def test_active_read_missing_capture_rejected():
    with pytest.raises(ValueError, match="getter"):
        read(captured=None)


@pytest.mark.parametrize("gate", [-1, True, 2**32])
def test_active_read_relative_gate_adapter_range(gate):
    with pytest.raises(ValueError):
        read(teams=(None, ReadRestoreTeam(0, gate)))


@pytest.mark.parametrize(
    "matrix", [(), (Q, Q, Q, (1, 2, 3)), (Q, Q, Q, (0, 0, float("inf"), 1))]
)
def test_active_matrix_shape_and_finite_rejection(matrix):
    with pytest.raises(ValueError):
        read(captured=CapturedTransform(CAPTURE.pose, matrix))


def test_relative_inverse_context_shape_rejected():
    with pytest.raises(ValueError):
        read(teams=(None, ReadRestoreTeam(0, 1)), relative=RelativeReadContext((), Q))


def test_component_validity_adapter_policy():
    with pytest.raises(ValueError, match="bool"):
        read_component_position(transform_valid=1, position=(0, 0, 0))


def test_zero_world_rotation_inverse_is_adapter_rejection_not_source_fallback():
    with pytest.raises(ValueError):
        read(
            captured=CapturedTransform(
                replace(CAPTURE.pose, world_rotation=(0, 0, 0, 0)), MATRIX
            )
        )
