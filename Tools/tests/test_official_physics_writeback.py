"""Finite writeback-buffer fixtures; no Unity Transform setter is executed."""

import struct
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from official_physics_proxy_baseline import LocalPose
from official_physics_proxy_frames import vertex_to_transform_rotations
from official_physics_writeback import (
    BoneWritebackTeam,
    WorldBonePose,
    rotate_double,
    write_local_bone_pose,
    write_world_bone_pose,
)

Q = (0, 0, 0, 1)
IDENTITY_SIGN = (1, 1, 1, 1)
TEAM = BoneWritebackTeam(0, 0, 0, 2, IDENTITY_SIGN)
WORLD = WorldBonePose(((10, 20, 30), (12, 24, 36)), (Q, Q))
LOCAL = LocalPose(((90, 91, 92), (93, 94, 95)), (Q, Q))


def test_rotate_double_preserves_large_world_coordinates_below_single_resolution():
    v = (2**40 + 0.125, -(2**40) + 0.25, 0.123456789012345)
    assert rotate_double(Q, v) == v
    assert rotate_double((0, 0, 1, 0), v) == (-v[0], -v[1], v[2])


def test_double_rotation_keeps_original_nonunit_quaternion_and_double_arithmetic():
    # No normalization: q=(0,0,2,0) produces xy scale -7, not a unit 180 rotation.
    assert rotate_double((0, 0, 2, 0), (1.125, 2.25, 3.5)) == (-7.875, -15.75, 3.5)


@pytest.mark.parametrize(
    "q,v",
    [
        (Q, (float("nan"), 0, 0)),
        (Q, (0, float("inf"), 0)),
        ((0, 0, 0, float("inf")), (1, 2, 3)),
        (Q, (True, 0, 0)),
        (Q, (1, 2)),
        (Q, (1, 2, 10**1000)),
    ],
)
def test_double_adapter_rejects_invalid_inputs(q, v):
    with pytest.raises(ValueError):
        rotate_double(q, v)


def test_world_writer_maps_three_different_chunk_starts_and_keeps_unselected_output():
    source = WorldBonePose(((1, 2, 3), (2**40 + 0.125, 5, 6)), (Q, (0, 0, 1, 0)))
    team = BoneWritebackTeam(1, 2, 3, 1, IDENTITY_SIGN)
    initial = WorldBonePose(((9, 9, 9),) * 4, (Q,) * 4)
    result = write_world_bone_pose(
        [1], [0, 1], [None, team], source, [Q, Q, Q, (1, 0, 0, 0)], initial
    )
    assert result.positions == ((9, 9, 9), (9, 9, 9), source.positions[1], (9, 9, 9))
    assert result.rotations[2] == (0, 1, 0, 0)  # proxy z180 * vertex offset x180
    assert initial.positions[2] == (9, 9, 9)


def test_world_rotation_multiplies_sign_componentwise_before_proxy_product():
    team = BoneWritebackTeam(0, 0, 0, 1, (-1, 1, -1, 1))
    initial = WorldBonePose(((0, 0, 0),), (Q,))
    source = WorldBonePose(((1, 2, 3),), ((0, 0, 1, 0),))
    result = write_world_bone_pose(
        [0], [1], [None, team], source, [(0.25, 0.5, 0.75, 2)], initial
    )
    assert result.rotations[0] == (-0.5, -0.25, 2, 0.75)
    # Signed component scale is neither quaternion composition nor normalization.


def test_zero_team_is_noop_without_reading_team_or_offset_buffers():
    result = write_world_bone_pose([0, 1], [0, 0], [], WORLD, [], WORLD)
    assert result == WORLD
    result2 = write_local_bone_pose(
        [0, 1], [0, 0], [], (2, 2), (-1, 0), WORLD, [(1, 1, 1)] * 2, LOCAL
    )
    assert result2 == LOCAL


def test_world_writer_does_not_add_an_unobserved_fixed_or_move_gate():
    # Kernel has only nonzero team gating; attr/transform flags are upstream inputs.
    assert (
        write_world_bone_pose([0], [1, 1], [None, TEAM], WORLD, [Q, Q], WORLD) == WORLD
    )


def test_world_copy_keeps_double_signed_zero_and_not_single_quantization():
    source = WorldBonePose(((-0.0, 2**40 + 0.125, -0.0),), (Q,))
    team = BoneWritebackTeam(0, 0, 0, 1, IDENTITY_SIGN)
    result = write_world_bone_pose([0], [1], [None, team], source, [Q], source)
    assert struct.pack("<3d", *result.positions[0]) == struct.pack(
        "<3d", *source.positions[0]
    )


def test_frame_offset_to_world_to_local_explicit_synthetic_buffer_composition():
    offsets = vertex_to_transform_rotations(
        Q, [(0, 1, 0)] * 2, [(0, 0, 1)] * 2, [Q, (0, 0, 0, 2)]
    )
    proxy = WorldBonePose(((2**40, 0, 0), (2**40 + 0.125, 2, 3)), (Q, Q))
    written = write_world_bone_pose([0, 1], [1, 1], [None, TEAM], proxy, offsets, WORLD)
    assert written.rotations[1] == (0, 0, 0, 2)
    local = write_local_bone_pose(
        [0, 1],
        [1, 1],
        [None, TEAM],
        (1, 2),
        (-1, 0),
        written,
        [(1, 2, 3), (1, 1, 1)],
        LOCAL,
    )
    assert local.positions == (LOCAL.positions[0], (0.125, 1, 1))
    assert local.rotations[1] == (0, 0, 0, 2)


def test_local_writer_uses_relative_parent_index_chunk_offsets_and_parent_scale():
    team = BoneWritebackTeam(2, 1, 0, 2, IDENTITY_SIGN)
    world = WorldBonePose(
        ((100, 100, 100), (10, 20, 30), (12, 24, 36), (0, 0, 0)), (Q,) * 4
    )
    result = write_local_bone_pose(
        [3],
        [0, 0, 1, 1],
        [None, team],
        (0, 0, 1, 2),
        (-1, -1, -1, 0),
        world,
        [(1, 1, 1), (2, 4, -3), (999, 999, 999), (1, 1, 1)],
        LOCAL_WITH_FOUR,
    )
    assert result.positions[2] == (1, 1, -2)
    assert result.positions[1] == LOCAL_WITH_FOUR.positions[1]
    assert result.rotations[2] == Q


LOCAL_WITH_FOUR = LocalPose(((9, 9, 9),) * 4, (Q,) * 4)


def test_local_delta_subtracts_in_double_before_single_output_cast():
    world = WorldBonePose(((2**40, 0, 0), (2**40 + 0.125, 0, 0)), (Q, Q))
    result = write_local_bone_pose(
        [1], [1, 1], [None, TEAM], (1, 2), (-1, 0), world, [(1, 1, 1)] * 2, LOCAL
    )
    assert result.positions[1] == (0.125, 0, 0)


def test_local_writer_inverse_parent_rotation_and_original_quaternion_magnitude():
    world = WorldBonePose(((0, 0, 0), (1, 2, 3)), ((0, 0, 2, 0), (0, 0, 0, 3)))
    result = write_local_bone_pose(
        [1], [1, 1], [None, TEAM], (1, 3), (-1, 0), world, [(1, 1, 1)] * 2, LOCAL
    )
    # inverse nonunit parent is (0,0,-0.5,0), NOT conjugate or normalized inverse.
    assert result.positions[1] == (0.5, 1, 3)
    assert result.rotations[1] == (0, 0, -1.5, 0)


def test_local_negative_scale_quaternion_is_applied_after_parent_inverse_product():
    team = BoneWritebackTeam(0, 0, 0, 2, (-1, 1, -1, 1))
    world = WorldBonePose(((0, 0, 0), (1, 2, 3)), ((0, 0, 1, 0), (1, 0, 0, 0)))
    result = write_local_bone_pose(
        [1], [1, 1], [None, team], (1, 2), (-1, 0), world, [(1, 1, 1)] * 2, LOCAL
    )
    assert result.rotations[1] == (0, -1, 0, 0)


@pytest.mark.parametrize("attribute,parent", [(0, 0), (1, 0), (128, 0), (2, -1)])
def test_local_writer_retains_fixed_invalid_and_parentless_outputs(attribute, parent):
    result = write_local_bone_pose(
        [1],
        [1, 1],
        [None, TEAM],
        (1, attribute),
        (-1, parent),
        WORLD,
        [(0, 0, 0)] * 2,
        LOCAL,
    )
    assert result == LOCAL  # Scale zero is not read in skipped branch.


@pytest.mark.parametrize("value", [0, -0.0])
def test_active_zero_parent_scale_is_rejected_not_patched_to_epsilon(value):
    with pytest.raises(ValueError, match="scale"):
        write_local_bone_pose(
            [1],
            [1, 1],
            [None, TEAM],
            (1, 2),
            (-1, 0),
            WORLD,
            [(1, value, 1), (1, 1, 1)],
            LOCAL,
        )


@pytest.mark.parametrize("indices", [[0, 0], [-1], [2], [True]])
def test_invalid_or_duplicate_job_vertices_are_adapter_errors(indices):
    with pytest.raises(ValueError):
        write_world_bone_pose(indices, [1, 1], [None, TEAM], WORLD, [Q, Q], WORLD)


@pytest.mark.parametrize(
    "ids,teams",
    [
        ([1], [None, TEAM]),
        ([-1, 0], []),
        ([32768, 0], []),
        ([True, 0], []),
        ([1, 0], []),
        ([1, 0], [None, None]),
    ],
)
def test_parallel_team_id_and_missing_team_adapter_errors(ids, teams):
    with pytest.raises(ValueError):
        write_world_bone_pose([0], ids, teams, WORLD, [Q, Q], WORLD)


@pytest.mark.parametrize(
    "team",
    [
        BoneWritebackTeam(1, 0, 0, 1, IDENTITY_SIGN),
        BoneWritebackTeam(0, 2, 0, 2, IDENTITY_SIGN),
        BoneWritebackTeam(0, 0, 2, 2, IDENTITY_SIGN),
        BoneWritebackTeam(0, 0, 0, 0, IDENTITY_SIGN),
        BoneWritebackTeam(-1, 0, 0, 2, IDENTITY_SIGN),
        BoneWritebackTeam(0, True, 0, 2, IDENTITY_SIGN),
    ],
)
def test_chunk_bounds_are_explicit_not_clamped(team):
    with pytest.raises(ValueError):
        write_world_bone_pose([0], [1, 1], [None, team], WORLD, [Q, Q], WORLD)


def test_aliasing_output_targets_from_different_teams_is_rejected():
    teams = [
        None,
        BoneWritebackTeam(0, 0, 0, 1, IDENTITY_SIGN),
        BoneWritebackTeam(1, 0, 1, 1, IDENTITY_SIGN),
    ]
    with pytest.raises(ValueError, match="writer"):
        write_world_bone_pose([0, 1], [1, 2], teams, WORLD, [Q, Q], WORLD)


@pytest.mark.parametrize(
    "world", [WorldBonePose(WORLD.positions, (Q,)), WorldBonePose(((0, 0, 0),), (Q, Q))]
)
def test_world_pose_buffers_must_be_parallel(world):
    with pytest.raises(ValueError):
        write_world_bone_pose([], [1, 1], [None, TEAM], world, [Q, Q], WORLD)


def test_local_buffers_and_active_parent_indices_are_validated():
    with pytest.raises(ValueError):
        write_local_bone_pose(
            [1], [1, 1], [None, TEAM], (1,), (-1, 0), WORLD, [(1, 1, 1)] * 2, LOCAL
        )
    with pytest.raises(ValueError):
        write_local_bone_pose(
            [1], [1, 1], [None, TEAM], (1, 2), (-1, 2), WORLD, [(1, 1, 1)] * 2, LOCAL
        )


def test_empty_job_list_preserves_buffers():
    assert write_world_bone_pose([], [0, 0], [], WORLD, [], WORLD) == WORLD
    assert (
        write_local_bone_pose(
            [], [0, 0], [], (0, 0), (-1, -1), WORLD, [(1, 1, 1)] * 2, LOCAL
        )
        == LOCAL
    )


def test_local_output_cast_is_single_and_signed_scale_is_not_abs():
    world = WorldBonePose(((0, 0, 0), (1, 1, 1)), (Q, Q))
    result = write_local_bone_pose(
        [1],
        [1, 1],
        [None, TEAM],
        (1, 2),
        (-1, 0),
        world,
        [(3, -3, 3), (1, 1, 1)],
        LOCAL,
    )
    with pytest.raises(ValueError):
        write_local_bone_pose(
            [],
            [0, 0],
            [],
            (0, 0),
            (-1, -1),
            WORLD,
            [(1, 1, 1)],
            LOCAL,
        )
    assert struct.pack("<3f", *result.positions[1]).hex() == "abaaaa3eabaaaabeabaaaa3e"
