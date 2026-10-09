"""Behavior tests for the explicit WorkData point-collision reference."""

import math
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from official_physics_constraints import _single
from official_physics_point_collision import (
    ColliderWork,
    PointCollisionParameters,
    PointCollisionState,
    PointCollisionTeam,
    point_collision_particle,
)

ZERO = (0.0, 0.0, 0.0)
IDENTITY = (0.0, 0.0, 0.0, 1.0)


def work(
    shape=1,
    *,
    old_a=ZERO,
    old_b=ZERO,
    next_a=ZERO,
    next_b=ZERO,
    radii=(1.0, 1.0),
    rotation=IDENTITY,
    inverse_old_rotation=IDENTITY,
    aabb_min=(-2.0, -2.0, -2.0),
    aabb_max=(2.0, 2.0, 2.0),
    flag=None,
):
    return ColliderWork(
        0x30 | shape if flag is None else flag,
        aabb_min,
        aabb_max,
        radii,
        (old_a, old_b),
        (next_a, next_b),
        inverse_old_rotation,
        rotation,
    )


def run(
    position=(0.0, 0.5, 0.0),
    *,
    colliders=None,
    radius=0.25,
    limit=0.1,
    flag=0,
    attribute=2,
    friction=0.0,
    velocity=(7.0, 8.0, 9.0),
    base=(0.0, 0.5, 0.0),
    count=None,
    start=0,
    mode=1,
    scale=1.0,
):
    colliders = (work(),) if colliders is None else colliders
    state = PointCollisionState(position, velocity, base, friction, (9.0, 9.0, 9.0))
    team = PointCollisionTeam(
        flag, scale, start, len(colliders) - start if count is None else count
    )
    params = PointCollisionParameters(mode, (radius,) * 16, (limit,) * 16)
    return point_collision_particle(
        state, team, params, attribute=attribute, depth=0.3, colliders=colliders
    )


def test_sphere_penetration_and_proximity_friction():
    result = run()
    assert result.state.next_position == (0.0, 1.25, 0.0)
    assert result.state.velocity_position == (7.0, 8.0, 9.0)
    assert result.state.friction == 1.0
    assert result.state.collision_normal == (0.0, 1.0, 0.0)
    assert result.penetrating_contacts == 1
    assert result.writes == ("friction", "collision_normal", "next_position")


def test_sphere_uses_old_radial_direction_and_new_center():
    result = run((0.5, 0.0, 0.0), colliders=(work(next_a=(1.0, 0.0, 0.0)),))
    assert result.state.next_position == (2.25, 0.0, 0.0)
    assert result.state.collision_normal == (1.0, 0.0, 0.0)


def test_capsule_taper_interpolates_single_radii_at_old_segment_projection():
    collider = work(
        2,
        old_a=(0.0, -1.0, 0.0),
        old_b=(0.0, 1.0, 0.0),
        next_a=(0.0, -1.0, 0.0),
        next_b=(0.0, 1.0, 0.0),
        radii=(0.5, 1.5),
    )
    result = run((0.5, 0.5, 0.0), colliders=(collider,))
    assert result.state.next_position == (1.5, 0.5, 0.0)
    assert result.state.collision_normal == (1.0, 0.0, 0.0)


def test_capsule_projection_fraction_narrows_before_old_center_lerp():
    collider = work(2, old_b=(0.0, 3.0, 0.0), next_b=(0.0, 3.0, 0.0), radii=(0.5, 1.5))
    position = (0.5, 1.0, 0.0)
    t = _single(1.0 / 3.0)
    center_y = 3.0 * t
    radial = (0.5, _single(1.0 - center_y), 0.0)
    reciprocal = 1.0 / math.sqrt((radial[1] ** 2 + radial[0] ** 2) + radial[2] ** 2)
    normal = tuple(component * reciprocal for component in radial)
    narrowed = tuple(_single(component) for component in normal)
    radius = _single(_single(t + 0.5) + 0.25)
    surface = (normal[0] * radius, center_y + normal[1] * radius, 0.0)
    dot = (1.0 - surface[1]) * narrowed[1] + (0.5 - surface[0]) * narrowed[0]
    expected = (0.5 - narrowed[0] * dot, 1.0 - narrowed[1] * dot, 0.0)
    result = run(position, colliders=(collider,))
    assert result.state.next_position == expected
    assert result.state.next_position[1] != 1.0


@pytest.mark.parametrize("shape", range(2, 8))
def test_all_six_capsule_types_share_workdata_consumer(shape):
    collider = work(
        shape,
        old_a=(0.0, -1.0, 0.0),
        old_b=(0.0, 1.0, 0.0),
        next_a=(0.0, -1.0, 0.0),
        next_b=(0.0, 1.0, 0.0),
    )
    assert run((0.5, 0.0, 0.0), colliders=(collider,)).state.next_position == (
        1.25,
        0.0,
        0.0,
    )


def test_capsule_zero_length_old_segment_selects_start_without_division():
    collider = work(2, radii=(0.5, 1.5))
    assert run((0.25, 0.0, 0.0), colliders=(collider,)).state.next_position == (
        0.75,
        0.0,
        0.0,
    )


@pytest.mark.parametrize("y,radius", [(-1.1, 0.5), (1.1, 1.5)])
def test_capsule_projection_clamps_to_old_endpoints(y, radius):
    collider = work(
        2,
        old_a=(0.0, -1.0, 0.0),
        old_b=(0.0, 1.0, 0.0),
        next_a=(0.0, -1.0, 0.0),
        next_b=(0.0, 1.0, 0.0),
        radii=(0.5, 1.5),
        aabb_min=(-5.0, -5.0, -5.0),
        aabb_max=(5.0, 5.0, 5.0),
    )
    result = run((0.1, y, 0.0), colliders=(collider,))
    # Old projection clamps to the endpoint, selecting its distinct radius.
    endpoint = -1.0 if y < 0 else 1.0
    radial_length = (0.1**2 + (y - endpoint) ** 2) ** 0.5
    combined = radius + 0.25
    expected = (
        0.1 / radial_length * combined,
        endpoint + (y - endpoint) / radial_length * combined,
        0.0,
    )
    assert result.state.next_position == pytest.approx(expected, abs=2e-7)


def test_rotating_capsule_narrows_rotates_then_widens_direction():
    s = 2**-0.5
    collider = work(
        2,
        old_a=(0.0, -1.0, 0.0),
        old_b=(0.0, 1.0, 0.0),
        next_a=(-1.0, 0.0, 0.0),
        next_b=(1.0, 0.0, 0.0),
        rotation=(0.0, 0.0, s, s),
    )
    result = run((0.5, 0.0, 0.0), colliders=(collider,))
    assert result.state.next_position == pytest.approx(
        (0.499999925, 1.25, 0.0), abs=2e-7
    )
    assert result.state.collision_normal == pytest.approx((0.0, 1.0, 0.0), abs=2e-7)


def test_plane_uses_old_normal_new_plane_location_and_ignores_aabb():
    collider = work(
        8,
        old_a=(0.0, 1.0, 0.0),
        next_a=(0.0, 0.0, 0.0),
        aabb_min=(100.0, 100.0, 100.0),
        aabb_max=(101.0, 101.0, 101.0),
    )
    assert run((0.0, -0.5, 0.0), colliders=(collider,)).state.next_position == (
        0.0,
        0.25,
        0.0,
    )


def test_plane_keeps_nonunit_source_normal_arithmetic():
    collider = work(8, old_a=(0.0, 2.0, 0.0))
    result = run((0.0, 0.0, 0.0), colliders=(collider,))
    # Plane is y=.5, projection uses n*dot(delta,n), giving a correction of 2.
    assert result.state.next_position == (0.0, 2.0, 0.0)
    assert result.state.collision_normal == (0.0, 1.0, 0.0)


def test_plane_surface_keeps_double_but_projection_narrows_to_single():
    normal_y = 1.0 + 2**-25
    collider = work(8, old_a=(0.0, normal_y, 0.0))
    result = run(ZERO, colliders=(collider,))
    assert result.state.next_position == (0.0, normal_y * 0.25, 0.0)
    assert result.state.collision_normal == (0.0, 1.0, 0.0)


def test_capsule_inverse_old_rotation_precedes_next_rotation():
    s = 2**-0.5
    collider = work(
        2,
        old_a=(0.0, -1.0, 0.0),
        old_b=(0.0, 1.0, 0.0),
        next_a=(0.0, -1.0, 0.0),
        next_b=(0.0, 1.0, 0.0),
        inverse_old_rotation=(s, 0.0, 0.0, s),
        rotation=(0.0, 0.0, s, s),
    )
    result = run((0.0, 0.0, 0.5), colliders=(collider,))
    assert result.state.next_position == pytest.approx((1.25, 0.0, 0.5), abs=3e-7)
    assert result.state.collision_normal == pytest.approx((1.0, 0.0, 0.0), abs=3e-7)


def test_sphere_surface_double_normal_and_projection_single_normal_differ():
    position = (0.1, 0.2, 0.3)
    length = math.sqrt((0.2 * 0.2 + 0.1 * 0.1) + 0.3 * 0.3)
    normal = tuple(component * (1.0 / length) for component in position)
    narrowed = tuple(_single(component) for component in normal)
    surface = tuple(component * 1.25 for component in normal)
    delta = tuple(position[i] - surface[i] for i in range(3))
    dot = (delta[1] * narrowed[1] + delta[0] * narrowed[0]) + delta[2] * narrowed[2]
    normal_squared = _single(
        _single(_single(narrowed[1] ** 2) + _single(narrowed[0] ** 2))
        + _single(narrowed[2] ** 2)
    )
    gain = min(1.0, _single(math.sqrt(normal_squared)))
    expected = tuple(position[i] + (-narrowed[i] * dot) * gain for i in range(3))
    assert run(position).state.next_position == expected


def test_positive_spring_sphere_distance_is_tripled_before_near_threshold():
    result = run((0.0, 1.375, 0.0), flag=0x2000, base=(0.0, 1.375, 0.0), friction=0.3)
    assert result.penetrating_contacts == 0
    assert result.state.next_position == (0.0, 1.375, 0.0)
    assert result.state.friction == 0.3
    assert result.state.collision_normal == ZERO
    assert result.writes == ("collision_normal", "next_position")


def test_positive_near_contact_updates_friction_without_moving_particle():
    result = run((0.0, 1.375, 0.0))
    assert result.state.next_position == (0.0, 1.375, 0.0)
    assert result.penetrating_contacts == 0
    assert result.state.friction == 0.5
    assert result.state.collision_normal == (0.0, 1.0, 0.0)


def test_existing_higher_friction_is_not_reduced():
    assert run((0.0, 1.375, 0.0), friction=0.75).state.friction == 0.75


def test_near_boundary_includes_equal_radius_and_publishes_normal():
    result = run((0.0, 1.5, 0.0))
    assert result.state.friction == 0.0
    assert result.state.collision_normal == (0.0, 1.0, 0.0)
    assert result.penetrating_contacts == 0


def test_exact_surface_counts_as_penetrating_even_with_zero_correction():
    result = run((0.0, 1.25, 0.0), flag=0x2000, limit=0.0, base=(0.0, 1.25, 0.0))
    assert result.penetrating_contacts == 1
    assert result.state.next_position == (0.0, 1.25, 0.0)
    assert result.writes[-1] == "velocity_position"


def test_every_collider_reads_original_particle_before_averaging():
    colliders = (
        work(old_a=(-0.5, 0.0, 0.0), next_a=(-0.5, 0.0, 0.0)),
        work(old_a=(0.0, -0.5, 0.0), next_a=(0.0, -0.5, 0.0)),
    )
    result = run(ZERO, colliders=colliders)
    gain = _single(0.5**0.5)
    assert result.state.next_position == (0.375 * gain, 0.375 * gain, 0.0)
    assert result.penetrating_contacts == 2
    assert result.state.collision_normal == pytest.approx((gain, gain, 0.0), abs=6e-8)


def test_opposing_contacts_cancel_normals_and_do_not_raise_friction():
    colliders = (
        work(old_a=(-0.5, 0.0, 0.0), next_a=(-0.5, 0.0, 0.0)),
        work(old_a=(0.5, 0.0, 0.0), next_a=(0.5, 0.0, 0.0)),
    )
    result = run(ZERO, colliders=colliders, flag=0x2000, base=ZERO, friction=0.3)
    assert result.state.next_position == ZERO
    assert result.state.velocity_position == (7.0, 8.0, 9.0)
    assert result.state.collision_normal == ZERO
    assert result.state.friction == 0.3  # No friction buffer write on cancellation.


def test_spring_sphere_limit_and_085_return_lerp_drive_velocity_correction():
    result = run(flag=0x2000, limit=0.125, attribute=1)
    expected = 0.625 + (0.5 - 0.625) * (0.5 * _single(0.85))
    assert result.state.next_position == (0.0, expected, 0.0)
    assert result.state.velocity_position == (7.0, 8.0 + (expected - 0.5), 9.0)
    assert result.penetrating_contacts == 1


def test_spring_capsule_has_no_sphere_only_limit_or_return_lerp():
    collider = work(
        2,
        old_a=(0.0, -1.0, 0.0),
        old_b=(0.0, 1.0, 0.0),
        next_a=(0.0, -1.0, 0.0),
        next_b=(0.0, 1.0, 0.0),
    )
    result = run(
        (0.5, 0.0, 0.0),
        colliders=(collider,),
        flag=0x2000,
        limit=0.125,
        base=(0.5, 0.0, 0.0),
    )
    assert result.state.next_position == (1.25, 0.0, 0.0)
    assert result.state.velocity_position == (7.75, 8.0, 9.0)


@pytest.mark.parametrize("attribute", [0, 4, 8, 16, 18, 1])
def test_source_attribute_gates_preserve_all_buffers(attribute):
    result = run(attribute=attribute)
    assert result.writes == ()
    assert result.state.collision_normal == (9.0, 9.0, 9.0)


def test_team_flag_is_64_bit_and_unrelated_bits_are_not_process_gates():
    assert run(flag=1 << 61).state.next_position == (0.0, 1.25, 0.0)


@pytest.mark.parametrize("flag", [0x01, 0x11, 0x21])
def test_disabled_or_invalid_collider_is_skipped_before_work_inputs(flag):
    collider = work(flag=flag, old_a=(float("nan"), 0.0, 0.0))
    result = run(colliders=(collider,))
    assert result.state.next_position == (0.0, 0.5, 0.0)
    assert result.state.collision_normal == ZERO
    assert result.state.friction == 0.0
    assert result.writes == ("collision_normal", "next_position")


def test_chunk_selects_original_global_collider_slice_only():
    colliders = (
        work(old_a=(float("nan"), 0.0, 0.0)),
        work(),
        work(old_a=(float("nan"), 0.0, 0.0)),
    )
    assert run(colliders=colliders, start=1, count=1).state.next_position == (
        0.0,
        1.25,
        0.0,
    )


def test_zero_colliders_preserves_buffers_before_mode_or_curve_reads():
    result = run(colliders=(), count=0, mode=2, radius=float("nan"))
    assert result.writes == ()
    assert result.state.collision_normal == (9.0, 9.0, 9.0)


def test_far_no_collision_clears_normal_but_keeps_existing_friction():
    result = run((0.0, 10.0, 0.0), friction=0.4)
    assert result.state.friction == 0.4
    assert result.state.collision_normal == ZERO


def test_no_hit_does_not_add_zero_correction_or_destroy_signed_zero():
    result = run((-0.0, 10.0, -0.0))
    assert math.copysign(1.0, result.state.next_position[0]) == -1.0
    assert math.copysign(1.0, result.state.next_position[2]) == -1.0


def test_native_aabb_overlap_retains_asymmetric_z_comparison():
    # The first <= z lane compares maxB.z with itself; x/y are ordinary comparisons.
    collider = work(
        old_a=(0.0, 0.0, 10.0),
        next_a=(0.0, 0.0, 10.0),
        aabb_min=(-1.0, -1.0, -1.0),
        aabb_max=(1.0, 1.0, 1.0),
    )
    result = run((0.0, 0.0, 10.5), colliders=(collider,))
    assert result.state.next_position == (0.0, 0.0, 11.25)
    reverse = run((0.0, 0.0, -10.5), colliders=(collider,))
    assert reverse.penetrating_contacts == 0


def test_aabb_expansion_adds_radius_twice_and_includes_equal_boundary():
    collider = work(aabb_min=(0.0, 0.0, 0.0), aabb_max=(0.0, 0.0, 0.0))
    assert run((0.0, 0.5, 0.0), colliders=(collider,)).penetrating_contacts == 1
    assert run((0.0, 0.50000001, 0.0), colliders=(collider,)).penetrating_contacts == 0


def test_radius_curve_floor_then_single_scale_ratio():
    result = run(radius=-1.0, scale=2.0)
    expected = _single(1.0 + _single(_single(1e-4) * 2.0))
    assert result.state.next_position == (0.0, expected, 0.0)


def test_zero_scale_does_not_read_existing_friction_in_contact():
    result = run(scale=0.0, friction=float("nan"))
    assert result.state.next_position == (0.0, 1.0, 0.0)
    assert result.state.collision_normal == (0.0, 1.0, 0.0)
    assert result.state.friction != result.state.friction


def test_sphere_spring_rejects_underflowed_radius_with_positive_limit():
    with pytest.raises(ValueError, match="positive sphere spring radius"):
        run(flag=0x2000, radius=0.0, limit=1e38, scale=2**-149)


@pytest.mark.parametrize("mode", [0, 2, 3])
def test_unsupported_mode_is_explicit_adapter_rejection(mode):
    with pytest.raises(ValueError, match="Point"):
        run(mode=mode)


@pytest.mark.parametrize("shape", [0, 9, 15])
def test_unsupported_enabled_shape_is_explicit_adapter_rejection(shape):
    with pytest.raises(ValueError, match="shape"):
        run(colliders=(work(shape),))


def test_zero_radial_direction_rejects_uncovered_native_nan_domain():
    with pytest.raises(ValueError, match="nonzero"):
        run(ZERO)


def test_zero_plane_normal_is_a_finite_contact_and_not_a_normalization_error():
    result = run(colliders=(work(8),), flag=0x2000, friction=0.3)
    assert result.penetrating_contacts == 1
    assert result.state.next_position == (0.0, 0.5, 0.0)
    assert result.state.velocity_position == (7.0, 8.0, 9.0)
    assert result.state.collision_normal == ZERO
    assert result.state.friction == 0.3
    assert result.writes == ("collision_normal", "next_position", "velocity_position")


def test_input_snapshot_is_not_mutated():
    state = PointCollisionState((0.0, 0.5, 0.0), ZERO, ZERO, 0.0, ZERO)
    result = point_collision_particle(
        state,
        PointCollisionTeam(0, 1.0, 0, 1),
        PointCollisionParameters(1, (0.25,) * 16, (0.125,) * 16),
        attribute=2,
        depth=0.0,
        colliders=(work(),),
    )
    assert state.next_position == (0.0, 0.5, 0.0)
    assert result.state is not state


@pytest.mark.parametrize(
    "team",
    [
        PointCollisionTeam(0, 1.0, -1, 1),
        PointCollisionTeam(0, 1.0, 0, -1),
        PointCollisionTeam(0, -1.0, 0, 1),
        PointCollisionTeam(0, 1.0, 0, 2),
    ],
)
def test_bad_adapter_chunk_or_scale_fails(team):
    state = PointCollisionState((0.0, 0.5, 0.0), ZERO, ZERO, 0.0, ZERO)
    with pytest.raises(ValueError):
        point_collision_particle(
            state,
            team,
            PointCollisionParameters(1, (0.25,) * 16, (0.125,) * 16),
            attribute=2,
            depth=0.0,
            colliders=(work(),),
        )


def test_malformed_consumed_curve_fails():
    state = PointCollisionState((0.0, 0.5, 0.0), ZERO, ZERO, 0.0, ZERO)
    with pytest.raises(ValueError, match="sixteen"):
        point_collision_particle(
            state,
            PointCollisionTeam(0, 1.0, 0, 1),
            PointCollisionParameters(1, (0.25,), (0.125,) * 16),
            attribute=2,
            depth=0.0,
            colliders=(work(),),
        )
