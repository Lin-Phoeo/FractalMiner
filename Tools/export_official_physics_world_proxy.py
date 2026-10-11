"""Sealed reference imports + actual matrix getters -> world proxy -> reset14.

Each group has an independent explicit zero-based experiment arena and Team1;
these are NOT original allocator chunks/IDs. Both states may have independently
built bindposes: no changing-animation or recovered-character proof is implied.
No raw DLL execution, Unity launch, native dispatch or transform writer occurs.
"""

import argparse
import hashlib
import json
import re
from dataclasses import asdict
from pathlib import Path
from typing import Any

from official_physics_angle_baseline import _integer
from official_physics_bindpose import ImportedBoneWeight
from official_physics_bone_import import _matrix
from official_physics_particle_init import initialize_registered_particle_window
from official_physics_particle_registration import (
    PARTICLE_ARRAY_FIELDS,
    ParticleAllocation,
    plan_particle_registration,
)
from official_physics_particle_reset import ParticleFrameState, ParticleResetTeam
from official_physics_proxy_baseline import _int32
from official_physics_world_proxy import (
    ProxyUpdateTeam,
    WorldProxyBuffers,
    build_proxy_update_vertices,
    update_world_proxy,
)


def _digest(value: str) -> str:
    if not isinstance(value, str) or re.fullmatch(r"[0-9a-f]{64}", value) is None:
        raise ValueError("Require explicit lowercase SHA256 seals")
    return value


def _name(value: str) -> str:
    if not isinstance(value, str) or not value:
        raise ValueError("Require nonempty qualified identity/name")
    return value


def _samples(samples: list[dict[str, Any]]) -> dict[int, dict[str, Any]]:
    by_id, identities = {}, set()
    for sample in samples:
        identifier = _int32(sample["instance_id"])
        identity = _name(sample["identity"])
        if not identifier or identifier in by_id or identity in identities:
            raise ValueError(
                "Require unique runtime ID and serialized identity mapping"
            )
        _int32(sample["parent_instance_id"])
        identities.add(identity)
        by_id[identifier] = sample
    return by_id


def _dirty_state() -> ParticleFrameState:
    # Explicit nonzero experiment seed; NOT native reused array contents.
    return ParticleFrameState(
        (91, 92, 93),
        (81, 82, 83),
        (0, 0, 0, 2),
        (71, 72, 73),
        (0, 0, 0, 3),
        (61, 62, 63),
        (0, 0, 0, 4),
        (51, 52, 53),
        (41, 42, 43),
        (31, 32, 33),
        (21, 22, 23),
        0.8,
        0.9,
        (11, 12, 13),
    )


def build_document(
    imports: dict[str, Any],
    getters: dict[str, Any],
    *,
    getter_capture_sha256: str,
    experiment_layout: bool,
) -> dict[str, Any]:
    """Finite independently built reference states with same-state identity joins.

    Caller digest is an input premise here; export_file verifies actual bytes.
    Explicit layout does not authenticate native arrays or observer timing.
    Missing/bad inputs fail rather than synthesize matrices or fallback poses.
    """
    try:
        return _build_document(
            imports, getters, getter_capture_sha256, experiment_layout
        )
    except (KeyError, TypeError, IndexError) as exc:
        raise ValueError("Reference document is incomplete or malformed") from exc


def _build_document(
    imports: dict[str, Any],
    getters: dict[str, Any],
    seal: str,
    premise: bool,
) -> dict[str, Any]:
    if (
        premise is not True
        or any(
            type(d["schema_version"]) is not int or d["schema_version"] != 1
            for d in (imports, getters)
        )
        or imports["full_proxy_inputs_generated"] is not False
        or imports["getter_scope"] != getters["scope"]
        or _digest(imports["source_sha256"]["bindings"])
        != _digest(getters["bindings_sha256"])
        or _digest(imports["source_sha256"]["getter_capture"]) != _digest(seal)
        or not imports["states"]
        or len(imports["states"]) != len(getters["states"])
    ):
        raise ValueError(
            "Require matching sealed reference provenance and explicit experiment layout"
        )
    states, names = [], set()
    for state, capture in zip(imports["states"], getters["states"], strict=True):
        name = _name(state["name"])
        if name in names or name != capture["name"]:
            raise ValueError("Require unique matching reference states in source order")
        names.add(name)
        samples = _samples(capture["samples"])  # Separate ID map per state.
        if not state["groups"]:
            raise ValueError("Require nonempty reference groups")
        groups, group_names, components = [], set(), set()
        for group in state["groups"]:
            label, identity = _name(group["name"]), _name(group["component_identity"])
            if label in group_names or identity in components:
                raise ValueError("Require unique ordered group/component identities")
            group_names.add(label)
            components.add(identity)
            count = _integer(group["skin_bone_count"], 65535)
            ids = tuple(_int32(v) for v in group["runtime_instance_ids"])
            parents = tuple(_int32(v) for v in group["runtime_parent_ids"])
            vertex = group["vertices"]
            frames = vertex["frames"]
            if (
                not count
                or len(ids) != count + 1
                or len(parents) != count + 1
                or len(set(ids)) != len(ids)
                or any(
                    len(frames[k]) != count
                    for k in ("positions", "normals", "tangents")
                )
                or len(vertex["bone_weights"]) != count
                or len(vertex["skin_bone_bindposes"]) != count
            ):
                raise ValueError(
                    "Require parallel unreduced skin data and appended render slot"
                )
            if any(i not in samples for i in ids):
                raise ValueError("Actual matrix getter is missing for a runtime ID")
            selected = tuple(samples[i] for i in ids)
            if tuple(s["parent_instance_id"] for s in selected) != parents:
                raise ValueError(
                    "Getter runtime parent disagrees with imported source identity"
                )
            matrices = []
            for sample in selected:
                columns = sample["local_to_world"]
                if set(columns) != {"c0", "c1", "c2", "c3"}:
                    raise ValueError("Require four original GetColumn outputs")
                matrices.append(
                    _matrix(tuple(columns[k] for k in ("c0", "c1", "c2", "c3")))
                )
            team = ProxyUpdateTeam(15, 0, 0, count, 0, 0)
            inputs = WorldProxyBuffers(
                tuple(tuple(v) for v in frames["positions"]),
                tuple(tuple(v) for v in frames["normals"]),
                tuple(tuple(v) for v in frames["tangents"]),
                tuple(
                    ImportedBoneWeight(tuple(w["weights"]), tuple(w["bone_indices"]))
                    for w in vertex["bone_weights"]
                ),
                tuple(range(count)),  # Explicit one-to-one experiment map.
                tuple(_matrix(m) for m in vertex["skin_bone_bindposes"]),
                tuple(matrices),
            )
            work = build_proxy_update_vertices(
                {1: team}, team_order=(1,), output_capacity=count
            )
            world = update_world_proxy(
                work,
                {1: team},
                (1,) * count,
                inputs,
                ((91, 92, 93),) * count,
                ((0, 0, 0, 2),) * count,
            )
            registration = plan_particle_registration(
                count,
                1,
                {k: ParticleAllocation(0, count) for k in PARTICLE_ARRAY_FIELDS},
                manager_valid=True,
                array_capacities={k: count for k in PARTICLE_ARRAY_FIELDS},
            )
            reset = initialize_registered_particle_window(
                registration,
                (_dirty_state(),) * count,
                team_id=1,
                enabled_team=ParticleResetTeam(15, 0, 0),
                proxy_world_positions=world.positions,
                proxy_world_rotations=world.rotations,
                world_proxy_pose_confirmed=True,
            )
            groups.append(
                {
                    "name": label,
                    "component_identity": identity,
                    "skin_bone_count": count,
                    "runtime_instance_ids": ids,
                    "matrix_identities": tuple(s["identity"] for s in selected),
                    "experiment_team": asdict(team),
                    "world": asdict(world),
                    "reset": asdict(reset),
                }
            )
        states.append({"name": name, "groups": groups})
    return {
        "schema_version": 1,
        "getter_scope": imports["getter_scope"],
        "states": states,
        "layout_context": "Each group has independent zero-based caller arenas and Team1; not native global chunks",
        "input_context": "Unreduced imported bone frames and bindposes; same-state actual matrix GetColumns, not snapshot TRS",
        "initialization_context": "Explicit dirty experiment seed and flag15; not observed native allocator/clock state",
        "supplied_input_world_reference_generated": True,
        "supplied_world_first_reset_reference_generated": True,
        "full_proxy_inputs_generated": False,
        "native_arrays_published": False,
        "official_solver_integrated": False,
        "changing_animation_verified": False,
        "original_runtime_executed": False,
        "stage_modified": False,
    }


def export_file(
    imports: Path,
    getters: Path,
    output: Path,
    seals: tuple[str, ...],
    *,
    experiment_layout: bool,
) -> None:
    if len(seals) != 2:
        raise ValueError("Require two explicit SHA256 seals")
    for seal in seals:
        _digest(seal)
    if output.exists():
        raise FileExistsError(f"Refusing to overwrite {output}")
    raw = tuple(p.read_bytes() for p in (imports, getters))
    if any(hashlib.sha256(b).hexdigest() != s for b, s in zip(raw, seals, strict=True)):
        raise ValueError("Reference input differs from explicit seal")
    result = build_document(
        *(json.loads(b) for b in raw),
        getter_capture_sha256=seals[1],
        experiment_layout=experiment_layout,
    )
    result["input_sha256"] = dict(zip(("imports", "getters"), seals, strict=True))
    with output.open("x", encoding="utf-8", newline="\n") as stream:
        json.dump(result, stream, ensure_ascii=False, indent=2, allow_nan=False)
        stream.write("\n")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ("imports", "getters"):
        parser.add_argument("--" + name, type=Path, required=True)
        parser.add_argument("--" + name + "-sha256", required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--experiment-layout", action="store_true", required=True)
    args = parser.parse_args()
    export_file(
        args.imports,
        args.getters,
        args.output,
        (args.imports_sha256, args.getters_sha256),
        experiment_layout=args.experiment_layout,
    )
    print(f"World proxy reference exported: {args.output}")


if __name__ == "__main__":
    main()
