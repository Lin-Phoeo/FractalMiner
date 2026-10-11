"""Finite ordinary Line import and saved-selection matching INPUTS only.

ImportBoneType371507 builds sorted parent/child pairs in child-slot order, without
deduplication. Work_AverageLineDistanceJob/0x42b8e10 samples every
max(lineCount/100,1) edge; Single sum of squared distances is divided by the
Single count then square-rooted by CalcAverageAndMaxVertexDistanceRun371548.
The average is RMS, not mean length or maximum parent length.

Only Line/no-triangle/unreduced render-local inputs, valid saved selection and
explicit resolved overrides are supported. Returns candidate/winner bytes before
OR with existing proxy bytes. Does NOT fabricate initial attributes/TransformData
flags, observe runtime override dictionaries, generate Team or execute a solver.
"""

import math
from collections.abc import Sequence
from dataclasses import dataclass

from official_physics_angle_baseline import _index, _integer
from official_physics_angles import _float3
from official_physics_constraints import Vector3, _single
from official_physics_grid import build_fresh_selection_grid, grid_area_cells
from official_physics_saved_selection import (
    ProxySelectionSearchParameters,
    SavedSelection,
    choose_bone_build_selection,
    proxy_selection_search_parameters,
    selection_is_valid,
)
from official_physics_selection import convert_selection_attributes


def build_bone_lines(
    skin_parent_indices: Sequence[int], connection_mode: int
) -> tuple[tuple[int, int], ...]:
    """Already-resolved skin parents excluding final render; no root guessing."""
    if type(connection_mode) is not int or connection_mode != 0:
        raise ValueError("Adapter supports Line connection mode only")
    count = _integer(len(skin_parent_indices), 65535)
    lines = []
    for child, parent in enumerate(skin_parent_indices):
        if type(parent) is not int or parent < -1:
            raise ValueError("Adapter requires resolved parent indices or -1")
        if parent >= 0:
            parent = _index(parent, count)
            lines.append((min(parent, child), max(parent, child)))
    return tuple(lines)


@dataclass(frozen=True)
class LineDistanceMetrics:
    sampling_stride: int
    sampled_line_count: int
    sum_squared_lengths: float
    average_vertex_distance: float
    max_vertex_distance: float


def line_distance_metrics(
    positions: Sequence[Vector3], lines: Sequence[Sequence[int]]
) -> LineDistanceMetrics:
    """Zero-initialized Line-only statistic buffers; not triangle accumulation.

    Finite/size/index rejection is adapter policy, not native NaN/exception logic.
    Keeps helper0x4a4bd00 dot order: (y*y + x*x) + z*z and serial Single sum.
    """
    count = _integer(len(positions), 65535)
    line_count = _integer(len(lines), 65535)
    points = tuple(_float3(point) for point in positions)
    checked = []
    for line in lines:
        if len(line) != 2:
            raise ValueError("Adapter requires two ordered Line endpoints")
        checked.append(tuple(_index(index, count) for index in line))
    stride = max(line_count // 100, 1)
    total, maximum, sampled = 0.0, 0.0, 0
    for index in range(0, line_count, stride):
        a, b = checked[index]
        delta = tuple(_single(x - y) for x, y in zip(points[a], points[b], strict=True))
        squared = tuple(_single(value * value) for value in delta)
        distance_squared = _single(_single(squared[1] + squared[0]) + squared[2])
        total = _single(total + distance_squared)
        maximum = max(maximum, distance_squared)
        sampled += 1
    average = _single(math.sqrt(_single(total / _single(sampled)))) if sampled else 0.0
    maximum = _single(math.sqrt(maximum)) if sampled else 0.0
    return LineDistanceMetrics(stride, sampled, total, average, maximum)


@dataclass(frozen=True)
class LineSelectionInputs:
    lines: tuple[tuple[int, int], ...]
    metrics: LineDistanceMetrics
    selection: SavedSelection
    search: ProxySelectionSearchParameters
    native_candidates: tuple[tuple[int, ...], ...]
    matched_selection_bytes: tuple[int, ...]


def match_saved_line_selection(
    proxy_positions: Sequence[Vector3],
    skin_parent_indices: Sequence[int],
    saved: SavedSelection,
    *,
    resolved_bone_overrides: Sequence[tuple[int, int]],
) -> LineSelectionInputs:
    """Explicit valid-saved ordinary Line path BEFORE old-byte OR and flags.

    Positions must already share render-local space; no extra transform applied.
    Overrides address selection slots, not nearest target indices or bone names.
    Passing empty overrides is a declared producer premise, not runtime evidence.
    Saved root attributes are never overwritten with a guessed Fixed default.
    """
    if len(proxy_positions) != len(skin_parent_indices) or not selection_is_valid(
        saved
    ):
        raise ValueError(
            "Adapter requires unchanged skin order and valid saved selection"
        )
    lines = build_bone_lines(skin_parent_indices, 0)
    metrics = line_distance_metrics(proxy_positions, lines)
    selection = choose_bone_build_selection(
        saved, proxy_positions, metrics.max_vertex_distance, (), resolved_bone_overrides
    )
    assert selection.positions is not None and selection.attributes is not None
    search = proxy_selection_search_parameters(
        metrics.average_vertex_distance, selection.max_connection_distance
    )
    grid = build_fresh_selection_grid(selection.positions, search.grid_size)
    candidates = tuple(
        tuple(
            index
            for cell in grid_area_cells(point, search.radius, search.grid_size)
            for index in grid.get(cell, ())
        )
        for point in proxy_positions
    )
    matched = convert_selection_attributes(
        proxy_positions,
        selection.positions,
        selection.attributes,
        search.radius,
        candidates,
    )
    return LineSelectionInputs(lines, metrics, selection, search, candidates, matched)
