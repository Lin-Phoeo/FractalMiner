"""Synthetic geometric oracles, not execution of the native game/Burst solver."""

import math
import struct
import sys
from pathlib import Path
from typing import Any

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from official_physics_angles import (
    _normalized,
    angle_between,
    clamp_angle,
    friction_weight,
    from_to_rotation,
    iteration_pivot,
    limit_pair,
    restoration_pair,
    restoration_strength,
    rotate_double,
)


def s(value):
    return struct.unpack("<f", struct.pack("<f", value))[0]


def test_normalization_is_double_reciprocal_then_multiply():
    reciprocal = 1 / math.sqrt(27)
    expected = (reciprocal, reciprocal, 5 * reciprocal)
    assert expected != (1 / math.sqrt(27), 1 / math.sqrt(27), 5 / math.sqrt(27))
    assert _normalized((1, 1, 5)) == expected


@pytest.mark.parametrize(
    "a,b,angle",
    [
        ((1, 0, 0), (3, 0, 0), 0),
        ((2, 0, 0), (0, 3, 0), math.pi / 2),
        ((0, 0, 1), (0, 0, -2), math.pi),
    ],
)
def test_angle_is_double_radians_not_degrees(a, b, angle):
    assert angle_between(a, b) == pytest.approx(angle, rel=0, abs=1e-14)


def test_from_to_rotation_fraction_and_float_quaternion_boundary():
    q = from_to_rotation((1, 0, 0), (0, 1, 0), 0.5)
    v = rotate_double(q, (2, 0, 0))
    assert v == pytest.approx((math.sqrt(2), math.sqrt(2), 0), rel=0, abs=2e-7)
    full = from_to_rotation((1, 0, 0), (0, 1, 0), 1)
    assert (
        sum(value * value for value in full) != 1
    )  # Native does not normalize output.
    assert rotate_double(full, (1e8, 0, 0))[1] > 99999990


def test_near_parallel_identity_and_fraction_not_clamped():
    assert from_to_rotation((1, 0, 0), (1, 0.0002, 0), 1) == (0, 0, 0, 1)
    assert rotate_double(
        from_to_rotation((1, 0, 0), (0, 1, 0), 2), (1, 0, 0)
    ) == pytest.approx((-1, 0, 0), rel=0, abs=3e-7)


def test_antiparallel_uses_observed_signed_basis_selection():
    assert rotate_double(
        from_to_rotation((1, 0, 0), (-1, 0, 0)), (1, 0, 0)
    ) == pytest.approx((-1, 0, 0), rel=0, abs=3e-7)
    assert rotate_double(
        from_to_rotation((0, 1, 0), (0, -1, 0)), (0, 1, 0)
    ) == pytest.approx((0, -1, 0), rel=0, abs=3e-7)
    # Signed x>y && x>z, not abs-max; this direction chooses a parallel basis.
    # Reject in our finite adapter, don't invent a new official fallback axis.
    with pytest.raises(ValueError):
        from_to_rotation((-1, 0, 0), (1, 0, 0))


def test_clamp_angle_preserves_magnitude_and_in_range_input():
    limited = clamp_angle((2, 0, 0), (0, 1, 0), math.pi / 4)
    assert limited.changed
    assert limited.direction == pytest.approx(
        (math.sqrt(2), math.sqrt(2), 0), rel=0, abs=3e-7
    )
    unchanged = clamp_angle((2, 0, 0), (0, 1, 0), math.pi / 2)
    assert not unchanged.changed and unchanged.direction == (2, 0, 0)
    near = clamp_angle((1, 0.0002, 0), (1, 0, 0), 0)
    assert not near.changed  # Native near-parallel epsilon bypasses rotation.


def test_clamp_antiparallel_and_bad_adapter_domain():
    assert clamp_angle((1, 0, 0), (-1, 0, 0), math.pi / 2).direction == pytest.approx(
        (0, 1, 0), rel=0, abs=3e-7
    )
    with pytest.raises(ValueError):
        clamp_angle((-1, 0, 0), (1, 0, 0), 0)
    with pytest.raises(ValueError):
        clamp_angle((1, 0, 0), (0, 1, 0), -1)


@pytest.mark.parametrize("iteration,expected", [(0, s(0.1)), (1, s(0.3)), (2, 0.5)])
def test_three_iteration_pivots_preserve_single_operation_order(iteration, expected):
    assert iteration_pivot(iteration) == expected


@pytest.mark.parametrize("iteration", [-1, 3, True, 0.5])
def test_iteration_is_validated_not_repeated_or_silently_clamped(iteration):
    with pytest.raises(ValueError):
        iteration_pivot(iteration)


@pytest.mark.parametrize("friction,expected", [(0, 1), (1, 0.25), (0.5, s(0.4))])
def test_angle_friction_has_no_depth_squared_mass_term(friction, expected):
    assert friction_weight(friction) == expected


def test_strength_clamps_before_and_after_power_then_applies_gravity():
    assert (
        restoration_strength(
            (3,) * 16, 1, power_w=0.5, gravity_falloff=0.5, gravity_dot=0
        )
        == 0.25
    )
    assert (
        restoration_strength(
            (0.5,) * 16, 1, power_w=3, gravity_falloff=1, gravity_dot=0
        )
        == 0
    )
    assert (
        restoration_strength(
            (0.5,) * 16, 1, power_w=3, gravity_falloff=0, gravity_dot=0
        )
        == 1
    )
    assert (
        restoration_strength(
            (0.5,) * 16, 1, power_w=1, gravity_falloff=1, gravity_dot=2
        )
        == 1
    )  # no final clamp after gravity


def test_gravity_uses_rounded_complement_not_original_falloff():
    # S(1-S(1e-8)) is 1, so S(1-gap) is zero, not S(1e-8).
    assert (
        restoration_strength(
            (1,) * 16, 1, power_w=1, gravity_falloff=1e-8, gravity_dot=1e8
        )
        == 1
    )


def test_parent_has_its_own_friction_weight_without_normalizing_sum():
    full = restore()
    resisted = restore(parent_friction=1, iteration=1)
    middle = restore(iteration=1)
    assert resisted.child_correction == middle.child_correction
    assert resisted.parent_correction == pytest.approx(
        tuple(x * 0.25 for x in middle.parent_correction), rel=0, abs=1e-14
    )
    assert full.child_position != middle.child_position


def restore(**kwargs):
    return restoration_pair(
        (1, 0, 0),
        (0, 0, 0),
        (5, 6, 7),
        (8, 9, 10),
        (0, 1, 0),
        converted_stiffness_curve=kwargs.pop("curve", (1,) * 16),
        depth=1,
        power_w=1,
        gravity_falloff=0,
        gravity_dot=0,
        iteration=kwargs.pop("iteration", 0),
        child_friction=kwargs.pop("child_friction", 0),
        parent_friction=kwargs.pop("parent_friction", 0),
        parent_movable=kwargs.pop("parent_movable", True),
        velocity_attenuation=0.3,
        **kwargs,
    )


def test_restore_pair_moves_both_points_and_velocity_buffers():
    result = restore()
    assert result.child_position == pytest.approx((0.1, 0.9, 0), rel=0, abs=2e-7)
    assert result.parent_position == pytest.approx((0.1, -0.1, 0), rel=0, abs=2e-7)
    assert result.child_velocity_position == pytest.approx(
        tuple(a + b * s(0.3) for a, b in zip((5, 6, 7), result.child_correction)),
        rel=0,
        abs=1e-14,
    )
    assert result.parent_velocity_position == pytest.approx(
        tuple(a + b * s(0.3) for a, b in zip((8, 9, 10), result.parent_correction)),
        rel=0,
        abs=1e-14,
    )


def test_restore_pair_fixed_parent_is_not_moved_or_renormalized():
    result = restore(parent_movable=False)
    assert result.parent_position == (0, 0, 0)
    assert result.parent_velocity_position == (8, 9, 10)
    assert result.child_position == pytest.approx((0.1, 0.9, 0), rel=0, abs=2e-7)
    assert restore(child_friction=1).child_correction == pytest.approx(
        tuple(x * 0.25 for x in restore().child_correction), rel=0, abs=1e-14
    )


def test_restore_retains_large_double_origin_and_converted_curve_contract():
    assert restore(curve=(0,) * 16).child_position == pytest.approx(
        (1, 0, 0), rel=0, abs=1e-7
    )
    result = restoration_pair(
        (1e8 + 1, 0, 0),
        (1e8, 0, 0),
        (0, 0, 0),
        (0, 0, 0),
        (0, 1, 0),
        converted_stiffness_curve=(1,) * 16,
        depth=1,
        power_w=1,
        gravity_falloff=0,
        gravity_dot=0,
        iteration=2,
        child_friction=0,
        parent_friction=0,
        parent_movable=True,
        velocity_attenuation=0.3,
    )
    assert result.child_position[0] == pytest.approx(1e8 + 0.5, rel=0, abs=1e-7)


def limit(**kwargs):
    return limit_pair(
        (2, 0, 0),
        (0, 0, 0),
        (5, 6, 7),
        (8, 9, 10),
        (0, 1, 0),
        cached_length=kwargs.pop("cached_length", 2),
        limit_curve=kwargs.pop("curve", (0,) * 16),
        depth=1,
        limit_stiffness=kwargs.pop("limit_stiffness", 1),
        child_friction=kwargs.pop("child_friction", 0),
        parent_friction=0,
        parent_movable=kwargs.pop("parent_movable", True),
        **kwargs,
    )


def test_limit_pivot_and_velocity_use_independent_original_constants():
    result = limit()
    assert result.child_position == pytest.approx((0.8, 1.2, 0), rel=0, abs=3e-7)
    assert result.parent_position == pytest.approx((0.8, -0.8, 0), rel=0, abs=3e-7)
    assert result.child_velocity_position == pytest.approx(
        tuple(a + b * s(0.9) for a, b in zip((5, 6, 7), result.child_correction)),
        rel=0,
        abs=1e-14,
    )


def test_limit_half_length_correction_even_when_angle_is_in_range():
    result = limit(cached_length=4, curve=(180,) * 16)
    assert result.child_position == pytest.approx((2.6, 0, 0), rel=0, abs=2e-7)
    assert result.parent_position == pytest.approx((-0.4, 0, 0), rel=0, abs=2e-7)
    assert limit(parent_movable=False).parent_position == (0, 0, 0)


def test_limit_stiffness_softens_angle_and_independent_friction_weight():
    result = limit(limit_stiffness=0.5)
    assert result.child_position == pytest.approx(
        (0.8 + 1.2 / math.sqrt(2), 1.2 / math.sqrt(2), 0), rel=0, abs=3e-7
    )
    assert limit(child_friction=1).child_correction == pytest.approx(
        tuple(x * 0.25 for x in limit().child_correction), rel=0, abs=1e-14
    )


@pytest.mark.parametrize("invalid", [math.nan, math.inf, True, "1", 10**400])
def test_nonfinite_adapter_inputs_rejected(invalid):
    with pytest.raises(ValueError):
        friction_weight(invalid)
    with pytest.raises(ValueError):
        from_to_rotation((invalid, 0, 0), (0, 1, 0))


def test_zero_direction_negative_denominator_and_flag_adapter_guards():
    with pytest.raises(ValueError):
        angle_between((0, 0, 0), (1, 0, 0))
    malformed_quaternion: Any = (0, 0, 1)
    with pytest.raises(ValueError):
        rotate_double(malformed_quaternion, (1, 0, 0))
    with pytest.raises(ValueError):
        friction_weight(-1)
    with pytest.raises(ValueError):
        restore(parent_movable=1)
    with pytest.raises(ValueError):
        limit(cached_length=0)
