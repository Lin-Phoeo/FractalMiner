"""Finite tail/clock source-flow fixtures, not native or Unity runtime oracles."""

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
    TeamDynamicsState,
    TeamStepSettings,
    TeamWindState,
    WindInfo,
    WindStepSettings,
    advance_wind_state,
    advance_wind_time,
    complete_team_step,
)

Q, Z, U = (0.0, 0.0, 0.0, 1.0), (0.0, 0.0, 0.0), (1.0, 1.0, 1.0)


def dynamics(**kw):
    return replace(TeamDynamicsState(U, U, 0, 1, 9, 9, 9, 9), **kw)


def settings(**kw):
    return replace(TeamStepSettings(4, (0, -1, 0), 0.75, 1, 1), **kw)


def wind_settings(**kw):
    return replace(WindStepSettings(1, 1, 0.5), **kw)


def wind(**kw):
    return replace(
        TeamWindState((WindInfo(7, 1, 3, (0, 1, 0)),), WindInfo(-1, 5, 9, (1, 0, 0))),
        **kw,
    )


def center_step(**kw):
    state = CenterStepState(Z, Q, (4, 0, 0), Q, (2, 2, 2), (2, 2, 2), Z, Q)
    team = CenterStepTeam(2, 2, 1, 0, 0, 0)
    return advance_center_step(
        replace(state, **kw),
        team,
        LocalInertiaSettings(0.5, -1, -1),
        team_id=1,
        update_index=0,
        delta_time=0.5,
    )


def run(
    step=None,
    dyn=None,
    cfg=None,
    w=None,
    wcfg=None,
    frame=None,
    dt=0.5,
    gravity_local=(0, -1, 0),
):
    return complete_team_step(
        step or center_step(),
        dyn or dynamics(),
        cfg or settings(),
        init_local_gravity_direction=gravity_local,
        wind=w or wind(),
        wind_settings=wcfg or wind_settings(),
        frame_wind=frame,
        delta_time=dt,
    )


def test_scale_gravity_weight_fields_and_explicit_unported_boundaries():
    original = dynamics()
    result = run(dyn=original, frame=FrameWindState(8, (0, 0, 1)))
    d = result.dynamics
    assert d.scale_ratio == 2 and d.gravity_dot == 1 and d.gravity_ratio == 0.25
    assert d.velocity_weight == d.blend_weight == 0.5
    assert original.scale_ratio == 9 and original.velocity_weight == 0
    assert result.wind.moving.main == 2 and result.wind.moving.direction == (0, 0, -1)
    assert result.writes == ("team_dynamics_fragment", "team_wind_state")
    assert result.pending_tail == ("native_publication",)
    assert result.pending_pipeline == (
        "frame_center_and_zone_selection",
        "particle_wind_force",
        "constraints_reset_and_publication",
    )
    assert (
        result.step is not None and result.step.pending_tail
    )  # Original fragment immutable.


def test_inactive_step_does_not_consume_tail_inputs():
    step = replace(center_step(), center=None, pending_tail=())
    d, w = dynamics(init_scale=(float("nan"), 1, 1)), wind()
    result = run(step=step, dyn=d, w=w, dt=float("nan"))
    assert result.dynamics is d and result.wind is w and result.writes == ()
    assert result.pending_tail == () and result.pending_pipeline == ()


@pytest.mark.parametrize("scale", [Z, (1e-10, 1e-10, 1e-10)])
def test_scale_ratio_floor_without_changing_generated_scale(scale):
    result = run(
        center_step(old_frame_world_scale=scale, frame_world_scale=scale),
        wcfg=wind_settings(influence=0),
    )
    assert result.dynamics.scale_ratio == _single(1e-6)
    assert result.step.center.world_scale == tuple(_single(x) for x in scale)


def test_scale_ratio_is_vector_length_ratio_not_one_axis_or_average():
    result = run(
        center_step(old_frame_world_scale=(3, 4, 0), frame_world_scale=(3, 4, 0)),
        dyn=dynamics(init_scale=(0, 0, 2)),
        wcfg=wind_settings(influence=0),
    )
    assert result.dynamics.scale_ratio == 2.5


@pytest.mark.parametrize(
    "local,expected", [((0, -1, 0), 1), ((0, 1, 0), 0), ((1, 0, 0), 0.5)]
)
def test_gravity_orientation_dot(local, expected):
    result = run(gravity_local=local, wcfg=wind_settings(influence=0))
    assert result.dynamics.gravity_dot == expected
    assert result.dynamics.gravity_ratio == _single(0.25 + (1 - expected) * 0.75)


def test_gravity_mirrors_only_local_y_before_rotation():
    result = run(
        dyn=dynamics(negative_scale_direction=(-1, -1, -1)),
        gravity_local=(1, -1, 0),
        cfg=settings(world_gravity_direction=(1, -1, 0)),
        wcfg=wind_settings(influence=0),
    )
    assert result.dynamics.gravity_dot == 0.5  # (1,+1,0) dot (1,-1,0), no x mirror.


def test_gravity_rotates_by_new_substep_rotation_without_normalizing_directions():
    result = run(
        center_step(
            old_frame_world_rotation=(0, 0, 1, 0), frame_world_rotation=(0, 0, 1, 0)
        ),
        gravity_local=(0, -2, 0),
        cfg=settings(world_gravity_direction=(0, -2, 0)),
        wcfg=wind_settings(influence=0),
    )
    assert result.dynamics.gravity_dot == 0  # Raw dot -4, mapped and clamped.


@pytest.mark.parametrize("direction", [Z, (1e-5, 0, 0)])
def test_degenerate_gravity_direction_skips_local_gravity_read(direction):
    result = run(
        cfg=settings(world_gravity_direction=direction),
        gravity_local=(float("nan"), 0, 0),
        wcfg=wind_settings(influence=0),
    )
    assert result.dynamics.gravity_dot == 1


@pytest.mark.parametrize(
    "gravity,falloff,expected",
    [(0, 0.75, 1), (-1, 0.75, 1), (4, 0, 1), (4, -1, 1), (4, 2, 0)],
)
def test_gravity_ratio_source_enable_thresholds(gravity, falloff, expected):
    result = run(
        cfg=settings(gravity=gravity, gravity_falloff=falloff),
        wcfg=wind_settings(influence=0),
    )
    assert result.dynamics.gravity_ratio == expected


@pytest.mark.parametrize(
    "weight,reset_time,expected",
    [
        (0, 1, 0.5),
        (0.8, 1, 1),
        (0, 0, 1),
        (0, -1, 1),
        (1, float("nan"), 1),
        (1.2, float("nan"), _single(1.2)),
        (-1, 1, 0),
    ],
)
def test_velocity_stabilization_only_updates_below_one(weight, reset_time, expected):
    result = run(
        dyn=dynamics(velocity_weight=weight),
        cfg=settings(stabilization_time_after_reset=reset_time),
        wcfg=wind_settings(influence=0),
    )
    assert result.dynamics.velocity_weight == expected


@pytest.mark.parametrize(
    "blend,distance,expected", [(0.5, 0.25, 0.0625), (10, 1, 1), (-1, 1, 0), (1, 0, 0)]
)
def test_blend_weight_uses_parameter_velocity_distance_not_lod(
    blend, distance, expected
):
    result = run(
        dyn=dynamics(distance_weight=distance),
        cfg=settings(blend_weight=blend),
        wcfg=wind_settings(influence=0),
    )
    assert result.dynamics.blend_weight == expected


@pytest.mark.parametrize(
    "main,frequency,expected",
    [
        (0, 1, _single(0.2)),
        (7.5, 1, _single(0.7)),
        (100, 1, 1.5),
        (0, 100, 1.5),
        (-3, 1, 0),
        (0, -1, _single(-0.2)),
    ],
)
def test_wind_time_rate_is_capped_above_not_floored(main, frequency, expected):
    info = WindInfo(9, 0, main, (0, 1, 0))
    result = advance_wind_time(info, frequency=frequency, delta_time=1)
    assert result.time == expected
    assert (
        result.main == main
        and result.direction == info.direction
        and result.wind_id == 9
    )


@pytest.mark.parametrize(
    "old,dt,expected",
    [
        (10000, 1, -9998.5),
        (9998.5, 1, 10000),
        (50000, 1, 30001.5),
        (-20000, 1, -19998.5),
    ],
)
def test_wind_time_one_subtraction_not_modulo_and_no_negative_wrap(old, dt, expected):
    result = advance_wind_time(WindInfo(1, old, 100, Z), frequency=1, delta_time=dt)
    assert result.time == expected


@pytest.mark.parametrize("influence", [0, -1, 1e-8])
def test_disabled_wind_leaves_previous_whole_state_untouched(influence):
    original = wind()
    result = advance_wind_state(
        original,
        wind_settings(influence=influence),
        frame=None,
        scale_ratio=float("nan"),
        delta_time=float("nan"),
    )
    assert result.state is original and result.writes == ()


def test_zone_clocks_advance_even_zero_main_negative_id_and_preserve_order():
    original = wind(zones=(WindInfo(-1, 0, 0, Z), WindInfo(8, 2, 7.5, (1, 0, 0))))
    result = advance_wind_state(
        original,
        wind_settings(moving_wind=0),
        frame=None,
        scale_ratio=float("nan"),
        delta_time=1,
    )
    assert [z.time for z in result.state.zones] == [
        pytest.approx(0.2),
        pytest.approx(2.7),
    ]
    assert [z.wind_id for z in result.state.zones] == [-1, 8]
    assert result.state.moving.main == 0
    assert result.state.moving.time == 5 and result.state.moving.direction == (1, 0, 0)
    assert result.writes == ("team_wind_state",)


@pytest.mark.parametrize("moving", [0, -1, _single(0.01)])
def test_moving_wind_threshold_clears_only_main_not_clock_direction(moving):
    result = advance_wind_state(
        wind(),
        wind_settings(moving_wind=moving),
        frame=None,
        scale_ratio=float("nan"),
        delta_time=1,
    )
    assert result.state.moving == WindInfo(-1, 5, 0, (1, 0, 0))


def test_moving_wind_uses_frame_speed_opposite_frame_direction_and_scale():
    result = advance_wind_state(
        wind(zones=()),
        wind_settings(),
        frame=FrameWindState(8, (1, 2, 3)),
        scale_ratio=2,
        delta_time=0.5,
    )
    assert result.state.moving.wind_id == -1
    assert result.state.moving.main == 2 and result.state.moving.direction == (
        -1,
        -2,
        -3,
    )
    assert result.state.moving.time == _single(
        5 + _single(_single(_single(_single(2 / 7.5) * 0.5) + _single(0.2)) * 0.5)
    )


def test_tail_requires_real_frame_wind_instead_of_guessed_step_direction():
    with pytest.raises(ValueError, match="frame wind"):
        run()


def test_two_step_generated_weights_and_scale_feed_start_end():
    s = CenterStepState(Z, Q, (4, 0, 0), Q, (2, 2, 2), (2, 2, 2), Z, Q)
    t = CenterStepTeam(2, 2, 1, 0, 0, 0)
    d, w = dynamics(), wind()
    p = ParticleStartState((1, 0, 0), Z, Q, Z, Q, Z, 0)
    for index in range(2):
        step = advance_center_step(
            s,
            t,
            LocalInertiaSettings(0.5, -1, -1),
            team_id=1,
            update_index=index,
            delta_time=0.5,
        )
        tail = run(step, d, w=w, wcfg=wind_settings(influence=0))
        d, w = tail.dynamics, tail.wind
        c = step.center
        begin = start_particle_step(
            p,
            StartStepSettings(
                step.team.frame_interpolation,
                1,
                0.5,
                (0,) * 16,
                1,
                d.velocity_weight,
                d.scale_ratio,
                4,
                (0, -1, 0),
                d.gravity_ratio,
                Z,
                0,
            ),
            attribute=2,
            center=c.for_start(),
            wind=Z,
        )
        end = finish_particle_step(
            ParticleEndState(
                begin.next_position,
                p.old_position,
                begin.velocity_position,
                p.velocity,
                0,
                0,
                Z,
                0,
            ),
            EndStepSettings(0.5, d.scale_ratio, d.velocity_weight, -1, 0, 0, 0),
            attribute=2,
            center=c.for_end(),
        )
        p = replace(p, old_position=end.old_position, velocity=end.velocity)
        s, t = step.next_state, step.team
    assert p.old_position == (5, -1.25, 0) and p.velocity == (0, -1.5, 0)
    assert d.velocity_weight == d.blend_weight == 1
    assert tail.pending_tail == ("native_publication",)


@pytest.mark.parametrize(
    "changes",
    [
        {"init_scale": Z},
        {"init_scale": (math.inf, 1, 1)},
        {"distance_weight": math.nan},
    ],
)
def test_invalid_dynamics_adapter_refuses_instead_of_native_fault_contract(changes):
    with pytest.raises(ValueError):
        run(dyn=dynamics(**changes), wcfg=wind_settings(influence=0))


@pytest.mark.parametrize("dt", [0, -1, math.nan])
def test_invalid_selected_dt(dt):
    with pytest.raises(ValueError):
        run(wcfg=wind_settings(influence=0), dt=dt)


@pytest.mark.parametrize("scale", [0, -1, math.nan])
def test_invalid_selected_moving_wind_scale(scale):
    with pytest.raises(ValueError):
        advance_wind_state(
            wind(),
            wind_settings(),
            frame=FrameWindState(1, Z),
            scale_ratio=scale,
            delta_time=1,
        )


def test_invalid_selected_wind_frequency():
    with pytest.raises(ValueError):
        advance_wind_time(WindInfo(1, 0, 1, Z), frequency=math.nan, delta_time=1)
