"""Finite bone-proxy frame kernels, not complete ConvertProxyMesh or live physics.

Source Jobs371595/0x39d3c00,371597/0x39d3d30,371603/0x343c570; caller
ProxyNormalAdjustment371527/0x43f6b10. Only alignment None(0) is supported.
No normalAxis reinterpretation, radiation modes, triangle rebuild, saved-selection
branch, Team/scheduler/solver or Unity bone writes. Original ordered proxy inputs,
raw world rotations and inverse render rotation must be supplied, never guessed.
Shape/finite/degeneracy/count rejection is adapter policy, not native exceptions.
"""

from collections.abc import Sequence
from dataclasses import dataclass
from typing import cast

from official_physics_angle_baseline import _integer
from official_physics_angle_cache import (
    _quaternion,
    multiply_quaternions,
    quaternion_inverse,
)
from official_physics_angles import Quaternion, _float3
from official_physics_bindpose import BoundBoneInputs
from official_physics_constraints import Vector3
from official_physics_proxy_baseline import LocalPose, rotation_from_normal_tangent


def default_normal_adjustments(
    vertex_count: int, alignment_mode: int = 0
) -> tuple[Quaternion, ...]:
    """Caller-side identity-fill contract for None mode only.

    Source allocates then Run<FillJob<quaternion>> with identity; mode0 returns
    without radiation adjustment. This reference is NOT native generic scheduling
    or proof of the game's actual initialized buffer. Other modes fail explicitly.
    """
    count = _integer(vertex_count, 65536)
    if _integer(alignment_mode, 2) != 0:
        raise ValueError("Adapter has not restored nonzero normal alignment modes")
    return ((0.0, 0.0, 0.0, 1.0),) * count


def _parallel(buffers: Sequence[Sequence[object]]) -> int:
    count = _integer(len(buffers[0]), 65536)
    if any(len(buffer) != count for buffer in buffers[1:]):
        raise ValueError("Adapter requires parallel ordered proxy buffers")
    return count


def vertex_bindpose_frames(
    positions: Sequence[Vector3],
    normals: Sequence[Vector3],
    tangents: Sequence[Vector3],
) -> LocalPose:
    """Job371597: -position and inverse(frame), SEPARATE outputs.

    Negation0x39d3f50 flips xyz sign bits. Rotation helper0x39d4250 uses
    normal=UP/tangent=FORWARD. Inversion is reciprocal squared norm followed by
    (-1,-1,-1,+1), NOT normalized conjugate or a rotated inverse-TRS translation.
    """
    _parallel((positions, normals, tangents))
    inverse_positions, inverse_rotations = [], []
    for position, normal, tangent in zip(positions, normals, tangents, strict=True):
        position = _float3(position)
        inverse_positions.append(cast(Vector3, tuple(-lane for lane in position)))
        inverse_rotations.append(
            quaternion_inverse(rotation_from_normal_tangent(normal, tangent))
        )
    return LocalPose(tuple(inverse_positions), tuple(inverse_rotations))


def vertex_to_transform_rotations(
    inverse_render_rotation: Quaternion,
    normals: Sequence[Vector3],
    tangents: Sequence[Vector3],
    world_rotations: Sequence[Quaternion],
) -> tuple[Quaternion, ...]:
    """Job371595: inverse(frame) * (invRender * original worldQuaternion).

    Preserve this product order and raw world quaternion magnitude. Caller must
    provide the original initInverseRotation and exact skin/proxy slot mapping.
    No auto-normalization, children-derived direction or current FBX local pose.
    """
    _parallel((normals, tangents, world_rotations))
    inverse_render = _quaternion(inverse_render_rotation)
    return tuple(
        multiply_quaternions(
            quaternion_inverse(rotation_from_normal_tangent(normal, tangent)),
            multiply_quaternions(inverse_render, world_rotation),
        )
        for normal, tangent, world_rotation in zip(
            normals, tangents, world_rotations, strict=True
        )
    )


def apply_bone_transform_flags(
    attributes: Sequence[int], initial_transform_flags: Sequence[int]
) -> tuple[int, ...]:
    """Job371603: Move -> OR4, ELSE Fixed -> OR2; either -> OR8.

    Both attribute bits set chooses Move, not both position flags. Preserve ALL
    existing flag bits; Invalid/other attribute bits neither reset nor add flags.
    These bits alone do not establish a safe/unique Unity transform writer.
    """
    _parallel((attributes, initial_transform_flags))
    result = []
    for attribute, initial in zip(attributes, initial_transform_flags, strict=True):
        attribute, flags = _integer(attribute, 255), _integer(initial, 255)
        if attribute & 2:
            flags |= 4
        elif attribute & 1:
            flags |= 2
        if attribute & 3:
            flags |= 8
        result.append(flags)
    return tuple(result)


@dataclass(frozen=True)
class BoneProxyFrames:
    bound: BoundBoneInputs
    normal_adjustments: tuple[Quaternion, ...]
    vertex_to_transform_rotations: tuple[Quaternion, ...]
    vertex_bindposes: LocalPose
    transform_flags: tuple[int, ...]


def prepare_bone_proxy_frames(
    bound: BoundBoneInputs,
    inverse_render_rotation: Quaternion,
    initial_transform_flags: Sequence[int],
    alignment_mode: int = 0,
) -> BoneProxyFrames:
    """Explicit snapshot/new-selection -> finite bone-proxy frame composition.

    PRECONDITION: unchanged one-to-one skin/proxy slot order, None alignment, no
    mesh/triangle normal reconstruction, no selection reduction/reordering. Does
    NOT select the real saved-selection branch or execute whole ConvertProxyMesh.
    Callers cannot use this shortcut on merged/reduced/mesh proxies.
    """
    frames, snapshots = bound.vertices.frames, bound.inputs.snapshots
    _parallel((frames.positions, snapshots, bound.inputs.selection.attributes))
    adjustments = default_normal_adjustments(len(frames.positions), alignment_mode)
    to_transforms = vertex_to_transform_rotations(
        inverse_render_rotation,
        frames.normals,
        frames.tangents,
        tuple(snapshot.rotation for snapshot in snapshots),
    )
    bindposes = vertex_bindpose_frames(
        frames.positions, frames.normals, frames.tangents
    )
    flags = apply_bone_transform_flags(
        bound.inputs.selection.attributes, initial_transform_flags
    )
    return BoneProxyFrames(bound, adjustments, to_transforms, bindposes, flags)
