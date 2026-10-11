"""Sealed world-getter file -> identity-ordered bone imports, not full proxies.

Consumes reviewed serialized bindings and an explicit Unity getter producer's
JSON. Provenance is retained, not upgraded to official game pose/solver evidence.
No saved attributes, normal-axis override, topology, Team or Unity writer output.
Requires full matching identity coverage per state; names never resolve bones.
"""

import argparse
import hashlib
import json
import re
from dataclasses import asdict
from pathlib import Path
from typing import Any

from export_official_physics_identity_inputs import _qualified
from export_official_physics_identity_inputs import build_document as compile_identities
from official_physics_bone_import import Matrix4, _matrix
from official_physics_collection import CollectedBoneTransforms
from official_physics_getter_inputs import InstanceGetter, prepare_identity_bone_import
from official_physics_identity_inputs import BoneIdentityInputs
from official_physics_snapshot import TransformGetterValues, read_transform_snapshot


def _columns(raw: dict[str, Any]) -> Matrix4:
    if set(raw) != {"c0", "c1", "c2", "c3"}:
        raise ValueError("Require explicit four Unity GetColumn outputs")
    return _matrix(tuple(raw[key] for key in ("c0", "c1", "c2", "c3")))


def build_document(
    bindings: dict[str, Any], capture: dict[str, Any], bindings_sha256: str
) -> dict[str, Any]:
    if type(capture["schema_version"]) is not int or capture["schema_version"] != 1:
        raise ValueError("Require getter-capture schema 1")
    if capture["bindings_sha256"] != bindings_sha256:
        raise ValueError("Getter capture belongs to different serialized bindings")
    if not capture["states"]:
        raise ValueError("Require at least one explicit getter state")
    compiled = compile_identities(bindings)
    original_ids = {_qualified(record["id"]) for record in bindings["transforms"]}
    states, names = [], set()
    for state in capture["states"]:
        name = state["name"]
        if not isinstance(name, str) or not name or name in names:
            raise ValueError("Require unique nonempty capture state labels")
        names.add(name)
        records = {}
        for sample in state["samples"]:
            identity = _qualified(sample["identity"])
            if identity in records:
                raise ValueError("Duplicate sampled serialized identity")
            values = TransformGetterValues(
                tuple(sample["position"]),
                tuple(sample["rotation"]),
                _columns(sample["local_to_world"]),
                tuple(sample["local_position"]),
                tuple(sample["local_rotation"]),
            )
            # Validate even records not selected by a cloth group, without
            # fabricating getters or converting world coordinates from local TRS.
            read_transform_snapshot(values)
            records[identity] = InstanceGetter(
                sample["instance_id"],
                sample["parent_instance_id"],
                values,
                _columns(sample["world_to_local"]),
            )
        if records.keys() != original_ids:
            raise ValueError(
                "Require exact original identity coverage per getter state"
            )
        groups = []
        for group, source in zip(compiled["groups"], bindings["groups"], strict=True):
            count = group["skin_bone_count"]
            collected = CollectedBoneTransforms(
                tuple(
                    _qualified(node) for node in group["ordered_transform_identities"]
                ),
                tuple(_qualified(root["id"]) for root in source["roots"]),
                count,
                group["render_transform_index"],
                None,
            )
            inputs = BoneIdentityInputs(
                collected,
                tuple(group["snapshot_parent_indices"]),
                tuple(group["skin_parent_indices"]),
                tuple(group["root_indices"]),
            )
            imported = prepare_identity_bone_import(inputs, records)
            groups.append(
                {
                    "name": group["name"],
                    "component_identity": group["component_identity"],
                    "skin_bone_count": count,
                    **asdict(imported),
                }
            )
        states.append({"name": name, "groups": groups})
    return {
        "schema_version": 1,
        "getter_scope": capture["scope"],
        "getter_unity_version": capture["unity_version"],
        "states": states,
        "selection_attributes_generated": False,
        "full_proxy_inputs_generated": False,
        "native_arrays_published": False,
        "official_solver_integrated": False,
        "original_runtime_executed": False,
        "stage_modified": False,
    }


def export_file(
    bindings: Path,
    capture: Path,
    output: Path,
    bindings_sha256: str,
    capture_sha256: str,
) -> None:
    if any(
        re.fullmatch(r"[0-9a-f]{64}", value) is None
        for value in (bindings_sha256, capture_sha256)
    ):
        raise ValueError("Require two explicit lowercase SHA256 seals")
    if output.exists():
        raise FileExistsError(f"Refusing to overwrite {output}")
    raw_b, raw_c = bindings.read_bytes(), capture.read_bytes()
    if (
        hashlib.sha256(raw_b).hexdigest() != bindings_sha256
        or hashlib.sha256(raw_c).hexdigest() != capture_sha256
    ):
        raise ValueError("Bindings or getter capture differs from its SHA256 seal")
    result = build_document(json.loads(raw_b), json.loads(raw_c), bindings_sha256)
    result["source_sha256"] = {
        "bindings": bindings_sha256,
        "getter_capture": capture_sha256,
    }
    with output.open("x", encoding="utf-8", newline="\n") as stream:
        json.dump(result, stream, ensure_ascii=False, indent=2, allow_nan=False)
        stream.write("\n")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--bindings", type=Path, required=True)
    parser.add_argument("--getter-capture", type=Path, required=True)
    parser.add_argument("--bindings-sha256", required=True)
    parser.add_argument("--getter-sha256", required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    export_file(
        args.bindings,
        args.getter_capture,
        args.output,
        args.bindings_sha256,
        args.getter_sha256,
    )
    print(f"Getter-based BoneCloth imports exported: {args.output}")


if __name__ == "__main__":
    main()
