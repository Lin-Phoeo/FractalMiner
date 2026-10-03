"""Finite offline particle Wind/WindForceBlend, not a Unity/native wind solver.

Static sources: managed370476/0x5a66520 and actual non-Burst fallback0x5a6b018;
WindForceBlend370477/0x5a66188; classic cnoise2 at0xa1f5870. Caller supplies
already selected zones, resolved vertexRootIndices[vindex], friction[pindex]
and windData[windId].turbulence. No zone selection, frame-center generation,
NativeArray/FixedList publication or certification of dynamic Burst targets.
Single operation grouping preserved; Python CRT transcendental approximation
is NOT a game/Burst bit oracle. Finite/index rejection is adapter safety only.
"""

import math
from collections.abc import Mapping
from dataclasses import dataclass

from official_physics_angle_baseline import _integer
from official_physics_angle_cache import multiply_quaternions, rotate_single
from official_physics_angles import Quaternion, _float3
from official_physics_constraints import Vector3, _single
from official_physics_particle_step import _single_add, _single_dot, _single_scale
from official_physics_team_tail import TeamWindState, WindInfo

Vector2 = tuple[float, float]


@dataclass(frozen=True)
class WindForceSettings:
    influence: float
    turbulence: float
    blend: float
    synchronization: float
    depth_weight: float
    moving_wind: float


@dataclass(frozen=True)
class ParticleWindResult:
    force: Vector3
    seed: Vector3
    zone_forces: tuple[Vector3, ...]
    moving_force: Vector3 | None  # None = branch not evaluated, not buffer clear.


def _mod289(value: float) -> float:
    # Do not replace with Python modulo, especially at negative/large coordinates.
    quotient = _single(math.floor(_single(value * _single(0.0034602077212184668))))
    return _single(value - _single(quotient * _single(289)))


def _permute(value: float) -> float:
    return _mod289(_single(_single(_single(value * 34) + 1) * value))


def _fraction(value: float) -> float:
    return _single(value - _single(math.floor(value)))


def _fade(value: float) -> float:
    cube = _single(_single(value * value) * value)
    polynomial = _single(_single(value * _single(_single(value * 6) - 15)) + 10)
    return _single(cube * polynomial)


def _lerp(a: float, b: float, t: float) -> float:
    return _single(a + _single(_single(b - a) * t))


def classic_noise2(position: Vector2) -> float:
    """Native classic Perlin 2D (not simplex/random), scalar lane transcription.

    Own finite arithmetic port of observed helpers, with independent managed
    Unity.Mathematics fixture checks. Original algorithm reference: Unity's
    Noise/classicnoise2D.cs (Stefan Gustavson classic noise). No library source
    file is vendored here. No NaN/Inf/Burst fast-math equivalence is asserted.
    """
    if len(position) != 2:
        raise ValueError("Adapter requires two Single noise coordinates")
    x, y = _single(position[0]), _single(position[1])
    floor_x, floor_y = _single(math.floor(x)), _single(math.floor(y))
    fraction_x, fraction_y = _fraction(x), _fraction(y)
    values = []
    for dx, dy in ((0, 0), (1, 0), (0, 1), (1, 1)):
        ix, iy = _mod289(_single(floor_x + dx)), _mod289(_single(floor_y + dy))
        index = _permute(_single(_permute(ix) + iy))
        gx = _single(
            _single(_fraction(_single(index * _single(0.024390242993831635))) * 2) - 1
        )
        gy = _single(abs(gx) - 0.5)
        gx = _single(gx - _single(math.floor(_single(gx + 0.5))))
        squared = _single(_single(gy * gy) + _single(gx * gx))
        norm = _single(
            _single(1.7928428649902344) - _single(_single(0.8537347316741943) * squared)
        )
        gx, gy = _single(gx * norm), _single(gy * norm)
        fx, fy = _single(fraction_x - dx), _single(fraction_y - dy)
        values.append(_single(_single(gy * fy) + _single(gx * fx)))
    fade_x, fade_y = _fade(fraction_x), _fade(fraction_y)
    row0, row1 = (
        _lerp(values[0], values[1], fade_x),
        _lerp(values[2], values[3], fade_x),
    )
    return _single(_lerp(row0, row1, fade_y) * _single(2.299999952316284))


def euler_zxy(angles: Vector3) -> Quaternion:
    """Selected order4 path0x2de4f00, radians; not the entire Euler dispatcher."""
    x, y, z = _float3(angles)
    sx, sy, sz = (_single(math.sin(_single(v * 0.5))) for v in (x, y, z))
    cx, cy, cz = (_single(math.cos(_single(v * 0.5))) for v in (x, y, z))
    first = (sx, sy, sz, cx)
    first_b, first_c = (cy, cx, cx, cy), (cz, cz, cy, cz)
    second, second_b = (cx, cy, cz, sx), (sy, sx, sx, sy)
    signs, second_c = (1, -1, -1, 1), (sz, sz, sy, sz)
    out = []
    for i in range(4):
        a = _single(_single(first[i] * first_b[i]) * first_c[i])
        b = _single(_single(_single(second[i] * second_b[i]) * signs[i]) * second_c[i])
        out.append(_single(a + b))
    return (out[0], out[1], out[2], out[3])


def axis_quaternion(direction: Vector3) -> Quaternion:
    """AxisToEuler0x5a592d4 → EulerZXY; no normalize/LookRotation substitution."""
    x, y, z = _float3(direction)
    horizontal = (x, _single(y - y), z)
    length = _single(math.sqrt(_single_dot(horizontal, horizontal)))
    pitch = _single(math.atan2(-y, length))
    yaw = _single(math.atan2(x, z))
    return euler_zxy((pitch, yaw, 0))


def wind_force_blend(
    info: WindInfo,
    settings: WindForceSettings,
    *,
    wind_position: Vector3,
    turbulence_ratio: float,
) -> Vector3:
    """One already resolved zone/moving wind; main<.01 returns before inputs.

    Blend is not clamped. Per-zone ratio*turbulence changes direction AND the
    intensity reduction. Quaternion composition is axis*perturbation, not the
    reverse. Negative resulting amplitude is preserved, not repaired to zero.
    """
    main = _single(info.main)
    if main < _single(0.01):
        return (0.0, 0.0, 0.0)
    position = _float3(wind_position)
    time = _single(info.time)
    periodic = tuple(
        _single(math.sin(_single(v + _single(time * 10)))) for v in position[:2]
    )
    sample = tuple(
        _single(v + _single(time * _single(2.313199996948242))) for v in position[:2]
    )
    noise = (
        classic_noise2((sample[0], sample[1])),
        classic_noise2((sample[1], sample[0])),
    )
    blend = _single(settings.blend)
    mixed = tuple(
        _lerp(periodic[i], _single(noise[i] * _single(2.3)), blend) for i in range(2)
    )
    turbulence = _single(_single(turbulence_ratio) * _single(settings.turbulence))
    angle = tuple(
        _single(_single(v * 45) * _single(0.01745329238474369)) for v in mixed
    )
    pitch = _single(angle[0] * turbulence)
    yaw = _single(
        _single(angle[1] * _single(_single(blend * _single(0.4)) + _single(0.1)))
        * turbulence
    )
    perturbation = euler_zxy((pitch, yaw, 0))
    rotation = multiply_quaternions(axis_quaternion(info.direction), perturbation)
    direction = rotate_single(rotation, (0, 0, 1))
    gate = min(1.0, max(0.0, _single(1 - _single(main / _single(7.5)))))
    gate = _single(gate * turbulence)
    intensity = _single(_single(mixed[0] - (-1)) * 0.5)
    reduction = _single(_single(gate * intensity) * main)
    return _single_scale(direction, _single(main - reduction))


def particle_wind_seed(
    *, team_id: int, root_index: int, synchronization: float
) -> Vector3:
    """Seed uses vertexRootIndices[vindex], not global particle slot pindex.

    teamId+1 is native Int32 addition, including the finite boundary wrap.
    rootIndex is signed Int32. Resolved adapter doesn't emulate unsafe indexing.
    """
    team = _integer(team_id, 2147483647)
    if type(root_index) is not int or not -2147483648 <= root_index <= 2147483647:
        raise ValueError("Adapter requires a signed Int32 root index")
    incremented = team + 1 if team < 2147483647 else -2147483648
    root = _single(_single(root_index) * _single(0.002396299969404936))
    root = _single(_single(1 - _single(synchronization)) * root)
    root = _single(root * 100)
    seed = _single(root + _single(_single(incremented) * _single(4.1923065185546875)))
    return (seed, seed, seed)


def particle_wind(
    state: TeamWindState,
    settings: WindForceSettings,
    *,
    team_id: int,
    root_index: int,
    depth: float,
    friction: float,
    zone_turbulence: Mapping[int, float],
) -> ParticleWindResult:
    """Resolved source-order list → summed forces → depth/friction/influence.

    friction is source frictionArray[pindex], not vertexRootIndices slot or
    newly computed End friction. No influence early-out, IsValid/main filter,
    force average, weight clamp or default missing zone value is introduced.
    Actual zone capacity, IDs and array ownership remain upstream requirements.
    """
    seed = particle_wind_seed(
        team_id=team_id, root_index=root_index, synchronization=settings.synchronization
    )
    total: Vector3 = (0.0, 0.0, 0.0)
    zones = []
    for info in state.zones:
        if info.wind_id not in zone_turbulence:
            raise ValueError(
                "Adapter requires resolved zone turbulence for every selected wind ID"
            )
        force = wind_force_blend(
            info,
            settings,
            wind_position=seed,
            turbulence_ratio=zone_turbulence[info.wind_id],
        )
        zones.append(force)
        total = _single_add(total, force)
    moving = None
    if _single(settings.moving_wind) > _single(0.01):
        moving = wind_force_blend(
            state.moving, settings, wind_position=seed, turbulence_ratio=1
        )
        total = _single_add(total, moving)
    d = _single(depth)
    depth_factor = _single(
        _single(_single(_single(d * d) - 1) * _single(settings.depth_weight)) + 1
    )
    mobility = _single(_single(1 - _single(friction)) * _single(settings.influence))
    force = _single_scale(total, _single(depth_factor * mobility))
    return ParticleWindResult(force, seed, tuple(zones), moving)
