"""Analytic work-list/shared-buffer examples, not execution of the game solver."""

import math
import struct
import sys
from dataclasses import replace
from pathlib import Path
from typing import Any

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from official_physics_distance_pass import (
    DistanceBuffers,
    DistancePassSettings,
    DistancePassTeam,
    solve_distance_range,
    solve_distance_slot,
    unpack_distance_index,
)


def single(value):
    return struct.unpack("<f", struct.pack("<f", value))[0]


def fixture() -> dict[str, Any]:
    # Four independent spaces: work slot0/1, particle3/4, proxy6/7, adjacency4/5.
    return {
        "buffers": DistanceBuffers(
            ((99, 0, 0), (88, 0, 0), (0, 0, 0), (2, 0, 0), (4, 0, 0)),
            ((0, 0, 0),) * 5,
            ((0, 0, 0),) * 5,
            (0,) * 5,
        ),
        "teams": {1: DistancePassTeam(0, 2, 5, 3, 3, 4, 1, 1, 0)},
        "parameters": {1: DistancePassSettings((1,) * 16, 0.5)},
        "step_particle_indices": (3, 4),
        "team_ids": (0, 0, 1, 1, 1),
        "attributes": (0, 0, 0, 0, 0, 1, 2, 2),
        "depths": (1,) * 8,
        "adjacency_words": (0, 0, 0, 0, 1 << 20, (1 << 20) | 1),
        "neighbor_local_indices": (0, 0, 0, 0, 2, 1),
        "signed_rest_lengths": (0, 0, 0, 0, 1, 1),
        "simulation_power_y": 1,
    }


def call(**changes: Any):
    args = fixture()
    args.update(changes)
    return solve_distance_range(**args, index_count=2)


@pytest.mark.parametrize(
    "word,expected",
    [
        (0, (0, 0)),
        (0x00100005, (1, 5)),
        (0xFFFFFFFF, (4095, 1048575)),
        (-1, (4095, 1048575)),
        (-2147483648, (2048, 0)),
    ],
)
def test_packed_distance_index_uses_high12_count_low20_start(word, expected):
    assert unpack_distance_index(word) == expected


@pytest.mark.parametrize("word", [True, 1.0, -2147483649, 4294967296])
def test_packed_distance_index_rejects_outside_int32_bit_pattern(word):
    with pytest.raises(ValueError):
        unpack_distance_index(word)


def test_sparse_work_list_and_distinct_chunks_resolve_then_publish_in_place():
    result = call()
    assert result.buffers.next_positions == (
        (99, 0, 0),
        (88, 0, 0),
        (0, 0, 0),
        (2.5, 0, 0),
        (3.75, 0, 0),
    )
    assert result.buffers.velocity_positions[3:] == ((0.25, 0, 0), (-0.125, 0, 0))
    assert [
        (v.slot, v.particle_index, v.proxy_index, v.neighbor_indices, v.status)
        for v in result.visits
    ] == [(0, 3, 6, (4,), "solved"), (1, 4, 7, (3,), "solved")]
    assert all(
        v.writes == ("next_position", "velocity_position") for v in result.visits
    )


def test_work_list_order_is_not_sorted_and_changes_second_particles_input():
    result = call(step_particle_indices=(4, 3))
    assert result.buffers.next_positions[3:] == ((2.25, 0, 0), (3.5, 0, 0))
    assert [v.particle_index for v in result.visits] == [4, 3]


def test_duplicate_work_slot_revisits_updated_center():
    result = call(step_particle_indices=(3, 3))
    assert result.buffers.next_positions[3:] == ((2.75, 0, 0), (4, 0, 0))
    assert result.buffers.velocity_positions[3] == (0.375, 0, 0)


def test_two_distance_sweeps_thread_both_position_and_velocity_buffers():
    first = call()
    second = call(buffers=first.buffers)
    assert second.buffers.next_positions[3:] == ((2.625, 0, 0), (3.6875, 0, 0))
    assert second.buffers.velocity_positions[3:] == ((0.3125, 0, 0), (-0.15625, 0, 0))


@pytest.mark.parametrize("attribute", [0, 4, 8, 252])
def test_invalid_vertex_low_two_bits_zero_skips_without_publishing(attribute):
    attrs = list(fixture()["attributes"])
    attrs[6] = attribute
    result = call(attributes=attrs)
    assert result.visits[0].status == "invalid-vertex"
    assert result.visits[0].writes == ()
    assert result.buffers.next_positions[3] == (2, 0, 0)


@pytest.mark.parametrize("attribute", [1, 5, 255 & ~2])
def test_fixed_vertex_skips_ordinary_team(attribute):
    attrs = list(fixture()["attributes"])
    attrs[6] = attribute
    result = call(attributes=attrs)
    assert result.visits[0].status == "fixed-ordinary"
    assert result.buffers.next_positions[3] == (2, 0, 0)


@pytest.mark.parametrize("attribute", [2, 3, 6, 255])
def test_move_bit_is_the_only_fixed_test(attribute):
    attrs = list(fixture()["attributes"])
    attrs[6] = attribute
    assert call(attributes=attrs).visits[0].status == "solved"


def test_spring_fixed_mass_is_ten_and_fixed_center_is_processed():
    args = fixture()
    attrs = list(args["attributes"])
    attrs[6] = 1
    result = call(attributes=attrs, teams={1: replace(args["teams"][1], flag=0x2000)})
    correction = single(0.1) / single(single(0.1) + 1)
    assert result.buffers.next_positions[3][0] == 2 + correction
    assert result.visits[0].center_inverse_mass == single(0.1)


def test_fixed_neighbor_uses_fifty_even_when_its_low_two_bits_are_invalid():
    args = fixture()
    attrs = list(args["attributes"])
    attrs[7] = 0
    result = call(attributes=attrs)
    assert result.buffers.next_positions[3][0] == 2 + 1 / single(1 + single(1 / 50))
    assert result.visits[0].neighbor_indices == (4,)


@pytest.mark.parametrize("flag", [0, 2, 0x10, 1 << 61])
def test_distance_kernel_does_not_add_display_or_team_process_gate(flag):
    args = fixture()
    assert (
        call(teams={1: replace(args["teams"][1], flag=flag)}).visits[0].status
        == "solved"
    )


def test_work_list_team_zero_is_not_implicitly_discarded():
    args = fixture()
    result = call(
        team_ids=(0, 0, 0, 0, 0),
        teams={0: args["teams"][1]},
        parameters={0: args["parameters"][1]},
    )
    assert result.buffers.next_positions[3:] == ((2.5, 0, 0), (3.75, 0, 0))


def test_empty_team_distance_chunk_skips_before_proxy_buffers():
    args = fixture()
    args["teams"] = {1: replace(args["teams"][1], distance_start_count=0)}
    args.update(
        attributes=(),
        depths=(),
        adjacency_words=(),
        neighbor_local_indices=(),
        signed_rest_lengths=(),
    )
    result = solve_distance_range(**args, index_count=2)
    assert [v.status for v in result.visits] == ["empty-team-adjacency"] * 2
    assert all(v.writes == () for v in result.visits)


def test_zero_packed_count_does_not_publish_or_read_neighbor_and_velocity_buffers():
    args = fixture()
    args["adjacency_words"] = (0, 0, 0, 0, 0, 0)
    args["buffers"] = replace(args["buffers"], velocity_positions=())
    args.update(neighbor_local_indices=(), signed_rest_lengths=())
    result = solve_distance_range(**args, index_count=2)
    assert [v.status for v in result.visits] == ["no-neighbors"] * 2
    assert all(v.writes == () for v in result.visits)


def test_degenerate_edges_do_not_publish_or_require_velocity_value():
    args = fixture()
    buffers = args["buffers"]
    args["buffers"] = replace(
        buffers,
        next_positions=((0, 0, 0),) * 5,
        velocity_positions=((math.nan, 0, 0),) * 5,
    )
    result = solve_distance_range(**args, index_count=2)
    assert [v.status for v in result.visits] == ["no-nondegenerate-edges"] * 2
    assert all(v.writes == () for v in result.visits)


def test_zero_stiffness_still_counts_and_publishes_valid_edge():
    result = call(parameters={1: DistancePassSettings((0,) * 16, 0.5)})
    assert [v.status for v in result.visits] == ["solved"] * 2
    for visit in result.visits:
        assert visit.result is not None
        assert visit.result.contributing_neighbors == 1
    assert result.buffers.next_positions == fixture()["buffers"].next_positions


def test_signed_rest_length_applies_half_stiffness():
    result = call(signed_rest_lengths=(0, 0, 0, 0, -1, 1))
    assert result.buffers.next_positions[3] == (2.25, 0, 0)


def test_init_scale_x_and_scale_ratio_are_multiplied_as_single_before_use():
    args = fixture()
    team = replace(args["teams"][1], init_scale_x=1 + 2**-25, scale_ratio=1)
    assert call(teams={1: team}).buffers.next_positions[3] == (2.5, 0, 0)


def test_pose_ratio_uses_base_positions_in_the_particle_space():
    args = fixture()
    base = list(args["buffers"].base_positions)
    base[3] = (1, 0, 0)
    base[4] = (4, 0, 0)
    result = call(
        buffers=replace(args["buffers"], base_positions=base),
        teams={1: replace(args["teams"][1], animation_pose_ratio=1)},
    )
    assert result.buffers.next_positions[3] == (1.5, 0, 0)


@pytest.mark.parametrize("count", [0, -1, -2147483648])
def test_nonpositive_count_preserves_buffers_identity_and_reads_no_elements(count):
    args = fixture()
    args.update(
        teams={},
        parameters={},
        step_particle_indices=(),
        team_ids=(),
        attributes=(),
        depths=(),
        simulation_power_y=math.nan,
    )
    result = solve_distance_range(**args, index_count=count)
    assert result.buffers is args["buffers"]
    assert result.visits == ()


def test_positive_range_preserves_caller_arrays_and_unused_trailing_values():
    args = fixture()
    original = list(args["buffers"].next_positions)
    velocity = list(args["buffers"].velocity_positions)
    buffers = replace(
        args["buffers"], next_positions=original, velocity_positions=velocity
    )
    result = call(buffers=buffers)
    assert original == list(args["buffers"].next_positions)
    assert velocity == list(args["buffers"].velocity_positions)
    assert result.buffers.next_positions is not original
    assert result.buffers.base_positions is buffers.base_positions


@pytest.mark.parametrize(
    "changes",
    [
        {"step_particle_indices": (-1, 4)},
        {"step_particle_indices": (3,)},
        {"team_ids": (0, 0, 1)},
        {"teams": {}},
        {"parameters": {}},
        {"attributes": ()},
        {"depths": ()},
        {"adjacency_words": ()},
        {"neighbor_local_indices": (0, 0, 0, 0, 65536, 1)},
        {"neighbor_local_indices": (0, 0, 0, 0, 99, 1)},
        {"signed_rest_lengths": ()},
        {"simulation_power_y": math.nan},
    ],
)
def test_missing_or_invalid_consumed_inputs_rejected(changes):
    with pytest.raises(ValueError):
        call(**changes)


@pytest.mark.parametrize("count", [True, 1.0, 2147483648])
def test_range_count_requires_int32(count):
    with pytest.raises(ValueError):
        solve_distance_range(**fixture(), index_count=count)


def test_slot_can_select_sparse_ordinal_directly_without_running_prior_slots():
    result = solve_distance_slot(**fixture(), slot=1)
    assert (result.slot, result.particle_index, result.proxy_index) == (1, 4, 7)
    assert result.result is not None
    assert result.result.next_position == (3.5, 0, 0)


def test_failed_second_slot_does_not_mutate_callers_first_particle():
    args = fixture()
    original = list(args["buffers"].next_positions)
    args["buffers"] = replace(args["buffers"], next_positions=original)
    args["neighbor_local_indices"] = (0, 0, 0, 0, 2, 99)
    with pytest.raises(ValueError):
        solve_distance_range(**args, index_count=2)
    assert original == list(fixture()["buffers"].next_positions)


@pytest.mark.parametrize(
    "length,contributes",
    [
        (math.nextafter(9.99999993922529e-9, 0), False),
        (9.99999993922529e-9, True),
        (math.nextafter(9.99999993922529e-9, math.inf), True),
    ],
)
def test_short_edge_threshold_is_strict_double_less_than(length, contributes):
    args = fixture()
    positions = list(args["buffers"].next_positions)
    positions[3] = (0, 0, 0)
    positions[4] = (length, 0, 0)
    args["buffers"] = replace(args["buffers"], next_positions=positions)
    visit = solve_distance_slot(**args, slot=0)
    assert (visit.status == "solved") is contributes


def test_zero_neighbors_skips_base_and_velocity_reads_but_not_stiffness():
    args = fixture()
    args["adjacency_words"] = (0,) * 6
    args["buffers"] = replace(args["buffers"], base_positions=(), velocity_positions=())
    assert solve_distance_slot(**args, slot=0).status == "no-neighbors"
    args["parameters"] = {1: DistancePassSettings((), 0)}
    with pytest.raises(ValueError):
        solve_distance_slot(**args, slot=0)


def test_invalid_center_still_reads_preceding_depth_input():
    args = fixture()
    attrs = list(args["attributes"])
    attrs[6] = 0
    args.update(attributes=attrs, depths=())
    with pytest.raises(ValueError):
        solve_distance_slot(**args, slot=0)


def test_degenerate_neighbor_never_evaluates_inverse_mass_denominator():
    args = fixture()
    positions = list(args["buffers"].next_positions)
    positions[4] = positions[3]
    frictions = list(args["buffers"].frictions)
    frictions[4] = -100
    args["buffers"] = replace(
        args["buffers"], next_positions=positions, frictions=frictions
    )
    assert solve_distance_slot(**args, slot=0).status == "no-nondegenerate-edges"


def test_neighbor_accumulation_preserves_encoded_order_with_double_cancellation():
    args = fixture()
    buffers = args["buffers"]
    args["buffers"] = replace(
        buffers,
        next_positions=(
            (0, 0, 0),
            (0, 0, 0),
            (0, 0, 0),
            (0, 0, 0),
            (2**54, 0, 0),
            (2, 0, 0),
            (-(2**54), 0, 0),
        ),
        base_positions=((0, 0, 0),) * 7,
        velocity_positions=((0, 0, 0),) * 7,
        frictions=(0,) * 7,
    )
    args.update(
        attributes=(2,) * 10,
        depths=(1,) * 10,
        adjacency_words=(0, 0, 0, 0, 3 << 20),
        neighbor_local_indices=(0, 0, 0, 0, 2, 3, 4),
        signed_rest_lengths=(0,) * 7,
    )
    first = solve_distance_slot(**args, slot=0)
    assert first.result is not None
    assert first.result.correction == (0, 0, 0)
    assert first.result.contributing_neighbors == 3
    args["neighbor_local_indices"] = (0, 0, 0, 0, 2, 4, 3)
    second = solve_distance_slot(**args, slot=0)
    assert second.result is not None
    assert second.result.correction == (1 / 3, 0, 0)


def test_start_distance_end_next_start_feedback_uses_both_constraint_buffers():
    from official_physics_particle_step import (
        EndStepSettings,
        ParticleEndState,
        finish_particle_step,
    )
    from official_physics_start_step import (
        ParticleStartState,
        ResolvedStartCenter,
        StartStepSettings,
        start_particle_step,
    )

    args = fixture()
    identity = (0, 0, 0, 1)
    zero = (0, 0, 0)
    cfg = StartStepSettings(1, 1, 0.5, (0,) * 16, 1, 1, 1, 0, (0, -1, 0), 1, zero, 0)
    center = ResolvedStartCenter(zero, zero, identity, zero, identity)
    incoming = [
        ParticleStartState(old, pose, identity, pose, identity, velocity, 1)
        for old, pose, velocity in [
            (zero, zero, zero),
            ((1, 0, 0), (1, 0, 0), (2, 0, 0)),
            ((3, 0, 0), (2, 0, 0), (2, 0, 0)),
        ]
    ]
    started = [
        start_particle_step(
            s, cfg, attribute=1 if i == 0 else 2, center=center, wind=zero
        )
        for i, s in enumerate(incoming)
    ]
    b = args["buffers"]
    buffers = replace(
        b,
        next_positions=tuple(b.next_positions[:2])
        + tuple(s.next_position for s in started),
        base_positions=tuple(b.base_positions[:2])
        + tuple(s.base_position for s in started),
        velocity_positions=tuple(b.velocity_positions[:2])
        + tuple(s.velocity_position for s in started),
    )
    first = call(buffers=buffers)
    assert first.buffers.next_positions[3:] == ((2.5, 0, 0), (3.75, 0, 0))
    assert first.buffers.velocity_positions[3:] == ((1.25, 0, 0), (2.875, 0, 0))
    end_cfg = EndStepSettings(0.5, 1, 1, -1, 0, 0, 0)
    ended = [
        finish_particle_step(
            ParticleEndState(
                first.buffers.next_positions[i + 2],
                incoming[i].old_position,
                first.buffers.velocity_positions[i + 2],
                incoming[i].velocity,
                0,
                0,
                zero,
                1,
            ),
            end_cfg,
            attribute=1 if i == 0 else 2,
        )
        for i in range(3)
    ]
    assert [s.velocity for s in ended[1:]] == [(2.5, 0, 0), (1.75, 0, 0)]
    assert [s.real_velocity for s in ended[1:]] == [(3, 0, 0), (1.5, 0, 0)]
    following = [
        start_particle_step(
            replace(
                incoming[i],
                old_position=ended[i].old_position,
                velocity=ended[i].velocity,
            ),
            cfg,
            attribute=1 if i == 0 else 2,
            center=center,
            wind=zero,
        )
        for i in range(3)
    ]
    assert [s.next_position for s in following[1:]] == [(3.75, 0, 0), (4.625, 0, 0)]
    second_buffers = replace(
        first.buffers,
        next_positions=tuple(b.next_positions[:2])
        + tuple(s.next_position for s in following),
        velocity_positions=tuple(b.velocity_positions[:2])
        + tuple(s.velocity_position for s in following),
    )
    second = call(buffers=second_buffers)
    assert second.buffers.next_positions[3:] == ((3.6875, 0, 0), (4.65625, 0, 0))
