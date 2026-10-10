"""Independent fixtures for the distinct managed Double collider Job path."""

import math
import sys
from dataclasses import replace
from pathlib import Path
from typing import cast

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from official_physics_collider_frame import (
    ColliderFrameTeam,
    prepare_collider_frame,
)
from official_physics_collider_job import (
    ColliderJobState,
    end_collider_job,
    end_collider_jobs,
    finish_collider_job_frame,
    start_collider_job,
    start_collider_jobs,
)
from official_physics_collider_step import (
    ColliderStepCenter,
    ColliderStepState,
    ColliderStepTeam,
    start_collider_step,
)
from official_physics_constraints import _single
from official_physics_point_collision import (
    ColliderWork,
    PointCollisionParameters,
    PointCollisionState,
    PointCollisionTeam,
    point_collision_particle,
)

ZERO = (0.0, 0.0, 0.0)
Q = (0.0, 0.0, 0.0, 1.0)


def state(shape: int = 1, **changes) -> ColliderJobState:
    value = ColliderJobState(
        flag=0x30 | shape,
        frame_position=(3.0, 0.0, 0.0),
        frame_rotation=Q,
        frame_scale=(1.0, 1.0, 1.0),
        old_frame_position=ZERO,
        old_frame_rotation=Q,
        now_position=(101.0, 102.0, 103.0),
        now_rotation=(1.0, 0.0, 0.0, 0.0),
        old_position=ZERO,
        old_rotation=Q,
        size=(1.0, 2.0, 10.0),
        work=None,
    )
    return replace(value, **changes)


def run(
    value: ColliderJobState | None = None,
    *,
    interpolation: float = 1,
    move: float = 0,
    rotation: float = 1,
):
    return start_collider_job(
        state() if value is None else value,
        ColliderStepTeam(interpolation),
        ColliderStepCenter(move, rotation),
    )


def work_of(value: ColliderJobState) -> ColliderWork:
    assert value.work is not None
    return value.work


@pytest.mark.parametrize("flag", [0, 0x10, 0x20, 0x81])
def test_inactive_job_preserves_every_field_without_reading_numeric_inputs(flag):
    original = state(flag=flag, frame_position=(math.nan, 0, 0))
    result = run(original, interpolation=math.nan, move=math.nan)
    assert result.state is original
    assert result.writes == ()


@pytest.mark.parametrize("flag", [-1, 256, True])
def test_adapter_flag_domain_is_explicit(flag):
    with pytest.raises(ValueError, match="integer"):
        run(state(flag=flag))


def test_single_value_state_cannot_silently_enter_double_job():
    single = ColliderStepState(
        0x31, (1, 2, 10), ZERO, Q, (1, 1, 1), ZERO, Q, ZERO, Q, ZERO, Q, None
    )
    with pytest.raises(TypeError, match="Double"):
        run(cast(ColliderJobState, single))


def test_double_positions_survive_two_lerps_without_single_narrowing():
    origin = 1e12
    original = state(
        frame_position=(origin + 0.5, 4, 8),
        old_frame_position=(origin, 0, 0),
        old_position=(origin - 0.25, -4, -8),
    )
    result = run(original, interpolation=0.25, move=0.5)
    assert result.state.now_position == (origin + 0.125, 1, 2)
    assert result.state.old_position == (origin - 0.0625, -1.5, -3)
    assert work_of(result.state).next_points[0] == result.state.now_position
    assert result.state.now_position[0] != _single(origin)
    assert result.writes == (
        "now_position",
        "now_rotation",
        "old_position",
        "old_rotation",
        "work",
    )
    assert result.state.old_frame_position == original.old_frame_position


def test_interpolation_ratio_is_single_then_widened_not_python_double():
    ratio = 0.100000001
    result = run(state(frame_position=(1, 0, 0)), interpolation=ratio)
    assert result.state.now_position[0] == _single(ratio)
    assert result.state.now_position[0] != ratio


@pytest.mark.parametrize("fraction,expected", [(-0.5, -2), (1.5, 6)])
def test_double_lerp_extrapolates_without_clamp(fraction, expected):
    assert (
        run(state(frame_position=(4, 0, 0)), interpolation=fraction).state.now_position[
            0
        ]
        == expected
    )


def test_move_ratio_extrapolates_without_clamp():
    assert run(state(old_position=(1, 0, 0)), move=1.5).state.old_position == (4, 0, 0)


def test_sphere_scale_is_single_but_center_and_bounds_are_double():
    origin = 2**24 + 0.5
    value = state(
        frame_position=(origin, 0, 0),
        old_position=(origin, 0, 0),
        size=(0.125, 50, 60),
        frame_scale=(-2, 40, 60),
    )
    work = work_of(run(value).state)
    assert work.radii == (0.25, 0.25)
    assert work.aabb_min == (origin - 0.25, -0.25, -0.25)
    assert work.aabb_max == (origin + 0.25, 0.25, 0.25)
    assert work.old_points == work.next_points == ((origin, 0, 0), ZERO)


@pytest.mark.parametrize("shape,axis", [(2, 0), (3, 1), (4, 2), (5, 0), (6, 1), (7, 2)])
def test_all_capsules_keep_double_centers_and_correct_length_convention(shape, axis):
    origin = 2**24 + 0.5
    center = (origin, origin, origin)
    work = work_of(run(state(shape, frame_position=center, old_position=center)).state)
    first, second = list(center), list(center)
    first[axis] += 4 if shape <= 4 else 0
    second[axis] -= 3 if shape <= 4 else 7
    assert work.old_points == work.next_points == (tuple(first), tuple(second))
    assert work.aabb_min[axis] == origin - (5 if shape <= 4 else 9)
    assert work.aabb_max[axis] == origin + (5 if shape <= 4 else 1)
    assert work.aabb_min[(axis + 1) % 3] == origin - 2


@pytest.mark.parametrize(
    "scale,reverse,expected",
    [(2, False, 8), (-2, False, -8), (2, True, -8), (-2, True, 8)],
)
def test_capsule_signed_axial_scale_and_reverse_are_still_single(
    scale, reverse, expected
):
    value = state(
        2,
        flag=0x32 | (0x80 if reverse else 0),
        frame_position=ZERO,
        frame_scale=(scale, 9, 11),
    )
    work = work_of(run(value).state)
    assert work.radii == (2, 4)
    assert work.old_points == ((expected, 0, 0), (-expected * 0.75, 0, 0))


def test_capsule_clamps_each_nonpositive_segment_to_zero():
    work = work_of(run(state(2, size=(4, 5, 2), frame_position=ZERO)).state)
    assert work.old_points == work.next_points == (ZERO, ZERO)
    assert work.aabb_min == (-5, -5, -5)
    assert work.aabb_max == (5, 5, 5)


def test_zero_axial_scale_collapses_offsets_and_radii_without_losing_double_center():
    value = state(3, frame_position=(1e12 + 0.125, 0, 0), frame_scale=(7, 0, 9))
    work = work_of(run(value).state)
    assert work.radii == (0, 0)
    assert work.old_points == (ZERO, ZERO)
    assert work.next_points == (value.frame_position, value.frame_position)


def test_capsule_offset_rotation_is_single_then_widened_not_double_rotation():
    half = math.sqrt(0.5)
    origin = 1e9 + 0.125
    value = state(
        2,
        frame_position=(origin, 0, 0),
        old_position=(origin, 0, 0),
        frame_rotation=(0, 0, half, half),
    )
    work = work_of(run(value).state)
    # Native Single quaternion/rotate produces a residual x offset, retained
    # when widened and added to the Double center, rather than re-rotated Double.
    qz = _single(half)
    rounded_product = _single(qz * _single(8 * qz))
    assert work.next_points[0][0] == origin + _single(4 - rounded_product)
    assert work.next_points[0][1] == rounded_product
    assert work.next_points[0][0] != origin


def test_raw_second_slerp_not_normalized_storage_drives_old_shape_and_inverse():
    value = run(
        state(2, frame_position=ZERO, old_rotation=(0, 0, 2, 0)), rotation=0.5
    ).state
    work = work_of(value)
    assert work.old_points[0] == pytest.approx((-12, 8, 0), abs=3e-6)
    assert value.old_rotation == pytest.approx(
        (0, 0, 2 / math.sqrt(5), 1 / math.sqrt(5)), abs=2e-7
    )
    assert work.inverse_old_rotation == pytest.approx(
        (0, 0, -math.sqrt(2) / 2.5, math.sqrt(0.5) / 2.5), abs=2e-7
    )


@pytest.mark.parametrize(
    "scale_y,normal", [(2, (0, 1, 0)), (-2, (0, -1, 0)), (0, ZERO)]
)
def test_plane_packs_single_normal_and_double_next_center_and_ignores_reverse(
    scale_y, normal
):
    value = state(
        8, flag=0xB8, frame_position=(1e12 + 0.125, 0, 0), frame_scale=(8, scale_y, 10)
    )
    work = work_of(run(value).state)
    assert work.old_points == (normal, ZERO)
    assert work.next_points == (value.frame_position, ZERO)
    assert work.aabb_min == work.aabb_max == ZERO
    assert work.radii == (0, 0)


@pytest.mark.parametrize("shape", [0, 9, 15])
def test_unsupported_shape_zeros_geometry_but_keeps_rotation_writes(shape):
    prior = work_of(run().state)
    value = run(state(shape, work=prior)).state
    work = work_of(value)
    assert work is not prior
    assert work.old_points == work.next_points == (ZERO, ZERO)
    assert work.aabb_min == work.aabb_max == ZERO
    assert work.radii == (0, 0)
    assert work.rotation == work.inverse_old_rotation == Q


def test_end_selected_job_has_no_flag_gate_and_copies_double_now_not_frame():
    value = state(flag=0, now_position=(1e12 + 0.125, 2, 3), now_rotation=(0, 0, 0, 2))
    result = end_collider_job(value)
    assert result.state.old_position == value.now_position
    assert result.state.old_rotation == value.now_rotation
    assert result.state.frame_position == value.frame_position
    assert result.writes == ("old_position", "old_rotation")


def test_start_range_uses_sparse_global_ids_signed_teams_and_duplicate_feedback():
    values = (state(), state(frame_position=(4, 0, 0)), state())
    result = start_collider_jobs(
        values,
        {-1: ColliderStepTeam(1)},
        {-1: ColliderStepCenter(0.5, 1)},
        step_collider_indices=(1, 1, 999),
        team_ids=(99, -1),
        index_count=2,
    )
    assert [visit.collider_index for visit in result.visits] == [1, 1]
    assert [visit.team_id for visit in result.visits] == [-1, -1]
    assert result.visits[0].result.state.old_position == (2, 0, 0)
    assert result.visits[1].result.state.old_position == (3, 0, 0)
    assert result.states[1].old_position == (3, 0, 0)
    assert result.states[0] is values[0] and result.states[2] is values[2]
    assert values[1].old_position == ZERO


def test_start_range_team_zero_has_no_special_skip():
    result = start_collider_jobs(
        (state(),),
        {0: ColliderStepTeam(1)},
        {0: ColliderStepCenter(0, 1)},
        step_collider_indices=(0,),
        team_ids=(0,),
        index_count=1,
    )
    assert result.visits[0].result.writes


def test_inactive_start_range_returns_before_any_team_lookup():
    original = state(flag=0)
    result = start_collider_jobs(
        (original,), {}, {}, step_collider_indices=(0,), team_ids=(), index_count=1
    )
    assert result.states[0] is original
    assert result.visits[0].team_id is None
    assert result.visits[0].result.writes == ()


@pytest.mark.parametrize("count", [0, -1])
def test_empty_start_range_reads_no_selected_entries(count):
    original = state()
    result = start_collider_jobs(
        (original,),
        {},
        {},
        step_collider_indices=(999,),
        team_ids=(),
        index_count=count,
    )
    assert result.states == (original,)
    assert result.visits == ()


@pytest.mark.parametrize(
    "indices,ids,teams,centers,count",
    [
        ((0,), (0,), {0: ColliderStepTeam(1)}, {0: ColliderStepCenter(0, 1)}, 2),
        ((3,), (0,), {}, {}, 1),
        ((-1,), (0,), {}, {}, 1),
        ((0,), (), {}, {}, 1),
        ((0,), (32768,), {}, {}, 1),
        ((0,), (0,), {}, {0: ColliderStepCenter(0, 1)}, 1),
        ((0,), (0,), {0: ColliderStepTeam(1)}, {}, 1),
    ],
)
def test_start_adapter_rejects_missing_inputs_or_bad_bounds_before_publication(
    indices, ids, teams, centers, count
):
    original = state()
    with pytest.raises(ValueError):
        start_collider_jobs(
            (original,),
            teams,
            centers,
            step_collider_indices=indices,
            team_ids=ids,
            index_count=count,
        )
    assert original.old_position == ZERO


def test_end_range_is_sparse_ordered_global_selection_not_full_buffer():
    values = (
        state(now_position=(5, 0, 0)),
        state(now_position=(6, 0, 0)),
        state(now_position=(7, 0, 0)),
    )
    result = end_collider_jobs(
        values, step_collider_indices=(2, 0, 2, 999), index_count=3
    )
    assert result[1] is values[1]
    assert result[0].old_position == (5, 0, 0)
    assert result[2].old_position == (7, 0, 0)
    assert values[0].old_position == ZERO


@pytest.mark.parametrize("count", [0, -1])
def test_empty_end_range_does_not_inspect_entries(count):
    assert (
        end_collider_jobs((state(),), step_collider_indices=(999,), index_count=count)[
            0
        ].old_position
        == ZERO
    )


@pytest.mark.parametrize(
    "count,indices", [(2, (0,)), (1, (3,)), (1, (-1,)), (True, (0,))]
)
def test_end_adapter_rejects_bad_selected_bounds_without_publishing(count, indices):
    original = state()
    with pytest.raises(ValueError):
        end_collider_jobs((original,), step_collider_indices=indices, index_count=count)
    assert original.old_position == ZERO


@pytest.mark.parametrize(
    "flag", [0, 2, 0x22 | 0x10, 0x22 | 0x800, 0x22 | 0x80000, 0x22 | (1 << 61)]
)
def test_post_team_process_and_update_gates_leave_histories_untouched(flag):
    original = state()
    result = finish_collider_job_frame(original, team_flag=flag)
    assert result.state is original
    assert result.writes == ()


def test_post_uses_full_double_frame_target_not_current_interpolated_position():
    value = run(
        state(frame_position=(1e12 + 0.5, 0, 0), old_frame_position=(1e12, 0, 0)),
        interpolation=0.25,
    ).state
    result = finish_collider_job_frame(value, team_flag=0x22)
    assert result.state.old_frame_position == (1e12 + 0.5, 0, 0)
    assert result.state.now_position == (1e12 + 0.125, 0, 0)
    assert result.writes == ("old_frame_position", "old_frame_rotation")


def test_pre_double_start_end_post_next_frame_retains_distinct_histories():
    value = state()
    prepared = prepare_collider_frame(
        value,
        ColliderFrameTeam(2 | 4, 0, 0, (1, 1, 1)),
        collider_index=0,
        centers=(ZERO,),
        transform_positions=((1e12, 0, 0),),
        transform_rotations=(Q,),
        transform_scales=((1, 1, 1),),
    ).state
    assert isinstance(prepared, ColliderJobState)
    assert prepared.old_position == prepared.old_frame_position == (1e12, 0, 0)
    value = run(
        replace(prepared, frame_position=(1e12 + 1, 0, 0)), interpolation=0.5, move=0.25
    ).state
    assert value.now_position == (1e12 + 0.5, 0, 0)
    assert value.old_position == (1e12 + 0.125, 0, 0)
    value = end_collider_job(value).state
    assert value.old_position == (1e12 + 0.5, 0, 0)
    value = finish_collider_job_frame(value, team_flag=0x22).state
    assert value.old_frame_position == (1e12 + 1, 0, 0)
    value = run(
        replace(value, frame_position=(1e12 + 2, 0, 0)), interpolation=0.5, move=0.25
    ).state
    assert value.now_position == (1e12 + 1.5, 0, 0)
    assert value.old_position == (1e12 + 0.75, 0, 0)


@pytest.mark.parametrize("shape", [1, 3])
def test_job_produced_work_flows_through_existing_point_consumer(shape):
    value = run(state(shape, frame_position=(1, 0, 0), size=(1, 1, 4)), move=0.5).state
    particle = PointCollisionState((0.75, 0, 0), ZERO, ZERO, 0, ZERO)
    result = point_collision_particle(
        particle,
        PointCollisionTeam(0, 1, 0, 1),
        PointCollisionParameters(1, (0.25,) * 16, (0.1,) * 16),
        attribute=2,
        depth=0.5,
        colliders=(work_of(value),),
    )
    assert result.state.next_position == (2.25, 0, 0)


def test_single_and_double_routes_are_not_artificially_equated():
    origin = 2**24 + 0.5
    double = state(
        2,
        size=(0.25, 0.25, 0),
        frame_position=(origin, 0, 0),
        old_position=(origin, 0, 0),
    )
    single = ColliderStepState(
        double.flag,
        double.size,
        double.frame_position,
        double.frame_rotation,
        double.frame_scale,
        double.old_frame_position,
        double.old_frame_rotation,
        double.now_position,
        double.now_rotation,
        double.old_position,
        double.old_rotation,
        None,
    )
    double_work = work_of(run(double).state)
    single_work = start_collider_step(
        single, ColliderStepTeam(1), ColliderStepCenter(0, 1)
    ).state.work
    assert single_work is not None
    assert double_work.aabb_min[0] == origin - 0.25
    assert double_work.aabb_max[0] == origin + 0.25
    assert single_work.aabb_min[0] == single_work.aabb_max[0] == _single(origin)
