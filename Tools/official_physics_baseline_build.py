"""Offline transform-baseline CONTROL FLOW, not the mesh builder/live solver.

CreateTransformBaseLine method371533/RVA0x37e9610, source-hash-bound evidence:
docs/implementation/official-physics-baseline-build-20261002/README.md.
Caller supplies already-mapped local roots in original rootIdList order and the
ORIGINAL child-map enumeration per vertex. This module DOES NOT infer hash-table
order from bones, parent indices or insertion order. Nor does it choose the live
mesh/transform path, construct local pose, allocate Team buffers or schedule Jobs.

Full-forest validation and UInt16 overflow rejection are adapter safeguards, not
claims about original native exceptions. Valid input order/duplicates in roots
are preserved; there is no global dedup or sorting during baseline generation.
"""

from collections.abc import Sequence
from dataclasses import dataclass

from official_physics_angle_baseline import _index, _integer, is_movable


@dataclass(frozen=True)
class BuiltBaselines:
    flags: tuple[int, ...]
    starts: tuple[int, ...]
    counts: tuple[int, ...]
    data: tuple[int, ...]


def _validate_forest(
    parents: Sequence[int],
    attributes: Sequence[int],
    roots: Sequence[int],
    children: Sequence[Sequence[int]],
) -> None:
    """Reject malformed input; never re-order the caller's native child map."""
    count = len(parents)
    _integer(count, 65536)
    if len(attributes) != count or len(children) != count:
        raise ValueError("Adapter requires equally sized vertex buffers")
    for parent, attribute in zip(parents, attributes, strict=True):
        if type(parent) is not int or not -(2**31) <= parent < 2**31:
            raise ValueError("Adapter requires Int32 parents")
        if parent >= 0:
            _index(parent, count)
        _integer(attribute, 255)
    for root in roots:
        _index(root, count)
    seen_children: set[int] = set()
    for parent, ordered in enumerate(children):
        for child in ordered:
            _index(child, count)
            if child in seen_children or parents[child] != parent:
                raise ValueError("Adapter child map has duplicates or wrong parent")
            seen_children.add(child)
    if len(seen_children) != sum(parent >= 0 for parent in parents):
        raise ValueError("Adapter child map omits a parented vertex")
    # Iterative parent walk: validation only, NOT traversal/dedup of output roots.
    colors = [0] * count
    for vertex in range(count):
        current, path = vertex, []
        while current >= 0 and colors[current] == 0:
            colors[current] = 1
            path.append(current)
            current = parents[current]
        if current >= 0 and colors[current] == 1:
            raise ValueError("Adapter refuses a parent cycle")
        for item in path:
            colors[item] = 2


def build_transform_baselines(
    parents: Sequence[int],
    attributes: Sequence[int],
    ordered_local_roots: Sequence[int],
    ordered_children: Sequence[Sequence[int]],
) -> BuiltBaselines:
    """Two native LIFO traversals; only baseline root may be non-Move.

    Non-Move candidate with immediate Move child starts ONE baseline. Otherwise
    search only its non-Move children, pushed in supplied enumeration order.
    Once started, traverse only Move children, including the non-Move root itself;
    do NOT additionally search non-Move siblings/descendants for further groups.
    IncludeLine flag1 iff ANY included vertex lacks attribute mask128.
    Native truncates start/count/vertex to UInt16; this finite adapter refuses
    nonrepresentable start/count/vertex instead of silently wrapping buffers.
    """
    _validate_forest(parents, attributes, ordered_local_roots, ordered_children)
    flags, starts, counts, data = [], [], [], []
    for root in ordered_local_roots:
        candidates = [root]
        while candidates:
            candidate = candidates.pop()
            if is_movable(attributes[candidate]):
                continue
            children = ordered_children[candidate]
            if not any(is_movable(attributes[child]) for child in children):
                candidates.extend(
                    child for child in children if not is_movable(attributes[child])
                )
                continue
            start, size, flag = len(data), 0, 0
            if start > 65535:
                raise ValueError("Adapter refuses UInt16 baseline start wrap")
            pending = [candidate]
            while pending:
                vertex = pending.pop()
                data.append(vertex)
                size += 1
                if size > 65535:
                    raise ValueError("Adapter refuses UInt16 baseline count wrap")
                if not attributes[vertex] & 128:
                    flag |= 1
                pending.extend(
                    child
                    for child in ordered_children[vertex]
                    if is_movable(attributes[child])
                )
            starts.append(start)
            counts.append(size)
            flags.append(flag)
    return BuiltBaselines(tuple(flags), tuple(starts), tuple(counts), tuple(data))
