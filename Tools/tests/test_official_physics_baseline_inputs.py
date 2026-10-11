"""Baseline production composes existing source-bound math, not live physics."""

import copy
import sys
from pathlib import Path
from typing import Any

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from official_physics_baseline_inputs import compose_baseline_inputs


def fixture() -> dict[str, Any]:
    # IDs are deliberately non-topological and signed runtime Int32, not PPtrs.
    return {
        "ids": (-7, 3, -2, 12, 99),
        "parent_ids": (500, -7, -7, 3, 500),
        "root_ids": (-7,),
        "attributes": (1, 2, 2, 2, 1),
        "positions": ((0, 0, 0), (1, 0, 0), (0, 3, 0), (1, 1, 0), (9, 0, 0)),
        "normals": ((0, 1, 0),) * 5,
        "tangents": ((0, 0, 1),) * 5,
        "fresh_serial_no_resize": True,
        "cleared_output_buffers": True,
    }


def test_mapped_order_baseline_pose_and_global_depth():
    values = fixture()
    before = copy.deepcopy(values)
    result = compose_baseline_inputs(**values)
    assert result.parents == (-1, 0, 0, 1, -1)
    assert result.local_roots == (0,)
    assert result.children == ((2, 1), (3,), (), (), ())
    assert result.baselines.data == (0, 1, 3, 2)
    assert result.baselines.starts == (0,) and result.baselines.counts == (4,)
    assert result.local_pose.positions[3] == (0, 1, 0)
    assert result.local_pose.rotations[0] == (0, 0, 0, 1)
    # An unlisted quaternion is CLEAR MEMORY zero, not an invented identity.
    assert result.local_pose.rotations[4] == (0, 0, 0, 0)
    assert result.root_depth.roots == (-1, 0, 0, 0, -1)
    assert result.root_depth.lengths == (0, 1, 3, 2, 0)
    assert result.root_depth.maximum_length == 3
    assert result.root_depth.depths == pytest.approx((0, 1 / 3, 1, 2 / 3, 0))
    assert values == before


def test_duplicate_roots_are_not_sorted_or_deduplicated():
    values = fixture()
    values["root_ids"] = (-7, -7)
    result = compose_baseline_inputs(**values)
    assert result.baselines.data == (0, 1, 3, 2) * 2
    assert result.baselines.starts == (0, 4)


def test_depth_all_vertex_domain_not_baseline_or_computed_local_pose():
    values = fixture() | {"root_ids": (), "attributes": (1, 2, 2, 2, 1)}
    result = compose_baseline_inputs(**values)
    assert result.baselines.data == ()
    assert result.local_pose.positions == ((0, 0, 0),) * 5
    assert result.local_pose.rotations == ((0, 0, 0, 0),) * 5
    assert result.root_depth.lengths[3] == 2
    assert result.root_depth.maximum_length == 3


def test_zero_edges_retain_cleared_depths():
    values = fixture()
    values["positions"] = ((0, 0, 0),) * 5
    result = compose_baseline_inputs(**values)
    assert result.root_depth.depths == (0,) * 5


@pytest.mark.parametrize("key", ["fresh_serial_no_resize", "cleared_output_buffers"])
@pytest.mark.parametrize("value", [False, None, 1])
def test_explicit_reference_premises_required(key, value):
    with pytest.raises(ValueError):
        compose_baseline_inputs(**(fixture() | {key: value}))


@pytest.mark.parametrize(
    "change",
    [
        {"ids": (-7, -7, -2, 12, 99)},
        {"ids": (2**40, 3, -2, 12, 99)},
        {"root_ids": (500,)},
        {"parent_ids": (3, -7, -7, 3, 500)},
        {"attributes": (1, 2)},
        {"positions": ((0, 0, 0),)},
        {"positions": ((float("nan"), 0, 0),) * 5},
    ],
)
def test_invalid_buffers_or_forest_rejected(change):
    with pytest.raises(ValueError):
        compose_baseline_inputs(**(fixture() | change))
