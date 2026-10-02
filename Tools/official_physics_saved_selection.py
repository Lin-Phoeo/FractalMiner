"""Finite ordinary bone-build selection and proxy attribute application reference.

Worker368612/0x3ddcec0 branches on IsValid, not userEdit. Valid selection is
reused (deep-cloned by MoveNext); invalid selection uses the proxy constructor,
identity transform, Move fill and explicit roots. Resolved dictionary overrides
then replace full bytes on BOTH paths. NOT prebuild/paint/mesh or full worker.

ApplySelectionAttribute371531/0x41b6e80 takes radius=max(proxy average distance,
selection maximum distance, Single 1e-5), gridSize=radius*1.5. Job371602/0x2ef3e40
ORs nearest source byte into OLD proxy flags. This differs from ConvertFrom.
Caller positions must already share original local space; no guessed conversion.
Only fresh serial/no-resize grid is supported; no Team/solver or Unity writes.
Finite/count/type/index rejection is adapter policy, not native exception logic.
"""

from collections.abc import Sequence
from dataclasses import dataclass

from official_physics_angle_baseline import _index, _integer
from official_physics_angles import _float3
from official_physics_bone_import import transform_point_single
from official_physics_constraints import Vector3, _single
from official_physics_grid import build_fresh_selection_grid, grid_area_cells
from official_physics_proxy_frames import apply_bone_transform_flags
from official_physics_selection import convert_selection_attributes

_IDENTITY = ((1, 0, 0, 0), (0, 1, 0, 0), (0, 0, 1, 0), (0, 0, 0, 1))


@dataclass(frozen=True)
class SavedSelection:
    positions: tuple[Vector3, ...] | None
    attributes: tuple[int, ...] | None
    max_connection_distance: float
    user_edit: bool


def selection_is_valid(selection: SavedSelection) -> bool:
    """IsValid369315/0x4564da0: nonnull, nonempty, equal-length arrays ONLY."""
    positions, attributes = selection.positions, selection.attributes
    return (
        positions is not None
        and attributes is not None
        and len(positions) > 0
        and len(attributes) > 0
        and len(positions) == len(attributes)
    )


def _checked_selection(
    selection: SavedSelection,
) -> tuple[tuple[Vector3, ...], tuple[int, ...], float]:
    if not selection_is_valid(selection):
        raise ValueError("Adapter requires a valid nonempty saved selection")
    # Explicit narrowing; IsValid intentionally does not perform finite validation.
    assert selection.positions is not None and selection.attributes is not None
    _integer(len(selection.positions), 65535)
    if type(selection.user_edit) is not bool:
        raise ValueError("Adapter requires a Boolean userEdit field")
    return (
        tuple(_float3(point) for point in selection.positions),
        tuple(_integer(attribute, 255) for attribute in selection.attributes),
        _single(selection.max_connection_distance),
    )


def choose_bone_build_selection(
    saved: SavedSelection,
    imported_proxy_positions: Sequence[Vector3],
    imported_proxy_max_vertex_distance: float,
    resolved_root_indices: Sequence[int],
    resolved_bone_overrides: Sequence[tuple[int, int]],
) -> SavedSelection:
    """Ordinary bone branch AFTER ImportFrom, BEFORE reduction/optimization.

    Valid saved arrays are cloned regardless of userEdit or collected bone count.
    Invalid saved arrays construct from proxy localPositions with source identity
    matrix, maxVertexDistance (NOT average or recomputed parent distance), Move
    fill and resolved root Fixed bytes. New selection has default userEdit=false.

    Overrides use original dictionary enumeration and RenderSetupData ID lookup:
    -1 skips a missing ID; nonnegative indices address the SELECTION array.
    Null selection objects/upstream flags/prebuild/paint paths are not emulated.
    No bone name guessing, reindexing or implicit skin/proxy correspondence.
    """
    if selection_is_valid(saved):
        positions, attributes, maximum = _checked_selection(saved)
        edited = saved.user_edit
        mutable = list(attributes)
    else:
        count = _integer(len(imported_proxy_positions), 65535)
        positions = tuple(
            transform_point_single(_IDENTITY, point)
            for point in imported_proxy_positions
        )
        maximum = _single(imported_proxy_max_vertex_distance)
        edited = False
        mutable = [2] * count
        for root in resolved_root_indices:
            mutable[_index(root, count)] = 1
    for index, attribute in resolved_bone_overrides:
        if type(index) is not int or index < -1:
            raise ValueError("Adapter requires a resolved index or missing-ID -1")
        if index >= 0:
            mutable[_index(index, len(mutable))] = _integer(attribute, 255)
    return SavedSelection(positions, tuple(mutable), maximum, edited)


@dataclass(frozen=True)
class ProxySelectionSearchParameters:
    radius: float
    grid_size: float


def proxy_selection_search_parameters(
    average_vertex_distance: float, max_connection_distance: float
) -> ProxySelectionSearchParameters:
    """ApplySelectionAttribute RIP sites0x41b722d/7240: 1e-5 and **1.5**.

    Finite domain only (native NaN comparison paths are deliberately excluded).
    Negative finite distances are accepted and floored by original epsilon.
    """
    radius = max(
        _single(average_vertex_distance),
        _single(max_connection_distance),
        _single(1e-5),
    )
    return ProxySelectionSearchParameters(radius, _single(radius * _single(1.5)))


def apply_proxy_selection_attributes(
    proxy_positions: Sequence[Vector3],
    old_attributes: Sequence[int],
    selection_positions: Sequence[Vector3],
    selection_attributes: Sequence[int],
    radius: float,
    native_candidates: Sequence[Sequence[int]],
) -> tuple[int, ...]:
    """Job371602 scalar matcher + preserved old byte, no synthetic candidate sort.

    Nearest inclusive radius, later-enumerated ties replace winner (even Invalid).
    Final byte is old | winner; no match leaves old unchanged. Not old=Invalid,
    not full-byte assignment, and Fixed does not suppress an existing Move bit.
    """
    if len(old_attributes) != len(proxy_positions):
        raise ValueError("Adapter requires parallel ordered proxy buffers")
    old = tuple(_integer(attribute, 255) for attribute in old_attributes)
    winners = convert_selection_attributes(
        proxy_positions,
        selection_positions,
        selection_attributes,
        radius,
        native_candidates,
    )
    return tuple(a | b for a, b in zip(old, winners, strict=True))


@dataclass(frozen=True)
class AppliedBoneSelection:
    attributes: tuple[int, ...]
    transform_flags: tuple[int, ...]
    search: ProxySelectionSearchParameters


def apply_bone_proxy_selection(
    proxy_positions: Sequence[Vector3],
    old_attributes: Sequence[int],
    initial_transform_flags: Sequence[int],
    selection: SavedSelection,
    average_vertex_distance: float,
) -> AppliedBoneSelection:
    """Fresh serial bone-proxy attribute/transform-flag composition ONLY.

    Extra saved points are legal. GetPositionNativeArray's NON-transform overload
    is used upstream; caller must resolve space before entering this function.
    Native invalid selection sets error0x50de (this adapter raises ValueError).
    Final target buffers can be reordered/reduced if caller supplies their exact
    positions/attributes/flag order. No assumption of saved point/bone 1:1.
    """
    positions, attributes, maximum = _checked_selection(selection)
    search = proxy_selection_search_parameters(average_vertex_distance, maximum)
    grid = build_fresh_selection_grid(positions, search.grid_size)
    candidates = tuple(
        tuple(
            index
            for cell in grid_area_cells(point, search.radius, search.grid_size)
            for index in grid.get(cell, ())
        )
        for point in proxy_positions
    )
    applied = apply_proxy_selection_attributes(
        proxy_positions,
        old_attributes,
        positions,
        attributes,
        search.radius,
        candidates,
    )
    return AppliedBoneSelection(
        applied, apply_bone_transform_flags(applied, initial_transform_flags), search
    )
