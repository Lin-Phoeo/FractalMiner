"""Finite Angle slot and serial range over explicit produced baseline inputs.

Managed368686/actual fallback59d5830 and ordinary Job368722 have separate
numeric seams. Range368687 and ordinary Execute368721 finish each baseline
before the next slot; no parallel ordering or actual Burst selection is claimed.
Index/finite/first-nonMove/nonzero policies are adapter premises. Raw native
struct copies, pointer aliasing and malformed-buffer read behavior are not modeled.
This does not produce lists/Team/proxy buffers, allocate or publish Unity bones.
"""

from collections.abc import Mapping, Sequence
from dataclasses import dataclass, replace
from typing import Literal

from official_physics_angle_baseline import (
    AngleSettings,
    BaselineResult,
    BaselineState,
    ResolvedBaseline,
    TeamWindow,
    resolve_baseline,
    solve_baseline,
    unpack_step_index,
)
from official_physics_point_pass import _integer, _item

AngleRoute = Literal["managed", "job"]


@dataclass(frozen=True)
class AnglePassTeam:
    window: TeamWindow
    gravity_dot: float  # TeamData@68, Single.


@dataclass(frozen=True)
class AnglePassParameters:
    use_limit: bool  # AngleConstraintParams@76.
    use_restoration: bool  # @0.
    limit_curve: Sequence[float]  # @80, already converted.
    limit_stiffness: float  # @144.
    restoration_curve: Sequence[float]  # @4, already converted (*0.2).
    restoration_attenuation: float  # @68.
    gravity_falloff: float  # @72.


@dataclass(frozen=True)
class AngleSlotResult:
    slot: int
    team_id: int
    baseline_index: int
    route: AngleRoute
    status: str
    state: BaselineState
    plan: ResolvedBaseline | None
    result: BaselineResult | None
    writes: tuple[str, ...]


@dataclass(frozen=True)
class AnglePassResult:
    state: BaselineState
    visits: tuple[AngleSlotResult, ...]


def _route(route: AngleRoute) -> AngleRoute:
    if route not in ("managed", "job"):
        raise ValueError("Adapter numeric route must be managed or job")
    return route


def solve_angle_slot(
    state: BaselineState,
    teams: Mapping[int, AnglePassTeam],
    parameters: Mapping[int, AnglePassParameters],
    *,
    packed_step_indices: Sequence[int],
    starts: Sequence[int],
    counts: Sequence[int],
    data: Sequence[int],
    parents: Sequence[int],
    attributes: Sequence[int],
    depths: Sequence[float],
    simulation_power_w: float,
    slot: int,
    route: AngleRoute = "managed",
) -> AngleSlotResult:
    """Unsigned high16 Team and low16 GLOBAL baseline, no Team flag filter.

    Sparse typed maps are explicit adapter storage. Both-disabled skips Team and
    baseline resolution. Native managed copies float4 power even before an empty
    range, whereas ordinary Job reads only w in restoration: this scalar API
    preserves value math, not exact raw memory-load behavior.
    """
    route = _route(route)
    slot = _integer(slot)
    team_id, baseline = unpack_step_index(_item(packed_step_indices, slot))
    if team_id not in parameters:
        raise ValueError("Adapter requires selected Angle parameters")
    settings = parameters[team_id]
    if (
        type(settings.use_limit) is not bool
        or type(settings.use_restoration) is not bool
    ):
        raise ValueError("Adapter Angle enable flags must be bool")
    if not settings.use_limit and not settings.use_restoration:
        return AngleSlotResult(
            slot, team_id, baseline, route, "disabled", state, None, None, ()
        )
    if team_id not in teams:
        raise ValueError("Adapter requires selected Angle TeamData")
    team = teams[team_id]
    # Reuse the checked single-Team resolver; only its Team table is locally
    # rebased. The global baseline index and all source buffer offsets stay intact.
    plan = resolve_baseline(
        baseline, (team.window,), starts, counts, data, parents, attributes, depths
    )
    plan = replace(plan, team_index=team_id)
    resolved = AngleSettings(
        settings.use_limit,
        settings.use_restoration,
        settings.limit_curve,
        settings.limit_stiffness,
        settings.restoration_curve,
        settings.restoration_attenuation,
        simulation_power_w,
        settings.gravity_falloff,
        team.gravity_dot,
    )
    result = solve_baseline(plan, state, resolved, ordinary_job=route == "job")
    writes: tuple[str, ...] = ()
    if plan.vertices:
        writes = ("rotations",)
        if len(plan.vertices) > 1:
            writes += ("edge_caches",)
        if result.visits:
            writes += ("next_positions", "velocity_positions")
    return AngleSlotResult(
        slot,
        team_id,
        baseline,
        route,
        "solved" if plan.vertices else "empty-baseline",
        result.state,
        plan,
        result,
        writes,
    )


def solve_angle_range(
    state: BaselineState,
    teams: Mapping[int, AnglePassTeam],
    parameters: Mapping[int, AnglePassParameters],
    *,
    packed_step_indices: Sequence[int],
    starts: Sequence[int],
    counts: Sequence[int],
    data: Sequence[int],
    parents: Sequence[int],
    attributes: Sequence[int],
    depths: Sequence[float],
    simulation_power_w: float,
    index_count: int,
    route: AngleRoute = "managed",
) -> AnglePassResult:
    """Signed count once, ascending slots, each entire three-pass baseline.

    Do not sort/deduplicate baselines or make Jacobi snapshots. The next slot
    receives all previous private writes; its enabled caches reinitialize once.
    No guessed range partition, native concurrent order or partial publication.
    """
    route = _route(route)
    count = _integer(index_count, -0x80000000)
    if count <= 0:
        return AnglePassResult(state, ())
    working = state
    visits = []
    for slot in range(count):
        visit = solve_angle_slot(
            working,
            teams,
            parameters,
            packed_step_indices=packed_step_indices,
            starts=starts,
            counts=counts,
            data=data,
            parents=parents,
            attributes=attributes,
            depths=depths,
            simulation_power_w=simulation_power_w,
            slot=slot,
            route=route,
        )
        visits.append(visit)
        working = visit.state
    return AnglePassResult(working, tuple(visits))
