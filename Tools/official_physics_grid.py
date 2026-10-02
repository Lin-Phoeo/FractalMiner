"""Finite scalar fresh/sequential/no-resize selection-grid reference.

Source flow: CalcAABBInternal 0x40c6080; ConvertFrom 0x5a1f270;
GridMap AddGrid/GetArea helpers 0x407d1c0/0x407d2e0; GridEnumerator
MoveNext 0x4032d00; hash head insertion 0x3cd04f0 and key-filtered next
0x31a2070. Cell enumeration is x-fastest, then y, then z. SAME-CELL values
are reverse serial insertion order, NOT sorted source indices.

Domain excludes removal, reuse, resizing and concurrent insertion. This is not
the native allocator, full ConvertFrom mutation/empty-input semantics, saved
selection branch selection, world snapshots, proxy application or Unity backend.
Caller positions must already be in the ORIGINAL shared matching space.
Finite/Int32/capacity/iteration rejection below is adapter-only safety policy.
"""

import math
from collections.abc import Sequence
from dataclasses import dataclass
from typing import cast

from official_physics_angle_baseline import _integer
from official_physics_angles import _float3
from official_physics_constraints import Vector3, _single
from official_physics_selection import convert_selection_attributes

Cell = tuple[int, int, int]


@dataclass(frozen=True)
class SelectionSearchParameters:
    minimum: Vector3
    maximum: Vector3
    max_side_length: float
    radius: float
    grid_size: float


def selection_search_parameters(
    target_positions: Sequence[Vector3],
) -> SelectionSearchParameters:
    """Nonempty target AABB: Single extrema -> double extents -> Single maximum."""
    count = _integer(len(target_positions), 65535)
    if not count:
        raise ValueError("Adapter excludes the empty ConvertFrom no-op domain")
    bound = _single(3.4028234663852886e38)
    minimum, maximum = (bound,) * 3, (-bound,) * 3
    for point in target_positions:
        position = _float3(point)
        # Original comparisons choose the candidate on equality, including -0.
        minimum = tuple(min(p, m) for p, m in zip(position, minimum))
        maximum = tuple(max(p, m) for p, m in zip(position, maximum))
    # The AABB stores double3, subtracts double extents, THEN converts to Single.
    side = _single(max(hi - lo for lo, hi in zip(minimum, maximum)))
    radius = max(_single(side * _single(0.2)), _single(1e-5))
    return SelectionSearchParameters(
        cast(Vector3, minimum),
        cast(Vector3, maximum),
        side,
        radius,
        _single(radius * _single(0.5)),
    )


def _grid_size(value: float) -> float:
    size = _single(value)
    if size <= 0:
        raise ValueError("Adapter requires a positive Single grid size")
    return size


def grid_cell(position: Vector3, grid_size: float) -> Cell:
    """divss, math.floor(float3), then signed Int32 conversion (not truncation)."""
    size = _grid_size(grid_size)
    cell = tuple(math.floor(_single(p / size)) for p in _float3(position))
    # Reserve +1 for native MoveNext increment; refuse Int32 overflow/wrap.
    if any(not -(2**31) <= c < 2**31 - 1 for c in cell):
        raise ValueError("Adapter refuses nonrepresentable or increment-unsafe cell")
    return cast(Cell, cell)


def grid_area_cells(
    position: Vector3, radius: float, grid_size: float
) -> tuple[Cell, ...]:
    """Inclusive native cell bounds, x increment first. Not a sphere-only scan."""
    size, search_radius = _grid_size(grid_size), _single(radius)
    if search_radius < 0:
        raise ValueError("Adapter requires nonnegative Single radius")
    point = _float3(position)
    lower = grid_cell(
        cast(Vector3, tuple(_single(p - search_radius) for p in point)), size
    )
    upper = grid_cell(
        cast(Vector3, tuple(_single(search_radius + p) for p in point)), size
    )
    counts = tuple(hi - lo + 1 for lo, hi in zip(lower, upper))
    if math.prod(counts) > 4096:
        raise ValueError("Adapter cell budget exceeded (not a native limit)")
    return tuple(
        (x, y, z)
        for z in range(lower[2], upper[2] + 1)
        for y in range(lower[1], upper[1] + 1)
        for x in range(lower[0], upper[0] + 1)
    )


def build_fresh_selection_grid(
    source_positions: Sequence[Vector3], grid_size: float
) -> dict[Cell, tuple[int, ...]]:
    """Fresh, serial, no-resize map only; all flags included as in ConvertFrom.

    Hash collisions do not change relative order of entries with equal int3 key:
    native insertion prepends and native next filters all three key components.
    This does NOT emulate allocator/free-list or claim equivalence after rehash.
    """
    _integer(len(source_positions), 65535)
    size = _grid_size(grid_size)
    cells: dict[Cell, list[int]] = {}
    for index, position in enumerate(source_positions):
        cells.setdefault(grid_cell(position, size), []).append(index)
    return {cell: tuple(reversed(indices)) for cell, indices in cells.items()}


def convert_fresh_selection_grid(
    target_positions: Sequence[Vector3],
    source_positions: Sequence[Vector3],
    source_attributes: Sequence[int],
) -> tuple[int, ...]:
    """Compose nonempty scalar radius/grid/candidates/matcher without guesses.

    Not full SelectionData.ConvertFrom: native zero-source/zero-target exits
    preserve prior state, whereas this stateless adapter refuses that domain.
    Positions must already share original matching coordinates; no bone/name
    matching, attribute priority, gain tuning or source-point filtering is added.
    """
    parameters = selection_search_parameters(target_positions)
    if not len(source_positions):
        raise ValueError("Adapter excludes the empty ConvertFrom no-op domain")
    grid = build_fresh_selection_grid(source_positions, parameters.grid_size)
    candidates = tuple(
        tuple(
            index
            for cell in grid_area_cells(point, parameters.radius, parameters.grid_size)
            for index in grid.get(cell, ())
        )
        for point in target_positions
    )
    return convert_selection_attributes(
        target_positions,
        source_positions,
        source_attributes,
        parameters.radius,
        candidates,
    )
