"""Finite particle reset tests; not live Unity/native/Burst acceptance."""

import math
import sys
from dataclasses import fields, replace
from pathlib import Path
from typing import Any, cast

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from official_physics_angle_cache import multiply_quaternions, rotate_single
from official_physics_center_step import (
    CenterStepState,
    CenterStepTeam,
    LocalInertiaSettings,
    advance_center_step,
)
from official_physics_constraints import Vector3, _single
from official_physics_frame_anchor import AnchorState
from official_physics_frame_history import FrameHistoryState, prepare_frame_history
from official_physics_frame_inertia import (
    FrameInertiaState,
    FrameInertiaTeam,
    shift_world_position,
)
from official_physics_frame_prelude import FramePreludeSettings
from official_physics_frame_target import (
    ComponentFrameSample,
    FrameTargetBuffers,
    FrameTargetTeam,
    produce_frame_target,
    resolve_frame_target,
)
from official_physics_matrix import build_double_trs, transform_double_point
from official_physics_particle_reset import (
    ParticleFrameState,
    ParticleResetTeam,
    ResolvedParticleFrameCenter,
    prepare_particle_frame,
    prepare_particle_frames,
    transform_particle_rotation,
)
from official_physics_particle_step import (
    EndStepSettings,
    ParticleEndState,
    finish_particle_step,
)
from official_physics_particle_wind import WindForceSettings, particle_wind
from official_physics_proxy_baseline import rotation_from_normal_tangent
from official_physics_scale_remap import ComponentScaleCache, transform_double_vector
from official_physics_start_step import (
    ParticleStartState,
    StartStepSettings,
    start_particle_step,
)
from official_physics_team_tail import TeamWindState, WindInfo
from official_physics_wind_zones import WindZoneData, select_wind_zones

Z = (0.0, 0.0, 0.0)
Q = (0.0, 0.0, 0.0, 1.0)
P = (1e12 + 0.125, -2e12 + 0.25, 3e12 - 0.5)
WRITES = (
    "next_position",
    "old_position",
    "old_rotation",
    "base_position",
    "base_rotation",
    "old_animation_position",
    "old_animation_rotation",
    "velocity_position",
    "display_position",
    "velocity",
    "real_velocity",
    "friction",
    "static_friction",
    "collision_normal",
)
I = ((1, 0, 0, 0), (0, 1, 0, 0), (0, 0, 1, 0), (0, 0, 0, 1))
HISTORY_WRITES = (
    "old_position",
    "old_rotation",
    "old_animation_position",
    "old_animation_rotation",
    "display_position",
    "velocity",
    "real_velocity",
)


def dirty_state():
    return ParticleFrameState(
        (1, 2, 3),
        (4, 5, 6),
        (0, 1, 0, 2),
        (7, 8, 9),
        (1, 0, 0, 3),
        (10, 11, 12),
        (0, 0, 1, 4),
        (13, 14, 15),
        (16, 17, 18),
        (19, 20, 21),
        (22, 23, 24),
        0.75,
        0.5,
        (25, 26, 27),
    )


def run(state=None, team=None, **kw: Any):
    args: dict[str, Any] = {
        "team_id": 1,
        "particle_index": 7,
        "proxy_positions": (P,),
        "proxy_rotations": (Q,),
    }
    args.update(kw)
    return prepare_particle_frame(
        dirty_state() if state is None else state,
        ParticleResetTeam(6, 7, 0) if team is None else team,
        **args,
    )


@pytest.mark.parametrize("flag", [6, 0x406, 0x40006, 0x40406, 0x2006, 0x26])
def test_reset_copies_six_double_positions_three_single_rotations_clears_five_caches(
    flag,
):
    original = dirty_state()
    result = run(original, ParticleResetTeam(flag, 7, 0))
    for name in (
        "next_position",
        "old_position",
        "base_position",
        "old_animation_position",
        "velocity_position",
        "display_position",
    ):
        assert getattr(result.state, name) == P
    for name in ("old_rotation", "base_rotation", "old_animation_rotation"):
        assert getattr(result.state, name) == Q
    assert (
        result.state.velocity
        == result.state.real_velocity
        == result.state.collision_normal
        == Z
    )
    assert result.state.friction == result.state.static_friction == 0
    assert result.writes == WRITES and result.reset_applied
    assert result.proxy_index == 0
    assert original == dirty_state()


def test_reset_does_not_normalize_rotation_or_narrow_double_position():
    result = run(proxy_rotations=((1 / 3, 0, 0, 2),))
    assert result.state.old_animation_rotation == (0.3333333432674408, 0, 0, 2)
    assert result.state.old_position == P


def test_reset_does_not_read_overwritten_dirty_history_values():
    changes: dict[str, Any] = {
        f.name: (
            math.nan
            if f.name in ("friction", "static_friction")
            else (math.nan,) * (4 if "rotation" in f.name else 3)
        )
        for f in fields(ParticleFrameState)
    }
    bad = replace(dirty_state(), **changes)
    assert run(bad).state == run().state


@pytest.mark.parametrize("flag", [0, 1, 4, 0x16, 0x806, 0x80006, (1 << 61) | 6])
def test_inactive_process_preserves_whole_history_and_does_not_read_proxy_or_chunk(
    flag,
):
    original = dirty_state()
    result = run(
        original,
        ParticleResetTeam(flag, -99, -99),
        proxy_positions=(),
        proxy_rotations=(),
    )
    assert result.state is original and result.writes == ()
    assert result.proxy_index is None and not result.reset_applied


def test_team_zero_skips_even_bad_unselected_flag_and_index():
    original = dirty_state()
    result = run(
        original,
        ParticleResetTeam(True, -99, -99),
        team_id=0,
        particle_index=-1,
        proxy_positions=(),
        proxy_rotations=(),
    )
    assert result.state is original and result.writes == ()


@pytest.mark.parametrize("flag", [2, 0x22, 0x82, 0x10002, 0x2002, 0x20002, 0x202])
def test_active_no_reset_no_history_flags_preserves_inputs_without_proxy_read(flag):
    original = dirty_state()
    result = run(
        original, ParticleResetTeam(flag, 7, 0), proxy_positions=(), proxy_rotations=()
    )
    assert result.state is original and result.writes == ()
    assert result.proxy_index is None and not result.reset_applied


@pytest.mark.parametrize(
    "particle,particle_start,proxy_start,expected",
    [(7, 7, 0, 0), (4, 3, 6, 7), (1, 7, 9, 3)],
)
def test_global_particle_to_proxy_index_uses_chunk_start_difference(
    particle, particle_start, proxy_start, expected
):
    result = run(
        team=ParticleResetTeam(6, particle_start, proxy_start),
        particle_index=particle,
        proxy_positions=tuple((i, i + 0.5, i + 1) for i in range(10)),
        proxy_rotations=(Q,) * 10,
    )
    assert result.proxy_index == expected
    assert result.state.old_position == (expected, expected + 0.5, expected + 1)


@pytest.mark.parametrize("team_id", [True, -1, 32768, 1.5])
def test_adapter_refuses_team_id_outside_nonnegative_int16_domain(team_id):
    with pytest.raises(ValueError):
        run(team_id=team_id)


@pytest.mark.parametrize("flag", [True, -1, 2**64, 1.5])
def test_adapter_consumed_flag_is_uint64(flag):
    with pytest.raises(ValueError):
        run(team=ParticleResetTeam(flag, 7, 0))


@pytest.mark.parametrize(
    "kw",
    [
        {"particle_index": -1},
        {"particle_index": True},
        {"particle_index": 2**31},
        {"team": ParticleResetTeam(6, -1, 0)},
        {"team": ParticleResetTeam(6, 7, -1)},
        {"team": ParticleResetTeam(6, 8, 0)},
        {"proxy_positions": ()},
        {"proxy_rotations": ()},
        {"proxy_positions": ((math.inf, 0, 0),)},
        {"proxy_rotations": ((0, 0, math.nan, 1),)},
        {"proxy_positions": ((1, 2),)},
        {"proxy_rotations": ((0, 0, 1),)},
    ],
)
def test_adapter_refuses_consumed_invalid_reset_inputs(kw):
    with pytest.raises(ValueError):
        run(**kw)


@pytest.mark.parametrize("flag", [0x402, 0x40002, 0x40402])
def test_nonreset_history_transform_never_silently_becomes_noop(flag):
    with pytest.raises(ValueError, match="history"):
        run(team=ParticleResetTeam(flag, 7, 0))


def center(**kw):
    return replace(ResolvedParticleFrameCenter((10, 20, 30), (3, 4, 5), Q, I), **kw)


def test_sign_history_remap_transforms_three_positions_two_rotations_two_velocities_only():
    matrix = ((-2, 0, 0, 0), (0, 3, 0, 0), (0, 0, 4, 0), (100, 200, 300, 1))
    source = replace(dirty_state(), old_rotation=Q, old_animation_rotation=Q)
    result = run(
        source,
        ParticleResetTeam(0x40002, 7, 0),
        center=center(negative_scale_matrix=matrix),
        proxy_positions=(),
        proxy_rotations=(),
    )
    assert not result.reset_applied and result.proxy_index is None
    for name in ("old_position", "old_animation_position", "display_position"):
        assert getattr(result.state, name) == transform_double_point(
            matrix, getattr(source, name)
        )
    for name in ("old_rotation", "old_animation_rotation"):
        assert getattr(result.state, name) == Q
    for name in ("velocity", "real_velocity"):
        assert getattr(result.state, name) == tuple(
            _single(v) for v in transform_double_vector(matrix, getattr(source, name))
        )
    for f in fields(source):
        if f.name not in HISTORY_WRITES:
            assert getattr(result.state, f.name) == getattr(source, f.name)
    assert result.writes == HISTORY_WRITES


def test_inertia_shift_uses_old_component_pivot_and_left_rotation_not_proxy_or_now_center():
    source = dirty_state()
    shift_q = (0, 0, 1, 0)
    c = center(frame_component_shift_rotation=shift_q, negative_scale_matrix=())
    result = run(
        source,
        ParticleResetTeam(0x402, 7, 0),
        center=c,
        proxy_positions=(),
        proxy_rotations=(),
    )
    for name in ("old_position", "old_animation_position", "display_position"):
        assert getattr(result.state, name) == shift_world_position(
            getattr(source, name),
            c.old_component_world_position,
            c.frame_component_shift_vector,
            shift_q,
        )
    for name in ("old_rotation", "old_animation_rotation"):
        assert getattr(result.state, name) == multiply_quaternions(
            shift_q, getattr(source, name)
        )
    for name in ("velocity", "real_velocity"):
        assert getattr(result.state, name) == rotate_single(
            shift_q, getattr(source, name)
        )
    assert result.state.old_position == (19, 39, 11)
    assert result.writes == HISTORY_WRITES


def test_combined_sign_and_inertia_history_transforms_are_ordered_not_commutative():
    source = replace(dirty_state(), old_rotation=Q, old_animation_rotation=Q)
    matrix = ((-2, 0, 0, 0), (0, 3, 0, 0), (0, 0, 4, 0), (100, 200, 300, 1))
    c = center(
        negative_scale_matrix=matrix, frame_component_shift_rotation=(0, 0, 1, 0)
    )
    both = run(source, ParticleResetTeam(0x40402, 7, 0), center=c)
    sign = run(source, ParticleResetTeam(0x40002, 7, 0), center=c)
    expected = run(sign.state, ParticleResetTeam(0x402, 7, 0), center=c)
    reverse_first = run(source, ParticleResetTeam(0x402, 7, 0), center=c)
    reverse = run(reverse_first.state, ParticleResetTeam(0x40002, 7, 0), center=c)
    assert both.state == expected.state and both.state != reverse.state
    assert both.writes == HISTORY_WRITES


def test_reset_priority_does_not_read_even_invalid_history_center():
    assert run(
        team=ParticleResetTeam(0x40406, 7, 0),
        center=center(
            negative_scale_matrix=(), frame_component_shift_rotation=(math.nan,) * 4
        ),
    ).reset_applied


def test_sign_branch_does_not_read_inertia_shift_inputs():
    source = replace(dirty_state(), old_rotation=Q, old_animation_rotation=Q)
    c = center(
        old_component_world_position=(math.nan,) * 3,
        frame_component_shift_vector=(math.nan,) * 3,
        frame_component_shift_rotation=(math.nan,) * 4,
    )
    assert (
        run(source, ParticleResetTeam(0x40002, 7, 0), center=c).writes == HISTORY_WRITES
    )


@pytest.mark.parametrize("q", [Q, (0, 0, 1, 0), (0.1, 0.2, 0.3, 0.9), (0, 0, 0, 2)])
def test_matrix_rotation_uses_single_y_z_axes_before_double_matrix_then_reconstructs(q):
    matrix = build_double_trs(
        (1e15, -1e15, 2e15), (0.2, 0.3, 0.1, 0.9), (-1.5, 2.25, 0.75)
    )
    y = cast(
        Vector3,
        tuple(
            _single(v)
            for v in transform_double_vector(matrix, rotate_single(q, (0, 1, 0)))
        ),
    )
    z = cast(
        Vector3,
        tuple(
            _single(v)
            for v in transform_double_vector(matrix, rotate_single(q, (0, 0, 1)))
        ),
    )
    assert transform_particle_rotation(q, matrix) == rotation_from_normal_tangent(y, z)
    assert transform_particle_rotation(Q, I) == Q


def test_identity_sign_matrix_reconstructs_raw_nonunit_rotation_not_copy():
    q = (0.1, 0.2, 0.3, 2)
    assert transform_particle_rotation(q, I) != q


@pytest.mark.parametrize(
    "changes",
    [
        {"old_position": (math.inf,) * 3},
        {"old_rotation": (math.nan,) * 4},
        {"velocity": (math.nan,) * 3},
    ],
)
def test_consumed_history_inputs_are_finite(changes):
    with pytest.raises(ValueError):
        run(
            replace(dirty_state(), **changes),
            ParticleResetTeam(0x402, 7, 0),
            center=center(),
        )


def test_bulk_history_branch_consumes_only_corresponding_center_slot():
    result = prepare_particle_frames(
        (dirty_state(), dirty_state()),
        (0, 1),
        {1: ParticleResetTeam(0x402, 1, 0)},
        proxy_positions=(),
        proxy_rotations=(),
        index_count=2,
        centers={1: center()},
    )
    assert result[0].state == dirty_state() and result[1].writes == HISTORY_WRITES


def test_bulk_missing_center_rejected_on_consumed_history_branch():
    with pytest.raises(ValueError, match="history"):
        prepare_particle_frames(
            (dirty_state(),),
            (1,),
            {1: ParticleResetTeam(0x402, 0, 0)},
            proxy_positions=(),
            proxy_rotations=(),
            index_count=1,
            centers={},
        )


def test_range_uses_global_slots_and_distinct_team_chunk_starts():
    states = (dirty_state(),) * 5
    result = prepare_particle_frames(
        states,
        (0, 1, 1, 2, 2),
        {1: ParticleResetTeam(6, 1, 4), 2: ParticleResetTeam(6, 3, 0)},
        proxy_positions=tuple((i, 0, 0) for i in range(6)),
        proxy_rotations=(Q,) * 6,
        index_count=4,
    )
    assert len(result) == 4 and result[0].state is states[0]
    assert tuple(r.proxy_index for r in result) == (None, 4, 5, 0)
    assert tuple(r.state.old_position for r in result[1:]) == (
        (4, 0, 0),
        (5, 0, 0),
        (0, 0, 0),
    )
    assert states[4] == dirty_state()


@pytest.mark.parametrize("count", [-(2**31), -1, 0])
def test_nonpositive_range_count_does_not_read_any_arrays(count):
    assert (
        prepare_particle_frames(
            (), (), {}, proxy_positions=(), proxy_rotations=(), index_count=count
        )
        == ()
    )


@pytest.mark.parametrize("count", [True, 1.5, 2**31, -(2**31) - 1])
def test_range_count_requires_int32(count):
    with pytest.raises(ValueError):
        prepare_particle_frames(
            (), (), {}, proxy_positions=(), proxy_rotations=(), index_count=count
        )


@pytest.mark.parametrize(
    "states,ids,teams",
    [((), (0,), {}), ((dirty_state(),), (), {}), ((dirty_state(),), (1,), {})],
)
def test_range_missing_declared_state_team_mapping_is_rejected(states, ids, teams):
    with pytest.raises(ValueError):
        prepare_particle_frames(
            states, ids, teams, proxy_positions=(), proxy_rotations=(), index_count=1
        )


def test_range_failure_never_mutates_prior_particle_values():
    states = (dirty_state(), dirty_state())
    with pytest.raises(ValueError):
        prepare_particle_frames(
            states,
            (1, 1),
            {1: ParticleResetTeam(6, 0, 0)},
            proxy_positions=(P,),
            proxy_rotations=(Q,),
            index_count=2,
        )
    assert states == (dirty_state(), dirty_state())


def test_reset_generated_frame_center_wind_start_end_two_substeps_and_seek_restart():
    """Source-bound value fragments in order, not native scheduling/publication."""
    S = (1, 1, 1)
    positions = ((9, 0, 0), (11, 0, 0))
    target = produce_frame_target(
        ComponentFrameSample((999, 999, 999), Q, S),
        FrameTargetTeam(0, 2, 0, 1, S),
        FrameTargetBuffers((0, 1), positions, (Q, Q), (Q, Q)),
    )
    assert target.position == (10, 0, 0) and target.rotation == Q
    prior = CenterStepState((-100, -200, -300), Q, Z, Q, S, S, (-100, -200, -300), Q)
    step = resolve_frame_target(prior, target)
    history = FrameHistoryState(
        FrameInertiaState(target.position, Q, Z, Q, Z, Z, Q, Z, step, Z),
        ComponentScaleCache(Q, S, S),
        AnchorState(Z, Q, Z, Q, Z),
        (-100, -200, -300),
        Q,
    )
    frame = prepare_frame_history(
        history,
        FrameInertiaTeam(6, 1, 1, 2, 1, 0.5),
        FramePreludeSettings(0, -1, 1, 0, 999, 180),
        component_world_scale=S,
    )
    assert frame.history.old_world_position == target.position
    reset = run(proxy_positions=positions, proxy_rotations=(Q, Q)).state
    assert reset.old_position == reset.old_animation_position == (9, 0, 0)
    zone = WindZoneData(3, 0, S, 2, 0, 1, (1, 0, 0), Z, I, (1,) * 16)
    wind_state = select_wind_zones(
        TeamWindState((), WindInfo(-1, 0, 0, Z)),
        (zone,),
        wind_count=1,
        influence=1,
        frame_world_position=target.position,
    ).state
    wind = particle_wind(
        wind_state,
        WindForceSettings(1, 0, 0, 0, 0, 0),
        team_id=1,
        root_index=0,
        depth=0,
        friction=reset.friction,
        zone_turbulence={0: 0},
    ).force
    assert wind == pytest.approx((2, 0, 0), abs=3e-7)
    team = CenterStepTeam(6, 2, 1, 0, 0, 0)
    step = frame.history.inertia.step_state
    results = []
    for index in range(2):
        generated = advance_center_step(
            step,
            team,
            LocalInertiaSettings(1, -1, -1),
            team_id=1,
            update_index=index,
            delta_time=0.5,
        )
        assert generated.center is not None
        assert generated.center.step_vector == Z
        start = start_particle_step(
            ParticleStartState(
                reset.old_position,
                reset.old_animation_position,
                reset.old_animation_rotation,
                positions[0],
                Q,
                reset.velocity,
                0,
            ),
            StartStepSettings(
                generated.team.frame_interpolation,
                1,
                0.5,
                (0,) * 16,
                1,
                1,
                1,
                2,
                (0, -1, 0),
                1,
                Z,
                0,
            ),
            attribute=2,
            center=generated.center.for_start(),
            wind=wind,
        )
        end = finish_particle_step(
            ParticleEndState(
                start.next_position,
                reset.old_position,
                start.velocity_position,
                reset.velocity,
                reset.friction,
                reset.static_friction,
                reset.collision_normal,
                0,
            ),
            EndStepSettings(0.5, 1, 1, -1, 0, 0, 0),
            attribute=2,
            center=generated.center.for_end(),
        )
        reset = replace(
            reset,
            old_position=end.old_position,
            velocity=end.velocity,
            real_velocity=end.real_velocity,
            friction=end.friction,
            static_friction=end.static_friction,
        )
        assert (
            reset.old_animation_position == positions[0]
        )  # End must not publish animation history.
        results.append(end)
        step, team = generated.next_state, generated.team
    assert results[0].old_position == pytest.approx((9.5, -0.5, 0), abs=3e-7)
    assert results[1].old_position == pytest.approx((10.5, -1.5, 0), abs=3e-7)
    assert reset.velocity == pytest.approx((2, -2, 0), abs=3e-7)
    # Seek/restart reinitializes from NEW proxy pose, not previous simulated history.
    restarted = run(reset, proxy_positions=((42, 43, 44),), proxy_rotations=(Q,)).state
    assert restarted.old_position == restarted.old_animation_position == (42, 43, 44)
    assert (
        restarted.velocity == restarted.real_velocity == restarted.collision_normal == Z
    )
