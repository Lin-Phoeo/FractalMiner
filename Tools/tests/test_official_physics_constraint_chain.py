"""Resolved finite fragments, not a complete host solver or native oracle.

Explicit synthetic WorkData/adjacency/center/wind drive Start → Distance →
PointCollision → Distance → End → next Start. Angle/bending/tether/motion and
self-collision are NOT silently supplied as no-ops or declared exercised.
"""

import sys
from dataclasses import replace
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from official_physics_constraints import _single
from official_physics_distance_pass import (
    DistanceBuffers,
    DistancePassSettings,
    DistancePassTeam,
    solve_distance_range,
)
from official_physics_particle_step import (
    EndStepSettings,
    ParticleEndState,
    finish_particle_step,
)
from official_physics_point_collision import (
    ColliderWork,
    PointCollisionParameters,
    PointCollisionState,
    PointCollisionTeam,
    point_collision_particle,
)
from official_physics_start_step import (
    ParticleStartState,
    ResolvedStartCenter,
    StartStepSettings,
    start_particle_step,
)
from official_physics_substep_plan import (
    SelfCollisionCounts,
    SubstepInputs,
    plan_simulation_substep,
)

ZERO = (0.0, 0.0, 0.0)
IDENTITY = (0.0, 0.0, 0.0, 1.0)


def start_inputs(flag=0):
    cfg = StartStepSettings(
        1, 1, 0.5, (0,) * 16, 1, 1, 1, 0, (0, -1, 0), 1, ZERO, 0, flag
    )
    center = ResolvedStartCenter(ZERO, ZERO, IDENTITY, ZERO, IDENTITY)
    states = tuple(
        ParticleStartState(p, p, IDENTITY, p, IDENTITY, ZERO, 1)
        for p in ((0, 0.5, 0), (0, 2, 0))
    )
    return states, cfg, center


def distance(buffers, flag=0):
    # Independent particle/proxy/adjacency chunk origins, encoded work order.
    return solve_distance_range(
        buffers,
        {1: DistancePassTeam(flag, 1, 2, 3, 2, 2, 1, 1, 0)},
        {1: DistancePassSettings((1,) * 16, 0.5)},
        step_particle_indices=(1, 2),
        team_ids=(0, 1, 1),
        attributes=(0, 0, 2, 2),
        depths=(0, 0, 1, 1),
        adjacency_words=(0, 0, 0, 1 << 20, (1 << 20) | 1),
        neighbor_local_indices=(0, 0, 1, 0),
        signed_rest_lengths=(0, 0, 1, 1),
        simulation_power_y=1,
        index_count=2,
    )


def fragments(*, spring=False, dynamic_friction=0.0):
    flag = 0x2000 if spring else 0
    states, start_cfg, center = start_inputs(flag)
    started = tuple(
        start_particle_step(s, start_cfg, attribute=2, center=center, wind=ZERO)
        for s in states
    )
    buffers = DistanceBuffers(
        (ZERO,) + tuple(s.next_position for s in started),
        (ZERO,) + tuple(s.base_position for s in started),
        (ZERO,) + tuple(s.velocity_position for s in started),
        (0, 0, 0),
    )
    first = distance(buffers, flag)
    # Capsule along X: ordinary and Spring use the same shape correction.
    # No guessed prefab → WorkData conversion is performed by this fixture.
    endpoints = ((-1.0, 0.0, 0.0), (1.0, 0.0, 0.0))
    collider = ColliderWork(
        0x32,
        (-2, -2, -2),
        (2, 2, 2),
        (1, 1),
        endpoints,
        endpoints,
        IDENTITY,
        IDENTITY,
    )
    collisions = tuple(
        point_collision_particle(
            PointCollisionState(
                first.buffers.next_positions[i],
                first.buffers.velocity_positions[i],
                first.buffers.base_positions[i],
                first.buffers.frictions[i],
                ZERO,
            ),
            PointCollisionTeam(flag, 1, 0, 1),
            PointCollisionParameters(1, (0.25,) * 16, (0.125,) * 16),
            attribute=2,
            depth=1,
            colliders=(collider,),
        )
        for i in (1, 2)
    )
    collided = replace(
        first.buffers,
        next_positions=(ZERO,) + tuple(c.state.next_position for c in collisions),
        velocity_positions=(ZERO,)
        + tuple(c.state.velocity_position for c in collisions),
        frictions=(0,) + tuple(c.state.friction for c in collisions),
    )
    second = distance(collided, flag)
    ended = tuple(
        finish_particle_step(
            ParticleEndState(
                second.buffers.next_positions[i + 1],
                s.old_position,
                second.buffers.velocity_positions[i + 1],
                s.velocity,
                collisions[i].state.friction,
                0,
                collisions[i].state.collision_normal,
                1,
            ),
            EndStepSettings(0.5, 1, 1, -1, dynamic_friction, 0, 0, flag),
            attribute=2,
        )
        for i, s in enumerate(states)
    )
    following = tuple(
        start_particle_step(
            replace(s, old_position=e.old_position, velocity=e.velocity),
            start_cfg,
            attribute=2,
            center=center,
            wind=ZERO,
        )
        for s, e in zip(states, ended, strict=True)
    )
    return first, collisions, collided, second, ended, following


def hand_computed_second_sweep():
    # Independent axial formula, not distance_particle as a reference oracle.
    # depth1 removes the depth term; friction1 gives Single(1/(1+3)).
    mass = _single(1 / 4)
    denominator = _single(mass + 1)
    delta_first = (-0.375 / denominator) * mass
    next_first = 1.25 + delta_first
    delta_second = ((1.875 - next_first) - 1) / denominator * -1
    next_second = 1.875 + delta_second
    vp_first = 0.625 + delta_first * 0.5
    vp_second = 1.9375 + delta_second * 0.5
    return next_first, next_second, vp_first, vp_second


def test_start_distance_capsule_distance_end_feedback_matches_axial_math():
    first, collisions, _, second, ended, _ = fragments()
    assert first.buffers.next_positions[1:] == ((0, 0.75, 0), (0, 1.875, 0))
    assert first.buffers.velocity_positions[1:] == ((0, 0.625, 0), (0, 1.9375, 0))
    assert [c.state.next_position for c in collisions] == [
        (0, 1.25, 0),
        (0, 1.875, 0),
    ]
    assert [c.penetrating_contacts for c in collisions] == [1, 0]
    assert [c.state.friction for c in collisions] == [1, 0]
    nxt0, nxt1, vp0, vp1 = hand_computed_second_sweep()
    assert second.buffers.next_positions[1:] == ((0, nxt0, 0), (0, nxt1, 0))
    assert second.buffers.velocity_positions[1:] == ((0, vp0, 0), (0, vp1, 0))
    assert [e.velocity for e in ended] == [
        (0, _single((nxt0 - vp0) / 0.5), 0),
        (0, _single((nxt1 - vp1) / 0.5), 0),
    ]
    assert [e.real_velocity for e in ended] == [
        (0, _single((nxt0 - 0.5) / 0.5), 0),
        (0, _single((nxt1 - 2) / 0.5), 0),
    ]
    assert ended[0].friction == _single(0.6)


def test_collision_friction_changes_second_distance_inverse_mass():
    _, _, collided, correct, _, _ = fragments()
    wrong = distance(replace(collided, frictions=(0, 0, 0)))
    assert wrong.buffers.next_positions[1:] == ((0, 1.0625, 0), (0, 1.96875, 0))
    assert correct.buffers.next_positions != wrong.buffers.next_positions
    # A omitted/merged second pass would retain these different coordinates.
    assert correct.buffers.next_positions != collided.next_positions


def test_spring_collision_shifts_velocity_reference_as_well_as_position():
    ordinary = fragments()
    spring = fragments(spring=True)
    assert spring[1][0].state.velocity_position == (0, 1.125, 0)
    assert ordinary[1][0].state.velocity_position == (0, 0.625, 0)
    assert spring[3].buffers.next_positions == ordinary[3].buffers.next_positions
    for spr, plain in zip(spring[4], ordinary[4], strict=True):
        assert spr.old_position == plain.old_position
        assert spr.real_velocity == plain.real_velocity
    assert spring[4][0].velocity[1] == pytest.approx(
        ordinary[4][0].velocity[1] - 1, abs=1e-7
    )


@pytest.mark.parametrize("spring", [False, True])
def test_following_start_uses_end_history_not_collision_or_display_snapshot(spring):
    _, _, collided, _, ended, following = fragments(spring=spring)
    for e, s in zip(ended, following, strict=True):
        # Start deliberately narrows the center-relative Double oldPos before
        # Single rotation, even for identity and zero center motion.
        moved_y = _single(e.old_position[1])
        assert s.velocity_position == (0, moved_y, 0)
        assert s.next_position == (
            e.old_position[0],
            moved_y + _single(e.velocity[1] * 0.5),
            e.old_position[2],
        )
    assert following[0].velocity_position != collided.next_positions[1]


def test_end_dynamic_friction_consumes_published_collision_normal():
    collision = fragments()[1][0].state
    assert collision.collision_normal == (0, 1, 0)
    # Explicit tangential velocity reference after other constraints, exercising
    # normal/friction consumption independently from the axial fragment above.
    incoming = ParticleEndState(
        collision.next_position,
        (0, 0.5, 0),
        (-0.25, 1.25, 0),
        ZERO,
        collision.friction,
        0,
        collision.collision_normal,
        1,
    )
    settings = EndStepSettings(0.5, 1, 1, -1, 1, 0, 0)
    damped = finish_particle_step(incoming, settings, attribute=2)
    undamped = finish_particle_step(
        replace(incoming, collision_normal=ZERO), settings, attribute=2
    )
    assert damped.velocity == (0.125, 0, 0)
    assert undamped.velocity == (0.5, 0, 0)
    assert damped.real_velocity == undamped.real_velocity


@pytest.mark.parametrize("spring", [False, True])
def test_end_decayed_friction_is_consumed_by_next_substep_distance(spring):
    _, _, _, second, ended, following = fragments(spring=spring)
    next_buffers = replace(
        second.buffers,
        next_positions=(ZERO,) + tuple(s.next_position for s in following),
        base_positions=(ZERO,) + tuple(s.base_position for s in following),
        velocity_positions=(ZERO,) + tuple(s.velocity_position for s in following),
        frictions=(0,) + tuple(e.friction for e in ended),
    )
    result = distance(next_buffers, 0x2000 if spring else 0)
    first_y, second_y = (s.next_position[1] for s in following)
    # Independent source-order Single mass construction with End's .6 value,
    # then Double axial correction; no tested solver used as the oracle.
    mass0 = _single(1 / _single(_single(_single(0.6) * 3) + 1))
    denominator = _single(mass0 + 1)
    delta0 = second_y - first_y
    direction0 = delta0 * (1 / abs(delta0))
    correction0 = ((direction0 * (abs(delta0) - 1)) / denominator) * mass0
    next0 = first_y + correction0
    delta1 = next0 - second_y
    direction1 = delta1 * (1 / abs(delta1))
    correction1 = (direction1 * (abs(delta1) - 1)) / denominator
    assert result.buffers.next_positions[1:] == (
        (0, next0, 0),
        (0, second_y + correction1, 0),
    )
    assert result.buffers.velocity_positions[1:] == (
        (0, following[0].velocity_position[1] + correction0 * 0.5, 0),
        (0, following[1].velocity_position[1] + correction1 * 0.5, 0),
    )
    lost_friction = distance(
        replace(next_buffers, frictions=(0, 0, 0)), 0x2000 if spring else 0
    )
    assert result.buffers.next_positions != lost_friction.buffers.next_positions


def test_host_plan_places_selected_fragments_without_claiming_other_solvers_ran():
    plan = plan_simulation_substep(
        SubstepInputs(2, 0, 0, False, False),
        "resolved-input-handle",
        SelfCollisionCounts(0, 0, 0, 0),
    )
    assert [plan.calls[i].operation for i in (5, 8, 11, 12, 16)] == [
        "StartSimulationStepJob",
        "DistanceConstraint.SolverConstraint",
        "ColliderCollisionConstraint.SolverConstraint",
        "DistanceConstraint.SolverConstraint",
        "EndSimulationStepJob",
    ]
    assert plan.calls[11].input_handle == plan.calls[10].output_handle
    assert plan.calls[12].input_handle == plan.calls[11].output_handle
    assert plan.calls[14].no_op and plan.calls[15].no_op
    assert len(plan.calls) == 18
