"""Finite PreSimulationUpdate particle reset/history reference, not Unity physics.

Managed370446/5a6035c and DirectCall fallback5a597d8: process gates, reset14
buffers, otherwise negative-scale remap THEN inertia shift of seven histories.
Source chunk-index conversion and declared range order retained. No native array
allocation/publication, jobs, host reset request generation or Burst execution.
Finite/nonnegative bounded IDs/indexes, no Int32 overflow and degenerate rotation
rejection are ADAPTER restrictions, not native exception/clamp semantics.
Python Double/explicit Single math is not a game CRT/Burst bit oracle.
"""

from collections.abc import Mapping, Sequence
from dataclasses import dataclass, replace

from official_physics_angle_baseline import _integer
from official_physics_angle_cache import (
    _quaternion,
    multiply_quaternions,
    rotate_single,
)
from official_physics_angles import Quaternion, _float3
from official_physics_constraints import Vector3, _scale, _vector
from official_physics_frame_inertia import shift_world_position
from official_physics_matrix import Matrix4, transform_double_point
from official_physics_proxy_baseline import _int32, rotation_from_normal_tangent
from official_physics_scale_remap import transform_double_vector

_ZERO: Vector3 = (0.0, 0.0, 0.0)
_RESET_WRITES = (
    "next_position",
    "old_position",
    "old_rotation",
    "base_position",
    "base_rotation",
    "old_animation_position",
    "old_animation_rotation",
    "velocity_position",
    "display_position",
    "velocity",
    "real_velocity",
    "friction",
    "static_friction",
    "collision_normal",
)
_HISTORY_WRITES = (
    "old_position",
    "old_rotation",
    "old_animation_position",
    "old_animation_rotation",
    "display_position",
    "velocity",
    "real_velocity",
)


@dataclass(frozen=True)
class ParticleFrameState:
    next_position: Vector3  # Double3: nextPosArray.
    old_position: Vector3  # Double3: oldPosArray (simulation history).
    old_rotation: Quaternion  # oldRotArray; distinct from oldRotationArray.
    base_position: Vector3
    base_rotation: Quaternion
    old_animation_position: Vector3  # oldPositionArray (previous proxy pose).
    old_animation_rotation: Quaternion  # oldRotationArray.
    velocity_position: Vector3
    display_position: Vector3
    velocity: Vector3  # Single3.
    real_velocity: Vector3  # Single3, not solver velocity.
    friction: float  # Single.
    static_friction: float  # Single.
    collision_normal: Vector3  # Single3.


@dataclass(frozen=True)
class ParticleResetTeam:
    flag: int
    particle_chunk_start: int  # TeamData @372, original global particle start.
    proxy_common_chunk_start: int  # @292, original global proxy start.


@dataclass(frozen=True)
class ResolvedParticleFrameCenter:
    old_component_world_position: Vector3  # Center @152, not old/nowWorldPosition.
    frame_component_shift_vector: Vector3  # @204, Single.
    frame_component_shift_rotation: Quaternion  # @216, Single.
    negative_scale_matrix: Matrix4  # @568, SAME frame's already generated matrix.


@dataclass(frozen=True)
class ParticleFrameResult:
    state: ParticleFrameState
    writes: tuple[str, ...]  # Source order, not actual buffer publication.
    proxy_index: int | None
    reset_applied: bool


def transform_particle_rotation(rotation: Quaternion, matrix: Matrix4) -> Quaternion:
    """5a593a8 with caller sign=(1,1,1): rotated Y/Z, matrix*w0, rebuild.

    Single rotation BEFORE widening, full Double matrix products BEFORE Single
    narrowing. Native39d4250 ABI takes forward then up; existing value API takes
    normal/up then tangent/forward. No inverse-transpose or q auto-normalization.
    """
    up = _float3(
        _scale(transform_double_vector(matrix, rotate_single(rotation, (0, 1, 0))), 1.0)
    )
    forward = _float3(
        _scale(transform_double_vector(matrix, rotate_single(rotation, (0, 0, 1))), 1.0)
    )
    return rotation_from_normal_tangent(up, forward)


def prepare_particle_frame(
    state: ParticleFrameState,
    team: ParticleResetTeam,
    *,
    team_id: int,
    particle_index: int,
    proxy_positions: Sequence[Vector3],
    proxy_rotations: Sequence[Quaternion],
    center: ResolvedParticleFrameCenter | None = None,
) -> ParticleFrameResult:
    """One original global slot: team0 → IsProcess → reset4 OR history remap.

    No attribute/depth gate. Reset wins over40000/400 and copies proxy pose into
    six Double positions/three Single quaternions; clears five cache buffers.
    Otherwise40000 remaps first;400 shifts second. The other seven fields remain
    untouched. Skipped inputs are not normalized, validated or guessed.
    """
    team_id = _integer(team_id, 32767)
    if team_id == 0:
        return ParticleFrameResult(state, (), None, False)
    flag = _integer(team.flag, 2**64 - 1)
    if not flag & 2 or flag & ((1 << 61) | 0x10 | 0x800 | 0x80000):
        return ParticleFrameResult(state, (), None, False)
    if flag & 4:
        index = _integer(particle_index, 2**31 - 1)
        particle_start = _integer(team.particle_chunk_start, 2**31 - 1)
        proxy_start = _integer(team.proxy_common_chunk_start, 2**31 - 1)
        proxy_index = _integer(proxy_start - particle_start + index, 2**31 - 1)
        if proxy_index >= len(proxy_positions) or proxy_index >= len(proxy_rotations):
            raise ValueError("Adapter reset proxy index exceeds supplied pose buffers")
        p, q = (
            _vector(proxy_positions[proxy_index]),
            _quaternion(proxy_rotations[proxy_index]),
        )
        reset = ParticleFrameState(
            p, p, q, p, q, p, q, p, p, _ZERO, _ZERO, 0.0, 0.0, _ZERO
        )
        return ParticleFrameResult(reset, _RESET_WRITES, proxy_index, True)
    if not flag & (0x40000 | 0x400):
        return ParticleFrameResult(state, (), None, False)
    if center is None:
        raise ValueError("Adapter requires resolved history transform center")
    old, animation, display = map(
        _vector,
        (state.old_position, state.old_animation_position, state.display_position),
    )
    old_rotation, animation_rotation = map(
        _quaternion, (state.old_rotation, state.old_animation_rotation)
    )
    velocity, real_velocity = map(_float3, (state.velocity, state.real_velocity))
    if flag & 0x40000:
        matrix = center.negative_scale_matrix
        old = transform_double_point(matrix, old)
        old_rotation = transform_particle_rotation(old_rotation, matrix)
        animation = transform_double_point(matrix, animation)
        animation_rotation = transform_particle_rotation(animation_rotation, matrix)
        display = transform_double_point(matrix, display)
        velocity = _float3(transform_double_vector(matrix, velocity))
        real_velocity = _float3(transform_double_vector(matrix, real_velocity))
    if flag & 0x400:
        pivot = _vector(center.old_component_world_position)
        shift = _float3(center.frame_component_shift_vector)
        rotation = _quaternion(center.frame_component_shift_rotation)
        old = shift_world_position(old, pivot, shift, rotation)
        old_rotation = multiply_quaternions(rotation, old_rotation)
        animation = shift_world_position(animation, pivot, shift, rotation)
        animation_rotation = multiply_quaternions(rotation, animation_rotation)
        display = shift_world_position(display, pivot, shift, rotation)
        velocity = rotate_single(rotation, velocity)
        real_velocity = rotate_single(rotation, real_velocity)
    result = replace(
        state,
        old_position=old,
        old_rotation=old_rotation,
        old_animation_position=animation,
        old_animation_rotation=animation_rotation,
        display_position=display,
        velocity=velocity,
        real_velocity=real_velocity,
    )
    return ParticleFrameResult(result, _HISTORY_WRITES, None, False)


def prepare_particle_frames(
    states: Sequence[ParticleFrameState],
    team_ids: Sequence[int],
    teams: Mapping[int, ParticleResetTeam],
    *,
    proxy_positions: Sequence[Vector3],
    proxy_rotations: Sequence[Quaternion],
    index_count: int,
    centers: Mapping[int, ResolvedParticleFrameCenter] | None = None,
) -> tuple[ParticleFrameResult, ...]:
    """Original RangeKernel's ascending0..count-1, immutable/private value output.

    Count<=0 reads no arrays. Bound/missing-input checks are adapter protections;
    not a NativeArray parallel job or native partial-write exception contract.
    Caller MUST publish writes in the original phase, before StartSimulationStep.
    """
    count = _int32(index_count)
    if count <= 0:
        return ()
    if count > len(states) or count > len(team_ids):
        raise ValueError("Adapter declared range exceeds supplied particle buffers")
    result = []
    for index in range(count):
        team_id = _integer(team_ids[index], 32767)
        if team_id == 0:
            result.append(ParticleFrameResult(states[index], (), None, False))
            continue
        if team_id not in teams:
            raise ValueError("Adapter particle slot has no corresponding TeamData")
        result.append(
            prepare_particle_frame(
                states[index],
                teams[team_id],
                team_id=team_id,
                particle_index=index,
                proxy_positions=proxy_positions,
                proxy_rotations=proxy_rotations,
                center=None if centers is None else centers.get(team_id),
            )
        )
    return tuple(result)
