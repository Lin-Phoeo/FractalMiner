"""Fresh candidate core Team/chunk layout over explicit finite counts.

This is a deterministic adapter policy for a newly-created empty candidate
manager. It is NOT the original native allocator, its free-list, observed Team
IDs, or a publication into Unity NativeArrays. Every supported arena has an
independent prefix cursor. Unsupported Team chunks are deliberately absent.
"""

from collections.abc import Sequence
from dataclasses import dataclass

_INT32_MAX = 2**31 - 1


@dataclass(frozen=True)
class Chunk:
    start: int
    count: int


@dataclass(frozen=True)
class CandidateCoreGroup:
    name: str
    component_identity: str
    proxy_transform_count: int
    proxy_common_count: int
    proxy_mesh_count: int
    proxy_skin_bone_count: int
    baseline_count: int
    baseline_data_count: int
    particle_count: int
    distance_start_count: int
    distance_data_count: int


@dataclass(frozen=True)
class CandidateCoreTeam:
    team_id: int
    name: str
    component_identity: str
    proxy_transform: Chunk
    proxy_common: Chunk
    proxy_mesh: Chunk
    proxy_skin_bone: Chunk
    baseline: Chunk
    baseline_data: Chunk
    particle: Chunk
    distance_start: Chunk
    distance_data: Chunk


@dataclass(frozen=True)
class CandidateCoreLayout:
    teams: tuple[CandidateCoreTeam, ...]
    capacities: dict[str, int]


_ARENAS = (
    "proxy_transform",
    "proxy_common",
    "proxy_mesh",
    "proxy_skin_bone",
    "baseline",
    "baseline_data",
    "particle",
    "distance_start",
    "distance_data",
)


def _count(value: int) -> int:
    if type(value) is not int or not 0 <= value <= _INT32_MAX:
        raise ValueError("Candidate layout requires a nonnegative Int32 count")
    return value


def _label(value: str) -> str:
    if not isinstance(value, str) or not value:
        raise ValueError("Candidate layout requires nonempty string identities")
    return value


def _validated(group: CandidateCoreGroup) -> CandidateCoreGroup:
    if not isinstance(group, CandidateCoreGroup):
        raise ValueError(  # noqa: TRY004
            "Candidate layout requires explicit core group records"
        )
    _label(group.name)
    _label(group.component_identity)
    values = {field: _count(getattr(group, field + "_count")) for field in _ARENAS}
    common = values["proxy_common"]
    if not common:
        raise ValueError("Candidate core group requires at least one proxy vertex")
    if (
        values["proxy_transform"] != common + 1
        or values["proxy_mesh"] != common
        or values["proxy_skin_bone"] != common
        or values["particle"] != common
        or values["distance_start"] != common
    ):
        raise ValueError(
            "Candidate core domains require skin+render transforms and matching vertex rows"
        )
    return group


def build_fresh_candidate_core_layout(
    groups: Sequence[CandidateCoreGroup],
    *,
    team_ids: Sequence[int],
    fresh_empty_arenas: bool,
) -> CandidateCoreLayout:
    """Allocate supported core arenas by independent serial prefix cursors.

    Team IDs are caller-supplied candidate identities. The function neither
    predicts DynamicArray.Add/free-list results nor claims native allocator
    alignment. Exact fresh-empty and serial ordering are mandatory premises.
    """
    if fresh_empty_arenas is not True:
        raise ValueError("Require an explicitly fresh empty candidate manager")
    records = tuple(_validated(group) for group in groups)
    identifiers = tuple(team_ids)
    if not records or len(records) != len(identifiers):
        raise ValueError("Require matching nonempty group and Team ID sequences")
    if len({group.name for group in records}) != len(records) or len(
        {group.component_identity for group in records}
    ) != len(records):
        raise ValueError(
            "Candidate group names and component identities must be unique"
        )
    if any(type(value) is not int or not 1 <= value <= 32767 for value in identifiers):
        raise ValueError("Candidate Team IDs must be positive Int16 values")
    if len(set(identifiers)) != len(identifiers):
        raise ValueError("Candidate Team IDs must be unique")

    cursors = {name: 0 for name in _ARENAS}
    teams = []
    for identifier, group in zip(identifiers, records, strict=True):
        chunks = {}
        for arena in _ARENAS:
            count = getattr(group, arena + "_count")
            start = cursors[arena]
            if start + count > _INT32_MAX:
                raise ValueError("Candidate core arena exceeds nonnegative Int32 slots")
            chunks[arena] = Chunk(start, count)
            cursors[arena] = start + count
        teams.append(
            CandidateCoreTeam(
                team_id=identifier,
                name=group.name,
                component_identity=group.component_identity,
                **chunks,
            )
        )
    return CandidateCoreLayout(tuple(teams), cursors)
