"""Finite anchor region 5a35a8d..5a35eba after sign-remap/frame-target production.

Does not select/sample anchor transforms, produce frameWorld, remap scale signs,
publish original arrays or advance oldAnchor at the kernel tail. Requires those
inputs already resolved. Anchor local position is produced here on reset.
Finite values/[0,1] inertia/singular rejection are ADAPTER restrictions.
"""

from dataclasses import dataclass, replace

from official_physics_angle_baseline import _integer
from official_physics_angle_cache import (
    _quaternion,
    multiply_quaternions,
    quaternion_inverse,
)
from official_physics_angles import Quaternion, _float3
from official_physics_constraints import Vector3, _add, _single, _sub, _vector
from official_physics_frame_inertia import FrameInertiaState, FrameInertiaTeam
from official_physics_matrix import (
    build_double_trs,
    inverse_double_matrix,
    transform_double_point,
)
from official_physics_setter import _lerp, interpolate_rotation

_ZERO: Vector3 = (0.0, 0.0, 0.0)
_Q: Quaternion = (0.0, 0.0, 0.0, 1.0)
_S: Vector3 = (1.0, 1.0, 1.0)


@dataclass(frozen=True)
class AnchorState:
    anchor_position: Vector3
    anchor_rotation: Quaternion
    old_anchor_position: Vector3
    old_anchor_rotation: Quaternion
    anchor_component_local_position: Vector3  # Single, not Double world position.


@dataclass(frozen=True)
class AnchorFrameResult:
    state: FrameInertiaState
    team: FrameInertiaTeam
    anchor: AnchorState
    anchor_reinitialized: bool
    anchor_applied: bool


def advance_frame_anchor(
    state: FrameInertiaState,
    team: FrameInertiaTeam,
    anchor: AnchorState,
    anchor_inertia: float,
) -> AnchorFrameResult:
    """AnchorReset/reset initialization → Anchor contribution → working transform.

    flag10000/4 initialization is independent of Anchor8000. Contribution is not
    suppressed on reset, and oldAnchor fields are not advanced here without reset.
    Next call is prepare_frame_inertia then advance_frame_inertia using this result.
    """
    flag = _integer(team.flag, 2**64 - 1)
    reinitialized = bool(flag & (0x10000 | 4))
    applied = bool(flag & 0x8000)
    shift, rotation = _ZERO, _Q
    work = state.working_old_component_position
    work_q = state.working_old_component_rotation
    if reinitialized:
        position = _vector(anchor.anchor_position)
        q = _quaternion(anchor.anchor_rotation)
        matrix = build_double_trs(position, q, _S)
        local = _float3(
            transform_double_point(
                inverse_double_matrix(matrix), state.component_world_position
            )
        )
        anchor = replace(
            anchor,
            old_anchor_position=position,
            old_anchor_rotation=q,
            anchor_component_local_position=local,
        )
    if applied:
        inertia = _single(anchor_inertia)
        if not 0 <= inertia <= 1:
            raise ValueError("Adapter anchor inertia must be in [0,1]")
        matrix = build_double_trs(anchor.anchor_position, anchor.anchor_rotation, _S)
        target = transform_double_point(
            matrix, _float3(anchor.anchor_component_local_position)
        )
        delta = _float3(_sub(target, _vector(work)))
        delta_q = multiply_quaternions(
            anchor.anchor_rotation, quaternion_inverse(anchor.old_anchor_rotation)
        )
        weight = _single(1 - inertia)
        shift = _lerp(_ZERO, delta, weight)
        rotation = interpolate_rotation(_Q, delta_q, weight)
        work = _add(_vector(work), shift)
        work_q = multiply_quaternions(rotation, work_q)
        flag |= 0x400
    return AnchorFrameResult(
        replace(
            state,
            working_old_component_position=work,
            working_old_component_rotation=work_q,
            anchor_shift_vector=shift,
            anchor_shift_rotation=rotation,
        ),
        replace(team, flag=flag),
        anchor,
        reinitialized,
        applied,
    )
