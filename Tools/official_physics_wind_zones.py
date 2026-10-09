"""Finite frame wind selection and frameLocalPosition references.

Wind managed369646/5a36ff4 and non-Burst fallback5a2a620; frame local region
5a36bb8..5a36c13. Consumes caller-resolved WindData slots and frame target/inverse.
No WindManager update, transform sampling, NativeArray/FixedList publication,
Job/Burst execution or Unity integration. Tables use native array-slot IDs.
Single/Double order retained; Python sqrt is not a native bit oracle. Finite,
range and degenerate rejection are ADAPTER restrictions, not native behavior.
"""

import math
from collections.abc import Sequence
from dataclasses import dataclass
from typing import cast

from official_physics_angle_baseline import _integer
from official_physics_angles import _float3
from official_physics_center_step import CenterStepState
from official_physics_constraints import Vector3, _single, _sub, evaluate_curve
from official_physics_matrix import Matrix4, _matrix, transform_double_point
from official_physics_particle_step import (
    _single_dot,
    _single_normalize,
    _single_scale,
)
from official_physics_proxy_baseline import _int32
from official_physics_scale_remap import FrameScaleMatrixResult
from official_physics_team_tail import TeamWindState, WindInfo

_INFLUENCE_EPSILON = _single(1e-8)
_MAIN_EPSILON = _RADIAL_EPSILON = _single(1e-6)
_MAX_VOLUME = _single(3.4028234663852886e38)


@dataclass(frozen=True)
class WindZoneData:
    flag: int  # WindData BitField32: valid1, enabled2, addition4.
    mode: int  # Int32: sphere1, box2, radial sphere10; other values unbounded.
    size: Vector3
    main: float
    turbulence: float  # Downstream particle lookup, not read by selection.
    zone_volume: float
    world_wind_direction: Vector3
    world_position: Vector3  # Source field is misspelled worldPositin, Single3.
    world_to_local_matrix: Matrix4  # Single4 columns, widened to Double4.
    attenuation: Sequence[float]  # Sixteen Single samples in flat memory order.


@dataclass(frozen=True)
class WindZoneResult:
    state: TeamWindState
    addition_candidates: int  # Trace only: counts candidates even if main<=epsilon.
    winner_id: int  # Trace only: may identify a weak candidate absent from zones.


def produce_frame_local_position(
    step: CenterStepState, matrices: FrameScaleMatrixResult
) -> Vector3:
    """5a36bb8: frame inverse * frame target in Double, THEN narrow to Single3.

    Retain inverse/multiply rounding residual; do not simplify this to zero.
    Uses the inverse produced before reset/inertia, not a rebuilt transform.
    Returns CenterData.frameLocalPosition@300 as a value, without publishing it.
    """
    return _float3(
        transform_double_point(matrices.frame_inverse, step.frame_world_position)
    )


def _local_point(zone: WindZoneData, world_point: Vector3) -> Vector3:
    # 5a2ddb8 ->5a2dd04 ->4a6eb10 widens each original Single4 column.
    matrix = _matrix(zone.world_to_local_matrix)
    widened = cast(Matrix4, tuple(tuple(_single(x) for x in col) for col in matrix))
    return _float3(transform_double_point(widened, world_point))


def _append_zone(
    selected: list[WindInfo], candidate: WindInfo, previous: TeamWindState
) -> None:
    """5a7782c: main gate, FIRST matching previous clock, unconditional append.

    Name AddOrReplaceWindZone does not mean replace a duplicate in NEW list.
    Native FixedList capacity/array ownership remain caller preconditions.
    """
    if candidate.main <= _MAIN_EPSILON:
        return
    time = -10000.0
    for old in previous.zones:
        if old.wind_id == candidate.wind_id:
            time = _single(old.time)
            break
    selected.append(
        WindInfo(candidate.wind_id, time, candidate.main, candidate.direction)
    )


def _remove_zone_swap_back(selected: list[WindInfo], wind_id: int) -> None:
    # 5a77a78 ->7669404 ->766a0b8: first matching slot, last item fills its hole.
    for index, info in enumerate(selected):
        if info.wind_id == wind_id:
            selected[index] = selected[-1]
            selected.pop()
            return


def select_wind_zones(
    previous: TeamWindState,
    wind_data: Sequence[WindZoneData],
    *,
    wind_count: int,
    influence: float,
    frame_world_position: Vector3,
) -> WindZoneResult:
    """Fresh zones, ascending WindData slots, at most three addition candidates.

    count<=0 skips influence; disabled influence clears zones at FRAME selection,
    unlike the substep UpdateWind gate. Moving wind is copied unchanged here.
    Non-addition candidates with smaller/equal volume remove the old winner using
    swap-back before the main gate; weak winners still constrain later volumes.
    IDs/clocks refer to previous TeamWindData; no implicit wind-time advancement.
    """
    count = _int32(wind_count)
    selected: list[WindInfo] = []
    additions, winner = 0, -1
    if count <= 0 or _single(influence) <= _INFLUENCE_EPSILON:
        return WindZoneResult(TeamWindState((), previous.moving), additions, winner)
    if count > len(wind_data):
        raise ValueError("Adapter wind count exceeds supplied original table")
    volume_limit = _MAX_VOLUME
    for wind_id in range(count):
        zone = wind_data[wind_id]
        flag = _integer(zone.flag, 2**32 - 1)
        if not flag & 1 or not flag & 2:
            continue
        addition = bool(flag & 4)
        if addition and additions >= 3:
            continue
        local = _local_point(zone, frame_world_position)
        distance = _single(math.sqrt(_single_dot(local, local)))
        mode = _int32(zone.mode)
        if mode in (1, 10):
            radius = _single(zone.size[0])
            if distance > radius:
                continue
        elif mode == 2:
            size = _float3(zone.size)
            doubled = _single_scale(cast(Vector3, tuple(abs(x) for x in local)), 2.0)
            if any(x > bound for x, bound in zip(doubled, size, strict=True)):
                continue
        volume = volume_limit
        if not addition:
            volume = _single(zone.zone_volume)
            if volume > volume_limit:
                continue
        if mode == 10:
            if distance <= _RADIAL_EPSILON:
                continue
            # 40c6230 widens Single worldPositin, then59d77a4 subtracts in Double.
            direction = _single_normalize(
                _float3(_sub(frame_world_position, _float3(zone.world_position)))
            )
        else:
            direction = _float3(zone.world_wind_direction)
        main = _single(zone.main)
        if mode == 10:
            time = min(1.0, max(0.0, _single(distance / _single(zone.size[0]))))
            attenuation = min(1.0, max(0.0, evaluate_curve(zone.attenuation, time)))
            main = _single(attenuation * main)
        candidate = WindInfo(wind_id, -10000.0, main, direction)
        if not addition:
            _remove_zone_swap_back(selected, winner)
            _append_zone(selected, candidate, previous)
            volume_limit, winner = volume, wind_id
        else:
            _append_zone(selected, candidate, previous)
            additions += 1
    return WindZoneResult(
        TeamWindState(tuple(selected), previous.moving), additions, winner
    )
