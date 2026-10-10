"""Current two-stage TriangleBending work/aggregate contracts."""

import sys
from dataclasses import replace
from pathlib import Path
from typing import Any

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from official_physics_bending import (
    METHOD_DIRECTIONAL_DIHEDRAL,
    METHOD_NONE,
    VOLUME_SIGN,
    BendingParameters,
    pack_triangle_pair,
    pack_write_offsets,
)
from official_physics_bending_pass import (
    BendingTeam,
    pack_step_triangle_index,
    pack_write_index,
    solve_bending_aggregate_range,
    solve_bending_pass,
    solve_bending_work_range,
    unpack_step_triangle_index,
    unpack_write_index,
)
from official_physics_constraints import _single


def fixture() -> dict[str, Any]:
    tetra = ((0.0, 0.0, 0.0), (1.0, 0.0, 0.0), (0.0, 1.0, 0.0), (0.0, 0.0, 1.0))
    return {
        "next_positions": ((99.0, 0.0, 0.0),) * 3 + tetra,
        "write_buffer": ((77.0, 77.0, 77.0),) * 14,
        "teams": {
            5: BendingTeam(
                particle_start=3,
                proxy_start=7,
                bending_pair_count=1,
                bending_write_index_start=5,
                bending_buffer_start=10,
                scale_ratio=1.0,
                negative_scale_sign=1.0,
            )
        },
        "parameters": {5: BendingParameters(METHOD_DIRECTIONAL_DIHEDRAL, 1.0)},
        "step_triangle_indices": (pack_step_triangle_index(5, 2),),
        "step_particle_indices": (3, 4, 5, 6),
        "team_ids": (0, 0, 0, 5, 5, 5, 5),
        "attributes": (0,) * 7 + (2, 2, 2, 2),
        "depths": (0.0,) * 7 + (1.0, 1.0, 1.0, 1.0),
        "frictions": (0.0,) * 7,
        "triangle_pairs": (0, 0, pack_triangle_pair(0, 1, 2, 3)),
        "rest_angle_or_volume": (0.0, 0.0, 0.0),
        "sign_or_volume": (0, 0, VOLUME_SIGN),
        "write_data": (0, 0, pack_write_offsets(0, 0, 0, 0)),
        "write_indices": (0,) * 5
        + tuple(pack_write_index(1, start) for start in range(4)),
        "simulation_power_y": 1.0,
    }


def work_args(args: dict[str, Any], **changes: Any) -> dict[str, Any]:
    keys = (
        "next_positions",
        "write_buffer",
        "teams",
        "parameters",
        "step_triangle_indices",
        "attributes",
        "depths",
        "frictions",
        "triangle_pairs",
        "rest_angle_or_volume",
        "sign_or_volume",
        "write_data",
        "write_indices",
        "simulation_power_y",
    )
    selected = {key: args[key] for key in keys}
    selected.update(changes)
    return selected


@pytest.mark.parametrize(
    "team,pair,word",
    [
        (0, 0, 0),
        (5, 2, 0x00500002),
        (4095, 1048575, 0xFFFFFFFF),
    ],
)
def test_step_triangle_word_is_high12_team_low20_global_pair(team, pair, word):
    assert pack_step_triangle_index(team, pair) == word
    assert unpack_step_triangle_index(word) == (team, pair)
    assert unpack_step_triangle_index(word - 2**32 if word >= 2**31 else word) == (
        team,
        pair,
    )


@pytest.mark.parametrize(
    "count,start,word",
    [(0, 0, 0), (1, 5, 0x00100005), (4095, 1048575, 0xFFFFFFFF)],
)
def test_write_index_word_is_high12_count_low20_start(count, start, word):
    assert pack_write_index(count, start) == word
    assert unpack_write_index(word) == (count, start)


@pytest.mark.parametrize(
    "team,pair", [(-1, 0), (4096, 0), (0, -1), (0, 1048576), (True, 0)]
)
def test_step_pack_rejects_out_of_range_lanes(team, pair):
    with pytest.raises(ValueError):
        pack_step_triangle_index(team, pair)


def test_volume_work_stage_resolves_sparse_spaces_and_writes_exclusive_float_slots():
    args = fixture()
    result = solve_bending_work_range(**work_args(args), index_count=1)
    visit = result.visits[0]
    assert (visit.team_id, visit.pair_index) == (5, 2)
    assert visit.vertices == (0, 1, 2, 3)
    assert visit.particle_indices == (3, 4, 5, 6)
    assert visit.proxy_indices == (7, 8, 9, 10)
    assert visit.status == "solved-volume"
    assert visit.write_indices == (10, 11, 12, 13)
    current = 0.1666666716337204 * 1000.0
    lam = -current / 6000.0
    assert result.write_buffer[10:] == (
        (_single(-lam), _single(-lam), _single(-lam)),
        (_single(lam), 0.0, 0.0),
        (0.0, _single(lam), 0.0),
        (0.0, 0.0, _single(lam)),
    )
    assert result.write_buffer[:10] == args["write_buffer"][:10]


def test_work_stage_applies_nonzero_private_offsets_after_each_vertex_base():
    args = fixture()
    write_indices = (0,) * 5 + tuple(
        pack_write_index(1, start) for start in (0, 4, 8, 12)
    )
    result = solve_bending_work_range(
        **work_args(
            args,
            write_buffer=((77.0, 77.0, 77.0),) * 27,
            write_data=(0, 0, pack_write_offsets(1, 2, 3, 4)),
            write_indices=write_indices,
        ),
        index_count=1,
    )
    assert result.visits[0].write_indices == (11, 16, 21, 26)
    assert all(
        result.write_buffer[index] != (77.0, 77.0, 77.0) for index in (11, 16, 21, 26)
    )


def test_full_pass_averages_float_slots_then_adds_to_double_positions():
    args = fixture()
    result = solve_bending_pass(**args, work_index_count=1, particle_index_count=4)
    current = 0.1666666716337204 * 1000.0
    lam = -current / 6000.0
    corrections = (
        (_single(-lam), _single(-lam), _single(-lam)),
        (_single(lam), 0.0, 0.0),
        (0.0, _single(lam), 0.0),
        (0.0, 0.0, _single(lam)),
    )
    assert result.next_positions[:3] == args["next_positions"][:3]
    assert result.next_positions[3:] == tuple(
        tuple(position[i] + corrections[j][i] for i in range(3))
        for j, position in enumerate(args["next_positions"][3:])
    )
    assert [visit.status for visit in result.aggregate_visits] == ["aggregated"] * 4


def test_aggregate_uses_single_order_and_division_before_double_addition():
    args = fixture()
    write_buffer = list(args["write_buffer"])
    write_buffer[10:13] = (
        (16777216.0, 1.0, 0.25),
        (1.0, 2.0, 0.5),
        (-16777216.0, 3.0, 0.75),
    )
    write_indices = list(args["write_indices"])
    write_indices[5] = pack_write_index(3, 0)
    result = solve_bending_aggregate_range(
        args["next_positions"],
        args["teams"],
        step_particle_indices=(3,),
        team_ids=args["team_ids"],
        attributes=args["attributes"],
        write_indices=write_indices,
        write_buffer=write_buffer,
        index_count=1,
    )
    assert result.visits[0].correction == (0.0, 2.0, 0.5)
    assert result.next_positions[3] == (0.0, 2.0, 0.5)


def test_fixed_vertex_uses_point_zero_one_mass_in_math_but_aggregate_skips_it():
    args = fixture()
    attributes = list(args["attributes"])
    attributes[7] = 1
    result = solve_bending_pass(
        **dict(args, attributes=attributes), work_index_count=1, particle_index_count=4
    )
    assert result.work_visits[0].inverse_masses[0] == _single(0.01)
    assert result.write_buffer[10] != args["write_buffer"][10]
    assert result.aggregate_visits[0].status == "fixed-vertex"
    assert result.next_positions[3] == args["next_positions"][3]


def test_method_none_and_runtime_sub_epsilon_skip_before_pair_buffers():
    args = fixture()
    empty = {
        "triangle_pairs": (),
        "rest_angle_or_volume": (),
        "sign_or_volume": (),
        "write_data": (),
        "next_positions": (),
        "attributes": (),
        "depths": (),
        "frictions": (),
    }
    for settings, status in [
        (BendingParameters(METHOD_NONE, 1.0), "disabled"),
        (
            BendingParameters(METHOD_DIRECTIONAL_DIHEDRAL, _single(1e-6) / 2),
            "below-stiffness-threshold",
        ),
    ]:
        result = solve_bending_work_range(
            **work_args(args, parameters={5: settings}, **empty), index_count=1
        )
        assert result.visits[0].status == status
        assert result.write_buffer is args["write_buffer"]


def test_runtime_exact_1e_minus_6_stiffness_runs_and_zero_power_writes_zeros():
    args = fixture()
    settings = BendingParameters(METHOD_DIRECTIONAL_DIHEDRAL, _single(1e-6))
    result = solve_bending_work_range(
        **work_args(args, parameters={5: settings}, simulation_power_y=0.0),
        index_count=1,
    )
    assert result.visits[0].status == "solved-volume"
    assert result.write_buffer[10:] == ((0.0, 0.0, 0.0),) * 4


def test_effective_stiffness_saturates_after_single_multiply():
    args = fixture()
    baseline = solve_bending_work_range(**work_args(args), index_count=1)
    saturated = solve_bending_work_range(
        **work_args(
            args,
            parameters={5: BendingParameters(METHOD_DIRECTIONAL_DIHEDRAL, 2.0)},
            simulation_power_y=2.0,
        ),
        index_count=1,
    )
    assert saturated.visits[0].result == baseline.visits[0].result
    assert saturated.write_buffer == baseline.write_buffer


def test_volume_rest_scales_in_single_by_scale_ratio_and_negative_sign():
    args = fixture()
    team = replace(args["teams"][5], scale_ratio=2.0, negative_scale_sign=-1.0)
    result = solve_bending_work_range(
        **work_args(args, teams={5: team}, rest_angle_or_volume=(0.0, 0.0, 3.0)),
        index_count=1,
    )
    assert result.visits[0].adjusted_rest == -6.0


def test_directional_dihedral_uses_signed_rest_and_negative_scale_sign():
    args = fixture()
    hinge = ((0.0, 1.0, 0.0), (0.0, 0.0, 1.0), (0.0, 0.0, 0.0), (1.0, 0.0, 0.0))
    positions = args["next_positions"][:3] + hinge
    team = replace(args["teams"][5], negative_scale_sign=-1.0)
    result = solve_bending_work_range(
        **work_args(
            args,
            next_positions=positions,
            teams={5: team},
            sign_or_volume=(0, 0, -1),
            rest_angle_or_volume=(0.0, 0.0, 0.25),
        ),
        index_count=1,
    )
    visit = result.visits[0]
    assert visit.status == "solved-directional-dihedral"
    assert visit.adjusted_rest == _single(0.25)


def test_aggregate_empty_team_and_fixed_vertex_skip_before_later_buffers():
    args = fixture()
    empty_team = replace(args["teams"][5], bending_pair_count=0)
    result = solve_bending_aggregate_range(
        (),
        {5: empty_team},
        step_particle_indices=(3,),
        team_ids=args["team_ids"],
        attributes=(),
        write_indices=(),
        write_buffer=(),
        index_count=1,
    )
    assert result.visits[0].status == "empty-team-bending"
    fixed = list(args["attributes"])
    fixed[7] = 1
    result = solve_bending_aggregate_range(
        args["next_positions"],
        args["teams"],
        step_particle_indices=(3,),
        team_ids=args["team_ids"],
        attributes=fixed,
        write_indices=(),
        write_buffer=(),
        index_count=1,
    )
    assert result.visits[0].status == "fixed-vertex"


def test_zero_write_count_skips_without_reading_write_buffer():
    args = fixture()
    write_indices = list(args["write_indices"])
    write_indices[5] = 0
    result = solve_bending_aggregate_range(
        args["next_positions"],
        args["teams"],
        step_particle_indices=(3,),
        team_ids=args["team_ids"],
        attributes=args["attributes"],
        write_indices=write_indices,
        write_buffer=(),
        index_count=1,
    )
    assert result.visits[0].status == "no-writes"


@pytest.mark.parametrize("count", [0, -1, -2147483648])
def test_nonpositive_work_and_aggregate_counts_preserve_input_identity(count):
    args = fixture()
    work = solve_bending_work_range(**work_args(args), index_count=count)
    assert work.write_buffer is args["write_buffer"] and work.visits == ()
    aggregate = solve_bending_aggregate_range(
        args["next_positions"],
        {},
        step_particle_indices=(),
        team_ids=(),
        attributes=(),
        write_indices=(),
        write_buffer=(),
        index_count=count,
    )
    assert aggregate.next_positions is args["next_positions"]
    assert aggregate.visits == ()


def test_duplicate_work_slot_overwrites_same_exclusive_slots_in_input_order():
    args = fixture()
    result = solve_bending_work_range(
        **work_args(args, step_triangle_indices=args["step_triangle_indices"] * 2),
        index_count=2,
    )
    assert [visit.slot for visit in result.visits] == [0, 1]
    assert result.visits[0].write_values == result.visits[1].write_values


def test_unknown_method_skips_instead_of_guessing_directional_behavior():
    args = fixture()
    result = solve_bending_work_range(
        **work_args(
            args,
            parameters={5: BendingParameters(3, 1.0)},
            sign_or_volume=(0, 0, 1),
        ),
        index_count=1,
    )
    assert result.visits[0].status == "unsupported-method"


def test_volume_marker_dispatches_before_dihedral_method_switch():
    args = fixture()
    result = solve_bending_work_range(
        **work_args(args, parameters={5: BendingParameters(3, 1.0)}),
        index_count=1,
    )
    assert result.visits[0].status == "solved-volume"


def test_missing_selected_team_or_parameters_is_explicit_adapter_error():
    args = fixture()
    with pytest.raises(ValueError, match="TeamData"):
        solve_bending_work_range(**work_args(args, teams={}), index_count=1)
    with pytest.raises(ValueError, match="parameters"):
        solve_bending_work_range(**work_args(args, parameters={}), index_count=1)


def test_aggregate_rejects_negative_signed_team_id_as_invalid_adapter_input():
    args = fixture()
    team_ids = list(args["team_ids"])
    team_ids[3] = -1
    with pytest.raises(ValueError, match="nonnegative Team"):
        solve_bending_aggregate_range(
            args["next_positions"],
            {-1: args["teams"][5]},
            step_particle_indices=(3,),
            team_ids=team_ids,
            attributes=args["attributes"],
            write_indices=args["write_indices"],
            write_buffer=args["write_buffer"],
            index_count=1,
        )
