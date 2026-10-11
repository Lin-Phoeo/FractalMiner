"""Fresh ordinary Line connectivity and local DistanceConstraint inputs.

Source-bound finite reference, NOT a native allocator/Job or live Unity backend.
Only serial fresh no-resize maps and a CREATED EMPTY edge-to-triangle map are
supported. Validate adapter inputs rather than emulate native malformed memory.
Graph UniqueAdd drops repeats, whereas supplied Distance adjacency repeats are
retained. Source rows/UInt16 data/packed high12 count low20 start stay separate.
"""

import math
from collections.abc import Sequence
from dataclasses import dataclass

from official_physics_angle_baseline import _index, _integer
from official_physics_angles import _float3
from official_physics_constraints import Vector3, _single


def _pack(rows: Sequence[Sequence[int]]) -> tuple[tuple[int, ...], tuple[int, ...]]:
    words, data = [], []
    for row in rows:
        count, start = _integer(len(row), 4095), _integer(len(data), 0xFFFFF)
        words.append((count << 20) | start)
        data.extend(row)
    return tuple(words), tuple(data)


@dataclass(frozen=True)
class LineConnectivity:
    rows: tuple[tuple[int, ...], ...]
    words: tuple[int, ...]
    data: tuple[int, ...]


def build_line_connectivity(
    vertex_count: int,
    lines: Sequence[Sequence[int]],
    *,
    fresh_serial_no_resize: bool,
) -> LineConnectivity:
    """Ordinary FromLine Execute: two UniqueAdds per line, head-chain order.

    Native builder capacity4*n, initial bucket/next heads -1; at most capacity
    serial successful inserts implies no resize. Arbitrary dense lines beyond
    this bound are refused rather than inventing rehash order. EdgeSet order is
    irrelevant ONLY for this zero-triangle route, not a general proxy contract.
    """
    if fresh_serial_no_resize is not True:
        raise ValueError("Require explicit fresh serial no-resize graph")
    count = _integer(vertex_count, 65535)
    rows: list[list[int]] = [[] for _ in range(count)]
    inserts = 0
    for line in lines:
        if len(line) != 2:
            raise ValueError("Adapter requires two Line endpoints")
        a, b = (_index(v, count) for v in line)
        for key, value in ((a, b), (b, a)):
            if value not in rows[key]:
                rows[key].insert(0, value)
                inserts += 1
                if inserts > 4 * count:
                    raise ValueError("Graph exceeds certified fresh map capacity")
    ordered = tuple(tuple(row) for row in rows)
    words, data = _pack(ordered)
    return LineConnectivity(ordered, words, data)


@dataclass(frozen=True)
class DistanceInputs:
    # None is original default-null arrays, not an allocated zero-count row.
    words: tuple[int, ...] | None
    data: tuple[int, ...] | None
    signed_rest_lengths: tuple[float, ...] | None
    # Temporary entries accepted by attributes, BEFORE the 1e-6 length filter.
    pre_length_entry_count: int


def _rest_length(a: Vector3, b: Vector3) -> float:
    delta = tuple(_single(x - y) for x, y in zip(a, b, strict=True))
    square = tuple(_single(v * v) for v in delta)
    dot = _single(_single(square[1] + square[0]) + square[2])
    return _single(math.sqrt(dot))


def build_distance_inputs(
    positions: Sequence[Vector3],
    parents: Sequence[int],
    attributes: Sequence[int],
    graph_rows: Sequence[Sequence[int]],
    *,
    fresh_serial_no_resize: bool,
    zero_triangle_edge_map: bool,
) -> DistanceInputs:
    """CreateData finite zero-triangle route; no runtime topology claim.

    Explicit fresh map bounds are enforced before output publication. An edge
    requires at least one Move(bit2), and neither endpoint Invalid(mask3==0).
    Parent relationship is positive; other adjacency negative. Lengths use the
    Single float3 subtract/dot(y²+x² then z²)/sqrt helper. Strict <1e-6 omits the
    neighbor; not the consumer's Double length<1e-8f gate. Optional triangle
    phase sees an empty created map and every FixedList count0<2, so adds none.
    """
    if fresh_serial_no_resize is not True or zero_triangle_edge_map is not True:
        raise ValueError("Require explicit fresh maps and created-empty triangle map")
    count = _integer(len(positions), 65535)
    if any(len(values) != count for values in (parents, attributes, graph_rows)):
        raise ValueError("Require matching original vertex domains")
    points = tuple(_float3(p) for p in positions)
    checked_parents = []
    for parent in parents:
        if type(parent) is not int or parent < -1:
            raise ValueError("Adapter requires resolved parent or -1")
        checked_parents.append(_index(parent, count) if parent >= 0 else -1)
    attrs = tuple(_integer(a, 255) for a in attributes)
    rows = tuple(tuple(_index(v, count) for v in row) for row in graph_rows)
    # JobUtility allocates the converted map at dataLength, NOT 4*n. Exactly
    # one Add per supplied entry fills but never exceeds that fresh capacity.
    phases: list[list[list[int]]] = [[[] for _ in range(count)] for _ in range(2)]
    phase_counts = [0, 0]
    for center, row in enumerate(rows):
        # JobUtility packed-row conversion and temporary head insertion each
        # reverse once. The net order is the original published graph row.
        for neighbor in reversed(row):
            if not ((attrs[center] | attrs[neighbor]) & 2):
                continue
            if not (attrs[center] & 3) or not (attrs[neighbor] & 3):
                continue
            phase = (
                0
                if neighbor == checked_parents[center]
                or center == checked_parents[neighbor]
                else 1
            )
            phases[phase][center].insert(0, neighbor)
            phase_counts[phase] += 1
            if phase_counts[phase] > 2 * count:
                raise ValueError("Distance temporary map exceeds certified capacity")
    accepted = sum(phase_counts)
    if not accepted:
        return DistanceInputs(None, None, None, 0)
    output_rows, lengths = [], []
    for center in range(count):
        output = []
        for phase in range(2):
            for neighbor in phases[phase][center]:
                distance = _rest_length(points[center], points[neighbor])
                if distance < _single(1e-6):
                    continue
                output.append(neighbor)
                lengths.append(-distance if phase else distance)
        output_rows.append(tuple(output))
    words, data = _pack(output_rows)
    return DistanceInputs(words, data, tuple(lengths), accepted)
