"""Finite resolved StartSimulationStep reference, not a complete physics solver.

Source 370473/0x5a64a78: animation pose interpolation, depth-blended center
consumption, inertia rotation/translation, fixed Spring and composition with force integration.
Centers and wind are REQUIRED resolved inputs for the moving path, never guessed
or silently zeroed. Center generation, Wind, list/index allocation,
constraints, reset, native dispatch and Unity publication remain outside scope.
Single narrowing/order is retained; Python trig/sqrt is not a native/Burst oracle.
Finite input, positive dt, [0,1] interpolation domains and degenerate quaternion
refusal are ADAPTER policy, not recovered native clamps or fault contracts.
All writes below are returned logical operations, never native array mutation.
"""

import math
from collections.abc import Sequence
from dataclasses import dataclass
from typing import cast

from official_physics_angle_baseline import _integer
from official_physics_angle_cache import _quaternion, rotate_single
from official_physics_angles import Quaternion, _float3
from official_physics_constraints import (
    Vector3,
    _add,
    _single,
    _sub,
    _vector,
    evaluate_curve,
)
from official_physics_particle_step import integrate_force_fragment
from official_physics_setter import _dot, _lerp, interpolate_rotation
from official_physics_spring import (
    ClothNormalAxis,
    SpringConstraintSettings,
    apply_spring,
)


@dataclass(frozen=True)
class ParticleStartState:
    old_position: Vector3  # oldPosArray: simulation history, NOT oldPositionArray.
    old_animation_position: Vector3  # oldPositionArray: previous proxy pose.
    old_animation_rotation: Quaternion
    proxy_position: Vector3
    proxy_rotation: Quaternion
    velocity: Vector3
    depth: float


@dataclass(frozen=True)
class StartStepSettings:
    frame_interpolation: float
    depth_inertia: float
    delta_time: float
    damping_curve: Sequence[float]
    power_z: float
    velocity_weight: float
    scale_ratio: float
    gravity: float
    gravity_direction: Vector3
    gravity_ratio: float
    impact: Vector3
    force_mode: int
    team_flag: int = 0


@dataclass(frozen=True)
class ResolvedStartCenter:
    old_world_position: Vector3  # CenterData @408, Double.
    inertia_vector: Vector3  # @484, Single.
    inertia_rotation: Quaternion  # @496, Single.
    step_vector: Vector3  # @456, Single.
    step_rotation: Quaternion  # @468, Single.


@dataclass(frozen=True)
class ResolvedStartSpring:
    """Source inputs carried by the fixed-particle Spring callsite only."""

    parameters: SpringConstraintSettings
    normal_axis: ClothNormalAxis
    noise_time: float


@dataclass(frozen=True)
class ParticleStartResult:
    base_position: Vector3
    base_rotation: Quaternion
    step_basic_position: Vector3
    step_basic_rotation: Quaternion
    velocity_position: Vector3
    next_position: Vector3
    inertia_weight: float | None
    integrated_velocity: Vector3 | None  # Diagnostic LOCAL value, no buffer write.
    writes: tuple[str, ...]


def _normalize_rotation(value: Quaternion) -> Quaternion:
    # 59d7b18: dot (y²+x²)+z²+w² -> Single sqrt -> reciprocal -> lane multiply.
    q = _quaternion(value)
    length = _single(math.sqrt(_dot(q, q)))
    if length <= 0:
        raise ValueError("Adapter refuses degenerate animation quaternion")
    inverse = _single(1 / length)
    return cast(Quaternion, tuple(_single(lane * inverse) for lane in q))


def start_particle_step(
    state: ParticleStartState,
    settings: StartStepSettings,
    *,
    attribute: int,
    center: ResolvedStartCenter | None = None,
    wind: Vector3 | None = None,
    spring: ResolvedStartSpring | None = None,
) -> ParticleStartResult:
    """One resolved particle: base/step pose writes precede movable gating.

    IsMove bit2 OR Team spring bit0x2000 enters inertia/force. A spring Team
    with IsFixed bit1 invokes Spring after force integration. The resolved
    Spring inputs are required specifically for that branch, including
    attribute3 (both bits); ordinary fixed particles do not read them.
    Ordinary fixed particles only follow animation; unused force inputs are not
    evaluated. Source preserves oldPos/velocity buffers throughout StartStep.
    """
    attribute = _integer(attribute, 255)
    flag = _integer(settings.team_flag, 2**64 - 1)
    t = _single(settings.frame_interpolation)
    if not 0 <= t <= 1:
        raise ValueError("Adapter frame interpolation weight must be in [0,1]")
    old_pose, proxy = map(_vector, (state.old_animation_position, state.proxy_position))
    # Double lerp uses the already narrowed/widened Single interpolation t.
    base = _add(
        old_pose,
        cast(Vector3, tuple((y - x) * t for x, y in zip(old_pose, proxy, strict=True))),
    )
    rotation = _normalize_rotation(
        interpolate_rotation(state.old_animation_rotation, state.proxy_rotation, t)
    )
    writes = (
        "base_position",
        "base_rotation",
        "step_basic_position",
        "step_basic_rotation",
    )
    nxt, velocity_position = base, base
    factor = None
    velocity = None
    if attribute & 2 or flag & 0x2000:
        if center is None:
            raise ValueError(
                "Adapter requires resolved source center for Start inertia"
            )
        if wind is None:
            raise ValueError("Adapter requires resolved source wind for Start force")
        depth = _single(state.depth)
        factor = _single(
            _single(1 - _single(depth * depth)) * _single(settings.depth_inertia)
        )
        if not 0 <= factor <= 1:
            raise ValueError("Adapter inertia interpolation weight must be in [0,1]")
        translation = _lerp(
            _float3(center.inertia_vector), _float3(center.step_vector), factor
        )
        q = interpolate_rotation(center.inertia_rotation, center.step_rotation, factor)
        old, pivot = _vector(state.old_position), _vector(center.old_world_position)
        # Narrow the center-relative Double offset BEFORE Single rotation.
        offset = rotate_single(q, _float3(_sub(old, pivot)))
        moved = _add(pivot, _add(offset, translation))
        # Not algebraically simplified: native recreates old + (moved - old).
        velocity_position = _add(old, _sub(moved, old))
        velocity, displacement = integrate_force_fragment(
            rotate_single(q, state.velocity),
            depth=depth,
            damping=evaluate_curve(settings.damping_curve, depth),
            power_z=settings.power_z,
            velocity_weight=settings.velocity_weight,
            gravity=settings.gravity,
            gravity_direction=settings.gravity_direction,
            gravity_ratio=settings.gravity_ratio,
            impact=settings.impact,
            force_mode=settings.force_mode,
            wind=wind,
            scale_ratio=settings.scale_ratio,
            delta_time=settings.delta_time,
        )
        nxt = _add(moved, displacement)  # Widen Single displacement, then Double add.
    if flag & 0x2000 and attribute & 1:
        if spring is None:
            raise ValueError("Adapter requires resolved Spring inputs for fixed Spring")
        nxt = apply_spring(
            spring_params=spring.parameters,
            normal_axis=spring.normal_axis,
            next_position=nxt,
            base_position=base,
            base_rotation=rotation,
            noise_time=spring.noise_time,
            scale_ratio=settings.scale_ratio,
        )
    return ParticleStartResult(
        base,
        rotation,
        base,
        rotation,
        velocity_position,
        nxt,
        factor,
        velocity,
        writes + ("velocity_position", "next_position"),
    )
