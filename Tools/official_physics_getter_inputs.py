"""Identity-ordered world getter import, NOT full proxy, solver or game capture.

Joins explicit LIVE instance IDs/getter values to previously compiled serialized
identity slots. Serialized signed Int64 PPtr is never cast to Int32. List.IndexOf
first-hit parent order is cross-checked before invoking the existing source-bound
ReadTransformJob and bone vertex/weight/bindpose references. All finite matrices
are explicit getter inputs; prefab local TRS and guessed inverses are not used.
Null/destroyed access, previous storage, animation scheduling, saved selection,
normal-axis processing and native arrays remain outside this adapter.
Validation is adapter policy, not native exception or live Unity object logic.
"""

from collections.abc import Mapping, Sequence
from dataclasses import dataclass

from official_physics_bindpose import ImportedBoneVertices, import_bone_vertices
from official_physics_bone_import import Matrix4, _matrix
from official_physics_collection import TransformIdentity, _identity
from official_physics_identity_inputs import BoneIdentityInputs
from official_physics_snapshot import (
    RenderTransformSnapshot,
    TransformGetterValues,
    read_transform_snapshots,
)


@dataclass(frozen=True)
class InstanceGetter:
    instance_id: int
    parent_instance_id: int
    values: TransformGetterValues
    world_to_local: Sequence[Sequence[float]]


@dataclass(frozen=True)
class IdentityBoneImport:
    runtime_instance_ids: tuple[int, ...]
    runtime_parent_ids: tuple[int, ...]
    runtime_root_ids: tuple[int, ...]
    snapshots: tuple[RenderTransformSnapshot, ...]
    render_world_to_local: Matrix4
    render_local_to_world: Matrix4
    vertices: ImportedBoneVertices


def _runtime_id(value: int, *, nullable: bool = False) -> int:
    if type(value) is not int or not -(2**31) <= value < 2**31:
        raise ValueError("Adapter requires actual signed Int32 runtime instance IDs")
    if value == 0 and not nullable:
        raise ValueError("Adapter refuses null instance identity")
    return value


def prepare_identity_bone_import(
    inputs: BoneIdentityInputs,
    getters: Mapping[TransformIdentity, InstanceGetter],
) -> IdentityBoneImport:
    """Compiled slots -> runtime parent check -> snapshots -> SKIN vertex import.

    Matrices come from the appended render object's actual getter record. Extra
    records support uncollected/ignored root references. All objects must be valid;
    an absent record cannot silently preserve a previous or fabricate zero slot.
    Instance-ID uniqueness is per distinct serialized object, NOT per output slot.
    No physical attributes are generated or assigned here.
    """
    collected = inputs.collected
    skin_count = collected.skin_bone_count
    if (
        skin_count != collected.render_transform_index
        or len(collected.transforms) != skin_count + 1
        or len(inputs.snapshot_parent_indices) != skin_count + 1
        or len(inputs.skin_parent_indices) != skin_count
    ):
        raise ValueError("Adapter requires checked collector/parent windows")
    records: dict[TransformIdentity, InstanceGetter] = {}
    instance_objects: dict[int, TransformIdentity] = {}
    for node, record in getters.items():
        identity = _identity(node)
        instance = _runtime_id(record.instance_id)
        _runtime_id(record.parent_instance_id, nullable=True)
        if instance in instance_objects:
            raise ValueError(
                "Different serialized objects cannot share a live instance"
            )
        instance_objects[instance] = identity
        records[identity] = record
    needed = set(collected.transforms) | set(collected.root_transforms)
    if not needed.issubset(records):
        raise ValueError("Adapter refuses missing actual getter/root records")
    ordered = tuple(records[node] for node in collected.transforms)
    ids = tuple(record.instance_id for record in ordered)
    parents = tuple(record.parent_instance_id for record in ordered)
    first_indices: dict[int, int] = {}
    for index, instance in enumerate(ids):
        first_indices.setdefault(instance, index)
    actual_parents = tuple(first_indices.get(parent, -1) for parent in parents)
    actual_skin_parents = tuple(
        -1 if index == collected.render_transform_index else index
        for index in actual_parents[:skin_count]
    )
    root_ids = tuple(records[root].instance_id for root in collected.root_transforms)
    if (
        actual_parents != inputs.snapshot_parent_indices
        or actual_skin_parents != inputs.skin_parent_indices
        or tuple(first_indices.get(root, -1) for root in root_ids)
        != inputs.root_indices
    ):
        raise ValueError(
            "Actual runtime hierarchy differs from compiled identity slots"
        )
    snapshots = read_transform_snapshots(tuple(record.values for record in ordered))
    render = ordered[skin_count]
    wtol, ltow = _matrix(render.world_to_local), _matrix(render.values.local_to_world)
    skin = snapshots[:skin_count]
    vertices = import_bone_vertices(
        wtol,
        ltow,
        tuple(slot.position for slot in skin),
        tuple(slot.rotation for slot in skin),
        tuple(slot.scale for slot in skin),
    )
    return IdentityBoneImport(ids, parents, root_ids, snapshots, wtol, ltow, vertices)
