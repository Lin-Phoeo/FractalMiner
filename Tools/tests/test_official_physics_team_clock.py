"""Finite source clock + existing center/list integration, not Unity execution."""

import sys
from dataclasses import replace
from pathlib import Path
from typing import Any

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from official_physics_center_step import (
    CenterStepState,
    CenterStepTeam,
    LocalInertiaSettings,
    advance_center_step,
)
from official_physics_constraints import _single
from official_physics_team_clock import (
    TeamClockState,
    TeamFrameTimes,
    advance_team_frame_clock,
)
from official_physics_work_lists import StepTeam, build_step_work_lists


def state(**updates: Any) -> TeamClockState:
    return replace(
        TeamClockState(2, 0, 0, 0, 0, 0, 0, 0, 0, 1, 77, 88, False, 0.25, 1),
        **updates,
    )


def times(**updates: Any) -> TeamFrameTimes:
    return replace(TeamFrameTimes(0.5, 0.25, 0.75, 0.5, 0.25, 3), **updates)


def run(team=None, cfg=None, mode=0, team_id=1):
    return advance_team_frame_clock(
        team or state(), cfg or times(), team_id=team_id, resolved_update_mode=mode
    )


@pytest.mark.parametrize(
    "mode,delta,scale,count,time",
    [(0, 0.5, 0.5, 1, 0.25), (1, 0.25, 0.5, 0, 0.125), (2, 0.75, 1, 3, 0.75)],
)
def test_mode_selects_clock_unscaled_bypasses_global_scale(
    mode, delta, scale, count, time
):
    result = run(mode=mode)
    assert result.processed
    assert result.team.update_mode == mode
    assert result.team.frame_delta_time == delta
    assert result.team.now_time_scale == scale
    assert result.team.time == time
    assert result.team.old_time == 0
    assert result.team.update_count == count
    assert result.team.flag & 0x20 == (0x20 if count else 0)


def test_substep_cap_discards_excess_time_and_publishes_window():
    original = state(time=1, now_update_time=0.125, frame_update_time=0.75)
    result = run(original, times(delta_time=2, global_time_scale=1, max_steps=2))
    assert result.raw_update_count == 11
    assert result.team.update_count == 2
    assert result.team.skip_count == 9
    assert result.team.time == 0.75
    assert result.team.now_update_time == 0.125
    assert result.team.old_update_time == 0.125
    assert result.team.frame_old_time == 0.75
    assert result.team.frame_update_time == 0.75
    assert result.team.old_time == 1  # Before excess-time discard.
    assert original == state(time=1, now_update_time=0.125, frame_update_time=0.75)


def test_zero_step_retains_frame_window_even_though_time_and_fade_advance():
    original = state(frame_update_time=8, frame_old_time=7, old_update_time=6)
    result = run(original, times(delta_time=0.1))
    assert result.team.update_count == result.team.skip_count == 0
    assert result.team.old_update_time == 6
    assert result.team.frame_update_time == 8
    assert result.team.frame_old_time == 7
    assert result.team.time == _single(_single(0.1) * 0.5)
    assert result.team.cloth_lod_fade_weight == _single(
        0.25 + _single(_single(0.1) * 0.5)
    )


def test_flag8_zeros_only_five_clock_fields_before_new_time():
    result = run(
        state(
            flag=2 | 8,
            time=9,
            now_update_time=8,
            old_update_time=7,
            frame_update_time=6,
            frame_old_time=5,
            old_time=4,
        ),
        times(delta_time=0),
    )
    assert result.team.time == result.team.now_update_time == 0
    assert (
        result.team.old_update_time
        == result.team.frame_update_time
        == result.team.frame_old_time
        == 0
    )
    assert result.team.old_time == 0
    assert result.team.flag == 10


def test_flag4_does_not_reset_team_clocks_like_flag8():
    result = run(state(flag=6, time=1, now_update_time=1), times(delta_time=0))
    assert result.team.time == 1
    assert result.team.now_update_time == 1


def test_animation_pose_request_sets_particle_reset_but_no_steps():
    result = run(state(time=1, reset_simulation_to_animation_pose=True))
    assert result.raw_update_count == 5
    assert result.team.time == result.team.now_update_time == 1.25
    assert result.team.update_count == result.team.skip_count == 0
    assert result.team.flag == 6
    assert result.team.frame_update_time == result.team.frame_old_time == 0


def test_zero_scale_with_backlog_rebases_now_with_exact_source_epsilon():
    result = run(state(time=1), times(global_time_scale=0))
    assert result.team.time == 0.75  # Excess discard happens BEFORE paused branch.
    assert result.team.update_count == result.team.skip_count == 0
    assert result.team.now_update_time == _single(_single(0.75 - 0.25) + _single(1e-4))
    assert result.team.cloth_lod_fade_weight == 0.25


def test_zero_scale_without_backlog_keeps_now_time():
    result = run(state(now_update_time=0.125), times(global_time_scale=0))
    assert result.team.now_update_time == 0.125
    assert result.team.update_count == 0  # Native truncate toward zero, not floor(-.5).


def test_negative_quotient_is_not_invented_clamped_to_zero():
    result = run(state(now_update_time=1), times(delta_time=0))
    assert result.raw_update_count == result.team.update_count == -4
    assert result.team.skip_count == 0
    assert not result.team.flag & 0x20


@pytest.mark.parametrize("flag", [0, 2 | (1 << 61), 2 | 0x10, 2 | 0x800, 2 | 0x80000])
def test_ineligible_clock_fragment_keeps_values_without_reading_unused_inputs(flag):
    original = state(flag=flag, time=7)
    result = run(original, times(delta_time=float("nan")), mode=-1)
    assert not result.processed
    assert result.team is original
    assert result.raw_update_count is None
    assert result.writes == ()


def test_team0_skips_before_flag_or_clock_reads():
    original = state(flag=-1)
    result = run(original, times(delta_time=float("nan")), mode=-1, team_id=0)
    assert result.team is original


@pytest.mark.parametrize("mode", [0, 1, 2])
def test_unselected_frame_deltas_are_not_read(mode):
    delta = [float("nan")] * 3
    delta[mode] = 0.25
    assert run(
        cfg=times(
            delta_time=delta[0], fixed_delta_time=delta[1], unscaled_delta_time=delta[2]
        ),
        mode=mode,
    ).processed


def test_unscaled_does_not_read_unused_global_scale():
    assert run(cfg=times(global_time_scale=float("nan")), mode=2).processed


def test_zero_fade_time_does_not_read_previous_weight():
    assert (
        run(
            state(cloth_lod_fade_time=0, cloth_lod_fade_weight=float("nan"))
        ).team.cloth_lod_fade_weight
        == 1
    )


def test_flag8_does_not_read_old_clock_values():
    result = run(
        state(
            flag=10,
            time=float("nan"),
            now_update_time=float("nan"),
            old_update_time=float("nan"),
            frame_update_time=float("nan"),
            frame_old_time=float("nan"),
        )
    )
    assert result.team.time == 0.25


@pytest.mark.parametrize(
    "fading,fade_time,expected",
    [(False, 0, 1), (True, 0, 0), (False, 1, 0.5), (True, 1, 0)],
)
def test_cloth_fade_direction_and_zero_time_branch(fading, fade_time, expected):
    result = run(
        state(flag=2 | ((1 << 60) if fading else 0), cloth_lod_fade_time=fade_time)
    )
    assert result.team.cloth_lod_fade_weight == expected


@pytest.mark.parametrize("weight,fading,expected", [(0.9, False, 1), (0.1, True, 0)])
def test_cloth_fade_clamp(weight, fading, expected):
    assert (
        run(
            state(flag=2 | ((1 << 60) if fading else 0), cloth_lod_fade_weight=weight)
        ).team.cloth_lod_fade_weight
        == expected
    )


@pytest.mark.parametrize("mode", [-1, 3, True, 0.0])
def test_unresolved_modes_refused_not_defaulted(mode):
    with pytest.raises(ValueError):
        run(mode=mode)


@pytest.mark.parametrize(
    "field,value",
    [
        ("simulation_delta_time", 0),
        ("simulation_delta_time", -1),
        ("delta_time", float("nan")),
        ("global_time_scale", -1),
        ("max_steps", 0),
        ("max_steps", True),
    ],
)
def test_invalid_selected_times_rejected(field, value):
    with pytest.raises(ValueError):
        run(cfg=times(**{field: value}))


@pytest.mark.parametrize(
    "field,value",
    [
        ("time_scale", -1),
        ("time", float("nan")),
        ("flag", -1),
        ("reset_simulation_to_animation_pose", 1),
        ("cloth_lod_fade_weight", float("nan")),
    ],
)
def test_invalid_state_rejected(field, value):
    with pytest.raises(ValueError):
        run(state(**{field: value}))


@pytest.mark.parametrize("team_id", [-1, True, 2**31])
def test_invalid_team_id(team_id):
    with pytest.raises(ValueError):
        run(team_id=team_id)


def test_int32_truncate_overflow_rejected_not_native_fault_emulation():
    with pytest.raises(ValueError):
        run(state(time=1e20))


def test_clock_drives_center_step_and_whole_chunk_worklists_across_two_frames():
    clock = state()
    q, zero, one = (0.0, 0.0, 0.0, 1.0), (0.0, 0.0, 0.0), (1.0, 1.0, 1.0)
    center = CenterStepState(zero, q, (2, 0, 0), q, one, one, zero, q)
    cfg = times(delta_time=0.5, global_time_scale=1)
    for frame in range(2):
        clock = run(clock, cfg).team
        subteam = CenterStepTeam(
            clock.flag,
            clock.update_count,
            clock.time,
            clock.frame_old_time,
            clock.now_update_time,
            0,
        )
        for index in range(clock.update_count + 1):
            step = advance_center_step(
                center,
                subteam,
                LocalInertiaSettings(0, -1, -1),
                team_id=7,
                update_index=index,
                delta_time=cfg.simulation_delta_time,
            )
            center, subteam = step.next_state, step.team
            work = build_step_work_lists(
                {7: StepTeam(subteam.flag, 500, 2, 100, 1)},
                particle_team_order=(7,),
                baseline_team_order=(7,),
                particle_output_capacity=2,
                baseline_output_capacity=1,
            )
            assert bool(work.particle_indices) == (index < clock.update_count)
            if work.particle_indices:
                assert work.particle_indices == (500, 501)
                assert work.baseline_indices == ((7 << 16) | 100,)
        assert subteam.now_update_time == (frame + 1) * 0.5
        # Explicit fragment merge; not an automatic native Team publication.
        clock = replace(
            clock, flag=subteam.flag, now_update_time=subteam.now_update_time
        )
    assert clock.old_time == 0.5
    assert clock.frame_old_time == 0.5
    assert clock.frame_update_time == 1
