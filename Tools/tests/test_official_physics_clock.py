"""Recovered clock equations; not independent native execution/solver tests."""

import math
import struct
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from official_physics_clock import fixed_callback_count, frame_settings


def f32(value):
    return struct.unpack("<f", struct.pack("<f", value))[0]


@pytest.mark.parametrize(
    "frequency,steps,expected_f,expected_n",
    [
        (-1, 0, 30, 1),
        (30, 1, 30, 1),
        (90, 3, 90, 3),
        (150, 5, 150, 5),
        (151, 6, 150, 5),
    ],
)
def test_clamps_then_derives_single_precision_step(
    frequency, steps, expected_f, expected_n
):
    state = frame_settings(frequency, steps, 1.0)
    assert (state.frequency, state.max_steps) == (expected_f, expected_n)
    assert state.simulation_delta_time == f32(1.0 / expected_f)
    assert state.max_delta_time == f32(expected_n * state.simulation_delta_time)


@pytest.mark.parametrize("frequency", [30, 45, 60, 89, 90, 91, 120, 150])
def test_power_vector_follows_native_lane_order_and_branch(frequency):
    result = frame_settings(frequency, 3, 1.0)
    r = f32(90.0 / frequency)
    expected = (
        r,
        f32(r**0.5) if r > 1 else r,
        f32(r ** f32(0.3)) if r > 1 else r,
        f32(r ** f32(1.8)),
    )
    assert result.simulation_power == expected
    if frequency >= 90:
        assert result.simulation_power[1:3] == (r, r)
    if frequency == 90:
        assert result.simulation_power == (1.0, 1.0, 1.0, 1.0)


@pytest.mark.parametrize(
    "scale,expected", [(-2.0, 0.0), (-0.0, -0.0), (0.25, 0.25), (2.0, 1.0)]
)
def test_global_scale_clamp_does_not_rescale_base_step_or_power(scale, expected):
    state = frame_settings(90, 3, scale)
    assert state.global_time_scale == expected
    assert state.simulation_delta_time == f32(1 / 90)
    assert state.simulation_power == (1.0, 1.0, 1.0, 1.0)
    assert math.copysign(1.0, state.global_time_scale) == math.copysign(1.0, expected)


@pytest.mark.parametrize(
    "value", [math.nan, math.inf, -math.inf, 1e100, True, "1", None]
)
def test_adapter_refuses_invalid_scale_instead_of_claiming_native_edge_equivalence(
    value,
):
    with pytest.raises(ValueError):
        frame_settings(90, 3, value)


@pytest.mark.parametrize(
    "index,value",
    [(0, True), (0, 90.0), (0, 2**31), (1, -(2**31) - 1), (1, None), (1, "3")],
)
def test_adapter_requires_int32_settings(index, value):
    args = [90, 3, 1.0]
    args[index] = value
    with pytest.raises(ValueError):
        frame_settings(*args)


def test_count_is_render_interval_counter_not_simulation_substeps():
    count = 0
    for _ in range(3):
        count = fixed_callback_count(count)
    assert count == 3
    assert fixed_callback_count(count, reset=True) == 0
    assert fixed_callback_count(2**31 - 1) == -(2**31)
    assert fixed_callback_count(-1) == 0


@pytest.mark.parametrize("value", [True, 1.0, 2**31, -(2**31) - 1, None])
def test_counter_adapter_rejects_non_int32_inputs(value):
    with pytest.raises(ValueError):
        fixed_callback_count(value)


@pytest.mark.parametrize("reset", [1, None, "reset"])
def test_counter_adapter_rejects_ambiguous_reset_policy(reset):
    with pytest.raises(ValueError):
        fixed_callback_count(0, reset=reset)
