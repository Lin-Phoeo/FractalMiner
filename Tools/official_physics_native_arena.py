"""Finite ExNativeArray free-list bookkeeping, NOT native memory allocation.

AddEmptyChunk371330: one first predecessor match, then one first successor,
ListExtensions.RemoveAtSwapBack, append merged chunk; no sorting/recursive normalization.
GetEmptyChunk371329: first fit in list order, exact removes, larger splits from
the front in the SAME list slot. Nonpositive/no-fit returns packed zero chunk.
Remove371317: merge only for positive length; iff ORIGINAL removed end equals
useCount, reset to zero then max free-chunk START, not end or active-count sum.

Finite nonnegative/no-overflow owned windows and detached copies are adapter
policy, not native invalid-input/fault/Int32-overflow/partial-write equivalence.
ArenaState has no implicit defaults. Snapshot free-list ordering is explicit.
No buffer fill, native allocator/capacity/reallocation, useCount growth at outer
AddRange, physical storage lifetime, concurrent Job, GCHandle or Unity effects.
The Transform bridge applies logical removals only; previous native_allocator
flag remains false and inactive pose bytes are not certified as preserved.
"""

from collections.abc import Mapping
from dataclasses import dataclass

from official_physics_registration import _int32
from official_physics_transform_release import ARENA_OPERATIONS, TransformRangeRelease


@dataclass(frozen=True)
class ArenaChunk:
    start: int
    length: int


@dataclass(frozen=True)
class ArenaState:
    use_count: int
    empty_chunks: tuple[ArenaChunk, ...]


@dataclass(frozen=True)
class ArenaReuse:
    chunk: ArenaChunk
    state: ArenaState | None


def _window(chunk: ArenaChunk) -> None:
    start, length = _int32(chunk.start), _int32(chunk.length)
    if start < 0 or length <= 0 or start + length > 2**31 - 1:
        raise ValueError("Adapter requires finite owned arena chunk window")


def _free(state: ArenaState | None) -> list[ArenaChunk]:
    if state is None:
        raise ValueError("Adapter requires explicit arena state capture")
    chunks = list(state.empty_chunks)
    for chunk in chunks:
        _window(chunk)
    return chunks


def _swap_back(chunks: list[ArenaChunk], index: int) -> None:
    chunks[index] = chunks[-1]
    chunks.pop()


def add_empty_chunk(state: ArenaState | None, chunk: ArenaChunk) -> ArenaState | None:
    """Two successful source merge passes; does not change useCount."""
    if _int32(chunk.length) <= 0:
        return state
    _window(chunk)
    chunks = _free(state)
    assert state is not None
    for index, previous in enumerate(chunks):
        if previous.start + previous.length == chunk.start:
            chunk = ArenaChunk(previous.start, previous.length + chunk.length)
            _swap_back(chunks, index)
            break
    for index, following in enumerate(chunks):
        if following.start == chunk.start + chunk.length:
            chunk = ArenaChunk(chunk.start, chunk.length + following.length)
            _window(chunk)
            _swap_back(chunks, index)
            break
    chunks.append(chunk)
    return ArenaState(state.use_count, tuple(chunks))


def remove_native_chunk(
    state: ArenaState | None, chunk: ArenaChunk
) -> ArenaState | None:
    """Logical Remove only: native storage and capacity are not removed here."""
    if _int32(chunk.length) <= 0:
        return state
    updated = add_empty_chunk(state, chunk)
    assert updated is not None and state is not None
    count = _int32(state.use_count)
    if chunk.start + chunk.length == count:
        count = max((free.start for free in updated.empty_chunks), default=0)
    return ArenaState(count, updated.empty_chunks)


def take_empty_chunk(state: ArenaState | None, requested: int) -> ArenaReuse:
    """GetEmptyChunk only; the outer AddRange updates count/capacity separately."""
    if _int32(requested) <= 0:
        return ArenaReuse(ArenaChunk(0, 0), state)
    chunks = _free(state)
    assert state is not None
    for index, chunk in enumerate(chunks):
        if requested == chunk.length:
            _swap_back(chunks, index)
            return ArenaReuse(chunk, ArenaState(state.use_count, tuple(chunks)))
        if requested < chunk.length:
            chunks[index] = ArenaChunk(
                chunk.start + requested, chunk.length - requested
            )
            return ArenaReuse(
                ArenaChunk(chunk.start, requested),
                ArenaState(state.use_count, tuple(chunks)),
            )
    return ArenaReuse(ArenaChunk(0, 0), state)


def apply_transform_arena_removals(
    release: TransformRangeRelease, arenas: Mapping[str, ArenaState]
) -> dict[str, ArenaState]:
    """Connect all fourteen described removals to independent logical states.

    Fill/access/physical allocator/array publication remain outside this API.
    Missing selected inputs cannot silently become an empty allocator state.
    """
    if release.arena_operations != ARENA_OPERATIONS:
        raise ValueError("Adapter requires exact Transform arena operation sequence")
    result = dict(arenas)
    chunk = ArenaChunk(release.start, release.length)
    _window(chunk)
    for name, _, _ in release.arena_operations:
        if name not in result:
            raise ValueError("Adapter requires every selected Transform arena state")
        state = remove_native_chunk(result[name], chunk)
        assert state is not None
        result[name] = state
    return result
