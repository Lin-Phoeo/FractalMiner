"""Synthetic anchor-resolved inputs, not a full native frame-center oracle."""

import math
import sys
from dataclasses import replace
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from official_physics_center_step import CenterStepState
from official_physics_constraints import _single
from official_physics_frame_inertia import (
    FrameInertiaSettings,
    FrameInertiaState,
    FrameInertiaTeam,
    advance_frame_inertia,
)
from official_physics_frame_prelude import (
    FramePreludeSettings,
    prepare_frame_inertia,
    smoothing_gain,
)

Q, Z, S = (0.0, 0.0, 0.0, 1.0), (0.0, 0.0, 0.0), (1.0, 1.0, 1.0)


def state(**kw):
    return replace(
        FrameInertiaState(
            (4, 0, 0),
            Q,
            Z,
            Q,
            Z,
            Z,
            Q,
            Z,
            CenterStepState(Z, Q, (4, 0, 0), Q, S, S, Z, Q),
            Z,
        ),
        **kw,
    )


def team(**kw):
    return replace(FrameInertiaTeam(0x22, 1, 1, 0, 1, 0.25), **kw)


def settings(**kw):
    return replace(FramePreludeSettings(0, -1, 1, 0, 100, 180), **kw)


def run(s=None, t=None, cfg=None):
    return prepare_frame_inertia(s or state(), t or team(), cfg or settings())


def test_disabled_smoothing_retains_work_and_cached_velocity_but_clears_temporary():
    original = state(smoothing_velocity=S, smoothing_shift_vector=(99, 99, 99))
    result = run(original)
    assert result.state.working_old_component_position == Z
    assert result.state.smoothing_velocity == S
    assert result.state.smoothing_shift_vector == Z
    assert result.team.flag == 0x22
    assert not result.smoothing_applied and not result.velocity_updated


@pytest.mark.parametrize("amount,active", [(0, False), (5e-7, False), (1e-6, True)])
def test_smoothing_threshold_includes_equality(amount, active):
    result = run(cfg=settings(movement_inertia_smoothing=amount))
    assert result.smoothing_applied is active


@pytest.mark.parametrize(
    "amount,gain", [(0, 1), (0.5, 0.13375000655651093), (1, _single(0.01))]
)
def test_smoothing_gain_uses_cubic_complement_and_single_constants(amount, gain):
    assert smoothing_gain(amount) == gain


def test_gain_keeps_multiply_then_add_rounding_not_fused_formula():
    assert smoothing_gain(0.3) == 0.34956997632980347
    # Fusing the coefficient multiply/add would instead produce .34957000613212585.


def test_gain_uses_double_pow_then_single_not_three_single_multiplications():
    assert smoothing_gain(0.01) == 0.9705960154533386


@pytest.mark.parametrize("amount", [-0.1, 1.1, math.nan])
def test_gain_rejects_unsupported_domain(amount):
    with pytest.raises(ValueError):
        smoothing_gain(amount)


def test_limit_larger_than_target_retains_velocity_direction_and_magnitude():
    result = run(cfg=settings(movement_inertia_smoothing=1, movement_speed_limit=10))
    assert result.state.smoothing_velocity == (_single(0.04), 0, 0)


def test_velocity_update_generates_double_work_and_separate_single_shift():
    result = run(cfg=settings(movement_inertia_smoothing=0.5))
    assert result.state.smoothing_velocity == (0.5350000262260437, 0, 0)
    assert result.state.working_old_component_position == (3.4649999737739563, 0, 0)
    assert result.state.smoothing_shift_vector == (3.4649999141693115, 0, 0)
    assert result.team.flag == 0x422
    assert result.smoothing_applied and result.velocity_updated


def test_no_update_flag_uses_cached_velocity_without_lerping_new_target():
    result = run(
        state(smoothing_velocity=(1, 0, 0)),
        team(flag=2),
        settings(movement_inertia_smoothing=0.5),
    )
    assert result.state.smoothing_velocity == (1, 0, 0)
    assert result.state.working_old_component_position == (3, 0, 0)
    assert result.state.smoothing_shift_vector == (3, 0, 0)
    assert not result.velocity_updated


@pytest.mark.parametrize("dt", [0, -1])
def test_nonpositive_time_zeroes_new_target_but_still_applies_cached_smoothing(dt):
    result = run(
        state(smoothing_velocity=(1, 0, 0)),
        team(frame_delta_time=dt),
        settings(movement_inertia_smoothing=1),
    )
    expected = _single(1 - _single(0.01))
    assert result.state.smoothing_velocity == (expected, 0, 0)
    assert result.state.working_old_component_position == (
        4 - _single(expected * dt),
        0,
        0,
    )


def test_velocity_limit_uses_local_scale_ratio_before_lerp():
    result = run(
        state(component_world_position=(3, 4, 0)),
        cfg=settings(
            movement_inertia_smoothing=0.5, movement_speed_limit=1, scale_length_ratio=2
        ),
    )
    # target length=5, cap=2, target=(1.2f,1.6f,0) BEFORE filtering.
    assert result.state.smoothing_velocity == pytest.approx(
        (0.1605000198, 0.2140000165, 0), abs=1e-9
    )


@pytest.mark.parametrize(
    "delta,expected", [(1e-10, _single(1e-10)), (1e-9, _single(1e-9)), (2e-9, 0)]
)
def test_clamp_vector_length_has_distinct_strict_epsilon(delta, expected):
    result = run(
        state(component_world_position=(delta, 0, 0)),
        cfg=settings(movement_inertia_smoothing=1, movement_speed_limit=0),
    )
    assert result.state.smoothing_velocity[0] == _single(expected * _single(0.01))


def test_shift_is_subtracted_in_double_before_narrowing_not_derived_from_velocity():
    big = 2**40
    result = run(
        state(
            component_world_position=(big + 0.5, 0, 0),
            working_old_component_position=(big, 0, 0),
            smoothing_velocity=(0.1, 0, 0),
        ),
        team(flag=2),
        settings(movement_inertia_smoothing=0.5),
    )
    assert result.state.working_old_component_position == (big + 0.39990234375, 0, 0)
    assert result.state.smoothing_shift_vector == (0.39990234375, 0, 0)


def test_existing_anchor_shift_and_rotation_are_preserved_for_later_correction():
    original = state(anchor_shift_vector=(10, 0, 0), anchor_shift_rotation=(1, 0, 0, 0))
    result = run(original, cfg=settings(movement_inertia_smoothing=0.5))
    assert result.state.anchor_shift_vector == original.anchor_shift_vector
    assert result.state.anchor_shift_rotation == original.anchor_shift_rotation
    assert original.smoothing_velocity == Z
    assert original.working_old_component_position == Z


@pytest.mark.parametrize("mode,bit", [(1, 4), (2, 0x200)])
def test_teleport_distance_equality_sets_only_requested_mode_flag(mode, bit):
    result = run(
        cfg=settings(teleport_mode=mode, teleport_distance=2, scale_length_ratio=2)
    )
    assert result.teleport_triggered
    assert result.team.flag == 0x22 | bit


@pytest.mark.parametrize("mode", [0, 1, 2])
def test_teleport_below_both_limits_does_not_trigger(mode):
    result = run(cfg=settings(teleport_mode=mode, teleport_distance=5))
    assert not result.teleport_triggered
    assert result.team.flag == 0x22


def test_teleport_rotation_equality_uses_degrees_and_not_position_distance():
    result = run(
        state(component_world_rotation=(0, 0, 1, 0)),
        cfg=settings(teleport_mode=2, teleport_rotation=180),
    )
    assert result.teleport_triggered and result.team.flag == 0x222


@pytest.mark.parametrize("flag", [0x222, 0x26])
def test_existing_keep_or_reset_skips_teleport_threshold_reads(flag):
    result = run(
        t=team(flag=flag),
        cfg=settings(
            teleport_mode=1, teleport_distance=math.nan, teleport_rotation=math.nan
        ),
    )
    assert not result.teleport_triggered
    assert result.team.flag == flag


def test_disabled_teleport_does_not_consume_invalid_thresholds():
    result = run(cfg=settings(teleport_distance=math.nan, teleport_rotation=math.nan))
    assert not result.teleport_triggered


def test_zero_distance_threshold_includes_stationary_component():
    result = run(
        state(component_world_position=Z),
        cfg=settings(teleport_mode=2, teleport_distance=0),
    )
    assert result.teleport_triggered


def test_reset_reinitializes_resolved_component_and_frame_histories():
    half = math.sqrt(0.5)
    original = state(
        component_world_rotation=(0, 0, half, half),
        old_component_world_position=(12, 0, 0),
        step_state=CenterStepState(
            (10, 0, 0), Q, (8, 0, 0), Q, (2, 2, 2), (3, 3, 3), (20, 0, 0), Q
        ),
    )
    result = run(original, cfg=settings(teleport_mode=1, teleport_distance=1))
    assert result.history_reinitialized
    assert result.state.working_old_component_position == (4, 0, 0)
    assert result.state.old_component_world_position == (4, 0, 0)
    assert result.state.working_old_component_rotation == tuple(
        _single(v) for v in original.component_world_rotation
    )
    assert result.state.step_state.old_frame_world_position == (8, 0, 0)
    assert result.state.step_state.now_world_position == (8, 0, 0)
    assert result.state.step_state.old_frame_world_scale == (3, 3, 3)
    finish = advance_frame_inertia(
        result.state, result.team, FrameInertiaSettings(1, -1, -1, 1)
    )
    assert finish.motion.speed == 0 and finish.smoothing_velocity == Z


def test_external_history_flag_reinitializes_history_without_resetting_work_or_pivot():
    result = run(state(old_component_world_position=(9, 0, 0)), t=team(flag=0x40022))
    assert result.history_reinitialized
    assert result.state.working_old_component_position == Z
    assert result.state.old_component_world_position == (9, 0, 0)
    assert result.state.step_state.old_frame_world_position == (4, 0, 0)


def test_reset_does_not_skip_smoothing_before_later_clear_fragment():
    result = run(t=team(flag=0x26), cfg=settings(movement_inertia_smoothing=0.5))
    assert result.smoothing_applied and result.velocity_updated
    assert result.state.smoothing_velocity[0] > 0
    assert result.state.working_old_component_position == (4, 0, 0)


def test_smoothing_and_existing_anchor_feed_frame_history_and_not_motion_alias():
    prepared = run(
        state(anchor_shift_vector=(10, 0, 0)),
        cfg=settings(movement_inertia_smoothing=0.5),
    )
    corrected = advance_frame_inertia(
        prepared.state, prepared.team, FrameInertiaSettings(1, -1, -1, 1)
    )
    assert corrected.motion.delta_single == (0.5350000262260437, 0, 0)
    assert corrected.component_shift_vector == (13.46500015258789, 0, 0)
    assert (
        corrected.step_state.old_frame_world_position
        == corrected.component_shift_vector
    )


def test_two_frames_preserve_velocity_feedback_instead_of_restarting_filter():
    first = run(cfg=settings(movement_inertia_smoothing=1))
    second = run(
        replace(
            first.state,
            component_world_position=(8, 0, 0),
            working_old_component_position=(4, 0, 0),
        ),
        first.team,
        settings(movement_inertia_smoothing=1),
    )
    assert first.state.smoothing_velocity == (_single(0.04), 0, 0)
    assert second.state.smoothing_velocity == (0.07959999889135361, 0, 0)


@pytest.mark.parametrize(
    "kw",
    [
        {"movement_inertia_smoothing": -1},
        {"movement_inertia_smoothing": 2},
        {"scale_length_ratio": -1},
        {"teleport_mode": 3},
        {"teleport_mode": True},
        {"movement_speed_limit": math.inf},
    ],
)
def test_adapter_rejects_unsupported_selected_settings(kw):
    with pytest.raises(ValueError):
        run(cfg=settings(**({"movement_inertia_smoothing": 0.5} | kw)))


def test_adapter_rejects_invalid_frame_time():
    with pytest.raises(ValueError):
        run(t=team(frame_delta_time=math.nan))
