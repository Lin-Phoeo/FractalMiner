"""Analytic/synthetic vectors, not execution of the proprietary native solver."""

import math
import struct
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from official_physics_constraints import (
    DistanceNeighbor,
    distance_particle,
    evaluate_curve,
    inverse_mass,
)


def f32(value):
    return struct.unpack("<f", struct.pack("<f", value))[0]


@pytest.mark.parametrize(
    "friction,depth,expected",
    [(0, 0, 1 / 6), (0, 1, 1), (1, 1, 1 / 4), (1, 0, 1 / 9), (0, 0.5, 1 / 2.25)],
)
def test_inverse_mass_parameter_identity_and_analytic_values(friction, depth, expected):
    assert inverse_mass(friction, depth) == f32(expected)


def test_fixed_mass_path_ignores_depth_and_friction():
    assert inverse_mass(0, 0, fixed=True, fixed_mass=50) == f32(1 / 50)
    assert inverse_mass(1, 1, fixed=True, fixed_mass=10) == f32(1 / 10)
    assert inverse_mass(-10, 7, fixed=True, fixed_mass=2) == 0.5


@pytest.mark.parametrize("time,index", [(0, 0), (1, 15), (2, 15)])
def test_curve_endpoints_use_sixteen_flattened_samples(time, index):
    assert evaluate_curve(tuple(range(16)), time) == index


def test_curve_half_segment_and_negative_extrapolation():
    samples = tuple(2 * i for i in range(16))
    assert evaluate_curve(samples, 1 / 30) == pytest.approx(1, abs=2e-7)
    assert evaluate_curve(samples, -1 / 15) == -2
    assert evaluate_curve((0.4,) * 16, 0.77) == f32(0.4)


def test_curve_single_operation_boundaries_not_naive_double_lerp():
    samples = tuple(f32(i * 0.07 + 0.1) for i in range(16))
    time = f32(0.412345)
    index = math.trunc(f32(time * 15))
    fraction = f32(f32(time - f32(index * f32(1 / 15))) / f32(1 / 15))
    expected = f32(
        samples[index] + f32(f32(samples[index + 1] - samples[index]) * fraction)
    )
    assert evaluate_curve(samples, time) == expected


def solve(neighbors, **kwargs):
    return distance_particle(
        (0, 0, 0),
        (0, 0, 0),
        (0, 0, 0),
        neighbors,
        center_inverse_mass=1,
        stiffness_curve=(1,) * 16,
        depth=1,
        simulation_power_y=1,
        rest_scale=1,
        animation_pose_ratio=kwargs.pop("animation_pose_ratio", 0),
        velocity_attenuation=kwargs.pop("velocity_attenuation", 0.3),
        **kwargs,
    )


def edge(position=(2, 0, 0), base=(1, 0, 0), rest: float = 1, mass: float = 1):
    return DistanceNeighbor(position, base, rest, mass)


def test_stretched_edge_corrects_center_toward_neighbor_and_velocity_position():
    result = solve([edge()])
    assert result.next_position == (0.5, 0, 0)
    assert result.velocity_position == (0.5 * f32(0.3), 0, 0)
    assert result.contributing_neighbors == 1


def test_compressed_edge_and_fixed_neighbor_weight():
    assert solve([edge(position=(0.5, 0, 0))]).next_position == (-0.25, 0, 0)
    assert solve([edge(mass=0.25)]).next_position == (0.8, 0, 0)


def test_signed_rest_half_stiffness_and_animation_pose_blending():
    assert solve([edge(rest=-1)]).next_position == (0.25, 0, 0)
    assert solve([edge(base=(3, 0, 0))], animation_pose_ratio=0.5).next_position == (
        0,
        0,
        0,
    )
    assert solve([edge(base=(3, 0, 0))], animation_pose_ratio=1).next_position == (
        -0.5,
        0,
        0,
    )


def test_average_valid_edges_not_sum_and_skip_only_degenerate_length():
    result = solve(
        [edge(), edge(position=(0, 2, 0), base=(0, 1, 0)), edge(position=(0, 0, 0))]
    )
    assert result.next_position == (0.25, 0.25, 0)
    assert result.contributing_neighbors == 2
    assert solve([]).next_position == (0, 0, 0)
    assert solve([edge(position=(1e-10, 0, 0))]).contributing_neighbors == 0


def test_clamp_before_and_after_power_and_negative_rest_adjustment():
    result = distance_particle(
        (0, 0, 0),
        (0, 0, 0),
        (4, 5, 6),
        [edge(rest=-1)],
        center_inverse_mass=1,
        stiffness_curve=(3,) * 16,
        depth=1,
        simulation_power_y=3,
        rest_scale=1,
        animation_pose_ratio=0,
        velocity_attenuation=0,
    )
    # clamp(curve)=1; *power=3; negative edge * .5=1.5; final clamp=1.
    assert result.next_position == (0.5, 0, 0)
    assert result.velocity_position == (4, 5, 6)
    zero = distance_particle(
        (0, 0, 0),
        (0, 0, 0),
        (0, 0, 0),
        [edge()],
        center_inverse_mass=1,
        stiffness_curve=(0,) * 16,
        depth=1,
        simulation_power_y=1,
        rest_scale=1,
        animation_pose_ratio=0,
        velocity_attenuation=0.3,
    )
    assert zero.contributing_neighbors == 1  # Valid length, even when stiffness=0.
    assert zero.correction == (0, 0, 0)


def test_rest_scale_is_single_but_position_precision_is_double():
    result = distance_particle(
        (1e8, 0, 0),
        (0, 0, 0),
        (0, 0, 0),
        [edge(position=(1e8 + 2, 0, 0))],
        center_inverse_mass=1,
        stiffness_curve=(1,) * 16,
        depth=1,
        simulation_power_y=1,
        rest_scale=1 + 2**-25,  # Rounds to exactly 1 as Single, not as Double.
        animation_pose_ratio=0,
        velocity_attenuation=0.3,
    )
    assert result.next_position[0] == 1e8 + 0.5


@pytest.mark.parametrize(
    "invalid", [math.nan, math.inf, -math.inf, True, "1", 1e40, 10**400]
)
def test_non_single_inputs_rejected_as_adapter_policy(invalid):
    with pytest.raises(ValueError):
        inverse_mass(invalid, 1)
    with pytest.raises(ValueError):
        evaluate_curve((1,) * 16, invalid)


@pytest.mark.parametrize("samples", [(), (1,) * 15, (1,) * 17, (math.nan,) * 16])
def test_bad_sample_table_rejected(samples):
    with pytest.raises(ValueError):
        evaluate_curve(samples, 0.5)


@pytest.mark.parametrize(
    "kwargs",
    [{"fixed": 1}, {"fixed_mass": 0}, {"fixed_mass": -1}, {"fixed_mass": 1e-50}],
)
def test_inverse_mass_invalid_adapter_domain(kwargs):
    with pytest.raises(ValueError):
        inverse_mass(0, 0, **kwargs)


def test_nonpositive_denominator_rejected_not_silently_clamped():
    with pytest.raises(ValueError):
        inverse_mass(-1, 1)


@pytest.mark.parametrize(
    "neighbor",
    [
        edge(position=(math.inf, 0, 0)),
        edge(position=(1, 2)),
        edge(mass=0),
        edge(rest=math.nan),
    ],
)
def test_bad_neighbor_inputs_rejected(neighbor):
    with pytest.raises(ValueError):
        solve([neighbor])


def test_overflowing_double_geometry_rejected():
    with pytest.raises(ValueError):
        solve([edge(position=(1e308, 0, 0))])


def test_zero_center_mass_rejected_instead_of_claiming_native_fixed_gate():
    with pytest.raises(ValueError):
        distance_particle(
            (0, 0, 0),
            (0, 0, 0),
            (0, 0, 0),
            [],
            center_inverse_mass=0,
            stiffness_curve=(1,) * 16,
            depth=1,
            simulation_power_y=1,
            rest_scale=1,
            animation_pose_ratio=0,
            velocity_attenuation=0.3,
        )
