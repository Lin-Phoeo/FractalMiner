"""Finite frame reset completion and PostTeam history lifecycle fragments.

Static sources: reset fields5a36258..5a36313, weights5a36c13..5a36c42, and
PostTeamUpdateKernel$BurstManaged369588/5a2c1f0..5a2c9d1. Not native publication,
job completion, array ownership, a full frame solver or Unity integration.
Call post only AFTER all substeps/writeback/collider post. Do not substitute
PostTeam history copies for frame-center or substep history updates.
Finite/singular rejection is adapter policy; Single/Double math is not a bit oracle.
"""

from dataclasses import dataclass, replace

from official_physics_angle_baseline import _integer
from official_physics_angle_cache import _quaternion
from official_physics_angles import Quaternion, _float3
from official_physics_constraints import Vector3, _single, _vector
from official_physics_frame_anchor import AnchorState
from official_physics_frame_inertia import FrameInertiaState, FrameInertiaTeam
from official_physics_frame_prelude import (
    FramePreludeResult,
    FramePreludeSettings,
    prepare_frame_inertia,
)
from official_physics_matrix import (
    build_double_trs,
    inverse_double_matrix,
    transform_double_point,
)
from official_physics_scale_remap import ComponentScaleCache
from official_physics_team_tail import TeamDynamicsState

_UNIT: Vector3 = (1.0, 1.0, 1.0)
_ZERO: Vector3 = (0.0, 0.0, 0.0)
_CLEAR_POST_FLAGS = 0x406AC
_EPSILON = _single(1e-6)


@dataclass(frozen=True)
class FrameHistoryState:
    inertia: FrameInertiaState
    component_cache: ComponentScaleCache
    anchor: AnchorState
    old_world_position: Vector3  # Center @408, separate from now @368/oldFrame @312.
    old_world_rotation: Quaternion  # Center @432; not oldComponent @176.


@dataclass(frozen=True)
class FrameHistoryPreludeResult:
    history: FrameHistoryState
    prelude: FramePreludeResult  # Original fragment flags/diagnostics, same inertia.


@dataclass(frozen=True)
class FramePostTeam:
    flag: int
    time: float
    old_time: float
    now_update_time: float
    old_update_time: float
    frame_update_time: float
    frame_old_time: float
    force_mode: int
    impact_force: Vector3
    skip_count: int


@dataclass(frozen=True)
class FrameHistoryPostResult:
    history: FrameHistoryState
    team: FramePostTeam
    writes: tuple[str, ...]  # Selected value fragments, NOT native array writes.
    frame_history_advanced: bool
    time_wrapped: bool


def prepare_frame_history(
    history: FrameHistoryState,
    team: FrameInertiaTeam,
    settings: FramePreludeSettings,
    *,
    component_world_scale: Vector3,
) -> FrameHistoryPreludeResult:
    """Existing prelude plus its missing oldComponent and oldWorld reset fields.

    Call AFTER scale/target/matrices/anchor, BEFORE frame-inertia correction.
    A newly triggered teleport reset does not rerun the preceding anchor region.
    flag40000 copies frame/now/oldWorld but does not reset component q/scale.
    Does not clear smoothing, initialize weights, reset particles or publish arrays.
    """
    prelude = prepare_frame_inertia(history.inertia, team, settings)
    state = prelude.state
    flag = prelude.team.flag
    cache = history.component_cache
    if flag & 4:
        cache = replace(
            cache,
            old_component_rotation=_quaternion(state.component_world_rotation),
            old_component_scale=_float3(component_world_scale),
        )
    old_world, old_q = history.old_world_position, history.old_world_rotation
    if flag & (4 | 0x40000):
        old_world = _vector(state.step_state.frame_world_position)
        old_q = _quaternion(state.step_state.frame_world_rotation)
    return FrameHistoryPreludeResult(
        replace(
            history,
            inertia=state,
            component_cache=cache,
            old_world_position=old_world,
            old_world_rotation=old_q,
        ),
        prelude,
    )


def initialize_frame_weights(
    dynamics: TeamDynamicsState, flag: int, stabilization_time: float
) -> TeamDynamicsState:
    """5a36c13..5a36c42; AFTER inertia, before zones/frame publication/substeps.

    This is distinct from substep stabilization increments. Do not overwrite the
    velocity-weight snapshot that frame inertia has already consumed.
    """
    flag = _integer(flag, 2**64 - 1)
    if not flag & (4 | 8):
        return dynamics
    value = 0.0 if _single(stabilization_time) > _EPSILON else 1.0
    return replace(dynamics, velocity_weight=value, blend_weight=value)


def finish_frame_history(
    history: FrameHistoryState, team: FramePostTeam, *, component_world_scale: Vector3
) -> FrameHistoryPostResult:
    """IsProcess → component → update-gated frame/force → anchor → flags/clocks.

    Copies raw current component, NOT corrected working-old. Does not advance
    nowWorld or oldWorld. Post has no separate team-index-zero guard in its body;
    the caller owns range/index validity. Unselected fields are preserved.
    The original then publishes Team followed by Center; this returns values only.
    """
    flag = _integer(team.flag, 2**64 - 1)
    if not flag & 2 or flag & ((1 << 61) | 0x10 | 0x800 | 0x80000):
        return FrameHistoryPostResult(history, team, (), False, False)
    state = history.inertia
    cache = replace(
        history.component_cache,
        old_component_rotation=_quaternion(state.component_world_rotation),
        old_component_scale=_float3(component_world_scale),
    )
    state = replace(
        state, old_component_world_position=_vector(state.component_world_position)
    )
    advanced = bool(flag & 0x20)
    writes = ("component_history",)
    if advanced:
        step = state.step_state
        state = replace(
            state,
            step_state=replace(
                step,
                old_frame_world_position=_vector(step.frame_world_position),
                old_frame_world_rotation=_quaternion(step.frame_world_rotation),
                old_frame_world_scale=_float3(step.frame_world_scale),
            ),
        )
        team = replace(team, force_mode=0, impact_force=_ZERO, skip_count=0)
        writes += ("frame_history", "force_and_skip_clear")
    anchor = history.anchor
    position, rotation = (
        _vector(anchor.anchor_position),
        _quaternion(anchor.anchor_rotation),
    )
    # 5a2b95c: full Double inverse TRS (unit scale), point multiply, THEN narrow.
    local = _float3(
        transform_double_point(
            inverse_double_matrix(build_double_trs(position, rotation, _UNIT)),
            state.component_world_position,
        )
    )
    anchor = replace(
        anchor,
        old_anchor_position=position,
        old_anchor_rotation=rotation,
        anchor_component_local_position=local,
    )
    writes += ("anchor_history_and_local", "transient_flags")
    team = replace(team, flag=flag & ~_CLEAR_POST_FLAGS)
    wrapped = _single(team.time) > _single(7200)
    if wrapped:
        # Source subps includes old/now/oldUpdate/frameUpdate, plus two subss.
        team = replace(
            team,
            **{
                name: _single(_single(getattr(team, name)) - _single(3600))
                for name in (
                    "time",
                    "old_time",
                    "now_update_time",
                    "old_update_time",
                    "frame_update_time",
                    "frame_old_time",
                )
            },
        )
        writes += ("clock_wrap",)
    return FrameHistoryPostResult(
        replace(history, inertia=state, component_cache=cache, anchor=anchor),
        team,
        writes,
        advanced,
        wrapped,
    )
