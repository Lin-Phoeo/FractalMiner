"""Offline reference for recovered TimeManager equations, NOT a cloth solver.

See docs/implementation/official-physics-clock-20261002. Arithmetic rounds at
Single operation boundaries; Python pow is a mathematical reference, NOT a
bit-identical replacement for the game's CRT float-power implementation.
The finite/int32 validation guards are adaptation policy, not native claims.
Nothing here owns a Unity clock, transforms, jobs or rendering state.
"""

import math
import struct
from dataclasses import dataclass


def _int32(value: int) -> int:
    if type(value) is not int or not -(2**31) <= value < 2**31:
        raise ValueError("Expected a signed Int32, not bool/float/out-of-range input")
    return value


def _single(value: float) -> float:
    return struct.unpack("<f", struct.pack("<f", value))[0]


@dataclass(frozen=True)
class FrameSettings:
    frequency: int
    max_steps: int
    global_time_scale: float
    simulation_delta_time: float
    max_delta_time: float
    simulation_power: tuple[float, float, float, float]


def frame_settings(
    frequency: int, max_steps: int, global_time_scale: float
) -> FrameSettings:
    """Derived settings only; no elapsed-time accumulation or step-count claim."""
    frequency = min(150, max(30, _int32(frequency)))
    max_steps = min(5, max(1, _int32(max_steps)))
    if (
        type(global_time_scale) not in (int, float)
        or not math.isfinite(global_time_scale)
        or abs(global_time_scale) > 3.4028234663852886e38
    ):
        raise ValueError("Adapter requires finite representable Single scale")
    scale = _single(global_time_scale)
    if scale < 0:
        scale = 0.0
    elif scale > 1:
        scale = 1.0
    step = _single(1.0 / frequency)
    ratio = _single(90.0 / frequency)
    power = (
        ratio,
        _single(math.pow(ratio, 0.5)) if ratio > 1 else ratio,
        _single(math.pow(ratio, _single(0.3))) if ratio > 1 else ratio,
        _single(math.pow(ratio, _single(1.8))),
    )
    return FrameSettings(
        frequency, max_steps, scale, step, _single(max_steps * step), power
    )


def fixed_callback_count(previous: int, *, reset: bool = False) -> int:
    """Recovered counter write semantics, not the number of simulation substeps."""
    previous = _int32(previous)
    if type(reset) is not bool:
        raise ValueError("Adapter reset policy must be bool")
    return 0 if reset else ((previous + 1 + 2**31) % 2**32) - 2**31
