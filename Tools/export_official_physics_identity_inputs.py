"""Export identity-only BoneCloth slots from the reviewed schema-v1 bindings.

Requires an explicit SHA256 seal of the bindings produced/validated by
export_official_physics_bindings.py. Rechecks the serialized forest and refuses
overwrite. Does not establish MonoBehaviour classes, live object validity or
the actual game build route; those belong to the original bindings/source audit.
The compiled route is the static Init BoneCloth call only, whose collisionBones
argument is null. collider_ids are NOT that constructor argument.
"""

import argparse
import hashlib
import json
import re
from pathlib import Path
from typing import Any

from official_physics_collection import TransformIdentity, _identity
from official_physics_identity_inputs import build_bone_identity_inputs


def _qualified(value: Any) -> TransformIdentity:
    if not isinstance(value, str) or ":" not in value:
        raise ValueError("Adapter requires a qualified serialized identity")
    file, number = value.rsplit(":", 1)
    result = _identity((file, int(number)))
    if value != f"{result[0]}:{result[1]}":
        raise ValueError("Adapter requires canonical signed Int64 identity spelling")
    return result


def _path_id(value: Any, *, nullable: bool = False) -> int:
    if type(value) is not int or not -(2**63) <= value < 2**63:
        raise ValueError("Adapter requires signed Int64 PPtr, not runtime Int32 ID")
    if value == 0 and not nullable:
        raise ValueError("Adapter requires a non-null Transform identity")
    return value


def build_document(source: dict[str, Any]) -> dict[str, Any]:
    """Compile already-reviewed binding references; labels never resolve objects."""
    if type(source["schema_version"]) is not int or source["schema_version"] != 1:
        raise ValueError("Adapter requires reviewed bindings schema version 1")
    if type(source["transform_count"]) is not int or source["transform_count"] != len(
        source["transforms"]
    ):
        raise ValueError("Transform count does not match reviewed binding slots")
    children: dict[TransformIdentity, tuple[TransformIdentity, ...]] = {}
    parents: dict[TransformIdentity, TransformIdentity | None] = {}
    for record in source["transforms"]:
        node = _qualified(record["id"])
        if node in children or _path_id(record["path_id"]) != node[1]:
            raise ValueError("Duplicate or mismatched serialized Transform identity")
        parent = _path_id(record["parent_path_id"], nullable=True)
        parents[node] = (node[0], parent) if parent else None
        children[node] = tuple(
            (node[0], _path_id(child)) for child in record["children_path_ids"]
        )
    if not source["groups"]:
        raise ValueError("Adapter requires a reviewed nonempty BoneCloth roster")
    groups, components = [], set()
    for group in source["groups"]:
        component = _qualified(group["component_id"])
        if component in components:
            raise ValueError("Adapter refuses duplicate cloth component identities")
        components.add(component)
        result = build_bone_identity_inputs(
            children,
            parents,
            [_qualified(root["id"]) for root in group["roots"]],
            _qualified(group["owner_transform_id"]),
            ignored=[_qualified(node["id"]) for node in group["ignored"]],
            collision_bones=None,
        )
        groups.append(
            {
                "name": group["name"],
                "component_identity": group["component_id"],
                "ordinary_render_identity": group["owner_transform_id"],
                "ordered_transform_identities": [
                    f"{file}:{number}" for file, number in result.collected.transforms
                ],
                "skin_bone_count": result.collected.skin_bone_count,
                "render_transform_index": result.collected.render_transform_index,
                "snapshot_parent_indices": list(result.snapshot_parent_indices),
                "skin_parent_indices": list(result.skin_parent_indices),
                "root_indices": list(result.root_indices),
                "collision_bone_indices": None,
                "constructor_collision_argument_scope": (
                    "Init BoneCloth call passes null; runtime/prebuilt calls not inferred"
                ),
            }
        )
    return {
        "schema_version": 1,
        "scope": "Serialized identities for the static ordinary Init BoneCloth route",
        "groups": groups,
        "runtime_instance_ids_generated": False,
        "world_getters_generated": False,
        "selection_attributes_generated": False,
        "full_proxy_inputs_generated": False,
        "native_arrays_published": False,
        "game_build_route_observed": False,
        "unity_backend_modified": False,
    }


def export_file(bindings: Path, output: Path, expected_sha256: str) -> None:
    if re.fullmatch(r"[0-9a-f]{64}", expected_sha256) is None:
        raise ValueError("Require an explicit lowercase SHA256 bindings seal")
    if output.exists():
        raise FileExistsError(f"Refusing to overwrite {output}")
    raw = bindings.read_bytes()
    if hashlib.sha256(raw).hexdigest() != expected_sha256:
        raise ValueError("Bindings differ from the reviewed SHA256 seal")
    result = build_document(json.loads(raw))
    result["source_sha256"] = expected_sha256
    with output.open("x", encoding="utf-8", newline="\n") as stream:
        json.dump(result, stream, ensure_ascii=False, indent=2, allow_nan=False)
        stream.write("\n")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--bindings", type=Path, required=True)
    parser.add_argument("--bindings-sha256", required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    export_file(args.bindings, args.output, args.bindings_sha256)
    print(f"Identity-only BoneCloth slots exported: {args.output}")


if __name__ == "__main__":
    main()
