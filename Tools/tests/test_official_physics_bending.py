"""Finite TriangleBending math examples; never executes the original runtime."""

import math
import struct
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from official_physics_bending import (
    METHOD_DIRECTIONAL_DIHEDRAL,
    METHOD_NONE,
    BendingParameters,
    convert_bending_parameters,
    pack_triangle_pair,
    pack_write_offsets,
    solve_dihedral,
    solve_volume,
    unpack_triangle_pair,
    unpack_write_offsets,
)
from official_physics_constraints import _single

TETRA = ((0.0, 0.0, 0.0), (1.0, 0.0, 0.0), (0.0, 1.0, 0.0), (0.0, 0.0, 1.0))
HINGE = ((0.0, 1.0, 0.0), (0.0, 0.0, 1.0), (0.0, 0.0, 0.0), (1.0, 0.0, 0.0))


@pytest.mark.parametrize(
    "vertices,word",
    [
        ((0, 1, 2, 3), 0x0000000100020003),
        ((1, 2, 3, 4), 0x0001000200030004),
        ((65535, 65534, 32768, 32767), 0xFFFFFFFE80007FFF),
    ],
)
def test_triangle_pair_is_four_unsigned_16_bit_lanes_high_to_low(vertices, word):
    assert pack_triangle_pair(*vertices) == word
    assert unpack_triangle_pair(word) == vertices


@pytest.mark.parametrize(
    "offsets,word",
    [
        ((0, 1, 2, 3), 0x00010203),
        ((1, 2, 3, 4), 0x01020304),
        ((255, 254, 128, 127), 0xFFFE807F),
    ],
)
def test_write_offsets_are_four_unsigned_bytes_high_to_low(offsets, word):
    assert pack_write_offsets(*offsets) == word
    assert unpack_write_offsets(word) == offsets


@pytest.mark.parametrize("value", [-1, 65536, True, 1.0])
def test_triangle_pair_rejects_non_uint16_vertices(value):
    with pytest.raises(ValueError):
        pack_triangle_pair(value, 0, 0, 0)


@pytest.mark.parametrize("value", [-1, 256, True, 1.0])
def test_write_offsets_reject_non_bytes(value):
    with pytest.raises(ValueError):
        pack_write_offsets(value, 0, 0, 0)


def test_serialized_parameter_convert_uses_strict_1e_minus_8_single_threshold():
    epsilon = _single(1e-8)
    assert convert_bending_parameters(epsilon).method == METHOD_NONE
    assert (
        convert_bending_parameters(math.nextafter(epsilon, math.inf)).method
        == METHOD_NONE
    )
    bits = struct.unpack("<I", struct.pack("<f", epsilon))[0]
    above = struct.unpack("<f", struct.pack("<I", bits + 1))[0]
    assert above > epsilon
    assert convert_bending_parameters(above) == BendingParameters(
        METHOD_DIRECTIONAL_DIHEDRAL, above
    )


def test_volume_tetrahedron_preserves_float_literal_widening_and_double_geometry():
    out = solve_volume(TETRA, (1.0, 1.0, 1.0, 1.0), 0.0, 1.0)
    assert out is not None
    expected_volume = 0.1666666716337204 * 1000.0
    expected_lambda = -expected_volume / 6000.0
    assert out.current == expected_volume
    assert out.denominator == 6000.0
    assert out.multiplier == expected_lambda
    assert out.corrections == (
        (-expected_lambda, -expected_lambda, -expected_lambda),
        (expected_lambda, 0.0, 0.0),
        (0.0, expected_lambda, 0.0),
        (0.0, 0.0, expected_lambda),
    )


def test_volume_matching_rest_still_succeeds_and_writes_four_zero_vectors():
    rest = 0.1666666716337204 * 1000.0
    out = solve_volume(TETRA, (1.0,) * 4, rest, 0.75)
    assert out is not None
    assert out.corrections == ((0.0, 0.0, 0.0),) * 4


def test_volume_stiffness_and_each_inverse_mass_enter_in_observed_order():
    masses = (0.5, 1.0, 2.0, 4.0)
    out = solve_volume(TETRA, masses, 0.0, 0.25)
    assert out is not None
    assert out.denominator == 8500.0
    expected = 0.25 * (0.0 - out.current) / out.denominator
    assert out.multiplier == expected
    assert out.corrections[0] == (-expected * 0.5,) * 3
    assert out.corrections[3] == (0.0, 0.0, expected * 4.0)


def test_volume_zero_gradient_returns_false_without_a_correction():
    assert solve_volume(((0.0, 0.0, 0.0),) * 4, (1.0,) * 4, 1.0, 1.0) is None


def test_dihedral_directional_known_hinge_matches_signed_phi_and_gradients():
    out = solve_dihedral(-1.0, HINGE, (1.0,) * 4, 0.0, 1.0)
    assert out is not None
    lam = math.pi / 8.0
    assert out.current == -math.pi / 2.0
    assert out.denominator == 4.0
    assert out.multiplier == lam
    assert out.corrections == (
        (0.0, 0.0, -lam),
        (0.0, -lam, 0.0),
        (0.0, lam, lam),
        (0.0, 0.0, 0.0),
    )


def test_dihedral_undirected_multiplies_denominator_by_orientation_sign():
    out = solve_dihedral(0.0, HINGE, (1.0,) * 4, 0.0, 1.0)
    assert out is not None
    assert out.current == math.pi / 2.0
    assert out.denominator == -4.0
    assert out.multiplier == math.pi / 8.0


def test_dihedral_matching_directional_rest_produces_zero_corrections():
    out = solve_dihedral(-1.0, HINGE, (1.0,) * 4, -math.pi / 2.0, 0.5)
    assert out is not None
    assert out.corrections == ((0.0, 0.0, 0.0),) * 4


def test_dihedral_inverse_mass_weights_correction_but_not_geometry():
    out = solve_dihedral(-1.0, HINGE, (0.5, 1.0, 2.0, 4.0), 0.0, 0.25)
    assert out is not None
    assert out.denominator == 5.5
    expected = (math.pi / 2.0) / 5.5 * 0.25
    assert out.multiplier == expected
    assert out.corrections[0] == (0.0, 0.0, -0.5 * expected)
    assert out.corrections[2] == (0.0, 2.0 * expected, 2.0 * expected)


def test_dihedral_asymmetric_fixture_locks_component_divsd_precision_seam():
    points = (
        (-0.7046689406673505, -1.3966033043019923, 0.603737892159415),
        (-1.710254853329829, 0.1435280172267568, -0.5372443323496578),
        (-1.7680043009011728, 0.02974293275768103, -1.8500173662320605),
        (-0.2654172653504565, -1.7205783057015243, -1.6371479466245398),
    )
    out = solve_dihedral(-1.0, points, (0.2, 0.7, 1.1, 0.4), -0.35, 0.63)
    assert out is not None
    assert out.current == 2.9983593124024837
    assert out.denominator == 0.9932891507405908
    assert out.multiplier == -2.12371832033075
    assert out.corrections[2] == (
        -1.2001054964146407,
        -1.01068240265764,
        0.160868975733047,
    )


def test_dihedral_short_shared_edge_returns_false_before_normals():
    points = list(HINGE)
    points[3] = (5e-9, 0.0, 0.0)
    assert solve_dihedral(-1.0, points, (1.0,) * 4, 0.0, 1.0) is None


def test_dihedral_zero_area_face_returns_false():
    points = list(HINGE)
    points[0] = points[2]
    assert solve_dihedral(-1.0, points, (1.0,) * 4, 0.0, 1.0) is None


def test_undirected_zero_orientation_is_rejected_by_finite_adapter_policy():
    coplanar = ((0.0, 1.0, 0.0), (0.0, -1.0, 0.0), (0.0, 0.0, 0.0), (1.0, 0.0, 0.0))
    with pytest.raises(ValueError, match="orientation"):
        solve_dihedral(0.0, coplanar, (1.0,) * 4, 0.0, 1.0)


@pytest.mark.parametrize(
    "positions,masses,rest,stiffness",
    [
        (TETRA[:3], (1.0,) * 4, 0.0, 1.0),
        (TETRA, (1.0,) * 3, 0.0, 1.0),
        (TETRA, (1.0, 1.0, -1.0, 1.0), 0.0, 1.0),
        (TETRA, (1.0,) * 4, math.nan, 1.0),
        (TETRA, (1.0,) * 4, 0.0, math.inf),
    ],
)
def test_finite_adapter_rejects_malformed_or_nonfinite_volume_inputs(
    positions, masses, rest, stiffness
):
    with pytest.raises(ValueError):
        solve_volume(positions, masses, rest, stiffness)
