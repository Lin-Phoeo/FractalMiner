"""Finite explicit RemoveTransform writes and Animator dirty-call effects.

RemoveTransform369419/0x5a1cc48 gates manager validity and signed length>0,
then performs fourteen arena operations and ascending TransformAccess clears.
Only flag/team/access writes are represented in the detached slot capture;
other fields remain opaque inactive storage cells, NOT valid surviving poses.
Arena Remove/RemoveAndFill events are descriptions, not executed allocator,
useCount/free-list/NativeArray changes, resize, relocation or buffer release.
No implicit Animator dirty/record/handler/GCHandle cleanup or Job completion.

AddAnimatorTransform369503/0x34408a0 and MarkAnimatorTransformDirty369504/
0x5a22398 add the original Int32 Team only when caller-resolved Unity validity
is true. This consumes the existing registration call descriptions, without
confusing raw Python object identity or stored Int16 Team with native validity.
Finite ranges, type checks and private copies are adapter policy, not native
invalid-index/fault/partial-write equivalence. No Unity runtime integration.
"""

from collections.abc import Sequence
from collections.abc import Set as AbstractSet
from dataclasses import dataclass, replace
from typing import Literal

from official_physics_registration import RegisteredSlot, _bool, _int32

ArenaOperation = tuple[str, Literal["Remove", "RemoveAndFill"], int | None]
ARENA_OPERATIONS: tuple[ArenaOperation, ...] = (
    ("flagArray", "RemoveAndFill", 0),
    ("initLocalPositionArray", "Remove", None),
    ("initLocalRotationArray", "Remove", None),
    ("positionArray", "Remove", None),
    ("rotationArray", "Remove", None),
    ("lastpositionArray", "Remove", None),
    ("lastrotationArray", "Remove", None),
    ("scaleArray", "Remove", None),
    ("localPositionArray", "Remove", None),
    ("localRotationArray", "Remove", None),
    ("lastlocalPositionArray", "Remove", None),
    ("lastlocalRotationArray", "Remove", None),
    ("localToWorldMatrixArray", "Remove", None),
    ("teamIdArray", "RemoveAndFill", 0),
)


@dataclass(frozen=True)
class TransformRangeRelease:
    slots: tuple[RegisteredSlot, ...]
    start: int
    length: int
    arena_operations: tuple[ArenaOperation, ...]
    transform_access_clears: tuple[int, ...]
    native_allocator_applied: Literal[False] = False


def release_registered_transform_range(
    *,
    manager_valid: bool,
    start: int,
    length: int,
    slots: Sequence[RegisteredSlot] | None,
) -> TransformRangeRelease | None:
    """Patch explicit inactive-cell fields and describe remaining arena calls.

    None skips inactive/nonpositive routes without reading unused inputs. This
    finite API requires a nonnegative owned window; the native source only gates
    validity/length. No claim that freed native pose storage preserves bytes.
    """
    if not _bool(manager_valid) or _int32(length) <= 0:
        return None
    if slots is None:
        raise ValueError("Adapter requires selected registered slot capture")
    start = _int32(start)
    if start < 0 or start + length > len(slots):
        raise ValueError("Adapter requires owned registered slot window")
    result = list(slots)
    indices = tuple(range(start, start + length))
    for index in indices:
        result[index] = replace(result[index], flag=0, team_id=0, transform_handle=None)
    return TransformRangeRelease(
        tuple(result), start, length, ARENA_OPERATIONS, indices
    )


def apply_animator_transform_dirty(
    *,
    method: str,
    team_id: int,
    transform_valid: bool,
    dirty_teams: AbstractSet[int],
) -> frozenset[int]:
    """Consume one Add/Mark call with explicit Unity-null/destroyed outcome."""
    if method not in ("AddAnimatorTransform", "MarkAnimatorTransformDirty"):
        raise ValueError("Adapter requires a supported Animator dirty method")
    valid = _bool(transform_valid)
    dirty = frozenset(_int32(value) for value in dirty_teams)
    return dirty | {_int32(team_id)} if valid else dirty
