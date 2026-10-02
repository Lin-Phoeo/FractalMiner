"""Finite source-flow fixtures, not a running Unity/native oracle."""

import math
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from official_physics_grid import convert_fresh_selection_grid
from official_physics_snapshot import (
    TransformGetterValues,
    multiply_matrices_single,
    prepare_snapshot_bone_inputs,
    read_transform_snapshot,
    read_transform_snapshots,
    rotation_matrix_single,
)

IDENTITY = ((1, 0, 0, 0), (0, 1, 0, 0), (0, 0, 1, 0), (0, 0, 0, 1))
Q = (0, 0, 0, 1)


def getter(position=(1, 2, 3), rotation=Q, matrix=IDENTITY):
    return TransformGetterValues(position, rotation, matrix, (4, 5, 6), (1, 2, 3, 4))


def test_world_and_local_buffers_are_distinct_raw_single_copies():
    result = read_transform_snapshot(getter((16777217, -0.0, 3)))
    assert result.position == (16777216, 0, 3)
    assert math.copysign(1, result.position[1]) == -1
    assert result.rotation == Q
    assert result.local_position == (4, 5, 6)
    assert result.local_rotation == (1, 2, 3, 4)  # Never normalize local q.
    assert result.scale == (1, 1, 1)
    assert result.inverse_rotation == (0, 0, 0, 1)


def test_signed_scale_and_shear_take_diagonal_not_column_lengths():
    matrix = ((-2, 7, 8, 0), (9, 3, 10, 0), (11, 12, 4, 0), (20, 30, 40, 1))
    assert read_transform_snapshot(getter(matrix=matrix)).scale == (-2, 3, 4)


def test_inverse_world_rotation_is_removed_before_scale_diagonal():
    # Deliberately nonunit q: inverse=(0,0,-.5,.5), no hidden normalization.
    matrix = ((0, 2, 0, 0), (-3, 0, 0, 0), (0, 0, 4, 0), (8, 9, 10, 1))
    result = read_transform_snapshot(getter(rotation=(0, 0, 1, 1), matrix=matrix))
    assert result.scale == (1, 1.5, 4)
    assert result.rotation == (0, 0, 1, 1)
    assert result.inverse_rotation == (0, 0, -0.5, 0.5)


@pytest.mark.parametrize(
    "q, expected",
    [
        (Q, IDENTITY),
        ((1, 0, 0, 0), ((1, 0, 0, 0), (0, -1, 0, 0), (0, 0, -1, 0), (0, 0, 0, 1))),
        ((0, 1, 0, 0), ((-1, 0, 0, 0), (0, 1, 0, 0), (0, 0, -1, 0), (0, 0, 0, 1))),
        ((0, 0, 1, 0), ((-1, 0, 0, 0), (0, -1, 0, 0), (0, 0, 1, 0), (0, 0, 0, 1))),
        (
            (1, 2, 3, 4),
            ((-25, 28, -10, 0), (-20, -19, 20, 0), (22, 4, -9, 0), (0, 0, 0, 1)),
        ),
    ],
)
def test_rotation_constructor_column_signs_and_no_normalization(q, expected):
    assert rotation_matrix_single(q) == expected


def test_matrix_product_has_left_associated_single_adds_no_fma():
    left = ((16777216, 0, 0, 0), (1, 0, 0, 0), (-16777216, 0, 0, 0), (1, 0, 0, 0))
    right = ((1, 1, 1, 1),) * 4
    assert multiply_matrices_single(left, right) == ((1, 0, 0, 0),) * 4


def test_matrix_product_general_four_columns():
    left = ((1, 2, 3, 4), (5, 6, 7, 8), (9, 10, 11, 12), (13, 14, 15, 16))
    right = ((1, 2, 3, 4), (4, 3, 2, 1), (0, 1, 0, 0), (0, 0, 0, 1))
    assert multiply_matrices_single(left, right) == (
        (90, 100, 110, 120),
        (50, 60, 70, 80),
        (5, 6, 7, 8),
        (13, 14, 15, 16),
    )


def test_invalid_transform_retains_previous_slot_without_reading_values():
    previous = read_transform_snapshot(getter())
    assert read_transform_snapshot(None, previous) is previous
    result = read_transform_snapshots([None, getter((7, 8, 9))], [previous, None])
    assert result[0] is previous
    assert result[1].position == (7, 8, 9)


def test_invalid_without_prior_storage_is_refused_not_zero_filled():
    with pytest.raises(ValueError, match="previous"):
        read_transform_snapshot(None)


def test_mismatched_previous_storage_is_refused():
    with pytest.raises(ValueError, match="parallel"):
        read_transform_snapshots([getter()], [])


def test_empty_snapshot_read_is_supported():
    assert read_transform_snapshots([]) == ()


def test_skin_only_snapshots_feed_selection_frames_and_fresh_grid():
    samples = [getter((10, 0, 0)), getter((10, 2, 0))]
    wtol = ((1, 0, 0, 0), (0, 1, 0, 0), (0, 0, 1, 0), (-10, 0, 0, 1))
    result = prepare_snapshot_bone_inputs(samples, wtol, [-1, 0], [0])
    assert result.selection.positions == ((0, 0, 0), (0, 2, 0))
    assert result.selection.attributes == (1, 2)
    assert result.selection.max_connection_distance == 2
    assert result.frames.positions == result.selection.positions
    assert result.frames.normals == ((0, 1, 0),) * 2
    assert result.snapshots[0].scale == (1, 1, 1)
    assert convert_fresh_selection_grid(
        result.frames.positions, result.selection.positions, result.selection.attributes
    ) == (1, 2)


def test_composed_input_can_keep_prior_invalid_slot():
    prior = read_transform_snapshot(getter((2, 3, 4)))
    result = prepare_snapshot_bone_inputs([None], IDENTITY, [-1], [0], [prior])
    assert result.snapshots == (prior,)
    assert result.selection.positions == ((2, 3, 4),)


@pytest.mark.parametrize("value", [float("nan"), float("inf"), True, 1e40])
def test_invalid_world_position_is_adapter_rejection(value):
    with pytest.raises(ValueError):
        read_transform_snapshot(getter((value, 0, 0)))


@pytest.mark.parametrize(
    "field", ["rotation", "local_rotation", "local_position", "local_to_world"]
)
def test_malformed_getters_are_adapter_rejection(field):
    from dataclasses import replace

    with pytest.raises(ValueError):
        read_transform_snapshot(replace(getter(), **{field: (1, 2)}))


def test_zero_world_quaternion_is_adapter_rejection_not_native_claim():
    with pytest.raises(ValueError):
        read_transform_snapshot(getter(rotation=(0, 0, 0, 0)))


def test_rotation_constructor_overflow_is_refused():
    with pytest.raises(ValueError):
        rotation_matrix_single((3e38, 0, 0, 1))


def test_matrix_intermediate_overflow_is_refused():
    with pytest.raises(ValueError):
        multiply_matrices_single(((3e38, 0, 0, 0),) * 4, ((2, 0, 0, 0),) * 4)
