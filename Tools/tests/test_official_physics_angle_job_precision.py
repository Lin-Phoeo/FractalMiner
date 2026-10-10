"""Finite Job-specific narrowing fixtures, independent struct Single arithmetic."""

import math
import struct
import sys
from pathlib import Path
from typing import Any

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from official_physics_angle_baseline import (
    AngleSettings,
    BaselineState,
    TeamWindow,
    resolve_baseline,
    solve_baseline,
)
from official_physics_angle_cache import EdgeCache, limit_cached_edge
from official_physics_angles import restoration_pair

IDENTITY = (0.0, 0.0, 0.0, 1.0)
ZERO = (0.0, 0.0, 0.0)


def test_cached_limit_selector_rejected_before_unresolved_input_reads():
    unresolved: Any = None
    with pytest.raises(ValueError, match="selector must be bool"):
        limit_cached_edge(
            unresolved,
            unresolved,
            unresolved,
            unresolved,
            unresolved,
            unresolved,
            limit_curve=(),
            depth=0,
            limit_stiffness=0,
            child_friction=0,
            parent_friction=0,
            parent_movable=False,
            ordinary_job=unresolved,
        )


def s(value):
    return struct.unpack("<f", struct.pack("<f", value))[0]


def pair_arguments():
    return {
        "child_position": (16777217.0, 1.25, 0.375),
        "parent_position": ZERO,
        "child_velocity": (7.0, 8.0, 9.0),
        "parent_velocity": (1.0, 2.0, 3.0),
        "restoration_world_vector": (0.0, 1.0, 0.0),
        "converted_stiffness_curve": (0.0,) * 16,
        "depth": 0.5,
        "power_w": 0.0,
        "gravity_falloff": 0.2,
        "gravity_dot": 0.4,
        "iteration": 0,
        "child_friction": 0.1,
        "parent_friction": 0.2,
        "parent_movable": True,
        "velocity_attenuation": 0.8,
    }


@pytest.mark.parametrize("iteration", [0, 1, 2])
@pytest.mark.parametrize("parent_move", [False, True])
def test_job_identity_rotation_still_narrows_delta_and_three_vector_products(
    iteration,
    parent_move,
):
    from official_physics_angles import restoration_job_pair

    args = pair_arguments()
    args.update(iteration=iteration, parent_movable=parent_move)
    result = restoration_job_pair(**args)
    child, parent = args["child_position"], args["parent_position"]
    delta = tuple(s(child[i] - parent[i]) for i in range(3))
    # Fraction0 produces identity, but native float3 multiplications still round.
    pivot = s(s(s(iteration * 0.5) * s(0.4)) + s(0.1))
    complement = s(1 - pivot)
    middle = tuple(parent[i] + s(delta[i] * pivot) for i in range(3))
    c_weight = s(1 / s(s(s(0.1) * 3) + 1))
    p_weight = s(1 / s(s(s(0.2) * 3) + 1))
    c_delta = tuple(
        (middle[i] + s(delta[i] * complement) - child[i]) * c_weight for i in range(3)
    )
    p_delta = tuple(
        (middle[i] - s(delta[i] * pivot) - parent[i]) * p_weight if parent_move else 0.0
        for i in range(3)
    )
    assert result.child_correction == c_delta
    assert result.parent_correction == p_delta
    assert result.child_position == tuple(child[i] + c_delta[i] for i in range(3))
    assert result.child_velocity_position == tuple(
        args["child_velocity"][i] + c_delta[i] * s(0.8) for i in range(3)
    )
    assert result.parent_position == parent
    assert result.parent_velocity_position == args["parent_velocity"]
    # Managed Double vector products do not have this three-product rounding.
    if iteration != 2:
        assert result.child_position != restoration_pair(**args).child_position


def test_job_alignment_uses_single_narrowed_post_limit_delta():
    child = (12345.6789, 9876.54321, 1.23456789)
    cache = EdgeCache(
        (0.0, 1.0, 0.0), IDENTITY, s(math.sqrt(sum(v * v for v in child))), None
    )
    args = {
        "child_position": child,
        "parent_position": ZERO,
        "child_velocity": ZERO,
        "parent_velocity": ZERO,
        "parent_rotation_cache": IDENTITY,
        "cache": cache,
        "limit_curve": (180.0,) * 16,
        "depth": 0.5,
        "limit_stiffness": 1.0,
        "child_friction": 0.0,
        "parent_friction": 0.0,
        "parent_movable": False,
    }
    result = limit_cached_edge(**args, ordinary_job=True)
    target = tuple(s(v) for v in result.pair.child_position)
    length = math.sqrt(
        (target[1] * target[1] + target[0] * target[0]) + target[2] * target[2]
    )
    unit = tuple(v * (1 / length) for v in target)
    theta = math.acos(unit[1])
    # cross(+Y,target)=(target.z,0,-target.x), normalize Double, then narrow.
    axis_len = math.sqrt(unit[2] * unit[2] + unit[0] * unit[0])
    axis = (s(unit[2] * (1 / axis_len)), 0.0, s(-unit[0] * (1 / axis_len)))
    half = s(s(theta) * 0.5)
    sine, cosine = s(math.sin(half)), s(math.cos(half))
    expected = (s(axis[0] * sine), 0.0, s(axis[2] * sine), cosine)
    assert result.child_rotation == expected
    assert result.pair == limit_cached_edge(**args).pair
    assert result.child_rotation != limit_cached_edge(**args).child_rotation


def test_job_baseline_uses_distinct_restoration_seam_and_preserves_input():
    plan = resolve_baseline(
        0, [TeamWindow(0, 2, 0, 2, 0, 2)], [0], [2], [0, 1], [-1, 0], [1, 2], [0.0, 0.5]
    )
    positions = (ZERO, pair_arguments()["child_position"])
    state = BaselineState(
        positions,
        positions,
        (ZERO, (0.0, 1.0, 0.0)),
        (IDENTITY,) * 2,
        (0.0,) * 2,
        (IDENTITY,) * 2,
        (None,) * 2,
    )
    settings = AngleSettings(
        False, True, (0.0,) * 16, 1.0, (0.0,) * 16, 0.8, 0.0, 0.2, 0.4
    )
    original = repr(state)
    result = solve_baseline(plan, state, settings, ordinary_job=True)
    assert repr(state) == original
    assert (
        result.state.next_positions
        != solve_baseline(plan, state, settings).state.next_positions
    )
    assert [(v.iteration, v.phase) for v in result.visits] == [
        (i, "restoration") for i in range(3)
    ]
    assert result.state.rotations == (IDENTITY,) * 2


@pytest.mark.parametrize("bad", [0, 1, None, "job"])
def test_numeric_backend_selector_is_explicit_adapter_bool(bad):
    unresolved: Any = None
    with pytest.raises(ValueError, match="bool"):
        solve_baseline(
            unresolved,
            unresolved,
            AngleSettings(False, False, (), 1, (), 1, 1, 1, 1),
            ordinary_job=bad,
        )


def test_job_refuses_a_double_direction_that_narrows_to_zero():
    from official_physics_angles import restoration_job_pair

    args = pair_arguments()
    args["child_position"] = (1e-46, 0.0, 0.0)
    with pytest.raises(ValueError, match="nonzero"):
        restoration_job_pair(**args)


def test_dyadic_zero_strength_job_is_not_an_early_return_or_double_bridge():
    from official_physics_angles import restoration_job_pair

    args = pair_arguments()
    args.update(
        child_position=(1 + 2**-25, 2 + 2**-24, 0.0),
        child_velocity=ZERO,
        parent_velocity=ZERO,
        iteration=2,
        child_friction=0.0,
        parent_friction=0.0,
        velocity_attenuation=0.5,
        restoration_world_vector=(0.0, 0.0, 1.0),
    )
    job = restoration_job_pair(**args)
    assert job.child_position == (1.0, 2.0, 0.0)
    assert job.child_correction == (-(2**-25), -(2**-24), 0.0)
    assert job.child_velocity_position == (-(2**-26), -(2**-25), 0.0)
    assert restoration_pair(**args).child_position == args["child_position"]


def test_post_limit_narrowing_crosses_actual_from_to_epsilon_branch():
    target = (1.0, 0.001414214629263386, 0.0)
    args = {
        "child_position": target,
        "parent_position": ZERO,
        "child_velocity": ZERO,
        "parent_velocity": ZERO,
        "parent_rotation_cache": IDENTITY,
        "cache": EdgeCache((1.0, 0.0, 0.0), IDENTITY, 1.0000009536743164, None),
        "limit_curve": (180.0,) * 16,
        "depth": 0.5,
        "limit_stiffness": 1.0,
        "child_friction": 0.0,
        "parent_friction": 0.0,
        "parent_movable": False,
    }
    job = limit_cached_edge(**args, ordinary_job=True)
    managed = limit_cached_edge(**args)
    assert job.pair == managed.pair
    delta = managed.pair.child_position
    unit_x = delta[0] * (
        1 / math.sqrt((delta[1] * delta[1] + delta[0] * delta[0]) + delta[2] * delta[2])
    )
    narrowed = tuple(s(v) for v in delta)
    narrow_x = narrowed[0] * (
        1
        / math.sqrt(
            (narrowed[1] * narrowed[1] + narrowed[0] * narrowed[0])
            + narrowed[2] * narrowed[2]
        )
    )
    assert 1 - unit_x > s(1e-6) > 1 - narrow_x
    assert job.child_rotation == IDENTITY
    assert managed.child_rotation != IDENTITY


@pytest.mark.parametrize("parent_move", [False, True])
def test_job_quarter_turn_uses_single_rotate_then_single_products(parent_move):
    from official_physics_angles import restoration_job_pair

    args = pair_arguments()
    args.update(
        child_position=(1 + 2**-25, 0.0, 0.0),
        child_velocity=ZERO,
        parent_velocity=ZERO,
        iteration=2,
        converted_stiffness_curve=(1.0,) * 16,
        power_w=1.0,
        gravity_falloff=0.0,
        child_friction=0.0,
        parent_friction=0.0,
        parent_movable=parent_move,
    )
    # Independent AxisAngle(+Z,pi/2) and float3 helper component recurrence.
    half = s(s(math.pi / 2) * 0.5)
    qz, qw = s(math.sin(half)), s(math.cos(half))
    twice_y = s(2 * qz)
    desired = (s(1.0 + s(-s(qz * twice_y))), s(qw * twice_y), 0.0)
    child_target = (0.5 + s(desired[0] * 0.5), s(desired[1] * 0.5), 0.0)
    parent_target = (0.5 - s(desired[0] * 0.5), -s(desired[1] * 0.5), 0.0)
    result = restoration_job_pair(**args)
    assert result.child_position == child_target
    assert result.parent_position == (parent_target if parent_move else ZERO)
    assert result.child_velocity_position == tuple(
        (child_target[i] - args["child_position"][i]) * s(0.8) for i in range(3)
    )
