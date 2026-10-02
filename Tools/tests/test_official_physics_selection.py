"""Selection fixtures from reviewed scalar/control flow, not a live DLL oracle."""

import sys
from pathlib import Path
from typing import Any, cast

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from official_physics_selection import (
    convert_selection_attributes,
    generate_bone_selection,
)

IDENTITY = ((1, 0, 0, 0), (0, 1, 0, 0), (0, 0, 1, 0), (0, 0, 0, 1))


def test_generated_selection_positions_attributes_max_edge_and_user_edit():
    result = generate_bone_selection(
        IDENTITY, [(0, 0, 0), (3, 4, 0), (3, 4, 12)], [-1, 0, 1], [0]
    )
    assert result.positions == ((0, 0, 0), (3, 4, 0), (3, 4, 12))
    assert result.attributes == (1, 2, 2)
    assert result.max_connection_distance == 12
    assert result.user_edit is True


def test_matrix_changes_local_distances_not_world_distances():
    matrix = ((2, 0, 0, 0), (0, 3, 0, 0), (0, 0, 4, 0), (7, 8, 9, 1))
    result = generate_bone_selection(matrix, [(0, 0, 0), (1, 1, 1)], [-1, 0], [0])
    assert result.positions == ((7, 8, 9), (9, 11, 13))
    assert result.max_connection_distance == pytest.approx(5.385164737701416, abs=0)


def test_fixed_roots_are_explicit_not_all_parentless_nodes():
    result = generate_bone_selection(
        IDENTITY, [(0, 0, 0)] * 3, [-1, -1, 0], [2, None, 2]
    )
    assert result.attributes == (2, 2, 1)


def test_fixed_edges_still_contribute_maximum_connection_distance():
    result = generate_bone_selection(IDENTITY, [(0, 0, 0), (0, 0, 5)], [-1, 0], [0, 1])
    assert result.attributes == (1, 1) and result.max_connection_distance == 5


def test_parent_after_child_is_legal_and_no_parent_first_sort():
    result = generate_bone_selection(IDENTITY, [(0, 0, 3), (0, 0, 0)], [1, -1], [1])
    assert result.attributes == (2, 1) and result.max_connection_distance == 3


def test_unlinked_vertices_do_not_contribute_or_use_bbox_width():
    result = generate_bone_selection(IDENTITY, [(0, 0, 0), (100, 0, 0)], [-1, -1], [])
    assert result.max_connection_distance == 0


def test_empty_selection_has_no_fabricated_center_vertex():
    result = generate_bone_selection(IDENTITY, [], [], [])
    assert result.positions == result.attributes == ()
    assert result.max_connection_distance == 0 and result.user_edit


def test_subtraction_and_dot_products_are_single_not_double():
    result = generate_bone_selection(
        IDENTITY, [(16777216, 0, 0), (16777217, 0, 0)], [-1, 0], [0]
    )
    assert result.max_connection_distance == 0


def test_match_within_radius_uses_nearest_position_not_slot_or_name():
    result = convert_selection_attributes(
        [(0, 0, 0), (5, 0, 0)],
        [(5, 0, 0), (0, 0, 0), (9, 0, 0)],
        [17, 130, 2],
        1,
        [[0, 1, 2], [0, 1, 2]],
    )
    assert result == (130, 17)


def test_radius_is_inclusive_and_unmatched_is_invalid_zero():
    assert convert_selection_attributes([(0, 0, 0)], [(1, 0, 0)], [2], 1, [[0]]) == (2,)
    assert convert_selection_attributes([(0, 0, 0)], [(1.01, 0, 0)], [2], 1, [[0]]) == (
        0,
    )


def test_equal_distance_later_candidate_wins_preserve_native_enumeration_order():
    args = ([(0, 0, 0)], [(-1, 0, 0), (1, 0, 0)], [1, 2], 2)
    assert convert_selection_attributes(*args, [[0, 1]]) == (2,)
    assert convert_selection_attributes(*args, [[1, 0]]) == (1,)


def test_farther_candidate_cannot_overwrite_nearer_even_with_higher_flag():
    assert convert_selection_attributes(
        [(0, 0, 0)], [(1, 0, 0), (2, 0, 0)], [1, 255], 3, [[0, 1]]
    ) == (1,)


def test_exact_matches_with_zero_radius_and_invalid_attribute_can_win():
    assert convert_selection_attributes(
        [(0, 0, 0)], [(0, 0, 0)] * 2, [255, 0], 0, [[0, 1]]
    ) == (0,)


def test_empty_source_or_empty_candidates_produce_invalid_not_move_default():
    assert convert_selection_attributes([(0, 0, 0)], [], [], 1, [[]]) == (0,)
    assert convert_selection_attributes([(0, 0, 0)], [(0, 0, 0)], [2], 1, [[]]) == (0,)
    assert convert_selection_attributes([], [], [], 0, []) == ()


def test_kernel_does_not_invent_grid_candidates_or_scan_all_source_points():
    assert convert_selection_attributes(
        [(0, 0, 0)], [(0, 0, 0), (1, 0, 0)], [1, 2], 2, [[1]]
    ) == (2,)


@pytest.mark.parametrize("radius", [-1, float("inf"), float("nan")])
def test_bad_radius_rejected_by_adapter(radius):
    with pytest.raises(ValueError):
        convert_selection_attributes([], [], [], radius, [])


@pytest.mark.parametrize("attribute", [-1, 256, True, 1.5])
def test_bad_attribute_rejected_by_adapter(attribute):
    with pytest.raises(ValueError):
        convert_selection_attributes([], [(0, 0, 0)], [cast(Any, attribute)], 0, [])


@pytest.mark.parametrize("index", [-1, 1, True, 1.5])
def test_bad_candidate_rejected_by_adapter(index):
    with pytest.raises(ValueError):
        convert_selection_attributes(
            [(0, 0, 0)], [(0, 0, 0)], [1], 0, [[cast(Any, index)]]
        )


@pytest.mark.parametrize("parent", [True, 1.5, -(2**31) - 1, 2**31])
def test_non_int32_parent_rejected_by_adapter(parent):
    with pytest.raises(ValueError, match="Int32 parents"):
        generate_bone_selection(IDENTITY, [(0, 0, 0)], [cast(Any, parent)], [0])


@pytest.mark.parametrize(
    "case",
    [
        "parent_length",
        "parent_invalid",
        "cycle",
        "root_invalid",
        "matrix",
        "nonfinite",
        "capacity",
    ],
)
def test_bad_generation_contracts(case):
    matrix, positions, parents, roots = IDENTITY, [(0, 0, 0)], [-1], [0]
    if case == "parent_length":
        parents = []
    elif case == "parent_invalid":
        parents = [1]
    elif case == "cycle":
        parents = [0]
    elif case == "root_invalid":
        roots = [1]
    elif case == "matrix":
        matrix = ()
    elif case == "nonfinite":
        positions = [(float("nan"), 0, 0)]
    else:
        positions, parents = [(0, 0, 0)] * 65536, [-1] * 65536
    with pytest.raises(ValueError):
        generate_bone_selection(cast(Any, matrix), positions, parents, roots)


@pytest.mark.parametrize(
    "case", ["source_lengths", "candidate_lengths", "nonfinite", "capacity"]
)
def test_bad_conversion_contracts(case):
    targets, positions, attrs, candidates = [(0, 0, 0)], [(0, 0, 0)], [1], [[0]]
    if case == "source_lengths":
        attrs = []
    elif case == "candidate_lengths":
        candidates = []
    elif case == "nonfinite":
        targets = [(0, float("inf"), 0)]
    else:
        targets, candidates = [(0, 0, 0)] * 65536, [[]] * 65536
    with pytest.raises(ValueError):
        convert_selection_attributes(targets, positions, attrs, 1, candidates)


def test_generation_then_conversion_keeps_generated_data_immutable():
    selection = generate_bone_selection(IDENTITY, [(0, 0, 0), (1, 0, 0)], [-1, 0], [0])
    assert convert_selection_attributes(
        [(1, 0, 0), (0, 0, 0)], selection.positions, selection.attributes, 0, [[1], [0]]
    ) == (2, 1)
    assert selection.attributes == (1, 2)
