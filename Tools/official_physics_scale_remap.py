"""Finite scale regions of kernel369644, not complete frame-center production.

5a34dd7..5a35365 updates sign caches and selected old-component/anchor/velocity
fields. After caller-produced frameWorld, 5a357a1..5a35a8d builds frame inverse
and conditionally negativeScaleMatrix from OLD FRAME fields (312/336/352).
Sampling, fixed-point center reduction, array publication and tail are pending.
Python Double/Single math is not a native bit oracle. Finite values and singular
inverse rejection are ADAPTER restrictions, not native NaN/Inf policy.
"""

from collections.abc import Sequence
from dataclasses import dataclass, replace
from typing import cast

from official_physics_angle_baseline import _integer
from official_physics_angle_cache import _quaternion
from official_physics_angles import Quaternion, _float3
from official_physics_center_step import CenterStepState
from official_physics_constraints import Vector3, _finite, _single, _vector
from official_physics_frame_anchor import AnchorState
from official_physics_frame_inertia import FrameInertiaState, FrameInertiaTeam
from official_physics_matrix import (
    Matrix4,
    _matrix,
    build_double_trs,
    inverse_double_matrix,
    transform_double_point,
)


@dataclass(frozen=True)
class ComponentScaleCache:
    old_component_rotation: Quaternion  # Center @176; not current/working rotation.
    old_component_scale: Vector3  # Center @192, Single.
    negative_scale_direction: Vector3  # Team @104, prior cached sign lanes.


@dataclass(frozen=True)
class ScaleSigns:
    negative_scale_sign: float  # Any negative lane => -1; NOT determinant parity.
    negative_scale_direction: Vector3
    negative_scale_change: Vector3  # Single old_sign * new_sign, NOT subtraction.
    negative_scale_triangle_sign: tuple[float, float]
    negative_scale_quaternion_value: Quaternion  # Multiplier, NOT a rotation.


@dataclass(frozen=True)
class ComponentScaleResult:
    state: FrameInertiaState
    team: FrameInertiaTeam
    anchor: AnchorState
    cache: ComponentScaleCache
    signs: ScaleSigns
    sign_changed: bool
    component_remap: Matrix4 | None  # Local temporary, NOT negativeScaleMatrix.


@dataclass(frozen=True)
class FrameScaleMatrixResult:
    frame_inverse: Matrix4  # Local for subsequent frame-center/wind consumers.
    negative_scale_matrix: Matrix4  # Center @568, updated ONLY with flag40000.
    negative_scale_matrix_updated: bool


def multiply_double_matrices(
    left: Sequence[Sequence[float]], right: Sequence[Sequence[float]]
) -> Matrix4:
    """5a2dfec: four products and three left-to-right Double adds per lane."""
    a, b = _matrix(left), _matrix(right)
    return _matrix(
        tuple(
            tuple(
                _finite(
                    ((a[0][i] * col[0] + a[1][i] * col[1]) + a[2][i] * col[2])
                    + a[3][i] * col[3]
                )
                for i in range(4)
            )
            for col in b
        )
    )


def transform_double_vector(
    matrix: Sequence[Sequence[float]], single_vector: Vector3
) -> Vector3:
    """5a2c004→5a2de5c: widen Single3, w=0, full Double4 product, extract xyz.

    Translation*0 is still added, as in the four-column source path. Caller performs
    the final Single narrowing when writing smoothingVelocity.
    """
    m = _matrix(matrix)
    x, y, z = _float3(single_vector)
    return cast(
        Vector3,
        tuple(
            _finite(((m[0][i] * x + m[1][i] * y) + m[2][i] * z) + m[3][i] * 0.0)
            for i in range(3)
        ),
    )


def prepare_component_scale_remap(
    state: FrameInertiaState,
    team: FrameInertiaTeam,
    anchor: AnchorState,
    component_world_scale: Vector3,
    cache: ComponentScaleCache,
) -> ComponentScaleResult:
    """Sign caches → conditional component remap → initial working-old transform.

    Always evaluated before anchor/prelude, including reset frames. Current component
    sample and Center @152 pivot must be from the same snapshot as the cache. This
    does not remap/reset frame histories, clear40000, advance old rotations or produce
    frameWorld. Next: caller center reduction → frame matrices → anchor → prelude.
    """
    flag = _integer(team.flag, 2**64 - 1)
    scale = _float3(component_world_scale)
    old_direction = _float3(cache.negative_scale_direction)
    direction = cast(
        Vector3, tuple(float((v > 0) - (v < 0)) for v in scale)
    )  # 59fbbec, including ±0 => +0.
    change = cast(
        Vector3, tuple(_single(a * b) for a, b in zip(old_direction, direction))
    )
    negative = any(v < 0 for v in scale)
    signs = ScaleSigns(
        -1.0 if negative else 1.0,
        direction,
        change,
        (-1.0 if scale[0] < 0 or scale[2] < 0 else 1.0, -1.0 if scale[0] < 0 else 1.0),
        cast(Quaternion, (*(-v for v in direction), 1.0))
        if negative
        else (1.0, 1.0, 1.0, 1.0),
    )
    flag = flag | 0x20000 if negative else flag & ~0x20000
    changed = old_direction != direction
    old_position = _vector(state.old_component_world_position)
    old_rotation = _quaternion(cache.old_component_rotation)
    cache = replace(cache, negative_scale_direction=direction)
    remap = None
    if changed:
        flag |= 0x40000
        current = build_double_trs(
            state.component_world_position, state.component_world_rotation, scale
        )
        old = build_double_trs(old_position, old_rotation, cache.old_component_scale)
        remap = multiply_double_matrices(current, inverse_double_matrix(old))
        old_position = transform_double_point(remap, old_position)
        anchor = replace(
            anchor,
            old_anchor_position=transform_double_point(
                remap, anchor.old_anchor_position
            ),
        )
        state = replace(
            state,
            old_component_world_position=old_position,
            smoothing_velocity=_float3(
                transform_double_vector(remap, state.smoothing_velocity)
            ),
        )
        cache = replace(cache, old_component_scale=scale)
    return ComponentScaleResult(
        replace(
            state,
            working_old_component_position=old_position,
            working_old_component_rotation=old_rotation,
        ),
        replace(team, flag=flag),
        anchor,
        cache,
        signs,
        changed,
        remap,
    )


def prepare_frame_scale_matrices(
    step_state: CenterStepState,
    component_world_scale: Vector3,
    flag: int,
    previous_negative_scale_matrix: Matrix4,
) -> FrameScaleMatrixResult:
    """Caller-resolved frame target → unconditional inverse → conditional remap.

    The CURRENT scale is the component sample, not a stale frame-scale field.
    Use before prelude overwrites oldFrame history on flag40000/reset. A preexisting
    40000 still triggers this even if this frame's direction is unchanged. Previous
    negativeScaleMatrix is retained on the no-update branch, not replaced by inverse.
    """
    flag = _integer(flag, 2**64 - 1)
    current = build_double_trs(
        step_state.frame_world_position,
        step_state.frame_world_rotation,
        component_world_scale,
    )
    frame_inverse = inverse_double_matrix(current)
    updated = bool(flag & 0x40000)
    negative_matrix = previous_negative_scale_matrix
    if updated:
        old = build_double_trs(
            step_state.old_frame_world_position,
            step_state.old_frame_world_rotation,
            step_state.old_frame_world_scale,
        )
        negative_matrix = multiply_double_matrices(current, inverse_double_matrix(old))
    return FrameScaleMatrixResult(frame_inverse, negative_matrix, updated)
