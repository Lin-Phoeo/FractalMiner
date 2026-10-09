"""Source-bound frame correction probes; all poses are synthetic resolved inputs."""

import math
import sys
from dataclasses import replace
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from official_physics_center_step import (
    CenterStepState,
    CenterStepTeam,
    LocalInertiaSettings,
    advance_center_step,
)
from official_physics_constraints import _single
from official_physics_frame_inertia import (
    FrameInertiaSettings,
    FrameInertiaState,
    FrameInertiaTeam,
    advance_frame_inertia,
    frame_scale_length_ratio,
    shift_world_position,
)
from official_physics_particle_step import (
    EndStepSettings,
    ParticleEndState,
    finish_particle_step,
)
from official_physics_start_step import (
    ParticleStartState,
    StartStepSettings,
    start_particle_step,
)
from official_physics_team_tail import (
    FrameWindState,
    TeamWindState,
    WindInfo,
    WindStepSettings,
    advance_wind_state,
)

Q = (0.0, 0.0, 0.0, 1.0)
Z = (0.0, 0.0, 0.0)
S = (1.0, 1.0, 1.0)


def state(**changes):
    step = CenterStepState((1, 2, 3), Q, (10, 2, 3), Q, S, S, (2, 3, 4), Q)
    return replace(
        FrameInertiaState((4, 0, 0), Q, Z, Q, Z, Z, Q, Z, step, S), **changes
    )


def team(**changes):
    return replace(FrameInertiaTeam(2, 1, 1, 0, 1, 0.25), **changes)


def settings(**changes):
    return replace(FrameInertiaSettings(1, -1, -1, 1), **changes)


def run(s=None, t=None, cfg=None):
    return advance_frame_inertia(s or state(), t or team(), cfg or settings())


def test_no_correction_preserves_world_history_but_records_initial_component_delta():
    s = state()
    result = run(s)
    assert result.component_shift_vector == (4, 0, 0)
    assert result.component_shift_rotation == Q
    assert result.corrected_old_component_position == Z
    assert result.motion.delta_single == (4, 0, 0)
    assert result.motion.speed == 4
    assert result.step_state is s.step_state
    assert result.flag == 2 and not result.world_history_shifted


@pytest.mark.parametrize("inertia,expected", [(0, 4), (0.25, 3), (0.5, 2), (1, 0)])
def test_world_inertia_moves_working_old_component_towards_current(inertia, expected):
    result = run(cfg=settings(world_inertia=inertia))
    assert result.corrected_old_component_position == (expected, 0, 0)
    assert result.motion.delta_single == (4 - expected, 0, 0)
    if inertia < 1:
        assert result.component_shift_vector == (expected, 0, 0)
        assert result.step_state.old_frame_world_position == (1 + expected, 2, 3)
        assert result.step_state.now_world_position == (2 + expected, 3, 4)
        assert result.world_history_shifted and result.flag == 0x402


@pytest.mark.parametrize("flag", [2 | 0x200, 2 | 0x800, 2 | 0x80000])
def test_keep_teleport_or_invisible_culling_forces_full_follow(flag):
    result = run(t=team(flag=flag))
    assert result.corrected_old_component_position == (4, 0, 0)
    assert result.motion.speed == 0
    assert result.translation_fraction == result.rotation_fraction == 1


def test_world_follow_uses_single_complement_and_one_e_minus_eight_gate():
    # Adjacent Single below 1 differs by 2^-24: greater than 1e-8, less than 1e-6.
    result = run(cfg=settings(world_inertia=1 - 2**-24))
    assert result.translation_fraction == 2**-24
    assert result.corrected_old_component_position == (4 * 2**-24, 0, 0)
    assert result.world_history_shifted


@pytest.mark.parametrize("limit,expected", [(2, 2), (0, 4), (4, 0), (-1, 0)])
def test_movement_limit_including_equality_and_disabled_negative(limit, expected):
    result = run(cfg=settings(movement_speed_limit=limit))
    assert result.corrected_old_component_position == (expected, 0, 0)


def test_movement_limit_uses_separate_source_scale_length_ratio():
    assert frame_scale_length_ratio((2, 2, 2), S) == 2
    result = run(cfg=settings(movement_speed_limit=1, scale_length_ratio=2))
    assert result.corrected_old_component_position == (2, 0, 0)
    assert result.motion.speed == 2


def test_frame_scale_length_ratio_uses_lengths_not_one_axis_or_signed_scale():
    assert frame_scale_length_ratio((3, 4, 0), (0, 0, -2)) == 2.5
    with pytest.raises(ValueError, match="denominator"):
        frame_scale_length_ratio(S, Z)


def test_movement_limit_is_applied_after_global_follow_and_accumulates_fraction():
    result = run(cfg=settings(world_inertia=0.5, movement_speed_limit=1))
    assert result.corrected_old_component_position == (3, 0, 0)
    assert result.translation_fraction == 0.75
    assert result.component_shift_vector == (3, 0, 0)
    assert result.motion.speed == 1


def test_rotation_limit_is_independent_from_translation_limit():
    half = math.sqrt(0.5)
    result = run(
        state(component_world_rotation=(0, 0, half, half)),
        cfg=settings(rotation_speed_limit=45),
    )
    assert result.translation_fraction == 0
    assert result.rotation_fraction == pytest.approx(0.5, abs=2e-7)
    assert result.component_shift_rotation == pytest.approx(
        (0, 0, math.sin(math.pi / 8), math.cos(math.pi / 8)), abs=2e-7
    )
    assert result.motion.speed == 4


@pytest.mark.parametrize("dt", [0, -1])
def test_nonpositive_frame_time_zeroes_limit_speeds_without_zeroing_direction(dt):
    result = run(t=team(frame_delta_time=dt), cfg=settings(movement_speed_limit=1))
    assert result.corrected_old_component_position == Z
    assert result.motion.speed == 0
    assert result.motion.direction == (1, 0, 0)


@pytest.mark.parametrize("count,expected", [(0, 0), (1, 1), (2, 2), (5, 4)])
def test_update_count_uses_simulation_time_over_scaled_frame_time(count, expected):
    result = run(t=team(update_count=count))
    assert result.corrected_old_component_position == (expected, 0, 0)
    assert result.compensation_fraction == expected / 4


def test_velocity_weight_not_blend_weight_drives_compensation():
    result = run(t=team(update_count=1, velocity_weight=0.5))
    assert result.compensation_fraction == 0.625
    assert result.corrected_old_component_position == (2.5, 0, 0)


def test_time_scale_compensation_follows_count_and_velocity_weight():
    result = run(t=team(now_time_scale=0.5, update_count=1, velocity_weight=0.5))
    assert result.compensation_fraction == 0.875
    assert result.corrected_old_component_position == (3.5, 0, 0)
    # Final motion uses reciprocal timeScale a second time, after correcting work.
    assert result.motion.speed == 1


def test_zero_time_scale_with_no_steps_follows_component_and_zeroes_speed():
    result = run(t=team(now_time_scale=0))
    assert result.compensation_fraction == 1
    assert result.corrected_old_component_position == (4, 0, 0)
    assert result.motion.speed == 0


@pytest.mark.parametrize("time_scale,dt", [(0, 1), (1, 0)])
def test_adapter_rejects_undefined_count_division_instead_of_returning_zero(
    time_scale, dt
):
    with pytest.raises(ValueError, match="denominator"):
        run(t=team(update_count=1, now_time_scale=time_scale, frame_delta_time=dt))


def test_final_shift_combines_initial_delta_with_prior_anchor_shift():
    result = run(
        state(anchor_shift_vector=(10, 0, 0)),
        cfg=settings(world_inertia=0.5, movement_speed_limit=1),
    )
    assert result.component_shift_vector == (13, 0, 0)
    assert result.motion.delta_single == (1, 0, 0)
    assert result.step_state.old_frame_world_position == (14, 2, 3)


def test_final_shift_adds_resolved_smoothing_offset_after_anchor_offset():
    result = run(
        state(anchor_shift_vector=(10, 0, 0), smoothing_shift_vector=(2, -1, 3)),
        cfg=settings(world_inertia=0.5, movement_speed_limit=1),
    )
    assert result.component_shift_vector == (15, -1, 3)
    assert result.motion.delta_single == (1, 0, 0)
    assert result.step_state.old_frame_world_position == (16, 1, 6)


def test_anchor_then_smoothing_are_two_separate_single_additions():
    result = run(
        state(
            anchor_shift_vector=(2**24, 0, 0),
            smoothing_shift_vector=(-(2**24), 0, 0),
        ),
        cfg=settings(world_inertia=0.75),
    )
    # (1f + 16777216f) + -16777216f == 0f; regrouping the offsets yields 1f.
    assert result.component_shift_vector == Z
    assert result.motion.delta_single == (3, 0, 0)


def test_global_limits_and_count_compensation_share_initial_delta():
    half = math.sqrt(0.5)
    result = run(
        state(
            component_world_rotation=(0, 0, half, half),
            anchor_shift_vector=(10, 0, 0),
            smoothing_shift_vector=(2, 0, 0),
        ),
        team(
            now_time_scale=0.5,
            update_count=1,
            simulation_delta_time=0.125,
            velocity_weight=0.5,
        ),
        settings(world_inertia=0.5, movement_speed_limit=1, rotation_speed_limit=22.5),
    )
    assert result.compensation_fraction == 0.8125
    assert result.translation_fraction == 0.953125
    assert result.rotation_fraction == pytest.approx(0.953125, abs=2e-7)
    assert result.component_shift_vector == (15.8125, 0, 0)
    assert result.motion.delta_single == (0.1875, 0, 0)
    assert result.motion.speed == 0.375
    angle = math.pi / 4 * 0.953125
    assert result.component_shift_rotation == pytest.approx(
        (0, 0, math.sin(angle), math.cos(angle)), abs=3e-7
    )


def test_nonbinary_compensation_has_source_order_single_golden_values():
    result = run(
        t=team(
            update_count=7,
            simulation_delta_time=0.0012345,
            frame_delta_time=0.0333333,
            now_time_scale=0.61,
            velocity_weight=0.82,
        ),
        cfg=settings(world_inertia=0.5),
    )
    # Independent struct-Single calculation; catches multiplication/division regrouping.
    assert result.compensation_fraction == 0.71238112449646
    assert result.translation_fraction == result.rotation_fraction == 0.85619056224823


def test_preexisting_inertia_shift_consumes_anchor_shift_even_with_zero_new_fractions():
    result = run(state(anchor_shift_vector=(2, 0, 0)), t=team(flag=0x402))
    assert result.component_shift_vector == (2, 0, 0)
    assert result.step_state.now_world_position == (4, 3, 4)
    assert result.translation_fraction == result.rotation_fraction == 0


def test_shift_position_rotates_around_old_component_pivot_then_adds_shift():
    q = (0, 0, math.sqrt(0.5), math.sqrt(0.5))
    result = shift_world_position((12, 20, 0), (10, 20, 0), (3, 0, 0), q)
    assert result == pytest.approx((13, 22, 0), abs=2e-7)


def test_shift_position_retains_shift_plus_rotated_delta_before_pivot_addition():
    # Reassociating to oldPos+shift would produce 1; source grouping yields 0.
    assert shift_world_position((1, 0, 0), (1e16, 0, 0), Z, Q) == Z


def test_world_rotation_left_multiplies_anchor_then_component_delta():
    z90 = (0, 0, math.sqrt(0.5), math.sqrt(0.5))
    x180 = (1, 0, 0, 0)
    result = run(
        state(component_world_rotation=z90, anchor_shift_rotation=x180),
        cfg=settings(world_inertia=0),
    )
    # x180*z90 = (sqrt(.5), -sqrt(.5), 0, 0); swapping order flips Y.
    assert result.component_shift_rotation == pytest.approx(
        (math.sqrt(0.5), -math.sqrt(0.5), 0, 0), abs=2e-7
    )
    assert result.step_state.old_frame_world_rotation == result.component_shift_rotation


def test_resolved_pivot_is_neither_current_nor_working_component_position():
    half = math.sqrt(0.5)
    step = replace(
        state().step_state,
        old_frame_world_position=(12, 20, 0),
        now_world_position=(10, 23, 0),
    )
    result = run(
        state(
            component_world_position=(5, 0, 0),
            working_old_component_position=(1, 0, 0),
            old_component_world_position=(10, 20, 0),
            component_world_rotation=(0, 0, half, half),
            step_state=step,
        ),
        cfg=settings(world_inertia=0),
    )
    assert result.step_state.old_frame_world_position == pytest.approx(
        (14, 22, 0), abs=8e-7
    )
    assert result.step_state.now_world_position == pytest.approx((11, 20, 0), abs=8e-7)


def test_noncommuting_work_rotation_and_distinct_history_rotations():
    half = math.sqrt(0.5)
    z90, x180, y180 = (0, 0, half, half), (1, 0, 0, 0), (0, 1, 0, 0)
    step = replace(
        state().step_state, old_frame_world_rotation=z90, now_world_rotation=y180
    )
    result = run(
        state(
            component_world_rotation=z90,
            working_old_component_rotation=x180,
            step_state=step,
        ),
        cfg=settings(world_inertia=0),
    )
    # initial = z90*inverse(x180), then left-multiply each distinct history rotation.
    assert result.component_shift_rotation == pytest.approx(
        (-half, -half, 0, 0), abs=2e-7
    )
    assert result.step_state.old_frame_world_rotation == pytest.approx(
        (-1, 0, 0, 0), abs=2e-7
    )
    assert result.step_state.now_world_rotation == pytest.approx(
        (0, 0, -half, half), abs=2e-7
    )


def test_only_old_frame_and_now_world_history_change_in_step_state():
    s = state()
    result = run(s, cfg=settings(world_inertia=0.5))
    assert result.step_state.frame_world_position == s.step_state.frame_world_position
    assert result.step_state.frame_world_rotation == s.step_state.frame_world_rotation
    assert result.step_state.old_frame_world_scale == S
    assert result.step_state.frame_world_scale == S
    assert s.step_state.old_frame_world_position == (1, 2, 3)


def test_reset_fragment_clears_shift_and_smoothing_with_resolved_reset_prelude():
    s = state(working_old_component_position=(4, 0, 0))
    result = run(s, t=team(flag=6), cfg=settings(world_inertia=math.nan))
    assert result.component_shift_vector == result.smoothing_velocity == Z
    assert result.component_shift_rotation == Q
    assert result.motion.speed == 0
    assert result.step_state is s.step_state
    assert result.flag == 6


def test_frame_correction_feeds_moving_wind_with_corrected_residual():
    result = run(cfg=settings(world_inertia=0.5))
    wind = advance_wind_state(
        TeamWindState((), WindInfo(7, 0, 0, Z)),
        WindStepSettings(influence=1, frequency=0, moving_wind=3),
        frame=FrameWindState.from_motion(result.motion),
        scale_ratio=2,
        delta_time=1,
    )
    assert wind.state.moving.main == 3
    assert wind.state.moving.direction == (-1, 0, 0)


def test_resolved_frame_to_center_to_start_end_two_substep_feedback():
    # Synthetic adapters only: no constraint iteration, full tail or native publication.
    frame = run(
        state(step_state=CenterStepState(Z, Q, (4, 0, 0), Q, S, S, Z, Q)),
        team(update_count=2, simulation_delta_time=0.25),
    )
    assert frame.compensation_fraction == 0.5
    assert frame.motion.speed == 2
    assert frame.step_state.old_frame_world_position == (2, 0, 0)
    assert frame.step_state.now_world_position == (2, 0, 0)
    history = frame.step_state
    clock = CenterStepTeam(frame.flag, 2, 1, 0, 0, 0)
    particle = ParticleStartState((1, 0, 0), Z, Q, Z, Q, Z, 0)
    start_cfg = StartStepSettings(
        0, 1, 0.25, (0,) * 16, 1, 1, 1, 4, (0, -1, 0), 1, Z, 0
    )
    for index in range(2):
        step = advance_center_step(
            history,
            clock,
            LocalInertiaSettings(0.5, -1, -1),
            team_id=1,
            update_index=index,
            delta_time=0.25,
        )
        center = step.center
        assert center is not None
        assert center.step_vector == (0.5, 0, 0)
        assert center.now_world_position == (2.5 + 0.5 * index, 0, 0)
        begin = start_particle_step(
            particle,
            replace(start_cfg, frame_interpolation=step.team.frame_interpolation),
            attribute=2,
            center=center.for_start(),
            wind=Z,
        )
        end = finish_particle_step(
            ParticleEndState(
                begin.next_position,
                particle.old_position,
                begin.velocity_position,
                particle.velocity,
                0,
                0,
                Z,
                0,
            ),
            EndStepSettings(0.25, 1, 1, -1, 0, 0, 0),
            attribute=2,
            center=center.for_end(),
        )
        particle = replace(
            particle, old_position=end.old_position, velocity=end.velocity
        )
        history, clock = step.next_state, step.team
    assert particle.old_position == (2, -0.75, 0)
    assert particle.velocity == (0, -2, 0)
    assert end.real_velocity == (2, -2, 0)
    assert center.old_world_position == (2.5, 0, 0)
    assert center.now_world_position == (3, 0, 0)


def test_double_position_is_preserved_until_final_residual_narrowing():
    n = 2**40
    result = run(
        state(
            component_world_position=(n + 0.5, 0, 0),
            working_old_component_position=(n, 0, 0),
        ),
        cfg=settings(world_inertia=0.5),
    )
    assert result.corrected_old_component_position == (n + 0.25, 0, 0)
    assert result.motion.delta_single == (0.25, 0, 0)


@pytest.mark.parametrize(
    "changes",
    [
        {"world_inertia": -1},
        {"world_inertia": 2},
        {"scale_length_ratio": -1},
        {"rotation_speed_limit": math.inf},
    ],
)
def test_adapter_rejects_settings_outside_supported_finite_domain(changes):
    with pytest.raises(ValueError):
        run(cfg=settings(**changes))


@pytest.mark.parametrize(
    "changes",
    [
        {"flag": -1},
        {"update_count": -1},
        {"velocity_weight": 2},
        {"now_time_scale": -1},
    ],
)
def test_adapter_rejects_invalid_team_domain(changes):
    with pytest.raises(ValueError):
        run(t=team(**changes))


def test_frame_scale_length_ratio_narrows_input_lanes_before_dot():
    assert frame_scale_length_ratio((16777217, 0, 0), S) == _single(
        16777216 / _single(math.sqrt(3))
    )
