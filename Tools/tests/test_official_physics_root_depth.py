"""Source-bound root/depth behavior tests, not a native runtime oracle."""

import math
import sys
from pathlib import Path
from typing import Any

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from official_physics_baseline_build import build_transform_baselines
from official_physics_proxy_baseline import reverse_inserted_children_no_resize
from official_physics_root_depth import evaluate_vertex_root_depth


def test_lengths_not_bone_count_and_global_not_per_root_normalization():
    result = evaluate_vertex_root_depth(
        [-1, 0, 1, -1, 3],
        [1, 2, 2, 1, 2],
        [(0, 0, 0), (0, 3, 0), (0, 7, 0), (10, 0, 0), (10, 2, 0)],
        [0.9] * 5,
    )
    assert result.roots == (-1, 0, 0, -1, 3)
    assert result.lengths == (0, 3, 7, 0, 2)
    assert result.maximum_length == 7
    assert result.depths == pytest.approx((0, 3 / 7, 1, 0, 2 / 7))


def test_first_nonmove_parent_is_root_not_global_topmost_transform():
    result = evaluate_vertex_root_depth(
        [-1, 0, 1, 2],
        [1, 2, 1, 2],
        [(0, 0, 0), (1, 0, 0), (3, 0, 0), (6, 0, 0)],
        [0] * 4,
    )
    assert result.roots == (-1, 0, -1, 2)
    assert result.lengths == (0, 1, 0, 3)
    assert result.depths == pytest.approx((0, 1 / 3, 0, 1))


def test_move_root_with_no_parent_and_descendant_root_is_last_visited_parent():
    result = evaluate_vertex_root_depth(
        [-2, 0, 1], [2] * 3, [(0, 0, 0), (0, 1, 0), (0, 4, 0)], [0] * 3
    )
    assert result.roots == (-1, 0, 0)
    assert result.lengths == (0, 1, 4)


@pytest.mark.parametrize("attribute", [0, 1, 4, 128, 129, 253])
def test_nonmove_vertex_ignores_its_valid_parent_and_keeps_no_root(attribute):
    result = evaluate_vertex_root_depth(
        [-1, 0], [1, attribute], [(0, 0, 0), (0, 5, 0)], [0.25, 0.75]
    )
    assert result.roots == (-1, -1)
    assert result.lengths == (0, 0)
    assert result.depths == (0.25, 0.75)


@pytest.mark.parametrize("attribute", [2, 3, 6, 130, 255])
def test_move_gate_is_bit_two_not_exact_enum(attribute):
    result = evaluate_vertex_root_depth(
        [-1, 0], [1, attribute], [(0, 0, 0), (0, 5, 0)], [0, 0]
    )
    assert result.roots == (-1, 0)
    assert result.depths == (0, 1)


@pytest.mark.parametrize("length", [0, 1e-9, 1e-8])
def test_small_global_length_preserves_caller_depth_buffer(length):
    result = evaluate_vertex_root_depth(
        [-1, 0], [1, 2], [(0, 0, 0), (length, 0, 0)], [0.25, 0.75]
    )
    assert result.depths == (0.25, 0.75)
    assert result.roots == (-1, 0)


def test_just_above_native_threshold_normalizes_all_slots():
    result = evaluate_vertex_root_depth(
        [-1, 0], [1, 2], [(0, 0, 0), (1.00001e-8, 0, 0)], [0.25, 0.75]
    )
    assert result.depths == (0, 1)


def test_coincident_vertex_keeps_parent_identity_despite_zero_length():
    result = evaluate_vertex_root_depth(
        [-1, 0, 1], [1, 2, 2], [(0, 0, 0), (0, 0, 0), (0, 3, 4)], [0] * 3
    )
    assert result.roots == (-1, 0, 0)
    assert result.lengths == (0, 0, 5)
    assert result.depths == (0, 0, 1)


def test_single_inputs_rounded_before_distance_subtraction():
    result = evaluate_vertex_root_depth(
        [-1, 0], [1, 2], [(16777216, 0, 0), (16777217, 0, 0)], [0.25, 0.75]
    )
    assert result.lengths == (0, 0)
    assert result.depths == (0.25, 0.75)


def test_single_length_accumulation_from_child_upward_not_parent_memoization():
    result = evaluate_vertex_root_depth(
        [-1, 0, 1, 2],
        [1, 2, 2, 2],
        [(16777216, 0, 0), (0, 0, 0), (1, 0, 0), (2, 0, 0)],
        [0] * 4,
    )
    assert result.lengths == (0, 16777216, 16777216, 16777218)


def test_non_topological_vertex_order():
    result = evaluate_vertex_root_depth(
        [2, -1, 1], [2, 1, 2], [(0, 5, 0), (0, 0, 0), (0, 2, 0)], [0] * 3
    )
    assert result.roots == (1, -1, 1)
    assert result.lengths == (5, 0, 2)


def test_empty_buffers():
    result = evaluate_vertex_root_depth([], [], [], [])
    assert result.roots == result.lengths == result.depths == ()
    assert result.maximum_length == 0


def test_join_with_ordered_baseline_builder_does_not_limit_depth_to_baseline_data():
    parents, attributes = [-1, 0, 1, 0, 3], [1, 2, 2, 1, 2]
    baselines = build_transform_baselines(
        parents, attributes, [0], reverse_inserted_children_no_resize(parents)
    )
    assert baselines.data == (0, 1, 2)
    result = evaluate_vertex_root_depth(
        parents,
        attributes,
        [(0, 0, 0), (0, 2, 0), (0, 4, 0), (10, 0, 0), (10, 8, 0)],
        [0] * 5,
    )
    assert result.roots == (-1, 0, 0, -1, 3)
    assert result.depths == (0, 0.25, 0.5, 0, 1)


@pytest.mark.parametrize("buffer", [0, 1, 2, 3])
def test_parallel_buffer_lengths(buffer):
    args: list[Any] = [[-1], [1], [(0, 0, 0)], [0]]
    args[buffer] = []
    with pytest.raises(ValueError):
        evaluate_vertex_root_depth(*args)


@pytest.mark.parametrize("parents", [[0], [1, 0], [1, -1, 2]])
def test_adapter_rejects_cycles_even_in_nonmove_data(parents):
    with pytest.raises(ValueError, match="cycle"):
        evaluate_vertex_root_depth(
            parents, [1] * len(parents), [(0, 0, 0)] * len(parents), [0] * len(parents)
        )


@pytest.mark.parametrize("parent", [True, 0.5, -(2**31) - 1, 2**31, 1])
def test_adapter_rejects_invalid_parent(parent):
    with pytest.raises(ValueError):
        evaluate_vertex_root_depth([parent], [1], [(0, 0, 0)], [0])


@pytest.mark.parametrize("attribute", [True, -1, 256, 2.5])
def test_adapter_rejects_invalid_attribute(attribute):
    with pytest.raises(ValueError):
        evaluate_vertex_root_depth([-1], [attribute], [(0, 0, 0)], [0])


@pytest.mark.parametrize("value", [math.nan, math.inf, True, 1e40])
@pytest.mark.parametrize("buffer", ["position", "depth"])
def test_adapter_rejects_nonfinite_or_unrepresentable_inputs(value, buffer):
    with pytest.raises(ValueError):
        evaluate_vertex_root_depth(
            [-1],
            [1],
            [(value, 0, 0)] if buffer == "position" else [(0, 0, 0)],
            [value] if buffer == "depth" else [0],
        )


def test_adapter_rejects_nonfinite_single_distance_intermediate():
    with pytest.raises(ValueError):
        evaluate_vertex_root_depth(
            [-1, 0], [1, 2], [(-3e38, 0, 0), (3e38, 0, 0)], [0, 0]
        )
