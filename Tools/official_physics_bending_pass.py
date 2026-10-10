"""Finite current-version TriangleBending work and aggregate references.

The recovered game path is two-stage: a pair work list writes four exclusive
float3 correction slots, then a particle work list sums those slots in Single,
averages, widens to Double and updates nextPos.  This module models those
explicit buffers and their observed ascending managed ranges.  It does not
produce topology/work lists, reproduce worker partitioning/Burst dispatch, or
publish Unity transforms.  Bounds and finite checks are adapter policy.
"""

from collections.abc import Mapping, Sequence
from dataclasses import dataclass

from official_physics_angle_baseline import _integer
from official_physics_bending import (
    METHOD_DIHEDRAL,
    METHOD_DIRECTIONAL_DIHEDRAL,
    METHOD_NONE,
    VOLUME_SIGN,
    BendingCorrection,
    BendingParameters,
    solve_dihedral,
    solve_volume,
    unpack_triangle_pair,
    unpack_write_offsets,
)
from official_physics_constraints import Vector3, _single, _vector, inverse_mass
from official_physics_proxy_baseline import _int32

_RUNTIME_STIFFNESS_EPSILON = _single(1e-6)


def _item(values: Sequence, index: int, label: str):
    index = _integer(index, 0x7FFFFFFF)
    if index >= len(values):
        raise ValueError(f"Adapter {label} index exceeds supplied buffer")
    return values[index]


def _u32_pattern(value: int, label: str) -> int:
    if type(value) is not int or not -(2**31) <= value < 2**32:
        raise ValueError(f"Adapter {label} must preserve an Int32/UInt32 bit pattern")
    return value & 0xFFFFFFFF


def _signed16(value: int) -> int:
    if type(value) is not int or not -32768 <= value <= 32767:
        raise ValueError("Adapter team ID must be a signed Int16")
    return value


def pack_step_triangle_index(team_id: int, pair_index: int) -> int:
    team = _integer(team_id, 0xFFF)
    pair = _integer(pair_index, 0xFFFFF)
    return team << 20 | pair


def unpack_step_triangle_index(word: int) -> tuple[int, int]:
    word = _u32_pattern(word, "step triangle word")
    return word >> 20, word & 0xFFFFF


def pack_write_index(count: int, start: int) -> int:
    return _integer(count, 0xFFF) << 20 | _integer(start, 0xFFFFF)


def unpack_write_index(word: int) -> tuple[int, int]:
    word = _u32_pattern(word, "write index word")
    return word >> 20, word & 0xFFFFF


@dataclass(frozen=True)
class BendingTeam:
    particle_start: int  # TeamData@372 DataChunk.startIndex.
    proxy_start: int  # @292.
    bending_pair_count: int  # @416 DataChunk.dataLength; aggregate source gate.
    bending_write_index_start: int  # @424 startIndex.
    bending_buffer_start: int  # @432 startIndex.
    scale_ratio: float  # @96, Single.
    negative_scale_sign: float  # @100, Single.


@dataclass(frozen=True)
class BendingWorkVisit:
    slot: int
    team_id: int
    pair_index: int
    vertices: tuple[int, ...]
    particle_indices: tuple[int, ...]
    proxy_indices: tuple[int, ...]
    inverse_masses: tuple[float, ...]
    status: str
    adjusted_rest: float | None
    result: BendingCorrection | None
    write_indices: tuple[int, ...]
    write_values: tuple[Vector3, ...]


@dataclass(frozen=True)
class BendingWorkResult:
    write_buffer: Sequence[Vector3]
    visits: tuple[BendingWorkVisit, ...]


@dataclass(frozen=True)
class BendingAggregateVisit:
    slot: int
    particle_index: int
    team_id: int
    proxy_index: int | None
    status: str
    write_indices: tuple[int, ...]
    correction: Vector3 | None


@dataclass(frozen=True)
class BendingAggregateResult:
    next_positions: Sequence[Vector3]
    visits: tuple[BendingAggregateVisit, ...]


@dataclass(frozen=True)
class BendingPassResult:
    next_positions: Sequence[Vector3]
    write_buffer: Sequence[Vector3]
    work_visits: tuple[BendingWorkVisit, ...]
    aggregate_visits: tuple[BendingAggregateVisit, ...]


def _team(team: BendingTeam) -> BendingTeam:
    for value in (
        team.particle_start,
        team.proxy_start,
        team.bending_pair_count,
        team.bending_write_index_start,
        team.bending_buffer_start,
    ):
        _integer(value, 0x7FFFFFFF)
    _single(team.scale_ratio)
    _single(team.negative_scale_sign)
    return team


def _float3(value: Vector3) -> Vector3:
    value = _vector(value)
    return (_single(value[0]), _single(value[1]), _single(value[2]))


def solve_bending_work_slot(
    teams: Mapping[int, BendingTeam],
    parameters: Mapping[int, BendingParameters],
    *,
    next_positions: Sequence[Vector3],
    step_triangle_indices: Sequence[int],
    attributes: Sequence[int],
    depths: Sequence[float],
    frictions: Sequence[float],
    triangle_pairs: Sequence[int],
    rest_angle_or_volume: Sequence[float],
    sign_or_volume: Sequence[int],
    write_data: Sequence[int],
    write_indices: Sequence[int],
    simulation_power_y: float,
    slot: int,
) -> BendingWorkVisit:
    """Resolve one packed global pair and return its optional four private writes."""
    slot = _integer(slot, 0x7FFFFFFF)
    team_id, pair_index = unpack_step_triangle_index(
        _item(step_triangle_indices, slot, "step triangle")
    )
    if team_id not in teams:
        raise ValueError("Adapter requires selected TeamData")
    if team_id not in parameters:
        raise ValueError("Adapter requires selected TriangleBending parameters")
    team, settings = _team(teams[team_id]), parameters[team_id]
    if type(settings.method) is not int:
        raise ValueError("Adapter bending method must be an integer enum")
    stiffness = _single(settings.stiffness)

    def skipped(status: str) -> BendingWorkVisit:
        return BendingWorkVisit(
            slot, team_id, pair_index, (), (), (), (), status, None, None, (), ()
        )

    if settings.method == METHOD_NONE:
        return skipped("disabled")
    if stiffness < _RUNTIME_STIFFNESS_EPSILON:
        return skipped("below-stiffness-threshold")
    power = _single(simulation_power_y)
    effective_stiffness = _single(stiffness * power)
    effective_stiffness = min(1.0, max(0.0, effective_stiffness))

    vertices = unpack_triangle_pair(_item(triangle_pairs, pair_index, "triangle pair"))
    particle_indices = tuple(
        _integer(team.particle_start + vertex, 0x7FFFFFFF) for vertex in vertices
    )
    proxy_indices = tuple(
        _integer(team.proxy_start + vertex, 0x7FFFFFFF) for vertex in vertices
    )
    positions = tuple(
        _vector(_item(next_positions, index, "next position"))
        for index in particle_indices
    )
    masses = []
    for particle, proxy in zip(particle_indices, proxy_indices):
        friction = _single(_item(frictions, particle, "friction"))
        depth = _single(_item(depths, proxy, "depth"))
        attribute = _integer(_item(attributes, proxy, "attribute"), 255)
        masses.append(
            inverse_mass(
                friction,
                depth,
                fixed=not bool(attribute & 2),
                fixed_mass=100,
            )
        )
    inverse_masses = tuple(masses)
    rest = _single(_item(rest_angle_or_volume, pair_index, "rest data"))
    sign_value = _item(sign_or_volume, pair_index, "sign/volume")
    if type(sign_value) is not int or not -128 <= sign_value <= 127:
        raise ValueError("Adapter sign/volume value must be an SByte")

    adjusted_rest: float
    if sign_value == VOLUME_SIGN:
        adjusted_rest = _single(rest * _single(team.scale_ratio))
        adjusted_rest = _single(adjusted_rest * _single(team.negative_scale_sign))
        solved = solve_volume(
            positions, inverse_masses, adjusted_rest, effective_stiffness
        )
        solved_status, degenerate_status = "solved-volume", "degenerate-volume"
    elif settings.method == METHOD_DIHEDRAL:
        adjusted_rest = rest
        solved = solve_dihedral(
            0.0, positions, inverse_masses, adjusted_rest, effective_stiffness
        )
        solved_status, degenerate_status = (
            "solved-dihedral",
            "degenerate-dihedral",
        )
    elif settings.method == METHOD_DIRECTIONAL_DIHEDRAL:
        direction = -1.0 if sign_value < 0 else 1.0
        adjusted_rest = _single(rest * _single(direction))
        adjusted_rest = _single(adjusted_rest * _single(team.negative_scale_sign))
        solved = solve_dihedral(
            direction, positions, inverse_masses, adjusted_rest, effective_stiffness
        )
        solved_status, degenerate_status = (
            "solved-directional-dihedral",
            "degenerate-directional-dihedral",
        )
    else:
        return BendingWorkVisit(
            slot,
            team_id,
            pair_index,
            vertices,
            particle_indices,
            proxy_indices,
            inverse_masses,
            "unsupported-method",
            rest,
            None,
            (),
            (),
        )
    if solved is None:
        return BendingWorkVisit(
            slot,
            team_id,
            pair_index,
            vertices,
            particle_indices,
            proxy_indices,
            inverse_masses,
            degenerate_status,
            adjusted_rest,
            None,
            (),
            (),
        )

    offsets = unpack_write_offsets(_item(write_data, pair_index, "write data"))
    destinations = []
    values = []
    for vertex, offset, correction in zip(vertices, offsets, solved.corrections):
        index_word = _item(
            write_indices,
            team.bending_write_index_start + vertex,
            "write index",
        )
        _, base = unpack_write_index(index_word)
        destinations.append(
            _integer(team.bending_buffer_start + base + offset, 0x7FFFFFFF)
        )
        values.append(_float3(correction))
    return BendingWorkVisit(
        slot,
        team_id,
        pair_index,
        vertices,
        particle_indices,
        proxy_indices,
        inverse_masses,
        solved_status,
        adjusted_rest,
        solved,
        tuple(destinations),
        tuple(values),
    )


def solve_bending_work_range(
    teams: Mapping[int, BendingTeam],
    parameters: Mapping[int, BendingParameters],
    *,
    next_positions: Sequence[Vector3],
    write_buffer: Sequence[Vector3],
    step_triangle_indices: Sequence[int],
    attributes: Sequence[int],
    depths: Sequence[float],
    frictions: Sequence[float],
    triangle_pairs: Sequence[int],
    rest_angle_or_volume: Sequence[float],
    sign_or_volume: Sequence[int],
    write_data: Sequence[int],
    write_indices: Sequence[int],
    simulation_power_y: float,
    index_count: int,
) -> BendingWorkResult:
    count = _int32(index_count)
    if count <= 0:
        return BendingWorkResult(write_buffer, ())
    output = None
    visits = []
    for slot in range(count):
        visit = solve_bending_work_slot(
            teams,
            parameters,
            next_positions=next_positions,
            step_triangle_indices=step_triangle_indices,
            attributes=attributes,
            depths=depths,
            frictions=frictions,
            triangle_pairs=triangle_pairs,
            rest_angle_or_volume=rest_angle_or_volume,
            sign_or_volume=sign_or_volume,
            write_data=write_data,
            write_indices=write_indices,
            simulation_power_y=simulation_power_y,
            slot=slot,
        )
        visits.append(visit)
        if visit.write_indices:
            if output is None:
                output = list(write_buffer)
            for index, value in zip(visit.write_indices, visit.write_values):
                if index >= len(output):
                    raise ValueError(
                        "Adapter write buffer index exceeds supplied buffer"
                    )
                output[index] = value
    return BendingWorkResult(
        write_buffer if output is None else tuple(output), tuple(visits)
    )


def solve_bending_aggregate_slot(
    next_positions: Sequence[Vector3],
    teams: Mapping[int, BendingTeam],
    *,
    step_particle_indices: Sequence[int],
    team_ids: Sequence[int],
    attributes: Sequence[int],
    write_indices: Sequence[int],
    write_buffer: Sequence[Vector3],
    slot: int,
) -> BendingAggregateVisit:
    slot = _integer(slot, 0x7FFFFFFF)
    particle = _integer(_item(step_particle_indices, slot, "step particle"), 0x7FFFFFFF)
    team_id = _signed16(_item(team_ids, particle, "team ID"))
    if team_id < 0:
        raise ValueError("Adapter requires a nonnegative Team index")
    if team_id not in teams:
        raise ValueError("Adapter requires aggregate TeamData")
    team = _team(teams[team_id])

    def skipped(status: str, proxy: int | None = None) -> BendingAggregateVisit:
        return BendingAggregateVisit(slot, particle, team_id, proxy, status, (), None)

    if team.bending_pair_count <= 0:
        return skipped("empty-team-bending")
    local = particle - team.particle_start
    if local < 0:
        raise ValueError("Adapter particle precedes selected Team particle chunk")
    proxy = _integer(team.proxy_start + local, 0x7FFFFFFF)
    attribute = _integer(_item(attributes, proxy, "attribute"), 255)
    if not attribute & 2:
        return skipped("fixed-vertex", proxy)
    count, start = unpack_write_index(
        _item(
            write_indices,
            team.bending_write_index_start + local,
            "write index",
        )
    )
    if count == 0:
        return skipped("no-writes", proxy)

    total = (0.0, 0.0, 0.0)
    consumed = []
    for offset in range(count):
        index = _integer(team.bending_buffer_start + start + offset, 0x7FFFFFFF)
        value = _float3(_item(write_buffer, index, "write buffer"))
        total = (
            _single(total[0] + value[0]),
            _single(total[1] + value[1]),
            _single(total[2] + value[2]),
        )
        consumed.append(index)
    divisor = _single(count)
    correction = (
        _single(total[0] / divisor),
        _single(total[1] / divisor),
        _single(total[2] / divisor),
    )
    # The caller widens this float3 before the recovered double3 addition.
    _vector(_item(next_positions, particle, "next position"))
    return BendingAggregateVisit(
        slot,
        particle,
        team_id,
        proxy,
        "aggregated",
        tuple(consumed),
        correction,
    )


def solve_bending_aggregate_range(
    next_positions: Sequence[Vector3],
    teams: Mapping[int, BendingTeam],
    *,
    step_particle_indices: Sequence[int],
    team_ids: Sequence[int],
    attributes: Sequence[int],
    write_indices: Sequence[int],
    write_buffer: Sequence[Vector3],
    index_count: int,
) -> BendingAggregateResult:
    count = _int32(index_count)
    if count <= 0:
        return BendingAggregateResult(next_positions, ())
    output = None
    visits = []
    for slot in range(count):
        visit = solve_bending_aggregate_slot(
            next_positions if output is None else output,
            teams,
            step_particle_indices=step_particle_indices,
            team_ids=team_ids,
            attributes=attributes,
            write_indices=write_indices,
            write_buffer=write_buffer,
            slot=slot,
        )
        visits.append(visit)
        if visit.correction is not None:
            if output is None:
                output = list(next_positions)
            position = _vector(_item(output, visit.particle_index, "next position"))
            output[visit.particle_index] = (
                position[0] + visit.correction[0],
                position[1] + visit.correction[1],
                position[2] + visit.correction[2],
            )
    return BendingAggregateResult(
        next_positions if output is None else tuple(output), tuple(visits)
    )


def solve_bending_pass(
    next_positions: Sequence[Vector3],
    write_buffer: Sequence[Vector3],
    teams: Mapping[int, BendingTeam],
    parameters: Mapping[int, BendingParameters],
    *,
    step_triangle_indices: Sequence[int],
    step_particle_indices: Sequence[int],
    team_ids: Sequence[int],
    attributes: Sequence[int],
    depths: Sequence[float],
    frictions: Sequence[float],
    triangle_pairs: Sequence[int],
    rest_angle_or_volume: Sequence[float],
    sign_or_volume: Sequence[int],
    write_data: Sequence[int],
    write_indices: Sequence[int],
    simulation_power_y: float,
    work_index_count: int,
    particle_index_count: int,
) -> BendingPassResult:
    work = solve_bending_work_range(
        teams,
        parameters,
        next_positions=next_positions,
        write_buffer=write_buffer,
        step_triangle_indices=step_triangle_indices,
        attributes=attributes,
        depths=depths,
        frictions=frictions,
        triangle_pairs=triangle_pairs,
        rest_angle_or_volume=rest_angle_or_volume,
        sign_or_volume=sign_or_volume,
        write_data=write_data,
        write_indices=write_indices,
        simulation_power_y=simulation_power_y,
        index_count=work_index_count,
    )
    aggregate = solve_bending_aggregate_range(
        next_positions,
        teams,
        step_particle_indices=step_particle_indices,
        team_ids=team_ids,
        attributes=attributes,
        write_indices=write_indices,
        write_buffer=work.write_buffer,
        index_count=particle_index_count,
    )
    return BendingPassResult(
        aggregate.next_positions,
        work.write_buffer,
        work.visits,
        aggregate.visits,
    )
