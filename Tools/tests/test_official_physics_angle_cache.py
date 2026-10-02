"""Synthetic cache/state tests, not an execution oracle for the game's DLL."""

import math
import struct
import sys
from pathlib import Path
from typing import Any

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from official_physics_angle_cache import (
    initialize_edge_cache,
    limit_cached_edge,
    multiply_quaternions,
    quaternion_inverse,
    rotate_single,
)
from official_physics_angles import from_to_rotation, restoration_pair, rotate_double


def s(value):
    return struct.unpack("<f", struct.pack("<f", value))[0]


IDENTITY = (0, 0, 0, 1)


def test_inverse_is_reciprocal_norm_squared_not_conjugate_only():
    assert quaternion_inverse((0, 0, 0, 2)) == (0, 0, 0, 0.5)
    assert quaternion_inverse((1, 2, 3, 4)) == tuple(
        s(s(v * s(1 / 30)) * sign) for v, sign in zip((1, 2, 3, 4), (-1, -1, -1, 1))
    )


def test_inverse_dot_single_addition_order_is_not_double_sum_then_cast():
    q = (10000, 2, 2, 2)
    inverse = quaternion_inverse(q)
    assert inverse[0] == s(-s(s(1 / 1e8) * 10000))
    # Each +4 rounds down at 1e8, unlike adding the small terms together first.
    assert inverse[0] != s(-s(s(1 / s(1e8 + 12)) * 10000))


def test_product_order_noncommuting_axes_and_no_normalization():
    assert multiply_quaternions((1, 0, 0, 0), (0, 1, 0, 0)) == (0, 0, 1, 0)
    assert multiply_quaternions((0, 1, 0, 0), (1, 0, 0, 0)) == (0, 0, -1, 0)
    assert multiply_quaternions((0, 0, 0, 2), (1, 2, 3, 4)) == (2, 4, 6, 8)


def test_single_product_preserves_native_grouping_not_hamilton_reassociation():
    a = (1e8, 1, -1e8, 1)
    b = (1, 1, 1, 1)
    # x = S(S(aw*bx + S(ax*bw+ay*bz)) - az*by)
    assert multiply_quaternions(a, b)[0] == 2e8
    # w = S(S(aw*bw - S(ax*bx+ay*by)) - az*bz)
    assert multiply_quaternions(a, b)[3] == 0


def test_single_rotation_does_not_use_double_then_one_final_cast():
    q = (s(0.13), s(0.27), s(0.31), s(0.73))
    v = (s(12345.7), s(-2468.1), s(0.333))
    result = rotate_single(q, v)
    # Independent cross/component Single recurrence (all boundaries explicit).
    cross = lambda a, b: tuple(
        s(s(a[j] * b[k]) - s(a[k] * b[j])) for j, k in ((1, 2), (2, 0), (0, 1))
    )
    t = tuple(s(2 * x) for x in cross(q[:3], v))
    c = cross(q[:3], t)
    expected = tuple(s(s(v[i] + s(q[3] * t[i])) + c[i]) for i in range(3))
    assert result == expected
    assert result != tuple(s(x) for x in rotate_double(q, v))


def initialize(
    *,
    parent_rotation=IDENTITY,
    child_rotation=IDENTITY,
    use_limit=True,
    use_restoration=True,
):
    return initialize_edge_cache(
        (1e8 + 2, 0, 0),
        (1e8, 0, 0),
        (5, 0, 0),
        (1, 0, 0),
        parent_rotation,
        child_rotation,
        use_limit=use_limit,
        use_restoration=use_restoration,
    )


def test_cache_uses_basic_direction_but_current_next_distance():
    cache = initialize()
    assert cache.local_direction == (1, 0, 0)
    assert cache.local_rotation == IDENTITY
    assert cache.cached_length == 4
    assert cache.restoration_world_vector == (2, 0, 0)  # not normalized


@pytest.mark.parametrize(
    "limit,restore", [(False, False), (False, True), (True, False), (True, True)]
)
def test_each_flag_owns_only_its_own_cache(limit, restore):
    cache = initialize(use_limit=limit, use_restoration=restore)
    assert (cache.local_direction is not None) == limit
    assert (cache.local_rotation is not None) == limit
    assert (cache.cached_length is not None) == limit
    assert (cache.restoration_world_vector is not None) == restore


def test_local_direction_uses_inverse_parent_but_restoration_remains_world():
    q = from_to_rotation((1, 0, 0), (0, 1, 0))
    cache = initialize(parent_rotation=q, child_rotation=q)
    assert cache.local_direction == pytest.approx((0, -1, 0), rel=0, abs=3e-7)
    assert cache.local_rotation == pytest.approx(IDENTITY, rel=0, abs=3e-7)
    assert cache.restoration_world_vector == (2, 0, 0)


def cached(cache=None, parent_rotation=IDENTITY):
    if cache is None:
        cache = initialize_edge_cache(
            (0, 2, 0),
            (0, 0, 0),
            (2, 0, 0),
            (0, 0, 0),
            IDENTITY,
            IDENTITY,
            use_limit=True,
            use_restoration=True,
        )
    return limit_cached_edge(
        (2, 0, 0),
        (0, 0, 0),
        (1, 2, 3),
        (4, 5, 6),
        parent_rotation,
        cache,
        limit_curve=(0,) * 16,
        depth=1,
        limit_stiffness=1,
        child_friction=0,
        parent_friction=0,
        parent_movable=False,
    )


def test_cached_limit_updates_positions_velocity_and_child_rotation():
    result = cached()
    assert result.used_world_basis == (0, 1, 0)
    assert result.pair.child_position == pytest.approx((0.8, 1.2, 0), rel=0, abs=3e-7)
    assert result.pair.parent_position == (0, 0, 0)
    predicted = rotate_double(result.child_rotation, (0, 1, 0))
    direction = result.pair.child_position
    magnitude = math.sqrt(sum(x * x for x in direction))
    assert predicted == pytest.approx(
        tuple(x / magnitude for x in direction), rel=0, abs=4e-7
    )
    assert result.pair.child_velocity_position != (1, 2, 3)


def test_parent_cache_rotation_is_used_at_call_time_not_frozen_basic_basis():
    cache = initialize_edge_cache(
        (2, 0, 0),
        (0, 0, 0),
        (2, 0, 0),
        (0, 0, 0),
        IDENTITY,
        IDENTITY,
        use_limit=True,
        use_restoration=False,
    )
    q = from_to_rotation((1, 0, 0), (0, 1, 0))
    result = cached(cache, parent_rotation=q)
    assert result.used_world_basis == pytest.approx((0, 1, 0), rel=0, abs=3e-7)
    assert result.pair.child_position[1] > 1


def test_parent_and_local_product_is_right_nested_then_left_multiplied():
    local = (1, 0, 0, 0)
    parent = (0, 1, 0, 0)
    cache = initialize_edge_cache(
        (0, 2, 0),
        (0, 0, 0),
        (2, 0, 0),
        (0, 0, 0),
        IDENTITY,
        local,
        use_limit=True,
        use_restoration=False,
    )
    # parent keeps Y as Y; allow 180deg, preserving the point correction path.
    result = limit_cached_edge(
        (2, 0, 0),
        (0, 0, 0),
        (0, 0, 0),
        (0, 0, 0),
        parent,
        cache,
        limit_curve=(180,) * 16,
        depth=1,
        limit_stiffness=1,
        child_friction=0,
        parent_friction=0,
        parent_movable=False,
    )
    expected = multiply_quaternions(
        from_to_rotation(result.used_world_basis, result.pair.child_position),
        multiply_quaternions(parent, local),
    )
    assert result.child_rotation == expected


def test_two_edges_read_updated_parent_rotation_and_position():
    first = cached()
    cache = initialize_edge_cache(
        (0, 4, 0),
        (0, 2, 0),
        (2, 2, 0),
        (2, 0, 0),
        IDENTITY,
        IDENTITY,
        use_limit=True,
        use_restoration=True,
    )
    second = limit_cached_edge(
        (2, 2, 0),
        first.pair.child_position,
        (0, 0, 0),
        first.pair.child_velocity_position,
        first.child_rotation,
        cache,
        limit_curve=(0,) * 16,
        depth=1,
        limit_stiffness=1,
        child_friction=0,
        parent_friction=0,
        parent_movable=True,
    )
    assert second.used_world_basis != (0, 1, 0)
    assert cache.local_direction is not None
    assert second.used_world_basis == rotate_single(
        first.child_rotation, cache.local_direction
    )
    assert second.pair.parent_position != first.pair.child_position
    # Zero-angle limit + identity local rotation aligns this edge to its parent.
    # Near-parallel FromTo returns identity, so the inherited rotation is equal.
    assert second.child_rotation == first.child_rotation


def test_restoration_follows_limit_but_does_not_rewrite_its_rotation_cache():
    limited = cached()
    pair = limited.pair
    restored = restoration_pair(
        pair.child_position,
        pair.parent_position,
        pair.child_velocity_position,
        pair.parent_velocity_position,
        (0, 2, 0),
        converted_stiffness_curve=(1,) * 16,
        depth=1,
        power_w=1,
        gravity_falloff=0,
        gravity_dot=0,
        iteration=0,
        child_friction=0,
        parent_friction=0,
        parent_movable=False,
        velocity_attenuation=0.3,
    )
    assert restored.child_position != pair.child_position
    assert limited.pair == pair  # immutable result; restoration has no cache write


@pytest.mark.parametrize("bad", [float("nan"), float("inf"), True, "1", 10**400])
def test_invalid_single_input_rejected(bad):
    with pytest.raises(ValueError):
        quaternion_inverse((bad, 0, 0, 1))


def test_adapter_rejects_zero_quaternion_bad_size_and_uninitialized_limit():
    with pytest.raises(ValueError):
        quaternion_inverse((0, 0, 0, 0))
    malformed: Any = (0, 0, 1)
    with pytest.raises(ValueError):
        multiply_quaternions(malformed, IDENTITY)
    malformed_flag: Any = 1
    with pytest.raises(ValueError):
        initialize(use_limit=malformed_flag)
    with pytest.raises(ValueError):
        cached(initialize(use_limit=False))


def test_cache_is_immutable_and_initialization_does_not_mutate_inputs():
    q = [0, 0, 0, 1]
    cache = initialize(parent_rotation=q, child_rotation=q)
    assert q == [0, 0, 0, 1]
    immutable: Any = cache
    with pytest.raises(AttributeError):
        immutable.cached_length = 99


def test_three_iterations_keep_prepass_length_and_feed_previous_result():
    cache = initialize_edge_cache(
        (0, 2, 0),
        (0, 0, 0),
        (2, 0, 0),
        (0, 0, 0),
        IDENTITY,
        IDENTITY,
        use_limit=True,
        use_restoration=True,
    )
    position, velocity = (2, 0, 0), (0, 0, 0)
    snapshots = []
    for iteration in range(3):
        result = limit_cached_edge(
            position,
            (0, 0, 0),
            velocity,
            (0, 0, 0),
            IDENTITY,
            cache,
            limit_curve=(0,) * 16,
            depth=1,
            limit_stiffness=1,
            child_friction=0,
            parent_friction=0,
            parent_movable=False,
        )
        assert cache.restoration_world_vector is not None
        restored = restoration_pair(
            result.pair.child_position,
            result.pair.parent_position,
            result.pair.child_velocity_position,
            result.pair.parent_velocity_position,
            cache.restoration_world_vector,
            converted_stiffness_curve=(0.2,) * 16,
            depth=1,
            power_w=1,
            gravity_falloff=0,
            gravity_dot=0,
            iteration=iteration,
            child_friction=0,
            parent_friction=0,
            parent_movable=False,
            velocity_attenuation=0.3,
        )
        position, velocity = restored.child_position, restored.child_velocity_position
        snapshots.append(position)
        assert cache.cached_length == 2
    assert len(set(snapshots)) == 3
    assert position[0] < snapshots[0][0]  # successive movement towards basic Y
    assert velocity != (0, 0, 0)
