"""Motion tests use explicit produced inputs, not native/Burst execution."""

import math
import sys
from dataclasses import replace
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from official_physics_angle_cache import rotate_single
from official_physics_constraints import _single, evaluate_curve
from official_physics_motion import (
    MotionBuffers,
    MotionParameters,
    MotionSettings,
    MotionTeam,
    convert_motion_parameters,
    motion_particle,
    solve_motion_range,
    solve_motion_slot,
)

ZERO = (0.0, 0.0, 0.0)
IDENTITY = (0.0, 0.0, 0.0, 1.0)


def curve(value):
    return (value,) * 16


def settings(*, maximum=True, backstop=False, **changes):
    parameters = MotionParameters(maximum, curve(1), backstop, 1, curve(0), 1)
    return MotionSettings(replace(parameters, **changes), curve(0.006), 1)


def particle(position, config=None, *, base=ZERO, rotation=IDENTITY, depth=0.5):
    return motion_particle(
        position, (0.25, -0.5, 0.75), base, rotation, depth, config or settings()
    )


def inputs():
    return {
        "buffers": MotionBuffers(
            ((9, 9, 9), (2, 0, 0)), (ZERO, ZERO), (ZERO, ZERO), (IDENTITY, IDENTITY)
        ),
        "teams": {3: MotionTeam(1, 4)},
        "parameters": {3: settings(stiffness=0.5)},
        "step_particle_indices": (1, 1),
        "team_ids": (0, 3),
        "attributes": (0, 0, 0, 0, 2),
        "depths": (0, 0, 0, 0, 0.5),
    }


def test_maximum_and_widened_single_velocity_feedback():
    result = particle((3, 4, 0))
    # Native clamp ratio multiplication followed by the separate lerp(1).
    candidate = (3 * (1 / 5), 4 * (1 / 5), 0.0)
    expected = (3 + (candidate[0] - 3), 4 + (candidate[1] - 4), 0.0)
    correction = (expected[0] - 3, expected[1] - 4, 0.0)
    assert result.next_position == expected
    assert result.correction == correction
    assert result.velocity_position == (
        0.25 + correction[0] * _single(0.95),
        -0.5 + correction[1] * _single(0.95),
        0.75,
    )
    assert result.max_distance_applied and not result.backstop_applied
    assert result.writes == ("next_position", "velocity_position")
    assert result.velocity_position[0] != 0.25 + correction[0] * 0.95


@pytest.mark.parametrize("position", [ZERO, (1, 0, 0), (0.5, 0, 0)])
def test_unviolated_maximum_still_publishes_two_buffers(position):
    result = particle(position)
    assert result.next_position == position
    assert result.velocity_position == (0.25, -0.5, 0.75)
    assert not result.max_distance_applied
    assert len(result.writes) == 2


@pytest.mark.parametrize("stiffness", [0, 0.5, 1, 2, -1])
def test_stiffness_is_single_but_is_not_saturated(stiffness):
    result = particle((2, 0, 0), settings(stiffness=stiffness))
    assert result.next_position == (2 - stiffness, 0, 0)
    assert result.velocity_position[0] == 0.25 - stiffness * _single(0.95)


@pytest.mark.parametrize("distance", [0, -1])
def test_nonpositive_maximum_retains_native_clamp_rule(distance):
    result = particle((2, 0, 0), settings(max_distance_curve=curve(distance)))
    assert result.next_position == (distance, 0, 0)


def test_clamp_epsilon_is_strict_and_widened_single():
    epsilon = _single(1e-9)
    config = settings(max_distance_curve=curve(0))
    assert particle((epsilon, 0, 0), config).next_position == (epsilon, 0, 0)
    assert (
        particle((math.nextafter(epsilon, math.inf), 0, 0), config).next_position
        == ZERO
    )


def test_backstop_pushes_from_negative_normal_sphere():
    result = particle((0, -0.5, 0), settings(maximum=False, backstop=True))
    assert result.next_position == ZERO
    assert result.correction == (0, 0.5, 0)
    assert result.backstop_applied and not result.max_distance_applied


@pytest.mark.parametrize("position", [(0, -1, 0), ZERO, (0, 0.003, 0), (0, 1, 0)])
def test_backstop_center_surface_shell_and_outside_do_not_project(position):
    result = particle(position, settings(maximum=False, backstop=True))
    assert result.next_position == position
    assert not result.backstop_applied


@pytest.mark.parametrize("radius", [0, -1])
def test_disabled_radius_does_not_evaluate_backstop_curve(radius):
    result = particle(
        (0, -0.5, 0),
        settings(
            maximum=False,
            backstop=True,
            backstop_radius=radius,
            backstop_distance_curve=(),
        ),
    )
    assert result.next_position == (0, -0.5, 0)
    assert not result.backstop_applied


def test_maximum_then_backstop_order_is_not_reversed():
    config = settings(backstop=True, max_distance_curve=curve(0.25))
    result = particle((0, -2, 0), config)
    assert result.next_position == ZERO
    assert result.max_distance_applied and result.backstop_applied


@pytest.mark.parametrize(
    "axis,direction",
    [
        (0, (1, 0, 0)),
        (1, (0, 1, 0)),
        (2, (0, 0, 1)),
        (3, (-1, 0, 0)),
        (4, (0, -1, 0)),
        (5, (0, 0, -1)),
        (-1, (0, 1, 0)),
        (99, (0, 1, 0)),
    ],
)
def test_six_normal_axes_and_default_up(axis, direction):
    config = replace(settings(maximum=False, backstop=True), normal_axis=axis)
    result = particle(tuple(-0.5 * lane for lane in direction), config)
    assert result.next_position == ZERO
    assert result.backstop_applied


def test_maximum_uses_squared_depth_not_raw_depth():
    samples = tuple(index / 15 for index in range(16))
    config = settings(max_distance_curve=samples)
    expected = evaluate_curve(samples, _single(_single(0.6) * _single(0.6)))
    result = particle((2, 0, 0), config, depth=0.6)
    assert result.next_position == (expected, 0, 0)
    assert expected != evaluate_curve(samples, 0.6)


def test_backstop_distance_uses_squared_depth_and_single_center_offset():
    samples = tuple(index / 15 for index in range(16))
    config = settings(maximum=False, backstop=True, backstop_distance_curve=samples)
    result = particle((0, -0.7, 0), config, depth=0.6)
    distance = evaluate_curve(samples, _single(_single(0.6) * _single(0.6)))
    assert result.next_position == (0, 1 - _single(distance + 1), 0)


def test_double_positions_retain_large_world_origin():
    origin = 2**30
    result = particle((origin + 2, origin, origin), base=(origin, origin, origin))
    assert result.next_position == (origin + 1, origin, origin)
    assert result.correction == (-1, 0, 0)


def test_nonunit_quaternion_is_not_normalized_and_center_offset_is_single():
    rotation = (0.13, -0.29, 0.47, 0.73)
    direction = rotate_single(rotation, (0, 1, 0))
    radius, distance = _single(1.17), _single(0.11)
    separation = _single(radius + distance)
    center = tuple(_single(_single(-lane) * separation) for lane in direction)
    position = (center[0] + 0.1, center[1] + 0.2, center[2] - 0.1)
    delta = tuple(position[i] - center[i] for i in range(3))
    length = math.sqrt((delta[1] ** 2 + delta[0] ** 2) + delta[2] ** 2)
    expected = tuple(center[i] + (delta[i] / length) * radius for i in range(3))
    config = settings(
        maximum=False,
        backstop=True,
        backstop_radius=1.17,
        backstop_distance_curve=curve(0.11),
    )
    result = particle(position, config, rotation=rotation)
    # Final lerp(1) is still original + (candidate-original), not direct candidate.
    assert result.next_position == tuple(
        position[i] + (expected[i] - position[i]) for i in range(3)
    )
    assert result.backstop_applied


def test_half_turn_quaternion_has_independent_geometric_reference():
    # An exact 180-degree X rotation sends Up to Down. Backstop then lies at
    # y=+1 rather than y=-1. Expected geometry does not use rotate_single.
    result = particle(
        (0, 0.5, 0), settings(maximum=False, backstop=True), rotation=(1, 0, 0, 0)
    )
    assert result.next_position == ZERO and result.backstop_applied
    assert result.correction == (0, -0.5, 0)


def test_nonaxial_backstop_uses_three_divisions_not_reciprocal_multiply():
    center = (0, -1, 0)
    position = (0.123456789, -1 + 0.234567891, 0.345678912)
    delta = tuple(position[i] - center[i] for i in range(3))
    length = math.sqrt(
        (delta[1] * delta[1] + delta[0] * delta[0]) + delta[2] * delta[2]
    )
    projected = tuple(center[i] + delta[i] / length for i in range(3))
    expected = tuple(position[i] + (projected[i] - position[i]) for i in range(3))
    reciprocal = 1 / length
    wrong_projected = tuple(center[i] + delta[i] * reciprocal for i in range(3))
    wrong = tuple(position[i] + (wrong_projected[i] - position[i]) for i in range(3))
    result = particle(position, settings(maximum=False, backstop=True))
    assert result.next_position == expected
    assert expected != wrong


def test_disabled_settings_skip_team_proxy_and_all_particle_buffers():
    data = inputs()
    data.update(
        teams={}, buffers=MotionBuffers((), (), (), ()), attributes=(), depths=()
    )
    data["parameters"] = {3: settings(maximum=False)}
    visit = solve_motion_slot(**data, slot=0)
    assert visit.status == "disabled" and visit.proxy_index is None
    assert visit.result is None and visit.writes == ()


@pytest.mark.parametrize("attribute", [0, 1, 8, 9, 16, 17])
def test_nonmove_skips_position_and_depth_buffers(attribute):
    data = inputs()
    data.update(buffers=MotionBuffers((), (), (), ()), depths=())
    data["attributes"] = (0, 0, 0, 0, attribute)
    visit = solve_motion_slot(**data, slot=0)
    assert visit.status == "non-move" and visit.result is None


def test_nonmotion_loads_next_base_depth_but_not_quaternion_velocity():
    data = inputs()
    data["attributes"] = (0, 0, 0, 0, 10)
    data["buffers"] = replace(data["buffers"], base_rotations=(), velocity_positions=())
    visit = solve_motion_slot(**data, slot=0)
    assert visit.status == "non-motion" and visit.result is None
    data["depths"] = ()
    with pytest.raises(ValueError):
        solve_motion_slot(**data, slot=0)


@pytest.mark.parametrize("attribute", [2, 3, 18, 34, 130, 255 & ~8])
def test_move_without_invalid_motion_bit_is_eligible(attribute):
    data = inputs()
    data["attributes"] = (0, 0, 0, 0, attribute)
    visit = solve_motion_slot(**data, slot=0)
    assert visit.particle_index == 1 and visit.team_id == 3 and visit.proxy_index == 4
    assert visit.status == "applied" and visit.result is not None
    assert visit.result.next_position == (1.5, 0, 0)


def test_repeat_range_consumes_previous_writes_and_preserves_inputs():
    data = inputs()
    original = data["buffers"]
    result = solve_motion_range(**data, index_count=2)
    assert result.buffers.next_positions[1] == (1.25, 0, 0)
    assert result.buffers.velocity_positions[1] == (-0.75 * _single(0.95), 0, 0)
    assert original.next_positions[1] == (2, 0, 0)
    assert result.buffers.base_positions is original.base_positions
    assert result.buffers.base_rotations is original.base_rotations
    assert result.buffers.next_positions[0] is original.next_positions[0]


@pytest.mark.parametrize("count", [0, -1, -0x80000000])
def test_nonpositive_count_does_not_consume_other_inputs(count):
    data = inputs()
    data.update(
        teams={},
        parameters={},
        step_particle_indices=(),
        team_ids=(),
        attributes=(),
        depths=(),
    )
    result = solve_motion_range(**data, index_count=count)
    assert result.buffers is data["buffers"] and result.visits == ()


def test_all_skipped_range_preserves_original_buffers():
    data = inputs()
    data["attributes"] = (0, 0, 0, 0, 1)
    result = solve_motion_range(**data, index_count=2)
    assert result.buffers is data["buffers"]


@pytest.mark.parametrize("bad_team", [-1, -32768, 32768, True])
def test_adapter_rejects_unsafe_team_indices_not_python_negative_indexing(bad_team):
    data = inputs()
    data["team_ids"] = (0, bad_team)
    with pytest.raises(ValueError):
        solve_motion_slot(**data, slot=0)


def test_proxy_arithmetic_wraps_before_adapter_bounds_check():
    data = inputs()
    data["teams"] = {3: MotionTeam(0x7FFFFFFF, 0)}
    with pytest.raises(ValueError):
        solve_motion_slot(**data, slot=0)


@pytest.mark.parametrize("cloth_type", [0, 1, 10, 11, -1])
def test_convert_spring_only_disables_flags_and_does_not_validate_ranges(cloth_type):
    params = convert_motion_parameters(
        True, curve(0.3), True, -2, curve(0.1), 2, cloth_type
    )
    assert params.use_max_distance is (cloth_type != 10)
    assert params.use_backstop is (cloth_type != 10)
    assert params.backstop_radius == -2 and params.stiffness == 2
    assert params.max_distance_curve == curve(_single(0.3))


@pytest.mark.parametrize("value", [True, math.nan, math.inf, "1", 1e40])
def test_active_finite_domain_rejections_are_adapter_policy(value):
    with pytest.raises(ValueError):
        particle((2, 0, 0), settings(stiffness=value))


def test_convert_rejects_nonbool_flags_and_malformed_curve():
    with pytest.raises(ValueError):
        convert_motion_parameters(1, curve(1), False, 1, curve(0), 1, 0)  # type: ignore[arg-type]
    with pytest.raises(ValueError):
        convert_motion_parameters(True, (), False, 1, curve(0), 1, 0)


def test_slot_requires_explicit_parameters_and_team_storage():
    data = inputs()
    data["parameters"] = {}
    with pytest.raises(ValueError):
        solve_motion_slot(**data, slot=0)
    data = inputs()
    data["teams"] = {}
    with pytest.raises(ValueError):
        solve_motion_slot(**data, slot=0)


def test_motion_uses_supplied_quaternion_even_maximum_only():
    with pytest.raises(ValueError):
        particle((2, 0, 0), rotation=(0, 1, 0))


def test_radius_is_evaluated_at_raw_depth_before_motion_curves(monkeypatch):
    import official_physics_motion as motion

    calls = []
    original_evaluator = motion.evaluate_curve

    def observe(samples, time):
        calls.append((samples, time))
        return original_evaluator(samples, time)

    monkeypatch.setattr(motion, "evaluate_curve", observe)
    config = settings(backstop=True)
    particle((0, -2, 0), config, depth=0.6)
    squared = _single(_single(0.6) * _single(0.6))
    assert calls == [
        (config.radius_curve, _single(0.6)),
        (config.motion.max_distance_curve, squared),
        (config.motion.backstop_distance_curve, squared),
    ]


def test_backstop_epsilon_is_1e8_not_clamp_1e9():
    epsilon = _single(1e-8)
    config = settings(maximum=False, backstop=True)
    # Along X, with exact sphere center at y=-1, to avoid cancellation in len.
    result = particle((epsilon, -1, 0), config)
    assert result.next_position == (epsilon, -1, 0)
    assert not result.backstop_applied
    above = math.nextafter(epsilon, math.inf)
    result = particle((above, -1, 0), config)
    assert result.next_position == (1, -1, 0) and result.backstop_applied


def test_start_motion_end_next_start_feedback_remains_distinct_from_position():
    from official_physics_particle_step import (
        EndStepSettings,
        ParticleEndState,
        finish_particle_step,
    )
    from official_physics_start_step import (
        ParticleStartState,
        ResolvedStartCenter,
        StartStepSettings,
        start_particle_step,
    )

    state = ParticleStartState(
        (0, 2, 0), (0, 1, 0), IDENTITY, (0, 1, 0), IDENTITY, ZERO, 1
    )
    start_settings = StartStepSettings(
        1, 1, 0.5, curve(0), 1, 1, 1, 0, (0, -1, 0), 1, ZERO, 0
    )
    center = ResolvedStartCenter(ZERO, ZERO, IDENTITY, ZERO, IDENTITY)
    started = start_particle_step(
        state, start_settings, attribute=2, center=center, wind=ZERO
    )
    constrained = motion_particle(
        started.next_position, started.velocity_position, ZERO, IDENTITY, 1, settings()
    )
    assert constrained.next_position == (0, 1, 0)
    assert constrained.velocity_position == (0, 2 - _single(0.95), 0)
    ended = finish_particle_step(
        ParticleEndState(
            constrained.next_position,
            state.old_position,
            constrained.velocity_position,
            ZERO,
            0,
            0,
            ZERO,
            1,
        ),
        EndStepSettings(0.5, 1, 1, -1, 0, 0, 0),
        attribute=2,
    )
    assert ended.old_position == (0, 1, 0)
    expected_velocity = _single((1 - (2 - _single(0.95))) / 0.5)
    assert ended.velocity == (0, expected_velocity, 0)
    following = start_particle_step(
        replace(state, old_position=ended.old_position, velocity=ended.velocity),
        start_settings,
        attribute=2,
        center=center,
        wind=ZERO,
    )
    assert following.velocity_position == (0, 1, 0)
    assert following.next_position == (0, 1 + _single(expected_velocity * 0.5), 0)
