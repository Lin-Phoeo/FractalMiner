"""Packed baseline slot/range contracts; not an original runtime oracle."""

import sys
from dataclasses import replace
from pathlib import Path
from typing import Any

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from official_physics_angle_baseline import BaselineState, TeamWindow
from official_physics_angle_pass import (
    AnglePassParameters,
    AnglePassTeam,
    solve_angle_range,
    solve_angle_slot,
)

IDENTITY = (0.0, 0.0, 0.0, 1.0)
ZERO = (0.0, 0.0, 0.0)


def fixture() -> dict[str, Any]:
    basic = ((99.0, 0.0, 0.0), ZERO, (0.0, 1.0, 0.0), (0.0, 2.0, 0.0))
    points = basic[:2] + ((0.8, 0.6, 0.0), (1.3, 1.4, 0.1))
    return {
        "state": BaselineState(
            points,
            points,
            basic,
            (IDENTITY,) * 4,
            (0.0, 0.0, 0.1, 0.2),
            (IDENTITY,) * 4,
            (None,) * 4,
        ),
        "teams": {5: AnglePassTeam(TeamWindow(1, 3, 4, 3, 3, 4), 0.4)},
        "parameters": {
            5: AnglePassParameters(
                True, True, (20.0,) * 16, 0.7, (0.16,) * 16, 0.8, 0.2
            )
        },
        "packed_step_indices": (5 << 16 | 7,),
        "starts": (0,) * 7 + (1,),
        "counts": (0,) * 7 + (3,),
        "data": (65535, 65535, 65535, 65535, 0, 1, 2),
        "parents": (-999,) * 4 + (-1, 0, 1),
        "attributes": (255,) * 4 + (1, 2, 2),
        "depths": (0.0,) * 4 + (0.0, 0.5, 1.0),
        "simulation_power_w": 0.5,
    }


@pytest.mark.parametrize("route", ["managed", "job"])
def test_sparse_slot_keeps_global_baseline_and_separate_particle_proxy_windows(route):
    args = fixture()
    before = repr(args["state"])
    out = solve_angle_slot(**args, slot=0, route=route)
    assert (out.team_id, out.baseline_index, out.slot) == (5, 7, 0)
    assert out.plan is not None
    assert [v.particle_index for v in out.plan.vertices] == [1, 2, 3]
    assert [v.proxy_index for v in out.plan.vertices] == [4, 5, 6]
    assert out.plan.team_index == 5
    assert out.result is not None and len(out.result.visits) == 12
    assert out.state.next_positions[0] == args["state"].next_positions[0]
    assert out.state.next_positions[2:] != args["state"].next_positions[2:]
    assert repr(args["state"]) == before
    assert out.writes == (
        "rotations",
        "edge_caches",
        "next_positions",
        "velocity_positions",
    )


@pytest.mark.parametrize("team_id", [0, 32768, 65535])
@pytest.mark.parametrize("signed", [False, True])
def test_high16_team_is_unsigned_and_no_team_zero_filter(team_id, signed):
    args = fixture()
    team, parameters = args["teams"][5], args["parameters"][5]
    args["teams"], args["parameters"] = {team_id: team}, {team_id: parameters}
    word = team_id << 16 | 7
    args["packed_step_indices"] = (word - 2**32 if signed and word >= 2**31 else word,)
    assert solve_angle_slot(**args, slot=0).team_id == team_id


@pytest.mark.parametrize("route", ["managed", "job"])
def test_both_disabled_skip_team_and_all_baseline_state_buffers(route):
    args = fixture()
    state = BaselineState((), (), (), (), (), (), ())
    args.update(
        state=state,
        teams={},
        starts=(),
        counts=(),
        data=(),
        parents=(),
        attributes=(),
        depths=(),
    )
    args["parameters"][5] = replace(
        args["parameters"][5], use_limit=False, use_restoration=False
    )
    out = solve_angle_slot(**args, slot=0, route=route)
    assert out.state is state and out.status == "disabled"
    assert out.result is None and out.plan is None and out.writes == ()


def test_enabled_empty_baseline_preserves_state_identity():
    args = fixture()
    args["counts"] = (0,) * 8
    out = solve_angle_slot(**args, slot=0)
    assert out.status == "empty-baseline" and out.state is args["state"]
    assert out.writes == ()


def test_single_fixed_slot_copies_rotation_without_edge_cache_or_position_writes():
    args = fixture()
    args["counts"] = (0,) * 7 + (1,)
    out = solve_angle_slot(**args, slot=0)
    assert out.result is not None and out.result.visits == ()
    assert out.state.rotations[1] == args["state"].basic_rotations[1]
    assert out.state.edge_caches == args["state"].edge_caches
    assert out.state.next_positions == args["state"].next_positions
    assert out.state.velocity_positions == args["state"].velocity_positions
    assert out.writes == ("rotations",)


@pytest.mark.parametrize(
    "limit,restoration", [(True, False), (False, True), (True, True)]
)
def test_each_enabled_path_is_consumed_without_extra_curve_conversion(
    limit, restoration
):
    args = fixture()
    args["parameters"][5] = replace(
        args["parameters"][5], use_limit=limit, use_restoration=restoration
    )
    out = solve_angle_slot(**args, slot=0)
    assert out.result is not None
    assert [v.phase for v in out.result.visits] == [
        p
        for _ in range(6)
        for p in (
            ("limit",)
            if not restoration
            else ("restoration",)
            if not limit
            else ("limit", "restoration")
        )
    ]
    cache = out.state.edge_caches[2]
    assert cache is not None
    assert (cache.local_direction is not None) == limit
    assert (cache.restoration_world_vector is not None) == restoration


@pytest.mark.parametrize("attribute", [2, 3, 6, 18, 255])
def test_move_bit_alone_no_nocollision_or_fixed_bit_veto(attribute):
    args = fixture()
    args["attributes"] = (0,) * 4 + (1, attribute, attribute)
    out = solve_angle_slot(**args, slot=0)
    assert out.result is not None and out.result.visits


def test_fixed_nonroot_initializes_cache_but_never_solves():
    args = fixture()
    args["attributes"] = (0,) * 4 + (1, 1, 1)
    out = solve_angle_slot(**args, slot=0)
    assert out.result is not None and out.result.visits == ()
    assert out.state.edge_caches[2] is not None
    assert out.state.next_positions == args["state"].next_positions
    assert out.writes == ("rotations", "edge_caches")


@pytest.mark.parametrize("route", ["managed", "job"])
def test_serial_range_finishes_each_baseline_then_reinitializes_next_duplicate(route):
    args = fixture()
    args["packed_step_indices"] *= 2
    first = solve_angle_slot(**args, slot=0, route=route)
    second = solve_angle_slot(**dict(args, state=first.state), slot=1, route=route)
    result = solve_angle_range(**args, index_count=2, route=route)
    assert result.state == second.state
    assert [v.slot for v in result.visits] == [0, 1]
    assert result.state != first.state
    assert result.visits[0].result is not None
    assert result.visits[0].result.state == first.state
    assert result.visits[1].state == second.state
    first_cache, final_cache = (
        result.visits[0].state.edge_caches[3],
        result.state.edge_caches[3],
    )
    assert first_cache is not None and final_cache is not None
    assert first_cache.cached_length != final_cache.cached_length


def test_native_stored_baseline_order_is_not_sorted():
    args = fixture()
    # Move root remains0; child2 reads existing parent1 cache before child1 solves.
    args["data"] = args["data"][:4] + (0, 2, 1)
    out = solve_angle_slot(**args, slot=0)
    assert out.result is not None
    assert [v.local_index for v in out.result.visits[:4]] == [2, 2, 1, 1]
    assert out.state != solve_angle_slot(**fixture(), slot=0).state


@pytest.mark.parametrize("count", [0, -1, -2147483648])
def test_nonpositive_range_count_has_no_logical_writes(count):
    args = fixture()
    args.update(
        teams={},
        parameters={},
        packed_step_indices=(),
        starts=(),
        counts=(),
        data=(),
        parents=(),
        attributes=(),
        depths=(),
    )
    out = solve_angle_range(**args, index_count=count)
    assert out.state is args["state"] and out.visits == ()


@pytest.mark.parametrize("slot", [-1, True, 0.0, 1])
def test_invalid_slot_is_adapter_error(slot):
    with pytest.raises(ValueError):
        solve_angle_slot(**fixture(), slot=slot)


@pytest.mark.parametrize("route", ["burst", "", None, False])
def test_unknown_numeric_route_not_silently_managed(route):
    with pytest.raises(ValueError, match="route"):
        solve_angle_slot(**fixture(), slot=0, route=route)


def test_missing_selected_parameters_and_team_are_explicit_adapter_errors():
    args = fixture()
    with pytest.raises(ValueError, match="parameters"):
        solve_angle_slot(**dict(args, parameters={}), slot=0)
    with pytest.raises(ValueError, match="Team"):
        solve_angle_slot(**dict(args, teams={}), slot=0)


@pytest.mark.parametrize("flag", ["use_limit", "use_restoration"])
def test_parameter_enable_types_not_silently_truthy(flag):
    args = fixture()
    args["parameters"][5] = replace(args["parameters"][5], **{flag: 1})
    with pytest.raises(ValueError, match="bool"):
        solve_angle_slot(**args, slot=0)


def test_failure_in_second_baseline_does_not_publish_first_partial_result():
    args = fixture()
    original = repr(args["state"])
    args["packed_step_indices"] *= 2
    with pytest.raises(ValueError):
        solve_angle_range(**args, index_count=3)
    assert repr(args["state"]) == original


def test_job_numeric_route_is_distinct_not_managed_alias():
    args = fixture()
    args["parameters"][5] = replace(
        args["parameters"][5], use_limit=False, restoration_curve=(0.0,) * 16
    )
    args["state"] = replace(
        args["state"],
        next_positions=args["state"].next_positions[:2]
        + ((1.0 + 2**-25, 2.0 + 2**-24, 0.0), (1.3, 1.4, 0.1)),
    )
    managed = solve_angle_slot(**args, slot=0, route="managed")
    job = solve_angle_slot(**args, slot=0, route="job")
    assert managed.state.next_positions != job.state.next_positions


def test_baseline_data_address_overflow_is_explicit_adapter_rejection():
    from official_physics_angle_baseline import resolve_baseline

    with pytest.raises(ValueError, match="declared range"):
        resolve_baseline(
            0, [TeamWindow(0, 0, 0, 0, 2147483647, 2)], [1], [0], [], [], [], []
        )


@pytest.mark.parametrize("route", ["managed", "job"])
def test_start_tether_angle_end_next_start_threads_velocity_reference(route):
    from official_physics_constraints import _single
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
    from official_physics_tether import TetherSettings, tether_particle

    initial = ParticleStartState(
        (1, 2, 0), (0, 1, 0), IDENTITY, (0, 1, 0), IDENTITY, ZERO, 1
    )
    settings = StartStepSettings(
        1, 1, 0.5, (0,) * 16, 1, 1, 1, 0, (0, -1, 0), 1, ZERO, 0
    )
    center = ResolvedStartCenter(ZERO, ZERO, IDENTITY, ZERO, IDENTITY)
    started = start_particle_step(
        initial, settings, attribute=2, center=center, wind=ZERO
    )
    tethered = tether_particle(
        started.next_position,
        started.velocity_position,
        ZERO,
        started.step_basic_position,
        ZERO,
        TetherSettings(0.4, 0.03),
    )
    state = BaselineState(
        (ZERO, tethered.next_position),
        (ZERO, tethered.velocity_position),
        (ZERO, started.step_basic_position),
        (IDENTITY,) * 2,
        (0.0,) * 2,
        (IDENTITY,) * 2,
        (None,) * 2,
    )
    constrained = solve_angle_range(
        state,
        {0: AnglePassTeam(TeamWindow(0, 2, 0, 2, 0, 2), 0.0)},
        {0: AnglePassParameters(True, True, (0.0,) * 16, 1, (0.2,) * 16, 0.8, 0)},
        packed_step_indices=(0,),
        starts=(0,),
        counts=(2,),
        data=(0, 1),
        parents=(-1, 0),
        attributes=(1, 2),
        depths=(0.0, 1.0),
        simulation_power_w=1,
        index_count=1,
        route=route,
    )
    final = constrained.state
    assert final.next_positions[1] != tethered.next_position
    assert final.velocity_positions[1] != tethered.velocity_position
    ended = finish_particle_step(
        ParticleEndState(
            final.next_positions[1],
            initial.old_position,
            final.velocity_positions[1],
            ZERO,
            0,
            0,
            ZERO,
            1,
        ),
        EndStepSettings(0.5, 1, 1, -1, 0, 0, 0),
        attribute=2,
    )
    assert ended.old_position == final.next_positions[1]
    expected_velocity = tuple(
        _single((p - v) / 0.5)
        for p, v in zip(
            final.next_positions[1], final.velocity_positions[1], strict=True
        )
    )
    assert ended.velocity == expected_velocity
    assert ended.velocity != tuple(
        _single((p - v) / 0.5)
        for p, v in zip(final.next_positions[1], started.velocity_position, strict=True)
    )
    following = start_particle_step(
        replace(initial, old_position=ended.old_position, velocity=ended.velocity),
        settings,
        attribute=2,
        center=center,
        wind=ZERO,
    )
    assert following.velocity_position == tuple(_single(p) for p in ended.old_position)
    assert following.next_position == tuple(
        _single(p) + _single(v * 0.5)
        for p, v in zip(ended.old_position, ended.velocity, strict=True)
    )
