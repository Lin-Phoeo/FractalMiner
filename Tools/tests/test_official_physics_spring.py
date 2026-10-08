"""Finite tests for the recovered fixed-particle Spring source flow."""

import math
import sys
from dataclasses import replace
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from official_physics_constraints import _single
from official_physics_spring import (
    ClothNormalAxis,
    SpringConstraintSettings,
    apply_spring,
)

I = (0.0, 0.0, 0.0, 1.0)


def cfg(**changes):
    return replace(SpringConstraintSettings(1.0, 1.0, 1.0, 0.0), **changes)


def apply(*, settings=None, **changes):
    values = {
        "spring_params": settings or cfg(),
        "normal_axis": ClothNormalAxis.Right,
        "next_position": (4.0, 0.0, 0.0),
        "base_position": (0.0, 0.0, 0.0),
        "base_rotation": I,
        "noise_time": 0.0,
        "scale_ratio": 1.0,
    }
    values.update(changes)
    return apply_spring(**values)


def test_full_power_returns_base_after_source_limits():
    assert apply() == (0.0, 0.0, 0.0)


def test_zero_power_keeps_the_source_limited_displacement():
    actual = apply(settings=cfg(spring_power=0.0, limit_distance=3.0))
    assert actual == pytest.approx((3.0, 0.0, 0.0), abs=1e-12)


@pytest.mark.parametrize("scale_ratio", [0.0, -1.0])
def test_nonpositive_scaled_limit_resets_to_base(scale_ratio):
    assert apply(settings=cfg(spring_power=0.0), scale_ratio=scale_ratio) == (0, 0, 0)


def test_limit_distance_is_scaled_before_the_vector_length_clamp():
    actual = apply(settings=cfg(spring_power=0.0, limit_distance=2.0), scale_ratio=1.5)
    assert actual == pytest.approx((3.0, 0.0, 0.0), abs=1e-12)


def test_normal_limit_is_an_elliptic_cross_section_not_component_clamp():
    actual = apply(
        settings=cfg(spring_power=0.0, limit_distance=5.0, normal_limit_ratio=0.5),
        normal_axis=ClothNormalAxis.Up,
        next_position=(0.0, 3.0, 4.0),
    )
    # tangent=4, so normal limit = .5 * sqrt(5² - 4²) = 1.5.
    assert actual == pytest.approx((0.0, 1.5, 4.0), abs=2e-7)


def test_normal_ratio_one_skips_the_normal_limit_branch():
    assert apply(
        settings=cfg(spring_power=0.0, limit_distance=5.0, normal_limit_ratio=1.0),
        normal_axis=ClothNormalAxis.Up,
        next_position=(0.0, 3.0, 4.0),
    ) == (0.0, 3.0, 4.0)


@pytest.mark.parametrize(
    "axis,direction",
    [
        (ClothNormalAxis.Right, (1.0, 0.0, 0.0)),
        (ClothNormalAxis.Up, (0.0, 1.0, 0.0)),
        (ClothNormalAxis.Forward, (0.0, 0.0, 1.0)),
        (ClothNormalAxis.InverseRight, (-1.0, 0.0, 0.0)),
        (ClothNormalAxis.InverseUp, (0.0, -1.0, 0.0)),
        (ClothNormalAxis.InverseForward, (0.0, 0.0, -1.0)),
    ],
)
def test_all_six_official_normal_axis_ordinals_select_the_expected_axis(
    axis, direction
):
    assert apply(
        settings=cfg(spring_power=0.0, limit_distance=2.0, normal_limit_ratio=0.0),
        normal_axis=axis,
        next_position=direction,
    ) == (0.0, 0.0, 0.0)


def test_normal_limit_keeps_a_component_already_inside_the_ellipse():
    assert apply(
        settings=cfg(spring_power=0.0, limit_distance=5.0, normal_limit_ratio=0.5),
        normal_axis=ClothNormalAxis.Up,
        next_position=(0.0, 1.0, 4.0),
    ) == (0.0, 1.0, 4.0)


def test_negative_normal_ratio_preserves_zero_component_source_sign_path():
    assert apply(
        settings=cfg(spring_power=0.0, limit_distance=5.0, normal_limit_ratio=-0.5),
        normal_axis=ClothNormalAxis.Up,
        next_position=(0.0, 0.0, 4.0),
    ) == (0.0, 0.0, 4.0)


def test_normal_axis_is_rotated_by_base_rotation_before_projection():
    # +X rotated +90° about Z becomes +Y; therefore this is the same limit as
    # the prior Y-axis fixture rather than an X-axis limit.
    half = math.sqrt(0.5)
    actual = apply(
        settings=cfg(spring_power=0.0, limit_distance=5.0, normal_limit_ratio=0.5),
        normal_axis=ClothNormalAxis.Right,
        next_position=(0.0, 3.0, 4.0),
        base_rotation=(0.0, 0.0, half, half),
    )
    # Quaternion lanes are explicitly Single in the recovered helper.
    assert actual == pytest.approx((0.0, 1.5, 4.0), abs=2e-7)


def test_noise_modulates_power_at_observed_0_point_6_amplitude():
    actual = apply(
        settings=cfg(spring_power=0.5, limit_distance=20.0, spring_noise=1.0),
        noise_time=math.pi / 2,
        next_position=(10.0, 0.0, 0.0),
    )
    # power=.5*(1 + sin(pi/2)*1*.6)=.8; output = 10*(1-.8)=2.
    assert actual == pytest.approx((2.0, 0.0, 0.0), abs=2e-7)


def test_negative_noise_modulated_power_is_zeroed_not_reflected():
    actual = apply(
        settings=cfg(spring_power=0.5, limit_distance=20.0, spring_noise=4.0),
        noise_time=-math.pi / 2,
        next_position=(10.0, 0.0, 0.0),
    )
    assert actual == pytest.approx((10.0, 0.0, 0.0), abs=1e-11)


def test_scale_ratio_is_double_in_spring_signature():
    scale = 1.0000000000001
    assert apply(settings=cfg(spring_power=0), scale_ratio=scale)[0] == scale


def test_noise_time_is_double_and_amplitude_multiplies_in_single_first():
    time, noise, power = 16777217.0, 0.123456789, 0.731234567
    p = _single(power)
    amplitude = _single(_single(noise) * _single(0.6))
    effective = ((math.sin(time) * amplitude) * p) + p
    expected = 10.0 - (10.0 * effective)
    actual = apply(
        settings=cfg(spring_power=power, limit_distance=20, spring_noise=noise),
        next_position=(10, 0, 0),
        noise_time=time,
    )
    assert actual[0] == expected


def test_negative_power_without_noise_is_preserved():
    assert apply(settings=cfg(spring_power=-0.5, limit_distance=20))[0] == 6.0


def test_final_vector_subtraction_is_not_replaced_by_one_minus_power():
    value, power = 0.1, _single(0.731234567)
    expected = value - value * power
    assert expected != value * (1 - power)
    assert (
        apply(
            settings=cfg(spring_power=power, limit_distance=20),
            next_position=(value, 0, 0),
        )[0]
        == expected
    )


@pytest.mark.parametrize("axis", [-1, 6, True, 1.5])
def test_adapter_requires_a_real_cloth_normal_axis(axis):
    with pytest.raises(ValueError, match="ClothNormalAxis"):
        apply(normal_axis=axis)


def test_adapter_requires_spring_constraint_settings():
    with pytest.raises(TypeError, match="SpringConstraintSettings"):
        apply(settings=object())


def test_adapter_requires_four_rotation_components():
    with pytest.raises(ValueError, match="four base rotation"):
        apply(base_rotation=(0.0, 0.0, 1.0))


@pytest.mark.parametrize(
    "field,value",
    [
        ("spring_power", math.nan),
        ("limit_distance", math.inf),
        ("spring_noise", math.nan),
    ],
)
def test_adapter_rejects_nonfinite_spring_parameters(field, value):
    with pytest.raises(ValueError, match="finite"):
        apply(settings=cfg(**{field: value}))
