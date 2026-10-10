"""Finite Motion value/slot/serial-range reference over explicit produced inputs.

Registered managed368895/59f2464, actual fallback59e8c0c, ordinary Job368926/
59f2f54 are inspected separately. Geometry/feedback are Double, curves/depth/
axis/quaternion/center offset are Single. No mass/power/scale/blend/friction
term is inserted; motion is relative to supplied animation basePose.

This does not produce proxy/Team/work lists, dispatch native/Burst jobs, model
native struct-copy timing, allocate native arrays or publish Unity bones.
Finite/representable/type/index rejection is adapter policy, not native fault
or nonfinite behavior. Python sqrt is not a CRT/Burst bitwise oracle.
"""

from collections.abc import Mapping, Sequence
from dataclasses import dataclass, replace

from official_physics_angle_cache import rotate_single
from official_physics_angles import Quaternion
from official_physics_constraints import (
    Vector3,
    _add,
    _length,
    _scale,
    _single,
    _sub,
    _vector,
    evaluate_curve,
)
from official_physics_point_pass import _integer, _item, _wrap32

_CLAMP_EPSILON = _single(1e-9)
_BACKSTOP_EPSILON = _single(1e-8)
_MIN_RADIUS = _single(0.0001)
_VELOCITY_RATIO = _single(0.95)
_ZERO: Vector3 = (0.0, 0.0, 0.0)
_AXES: tuple[Vector3, ...] = (
    (1.0, 0.0, 0.0),
    (0.0, 1.0, 0.0),
    (0.0, 0.0, 1.0),
    (-1.0, -0.0, -0.0),
    (-0.0, -1.0, -0.0),
    (-0.0, -0.0, -1.0),
)


@dataclass(frozen=True)
class MotionParameters:
    use_max_distance: bool  # MotionConstraintParams unboxed@0.
    max_distance_curve: Sequence[float]  # @4, flat Single float4x4.
    use_backstop: bool  # @68.
    backstop_radius: float  # @72, Single.
    backstop_distance_curve: Sequence[float]  # @76, flat Single float4x4.
    stiffness: float  # @140, Single; no saturate in the selected kernel.


@dataclass(frozen=True)
class MotionSettings:
    motion: MotionParameters  # ClothParameters@468.
    radius_curve: Sequence[float]  # ClothParameters@92, not a Motion member.
    normal_axis: int  # ClothParameters@156, Int32 enum; unknown -> Up.


@dataclass(frozen=True)
class MotionTeam:
    particle_start: int  # TeamData@372.
    proxy_start: int  # @292.


@dataclass(frozen=True)
class MotionBuffers:
    next_positions: Sequence[Vector3]
    velocity_positions: Sequence[Vector3]
    base_positions: Sequence[Vector3]
    base_rotations: Sequence[Quaternion]


@dataclass(frozen=True)
class MotionResult:
    next_position: Vector3
    velocity_position: Vector3
    correction: Vector3
    max_distance_applied: bool
    backstop_applied: bool
    writes: tuple[str, ...]


@dataclass(frozen=True)
class MotionVisit:
    slot: int
    particle_index: int
    team_id: int
    proxy_index: int | None
    status: str
    result: MotionResult | None
    writes: tuple[str, ...]


@dataclass(frozen=True)
class MotionPassResult:
    buffers: MotionBuffers
    visits: tuple[MotionVisit, ...]


def _flags(parameters: MotionParameters) -> tuple[bool, bool]:
    if (
        type(parameters.use_max_distance) is not bool
        or type(parameters.use_backstop) is not bool
    ):
        raise ValueError("Adapter Motion enable flags must be bool")
    return parameters.use_max_distance, parameters.use_backstop


def _curve(samples: Sequence[float]) -> tuple[float, ...]:
    if len(samples) != 16:
        raise ValueError("Adapter requires sixteen converted Single curve samples")
    return tuple(_single(value) for value in samples)


def convert_motion_parameters(
    use_max_distance: bool,
    max_distance_curve: Sequence[float],
    use_backstop: bool,
    backstop_radius: float,
    backstop_distance_curve: Sequence[float],
    stiffness: float,
    cloth_type: int,
) -> MotionParameters:
    """368923/34e0970: type10 only suppresses flags; copy other converted fields.

    Samples must ALREADY represent ConvertFloatArray output. This reference
    neither samples a Unity AnimationCurve nor invokes SerializeData.DataValidate.
    Unknown finite Int32 cloth types copy flags just like non-Spring types.
    """
    source = MotionParameters(
        use_max_distance,
        max_distance_curve,
        use_backstop,
        backstop_radius,
        backstop_distance_curve,
        stiffness,
    )
    maximum, backstop = _flags(source)
    spring = _integer(cloth_type, -0x80000000) == 10
    return MotionParameters(
        maximum and not spring,
        _curve(max_distance_curve),
        backstop and not spring,
        _single(backstop_radius),
        _curve(backstop_distance_curve),
        _single(stiffness),
    )


def motion_particle(
    next_position: Vector3,
    velocity_position: Vector3,
    base_position: Vector3,
    base_rotation: Quaternion,
    depth: float,
    settings: MotionSettings,
) -> MotionResult:
    """One already-selected Move/IsMotion particle, using animation basePose.

    Raw depth evaluates particle radius; squared Single depth evaluates Motion
    curves. Axis rotation occurs even on max-distance-only routes. Max clamp
    precedes Backstop. Center offset is Single before widening and adding base.
    Final lerp uses unsaturated widened Single stiffness, then .95f feedback.
    Eligible enabled routes publish both buffers even when correction is zero.
    """
    maximum, backstop = _flags(settings.motion)
    if not maximum and not backstop:
        return MotionResult(next_position, velocity_position, _ZERO, False, False, ())
    original, base = _vector(next_position), _vector(base_position)
    depth = _single(depth)
    radius = max(evaluate_curve(settings.radius_curve, depth), _MIN_RADIUS)
    squared_depth = _single(depth * depth)
    axis = _integer(settings.normal_axis, -0x80000000)
    local_direction = _AXES[axis] if 0 <= axis < 6 else _AXES[1]
    direction = rotate_single(base_rotation, local_direction)
    candidate = original
    max_applied = back_applied = False
    if maximum:
        delta = _sub(candidate, base)
        limit = evaluate_curve(settings.motion.max_distance_curve, squared_depth)
        length = _length(delta)
        if length > _CLAMP_EPSILON and length > limit:
            # 59e7e70 uses max / length once, then three Double multiplications.
            delta = _scale(delta, limit / length)
            max_applied = True
        candidate = _add(base, delta)
    if backstop:
        back_radius = _single(settings.motion.backstop_radius)
        if back_radius > 0:
            distance = evaluate_curve(
                settings.motion.backstop_distance_curve, squared_depth
            )
            separation = _single(distance + back_radius)
            # Native negate(float3) then mul(float3, Single), then to double3.
            offset: Vector3 = (
                _single(_single(-direction[0]) * separation),
                _single(_single(-direction[1]) * separation),
                _single(_single(-direction[2]) * separation),
            )
            center = _add(base, offset)
            delta = _sub(candidate, center)
            length = _length(delta)
            if length > _BACKSTOP_EPSILON and length < _single(back_radius + radius):
                # Preserve direct component divisions, not reciprocal * delta.
                normal = _vector(
                    (delta[0] / length, delta[1] / length, delta[2] / length)
                )
                if length < back_radius:
                    candidate = _add(center, _scale(normal, back_radius))
                    back_applied = True
    # 59eac0c = original + (candidate-original) * widened Single stiffness.
    position = _add(
        original, _scale(_sub(candidate, original), _single(settings.motion.stiffness))
    )
    correction = _sub(position, original)
    velocity = _add(_vector(velocity_position), _scale(correction, _VELOCITY_RATIO))
    return MotionResult(
        position,
        velocity,
        correction,
        max_applied,
        back_applied,
        ("next_position", "velocity_position"),
    )


def solve_motion_slot(
    buffers: MotionBuffers,
    teams: Mapping[int, MotionTeam],
    parameters: Mapping[int, MotionSettings],
    *,
    step_particle_indices: Sequence[int],
    team_ids: Sequence[int],
    attributes: Sequence[int],
    depths: Sequence[float],
    slot: int,
) -> MotionVisit:
    """List ordinal -> global particle -> signed Int16 Team -> Int32 proxy.

    Both flags off returns before Team field/attribute/particle reads. Move
    bit2 precedes next/base/depth reads; IsMotion excludes bit8 after those
    reads. No Valid/team0/IsProcess/noCollision gate is invented. Negative
    native Team/pointer indices are rejected explicitly by this safe adapter.
    Friction and collisionNormal pointer arguments have no consumed writes.
    """
    slot = _integer(slot)
    particle = _integer(_item(step_particle_indices, slot))
    team_id = _integer(_item(team_ids, particle), -32768, 32767)
    if team_id < 0:
        raise ValueError("Adapter cannot resolve a negative native Team array index")
    if team_id not in parameters:
        raise ValueError("Adapter requires selected Motion parameters")
    settings = parameters[team_id]
    maximum, backstop = _flags(settings.motion)
    if not maximum and not backstop:
        return MotionVisit(slot, particle, team_id, None, "disabled", None, ())
    if team_id not in teams:
        raise ValueError("Adapter requires selected TeamData")
    team = teams[team_id]
    proxy = _integer(
        _wrap32(_integer(team.proxy_start) - _integer(team.particle_start) + particle)
    )
    attribute = _integer(_item(attributes, proxy), 0, 255)
    if not attribute & 2:
        return MotionVisit(slot, particle, team_id, proxy, "non-move", None, ())
    original = _item(buffers.next_positions, particle)
    base = _item(buffers.base_positions, particle)
    depth = _item(depths, proxy)
    if attribute & 8:
        return MotionVisit(slot, particle, team_id, proxy, "non-motion", None, ())
    result = motion_particle(
        original,
        _item(buffers.velocity_positions, particle),
        base,
        _item(buffers.base_rotations, particle),
        depth,
        settings,
    )
    return MotionVisit(slot, particle, team_id, proxy, "applied", result, result.writes)


def solve_motion_range(
    buffers: MotionBuffers,
    teams: Mapping[int, MotionTeam],
    parameters: Mapping[int, MotionSettings],
    *,
    step_particle_indices: Sequence[int],
    team_ids: Sequence[int],
    attributes: Sequence[int],
    depths: Sequence[float],
    index_count: int,
) -> MotionPassResult:
    """Range368896/59e9528: signed count snapshot, ascending serial ordinals.

    Repeated selections consume earlier writes. Original buffers stay private;
    outputs copy outer next/velocity sequences lazily, base inputs keep identity.
    The native range calls a runtime-selecting wrapper; this reference chooses
    audited finite managed/fallback math, not observed actual Burst dispatch.
    """
    count = _integer(index_count, -0x80000000)
    working = buffers
    positions = velocities = None
    visits = []
    for slot in range(max(0, count)):
        visit = solve_motion_slot(
            working,
            teams,
            parameters,
            step_particle_indices=step_particle_indices,
            team_ids=team_ids,
            attributes=attributes,
            depths=depths,
            slot=slot,
        )
        visits.append(visit)
        if visit.result is not None:
            if positions is None or velocities is None:
                positions, velocities = list(buffers.next_positions), list(
                    buffers.velocity_positions
                )
                working = replace(
                    buffers, next_positions=positions, velocity_positions=velocities
                )
            positions[visit.particle_index] = visit.result.next_position
            velocities[visit.particle_index] = visit.result.velocity_position
    if positions is not None and velocities is not None:
        working = replace(
            working,
            next_positions=tuple(positions),
            velocity_positions=tuple(velocities),
        )
    return MotionPassResult(working, tuple(visits))
