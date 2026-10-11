"""Given allocations and flag fragments, not a native allocator/lifecycle."""

import copy
import sys
from dataclasses import replace
from pathlib import Path
from typing import Any

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from official_physics_particle_registration import (
    PARTICLE_ARRAY_FIELDS,
    ParticleAllocation,
    apply_team_enable_bits,
    plan_particle_registration,
)

EXPECTED_FIELDS = (
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


def given(count=4, start=901) -> dict[str, Any]:
    return {name: ParticleAllocation(start, count) for name, _ in EXPECTED_FIELDS}


def capacities(capacity=1000) -> dict[str, Any]:
    return {name: capacity for name, _ in EXPECTED_FIELDS}


def plan(count=4, team_id=7, allocations=None, **updates):
    args = {"manager_valid": True, "array_capacities": capacities()}
    args.update(updates)
    return plan_particle_registration(
        count, team_id, given(count) if allocations is None else allocations, **args
    )


def test_full_vertex_count_original_fifteen_add_order_and_first_chunk_patch():
    allocations = dict(reversed(list(given().items())))
    before = copy.deepcopy(allocations)
    result = plan(allocations=allocations)
    assert PARTICLE_ARRAY_FIELDS == tuple(name for name, _ in EXPECTED_FIELDS)
    assert result.registered and result.particle_chunk == ParticleAllocation(901, 4)
    assert result.team_fill_value == 7
    assert (
        tuple((call.name, call.element_type) for call in result.calls)
        == EXPECTED_FIELDS
    )
    assert all(
        call.count == 4 and call.result == result.particle_chunk
        for call in result.calls
    )
    assert result.calls[0].fill_value == 7
    assert all(call.fill_value is None for call in result.calls[1:])
    assert allocations == before


@pytest.mark.parametrize(
    ("team_id", "signed_short"),
    [
        (0, 0),
        (32767, 32767),
        (32768, -32768),
        (65535, -1),
        (65536, 0),
        (-1, -1),
        (-32769, 32767),
        (-(2**31), 0),
        (2**31 - 1, -1),
    ],
)
def test_registration_has_no_team_zero_gate_and_int32_low16_is_signed(
    team_id, signed_short
):
    result = plan(team_id=team_id)
    assert result.registered and result.team_fill_value == signed_short
    assert result.calls[0].fill_value == signed_short


def test_invalid_manager_returns_before_reading_process_or_allocations():
    result = plan(-1, True, allocations={}, manager_valid=False, array_capacities={})
    assert not result.registered and result.calls == ()
    assert result.particle_chunk is None and result.team_fill_value is None


def test_zero_count_keeps_fifteen_calls_and_given_empty_window():
    result = plan(0, allocations=given(0, 1000))
    assert result.registered and len(result.calls) == 15
    assert result.particle_chunk == ParticleAllocation(1000, 0)


def test_maximum_count_is_compact_not_materialized_as_billions_of_particles():
    result = plan(
        2**31 - 1,
        allocations=given(2**31 - 1, 0),
        array_capacities=capacities(2**31 - 1),
    )
    assert len(result.calls) == 15 and result.calls[-1].count == 2**31 - 1


@pytest.mark.parametrize("value", [-1, 2**31, True, 1.0])
def test_vertex_count_adapter_domain(value):
    with pytest.raises(ValueError, match="Adapter"):
        plan(value)


@pytest.mark.parametrize("value", [-(2**31) - 1, 2**31, True, 1.0])
def test_team_id_is_actual_signed_int32(value):
    with pytest.raises(ValueError, match="Adapter"):
        plan(team_id=value)


@pytest.mark.parametrize("value", [0, 1, None])
def test_manager_valid_is_explicit_bool(value):
    with pytest.raises(ValueError, match="Adapter"):
        plan(manager_valid=value)


@pytest.mark.parametrize("name", [name for name, _ in EXPECTED_FIELDS])
def test_each_allocation_must_match_vertex_count_and_first_window(name):
    for changes in ({"start": 900}, {"count": 3}):
        allocations = given()
        allocations[name] = replace(allocations[name], **changes)
        with pytest.raises(ValueError, match="Adapter"):
            plan(allocations=allocations)


@pytest.mark.parametrize("name", [name for name, _ in EXPECTED_FIELDS])
def test_every_buffer_capacity_checked(name):
    caps = capacities()
    caps[name] = 904
    with pytest.raises(ValueError, match="capacity"):
        plan(array_capacities=caps)


@pytest.mark.parametrize("value", [-1, 2**31, True, 1.0])
def test_capacity_is_bounded_nonnegative_int32(value):
    caps = capacities()
    caps["baseRotArray"] = value
    with pytest.raises(ValueError, match="Adapter"):
        plan(array_capacities=caps)


@pytest.mark.parametrize("field", ["start", "count"])
@pytest.mark.parametrize("value", [-1, 2**31, True, 1.0])
def test_chunk_domain(field, value):
    allocations = given()
    allocations["teamIdArray"] = replace(allocations["teamIdArray"], **{field: value})
    with pytest.raises(ValueError, match="Adapter"):
        plan(allocations=allocations)


@pytest.mark.parametrize("which", ["allocations", "capacities"])
@pytest.mark.parametrize("change", ["missing", "extra"])
def test_exact_named_field_set_adapter_policy(which, change):
    allocations, caps = given(), capacities()
    changed = allocations if which == "allocations" else caps
    if change == "missing":
        del changed["oldPosArray"]
    else:
        changed["stepBasicPosition"] = changed["oldPosArray"]
    with pytest.raises(ValueError, match="Adapter"):
        plan(allocations=allocations, array_capacities=caps)


def test_allocation_type_is_explicit_not_tuple_or_dictionary():
    allocations = given()
    allocations["nextPosArray"] = (901, 4)
    with pytest.raises(ValueError, match="Adapter"):
        plan(allocations=allocations)


def enable(flag=0xD, enabled=True, manager_valid=True, team_id=7):
    return apply_team_enable_bits(
        flag, enabled, manager_valid=manager_valid, team_id=team_id
    )


def test_fresh_enable_sets_enable_and_reset_without_running_step():
    result = enable()
    assert result.flag == 0xF and result.applied
    assert result.pending_side_effects == (
        "ClothManager.CompleteMasterJob",
        "enableTeamSet.Add(team_id)",
        "ColliderManager.Enable(team_id)",
        "TransformManager.Enable(componentTransformIndex, enabled)",
        "TransformManager.Enable(syncTransformChunk, enabled)",
    )


def test_disable_clears_enable_and_reset_adds_disable_marker_preserving_others():
    result = enable(0xFFFFFFFFFFFFFFFF, False)
    assert result.flag == (0xFFFFFFFFFFFFFFFF & ~6) | 0x100000
    assert result.applied
    assert result.pending_side_effects[1] == "enableTeamSet.Remove(team_id)"


def test_enable_keeps_disable_marker_and_repeated_enable_is_not_early_return():
    result = enable(0x10000F)
    assert (
        result.flag == 0x10000F
        and result.applied
        and len(result.pending_side_effects) == 5
    )


@pytest.mark.parametrize("flag", [0, 1, 8, 0x20, 0x80, 0x200, 1 << 63])
@pytest.mark.parametrize("enabled", [False, True])
def test_exact_selected_bit_update_no_hidden_valid_running_filter(flag, enabled):
    result = enable(flag, enabled)
    expected = flag | 6 if enabled else (flag & ~6) | 0x100000
    assert result.flag == expected and result.applied


@pytest.mark.parametrize(
    ("manager_valid", "team_id"), [(False, 7), (True, 0), (False, 0)]
)
def test_enable_owner_and_team_zero_gates_precede_team_flag_read(
    manager_valid, team_id
):
    result = enable(-1, manager_valid=manager_valid, team_id=team_id)
    assert (
        not result.applied and result.flag == -1 and result.pending_side_effects == ()
    )


def test_enable_signed_nonzero_team_is_not_invented_positive_slot_gate():
    assert enable(team_id=-1).applied


@pytest.mark.parametrize("flag", [-1, 2**64, True, 1.0])
def test_enable_flag_domain_on_active_path(flag):
    with pytest.raises(ValueError, match="Adapter"):
        enable(flag)


@pytest.mark.parametrize("enabled", [0, 1, None])
def test_enabled_boolean_policy(enabled):
    with pytest.raises(ValueError, match="Adapter"):
        enable(enabled=enabled)


@pytest.mark.parametrize("manager_valid", [0, 1, None])
def test_enable_owner_boolean_policy(manager_valid):
    with pytest.raises(ValueError, match="Adapter"):
        enable(manager_valid=manager_valid)


@pytest.mark.parametrize("team_id", [-(2**31) - 1, 2**31, True, 1.0])
def test_enable_team_id_domain_on_valid_owner_path(team_id):
    with pytest.raises(ValueError, match="Adapter"):
        enable(team_id=team_id)
