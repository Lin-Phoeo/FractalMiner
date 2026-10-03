"""Finite static-source wind tests; managed math reference is not a game oracle."""

import math
import struct
import sys
from dataclasses import replace
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from official_physics_angle_cache import rotate_single
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
from official_physics_particle_wind import (
    WindForceSettings,
    axis_quaternion,
    classic_noise2,
    euler_zxy,
    particle_wind,
    particle_wind_seed,
    wind_force_blend,
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
    complete_team_step,
)

Z = (0.0, 0.0, 0.0)
Q = (0.0, 0.0, 0.0, 1.0)


def cfg(**kw):
    return replace(WindForceSettings(1, 0, 0, 0, 0, 0), **kw)


def info(**kw):
    return replace(WindInfo(7, 0, 3, (0, 0, 1)), **kw)


def state(**kw):
    return replace(TeamWindState((info(),), info(wind_id=-1)), **kw)


def run(w=None, settings=None, **kw):
    inputs = {
        "team_id": 1,
        "root_index": 3,
        "depth": 0.5,
        "friction": 0,
        "zone_turbulence": {7: 0},
    }
    inputs.update(kw)
    return particle_wind(w or state(), settings or cfg(), **inputs)


@pytest.mark.parametrize(
    "point,bits",
    [
        ((0, 0), "00000000"),
        ((0.25, 0.5), "bd1253e2"),
        ((-0.25, 0.5), "3e9bef4a"),
        ((1.2, -3.4), "bdb3497d"),
        ((4.1923065, 4.1923065), "3e8bc153"),
        ((100.75, -300.125), "3d1b974f"),
        ((-289.5, 289.25), "3e8d92e5"),
        ((0.001, -0.001), "baee04c0"),
        ((2.5, 7.125), "3ed6919e"),
        ((15.25, 15.25), "3f07ea87"),
        ((10000.125, -10000.375), "3ec29075"),
    ],
)
def test_classic_noise_independent_managed_mathematics_reference(point, bits):
    # Captured from unmodified project Unity.Mathematics.dll in a private .NET
    # process, never the game. No mock/provider can hide a wrong noise algorithm.
    expected = struct.unpack("<f", bytes.fromhex(bits)[::-1])[0]
    assert classic_noise2(point) == expected


def test_noise_period_and_swapped_coordinates_are_not_interchangeable():
    assert classic_noise2((0.25, 0.5)) == classic_noise2((289.25, -288.5))
    assert classic_noise2((0.25, 0.5)) != classic_noise2((0.5, 0.25))


@pytest.mark.parametrize(
    "angles,expected",
    [
        (Z, Q),
        ((0.3, -0.7, 0.2), (0.10582854, -0.35136804, 0.14371376, 0.9190687)),
        ((-1.1, 2.3, -0.9), (-0.53072554, 0.6078162, 0.27811956, 0.52109444)),
        ((0.5, 0.7, 0), (0.23240453, 0.33223793, -0.08483428, 0.9101699)),
        ((0, 1.5707964, 0), (0, 0.70710677, 0, 0.70710677)),
    ],
)
def test_euler_zxy_radians_against_managed_reference(angles, expected):
    assert euler_zxy(angles) == pytest.approx(expected, abs=1e-7)


@pytest.mark.parametrize(
    "direction", [(1, 2, 3), (-2, 0.2, 1), (0, 1, 0), (0, -1, 0), (0, 0, -2), Z]
)
def test_axis_orientation_not_lookrotation_or_unity_euler_degrees(direction):
    expected = (
        tuple(x / math.sqrt(sum(v * v for v in direction)) for x in direction)
        if direction != Z
        else (0, 0, 1)
    )
    assert rotate_single(axis_quaternion(direction), (0, 0, 1)) == pytest.approx(
        expected, abs=3e-7
    )


@pytest.mark.parametrize("main", [0, -1, _single(0.009)])
def test_blend_main_gate_skips_unread_seed_clock_settings_direction(main):
    invalid = (math.nan, math.nan, math.nan)
    assert (
        wind_force_blend(
            info(main=main, time=math.nan, direction=invalid),
            cfg(turbulence=math.nan, blend=math.nan),
            wind_position=invalid,
            turbulence_ratio=math.nan,
        )
        == Z
    )


@pytest.mark.parametrize(
    "main,time,seed,direction,turbulence,mix,ratio,expected",
    [
        (
            3,
            1,
            (0.2, 0.7, -1),
            (1, 2, 3),
            0.8,
            0.5,
            0.7,
            (0.48125285, 2.2597601, 1.7238487),
        ),
        (
            9,
            -2,
            (2, -3, 5),
            (-2, 0.2, 1),
            1.2,
            1,
            0.4,
            (-7.8361197, 0.61697507, 4.3834414),
        ),
        (
            1,
            0.1,
            (7, 7, 7),
            (0, 1, 0),
            0.9,
            0,
            1,
            (0.011986319, 0.17111617, 0.14428781),
        ),
        (
            0.01,
            3,
            (0.3, -0.9, 0),
            (0, 0, -2),
            0.4,
            0.2,
            0.6,
            (0.00014704598, 0.0014600378, -0.00964561),
        ),
        (2, 0, Z, (0, 0, 1), 4, 0, 1, (0, 0, -0.9333334)),
    ],
)
def test_blend_source_flow_using_independent_managed_math(
    main, time, seed, direction, turbulence, mix, ratio, expected
):
    # High-level formula fixture uses real managed cnoise/Euler, not our helpers;
    # formula itself was reconstructed from the static native body, not runtime.
    actual = wind_force_blend(
        info(main=main, time=time, direction=direction),
        cfg(turbulence=turbulence, blend=mix),
        wind_position=seed,
        turbulence_ratio=ratio,
    )
    assert actual == pytest.approx(expected, abs=2e-6)


def test_seed_synchronization_one_removes_root_but_not_team():
    assert (
        particle_wind_seed(team_id=0, root_index=-1, synchronization=1)
        == (_single(4.1923065185546875),) * 3
    )
    assert particle_wind_seed(
        team_id=0, root_index=1000, synchronization=1
    ) == particle_wind_seed(team_id=0, root_index=-1, synchronization=1)
    assert particle_wind_seed(
        team_id=1, root_index=1000, synchronization=1
    ) != particle_wind_seed(team_id=0, root_index=1000, synchronization=1)


def test_seed_source_int32_team_increment_wrap_and_signed_root():
    expected = _single(_single(-2147483648) * _single(4.1923065185546875))
    assert (
        particle_wind_seed(team_id=2147483647, root_index=-1, synchronization=1)
        == (expected,) * 3
    )
    assert particle_wind_seed(
        team_id=0, root_index=-1, synchronization=0
    ) != particle_wind_seed(team_id=0, root_index=1, synchronization=0)


def test_particle_resolved_zones_add_not_average_and_no_id_main_filter():
    result = run(
        state(zones=(info(main=2), info(wind_id=9, main=4))),
        zone_turbulence={7: 0, 9: 0},
    )
    assert result.force == (0, 0, 6)
    assert result.zone_forces == ((0, 0, 2), (0, 0, 4))
    assert result.moving_force is None


@pytest.mark.parametrize(
    "depth,friction,influence,weight,expected",
    [
        (0, 0, 1, 1, 0),
        (1, 0.25, 2, 1, 4.5),
        (2, 0, 1, 1, 12),
        (0, 2, 1, 0, -3),
        (0, 0, -2, 0, -6),
    ],
)
def test_depth_friction_influence_are_source_weights_not_clamped(
    depth, friction, influence, weight, expected
):
    assert run(
        settings=cfg(influence=influence, depth_weight=weight),
        depth=depth,
        friction=friction,
    ).force == (0, 0, expected)


@pytest.mark.parametrize("moving", [0, -1, _single(0.01)])
def test_moving_force_gate_skips_unread_moving_info(moving):
    invalid = WindInfo(-1, math.nan, math.nan, (math.nan,) * 3)
    assert run(state(moving=invalid), cfg(moving_wind=moving)).moving_force is None


def test_moving_force_uses_ratio_one_not_zone_table():
    result = run(
        state(zones=(), moving=info(wind_id=-123)),
        cfg(moving_wind=1),
        zone_turbulence={},
    )
    assert (
        result.zone_forces == ()
        and result.moving_force == (0, 0, 3)
        and result.force == (0, 0, 3)
    )


def test_zero_influence_does_not_skip_source_zone_resolution():
    with pytest.raises(ValueError, match="zone turbulence"):
        run(settings=cfg(influence=0), zone_turbulence={})


def test_zero_main_does_not_skip_zone_table_but_blend_skips_ratio_validation():
    assert run(state(zones=(info(main=0),)), zone_turbulence={7: math.nan}).force == Z
    with pytest.raises(ValueError, match="zone turbulence"):
        run(state(zones=(info(main=0),)), zone_turbulence={})


def test_wind_state_clock_then_particle_force_changes_with_time():
    w = state()
    settings = cfg(turbulence=0.8, blend=0.5)
    first = run(w, settings, zone_turbulence={7: 0.7})
    advanced = advance_wind_state(
        w, WindStepSettings(1, 1, 0), frame=None, scale_ratio=1, delta_time=0.5
    )
    second = run(advanced.state, settings, zone_turbulence={7: 0.7})
    assert second.force != first.force and w.zones[0].time == 0


def test_two_substeps_center_tail_real_zone_and_moving_force_feed_start_end():
    # No zero-wind placeholder: the generated force is (-1,0,2), applied in
    # both Start steps and fed back through End. It uses actual frame wind
    # speed 4, not stepVector/dt, with generated scaleRatio=2.
    s = CenterStepState(Z, Q, (4, 0, 0), Q, (2, 2, 2), (2, 2, 2), Z, Q)
    t = CenterStepTeam(2, 2, 1, 0, 0, 0)
    dynamics = TeamDynamicsState((1, 1, 1), (1, 1, 1), 0, 1, 9, 9, 9, 9)
    w = state(zones=(info(main=2),))
    p = ParticleStartState((1, 0, 0), Z, Q, Z, Q, Z, 0)
    forces = []
    for index in range(2):
        step = advance_center_step(
            s,
            t,
            LocalInertiaSettings(0.5, -1, -1),
            team_id=1,
            update_index=index,
            delta_time=0.5,
        )
        tail = complete_team_step(
            step,
            dynamics,
            TeamStepSettings(4, (0, -1, 0), 0.75, 1, 1),
            init_local_gravity_direction=(0, -1, 0),
            wind=w,
            wind_settings=WindStepSettings(1, 1, 0.5),
            frame_wind=FrameWindState(4, (1, 0, 0)),
            delta_time=0.5,
        )
        dynamics, w = tail.dynamics, tail.wind
        force = run(w, cfg(moving_wind=0.5)).force
        forces.append(force)
        begin = start_particle_step(
            p,
            StartStepSettings(
                step.team.frame_interpolation,
                1,
                0.5,
                (0,) * 16,
                1,
                dynamics.velocity_weight,
                dynamics.scale_ratio,
                4,
                (0, -1, 0),
                dynamics.gravity_ratio,
                Z,
                0,
            ),
            attribute=2,
            center=step.center.for_start(),
            wind=force,
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
            EndStepSettings(
                0.5, dynamics.scale_ratio, dynamics.velocity_weight, -1, 0, 0, 0
            ),
            attribute=2,
            center=step.center.for_end(),
        )
        p = replace(p, old_position=end.old_position, velocity=end.velocity)
        s, t = step.next_state, step.team
    for force in forces:
        assert force == pytest.approx((-1, 0, 2), abs=3e-7)
    assert p.old_position == pytest.approx((3.75, -1.25, 2.5), abs=3e-7)
    assert p.velocity == pytest.approx((-1.5, -1.5, 3), abs=3e-7)
    assert dynamics.velocity_weight == 1


@pytest.mark.parametrize("point", [(math.nan, 0), (0, math.inf), (1,), (1, 2, 3)])
def test_invalid_noise_adapter_values(point):
    with pytest.raises(ValueError):
        classic_noise2(point)


@pytest.mark.parametrize("value", [(math.nan, 0, 0), (0, math.inf, 0), (1, 2)])
def test_invalid_euler_or_axis_adapter(value):
    with pytest.raises(ValueError):
        euler_zxy(value)
    with pytest.raises(ValueError):
        axis_quaternion(value)


@pytest.mark.parametrize(
    "inputs",
    [
        {"team_id": -1},
        {"team_id": True},
        {"root_index": 2**31},
        {"root_index": 1.5},
        {"synchronization": math.nan},
    ],
)
def test_invalid_seed_adapter(inputs):
    args = {"team_id": 1, "root_index": 0, "synchronization": 0}
    args.update(inputs)
    with pytest.raises(ValueError):
        particle_wind_seed(**args)


@pytest.mark.parametrize("field", ["turbulence", "blend"])
def test_invalid_active_blend_settings(field):
    with pytest.raises(ValueError):
        wind_force_blend(
            info(), cfg(**{field: math.nan}), wind_position=Z, turbulence_ratio=1
        )


@pytest.mark.parametrize("inputs", [{"depth": math.nan}, {"friction": math.nan}])
def test_invalid_final_particle_weights(inputs):
    with pytest.raises(ValueError):
        run(**inputs)
