"""Synthetic scalar/state probes, not an executed official DLL oracle."""

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
    ResolvedCenter,
    _single_normalize,
    finish_particle_step,
    integrate_force_fragment,
)


def state(**changes: Any) -> ParticleEndState:
    return replace(
        ParticleEndState(
            next_position=(1, 0, 0),
            old_position=(0, 0, 0),
            velocity_position=(0, 0, 0),
            velocity=(8, 9, 10),
            friction=0,
            static_friction=0,
            collision_normal=(0, 1, 0),
            depth=0,
        ),
        **changes,
    )


def settings(**changes: Any) -> EndStepSettings:
    return replace(EndStepSettings(1, 1, 1, -1, 0, 0, 0), **changes)


def test_unconstrained_end_publishes_two_distinct_velocities():
    result = finish_particle_step(
        state(velocity_position=(0.5, 0, 0)), settings(velocity_weight=0.5), attribute=2
    )
    assert result.velocity == (0.25, 0, 0)
    assert result.real_velocity == (1, 0, 0)
    assert result.old_position == result.corrected_next_position == (1, 0, 0)
    assert result.writes == (
        "static_friction",
        "friction",
        "velocity",
        "real_velocity",
        "old_position",
    )


@pytest.mark.parametrize("attribute", [0, 1, 4, 5, 128])
def test_fixed_only_real_velocity_and_old_position(attribute):
    result = finish_particle_step(
        state(friction=0.8, static_friction=0.9), settings(), attribute=attribute
    )
    assert result.velocity == (8, 9, 10)
    assert result.friction == _single(0.8)
    assert result.static_friction == _single(0.9)
    assert result.real_velocity == (1, 0, 0)
    assert result.writes == ("real_velocity", "old_position")


def test_team_spring_bit_makes_fixed_eligible_for_end_math():
    result = finish_particle_step(state(), settings(team_flag=0x2000), attribute=1)
    assert result.velocity == (1, 0, 0)
    assert "friction" in result.writes


def test_static_stick_changes_old_position_not_source_next_buffer():
    original = state(friction=1, static_friction=0.99)
    result = finish_particle_step(original, settings(static_friction=2), attribute=2)
    assert result.static_friction == 1
    assert result.old_position == (0, 0, 0)
    assert result.velocity == (1, 0, 0)  # Both local next and velocityPos corrected.
    assert result.real_velocity == (0, 0, 0)
    assert original.next_position == (1, 0, 0)
    assert "next_position" not in result.writes


def test_static_slip_uses_maximum_not_minimum_decay():
    result = finish_particle_step(
        state(friction=1, static_friction=0.8),
        settings(static_friction=0.1),
        attribute=2,
    )
    expected = max(0.0, _single(0.8) - (1 - _single(0.1)) / _single(0.2))
    assert result.static_friction == _single(expected) == 0
    assert result.old_position == (1, 0, 0)


def test_static_decay_minimum_and_projection_only_tangent():
    original = state(next_position=(1, 2, 0), friction=1, static_friction=0.5)
    result = finish_particle_step(
        original, settings(static_friction=0.999), attribute=2
    )
    slip = _single(0.5) - _single(0.05)
    assert result.static_friction == _single(slip)
    assert result.old_position == pytest.approx((1 - slip, 2, 0))
    assert result.real_velocity == pytest.approx(result.old_position)


def test_projection_does_not_divide_by_nonunit_normal_length():
    result = finish_particle_step(
        state(
            next_position=(1, 1, 0),
            friction=1,
            static_friction=0.5,
            collision_normal=(0, 2, 0),
        ),
        settings(static_friction=10),
        attribute=2,
    )
    stick = _single(0.5) + _single(0.04)
    assert result.old_position == pytest.approx((1 - stick, 1 + 3 * stick, 0))


@pytest.mark.parametrize(
    "normal,friction,static_parameter",
    [((0, 0, 0), 1, 1), ((0, 1, 0), 0, 1), ((0, 1, 0), 1, 0)],
)
def test_inactive_static_branch_decays_saved_state(normal, friction, static_parameter):
    result = finish_particle_step(
        state(collision_normal=normal, friction=friction, static_friction=0.5),
        settings(static_friction=static_parameter),
        attribute=2,
    )
    assert result.static_friction == _single(_single(0.5) - _single(0.05))
    assert result.old_position == (1, 0, 0)


def test_dynamic_friction_orientation_and_memory_decay():
    result = finish_particle_step(
        state(friction=1), settings(dynamic_friction=1), attribute=2
    )
    assert result.velocity == (0.25, 0, 0)
    assert result.friction == _single(0.6)
    assert result.real_velocity == (1, 0, 0)
    normal_motion = finish_particle_step(
        state(next_position=(0, 1, 0), friction=1),
        settings(dynamic_friction=1),
        attribute=2,
    )
    assert normal_motion.velocity == (0, 1, 0)


@pytest.mark.parametrize("limit,expected", [(-1, 1), (0, 0), (0.5, 0.5), (2, 1)])
def test_speed_limit_does_not_clamp_real_velocity_or_position(limit, expected):
    result = finish_particle_step(
        state(), settings(particle_speed_limit=limit), attribute=2
    )
    assert result.velocity == (expected, 0, 0)
    assert result.real_velocity == (1, 0, 0)
    assert result.old_position == (1, 0, 0)


def test_zero_speed_and_tiny_vector_are_safe():
    result = finish_particle_step(
        state(next_position=(0, 0, 0)),
        settings(particle_speed_limit=0, dynamic_friction=1),
        attribute=2,
    )
    assert result.velocity == result.real_velocity == (0, 0, 0)
    tiny = finish_particle_step(
        state(next_position=(1e-10, 0, 0)),
        settings(particle_speed_limit=0),
        attribute=2,
    )
    assert tiny.velocity[0] == _single(1e-10)


def test_speed_limit_uses_distinct_one_e_minus_nine_threshold():
    result = finish_particle_step(
        state(next_position=(1e-9, 0, 0)), settings(particle_speed_limit=0), attribute=2
    )
    assert result.velocity == (0, 0, 0)


def test_scaled_limit_and_final_velocity_weight():
    result = finish_particle_step(
        state(next_position=(4, 0, 0)),
        settings(scale_ratio=2, particle_speed_limit=1, velocity_weight=0.25),
        attribute=2,
    )
    assert result.velocity == (0.5, 0, 0)
    assert result.real_velocity == (4, 0, 0)


def test_centrifugal_push_is_after_speed_limit_and_not_real_velocity():
    original = state(
        next_position=(1, 0, 0), old_position=(1, -1, 0), velocity_position=(1, -1, 0)
    )
    result = finish_particle_step(
        original,
        settings(particle_speed_limit=0, centrifugal_acceleration=1),
        attribute=2,
        center=ResolvedCenter((0, 0, 0), (0, 0, 1), 2),
    )
    assert result.velocity == pytest.approx((_single(0.16), 0, 0))
    assert result.real_velocity == (0, 1, 0)
    assert result.old_position == (1, 0, 0)


def test_centrifugal_opposite_tangent_is_clamped_out():
    result = finish_particle_step(
        state(next_position=(1, 0, 0), velocity_position=(1, 1, 0)),
        settings(centrifugal_acceleration=1),
        attribute=2,
        center=ResolvedCenter((0, 0, 0), (0, 0, 1), 2),
    )
    assert result.velocity == (0, -1, 0)


def test_centrifugal_on_axis_has_no_push():
    result = finish_particle_step(
        state(next_position=(0, 0, 1), velocity_position=(-1, 0, 1)),
        settings(centrifugal_acceleration=1),
        attribute=2,
        center=ResolvedCenter((0, 0, 0), (0, 0, 1), 2),
    )
    assert result.velocity == (1, 0, 0)


def test_centrifugal_requires_resolved_center_not_identity_repair():
    with pytest.raises(ValueError, match="center"):
        finish_particle_step(state(), settings(centrifugal_acceleration=1), attribute=2)


@pytest.mark.parametrize("omega", [0, -1, 1e-10])
def test_centrifugal_angular_gate(omega):
    result = finish_particle_step(
        state(),
        settings(centrifugal_acceleration=1),
        attribute=2,
        center=ResolvedCenter((0, 0, 0), (0, 0, 1), omega),
    )
    assert result.velocity == (1, 0, 0)


def test_degenerate_centrifugal_axis_rejected():
    with pytest.raises(ValueError, match="axis"):
        finish_particle_step(
            state(),
            settings(centrifugal_acceleration=1),
            attribute=2,
            center=ResolvedCenter((0, 0, 0), (0, 0, 0), 2),
        )


def test_degenerate_single_normalization_guard():
    with pytest.raises(ValueError, match="direction"):
        _single_normalize((0, 0, 0))


@pytest.mark.parametrize("mode", [True, 1.5, -(2**31) - 1, 2**31])
def test_bad_force_mode_rejected(mode):
    with pytest.raises(ValueError, match="Int32"):
        integrate_force_fragment(
            (0, 0, 0),
            depth=0,
            damping=0,
            power_z=1,
            velocity_weight=1,
            gravity=0,
            gravity_direction=(0, 0, 0),
            gravity_ratio=1,
            impact=(0, 0, 0),
            force_mode=mode,
            wind=(0, 0, 0),
            scale_ratio=1,
            delta_time=1,
        )


def test_wind_is_resolved_input_and_depth_mass_changes_impact():
    velocity, displacement = integrate_force_fragment(
        (0, 0, 0),
        depth=1,
        damping=0,
        power_z=1,
        velocity_weight=1,
        gravity=0,
        gravity_direction=(0, 0, 0),
        gravity_ratio=1,
        impact=(6, 0, 0),
        force_mode=1,
        wind=(0, 2, 0),
        scale_ratio=0.5,
        delta_time=0.5,
    )
    assert velocity == (1.5, 0.5, 0)
    assert displacement == (0.75, 0.25, 0)


def test_force_fragment_gravity_scaled_semi_implicit_step():
    velocity, displacement = integrate_force_fragment(
        (0, 0, 0),
        depth=0,
        damping=0,
        power_z=1,
        velocity_weight=1,
        gravity=10,
        gravity_direction=(0, -1, 0),
        gravity_ratio=0.5,
        impact=(0, 0, 0),
        force_mode=0,
        wind=(0, 0, 0),
        scale_ratio=2,
        delta_time=0.5,
    )
    assert velocity == (0, -5, 0)
    assert displacement == (0, -2.5, 0)


@pytest.mark.parametrize(
    "mode,expected", [(0, 0), (1, 1), (2, 1), (10, 6), (11, 6), (12, 0)]
)
def test_force_mode_depth_mass_and_velocity_reset(mode, expected):
    velocity, displacement = integrate_force_fragment(
        (4, 0, 0),
        depth=0,
        damping=0,
        power_z=1,
        velocity_weight=1,
        gravity=0,
        gravity_direction=(0, 0, 0),
        gravity_ratio=1,
        impact=(6, 0, 0),
        force_mode=mode,
        wind=(0, 0, 0),
        scale_ratio=1,
        delta_time=1,
    )
    old = 0 if mode in (2, 11) else 4
    assert velocity == displacement == (old + expected, 0, 0)


def test_damping_has_two_clamps_and_preserves_operation_order():
    kwargs = {
        "depth": 1,
        "velocity_weight": 0.5,
        "gravity": 0,
        "gravity_direction": (0, 0, 0),
        "gravity_ratio": 1,
        "impact": (0, 0, 0),
        "force_mode": 0,
        "wind": (0, 0, 0),
        "scale_ratio": 1,
        "delta_time": 1,
    }
    velocity, _ = integrate_force_fragment((4, 0, 0), damping=0.25, power_z=2, **kwargs)
    assert velocity == (1, 0, 0)
    velocity, _ = integrate_force_fragment((4, 0, 0), damping=2, power_z=0.5, **kwargs)
    assert velocity == (1, 0, 0)
    velocity, _ = integrate_force_fragment((4, 0, 0), damping=1, power_z=2, **kwargs)
    assert velocity == (0, 0, 0)


def test_two_step_force_end_feedback():
    # Constant gravity, no constraints/center motion: a synthetic mathematical
    # recurrence. It is NOT a runtime proof of the complete official solver.
    p, v = (0, 0, 0), (0, 0, 0)
    for _ in range(2):
        _, delta = integrate_force_fragment(
            v,
            depth=0,
            damping=0,
            power_z=1,
            velocity_weight=1,
            gravity=4,
            gravity_direction=(0, -1, 0),
            gravity_ratio=1,
            impact=(0, 0, 0),
            force_mode=0,
            wind=(0, 0, 0),
            scale_ratio=1,
            delta_time=0.5,
        )
        nxt = tuple(a + b for a, b in zip(p, delta, strict=True))
        result = finish_particle_step(
            state(next_position=nxt, old_position=p, velocity_position=p),
            settings(delta_time=0.5),
            attribute=2,
        )
        p, v = result.old_position, result.velocity
    assert p == (0, -3, 0) and v == (0, -4, 0)


@pytest.mark.parametrize(
    "field,value",
    [
        ("delta_time", 0),
        ("delta_time", float("nan")),
        ("scale_ratio", float("inf")),
        ("team_flag", True),
        ("team_flag", -1),
        ("velocity_weight", "1"),
    ],
)
def test_bad_end_settings_rejected(field, value):
    with pytest.raises(ValueError):
        finish_particle_step(state(), settings(**{field: value}), attribute=2)


@pytest.mark.parametrize("attribute", [-1, 256, True, 2.0])
def test_bad_attribute_rejected(attribute):
    with pytest.raises(ValueError):
        finish_particle_step(state(), settings(), attribute=attribute)


@pytest.mark.parametrize("normal", [(1, 2), (float("nan"), 0, 0)])
def test_bad_normal_rejected(normal):
    with pytest.raises(ValueError):
        finish_particle_step(state(collision_normal=normal), settings(), attribute=2)
