"""Explicit sparse work-list production, not a live scheduler/Team importer."""

import copy
import sys
from dataclasses import replace
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from official_physics_work_lists import StepTeam, build_step_work_lists


def team(**updates):
    return replace(StepTeam(0xA2, 500, 3, 17, 2), **updates)


def build(
    teams,
    particle=(7,),
    baseline=(7,),
    particle_capacity=10_000,
    baseline_capacity=10_000,
):
    return build_step_work_lists(
        teams,
        particle_team_order=particle,
        baseline_team_order=baseline,
        particle_output_capacity=particle_capacity,
        baseline_output_capacity=baseline_capacity,
    )


def test_sparse_global_chunks_and_independent_block_orders():
    teams = {7: team(), 3: team(particle_start=30, particle_count=1, baseline_start=80)}
    before = copy.deepcopy(teams)
    result = build(teams, (7, 3), (3, 7))
    assert result.particle_indices == (500, 501, 502, 30)
    assert result.baseline_indices == (
        (3 << 16) | 80,
        (3 << 16) | 81,
        (7 << 16) | 17,
        (7 << 16) | 18,
    )
    assert teams == before


def test_team_zero_skips_before_data_lookup_and_is_not_an_extra_population():
    result = build({}, (0, 0), ())
    assert result.particle_indices == result.baseline_indices == ()


@pytest.mark.parametrize("flag", [0, 2, 0x20, 0x80, 0x22, 0x82, 0xA0])
def test_all_process_running_and_step_running_bits_required(flag):
    # An inactive Team never reads malformed chunks, preserving the native gate.
    assert (
        build(
            {7: team(flag=flag, particle_start=-1, baseline_count=-1)}
        ).particle_indices
        == ()
    )


@pytest.mark.parametrize("excluded", [0x10, 0x800, 0x80000, 1 << 61])
def test_process_exclusion_bits(excluded):
    result = build({7: team(flag=0xA2 | excluded)})
    assert result.particle_indices == result.baseline_indices == ()


@pytest.mark.parametrize("other", [1, 4, 8, 0x200, 0x2000, 1 << 63])
def test_no_invented_valid_reset_teleport_or_spring_filter(other):
    assert build({7: team(flag=0xA2 | other)}).particle_indices == (500, 501, 502)


def test_all_particle_slots_included_no_attribute_or_root_input():
    assert build({7: team()}).particle_indices == (500, 501, 502)


def test_duplicate_team_blocks_preserve_explicit_reference_order():
    result = build(
        {7: team(), 3: team(particle_start=10, particle_count=1)}, (7, 3, 7), (7, 7, 3)
    )
    assert result.particle_indices == (500, 501, 502, 10, 500, 501, 502)
    assert result.baseline_indices == ((7 << 16) | 17, (7 << 16) | 18) * 2 + (
        (3 << 16) | 17,
        (3 << 16) | 18,
    )


def test_packing_uses_global_baseline_and_native_low16_truncation():
    result = build({7: team(baseline_start=65535, baseline_count=3)})
    assert result.baseline_indices == ((7 << 16) | 65535, 7 << 16, (7 << 16) | 1)


@pytest.mark.parametrize("slot", [32768, 65535])
def test_packed_output_is_signed_int32_bit_pattern(slot):
    result = build({slot: team(baseline_count=1)}, (slot,), (slot,))
    expected = (slot << 16) | 17
    assert result.baseline_indices == (expected - 2**32,)


def test_empty_chunk_does_not_emit_fabricated_particle_or_baseline():
    result = build({7: team(particle_count=0, baseline_count=0)})
    assert result.particle_indices == result.baseline_indices == ()


def test_unequal_chunk_lengths_are_not_normalized():
    result = build({7: team(particle_count=0, baseline_count=2)})
    assert result.particle_indices == () and len(result.baseline_indices) == 2


def test_explicit_output_capacities_prevent_unbounded_materialization():
    assert build(
        {7: team()}, particle_capacity=3, baseline_capacity=2
    ).particle_indices == (500, 501, 502)
    with pytest.raises(ValueError, match="capacity"):
        build({7: team()}, particle_capacity=2)
    with pytest.raises(ValueError, match="capacity"):
        build({7: team()}, baseline_capacity=1)


@pytest.mark.parametrize("capacity", [-1, 2**31, True, 1.0])
def test_output_capacity_adapter_domain(capacity):
    with pytest.raises(ValueError, match="Adapter"):
        build({7: team()}, particle_capacity=capacity)


def test_last_int32_global_slot_is_valid_in_each_namespace():
    result = build(
        {
            7: team(
                particle_start=2**31 - 1,
                particle_count=1,
                baseline_start=2**31 - 1,
                baseline_count=1,
            )
        }
    )
    assert result.particle_indices == (2**31 - 1,)
    assert result.baseline_indices == ((7 << 16) | 65535,)


@pytest.mark.parametrize(
    "changes",
    [
        {"particle_start": -1},
        {"particle_count": -1},
        {"baseline_start": -1},
        {"baseline_count": -1},
        {"particle_count": 2**31},
        {"baseline_start": 2**31},
        {"particle_start": True},
        {"baseline_count": 1.0},
    ],
)
def test_malformed_chunk_is_adapter_error_not_native_atomic_simulation(changes):
    with pytest.raises(ValueError, match="Adapter"):
        build({7: team(**changes)})


@pytest.mark.parametrize("field", ["particle_start", "baseline_start"])
def test_chunk_last_slot_overflow_rejected(field):
    with pytest.raises(ValueError, match="Adapter"):
        build({7: team(**{field: 2**31 - 1})})


@pytest.mark.parametrize("field", ["particle_count", "baseline_count"])
def test_aggregate_counter_overflow_rejected_before_allocating_any_output(field):
    with pytest.raises(ValueError, match="Adapter"):
        build(
            {7: team(**{field: 2**31 - 1, "particle_start": 0, "baseline_start": 0})},
            (7, 7),
            (7, 7),
        )


@pytest.mark.parametrize("flag", [-1, 2**64, True, 1.0])
def test_flag_must_be_actual_uint64(flag):
    with pytest.raises(ValueError, match="Adapter"):
        build({7: team(flag=flag)})


@pytest.mark.parametrize("slot", [-1, 65536, True, 1.0])
def test_team_slot_adapter_domain(slot):
    with pytest.raises(ValueError, match="Adapter"):
        build({}, (slot,), (slot,))


def test_selected_missing_team_rejected():
    with pytest.raises(ValueError, match="Adapter"):
        build({})


def test_orders_must_name_same_reference_population_not_drop_a_team():
    with pytest.raises(ValueError, match="Adapter"):
        build({7: team()}, (7,), ())


def test_orders_must_have_same_duplicate_multiplicity():
    with pytest.raises(ValueError, match="Adapter"):
        build({7: team()}, (7, 7), (7,))


def test_unselected_invalid_mapping_entries_are_not_read():
    result = build({7: team(), -10: team(flag=-1)})
    assert result.particle_indices == (500, 501, 502)
