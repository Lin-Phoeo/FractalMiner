"""Finite source-bound world/local bone BUFFER writeback, not Unity setters.

Managed fallback kernels369808/0x5a42b30 and369832/0x5a56ba0. Source world
positions are double3, rotations/scale float3/quaternion. Copy world position;
worldRotation = proxyRotation * (vertexToTransformRotation *component* sign).
Local Move/parented slots use inverse(parentQuaternion), DOUBLE world delta and
rotation, parent scale division, final Single position; local quaternion sign
is component-multiplied AFTER inverseParent*childWorldRotation. No normalization.

Original Team common/transform/bone chunk starts and native Job-list order are
REQUIRED. This is not original list construction, Team publication, scheduling,
normal-axis closure, simulation, setter execution, or a live-game/Burst oracle.
Finite/range/zero-scale/duplicate-writer rejection is adapter-only safety policy.
"""

import math
from collections.abc import Sequence
from dataclasses import dataclass
from typing import cast

from official_physics_angle_baseline import _index, _integer
from official_physics_angle_cache import (
    _quaternion,
    multiply_quaternions,
    quaternion_inverse,
)
from official_physics_angles import Quaternion, _float3
from official_physics_constraints import Vector3, _single
from official_physics_proxy_baseline import LocalPose, _int32

Double3 = tuple[float, float, float]


def _double(value: float) -> float:
    if not isinstance(value, (int, float)) or isinstance(value, bool):
        raise ValueError("Adapter requires finite Double values")  # noqa: TRY004 (uniform adapter contract)
    try:
        converted = float(value)
    except OverflowError as error:
        raise ValueError("Adapter Double overflow") from error
    if not math.isfinite(converted):
        raise ValueError("Adapter requires finite Double values")
    return converted


def _double3(value: Sequence[float]) -> Double3:
    if len(value) != 3:
        raise ValueError("Adapter requires a double3")
    return cast(Double3, tuple(_double(lane) for lane in value))


def _cross_double(a: Double3, b: Double3) -> Double3:
    return _double3(
        (
            a[1] * b[2] - a[2] * b[1],
            a[2] * b[0] - a[0] * b[2],
            a[0] * b[1] - a[1] * b[0],
        )
    )


def rotate_double(quaternion: Quaternion, vector: Double3) -> Double3:
    """0x59d732c: widen original Single q, t=2*cross(q.xyz,v), (v+w*t)+cross.

    All vector arithmetic is Double, not rotate_single followed by widening.
    Nonunit quaternion magnitude is deliberately preserved. No FMA reassociation.
    """
    q, v = _quaternion(quaternion), _double3(vector)
    xyz = cast(Double3, q[:3])
    t = _double3(tuple(2.0 * lane for lane in _cross_double(xyz, v)))
    scaled = _double3(tuple(q[3] * lane for lane in t))
    first = _double3(tuple(a + b for a, b in zip(v, scaled, strict=True)))
    return _double3(
        tuple(a + b for a, b in zip(first, _cross_double(xyz, t), strict=True))
    )


def _component_sign(q: Quaternion, sign: Quaternion) -> Quaternion:
    q, sign = _quaternion(q), _quaternion(sign)
    return cast(Quaternion, tuple(_single(a * b) for a, b in zip(q, sign, strict=True)))


@dataclass(frozen=True)
class WorldBonePose:
    positions: tuple[Double3, ...]
    rotations: tuple[Quaternion, ...]


@dataclass(frozen=True)
class BoneWritebackTeam:
    common_start: int
    transform_start: int
    bone_start: int
    vertex_count: int
    negative_scale_quaternion_value: Quaternion


def _world(pose: WorldBonePose) -> WorldBonePose:
    count = _integer(len(pose.positions), 65536)
    if len(pose.rotations) != count:
        raise ValueError("Adapter requires parallel world-position/rotation buffers")
    return WorldBonePose(
        tuple(_double3(p) for p in pose.positions),
        tuple(_quaternion(q) for q in pose.rotations),
    )


def _jobs(indices: Sequence[int], team_ids: Sequence[int]) -> tuple[int, ...]:
    count = _integer(len(team_ids), 65536)
    for team in team_ids:
        _integer(team, 32767)  # Native signed Int16; negative native indexing excluded.
    result = tuple(_index(index, count) for index in indices)
    if len(set(result)) != len(result):
        raise ValueError("Adapter rejects duplicate parallel Job writers")
    return result


def _team(
    team_id: int, teams: Sequence[BoneWritebackTeam | None]
) -> BoneWritebackTeam | None:
    if team_id == 0:
        return None  # Source exits before reading TeamData or offsets.
    team = teams[_index(team_id, len(teams))]
    if team is None:
        raise ValueError("Adapter requires original TeamData for a nonzero team")
    return team


def _slot(vertex: int, team: BoneWritebackTeam, target_count: int) -> tuple[int, int]:
    start = _integer(team.common_start, 2**31 - 1)
    transform = _integer(team.transform_start, 2**31 - 1)
    _integer(team.bone_start, 2**31 - 1)
    relative = _index(vertex - start, _integer(team.vertex_count, 65536))
    return relative, _index(_integer(transform + relative, 2**31 - 1), target_count)


def _unique(target: int, seen: set[int]) -> None:
    if target in seen:
        raise ValueError("Adapter rejects aliasing parallel output writers")
    seen.add(target)


def write_world_bone_pose(
    job_vertices: Sequence[int],
    team_ids: Sequence[int],
    teams: Sequence[BoneWritebackTeam | None],
    proxy_world: WorldBonePose,
    vertex_to_transform_rotations: Sequence[Quaternion],
    initial_transform_world: WorldBonePose,
) -> WorldBonePose:
    """Original world-buffer kernel: no additional attr/Fixed/Move flag gate.

    relative=vertex-common.start; output=transform.start+relative;
    offsetRotation=vertexToTransform[bone.start+relative]. Position is copied
    unchanged in Double. Preserve unlisted/zero-team output slots. Caller must
    supply original gated list; this API is not a Transform setter or list builder.
    """
    proxy, initial = _world(proxy_world), _world(initial_transform_world)
    if len(team_ids) != len(proxy.positions):
        raise ValueError("Adapter requires parallel proxy/team buffers")
    positions, rotations = list(initial.positions), list(initial.rotations)
    seen: set[int] = set()
    for vertex in _jobs(job_vertices, team_ids):
        team = _team(team_ids[vertex], teams)
        if team is None:
            continue
        relative, target = _slot(vertex, team, len(positions))
        offset = _index(
            _integer(team.bone_start + relative, 2**31 - 1),
            len(vertex_to_transform_rotations),
        )
        _unique(target, seen)
        adjusted = _component_sign(
            vertex_to_transform_rotations[offset], team.negative_scale_quaternion_value
        )
        positions[target] = proxy.positions[vertex]
        rotations[target] = multiply_quaternions(proxy.rotations[vertex], adjusted)
    return WorldBonePose(tuple(positions), tuple(rotations))


def write_local_bone_pose(
    job_vertices: Sequence[int],
    team_ids: Sequence[int],
    teams: Sequence[BoneWritebackTeam | None],
    attributes: Sequence[int],
    vertex_parent_indices: Sequence[int],
    transform_world: WorldBonePose,
    transform_scales: Sequence[Vector3],
    initial_transform_local: LocalPose,
) -> LocalPose:
    """Original local-buffer kernel, source world buffers immutable during pass.

    Only nonzero-team, parent>=0, Move(bit2) vertices write. parent index is
    Team-relative (parentTransform=transform.start+parent), NOT global or PPtr.
    Parent scale is the PROVIDED transformScaleArray, not inferred localScale,
    abs(scale), initScale or scaleRatio. Negative signs are retained; active zero
    scales fail rather than introducing an unobserved epsilon correction.
    """
    world = _world(transform_world)
    count = len(team_ids)
    if len(attributes) != count or len(vertex_parent_indices) != count:
        raise ValueError("Adapter requires parallel ordered proxy buffers")
    if any(
        len(buffer) != len(world.positions)
        for buffer in (
            transform_scales,
            initial_transform_local.positions,
            initial_transform_local.rotations,
        )
    ):
        raise ValueError("Adapter requires parallel ordered transform buffers")
    attrs = tuple(_integer(a, 255) for a in attributes)
    parents = tuple(_int32(p) for p in vertex_parent_indices)
    scales = tuple(_float3(s) for s in transform_scales)
    positions = [_float3(p) for p in initial_transform_local.positions]
    rotations = [_quaternion(q) for q in initial_transform_local.rotations]
    seen: set[int] = set()
    for vertex in _jobs(job_vertices, team_ids):
        team = _team(team_ids[vertex], teams)
        if team is None or parents[vertex] < 0 or not attrs[vertex] & 2:
            continue
        _, target = _slot(vertex, team, len(positions))
        parent_relative = _index(parents[vertex], team.vertex_count)
        parent = _index(
            _integer(team.transform_start + parent_relative, 2**31 - 1), len(positions)
        )
        _unique(target, seen)
        inverse = quaternion_inverse(world.rotations[parent])
        delta = _double3(
            tuple(
                a - b
                for a, b in zip(
                    world.positions[target], world.positions[parent], strict=True
                )
            )
        )
        rotated = rotate_double(inverse, delta)
        if any(s == 0 for s in scales[parent]):
            raise ValueError("Adapter refuses an active zero parent scale")
        positions[target] = cast(
            Vector3,
            tuple(
                _single(_double(p / s))
                for p, s in zip(rotated, scales[parent], strict=True)
            ),
        )
        rotations[target] = _component_sign(
            multiply_quaternions(inverse, world.rotations[target]),
            team.negative_scale_quaternion_value,
        )
    return LocalPose(tuple(positions), tuple(rotations))
