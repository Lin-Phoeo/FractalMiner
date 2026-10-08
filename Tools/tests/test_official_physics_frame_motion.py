"""Tests for the bounded frame-motion reduction inside the frame Team kernel."""

import math
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from official_physics_constraints import _single
from official_physics_frame_motion import reduce_frame_motion
from official_physics_team_tail import (
    FrameWindState,
    TeamWindState,
    WindInfo,
    WindStepSettings,
    advance_wind_state,
)


def test_three_four_five_delta_uses_frame_delta_time_then_now_time_scale():
    result = reduce_frame_motion(
        (3.0, 4.0, 0.0), frame_delta_time=2.0, now_time_scale=2.0
    )
    assert result.speed == 1.25
    assert result.direction == pytest.approx((0.6, 0.8, 0.0), abs=1e-7)


def test_zero_delta_writes_zero_speed_and_direction():
    result = reduce_frame_motion(
        (0.0, 0.0, 0.0), frame_delta_time=1.0, now_time_scale=1.0
    )
    assert result.speed == 0.0
    assert result.direction == (0.0, 0.0, 0.0)


@pytest.mark.parametrize("frame_delta_time", [0.0, -1.0])
def test_nonpositive_frame_delta_time_only_zeroes_speed(frame_delta_time):
    result = reduce_frame_motion(
        (0.0, 3.0, 4.0),
        frame_delta_time=frame_delta_time,
        now_time_scale=2.0,
    )
    assert result.speed == 0.0
    assert result.direction == pytest.approx((0.0, 0.6, 0.8), abs=1e-7)


@pytest.mark.parametrize(
    "now_time_scale", [_single(1e-6), _single(1e-6) / 2, 0.0, -1.0]
)
def test_time_scale_at_or_below_source_epsilon_only_zeroes_speed(now_time_scale):
    result = reduce_frame_motion(
        (0.0, 3.0, 4.0),
        frame_delta_time=2.0,
        now_time_scale=now_time_scale,
    )
    assert result.speed == 0.0
    assert result.direction == pytest.approx((0.0, 0.6, 0.8), abs=1e-7)


def test_length_equal_to_epsilon_keeps_speed_but_zeroes_direction():
    epsilon = _single(1e-6)
    result = reduce_frame_motion(
        (epsilon, 0.0, 0.0), frame_delta_time=1.0, now_time_scale=1.0
    )
    assert result.speed == epsilon
    assert result.direction == (0.0, 0.0, 0.0)


def test_length_above_epsilon_is_normalized():
    epsilon = _single(1e-6)
    result = reduce_frame_motion(
        (_single(epsilon * 2), 0.0, 0.0),
        frame_delta_time=1.0,
        now_time_scale=1.0,
    )
    assert result.direction == (1.0, 0.0, 0.0)


def test_double_delta_is_narrowed_lane_wise_before_dot_and_length():
    result = reduce_frame_motion(
        (16777217.0, 1.0000000596046448, 0.0),
        frame_delta_time=1.0,
        now_time_scale=1.0,
    )
    assert result.delta_single == (16777216.0, 1.0, 0.0)
    assert result.speed == 16777216.0


def test_speed_retains_reciprocal_then_multiply_single_order():
    result = reduce_frame_motion(
        (0.35512974858283997, 0.0, 0.0),
        frame_delta_time=114.75224304199219,
        now_time_scale=3276.538330078125,
    )
    length = _single(0.35512974858283997)
    dt = _single(114.75224304199219)
    scale = _single(3276.538330078125)
    rate = _single(length / dt)
    expected = _single(_single(1.0 / scale) * rate)
    collapsed = _single(rate / scale)
    assert expected != collapsed
    assert result.speed == expected


@pytest.mark.parametrize(
    "delta,frame_delta_time,now_time_scale",
    [
        ((math.nan, 0.0, 0.0), 1.0, 1.0),
        ((0.0, math.inf, 0.0), 1.0, 1.0),
        ((0.0, 0.0, 0.0), math.nan, 1.0),
        ((0.0, 0.0, 0.0), 1.0, math.inf),
    ],
)
def test_adapter_rejects_nonfinite_inputs(delta, frame_delta_time, now_time_scale):
    with pytest.raises(ValueError, match="finite"):
        reduce_frame_motion(
            delta,
            frame_delta_time=frame_delta_time,
            now_time_scale=now_time_scale,
        )


def test_adapter_requires_exactly_three_delta_lanes():
    with pytest.raises(ValueError, match="three"):
        reduce_frame_motion((1.0, 2.0), frame_delta_time=1.0, now_time_scale=1.0)


def test_result_feeds_existing_moving_wind_without_conflating_two_scales():
    motion = reduce_frame_motion(
        (0.0, 3.0, 4.0), frame_delta_time=2.0, now_time_scale=2.0
    )
    old_moving = WindInfo(77, 3.0, 9.0, (1.0, 0.0, 0.0))
    result = advance_wind_state(
        TeamWindState((), old_moving),
        WindStepSettings(influence=1.0, frequency=0.0, moving_wind=2.0),
        frame=FrameWindState.from_motion(motion),
        scale_ratio=2.0,
        delta_time=1.0,
    )
    # Reduction first divides 5 units by dt=2 and nowTimeScale=2 => 1.25.
    # UpdateWind later and independently computes 1.25*movingWind/scaleRatio.
    assert result.state.moving.main == 1.25
    assert result.state.moving.direction == pytest.approx((0.0, -0.6, -0.8))


def test_frame_wind_adapter_requires_a_frame_motion_result():
    with pytest.raises(TypeError, match="FrameMotionResult"):
        FrameWindState.from_motion(object())
