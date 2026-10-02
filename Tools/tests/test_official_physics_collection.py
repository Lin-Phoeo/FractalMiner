"""Collector control-flow fixtures, not a live original Unity/IL2CPP oracle."""

import sys
from pathlib import Path
from typing import Any, cast

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from official_physics_collection import collect_bone_transforms


def key(value: int, file: str = "synthetic") -> tuple[str, int]:
    return (file, value)


def test_root_and_child_lists_are_pushed_forward_and_popped_lifo():
    graph = {
        key(1): [key(2), key(3)],
        key(2): [key(4)],
        key(3): [],
        key(4): [],
        key(5): [],
        key(9): [],
    }
    result = collect_bone_transforms(graph, [key(1), key(5)], key(9))
    assert result.transforms == (key(5), key(1), key(3), key(2), key(4), key(9))
    assert result.root_transforms == (key(1), key(5))
    assert (result.skin_bone_count, result.render_transform_index) == (5, 5)
    assert result.collision_bone_indices is None


def test_ignore_prunes_descendants_not_only_the_ignored_node():
    graph = {
        key(1): [key(2), key(3)],
        key(2): [key(4)],
        key(3): [],
        key(4): [],
        key(9): [],
    }
    result = collect_bone_transforms(graph, [key(1)], key(9), ignored=[key(2)])
    assert result.transforms == (key(1), key(3), key(9))


def test_explicit_descendant_root_can_still_collect_below_ignored_ancestor():
    graph = {key(1): [key(2)], key(2): [key(3)], key(3): [], key(9): []}
    result = collect_bone_transforms(graph, [key(3), key(1)], key(9), ignored=[key(2)])
    assert result.transforms == (key(1), key(3), key(9))


def test_duplicate_and_overlapping_roots_only_collect_once_but_root_list_retained():
    graph = {key(1): [key(2)], key(2): [], key(9): []}
    result = collect_bone_transforms(graph, [key(1), key(2), key(1)], key(9))
    assert result.transforms == (key(1), key(2), key(9))
    assert result.root_transforms == (key(1), key(2), key(1))


def test_all_ignored_roots_still_append_render_transform():
    result = collect_bone_transforms(
        {key(1): [], key(9): []}, [key(1)], key(9), ignored=[key(1)]
    )
    assert result.transforms == (key(9),)
    assert result.root_transforms == (key(1),)
    assert result.skin_bone_count == result.render_transform_index == 0


def test_render_is_appended_unconditionally_even_when_already_collected():
    result = collect_bone_transforms({key(1): []}, [key(1)], key(1))
    assert result.transforms == (key(1), key(1))
    assert result.skin_bone_count == result.render_transform_index == 1


def test_collision_indices_use_pre_render_list_skip_null_keep_missing_and_duplicates():
    graph = {key(1): [key(2)], key(2): [], key(9): []}
    result = collect_bone_transforms(
        graph, [key(1)], key(9), collision_bones=[key(2), None, key(9), key(8), key(2)]
    )
    assert result.collision_bone_indices == (1, -1, -1, 1)
    assert (
        collect_bone_transforms(
            graph, [key(1)], key(9), collision_bones=[]
        ).collision_bone_indices
        == ()
    )


def test_render_already_collected_can_be_found_in_collision_list():
    result = collect_bone_transforms(
        {key(1): []}, [key(1)], key(1), collision_bones=[key(1)]
    )
    assert result.collision_bone_indices == (0,)


def test_external_ignore_does_not_invent_a_transform():
    result = collect_bone_transforms(
        {key(1): [], key(9): []}, [key(1)], key(9), ignored=[key(8)]
    )
    assert result.transforms == (key(1), key(9))


def test_full_identity_not_path_id_alone_or_bone_name():
    a, b, center = key(-5, "one"), key(-5, "two"), key(9)
    result = collect_bone_transforms({a: [], b: [], center: []}, [a, b], center)
    assert result.transforms == (b, a, center)


def test_collected_identity_is_deduplicated_before_child_expansion():
    # Synthetic duplicate edges are not a valid Unity hierarchy; still finite.
    graph = {key(1): [key(2), key(2)], key(2): [key(1)], key(9): []}
    assert collect_bone_transforms(graph, [key(1)], key(9)).transforms == (
        key(1),
        key(2),
        key(9),
    )


def test_input_mapping_insertion_order_has_no_influence():
    graph = {key(1): [key(2), key(3)], key(2): [], key(3): [], key(9): []}
    a = collect_bone_transforms(graph, [key(1)], key(9))
    b = collect_bone_transforms(dict(reversed(list(graph.items()))), [key(1)], key(9))
    assert a == b


@pytest.mark.parametrize(
    "bad",
    [
        None,
        ("", 1),
        ("synthetic", True),
        ("synthetic", 0),
        ("synthetic", 2**63),
        ("synthetic", -(2**63) - 1),
        ("synthetic", 1.0),
        ("synthetic",),
        "bone_name",
    ],
)
def test_invalid_serialized_reference_rejected_by_adapter(bad):
    with pytest.raises(ValueError, match="identity"):
        collect_bone_transforms({key(1): [], key(9): []}, [cast(Any, bad)], key(9))


@pytest.mark.parametrize(
    "case",
    [
        "empty_roots",
        "root_missing",
        "render_missing",
        "child_missing",
        "invalid_key",
        "invalid_ignore",
        "invalid_collision",
    ],
)
def test_invalid_contracts_are_adapter_errors(case):
    graph, roots, render, kwargs = {key(1): [], key(9): []}, [key(1)], key(9), {}
    if case == "empty_roots":
        roots = []
    elif case == "root_missing":
        roots = [key(8)]
    elif case == "render_missing":
        render = key(8)
    elif case == "child_missing":
        graph[key(1)] = [key(8)]
    elif case == "invalid_key":
        graph[cast(Any, "name")] = []
    elif case == "invalid_ignore":
        kwargs["ignored"] = [None]
    else:
        kwargs["collision_bones"] = ["name"]
    with pytest.raises(ValueError):
        collect_bone_transforms(graph, roots, render, **cast(Any, kwargs))


def test_size_limit_is_adapter_policy_not_original_allocation_claim():
    graph = {key(i): [] for i in range(1, 65538)}
    with pytest.raises(ValueError, match="capacity"):
        collect_bone_transforms(graph, [key(i) for i in range(1, 65537)], key(65537))


def test_caller_buffers_not_mutated():
    graph = {key(1): [key(2)], key(2): [], key(9): []}
    roots, ignored, collision = [key(1)], [], [None, key(2)]
    collect_bone_transforms(
        graph, roots, key(9), ignored=ignored, collision_bones=collision
    )
    assert graph == {key(1): [key(2)], key(2): [], key(9): []}
    assert roots == [key(1)] and ignored == [] and collision == [None, key(2)]
