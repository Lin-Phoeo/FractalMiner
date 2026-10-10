"""Finite serial Point Range reference over explicit, already-produced inputs.

Range368741/0x59ea2b4 reads signed *lengthPtr once and calls the Point wrapper
for list ordinals 0..length-1. Selected-particle math uses the existing managed
Point reference. The list supplies global particles; TeamData maps
them to proxy vertices. Duplicate selections observe earlier serial writes.

This is not native Job scheduling, a Burst implementation, the separate
Point Job Execute(index) body, list/WorkData production, or Unity bone output.
Sequences/maps and private outer copies are adapter representations. Strict
bounds/types and finite-domain rejection are adapter policy, not native faults.
"""

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import TypeVar

from official_physics_point_collision import (
    ColliderWork,
    PointCollisionParameters,
    PointCollisionResult,
    PointCollisionState,
    PointCollisionTeam,
    point_collision_particle,
)

T = TypeVar("T")


def _integer(value: object, minimum: int = 0, maximum: int = 0x7FFFFFFF) -> int:
    if type(value) is not int or not minimum <= value <= maximum:
        raise ValueError("Adapter requires an integer in the supplied source domain")
    return value


def _item(values: Sequence[T], index: int) -> T:
    _integer(index)
    if index >= len(values):
        raise ValueError("Adapter Point index exceeds supplied buffer")
    return values[index]


def _wrap32(value: int) -> int:
    return ((value + 0x80000000) & 0xFFFFFFFF) - 0x80000000


@dataclass(frozen=True)
class PointPassTeam:
    flag: int  # TeamData BitField64 @0; Spring bit13, no IsProcess gate here.
    scale_ratio: float  # Single @96.
    proxy_start: int  # proxyCommonChunk.startIndex @292.
    particle_start: int  # particleChunk.startIndex @372.
    collider_chunk_start: int  # colliderChunk.startIndex @380.
    collider_count: int  # @396; exact zero is the source gate.


@dataclass(frozen=True)
class PointVisit:
    slot: int
    particle_index: int
    team_id: int
    proxy_index: int | None
    status: str
    result: PointCollisionResult | None
    writes: tuple[str, ...]


@dataclass(frozen=True)
class PointPassResult:
    states: tuple[PointCollisionState, ...]
    visits: tuple[PointVisit, ...]


def solve_point_collision_slot(
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
    """Resolve one list ordinal; return its logical writes without mutating inputs.

    parameters[team].radius_curve is ClothParameters.radiusCurveData @92,
    not a field of colliderCollisionConstraint @612. Its mode and limit curve
    represent that substructure's mode @0 and limitDistance @12. Callers must
    supply those decoded curves explicitly; no serialized-field guess is made.
    team_ids is signed Int16. Explicit mapping keys retain its sign; this does
    not certify that a negative ID can safely index a real native Team array.
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
    result = point_collision_particle(
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


def solve_point_collision_range(
    states: Sequence[PointCollisionState],
    teams: Mapping[int, PointPassTeam],
    parameters: Mapping[int, PointCollisionParameters],
    *,
    step_particle_indices: Sequence[int],
    team_ids: Sequence[int],
    attributes: Sequence[int],
    depths: Sequence[float],
    colliders: Sequence[ColliderWork],
    index_count: int,
) -> PointPassResult:
    """Execute the successful finite managed Range path in original list order.

    index_count is the explicit snapshot of signed *lengthPtr, independent of
    the work-list buffer's capacity. Nonpositive values do no particle work.
    Only selected written states are replaced; untouched objects and all
    unwritten state fields preserve their original representation. Duplicate
    particles are intentionally retained and consume previous serial results.
    Exceptions cannot leave partial changes in the caller's supplied states.
    An empty arithmetic range does not imply any host JobHandle dependency
    was preserved, completed, or scheduled: that is a separate host decision.
    """
    count = _integer(index_count, -0x80000000)
    if count <= 0:
        return PointPassResult(tuple(states), ())
    if count > len(step_particle_indices):
        raise ValueError("Adapter Point length exceeds supplied work list")
    current = list(states)
    visits = []
    for slot in range(count):
        visit = solve_point_collision_slot(
            current,
            teams,
            parameters,
            step_particle_indices=step_particle_indices,
            team_ids=team_ids,
            attributes=attributes,
            depths=depths,
            colliders=colliders,
            slot=slot,
        )
        if visit.writes:
            result = visit.result
            if result is None:
                raise RuntimeError(
                    "Adapter Point visit published writes without a result"
                )
            current[visit.particle_index] = result.state
        visits.append(visit)
    return PointPassResult(tuple(current), tuple(visits))
