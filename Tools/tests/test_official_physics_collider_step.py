"""Offline producer/consumer checks of the managed Start collider step."""

import math
import sys
from dataclasses import replace
from pathlib import Path
from typing import Any

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from official_physics_collider_step import (
    ColliderStepCenter,
    ColliderStepResult,
    ColliderStepState,
    ColliderStepTeam,
    _change_sign4,
    start_collider_step,
)
from official_physics_constraints import _single
from official_physics_point_collision import (
    ColliderWork,
    PointCollisionParameters,
    PointCollisionState,
    PointCollisionTeam,
    point_collision_particle,
)

ZERO = (0.0, 0.0, 0.0)
Q = (0.0, 0.0, 0.0, 1.0)
WRITES = ("now_position", "now_rotation", "old_position", "old_rotation", "work")


def state(shape: int = 1, **changes: Any) -> ColliderStepState:
    value = ColliderStepState(
        0x30 | shape,
        (1, 2, 10),
        (3, 0, 0),
        Q,
        (1, 1, 1),
        ZERO,
        Q,
        (101, 102, 103),
        (1, 0, 0, 0),
        ZERO,
        Q,
        None,
    )
    return replace(value, **changes)


def run(
    value: ColliderStepState | None = None,
    *,
    interpolation: float = 1,
    move: float = 0,
    rotation: float = 1,
) -> ColliderStepResult:
    return start_collider_step(
        state() if value is None else value,
        ColliderStepTeam(interpolation),
        ColliderStepCenter(move, rotation),
    )


def produced(value: ColliderStepState) -> ColliderWork:
    assert value.work is not None
    return value.work


@pytest.mark.parametrize("flag", [0, 0x10, 0x20, 0x81])
def test_gate_preserves_state_without_reading_unneeded_numeric_inputs(
    flag: int,
) -> None:
    original = state(flag=flag, frame_position=(math.nan, 0, 0))
    result = run(original, interpolation=math.nan, move=math.nan)
    assert result.state is original
    assert result.writes == ()


def test_sphere_uses_absolute_x_scale_and_swept_double_expansion() -> None:
    original = state(size=(0.5, 99, 20), frame_scale=(-2, 50, 80))
    result = run(original)
    work = produced(result.state)
    assert work.radii == (1, 1)
    assert work.old_points == (ZERO, ZERO)
    assert work.next_points == ((3, 0, 0), ZERO)
    assert work.aabb_min == (-1, -1, -1)
    assert work.aabb_max == (4, 1, 1)
    assert result.writes == WRITES
    assert result.state.old_frame_position == original.old_frame_position


@pytest.mark.parametrize("shape,axis", [(2, 0), (3, 1), (4, 2), (5, 0), (6, 1), (7, 2)])
def test_capsule_type_selects_axis_and_centered_or_one_sided_lengths(
    shape: int, axis: int
) -> None:
    result = run(state(shape, frame_position=ZERO))
    work = produced(result.state)
    first, second = [0.0] * 3, [0.0] * 3
    first[axis], second[axis] = (4, -3) if shape <= 4 else (0, -7)
    assert work.radii == (1, 2)
    assert work.old_points == (tuple(first), tuple(second))
    assert work.next_points == work.old_points
    # Distinct radius envelopes are unioned; for the centered form the first
    # sphere reaches +5 and the second reaches -5 on the selected axis.
    assert work.aabb_max[axis] == (5 if shape <= 4 else 1)
    assert work.aabb_min[axis] == (-5 if shape <= 4 else -9)


@pytest.mark.parametrize(
    "scale,reverse,first_x",
    [(2, False, 8), (-2, False, -8), (2, True, -8), (-2, True, 8)],
)
def test_capsule_axial_scale_sign_and_reverse_flag(
    scale: float, reverse: bool, first_x: float
) -> None:
    result = run(
        state(
            2,
            flag=0x32 | (0x80 if reverse else 0),
            frame_position=ZERO,
            frame_scale=(scale, 9, 11),
        )
    )
    work = produced(result.state)
    assert work.radii == (2, 4)
    assert work.old_points[0] == (first_x, 0, 0)
    assert work.old_points[1] == (-first_x * 0.75, 0, 0)


def test_capsule_nonpositive_segment_lengths_clamp_to_zero() -> None:
    work = produced(run(state(2, size=(4, 5, 2), frame_position=ZERO)).state)
    assert work.old_points == (ZERO, ZERO)
    assert work.aabb_min == (-5, -5, -5)
    assert work.aabb_max == (5, 5, 5)


def test_zero_axial_scale_collapses_capsule_and_radii() -> None:
    work = produced(run(state(3, frame_scale=(7, 0, 9))).state)
    assert work.radii == (0, 0)
    assert work.old_points == (ZERO, ZERO)
    assert work.next_points == ((3, 0, 0), (3, 0, 0))


@pytest.mark.parametrize(
    "scale_y,expected", [(2, (0, 1, 0)), (-2, (0, -1, 0)), (0, ZERO)]
)
def test_plane_packs_next_normal_in_old_position_and_ignores_reverse(
    scale_y: float, expected: tuple[float, float, float]
) -> None:
    result = run(state(8, flag=0xB8, frame_scale=(8, scale_y, 10)))
    work = produced(result.state)
    assert work.old_points == (expected, ZERO)
    assert work.next_points == ((3, 0, 0), ZERO)
    assert work.radii == (0, 0)
    assert work.aabb_min == work.aabb_max == ZERO


def test_plane_normal_rotates_with_normalized_first_interpolation() -> None:
    half = math.sqrt(0.5)
    work = produced(run(state(8, frame_rotation=(0, 0, half * 2, half * 2))).state)
    assert work.old_points[0] == pytest.approx((-1, 0, 0), abs=4e-7)


def test_interpolation_then_position_inertia_uses_original_old_position() -> None:
    original = state(
        frame_position=(10, 20, 30),
        old_frame_position=(2, 4, 6),
        old_position=(-2, -4, -6),
    )
    result = run(original, interpolation=0.25, move=0.5)
    assert result.state.now_position == (4, 8, 12)
    assert result.state.old_position == (1, 2, 3)
    assert produced(result.state).old_points[0] == (1, 2, 3)
    assert produced(result.state).next_points[0] == (4, 8, 12)


@pytest.mark.parametrize(
    "fraction,expected", [(-0.5, (-2, -4, -6)), (1.5, (6, 12, 18))]
)
def test_frame_interpolation_extrapolates_without_clamp(
    fraction: float, expected: tuple[float, float, float]
) -> None:
    result = run(state(frame_position=(4, 8, 12)), interpolation=fraction)
    assert result.state.now_position == expected


def test_inertia_ratios_are_not_clamped() -> None:
    result = run(state(old_position=(1, 0, 0)), move=1.5)
    assert result.state.old_position == (4, 0, 0)


def test_quaternion_shortest_arc_antipode_stays_identity() -> None:
    result = run(state(frame_rotation=(0, 0, 0, -1)), interpolation=0.5)
    assert result.state.now_rotation == Q
    assert produced(result.state).rotation == Q


@pytest.mark.parametrize("sign,expected", [(0.0, 1), (-0.0, -1), (1.0, 1), (-1.0, -1)])
def test_nlerp_change_sign_helper_preserves_sign_bit_including_negative_zero(
    sign: float, expected: float
) -> None:
    value = _change_sign4((0.0, -0.0, 1.0, -1.0), sign)
    assert math.copysign(1, value[0]) == expected
    assert math.copysign(1, value[1]) == -expected
    assert value[2:] == (expected, -expected)


def test_rotation_extrapolation_is_not_clamped() -> None:
    half = math.sqrt(0.5)
    result = run(
        state(2, frame_position=ZERO, frame_rotation=(0, 0, half, half)),
        interpolation=1.5,
    )
    assert produced(result.state).next_points[0] == pytest.approx(
        (-math.sqrt(8), math.sqrt(8), 0), abs=2e-6
    )


def test_raw_second_slerp_drives_old_endpoints_and_inverse_but_storage_normalizes() -> (
    None
):
    result = run(state(2, frame_position=ZERO, old_rotation=(0, 0, 2, 0)), rotation=0.5)
    work = produced(result.state)
    # Nonunit old input yields a nonunit spherical result. Replacing the raw
    # result with its normalized oldRotation write changes the endpoint to
    # approximately (-2.4, 3.2, 0), rather than the source's (-12, 8, 0).
    assert work.old_points[0] == pytest.approx((-12, 8, 0), abs=3e-6)
    assert result.state.old_rotation == pytest.approx(
        (0, 0, 2 / math.sqrt(5), 1 / math.sqrt(5)), abs=2e-7
    )
    assert work.inverse_old_rotation == pytest.approx(
        (0, 0, -math.sqrt(2) / 2.5, math.sqrt(0.5) / 2.5), abs=2e-7
    )
    assert work.rotation == Q


@pytest.mark.parametrize("shape", [0, 9, 15])
def test_unsupported_shape_overwrites_geometric_fields_but_populates_rotations(
    shape: int,
) -> None:
    original = state(shape)
    prior = produced(run(state()).state)
    result = run(replace(original, work=prior))
    work = produced(result.state)
    assert work.old_points == work.next_points == (ZERO, ZERO)
    assert work.aabb_min == work.aabb_max == ZERO
    assert work.radii == (0, 0)
    assert work.rotation == work.inverse_old_rotation == Q
    assert work is not prior
    assert result.writes == WRITES


def test_start_explicitly_narrows_high_coordinates_before_work_double_storage() -> None:
    result = run(
        state(frame_position=(1e12 + 0.125, 0, 0), old_frame_position=(1e12, 0, 0)),
        move=1,
    )
    assert result.state.now_position[0] == _single(1e12)
    assert produced(result.state).next_points[0][0] == _single(1e12)
    assert produced(result.state).next_points[0][0] != 1e12 + 0.125


def test_sphere_and_capsule_bounds_have_different_float_to_double_order() -> None:
    common = {
        "frame_position": (2**24, 0, 0),
        "old_position": (2**24, 0, 0),
        "size": (0.25, 0.25, 0),
    }
    sphere = produced(run(state(1, **common)).state)
    capsule = produced(run(state(2, **common)).state)
    assert sphere.aabb_min[0] == 2**24 - 0.25
    assert sphere.aabb_max[0] == 2**24 + 0.25
    assert capsule.aabb_min[0] == capsule.aabb_max[0] == 2**24


@pytest.mark.parametrize("shape", [1, 3])
def test_produced_workdata_flows_through_point_collision_across_two_steps(
    shape: int,
) -> None:
    collider = state(shape, frame_position=(1, 0, 0), size=(1, 1, 4))
    parameters = PointCollisionParameters(1, (0.25,) * 16, (0.1,) * 16)
    team = PointCollisionTeam(0, 1, 0, 1)
    particle = PointCollisionState((0.75, 0, 0), ZERO, ZERO, 0, ZERO)
    first = run(collider, move=0.5).state
    particle = point_collision_particle(
        particle, team, parameters, attribute=2, depth=0.5, colliders=(produced(first),)
    ).state
    assert particle.next_position == (2.25, 0, 0)
    second = run(replace(first, frame_position=(2, 0, 0)), move=0.5).state
    assert second.old_position == (1.25, 0, 0)
    particle = point_collision_particle(
        particle,
        team,
        parameters,
        attribute=2,
        depth=0.5,
        colliders=(produced(second),),
    ).state
    assert particle.next_position == (3.25, 0, 0)


def test_plane_producer_to_consumer_across_two_steps() -> None:
    parameters = PointCollisionParameters(1, (0.25,) * 16, (0.1,) * 16)
    team = PointCollisionTeam(0, 1, 0, 1)
    particle = PointCollisionState((0, -0.5, 0), ZERO, ZERO, 0, ZERO)
    first = run(state(8, frame_position=ZERO)).state
    particle = point_collision_particle(
        particle, team, parameters, attribute=2, depth=0.5, colliders=(produced(first),)
    ).state
    assert particle.next_position == (0, 0.25, 0)
    second = run(replace(first, frame_position=(0, 1, 0))).state
    particle = point_collision_particle(
        particle,
        team,
        parameters,
        attribute=2,
        depth=0.5,
        colliders=(produced(second),),
    ).state
    assert particle.next_position == (0, 1.25, 0)


@pytest.mark.parametrize(
    "changes",
    [
        {"frame_position": (math.inf, 0, 0)},
        {"frame_rotation": (0, 0, 0, 0)},
        {"frame_rotation": (1, 2, 3)},
        {"frame_scale": (1, 2)},
    ],
)
def test_finite_adapter_rejects_invalid_active_input(changes: dict[str, Any]) -> None:
    with pytest.raises(ValueError):
        run(state(**changes))


@pytest.mark.parametrize("flag", [-1, 256, True, "49"])
def test_flag_adapter_rejects_non_byte_input(flag: Any) -> None:
    with pytest.raises(ValueError):
        run(state(flag=flag))
