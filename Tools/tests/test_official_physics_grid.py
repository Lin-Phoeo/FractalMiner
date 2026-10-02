"""Source-flow fixtures; not a live native/Burst oracle."""

import math
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from official_physics_grid import (
    build_fresh_selection_grid,
    convert_fresh_selection_grid,
    grid_area_cells,
    grid_cell,
    selection_search_parameters,
)
from official_physics_selection import generate_bone_selection


def test_target_aabb_max_side_radius_and_half_sized_grid():
    result = selection_search_parameters([(2, 3, 4), (-3, 5, 6)])
    assert result.minimum == (-3, 3, 4)
    assert result.maximum == (2, 5, 6)
    assert result.max_side_length == 5
    assert result.radius == 1 and result.grid_size == 0.5


def test_radius_floor_for_single_vertex_and_coincident_targets():
    result = selection_search_parameters([(7, 8, 9)] * 2)
    assert result.max_side_length == 0
    assert result.radius == 9.999999747378752e-6
    assert result.grid_size == 4.999999873689376e-6


def test_aabb_first_rounds_input_positions_to_single():
    result = selection_search_parameters([(16777216, 0, 0), (16777217, 0, 0)])
    assert result.max_side_length == 0


def test_equal_aabb_extrema_take_last_candidate_including_signed_zero():
    result = selection_search_parameters([(0, 0, 0), (-0.0, -0.0, -0.0)])
    assert all(
        math.copysign(1, value) == -1 for value in result.minimum + result.maximum
    )


def test_double_extent_exceeding_single_range_rejected_by_adapter():
    with pytest.raises(ValueError):
        selection_search_parameters([(-3e38, 0, 0), (3e38, 0, 0)])


def test_grid_uses_floor_including_negative_and_boundary_coordinates():
    assert grid_cell((-0.01, -1, 1), 1) == (-1, -1, 1)
    assert grid_cell((-1.01, 0.99, 0), 1) == (-2, 0, 0)
    assert grid_cell((2, 4, 6), 2) == (1, 2, 3)


def test_cell_division_rounds_to_single_before_floor():
    # Binary64 division is just below 5; native divss rounds it to exactly 5.
    assert grid_cell((0.5, 0, 0), 0.1) == (5, 0, 0)


def test_area_inclusive_x_fastest_then_y_then_z():
    cells = grid_area_cells((0.5, 0.5, 0.5), 0.5, 1)
    assert cells == (
        (0, 0, 0),
        (1, 0, 0),
        (0, 1, 0),
        (1, 1, 0),
        (0, 0, 1),
        (1, 0, 1),
        (0, 1, 1),
        (1, 1, 1),
    )


def test_zero_radius_area_has_exactly_one_cell():
    assert grid_area_cells((-0.5, 0, 0), 0, 1) == ((-1, 0, 0),)


def test_fresh_sequential_bucket_is_head_insert_not_source_index_order():
    grid = build_fresh_selection_grid([(0, 0, 0), (0.01, 0, 0), (1, 0, 0)], 1)
    assert grid == {(0, 0, 0): (1, 0), (1, 0, 0): (2,)}
    assert build_fresh_selection_grid([], 1) == {}


def test_same_cell_equal_distance_later_native_candidate_is_earlier_source():
    assert convert_fresh_selection_grid([(0, 0, 0)], [(0, 0, 0)] * 2, [1, 130]) == (1,)


def test_different_cell_tie_respects_cell_order_not_source_order():
    targets = [(0, 0, 0), (1, 0, 0)]
    assert convert_fresh_selection_grid(
        targets, [(0.01, 0, 0), (-0.01, 0, 0)], [2, 1]
    ) == (2, 0)


def test_match_radius_from_targets_not_sources_or_saved_max_edge():
    assert convert_fresh_selection_grid(
        [(0, 0, 0)], [(0.01, 0, 0), (100, 0, 0)], [1, 2]
    ) == (0,)


def test_empty_cells_and_invalid_source_byte_preserved():
    assert convert_fresh_selection_grid([(0, 0, 0), (1, 0, 0)], [(0, 0, 0)], [0]) == (
        0,
        0,
    )


def test_generation_through_fresh_grid_matching_without_supplied_candidates():
    identity = ((1, 0, 0, 0), (0, 1, 0, 0), (0, 0, 1, 0), (0, 0, 0, 1))
    selection = generate_bone_selection(identity, [(0, 0, 0), (1, 0, 0)], [-1, 0], [0])
    assert convert_fresh_selection_grid(
        [(1, 0, 0), (0, 0, 0)], selection.positions, selection.attributes
    ) == (2, 1)
    assert selection.attributes == (1, 2)


@pytest.mark.parametrize("size", [0, -1, float("inf"), float("nan"), 1e-50])
def test_bad_grid_size_rejected(size):
    with pytest.raises(ValueError):
        grid_cell((0, 0, 0), size)


@pytest.mark.parametrize("radius", [-1, float("inf"), float("nan")])
def test_bad_radius_rejected(radius):
    with pytest.raises(ValueError):
        grid_area_cells((0, 0, 0), radius, 1)


@pytest.mark.parametrize(
    "point", [(float("nan"), 0, 0), (2**31, 0, 0), (-(2**31) - 256, 0, 0)]
)
def test_nonfinite_or_nonrepresentable_cell_rejected(point):
    with pytest.raises(ValueError):
        grid_cell(point, 1)


def test_area_iteration_safety_cap_not_native_allocation_limit():
    with pytest.raises(ValueError, match="cell budget"):
        grid_area_cells((0, 0, 0), 100, 1)


@pytest.mark.parametrize("positions", [[], [(float("inf"), 0, 0)], [(0, 0, 0)] * 65536])
def test_search_parameter_input_rejected(positions):
    with pytest.raises(ValueError):
        selection_search_parameters(positions)


@pytest.mark.parametrize(
    "targets,sources,attrs",
    [
        ([], [(0, 0, 0)], [1]),
        ([(0, 0, 0)], [], []),
        ([(0, 0, 0)], [(0, 0, 0)], []),
        ([(0, 0, 0)], [(0, 0, 0)], [256]),
    ],
)
def test_matcher_rejects_empty_native_noop_domain_and_bad_attributes(
    targets, sources, attrs
):
    with pytest.raises(ValueError):
        convert_fresh_selection_grid(targets, sources, attrs)


def test_source_grid_capacity_rejected():
    with pytest.raises(ValueError):
        build_fresh_selection_grid([(0, 0, 0)] * 65536, 1)
