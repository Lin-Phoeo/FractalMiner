"""Finite DistanceConstraint kernel/range reference over explicit input buffers.

Managed368841/59eafdc and range368842/59e6b64. Work slots select global
particles; adjacency links hold team-local UInt16 vertices. Sequential writes
are visible to later work slots. Actual Job partitioning/Burst dispatch and
work-list/adjacency production remain caller responsibilities. Typed vector
tuples and outer private copies provide adapter isolation, not NativeArray
failure semantics. Bounds/finite rejection is adapter policy.
"""

from collections.abc import Mapping, Sequence
from dataclasses import dataclass, replace
from typing import TypeVar

from official_physics_angle_baseline import _integer
from official_physics_constraints import (
    DistanceNeighbor,
    DistanceResult,
    Vector3,
    _length,
    _single,
    _sub,
    _vector,
    distance_particle,
    evaluate_curve,
    inverse_mass,
)
from official_physics_proxy_baseline import _int32

T = TypeVar("T")


def _item(values: Sequence[T], index: int) -> T:
    _integer(index, 0x7FFFFFFF)
    if index >= len(values):
        raise ValueError("Adapter distance index exceeds supplied buffer")
    return values[index]


def unpack_distance_index(word: int) -> tuple[int, int]:
    """UInt32 bit pattern: high12 count, low20 team-local adjacency start."""
    if type(word) is not int or not -(2**31) <= word < 2**32:
        raise ValueError("Adapter requires Int32 or equivalent UInt32 bit pattern")
    unsigned = word & 0xFFFFFFFF
    return unsigned >> 20, unsigned & 0xFFFFF


@dataclass(frozen=True)
class DistancePassTeam:
    flag: int
    particle_start: int  # TeamData @372.
    proxy_start: int  # @292.
    distance_start: int  # @400.
    distance_start_count: int  # @404; zero is the source gate.
    distance_data_start: int  # @408.
    init_scale_x: float  # @84, Single.
    scale_ratio: float  # @96, Single in this kernel.
    animation_pose_ratio: float  # @232.


@dataclass(frozen=True)
class DistancePassSettings:
    stiffness_curve: Sequence[float]
    velocity_attenuation: float


@dataclass(frozen=True)
class DistanceBuffers:
    next_positions: Sequence[Vector3]
    base_positions: Sequence[Vector3]
    velocity_positions: Sequence[Vector3]
    frictions: Sequence[float]


@dataclass(frozen=True)
class DistanceVisit:
    slot: int
    particle_index: int
    team_id: int
    proxy_index: int | None
    neighbor_indices: tuple[int, ...]
    status: str
    center_inverse_mass: float | None
    result: DistanceResult | None
    writes: tuple[str, ...]


@dataclass(frozen=True)
class DistancePassResult:
    buffers: DistanceBuffers
    visits: tuple[DistanceVisit, ...]


def solve_distance_slot(
    buffers: DistanceBuffers,
    teams: Mapping[int, DistancePassTeam],
    parameters: Mapping[int, DistancePassSettings],
    *,
    step_particle_indices: Sequence[int],
    team_ids: Sequence[int],
    attributes: Sequence[int],
    depths: Sequence[float],
    adjacency_words: Sequence[int],
    neighbor_local_indices: Sequence[int],
    signed_rest_lengths: Sequence[float],
    simulation_power_y: float,
    slot: int,
) -> DistanceVisit:
    """Resolve ONE work-list ordinal and return its two optional logical writes.

    No team0 or IsProcess gate exists here: eligibility is partly provided by the
    step list. Invalid means (attribute&3)==0; fixed means (attribute&2)==0.
    Fixed centers run only on Spring teams; fixed neighbors always participate.
    Only valid-length edges enter the arithmetic/count. No contribution means
    no writes and no velocity/attenuation read. Input production is not inferred.
    """
    slot = _integer(slot, 0x7FFFFFFF)
    particle = _integer(_item(step_particle_indices, slot), 0x7FFFFFFF)
    team_id = _integer(_item(team_ids, particle), 32767)
    if team_id not in teams or team_id not in parameters:
        raise ValueError("Adapter requires selected TeamData and ClothParameters")
    team, settings = teams[team_id], parameters[team_id]
    rest_scale = _single(_single(team.init_scale_x) * _single(team.scale_ratio))
    particle_start = _integer(team.particle_start, 0x7FFFFFFF)
    proxy_start = _integer(team.proxy_start, 0x7FFFFFFF)
    start = _integer(team.distance_start, 0x7FFFFFFF)
    start_count = _integer(team.distance_start_count, 0x7FFFFFFF)
    local = _integer(particle - particle_start, 0x7FFFFFFF)

    def skipped(status: str, proxy: int | None = None) -> DistanceVisit:
        return DistanceVisit(slot, particle, team_id, proxy, (), status, None, None, ())

    if not start_count:
        return skipped("empty-team-adjacency")
    proxy = _integer(proxy_start + local, 0x7FFFFFFF)
    position = _vector(_item(buffers.next_positions, particle))
    attribute = _integer(_item(attributes, proxy), 255)
    depth = _single(_item(depths, proxy))
    friction = _single(_item(buffers.frictions, particle))
    if not attribute & 3:
        return skipped("invalid-vertex", proxy)
    spring = bool(_integer(team.flag, 2**64 - 1) & 0x2000)
    fixed = not bool(attribute & 2)
    if fixed and not spring:
        return skipped("fixed-ordinary", proxy)
    fixed_mass = 10 if spring else 50
    mass = inverse_mass(friction, depth, fixed=fixed, fixed_mass=fixed_mass)
    # Source evaluates center stiffness before reading the packed adjacency gate.
    power = _single(simulation_power_y)
    _single(min(1, max(0, evaluate_curve(settings.stiffness_curve, depth))) * power)
    count, adjacency_start = unpack_distance_index(
        _item(adjacency_words, start + local)
    )
    if not count:
        return skipped("no-neighbors", proxy)
    base = _vector(_item(buffers.base_positions, particle))
    data_start = _integer(team.distance_data_start, 0x7FFFFFFF)
    neighbors = []
    indices = []
    for edge_slot in range(count):
        edge_index = _integer(data_start + adjacency_start + edge_slot, 0x7FFFFFFF)
        other_local = _integer(_item(neighbor_local_indices, edge_index), 65535)
        rest = _single(_item(signed_rest_lengths, edge_index))
        other_particle = _integer(particle_start + other_local, 0x7FFFFFFF)
        other_proxy = _integer(proxy_start + other_local, 0x7FFFFFFF)
        other = _vector(_item(buffers.next_positions, other_particle))
        other_base = _vector(_item(buffers.base_positions, other_particle))
        other_friction = _single(_item(buffers.frictions, other_particle))
        other_attribute = _integer(_item(attributes, other_proxy), 255)
        other_depth = _single(_item(depths, other_proxy))
        if _length(_sub(other, position)) < 9.99999993922529e-9:
            continue
        other_mass = inverse_mass(
            other_friction,
            other_depth,
            fixed=not bool(other_attribute & 2),
            fixed_mass=fixed_mass,
        )
        neighbors.append(DistanceNeighbor(other, other_base, rest, other_mass))
        indices.append(other_particle)
    if not neighbors:
        return skipped("no-nondegenerate-edges", proxy)
    result = distance_particle(
        position,
        base,
        _item(buffers.velocity_positions, particle),
        neighbors,
        center_inverse_mass=mass,
        stiffness_curve=settings.stiffness_curve,
        depth=depth,
        simulation_power_y=power,
        rest_scale=rest_scale,
        animation_pose_ratio=team.animation_pose_ratio,
        velocity_attenuation=settings.velocity_attenuation,
    )
    return DistanceVisit(
        slot,
        particle,
        team_id,
        proxy,
        tuple(indices),
        "solved",
        mass,
        result,
        ("next_position", "velocity_position"),
    )


def solve_distance_range(
    buffers: DistanceBuffers,
    teams: Mapping[int, DistancePassTeam],
    parameters: Mapping[int, DistancePassSettings],
    *,
    step_particle_indices: Sequence[int],
    team_ids: Sequence[int],
    attributes: Sequence[int],
    depths: Sequence[float],
    adjacency_words: Sequence[int],
    neighbor_local_indices: Sequence[int],
    signed_rest_lengths: Sequence[float],
    simulation_power_y: float,
    index_count: int,
) -> DistancePassResult:
    """Range368842's ascending work slots, privately publish each completed slot.

    Order is caller-supplied; no sort, deduplication, all-particle sweep or Jacobi
    substitution. Count<=0 reads no element and preserves buffers by identity.
    Positive count snapshots only outer next/velocity sequences. Vector tuples
    are the typed contract. Real worker-range partitioning remains unproven.
    """
    count = _int32(index_count)
    if count <= 0:
        return DistancePassResult(buffers, ())
    positions, velocities = (
        list(buffers.next_positions),
        list(buffers.velocity_positions),
    )
    working = replace(buffers, next_positions=positions, velocity_positions=velocities)
    visits = []
    for slot in range(count):
        visit = solve_distance_slot(
            working,
            teams,
            parameters,
            step_particle_indices=step_particle_indices,
            team_ids=team_ids,
            attributes=attributes,
            depths=depths,
            adjacency_words=adjacency_words,
            neighbor_local_indices=neighbor_local_indices,
            signed_rest_lengths=signed_rest_lengths,
            simulation_power_y=simulation_power_y,
            slot=slot,
        )
        visits.append(visit)
        if visit.result is not None:
            positions[visit.particle_index] = visit.result.next_position
            velocities[visit.particle_index] = visit.result.velocity_position
    return DistancePassResult(
        replace(
            working,
            next_positions=tuple(positions),
            velocity_positions=tuple(velocities),
        ),
        tuple(visits),
    )
