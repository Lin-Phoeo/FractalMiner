"""Resolved UpdateTeam routing and successful-buffer-transition prediction.

Official 368942/343d8b0, params369050/34dff30. Caller supplies the current
team, resolved outgoing ContainsTeamData result, all resolved incoming parents,
three old chunks and four GLOBAL counters. No implicit empty graph/zero state.
Modes alone cannot disable inbound-parent collision or clear stale buffers.

This is not Register, Team graph production, native allocation, InitPrimitive,
recursive/tail-loop execution, concurrency, collision mathematics or Unity
integration. Predicted counts apply only AFTER all planned buffer operations
succeed. Native allocation faults/partial publication are not emulated. Strict
finite/type/size checks are adapter policy, not native validation. Converted
curve samples are explicit; no Unity AnimationCurve sampling/DataValidate.
"""

from collections.abc import Sequence
from dataclasses import dataclass

from official_physics_constraints import _single
from official_physics_point_pass import _integer, _wrap32
from official_physics_substep_plan import SelfCollisionCounts

ROUTING_MASK = ((1 << 50) - 1) ^ ((1 << 32) - 1)
_INTERSECT_MASK = 0x3F00000000000


@dataclass(frozen=True)
class SelfCollisionParameters:
    self_mode: int
    surface_thickness_curve: Sequence[float]
    sync_mode: int
    cloth_mass: float


@dataclass(frozen=True)
class Topology:
    flags: int  # TeamData unboxed@0, UInt64; Exit=bit8.
    particle_count: int  # @376, particleChunk.dataLength.
    edge_count: int  # @320, proxyEdgeChunk.dataLength.
    triangle_count: int  # @312, proxyTriangleChunk.dataLength.


@dataclass(frozen=True)
class Peer:
    flags: int  # Incoming parents require Valid=bit0; target does not retest it.
    edge_count: int
    triangle_count: int
    sync_mode: int  # Parent params. Outgoing target's own mode is not read.


@dataclass(frozen=True)
class Chunk:
    start_index: int
    data_length: int  # IsValid only tests signed dataLength > 0.


@dataclass(frozen=True)
class ChunkEvent:
    kind: str
    operation: str  # allocate, retain, remove, none; not an executed operation.
    old_chunk: Chunk
    length: int  # allocate=requested length, otherwise unchanged old length.


@dataclass(frozen=True)
class SelfCollisionUpdate:
    flags: int
    chunk_events: tuple[ChunkEvent, ...]
    counts: SelfCollisionCounts  # Conditional post-success global snapshot.
    refresh_sync_target: bool  # Tail-loop request, not performed here.


def _uint64(value: int) -> int:
    if type(value) is not int or not 0 <= value <= 0xFFFFFFFFFFFFFFFF:
        raise ValueError("Adapter flags require UInt64")
    return value


def _int32(value: int) -> int:
    return _integer(value, -0x80000000)


def convert_self_collision_parameters(
    self_mode: int,
    surface_thickness_curve: Sequence[float],
    sync_mode: int,
    cloth_mass: float,
    cloth_type: int,
) -> SelfCollisionParameters:
    """BoneSpring=10 forces modes0; others copy enum values (unknown included).

    Thickness/mass always copy converted Single values. No clamp is inserted.
    """
    own, sync, kind = _int32(self_mode), _int32(sync_mode), _int32(cloth_type)
    if len(surface_thickness_curve) != 16:
        raise ValueError("Adapter requires sixteen converted curve samples")
    return SelfCollisionParameters(
        0 if kind == 10 else own,
        tuple(_single(value) for value in surface_thickness_curve),
        0 if kind == 10 else sync,
        _single(cloth_mass),
    )


def plan_self_collision_update(
    topology: Topology,
    parameters: SelfCollisionParameters,
    sync_target: Peer | None,
    sync_parents: Sequence[Peer],
    old_chunks: Sequence[Chunk],
    global_counts: Sequence[int],
) -> SelfCollisionUpdate:
    """One resolved normal UpdateTeam visit, including old/new count deltas.

    None target explicitly means ContainsTeamData(syncTeamId)==false. Incoming
    parents must already be resolved, including invalid entries; missing native
    lookup/fault behavior is outside this adapter. No automatic visited guard,
    target recursion, sync-link mutation or removal is fabricated.
    """
    original = _uint64(topology.flags)
    lengths = tuple(
        _int32(value)
        for value in (
            topology.particle_count,
            topology.edge_count,
            topology.triangle_count,
        )
    )
    own, sync = _int32(parameters.self_mode), _int32(parameters.sync_mode)
    if len(old_chunks) != 3 or len(global_counts) != 4:
        raise ValueError("Adapter requires three chunks and four explicit counters")
    counts = [_int32(value) for value in global_counts]
    for chunk in old_chunks:
        _int32(chunk.start_index)
        _int32(chunk.data_length)
    if sync_target is not None:
        _uint64(sync_target.flags)
        _int32(sync_target.edge_count)
        _int32(sync_target.triangle_count)
        _int32(sync_target.sync_mode)
    for parent in sync_parents:
        _uint64(parent.flags)
        _int32(parent.edge_count)
        _int32(parent.triangle_count)
        _int32(parent.sync_mode)

    exit_requested = bool(original & 0x100)
    if exit_requested:
        own = sync = 0
    flags = original & ~ROUTING_MASK
    edges, triangles = lengths[1] > 0, lengths[2] > 0

    def enable(index: int, condition: bool) -> None:
        nonlocal flags
        if condition:
            flags |= 1 << index

    if own == 2:
        enable(33, edges)
        enable(35, edges)
        for index in (32, 34, 38, 41):
            enable(index, triangles)
        for index in (44, 47):
            enable(index, edges and triangles)

    def pair(peer: Peer, column: int) -> None:
        peer_edges, peer_triangles = peer.edge_count > 0, peer.triangle_count > 0
        enable(33, edges and peer_edges)
        enable(34, triangles)
        enable(32, peer_triangles)
        enable(35 + column, edges and peer_edges)
        enable(38 + column, peer_triangles)
        enable(41 + column, triangles)
        enable(44 + column, edges and peer_triangles)
        enable(47 + column, triangles and peer_edges)

    if sync == 2 and sync_target is not None:
        pair(sync_target, 1)
    if not exit_requested:
        for parent in sync_parents:
            if parent.flags & 1 and parent.sync_mode == 2:
                pair(parent, 2)

    events = []
    for index, (kind, chunk, length) in enumerate(
        zip(("point", "edge", "triangle"), old_chunks, lengths, strict=True)
    ):
        demand = bool(flags & (1 << (32 + index)))
        valid = chunk.data_length > 0
        if demand and not valid:
            operation = "allocate"
            counts[index] = _wrap32(counts[index] + length)
        elif not demand and valid:
            operation = "remove"
            counts[index] = _wrap32(counts[index] - chunk.data_length)
        else:
            operation = "retain" if valid else "none"
        events.append(
            ChunkEvent(
                kind,
                operation,
                chunk,
                length if operation == "allocate" else chunk.data_length,
            )
        )
    counts[3] = _wrap32(
        counts[3]
        + int(bool(flags & _INTERSECT_MASK))
        - int(bool(original & _INTERSECT_MASK))
    )
    return SelfCollisionUpdate(
        flags,
        tuple(events),
        SelfCollisionCounts(*counts),
        sync != 0 and sync_target is not None,
    )
