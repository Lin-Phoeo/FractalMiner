"""Finite registration/Enable plans over GIVEN allocations and Team state.

SimulationManager.RegisterProxyMesh method370396/0x343f930 and TeamManager.
SetEnable method369511/0x343c350, pinned original-file static evidence. This
module never executes DLLs, allocates native buffers, creates Team slots,
clears reused pose storage or performs lifecycle/Job/Collider/Transform calls.
Neither an allocator simulation nor live official Unity physics is claimed.
"""

from collections.abc import Mapping
from dataclasses import dataclass

_INT32_MAX = 2**31 - 1

# Original manager fields @16..128 and Add order. These are NOT reset14 order.
PARTICLE_ARRAY_TYPES = (
    ("teamIdArray", "Int16"),
    ("nextPosArray", "double3"),
    ("oldPosArray", "double3"),
    ("oldRotArray", "quaternion"),
    ("basePosArray", "double3"),
    ("baseRotArray", "quaternion"),
    ("oldPositionArray", "double3"),
    ("oldRotationArray", "quaternion"),
    ("velocityPosArray", "double3"),
    ("dispPosArray", "double3"),
    ("velocityArray", "float3"),
    ("realVelocityArray", "float3"),
    ("frictionArray", "Single"),
    ("staticFrictionArray", "Single"),
    ("collisionNormalArray", "float3"),
)
PARTICLE_ARRAY_FIELDS = tuple(name for name, _ in PARTICLE_ARRAY_TYPES)


@dataclass(frozen=True)
class ParticleAllocation:
    start: int
    count: int


@dataclass(frozen=True)
class ParticleArrayAdd:
    name: str
    element_type: str
    count: int
    result: ParticleAllocation
    fill_value: int | None  # None means unspecified; never implicit zero/identity.


@dataclass(frozen=True)
class ParticleRegistrationPlan:
    registered: bool
    calls: tuple[ParticleArrayAdd, ...]
    particle_chunk: ParticleAllocation | None  # TeamData.particleChunk @372/376.
    team_fill_value: int | None
    original_team_id: int | None = None  # Preserve Int32 identity before short cast.


@dataclass(frozen=True)
class TeamEnablePlan:
    flag: int
    applied: bool  # Flag fragment applied, NOT lifecycle effects performed.
    pending_side_effects: tuple[str, ...]


def _integer(value: int, minimum: int, maximum: int) -> int:
    if type(value) is not int or not minimum <= value <= maximum:
        raise ValueError("Adapter requires an actual bounded integer")
    return value


def _boolean(value: bool) -> bool:
    if type(value) is not bool:
        raise ValueError("Adapter requires an explicit boolean")
    return value


def plan_particle_registration(
    vertex_count: int,
    team_id: int,
    allocation_results: Mapping[str, ParticleAllocation],
    *,
    manager_valid: bool,
    array_capacities: Mapping[str, int],
) -> ParticleRegistrationPlan:
    """Describe original fifteen Adds with explicit external allocation results.

    Native gate is SimulationManager.isValid@364, NOT Team0 or vertex attributes.
    Invalid owner returns before process/mesh/Team/array reads. FULL VertexCount
    goes to every Add. Only first returned chunk patches Team.particleChunk;
    other fourteen native results are ignored. Require all fifteen windows to
    agree as explicit safe-adapter policy, NOT evidence that native allocation
    always aligns. Count/start/capacity nonnegative Int32 and exact field sets
    are policies, not emulation of native faults, overflow or allocation.

    Team input is signed Int32; native low16 truncation yields a signed Int16
    fill. No positivity/32767/4095 Team slot gate is invented here. Registration
    itself supplies no initial pose: reused slots retain old values until their
    separate producer writes them. stepBasicPosition/Rotation are NOT Adds here.
    The plan stays O(15), even for an externally declared enormous window.
    """
    if not _boolean(manager_valid):
        return ParticleRegistrationPlan(False, (), None, None)
    count = _integer(vertex_count, 0, _INT32_MAX)
    identifier = _integer(team_id, -(2**31), _INT32_MAX)
    names = set(PARTICLE_ARRAY_FIELDS)
    if set(allocation_results) != names or set(array_capacities) != names:
        raise ValueError("Adapter requires exactly fifteen named array inputs")

    first = None
    calls = []
    short = identifier & 65535
    signed_short = short - 65536 if short >= 32768 else short
    for name, element_type in PARTICLE_ARRAY_TYPES:
        allocation = allocation_results[name]
        if not isinstance(allocation, ParticleAllocation):
            # One ValueError contract for all malformed finite adapter inputs.
            raise ValueError(  # noqa: TRY004
                "Adapter requires explicit ParticleAllocation results"
            )
        start = _integer(allocation.start, 0, _INT32_MAX)
        allocated_count = _integer(allocation.count, 0, _INT32_MAX)
        capacity = _integer(array_capacities[name], 0, _INT32_MAX)
        if allocated_count != count:
            raise ValueError("Adapter Add result must have the full vertex count")
        if start + allocated_count > capacity:
            raise ValueError("Adapter allocation window exceeds explicit capacity")
        if first is None:
            first = allocation
        elif allocation != first:
            raise ValueError("Adapter requires aligned fifteen-array windows")
        calls.append(
            ParticleArrayAdd(
                name,
                element_type,
                count,
                allocation,
                signed_short if name == "teamIdArray" else None,
            )
        )
    return ParticleRegistrationPlan(True, tuple(calls), first, signed_short, identifier)


def apply_team_enable_bits(
    flag: int,
    enabled: bool,
    *,
    manager_valid: bool,
    team_id: int,
) -> TeamEnablePlan:
    """Return SetEnable's flag fragment and ordered NOT-EXECUTED side effects.

    TeamManager.isValid@96 and TeamID!=0 gate precede TeamData read. No same-value
    early return or Valid/Process/Running flag filter exists in this body. On
    enable set bits2/4; on disable clear both and set0x100000. Enabling does not
    clear that disable marker. CompleteMasterJob precedes the native flag write,
    followed by set membership, Collider Enable and two Transform Enable calls.
    This pure fragment cannot execute or imply those effects or a ready Job.
    """
    if not _boolean(manager_valid):
        return TeamEnablePlan(flag, False, ())
    identifier = _integer(team_id, -(2**31), _INT32_MAX)
    if identifier == 0:
        return TeamEnablePlan(flag, False, ())
    current = _integer(flag, 0, 2**64 - 1)
    on = _boolean(enabled)
    updated = current | 6 if on else (current & ~6) | 0x100000
    membership = "Add" if on else "Remove"
    return TeamEnablePlan(
        updated,
        True,
        (
            "ClothManager.CompleteMasterJob",
            f"enableTeamSet.{membership}(team_id)",
            "ColliderManager.Enable(team_id)",
            "TransformManager.Enable(componentTransformIndex, enabled)",
            "TransformManager.Enable(syncTransformChunk, enabled)",
        ),
    )
