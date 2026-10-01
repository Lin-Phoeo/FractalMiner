"""Offline parent-qualified original prefab -> recovered skeleton mapping.

Do not write Unity assets or infer runtime pose correction from bind/rest data.
An identity match and a constant-basis compatibility test are separate gates.
"""

import argparse
import hashlib
import json
from pathlib import Path
from typing import Any

import numpy as np


def map_bones(
    bindings: dict[str, Any], bones: list[dict[str, Any]], contract: dict[str, Any]
) -> list[dict[str, Any]]:
    nodes = {node["id"]: node for node in bindings["transforms"]}
    if len(nodes) != len(bindings["transforms"]):
        raise ValueError("Duplicate source identity")
    by_pid = {node["path_id"]: node for node in nodes.values()}
    anchor = 0
    for name in contract["source_anchor_names"]:
        matches = [
            node
            for node in nodes.values()
            if node["parent_path_id"] == anchor and node["name"] == name
        ]
        if len(matches) != 1:
            raise ValueError("Missing or ambiguous source anchor")
        anchor = matches[0]["path_id"]
    synthetic = set(contract["synthetic_model_roots"])
    aliases = contract["aliases"]
    paths: dict[int, str] = {}

    def model_path(index: int, pending: set[int]) -> str:
        if index in pending or not 0 <= index < len(bones):
            raise ValueError("Invalid or cyclic model hierarchy")
        if index not in paths:
            bone = bones[index]
            parent = bone["parent"]
            if type(parent) is not int or parent < -1:
                raise ValueError("Invalid model parent index")
            paths[index] = (
                model_path(parent, pending | {index}) + "/" if parent != -1 else ""
            ) + bone["name"]
        return paths[index]

    mapped: dict[int, dict[str, Any]] = {}
    used_ids = set()
    used_aliases = set()

    def bind(index: int) -> dict[str, Any]:
        if index in mapped:
            return mapped[index]
        path = model_path(index, set())
        bone = bones[index]
        parent = bone["parent"]
        if bone["name"] in synthetic:
            if parent != -1 or any(item["parent"] == index for item in bones):
                raise ValueError("Synthetic root cannot own mapped bones")
            mapped[index] = {
                "model_index": index,
                "model_path": path,
                "synthetic": True,
                "source_id": None,
            }
            return mapped[index]
        parent_pid = by_pid[anchor]["path_id"] if anchor else 0
        if parent != -1:
            parent_map = bind(parent)
            if parent_map["synthetic"]:
                raise ValueError("Cannot infer mapping below synthetic root")
            parent_pid = nodes[parent_map["source_id"]]["path_id"]
        if path in aliases:
            alias = aliases[path]
            node = nodes.get(alias["source_id"])
            if (
                node is None
                or node["parent_path_id"] != parent_pid
                or node["name"] != alias["expected_source_name"]
            ):
                raise ValueError(
                    "Alias does not match expected source identity/parent/name"
                )
            used_aliases.add(path)
        else:
            matches = [
                node
                for node in nodes.values()
                if node["parent_path_id"] == parent_pid and node["name"] == bone["name"]
            ]
            if len(matches) != 1:
                raise ValueError(f"Missing or ambiguous parent-qualified bone: {path}")
            node = matches[0]
        if node["id"] in used_ids:
            raise ValueError("Two model bones map to one source Transform")
        used_ids.add(node["id"])
        mapped[index] = {
            "model_index": index,
            "model_path": path,
            "synthetic": False,
            "source_id": node["id"],
            "alias_used": path in aliases,
        }
        return mapped[index]

    for index in range(len(bones)):
        bind(index)
    if used_aliases != set(aliases):
        raise ValueError("Unused alias contract entry")
    return [mapped[index] for index in range(len(bones))]


def trs(node: dict[str, Any]) -> np.ndarray:
    x, y, z, w = node["local_rotation_xyzw"]
    rotation = np.array(
        [
            [1 - 2 * (y * y + z * z), 2 * (x * y - z * w), 2 * (x * z + y * w)],
            [2 * (x * y + z * w), 1 - 2 * (x * x + z * z), 2 * (y * z - x * w)],
            [2 * (x * z - y * w), 2 * (y * z + x * w), 1 - 2 * (x * x + y * y)],
        ],
        dtype=float,
    )
    matrix = np.eye(4)
    matrix[:3, :3] = rotation @ np.diag(node["local_scale"])
    matrix[:3, 3] = node["local_position"]
    return matrix


def audit_basis(
    bindings: dict[str, Any], mapping: list[dict[str, Any]], model: dict[str, Any]
) -> dict[str, Any]:
    nodes = {node["path_id"]: node for node in bindings["transforms"]}
    by_id = {node["id"]: node for node in nodes.values()}
    worlds: dict[int, np.ndarray] = {}

    def world(pid: int) -> np.ndarray:
        if pid not in worlds:
            node = nodes[pid]
            parent = node["parent_path_id"]
            worlds[pid] = (world(parent) if parent else np.eye(4)) @ trs(node)
        return worlds[pid]

    observations = []
    first_bind_by_bone: dict[int, np.ndarray] = {}
    repeated_bones = set()
    repeat_maximum = 0.0
    for mesh in model["meshes"]:
        palette = mesh["bones"]
        if len(mesh["bindPoses"]) != 16 * len(palette):
            raise ValueError("Bindpose/palette length mismatch")
        for offset, bone_index in enumerate(palette):
            if (
                type(bone_index) is not int
                or not 0 <= bone_index < len(mapping)
                or mapping[bone_index]["synthetic"]
            ):
                raise ValueError("Unmapped/synthetic bone in bindpose palette")
            inverse_bind = np.array(
                mesh["bindPoses"][offset * 16 : (offset + 1) * 16], dtype=float
            ).reshape((4, 4), order="F")
            if not np.isfinite(inverse_bind).all() or not np.allclose(
                inverse_bind[3], [0, 0, 0, 1], atol=1e-6
            ):
                raise ValueError("Invalid affine bindpose")
            if abs(np.linalg.det(inverse_bind[:3, :3])) < 1e-12:
                raise ValueError("Singular bindpose")
            if bone_index in first_bind_by_bone:
                repeated_bones.add(bone_index)
                repeat_maximum = max(
                    repeat_maximum,
                    float(
                        np.max(np.abs(inverse_bind - first_bind_by_bone[bone_index]))
                    ),
                )
            else:
                first_bind_by_bone[bone_index] = inverse_bind
            source = by_id[mapping[bone_index]["source_id"]]
            # Stored data is read identically to the current C# ReadMatrix:
            # sourceWorld = B * inverse(storedBind), hence B = sourceWorld * storedBind.
            basis = world(source["path_id"]) @ inverse_bind
            observations.append((bone_index, mesh["name"], basis))
    if not observations:
        raise ValueError("No bindpose observations")
    baseline = observations[0][2]
    deviations = []
    for bone_index, mesh_name, basis in observations:
        deviations.append(
            {
                "model_index": bone_index,
                "model_path": mapping[bone_index]["model_path"],
                "mesh": mesh_name,
                "translation_deviation": float(
                    np.linalg.norm(basis[:3, 3] - baseline[:3, 3])
                ),
                "linear_deviation": float(
                    np.max(np.abs(basis[:3, :3] - baseline[:3, :3]))
                ),
            }
        )
    translation = max(item["translation_deviation"] for item in deviations)
    linear = max(item["linear_deviation"] for item in deviations)
    return {
        "constant_left_basis_pass": translation <= 1e-4 and linear <= 1e-4,
        "tolerance": 1e-4,
        "bone_observations": len(observations),
        "unique_palette_bones": len({item[0] for item in observations}),
        "repeated_palette_bones": len(repeated_bones),
        "repeated_palette_bindpose_pass": repeat_maximum <= 1e-4,
        "maximum_repeated_bindpose_entry_deviation": repeat_maximum,
        "candidate_basis": baseline.tolist(),
        "maximum_translation_deviation": translation,
        "maximum_linear_deviation": linear,
        "worst_observations": sorted(
            deviations, key=lambda item: item["translation_deviation"], reverse=True
        )[:20],
        "runtime_modified": False,
        "non_claim": "A failed gate does not identify the cause: authored prefab pose, mesh/bind space, importer basis or mapping need separate investigation.",
    }


def export_files(
    bindings_path: Path, model_path: Path, contract_path: Path, output: Path
) -> None:
    if output.exists():
        raise FileExistsError(f"Refusing to overwrite {output}")
    paths = [bindings_path, model_path, contract_path]
    inputs = [json.loads(path.read_text(encoding="utf-8-sig")) for path in paths]
    bindings, model, contract = inputs
    mapping = map_bones(bindings, model["bones"], contract)
    result = {
        "schema_version": 1,
        "runtime_modified": False,
        "identity_mapping_pass": True,
        "mapping": mapping,
        "basis_audit": audit_basis(bindings, mapping, model),
        "source_sha256": {
            str(path.resolve()): hashlib.sha256(path.read_bytes()).hexdigest()
            for path in paths
        },
    }
    with output.open("x", encoding="utf-8", newline="\n") as stream:
        json.dump(result, stream, ensure_ascii=False, indent=2, allow_nan=False)
        stream.write("\n")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ("bindings", "model", "contract", "output"):
        parser.add_argument(f"--{name}", type=Path, required=True)
    args = parser.parse_args()
    export_files(args.bindings, args.model, args.contract, args.output)
    print(f"Offline skeleton mapping/basis audit: {args.output}")


if __name__ == "__main__":
    main()
