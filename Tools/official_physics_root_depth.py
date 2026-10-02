"""Offline original root/length/depth Job arithmetic, not live Unity physics.

VirtualMesh+BaseLine_CalcMaxBaseLineLengthJob.Execute method371609/RVA0x313fed0.
Source-bound evidence: docs/implementation/official-physics-root-depth-20261002.
Move ancestry accumulates float3 Single distances CHILD-UP, stopping at the first
non-Move parent (after adding its edge), or at a negative parent. All vertices
participate; baseline data slots do not filter this Job. One global maximum
normalizes depths, NOT per-root maxima. Original allocation/Job publication,
actual character proxy generation and runtime/bone writes are not implemented.
Finite/range/full-forest cycle validation is adapter policy, not native guards.
"""

import math
from collections.abc import Sequence
from dataclasses import dataclass
from typing import cast

from official_physics_angle_baseline import _integer, is_movable
from official_physics_angles import _float3
from official_physics_baseline_build import _validate_forest
from official_physics_constraints import Vector3, _single


@dataclass(frozen=True)
class VertexRootDepth:
    roots: tuple[int, ...]
    lengths: tuple[float, ...]
    depths: tuple[float, ...]
    maximum_length: float


def _distance_single(child: Vector3, parent: Vector3) -> float:
    delta = cast(
        Vector3,
        tuple(_single(a - b) for a, b in zip(parent, child, strict=True)),
    )
    squared = _single(
        _single(_single(delta[1] * delta[1]) + _single(delta[0] * delta[0]))
        + _single(delta[2] * delta[2])
    )
    return _single(math.sqrt(squared))


def evaluate_vertex_root_depth(
    parents: Sequence[int],
    attributes: Sequence[int],
    positions: Sequence[Vector3],
    initial_depths: Sequence[float],
) -> VertexRootDepth:
    """All-vertex sequential Job reference, caller owns initial depth buffer.

    Root index starts -1 and becomes LAST visited parent, not vertex itself.
    Non-Move vertices never walk their parent. A Move root with negative parent
    also remains -1; a descendant can still identify it as last visited parent.
    Length/root outputs are rewritten for every vertex. Depth outputs are only
    rewritten if the global maximum is strictly greater than float32(1e-8).
    Do not replace child-up accumulation with parent-first memoization: Single
    rounding can differ. Shared allocator initialization and actual Job invocation
    identity remain separate evidence gates; no scheduler or native oracle here.
    """
    count = _integer(len(parents), 65536)
    if any(len(buffer) != count for buffer in (attributes, positions, initial_depths)):
        raise ValueError("Adapter requires parallel root/depth buffers")
    # Derive children ONLY for existing full-forest safety validation. This is
    # not a claim about NativeMultiHashMap enumeration or baseline output order.
    children: list[list[int]] = [[] for _ in parents]
    for vertex, parent in enumerate(parents):
        if type(parent) is not int or not -(2**31) <= parent < 2**31:
            raise ValueError("Adapter requires Int32 parents")
        if parent >= 0:
            if parent >= count:
                raise ValueError("Adapter parent index outside vertex buffer")
            children[parent].append(vertex)
    _validate_forest(parents, attributes, (), children)
    original_positions = tuple(_float3(value) for value in positions)
    depths = tuple(_single(value) for value in initial_depths)
    roots, lengths = [], []
    maximum = 0.0
    for vertex in range(count):
        current, root, total = vertex, -1, 0.0
        while is_movable(attributes[current]) and parents[current] >= 0:
            parent = parents[current]
            total = _single(
                total
                + _distance_single(
                    original_positions[current], original_positions[parent]
                )
            )
            root, current = parent, parent
        roots.append(root)
        lengths.append(total)
        maximum = max(maximum, total)
    if maximum > _single(1e-8):
        depths = tuple(
            _single(min(1, max(0, _single(length / maximum)))) for length in lengths
        )
    return VertexRootDepth(tuple(roots), tuple(lengths), depths, maximum)
