"""Offline bone-input contracts, not a game/Burst runtime oracle."""

import math
import sys
from pathlib import Path
from typing import Any

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from official_physics_bone_import import (
    import_bone_frames,
    transform_direction_preserve_length,
    transform_point_single,
)
from official_physics_proxy_baseline import (
    evaluate_baseline_local_pose,
    map_transform_ids,
)
from official_physics_root_depth import evaluate_vertex_root_depth

IDENTITY = ((1, 0, 0, 0), (0, 1, 0, 0), (0, 0, 1, 0), (0, 0, 0, 1))
ROTATION = (0, 0, 0, 1)


def test_column_major_translation_and_no_perspective_divide():
    matrix = ((2, 0, 0, 0), (0, 3, 0, 0), (0, 0, 4, 0), (10, 20, 30, 2))
    assert transform_point_single(matrix, (1, 2, 3)) == (12, 26, 42)


def test_point_single_column_sum_grouping_not_double_dot():
    matrix = ((16777216, 0, 0, 0), (1, 0, 0, 0), (-16777216, 0, 0, 0), (1, 0, 0, 1))
    assert transform_point_single(matrix, (1, 1, 1)) == (1, 0, 0)


def test_point_input_rounding_before_multiply():
    assert transform_point_single(IDENTITY, (16777217, 0, 0)) == (16777216, 0, 0)


def test_direction_ignores_translation_preserves_length_under_nonuniform_scale():
    matrix = ((2, 0, 0, 0), (0, 3, 0, 0), (0, 0, 4, 0), (10, 20, 30, 1))
    actual = transform_direction_preserve_length(matrix, (3, 4, 0))
    assert actual == pytest.approx((5 / math.sqrt(5), 10 / math.sqrt(5), 0))
    assert sum(lane * lane for lane in actual) == pytest.approx(25)


def test_direction_is_not_inverse_transpose_normal_matrix():
    matrix = ((1, 0, 0, 0), (1, 1, 0, 0), (0, 0, 1, 0), (0, 0, 0, 1))
    assert transform_direction_preserve_length(matrix, (0, 1, 0)) == pytest.approx(
        (1 / math.sqrt(2), 1 / math.sqrt(2), 0)
    )


def test_direction_matrix_single_grouping_not_double_accumulation():
    matrix = ((16777216, 0, 0, 0), (1, 1, 0, 0), (-16777216, 0, 1, 0), (0, 0, 0, 1))
    assert transform_direction_preserve_length(matrix, (1, 1, 1)) == pytest.approx(
        (0, math.sqrt(1.5), math.sqrt(1.5))
    )


def test_zero_direction_returns_original_signed_zero():
    actual = transform_direction_preserve_length(IDENTITY, (-0.0, 0.0, -0.0))
    assert [math.copysign(1, lane) for lane in actual] == [-1, 1, -1]


def test_adapter_rejects_nonzero_direction_collapsed_by_matrix():
    matrix = ((0, 0, 0, 0), (0, 0, 0, 0), (0, 0, 0, 0), (0, 0, 0, 1))
    with pytest.raises(ValueError):
        transform_direction_preserve_length(matrix, (0, 1, 0))


def test_identity_import_uses_rotation_up_and_forward_not_child_directions():
    result = import_bone_frames(IDENTITY, [(1, 2, 3), (8, 9, 10)], [ROTATION, ROTATION])
    assert result.positions == ((1, 2, 3), (8, 9, 10))
    assert result.normals == ((0, 1, 0), (0, 1, 0))
    assert result.tangents == ((0, 0, 1), (0, 0, 1))


def test_yaw_rotation_and_proxy_rotation_compose_before_local_pose():
    yaw = (0, math.sqrt(0.5), 0, math.sqrt(0.5))
    inverse_yaw_matrix = ((0, 0, 1, 0), (0, 1, 0, 0), (-1, 0, 0, 0), (0, 0, 0, 1))
    result = import_bone_frames(inverse_yaw_matrix, [(1, 2, 3)], [yaw])
    assert result.positions == ((-3, 2, 1),)
    assert result.normals[0] == pytest.approx((0, 1, 0))
    assert result.tangents[0] == pytest.approx((0, 0, 1), abs=2e-7)


def test_nonunit_quaternion_not_silently_normalized():
    result = import_bone_frames(IDENTITY, [(0, 0, 0)], [(1, 0, 0, 1)])
    assert result.normals[0] == pytest.approx((0, -1, 2), abs=5e-7)
    assert result.tangents[0] == pytest.approx((0, -2, -1), abs=5e-7)


def test_import_to_id_map_local_pose_and_global_depth_join():
    mapped = map_transform_ids([10, 20, 30], [99, 10, 20], [10])
    imported = import_bone_frames(
        IDENTITY, [(0, 0, 0), (0, 2, 0), (0, 5, 0)], [ROTATION] * 3
    )
    pose = evaluate_baseline_local_pose(
        [0, 1, 2],
        mapped.parents,
        imported.positions,
        imported.normals,
        imported.tangents,
        [(0, 0, 0)] * 3,
        [ROTATION] * 3,
    )
    assert pose.positions == ((0, 0, 0), (0, 2, 0), (0, 3, 0))
    assert pose.rotations == (ROTATION,) * 3
    depth = evaluate_vertex_root_depth(
        mapped.parents, [1, 2, 2], imported.positions, [0] * 3
    )
    assert depth.roots == (-1, 0, 0)
    assert depth.depths == pytest.approx((0, 0.4, 1))


def test_empty_import():
    result = import_bone_frames(IDENTITY, [], [])
    assert result.positions == result.normals == result.tangents == ()


@pytest.mark.parametrize("matrix", [(), IDENTITY[:3], ((1, 0, 0),) * 4])
@pytest.mark.parametrize(
    "function", [transform_point_single, transform_direction_preserve_length]
)
def test_adapter_matrix_shape(matrix, function):
    with pytest.raises(ValueError):
        function(matrix, (1, 2, 3))


@pytest.mark.parametrize("value", [True, math.inf, math.nan, 1e40])
@pytest.mark.parametrize("field", ["matrix", "position", "quaternion"])
def test_adapter_invalid_scalars(value, field):
    args: list[Any] = [IDENTITY, [(1, 2, 3)], [ROTATION]]
    if field == "matrix":
        args[0] = ((value, 0, 0, 0),) + IDENTITY[1:]
    elif field == "position":
        args[1] = [(value, 0, 0)]
    else:
        args[2] = [(value, 0, 0, 1)]
    with pytest.raises(ValueError):
        import_bone_frames(*args)


def test_adapter_import_parallel_buffers():
    with pytest.raises(ValueError):
        import_bone_frames(IDENTITY, [(0, 0, 0)], [])


def test_adapter_rejects_overflow_in_transformed_position():
    with pytest.raises(ValueError):
        transform_point_single(((3e38, 0, 0, 0),) + IDENTITY[1:], (2, 0, 0))
