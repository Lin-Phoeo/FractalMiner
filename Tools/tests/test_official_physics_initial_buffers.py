"""Fresh ordinary import buffers and matching composition, not final BuildProxy."""

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from official_physics_initial_buffers import compose_fresh_bone_buffers


def test_clear_attributes_read_flags_and_append_render_not_written():
    result = compose_fresh_bone_buffers((1, 2, 0, 3), 5, 4, fresh_import=True)
    assert result.initial_proxy_attributes == (0, 0, 0, 0)
    assert result.initial_transform_flags == (1, 1, 1, 1, 1)
    assert result.proxy_attributes == (1, 2, 0, 3)
    assert result.transform_flags == (11, 13, 1, 13, 1)
    assert result.skin_transform_indices == (0, 1, 2, 3)


def test_all_attribute_bytes_preserved_and_move_has_priority():
    result = compose_fresh_bone_buffers(tuple(range(256)), 257, 256, fresh_import=True)
    assert result.proxy_attributes == tuple(range(256))
    expected = tuple(
        1 | (12 if byte & 2 else 10 if byte & 1 else 0) for byte in range(256)
    )
    assert result.transform_flags == expected + (1,)


@pytest.mark.parametrize("snapshot,render", [(3, 2), (2, 0), (2, True), (True, 1)])
def test_wrong_snapshot_window_or_reordered_render_refused(snapshot, render):
    with pytest.raises(ValueError):
        compose_fresh_bone_buffers((2,), snapshot, render, fresh_import=True)


@pytest.mark.parametrize("premise", [False, None, 1])
def test_fresh_import_must_be_explicit_not_reused_buffers(premise):
    with pytest.raises(ValueError):
        compose_fresh_bone_buffers((2,), 2, 1, fresh_import=premise)


@pytest.mark.parametrize("attribute", [True, -1, 256, 1.5])
def test_nonbyte_refused(attribute):
    with pytest.raises(ValueError):
        compose_fresh_bone_buffers((attribute,), 2, 1, fresh_import=True)


def test_empty_skin_still_has_read_only_render():
    result = compose_fresh_bone_buffers((), 1, 0, fresh_import=True)
    assert result.proxy_attributes == () and result.transform_flags == (1,)
