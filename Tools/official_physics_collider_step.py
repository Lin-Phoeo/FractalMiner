"""Finite offline value path of the managed Single Collider Start fallback.

Source: method370322/RVA0x5a5a33c..0x5a5b1c2. This phase accepts explicit
Single position values, produces the typed 184-byte WorkData consumed by Point,
and reports source-order writes. This is the Single kernel's explicit value
path, not the separate inlined Double StartSimulationStepJob.Execute(int).
The host's Double buffers are not implicitly reinterpreted or converted here.
No game/native code, Jobs/Burst dispatch, component lookup or Unity writes run.
Python libm is a mathematical CRT reference, not bitwise native/Burst proof.
Finite/nonzero input rejection is adapter policy, not native exception behavior.
"""

import math
from dataclasses import dataclass, replace

from official_physics_angle_cache import _quaternion, quaternion_inverse, rotate_single
from official_physics_angles import Quaternion, _float3
from official_physics_constraints import Vector3, _positive, _single
from official_physics_point_collision import ColliderWork

_ZERO: Vector3 = (0.0, 0.0, 0.0)
_SLERP_LINEAR_THRESHOLD = _single(0.9995)


@dataclass(frozen=True)
class ColliderStepTeam:
    frame_interpolation: float


@dataclass(frozen=True)
class ColliderStepCenter:
    step_move_inertia_ratio: float
    step_rotation_inertia_ratio: float


@dataclass(frozen=True)
class ColliderStepState:
    """Explicit Start-phase Single buffers; positions are narrowed when read.

    WorkData positions/bounds are Double after the observed conversion sites.
    Existing unwritten values and their representations survive the phase.
    """

    flag: int
    size: Vector3
    frame_position: Vector3
    frame_rotation: Quaternion
    frame_scale: Vector3
    old_frame_position: Vector3
    old_frame_rotation: Quaternion
    now_position: Vector3
    now_rotation: Quaternion
    old_position: Vector3
    old_rotation: Quaternion
    work: ColliderWork | None


@dataclass(frozen=True)
class ColliderStepResult:
    state: ColliderStepState
    writes: tuple[str, ...]


def _dot4(a: Quaternion, b: Quaternion) -> float:
    # helper0x39d3f10: ((y*y + x*x) + z*z) + w*w, rounding each operation.
    return _single(
        _single(
            _single(_single(a[1] * b[1]) + _single(a[0] * b[0])) + _single(a[2] * b[2])
        )
        + _single(a[3] * b[3])
    )


def _normalize4(value: Quaternion) -> Quaternion:
    # helper0x59d7b18 and nlerp's0x305cc20 both round sqrt before reciprocal.
    reciprocal = _single(1 / _positive(_single(math.sqrt(_dot4(value, value)))))
    return (
        _single(reciprocal * value[0]),
        _single(reciprocal * value[1]),
        _single(reciprocal * value[2]),
        _single(reciprocal * value[3]),
    )


def _change_sign4(value: Quaternion, sign: float) -> Quaternion:
    # helper0x5a19428: bitwise sign mask + XOR, including a negative-zero sign.
    return (
        (-value[0], -value[1], -value[2], -value[3])
        if math.copysign(1.0, sign) < 0
        else value
    )


def _slerp(a: Quaternion, b: Quaternion, fraction: float) -> Quaternion:
    """helper0x5a19748 including its raw spherical and normalized linear paths."""
    dot = _dot4(a, b)
    if dot < 0:
        dot = -dot
        b = (-b[0], -b[1], -b[2], -b[3])
    if dot >= _SLERP_LINEAR_THRESHOLD:
        # helper0x5a19668: normalize(a + t * (chgsign(b,dot(a,b)) - a)).
        b = _change_sign4(b, _dot4(a, b))
        value = tuple(
            _single(start + _single(fraction * _single(end - start)))
            for start, end in zip(a, b, strict=True)
        )
        return _normalize4((value[0], value[1], value[2], value[3]))
    sine_squared = _single(1 - _single(dot * dot))
    reciprocal_sine = _single(1 / _positive(_single(math.sqrt(sine_squared))))
    angle = _single(math.acos(dot))
    end_weight = _single(_single(math.sin(_single(angle * fraction))) * reciprocal_sine)
    end_term = tuple(_single(lane * end_weight) for lane in b)
    start_angle = _single(_single(1 - fraction) * angle)
    start_weight = _single(_single(math.sin(start_angle)) * reciprocal_sine)
    start_term = tuple(_single(lane * start_weight) for lane in a)
    return (
        _single(start_term[0] + end_term[0]),
        _single(start_term[1] + end_term[1]),
        _single(start_term[2] + end_term[2]),
        _single(start_term[3] + end_term[3]),
    )


def _lerp3(a: Vector3, b: Vector3, fraction: float) -> Vector3:
    # helper0x59fb7fc: start + t * (end-start), all operations Single.
    values = tuple(
        _single(start + _single(fraction * _single(end - start)))
        for start, end in zip(a, b, strict=True)
    )
    return (values[0], values[1], values[2])


def _add3(a: Vector3, b: Vector3) -> Vector3:
    return (_single(a[0] + b[0]), _single(a[1] + b[1]), _single(a[2] + b[2]))


def _sub3(a: Vector3, b: Vector3) -> Vector3:
    return (_single(a[0] - b[0]), _single(a[1] - b[1]), _single(a[2] - b[2]))


def _scale3(value: Vector3, scale: float) -> Vector3:
    return (
        _single(scale * value[0]),
        _single(scale * value[1]),
        _single(scale * value[2]),
    )


def _bounds3(a: Vector3, b: Vector3) -> tuple[Vector3, Vector3]:
    # Finite helper0x2cd2410/0x2cd2480: second operand wins equal values.
    low = tuple(min(y, x) for x, y in zip(a, b, strict=True))
    high = tuple(max(y, x) for x, y in zip(a, b, strict=True))
    return (low[0], low[1], low[2]), (high[0], high[1], high[2])


def _dot3(a: Vector3, b: Vector3) -> float:
    return _single(
        _single(_single(a[1] * b[1]) + _single(a[0] * b[0])) + _single(a[2] * b[2])
    )


def _endpoint_bounds(a: Vector3, b: Vector3, radius: float) -> tuple[Vector3, Vector3]:
    low, high = _bounds3(a, b)
    # Capsule bounds subtract/add in Single, then widen in helper0x40c6230.
    return (
        (_single(low[0] - radius), _single(low[1] - radius), _single(low[2] - radius)),
        (
            _single(high[0] + radius),
            _single(high[1] + radius),
            _single(high[2] + radius),
        ),
    )


def start_collider_step(
    state: ColliderStepState,
    team: ColliderStepTeam,
    center: ColliderStepCenter,
) -> ColliderStepResult:
    """One already-selected collider; caller resolves job index and signed Team.

    No interpolation/inertia clamp. For unsupported shape nibbles the native
    path still updates history and writes zero geometry with computed rotations.
    The returned work can be passed directly to point_collision_particle.
    """
    flag = state.flag
    if type(flag) is not int or not 0 <= flag <= 0xFF:
        raise ValueError("Adapter requires an explicit Byte collider flag")
    if not flag & 0x10 or not flag & 0x20:
        return ColliderStepResult(state, ())
    interpolation = _single(team.frame_interpolation)
    next_position = _lerp3(
        _float3(state.old_frame_position), _float3(state.frame_position), interpolation
    )
    next_rotation = _normalize4(
        _slerp(
            _quaternion(state.old_frame_rotation),
            _quaternion(state.frame_rotation),
            interpolation,
        )
    )
    old_position = _lerp3(
        _float3(state.old_position),
        next_position,
        _single(center.step_move_inertia_ratio),
    )
    old_rotation_raw = _slerp(
        _quaternion(state.old_rotation),
        next_rotation,
        _single(center.step_rotation_inertia_ratio),
    )
    stored_old_rotation = _normalize4(old_rotation_raw)
    inverse_old_rotation = quaternion_inverse(old_rotation_raw)
    size, scale = _float3(state.size), _float3(state.frame_scale)
    shape = flag & 0xF
    radii = (0.0, 0.0)
    old_points = next_points = (_ZERO, _ZERO)
    aabb_min = aabb_max = _ZERO
    if shape == 1:
        radius = _single(size[0] * abs(scale[0]))
        radii = (radius, radius)
        low, high = _bounds3(old_position, next_position)
        # Sphere widens its float bounds FIRST; AABB.Expand then uses Double.
        aabb_min = (low[0] - radius, low[1] - radius, low[2] - radius)
        aabb_max = (high[0] + radius, high[1] + radius, high[2] + radius)
        old_points, next_points = (old_position, _ZERO), (next_position, _ZERO)
    elif 2 <= shape <= 7:
        axis = (
            (1.0, 0.0, 0.0)
            if shape in (2, 5)
            else (0.0, 1.0, 0.0)
            if shape in (3, 6)
            else (0.0, 0.0, 1.0)
        )
        axial_scale = _dot3(scale, axis)
        direction = _scale3(
            axis, 1.0 if axial_scale > 0 else -1.0 if axial_scale < 0 else 0.0
        )
        if flag & 0x80:
            direction = (-direction[0], -direction[1], -direction[2])
        radius0, radius1, height = _scale3(size, abs(axial_scale))
        if shape <= 4:
            height0 = _single(_single(height * 0.5) - radius0)
            height1 = _single(_single(height * 0.5) - radius1)
        else:
            height0 = _single(0 - radius0)
            height1 = _single(_single(height - radius0) - radius1)
        height0 = height0 if height0 > 0 else 0.0
        height1 = height1 if height1 > 0 else 0.0
        offset0, offset1 = _scale3(direction, height0), _scale3(direction, height1)
        old0 = _add3(old_position, rotate_single(old_rotation_raw, offset0))
        old1 = _sub3(old_position, rotate_single(old_rotation_raw, offset1))
        next0 = _add3(next_position, rotate_single(next_rotation, offset0))
        next1 = _sub3(next_position, rotate_single(next_rotation, offset1))
        low0, high0 = _endpoint_bounds(old0, next0, radius0)
        low1, high1 = _endpoint_bounds(old1, next1, radius1)
        aabb_min = _bounds3(low0, low1)[0]
        aabb_max = _bounds3(high0, high1)[1]
        radii = (radius0, radius1)
        old_points, next_points = (old0, old1), (next0, next1)
    elif shape == 8:
        direction = _scale3(
            (0.0, 1.0, 0.0), 1.0 if scale[1] > 0 else -1.0 if scale[1] < 0 else 0.0
        )
        old_points = (rotate_single(next_rotation, direction), _ZERO)
        next_points = (next_position, _ZERO)
    work = ColliderWork(
        flag,
        aabb_min,
        aabb_max,
        radii,
        old_points,
        next_points,
        inverse_old_rotation,
        next_rotation,
    )
    result = replace(
        state,
        now_position=next_position,
        now_rotation=next_rotation,
        old_position=old_position,
        old_rotation=stored_old_rotation,
        work=work,
    )
    return ColliderStepResult(
        result, ("now_position", "now_rotation", "old_position", "old_rotation", "work")
    )
