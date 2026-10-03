"""Source-flow synthetic center→Start→End probes; no official runtime oracle."""

import math
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
    quaternion_angle,
    quaternion_angle_axis,
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

Q = (0.0, 0.0, 0.0, 1.0)
Z = (0.0, 0.0, 0.0)


def state(**kw: Any):
    return replace(
        CenterStepState(Z, Q, (4, 0, 0), Q, (1, 1, 1), (1, 1, 1), Z, Q), **kw
    )


def team(**kw: Any):
    return replace(CenterStepTeam(2, 2, 1, 0, 0, 0), **kw)


def settings(**kw: Any):
    return replace(LocalInertiaSettings(0.5, -1, -1), **kw)


def run(s=None, t=None, cfg=None, index=0, dt=0.5, team_id=1):
    return advance_center_step(
        s or state(),
        t or team(),
        cfg or settings(),
        team_id=team_id,
        update_index=index,
        delta_time=dt,
    )


def test_center_time_interpolation_and_history_update():
    original = state()
    result = run(original)
    assert result.team.now_update_time == 0.5
    assert result.team.frame_interpolation == 0.5
    assert result.team.flag == 0x82
    assert result.center.old_world_position == Z
    assert result.center.now_world_position == (2, 0, 0)
    assert result.center.step_vector == (2, 0, 0)
    assert result.center.inertia_vector == (1, 0, 0)
    assert result.center.step_move_inertia_ratio == 0.5
    assert result.center.step_rotation_inertia_ratio == 0.5
    assert result.next_state.now_world_position == (2, 0, 0)
    assert original.now_world_position == Z
    assert result.writes == ("team_clock_fragment", "center_fragment")
    assert result.pending_tail == (
        "scale_gravity_weight_fades",
        "UpdateWind",
        "native_publication",
    )


@pytest.mark.parametrize("span", [0, -1])
def test_nonpositive_frame_time_span_uses_one(span):
    result = run(t=team(time=span))
    assert result.team.frame_interpolation == 1
    assert result.center.now_world_position == (4, 0, 0)


@pytest.mark.parametrize("now,expected", [(-2, 0), (2, 1)])
def test_interpolation_clamps_clock_ratio(now, expected):
    result = run(t=team(now_update_time=now))
    assert result.team.frame_interpolation == expected


@pytest.mark.parametrize(
    "flag", [0, 1, 2 | 0x10, 2 | 0x800, 2 | 0x80000, 2 | (1 << 61)]
)
def test_unprocessable_team_preserves_every_input(flag):
    t = team(flag=flag)
    s = state(now_world_position=(float("nan"), 0, 0))
    result = run(s, t)
    assert result.team is t and result.next_state is s
    assert result.center is None and result.writes == ()


def test_team_zero_skips_without_loading_center_or_clock():
    s = state(now_world_position=(float("nan"), 0, 0))
    t = team(flag=-1)
    result = run(s, t, team_id=0)
    assert result.center is None and result.team is t


@pytest.mark.parametrize("flag", [2 | 4, 2 | 8, 2 | 0x200, 2 | 0x40000, 2 | (1 << 60)])
def test_reset_teleport_other_flags_not_reinterpreted_as_process_gate(flag):
    result = run(t=team(flag=flag))
    assert result.center is not None and result.team.flag == flag | 0x80


def test_exhausted_update_count_only_clears_step_running():
    s, t = state(), team(flag=2 | 0x80)
    result = run(s, t, index=2, dt=float("nan"))
    assert result.team.flag == 2
    assert result.team.now_update_time == t.now_update_time
    assert result.next_state is s and result.center is None
    assert result.writes == ("team_step_flag",)


def test_frame_interpolation_is_single_before_double_position_lerp():
    n = 2**30
    result = run(
        state(
            old_frame_world_position=(n + 0.125, 0, 0),
            frame_world_position=(n + 0.625, 0, 0),
            now_world_position=(n + 0.125, 0, 0),
        )
    )
    assert result.center.now_world_position == (n + 0.375, 0, 0)
    assert result.center.step_vector == (0.25, 0, 0)


def test_center_step_delta_narrows_after_double_subtraction():
    result = run(state(frame_world_position=(2.00000002, 0, 0)))
    assert result.center.now_world_position == (1.00000001, 0, 0)
    assert result.center.step_vector == (1, 0, 0)


@pytest.mark.parametrize("local,expected", [(0, 2), (0.25, 1.5), (1, 0)])
def test_local_inertia_uses_complement_for_particle_following(local, expected):
    result = run(cfg=settings(local_inertia=local))
    assert result.center.inertia_vector == (expected, 0, 0)


@pytest.mark.parametrize(
    "limit,expected", [(-1, 0.5), (0, 1), (1, 0.75), (2, 0.5), (3, 0.5)]
)
def test_translation_limit_changes_ratio_not_center_step(limit, expected):
    result = run(cfg=settings(local_movement_speed_limit=limit))
    assert result.center.step_move_inertia_ratio == expected
    assert result.center.step_vector == (2, 0, 0)
    assert result.center.now_world_position == (2, 0, 0)
    assert result.center.inertia_vector == (2 * expected, 0, 0)


def test_rotation_increment_is_new_times_inverse_old_not_local_delta():
    a = (math.sqrt(0.5), 0, 0, math.sqrt(0.5))
    b = (0, math.sqrt(0.5), 0, math.sqrt(0.5))
    result = run(
        state(old_frame_world_rotation=a, frame_world_rotation=b, now_world_rotation=a),
        dt=1,
    )
    q = result.center.step_rotation
    assert q[0] < 0 and q[1] > 0 and q[2] > 0  # b * inverse(a), not inverse(a) * b.
    assert result.center.old_world_rotation == tuple(_single(v) for v in a)


def test_rotation_limit_degrees_and_end_angular_velocity_radians():
    result = run(
        state(frame_world_rotation=(0, 0, 1, 0)),
        cfg=settings(local_rotation_speed_limit=45),
    )
    c = result.center
    assert c.angular_velocity == pytest.approx(math.pi, abs=1e-6)
    assert c.rotation_axis == pytest.approx((0, 0, 1), abs=2e-7)
    assert c.step_rotation_inertia_ratio == pytest.approx(0.75, abs=2e-7)
    assert c.step_move_inertia_ratio == 0.5


def test_rotation_limit_zero_uses_full_step_following():
    result = run(
        state(frame_world_rotation=(0, 0, 1, 0)),
        cfg=settings(local_rotation_speed_limit=0),
    )
    assert result.center.step_rotation_inertia_ratio == 1
    assert result.center.inertia_rotation == result.center.step_rotation


def test_no_rotation_has_zero_omega_and_axis():
    result = run()
    assert result.center.angular_velocity == 0 and result.center.rotation_axis == Z
    assert result.center.step_rotation == result.center.inertia_rotation == Q


def test_angle_threshold_shortest_arc_and_nonunit_source_rule():
    assert quaternion_angle(Q, Q) == 0
    assert quaternion_angle(Q, (0, 0, 0, -1)) == 0
    assert quaternion_angle(Q, (0, 0, 0, 2)) == 0  # No input normalization.
    assert quaternion_angle(Q, (0, 0, 1, 0)) == pytest.approx(math.pi)
    assert quaternion_angle(
        Q, (0, 0, -math.sqrt(0.5), -math.sqrt(0.5))
    ) == pytest.approx(math.pi / 2, abs=5e-7)


def test_angle_axis_keeps_signed_quaternion_not_shortest_arc_repair():
    angle, axis = quaternion_angle_axis((0, 0, -math.sqrt(0.5), -math.sqrt(0.5)))
    assert angle == pytest.approx(3 * math.pi / 2, abs=1e-6)
    assert axis == pytest.approx((0, 0, -1), abs=2e-7)
    assert quaternion_angle_axis(Q) == (0, Z)
    assert quaternion_angle_axis((0, 0, 0, -1)) == (0, Z)


def test_scale_is_interpolated_but_team_scale_ratio_tail_remains_pending():
    result = run(state(old_frame_world_scale=(1, 2, 3), frame_world_scale=(3, 4, 5)))
    assert result.center.world_scale == (2, 3, 4)
    assert "scale_gravity_weight_fades" in result.pending_tail


def test_two_substep_center_generation_then_particle_feedback():
    s, t = state(), team()
    p = ParticleStartState((1, 0, 0), Z, Q, Z, Q, Z, 0)
    cfg = StartStepSettings(0, 1, 0.5, (0,) * 16, 1, 1, 1, 4, (0, -1, 0), 1, Z, 0)
    for index in range(2):
        step = run(s, t, index=index)
        c = step.center
        begin = start_particle_step(
            p,
            replace(cfg, frame_interpolation=step.team.frame_interpolation),
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
            EndStepSettings(0.5, 1, 1, -1, 0, 0, 0),
            attribute=2,
            center=c.for_end(),
        )
        p = replace(p, old_position=end.old_position, velocity=end.velocity)
        s, t = step.next_state, step.team
    assert c.now_world_position == (4, 0, 0) and c.old_world_position == (2, 0, 0)
    assert p.old_position == (5, -3, 0) and p.velocity == (0, -4, 0)
    assert end.real_velocity == (4, -4, 0)
    assert c.for_end().now_world_position == (4, 0, 0)


@pytest.mark.parametrize(
    "kwargs",
    [
        {"team_id": -1},
        {"team_id": True},
        {"index": -1},
        {"index": 2.5},
        {"dt": 0},
        {"dt": float("nan")},
    ],
)
def test_adapter_invalid_indices_and_dt(kwargs):
    with pytest.raises(ValueError):
        run(**kwargs)


@pytest.mark.parametrize(
    "field,value",
    [("flag", -1), ("flag", True), ("update_count", -1), ("time", float("inf"))],
)
def test_adapter_invalid_team(field, value):
    with pytest.raises(ValueError):
        run(t=team(**{field: value}))


@pytest.mark.parametrize("local", [-0.1, 1.1, float("nan")])
def test_adapter_local_inertia_domain_no_hidden_clamp(local):
    with pytest.raises(ValueError):
        run(cfg=settings(local_inertia=local))


@pytest.mark.parametrize(
    "changes",
    [
        {"now_world_position": (0, 0)},
        {"now_world_rotation": (0, 0, 0, 0)},
        {"frame_world_rotation": (float("nan"), 0, 0, 1)},
        {"frame_world_scale": (float("inf"), 1, 1)},
    ],
)
def test_adapter_invalid_selected_center(changes):
    with pytest.raises(ValueError):
        run(state(**changes))
