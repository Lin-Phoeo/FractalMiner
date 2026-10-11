"""Source-gated ordinary Line proxy frame production, NOT full proxy/solver.

RuntimeBuild callback368612: Reduction only clothType0; Optimization371522
calls RemoveDuplicateTriangles371523 which returns for triangleCount<2.
This adapter accepts ONLY ordinary BoneCloth1/Line0/zero triangles, so vertex
order and imported normal/tangent arrays survive optimization unchanged.
None alignment retains the previously reviewed caller identity-fill contract;
generic FillJob actual writes and runtime allocator remain unproved here.
normalAxis is a distinct solver parameter, not an extra proxy pre-rotation.
"""

from collections.abc import Sequence
from dataclasses import dataclass

from official_physics_angle_baseline import _integer
from official_physics_angles import Quaternion
from official_physics_constraints import Vector3
from official_physics_proxy_baseline import LocalPose
from official_physics_proxy_frames import (
    default_normal_adjustments,
    vertex_bindpose_frames,
    vertex_to_transform_rotations,
)


@dataclass(frozen=True)
class LineProxyFrames:
    source_vertex_indices: tuple[int, ...]
    vertex_bindpose: LocalPose
    vertex_to_transform_rotations: tuple[Quaternion, ...]
    normal_adjustment_rotations: tuple[Quaternion, ...]


def compose_line_proxy_frames(
    positions: Sequence[Vector3],
    normals: Sequence[Vector3],
    tangents: Sequence[Vector3],
    world_rotations: Sequence[Quaternion],
    inverse_render_rotation: Quaternion,
    *,
    cloth_type: int,
    connect_mode: int,
    triangle_count: int,
    alignment_mode: int,
) -> LineProxyFrames:
    """Explicit source-order reference inputs, before full topology construction.

    Checks are adapter policy, not native exception semantics. No reduction or
    radiating alignment fallback. Accepting the route is not observing the game
    build route, original NativeArray/Job/Burst or recovered stage character.
    """
    if (
        _integer(cloth_type, 10) != 1
        or _integer(connect_mode, 2) != 0
        or _integer(triangle_count, 65536) != 0
        or _integer(alignment_mode, 2) != 0
    ):
        raise ValueError("Only ordinary BoneCloth Line zero-triangle None route")
    count = _integer(len(positions), 65536)
    if any(len(buffer) != count for buffer in (normals, tangents, world_rotations)):
        raise ValueError("Require unchanged parallel skin vertex windows")
    return LineProxyFrames(
        tuple(range(count)),
        vertex_bindpose_frames(positions, normals, tangents),
        vertex_to_transform_rotations(
            inverse_render_rotation, normals, tangents, world_rotations
        ),
        default_normal_adjustments(count, alignment_mode),
    )
