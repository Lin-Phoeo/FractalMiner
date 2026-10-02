"""Synthetic proxy input/pose fixtures; no original native DLL execution."""

import math
import sys
from pathlib import Path
from typing import Any

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from official_physics_angle_cache import rotate_single
from official_physics_baseline_build import build_transform_baselines
from official_physics_proxy_baseline import (
    evaluate_baseline_local_pose,
    map_transform_ids,
    reverse_inserted_children_no_resize,
    rotation_from_normal_tangent,
)

I = (0.0, 0.0, 0.0, 1.0)
UP, FORWARD = (0.0, 1.0, 0.0), (0.0, 0.0, 1.0)


def test_id_map_uses_runtime_int32_identity_not_bone_names_or_pathids():
    result = map_transform_ids([42, -7, 91], [999, 42, -7], [-7, 42, -7])
    assert (result.parents, result.roots) == ((-1, 0, 1), (1, 0, 1))
    assert map_transform_ids([], [], []).parents == ()


@pytest.mark.parametrize("bad", [True, 1.0, "1", -(2**31) - 1, 2**31])
def test_id_input_width_is_not_serialized_pptr_int64(bad: Any):
    with pytest.raises(ValueError):
        map_transform_ids([bad], [0], [])
    with pytest.raises(ValueError):
        map_transform_ids([1], [bad], [])
    with pytest.raises(ValueError):
        map_transform_ids([1], [0], [bad])


def test_id_map_duplicate_missing_root_or_unequal_buffers_rejected():
    for ids, parents, roots in [([1, 1], [0, 0], []), ([1], [0], [2]), ([1], [], [])]:
        with pytest.raises(ValueError):
            map_transform_ids(ids, parents, roots)


def test_fresh_no_resize_child_order_is_reverse_insert_not_sorted():
    children = reverse_inserted_children_no_resize([-1, 0, 0, 1, 0, -3])
    assert children == ((4, 2, 1), (3,), (), (), (), ())
    assert reverse_inserted_children_no_resize([]) == ()


@pytest.mark.parametrize("parents", [[True], [1.0], [-(2**31) - 1], [1], [-1] * 65537])
def test_invalid_no_resize_parent_adapter(parents: Any):
    with pytest.raises(ValueError):
        reverse_inserted_children_no_resize(parents)


def test_id_map_child_order_and_baseline_build_join_without_guessing_root_zero():
    mapped = map_transform_ids([40, 10, 70, 20], [0, 40, 10, 10], [40])
    children = reverse_inserted_children_no_resize(mapped.parents)
    built = build_transform_baselines(
        mapped.parents, [0, 0, 2, 2], mapped.roots, children
    )
    assert built.data == (1, 2, 3)  # reverse insertion + LIFO -> ascending siblings


@pytest.mark.parametrize("angle", [0, 30, 90, 120, 180, 210, 270, 330])
@pytest.mark.parametrize(
    "axis",
    [
        (1.0, 0.0, 0.0),
        UP,
        FORWARD,
        (1 / math.sqrt(14), 2 / math.sqrt(14), 3 / math.sqrt(14)),
    ],
)
def test_normal_tangent_rotation_covers_matrix_sign_masks_with_geometric_oracle(
    angle, axis
):
    half = math.radians(angle) / 2
    q = tuple(a * math.sin(half) for a in axis) + (math.cos(half),)
    normal, tangent = rotate_single(q, UP), rotate_single(q, FORWARD)
    rebuilt = rotation_from_normal_tangent(normal, tangent)
    assert sum(x * x for x in rebuilt) == pytest.approx(1, abs=4e-7)
    for basis in [(1, 0, 0), UP, FORWARD]:
        assert rotate_single(rebuilt, basis) == pytest.approx(
            rotate_single(q, basis), abs=7e-7
        )


def test_no_added_forward_normalization_or_fallback_lookrotation():
    # Native keeps the forward/tangent's length in the matrix. Normalizing it
    # before matrix construction would produce a different rotation (45 degrees).
    q = rotation_from_normal_tangent(UP, (0, -1, 1))
    # Matrix columns (1,0,0), (0,1,1), (0,-1,1) -> raw quaternion (2,0,0,4).
    assert q == pytest.approx((1 / math.sqrt(5), 0, 0, 2 / math.sqrt(5)), abs=2e-7)
    assert q[0] != pytest.approx(math.sin(math.pi / 8), abs=1e-3)


@pytest.mark.parametrize(
    "normal, tangent",
    [
        (UP, UP),
        ((0, 0, 0), FORWARD),
        (UP, (0, 0, 0)),
        ((math.nan, 0, 1), FORWARD),
        (UP, (math.inf, 0, 1)),
        ((1, 2), FORWARD),
    ],
)
def test_degenerate_or_nonfinite_frame_is_adapter_error_not_native_fallback(
    normal: Any, tangent: Any
):
    with pytest.raises(ValueError):
        rotation_from_normal_tangent(normal, tangent)


def pose_args():
    return (
        [-1, 0, -2],
        [(2, 4, 6), (3, 6, 9), (99, 99, 99)],
        [UP] * 3,
        [FORWARD] * 3,
        [(8, 7, 6)] * 3,
        [(0, 0, 1, 0)] * 3,
    )


def test_local_pose_root_uses_parent_sign_not_first_slot_and_unlisted_preserved():
    result = evaluate_baseline_local_pose([1, 0], *pose_args())
    assert result.positions == ((0, 0, 0), (1, 2, 3), (8, 7, 6))
    assert result.rotations == (I, I, (0, 0, 1, 0))
    root = evaluate_baseline_local_pose([2], *pose_args())
    assert root.positions[2] == (0, 0, 0)
    assert root.rotations[2] == I


def test_nonzero_parent_basis_inverse_not_raw_delta_or_child_basis_inverse():
    parents, positions, normals, tangents, out_p, out_q = pose_args()
    # Parent basis yaw90, child basis identity.
    tangents = [(1, 0, 0), FORWARD, FORWARD]
    result = evaluate_baseline_local_pose(
        [1, 1], parents, positions, normals, tangents, out_p, out_q
    )
    assert result.positions[1] == pytest.approx((-3, 2, 1), abs=1e-6)
    assert rotate_single(result.rotations[1], FORWARD) == pytest.approx(
        (-1, 0, 0), abs=3e-7
    )
    assert result.positions[0] == out_p[0]
    assert out_p == [(8, 7, 6)] * 3  # immutable publication, no caller writes


def test_pose_first_baseline_slot_with_parent_is_not_forced_identity():
    args: list[Any] = list(pose_args())
    result = evaluate_baseline_local_pose([1], *args)
    assert result.positions[1] == (1, 2, 3)


def test_local_pose_position_inputs_round_before_single_subtraction():
    args: list[Any] = list(pose_args())
    args[1] = [(16777216, 0, 0), (16777217, 1, 0), (0, 0, 0)]
    result = evaluate_baseline_local_pose([1], *args)
    assert result.positions[1] == (0, 1, 0)  # not Double subtraction -> (1,1,0)


@pytest.mark.parametrize("indices", [[True], [0.0], [-1], [65536], [3]])
def test_pose_bad_data_indices(indices: Any):
    with pytest.raises(ValueError):
        evaluate_baseline_local_pose(indices, *pose_args())


def test_pose_empty_list_preserves_output_without_evaluating_unused_frames():
    args: list[Any] = list(pose_args())
    args[2] = [(0, 0, 0)] * 3  # degenerate but not evaluated by job
    result = evaluate_baseline_local_pose([], *args)
    assert result.positions == tuple(args[4])
    assert result.rotations == tuple(args[5])


@pytest.mark.parametrize("slot", range(1, 6))
def test_pose_parallel_arrays_must_match(slot):
    args: list[Any] = list(pose_args())
    args[slot] = []
    with pytest.raises(ValueError):
        evaluate_baseline_local_pose([], *args)


@pytest.mark.parametrize("parent", [True, 0.0, 3, 2**31, -(2**31) - 1])
def test_pose_bad_parent_reference_is_adapter_error(parent: Any):
    args: list[Any] = list(pose_args())
    args[0] = [parent, 0, -1]
    with pytest.raises(ValueError):
        evaluate_baseline_local_pose([0], *args)


def test_complete_offline_input_to_baseline_to_local_pose_chain():
    mapped = map_transform_ids([40, 10, 70], [0, 40, 10], [40])
    child_map = reverse_inserted_children_no_resize(mapped.parents)
    built = build_transform_baselines(
        mapped.parents, [0, 0, 2], mapped.roots, child_map
    )
    pose = evaluate_baseline_local_pose(
        built.data,
        mapped.parents,
        [(0, 0, 0), (0, 1, 0), (0, 2, 0)],
        [UP] * 3,
        [FORWARD] * 3,
        [(7, 7, 7)] * 3,
        [I] * 3,
    )
    assert built.data == (1, 2)
    assert pose.positions == ((7, 7, 7), (0, 1, 0), (0, 1, 0))
