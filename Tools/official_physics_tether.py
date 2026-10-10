"""Finite Tether value/slot/serial-range references over explicit produced inputs.

Managed369163/5a109f0, actual non-Burst fallback5a05d50, ordinary
Job369194/5a1108c and serial369164/5a061b8 are inspected separately.
Geometry is Double; limits are Single, .3/.7 constants are widened Single.
No center, depth, friction, power or Team flag is consumed by these bodies.

This does not generate proxy/Team/list buffers, dispatch native Jobs/Burst,
allocate native arrays or publish Unity bones. The serial range is not proof
of parallel Job order. Finite/representable/index error policy is the adapter's,
not the game's fault or nonfinite behavior. Python sqrt is not a CRT oracle.
"""

from collections.abc import Mapping, Sequence
from dataclasses import dataclass, replace

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
from official_physics_point_pass import _integer, _item, _wrap32

_ZERO: Vector3 = (0.0, 0.0, 0.0)
_EPSILON = _single(1e-8)
_SOFT_RANGE = _single(0.3)
_VELOCITY_RATIO = _single(0.7)


@dataclass(frozen=True)
class TetherSettings:
    compression_limit: float  # ClothParameters@236, Single.
    stretch_limit: float  # @240, Single.


@dataclass(frozen=True)
class TetherTeam:
    particle_start: int  # TeamData@372, Int32.
    proxy_start: int  # @292, Int32.


@dataclass(frozen=True)
class TetherBuffers:
    next_positions: Sequence[Vector3]
    velocity_positions: Sequence[Vector3]
    step_basic_positions: Sequence[Vector3]


@dataclass(frozen=True)
class TetherResult:
    next_position: Vector3
    velocity_position: Vector3
    correction: Vector3
    status: str
    writes: tuple[str, ...]


@dataclass(frozen=True)
class TetherVisit:
    slot: int
    particle_index: int
    team_id: int
    proxy_index: int
    root_particle_index: int | None
    status: str
    result: TetherResult | None
    writes: tuple[str, ...]


@dataclass(frozen=True)
class TetherPassResult:
    buffers: TetherBuffers
    visits: tuple[TetherVisit, ...]


def convert_tether_settings(
    distance_compression: float,
    cloth_type: int,
    *,
    previous_compression: float | None = None,
) -> TetherSettings:
    """369191/34e1a90: unknown types do not write the compression field.

    Mesh0/Bone1 copy serialized Single; Spring10 writes .8f. All routes write
    .03f stretch. Unknown types require explicit prior storage in this adapter;
    no fabricated zero/default is supplied. This does not call DataValidate.
    """
    cloth_type = _integer(cloth_type, -0x80000000)
    if cloth_type in (0, 1):
        compression = _single(distance_compression)
    elif cloth_type == 10:
        compression = _single(0.8)
    else:
        if previous_compression is None:
            raise ValueError(
                "Adapter requires previous compression for unknown cloth type"
            )
        compression = _single(previous_compression)
    return TetherSettings(compression, _single(0.03))


def _clamp01(value: float) -> float:
    """59d788c finite Double path: strict upper comparison, then lower."""
    value = _finite(value)
    if value > 1:
        value = 1.0
    if value < 0:
        value = 0.0
    return value


def _tether_projection(
    next_position: Vector3,
    root_position: Vector3,
    step_basic_position: Vector3,
    root_step_basic_position: Vector3,
    settings: TetherSettings,
) -> tuple[Vector3, Vector3, str]:
    """Already-selected Move vertex with a nonnegative, resolved root.

    Rest length is current step-basic separation, not bind length or total
    root-chain distance. Each direction lane divides by Double length before
    multiplication; only Single limit construction is narrowed. Velocity is
    read/written only on a violated bound. No extra power/mass/flag gate exists.
    """

    def unchanged(status: str) -> tuple[Vector3, Vector3, str]:
        return next_position, _ZERO, status

    delta = _sub(_vector(root_position), _vector(next_position))
    length = _length(delta)
    if length < _EPSILON:
        return unchanged("short-current-edge")
    rest = _length(
        _sub(_vector(root_step_basic_position), _vector(step_basic_position))
    )
    if rest == 0:
        return unchanged("zero-reference-edge")
    lower = _single(1 - _single(settings.compression_limit))
    upper = _single(_single(settings.stretch_limit) + 1)
    ratio = _finite(length / rest)
    if lower > ratio:
        boundary, excess, status = lower, lower - ratio, "compression"
    elif ratio > upper:
        boundary, excess, status = upper, ratio - upper, "stretch"
    else:
        return unchanged("within-limits")
    # Native Double clamp preserves equality; finite excess is nonnegative.
    gain = _clamp01(_finite(excess / _SOFT_RANGE))
    gap = _finite(length - boundary * rest)
    direction = _vector((delta[0] / length, delta[1] / length, delta[2] / length))
    correction = _scale(direction, _finite(gain * gap))
    return _add(_vector(next_position), correction), correction, status


def tether_particle(
    next_position: Vector3,
    velocity_position: Vector3,
    root_position: Vector3,
    step_basic_position: Vector3,
    root_step_basic_position: Vector3,
    settings: TetherSettings,
) -> TetherResult:
    """Finite selected Move vertex; velocity is consumed only on correction."""
    position, correction, status = _tether_projection(
        next_position,
        root_position,
        step_basic_position,
        root_step_basic_position,
        settings,
    )
    writes: tuple[str, ...] = ()
    velocity = velocity_position
    if status in ("compression", "stretch"):
        velocity = _add(_vector(velocity_position), _scale(correction, _VELOCITY_RATIO))
        writes = ("next_position", "velocity_position")
    return TetherResult(position, velocity, correction, status, writes)


def solve_tether_slot(
    buffers: TetherBuffers,
    teams: Mapping[int, TetherTeam],
    parameters: Mapping[int, TetherSettings],
    *,
    step_particle_indices: Sequence[int],
    team_ids: Sequence[int],
    attributes: Sequence[int],
    root_local_indices: Sequence[int],
    slot: int,
) -> TetherVisit:
    """List ordinal → particle → signed Int16 Team → proxy → local Int32 root.

    Move bit2 alone is the eligibility gate, including attributes3/18. No
    valid/NoCollision/Spring/team0/IsProcess filter is added. All negative roots
    skip. Both offset expressions wrap Int32 before widening. Typed maps are
    explicit adapter storage, not native layout or negative native-array safety.
    """
    slot = _integer(slot)
    particle = _integer(_item(step_particle_indices, slot))
    team_id = _integer(_item(team_ids, particle), -32768, 32767)
    if team_id not in teams or team_id not in parameters:
        raise ValueError("Adapter requires selected TeamData and Tether parameters")
    team, settings = teams[team_id], parameters[team_id]
    start, proxy_start = _integer(team.particle_start), _integer(team.proxy_start)
    proxy = _integer(_wrap32(proxy_start - start + particle))
    attribute = _integer(_item(attributes, proxy), 0, 255)
    if not attribute & 2:
        return TetherVisit(slot, particle, team_id, proxy, None, "non-move", None, ())
    root = _integer(_item(root_local_indices, proxy), -0x80000000)
    if root < 0:
        return TetherVisit(slot, particle, team_id, proxy, None, "no-root", None, ())
    root_particle = _integer(_wrap32(start + root))
    position = _item(buffers.next_positions, particle)
    root_position = _item(buffers.next_positions, root_particle)
    # Do not resolve later buffers when the source current-length gate returns.
    if _length(_sub(_vector(root_position), _vector(position))) < _EPSILON:
        return TetherVisit(
            slot,
            particle,
            team_id,
            proxy,
            root_particle,
            "short-current-edge",
            None,
            (),
        )
    basic = _item(buffers.step_basic_positions, particle)
    root_basic = _item(buffers.step_basic_positions, root_particle)
    # Geometry and actual velocity access are separate; no placeholder input.
    projected, correction, status = _tether_projection(
        position, root_position, basic, root_basic, settings
    )
    if status not in ("compression", "stretch"):
        return TetherVisit(
            slot, particle, team_id, proxy, root_particle, status, None, ()
        )
    velocity = _add(
        _vector(_item(buffers.velocity_positions, particle)),
        _scale(correction, _VELOCITY_RATIO),
    )
    result = TetherResult(
        projected, velocity, correction, status, ("next_position", "velocity_position")
    )
    return TetherVisit(
        slot,
        particle,
        team_id,
        proxy,
        root_particle,
        result.status,
        result,
        result.writes,
    )


def solve_tether_range(
    buffers: TetherBuffers,
    teams: Mapping[int, TetherTeam],
    parameters: Mapping[int, TetherSettings],
    *,
    step_particle_indices: Sequence[int],
    team_ids: Sequence[int],
    attributes: Sequence[int],
    root_local_indices: Sequence[int],
    index_count: int,
) -> TetherPassResult:
    """Managed range's signed count read once; ascending slots publish privately.

    Duplicate slots and previously modified roots see prior completed writes.
    This is not proof of the scheduler's work partition/parallel execution order.
    Only next/velocity outer sequences are copied; other input identities stay.
    """
    count = _integer(index_count, -0x80000000)
    if count <= 0:
        return TetherPassResult(buffers, ())
    positions, velocities = (
        list(buffers.next_positions),
        list(buffers.velocity_positions),
    )
    working = replace(buffers, next_positions=positions, velocity_positions=velocities)
    visits = []
    for slot in range(count):
        visit = solve_tether_slot(
            working,
            teams,
            parameters,
            step_particle_indices=step_particle_indices,
            team_ids=team_ids,
            attributes=attributes,
            root_local_indices=root_local_indices,
            slot=slot,
        )
        visits.append(visit)
        if visit.result is not None:
            positions[visit.particle_index] = visit.result.next_position
            velocities[visit.particle_index] = visit.result.velocity_position
    return TetherPassResult(
        replace(
            working,
            next_positions=tuple(positions),
            velocity_positions=tuple(velocities),
        ),
        tuple(visits),
    )
