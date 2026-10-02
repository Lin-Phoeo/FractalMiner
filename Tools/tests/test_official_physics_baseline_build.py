"""Synthetic native-control-flow fixtures, not an executed official DLL oracle."""

import sys
from pathlib import Path
from typing import Any, cast

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from official_physics_angle_baseline import TeamWindow, resolve_baseline
from official_physics_baseline_build import build_transform_baselines


def test_empty_input_has_no_fabricated_baseline():
    result = build_transform_baselines([], [], [], [])
    assert (result.flags, result.starts, result.counts, result.data) == ((), (), (), ())


@pytest.mark.parametrize("attribute", range(256))
def test_candidate_move_mask_only_not_fixed_or_other_flag_veto(attribute):
    result = build_transform_baselines([-1, 0], [attribute, 2], [0], [[1], []])
    assert result.data == (() if attribute & 2 else (0, 1))


def test_nonmove_does_not_require_fixed_bit():
    result = build_transform_baselines([-1, 0], [0, 3], [0], [[1], []])
    assert result.data == (0, 1)  # child contradictory Fixed+Move is still movable
    assert (result.starts, result.counts, result.flags) == ((0,), (2,), (1,))


def test_search_through_nonmove_ancestors_until_immediate_move_child():
    result = build_transform_baselines(
        [-1, 0, 1, 2], [1, 0, 4, 2], [0], [[1], [2], [3], []]
    )
    assert result.data == (2, 3)  # original root is NOT the baseline first vertex


def test_outer_candidate_search_is_lifo_not_bfs_or_sorted():
    result = build_transform_baselines(
        [-1, 0, 0, 1, 2], [0, 0, 0, 2, 2], [0], [[2, 1], [3], [4], [], []]
    )
    assert result.data == (1, 3, 2, 4)
    assert (result.starts, result.counts) == ((0, 2), (2, 2))


def test_inner_move_traversal_is_lifo_depth_first_not_presorted():
    result = build_transform_baselines(
        [-1, 0, 0, 1, 2, 1],
        [0, 2, 2, 2, 2, 2],
        [0],
        [[2, 1], [5, 3], [4], [], [], []],
    )
    assert result.data == (0, 1, 3, 5, 2, 4)


def test_opposite_child_enumeration_changes_output_not_normalized():
    args = ([-1, 0, 0], [0, 2, 2], [0])
    first = build_transform_baselines(*args, [[1, 2], [], []])
    second = build_transform_baselines(*args, [[2, 1], [], []])
    assert first.data == (0, 2, 1)
    assert second.data == (0, 1, 2)


def test_move_candidate_skips_its_entire_subtree():
    result = build_transform_baselines([-1, 0, 1], [2, 0, 2], [0], [[1], [2], []])
    assert result.data == ()


def test_nonmove_leaf_does_not_create_one_vertex_group():
    result = build_transform_baselines([-1], [1], [0], [[]])
    assert result.data == ()


def test_started_baseline_does_not_search_fixed_siblings_or_cross_fixed_child():
    result = build_transform_baselines(
        [-1, 0, 0, 1, 2, 3],
        [1, 2, 1, 1, 2, 2],
        [0],
        [[1, 2], [3], [4], [5], [], []],
    )
    assert result.data == (0, 1)  # 2->4 and 3->5 are not discovered here
    explicit = build_transform_baselines(
        [-1, 0, 0, 1, 2, 3],
        [1, 2, 1, 1, 2, 2],
        [0, 2, 3],
        [[1, 2], [3], [4], [5], [], []],
    )
    assert explicit.data == (0, 1, 2, 4, 3, 5)


def test_root_list_order_and_duplicates_preserved_no_global_visited_dedup():
    result = build_transform_baselines(
        [-1, -1, 0, 1], [1, 0, 2, 2], [1, 0, 1], [[2], [3], [], []]
    )
    assert result.data == (1, 3, 0, 2, 1, 3)
    assert (result.starts, result.counts) == ((0, 2, 4), (2, 2, 2))


def test_selected_nonforestroot_can_be_a_baseline_root():
    result = build_transform_baselines([-1, 0, 1], [2, 0, 2], [1], [[1], [2], []])
    assert result.data == (1, 2)  # no inferred parent=-1 root rule


@pytest.mark.parametrize(
    "attrs, expected", [([128, 130], 0), ([0, 130], 1), ([128, 2], 1)]
)
def test_include_line_flag_considers_root_and_each_visited_node(attrs, expected):
    result = build_transform_baselines([-1, 0], attrs, [0], [[1], []])
    assert result.flags == (expected,)


def test_omitted_fixed_nodes_do_not_contribute_include_line_flag():
    result = build_transform_baselines([-1, 0, 0], [128, 130, 0], [0], [[1, 2], [], []])
    assert (result.data, result.flags) == ((0, 1), (0,))


def test_negative_parent_int32_not_only_minus_one():
    result = build_transform_baselines([-(2**31), 0], [0, 2], [0], [[1], []])
    assert result.data == (0, 1)


@pytest.mark.parametrize("bad", [True, 2.0, "2", -1, 256])
def test_bad_byte_attribute_rejected_even_if_unreachable(bad: Any):
    with pytest.raises(ValueError):
        build_transform_baselines([-1], [bad], [], [[]])


@pytest.mark.parametrize("bad", [True, 0.0, "0", -(2**31) - 1, 2**31, 1])
def test_bad_parent_type_range_or_outside_vertex_buffer(bad: Any):
    with pytest.raises(ValueError):
        build_transform_baselines([bad], [0], [], [[]])


@pytest.mark.parametrize("bad", [True, 0.0, "0", -1, 1])
def test_bad_root_rejected(bad: Any):
    with pytest.raises(ValueError):
        build_transform_baselines([-1], [0], [bad], [[]])


@pytest.mark.parametrize("bad", [True, 1.0, "1", -1, 2])
def test_bad_child_rejected(bad: Any):
    with pytest.raises(ValueError):
        build_transform_baselines([-1, 0], [0, 2], [0], [[bad], []])


@pytest.mark.parametrize("children", [[[], []], [[1, 1], []], [[], [1]], [[0, 1], []]])
def test_missing_duplicate_or_wrong_parent_child_map_is_adapter_error(children):
    with pytest.raises(ValueError):
        build_transform_baselines([-1, 0], [0, 2], [0], children)


@pytest.mark.parametrize("parents, children", [([0], [[0]]), ([1, 0], [[1], [0]])])
def test_cycle_rejected_even_if_no_roots_instead_of_unbounded_native_traversal(
    parents, children
):
    with pytest.raises(ValueError, match="cycle"):
        build_transform_baselines(parents, [0] * len(parents), [], children)


@pytest.mark.parametrize(
    "attributes, children", [([], [[]]), ([0], []), ([0, 2], [[]])]
)
def test_input_parallel_buffers_must_match_vertex_count(attributes, children):
    with pytest.raises(ValueError):
        build_transform_baselines([-1], attributes, [], children)


def test_uint16_highest_vertex_is_valid_but_unrepresentable_vertex_count_rejected():
    parents = [-1] * 65536
    parents[-1] = 0
    attrs = [0] * 65536
    attrs[-1] = 2
    children = [[] for _ in parents]
    children[0] = [65535]
    result = build_transform_baselines(parents, attrs, [0], children)
    assert result.data == (0, 65535)
    with pytest.raises(ValueError):
        build_transform_baselines([-1] * 65537, [0] * 65537, [], [[]] * 65537)


def test_longest_representable_baseline_count_and_count_wrap_rejection():
    parents = [-1] + list(range(65535))
    attrs = [0] + [2] * 65535
    children = [[i + 1] for i in range(65535)] + [[]]
    # No recursion limit; 65535 count fits, 65536 would wrap native UInt16 to zero.
    partial = build_transform_baselines(
        parents[:-1], attrs[:-1], [0], children[:-2] + [[]]
    )
    assert partial.counts == (65535,)
    with pytest.raises(ValueError, match="count"):
        build_transform_baselines(parents, attrs, [0], children)


def test_start_uint16_limit_is_separate_from_end_offset():
    result = build_transform_baselines([-1, 0], [0, 2], [0] * 32768, [[1], []])
    assert result.starts[-1] == 65534
    assert len(result.data) == 65536  # native count is separate; no false total cap
    with pytest.raises(ValueError, match="start"):
        build_transform_baselines([-1, 0], [0, 2], [0] * 32769, [[1], []])


def test_inputs_unchanged_and_output_is_immutable():
    parents, attrs, roots, children = [-1, 0], [0, 2], [0], [[1], []]
    result = build_transform_baselines(parents, attrs, roots, children)
    assert (parents, attrs, roots, children) == ([-1, 0], [0, 2], [0], [[1], []])
    with pytest.raises(AttributeError):
        cast(Any, result).data = ()


def test_builder_outputs_feed_existing_three_space_adapter_without_artistic_root_fix():
    parents, attrs = [-1, 0, 1, 1], [0, 0, 2, 2]
    built = build_transform_baselines(parents, attrs, [0], [[1], [2, 3], [], []])
    window = TeamWindow(10, 4, 6, 4, 2, len(built.data))
    plan = resolve_baseline(
        (1 << 16) | 3,
        [window, window],
        [65535] * 3 + list(built.starts),
        [65535] * 3 + list(built.counts),
        [65535] * 2 + list(built.data),
        [999] * 6 + parents,
        [255] * 6 + attrs,
        [0] * 6 + [0, 0, 0.5, 1],
    )
    assert [
        (v.local_index, v.particle_index, v.parent_particle_index)
        for v in plan.vertices
    ] == [(1, 11, None), (3, 13, 11), (2, 12, 11)]
