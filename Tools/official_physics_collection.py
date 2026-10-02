"""Source-bound BoneCloth collector reference, not a full/live proxy importer.

Original RenderSetupData constructor method370195/RVA0x38d4a50: root and child
lists push forward into a LIFO stack, duplicate objects skip, ignore prunes the
subtree, collision indices are looked up BEFORE appending the render transform.
Root references retain input order/duplicates; render is appended unconditionally.

This offline adapter substitutes resolved (serialized file, signed Int64 PPtr)
identities for LIVE Unity object references, never for runtime Int32 instance IDs.
Caller must supply original ordered GetChild-equivalent lists and valid/live
reference resolution. Null/destroyed root or ignore behavior is NOT restored.
Validation and 65536-slot cap are adapter policy. No world snapshot evaluation,
movable attributes, selection, normal-axis processing, scheduling or bone writes.
"""

from collections.abc import Mapping, Sequence
from dataclasses import dataclass

TransformIdentity = tuple[str, int]


@dataclass(frozen=True)
class CollectedBoneTransforms:
    transforms: tuple[TransformIdentity, ...]
    root_transforms: tuple[TransformIdentity, ...]
    skin_bone_count: int
    render_transform_index: int
    collision_bone_indices: tuple[int, ...] | None


def _identity(value: TransformIdentity) -> TransformIdentity:
    if (
        not isinstance(value, tuple)
        or len(value) != 2
        or not isinstance(value[0], str)
        or not value[0]
        or type(value[1]) is not int
        or value[1] == 0
        or not -(2**63) <= value[1] < 2**63
    ):
        raise ValueError("Adapter requires a resolved non-null serialized identity")
    return value


def collect_bone_transforms(
    children: Mapping[TransformIdentity, Sequence[TransformIdentity]],
    roots: Sequence[TransformIdentity],
    render_transform: TransformIdentity,
    *,
    ignored: Sequence[TransformIdentity] = (),
    collision_bones: Sequence[TransformIdentity | None] | None = None,
) -> CollectedBoneTransforms:
    """Collect ordered identity slots only; render is outside skin_bone_count.

    Collision bones absent from collected slots produce -1, including render
    unless already collected. None collision entries are skipped, not emitted.
    Supplied graph/order remain caller-owned. Ignored roots stay in root_transforms.
    """
    graph = {
        _identity(node): tuple(_identity(child) for child in descendants)
        for node, descendants in children.items()
    }
    ordered_roots = tuple(_identity(root) for root in roots)
    render = _identity(render_transform)
    excluded = {_identity(node) for node in ignored}
    if not ordered_roots:
        raise ValueError(
            "Adapter requires at least one root; original ctor fails empty"
        )
    if render not in graph or any(root not in graph for root in ordered_roots):
        raise ValueError("Adapter requires roots and render in resolved hierarchy")
    if any(child not in graph for values in graph.values() for child in values):
        raise ValueError("Adapter refuses unresolved child identities")
    stack = list(ordered_roots)
    collected: list[TransformIdentity] = []
    indices: dict[TransformIdentity, int] = {}
    while stack:
        node = stack.pop()
        if node in indices or node in excluded:
            continue
        if len(collected) >= 65535:
            raise ValueError(
                "Adapter capacity reserves final render slot in UInt16 domain"
            )
        indices[node] = len(collected)
        collected.append(node)
        stack.extend(graph[node])
    collision_indices = None
    if collision_bones is not None:
        collision_indices = tuple(
            indices.get(_identity(bone), -1)
            for bone in collision_bones
            if bone is not None
        )
    count = len(collected)
    collected.append(render)
    return CollectedBoneTransforms(
        tuple(collected), ordered_roots, count, count, collision_indices
    )
