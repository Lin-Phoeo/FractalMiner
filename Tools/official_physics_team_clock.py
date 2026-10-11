"""Finite Team frame-clock fragment of ordinary PostJob369639/0x5a2f048.

0x5a2f63e..0x5a2f7eb: five-clock reset, delta/scale, capped steps and discarded
time, animation-pose request, zero-scale backlog, LOD fade, Running bit. Caller
supplies the mode resolved at that source site and flags AFTER distance culling.
Not full AlwaysTeamUpdate: pre-job dictionaries/sync links, anchor/culling
production, allocation, native publication and actual Unity clocks are missing.
This immutable fragment does not schedule jobs or implicitly clear reset flags.
Single operation boundaries are retained. Finite/nonnegative time-scale inputs,
Int32 conversion refusal and strict bool/mode/count checks are adapter policy.
"""

import math
from dataclasses import dataclass, replace

from official_physics_angle_baseline import _integer
from official_physics_clock import _int32
from official_physics_constraints import _positive, _single

_EXCLUDED = (1 << 61) | 0x10 | 0x800 | 0x80000
_EPSILON = _single(1e-4)


@dataclass(frozen=True)
class TeamClockState:
    flag: int
    update_mode: int
    frame_delta_time: float
    time: float
    old_time: float
    now_update_time: float
    old_update_time: float
    frame_update_time: float
    frame_old_time: float
    time_scale: float
    update_count: int
    skip_count: int
    reset_simulation_to_animation_pose: bool
    cloth_lod_fade_weight: float
    cloth_lod_fade_time: float
    now_time_scale: float = 1.0


@dataclass(frozen=True)
class TeamFrameTimes:
    delta_time: float
    fixed_delta_time: float
    unscaled_delta_time: float
    global_time_scale: float
    simulation_delta_time: float
    max_steps: int


@dataclass(frozen=True)
class TeamFrameClockResult:
    team: TeamClockState
    processed: bool
    raw_update_count: int | None
    writes: tuple[str, ...]  # Fragment values, NOT NativeArray writes.


def advance_team_frame_clock(
    team: TeamClockState,
    frame: TeamFrameTimes,
    *,
    team_id: int,
    resolved_update_mode: int,
) -> TeamFrameClockResult:
    """Return only the clock/fade slice after upstream mode/culling resolution.

    Mode0/1/2 select normal/fixed/unscaled supplied frame delta. Mode2 bypasses
    GLOBAL time scale, NOT Team time scale. No floor/max(0) for step quotient:
    native cvttss2si truncates toward zero; representable negative counts remain.
    Over-cap steps subtract time, rather than carrying arbitrary backlog forward.
    OldTime captures pre-increment time, whereas frame history only advances when
    the final count is positive. Flag8 resets five clocks; flag4 alone does not.
    Bit60 controls LOD fade, which is NOT the downstream dynamics blend weight.

    Skipped clock fragments preserve this object; earlier anchor/culling fields
    may still have changed in the original full method. Team0 is outside its
    loop. First-reset/enabling and explicit pause/seek request generation remain
    caller responsibilities. Never interpret this API as full lifecycle recovery.
    """
    team_id = _integer(team_id, 2**31 - 1)
    if team_id == 0:
        return TeamFrameClockResult(team, False, None, ())
    flag = _integer(team.flag, 2**64 - 1)
    if not flag & 2 or flag & _EXCLUDED:
        return TeamFrameClockResult(team, False, None, ())
    mode = _integer(resolved_update_mode, 2)
    if type(team.reset_simulation_to_animation_pose) is not bool:
        raise ValueError("Adapter animation-pose request must be an actual bool")
    step = _positive(frame.simulation_delta_time)
    maximum = _int32(frame.max_steps)
    if maximum <= 0:
        raise ValueError("Adapter requires a positive maximum step count")
    dt = _single(
        (frame.delta_time, frame.fixed_delta_time, frame.unscaled_delta_time)[mode]
    )
    scale = _single(team.time_scale)
    global_scale = 1.0 if mode == 2 else _single(frame.global_time_scale)
    if scale < 0 or global_scale < 0 or dt < 0:
        raise ValueError("Adapter requires nonnegative selected delta/time scales")
    now_scale = _single(scale * global_scale)
    # The source has an additional suspend-bit zeroing site. The earlier
    # suspend gate prevents this slice on the stable-flag path represented here.
    delta = _single(now_scale * dt)
    if flag & 8:
        previous = now = old_update = frame_update = frame_old = 0.0
    else:
        previous, now, old_update, frame_update, frame_old = (
            _single(team.time),
            _single(team.now_update_time),
            _single(team.old_update_time),
            _single(team.frame_update_time),
            _single(team.frame_old_time),
        )
    time = _single(previous + delta)
    quotient = _single(_single(time - now) / step)
    raw = math.trunc(quotient)
    _int32(raw)  # No emulation of native overflow/NaN sentinel or unsafe faults.
    count = min(raw, maximum)
    skipped = raw - count
    if team.reset_simulation_to_animation_pose:
        now, count, skipped = time, 0, 0
        flag |= 4
    if skipped > 0:
        time = _single(time - _single(_single(skipped) * step))
    if count > 0:
        if delta == 0:
            now = _single(_single(time - step) + _EPSILON)
            count = skipped = 0
        if count > 0:
            frame_old, frame_update, old_update = frame_update, time, now
    fade_time = _single(team.cloth_lod_fade_time)
    if fade_time <= 0:
        fade = 0.0 if flag & (1 << 60) else 1.0
    else:
        amount = _single(delta / fade_time)
        previous_fade = _single(team.cloth_lod_fade_weight)
        fade = _single(
            previous_fade - amount if flag & (1 << 60) else previous_fade + amount
        )
        fade = min(1.0, max(0.0, fade))
    flag = (flag & ~0x20) | (0x20 if count > 0 else 0)
    result = replace(
        team,
        flag=flag,
        update_mode=mode,
        frame_delta_time=dt,
        time=time,
        old_time=previous,
        now_update_time=now,
        old_update_time=old_update,
        frame_update_time=frame_update,
        frame_old_time=frame_old,
        now_time_scale=now_scale,
        update_count=count,
        skip_count=skipped,
        cloth_lod_fade_weight=fade,
    )
    return TeamFrameClockResult(
        result, True, raw, ("clock_fragment", "lod_fade", "running_flag")
    )
