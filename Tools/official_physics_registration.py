"""Finite manager Set/Copy/slot-Enable field references, NOT native registry.

Source369417/0x343bbf0 separately samples ELEVEN getters. Init/current/last
are not one snapshot copied three times; re-registration replaces init with its
actual getter values, not automatically a mesh bind pose. Scale is localScale
here, different from ReadTransform's inverse-world-rotation signed diagonal.

Set/Copy do NOT write localToWorldMatrixArray. Copy does NOT call TeamManager.
Null/destroyed Set calls MarkAnimatorTransformDirty before clearing flag/access/
team only; successful Set calls AddAnimatorTransform after its buffer writes.
These are CALL DESCRIPTIONS, not executed map changes or a proven unlink.

No Add allocation/free list, bulk registration, Expand, Remove allocator effects,
Animator job, hierarchy getters/setters, writer timing or Unity integration.
Caller supplies valid pre-existing typed slots, opaque resolved handles and
separately captured getter samples; no conversion of asset PPtr to runtime IDs.
Finite/range/bool/missing-sample rejection is adapter policy, not native errors.
Results are atomic private values, not native partial writes on exceptions.
"""

from dataclasses import dataclass, replace

from official_physics_angle_baseline import _integer
from official_physics_angle_cache import _quaternion
from official_physics_angles import Quaternion, _float3
from official_physics_constraints import Vector3
from official_physics_read_restore import Matrix
from official_physics_writeback import Double3, _double3


@dataclass(frozen=True)
class RegistrationCapture:
    """Eleven ordered getter results; positions/scales are Single3, q Single4.

    Repeated getters can differ. A single stable pose is an extra caller
    precondition, not a property established by the native registration method.
    """

    initial_local_position: Vector3
    initial_local_rotation: Quaternion
    world_position: Vector3
    world_rotation: Quaternion
    last_world_position: Vector3
    last_world_rotation: Quaternion
    local_scale: Vector3
    local_position: Vector3
    local_rotation: Quaternion
    last_local_position: Vector3
    last_local_rotation: Quaternion


@dataclass(frozen=True)
class RegisteredSlot:
    flag: int  # Byte.
    initial_local_position: Vector3
    initial_local_rotation: Quaternion
    world_position: Double3
    world_rotation: Quaternion
    last_world_position: Double3
    last_world_rotation: Quaternion
    scale: Vector3
    local_position: Vector3
    local_rotation: Quaternion
    last_local_position: Vector3
    last_local_rotation: Quaternion
    local_to_world_matrix: Matrix
    transform_handle: object | None
    team_id: int  # Signed Int16 in the array; not the original Int32 call arg.


@dataclass(frozen=True)
class AnimatorCall:
    method: str
    team_id: int
    transform_handle: object | None


@dataclass(frozen=True)
class RegistrationResult:
    slot: RegisteredSlot
    write_order: tuple[str, ...]
    animator_call: AnimatorCall | None = None
    animator_call_before_writes: bool = False


POSE_FIELDS = (
    "initial_local_position",
    "initial_local_rotation",
    "world_position",
    "world_rotation",
    "last_world_position",
    "last_world_rotation",
    "scale",
    "local_position",
    "local_rotation",
    "last_local_position",
    "last_local_rotation",
)


def _bool(value: bool) -> bool:
    if type(value) is not bool:
        raise ValueError("Adapter requires actual bool validity/switch")
    return value


def _int32(value: int) -> int:
    if type(value) is not int or not -(2**31) <= value < 2**31:
        raise ValueError("Adapter requires signed Int32 argument")
    return value


def set_registered_transform(
    *,
    manager_valid: bool,
    transform_valid: bool,
    previous: RegisteredSlot,
    flag: int,
    team_id: int,
    transform_handle: object | None,
    captured: RegistrationCapture | None,
) -> RegistrationResult | None:
    """369417: successful finite slot patch, or None for inactive manager.

    transform_valid is caller-resolved Unity null/destroyed status, NOT Job
    TransformAccess validity. Existing matrix retained without reading it.
    Described Animator calls do not imply actual runtime collection operations.
    """
    if not _bool(manager_valid):
        return None
    valid = _bool(transform_valid)
    team_id = _int32(team_id)
    if not valid:
        return RegistrationResult(
            replace(previous, flag=0, transform_handle=None, team_id=0),
            ("flag", "transform_access", "team_id"),
            AnimatorCall("MarkAnimatorTransformDirty", team_id, transform_handle),
            True,
        )
    flag = _integer(flag, 255)
    if captured is None or transform_handle is None:
        raise ValueError("Adapter requires resolved handle and captured getters")
    word = team_id & 0xFFFF
    signed_word = word if word < 0x8000 else word - 0x10000
    slot = replace(
        previous,
        flag=flag,
        initial_local_position=_float3(captured.initial_local_position),
        initial_local_rotation=_quaternion(captured.initial_local_rotation),
        world_position=_double3(_float3(captured.world_position)),
        world_rotation=_quaternion(captured.world_rotation),
        last_world_position=_double3(_float3(captured.last_world_position)),
        last_world_rotation=_quaternion(captured.last_world_rotation),
        scale=_float3(captured.local_scale),
        local_position=_float3(captured.local_position),
        local_rotation=_quaternion(captured.local_rotation),
        last_local_position=_float3(captured.last_local_position),
        last_local_rotation=_quaternion(captured.last_local_rotation),
        team_id=signed_word,
        transform_handle=transform_handle,
    )
    return RegistrationResult(
        slot,
        ("flag",) + POSE_FIELDS + ("team_id", "transform_access"),
        AnimatorCall("AddAnimatorTransform", team_id, transform_handle),
    )


def copy_registered_transform(
    *, manager_valid: bool, source: RegisteredSlot, target: RegisteredSlot
) -> RegistrationResult | None:
    """369418/0x5a1bc88: raw copies, destination matrix remains unchanged.

    No enabled/null/team0 gate, resampling, normalization or TeamManager call.
    Already-typed caller buffers are not re-rounded/validated on a raw copy.
    Native shared-buffer aliasing/timing is NOT modeled by these value snapshots.
    """
    if not _bool(manager_valid):
        return None
    return RegistrationResult(
        replace(source, local_to_world_matrix=target.local_to_world_matrix),
        ("flag",) + POSE_FIELDS + ("transform_access", "team_id"),
    )


def enable_registered_flag(
    *, manager_valid: bool, slot: int, flag: int, enabled: bool
) -> int | None:
    """369421/0x343c860 ONLY slot overload, not EnableTransformJob/chunk.

    None skips lookup for inactive manager or negative index. Zero flag stays
    zero; only bit0x10 changes for nonzero flags. No initial pose or other writes.
    Caller must resolve a nonnegative slot in its own actual flag buffer.
    """
    if not _bool(manager_valid) or _int32(slot) < 0:
        return None
    flag = _integer(flag, 255)
    if flag == 0:
        return 0
    return flag | 0x10 if _bool(enabled) else flag & 0xEF
