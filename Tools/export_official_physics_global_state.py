"""Sealed local Team1 world/reset references -> candidate global state.

This remaps already-verified payloads without recomputing floating-point math.
It accepts only the former independent zero-based experiment groups and one
fresh contiguous candidate core layout. No native arrays or Unity state are
written, and the two saved states are not claimed to be continuous animation.
"""

import argparse
import hashlib
import json
import re
from copy import deepcopy
from pathlib import Path
from typing import Any

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
_WRITES = (
    "next_position",
    "old_position",
    "old_rotation",
    "base_position",
    "base_rotation",
    "old_animation_position",
    "old_animation_rotation",
    "velocity_position",
    "display_position",
    "velocity",
    "real_velocity",
    "friction",
    "static_friction",
    "collision_normal",
)
_INT32_MAX = 2**31 - 1


def _name(value: Any) -> str:
    if not isinstance(value, str) or not value:
        raise ValueError("Global candidate requires nonempty names/identities")
    return value


def _integer(value: Any, maximum: int = _INT32_MAX) -> int:
    if type(value) is not int or not 0 <= value <= maximum:
        raise ValueError("Global candidate requires a nonnegative bounded integer")
    return value


def _window(value: Any) -> tuple[int, int]:
    if not isinstance(value, dict) or set(value) != {"start", "count"}:
        raise ValueError("Global candidate requires explicit start/count windows")
    start, count = _integer(value["start"]), _integer(value["count"])
    if start + count > _INT32_MAX:
        raise ValueError("Global candidate window exceeds nonnegative Int32 slots")
    return start, count


def _layout_teams(layout: dict[str, Any]) -> tuple[dict[str, Any], ...]:
    if (
        layout["fresh_candidate_core_layout_generated"] is not True
        or layout["state_topology_invariant"] is not True
        or layout["original_runtime_team_ids_observed"] is not False
        or layout["original_runtime_chunks_observed"] is not False
        or layout["native_arrays_published"] is not False
    ):
        raise ValueError("Require the bounded fresh candidate layout boundary")
    capacities = layout["capacities"]
    if not isinstance(capacities, dict) or tuple(capacities) != _ARENAS:
        raise ValueError("Candidate layout arena order/set differs")
    checked_capacities = {arena: _integer(capacities[arena]) for arena in _ARENAS}
    teams = tuple(layout["teams"])
    ids = tuple(layout["team_ids"])
    if not teams or len(teams) != len(ids):
        raise ValueError("Candidate layout requires matching Teams and IDs")
    cursors = {arena: 0 for arena in _ARENAS}
    names, identities = set(), set()
    for expected, (identifier, team) in enumerate(
        zip(ids, teams, strict=True), start=1
    ):
        if identifier != expected or team["team_id"] != identifier:
            raise ValueError("Require sequential positive candidate Team IDs")
        label = _name(team["name"])
        identity = _name(team["component_identity"])
        if label in names or identity in identities:
            raise ValueError("Candidate Team names/identities must be unique")
        names.add(label)
        identities.add(identity)
        windows = {}
        for arena in _ARENAS:
            start, count = _window(team[arena])
            if start != cursors[arena]:
                raise ValueError("Candidate core arenas must be gapless in Team order")
            cursors[arena] += count
            windows[arena] = count
        common = windows["proxy_common"]
        if (
            not common
            or windows["proxy_transform"] != common + 1
            or windows["proxy_mesh"] != common
            or windows["proxy_skin_bone"] != common
            or windows["particle"] != common
            or windows["distance_start"] != common
        ):
            raise ValueError("Candidate Team core vertex domains disagree")
    if cursors != checked_capacities:
        raise ValueError("Candidate Team windows do not cover declared capacities")
    return teams


def _local_group(
    group: dict[str, Any], team: dict[str, Any]
) -> tuple[list[Any], list[Any], list[dict[str, Any]]]:
    if (_name(group["name"]), _name(group["component_identity"])) != (
        _name(team["name"]),
        _name(team["component_identity"]),
    ):
        raise ValueError("Local world/reset group identity/order disagrees")
    _, count = _window(team["proxy_common"])
    if group["skin_bone_count"] != count:
        raise ValueError("Local world/reset skin domain disagrees with Team")
    experiment = group["experiment_team"]
    if experiment != {
        "flag": 15,
        "proxy_transform_start": 0,
        "proxy_common_start": 0,
        "proxy_common_count": count,
        "proxy_mesh_start": 0,
        "proxy_skin_bone_start": 0,
    }:
        raise ValueError("Require the sealed independent Team1 zero-based experiment")
    world = group["world"]
    positions, rotations = world["positions"], world["rotations"]
    if (
        len(positions) != count
        or len(rotations) != count
        or world["written_vertices"] != list(range(count))
    ):
        raise ValueError("Local world payload must cover its complete ascending domain")
    reset = group["reset"]
    states, results = reset["states"], reset["results"]
    if (
        reset["particle_start"] != 0
        or reset["fully_reset"] is not True
        or len(states) != count
        or len(results) != count
    ):
        raise ValueError("Local reset payload must be a complete zero-based window")
    for local, (state, result) in enumerate(zip(states, results, strict=True)):
        if (
            result["proxy_index"] != local
            or result["reset_applied"] is not True
            or tuple(result["writes"]) != _WRITES
            or result["state"] != state
        ):
            raise ValueError("Local reset result/state/write order disagrees")
    return positions, rotations, results


def build_document(
    world_reset: dict[str, Any],
    layout: dict[str, Any],
    *,
    candidate_global_remap: bool,
) -> dict[str, Any]:
    """Remap sealed local payloads into global proxy/particle slot arrays."""
    try:
        if candidate_global_remap is not True:
            raise ValueError("Require an explicit candidate global remap premise")
        if world_reset["schema_version"] != 1 or layout["schema_version"] != 1:
            raise ValueError("Require schema version 1 inputs")
        if world_reset["getter_scope"] != layout["getter_scope"]:
            raise ValueError("World/reset and candidate layout scopes disagree")
        if world_reset["input_sha256"]["imports"] != layout["input_sha256"]["imports"]:
            raise ValueError("World/reset and candidate layout imports disagree")
        if (
            world_reset["supplied_input_world_reference_generated"] is not True
            or world_reset["supplied_world_first_reset_reference_generated"] is not True
            or world_reset["full_proxy_inputs_generated"] is not False
            or world_reset["native_arrays_published"] is not False
            or world_reset["official_solver_integrated"] is not False
            or world_reset["changing_animation_verified"] is not False
            or world_reset["original_runtime_executed"] is not False
            or world_reset["stage_modified"] is not False
        ):
            raise ValueError("World/reset reference boundary flags disagree")
        teams = _layout_teams(layout)
        states = tuple(world_reset["states"])
        state_names = tuple(layout["state_names"])
        if not states or len(states) != len(state_names):
            raise ValueError("World/reset states disagree with candidate layout")
        proxy_capacity = _integer(layout["capacities"]["proxy_common"])
        particle_capacity = _integer(layout["capacities"]["particle"])
        outputs = []
        for expected_name, source in zip(state_names, states, strict=True):
            if _name(source["name"]) != _name(expected_name):
                raise ValueError("World/reset state identity/order disagrees")
            groups = tuple(source["groups"])
            if len(groups) != len(teams):
                raise ValueError("World/reset group count disagrees with layout")
            positions: list[Any | None] = [None] * proxy_capacity
            rotations: list[Any | None] = [None] * proxy_capacity
            proxy_teams: list[int | None] = [None] * proxy_capacity
            particle_states: list[Any | None] = [None] * particle_capacity
            particle_teams: list[int | None] = [None] * particle_capacity
            reset_results: list[Any | None] = [None] * particle_capacity
            remapped_groups = []
            written = []
            for group, team in zip(groups, teams, strict=True):
                local_positions, local_rotations, local_results = _local_group(
                    group, team
                )
                proxy_start, count = _window(team["proxy_common"])
                particle_start, particle_count = _window(team["particle"])
                if count != particle_count:
                    raise ValueError(
                        "Proxy and particle domains must align by local row"
                    )
                identifier = team["team_id"]
                for local in range(count):
                    proxy = proxy_start + local
                    particle = particle_start + local
                    if (
                        positions[proxy] is not None
                        or particle_states[particle] is not None
                    ):
                        raise ValueError("Candidate global windows overlap")
                    positions[proxy] = deepcopy(local_positions[local])
                    rotations[proxy] = deepcopy(local_rotations[local])
                    proxy_teams[proxy] = identifier
                    state = deepcopy(local_results[local]["state"])
                    particle_states[particle] = state
                    particle_teams[particle] = identifier
                    reset_results[particle] = {
                        "global_particle_index": particle,
                        "global_proxy_index": proxy,
                        "team_id": identifier,
                        "state": state,
                        "writes": list(_WRITES),
                        "reset_applied": True,
                    }
                    written.append(proxy)
                remapped_groups.append(
                    {
                        "team_id": identifier,
                        "name": team["name"],
                        "component_identity": team["component_identity"],
                        "local_particle_start": 0,
                        "local_proxy_start": 0,
                        "global_particle": deepcopy(team["particle"]),
                        "global_proxy": deepcopy(team["proxy_common"]),
                    }
                )
            if any(
                value is None
                for arena in (
                    positions,
                    rotations,
                    proxy_teams,
                    particle_states,
                    particle_teams,
                    reset_results,
                )
                for value in arena
            ):
                raise ValueError("Candidate global state has an unfilled slot")
            outputs.append(
                {
                    "name": expected_name,
                    "groups": remapped_groups,
                    "proxy_world_positions": positions,
                    "proxy_world_rotations": rotations,
                    "world_written_vertices": written,
                    "proxy_team_ids": proxy_teams,
                    "particle_states": particle_states,
                    "particle_team_ids": particle_teams,
                    "reset_results": reset_results,
                    "fully_reset": True,
                }
            )
        return {
            "schema_version": 1,
            "getter_scope": world_reset["getter_scope"],
            "states": outputs,
            "layout_context": "Fresh candidate global Team/chunk windows; remapped from sealed independent Team1 zero-based references",
            "payload_context": "Exact saved world/reset payloads moved by index only; floating-point math not recomputed",
            "candidate_global_world_reset_generated": True,
            "state_count": len(outputs),
            "team_count": len(teams),
            "proxy_capacity": proxy_capacity,
            "particle_capacity": particle_capacity,
            "changing_animation_verified": False,
            "original_runtime_team_ids_observed": False,
            "original_runtime_chunks_observed": False,
            "native_arrays_published": False,
            "official_solver_integrated": False,
            "original_runtime_executed": False,
            "stage_modified": False,
        }
    except (KeyError, TypeError, IndexError) as exc:
        raise ValueError(
            "World/reset or layout document is incomplete/malformed"
        ) from exc


def export_file(
    world_reset: Path,
    layout: Path,
    output: Path,
    seals: tuple[str, ...],
    *,
    candidate_global_remap: bool,
) -> None:
    if len(seals) != 2 or any(
        re.fullmatch(r"[0-9a-f]{64}", seal) is None for seal in seals
    ):
        raise ValueError("Require two explicit lowercase SHA256 seals")
    if output.exists():
        raise FileExistsError(f"Refusing to overwrite {output}")
    raw = tuple(path.read_bytes() for path in (world_reset, layout))
    if any(
        hashlib.sha256(data).hexdigest() != seal
        for data, seal in zip(raw, seals, strict=True)
    ):
        raise ValueError("Reference input differs from explicit seal")
    result = build_document(
        *(json.loads(data) for data in raw),
        candidate_global_remap=candidate_global_remap,
    )
    result["input_sha256"] = dict(
        zip(("world_reset", "team_layout"), seals, strict=True)
    )
    with output.open("x", encoding="utf-8", newline="\n") as stream:
        json.dump(result, stream, ensure_ascii=False, indent=2, allow_nan=False)
        stream.write("\n")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ("world-reset", "team-layout"):
        parser.add_argument("--" + name, type=Path, required=True)
        parser.add_argument("--" + name + "-sha256", required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--candidate-global-remap", action="store_true", required=True)
    args = parser.parse_args()
    export_file(
        args.world_reset,
        args.team_layout,
        args.output,
        (args.world_reset_sha256, args.team_layout_sha256),
        candidate_global_remap=args.candidate_global_remap,
    )
    print(f"Candidate global world/reset exported: {args.output}")


if __name__ == "__main__":
    main()
