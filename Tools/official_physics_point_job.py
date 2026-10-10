"""Finite value reference for the separate ordinary Point Job Execute(index).

Source body368824/RVA0x59f5ae0 and its actual shape methods368825..368827.
Job shapes take Double radius, keep Double projection normals, and capsules
rotate the Double radial vector. They are NOT the managed kernel's helpers.
Curves/scale, published normals and normal accumulation are still Single.

Explicit produced WorkData and Team/proxy/list inputs are required. There is
no native buffer publication, worker scheduling, Burst equivalence, allocator,
original component identity resolution, or Unity bone output here. Strict
finite/unsupported/bounds rejection is adapter policy, not native behavior.
"""

from collections.abc import Mapping, Sequence

from official_physics_angles import _float3, _normalized, rotate_double
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
from official_physics_point_collision import (
    ColliderWork,
    PointCollisionParameters,
    PointCollisionResult,
    PointCollisionState,
    PointCollisionTeam,
    _lerp,
    _overlap,
    _plane_distance,
    _point_collision_particle,
    _segment_fraction,
)
from official_physics_point_pass import (
    PointPassTeam,
    PointVisit,
    _integer,
    _item,
    _wrap32,
)

_ZERO: Vector3 = (0.0, 0.0, 0.0)
_FAR_DISTANCE = 3.4028234663852886e38  # Double(Single.Max), both Job shapes.


def _job_contact(
    position: Vector3,
    base: Vector3,
    radius: float,
    limit: float,
    work: ColliderWork,
    shape: int,
    aabb_min: Vector3,
    aabb_max: Vector3,
) -> tuple[float, Vector3, Vector3]:
    if shape == 8:
        normal = _vector(work.old_points[0])
        surface = _add(_vector(work.next_points[0]), _scale(normal, radius))
        # Native publishes Single but passes the original Double3 to projection.
        distance, corrected = _plane_distance(position, surface, normal)
        return distance, corrected, _float3(normal)
    # The actual Job and managed shapes call the same asymmetric-z AABB helper.
    if not _overlap(aabb_min, aabb_max, work):
        return _FAR_DISTANCE, position, _ZERO
    old_a, next_a = _vector(work.old_points[0]), _vector(work.next_points[0])
    radius_a = _single(work.radii[0])
    if shape == 1:
        normal = _normalized(_sub(position, old_a))
        surface = _add(next_a, _scale(normal, _finite(radius_a + radius)))
    else:
        old_b, next_b = _vector(work.old_points[1]), _vector(work.next_points[1])
        fraction = _segment_fraction(position, old_a, old_b)
        radial = _sub(position, _lerp(old_a, old_b, fraction))
        local = rotate_double(work.inverse_old_rotation, radial)
        normal = _normalized(rotate_double(work.rotation, local))
        radius_b = _single(work.radii[1])
        interpolated = _single(
            _single(_single(radius_b - radius_a) * fraction) + radius_a
        )
        combined = _finite(interpolated + radius)  # Double addition, no narrowing.
        surface = _add(_lerp(next_a, next_b, fraction), _scale(normal, combined))
    distance, corrected = _plane_distance(position, surface, normal)
    if shape == 1 and limit > 0:
        # Job signature contains isSpring but the actual helper never reads it;
        # source gate is only maxLength > 0. Execute supplies -1 for ordinary.
        offset = _sub(corrected, base)
        length = _length(offset)
        if length > limit:
            corrected = _lerp(base, corrected, limit / length)
        if radius <= 0:
            raise ValueError("Adapter requires positive sphere spring radius")
        motion = _length(_sub(base, corrected))
        fraction = min(1.0, max(0.0, motion / radius)) * _single(0.85)
        corrected = _lerp(corrected, position, fraction)
        distance = _finite(distance * 3.0)
    return distance, corrected, _float3(normal)


def point_collision_job_particle(
    state: PointCollisionState,
    team: PointCollisionTeam,
    parameters: PointCollisionParameters,
    *,
    attribute: int,
    depth: float,
    colliders: Sequence[ColliderWork],
) -> PointCollisionResult:
    """Already-selected finite Job particle; no native Job dispatch is performed.

    Source-audited accumulation/gates are shared with the managed reference.
    Job contact arithmetic stays separate, so no path is silently converted
    into the other. Spring velocity adds the unscaled average correction,
    while next-position adds its normal-length-scaled counterpart.
    """
    return _point_collision_particle(
        state,
        team,
        parameters,
        attribute=attribute,
        depth=depth,
        colliders=colliders,
        contact=_job_contact,
    )


def solve_point_collision_job_slot(
    states: Sequence[PointCollisionState],
    teams: Mapping[int, PointPassTeam],
    parameters: Mapping[int, PointCollisionParameters],
    *,
    step_particle_indices: Sequence[int],
    team_ids: Sequence[int],
    attributes: Sequence[int],
    depths: Sequence[float],
    colliders: Sequence[ColliderWork],
    slot: int,
) -> PointVisit:
    """Resolve Execute's list ordinal and return its private logical writes.

    This body does not read NativeReference length; the scheduler decides which
    Execute indices exist. It has no Team0/IsProcess filter. Reusing typed value
    containers is not native layout/dispatch equivalence. No serial Job-range
    API is supplied: actual worker order and overlapping writes are unobserved.
    """
    slot = _integer(slot)
    particle = _integer(_item(step_particle_indices, slot))
    team_id = _integer(_item(team_ids, particle), -32768, 32767)
    if team_id not in teams:
        raise ValueError("Adapter requires selected TeamData")
    team = teams[team_id]

    def skipped(status: str, proxy: int | None = None) -> PointVisit:
        return PointVisit(slot, particle, team_id, proxy, status, None, ())

    count = _integer(team.collider_count)
    if count == 0:
        return skipped("empty-team-colliders")
    if team_id not in parameters:
        raise ValueError("Adapter requires selected ClothParameters")
    settings = parameters[team_id]
    if _integer(settings.mode, -0x80000000) != 1:
        return skipped("non-point-mode")
    proxy_start = _integer(team.proxy_start)
    particle_start = _integer(team.particle_start)
    proxy = _integer(_wrap32(proxy_start - particle_start + particle))
    state = _item(states, particle)
    attribute = _integer(_item(attributes, proxy), 0, 255)
    if attribute & 3 == 0:
        return skipped("invalid-vertex", proxy)
    if attribute & 0x10:
        return skipped("no-collision-vertex", proxy)
    spring = bool(_integer(team.flag, 0, 0xFFFFFFFFFFFFFFFF) & 0x2000)
    if not attribute & 2 and not spring:
        return skipped("fixed-ordinary", proxy)
    result = point_collision_job_particle(
        state,
        PointCollisionTeam(
            team.flag, team.scale_ratio, team.collider_chunk_start, count
        ),
        settings,
        attribute=attribute,
        depth=_item(depths, proxy),
        colliders=colliders,
    )
    return PointVisit(slot, particle, team_id, proxy, "solved", result, result.writes)
