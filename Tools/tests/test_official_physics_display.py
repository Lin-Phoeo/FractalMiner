"""Frame-end value references, not Unity/Burst or motion acceptance."""

import math
import struct
import sys
from dataclasses import replace
from pathlib import Path
from typing import Any, cast

import numpy as np
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from official_physics_angles import Quaternion
from official_physics_constraints import Vector3
from official_physics_display import (
    DisplayTeam,
    calculate_display_particle,
    calculate_display_positions,
    restore_negative_proxy_rotation,
)
from official_physics_particle_reset import (
    ParticleFrameState,
    ParticleResetTeam,
    prepare_particle_frame,
)
from official_physics_particle_step import (
    EndStepSettings,
    ParticleEndState,
    ResolvedCenter,
    finish_particle_step,
)
from official_physics_start_step import (
    ParticleStartState,
    ResolvedStartCenter,
    StartStepSettings,
    start_particle_step,
)

Z = (0.0, 0.0, 0.0)
Q = (0.0, 0.0, 0.0, 1.0)


def state(**changes):
    return replace(
        ParticleFrameState(
            (99, 99, 99),
            (10, 0, 0),
            Q,
            (98, 98, 98),
            Q,
            (-5, 0, 0),
            (0, 1, 0, 0),
            (97, 97, 97),
            (2, 0, 0),
            (96, 96, 96),
            (4, 0, 0),
            0.7,
            0.8,
            (0, 1, 0),
        ),
        **changes,
    )


def team(**changes):
    return replace(DisplayTeam(2, 7, 0, 0.5, 0.0, 0.5, 1.0, (1, 1, 1)), **changes)


def run(s=None, t=None, **changes: Any):
    args: dict[str, Any] = {
        "team_id": 1,
        "particle_index": 7,
        "simulation_delta_time": 0.5,
        "attributes": (2,),
        "proxy_positions": ((3, 0, 0),),
        "proxy_rotations": (Q,),
        "vertex_root_indices": (-1,),
    }
    args.update(changes)
    return calculate_display_particle(
        state() if s is None else s, team() if t is None else t, **args
    )


def test_move_predicts_with_real_velocity_then_lerps_from_previous_display():
    original = state()
    result = run(original)
    # alpha=.5/(.5+.5)=.5; target=10+Single(4*.5)=12; display=2+(12-2)*.5=7.
    assert result.interpolation == 0.5
    assert result.state.display_position == result.proxy_position == (7, 0, 0)
    assert result.writes == ("display_position", "proxy_position")
    assert result.state == replace(original, display_position=(7, 0, 0))
    assert original == state()


@pytest.mark.parametrize("time,now,old,expected", [(2, 0.5, 0, 22), (-1, 0.5, 0, -8)])
def test_display_time_ratio_is_unclamped(time, now, old, expected):
    result = run(t=team(time=time, now_update_time=now, old_time=old))
    assert result.state.display_position == (expected, 0, 0)


@pytest.mark.parametrize("now,old", [(0, 0.5), (-1, 0.5)])
def test_nonpositive_time_denominator_uses_zero_ratio(now, old):
    result = run(t=team(time=100, now_update_time=now, old_time=old))
    assert result.interpolation == 0 and result.state.display_position == (2, 0, 0)


@pytest.mark.parametrize(
    "weight,expected", [(-5, 3), (0, 3), (0.25, 4), (1, 7), (5, 7)]
)
def test_proxy_blend_is_clamped_but_unblended_display_is_retained(weight, expected):
    result = run(t=team(blend_weight=weight))
    assert result.state.display_position == (7, 0, 0)
    assert result.proxy_position == (expected, 0, 0)


@pytest.mark.parametrize("attribute", [0, 1, 4, 128, 255 & ~2])
def test_nonmoving_non_spring_copies_animation_to_display_without_proxy_write(
    attribute,
):
    result = run(
        state(old_position=(math.nan,) * 3, real_velocity=(math.nan,) * 3),
        team(time=math.nan, blend_weight=math.nan),
        attributes=(attribute,),
        simulation_delta_time=math.nan,
        vertex_root_indices=(),
    )
    assert result.state.display_position == (3, 0, 0)
    assert result.proxy_position is None and result.interpolation is None
    assert result.writes == ("display_position",)


def test_spring_flag_uses_moving_display_branch_even_for_fixed_vertex():
    assert run(t=team(flag=0x2002), attributes=(1,)).proxy_position == (7, 0, 0)


@pytest.mark.parametrize("flag", [0, 4, 0x12, 0x802, 0x80002, (1 << 61) | 2])
def test_nonprocess_team_never_reads_proxy_inputs_or_display_time(flag):
    original = state()
    result = run(
        original,
        team(flag=flag, particle_chunk_start=-1),
        attributes=(),
        proxy_positions=(),
        proxy_rotations=(),
        simulation_delta_time=math.nan,
    )
    assert (
        result.state is original and result.writes == () and result.proxy_index is None
    )


def test_zero_team_skips_unselected_bad_team_flag_and_global_index():
    result = run(
        t=team(flag=True),
        team_id=0,
        particle_index=-1,
        attributes=(),
        proxy_positions=(),
        proxy_rotations=(),
    )
    assert result.writes == ()


def test_proxy_global_index_uses_chunk_difference():
    result = run(
        t=team(particle_chunk_start=4, proxy_common_chunk_start=2),
        particle_index=5,
        proxy_positions=(Z, Z, Z, (3, 0, 0)),
        proxy_rotations=(Q,) * 4,
        attributes=(0,) * 4,
    )
    assert result.proxy_index == 3 and result.state.display_position == (3, 0, 0)


def test_root_radius_is_animated_root_to_original_animation_distance_times_float_1_3():
    result = run(
        proxy_positions=((3, 0, 0), Z), proxy_rotations=(Q, Q), vertex_root_indices=(1,)
    )
    assert result.state.display_position == pytest.approx(
        (3 * 1.2999999523162842, 0, 0)
    )
    assert result.proxy_position == result.state.display_position


def test_root_is_team_local_plus_proxy_start_not_particle_start_or_parent_slot():
    result = run(
        t=team(proxy_common_chunk_start=2),
        proxy_positions=(Z, Z, (3, 0, 0), Z),
        proxy_rotations=(Q,) * 4,
        attributes=(0, 0, 2),
        vertex_root_indices=(0, 0, 1),
    )
    assert result.proxy_index == 2
    assert result.state.display_position[0] == pytest.approx(3 * 1.2999999523162842)


def test_negative_root_skips_clamp_even_for_less_than_minus_one():
    assert run(vertex_root_indices=(-500,)).state.display_position == (7, 0, 0)


def test_zero_animated_root_radius_clamps_nonzero_displacement_to_root():
    assert run(vertex_root_indices=(0,)).state.display_position == (3, 0, 0)


def test_tiny_displacement_below_native_threshold_is_not_zeroed_by_zero_radius():
    result = run(
        state(
            old_position=(5e-10, 0, 0), display_position=(5e-10, 0, 0), real_velocity=Z
        ),
        proxy_positions=(Z,),
        vertex_root_indices=(0,),
    )
    assert result.state.display_position == (5e-10, 0, 0)


def test_displacement_exactly_at_native_epsilon_is_not_clamped():
    epsilon = 9.999999717180685e-10
    result = run(
        state(
            old_position=(epsilon, 0, 0),
            display_position=(epsilon, 0, 0),
            real_velocity=Z,
        ),
        proxy_positions=(Z,),
        vertex_root_indices=(0,),
    )
    assert result.state.display_position == (epsilon, 0, 0)


def test_within_root_radius_keeps_value_without_normalizing():
    result = run(
        state(old_position=(0.5, 0, 0), display_position=(0.5, 0, 0), real_velocity=Z),
        proxy_positions=((3, 0, 0), Z),
        proxy_rotations=(Q, Q),
        vertex_root_indices=(1,),
    )
    assert result.state.display_position == (0.5, 0, 0)


def test_animation_history_flag_copies_original_proxy_before_blend_and_negative_rotation():
    result = run(t=team(flag=0x20022, negative_scale_direction=(1, -1, 1)))
    assert result.state.old_animation_position == (3, 0, 0)
    assert result.state.old_animation_rotation == Q
    assert result.proxy_position == (7, 0, 0)
    assert result.proxy_rotation == (0, 0, 1, 0)
    assert result.writes == (
        "display_position",
        "proxy_position",
        "old_animation_position",
        "old_animation_rotation",
        "proxy_rotation",
    )
    assert result.state.old_position == (10, 0, 0) and result.state.old_rotation == Q


def test_fixed_animation_history_and_negative_rotation_are_still_published():
    result = run(
        t=team(flag=0x20022, negative_scale_direction=(1, 1, -1)), attributes=(1,)
    )
    assert result.proxy_position is None and result.state.old_animation_position == (
        3,
        0,
        0,
    )
    assert result.proxy_rotation == (0, 1, 0, 0)
    assert result.writes == (
        "display_position",
        "old_animation_position",
        "old_animation_rotation",
        "proxy_rotation",
    )


def test_raw_proxy_quaternion_history_copy_is_single_and_not_normalized():
    raw = (1 / 3, 0, 0, 2)
    result = run(t=team(flag=0x22), attributes=(1,), proxy_rotations=(raw,))
    assert result.state.old_animation_rotation == (0.3333333432674408, 0, 0, 2)
    assert result.proxy_rotation is None


@pytest.mark.parametrize(
    "direction,expected",
    [
        ((1, 1, 1), Q),
        ((-1, 1, 1), Q),
        ((1, -1, 1), (0, 0, 1, 0)),
        ((1, 1, -1), (0, 1, 0, 0)),
        ((-1, -1, -1), (1, 0, 0, 0)),
    ],
)
def test_negative_proxy_rotation_rebuilds_scaled_y_z_axes_without_duplicating_swap(
    direction, expected
):
    assert restore_negative_proxy_rotation(Q, direction) == expected


def test_nonunit_quaternion_matrix_path_is_not_rotate_vector_shortcut():
    # No normalization: quaternion-matrix basis gives up=(4,-1,4),
    # forward=(8,-4,-9) for q=(1,2,0,2), prior to reconstruction.
    # Expected float32 lanes are independently pinned from the static helper
    # instruction chain, rather than calling the production reconstruction helper.
    actual = restore_negative_proxy_rotation((1, 2, 0, 2), (1, 1, 1))
    assert tuple(struct.pack("<f", lane).hex() for lane in actual) == (
        "9bab123f",
        "ea48e43e",
        "0866b83e",
        "69fb153f",
    )


def test_random_unit_negative_rotations_match_independent_matrix_basis_not_axis_swap():
    rng = np.random.default_rng(640419)

    def matrix(q):
        x, y, z, w = map(float, q)
        return np.array(
            [
                [1 - 2 * (y * y + z * z), 2 * (x * y - z * w), 2 * (x * z + y * w)],
                [2 * (x * y + z * w), 1 - 2 * (x * x + z * z), 2 * (y * z - x * w)],
                [2 * (x * z - y * w), 2 * (y * z + x * w), 1 - 2 * (x * x + y * y)],
            ]
        )

    for _ in range(64):
        q = rng.normal(size=4)
        q /= np.linalg.norm(q)
        direction = rng.choice((-1, 1), size=3)
        source = matrix(q)
        forward = source[:, 2] * direction[2]
        up = source[:, 1] * direction[1]
        right = np.cross(up, forward)
        right /= np.linalg.norm(right)
        expected = np.column_stack((right, np.cross(forward, right), forward))
        actual = restore_negative_proxy_rotation(
            cast(Quaternion, tuple(map(float, q))),
            cast(Vector3, tuple(map(float, direction))),
        )
        np.testing.assert_allclose(matrix(actual), expected, rtol=0, atol=2e-6)


def test_nonpositive_clock_denominator_never_reads_unused_time_numerator():
    result = run(t=team(time=math.nan, now_update_time=-1, old_time=0.5))
    assert result.interpolation == 0


def test_flag_absent_preserves_dirty_unselected_animation_history():
    original = state(
        old_animation_position=(math.nan,) * 3, old_animation_rotation=(math.nan,) * 4
    )
    result = run(original)
    assert result.state.old_animation_position is original.old_animation_position
    assert result.state.old_animation_rotation is original.old_animation_rotation


def test_serial_range_publishes_negative_rotations_and_keeps_trailing_proxy_slots():
    result = calculate_display_positions(
        (state(),),
        (1,),
        {
            1: team(
                particle_chunk_start=0,
                flag=0x20022,
                negative_scale_direction=(1, 1, -1),
            )
        },
        simulation_delta_time=0.5,
        attributes=(1,),
        proxy_positions=((3, 0, 0), (100, 100, 100)),
        proxy_rotations=(Q, (0, 0, 0, 2)),
        vertex_root_indices=(),
        index_count=1,
    )
    assert result.proxy_rotations == ((0, 1, 0, 0), (0, 0, 0, 2))
    assert result.proxy_positions == ((3, 0, 0), (100, 100, 100))
    assert result.results[0].state.old_animation_rotation == Q


def test_positive_range_snapshots_outer_proxy_sequences():
    positions = [Z, (100, 100, 100)]
    rotations = [Q, (0, 0, 0, 2)]
    result = calculate_display_positions(
        (state(),),
        (1,),
        {1: team(particle_chunk_start=0)},
        simulation_delta_time=0.5,
        attributes=(0,),
        proxy_positions=positions,
        proxy_rotations=rotations,
        vertex_root_indices=(),
        index_count=1,
    )
    positions[1] = (200, 200, 200)
    rotations[1] = Q
    assert result.proxy_positions[1] == (100, 100, 100)
    assert result.proxy_rotations[1] == (0, 0, 0, 2)


def test_prediction_multiply_is_single_before_widening_not_double_multiply():
    result = run(
        state(old_position=Z, display_position=Z, real_velocity=(1 / 3, 0, 0)),
        team(time=1, old_time=0, now_update_time=0),
        simulation_delta_time=3,
        proxy_positions=(Z,),
    )
    assert result.state.display_position == (0.3333333432674408, 0, 0)
    # Single((1/3f)*3f)=1; alpha=1/3f, not Double multiplication of velocity.


def test_large_world_positions_remain_double():
    p = (1e12 + 0.125, -2e12 + 0.25, 3e12 - 0.5)
    result = run(
        state(old_position=p, display_position=p, real_velocity=Z),
        attributes=(2,),
        proxy_positions=(p,),
    )
    assert result.state.display_position == result.proxy_position == p


@pytest.mark.parametrize(
    "changes",
    [
        {"team_id": -1},
        {"team_id": 32768},
        {"team_id": True},
        {"particle_index": -1},
        {"particle_index": 2**31},
        {"attributes": (256,)},
        {"attributes": (True,)},
        {"attributes": ()},
        {"proxy_positions": ()},
        {"proxy_rotations": ()},
        {"vertex_root_indices": ()},
        {"vertex_root_indices": (1,)},
        {"vertex_root_indices": (True,)},
        {"simulation_delta_time": math.inf},
    ],
)
def test_adapter_rejects_consumed_invalid_inputs(changes):
    with pytest.raises(ValueError):
        run(**changes)


@pytest.mark.parametrize(
    "changes",
    [
        {"flag": True},
        {"flag": 2**64},
        {"particle_chunk_start": -1},
        {"proxy_common_chunk_start": -1},
        {"time": math.nan},
        {"now_update_time": math.inf},
        {"old_time": math.nan},
        {"blend_weight": math.inf},
    ],
)
def test_adapter_rejects_consumed_bad_team_inputs(changes):
    with pytest.raises(ValueError):
        run(t=team(**changes))


def test_negative_scale_is_not_consumed_when_flag_absent():
    assert run(t=team(negative_scale_direction=(math.nan,) * 3)).proxy_rotation is None


def test_degenerate_negative_scale_is_adapter_error_not_native_policy():
    with pytest.raises(ValueError):
        run(t=team(flag=0x20002, negative_scale_direction=(1, 0, 1)))


def test_serial_range_reads_root_after_earlier_root_proxy_write():
    s0 = state(old_position=(2, 0, 0), display_position=(2, 0, 0), real_velocity=Z)
    s1 = state(old_position=(7, 0, 0), display_position=(7, 0, 0), real_velocity=Z)
    result = calculate_display_positions(
        (s0, s1),
        (1, 1),
        {1: team(particle_chunk_start=0)},
        simulation_delta_time=0.5,
        attributes=(2, 2),
        proxy_positions=(Z, (3, 0, 0)),
        proxy_rotations=(Q, Q),
        vertex_root_indices=(-1, 0),
        index_count=2,
    )
    assert result.proxy_positions[0] == (2, 0, 0)
    assert result.proxy_positions[1][0] == pytest.approx(2 + 1.2999999523162842)
    assert result.results[1].state.display_position == result.proxy_positions[1]


@pytest.mark.parametrize("count", [0, -1, -(2**31)])
def test_empty_range_reads_no_time_or_inputs_and_preserves_full_buffers(count):
    positions = (Z,)
    rotations = (Q,)
    result = calculate_display_positions(
        (),
        (),
        {},
        simulation_delta_time=math.nan,
        attributes=(),
        proxy_positions=positions,
        proxy_rotations=rotations,
        vertex_root_indices=(),
        index_count=count,
    )
    assert result.results == () and result.proxy_positions is positions
    assert result.proxy_rotations is rotations


def test_empty_range_does_not_iterate_proxy_buffers():
    class Poison:
        def __len__(self):
            raise AssertionError("unselected length read")

        def __getitem__(self, index):
            raise AssertionError(f"unselected item read {index}")

    positions = cast(Any, Poison())
    rotations = cast(Any, Poison())
    result = calculate_display_positions(
        (),
        (),
        {},
        simulation_delta_time=math.nan,
        attributes=(),
        proxy_positions=positions,
        proxy_rotations=rotations,
        vertex_root_indices=(),
        index_count=0,
    )
    assert result.proxy_positions is positions and result.proxy_rotations is rotations


@pytest.mark.parametrize("count", [True, 1.5, 2**31])
def test_range_count_requires_int32(count):
    with pytest.raises(ValueError):
        calculate_display_positions(
            (),
            (),
            {},
            simulation_delta_time=0,
            attributes=(),
            proxy_positions=(),
            proxy_rotations=(),
            vertex_root_indices=(),
            index_count=count,
        )


@pytest.mark.parametrize(
    "states,ids,teams", [((), (0,), {}), ((state(),), (), {}), ((state(),), (1,), {})]
)
def test_range_rejects_missing_consumed_buffers_and_team(states, ids, teams):
    with pytest.raises(ValueError):
        calculate_display_positions(
            states,
            ids,
            teams,
            simulation_delta_time=0,
            attributes=(),
            proxy_positions=(),
            proxy_rotations=(),
            vertex_root_indices=(),
            index_count=1,
        )


def test_range_team_zero_does_not_validate_unselected_dirty_buffers():
    original = state()
    result = calculate_display_positions(
        (original,),
        (0,),
        {},
        simulation_delta_time=math.nan,
        attributes=(),
        proxy_positions=(),
        proxy_rotations=(),
        vertex_root_indices=(),
        index_count=1,
    )
    assert result.results[0].state is original and result.results[0].writes == ()


def test_range_nonprocess_preserves_proxy_and_particle_history_without_writes():
    original = state()
    result = calculate_display_positions(
        (original,),
        (1,),
        {1: team(flag=0x12)},
        simulation_delta_time=math.nan,
        attributes=(),
        proxy_positions=(Z,),
        proxy_rotations=(Q,),
        vertex_root_indices=(),
        index_count=1,
    )
    assert result.results[0].state is original and result.results[0].proxy_index is None
    assert result.proxy_positions == (Z,) and result.proxy_rotations == (Q,)


def test_failed_range_does_not_mutate_caller_proxy_values():
    positions = [Z, (3, 0, 0)]
    with pytest.raises(ValueError):
        calculate_display_positions(
            (state(), state()),
            (1, 2),
            {1: team(particle_chunk_start=0)},
            simulation_delta_time=0.5,
            attributes=(2, 2),
            proxy_positions=positions,
            proxy_rotations=(Q, Q),
            vertex_root_indices=(-1, -1),
            index_count=2,
        )
    assert positions == [Z, (3, 0, 0)]


def test_reset_display_and_next_frame_keep_simulation_display_and_animation_histories_distinct():
    initial = prepare_particle_frame(
        state(),
        ParticleResetTeam(6, 7, 0),
        team_id=1,
        particle_index=7,
        proxy_positions=((3, 0, 0),),
        proxy_rotations=(Q,),
    ).state
    moved = replace(initial, old_position=(10, 0, 0), real_velocity=(4, 0, 0))
    first = run(moved, team(flag=0x22, blend_weight=0.25))
    assert first.state.display_position == (7.5, 0, 0)
    assert first.proxy_position == (4.125, 0, 0)
    assert first.state.old_animation_position == (
        3,
        0,
        0,
    ) and first.state.old_position == (10, 0, 0)
    second = run(
        first.state,
        team(flag=2, time=1, old_time=0.5, now_update_time=1),
        proxy_positions=((5, 0, 0),),
    )
    assert second.state.display_position == (9.75, 0, 0)
    assert second.state.old_animation_position == (3, 0, 0)


def test_reset_two_substeps_display_next_start_consumes_history_then_restart():
    initial = prepare_particle_frame(
        state(),
        ParticleResetTeam(6, 7, 0),
        team_id=1,
        particle_index=7,
        proxy_positions=((3, 0, 0),),
        proxy_rotations=(Q,),
    ).state
    particle = initial
    # Explicit finite fixture centers, not defaults or evidence of native generation.
    start_center = ResolvedStartCenter(Z, Z, Q, Z, Q)
    end_center = ResolvedCenter(Z, (0, 1, 0), 0)
    for _ in range(2):
        start = start_particle_step(
            ParticleStartState(
                particle.old_position,
                particle.old_animation_position,
                particle.old_animation_rotation,
                (3, 0, 0),
                Q,
                particle.velocity,
                0,
            ),
            StartStepSettings(1, 1, 0.5, (0,) * 16, 1, 1, 1, 2, (0, -1, 0), 1, Z, 0),
            attribute=2,
            center=start_center,
            wind=(2, 0, 0),
        )
        end = finish_particle_step(
            ParticleEndState(
                start.next_position,
                particle.old_position,
                start.velocity_position,
                particle.velocity,
                particle.friction,
                particle.static_friction,
                particle.collision_normal,
                0,
            ),
            EndStepSettings(0.5, 1, 1, -1, 0, 0, 0),
            attribute=2,
            center=end_center,
        )
        particle = replace(
            particle,
            old_position=end.old_position,
            velocity=end.velocity,
            real_velocity=end.real_velocity,
            friction=end.friction,
            static_friction=end.static_friction,
        )
    assert particle.old_position == (4.5, -1.5, 0) and particle.real_velocity == (
        2,
        -2,
        0,
    )
    shown_range = calculate_display_positions(
        (particle,),
        (1,),
        {
            1: team(
                flag=0x20022,
                particle_chunk_start=0,
                blend_weight=0.25,
                negative_scale_direction=(1, -1, 1),
            )
        },
        simulation_delta_time=0.5,
        attributes=(2,),
        proxy_positions=((5, 0, 0),),
        proxy_rotations=(Q,),
        vertex_root_indices=(-1,),
        index_count=1,
    )
    shown = shown_range.results[0]
    assert shown.state.display_position == (4.25, -1.25, 0)
    assert shown.proxy_position == (4.8125, -0.3125, 0)
    assert shown.state.old_animation_position == (5, 0, 0)  # Not blended output!
    assert (
        shown.state.old_position == particle.old_position
    )  # Display never feeds simulation.
    # Next non-reset Start consumes flag20's ORIGINAL animation history while
    # receiving this range's blended/negative-scale proxy output as its new pose.
    following = start_particle_step(
        ParticleStartState(
            shown.state.old_position,
            shown.state.old_animation_position,
            shown.state.old_animation_rotation,
            shown_range.proxy_positions[0],
            shown_range.proxy_rotations[0],
            shown.state.velocity,
            0,
        ),
        StartStepSettings(0.25, 1, 0.5, (0,) * 16, 1, 1, 1, 2, (0, -1, 0), 1, Z, 0),
        attribute=2,
        center=start_center,
        wind=Z,
    )
    assert following.base_position == (4.953125, -0.078125, 0)
    assert following.base_rotation == pytest.approx(
        (0, 0, 0.3826834261417389, 0.9238795042037964), abs=3e-7
    )
    restarted = prepare_particle_frame(
        shown.state,
        ParticleResetTeam(6, 7, 0),
        team_id=1,
        particle_index=7,
        proxy_positions=((42, 43, 44),),
        proxy_rotations=(Q,),
    ).state
    assert (
        restarted.old_position
        == restarted.display_position
        == restarted.old_animation_position
        == (42, 43, 44)
    )
    assert restarted.real_velocity == restarted.velocity == Z
