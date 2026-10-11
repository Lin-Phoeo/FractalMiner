"""Fresh ordinary BoneCloth import attribute/flag buffers ONLY.

VirtualMesh ctor371567 allocates empty attributes; AddRange -> Expand ->
NativeArray ctor0x3dd98a0 with ClearMemory=1 yields Invalid=0 bytes. Ordinary
BoneCloth Line skips the BoneSpring DisableCollision fill. TransformData
AddTransformRange370726 appends in source order and fills Read=1 for ALL slots.
Job371603 applies attributes by SAME vertex slot, preserving appended render.
Not reused/appended/optimized/reduced buffers, normal-axis, Team or solver.
Fresh-import premise is explicit; static reference is not runtime observation.
"""

from collections.abc import Sequence
from dataclasses import dataclass

from official_physics_angle_baseline import _integer
from official_physics_proxy_frames import apply_bone_transform_flags


@dataclass(frozen=True)
class FreshBoneBuffers:
    initial_proxy_attributes: tuple[int, ...]
    initial_transform_flags: tuple[int, ...]
    proxy_attributes: tuple[int, ...]
    transform_flags: tuple[int, ...]
    skin_transform_indices: tuple[int, ...]


def compose_fresh_bone_buffers(
    matched_selection_bytes: Sequence[int],
    snapshot_count: int,
    render_index: int,
    *,
    fresh_import: bool,
) -> FreshBoneBuffers:
    """Fresh empty TransformData + unreduced skin order, before optimization.

    Native bulk append returns oldCount+i; here oldCount=0 is explicit. Duplicate
    object IDs do not merge slots; even render identical to a skin object retains
    its final separate Read-only slot. Existing/prebuilt state is not supported.
    """
    if fresh_import is not True:
        raise ValueError("Require explicit fresh ordinary import premise")
    count = _integer(len(matched_selection_bytes), 65535)
    if (
        _integer(snapshot_count, 65536) != count + 1
        or _integer(render_index, 65535) != count
    ):
        raise ValueError("Require unchanged skin slots and one final render slot")
    winners = tuple(_integer(value, 255) for value in matched_selection_bytes)
    initial_attributes = (0,) * count
    initial_flags = (1,) * snapshot_count
    attributes = tuple(
        old | winner for old, winner in zip(initial_attributes, winners, strict=True)
    )
    flags = (
        apply_bone_transform_flags(attributes, initial_flags[:count])
        + initial_flags[count:]
    )
    return FreshBoneBuffers(
        initial_attributes, initial_flags, attributes, flags, tuple(range(count))
    )
