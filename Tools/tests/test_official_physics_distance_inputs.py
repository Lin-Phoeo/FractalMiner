"""Fresh Line adjacency/rest production: source order, gates and Single seams."""

import copy
import math
import struct
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from official_physics_distance_inputs import (
    build_distance_inputs,
    build_line_connectivity,
)


def graph(count, lines):
    return build_line_connectivity(count, lines, fresh_serial_no_resize=True)


def single(value):
    return struct.unpack("<f", struct.pack("<f", value))[0]


def produce(positions, parents, attrs, rows):
    return build_distance_inputs(
        positions,
        parents,
        attrs,
        rows,
        fresh_serial_no_resize=True,
        zero_triangle_edge_map=True,
    )


def test_line_unique_bidirectional_head_order_not_sorted():
    lines = [(0, 2), (0, 1), (0, 3), (0, 2), (1, 0)]
    before = copy.deepcopy(lines)
    result = graph(4, lines)
    assert result.rows == ((3, 1, 2), (0,), (0,), (0,))
    assert result.words == ((3 << 20), (1 << 20) | 3, (1 << 20) | 4, (1 << 20) | 5)
    assert result.data == (3, 1, 2, 0, 0, 0)
    assert lines == before


def test_empty_graph_and_self_pair_unique_add():
    assert graph(2, ()).rows == ((), ())
    result = graph(1, ((0, 0), (0, 0)))
    assert result.rows == ((0,),) and result.data == (0,)


def test_positive_parent_phase_before_negative_other_phase():
    # Caller rows are the published graph rows, not temporary map enumeration.
    positions = ((0, 0, 0), (1, 0, 0), (0, 2, 0), (0, 0, 3))
    parents = (-1, 0, -1, 0)
    source = ((2, 3, 1, 2), (), (), ())
    result = produce(positions, parents, (2, 2, 2, 2), source)
    assert result.words is not None and result.data == (3, 1, 2, 2)
    assert result.signed_rest_lengths == (3, 1, -2, -2)
    assert result.pre_length_entry_count == 4
    assert result.words == (4 << 20, 4, 4, 4)


def test_fixed_fixed_invalid_and_extra_attribute_bits():
    positions = ((0, 0, 0), (1, 0, 0), (2, 0, 0), (3, 0, 0))
    parents = (-1, 0, 1, 2)
    rows = ((1, 2, 3), (0,), (0,), (0,))
    result = produce(positions, parents, (1, 1, 2 | 128, 4), rows)
    assert result.data == (2, 0)
    assert result.signed_rest_lengths == (-2, -2)
    assert result.words == (1 << 20, 1, (1 << 20) | 1, 2)


def test_move_center_still_rejects_invalid_neighbor_after_move_gate():
    result = produce(((0, 0, 0), (1, 0, 0)), (-1, -1), (2, 4), ((1,), ()))
    assert result.words is result.data is result.signed_rest_lengths is None


def test_null_arrays_distinct_from_created_empty_after_length_filter():
    points = ((0, 0, 0),) * 2
    null = produce(points, (-1, 0), (1, 1), ((1,), (0,)))
    assert null.words is null.data is null.signed_rest_lengths is None
    assert null.pre_length_entry_count == 0
    empty = produce(points, (-1, 0), (1, 2), ((1,), (0,)))
    assert empty.words == (0, 0)
    assert empty.data == empty.signed_rest_lengths == ()
    assert empty.pre_length_entry_count == 2


def test_short_edge_threshold_strict_single_one_micro_not_solver_epsilon():
    cutoff = single(1e-6)
    below = struct.unpack(
        "<f", struct.pack("<I", struct.unpack("<I", struct.pack("<f", cutoff))[0] - 1)
    )[0]
    result = produce(
        ((0, 0, 0), (below, 0, 0), (cutoff, 0, 0)),
        (-1, 0, 0),
        (2, 2, 2),
        ((1, 2), (), ()),
    )
    assert result.data == (2,)
    assert result.signed_rest_lengths == (cutoff,)


def test_rest_single_sub_dot_yx_z_and_sqrt_not_double_length():
    # Single inputs/subtractions and every multiply/add seam are significant.
    a, b = (7.1234567, -8.7654321, 1.1111111), (-2.2222222, 3.3333333, -4.4444444)
    d = [single(single(x) - single(y)) for x, y in zip(a, b)]
    sq = [single(x * x) for x in d]
    expected = single(math.sqrt(single(single(sq[1] + sq[0]) + sq[2])))
    result = produce((a, b), (-1, 0), (1, 2), ((1,), (0,)))
    assert result.signed_rest_lengths == (expected, expected)


@pytest.mark.parametrize("bad", [False, 1, None])
def test_explicit_fresh_and_empty_triangle_map_premises(bad):
    with pytest.raises(ValueError):
        build_line_connectivity(1, (), fresh_serial_no_resize=bad)
    with pytest.raises(ValueError):
        build_distance_inputs(
            ((0, 0, 0),),
            (-1,),
            (1,),
            ((),),
            fresh_serial_no_resize=bad,
            zero_triangle_edge_map=True,
        )
    with pytest.raises(ValueError):
        build_distance_inputs(
            ((0, 0, 0),),
            (-1,),
            (1,),
            ((),),
            fresh_serial_no_resize=True,
            zero_triangle_edge_map=bad,
        )


@pytest.mark.parametrize(
    "count,lines",
    [
        (True, ()),
        (-1, ()),
        (1, ((0,),)),
        (1, ((0, 1),)),
        (1, ((-1, 0),)),
        (2, ((0, False),)),
    ],
)
def test_bad_line_shapes_indices_refused(count, lines):
    with pytest.raises(ValueError):
        graph(count, lines)


@pytest.mark.parametrize(
    "positions,parents,attrs,rows",
    [
        (((0, 0, 0),), (), (1,), ((),)),
        (((0, 0, 0),), (-2,), (1,), ((),)),
        (((0, 0, 0),), (1,), (1,), ((),)),
        (((0, 0, 0),), (-1,), (256,), ((),)),
        (((float("nan"), 0, 0),), (-1,), (1,), ((),)),
        (((0, 0, 0),), (-1,), (1,), ((1,),)),
        (((0, 0, 0),), (-1,), (1,), ()),
    ],
)
def test_bad_distance_buffers_refused(positions, parents, attrs, rows):
    with pytest.raises(ValueError):
        produce(positions, parents, attrs, rows)


def test_fresh_no_resize_capacity_is_bound_not_global_hashmap_assumption():
    # Complete graph K10 has 90 inserts > fresh graph capacity4*n.
    with pytest.raises(ValueError):
        graph(10, [(a, b) for a in range(10) for b in range(a + 1, 10)])
    # Generic adjacency duplicates are retained, but >2*n same phase grows map.
    with pytest.raises(ValueError):
        produce(((0, 0, 0), (1, 0, 0)), (-1, 0), (2, 2), ((1,) * 5, ()))
