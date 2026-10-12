"""Finite source-aligned Animator RW buffer write tests; no Unity runtime."""

import math
import sys
from dataclasses import replace
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from official_physics_animator_write import (
    AnimatorRecord,
    AnimatorWriteTeam,
    write_animator_buffers,
)
from official_physics_publication import TransformBufferSnapshot
from official_physics_setter import RelativeWriteContext

Q = (0, 0, 0, 1)
QX = (1, 0, 0, 0)
QY = (0, 1, 0, 0)
BUFFERS = TransformBufferSnapshot(
    ((10, 20, 30), (40, 50, 60)),
    (QY, QX),
    ((1, 2, 3), (4, 5, 6)),
    (QY, QX),
)
RECORD = AnimatorRecord(
    local_positions=((100, 100, 100), (200, 200, 200)),
    local_rotations=(Q, Q),
    world_positions=((300, 300, 300), (400, 400, 400)),
    world_rotations=(Q, Q),
    statuses=(0, 9),
)
TEAM = AnimatorWriteTeam(flag=0x2000, cloth_simulate_weight=1, cloth_lod_fade_weight=1)
NAMES = (
    "transformID2RWHandlerID",
    "teamId2AnimatorInstanceId",
    "animatorID2RWHandler",
)


def run(**kwargs):
    values = {
        "flags": (0x16,),
        "team_ids": (1,),
        "teams": (None, TEAM),
        "buffers": BUFFERS,
        "transform_to_handler": {0: 1},
        "team_to_animator": {1: -42},
        "animator_records": {-42: RECORD},
        "relatives": {},
    }
    return write_animator_buffers(**(values | kwargs))


def test_local_full_weight_writes_selected_handler_and_status_one():
    result = run(flags=(0x14,))
    record = result.records[-42]
    assert record.local_positions == ((100, 100, 100), (1, 2, 3))
    assert record.local_rotations == (Q, QY)
    assert record.world_positions == RECORD.world_positions
    assert record.statuses == (0, 1)
    assert result.steps[0].control == "written"
    assert result.steps[0].reason == "local"
    assert result.steps[0].status == 1
    assert tuple(item[0] for item in result.steps[0].lookups) == NAMES


def test_world_rotation_without_position_gate_preserves_position_and_status_two():
    result = run(teams=(None, replace(TEAM, flag=0)))
    record = result.records[-42]
    assert record.world_rotations == (Q, QY)
    assert record.world_positions == RECORD.world_positions
    assert record.statuses == (0, 2)


def test_world_position_gate_writes_position_after_rotation_and_status_three():
    result = run()
    record = result.records[-42]
    assert record.world_rotations == (Q, QY)
    assert record.world_positions == ((300, 300, 300), (10, 20, 30))
    assert record.statuses == (0, 3)
    assert result.steps[0].write_order == (
        "world_rotation",
        "status_2",
        "world_position",
        "status_3",
    )


def test_fractional_weight_blends_from_existing_record_to_solver_value():
    team = replace(TEAM, cloth_simulate_weight=0.25)
    result = run(teams=(None, team), buffers=replace(BUFFERS, world_rotations=(Q, QX)))
    record = result.records[-42]
    assert record.world_positions[1] == (302.5, 305, 307.5)
    assert record.world_rotations[1] == Q


def test_world_bit_has_priority_over_local_bit():
    result = run(flags=(0x16,))
    assert result.steps[0].reason == "world"
    assert result.records[-42].local_positions == RECORD.local_positions


def test_relative_forward_matrix_is_applied_after_blend_and_left_multiplies_rotation():
    relative = RelativeWriteContext(
        ((1, 0, 0, 0), (0, 1, 0, 0), (0, 0, 1, 0), (-2, -3, -4, 1)),
        QX,
    )
    team = replace(TEAM, use_relative_transform=1)
    result = run(teams=(None, team), relatives={1: relative})
    record = result.records[-42]
    assert record.world_positions[1] == (8, 17, 26)
    assert record.world_rotations[1] == (0, 0, 1, 0)


def test_culling_ends_whole_job_before_any_map_or_later_slot():
    teams = (None, replace(TEAM, flag=0x800), TEAM)
    result = run(
        flags=None,
        team_ids=(1, 2),
        teams=teams,
        buffers=None,
        transform_to_handler=None,
        team_to_animator=None,
        animator_records={-42: RECORD},
    )
    assert result.terminated_at == 0
    assert len(result.steps) == 1
    assert result.steps[0].control == "return_job"
    assert result.steps[0].reason == "culling"
    assert result.steps[0].lookups == ()


def test_missing_map_continues_and_later_slot_can_write():
    result = run(
        flags=(0x16, 0x14),
        team_ids=(1, 1),
        transform_to_handler={1: 0},
    )
    assert [step.control for step in result.steps] == ["continue", "written"]
    assert result.steps[0].reason == "missing_transform_handler"
    assert result.steps[0].lookups == ((NAMES[0], 0, False),)
    assert result.records[-42].local_positions[0] == (4, 5, 6)


@pytest.mark.parametrize(
    "field,value,reason",
    [
        ("flags", (0,), "disabled"),
        (
            "teams",
            (None, replace(TEAM, flag=TEAM.flag | (1 << 61))),
            "team_bit61",
        ),
        (
            "teams",
            (None, replace(TEAM, cloth_simulate_weight=0)),
            "nonpositive_weight",
        ),
    ],
)
def test_post_lookup_hard_gates_end_whole_job(field, value, reason):
    result = run(**{field: value})
    assert result.terminated_at == 0
    assert result.steps[0].control == "return_job"
    assert result.steps[0].reason == reason
    assert tuple(item[0] for item in result.steps[0].lookups) == NAMES


def test_enabled_without_world_or_local_bits_only_continues():
    result = run(flags=(0x10,), buffers=None)
    assert result.terminated_at is None
    assert result.steps[0].control == "continue"
    assert result.steps[0].reason == "no_write_bits"


@pytest.mark.parametrize("branch", ["world", "local"])
def test_nan_source_position_continues_without_partial_write(branch):
    nan = float("nan")
    if branch == "world":
        buffers = replace(BUFFERS, world_positions=((nan, 0, 0),))
        flags = (0x12,)
    else:
        buffers = replace(BUFFERS, local_positions=((nan, 0, 0),))
        flags = (0x14,)
    result = run(flags=flags, buffers=buffers)
    assert result.steps[0].control == "continue"
    assert result.steps[0].reason == "invalid_source_position"
    assert result.records[-42] == RECORD


def test_world_position_is_validated_even_when_team_position_gate_is_off():
    nan = float("nan")
    result = run(
        teams=(None, replace(TEAM, flag=0)),
        buffers=replace(BUFFERS, world_positions=((nan, 0, 0),)),
    )
    assert result.steps[0].reason == "invalid_source_position"
    assert result.records[-42].world_rotations == RECORD.world_rotations


def test_missing_first_map_does_not_read_flags_buffers_or_later_maps():
    result = run(
        flags=None,
        buffers=None,
        transform_to_handler={},
        team_to_animator=None,
        animator_records={},
    )
    assert result.steps[0].lookups == ((NAMES[0], 0, False),)


def test_effective_weight_is_loaded_before_map_lookups_but_gated_after_them():
    with pytest.raises(ValueError, match="finite"):
        run(
            teams=(None, replace(TEAM, cloth_simulate_weight=float("nan"))),
            transform_to_handler={},
        )


def test_missing_animator_record_stops_at_third_lookup_without_buffer_reads():
    result = run(buffers=None, animator_records={})
    assert result.steps[0].reason == "missing_animator_record"
    assert tuple(item[0] for item in result.steps[0].lookups) == NAMES


def test_selected_handler_must_be_in_every_record_array():
    with pytest.raises(ValueError, match="handler"):
        run(transform_to_handler={0: 2})


def test_relative_context_is_required_only_for_selected_world_branch():
    team = replace(TEAM, use_relative_transform=1)
    with pytest.raises(ValueError, match="relative"):
        run(teams=(None, team))
    assert run(flags=(0x14,), teams=(None, team)).steps[0].reason == "local"


def test_fractional_quaternion_path_keeps_source_shortest_arc_behavior():
    q90 = (0, math.sqrt(0.5), 0, math.sqrt(0.5))
    team = replace(TEAM, cloth_simulate_weight=0.5)
    result = run(
        teams=(None, team),
        buffers=replace(BUFFERS, world_rotations=(q90, QX)),
    )
    assert result.records[-42].world_rotations[1] == pytest.approx(
        (0, math.sin(math.pi / 8), 0, math.cos(math.pi / 8)), abs=2e-7
    )


def test_inputs_are_not_mutated_when_record_is_written():
    before = RECORD
    result = run()
    assert RECORD == before
    assert result.records[-42] is not RECORD
