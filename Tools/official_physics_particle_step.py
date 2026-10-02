"""Finite particle-force fragment and EndSimulationStep value reference.

Source-bound scalar flow, NOT a complete solver or Unity/Burst execution oracle.
The force fragment starts AFTER center/inertia transforms and consumes ALREADY
resolved damping and wind. It does not implement StartSimulationStep's pose,
center, spring or wind generation. EndStep consumes already resolved particle
indices, collision normals and parameters; no missing center is invented.
Single boundaries/order are retained. Python sqrt is not native bit equivalence.
Finite/positive-dt/bounds/degenerate-axis guards are adapter policy only.
Returns private values/write order; never publishes or mutates native arrays.
"""

import math
from dataclasses import dataclass
from typing import cast

from official_physics_angle_baseline import _integer
from official_physics_angles import _cross, _dot, _float3
from official_physics_constraints import (
    Vector3,
    _add,
    _length,
    _positive,
    _scale,
    _single,
    _sub,
    _vector,
)

_EPSILON = _single(1e-8)
_LIMIT_EPSILON = _single(1e-9)  # ClampVectorLength helper has a distinct cutoff.


def _single_dot(a: Vector3, b: Vector3) -> float:
    lanes = [_single(x * y) for x, y in zip(a, b, strict=True)]
    return _single(_single(lanes[1] + lanes[0]) + lanes[2])


def _single_scale(a: Vector3, factor: float) -> Vector3:
    return cast(Vector3, tuple(_single(x * factor) for x in a))


def _single_add(a: Vector3, b: Vector3) -> Vector3:
    return cast(Vector3, tuple(_single(x + y) for x, y in zip(a, b, strict=True)))


def _divide(a: Vector3, factor: float) -> Vector3:
    return _vector(cast(Vector3, tuple(x / factor for x in a)))


def _single_normalize(a: Vector3) -> Vector3:
    a = _float3(a)
    length = _single(math.sqrt(_single_dot(a, a)))
    if length <= 0:
        raise ValueError("Adapter refuses degenerate Single direction")
    return _single_scale(a, _single(1 / length))


@dataclass(frozen=True)
class ParticleEndState:
    next_position: Vector3
    old_position: Vector3
    velocity_position: Vector3
    velocity: Vector3
    friction: float
    static_friction: float
    collision_normal: Vector3
    depth: float


@dataclass(frozen=True)
class EndStepSettings:
    delta_time: float
    scale_ratio: float
    velocity_weight: float
    particle_speed_limit: float
    dynamic_friction: float
    static_friction: float
    centrifugal_acceleration: float
    team_flag: int = 0


@dataclass(frozen=True)
class ResolvedCenter:
    now_world_position: Vector3
    rotation_axis: Vector3
    angular_velocity: float


@dataclass(frozen=True)
class ParticleEndResult:
    old_position: Vector3
    velocity: Vector3
    real_velocity: Vector3
    friction: float
    static_friction: float
    corrected_next_position: Vector3  # LOCAL value, no nextPosArray write!
    writes: tuple[str, ...]


def finish_particle_step(
    state: ParticleEndState,
    settings: EndStepSettings,
    *,
    attribute: int,
    center: ResolvedCenter | None = None,
) -> ParticleEndResult:
    """EndSimulationStep managed finite scalar body, resolved indices only.

    IsMove bit2 OR Team spring bit0x2000 enables friction/solver-velocity writes.
    Fixed particles still update realVelocity and oldPos. Static correction is
    subtracted from BOTH local next and local velocityPos, never the source next
    or velocityPos buffers. Speed/centrifugal/weight affect solver velocity only.
    """
    attribute = _integer(attribute, 255)
    flag = _integer(settings.team_flag, 2**64 - 1)
    dt = _positive(settings.delta_time)
    scale = _single(settings.scale_ratio)
    weight = _single(settings.velocity_weight)
    speed_limit = _single(settings.particle_speed_limit)
    dynamic_parameter = _single(settings.dynamic_friction)
    static_parameter = _single(settings.static_friction)
    centrifugal = _single(settings.centrifugal_acceleration)
    nxt, old, vp = map(
        _vector, (state.next_position, state.old_position, state.velocity_position)
    )
    velocity, normal = _float3(state.velocity), _float3(state.collision_normal)
    friction, static_saved, depth = map(
        _single, (state.friction, state.static_friction, state.depth)
    )
    writes: tuple[str, ...] = ()
    if attribute & 2 or flag & 0x2000:
        has_normal = _single_dot(normal, normal) > _EPSILON
        threshold = _single(static_parameter * scale)
        stick = float(static_saved)
        if has_normal and friction > 0 and threshold > 0:
            delta = _sub(nxt, old)
            # Project in source is n * dot(v,n), NOT divided by dot(n,n).
            tangent = _sub(delta, _scale(normal, _dot(delta, normal)))
            tangent_speed = _length(tangent) / dt
            if threshold > tangent_speed:
                stick += _single(0.04)
            else:
                stick -= max(_single(0.05), (tangent_speed - threshold) / _single(0.2))
            stick = min(1.0, max(0.0, stick))
            correction = _scale(tangent, stick)
            nxt, vp = _sub(nxt, correction), _sub(vp, correction)
        else:
            stick = min(1.0, max(0.0, stick - _single(0.05)))
        static_saved = _single(stick)
        v = _divide(_sub(nxt, vp), dt)
        squared_speed = _dot(v, v)
        direction = (
            _single_normalize(v) if squared_speed > _EPSILON else (0.0, 0.0, 0.0)
        )
        if (
            has_normal
            and friction > _EPSILON
            and dynamic_parameter > 0
            and squared_speed >= _EPSILON
        ):
            alignment = _single(_single(_single_dot(normal, direction) * 0.5) + 0.5)
            factor = _single(
                min(1.0, max(0.0, _single(dynamic_parameter * friction)))
                * _single(1 - _single(alignment * alignment))
            )
            v = _sub(v, _scale(v, factor))
        friction = _single(friction * _single(0.6))
        if speed_limit >= 0:
            limit = _single(speed_limit * scale)
            length = _length(v)
            if length > _LIMIT_EPSILON and length > limit:
                v = _scale(v, limit / length)
        if centrifugal > _EPSILON and squared_speed >= _EPSILON:
            if center is None:
                raise ValueError(
                    "Adapter requires resolved source center for centrifugal branch"
                )
            omega = _single(center.angular_velocity)
            if omega > _EPSILON:
                center_position = _vector(center.now_world_position)
                axis = _float3(center.rotation_axis)
                radial = _float3(_sub(nxt, center_position))  # narrow THEN widen
                plane = _sub(radial, _scale(axis, _dot(radial, axis)))
                radius = _length(plane)
                if radius > _EPSILON:
                    outward = _divide(plane, radius)
                    tangent = _cross(axis, outward)
                    tangent_length = _length(tangent)
                    if tangent_length <= 0:
                        raise ValueError(
                            "Adapter refuses degenerate center rotation axis"
                        )
                    tangent = _scale(tangent, 1 / tangent_length)
                    alignment = min(1.0, max(0.0, _dot(direction, tangent)))
                    amount = _single(_single(_single(1 - depth) + 1) * omega)
                    amount = _single(amount * omega)
                    amount_double = (
                        (alignment * (amount * radius)) * centrifugal
                    ) * _single(0.02)
                    v = _add(v, _scale(outward, amount_double))
        velocity = _float3(_scale(v, weight))
        writes = ("static_friction", "friction", "velocity")
    real = _float3(_divide(_sub(nxt, old), dt))
    return ParticleEndResult(
        nxt,
        velocity,
        real,
        friction,
        static_saved,
        nxt,
        writes + ("real_velocity", "old_position"),
    )


def integrate_force_fragment(
    inertia_rotated_velocity: Vector3,
    *,
    depth: float,
    damping: float,
    power_z: float,
    velocity_weight: float,
    gravity: float,
    gravity_direction: Vector3,
    gravity_ratio: float,
    impact: Vector3,
    force_mode: int,
    wind: Vector3,
    scale_ratio: float,
    delta_time: float,
) -> tuple[Vector3, Vector3]:
    """StartStep AFTER inertia, BEFORE Double position addition/spring.

    Returns Single velocity + Single displacement; no velocityArray write is
    performed by StartStep. Damping curve and Wind output are caller-resolved.
    Integer modes 1/2 divide impact by depth mass; 2/11 clear previous velocity.
    Unknown Int32 modes leave zero impact, matching source default branch.
    """
    if type(force_mode) is not int or not -(2**31) <= force_mode < 2**31:
        raise ValueError("Adapter force mode must be Int32")
    dt = _positive(delta_time)
    depth, damping, power_z, weight, gravity, ratio, scale = map(
        _single,
        (depth, damping, power_z, velocity_weight, gravity, gravity_ratio, scale_ratio),
    )
    velocity = _float3(inertia_rotated_velocity)
    impact, wind, gravity_direction = map(_float3, (impact, wind, gravity_direction))
    velocity = _single_scale(velocity, weight)
    damping = min(1.0, max(0.0, damping))
    keep = min(1.0, max(0.0, _single(1 - _single(damping * power_z))))
    velocity = _single_scale(velocity, keep)
    force = _single_scale(gravity_direction, _single(gravity * ratio))
    gap = _single(1 - depth)
    mass = _single(_single(_single(gap * gap) * 5) + 1)
    if force_mode in (1, 2):
        impact = cast(Vector3, tuple(_single(x / mass) for x in impact))
    elif force_mode not in (10, 11):
        impact = (0.0, 0.0, 0.0)
    if force_mode in (2, 11):
        velocity = (0.0, 0.0, 0.0)
    force = _single_add(_single_add(force, impact), wind)
    force = _single_scale(_single_scale(force, scale), dt)
    velocity = _single_add(velocity, force)
    return velocity, _single_scale(velocity, dt)
