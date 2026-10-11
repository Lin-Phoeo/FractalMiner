"""Given registration/window + world proxy pose -> existing first reset14.

Finite caller-scoped bridge, not a native allocator, animator skinning producer,
job publication or Unity backend. The world-space premise is explicit; merely
setting it does not certify a caller's local pose as world-space. Never replace
missing world data with render-local, baseline pose, identity or zero values.
"""

from collections.abc import Sequence
from dataclasses import dataclass

from official_physics_angle_baseline import _integer
from official_physics_angles import Quaternion
from official_physics_constraints import Vector3
from official_physics_particle_registration import ParticleRegistrationPlan
from official_physics_particle_reset import (
    ParticleFrameResult,
    ParticleFrameState,
    ParticleResetTeam,
    prepare_particle_frame,
)


@dataclass(frozen=True)
class ParticleWindowInitialization:
    particle_start: int | None
    states: tuple[ParticleFrameState, ...]  # Selected window only, not whole arena.
    results: tuple[ParticleFrameResult, ...]
    fully_reset: bool


def initialize_registered_particle_window(
    registration: ParticleRegistrationPlan,
    existing_states: Sequence[ParticleFrameState],
    *,
    team_id: int,
    enabled_team: ParticleResetTeam,
    proxy_world_positions: Sequence[Vector3],
    proxy_world_rotations: Sequence[Quaternion],
    world_proxy_pose_confirmed: bool,
) -> ParticleWindowInitialization:
    """Reused dirty states are reset only after original Process + Reset gates.

    Register can cast any Int32 Team argument to short; this existing reset
    consumer adapter only permits positive Int16 Team IDs matching BOTH the
    original Int32 registration identity and its short fill; aliases are refused.
    Team flag/particle start are supplied, not generated clocks or live TeamData.
    No Move/Fixed/Invalid filtering. Positions preserve Double; quaternion copies
    preserve Single magnitude. State/pose arrays remain unchanged; results carry
    reset14 write order for a future explicit publication phase.

    Inactive/no-reset windows preserve states, without reading proxy poses. A
    processing history-only request is refused by this FIRST-RESET bridge; use
    prepare_particle_frame with its resolved same-frame center for that path.
    """
    if registration.registered is not True:
        return ParticleWindowInitialization(None, (), (), False)
    if world_proxy_pose_confirmed is not True:
        raise ValueError("Adapter requires explicitly confirmed world proxy poses")
    team_id = _integer(team_id, 32767)
    if (
        not team_id
        or team_id != registration.team_fill_value
        or team_id != registration.original_team_id
    ):
        raise ValueError("Adapter reset Team must match the registered short fill")
    chunk = registration.particle_chunk
    if chunk is None:
        raise ValueError("Adapter registered window has no particle chunk")
    start, count = _integer(chunk.start, 2**31 - 1), _integer(chunk.count, 2**31 - 1)
    if start + count > len(existing_states):
        raise ValueError("Adapter registered window exceeds existing state capacity")
    if _integer(enabled_team.particle_chunk_start, 2**31 - 1) != start:
        raise ValueError("Adapter Team particle chunk differs from registration")
    flag = _integer(enabled_team.flag, 2**64 - 1)
    processing = bool(flag & 2) and not flag & ((1 << 61) | 0x10 | 0x800 | 0x80000)
    if processing and not flag & 4 and flag & (0x40000 | 0x400):
        raise ValueError("Adapter first-reset bridge cannot replace history producer")
    results = tuple(
        prepare_particle_frame(
            existing_states[index],
            enabled_team,
            team_id=team_id,
            particle_index=index,
            proxy_positions=proxy_world_positions,
            proxy_rotations=proxy_world_rotations,
        )
        for index in range(start, start + count)
    )
    return ParticleWindowInitialization(
        start,
        tuple(result.state for result in results),
        results,
        bool(results) and all(result.reset_applied for result in results),
    )
