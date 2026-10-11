"""Sealed two-state references -> fresh candidate core Team/chunk layout.

Only nine independently evidenced arenas are published. Sequential Team IDs
and prefix starts are an explicit empty-candidate policy, not official runtime
IDs/chunks or a recovered native allocator. No Unity/DLL execution occurs.
"""

import argparse
import hashlib
import json
import re
from pathlib import Path
from typing import Any

from official_physics_particle_registration import (
    PARTICLE_ARRAY_FIELDS,
    ParticleAllocation,
    plan_particle_registration,
)
from official_physics_team_layout import (
    CandidateCoreGroup,
    Chunk,
    build_fresh_candidate_core_layout,
)
from official_physics_work_lists import StepTeam, build_step_work_lists


def _name(value: Any) -> str:
    if not isinstance(value, str) or not value:
        raise ValueError("Reference requires a nonempty name/identity")
    return value


def _chunk(value: Chunk) -> dict[str, int]:
    return {"start": value.start, "count": value.count}


def _groups_for_state(
    source_state: dict[str, Any],
    baseline_state: dict[str, Any],
    distance_state: dict[str, Any],
) -> tuple[CandidateCoreGroup, ...]:
    if not (
        _name(source_state["name"])
        == _name(baseline_state["name"])
        == _name(distance_state["name"])
    ):
        raise ValueError("Reference state names/order disagree")
    sources = source_state["groups"]
    baselines = baseline_state["groups"]
    distances = distance_state["groups"]
    if not sources or not (len(sources) == len(baselines) == len(distances)):
        raise ValueError("Reference state requires aligned nonempty groups")
    result = []
    for source, baseline, distance in zip(sources, baselines, distances, strict=True):
        label = _name(source["name"])
        identity = _name(source["component_identity"])
        if (label, identity) != (
            _name(baseline["name"]),
            _name(baseline["component_identity"]),
        ) or (label, identity) != (
            _name(distance["name"]),
            _name(distance["component_identity"]),
        ):
            raise ValueError("Reference group identity/order disagree")
        count = source["skin_bone_count"]
        if (
            type(count) is not int
            or count <= 0
            or baseline["skin_bone_count"] != count
            or distance["skin_bone_count"] != count
            or len(source["runtime_instance_ids"]) != count + 1
        ):
            raise ValueError("Reference skin/render domains disagree")
        baseline_rows = baseline["baselines"]
        baseline_count = len(baseline_rows["flags"])
        if not (
            baseline_count
            == len(baseline_rows["starts"])
            == len(baseline_rows["counts"])
        ):
            raise ValueError("Reference baseline rows disagree")
        distance_rows = distance["distance"]
        words = distance_rows["words"]
        data = distance_rows["data"]
        lengths = distance_rows["signed_rest_lengths"]
        if words is None or data is None or lengths is None:
            raise ValueError("Candidate core layout requires allocated distance rows")
        if len(words) != count or len(data) != len(lengths):
            raise ValueError("Reference distance start/data domains disagree")
        result.append(
            CandidateCoreGroup(
                name=label,
                component_identity=identity,
                proxy_transform_count=count + 1,
                proxy_common_count=count,
                proxy_mesh_count=count,
                proxy_skin_bone_count=count,
                baseline_count=baseline_count,
                baseline_data_count=len(baseline_rows["data"]),
                particle_count=count,
                distance_start_count=count,
                distance_data_count=len(data),
            )
        )
    return tuple(result)


def build_document(
    imports: dict[str, Any],
    baselines: dict[str, Any],
    distances: dict[str, Any],
    *,
    fresh_empty_arenas: bool,
    sequential_candidate_team_ids: bool,
) -> dict[str, Any]:
    """Build one topology-invariant layout from matching sealed states."""
    try:
        if fresh_empty_arenas is not True or sequential_candidate_team_ids is not True:
            raise ValueError("Require explicit fresh/sequential candidate premises")
        documents = (imports, baselines, distances)
        if any(
            type(document["schema_version"]) is not int
            or document["schema_version"] != 1
            for document in documents
        ):
            raise ValueError("Require schema version 1 reference documents")
        if not (
            imports["getter_scope"]
            == baselines["getter_scope"]
            == distances["getter_scope"]
        ):
            raise ValueError("Reference getter scopes disagree")
        if (
            imports["full_proxy_inputs_generated"] is not False
            or baselines["baseline_reference_generated"] is not True
            or baselines["full_proxy_inputs_generated"] is not False
            or distances["distance_reference_generated"] is not True
            or distances["full_proxy_inputs_generated"] is not False
        ):
            raise ValueError("Reference producer boundary flags disagree")
        state_sets = tuple(document["states"] for document in documents)
        if not state_sets[0] or not (
            len(state_sets[0]) == len(state_sets[1]) == len(state_sets[2])
        ):
            raise ValueError("Require matching nonempty reference states")
        topologies = tuple(
            _groups_for_state(*states) for states in zip(*state_sets, strict=True)
        )
        if any(topology != topologies[0] for topology in topologies[1:]):
            raise ValueError("Reference state topology/counts drift")
        groups = topologies[0]
        if len(groups) > 32767:
            raise ValueError("Sequential candidate Team IDs exceed positive Int16")
        identifiers = tuple(range(1, len(groups) + 1))
        layout = build_fresh_candidate_core_layout(
            groups,
            team_ids=identifiers,
            fresh_empty_arenas=fresh_empty_arenas,
        )
        registrations = []
        step_teams = {}
        for team in layout.teams:
            allocation = ParticleAllocation(team.particle.start, team.particle.count)
            registration = plan_particle_registration(
                team.particle.count,
                team.team_id,
                {name: allocation for name in PARTICLE_ARRAY_FIELDS},
                manager_valid=True,
                array_capacities={
                    name: layout.capacities["particle"]
                    for name in PARTICLE_ARRAY_FIELDS
                },
            )
            registrations.append(
                {
                    "team_id": team.team_id,
                    "original_team_id": registration.original_team_id,
                    "team_fill_value": registration.team_fill_value,
                    "particle_chunk": _chunk(team.particle),
                    "array_add_order": list(PARTICLE_ARRAY_FIELDS),
                }
            )
            # 0xaf is an explicitly composed candidate stepping state:
            # fresh AddTeam 0x0d + Enable bit2 + supplied Running20/Step80.
            step_teams[team.team_id] = StepTeam(
                0xAF,
                team.particle.start,
                team.particle.count,
                team.baseline.start,
                team.baseline.count,
            )
        work = build_step_work_lists(
            step_teams,
            particle_team_order=identifiers,
            baseline_team_order=identifiers,
            particle_output_capacity=layout.capacities["particle"],
            baseline_output_capacity=layout.capacities["baseline"],
        )
        teams = []
        for team in layout.teams:
            teams.append(
                {
                    "team_id": team.team_id,
                    "name": team.name,
                    "component_identity": team.component_identity,
                    **{
                        arena: _chunk(getattr(team, arena))
                        for arena in layout.capacities
                    },
                }
            )
        return {
            "schema_version": 1,
            "getter_scope": imports["getter_scope"],
            "state_names": [state["name"] for state in state_sets[0]],
            "team_ids": list(identifiers),
            "team_id_policy": "caller candidate sequential 1..N in sealed group order; not observed runtime IDs",
            "arena_policy": "independent serial prefix cursors in a freshly empty candidate manager; not the native allocator/free-list",
            "supported_core_arenas": list(layout.capacities),
            "unsupported_team_chunks_omitted": True,
            "candidate_flags": {
                "add_team": 0x0D,
                "enabled_reset": 0x0F,
                "supplied_running_step": 0xAF,
            },
            "teams": teams,
            "capacities": layout.capacities,
            "particle_registration_plans": registrations,
            "candidate_work_lists": {
                "particle_indices": list(work.particle_indices),
                "baseline_indices": list(work.baseline_indices),
            },
            "fresh_candidate_core_layout_generated": True,
            "state_topology_invariant": True,
            "original_runtime_team_ids_observed": False,
            "original_runtime_chunks_observed": False,
            "native_arrays_published": False,
            "official_solver_integrated": False,
            "original_runtime_executed": False,
            "stage_modified": False,
        }
    except (KeyError, TypeError, IndexError) as exc:
        raise ValueError("Reference document is incomplete or malformed") from exc


def export_file(
    imports: Path,
    baselines: Path,
    distances: Path,
    output: Path,
    seals: tuple[str, ...],
    *,
    fresh_empty_arenas: bool,
    sequential_candidate_team_ids: bool,
) -> None:
    if len(seals) != 3 or any(
        re.fullmatch(r"[0-9a-f]{64}", seal) is None for seal in seals
    ):
        raise ValueError("Require three explicit lowercase SHA256 seals")
    if output.exists():
        raise FileExistsError(f"Refusing to overwrite {output}")
    paths = (imports, baselines, distances)
    raw = tuple(path.read_bytes() for path in paths)
    if any(
        hashlib.sha256(data).hexdigest() != seal
        for data, seal in zip(raw, seals, strict=True)
    ):
        raise ValueError("Reference input differs from explicit seal")
    result = build_document(
        *(json.loads(data) for data in raw),
        fresh_empty_arenas=fresh_empty_arenas,
        sequential_candidate_team_ids=sequential_candidate_team_ids,
    )
    result["input_sha256"] = dict(
        zip(("imports", "baselines", "distances"), seals, strict=True)
    )
    with output.open("x", encoding="utf-8", newline="\n") as stream:
        json.dump(result, stream, ensure_ascii=False, indent=2, allow_nan=False)
        stream.write("\n")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ("imports", "baselines", "distances"):
        parser.add_argument("--" + name, type=Path, required=True)
        parser.add_argument("--" + name + "-sha256", required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--fresh-empty-arenas", action="store_true", required=True)
    parser.add_argument(
        "--sequential-candidate-team-ids", action="store_true", required=True
    )
    args = parser.parse_args()
    export_file(
        args.imports,
        args.baselines,
        args.distances,
        args.output,
        (args.imports_sha256, args.baselines_sha256, args.distances_sha256),
        fresh_empty_arenas=args.fresh_empty_arenas,
        sequential_candidate_team_ids=args.sequential_candidate_team_ids,
    )
    print(f"Candidate core Team layout exported: {args.output}")


if __name__ == "__main__":
    main()
