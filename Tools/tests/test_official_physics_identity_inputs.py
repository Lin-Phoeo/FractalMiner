"""Serialized identity slot production; not a live Unity runtime oracle."""

import sys
from pathlib import Path
from typing import Any, cast

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from official_physics_identity_inputs import build_bone_identity_inputs


def k(n: int, file: str = "fixture") -> tuple[str, int]:
    return file, n


def fixture():
    children = {k(9): [k(1)], k(1): [k(2), k(3)], k(2): [], k(3): []}
    parents = {k(9): None, k(1): k(9), k(2): k(1), k(3): k(1)}
    return children, parents


def test_skin_and_snapshot_parent_windows_are_distinct():
    children, parents = fixture()
    result = build_bone_identity_inputs(children, parents, [k(1)], k(9))
    assert result.collected.transforms == (k(1), k(3), k(2), k(9))
    assert result.snapshot_parent_indices == (3, 0, 0, -1)
    assert result.skin_parent_indices == (-1, 0, 0)
    assert result.root_indices == (0,)
    assert result.collected.collision_bone_indices is None


def test_indexof_first_hit_not_last_appended_render_identity():
    children, parents = fixture()
    result = build_bone_identity_inputs(children, parents, [k(9)], k(9))
    assert result.collected.transforms == (k(9), k(1), k(3), k(2), k(9))
    assert result.snapshot_parent_indices == (-1, 0, 1, 1, -1)
    assert result.skin_parent_indices == (-1, 0, 1, 1)
    assert result.root_indices == (0,)


def test_collision_indices_are_from_skin_before_render_append():
    children, parents = fixture()
    result = build_bone_identity_inputs(
        children, parents, [k(1)], k(9), collision_bones=[k(9), None, k(3), k(3)]
    )
    assert result.collected.collision_bone_indices == (-1, 1, 1)


def test_duplicate_root_order_and_ignored_roots_are_not_rewritten():
    children, parents = fixture()
    result = build_bone_identity_inputs(
        children, parents, [k(1), k(2), k(1)], k(9), ignored=[k(2)]
    )
    assert result.root_indices == (0, -1, 0)
    assert result.skin_parent_indices == (-1, 0)


def test_all_roots_ignored_still_has_render_slot():
    children, parents = fixture()
    result = build_bone_identity_inputs(children, parents, [k(1)], k(9), ignored=[k(1)])
    assert result.skin_parent_indices == ()
    assert result.snapshot_parent_indices == (-1,)
    assert result.root_indices == (-1,)


def test_parent_not_collected_remains_missing_not_fixed_by_name():
    children, parents = fixture()
    result = build_bone_identity_inputs(children, parents, [k(2)], k(9))
    assert result.skin_parent_indices == (-1,)


def test_same_pathid_in_distinct_files_remains_distinct():
    children = {k(1, "a"): [], k(1, "b"): [], k(9): []}
    parents = {node: None for node in children}
    result = build_bone_identity_inputs(children, parents, [k(1, "a"), k(1, "b")], k(9))
    assert result.root_indices == (1, 0)


@pytest.mark.parametrize("number", [-(2**63), 2**63 - 1, -5985668592349786321])
def test_signed_int64_identity_is_not_narrowed_to_runtime_int32(number):
    result = build_bone_identity_inputs(
        {k(number): []}, {k(number): None}, [k(number)], k(number)
    )
    assert result.collected.transforms == (k(number), k(number))


def test_parent_mapping_may_have_different_iteration_order():
    children, parents = fixture()
    result = build_bone_identity_inputs(
        children, dict(reversed(list(parents.items()))), [k(1)], k(9)
    )
    assert result.skin_parent_indices == (-1, 0, 0)


def test_inputs_not_modified():
    children, parents = fixture()
    old_children = {node: list(values) for node, values in children.items()}
    old_parents = dict(parents)
    roots, ignored, collision = [k(1)], [k(2)], [None, k(3)]
    build_bone_identity_inputs(
        children, parents, roots, k(9), ignored=ignored, collision_bones=collision
    )
    assert children == old_children and parents == old_parents
    assert (roots, ignored, collision) == ([k(1)], [k(2)], [None, k(3)])


@pytest.mark.parametrize(
    "invalid",
    [
        ("", 1),
        ("f", 0),
        ("f", True),
        ("f", 2**63),
        ("f", -(2**63) - 1),
        ("f", 1.0),
        ["f", 1],
        (1, 1),
    ],
)
def test_invalid_identities_are_refused(invalid):
    children, parents = fixture()
    parents[k(1)] = cast(Any, invalid)
    with pytest.raises(ValueError):
        build_bone_identity_inputs(children, parents, [k(1)], k(9))


@pytest.mark.parametrize(
    "change",
    [
        "missing",
        "extra",
        "unresolved",
        "mismatch",
        "duplicate_child",
        "two_parents",
        "self_cycle",
        "cycle",
        "unresolved_ignore",
    ],
)
def test_hierarchy_ambiguity_or_invalid_identity_refused_even_outside_collected_branch(
    change,
):
    children, parents = fixture()
    ignored = []
    if change == "missing":
        del parents[k(3)]
    elif change == "extra":
        parents[k(8)] = None
    elif change == "unresolved":
        parents[k(9)] = k(8)
    elif change == "mismatch":
        parents[k(3)] = k(9)
    elif change == "duplicate_child":
        children[k(1)].append(k(2))
    elif change == "two_parents":
        children[k(9)].append(k(2))
    elif change == "self_cycle":
        children[k(9)].append(k(9))
        parents[k(9)] = k(9)
    elif change == "cycle":
        children[k(3)].append(k(9))
        parents[k(9)] = k(3)
    else:
        ignored = [k(8)]
    with pytest.raises(ValueError):
        build_bone_identity_inputs(children, parents, [k(2)], k(9), ignored=ignored)


def test_child_missing_from_graph_is_refused():
    children, parents = fixture()
    children[k(3)].append(k(8))
    with pytest.raises(ValueError):
        build_bone_identity_inputs(children, parents, [k(1)], k(9))


def test_deep_hierarchy_validation_is_iterative():
    count = 2000
    children = {k(n): [k(n + 1)] if n < count else [] for n in range(1, count + 1)}
    parents = {k(n): k(n - 1) if n > 1 else None for n in range(1, count + 1)}
    result = build_bone_identity_inputs(children, parents, [k(1)], k(count))
    assert result.collected.skin_bone_count == count
    assert result.skin_parent_indices == (-1, *range(count - 1))
