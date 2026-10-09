"""Finite CalcDisplayPosition value reference, NOT a Unity/Burst display job.

Managed370578/5a6da04 and DirectCall fallback5a6857c: predict from realVelocity,
unclamped clock interpolation, root-radius clamp, clamped proxy blend, conditional
animation history and negative-scale rotation publication. Positions stay Double.
The serial range preserves earlier proxy writes when later particles read roots;
it does NOT certify real parallel range partitioning, allocator or host scheduling.
Finite/nonnegative IDs/no-overflow/degenerate checks are ADAPTER policy, not native
exception, NaN propagation or normalization policy. No original DLL is executed.
"""

from collections.abc import Mapping, Sequence
from dataclasses import dataclass, replace
from typing import cast

from official_physics_angle_baseline import _integer
from official_physics_angle_cache import _quaternion
from official_physics_angles import Quaternion, _float3
from official_physics_constraints import (
    Vector3,
    _add,
    _finite,
    _length,
    _scale,
    _single,
    _sub,
    _vector,
)
from official_physics_matrix import build_double_trs
from official_physics_particle_reset import ParticleFrameState
from official_physics_proxy_baseline import _int32, rotation_from_normal_tangent


@dataclass(frozen=True)
class DisplayTeam:
    flag: int
    particle_chunk_start: int  # TeamData @372.
    proxy_common_chunk_start: int  # @292.
    time: float  # @20, Single; NOT frameUpdateTime.
    old_time: float  # @24, Single; NOT frameOldTime.
    now_update_time: float  # @28, Single.
    blend_weight: float  # @260, not clothSimulateWeight alone.
    negative_scale_direction: Vector3  # @104, Single signs, NOT initScale.


@dataclass(frozen=True)
class ParticleDisplayResult:
    state: ParticleFrameState
    proxy_index: int | None
    proxy_position: Vector3 | None  # Only present when this slot is written.
    proxy_rotation: Quaternion | None
    writes: tuple[str, ...]  # Source order; no actual NativeArray write.
    interpolation: float | None


@dataclass(frozen=True)
class DisplayRangeResult:
    results: tuple[ParticleDisplayResult, ...]
    proxy_positions: Sequence[Vector3]
    proxy_rotations: Sequence[Quaternion]


def restore_negative_proxy_rotation(
    rotation: Quaternion, negative_scale_direction: Vector3
) -> Quaternion:
    """305d310 TRS(0,q,sign), columns1/2 →39d4200→39d4250.

    build_double_trs constructs the same Single quaternion matrix, then widens
    and column-scales. Narrowing its scaled columns reproduces the source's
    Single column multiplication for finite values. Do not use rotate(q,Y/Z):
    for a nonunit q that has a different operation path. API order is up,forward.
    """
    matrix = build_double_trs((0, 0, 0), rotation, negative_scale_direction)
    up = cast(Vector3, tuple(_single(v) for v in matrix[1][:3]))
    forward = cast(Vector3, tuple(_single(v) for v in matrix[2][:3]))
    return rotation_from_normal_tangent(up, forward)


def _lerp(a: Vector3, b: Vector3, ratio: float) -> Vector3:
    # Native59eac0c: a + (b-a)*Double(ratio), no clamp or fused multiply-add.
    return _add(a, _scale(_sub(b, a), ratio))


def calculate_display_particle(
    state: ParticleFrameState,
    team: DisplayTeam,
    *,
    team_id: int,
    particle_index: int,
    simulation_delta_time: float,
    attributes: Sequence[int],
    proxy_positions: Sequence[Vector3],
    proxy_rotations: Sequence[Quaternion],
    vertex_root_indices: Sequence[int],
) -> ParticleDisplayResult:
    """One global particle: process gate, display/proxy, flag20 history, flag20000 q.

    Movable attribute2 OR spring Team2000 enables prediction. Nonmoving ordinary
    slots write only display=animation, plus selected optional history/rotation.
    History20 copies the ORIGINAL proxy pose, never the blended/negated output.
    Skipped branch fields stay untouched; missing consumed inputs are not guessed.
    """
    team_id = _integer(team_id, 32767)
    if team_id == 0:
        return ParticleDisplayResult(state, None, None, None, (), None)
    flag = _integer(team.flag, 2**64 - 1)
    if not flag & 2 or flag & ((1 << 61) | 0x10 | 0x800 | 0x80000):
        return ParticleDisplayResult(state, None, None, None, (), None)
    index = _integer(particle_index, 2**31 - 1)
    start = _integer(team.proxy_common_chunk_start, 2**31 - 1)
    particle_start = _integer(team.particle_chunk_start, 2**31 - 1)
    vertex = _integer(start - particle_start + index, 2**31 - 1)
    if (
        vertex >= len(attributes)
        or vertex >= len(proxy_positions)
        or vertex >= len(proxy_rotations)
    ):
        raise ValueError("Adapter display proxy index exceeds supplied buffers")
    attribute = _integer(attributes[vertex], 255)
    animation = _vector(proxy_positions[vertex])
    rotation = _quaternion(proxy_rotations[vertex])
    writes = ["display_position"]
    proxy_position = None
    interpolation = None
    display = animation
    if attribute & 2 or flag & 0x2000:
        dt = _single(simulation_delta_time)
        velocity = _float3(state.real_velocity)
        displacement = cast(Vector3, tuple(_single(v * dt) for v in velocity))
        prediction = _add(_vector(state.old_position), displacement)
        now, old = _single(team.now_update_time), _single(team.old_time)
        denominator = _single(_single(now + dt) - old)
        interpolation = (
            _single(_single(_single(team.time) - old) / denominator)
            if denominator > 0
            else 0.0
        )
        display = _lerp(_vector(state.display_position), prediction, interpolation)
        if vertex >= len(vertex_root_indices):
            raise ValueError("Adapter requires the consumed proxy root index")
        local_root = _int32(vertex_root_indices[vertex])
        if local_root >= 0:
            root_index = _integer(start + local_root, 2**31 - 1)
            if root_index >= len(proxy_positions):
                raise ValueError("Adapter root index exceeds supplied proxy positions")
            root = _vector(proxy_positions[root_index])
            delta = _sub(display, root)
            radius = _finite(_length(_sub(root, animation)) * 1.2999999523162842)
            length = _length(delta)
            if length > 9.999999717180685e-10 and length > radius:
                delta = _scale(delta, radius / length)
            display = _add(root, delta)
        weight = _single(team.blend_weight)
        # Native59e89e4 has endpoint returns; do not evaluate unused lerp at0/1.
        proxy_position = (
            animation
            if weight <= 0
            else display
            if weight >= 1
            else _lerp(animation, display, weight)
        )
        writes.append("proxy_position")
    result = replace(state, display_position=display)
    if flag & 0x20:
        result = replace(
            result, old_animation_position=animation, old_animation_rotation=rotation
        )
        writes.extend(("old_animation_position", "old_animation_rotation"))
    proxy_rotation = None
    if flag & 0x20000:
        proxy_rotation = restore_negative_proxy_rotation(
            rotation, team.negative_scale_direction
        )
        writes.append("proxy_rotation")
    return ParticleDisplayResult(
        result, vertex, proxy_position, proxy_rotation, tuple(writes), interpolation
    )


def calculate_display_positions(
    states: Sequence[ParticleFrameState],
    team_ids: Sequence[int],
    teams: Mapping[int, DisplayTeam],
    *,
    simulation_delta_time: float,
    attributes: Sequence[int],
    proxy_positions: Sequence[Vector3],
    proxy_rotations: Sequence[Quaternion],
    vertex_root_indices: Sequence[int],
    index_count: int,
) -> DisplayRangeResult:
    """Serial RangeKernel370579 order, privately apply writes to mutable proxy copy.

    A later root read sees earlier writes. No independent immutable-root snapshot
    substitution, caller mutation, real native partial-write exception behavior or
    claim about concurrent native job ranges. Count<=0 evaluates no slot/time or
    proxy element and passes through the original buffers. Positive-count output
    snapshots the outer sequence only; immutable Vector3/Quaternion tuples are
    part of this typed API contract, while unconsumed inner values are not copied.
    """
    count = _int32(index_count)
    if count <= 0:
        return DisplayRangeResult((), proxy_positions, proxy_rotations)
    positions, rotations = list(proxy_positions), list(proxy_rotations)
    if count > len(states) or count > len(team_ids):
        raise ValueError("Adapter declared display range exceeds particle buffers")
    results = []
    for index in range(count):
        team_id = _integer(team_ids[index], 32767)
        if team_id == 0:
            results.append(
                ParticleDisplayResult(states[index], None, None, None, (), None)
            )
            continue
        if team_id not in teams:
            raise ValueError("Adapter particle has no corresponding display TeamData")
        result = calculate_display_particle(
            states[index],
            teams[team_id],
            team_id=team_id,
            particle_index=index,
            simulation_delta_time=simulation_delta_time,
            attributes=attributes,
            proxy_positions=positions,
            proxy_rotations=rotations,
            vertex_root_indices=vertex_root_indices,
        )
        results.append(result)
        if result.proxy_index is not None:
            if result.proxy_position is not None:
                positions[result.proxy_index] = result.proxy_position
            if result.proxy_rotation is not None:
                rotations[result.proxy_index] = result.proxy_rotation
    return DisplayRangeResult(tuple(results), tuple(positions), tuple(rotations))
