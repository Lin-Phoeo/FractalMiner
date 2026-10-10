"""Produce ordinary BoneCloth identity slots from a resolved serialized forest.

Uses the verified collector, GetTransformIndexFromId (370205/0x5a51ef0) and
GetParentTransformIndex (370206/0x346ff20) first-hit List.IndexOf semantics.
This is an offline identity adapter, NOT a runtime Int32-ID producer. The caller
supplies resolved file-qualified signed Int64 objects and ordered child lists.
For the ordinary build, the render argument is the component Transform recorded
by ClothProcess.Init/CreateBoneRenderSetupData; prebuilt/runtime overrides are
not inferred here. Missing collected parents/roots remain -1, never guessed.

Forest, reciprocal-edge and identity validation are adapter policy, not native
guards. No world getters, saved-selection matching, proxy topology, Team/native
allocation, normal processing or Unity simulation is produced by this module.
Collision bones are explicit caller input; collider Transform references are
NOT silently assumed to be the constructor's collisionBones argument.
"""

from collections.abc import Mapping, Sequence
from dataclasses import dataclass

from official_physics_collection import (
    CollectedBoneTransforms,
    TransformIdentity,
    _identity,
    collect_bone_transforms,
)


@dataclass(frozen=True)
class BoneIdentityInputs:
    collected: CollectedBoneTransforms
    snapshot_parent_indices: tuple[int, ...]
    skin_parent_indices: tuple[int, ...]
    root_indices: tuple[int, ...]


def build_bone_identity_inputs(
    children: Mapping[TransformIdentity, Sequence[TransformIdentity]],
    parents: Mapping[TransformIdentity, TransformIdentity | None],
    roots: Sequence[TransformIdentity],
    render_transform: TransformIdentity,
    *,
    ignored: Sequence[TransformIdentity] = (),
    collision_bones: Sequence[TransformIdentity | None] | None = None,
) -> BoneIdentityInputs:
    """Compile identity-only input buffers without narrowing PPtr to instance ID.

    snapshot_parent_indices covers ALL collected slots including appended render.
    skin_parent_indices covers ONLY skin and removes a parent lookup iff its
    resulting index equals the final render index. An earlier identical render
    object is therefore retained, exactly like first-hit List.IndexOf.
    root_indices retains source order/duplicates and -1 for uncollected roots.
    These are not attribute, fixed-root or NativeArray buffers.
    """
    graph = {
        _identity(node): tuple(_identity(child) for child in values)
        for node, values in children.items()
    }
    parent_map = {
        _identity(node): None if parent is None else _identity(parent)
        for node, parent in parents.items()
    }
    if graph.keys() != parent_map.keys():
        raise ValueError("Adapter requires parallel resolved parent/child identities")
    ordered_ignored = tuple(_identity(node) for node in ignored)
    if any(node not in graph for node in ordered_ignored):
        raise ValueError("Adapter refuses unresolved ignored identities")
    linked_children: set[TransformIdentity] = set()
    for parent, values in graph.items():
        for child in values:
            if child not in graph or child in linked_children:
                raise ValueError("Adapter requires resolved single-parent child edges")
            if parent_map[child] != parent:
                raise ValueError("Adapter requires reciprocal parent/child edges")
            linked_children.add(child)
    for node, parent in parent_map.items():
        if parent is not None and (parent not in graph or node not in linked_children):
            raise ValueError("Adapter refuses unresolved or nonreciprocal parents")
    # Iterative validation supports long chains without recursion-limit failures.
    verified: set[TransformIdentity] = set()
    for node in graph:
        chain: set[TransformIdentity] = set()
        cursor = node
        while cursor not in verified:
            if cursor in chain:
                raise ValueError("Adapter requires an acyclic serialized forest")
            chain.add(cursor)
            parent = parent_map[cursor]
            if parent is None:
                break
            cursor = parent
        verified.update(chain)
    collected = collect_bone_transforms(
        graph,
        roots,
        render_transform,
        ignored=ordered_ignored,
        collision_bones=collision_bones,
    )
    first_indices: dict[TransformIdentity, int] = {}
    for index, node in enumerate(collected.transforms):
        first_indices.setdefault(node, index)
    snapshot_parents = tuple(
        first_indices.get(parent, -1) if parent is not None else -1
        for parent in (parent_map[node] for node in collected.transforms)
    )
    skin_parents = tuple(
        -1 if index == collected.render_transform_index else index
        for index in snapshot_parents[: collected.skin_bone_count]
    )
    return BoneIdentityInputs(
        collected,
        snapshot_parents,
        skin_parents,
        tuple(first_indices.get(root, -1) for root in collected.root_transforms),
    )
