"""Native-flow fixtures and independent linear-algebra checks, not game runtime."""

import struct
import sys
from pathlib import Path

import numpy as np
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from official_physics_bindpose import (
    bone_trs_single,
    import_bone_vertices,
    inverse_matrix_single,
    prepare_bound_bone_inputs,
)
from official_physics_snapshot import TransformGetterValues, multiply_matrices_single

I = ((1, 0, 0, 0), (0, 1, 0, 0), (0, 0, 1, 0), (0, 0, 0, 1))
Q = (0, 0, 0, 1)


def test_trs_scales_columns_not_rows_then_stores_world_translation():
    assert bone_trs_single((7, 8, 9), (0, 0, 1, 1), (2, 3, -4)) == (
        (-2, 4, 0, 0),
        (-6, -3, 0, 0),
        (0, 0, -4, 0),
        (7, 8, 9, 1),
    )


@pytest.mark.parametrize(
    "matrix",
    [
        I,
        ((-2, 0, 0, 0), (0, 4, 0, 0), (0, 0, 0.5, 0), (3, -7, 11, 1)),
        ((1, 0, 0, 0), (2, 1, 0, 0), (3, 4, 1, 0), (5, 6, 7, 1)),
        ((1, 2, 0, 1), (0, 1, 1, 0), (1, 0, 2, 0), (3, 1, 4, 1)),
    ],
)
def test_full_matrix_inverse_matches_independent_double_linalg(matrix):
    result = np.array(inverse_matrix_single(matrix)).T
    expected = np.linalg.inv(np.array(matrix, dtype=np.float64).T)
    np.testing.assert_allclose(result, expected, rtol=2e-6, atol=2e-6)
    np.testing.assert_allclose(np.array(matrix).T @ result, np.eye(4), atol=2e-6)


def test_diagonal_inverse_is_exact_including_negative_determinant():
    matrix = ((-2, 0, 0, 0), (0, 4, 0, 0), (0, 0, 0.5, 0), (0, 0, 0, 1))
    assert inverse_matrix_single(matrix) == (
        (-0.5, 0, 0, 0),
        (0, 0.25, 0, 0),
        (0, 0, 2, 0),
        (0, 0, 0, 1),
    )


def test_bindpose_order_is_inverse_bone_world_trs_times_render_ltow():
    ltow = ((1, 0, 0, 0), (0, 1, 0, 0), (0, 0, 1, 0), (4, 0, 0, 1))
    result = import_bone_vertices(I, ltow, [(10, 0, 0)], [Q], [(2, 1, 1)])
    assert result.skin_bone_bindposes == (
        ((0.5, 0, 0, 0), (0, 1, 0, 0), (0, 0, 1, 0), (-3, 0, 0, 1)),
    )
    assert result.frames.positions == ((10, 0, 0),)


def test_one_hot_weights_use_original_zero_based_skin_slot_order():
    result = import_bone_vertices(I, I, [(0, 0, 0)] * 3, [Q] * 3, [(1, 1, 1)] * 3)
    assert [w.bone_indices for w in result.bone_weights] == [
        (0, 0, 0, 0),
        (1, 0, 0, 0),
        (2, 0, 0, 0),
    ]
    assert all(w.weights == (1, 0, 0, 0) for w in result.bone_weights)
    assert result.skin_bone_bindposes == (I,) * 3


def test_skinning_bindpose_maps_render_local_point_to_bone_local():
    position, rotation, scale = (2, 3, 4), (0, 0, 1, 0), (-2, 4, 1)
    world = bone_trs_single(position, rotation, scale)
    render = ((1, 0, 0, 0), (0, 2, 0, 0), (0, 0, 3, 0), (1, 1, 1, 1))
    result = import_bone_vertices(I, render, [position], [rotation], [scale])
    restored = multiply_matrices_single(world, result.skin_bone_bindposes[0])
    assert restored == render


def test_getter_snapshot_scale_is_used_by_full_bone_vertex_composition():
    getters = [
        TransformGetterValues(
            (10, 0, 0),
            Q,
            ((2, 0, 0, 0), (0, 3, 0, 0), (0, 0, 4, 0), (10, 0, 0, 1)),
            (0, 0, 0),
            Q,
        )
    ]
    result = prepare_bound_bone_inputs(getters, I, I, [-1], [0])
    assert result.inputs.snapshots[0].scale == (2, 3, 4)
    assert result.vertices.frames == result.inputs.frames
    assert result.vertices.bone_weights[0].bone_indices == (0, 0, 0, 0)
    assert result.vertices.skin_bone_bindposes[0][0] == (0.5, 0, 0, 0)
    assert result.vertices.skin_bone_bindposes[0][3] == (-5, 0, 0, 1)


def test_empty_import_validates_both_matrices_but_has_no_vertex_outputs():
    result = import_bone_vertices(I, I, [], [], [])
    assert (
        result.bone_weights
        == result.skin_bone_bindposes
        == result.frames.positions
        == ()
    )
    with pytest.raises(ValueError):
        import_bone_vertices(I, (), [], [], [])


@pytest.mark.parametrize(
    "positions, rotations, scales",
    [
        ([(0, 0, 0)], [], [(1, 1, 1)]),
        ([(0, 0, 0)], [Q], []),
    ],
)
def test_parallel_input_mismatch_is_refused(positions, rotations, scales):
    with pytest.raises(ValueError, match="parallel"):
        import_bone_vertices(I, I, positions, rotations, scales)


@pytest.mark.parametrize("scale", [(0, 1, 1), (1, 0, 1), (1, 1, 0)])
def test_singular_bone_trs_is_refused_not_pseudoinverted(scale):
    with pytest.raises(ValueError, match="singular"):
        import_bone_vertices(I, I, [(0, 0, 0)], [Q], [scale])


@pytest.mark.parametrize("matrix", [((0, 0, 0, 0),) * 4, ((1, 0, 0, 0),) * 4])
def test_singular_full_matrix_is_adapter_rejection(matrix):
    with pytest.raises(ValueError, match="singular"):
        inverse_matrix_single(matrix)


@pytest.mark.parametrize("value", [float("nan"), float("inf"), True, 1e40])
def test_nonfinite_unrepresentable_scale_is_refused(value):
    with pytest.raises(ValueError):
        bone_trs_single((0, 0, 0), Q, (value, 1, 1))


def test_intermediate_minor_overflow_is_adapter_rejection():
    with pytest.raises(ValueError):
        inverse_matrix_single(
            ((1e30, 0, 0, 0), (0, 1e30, 0, 0), (0, 0, 1e30, 0), (0, 0, 0, 1))
        )


def test_reciprocal_determinant_overflow_is_adapter_rejection():
    with pytest.raises(ValueError):
        inverse_matrix_single(
            ((1e-40, 0, 0, 0), (0, 1, 0, 0), (0, 0, 1, 0), (0, 0, 0, 1))
        )


def test_matrix_inverse_rounds_inputs_to_single_first():
    matrix = ((16777217, 0, 0, 0), (0, 1, 0, 0), (0, 0, 1, 0), (0, 0, 0, 1))
    assert inverse_matrix_single(matrix)[0][0] == 2**-24


def test_weight_layout_fixture_is_float4_then_int4_not_unity_skin_weight1():
    result = import_bone_vertices(I, I, [(0, 0, 0)] * 2, [Q] * 2, [(1, 1, 1)] * 2)
    w = result.bone_weights[1]
    assert struct.pack("<4f4i", *w.weights, *w.bone_indices).hex() == (
        "0000803f00000000000000000000000001000000000000000000000000000000"
    )
