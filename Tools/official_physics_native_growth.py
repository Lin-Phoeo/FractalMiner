"""Finite ExNativeArray AddRange/Expand/Fill snapshot reference.

This layer models the source-visible logical capacity, detached cell contents,
useCount and emptyChunks updates. It does not allocate or dispose NativeArray,
run jobs, preserve allocator handles, emulate exceptions, or touch Unity.

AddRange first uses GetEmptyChunk. Without a fit, the source grows capacity to
``old_capacity + max(requested, old_capacity)``, ClearMemory-initializes the new
array, copies the old capacity, disposes the old array and records unused tail
capacity as an empty chunk. The typed overload fills only the returned chunk.
Expand allocates a new full-size chunk, copies the old prefix, then removes the
old chunk without clearing its detached cells.

Explicit ``clear_value`` is adapter policy: it represents the caller's typed
interpretation of zeroed bytes and avoids pretending every value type's default
is Python integer zero. Safe bounded snapshots are not native fault equivalence.
"""

from dataclasses import dataclass
from typing import Any

from official_physics_native_arena import (
    ArenaChunk,
    ArenaReuse,
    ArenaState,
    add_empty_chunk,
    remove_native_chunk,
    take_empty_chunk,
)
from official_physics_registration import _int32


@dataclass(frozen=True)
class ArenaBufferState:
    created: bool
    cells: tuple[Any, ...]
    arena: ArenaState


@dataclass(frozen=True)
class ArenaAllocation:
    chunk: ArenaChunk
    state: ArenaBufferState


def _checked_state(state: ArenaBufferState) -> int:
    capacity = len(state.cells)
    if capacity > 2**31 - 1:  # pragma: no cover - impossible host tuple size
        raise ValueError("Adapter capacity must fit signed Int32")
    count = _int32(state.arena.use_count)
    if not state.created and (capacity or count or state.arena.empty_chunks):
        raise ValueError("Uncreated adapter snapshot cannot contain arena state")
    if count < 0 or count > capacity:
        raise ValueError("Adapter useCount must be within created capacity")
    for chunk in state.arena.empty_chunks:
        start, length = _int32(chunk.start), _int32(chunk.length)
        if start < 0 or length <= 0 or start + length > capacity:
            raise ValueError("Adapter free chunk must fit created capacity")
    return capacity


def _request(value: int) -> int:
    result = _int32(value)
    if result < 0:
        raise ValueError("Adapter requires nonnegative AddRange length")
    return result


def _positive_window(chunk: ArenaChunk, capacity: int) -> tuple[int, int]:
    start, length = _int32(chunk.start), _int32(chunk.length)
    if start < 0 or length <= 0 or start + length > capacity:
        raise ValueError("Adapter chunk must fit created capacity")
    return start, length


def _replace_arena(state: ArenaBufferState, arena: ArenaState) -> ArenaBufferState:
    return ArenaBufferState(state.created, state.cells, arena)


def add_range(
    state: ArenaBufferState, requested: int, *, clear_value: Any
) -> ArenaAllocation:
    """Model AddRange(Int32) without native allocation or disposal side effects."""
    capacity = _checked_state(state)
    requested = _request(requested)
    if requested == 0:
        if state.created:
            return ArenaAllocation(ArenaChunk(0, 0), state)
        return ArenaAllocation(
            ArenaChunk(0, 0), ArenaBufferState(True, (), state.arena)
        )

    reuse: ArenaReuse = take_empty_chunk(state.arena, requested)
    if reuse.chunk.length > 0:
        assert reuse.state is not None
        end = reuse.chunk.start + reuse.chunk.length
        arena = ArenaState(max(state.arena.use_count, end), reuse.state.empty_chunks)
        return ArenaAllocation(reuse.chunk, _replace_arena(state, arena))

    growth = max(requested, capacity)
    new_capacity = capacity + growth
    if new_capacity > 2**31 - 1:
        raise ValueError("Adapter capacity growth exceeds signed Int32")
    cells = state.cells + (clear_value,) * growth
    chunk = ArenaChunk(capacity, requested)
    arena: ArenaState | None = state.arena
    tail_length = new_capacity - (capacity + requested)
    if tail_length > 0:
        arena = add_empty_chunk(arena, ArenaChunk(capacity + requested, tail_length))
    assert arena is not None
    arena = ArenaState(max(arena.use_count, capacity + requested), arena.empty_chunks)
    return ArenaAllocation(chunk, ArenaBufferState(True, cells, arena))


def fill_chunk(
    state: ArenaBufferState, chunk: ArenaChunk, fill_value: Any
) -> ArenaBufferState:
    """Model Fill(DataChunk,T): invalid storage and nonpositive size are no-ops."""
    capacity = _checked_state(state)
    if not state.created:
        return state
    length = _int32(chunk.length)
    if length <= 0:
        return state
    start, _ = _positive_window(chunk, capacity)
    cells = list(state.cells)
    cells[start : start + length] = (fill_value,) * length
    return ArenaBufferState(True, tuple(cells), state.arena)


def add_range_and_fill(
    state: ArenaBufferState,
    requested: int,
    fill_value: Any,
    *,
    clear_value: Any,
) -> ArenaAllocation:
    """Model AddRange(Int32,T): allocate first, then fill exactly that chunk."""
    allocation = add_range(state, requested, clear_value=clear_value)
    return ArenaAllocation(
        allocation.chunk,
        fill_chunk(allocation.state, allocation.chunk, fill_value),
    )


def expand_chunk(
    state: ArenaBufferState,
    chunk: ArenaChunk,
    new_length: int,
    *,
    clear_value: Any,
) -> ArenaAllocation:
    """Model Expand(DataChunk,Int32), including allocate-copy-remove ordering."""
    capacity = _checked_state(state)
    old_length = _int32(chunk.length)
    if old_length <= 0:
        return ArenaAllocation(chunk, state)
    new_length = _int32(new_length)
    if new_length <= old_length:
        return ArenaAllocation(chunk, state)
    old_start, _ = _positive_window(chunk, capacity)
    source = state.cells[old_start : old_start + old_length]
    allocation = add_range(state, new_length, clear_value=clear_value)
    destination = allocation.chunk.start
    cells = list(allocation.state.cells)
    cells[destination : destination + old_length] = source
    arena = remove_native_chunk(allocation.state.arena, chunk)
    assert arena is not None
    return ArenaAllocation(
        allocation.chunk,
        ArenaBufferState(allocation.state.created, tuple(cells), arena),
    )
