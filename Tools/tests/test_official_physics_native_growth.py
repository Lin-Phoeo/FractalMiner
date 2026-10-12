"""Finite AddRange/Expand/Fill snapshot behavior, not native allocation."""

import sys
from pathlib import Path
from typing import Any, cast

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from official_physics_native_arena import ArenaChunk, ArenaState
from official_physics_native_growth import (
    ArenaBufferState,
    add_range,
    add_range_and_fill,
    expand_chunk,
    fill_chunk,
)


def buffer(cells=(), *, created=True, use_count=0, empty_chunks=()) -> ArenaBufferState:
    return ArenaBufferState(created, tuple(cells), ArenaState(use_count, empty_chunks))


def test_zero_add_creates_a_zero_length_native_snapshot_only_when_missing():
    missing = buffer(created=False)
    result = add_range(missing, 0, clear_value=0)
    assert result.chunk == ArenaChunk(0, 0)
    assert result.state == buffer(created=True)

    existing = buffer(created=True)
    assert add_range(existing, 0, clear_value=object()).state is existing


def test_first_free_fit_is_reused_without_touching_cells_or_capacity():
    state = buffer(
        range(8),
        use_count=8,
        empty_chunks=(ArenaChunk(1, 2), ArenaChunk(5, 3)),
    )
    result = add_range(state, 2, clear_value=-1)
    assert result.chunk == ArenaChunk(1, 2)
    assert result.state == buffer(
        range(8), use_count=8, empty_chunks=(ArenaChunk(5, 3),)
    )


def test_split_free_fit_keeps_remainder_in_the_selected_slot():
    state = buffer(
        range(10),
        use_count=6,
        empty_chunks=(ArenaChunk(2, 5), ArenaChunk(8, 2)),
    )
    result = add_range(state, 3, clear_value=-1)
    assert result.chunk == ArenaChunk(2, 3)
    assert result.state == buffer(
        range(10),
        use_count=6,
        empty_chunks=(ArenaChunk(5, 2), ArenaChunk(8, 2)),
    )


def test_first_allocation_uses_exact_request_capacity_and_clear_memory_value():
    result = add_range(buffer(created=False), 3, clear_value="zero")
    assert result.chunk == ArenaChunk(0, 3)
    assert result.state == buffer(("zero",) * 3, use_count=3)


def test_growth_doubles_when_old_capacity_exceeds_request_and_registers_tail():
    state = buffer(("a", "b", "c", "d"), use_count=4)
    result = add_range(state, 3, clear_value="zero")
    assert result.chunk == ArenaChunk(4, 3)
    assert result.state == buffer(
        ("a", "b", "c", "d", "zero", "zero", "zero", "zero"),
        use_count=7,
        empty_chunks=(ArenaChunk(7, 1),),
    )


def test_growth_adds_request_when_request_exceeds_old_capacity():
    state = buffer((1, 2, 3, 4), use_count=4)
    result = add_range(state, 6, clear_value=0)
    assert result.chunk == ArenaChunk(4, 6)
    assert result.state == buffer((1, 2, 3, 4, 0, 0, 0, 0, 0, 0), use_count=10)


def test_growth_keeps_existing_free_order_then_appends_new_tail():
    state = buffer(
        range(6), use_count=6, empty_chunks=(ArenaChunk(1, 1), ArenaChunk(3, 1))
    )
    result = add_range(state, 2, clear_value=-1)
    assert result.chunk == ArenaChunk(6, 2)
    assert result.state == buffer(
        (0, 1, 2, 3, 4, 5, -1, -1, -1, -1, -1, -1),
        use_count=8,
        empty_chunks=(ArenaChunk(1, 1), ArenaChunk(3, 1), ArenaChunk(8, 4)),
    )


@pytest.mark.parametrize("count", [-1, -(2**31), True, 1.0, 2**31])
def test_add_rejects_requests_outside_safe_nonnegative_int32_adapter(count):
    with pytest.raises(ValueError):
        add_range(buffer(), count, clear_value=0)


def test_add_rejects_inconsistent_snapshot_before_mutating_it():
    with pytest.raises(ValueError, match="created"):
        add_range(buffer((1,), created=False), 1, clear_value=0)
    with pytest.raises(ValueError, match="capacity"):
        add_range(buffer((1,), use_count=2), 1, clear_value=0)
    with pytest.raises(ValueError, match="free"):
        add_range(buffer((1,), empty_chunks=(ArenaChunk(1, 1),)), 1, clear_value=0)


def test_add_rejects_capacity_growth_that_would_overflow_int32():
    state = buffer((0,) * 4, use_count=4)
    with pytest.raises(ValueError, match="Int32"):
        add_range(state, 2**31 - 4, clear_value=0)


def test_fill_writes_only_the_selected_positive_window():
    state = buffer((0, 1, 2, 3, 4), use_count=5)
    assert fill_chunk(state, ArenaChunk(1, 3), 9) == buffer(
        (0, 9, 9, 9, 4), use_count=5
    )


def test_fill_is_noop_for_missing_storage_or_nonpositive_length():
    missing = buffer(created=False)
    assert fill_chunk(missing, ArenaChunk(99, 4), 7) is missing
    state = buffer((1, 2), use_count=2)
    assert fill_chunk(state, ArenaChunk(cast(Any, object()), 0), 7) is state
    assert fill_chunk(state, ArenaChunk(cast(Any, object()), -1), 7) is state


@pytest.mark.parametrize("chunk", [ArenaChunk(-1, 1), ArenaChunk(1, 2)])
def test_fill_rejects_positive_windows_outside_created_capacity(chunk):
    with pytest.raises(ValueError):
        fill_chunk(buffer((1, 2), use_count=2), chunk, 0)


def test_typed_add_fills_exact_reused_window_and_preserves_other_dirty_cells():
    state = buffer(
        (10, 11, 12, 13, 14),
        use_count=5,
        empty_chunks=(ArenaChunk(1, 2),),
    )
    result = add_range_and_fill(state, 2, 77, clear_value=0)
    assert result.chunk == ArenaChunk(1, 2)
    assert result.state == buffer((10, 77, 77, 13, 14), use_count=5)


def test_typed_add_fills_request_but_not_new_capacity_tail():
    result = add_range_and_fill(buffer((1, 2, 3, 4), use_count=4), 2, 8, clear_value=0)
    assert result.chunk == ArenaChunk(4, 2)
    assert result.state == buffer(
        (1, 2, 3, 4, 8, 8, 0, 0),
        use_count=6,
        empty_chunks=(ArenaChunk(6, 2),),
    )


def test_expand_returns_original_for_nonpositive_or_non_growing_request():
    state = buffer((1, 2, 3), use_count=3)
    assert (
        expand_chunk(
            state,
            ArenaChunk(cast(Any, object()), 0),
            cast(Any, object()),
            clear_value=0,
        ).state
        is state
    )
    same = expand_chunk(state, ArenaChunk(0, 2), 2, clear_value=0)
    assert same.chunk == ArenaChunk(0, 2) and same.state is state


def test_expand_allocates_new_chunk_copies_old_prefix_and_removes_old_chunk():
    state = buffer(("a", "b", "c", "d"), use_count=4)
    result = expand_chunk(state, ArenaChunk(1, 2), 3, clear_value="zero")
    assert result.chunk == ArenaChunk(4, 3)
    assert result.state == buffer(
        ("a", "b", "c", "d", "b", "c", "zero", "zero"),
        use_count=7,
        empty_chunks=(ArenaChunk(7, 1), ArenaChunk(1, 2)),
    )


def test_expand_reused_destination_retains_uncopied_cell_until_caller_fills_it():
    state = buffer(
        tuple("abcdefghij"),
        use_count=10,
        empty_chunks=(ArenaChunk(5, 4),),
    )
    result = expand_chunk(state, ArenaChunk(0, 2), 3, clear_value="zero")
    assert result.chunk == ArenaChunk(5, 3)
    assert result.state == buffer(
        ("a", "b", "c", "d", "e", "a", "b", "h", "i", "j"),
        use_count=10,
        empty_chunks=(ArenaChunk(8, 1), ArenaChunk(0, 2)),
    )


def test_expand_then_remove_old_tail_keeps_original_remove_count_rule():
    state = buffer(
        tuple("abcdefghij"),
        use_count=10,
        empty_chunks=(ArenaChunk(0, 4),),
    )
    result = expand_chunk(state, ArenaChunk(8, 2), 3, clear_value="zero")
    assert result.chunk == ArenaChunk(0, 3)
    assert result.state == buffer(
        ("i", "j", "c", "d", "e", "f", "g", "h", "i", "j"),
        use_count=8,
        empty_chunks=(ArenaChunk(3, 1), ArenaChunk(8, 2)),
    )


def test_expand_rejects_invalid_active_chunk_or_new_length():
    state = buffer((1, 2, 3), use_count=3)
    with pytest.raises(ValueError):
        expand_chunk(state, ArenaChunk(2, 2), 3, clear_value=0)
    with pytest.raises(ValueError):
        expand_chunk(state, ArenaChunk(0, 2), True, clear_value=0)
