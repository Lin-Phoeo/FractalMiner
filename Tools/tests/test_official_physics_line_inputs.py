"""Finite Line import statistics and saved matching, not native execution."""

import math
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from official_physics_line_inputs import (
    build_bone_lines,
    line_distance_metrics,
    match_saved_line_selection,
)
from official_physics_saved_selection import SavedSelection


def test_line_order_is_child_loop_with_sorted_endpoints_and_missing_parent_skipped():
    assert build_bone_lines((-1, 3, 0, -1), 0) == ((1, 3), (0, 2))
    assert build_bone_lines((1, 0), 0) == ((0, 1), (0, 1))  # no deduplication


@pytest.mark.parametrize("mode", [1, 2, 3, True, -1])
def test_non_line_mode_refused(mode):
    with pytest.raises(ValueError):
        build_bone_lines((-1,), mode)


@pytest.mark.parametrize("parent", [True, 1.5, -2, 2, 2**31])
def test_invalid_parent_refused(parent):
    with pytest.raises(ValueError):
        build_bone_lines((-1, parent), 0)


def test_rms_length_is_not_mean_length_or_squared_length():
    result = line_distance_metrics(((0, 0, 0), (1, 0, 0), (3, 0, 0)), ((0, 1), (0, 2)))
    assert result.sampled_line_count == 2 and result.sampling_stride == 1
    assert result.sum_squared_lengths == 10
    assert result.average_vertex_distance == pytest.approx(math.sqrt(5), abs=2e-7)
    assert result.max_vertex_distance == 3


@pytest.mark.parametrize(
    "count,stride,samples",
    [
        (0, 1, 0),
        (99, 1, 99),
        (100, 1, 100),
        (199, 1, 199),
        (200, 2, 100),
        (301, 3, 101),
    ],
)
def test_original_sparse_sampling_not_first_hundred(count, stride, samples):
    positions = tuple((float(i), 0, 0) for i in range(count + 1))
    lines = tuple((0, i + 1) for i in range(count))
    result = line_distance_metrics(positions, lines)
    assert (result.sampling_stride, result.sampled_line_count) == (stride, samples)
    assert result.max_vertex_distance == (
        float(1 + ((count - 1) // stride) * stride) if count else 0
    )


@pytest.mark.parametrize(
    "positions,lines",
    [
        (((0, 0),), ()),
        (((float("nan"), 0, 0),), ()),
        (((0, 0, 0),), ((0, 1),)),
        (((0, 0, 0),), ((0,),)),
        (((0, 0, 0),), ((True, 0),)),
    ],
)
def test_bad_line_buffers_refused(positions, lines):
    with pytest.raises(ValueError):
        line_distance_metrics(positions, lines)


def test_saved_different_count_useredit_false_preserved_and_spatially_matched():
    saved = SavedSelection(((9, 0, 0), (0, 0, 0), (1, 0, 0)), (4, 1, 2), 0.01, False)
    output = match_saved_line_selection(
        ((0, 0, 0), (1, 0, 0)), (-1, 0), saved, resolved_bone_overrides=()
    )
    assert output.matched_selection_bytes == (1, 2)
    assert output.selection.positions == saved.positions
    assert output.selection.attributes == saved.attributes
    assert output.selection.user_edit is False and output.selection is not saved
    assert output.selection.max_connection_distance == pytest.approx(0.01)
    assert output.selection.positions is not None
    assert len(output.selection.positions) == 3
    assert output.search.radius == 1 and output.search.grid_size == 1.5


def test_valid_saved_root_not_forced_fixed_and_overrides_are_selection_indices():
    saved = SavedSelection(((1, 0, 0), (0, 0, 0)), (2, 2), 0.1, True)
    output = match_saved_line_selection(
        ((0, 0, 0), (1, 0, 0)),
        (-1, 0),
        saved,
        resolved_bone_overrides=((0, 1), (-1, 4)),
    )
    assert output.matched_selection_bytes == (2, 1)
    assert saved.attributes == (2, 2)


def test_same_cell_reverse_insertion_ties_and_invalid_winner_retained():
    saved = SavedSelection(((0, 0, 0), (0, 0, 0)), (0, 2), 1, False)
    output = match_saved_line_selection(
        ((0, 0, 0),), (-1,), saved, resolved_bone_overrides=()
    )
    assert output.native_candidates == ((1, 0),)
    assert output.matched_selection_bytes == (0,)


def test_missing_match_remains_invalid_not_move_default():
    saved = SavedSelection(((8, 0, 0),), (2,), 0.1, False)
    output = match_saved_line_selection(
        ((0, 0, 0),), (-1,), saved, resolved_bone_overrides=()
    )
    assert output.matched_selection_bytes == (0,)


def test_saved_radius_dominates_line_metric_without_coordinate_transform():
    saved = SavedSelection(((0, 1, 0),), (1,), 2, False)
    output = match_saved_line_selection(
        ((0, 0, 0),), (-1,), saved, resolved_bone_overrides=()
    )
    assert output.search.radius == 2 and output.matched_selection_bytes == (1,)


def test_invalid_saved_or_mismatched_windows_explicitly_refused():
    with pytest.raises(ValueError):
        match_saved_line_selection(
            ((0, 0, 0),),
            (),
            SavedSelection(((0, 0, 0),), (1,), 1, False),
            resolved_bone_overrides=(),
        )
    with pytest.raises(ValueError):
        match_saved_line_selection(
            ((0, 0, 0),),
            (-1,),
            SavedSelection(None, None, 1, False),
            resolved_bone_overrides=(),
        )
