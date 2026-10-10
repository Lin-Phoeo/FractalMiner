"""Behavior checks of the explicit typed Collider frame phases."""

import math
import sys
from dataclasses import replace
from pathlib import Path
from typing import Any, cast

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from official_physics_collider_frame import (
    ColliderFrameCenter,
    ColliderFrameState,
    ColliderFrameTeam,
    ColliderPostState,
    finish_collider_frame,
    prepare_collider_frame,
    prepare_collider_frames,
    remap_collider_rotation,
)
from official_physics_constraints import _single
from official_physics_matrix import build_double_trs

Q = (0.0, 0.0, 0.0, 1.0)
I = ((1, 0, 0, 0), (0, 1, 0, 0), (0, 0, 1, 0), (0, 0, 0, 1))
FRAME_WRITES = ("frame_position", "frame_rotation", "frame_scale")
HISTORY_WRITES = (
    "old_frame_position",
    "old_frame_rotation",
    "now_position",
    "now_rotation",
    "old_position",
    "old_rotation",
)


def state(flag=0x31):
    return ColliderFrameState(
        flag,
        (1, 2, 3),
        Q,
        (1, 1, 1),
        (4, 5, 6),
        Q,
        (7, 8, 9),
        Q,
        (10, 11, 12),
        Q,
    )


def run(s=None, t=None, **kw: Any):
    args: dict[str, Any] = {
        "collider_index": 3,
        "centers": ((0, 0, 0),) * 3 + ((1, 2, 3),),
        "transform_positions": ((1e12 + 0.125, 20, 30),),
        "transform_rotations": (Q,),
        "transform_scales": ((2, 3, 4),),
    }
    args.update(kw)
    return prepare_collider_frame(
        state() if s is None else s,
        ColliderFrameTeam(2, 3, 0, (1, 1, 1)) if t is None else t,
        **args,
    )


def test_frame_current_double_position_and_no_history_update():
    old = state()
    result = run(old)
    assert result.state.frame_position == (1e12 + 2.125, 26, 42)
    assert result.state.frame_scale == (2, 3, 4)
    assert result.state.old_frame_position == old.old_frame_position
    assert result.state.now_position == old.now_position
    assert result.state.old_position == old.old_position
    assert result.writes == FRAME_WRITES
    assert result.transform_index == 0
    assert not result.reset_applied


def test_center_is_rotated_then_scaled_in_world_axes():
    # Nonuniform scale distinguishes the observed order from a normal TRS point.
    half = math.sqrt(0.5)
    result = run(
        transform_rotations=((0, 0, half, half),),
        transform_positions=((0, 0, 0),),
        centers=((0, 0, 0),) * 3 + ((1, 0, 0),),
    )
    assert result.state.frame_position == pytest.approx((0, 3, 0), abs=1e-6)


@pytest.mark.parametrize("flag", [0, 0x10, 0x20, 0x81])
def test_collider_flag_gate_preserves_unread_inputs(flag):
    s = replace(state(flag), frame_position=(math.nan, 1, 2))
    result = run(s, centers=(), transform_positions=())
    assert result.state is s
    assert result.writes == ()
    assert result.transform_index is None


@pytest.mark.parametrize("flag", [0, 0x10 | 2, 0x800 | 2, 0x80000 | 2, (1 << 61) | 2])
def test_team_process_gate_preserves_unread_inputs(flag):
    s = state()
    result = run(
        s, ColliderFrameTeam(flag, -7, -9, (math.nan, math.nan, math.nan)), centers=()
    )
    assert result.state is s
    assert result.writes == ()


@pytest.mark.parametrize(
    "team_flag,collider_flag", [(6, 0x31), (2, 0x71), (6 | 0x40400, 0x71)]
)
def test_reset_copies_current_to_all_three_histories_and_clears_collider40(
    team_flag, collider_flag
):
    result = run(
        state(collider_flag),
        ColliderFrameTeam(team_flag, 3, 0, (math.nan, math.nan, math.nan)),
    )
    p = result.state.frame_position
    assert result.state.old_frame_position == p
    assert result.state.now_position == p
    assert result.state.old_position == p
    assert result.state.old_frame_rotation == Q
    assert result.state.now_rotation == Q
    assert result.state.old_rotation == Q
    assert result.state.flag == 0x31
    assert result.writes == FRAME_WRITES + HISTORY_WRITES + ("flag",)
    assert result.reset_applied


def test_inertia_shift_moves_three_histories_about_old_component_pivot():
    result = run(
        t=ColliderFrameTeam(2 | 0x400, 3, 0, (1, 1, 1)),
        frame_center=ColliderFrameCenter((1, 0, 0), (2, 3, 4), Q, I),
    )
    assert result.state.old_frame_position == (6, 8, 10)
    assert result.state.now_position == (9, 11, 13)
    assert result.state.old_position == (12, 14, 16)
    assert result.writes == FRAME_WRITES + HISTORY_WRITES


def test_negative_scale_then_shift_order_and_sign_rotation():
    matrix = build_double_trs((10, 0, 0), Q, (-1, 1, 1))
    result = run(
        t=ColliderFrameTeam(2 | 0x40400, 3, 0, (-1, 1, 1)),
        frame_center=ColliderFrameCenter((0, 0, 0), (2, 3, 4), Q, matrix),
    )
    assert result.state.old_frame_position == (8, 8, 10)
    assert result.state.now_position == (5, 11, 13)
    assert result.state.old_position == (2, 14, 16)
    assert result.state.old_rotation == Q


def test_rotation_remap_uses_only_y_and_z_sign_components():
    # Two sign negations cancel the same matrix reflection in the rotated axes.
    matrix = build_double_trs((999, 0, 0), Q, (1, -1, -1))
    assert remap_collider_rotation(Q, matrix, (7, -1, -1)) == Q
    assert remap_collider_rotation(Q, matrix, (-3, -1, -1)) == Q
    assert remap_collider_rotation(Q, matrix, (math.nan, -1, -1)) == Q


def test_shift_rotates_each_history_about_pivot_before_translation():
    half = math.sqrt(0.5)
    result = run(
        t=ColliderFrameTeam(2 | 0x400, 3, 0, (1, 1, 1)),
        frame_center=ColliderFrameCenter((4, 5, 6), (1, 2, 3), (0, 0, half, half), I),
    )
    assert result.state.old_frame_position == (5, 7, 9)
    assert result.state.now_position == pytest.approx((2, 10, 12), abs=2e-6)
    assert result.state.old_position == pytest.approx((-1, 13, 15), abs=2e-6)
    assert result.state.old_rotation == (0, 0, _single(half), _single(half))


def test_adapter_rejects_negative_transform_chunk_mapping():
    with pytest.raises(ValueError):
        run(t=ColliderFrameTeam(2, 4, 0, (1, 1, 1)))


def test_adapter_rejects_degenerate_rotation_basis_on_remap():
    with pytest.raises(ValueError):
        remap_collider_rotation(Q, I, (1, 0, 0))


def test_adapter_rejects_scale_sign_vector_with_missing_components():
    with pytest.raises(ValueError, match="three"):
        remap_collider_rotation(Q, I, cast(tuple[float, float, float], (1, 1)))


def test_negative_scale_only_does_not_read_unrequested_shift_fields():
    matrix = build_double_trs((10, 0, 0), Q, (-1, 1, 1))
    result = run(
        t=ColliderFrameTeam(2 | 0x40000, 3, 0, (-1, 1, 1)),
        frame_center=ColliderFrameCenter((math.nan, 0, 0), (math.nan, 0, 0), Q, matrix),
    )
    assert result.state.old_frame_position == (6, 5, 6)
    assert result.state.now_position == (3, 8, 9)
    assert result.state.old_position == (0, 11, 12)
    assert result.state.old_rotation == Q
    assert result.writes == FRAME_WRITES + HISTORY_WRITES


def test_source_transform_chunk_origins_are_independent():
    result = run(
        t=ColliderFrameTeam(2, 2, 5, (1, 1, 1)),
        transform_positions=((999, 0, 0),) * 6 + ((8, 9, 10),),
        transform_rotations=(Q,) * 7,
        transform_scales=((1, 1, 1),) * 7,
    )
    assert result.transform_index == 6
    assert result.state.frame_position == (9, 11, 13)


def test_range_keeps_original_global_slots_with_team_zero_entry():
    results = prepare_collider_frames(
        (state(), state(0), state()),
        (0, 9, 1),
        {
            0: ColliderFrameTeam(6, 0, 0, (1, 1, 1)),
            1: ColliderFrameTeam(6, 2, 1, (1, 1, 1)),
        },
        centers=((1, 0, 0), (99, 99, 99), (0, 1, 0)),
        transform_positions=((0, 0, 0), (10, 0, 0)),
        transform_rotations=(Q, Q),
        transform_scales=((2, 2, 2), (3, 3, 3)),
        index_count=3,
    )
    assert results[0].state.frame_position == (2, 0, 0)
    assert results[1].writes == ()
    assert results[2].state.frame_position == (10, 3, 0)
    assert tuple(r.transform_index for r in results) == (0, None, 1)


@pytest.mark.parametrize("count", [0, -1, -(2**31)])
def test_empty_declared_range_reads_no_buffers(count):
    assert (
        prepare_collider_frames(
            (),
            (),
            {},
            centers=(),
            transform_positions=(),
            transform_rotations=(),
            transform_scales=(),
            index_count=count,
        )
        == ()
    )


def test_post_uses_its_explicit_single_state_and_retains_other_inputs():
    s = ColliderPostState((16777217, 2.5, -3), Q, (90, 91, 92), (1, 2, 3, 4))
    result = finish_collider_frame(s, team_flag=0x22)
    assert result.state.old_frame_position == (_single(16777217), 2.5, -3)
    assert result.state.old_frame_rotation == Q
    assert result.state.frame_position == s.frame_position
    assert result.writes == ("old_frame_position", "old_frame_rotation")


@pytest.mark.parametrize("flag", [2, 0x20, 0x32, 0x822, 0x80022, (1 << 61) | 0x22])
def test_post_team_gate_preserves_even_nonfinite_frame(flag):
    s = ColliderPostState((math.nan, 0, 0), Q, (1, 2, 3), Q)
    result = finish_collider_frame(s, team_flag=flag)
    assert result.state is s
    assert result.writes == ()


@pytest.mark.parametrize("flag", [-1, 256, True])
def test_adapter_rejects_invalid_collider_flags(flag):
    with pytest.raises(ValueError):
        run(state(flag))


@pytest.mark.parametrize("flag", [-1, 2**64, True])
def test_adapter_rejects_invalid_team_flags(flag):
    with pytest.raises(ValueError):
        run(t=ColliderFrameTeam(flag, 3, 0, (1, 1, 1)))


@pytest.mark.parametrize(
    "args",
    [
        {"collider_index": -1},
        {"centers": ()},
        {"transform_positions": ()},
        {"transform_rotations": ()},
        {"transform_scales": ()},
        {"transform_positions": ((math.inf, 0, 0),)},
        {"transform_scales": ((1e99, 1, 1),)},
    ],
)
def test_adapter_rejects_bad_consumed_transform_inputs(args):
    with pytest.raises(ValueError):
        run(**args)


def test_adapter_requires_center_only_for_history_transform():
    with pytest.raises(ValueError, match="center"):
        run(t=ColliderFrameTeam(2 | 0x400, 3, 0, (1, 1, 1)))


@pytest.mark.parametrize(
    "args",
    [
        {"states": (), "team_ids": (), "teams": {}, "index_count": 1},
        {"states": (state(),), "team_ids": (), "teams": {}, "index_count": 1},
        {"states": (state(),), "team_ids": (1,), "teams": {}, "index_count": 1},
        {"states": (), "team_ids": (), "teams": {}, "index_count": True},
    ],
)
def test_adapter_range_rejects_missing_declared_inputs(args):
    with pytest.raises(ValueError):
        prepare_collider_frames(
            **args,
            centers=(),
            transform_positions=(),
            transform_rotations=(),
            transform_scales=(),
        )


def test_double_pre_state_is_not_accepted_as_a_single_post_state():
    with pytest.raises(TypeError, match="typed"):
        finish_collider_frame(cast(ColliderPostState, state()), team_flag=0x22)
