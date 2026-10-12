"""Ordered finite arena bookkeeping, not native allocation or Unity proof."""

import sys
from pathlib import Path
from typing import Any, cast

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from official_physics_native_arena import (
    ArenaChunk,
    ArenaState,
    add_empty_chunk,
    apply_transform_arena_removals,
    remove_native_chunk,
    take_empty_chunk,
)
from official_physics_transform_release import ARENA_OPERATIONS, TransformRangeRelease


def test_coalescing_predecessor_then_successor_removes_them_and_appends_at_end():
    state = ArenaState(20, (ArenaChunk(10, 2), ArenaChunk(2, 3), ArenaChunk(15, 2)))
    updated = add_empty_chunk(state, ArenaChunk(5, 5))
    assert updated == ArenaState(20, (ArenaChunk(15, 2), ArenaChunk(2, 10)))
    assert state.empty_chunks == (
        ArenaChunk(10, 2),
        ArenaChunk(2, 3),
        ArenaChunk(15, 2),
    )


def test_no_sort_or_repeated_recursive_coalescing_is_invented():
    # Explicit bounded noncanonical list: the source makes one pass per side.
    state = ArenaState(30, (ArenaChunk(1, 2), ArenaChunk(3, 2), ArenaChunk(12, 2)))
    updated = add_empty_chunk(state, ArenaChunk(5, 7))
    assert updated == ArenaState(30, (ArenaChunk(1, 2), ArenaChunk(3, 11)))


@pytest.mark.parametrize("chunks", [(ArenaChunk(2, 3),), (ArenaChunk(8, 2),), ()])
def test_single_side_or_no_neighbor_always_appends_merged_chunk(chunks):
    state = ArenaState(12, chunks)
    result = add_empty_chunk(state, ArenaChunk(5, 3))
    expected = (
        (ArenaChunk(2, 6),)
        if chunks and chunks[0].start == 2
        else (ArenaChunk(5, 5),) if chunks else (ArenaChunk(5, 3),)
    )
    assert result is not None and result.empty_chunks == expected


@pytest.mark.parametrize("length", [0, -1, -(2**31)])
def test_nonpositive_add_remove_do_not_read_state_or_start(length):
    chunk = ArenaChunk(cast(Any, object()), length)
    assert add_empty_chunk(None, chunk) is None
    assert remove_native_chunk(None, chunk) is None


def test_interior_remove_preserves_use_count_but_updates_free_list():
    state = ArenaState(20, ())
    assert remove_native_chunk(state, ArenaChunk(5, 3)) == ArenaState(
        20, (ArenaChunk(5, 3),)
    )


def test_tail_remove_reduces_use_count_to_max_free_start_not_max_free_end():
    state = ArenaState(20, (ArenaChunk(2, 2),))
    assert remove_native_chunk(state, ArenaChunk(17, 3)) == ArenaState(
        17, (ArenaChunk(2, 2), ArenaChunk(17, 3))
    )


def test_tail_merge_retains_empty_tail_span_beyond_new_use_count():
    state = ArenaState(17, (ArenaChunk(17, 3), ArenaChunk(5, 2)))
    assert remove_native_chunk(state, ArenaChunk(7, 10)) == ArenaState(
        5, (ArenaChunk(5, 15),)
    )


def test_whole_remove_sets_zero_but_keeps_free_span_for_reuse():
    assert remove_native_chunk(ArenaState(10, ()), ArenaChunk(0, 10)) == ArenaState(
        0, (ArenaChunk(0, 10),)
    )


def test_first_larger_fit_wins_before_later_exact_fit_and_preserves_index():
    state = ArenaState(30, (ArenaChunk(20, 9), ArenaChunk(3, 2)))
    result = take_empty_chunk(state, 2)
    assert result.chunk == ArenaChunk(20, 2)
    assert result.state == ArenaState(30, (ArenaChunk(22, 7), ArenaChunk(3, 2)))


def test_exact_match_swaps_last_into_selected_slot_before_removing_tail():
    state = ArenaState(
        30, (ArenaChunk(0, 1), ArenaChunk(5, 2), ArenaChunk(12, 3), ArenaChunk(20, 4))
    )
    result = take_empty_chunk(state, 2)
    assert result.chunk == ArenaChunk(5, 2)
    assert result.state == ArenaState(
        30, (ArenaChunk(0, 1), ArenaChunk(20, 4), ArenaChunk(12, 3))
    )


def test_predecessor_swap_back_changes_remaining_order_before_successor_search():
    state = ArenaState(
        30, (ArenaChunk(2, 3), ArenaChunk(16, 2), ArenaChunk(10, 2), ArenaChunk(24, 2))
    )
    assert add_empty_chunk(state, ArenaChunk(5, 5)) == ArenaState(
        30, (ArenaChunk(24, 2), ArenaChunk(16, 2), ArenaChunk(2, 10))
    )


def test_no_fit_returns_zero_length_empty_and_same_snapshot():
    state = ArenaState(10, (ArenaChunk(1, 2),))
    result = take_empty_chunk(state, 3)
    assert result.chunk == ArenaChunk(0, 0) and result.state is state


@pytest.mark.parametrize("count", [0, -1, -(2**31)])
def test_nonpositive_take_returns_empty_without_reading_missing_state(count):
    result = take_empty_chunk(None, count)
    assert result.chunk == ArenaChunk(0, 0) and result.state is None


def test_remove_then_take_keeps_use_count_unchanged_until_the_outer_add_producer():
    freed = remove_native_chunk(ArenaState(10, ()), ArenaChunk(7, 3))
    assert freed is not None
    reused = take_empty_chunk(freed, 2)
    assert reused.chunk == ArenaChunk(7, 2)
    assert reused.state == ArenaState(7, (ArenaChunk(9, 1),))


@pytest.mark.parametrize("function", [add_empty_chunk, remove_native_chunk])
@pytest.mark.parametrize(
    "chunk",
    [
        ArenaChunk(-1, 2),
        ArenaChunk(True, 1),
        ArenaChunk(2**31 - 1, 1),
        ArenaChunk(0, 2**31),
        ArenaChunk(0, True),
    ],
)
def test_active_chunk_requires_bounded_nonnegative_nonoverflowing_window(
    function, chunk
):
    with pytest.raises(ValueError):
        function(ArenaState(10, ()), chunk)


@pytest.mark.parametrize("function", [add_empty_chunk, remove_native_chunk])
def test_active_missing_state_is_not_default_empty_allocator(function):
    with pytest.raises(ValueError, match="state"):
        function(None, ArenaChunk(0, 1))


@pytest.mark.parametrize("count", [True, 1.0, 2**31])
def test_take_requires_signed_int32_request(count):
    with pytest.raises(ValueError):
        take_empty_chunk(ArenaState(10, ()), count)


def test_selected_free_chunk_payload_is_validated_without_normalizing_order():
    with pytest.raises(ValueError):
        take_empty_chunk(ArenaState(10, (ArenaChunk(0, 0),)), 1)


def test_tail_count_requires_actual_int32_capture():
    with pytest.raises(ValueError):
        remove_native_chunk(ArenaState(cast(Any, None), ()), ArenaChunk(0, 1))


def test_all_transform_arenas_receive_same_window_but_keep_independent_counts():
    release = TransformRangeRelease((), 7, 3, ARENA_OPERATIONS, (7, 8, 9))
    states = {
        name: ArenaState(10 if i % 2 == 0 else 20, ())
        for i, (name, _, _) in enumerate(ARENA_OPERATIONS)
    }
    result = apply_transform_arena_removals(release, states)
    for i, (name, _, _) in enumerate(ARENA_OPERATIONS):
        assert result[name] == ArenaState(7 if i % 2 == 0 else 20, (ArenaChunk(7, 3),))
    assert all(state.empty_chunks == () for state in states.values())


def test_transform_arena_bridge_rejects_missing_inputs_and_unknown_operation_order():
    release = TransformRangeRelease((), 7, 3, ARENA_OPERATIONS, (7, 8, 9))
    with pytest.raises(ValueError, match="arena"):
        apply_transform_arena_removals(release, {})
    with pytest.raises(ValueError, match="operation"):
        apply_transform_arena_removals(TransformRangeRelease((), 0, 1, (), (0,)), {})
