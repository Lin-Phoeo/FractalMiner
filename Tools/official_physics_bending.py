"""Finite TriangleBending arithmetic recovered from the managed fallback.

Evidence: docs/implementation/official-physics-bending-20261010.  Geometry and
corrections are Double, while serialized parameters and the caller's mass/rest
boundaries are Single.  This module is a checked mathematical reference: it
does not create triangle topology, schedule Burst jobs, mutate Unity objects or
claim bitwise equivalence to the native CRT acos/sqrt implementation.

Malformed, non-finite and the undirected zero-orientation case are rejected by
adapter policy.  The original method operates on unchecked native buffers; its
failure/NaN behaviour is deliberately not reproduced.
"""

import math
from collections.abc import Sequence
from dataclasses import dataclass

from official_physics_constraints import Vector3, _finite, _single, _vector

METHOD_NONE = 0
METHOD_DIHEDRAL = 1
METHOD_DIRECTIONAL_DIHEDRAL = 2
VOLUME_SIGN = 100

# The native methods widen these original Single literals to Double.
_CONVERT_EPSILON = _single(1e-8)
_EDGE_EPSILON = 9.99999993922529e-9
_VOLUME_EPSILON = 9.999999974752427e-7
_ONE_SIXTH = 0.1666666716337204
_VOLUME_SCALE = 1000.0


@dataclass(frozen=True)
class BendingParameters:
    method: int
    stiffness: float


@dataclass(frozen=True)
class BendingCorrection:
    current: float
    denominator: float
    multiplier: float
    corrections: tuple[Vector3, Vector3, Vector3, Vector3]


def _lane(value: int, maximum: int, label: str) -> int:
    if type(value) is not int or not 0 <= value <= maximum:
        raise ValueError(f"Adapter {label} must be an unsigned lane")
    return value


def _word(value: int, bits: int, label: str) -> int:
    lower = -(1 << (bits - 1))
    upper = 1 << bits
    if type(value) is not int or not lower <= value < upper:
        raise ValueError(f"Adapter {label} must preserve a {bits}-bit pattern")
    return value & (upper - 1)


def pack_triangle_pair(v0: int, v1: int, v2: int, v3: int) -> int:
    """Pack four team-local UInt16 vertices as v0,v1,v2,v3 high-to-low."""
    lanes = tuple(_lane(v, 0xFFFF, "triangle vertex") for v in (v0, v1, v2, v3))
    return lanes[0] << 48 | lanes[1] << 32 | lanes[2] << 16 | lanes[3]


def unpack_triangle_pair(word: int) -> tuple[int, int, int, int]:
    word = _word(word, 64, "triangle pair")
    return (
        word >> 48 & 0xFFFF,
        word >> 32 & 0xFFFF,
        word >> 16 & 0xFFFF,
        word & 0xFFFF,
    )


def pack_write_offsets(v0: int, v1: int, v2: int, v3: int) -> int:
    """Pack each pair vertex's private write ordinal as four UInt8 lanes."""
    lanes = tuple(_lane(v, 0xFF, "write offset") for v in (v0, v1, v2, v3))
    return lanes[0] << 24 | lanes[1] << 16 | lanes[2] << 8 | lanes[3]


def unpack_write_offsets(word: int) -> tuple[int, int, int, int]:
    word = _word(word, 32, "write offsets")
    return (word >> 24 & 0xFF, word >> 16 & 0xFF, word >> 8 & 0xFF, word & 0xFF)


def convert_bending_parameters(serialized_stiffness: float) -> BendingParameters:
    """Params.Convert369263: strict >1e-8f selects directional dihedral."""
    stiffness = _single(serialized_stiffness)
    method = (
        METHOD_DIRECTIONAL_DIHEDRAL if stiffness > _CONVERT_EPSILON else METHOD_NONE
    )
    return BendingParameters(method, stiffness)


def _positions4(values: Sequence[Vector3]) -> tuple[Vector3, Vector3, Vector3, Vector3]:
    if len(values) != 4:
        raise ValueError("Adapter requires exactly four triangle-pair positions")
    result = tuple(_vector(value) for value in values)
    return result  # type: ignore[return-value]


def _masses4(values: Sequence[float]) -> tuple[float, float, float, float]:
    if len(values) != 4:
        raise ValueError("Adapter requires exactly four inverse masses")
    result = tuple(_finite(value) for value in values)
    if any(value < 0 for value in result):
        raise ValueError("Adapter inverse masses must be nonnegative")
    return result  # type: ignore[return-value]


def _add(a: Vector3, b: Vector3) -> Vector3:
    return _vector((a[0] + b[0], a[1] + b[1], a[2] + b[2]))


def _sub(a: Vector3, b: Vector3) -> Vector3:
    return _vector((a[0] - b[0], a[1] - b[1], a[2] - b[2]))


def _scale(a: Vector3, factor: float) -> Vector3:
    factor = _finite(factor)
    return _vector((a[0] * factor, a[1] * factor, a[2] * factor))


def _divide(a: Vector3, divisor: float) -> Vector3:
    """Component divsd path; do not replace with reciprocal-and-multiply."""
    divisor = _finite(divisor)
    if divisor == 0:
        raise ValueError("Finite adapter requires a nonzero vector divisor")
    return _vector((a[0] / divisor, a[1] / divisor, a[2] / divisor))


def _dot(a: Vector3, b: Vector3) -> float:
    # Unity.Mathematics double3 helper order recovered at 0x59d7a44.
    return _finite((a[1] * b[1] + a[0] * b[0]) + a[2] * b[2])


def _cross(a: Vector3, b: Vector3) -> Vector3:
    return _vector(
        (
            a[1] * b[2] - a[2] * b[1],
            a[2] * b[0] - a[0] * b[2],
            a[0] * b[1] - a[1] * b[0],
        )
    )


def _length(value: Vector3) -> float:
    return math.sqrt(_dot(value, value))


def _normalized(value: Vector3) -> Vector3:
    length = _length(value)
    if length == 0:
        raise ValueError("Finite adapter requires a nonzero normal")
    return _scale(value, 1.0 / length)


def _length_sq(value: Vector3) -> float:
    return _dot(value, value)


def _sign(value: float) -> float:
    return -1.0 if value < 0 else 1.0 if value > 0 else 0.0


def solve_volume(
    next_positions: Sequence[Vector3],
    inverse_masses: Sequence[float],
    volume_rest: float,
    stiffness: float,
) -> BendingCorrection | None:
    """Volume369212 over one ordered (opposite0,opposite1,edge2,edge3) pair."""
    p0, p1, p2, p3 = _positions4(next_positions)
    m0, m1, m2, m3 = _masses4(inverse_masses)
    rest, stiffness = _finite(volume_rest), _finite(stiffness)

    current = _dot(_cross(_sub(p1, p0), _sub(p2, p0)), _sub(p3, p0))
    current = _finite(current * _ONE_SIXTH)
    current = _finite(current * _VOLUME_SCALE)

    g0 = _cross(_sub(p1, p2), _sub(p3, p2))
    g1 = _cross(_sub(p2, p0), _sub(p3, p0))
    g2 = _cross(_sub(p0, p1), _sub(p3, p1))
    g3 = _cross(_sub(p1, p0), _sub(p2, p0))
    denominator = _finite(m0 * _length_sq(g0) + m1 * _length_sq(g1))
    denominator = _finite(denominator + m2 * _length_sq(g2))
    denominator = _finite(denominator + m3 * _length_sq(g3))
    denominator = _finite(denominator * _VOLUME_SCALE)
    if abs(denominator) < _VOLUME_EPSILON:
        return None

    multiplier = _finite(stiffness * _finite(rest - current))
    multiplier = _finite(multiplier / denominator)
    corrections = tuple(
        _scale(gradient, _finite(multiplier * mass))
        for gradient, mass in zip((g0, g1, g2, g3), (m0, m1, m2, m3))
    )
    return BendingCorrection(current, denominator, multiplier, corrections)  # type: ignore[arg-type]


def solve_dihedral(
    sign: float,
    next_positions: Sequence[Vector3],
    inverse_masses: Sequence[float],
    rest_angle: float,
    stiffness: float,
) -> BendingCorrection | None:
    """DihedralAngle369213; sign==0 is undirected, nonzero is directional."""
    p0, p1, p2, p3 = _positions4(next_positions)
    m0, m1, m2, m3 = _masses4(inverse_masses)
    sign, rest, stiffness = _finite(sign), _finite(rest_angle), _finite(stiffness)

    edge = _sub(p3, p2)
    edge_length = _length(edge)
    if edge_length < _EDGE_EPSILON:
        return None
    inverse_edge_length = _finite(1.0 / edge_length)

    normal1 = _cross(_sub(p2, p0), _sub(p3, p0))
    normal2 = _cross(_sub(p3, p1), _sub(p2, p1))
    normal1_length_sq, normal2_length_sq = _length_sq(normal1), _length_sq(normal2)
    if normal1_length_sq == 0.0 or normal2_length_sq == 0.0:
        return None
    # Managed369213 emits six component divsd instructions here.  A reciprocal
    # followed by vector multiplication rounds differently for asymmetric data.
    normal1 = _divide(normal1, normal1_length_sq)
    normal2 = _divide(normal2, normal2_length_sq)

    d0 = _scale(normal1, edge_length)
    d1 = _scale(normal2, edge_length)
    d2 = _add(
        _scale(normal1, _finite(_dot(_sub(p0, p3), edge) * inverse_edge_length)),
        _scale(normal2, _finite(_dot(_sub(p1, p3), edge) * inverse_edge_length)),
    )
    d3 = _add(
        _scale(normal1, _finite(_dot(_sub(p2, p0), edge) * inverse_edge_length)),
        _scale(normal2, _finite(_dot(_sub(p2, p1), edge) * inverse_edge_length)),
    )

    normal1, normal2 = _normalized(normal1), _normalized(normal2)
    cosine = min(1.0, max(-1.0, _dot(normal1, normal2)))
    phi = math.acos(cosine)
    denominator = _finite(m0 * _length_sq(d0) + m1 * _length_sq(d1))
    denominator = _finite(denominator + m2 * _length_sq(d2))
    denominator = _finite(denominator + m3 * _length_sq(d3))
    if denominator == 0.0:
        return None

    direction = _sign(_dot(_cross(normal1, normal2), edge))
    if sign != 0.0:
        current = _finite(phi * direction)
    else:
        current = phi
        denominator = _finite(denominator * direction)
        if denominator == 0.0:
            raise ValueError(
                "Finite adapter rejects undirected zero orientation before native division"
            )

    multiplier = _finite(_finite(rest - current) / denominator)
    multiplier = _finite(multiplier * stiffness)
    corrections = tuple(
        _scale(gradient, _finite(-mass * multiplier))
        for gradient, mass in zip((d0, d1, d2, d3), (m0, m1, m2, m3))
    )
    return BendingCorrection(current, denominator, multiplier, corrections)  # type: ignore[arg-type]
