"""Source-bound selection generation and ordered candidate kernel, not full import.

GenerateBoneClothSelection method368604/RVA0x59dff84 generates render-local
positions, Move defaults, maximum SINGLE parent-edge distance, explicit Fixed
roots, and userEdit=true. Parent indices must already exclude the render slot;
input contains skin-bone snapshots ONLY, not the appended render transform.

ConvertSelectionJob method369329/RVA0x5a1a30c picks nearest within inclusive
radius; ties overwrite with LATER native candidates. Caller MUST supply original
grid/NativeMultiHashMap enumeration per target. This is NOT full ConvertFrom,
grid creation/enumeration, actual selection branch choice or proxy application.
Finite, size, index, and forest rejection are adapter policy, not native guards.
"""

from collections.abc import Sequence
from dataclasses import dataclass

from official_physics_angle_baseline import _index, _integer
from official_physics_angles import _float3
from official_physics_baseline_build import _validate_forest
from official_physics_bone_import import transform_point_single
from official_physics_constraints import Vector3, _single
from official_physics_root_depth import _distance_single


@dataclass(frozen=True)
class GeneratedBoneSelection:
    positions: tuple[Vector3, ...]
    attributes: tuple[int, ...]
    max_connection_distance: float
    user_edit: bool


def generate_bone_selection(
    world_to_local: Sequence[Sequence[float]],
    world_positions: Sequence[Vector3],
    parents_excluding_render: Sequence[int],
    fixed_root_indices: Sequence[int | None],
) -> GeneratedBoneSelection:
    """Generate a NEW selection, never overwrite user-edited saved selection.

    Root indices are resolved object identities (not names). None means a root
    skipped upstream as null/destroyed. Parentless does not imply Fixed. All
    parented edges contribute max distance, independent of attributes.
    """
    count = _integer(len(world_positions), 65535)
    if len(parents_excluding_render) != count:
        raise ValueError("Adapter requires parallel skin-bone snapshot/parent buffers")
    attributes = [2] * count
    roots = tuple(root for root in fixed_root_indices if root is not None)
    children: list[list[int]] = [[] for _ in range(count)]
    for vertex, parent in enumerate(parents_excluding_render):
        if type(parent) is not int or not -(2**31) <= parent < 2**31:
            raise ValueError("Adapter requires Int32 parents")
        if parent >= 0:
            children[_index(parent, count)].append(vertex)
    _validate_forest(parents_excluding_render, attributes, roots, children)
    # Validate matrix even for empty input; validation is adapter-only policy.
    transform_point_single(world_to_local, (0, 0, 0))
    positions = tuple(
        transform_point_single(world_to_local, position) for position in world_positions
    )
    maximum = 0.0
    for vertex, parent in enumerate(parents_excluding_render):
        if parent >= 0:
            maximum = max(
                maximum, _distance_single(positions[vertex], positions[parent])
            )
    for root in roots:
        attributes[root] = 1
    return GeneratedBoneSelection(positions, tuple(attributes), maximum, True)


def convert_selection_attributes(
    target_positions: Sequence[Vector3],
    source_positions: Sequence[Vector3],
    source_attributes: Sequence[int],
    radius: float,
    native_candidates: Sequence[Sequence[int]],
) -> tuple[int, ...]:
    """Scalar inner matching loop ONLY; no fabricated grid or candidate sorting.

    Starts Invalid(0), not previous target attribute. Full source byte is copied,
    including flags and Invalid. Candidate filtering/order belongs to caller's
    ORIGINAL grid. No brute-force scan of candidates omitted by that grid.
    """
    target_count = _integer(len(target_positions), 65535)
    source_count = _integer(len(source_positions), 65535)
    if len(source_attributes) != source_count or len(native_candidates) != target_count:
        raise ValueError("Adapter requires parallel selection buffers and candidates")
    search_radius = _single(radius)
    if search_radius < 0:
        raise ValueError("Adapter requires nonnegative Single radius")
    targets = tuple(_float3(position) for position in target_positions)
    sources = tuple(_float3(position) for position in source_positions)
    attributes = tuple(_integer(attribute, 255) for attribute in source_attributes)
    result = []
    for target, candidates in zip(targets, native_candidates, strict=True):
        attribute, minimum = 0, _single(3.4028234663852886e38)
        for candidate in candidates:
            index = _index(candidate, source_count)
            distance = _distance_single(target, sources[index])
            if distance <= search_radius and distance <= minimum:
                minimum, attribute = distance, attributes[index]
        result.append(attribute)
    return tuple(result)
