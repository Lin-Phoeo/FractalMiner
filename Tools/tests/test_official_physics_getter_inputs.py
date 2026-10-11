"""Explicit world-getter import composition, not a solver or game oracle."""

import sys
from dataclasses import replace
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from official_physics_getter_inputs import InstanceGetter, prepare_identity_bone_import
from official_physics_identity_inputs import build_bone_identity_inputs
from official_physics_snapshot import TransformGetterValues

I = ((1, 0, 0, 0), (0, 1, 0, 0), (0, 0, 1, 0), (0, 0, 0, 1))
Q = (0, 0, 0, 1)


def k(n):
    return ("synthetic", n)


def fixture():
    graph = {k(9): [k(1)], k(1): [k(2)], k(2): []}
    parents = {k(9): None, k(1): k(9), k(2): k(1)}
    slots = build_bone_identity_inputs(graph, parents, [k(1)], k(9))
    records = {}
    for n, parent, x in [(9, 0, 4), (1, 109, 7), (2, 101, 9)]:
        matrix = (*I[:3], (x, 0, 0, 1))
        inverse = (*I[:3], (-x, 0, 0, 1))
        records[k(n)] = InstanceGetter(
            100 + n,
            parent,
            TransformGetterValues((x, 0, 0), Q, matrix, (99, 0, 0), Q),
            inverse,
        )
    return slots, records


def test_joins_original_order_and_imports_skin_only_using_actual_render_matrices():
    slots, records = fixture()
    result = prepare_identity_bone_import(slots, records)
    assert result.runtime_instance_ids == (101, 102, 109)
    assert result.runtime_parent_ids == (109, 101, 0)
    assert result.runtime_root_ids == (101,)
    assert len(result.snapshots) == 3
    assert result.vertices.frames.positions == ((3, 0, 0), (5, 0, 0))
    assert len(result.vertices.bone_weights) == 2
    assert result.vertices.skin_bone_bindposes[0][3] == (-3, 0, 0, 1)
    assert result.snapshots[0].local_position == (99, 0, 0)


def test_duplicate_appended_render_uses_same_runtime_identity_and_first_hit_parent():
    slots, records = fixture()
    slots = build_bone_identity_inputs(
        {k(9): [k(1)], k(1): [k(2)], k(2): []},
        {k(9): None, k(1): k(9), k(2): k(1)},
        [k(9)],
        k(9),
    )
    result = prepare_identity_bone_import(slots, records)
    assert result.runtime_instance_ids == (109, 101, 102, 109)
    assert len(result.vertices.frames.positions) == 3


def test_ignored_root_retains_runtime_root_identity_but_not_a_skin_slot():
    slots, records = fixture()
    slots = build_bone_identity_inputs(
        {k(9): [k(1)], k(1): [k(2)], k(2): []},
        {k(9): None, k(1): k(9), k(2): k(1)},
        [k(1), k(2)],
        k(9),
        ignored=[k(1)],
    )
    result = prepare_identity_bone_import(slots, records)
    assert result.runtime_root_ids == (101, 102)
    assert result.vertices.frames.positions == ((5, 0, 0),)


@pytest.mark.parametrize("invalid", [0, True, 2**31, -(2**31) - 1, 1.0])
def test_invalid_runtime_identity_refused(invalid):
    slots, records = fixture()
    records[k(1)] = replace(records[k(1)], instance_id=invalid)
    with pytest.raises(ValueError):
        prepare_identity_bone_import(slots, records)


@pytest.mark.parametrize("invalid", [True, 2**31, -(2**31) - 1, 1.0])
def test_invalid_runtime_parent_identity_refused(invalid):
    slots, records = fixture()
    records[k(1)] = replace(records[k(1)], parent_instance_id=invalid)
    with pytest.raises(ValueError):
        prepare_identity_bone_import(slots, records)


def test_different_serialized_objects_cannot_share_one_live_instance_id():
    slots, records = fixture()
    records[k(2)] = replace(records[k(2)], instance_id=101)
    with pytest.raises(ValueError):
        prepare_identity_bone_import(slots, records)


def test_missing_getter_is_not_replaced_by_prefab_local_trs():
    slots, records = fixture()
    del records[k(2)]
    with pytest.raises(ValueError):
        prepare_identity_bone_import(slots, records)


def test_live_parent_disagreement_refused():
    slots, records = fixture()
    records[k(2)] = replace(records[k(2)], parent_instance_id=109)
    with pytest.raises(ValueError):
        prepare_identity_bone_import(slots, records)


def test_uncollected_external_parent_remains_minus_one():
    slots, records = fixture()
    records[k(9)] = replace(records[k(9)], parent_instance_id=-7000)
    result = prepare_identity_bone_import(slots, records)
    assert result.runtime_parent_ids[-1] == -7000


def test_matrices_are_explicit_not_inverted_or_forced_to_identity():
    slots, records = fixture()
    records[k(9)] = replace(records[k(9)], world_to_local=I)
    result = prepare_identity_bone_import(slots, records)
    assert result.vertices.frames.positions == ((7, 0, 0), (9, 0, 0))
    assert result.vertices.skin_bone_bindposes[0][3] == (-3, 0, 0, 1)


def test_zero_scale_refused_by_original_finite_bindpose_adapter():
    slots, records = fixture()
    values = replace(records[k(1)].values, local_to_world=((0, 0, 0, 0), *I[1:]))
    records[k(1)] = replace(records[k(1)], values=values)
    with pytest.raises(ValueError):
        prepare_identity_bone_import(slots, records)


def test_inputs_not_mutated():
    slots, records = fixture()
    before = dict(records)
    prepare_identity_bone_import(slots, records)
    assert records == before


@pytest.mark.parametrize("window", ["count", "render", "snapshot", "skin"])
def test_malformed_compiled_windows_refused(window):
    slots, records = fixture()
    if window == "count":
        slots = replace(slots, collected=replace(slots.collected, skin_bone_count=4))
    elif window == "render":
        slots = replace(
            slots, collected=replace(slots.collected, render_transform_index=0)
        )
    elif window == "snapshot":
        slots = replace(slots, snapshot_parent_indices=())
    else:
        slots = replace(slots, skin_parent_indices=())
    with pytest.raises(ValueError):
        prepare_identity_bone_import(slots, records)


def test_wrong_root_lookup_is_not_silently_accepted():
    slots, records = fixture()
    slots = replace(slots, root_indices=(1,))
    with pytest.raises(ValueError):
        prepare_identity_bone_import(slots, records)


def test_negative_runtime_instance_ids_are_valid_without_unsigned_reinterpretation():
    slots, records = fixture()
    records = {
        node: replace(
            record,
            instance_id=-record.instance_id,
            parent_instance_id=-record.parent_instance_id,
        )
        for node, record in records.items()
    }
    result = prepare_identity_bone_import(slots, records)
    assert result.runtime_instance_ids == (-101, -102, -109)
