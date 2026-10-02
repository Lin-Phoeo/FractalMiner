"""Offline single-baseline angle reference, NOT the full physics/Unity solver.

Original managed kernel evidence: official-physics-angle-baseline-20261002 docs.
Reads serialized baseline order, copies basic rotations and runs three in-place
angle passes. Private working copies prevent partial publication on adapter error;
there is no inferred parallel scheduling, extra root rule, integration or collision.
Bounds/finite/first-movable rejection are adapter policy, not native exceptions.
"""

from collections.abc import Sequence
from dataclasses import dataclass
from typing import cast

from official_physics_angle_cache import (
    EdgeCache,
    _quaternion,
    initialize_edge_cache,
    limit_cached_edge,
)
from official_physics_angles import PairResult, Quaternion, restoration_pair
from official_physics_constraints import Vector3, _single


def _integer(value: int, maximum: int) -> int:
    if type(value) is not int or not 0 <= value <= maximum:
        raise ValueError("Adapter requires an integer within the declared range")
    return value


def _index(value: int, count: int) -> int:
    return _integer(value, count - 1)


def unpack_step_index(word: int) -> tuple[int, int]:
    """Int32 bit pattern: HIGH16 team, LOW16 GLOBAL baseline index (not local)."""
    if type(word) is not int or not -(2**31) <= word < 2**32:
        raise ValueError("Adapter requires Int32 or equivalent UInt32 bit pattern")
    unsigned = word & 0xFFFFFFFF
    return unsigned >> 16, unsigned & 0xFFFF


def is_movable(attribute: int) -> bool:
    """Native helper0x37e95c0 / IsMove test mask2 only; no other flag veto."""
    return bool(_integer(attribute, 255) & 2)


@dataclass(frozen=True)
class TeamWindow:
    particle_start: int
    particle_count: int
    proxy_start: int
    proxy_count: int
    baseline_data_start: int
    baseline_data_count: int


@dataclass(frozen=True)
class ResolvedVertex:
    local_index: int
    particle_index: int
    proxy_index: int
    parent_particle_index: int | None
    movable: bool
    parent_movable: bool
    depth: float


@dataclass(frozen=True)
class ResolvedBaseline:
    team_index: int
    baseline_index: int
    vertices: tuple[ResolvedVertex, ...]


def resolve_baseline(
    packed_step: int,
    teams: Sequence[TeamWindow],
    starts: Sequence[int],
    counts: Sequence[int],
    data: Sequence[int],
    parents: Sequence[int],
    attributes: Sequence[int],
    depths: Sequence[float],
) -> ResolvedBaseline:
    """Resolve three independent index spaces; never sort the UInt16 data.

    First SLOT skips parent/cache resolution, not necessarily local vertex zero.
    Native solve gates every slot only by IsMove. This finite reference rejects a
    movable first slot rather than pretending an extra native root gate exists.
    Parents outside this baseline but inside the team are supported; their current
    rotation/position cache is caller-owned. Cross-baseline scheduling is NOT inferred.
    """
    team_index, baseline_index = unpack_step_index(packed_step)
    team = teams[_index(team_index, len(teams))]
    for number in (
        team.particle_start,
        team.particle_count,
        team.proxy_start,
        team.proxy_count,
        team.baseline_data_start,
        team.baseline_data_count,
    ):
        _integer(number, 0x7FFFFFFF)
    start = _integer(starts[_index(baseline_index, len(starts))], 65535)
    count = _integer(counts[_index(baseline_index, len(counts))], 65535)
    if start + count > team.baseline_data_count:
        raise ValueError("Baseline slice outside the declared team data chunk")
    begin = team.baseline_data_start + start
    if begin + count > len(data):
        raise ValueError("Baseline slice outside the supplied data array")
    vertices = []
    for slot in range(count):
        local = _integer(data[begin + slot], 65535)
        _index(local, team.particle_count)
        _index(local, team.proxy_count)
        particle, proxy = team.particle_start + local, team.proxy_start + local
        move = is_movable(attributes[_index(proxy, len(attributes))])
        depth = _single(depths[_index(proxy, len(depths))])
        parent_particle = None
        parent_move = False
        if slot == 0:
            if move:
                raise ValueError("Adapter refuses a first slot marked movable")
        else:
            parent = parents[_index(proxy, len(parents))]
            _index(parent, team.particle_count)
            _index(parent, team.proxy_count)
            parent_particle = team.particle_start + parent
            parent_proxy = team.proxy_start + parent
            parent_move = is_movable(attributes[_index(parent_proxy, len(attributes))])
        vertices.append(
            ResolvedVertex(
                local, particle, proxy, parent_particle, move, parent_move, depth
            )
        )
    return ResolvedBaseline(team_index, baseline_index, tuple(vertices))


@dataclass(frozen=True)
class BaselineState:
    next_positions: tuple[Vector3, ...]
    velocity_positions: tuple[Vector3, ...]
    basic_positions: tuple[Vector3, ...]
    basic_rotations: tuple[Quaternion, ...]
    frictions: tuple[float, ...]
    rotations: tuple[Quaternion, ...]
    edge_caches: tuple[EdgeCache | None, ...]


@dataclass(frozen=True)
class AngleSettings:
    use_limit: bool
    use_restoration: bool
    limit_curve: Sequence[float]
    limit_stiffness: float
    restoration_curve: Sequence[float]
    restoration_attenuation: float
    power_w: float
    gravity_falloff: float
    gravity_dot: float


@dataclass(frozen=True)
class AngleVisit:
    iteration: int
    local_index: int
    phase: str


@dataclass(frozen=True)
class BaselineResult:
    state: BaselineState
    visits: tuple[AngleVisit, ...]


def solve_baseline(
    plan: ResolvedBaseline, state: BaselineState, settings: AngleSettings
) -> BaselineResult:
    """Consume resolve_baseline output and execute ONE baseline on copied arrays.

    The internal writes are immediately visible to the next edge/iteration, not
    Jacobi snapshots or separate all-limit/all-restoration sweeps. Disabled lanes
    and root edge caches are untouched. Cache initialization occurs ONCE, including
    fixed non-root vertices. Does not reset an unlisted parent to basic rotation.
    No ancestor recompute or restoration rotation-cache rewrite is invented.
    Result must be explicitly threaded into any subsequent caller-selected baseline;
    this API does not prove such ordering is correct for the game's Job scheduler.
    """
    if (
        type(settings.use_limit) is not bool
        or type(settings.use_restoration) is not bool
    ):
        raise ValueError("Adapter angle enable flags must be bool")
    if not (settings.use_limit or settings.use_restoration) or not plan.vertices:
        return BaselineResult(state, ())
    size = len(state.next_positions)
    if any(
        len(array) != size
        for array in (
            state.velocity_positions,
            state.basic_positions,
            state.basic_rotations,
            state.frictions,
            state.rotations,
            state.edge_caches,
        )
    ):
        raise ValueError("Adapter requires consistent particle-array lengths")
    p = list(state.next_positions)
    velocity = list(state.velocity_positions)
    rotation = list(state.rotations)
    cache = list(state.edge_caches)
    for vertex in plan.vertices:
        j = _index(vertex.particle_index, size)
        rotation[j] = _quaternion(state.basic_rotations[j])
        if vertex.parent_particle_index is not None:
            a = _index(vertex.parent_particle_index, size)
            edge = initialize_edge_cache(
                state.basic_positions[j],
                state.basic_positions[a],
                p[j],
                p[a],
                state.basic_rotations[a],
                state.basic_rotations[j],
                use_limit=settings.use_limit,
                use_restoration=settings.use_restoration,
            )
            previous = cache[j] or EdgeCache(None, None, None, None)
            cache[j] = EdgeCache(
                edge.local_direction
                if settings.use_limit
                else previous.local_direction,
                edge.local_rotation if settings.use_limit else previous.local_rotation,
                edge.cached_length if settings.use_limit else previous.cached_length,
                edge.restoration_world_vector
                if settings.use_restoration
                else previous.restoration_world_vector,
            )
    visits = []

    def write(pair: PairResult, j: int, a: int, parent_movable: bool) -> None:
        p[j], velocity[j] = pair.child_position, pair.child_velocity_position
        if parent_movable:
            p[a], velocity[a] = pair.parent_position, pair.parent_velocity_position

    for iteration in range(3):
        for vertex in plan.vertices:
            if not vertex.movable:
                continue
            j, a = vertex.particle_index, vertex.parent_particle_index
            if a is None:
                raise ValueError("Movable vertex requires a resolved parent edge")
            edge = cast(EdgeCache, cache[j])
            if settings.use_limit:
                out = limit_cached_edge(
                    p[j],
                    p[a],
                    velocity[j],
                    velocity[a],
                    rotation[a],
                    edge,
                    limit_curve=settings.limit_curve,
                    depth=vertex.depth,
                    limit_stiffness=settings.limit_stiffness,
                    child_friction=state.frictions[j],
                    parent_friction=state.frictions[a],
                    parent_movable=vertex.parent_movable,
                )
                write(out.pair, j, a, vertex.parent_movable)
                rotation[j] = out.child_rotation
                visits.append(AngleVisit(iteration, vertex.local_index, "limit"))
            if settings.use_restoration:
                pair = restoration_pair(
                    p[j],
                    p[a],
                    velocity[j],
                    velocity[a],
                    cast(Vector3, edge.restoration_world_vector),
                    converted_stiffness_curve=settings.restoration_curve,
                    depth=vertex.depth,
                    power_w=settings.power_w,
                    gravity_falloff=settings.gravity_falloff,
                    gravity_dot=settings.gravity_dot,
                    iteration=iteration,
                    child_friction=state.frictions[j],
                    parent_friction=state.frictions[a],
                    parent_movable=vertex.parent_movable,
                    velocity_attenuation=settings.restoration_attenuation,
                )
                write(pair, j, a, vertex.parent_movable)
                visits.append(AngleVisit(iteration, vertex.local_index, "restoration"))
    result = BaselineState(
        tuple(p),
        tuple(velocity),
        state.basic_positions,
        state.basic_rotations,
        state.frictions,
        tuple(rotation),
        tuple(cache),
    )
    return BaselineResult(result, tuple(visits))
