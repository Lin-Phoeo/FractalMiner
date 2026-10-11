"""Finite particle/baseline work-list production over GIVEN sparse Team chunks.

CreateUpdateParticleList ordinary Execute(index)370620/0x5a6f838 and actual
non-Burst managed fallback370422/0x5a58a28. Native atomic counters reserve an
ascending block per eligible Team, but cross-Team order can differ per list.
This publishes logical prefixes after explicit cleared-counter premises; it
does not allocate native buffers, clear array tails, infer Team/clock state,
produce sibling lists or claim actual parallel/Burst scheduling.
"""

from collections import Counter
from collections.abc import Mapping, Sequence
from dataclasses import dataclass

_INT32_MAX = 2**31 - 1
_REQUIRED_FLAGS = 0xA2
_EXCLUDED_FLAGS = (1 << 61) | 0x10 | 0x800 | 0x80000


@dataclass(frozen=True)
class StepTeam:
    flag: int  # TeamData unboxed @0, UInt64.
    particle_start: int  # particleChunk @372.
    particle_count: int  # @376.
    baseline_start: int  # baseLineChunk @348; GLOBAL baseline, not data slot.
    baseline_count: int  # @352.


@dataclass(frozen=True)
class StepWorkLists:
    particle_indices: tuple[int, ...]
    baseline_indices: tuple[int, ...]


def _bounded(value: int, maximum: int) -> int:
    if type(value) is not int or not 0 <= value <= maximum:
        raise ValueError("Adapter requires an actual nonnegative bounded integer")
    return value


def _selected(
    teams: Mapping[int, StepTeam], order: Sequence[int]
) -> tuple[tuple[int, StepTeam], ...]:
    selected = []
    for slot in order:
        if slot == 0:
            continue  # Native Team0 gate precedes the Team-data read.
        if slot not in teams:
            raise ValueError("Adapter requires every selected sparse Team slot")
        team = teams[slot]
        flag = _bounded(team.flag, 2**64 - 1)
        if flag & _REQUIRED_FLAGS == _REQUIRED_FLAGS and not flag & _EXCLUDED_FLAGS:
            selected.append((slot, team))
    return tuple(selected)


def _chunk(start: int, count: int) -> tuple[int, int]:
    start, count = _bounded(start, _INT32_MAX), _bounded(count, _INT32_MAX)
    if count and start + count - 1 > _INT32_MAX:
        raise ValueError("Adapter chunk exceeds nonnegative Int32 global slots")
    return start, count


def build_step_work_lists(
    teams: Mapping[int, StepTeam],
    *,
    particle_team_order: Sequence[int],
    baseline_team_order: Sequence[int],
    particle_output_capacity: int,
    baseline_output_capacity: int,
) -> StepWorkLists:
    """Publish the two finite logical prefixes using separate GIVEN block orders.

    No attributes/root filtering: include the WHOLE particle and baseline chunks.
    Preserve duplicate blocks in the explicit reference schedule, not an assertion
    that the ordinary Job visits duplicates (it visits each Team ordinal once).
    The orders' equal nonzero-slot multisets are adapter consistency policy, not
    a native gate. Team slot<=65535, nonnegative Int32 chunk/counter, explicit
    output capacities and no slot overflow are also adapter policies; native
    signed atomics/wrap/fault/alias behavior is not simulated. Low16 GLOBAL
    baseline truncation IS preserved.

    Both counters are explicitly represented as initially zero; no observed game
    counter state, shared ordering between independent native atomic reservations,
    array capacity/tails, raw read timing or sibling-list completeness is claimed.
    """
    particle_order = tuple(_bounded(slot, 65535) for slot in particle_team_order)
    baseline_order = tuple(_bounded(slot, 65535) for slot in baseline_team_order)
    if Counter(slot for slot in particle_order if slot) != Counter(
        slot for slot in baseline_order if slot
    ):
        raise ValueError("Adapter orders must select the same Team slot multiset")
    particle_capacity = _bounded(particle_output_capacity, _INT32_MAX)
    baseline_capacity = _bounded(baseline_output_capacity, _INT32_MAX)
    particle_teams = _selected(teams, particle_order)
    baseline_teams = _selected(teams, baseline_order)
    particles = tuple(
        _chunk(team.particle_start, team.particle_count) for _, team in particle_teams
    )
    baselines = tuple(
        (slot, *_chunk(team.baseline_start, team.baseline_count))
        for slot, team in baseline_teams
    )
    # Check both counters before allocating either output prefix.
    particle_total = sum(count for _, count in particles)
    baseline_total = sum(count for _, _, count in baselines)
    if particle_total > _INT32_MAX or baseline_total > _INT32_MAX:
        raise ValueError("Adapter work-list counter exceeds nonnegative Int32")
    if particle_total > particle_capacity or baseline_total > baseline_capacity:
        raise ValueError("Adapter work-list exceeds explicit output capacity")

    def pack(slot: int, baseline: int) -> int:
        word = (slot << 16) | (baseline & 65535)
        return word - 2**32 if word >= 2**31 else word

    return StepWorkLists(
        tuple(start + local for start, count in particles for local in range(count)),
        tuple(
            pack(slot, start + local)
            for slot, start, count in baselines
            for local in range(count)
        ),
    )
