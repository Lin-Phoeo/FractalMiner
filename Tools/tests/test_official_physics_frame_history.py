"""Synthetic lifecycle/continuation tests, not native or Unity acceptance."""

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
from official_physics_frame_anchor import AnchorState, advance_frame_anchor
from official_physics_frame_history import (
    FrameHistoryState,
    FramePostTeam,
    finish_frame_history,
    initialize_frame_weights,
    prepare_frame_history,
)
from official_physics_frame_inertia import (
    FrameInertiaSettings,
    FrameInertiaState,
    FrameInertiaTeam,
    advance_frame_inertia,
)
from official_physics_frame_prelude import FramePreludeSettings
from official_physics_scale_remap import (
    ComponentScaleCache,
    prepare_component_scale_remap,
)
from official_physics_team_tail import TeamDynamicsState

Z, S, Q = (0.0, 0.0, 0.0), (1.0, 1.0, 1.0), (0.0, 0.0, 0.0, 1.0)
C_Q, F_Q = (0.0, 0.0, 1.0, 0.0), (1.0, 0.0, 0.0, 0.0)


def history():
    return FrameHistoryState(
        FrameInertiaState(
            (10, 2, 3),
            C_Q,
            (1, 2, 3),
            Q,
            (1, 2, 3),
            Z,
            Q,
            Z,
            CenterStepState(Z, Q, (8, 0, 0), F_Q, S, (3, 4, 5), (2, 0, 0), Q),
            (1, 0, 0),
        ),
        ComponentScaleCache(Q, (7, 8, 9), S),
        AnchorState((2, 0, 0), Q, (-3, 0, 0), Q, (99, 98, 97)),
        (-20, -30, -40),
        Q,
    )


def pre_team(flag=0x22):
    return FrameInertiaTeam(flag, 1, 1, 0, 1, 0.25)


def settings(**kw):
    return replace(FramePreludeSettings(0, -1, 1, 0, 100, 180), **kw)


def post_team(**kw):
    return replace(FramePostTeam(0x22, 60, 59, 58, 57, 56, 55, 3, (1, 2, 3), 7), **kw)


def test_ordinary_prelude_keeps_missing_histories_and_component_cache():
    original = history()
    result = prepare_frame_history(
        original, pre_team(), settings(), component_world_scale=(2, 3, 4)
    )
    assert result.history.component_cache is original.component_cache
    assert result.history.old_world_position == original.old_world_position
    assert result.history.old_world_rotation == original.old_world_rotation
    assert result.history.anchor is original.anchor
    assert result.history.inertia.step_state.old_frame_world_position == Z
    assert not result.prelude.history_reinitialized


@pytest.mark.parametrize("flag", [4, 0x40000, 0x40004])
def test_reset_copies_distinct_component_and_target_sources(flag):
    original = history()
    result = prepare_frame_history(
        original, pre_team(flag | 2), settings(), component_world_scale=(2, 3, 4)
    )
    h = result.history
    step = h.inertia.step_state
    assert h.old_world_position == (8, 0, 0) and h.old_world_rotation == F_Q
    assert step.old_frame_world_position == step.now_world_position == (8, 0, 0)
    assert step.old_frame_world_rotation == step.now_world_rotation == F_Q
    assert step.old_frame_world_scale == (3, 4, 5)
    if flag & 4:
        assert h.component_cache.old_component_rotation == C_Q
        assert h.component_cache.old_component_scale == (2, 3, 4)
        assert h.inertia.old_component_world_position == (10, 2, 3)
    else:
        assert h.component_cache is original.component_cache
        assert h.inertia.old_component_world_position == (1, 2, 3)
    assert h.anchor is original.anchor  # Do not rerun the preceding anchor region.
    assert h.component_cache.negative_scale_direction == S
    assert original.old_world_position == (-20, -30, -40)


def test_new_teleport_reset_completes_cache_without_retroactive_anchor_init():
    original = history()
    anchored = advance_frame_anchor(original.inertia, pre_team(), original.anchor, 1)
    result = prepare_frame_history(
        replace(original, inertia=anchored.state, anchor=anchored.anchor),
        anchored.team,
        settings(teleport_mode=1, teleport_distance=1),
        component_world_scale=S,
    )
    assert not anchored.anchor_reinitialized and result.prelude.teleport_triggered
    assert result.history.component_cache.old_component_rotation == C_Q
    assert result.history.anchor.old_anchor_position == (-3, 0, 0)
    assert result.history.anchor.anchor_component_local_position == (99, 98, 97)


def test_entry_reset_anchor_is_initialized_only_by_prior_anchor_stage():
    original = history()
    anchored = advance_frame_anchor(original.inertia, pre_team(6), original.anchor, 1)
    result = prepare_frame_history(
        replace(original, inertia=anchored.state, anchor=anchored.anchor),
        anchored.team,
        settings(),
        component_world_scale=S,
    )
    assert anchored.anchor_reinitialized
    assert result.history.anchor.old_anchor_position == (2, 0, 0)
    assert result.history.anchor.anchor_component_local_position == (8, 2, 3)


def test_reset_smoothing_is_computed_before_inertia_clears_it():
    prepared = prepare_frame_history(
        history(),
        pre_team(0x26),
        settings(movement_inertia_smoothing=0.5),
        component_world_scale=S,
    )
    assert prepared.history.inertia.smoothing_velocity != Z
    corrected = advance_frame_inertia(
        prepared.history.inertia,
        prepared.prelude.team,
        FrameInertiaSettings(1, -1, -1, 1),
    )
    assert corrected.smoothing_velocity == Z and corrected.component_shift_vector == Z
    assert corrected.motion.speed == 0


def test_sign_change_does_not_read_component_scale_in_missing_reset_completion():
    result = prepare_frame_history(
        history(), pre_team(0x40022), settings(), component_world_scale=(math.nan, 1, 1)
    )
    assert result.history.old_world_position == (8, 0, 0)
    assert result.history.component_cache.old_component_scale == (7, 8, 9)


@pytest.mark.parametrize("flag", [0, 2, 0x10000, 0x200])
def test_unselected_component_scale_is_not_read(flag):
    original = history()
    result = prepare_frame_history(
        original, pre_team(flag), settings(), component_world_scale=(math.nan, 1, 1)
    )
    assert result.history.component_cache is original.component_cache


def test_nonunit_component_quaternion_is_copied_without_normalization():
    original = history()
    original = replace(
        original,
        inertia=replace(original.inertia, component_world_rotation=(0, 0, 0, 2)),
    )
    result = prepare_frame_history(
        original, pre_team(6), settings(), component_world_scale=S
    )
    assert result.history.component_cache.old_component_rotation == (0, 0, 0, 2)


@pytest.mark.parametrize("flag", [0, 1, 0x12, 0x802, 0x80002, (1 << 61) | 2])
def test_post_process_gate_leaves_whole_state_and_unselected_inputs_untouched(flag):
    original, team = history(), post_team(flag=flag, time=math.nan)
    result = finish_frame_history(
        original, team, component_world_scale=(math.nan, 1, 1)
    )
    assert result.history is original and result.team is team
    assert (
        result.writes == ()
        and not result.frame_history_advanced
        and not result.time_wrapped
    )


@pytest.mark.parametrize(
    "flag,advance", [(2, False), (0x22, True), (0xA2, True), (0x82, False)]
)
def test_old_frame_and_force_reset_use_update_flag_not_step_flag_or_count(
    flag, advance
):
    original, team = history(), post_team(flag=flag)
    result = finish_frame_history(original, team, component_world_scale=(2, 3, 4))
    h = result.history
    assert result.frame_history_advanced is advance
    assert h.inertia.old_component_world_position == (10, 2, 3)
    assert h.component_cache.old_component_rotation == C_Q
    assert h.component_cache.old_component_scale == (2, 3, 4)
    assert h.inertia.working_old_component_position == (1, 2, 3)
    assert h.inertia.working_old_component_rotation == Q
    assert h.inertia.step_state.old_frame_world_position == (
        (8, 0, 0) if advance else Z
    )
    assert result.team.force_mode == (0 if advance else 3)
    assert result.team.impact_force == (Z if advance else (1, 2, 3))
    assert result.team.skip_count == (0 if advance else 7)
    assert h.inertia.step_state.now_world_position == (2, 0, 0)
    assert h.inertia.step_state.now_world_rotation == Q
    assert h.old_world_position == (-20, -30, -40)
    assert h.old_world_rotation == Q


def test_post_unconditionally_updates_anchor_history_and_rebuilds_local_with_unit_scale():
    original = history()
    result = finish_frame_history(
        original, post_team(flag=2), component_world_scale=(100, 200, 300)
    )
    assert result.history.anchor.old_anchor_position == (2, 0, 0)
    assert result.history.anchor.old_anchor_rotation == Q
    assert result.history.anchor.anchor_component_local_position == (8, 2, 3)


def test_anchor_local_uses_full_matrix_inverse_not_quaternion_inverse_or_transpose():
    original = history()
    original = replace(
        original, anchor=replace(original.anchor, anchor_rotation=(0, 0, 0.5, 1))
    )
    result = finish_frame_history(original, post_team(flag=2), component_world_scale=S)
    # TRS matrix XY=[[.5,-1],[1,.5]], full inverse on component-anchor=(8,2,3).
    assert result.history.anchor.anchor_component_local_position == pytest.approx(
        (4.8, -5.6, 3), abs=5e-7
    )
    assert result.history.anchor.old_anchor_rotation == (0, 0, 0.5, 1)


def test_large_world_anchor_difference_is_double_before_single_narrowing():
    original = history()
    big = 2**40
    original = replace(
        original,
        inertia=replace(original.inertia, component_world_position=(big + 0.25, 2, 3)),
        anchor=replace(original.anchor, anchor_position=(big, 0, 0)),
    )
    result = finish_frame_history(original, post_team(flag=2), component_world_scale=S)
    assert result.history.anchor.anchor_component_local_position == (0.25, 2, 3)
    assert result.history.inertia.old_component_world_position[0] == big + 0.25


def test_post_clears_only_original_transient_mask_retaining_anchor_and_negative_bits():
    flag = 2 | 0x406AC | 0x10000 | 0x20000 | 0x8000 | (1 << 63)
    result = finish_frame_history(
        history(), post_team(flag=flag), component_world_scale=S
    )
    assert result.team.flag == 2 | 0x10000 | 0x20000 | 0x8000 | (1 << 63)


@pytest.mark.parametrize(
    "time,wrapped",
    [
        (7200, False),
        (7200.0001, False),
        (7200.0005, True),
        (10801, True),
        (-8000, False),
    ],
)
def test_clock_wrap_strict_single_threshold_and_one_subtraction(time, wrapped):
    team = post_team(
        time=time,
        old_time=1,
        now_update_time=2,
        old_update_time=3,
        frame_update_time=4,
        frame_old_time=5,
    )
    result = finish_frame_history(history(), team, component_world_scale=S)
    assert result.time_wrapped is wrapped
    if wrapped:
        assert result.team.time == _single(_single(time) - 3600)
        assert (
            result.team.old_time,
            result.team.now_update_time,
            result.team.old_update_time,
            result.team.frame_update_time,
            result.team.frame_old_time,
        ) == (-3599, -3598, -3597, -3596, -3595)
    else:
        assert result.team.time == time and result.team.frame_old_time == 5


def test_no_wrap_does_not_consume_unselected_sibling_clocks():
    team = post_team(old_time=math.nan, now_update_time=math.nan)
    result = finish_frame_history(history(), team, component_world_scale=S)
    assert math.isnan(result.team.old_time)


@pytest.mark.parametrize("flag", [4, 8, 12])
@pytest.mark.parametrize("time,expected", [(0, 1), (1e-6, 1), (1.1e-6, 0), (-1, 1)])
def test_frame_weight_initialization_uses_reset_or_time_reset_and_strict_epsilon(
    flag, time, expected
):
    original = TeamDynamicsState(S, S, 0.3, 0.4, 2, 0.5, 0.6, 0.7)
    result = initialize_frame_weights(original, flag, time)
    assert result.velocity_weight == result.blend_weight == expected
    assert (
        result.distance_weight == original.distance_weight and result.scale_ratio == 2
    )


@pytest.mark.parametrize("flag", [0, 2, 0x40000])
def test_unselected_weight_branch_preserves_state_without_reading_setting(flag):
    original = TeamDynamicsState(S, S, 0.3, 0.4, 2, 0.5, 0.6, 0.7)
    assert initialize_frame_weights(original, flag, math.nan) is original


def test_two_substeps_consume_old_frame_until_post_then_next_frame_continues():
    original = history()
    original = replace(
        original,
        inertia=replace(
            original.inertia, step_state=CenterStepState(Z, Q, (8, 0, 0), Q, S, S, Z, Q)
        ),
    )
    prepared = prepare_frame_history(
        original, pre_team(), settings(), component_world_scale=S
    ).history
    team = CenterStepTeam(0x22, 2, 1, 0, 0, 0)
    cfg = LocalInertiaSettings(1, -1, -1)
    first = advance_center_step(
        prepared.inertia.step_state,
        team,
        cfg,
        team_id=1,
        update_index=0,
        delta_time=0.5,
    )
    second = advance_center_step(
        first.next_state, first.team, cfg, team_id=1, update_index=1, delta_time=0.5
    )
    assert first.center is not None and second.center is not None
    assert first.center.step_vector == second.center.step_vector == (4, 0, 0)
    assert first.center.now_world_position == (
        4,
        0,
        0,
    ) and second.center.now_world_position == (8, 0, 0)
    completed = finish_frame_history(
        replace(
            prepared, inertia=replace(prepared.inertia, step_state=second.next_state)
        ),
        post_team(flag=second.team.flag),
        component_world_scale=S,
    )
    next_state = replace(
        completed.history.inertia.step_state, frame_world_position=(16, 0, 0)
    )
    next_step = advance_center_step(
        next_state,
        CenterStepTeam(completed.team.flag, 2, 2, 1, 1, 0),
        cfg,
        team_id=1,
        update_index=0,
        delta_time=0.5,
    )
    assert next_step.center is not None
    assert next_step.center.step_vector == (
        4,
        0,
        0,
    ) and next_step.center.now_world_position == (12, 0, 0)


def test_reset_two_steps_zero_then_normal_next_frame():
    original = history()
    original = replace(
        original,
        inertia=replace(
            original.inertia,
            step_state=replace(original.inertia.step_state, frame_world_rotation=Q),
        ),
    )
    prepared = prepare_frame_history(
        original, pre_team(0x26), settings(), component_world_scale=S
    )
    cfg = LocalInertiaSettings(1, -1, -1)
    a = advance_center_step(
        prepared.history.inertia.step_state,
        CenterStepTeam(0x26, 2, 1, 0, 0, 0),
        cfg,
        team_id=1,
        update_index=0,
        delta_time=0.5,
    )
    b = advance_center_step(
        a.next_state, a.team, cfg, team_id=1, update_index=1, delta_time=0.5
    )
    assert a.center is not None and b.center is not None
    assert a.center.step_vector == b.center.step_vector == Z and b.team.flag & 4
    tail = finish_frame_history(
        replace(
            prepared.history,
            inertia=replace(prepared.history.inertia, step_state=b.next_state),
        ),
        post_team(flag=b.team.flag),
        component_world_scale=S,
    )
    assert not tail.team.flag & 4
    next_state = replace(
        tail.history.inertia.step_state, frame_world_position=(12, 0, 0)
    )
    next_step = advance_center_step(
        next_state,
        CenterStepTeam(tail.team.flag, 1, 2, 1, 1, 0),
        cfg,
        team_id=1,
        update_index=0,
        delta_time=1,
    )
    assert next_step.center is not None
    assert next_step.center.step_vector == (4, 0, 0)


def test_post_component_cache_feeds_next_scale_stage_without_reusing_corrected_work():
    original = history()
    tail = finish_frame_history(original, post_team(), component_world_scale=(2, 3, 4))
    next_inertia = replace(
        tail.history.inertia,
        component_world_position=(14, 2, 3),
        component_world_rotation=Q,
    )
    next_scale = prepare_component_scale_remap(
        next_inertia,
        pre_team(tail.team.flag),
        tail.history.anchor,
        (2, 3, 4),
        tail.history.component_cache,
    )
    assert next_scale.state.working_old_component_position == (10, 2, 3)
    assert next_scale.state.working_old_component_rotation == C_Q
    assert not next_scale.sign_changed


@pytest.mark.parametrize("flag", [-1, True, 2**64])
def test_adapter_rejects_invalid_flag(flag):
    with pytest.raises(ValueError):
        finish_frame_history(history(), post_team(flag=flag), component_world_scale=S)


@pytest.mark.parametrize(
    "kw", [{"time": math.nan}, {"time": 7201, "old_time": math.inf}]
)
def test_adapter_rejects_consumed_nonfinite_clock(kw):
    with pytest.raises(ValueError):
        finish_frame_history(history(), post_team(**kw), component_world_scale=S)


def test_adapter_rejects_selected_reset_scale_and_nonfinite_anchor():
    with pytest.raises(ValueError):
        prepare_frame_history(
            history(), pre_team(6), settings(), component_world_scale=(math.nan, 1, 1)
        )
    original = history()
    original = replace(
        original, anchor=replace(original.anchor, anchor_rotation=(math.nan, 0, 0, 1))
    )
    with pytest.raises(ValueError):
        finish_frame_history(original, post_team(), component_world_scale=S)


def test_stationary_second_anchor_does_not_reapply_first_frame_rotation():
    original = history()
    q = (0, 0, _single(math.sqrt(0.5)), _single(math.sqrt(0.5)))
    original = replace(
        original,
        inertia=replace(
            original.inertia,
            component_world_position=(3, 0, 0),
            old_component_world_position=(3, 0, 0),
        ),
        anchor=AnchorState((1, 0, 0), q, Z, Q, (2, 0, 0)),
    )
    first = advance_frame_anchor(
        replace(original.inertia, working_old_component_position=(3, 0, 0)),
        pre_team(0x8022),
        original.anchor,
        0,
    )
    assert first.state.anchor_shift_rotation != Q
    post = finish_frame_history(
        replace(original, inertia=first.state, anchor=first.anchor),
        post_team(flag=first.team.flag),
        component_world_scale=S,
    )
    next_scale = prepare_component_scale_remap(
        post.history.inertia,
        pre_team(post.team.flag),
        post.history.anchor,
        S,
        post.history.component_cache,
    )
    second = advance_frame_anchor(
        next_scale.state,
        next_scale.team,
        next_scale.anchor,
        0,
    )
    assert second.state.anchor_shift_vector == pytest.approx(Z, abs=3e-7)
    assert second.state.anchor_shift_rotation == pytest.approx(Q, abs=1e-7)


def test_reset_and_post_differ_on_component_scale_and_frame_scale_without_aliasing():
    original = history()
    result = prepare_frame_history(
        original, pre_team(0x40022), settings(), component_world_scale=(2, 3, 4)
    )
    assert result.history.component_cache.old_component_scale == (7, 8, 9)
    tail = finish_frame_history(
        result.history,
        post_team(flag=result.prelude.team.flag),
        component_world_scale=(2, 3, 4),
    )
    assert tail.history.component_cache.old_component_scale == (2, 3, 4)
    assert tail.history.inertia.step_state.old_frame_world_scale == (3, 4, 5)


def test_selected_weight_setting_rejects_nonfinite_adapter_input():
    with pytest.raises(ValueError):
        initialize_frame_weights(TeamDynamicsState(S, S, 0, 0, 1, 1, 1, 0), 4, math.nan)


def test_singular_anchor_full_inverse_is_rejected_as_adapter_policy():
    original = history()
    original = replace(
        original, anchor=replace(original.anchor, anchor_rotation=(0.5, 0.5, 0, 0))
    )
    with pytest.raises(ValueError, match="nonsingular"):
        finish_frame_history(original, post_team(), component_world_scale=S)


def test_time_reset_weights_are_initialized_after_old_weight_inertia_consumption():
    original = history()
    team = replace(pre_team(0xA), velocity_weight=0.25)
    prepared = prepare_frame_history(
        original, team, settings(), component_world_scale=S
    )
    corrected = advance_frame_inertia(
        prepared.history.inertia,
        prepared.prelude.team,
        FrameInertiaSettings(1, -1, -1, 1),
    )
    assert corrected.compensation_fraction == 0.75
    dynamics = TeamDynamicsState(S, S, team.velocity_weight, 1, 1, 1, 1, 0.1)
    initialized = initialize_frame_weights(dynamics, corrected.flag, 0)
    assert initialized.velocity_weight == initialized.blend_weight == 1
    assert team.velocity_weight == 0.25  # Earlier snapshot must not be replaced.
