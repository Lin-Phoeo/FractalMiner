"""Offline original physics bindings audit. No runtime or basis conversion.

Consume ID-qualified SceneProbe raw dumps and the reviewed cloth manifest.
Names are descriptive only: duplicates must not collapse distinct objects.
"""

import argparse
import hashlib
import json
import math
from collections import defaultdict
from pathlib import Path
from typing import Any

from export_official_cloth_config import normalized_references, parse_dump, root_key


def integer(value: Any) -> int:
    if type(value) is not int or not -(2**63) <= value < 2**63:
        raise ValueError("Object IDs must remain signed 64-bit integers")
    return value


def local_ref(value: Any, file_id: int = 0) -> int:
    if not isinstance(value, dict) or set(value) != {"m_FileID", "m_PathID"}:
        raise ValueError("Malformed PPtr")
    pid = integer(value["m_PathID"])
    if integer(value["m_FileID"]) != (file_id if pid else 0):
        raise ValueError("Unresolved external reference")
    return pid


def vector(value: Any, axes: str) -> list[float]:
    if not isinstance(value, dict) or set(value) != set(axes):
        raise ValueError("Malformed transform vector")
    items = [value[axis] for axis in axes]
    if any(type(item) not in (int, float) or not math.isfinite(item) for item in items):
        raise ValueError("Nonfinite or nonnumeric transform vector")
    return items


def build_bindings(
    objects: list[dict[str, Any]], groups: list[dict[str, Any]]
) -> dict[str, Any]:
    if not groups or not objects:
        raise ValueError("Empty physics binding input")
    sources = {obj["source"] for obj in objects}
    if len(sources) != 1:
        raise ValueError("Expected one complete character prefab serialized file")
    source = next(iter(sources))
    by_id: dict[int, dict[str, Any]] = {}
    for obj in objects:
        pid = integer(obj["path_id"])
        if pid == 0 or pid in by_id:
            raise ValueError("Duplicate or null object identity")
        by_id[pid] = obj

    def identity(pid: int) -> str:
        return f"{source}:{pid}"

    def require(pid: int, kind: str) -> dict[str, Any]:
        obj = by_id.get(pid)
        if obj is None or obj["type"] != kind:
            raise ValueError(f"Missing or wrong-type {kind}: {pid}")
        return obj["data"]

    transforms = {}
    go_to_transform = {}
    names: dict[str, list[str]] = defaultdict(list)
    for pid, obj in by_id.items():
        if obj["type"] != "Transform":
            continue
        data = obj["data"]
        go_id = local_ref(data["m_GameObject"])
        go = require(go_id, "GameObject")
        if go_id in go_to_transform:
            raise ValueError("Multiple Transforms own one GameObject")
        components = [local_ref(pair["component"]) for pair in go["m_Component"]]
        if components.count(pid) != 1 or len(components) != len(set(components)):
            raise ValueError("GameObject/Transform ownership mismatch")
        go_to_transform[go_id] = pid
        position = vector(data["m_LocalPosition"], "xyz")
        rotation = vector(data["m_LocalRotation"], "xyzw")
        scale = vector(data["m_LocalScale"], "xyz")
        if abs(sum(item * item for item in rotation) - 1.0) > 1e-4:
            raise ValueError("Invalid serialized quaternion norm")
        if any(abs(item) < 1e-12 for item in scale):
            raise ValueError("Singular serialized local scale")
        parent = local_ref(data["m_Father"])
        children = [local_ref(child) for child in data["m_Children"]]
        if 0 in children or len(children) != len(set(children)):
            raise ValueError("Duplicate or null child reference")
        transforms[pid] = {
            "id": identity(pid),
            "path_id": pid,
            "game_object_id": identity(go_id),
            "name": go["m_Name"],
            "parent_path_id": parent,
            "children_path_ids": children,
            "local_position": position,
            "local_rotation_xyzw": rotation,
            "local_scale": scale,
        }
        names[go["m_Name"]].append(identity(pid))
    if len(go_to_transform) != sum(obj["type"] == "GameObject" for obj in objects):
        raise ValueError("Incomplete GameObject/Transform coverage")
    for pid, node in transforms.items():
        parent = node["parent_path_id"]
        if parent and (
            parent not in transforms
            or pid not in transforms[parent]["children_path_ids"]
        ):
            raise ValueError("Missing or nonreciprocal parent")
        for child in node["children_path_ids"]:
            if child not in transforms or transforms[child]["parent_path_id"] != pid:
                raise ValueError("Missing or nonreciprocal child")

    def chain(pid: int) -> list[int]:
        result = []
        while pid:
            if pid in result:
                raise ValueError("Cyclic Transform hierarchy")
            result.append(pid)
            pid = transforms[pid]["parent_path_id"]
        return result[::-1]

    for pid, node in transforms.items():
        ancestors = chain(pid)
        node["hierarchy_ids"] = [identity(item) for item in ancestors]
        node["hierarchy_names"] = [transforms[item]["name"] for item in ancestors]

    def active_node(pid: int) -> dict[str, Any]:
        if pid not in transforms:
            raise ValueError(f"Missing physics Transform: {pid}")
        for item in chain(pid):
            go = require(
                local_ref(require(item, "Transform")["m_GameObject"]), "GameObject"
            )
            if go["m_IsActive"] is not True:
                raise ValueError("Physics reference has inactive ancestor")
        return transforms[pid]

    def component_node(pid: int) -> tuple[dict[str, Any], dict[str, Any]]:
        data = require(pid, "MonoBehaviour")
        go_id = local_ref(data["m_GameObject"])
        go = require(go_id, "GameObject")
        if [local_ref(pair["component"]) for pair in go["m_Component"]].count(pid) != 1:
            raise ValueError("GameObject/component ownership mismatch")
        if type(data["m_Enabled"]) is not int or data["m_Enabled"] != 1:
            raise ValueError("Disabled physics component")
        return data, active_node(go_to_transform[go_id])

    cloth_candidates: dict[tuple[int, ...], list[int]] = defaultdict(list)
    for pid, obj in by_id.items():
        if obj["type"] == "MonoBehaviour" and "serializeData" in obj["data"]:
            cloth_candidates[root_key(obj["data"]["serializeData"], 0)].append(pid)
    resolved_groups = []
    colliders = {}
    group_names = set()
    for group in groups:
        name = group["boneClothName"]
        if name in group_names or not name.startswith("MBC_Typhoea_"):
            raise ValueError("Duplicate or unexpected cloth group")
        group_names.add(name)
        settings = group["boneClothData"]
        roots = root_key(settings, 2)
        candidates = cloth_candidates.get(roots, [])
        if len(candidates) != 1:
            raise ValueError("Missing or ambiguous cloth component")
        component_id = candidates[0]
        component, owner = component_node(component_id)
        if normalized_references(settings, 2) != normalized_references(
            component["serializeData"], 0
        ):
            raise ValueError("Cloth binding parameters changed")
        resolved_roots = [active_node(pid) for pid in roots]
        ignored = [
            active_node(local_ref(item, 2)) for item in settings["ignoreFromRootBones"]
        ]
        if [node["name"] for node in resolved_roots] != group["rootBoneList"]:
            raise ValueError("Root reference/name order mismatch")
        if [node["name"] for node in ignored] != group["ignoredFromrootBoneList"]:
            raise ValueError("Ignored reference/name order mismatch")
        collider_ids = [
            local_ref(item, 2)
            for item in settings["colliderCollisionConstraint"]["colliderList"]
        ]
        collider_names = []
        for pid in collider_ids:
            data, node = component_node(pid)
            collider_names.append(node["name"])
            if "size" in data and "direction" in data:
                fingerprint = "capsule_fields"
                vector(data["size"], "xyz")
                required = ("reverseDirection", "radiusSeparation", "alignedOnCenter")
                if any(key not in data for key in required):
                    raise ValueError("Incomplete capsule serialization")
            elif "radius" in data:
                fingerprint = "sphere_fields"
                radius = data["radius"]
                if (
                    type(radius) not in (int, float)
                    or not math.isfinite(radius)
                    or radius <= 0
                ):
                    raise ValueError("Invalid sphere radius")
            elif "size" in data:
                # Original accessory colliders serialize Vector3 size, not radius.
                # Preserve it without inventing a sphere/capsule conversion.
                fingerprint = "size_only_fields"
                vector(data["size"], "xyz")
            else:
                raise ValueError(
                    f"Unknown referenced collider serialization: {pid} {sorted(data)}"
                )
            vector(data["center"], "xyz")
            colliders[pid] = {
                "id": identity(pid),
                "transform_id": node["id"],
                "name": node["name"],
                "shape_fingerprint": fingerprint,
                "class_resolved": False,
                "raw_component": data,
            }
        if collider_names != group["colliderParentBoneList"]:
            raise ValueError("Collider reference/name order mismatch")
        resolved_groups.append(
            {
                "name": name,
                "component_id": identity(component_id),
                "owner_transform_id": owner["id"],
                "roots": resolved_roots,
                "ignored": ignored,
                "collider_ids": [identity(pid) for pid in collider_ids],
            }
        )
    return {
        "schema_version": 1,
        "runtime_restored": False,
        "coordinate_space": "Serialized prefab local TRS; no axis conversion or runtime injection",
        "transform_count": len(transforms),
        "transforms": list(transforms.values()),
        "duplicate_names": {name: ids for name, ids in names.items() if len(ids) > 1},
        "groups": resolved_groups,
        "colliders": list(colliders.values()),
        "raw_objects": objects,
    }


def check_read_warnings(result: dict[str, Any], warnings: list[dict[str, Any]]) -> None:
    """Never certify a physics object whose type-tree reader reported a mismatch."""
    known = {f"{obj['source']}:{obj['path_id']}" for obj in result["raw_objects"]}
    critical = {
        f"{obj['source']}:{obj['path_id']}"
        for obj in result["raw_objects"]
        if obj["type"] in ("Transform", "GameObject")
    }
    critical.update(group["component_id"] for group in result["groups"])
    critical.update(collider["id"] for collider in result["colliders"])
    for warning in warnings:
        key = f"{warning['Source']}:{integer(warning['PathId'])}"
        if key not in known or key in critical or not warning.get("Messages"):
            raise ValueError(f"Unresolved or critical metadata reader warning: {key}")
    result["unvalidated_metadata_warnings"] = warnings
    result["critical_metadata_reader_warnings"] = 0


def export_files(
    scene_manifest: Path, cloth_manifest: Path, output: Path, expected_groups: int = 11
) -> None:
    if output.exists():
        raise FileExistsError(f"Refusing to overwrite {output}")
    scene = json.loads(scene_manifest.read_text(encoding="utf-8-sig"))
    cloth = json.loads(cloth_manifest.read_text(encoding="utf-8-sig"))
    objects = []
    hashes = {}
    base = scene_manifest.resolve().parent
    for record in scene["MetadataExports"]:
        relative = record["File"]
        if record.get("Error") is not None or not isinstance(relative, str):
            raise ValueError("Failed metadata export")
        path = (base / relative).resolve()
        if not path.is_relative_to(base):
            raise ValueError("Metadata path points outside input directory")
        raw = path.read_bytes()
        hashes[str(path)] = hashlib.sha256(raw).hexdigest()
        parsed = parse_dump(raw.decode("utf-8-sig"))
        asset = record["Asset"]
        objects.append(
            {
                "source": asset["Source"],
                "path_id": asset["PathId"],
                "type": asset["Type"],
                "data": parsed.data,
                "raw_scalars": parsed.scalars,
            }
        )
    result = build_bindings(objects, cloth["groups"])
    # Preserve external-file tables for later MonoScript identity resolution.
    # A script fingerprint is not a resolved external MonoScript class.
    result["serialized_files"] = scene.get("SerializedFiles", [])
    if len(result["groups"]) != expected_groups:
        raise ValueError(f"Expected {expected_groups} reviewed cloth groups")
    warning_path = base / "metadata-read-warnings.json"
    check_read_warnings(
        result, json.loads(warning_path.read_text(encoding="utf-8-sig"))
    )
    for path in (scene_manifest, cloth_manifest, warning_path):
        hashes[str(path.resolve())] = hashlib.sha256(path.read_bytes()).hexdigest()
    result["source_sha256"] = hashes
    with output.open("x", encoding="utf-8", newline="\n") as stream:
        json.dump(result, stream, ensure_ascii=False, indent=2, allow_nan=False)
        stream.write("\n")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--scene-manifest", type=Path, required=True)
    parser.add_argument("--cloth-manifest", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    export_files(args.scene_manifest, args.cloth_manifest, args.output)
    print(f"Verified original Transform/collider bindings: {args.output}")


if __name__ == "__main__":
    main()
