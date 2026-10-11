"""Fresh serial BoneCloth baseline input reference; not a Unity solver.

Compose source-bound ID mapping, child enumeration, baseline traversal, local
pose and ALL-vertex root/depth math. Explicit fresh/no-resize and ClearMemory
premises are required; no guessing about reused buffers or observed game state.
Source frames are render-local positions, NOT the computed baseline local pose.
"""

from collections.abc import Sequence
from dataclasses import dataclass

from official_physics_baseline_build import BuiltBaselines, build_transform_baselines
from official_physics_constraints import Vector3
from official_physics_proxy_baseline import (
    LocalPose,
    evaluate_baseline_local_pose,
    map_transform_ids,
    reverse_inserted_children_no_resize,
)
from official_physics_root_depth import VertexRootDepth, evaluate_vertex_root_depth


@dataclass(frozen=True)
class BaselineInputs:
    parents: tuple[int, ...]
    local_roots: tuple[int, ...]
    children: tuple[tuple[int, ...], ...]
    baselines: BuiltBaselines
    local_pose: LocalPose
    root_depth: VertexRootDepth


def compose_baseline_inputs(
    ids: Sequence[int],
    parent_ids: Sequence[int],
    root_ids: Sequence[int],
    attributes: Sequence[int],
    positions: Sequence[Vector3],
    normals: Sequence[Vector3],
    tangents: Sequence[Vector3],
    *,
    fresh_serial_no_resize: bool,
    cleared_output_buffers: bool,
) -> BaselineInputs:
    """Preserve runtime-ID slot/root order and original typed buffer boundaries.

    Fresh map capacity 3*n exceeds at most n serial insertions. Head insertion
    reverses matching child order, LIFO traversal reverses it again as observed.
    Output NativeArrays use ClearMemory1: unvisited rotations are ZERO, not
    identity. The native pose Job has no attributes field/ZeroDistance writes.
    Root/depth uses original proxy positions, not the pose Job output arrays.
    Adapter validation remains stricter than native malformed-input behavior.
    """
    if fresh_serial_no_resize is not True or cleared_output_buffers is not True:
        raise ValueError("Require explicit fresh serial no-resize and cleared outputs")
    mapped = map_transform_ids(ids, parent_ids, root_ids)
    children = reverse_inserted_children_no_resize(mapped.parents)
    baselines = build_transform_baselines(
        mapped.parents, attributes, mapped.roots, children
    )
    count = len(ids)
    local_pose = evaluate_baseline_local_pose(
        baselines.data,
        mapped.parents,
        positions,
        normals,
        tangents,
        ((0, 0, 0),) * count,
        ((0, 0, 0, 0),) * count,
    )
    depth = evaluate_vertex_root_depth(
        mapped.parents, attributes, positions, (0,) * count
    )
    return BaselineInputs(
        mapped.parents, mapped.roots, children, baselines, local_pose, depth
    )
