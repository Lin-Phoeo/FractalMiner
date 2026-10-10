"""Independent finite fixtures for the ordinary Point Job Execute body.

Expectations use hand geometry and struct-rounded Single arithmetic. They do
not treat the managed Point fallback as an independent numerical oracle.
"""

import math
import struct
import sys
from dataclasses import replace
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from official_physics_collider_job import ColliderJobState, start_collider_job
from official_physics_collider_step import ColliderStepCenter, ColliderStepTeam
from official_physics_point_collision import (
    ColliderWork,
    PointCollisionParameters,
    PointCollisionState,
    PointCollisionTeam,
)
from official_physics_point_job import (
    point_collision_job_particle,
    solve_point_collision_job_slot,
)
from official_physics_point_pass import PointPassTeam

ZERO = (0.0, 0.0, 0.0)
IDENTITY = (0.0, 0.0, 0.0, 1.0)


def single(value):
    """Independent IEEE-754 binary32 rounding, not a production helper."""
    return struct.unpack("<f", struct.pack("<f", value))[0]


def dot(a, b):
    return (a[1] * b[1] + a[0] * b[0]) + a[2] * b[2]


def normalized(value):
    reciprocal = 1 / math.sqrt(dot(value, value))
    return tuple(component * reciprocal for component in value)


def rotate(quaternion, value):
    """Hand-expanded Double cross products after narrowing quaternion only."""
    x, y, z, w = (single(component) for component in quaternion)
    tx = (y * value[2] - z * value[1]) * 2
    ty = (z * value[0] - x * value[2]) * 2
    tz = (x * value[1] - y * value[0]) * 2
    return (
        (value[0] + tx * w) + (y * tz - z * ty),
        (value[1] + ty * w) + (z * tx - x * tz),
        (value[2] + tz * w) + (x * ty - y * tx),
    )


def one_contact_projection(position, surface, normal):
    delta = tuple(position[i] - surface[i] for i in range(3))
    projection = dot(delta, normal)
    corrected = tuple(position[i] - normal[i] * projection for i in range(3))
    published = tuple(single(component) for component in normal)
    squared = single(
        single(
            single(published[1] * published[1]) + single(published[0] * published[0])
        )
        + single(published[2] * published[2])
    )
    gain = min(1, single(math.sqrt(squared)))
    return tuple(position[i] + (corrected[i] - position[i]) * gain for i in range(3))


def collider(
    shape=1,
    *,
    old_a=ZERO,
    old_b=ZERO,
    next_a=ZERO,
    next_b=ZERO,
    radii=(1.0, 1.0),
    flag=None,
    aabb_min=(-3.0, -3.0, -3.0),
    aabb_max=(3.0, 3.0, 3.0),
    inverse_old_rotation=IDENTITY,
    rotation=IDENTITY,
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


def particle(position=(0.0, 0.5, 0.0), **changes):
    value = PointCollisionState(position, (7.0, 8.0, 9.0), position, 0.0, (9, 9, 9))
    return replace(value, **changes)


def run(
    position=(0.0, 0.5, 0.0),
    *,
    works=None,
    radius=0.25,
    limit=0.125,
    scale=1.0,
    team_flag=0,
    attribute=2,
    depth=0.3,
    friction=0.0,
    velocity=(7.0, 8.0, 9.0),
    base=None,
    mode=1,
    start=0,
    count=None,
):
    works = (collider(),) if works is None else works
    return point_collision_job_particle(
        particle(
            position,
            velocity_position=velocity,
            base_position=position if base is None else base,
            friction=friction,
        ),
        PointCollisionTeam(
            team_flag, scale, start, len(works) - start if count is None else count
        ),
        PointCollisionParameters(mode, (radius,) * 16, (limit,) * 16),
        attribute=attribute,
        depth=depth,
        colliders=works,
    )


def test_sphere_axis_contact_and_single_normal_publication():
    result = run()
    assert result.state.next_position == (0.0, 1.25, 0.0)
    assert result.state.collision_normal == (0.0, 1.0, 0.0)
    assert result.state.velocity_position == (7.0, 8.0, 9.0)
    assert result.state.friction == 1.0
    assert result.penetrating_contacts == 1
    assert result.writes == ("friction", "collision_normal", "next_position")


def test_sphere_reads_old_direction_and_next_double_center():
    result = run((0.5, 0.0, 0.0), works=(collider(next_a=(1.0, 0.0, 0.0)),))
    assert result.state.next_position == (2.25, 0.0, 0.0)


def test_sphere_adds_widened_single_radii_in_double_not_single():
    radius = single(0.1)
    collider_radius = single(0.2)
    expected = radius + collider_radius
    result = run(
        (0, 0.15, 0), radius=radius, works=(collider(radii=(collider_radius, 1)),)
    )
    assert result.state.next_position == (0, expected, 0)
    assert expected != single(radius + collider_radius)


def test_sphere_projects_with_double_normal_not_published_single_normal():
    position = (0.1, 0.2, 0.3)
    normal = normalized(position)
    surface = tuple(component * 1.25 for component in normal)
    expected = one_contact_projection(position, surface, normal)
    narrowed_projection = one_contact_projection(
        position, surface, tuple(single(component) for component in normal)
    )
    result = run(position)
    assert result.state.next_position == expected
    assert result.state.next_position != narrowed_projection


def test_radius_curve_floor_and_scale_are_single_before_double_surface_sum():
    radius = single(single(1e-4) * single(2))
    expected = 1 + radius
    result = run(radius=-1, scale=2)
    assert result.state.next_position == (0, expected, 0)
    assert expected != single(expected)


def test_sphere_world_positions_remain_double_at_large_origin():
    origin = 1e12
    work = collider(
        old_a=(origin, 0.0, 0.0),
        next_a=(origin + 0.125, 0.0, 0.0),
        aabb_min=(origin - 2, -2, -2),
        aabb_max=(origin + 2, 2, 2),
    )
    assert run((origin + 0.5, 0.0, 0.0), works=(work,)).state.next_position == (
        origin + 1.375,
        0.0,
        0.0,
    )


@pytest.mark.parametrize("shape", range(2, 8))
def test_all_capsule_nibbles_consume_original_endpoints(shape):
    work = collider(
        shape,
        old_a=(0.0, -1.0, 0.0),
        old_b=(0.0, 1.0, 0.0),
        next_a=(0.0, -1.0, 0.0),
        next_b=(0.0, 1.0, 0.0),
    )
    assert run((0.5, 0.0, 0.0), works=(work,)).state.next_position == (1.25, 0, 0)


def test_capsule_taper_selects_projection_interpolated_radius():
    work = collider(
        2,
        old_a=(0.0, -1.0, 0.0),
        old_b=(0.0, 1.0, 0.0),
        next_a=(0.0, -1.0, 0.0),
        next_b=(0.0, 1.0, 0.0),
        radii=(0.5, 1.5),
    )
    assert run((0.5, 0.5, 0.0), works=(work,)).state.next_position == (1.5, 0.5, 0)


def test_capsule_degenerate_segment_uses_start_radius():
    work = collider(2, radii=(0.5, 1.5))
    assert run((0.25, 0.0, 0.0), works=(work,)).state.next_position == (0.75, 0, 0)


def test_capsule_adds_single_taper_and_single_particle_radius_as_double():
    radius = single(0.1)
    taper = single(
        single(single(single(0.3) - single(0.2)) * single(0.5)) + single(0.2)
    )
    result = run(
        (0.125, 0, 0),
        radius=radius,
        works=(
            collider(
                2,
                old_a=(0, -1, 0),
                old_b=(0, 1, 0),
                next_a=(0, -1, 0),
                next_b=(0, 1, 0),
                radii=(0.2, 0.3),
            ),
        ),
    )
    assert result.state.next_position == (taper + radius, 0, 0)
    assert taper + radius != single(taper + radius)


def test_capsule_projection_fraction_narrows_but_radial_and_projection_do_not():
    position = (0.5, 1, 0)
    fraction = single(1 / 3)
    center = (0, 3 * fraction, 0)
    radial = tuple(position[i] - center[i] for i in range(3))
    normal = normalized(radial)
    taper = single(single(single(1.5 - 0.5) * fraction) + 0.5)
    combined = taper + 0.25
    surface = tuple(center[i] + normal[i] * combined for i in range(3))
    expected = one_contact_projection(position, surface, normal)
    work = collider(2, old_b=(0, 3, 0), next_b=(0, 3, 0), radii=(0.5, 1.5))
    result = run(position, works=(work,))
    assert result.state.next_position == expected
    assert result.state.next_position[1] != 1


def test_capsule_two_rotations_preserve_double_radial_and_are_not_commuted():
    position = (0.2000000007, 0.375, 0.3000000009)
    inverse = (0.25, 0.125, -0.125, 0.875)
    rotation = (-0.125, 0.25, 0.375, 0.75)
    old_a, old_b = (0, -1, 0), (0, 1, 0)
    fraction = single((position[1] + 1) / 2)
    center = (0, -1 + 2 * fraction, 0)
    radial = tuple(position[i] - center[i] for i in range(3))
    normal = normalized(rotate(rotation, rotate(inverse, radial)))
    surface = tuple(center[i] + normal[i] * 1.25 for i in range(3))
    expected = one_contact_projection(position, surface, normal)
    swapped_normal = normalized(rotate(inverse, rotate(rotation, radial)))
    swapped_surface = tuple(center[i] + swapped_normal[i] * 1.25 for i in range(3))
    work = collider(
        2,
        old_a=old_a,
        old_b=old_b,
        next_a=old_a,
        next_b=old_b,
        inverse_old_rotation=inverse,
        rotation=rotation,
    )
    result = run(position, works=(work,))
    assert result.state.next_position == expected
    assert expected != one_contact_projection(position, swapped_surface, swapped_normal)


def test_capsule_spring_has_no_sphere_limit_or_return_lerp():
    work = collider(
        2,
        old_a=(0.0, -1.0, 0.0),
        old_b=(0.0, 1.0, 0.0),
        next_a=(0.0, -1.0, 0.0),
        next_b=(0.0, 1.0, 0.0),
    )
    result = run((0.5, 0, 0), works=(work,), team_flag=0x2000, limit=0.125)
    assert result.state.next_position == (1.25, 0, 0)
    assert result.state.velocity_position == (7.75, 8.0, 9.0)


def test_plane_ignores_aabb_secondary_points_and_rotations():
    work = collider(
        8,
        old_a=(0.0, 1.0, 0.0),
        old_b=(math.nan,) * 3,
        next_b=(math.nan,) * 3,
        aabb_min=(math.nan,) * 3,
        aabb_max=(math.nan,) * 3,
        inverse_old_rotation=(math.nan,) * 4,
        rotation=(math.nan,) * 4,
    )
    assert run((0, -0.5, 0), works=(work,)).state.next_position == (0, 0.25, 0)


def test_plane_nonunit_normal_is_not_normalized_before_projection():
    result = run(ZERO, works=(collider(8, old_a=(0, 2, 0)),))
    assert result.state.next_position == (0, 2, 0)
    assert result.state.collision_normal == (0, 1, 0)


def test_plane_surface_and_projection_keep_double_normal_before_publication():
    normal_y = 1 + 2**-25
    result = run(ZERO, works=(collider(8, old_a=(0, normal_y, 0)),))
    projected_y = normal_y * ((normal_y * 0.25) * normal_y)
    assert result.state.next_position == (0, projected_y, 0)
    assert projected_y != normal_y * 0.25
    assert result.state.collision_normal == (0, 1, 0)


def test_spring_velocity_keeps_unattenuated_noncollinear_average():
    works = (collider(8, old_a=(1, 0, 0)), collider(8, old_a=(0, 1, 0)))
    result = run((-0.5, -0.5, 0), works=works, team_flag=0x2000)
    gain = single(math.sqrt(single(0.5)))
    assert result.penetrating_contacts == 2
    assert result.state.next_position == (-0.5 + 0.375 * gain, -0.5 + 0.375 * gain, 0)
    assert result.state.velocity_position == (7.375, 8.375, 9)


def test_ordinary_noncollinear_contact_attenuates_position_only():
    works = (collider(8, old_a=(1, 0, 0)), collider(8, old_a=(0, 1, 0)))
    result = run((-0.5, -0.5, 0), works=works)
    gain = single(math.sqrt(single(0.5)))
    assert result.state.next_position == (-0.5 + 0.375 * gain, -0.5 + 0.375 * gain, 0)
    assert result.state.velocity_position == (7, 8, 9)


def test_opposing_penetrations_clear_position_and_velocity_correction():
    works = (collider(8, old_a=(1, 0, 0)), collider(8, old_a=(-1, 0, 0)))
    result = run(ZERO, works=works, team_flag=0x2000, friction=0.3)
    assert result.penetrating_contacts == 2
    assert result.state.next_position == ZERO
    assert result.state.velocity_position == (7, 8, 9)
    assert result.state.friction == 0.3
    assert result.state.collision_normal == ZERO
    assert result.writes == ("collision_normal", "next_position", "velocity_position")


def test_zero_plane_normal_contact_does_not_divide_or_raise():
    result = run(works=(collider(8),), team_flag=0x2000, friction=0.3)
    assert result.penetrating_contacts == 1
    assert result.state.next_position == (0, 0.5, 0)
    assert result.state.velocity_position == (7, 8, 9)
    assert result.state.collision_normal == ZERO
    assert result.state.friction == 0.3


def test_sub_epsilon_hit_normal_clears_both_spring_corrections():
    result = run(
        ZERO,
        works=(collider(8, old_a=(single(1e-9), 0, 0)),),
        team_flag=0x2000,
        friction=0.3,
    )
    assert result.penetrating_contacts == 1
    assert result.state.next_position == ZERO
    assert result.state.velocity_position == (7, 8, 9)
    assert result.state.friction == 0.3
    assert result.state.collision_normal == (single(1e-9), 0, 0)


def test_all_contacts_read_original_position_instead_of_serially_corrected_position():
    works = (
        collider(old_a=(-0.5, 0, 0), next_a=(-0.5, 0, 0)),
        collider(old_a=(0, -0.5, 0), next_a=(0, -0.5, 0)),
    )
    result = run(ZERO, works=works)
    gain = single(math.sqrt(single(0.5)))
    assert result.penetrating_contacts == 2
    assert result.state.next_position == (0.375 * gain, 0.375 * gain, 0)


def test_far_particle_clears_contact_normal_but_preserves_friction_and_velocity():
    result = run((0, 10, 0), friction=0.4)
    assert result.penetrating_contacts == 0
    assert result.state.friction == 0.4
    assert result.state.collision_normal == ZERO
    assert result.state.velocity_position == (7, 8, 9)


def test_no_hit_keeps_double_position_signed_zero_representation():
    result = run((-0.0, 10, -0.0))
    assert math.copysign(1, result.state.next_position[0]) == -1
    assert math.copysign(1, result.state.next_position[2]) == -1


def test_sphere_aabb_has_observed_asymmetric_z_lane():
    work = collider(
        old_a=(0, 0, 10),
        next_a=(0, 0, 10),
        aabb_min=(-1, -1, -1),
        aabb_max=(1, 1, 1),
    )
    assert run((0, 0, 10.5), works=(work,)).state.next_position == (0, 0, 11.25)
    assert run((0, 0, -10.5), works=(work,)).penetrating_contacts == 0


def test_aabb_expands_particle_radius_twice_and_includes_boundary():
    work = collider(aabb_min=ZERO, aabb_max=ZERO)
    assert run((0, 0.5, 0), works=(work,)).penetrating_contacts == 1
    assert run((0, 0.50000001, 0), works=(work,)).penetrating_contacts == 0


@pytest.mark.parametrize("attribute", [0, 4, 8, 16, 18, 1])
def test_ordinary_attribute_gates_do_not_write_buffers(attribute):
    result = run(attribute=attribute)
    assert result.writes == ()
    assert result.state.collision_normal == (9, 9, 9)


def test_fixed_spring_particle_is_solved_without_ordinary_movable_gate():
    result = run(attribute=1, team_flag=0x2000, works=(collider(8, old_a=(0, 1, 0)),))
    assert result.writes == ("friction", "collision_normal", "next_position")
    assert result.state.friction == 0
    assert result.state.collision_normal == (0, 1, 0)


@pytest.mark.parametrize("team_flag", [0, 1 << 61, 0x80000, 0x800, 0x10])
def test_team_process_flags_are_not_added_to_particle_job(team_flag):
    assert run(team_flag=team_flag).state.next_position == (0, 1.25, 0)


@pytest.mark.parametrize("flag", [0x01, 0x11, 0x21])
def test_inactive_collider_skips_nonfinite_geometry(flag):
    result = run(works=(collider(flag=flag, old_a=(math.nan,) * 3),))
    assert result.penetrating_contacts == 0
    assert result.state.next_position == (0, 0.5, 0)


def test_global_collider_chunk_skips_unselected_work():
    works = (
        collider(old_a=(math.nan,) * 3),
        collider(),
        collider(old_a=(math.nan,) * 3),
    )
    assert run(works=works, start=1, count=1).state.next_position == (0, 1.25, 0)


def test_empty_collider_chunk_returns_before_mode_or_curve_reads():
    result = run(works=(), count=0, mode=2, radius=math.nan, limit=math.nan)
    assert result.writes == ()
    assert result.state.collision_normal == (9, 9, 9)


def test_sphere_spring_limit_and_return_lerp_have_hand_computed_result():
    result = run(team_flag=0x2000, attribute=1)
    expected = 0.625 + (0.5 - 0.625) * (0.5 * single(0.85))
    assert result.state.next_position == (0, expected, 0)
    assert result.state.velocity_position == (7, 8 + (expected - 0.5), 9)


def test_sphere_spring_below_large_limit_still_applies_return_lerp():
    result = run(team_flag=0x2000, limit=2)
    expected = 1.25 + (0.5 - 1.25) * single(0.85)
    assert result.state.next_position == (0, expected, 0)
    assert result.state.velocity_position == (7, 8 + (expected - 0.5), 9)


def test_sphere_spring_underflowed_radius_with_positive_limit_is_adapter_rejection():
    with pytest.raises(ValueError, match="positive sphere spring radius"):
        run(team_flag=0x2000, radius=0, limit=1e38, scale=2**-149)


@pytest.mark.parametrize("depth", [-0.01, 0.37, 1.2])
def test_particle_radius_curve_uses_single_depth_and_original_time_fraction(depth):
    values = tuple(1 + i * 0.0625 for i in range(16))
    time = single(depth)
    index = math.trunc(single(min(1, max(0, time)) * 15))
    interval = single(1 / 15)
    fraction = single(single(time - single(index * interval)) / interval)
    i0, i1 = min(15, max(0, index)), min(15, max(0, index + 1))
    curve = single(values[i0] + single(single(values[i1] - values[i0]) * fraction))
    radius = single(single(0.3) * curve)
    result = point_collision_job_particle(
        particle(ZERO),
        PointCollisionTeam(0, 0.3, 0, 1),
        PointCollisionParameters(1, values, (math.nan,) * 16),
        attribute=2,
        depth=depth,
        colliders=(collider(8, old_a=(0, 1, 0)),),
    )
    assert result.state.next_position == (0, radius, 0)


def test_near_contact_friction_uses_distance_over_particle_radius():
    result = run((0, 1.375, 0))
    assert result.penetrating_contacts == 0
    assert result.state.next_position == (0, 1.375, 0)
    assert result.state.friction == 0.5
    assert result.state.collision_normal == (0, 1, 0)


def test_larger_existing_friction_is_kept_after_single_read():
    result = run((0, 1.375, 0), friction=0.9)
    assert result.state.friction == single(0.9)


def test_zero_scale_does_not_consume_existing_friction_when_radius_is_zero():
    result = run(scale=0, friction=math.nan)
    assert result.state.next_position == (0, 1, 0)
    assert math.isnan(result.state.friction)
    assert "friction" not in result.writes


@pytest.mark.parametrize("shape", [0, 9, 15])
def test_unsupported_enabled_shape_is_adapter_rejection(shape):
    with pytest.raises(ValueError, match="shape"):
        run(works=(collider(shape),))


@pytest.mark.parametrize("mode", [0, 2, 3])
def test_nonpoint_particle_mode_is_adapter_rejection(mode):
    with pytest.raises(ValueError):
        run(mode=mode)


def test_input_state_is_immutable_and_unwritten_base_is_identical():
    original = particle()
    result = point_collision_job_particle(
        original,
        PointCollisionTeam(0, 1, 0, 1),
        PointCollisionParameters(1, (0.25,) * 16, (math.nan,) * 16),
        attribute=2,
        depth=0.3,
        colliders=(collider(),),
    )
    assert original.next_position == (0, 0.5, 0)
    assert result.state is not original
    assert result.state.base_position is original.base_position


@pytest.mark.parametrize(
    "shape,position,expected",
    [
        (1, (1e12 + 0.5, 0, 0), (1e12 + 1.25, 0, 0)),
        (3, (1e12 + 0.5, 0, 0), (1e12 + 1.25, 0, 0)),
        (8, (1e12, -0.5, 0), (1e12, 0.25, 0)),
    ],
)
def test_distinct_double_collider_production_feeds_job_consumer(
    shape, position, expected
):
    origin = (1e12, 0, 0)
    original = ColliderJobState(
        flag=0x30 | shape,
        frame_position=origin,
        frame_rotation=IDENTITY,
        frame_scale=(1, 1, 1),
        old_frame_position=origin,
        old_frame_rotation=IDENTITY,
        now_position=ZERO,
        now_rotation=IDENTITY,
        old_position=origin,
        old_rotation=IDENTITY,
        size=(1, 1, 4),
        work=None,
    )
    produced = start_collider_job(
        original, ColliderStepTeam(1), ColliderStepCenter(0, 1)
    )
    assert produced.state.work is not None
    result = run(position, works=(produced.state.work,))
    assert result.state.next_position == expected
    assert original.work is None


def slot_fixture():
    sentinel = particle((99, 98, 97))
    return {
        "states": (sentinel, sentinel, sentinel, particle(), sentinel, particle()),
        "teams": {
            1: PointPassTeam(0, 1, 6, 2, 1, 1),
            2: PointPassTeam(0, 2, 10, 5, 1, 1),
        },
        "parameters": {
            1: PointCollisionParameters(1, (0.25,) * 16, (0.125,) * 16),
            2: PointCollisionParameters(1, (0.25,) * 16, (0.125,) * 16),
        },
        "step_particle_indices": (5, 3),
        "team_ids": (0, 0, 0, 1, 0, 2),
        "attributes": (0,) * 7 + (2,) + (0,) * 2 + (2,),
        "depths": (0.3,) * 11,
        "colliders": (object(), collider(), object()),
    }


def test_job_ordinal_resolves_sparse_particle_signed_team_and_proxy_index():
    args = slot_fixture()
    result = solve_point_collision_job_slot(**args, slot=0)
    assert (result.slot, result.particle_index, result.team_id, result.proxy_index) == (
        0,
        5,
        2,
        10,
    )
    assert result.result is not None
    assert result.result.state.next_position == (0, 1.5, 0)
    assert args["states"][5].next_position == (0, 0.5, 0)


@pytest.mark.parametrize("team_id", [0, -1, -32768, 32767])
def test_zero_and_signed_team_ids_retain_map_identity(team_id):
    args = slot_fixture()
    args["step_particle_indices"] = (3,)
    args["team_ids"] = (0, 0, 0, team_id)
    args["teams"] = {team_id: args["teams"][1]}
    args["parameters"] = {team_id: args["parameters"][1]}
    visit = solve_point_collision_job_slot(**args, slot=0)
    assert visit.team_id == team_id
    assert visit.result is not None
    assert visit.result.state.next_position == (0, 1.25, 0)


def test_job_empty_count_skips_parameters_chunks_numeric_state_and_proxy():
    visit = solve_point_collision_job_slot(
        (),
        {1: PointPassTeam(-1, math.nan, -1, -1, -1, 0)},
        {},
        step_particle_indices=(3,),
        team_ids=(0, 0, 0, 1),
        attributes=(),
        depths=(),
        colliders=(),
        slot=0,
    )
    assert visit.status == "empty-team-colliders"
    assert visit.result is None and visit.writes == () and visit.proxy_index is None


def test_job_nonempty_team_requires_explicit_parameters():
    args = slot_fixture()
    args["parameters"] = {}
    with pytest.raises(ValueError, match="ClothParameters"):
        solve_point_collision_job_slot(**args, slot=0)


@pytest.mark.parametrize("mode", [-2147483648, -1, 0, 2, 2147483647])
def test_job_nonpoint_mode_skips_chunks_vertex_and_position(mode):
    visit = solve_point_collision_job_slot(
        (),
        {1: PointPassTeam(-1, math.nan, -1, -1, -1, 1)},
        {1: PointCollisionParameters(mode, (), ())},
        step_particle_indices=(3,),
        team_ids=(0, 0, 0, 1),
        attributes=(),
        depths=(),
        colliders=(),
        slot=0,
    )
    assert visit.status == "non-point-mode" and visit.writes == ()


@pytest.mark.parametrize(
    "attribute,status",
    [
        (0, "invalid-vertex"),
        (0x10, "invalid-vertex"),
        (0x12, "no-collision-vertex"),
        (1, "fixed-ordinary"),
    ],
)
def test_job_vertex_gates_skip_depth_curve_scale_and_work(attribute, status):
    args = slot_fixture()
    args["step_particle_indices"] = (3,)
    args["attributes"] = (0,) * 7 + (attribute,)
    args["depths"] = args["colliders"] = ()
    args["teams"][1] = replace(args["teams"][1], scale_ratio=math.nan)
    args["parameters"][1] = PointCollisionParameters(1, (), ())
    visit = solve_point_collision_job_slot(**args, slot=0)
    assert visit.status == status and visit.result is None and visit.writes == ()


def test_job_negative_particle_local_offset_can_resolve_valid_global_proxy():
    args = slot_fixture()
    args["teams"][1] = replace(args["teams"][1], proxy_start=9, particle_start=5)
    assert solve_point_collision_job_slot(**args, slot=1).proxy_index == 7


@pytest.mark.parametrize("slot", [-1, True, 1.0, 2])
def test_invalid_job_ordinal_is_adapter_rejection(slot):
    with pytest.raises(ValueError):
        solve_point_collision_job_slot(**slot_fixture(), slot=slot)


@pytest.mark.parametrize("team_id", [True, 1.0, -32769, 32768, 3])
def test_missing_or_out_of_domain_job_team_is_adapter_rejection(team_id):
    args = slot_fixture()
    args["team_ids"] = (0, 0, 0, team_id, 0, 2)
    with pytest.raises(ValueError):
        solve_point_collision_job_slot(**args, slot=1)


@pytest.mark.parametrize("proxy_start,particle_start", [(0, 6), (2147483647, 0)])
def test_job_proxy_negative_or_int32_wrapped_negative_is_rejected(
    proxy_start, particle_start
):
    args = slot_fixture()
    args["teams"][1] = replace(
        args["teams"][1], proxy_start=proxy_start, particle_start=particle_start
    )
    with pytest.raises(ValueError):
        solve_point_collision_job_slot(**args, slot=1)
