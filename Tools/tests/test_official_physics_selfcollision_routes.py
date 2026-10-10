"""Resolved SelfCollision routing only; no native allocation or solver runs."""

import struct
import sys
from dataclasses import FrozenInstanceError, replace
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from official_physics_selfcollision_routes import (
    ROUTING_MASK,
    Chunk,
    Peer,
    Topology,
    convert_self_collision_parameters,
    plan_self_collision_update,
)
from official_physics_substep_plan import SubstepInputs, plan_simulation_substep

CURVE = tuple(float(i) / 15 for i in range(16))
EMPTY = (Chunk(0, 0),) * 3
DEFAULT_TOPOLOGY = Topology(1, 5, 3, 2)


def parameters(self_mode=0, sync_mode=0, cloth_type=1):
    return convert_self_collision_parameters(
        self_mode, CURVE, sync_mode, 0.3, cloth_type
    )


def plan(
    topology=DEFAULT_TOPOLOGY,
    params=None,
    target=None,
    parents=(),
    chunks=EMPTY,
    counts=(0, 0, 0, 0),
):
    return plan_self_collision_update(
        topology, params or parameters(), target, parents, chunks, counts
    )


def bits(*indices):
    return sum(1 << i for i in indices)


@pytest.mark.parametrize("cloth_type", [-1, 0, 1, 10, 99])
def test_convert_only_bone_spring_suppresses_modes(cloth_type):
    result = parameters(2, 2, cloth_type)
    assert (result.self_mode, result.sync_mode) == (
        (0, 0) if cloth_type == 10 else (2, 2)
    )
    assert len(result.surface_thickness_curve) == 16
    assert result.cloth_mass == pytest.approx(0.3)


@pytest.mark.parametrize("mode", [-1, 1, 3, 2147483647])
def test_unknown_modes_are_copied_not_upgraded_to_full_mesh(mode):
    result = plan(params=parameters(mode, mode), target=Peer(1, 4, 2, 2))
    assert not result.flags & ROUTING_MASK
    assert result.refresh_sync_target  # Nonzero mode differs from FullMesh=2.


@pytest.mark.parametrize(
    "edges,triangles,expected,lengths",
    [
        (0, 0, (), (0, 0, 0)),
        (3, 0, (33, 35), (0, 3, 0)),
        (0, 2, (32, 34, 38, 41), (5, 0, 2)),
        (3, 2, (32, 33, 34, 35, 38, 41, 44, 47), (5, 3, 2)),
        (-1, -1, (), (0, 0, 0)),
    ],
)
def test_self_full_mesh_signed_topology_gates(edges, triangles, expected, lengths):
    result = plan(Topology(1, 5, edges, triangles), parameters(2))
    assert result.flags == 1 | bits(*expected)
    assert tuple(event.length for event in result.chunk_events) == lengths
    assert result.counts.intersect == int(edges > 0 and triangles > 0)


@pytest.mark.parametrize(
    "own_edges,own_tri,peer_edges,peer_tri,expected",
    [
        (3, 2, 4, 6, (32, 33, 34, 36, 39, 42, 45, 48)),
        (3, 0, 0, 6, (32, 39, 45)),
        (0, 2, 4, 0, (34, 42, 48)),
        (3, 0, 4, 0, (33, 36)),
        (0, 2, 0, 6, (32, 34, 39, 42)),
    ],
)
def test_outgoing_sync_uses_target_topology_even_when_target_invalid(
    own_edges, own_tri, peer_edges, peer_tri, expected
):
    # target=None means ContainsTeamData failed. Its Valid flag is NOT a second
    # condition in this resolved path; incoming parents DO test Valid.
    result = plan(
        Topology(1, 5, own_edges, own_tri),
        parameters(0, 2),
        Peer(0, peer_edges, peer_tri, 0),
    )
    assert result.flags == 1 | bits(*expected)
    assert result.refresh_sync_target


def test_sync_mode_without_resolved_target_does_not_allocate_or_refresh():
    result = plan(params=parameters(0, 2))
    assert result.flags == 1
    assert not result.refresh_sync_target


def test_zero_local_modes_do_not_disable_incoming_parent_collision():
    result = plan(parents=(Peer(1, 4, 6, 2),))
    assert result.flags == 1 | bits(32, 33, 34, 37, 40, 43, 46, 49)
    assert (result.counts.point, result.counts.edge, result.counts.triangle) == (
        5,
        3,
        2,
    )
    assert result.counts.intersect == 1


def test_parent_valid_plus_exit_is_not_filtered_by_an_unread_exit_flag():
    assert plan(parents=(Peer(1 | 256, 4, 6, 2),)).flags == 1 | bits(
        32, 33, 34, 37, 40, 43, 46, 49
    )


def test_resolved_current_visit_does_not_retest_current_valid_flag():
    result = plan(Topology(0, 5, 3, 2), parameters(2))
    assert result.flags == bits(32, 33, 34, 35, 38, 41, 44, 47)


@pytest.mark.parametrize("flags,mode", [(0, 2), (256, 2), (1, 0), (1, 1)])
def test_parent_needs_valid_bit_and_full_mesh_sync_mode(flags, mode):
    assert plan(parents=(Peer(flags, 4, 6, mode),)).flags == 1


def test_distinct_parents_or_flags_without_counting_intersection_per_parent():
    result = plan(parents=(Peer(1, 4, 0, 2), Peer(1, 0, 6, 2)))
    assert result.flags == 1 | bits(32, 33, 34, 37, 40, 43, 46, 49)
    assert result.counts.intersect == 1


def test_exit_clears_all_routes_even_with_full_modes_and_parents():
    old = 1 | 256 | ROUTING_MASK | bits(9, 63)
    result = plan(
        Topology(old, 5, 3, 2),
        parameters(2, 2),
        Peer(1, 4, 6, 2),
        (Peer(1, 4, 6, 2),),
        (Chunk(10, 7), Chunk(20, 8), Chunk(30, 9)),
        (10, 20, 30, 4),
    )
    assert result.flags == old & ~ROUTING_MASK
    assert [event.operation for event in result.chunk_events] == ["remove"] * 3
    assert tuple(result.counts.__dict__.values()) == (3, 12, 21, 3)
    assert not result.refresh_sync_target


def test_clear_stale_routes_preserves_unrelated_bits_and_removes_valid_chunks():
    result = plan(
        Topology(1 | ROUTING_MASK | bits(16, 63), 5, 3, 2),
        chunks=(Chunk(-99, 1), Chunk(0, 2), Chunk(17, 3)),
        counts=(6, 7, 8, 9),
    )
    assert result.flags == 1 | bits(16, 63)
    assert tuple(result.counts.__dict__.values()) == (5, 5, 5, 8)


def test_valid_chunks_are_retained_without_rebuilding_to_new_topology_counts():
    chunks = (Chunk(-7, 1), Chunk(18, 9), Chunk(99, 8))
    result = plan(params=parameters(2), chunks=chunks, counts=(6, 7, 8, 2))
    assert [event.operation for event in result.chunk_events] == ["retain"] * 3
    assert tuple(event.length for event in result.chunk_events) == (1, 9, 8)
    assert result.counts.intersect == 3  # Old flags, not chunk validity, drive this.
    assert (result.counts.point, result.counts.edge, result.counts.triangle) == (
        6,
        7,
        8,
    )


def test_chunk_validity_is_signed_length_only_no_start_index_gate():
    chunks = (Chunk(-8, 0), Chunk(9, -2), Chunk(-10, 7))
    result = plan(params=parameters(2), chunks=chunks)
    assert [event.operation for event in result.chunk_events] == [
        "allocate",
        "allocate",
        "retain",
    ]
    assert (result.counts.point, result.counts.edge, result.counts.triangle) == (
        5,
        3,
        0,
    )


def test_invalid_undemanded_chunks_are_left_unchanged_not_removed():
    chunks = (Chunk(7, -3), Chunk(-8, 0), Chunk(9, -4))
    result = plan(chunks=chunks)
    assert [event.operation for event in result.chunk_events] == ["none"] * 3
    assert tuple(event.old_chunk for event in result.chunk_events) == chunks


def test_point_allocation_can_be_zero_when_triangle_route_is_enabled():
    result = plan(Topology(1, 0, 0, 2), parameters(2))
    assert result.chunk_events[0].operation == "allocate"
    assert result.chunk_events[0].length == 0
    assert result.counts.point == 0


@pytest.mark.parametrize(
    "old_intersect,new_intersect",
    [(False, False), (True, False), (False, True), (True, True)],
)
def test_intersection_counter_counts_transition_not_number_of_pairs(
    old_intersect, new_intersect
):
    old_flags = 1 | (bits(46) if old_intersect else 0)
    result = plan(
        Topology(old_flags, 5, 3, 2),
        parameters(2 if new_intersect else 0),
        counts=(0, 0, 0, 7),
    )
    assert result.counts.intersect == 7 + int(new_intersect) - int(old_intersect)


def test_global_counts_wrap_signed_int32_without_saturating():
    result = plan(
        params=parameters(2), counts=(2147483647, 2147483647, 2147483647, 2147483647)
    )
    assert tuple(result.counts.__dict__.values()) == (
        -2147483644,
        -2147483646,
        -2147483647,
        -2147483648,
    )


def test_removal_and_intersection_decrement_underflow_wrap_int32():
    result = plan(
        Topology(1 | bits(49), 5, 3, 2),
        chunks=(Chunk(0, 1),) * 3,
        counts=(-2147483648,) * 4,
    )
    assert tuple(result.counts.__dict__.values()) == (2147483647,) * 4


@pytest.mark.parametrize("index", range(44, 50))
def test_each_old_intersect_direction_contributes_to_aggregate_transition(index):
    result = plan(Topology(1 | bits(index), 5, 3, 2), counts=(0, 0, 0, 1))
    assert result.counts.intersect == 0


def test_conversion_copies_single_bits_without_clamping_or_aliasing_curve():
    samples = [0.1 + i * 0.17 for i in range(16)]
    original = list(samples)
    result = convert_self_collision_parameters(2, samples, 2, -1.3, 10)
    expected = tuple(
        struct.unpack("<f", struct.pack("<f", value))[0] for value in original
    )
    samples[0] = 999
    assert result.surface_thickness_curve == expected
    assert result.cloth_mass == struct.unpack("<f", struct.pack("<f", -1.3))[0]
    assert result.self_mode == result.sync_mode == 0


def test_closed_roster_disabled_routes_supply_explicit_host_no_ops():
    # Eleven disabled local modes in a freshly created ISOLATED roster. This is
    # not a runtime observation of absent external peers or stale buffers.
    for point_count in (15, 10, 38, 24, 12, 37, 6, 6, 4, 4, 8):
        result = plan(Topology(1, point_count, 100, 100))
        host = plan_simulation_substep(
            SubstepInputs(1, 0, 0, False, False), "in", result.counts
        )
        assert host.calls[14].no_op and host.calls[15].no_op
        assert all(event.operation == "none" for event in result.chunk_events)


def test_external_parent_reopens_existing_host_solver_routes():
    result = plan(parents=(Peer(1, 3, 2, 2),))
    host = plan_simulation_substep(
        SubstepInputs(1, 0, 0, False, False), "in", result.counts
    )
    assert not host.calls[14].no_op and not host.calls[15].no_op
    assert len(host.calls[14].nested_calls) == 13


def test_inputs_not_mutated_and_result_is_frozen():
    topology = Topology(1 | ROUTING_MASK, 5, 3, 2)
    parents = [Peer(1, 4, 2, 2)]
    chunks = list(EMPTY)
    result = plan(topology, parents=parents, chunks=chunks)
    assert topology.flags == 1 | ROUTING_MASK
    assert parents == [Peer(1, 4, 2, 2)] and chunks == list(EMPTY)
    with pytest.raises(FrozenInstanceError):
        result.flags = 0  # type: ignore[misc]


@pytest.mark.parametrize("value", [True, 1.0, -2147483649, 2147483648])
def test_int32_adapter_rejects_not_native_fault_emulation(value):
    with pytest.raises(ValueError):
        parameters(value)
    with pytest.raises(ValueError):
        plan(replace(Topology(1, 5, 3, 2), edge_count=value))


@pytest.mark.parametrize("value", [-1, True, 18446744073709551616])
def test_flags_are_explicit_uint64(value):
    with pytest.raises(ValueError):
        plan(replace(Topology(1, 5, 3, 2), flags=value))


@pytest.mark.parametrize("curve", [(), (0.0,) * 15, (float("nan"),) * 16])
def test_curve_requires_sixteen_preconverted_finite_single_samples(curve):
    with pytest.raises(ValueError):
        convert_self_collision_parameters(0, curve, 0, 0, 1)


@pytest.mark.parametrize("counts", [(), (0, 0, 0), (0, 0, 0, 0, 0), (True, 0, 0, 0)])
def test_counters_must_be_explicit_complete_int32_snapshot(counts):
    with pytest.raises(ValueError):
        plan(counts=counts)


@pytest.mark.parametrize("chunks", [(), (Chunk(0, 0),), EMPTY + (Chunk(0, 0),)])
def test_all_three_chunk_snapshots_are_required(chunks):
    with pytest.raises(ValueError):
        plan(chunks=chunks)


def test_public_api_has_no_implicit_zero_counts_or_empty_peer_graph():
    with pytest.raises(TypeError):
        plan_self_collision_update(Topology(1, 5, 3, 2), parameters())  # type: ignore[call-arg]
