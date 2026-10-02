"""Finite current/last-buffer publication reference, NOT native scheduling.

CopyDoubleBufferJob.Execute369462/0x5a1a730 copies each whole current NativeArray
to its corresponding last array, without transform flag/team gates. Copy count
is EACH source array's length; there is no quaternion math or pointer swap.
WriteTransform369425 supplies current arrays, WriteDoubleBufferTransform369408
supplies last arrays to the SAME WriteTransformJob. Its misleading field names
do not determine the supplied input's age. Actual dispatch timing is NOT ported.

Finite/shape/capacity/count rejection is adapter policy, not original exceptions.
Immutable snapshots model completed copies, not NativeArray aliases, JobHandle
dependencies, actual Transform setters, complete solver or live-game oracle.
"""

from dataclasses import dataclass
from typing import TypeVar

from official_physics_angle_baseline import _integer
from official_physics_angle_cache import _quaternion
from official_physics_angles import Quaternion, _float3
from official_physics_constraints import Vector3
from official_physics_writeback import Double3, _double3


@dataclass(frozen=True)
class TransformBufferSnapshot:
    world_positions: tuple[Double3, ...]
    world_rotations: tuple[Quaternion, ...]
    local_positions: tuple[Vector3, ...]
    local_rotations: tuple[Quaternion, ...]


def _snapshot(buffers: TransformBufferSnapshot) -> TransformBufferSnapshot:
    # Native arrays have independent lengths, including empty and destination tails.
    for array in (
        buffers.world_positions,
        buffers.world_rotations,
        buffers.local_positions,
        buffers.local_rotations,
    ):
        _integer(len(array), 65536)
    return TransformBufferSnapshot(
        tuple(_double3(p) for p in buffers.world_positions),
        tuple(_quaternion(q) for q in buffers.world_rotations),
        tuple(_float3(p) for p in buffers.local_positions),
        tuple(_quaternion(q) for q in buffers.local_rotations),
    )


T = TypeVar("T")


def _copy(source: tuple[T, ...], target: tuple[T, ...]) -> tuple[T, ...]:
    if len(target) < len(source):
        raise ValueError("Adapter requires destination capacity for full source copy")
    return source + target[len(source) :]


def copy_double_buffer(
    current: TransformBufferSnapshot, last: TransformBufferSnapshot
) -> TransformBufferSnapshot:
    """Completed finite copy: current to last, all four arrays, destination tails kept.

    Unselected/disabled slots are also copied. No flags, team, interpolation,
    normalization or mode-dependent filtering occurs in this copy Job. Inputs
    remain immutable; rejection has no partial writes (adapter-only behavior).
    """
    source, destination = _snapshot(current), _snapshot(last)
    return TransformBufferSnapshot(
        _copy(source.world_positions, destination.world_positions),
        _copy(source.world_rotations, destination.world_rotations),
        _copy(source.local_positions, destination.local_positions),
        _copy(source.local_rotations, destination.local_rotations),
    )


def select_transform_write_buffers(
    current: TransformBufferSnapshot,
    last: TransformBufferSnapshot,
    *,
    cross_frame: bool,
) -> TransformBufferSnapshot:
    """Snapshot of arrays supplied by the selected original manager entry.

    Ordinary WriteTransform -> current; WriteDoubleBufferTransform -> last.
    Caller supplies the independently established mode, never inferred from
    frame count or Job field names. No automatic publication or solver/Unity
    dispatch; nonselected arrays are not read. Native reference aliases are not
    modelled by this finite immutable snapshot API.
    """
    if type(cross_frame) is not bool:
        raise ValueError("Adapter requires an explicit boolean cross-frame mode")
    return _snapshot(last if cross_frame else current)
