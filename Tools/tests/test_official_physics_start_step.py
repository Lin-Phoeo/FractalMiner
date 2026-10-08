"""Synthetic Start/inertia/End fixtures, NOT an executed official solver oracle."""

import math
import sys
from dataclasses import replace
from pathlib import Path
from typing import Any

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from official_physics_constraints import _single
from official_physics_particle_step import (
    EndStepSettings,
    ParticleEndState,
    finish_particle_step,
)
from official_physics_spring import ClothNormalAxis, SpringConstraintSettings
from official_physics_start_step import (
    ParticleStartState,
    ResolvedStartCenter,
    ResolvedStartSpring,
    StartStepSettings,
    start_particle_step,
)

IDENTITY = (0.0, 0.0, 0.0, 1.0)
ZERO = (0.0, 0.0, 0.0)


def state(**changes: Any) -> ParticleStartState:
    return replace(
        ParticleStartState(
            old_position=(1, 0, 0),
            old_animation_position=(20, 0, 0),
            old_animation_rotation=IDENTITY,
            proxy_position=(40, 0, 0),
            proxy_rotation=IDENTITY,
            velocity=ZERO,
            depth=0,
        ),
        **changes,
    )


def settings(**changes: Any) -> StartStepSettings:
    return replace(
        StartStepSettings(
            frame_interpolation=0.25,
            depth_inertia=1,
            delta_time=0.5,
            damping_curve=(0.0,) * 16,
            power_z=1,
            velocity_weight=1,
            scale_ratio=1,
            gravity=0,
            gravity_direction=(0, -1, 0),
            gravity_ratio=1,
            impact=ZERO,
            force_mode=0,
        ),
        **changes,
    )


def center(**changes: Any) -> ResolvedStartCenter:
    return replace(ResolvedStartCenter(ZERO, ZERO, IDENTITY, ZERO, IDENTITY), **changes)


def run(s=None, cfg=None, c=None, **kwargs):
    return start_particle_step(
        s or state(),
        cfg or settings(),
        attribute=2,
        center=c or center(),
        wind=ZERO,
        **kwargs,
    )


def test_animation_pose_is_distinct_from_simulation_old_position():
    result = run()
    assert result.base_position == result.step_basic_position == (25, 0, 0)
    assert result.next_position == result.velocity_position == (1, 0, 0)
    assert result.base_rotation == result.step_basic_rotation == IDENTITY
    assert result.writes == (
        "base_position",
        "base_rotation",
        "step_basic_position",
        "step_basic_rotation",
        "velocity_position",
        "next_position",
    )
    assert "velocity" not in result.writes and "old_position" not in result.writes


@pytest.mark.parametrize("attribute", [0, 1, 4, 5, 128])
def test_nonmoving_particle_follows_animation_without_center_or_wind(attribute):
    result = start_particle_step(state(), settings(), attribute=attribute)
    assert result.next_position == result.velocity_position == (25, 0, 0)
    assert result.inertia_weight is None and result.integrated_velocity is None


def test_fixed_does_not_evaluate_unused_force_inputs():
    cfg = settings(delta_time=float("nan"), damping_curve=(), gravity=float("inf"))
    result = start_particle_step(state(velocity=(float("nan"), 0, 0)), cfg, attribute=1)
    assert result.next_position == (25, 0, 0)


def test_animation_world_position_keeps_double_precision():
    n = 2**30
    result = run(
        state(
            old_animation_position=(n + 0.125, 0, 0), proxy_position=(n + 0.625, 0, 0)
        )
    )
    assert result.base_position == (n + 0.25, 0, 0)


def test_animation_interpolation_weight_narrows_before_double_lerp():
    t = 0.123456789
    result = run(
        state(old_animation_position=ZERO, proxy_position=(3, 0, 0)),
        settings(frame_interpolation=t),
    )
    assert result.base_position == (3 * _single(t), 0, 0)


def test_pose_quaternion_normalized_after_slerp_not_input_normalized():
    result = run(
        state(old_animation_rotation=(0, 0, 0, 2), proxy_rotation=(0, 0, 2, 0)),
        settings(frame_interpolation=0),
    )
    assert result.base_rotation == IDENTITY


def test_pose_slerp_shortest_arc_and_normalization():
    result = run(state(proxy_rotation=(0, 0, 0, -1)))
    assert result.base_rotation == IDENTITY
    midpoint = run(
        state(proxy_rotation=(0, 0, 1, 0)), settings(frame_interpolation=0.5)
    )
    assert midpoint.base_rotation == pytest.approx(
        (0, 0, math.sqrt(0.5), math.sqrt(0.5))
    )


@pytest.mark.parametrize("depth,expected", [(0, 10), (0.5, 8), (1, 2)])
def test_depth_blends_inertia_toward_step_vector(depth, expected):
    result = run(
        state(old_position=ZERO, depth=depth),
        c=center(inertia_vector=(2, 0, 0), step_vector=(10, 0, 0)),
    )
    assert result.next_position == (expected, 0, 0)
    assert result.inertia_weight == _single(1 - _single(depth * depth))


def test_depth_inertia_parameter_multiplies_squared_depth_gap():
    result = run(
        state(depth=0.5),
        settings(depth_inertia=0.5),
        center(inertia_vector=ZERO, step_vector=(8, 0, 0)),
    )
    assert result.inertia_weight == 0.375
    assert result.next_position == (4, 0, 0)


def test_translation_lerp_rounding_at_each_single_operation():
    a, b, depth = _single(0.1), _single(0.9), _single(0.3)
    t = _single(_single(1 - _single(depth * depth)) * _single(0.7))
    expected = _single(a + _single(_single(b - a) * t))
    result = run(
        state(old_position=ZERO, depth=depth),
        settings(depth_inertia=0.7),
        center(inertia_vector=(a, 0, 0), step_vector=(b, 0, 0)),
    )
    assert result.next_position == (expected, 0, 0)


def test_rotate_about_previous_world_center_then_add_translation():
    original = state(old_position=(12, 0, 0), velocity=(1, 0, 0))
    c = center(
        old_world_position=(10, 0, 0), step_rotation=(0, 0, 1, 0), step_vector=(3, 0, 0)
    )
    result = run(original, c=c)
    assert result.velocity_position == (11, 0, 0)
    assert result.integrated_velocity == (-1, 0, 0)
    assert result.next_position == (10.5, 0, 0)
    assert original.old_position == (12, 0, 0)


def test_rotation_uses_depth_blend_and_rotates_velocity_too():
    result = run(
        state(depth=0, velocity=(1, 0, 0)),
        settings(depth_inertia=0.5),
        center(step_rotation=(0, 0, 1, 0)),
    )
    assert result.inertia_weight == 0.5
    assert result.velocity_position == pytest.approx((0, 1, 0), abs=2e-7)
    assert result.integrated_velocity == pytest.approx((0, 1, 0), abs=2e-7)
    assert result.next_position == pytest.approx((0, 1.5, 0), abs=3e-7)


def test_center_relative_offset_narrows_to_single_even_with_identity_rotation():
    result = run(
        state(old_position=(10 + 1.00000001, 0, 0)),
        c=center(old_world_position=(10, 0, 0)),
    )
    assert result.next_position == result.velocity_position == (11, 0, 0)


def test_velocity_position_reconstructs_delta_not_directly_moved_position():
    original = state(old_position=(1e16, 0, 0), depth=1)
    c = center(
        old_world_position=(1, 0, 0),
        inertia_rotation=(0, 0, 1, 0),
        inertia_vector=(_single(1e16), 0, 0),
    )
    result = run(original, c=c)
    assert result.next_position == (1, 0, 0)
    assert result.velocity_position == (0, 0, 0)


def test_translation_not_multiplied_by_scale_ratio():
    result = run(
        state(old_position=ZERO), settings(scale_ratio=3), center(step_vector=(2, 0, 0))
    )
    assert result.next_position == result.velocity_position == (2, 0, 0)


def test_damping_curve_is_evaluated_at_depth_then_force_is_integrated():
    result = run(
        state(depth=0.5, velocity=(4, 0, 0)),
        settings(
            damping_curve=tuple(i / 15 for i in range(16)),
            velocity_weight=0.5,
            gravity=4,
        ),
    )
    assert result.integrated_velocity == (1, -2, 0)
    assert result.next_position == (1.5, -1, 0)


def test_resolved_wind_is_consumed_not_replaced_with_zero():
    result = start_particle_step(
        state(), settings(), attribute=2, center=center(), wind=(0, 2, 0)
    )
    assert result.integrated_velocity == (0, 1, 0)
    assert result.next_position == (1, 0.5, 0)


@pytest.mark.parametrize(
    "mode,expected", [(0, 4), (1, 5), (2, 1), (10, 10), (11, 6), (99, 4)]
)
def test_force_fragment_is_composed_without_extra_weight_or_velocity_write(
    mode, expected
):
    result = run(
        state(velocity=(4, 0, 0)),
        settings(force_mode=mode, impact=(6, 0, 0), delta_time=1),
    )
    assert result.next_position == (1 + expected, 0, 0)
    assert result.integrated_velocity == (expected, 0, 0)
    assert "velocity" not in result.writes


def test_two_step_center_start_end_feedback_and_real_velocity_distinction():
    s = state()
    end = None
    for _ in range(2):
        begin = run(s, settings(gravity=4), center(step_vector=(2, 0, 0)))
        end = finish_particle_step(
            ParticleEndState(
                begin.next_position,
                s.old_position,
                begin.velocity_position,
                s.velocity,
                0,
                0,
                ZERO,
                s.depth,
            ),
            EndStepSettings(0.5, 1, 1, -1, 0, 0, 0),
            attribute=2,
        )
        s = replace(s, old_position=end.old_position, velocity=end.velocity)
    assert end is not None
    assert s.old_position == (5, -3, 0)
    assert s.velocity == (0, -4, 0)
    assert end.real_velocity == (4, -4, 0)


@pytest.mark.parametrize("attribute", [1, 3, 5])
def test_fixed_spring_branch_requires_its_resolved_inputs(attribute):
    with pytest.raises(ValueError, match="Spring"):
        start_particle_step(
            state(),
            settings(team_flag=0x2000),
            attribute=attribute,
            center=center(),
            wind=ZERO,
        )


def test_fixed_spring_runs_after_force_and_returns_to_base_at_full_power():
    result = start_particle_step(
        state(),
        settings(team_flag=0x2000),
        attribute=1,
        center=center(),
        wind=ZERO,
        spring=ResolvedStartSpring(
            SpringConstraintSettings(1.0, 100.0, 1.0, 0.0),
            ClothNormalAxis.Right,
            0.0,
        ),
    )
    # Force first produces the simulation position (1,0,0); source Spring
    # then pulls that result to the separately stored animation base (25,0,0).
    assert result.velocity_position == (1, 0, 0)
    assert result.next_position == (25, 0, 0)


def test_spring_bit_without_fixed_bit_enters_normal_force_path():
    result = start_particle_step(
        state(), settings(team_flag=0x2000), attribute=0, center=center(), wind=ZERO
    )
    assert result.next_position == (1, 0, 0)


def test_missing_resolved_center_rejected():
    with pytest.raises(ValueError, match="center"):
        start_particle_step(state(), settings(), attribute=2, wind=ZERO)


def test_missing_resolved_wind_rejected():
    with pytest.raises(ValueError, match="wind"):
        start_particle_step(state(), settings(), attribute=2, center=center())


@pytest.mark.parametrize("t", [-0.1, 1.1, float("nan"), True])
def test_frame_interpolation_adapter_bounds(t):
    with pytest.raises(ValueError):
        run(cfg=settings(frame_interpolation=t))


@pytest.mark.parametrize("depth,inertia", [(2, 1), (0, 2), (0, -1)])
def test_out_of_domain_inertia_weight_rejected_not_clamped(depth, inertia):
    with pytest.raises(ValueError, match="weight"):
        run(state(depth=depth), settings(depth_inertia=inertia))


@pytest.mark.parametrize("attribute", [-1, 256, True, 2.0])
def test_attribute_adapter_bounds(attribute):
    with pytest.raises(ValueError):
        start_particle_step(state(), settings(), attribute=attribute)


@pytest.mark.parametrize(
    "field,value",
    [("team_flag", -1), ("team_flag", True), ("delta_time", 0), ("damping_curve", ())],
)
def test_settings_adapter_errors(field, value):
    with pytest.raises(ValueError):
        run(cfg=settings(**{field: value}))


def test_degenerate_pose_rotation_rejected_without_identity_repair():
    with pytest.raises(ValueError, match="quaternion"):
        run(state(old_animation_rotation=(0, 0, 0, 0), proxy_rotation=(0, 0, 0, 0)))


@pytest.mark.parametrize(
    "changes",
    [
        {"old_position": (1, 2)},
        {"old_position": (float("inf"), 0, 0)},
        {"velocity": (float("nan"), 0, 0)},
        {"depth": float("nan")},
    ],
)
def test_selected_particle_invalid_values_rejected(changes):
    with pytest.raises(ValueError):
        run(state(**changes))


def test_center_invalid_values_rejected():
    with pytest.raises(ValueError):
        run(c=center(inertia_vector=(float("nan"), 0, 0)))
