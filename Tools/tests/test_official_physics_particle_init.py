"""Registered windows -> existing reset14, never guessed world/bind poses."""

import sys
from dataclasses import replace
from pathlib import Path
from typing import Any

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from official_physics_particle_init import initialize_registered_particle_window
from official_physics_particle_registration import (
    PARTICLE_ARRAY_FIELDS,
    ParticleAllocation,
    apply_team_enable_bits,
    plan_particle_registration,
)
from official_physics_particle_reset import ParticleFrameState, ParticleResetTeam
from official_physics_work_lists import StepTeam, build_step_work_lists


def dirty():
    return ParticleFrameState(
        (91, 92, 93),
        (81, 82, 83),
        (0, 0, 0, 2),
        (71, 72, 73),
        (0, 0, 0, 3),
        (61, 62, 63),
        (0, 0, 0, 4),
        (51, 52, 53),
        (41, 42, 43),
        (31, 32, 33),
        (21, 22, 23),
        0.8,
        0.9,
        (11, 12, 13),
    )


def registration(start=2, count=3, *, valid=True, team_id=7):
    fields = tuple(PARTICLE_ARRAY_FIELDS)
    return plan_particle_registration(
        count,
        team_id,
        {name: ParticleAllocation(start, count) for name in fields},
        manager_valid=valid,
        array_capacities={name: start + count for name in fields},
    )


def init(plan=None, states=None, team=None, **updates):
    kwargs: dict[str, Any] = {
        "team_id": 7,
        "enabled_team": team or ParticleResetTeam(0x0F, 2, 5),
        "proxy_world_positions": ((999, 999, 999),) * 5
        + (
            (1000000000.25, 2, 3),
            (4, 5, 6),
            (7, 8, 9),
        ),
        "proxy_world_rotations": ((0, 0, 0, 1),) * 5
        + (
            (0, 0, 0, 2),
            (0, 0, 0, 3),
            (0, 0, 0, 4),
        ),
        "world_proxy_pose_confirmed": True,
    }
    kwargs.update(updates)
    return initialize_registered_particle_window(
        plan or registration(), states or (dirty(),) * 7, **kwargs
    )


def test_registered_sparse_window_reset14_preserves_double_and_raw_q():
    states = (dirty(),) * 7
    result = init(states=states)
    assert result.particle_start == 2 and len(result.states) == 3
    assert all(item.reset_applied for item in result.results)
    assert tuple(item.proxy_index for item in result.results) == (5, 6, 7)
    first = result.states[0]
    assert (
        first.next_position
        == first.old_position
        == first.display_position
        == (1000000000.25, 2, 3)
    )
    assert (
        first.old_animation_position
        == first.base_position
        == first.velocity_position
        == first.next_position
    )
    assert (
        first.old_rotation
        == first.base_rotation
        == first.old_animation_rotation
        == (0, 0, 0, 2)
    )
    assert first.velocity == first.real_velocity == first.collision_normal == (0, 0, 0)
    assert first.friction == first.static_friction == 0
    assert result.fully_reset is True
    assert len(result.results[0].writes) == 14
    assert states == (dirty(),) * 7  # Prefix, window and tail never mutate.


def test_register_enable_reset_then_work_list_requires_later_running_step():
    enabled = apply_team_enable_bits(0x0D, True, manager_valid=True, team_id=7)
    assert enabled.flag == 0x0F
    result = init(team=ParticleResetTeam(enabled.flag, 2, 5))
    assert result.fully_reset
    pending = build_step_work_lists(
        {7: StepTeam(enabled.flag, 2, 3, 40, 2)},
        particle_team_order=(7,),
        baseline_team_order=(7,),
        particle_output_capacity=3,
        baseline_output_capacity=2,
    )
    assert pending.particle_indices == pending.baseline_indices == ()
    running = build_step_work_lists(
        {7: StepTeam(enabled.flag | 0xA0, 2, 3, 40, 2)},
        particle_team_order=(7,),
        baseline_team_order=(7,),
        particle_output_capacity=3,
        baseline_output_capacity=2,
    )
    assert running.particle_indices == (2, 3, 4)
    assert running.baseline_indices == ((7 << 16) | 40, (7 << 16) | 41)


@pytest.mark.parametrize("flag", [0x0D, 0x02, 0x0F | 0x800, 0x0F | (1 << 61)])
def test_ineligible_first_reset_preserves_dirty_values_without_pose_reads(flag):
    states = (dirty(),) * 7
    result = init(
        states=states,
        team=ParticleResetTeam(flag, 2, 5),
        proxy_world_positions=(),
        proxy_world_rotations=(),
    )
    assert result.states == states[2:5]
    assert result.fully_reset is False
    assert all(not item.writes for item in result.results)


def test_reset_wins_over_history_transform_and_needs_no_center():
    assert init(team=ParticleResetTeam(0x0F | 0x40400, 2, 5)).fully_reset


def test_history_only_is_rejected_by_first_reset_adapter_not_silently_remapped():
    with pytest.raises(ValueError, match="first-reset"):
        init(team=ParticleResetTeam(0x402, 2, 5))


def test_invalid_registration_skips_before_reading_other_inputs():
    result = initialize_registered_particle_window(
        registration(valid=False),
        (),
        team_id=0,
        enabled_team=ParticleResetTeam(-1, -1, -1),
        proxy_world_positions=(),
        proxy_world_rotations=(),
        world_proxy_pose_confirmed=False,
    )
    assert result.particle_start is None and result.states == result.results == ()
    assert result.fully_reset is False


@pytest.mark.parametrize("proof", [False, 1, None])
def test_explicit_world_proxy_space_required_not_render_local(proof):
    with pytest.raises(ValueError, match="world"):
        init(world_proxy_pose_confirmed=proof)


@pytest.mark.parametrize("team_id", [0, -1, 32768, True, 1.0, 8])
def test_consumer_team_domain_and_registration_fill_agreement(team_id):
    with pytest.raises(ValueError, match="Adapter"):
        init(team_id=team_id)


def test_raw_int32_register_team_alias_is_not_consumer_team_identity():
    # Registration permits low16 casting; this bridge refuses high-ID aliases.
    with pytest.raises(ValueError, match="Adapter"):
        init(plan=registration(team_id=65537), team_id=65537)


def test_low16_alias_cannot_bypass_original_registration_team_identity():
    with pytest.raises(ValueError, match="Adapter"):
        init(plan=registration(team_id=65537), team_id=1)


@pytest.mark.parametrize(
    "team", [ParticleResetTeam(15, 3, 5), ParticleResetTeam(True, 2, 5)]
)
def test_chunk_or_flag_adapter_inconsistency_rejected(team):
    with pytest.raises(ValueError, match="Adapter"):
        init(team=team)


def test_existing_state_window_capacity_checked_before_reset():
    with pytest.raises(ValueError, match="window"):
        init(states=(dirty(),) * 4)


def test_inconsistent_constructed_registration_missing_chunk_is_rejected():
    with pytest.raises(ValueError, match="chunk"):
        init(plan=replace(registration(), particle_chunk=None))


def test_proxy_capacity_missing_is_not_replaced_by_identity_or_local_pose():
    with pytest.raises(ValueError, match="proxy"):
        init(proxy_world_positions=((0, 0, 0),), proxy_world_rotations=())


def test_empty_registered_window_is_not_claimed_initialized():
    result = init(plan=registration(count=0))
    assert result.states == result.results == () and not result.fully_reset


def test_same_registered_window_can_reset_again_after_seek_no_cache_residue():
    first = init()
    dirty_again = tuple(
        replace(state, velocity=(100, 200, 300), friction=0.9) for state in first.states
    )
    states = (dirty(),) * 2 + dirty_again + (dirty(),) * 2
    second = init(
        states=states, proxy_world_positions=((0, 0, 0),) * 5 + ((9, 9, 9),) * 3
    )
    assert all(
        state.velocity == (0, 0, 0)
        and state.friction == 0
        and state.next_position == (9, 9, 9)
        for state in second.states
    )
