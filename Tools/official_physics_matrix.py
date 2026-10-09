"""Finite column-matrix references for 5a2baa8/5a2ec6c/a1e77ec.

Rotation is constructed in Single, widened, then column-scaled in Double.
Full inverse follows the observed double4 shuffle/minor path, not fastinverse,
inverseQ/scale or a generic elimination replacement. No native execution/bit oracle.
Finite inputs/intermediates and singular rejection are ADAPTER restrictions.

Math formulation reference: Unity.Mathematics 1.3.3 matrix.cs/double4x4.gen.cs.
com.unity.mathematics copyright © 2023 Unity Technologies ApS
Licensed under the Unity Companion License for Unity-dependent projects:
https://unity3d.com/legal/licenses/unity_companion_license
AS IS, without warranty; see the license for details. This project is Unity-dependent.
"""

from collections.abc import Sequence
from typing import cast

from official_physics_angle_cache import _quaternion
from official_physics_angles import Quaternion, _float3
from official_physics_constraints import Vector3, _finite, _single, _vector

Double4 = tuple[float, float, float, float]
Matrix4 = tuple[Double4, Double4, Double4, Double4]


def _matrix(value: Sequence[Sequence[float]]) -> Matrix4:
    if len(value) != 4 or any(len(column) != 4 for column in value):
        raise ValueError("Adapter requires four Double4 columns")
    return cast(Matrix4, tuple(tuple(_finite(x) for x in column) for column in value))


def build_double_trs(
    position: Vector3, rotation: Quaternion, scale: Vector3
) -> Matrix4:
    """5a2baa8: Single quaternion matrix → Double columns → Double scale/TRS."""
    p = _vector(position)
    x, y, z, w = _quaternion(rotation)
    sx, sy, sz = _float3(scale)
    x2, y2, z2 = (_single(v + v) for v in (x, y, z))
    a = (-y, x, -w)
    b = (z, -w, -x)
    c = (-w, -z, y)

    def column(
        left: float, lv: Vector3, right: float, rv: Vector3, axis: int, s: float
    ) -> Double4:
        values = tuple(
            _finite(
                float(
                    _single(
                        _single(_single(left * lv[i]) - _single(right * rv[i]))
                        + (1.0 if i == axis else 0.0)
                    )
                )
                * float(s)
            )
            for i in range(3)
        )
        return cast(Double4, (*values, 0.0))

    return (
        column(y2, a, z2, b, 0, sx),
        column(z2, c, x2, a, 1, sy),
        column(x2, b, y2, c, 2, sz),
        (*p, 1.0),
    )


def transform_double_point(
    matrix: Sequence[Sequence[float]], point: Vector3
) -> Vector3:
    """5a2ec6c: ((c0*x+c1*y)+c2*z)+c3; return xyz, no homogeneous divide."""
    m = _matrix(matrix)
    x, y, z = _vector(point)
    return cast(
        Vector3,
        tuple(
            _finite(((m[0][i] * x + m[1][i] * y) + m[2][i] * z) + m[3][i])
            for i in range(3)
        ),
    )


def inverse_double_matrix(matrix: Sequence[Sequence[float]]) -> Matrix4:
    """a1e77ec: lane-packed minors, signed denominator reduction, full inverse.

    Python separate binary Double operations, not a hardware-native oracle.
    No epsilon/normalization substitute is applied. Singular matrices are rejected
    by this finite adapter, whereas native arithmetic can propagate NaN/Inf.
    """
    c0, c1, c2, c3 = _matrix(matrix)
    a = (c1[0], c1[1], c0[0], c0[1])
    b = (c2[0], c2[1], c3[0], c3[1])
    c = (c1[2], c1[3], c0[2], c0[3])
    d = (c2[2], c2[3], c3[2], c3[3])
    e = (c1[1], c1[2], c0[1], c0[2])
    f = (c2[1], c2[2], c3[1], c3[2])
    g = (c1[3], c1[0], c0[3], c0[0])
    h = (c2[3], c2[0], c3[3], c3[0])
    rows = tuple(
        (b[2], b[0], a[0], a[2])
        if j == 0
        else (b[3], b[1], a[1], a[3])
        if j == 1
        else (d[2], d[0], c[0], c[2])
        if j == 2
        else (d[3], d[1], c[1], c[3])
        for j in range(4)
    )
    r0, r1, r2, r3 = rows
    r0_forward = (a[2], a[0], b[0], b[2])

    def pair(u: Double4, v: Double4, wv: Double4, t: Double4) -> Double4:
        return cast(
            Double4, tuple(_finite(u[i] * v[i] - wv[i] * t[i]) for i in range(4))
        )

    def expand(v: Double4, lane: int) -> Double4:
        return (v[lane], v[lane + 2], v[lane + 2], v[lane])

    p12 = pair(e, d, f, c)
    p02 = pair(a, d, b, c)
    p30 = pair(h, a, g, b)
    i12, i23 = expand(p12, 0), expand(p12, 1)
    i02, i13 = expand(p02, 0), expand(p02, 1)
    i30, i01 = expand(p30, 0), expand(p30, 1)
    minor0 = tuple(
        _finite((r3[i] * i12[i] - r2[i] * i13[i]) + r1[i] * i23[i]) for i in range(4)
    )
    denom = tuple(_finite(r0_forward[i] * minor0[i]) for i in range(4))
    sums = tuple(_finite(denom[i] + denom[i ^ 1]) for i in range(4))
    signed = tuple(_finite(sums[i] - sums[2 if i < 2 else 0]) for i in range(4))
    if any(v == 0 for v in signed):
        raise ValueError("Adapter requires a nonsingular finite inverse")
    reciprocal = tuple(_finite(1 / v) for v in signed)
    minor1 = tuple(
        _finite((r2[i] * i30[i] - r0[i] * i23[i]) - r3[i] * i02[i]) for i in range(4)
    )
    minor2 = tuple(
        _finite((r0[i] * i13[i] - r1[i] * i30[i]) - r3[i] * i01[i]) for i in range(4)
    )
    minor3 = tuple(
        _finite((r1[i] * i02[i] - r0[i] * i12[i]) + r2[i] * i01[i]) for i in range(4)
    )
    return _matrix(
        tuple(
            tuple(_finite(v[i] * reciprocal[i]) for i in range(4))
            for v in (minor0, minor1, minor2, minor3)
        )
    )
