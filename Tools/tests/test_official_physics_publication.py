"""Finite publication fixtures, not job scheduling or Unity setter execution."""

import struct
import sys
from dataclasses import replace
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from official_physics_proxy_baseline import LocalPose
from official_physics_publication import (
    TransformBufferSnapshot,
    copy_double_buffer,
    select_transform_write_buffers,
)
from official_physics_writeback import (
    BoneWritebackTeam,
    WorldBonePose,
    write_local_bone_pose,
    write_world_bone_pose,
)

Q = (0, 0, 0, 1)
FIELDS = ("world_positions", "world_rotations", "local_positions", "local_rotations")
CURRENT = TransformBufferSnapshot(
    ((2**40 + 0.125, -0.0, 3),), ((0, -0.0, 0, 2),), ((0.125, -0.0, 3),), (Q,)
)
LAST = TransformBufferSnapshot(
    ((90, 91, 92),), ((1, 0, 0, 0),), ((9, 8, 7),), ((0, 1, 0, 0),)
)
EMPTY = TransformBufferSnapshot((), (), (), ())


def bits(snapshot):
    return (
        tuple(struct.pack("<3d", *p) for p in snapshot.world_positions),
        tuple(struct.pack("<4f", *q) for q in snapshot.world_rotations),
        tuple(struct.pack("<3f", *p) for p in snapshot.local_positions),
        tuple(struct.pack("<4f", *q) for q in snapshot.local_rotations),
    )


def test_copy_is_current_to_last_for_all_four_arrays_not_reverse_or_swap():
    before_current, before_last = bits(CURRENT), bits(LAST)
    result = copy_double_buffer(CURRENT, LAST)
    assert bits(result) == before_current
    assert bits(CURRENT) == before_current
    assert bits(LAST) == before_last


@pytest.mark.parametrize("field", FIELDS)
def test_copy_uses_each_source_length_and_preserves_destination_tail(field):
    original = getattr(LAST, field)
    last = replace(LAST, **{field: original * 3})
    result = copy_double_buffer(CURRENT, last)
    assert getattr(result, field) == getattr(CURRENT, field) + original * 2


@pytest.mark.parametrize("field", FIELDS)
def test_short_destination_is_rejected_not_truncated_or_resized(field):
    last = replace(LAST, **{field: ()})
    with pytest.raises(ValueError, match="capacity"):
        copy_double_buffer(CURRENT, last)
    assert getattr(last, field) == ()


def test_empty_source_leaves_all_destination_values_untouched():
    assert bits(copy_double_buffer(EMPTY, LAST)) == bits(LAST)
    assert copy_double_buffer(EMPTY, EMPTY) == EMPTY


def test_source_arrays_are_independent_not_assumed_one_shared_count():
    source = TransformBufferSnapshot(
        CURRENT.world_positions * 2,
        (),
        CURRENT.local_positions,
        CURRENT.local_rotations * 3,
    )
    target = TransformBufferSnapshot(
        LAST.world_positions * 3,
        LAST.world_rotations,
        LAST.local_positions * 2,
        LAST.local_rotations * 4,
    )
    result = copy_double_buffer(source, target)
    assert result.world_positions == source.world_positions + LAST.world_positions
    assert result.world_rotations == LAST.world_rotations
    assert result.local_positions == source.local_positions + LAST.local_positions
    assert result.local_rotations == source.local_rotations + LAST.local_rotations


def test_large_double_and_signed_zero_are_retained_without_rotation_normalization():
    result = copy_double_buffer(CURRENT, LAST)
    assert bits(result) == bits(CURRENT)
    assert result.world_positions[0][0] == 2**40 + 0.125
    assert result.world_rotations[0][3] == 2


@pytest.mark.parametrize("field", FIELDS)
@pytest.mark.parametrize("bad", [float("nan"), float("inf"), True])
def test_nonfinite_or_boolean_values_are_adapter_errors(field, bad):
    item = getattr(CURRENT, field)[0]
    malformed = replace(CURRENT, **{field: ((bad,) + item[1:],)})
    with pytest.raises(ValueError):
        copy_double_buffer(malformed, LAST)


@pytest.mark.parametrize("field", FIELDS)
def test_nonfinite_destination_tail_is_also_rejected_by_finite_adapter(field):
    item = getattr(LAST, field)[0]
    last = replace(LAST, **{field: (item, (float("nan"),) + item[1:])})
    with pytest.raises(ValueError):
        copy_double_buffer(CURRENT, last)


def test_subnormal_source_values_are_not_flushed_or_renormalized():
    source = TransformBufferSnapshot(
        ((2**-1074, -0.0, -(2**-1074)),),
        ((2**-149, -(2**-149), -0.0, 2),),
        ((2**-149, -0.0, -(2**-149)),),
        ((2**-149, -(2**-149), -0.0, 2),),
    )
    assert bits(copy_double_buffer(source, LAST)) == bits(source)


def test_snapshot_copy_does_not_keep_mutable_source_lane_aliases():
    positions = [[1, 2, 3]]
    source = TransformBufferSnapshot(
        positions,
        CURRENT.world_rotations,
        CURRENT.local_positions,
        CURRENT.local_rotations,
    )
    published = copy_double_buffer(source, LAST)
    positions[0][0] = 123
    assert published.world_positions == ((1, 2, 3),)


@pytest.mark.parametrize("field", FIELDS)
def test_wrong_component_count_is_adapter_error(field):
    malformed = replace(CURRENT, **{field: (getattr(CURRENT, field)[0][:-1],)})
    with pytest.raises(ValueError):
        copy_double_buffer(malformed, LAST)


@pytest.mark.parametrize("field", FIELDS)
def test_snapshot_array_limit_is_adapter_policy(field):
    malformed = replace(CURRENT, **{field: getattr(CURRENT, field) * 65537})
    with pytest.raises(ValueError):
        select_transform_write_buffers(malformed, LAST, cross_frame=False)


def test_ordinary_write_entry_supplies_current_not_last():
    assert bits(
        select_transform_write_buffers(CURRENT, LAST, cross_frame=False)
    ) == bits(CURRENT)


def test_double_buffer_write_entry_supplies_last_not_current():
    assert bits(
        select_transform_write_buffers(CURRENT, LAST, cross_frame=True)
    ) == bits(LAST)


@pytest.mark.parametrize("value", [0, 1, None, "last", "false"])
def test_cross_frame_choice_is_explicit_boolean_not_truthiness(value):
    with pytest.raises(ValueError, match="explicit boolean"):
        select_transform_write_buffers(CURRENT, LAST, cross_frame=value)


def test_nonselected_buffers_are_not_read_or_implicitly_published():
    malformed = replace(CURRENT, world_positions=((float("nan"), 0, 0),))
    assert bits(
        select_transform_write_buffers(LAST, malformed, cross_frame=False)
    ) == bits(LAST)
    assert bits(
        select_transform_write_buffers(malformed, LAST, cross_frame=True)
    ) == bits(LAST)


def test_two_synthetic_frames_publish_only_on_explicit_copy():
    published = copy_double_buffer(CURRENT, LAST)
    next_current = replace(CURRENT, world_positions=((123, 456, 789),))
    assert bits(
        select_transform_write_buffers(next_current, published, cross_frame=True)
    ) == bits(CURRENT)
    assert select_transform_write_buffers(
        next_current, published, cross_frame=False
    ).world_positions == ((123, 456, 789),)
    next_published = copy_double_buffer(next_current, published)
    assert next_published.world_positions == ((123, 456, 789),)
    assert bits(published) == bits(CURRENT)


def test_writeback_to_copy_to_selected_snapshot_composition_is_explicit():
    team = BoneWritebackTeam(0, 0, 0, 2, (1, 1, 1, 1))
    world = WorldBonePose(((2**40, 0, 0), (2**40 + 0.125, 2, 3)), (Q, Q))
    local = LocalPose(((9, 8, 7), (6, 5, 4)), (Q, Q))
    written_world = write_world_bone_pose(
        [0, 1], [1, 1], [None, team], world, [Q, Q], world
    )
    written_local = write_local_bone_pose(
        [1],
        [1, 1],
        [None, team],
        (1, 2),
        (-1, 0),
        written_world,
        [(1, 2, 3), (1, 1, 1)],
        local,
    )
    source = TransformBufferSnapshot(
        written_world.positions,
        written_world.rotations,
        written_local.positions,
        written_local.rotations,
    )
    last = TransformBufferSnapshot(
        LAST.world_positions * 2,
        LAST.world_rotations * 2,
        LAST.local_positions * 2,
        LAST.local_rotations * 2,
    )
    published = copy_double_buffer(source, last)
    selected = select_transform_write_buffers(CURRENT, published, cross_frame=True)
    assert selected.world_positions[1][0] == 2**40 + 0.125
    assert selected.local_positions[1] == (0.125, 1, 1)
