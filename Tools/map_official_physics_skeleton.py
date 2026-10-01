"""Offline parent-qualified original prefab -> recovered skeleton mapping.

Do not write Unity assets or infer runtime pose correction from bind/rest data.
An identity match and a constant-basis compatibility test are separate gates.
"""

import argparse
import hashlib
import json
import zlib
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


def audit_model_provenance(
    model: dict[str, Any], avatar: dict[str, Any], raw_meshes: list[dict[str, Any]]
) -> dict[str, Any]:
    """Verify the existing model builder's exact source flattening/palette contract.

    This does not certify the mesh reader or infer which authored pose is intended.
    In particular Mij are flattened by rows, then current C# reads by columns.
    """
    names = avatar["bonePathsStr"]
    paths = avatar["bonePaths"]
    if len(names) != len(paths) or len(names) != len(model["bones"]):
        raise ValueError("Avatar/model bone count mismatch")
    hashes = []
    for index, (name, path, bone) in enumerate(
        zip(names, paths, model["bones"], strict=True)
    ):
        chain = path["boneIdxs"]
        if (
            not chain
            or chain[-1] != index
            or any(
                type(item) is not int or not 0 <= item < len(names) for item in chain
            )
            or len(set(chain)) != len(chain)
        ):
            raise ValueError("Invalid source Avatar path")
        parent = chain[-2] if len(chain) > 1 else -1
        if bone != {"name": name or "Armature", "parent": parent}:
            raise ValueError("Model bone definition differs from source Avatar")
        full_path = "/".join(names[item] for item in chain if names[item])
        hashes.append(zlib.crc32(full_path.encode("utf-8")))
    if len(set(hashes)) != len(hashes):
        raise ValueError("Ambiguous Avatar path CRC")
    raw_by_name = {mesh["m_Name"]: mesh for mesh in raw_meshes}
    model_names = [mesh["name"] for mesh in model["meshes"]]
    if (
        len(raw_by_name) != len(raw_meshes)
        or len(set(model_names)) != len(model_names)
        or set(raw_by_name) != set(model_names)
        or not model_names
    ):
        raise ValueError("Missing/duplicate raw or model mesh")
    count = 0
    for mesh in model["meshes"]:
        raw = raw_by_name[mesh["name"]]
        palette = mesh["bones"]
        if any(
            type(index) is not int or not 0 <= index < len(names) for index in palette
        ):
            raise ValueError("Invalid model palette")
        if [hashes[index] for index in palette] != raw["m_BoneNameHashes"]:
            raise ValueError("Model palette differs from source name hashes")
        matrices = raw["m_BindPose"]
        if len(matrices) != len(palette):
            raise ValueError("Raw bindpose count mismatch")
        keys = [f"M{row}{col}" for row in range(4) for col in range(4)]
        if any(not set(keys).issubset(matrix) for matrix in matrices):
            raise ValueError("Missing raw matrix field")
        flat = [matrix[key] for matrix in matrices for key in keys]
        if (
            not np.isfinite(np.array(flat, dtype=float)).all()
            or flat != mesh["bindPoses"]
        ):
            raise ValueError("Model bindpose values differ from original raw export")
        count += len(matrices)
    return {
        "source_model_bone_definitions_match": True,
        "raw_palette_and_bindposes_exact_match": True,
        "meshes": len(model_names),
        "bindpose_matrices": count,
        "non_claim": "Exact match to existing raw exports, not independent certification of the original mesh parser or authored/rest pose equivalence.",
    }


def physics_binding_plan(
    bindings: dict[str, Any], mapping: list[dict[str, Any]], weighted: set[int]
) -> dict[str, Any]:
    """Resolve references and preserve extra mount TRS without installing physics."""
    nodes = {node["id"]: node for node in bindings["transforms"]}
    by_pid = {node["path_id"]: node for node in nodes.values()}
    indices = {
        entry["source_id"]: entry["model_index"]
        for entry in mapping
        if not entry["synthetic"]
    }

    def mapped_references(references: list[dict[str, Any]]) -> list[int]:
        if any(node["id"] not in indices for node in references):
            raise ValueError("Unmapped physics root/ignore reference")
        return [indices[node["id"]] for node in references]

    groups = []
    for group in bindings["groups"]:
        roots = mapped_references(group["roots"])
        groups.append(
            {
                "name": group["name"],
                "root_model_indices": roots,
                "unweighted_root_indices": [
                    index for index in roots if index not in weighted
                ],
                "ignored_model_indices": mapped_references(group["ignored"]),
                "collider_ids": group["collider_ids"],
            }
        )
    colliders = []
    for collider in bindings["colliders"]:
        node = nodes.get(collider["transform_id"])
        chain = []
        visited = set()
        while node is not None and node["id"] not in indices:
            if node["id"] in visited:
                raise ValueError("Cyclic collider mount ancestry")
            visited.add(node["id"])
            chain.append(node)
            node = by_pid.get(node["parent_path_id"])
        if node is None:
            raise ValueError("Collider mount has no mapped ancestor")
        chain.reverse()
        matrix = np.eye(4)
        for step in chain:
            matrix = matrix @ trs(step)
        colliders.append(
            {
                "component_id": collider["id"],
                "source_transform_id": collider["transform_id"],
                "anchor_model_index": indices[node["id"]],
                "source_local_chain": [
                    {
                        key: step[key]
                        for key in (
                            "id",
                            "name",
                            "local_position",
                            "local_rotation_xyzw",
                            "local_scale",
                        )
                    }
                    for step in chain
                ],
                "anchor_local_matrix": matrix.tolist(),
                "shape_fingerprint": collider["shape_fingerprint"],
                "class_resolved": collider["class_resolved"],
            }
        )
    return {
        "groups": groups,
        "colliders": colliders,
        "runtime_ready": False,
        "non_claim": "A source-local mount plan, not a collider geometry conversion or proof of target local-axis equivalence; official classes, semantics and pose-space gates remain pending.",
    }


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
    # Relative transforms cancel any uniform left basis. Compare each weighted
    # bone to its nearest weighted ancestor; never invent identity for helpers
    # that have no stored bindpose. A spanning interval is not a single-joint
    # attribution and must retain its intermediate indices.
    bind_worlds = {
        index: np.linalg.inv(matrix) for index, matrix in first_bind_by_bone.items()
    }
    intervals = []
    unanchored_roots = []
    for index in sorted(bind_worlds):
        ancestor = model["bones"][index]["parent"]
        intermediate = []
        while ancestor != -1 and ancestor not in bind_worlds:
            intermediate.append(ancestor)
            ancestor = model["bones"][ancestor]["parent"]
        if ancestor == -1:
            unanchored_roots.append(index)
            continue
        source = by_id[mapping[index]["source_id"]]
        source_ancestor = by_id[mapping[ancestor]["source_id"]]
        source_relative = np.linalg.inv(world(source_ancestor["path_id"])) @ world(
            source["path_id"]
        )
        bind_relative = np.linalg.inv(bind_worlds[ancestor]) @ bind_worlds[index]
        local_translation = float(
            np.linalg.norm(source_relative[:3, 3] - bind_relative[:3, 3])
        )
        local_linear = float(
            np.max(np.abs(source_relative[:3, :3] - bind_relative[:3, :3]))
        )
        intervals.append(
            {
                "model_index": index,
                "model_path": mapping[index]["model_path"],
                "ancestor_model_index": ancestor,
                "ancestor_model_path": mapping[ancestor]["model_path"],
                "direct_parent": not intermediate,
                "unweighted_intermediate_indices": intermediate,
                "translation_deviation": local_translation,
                "linear_deviation": local_linear,
                "matched": local_translation <= 1e-4 and local_linear <= 1e-4,
                "source_relative_matrix": source_relative.tolist(),
                "bind_relative_matrix": bind_relative.tolist(),
            }
        )
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
        "local_interval_audit": {
            "palette_input_consistent": repeat_maximum <= 1e-4,
            "matched_intervals": sum(item["matched"] for item in intervals),
            "mismatched_intervals": sum(not item["matched"] for item in intervals),
            "unanchored_palette_roots": unanchored_roots,
            "intervals": intervals,
            "non_claim": "Relative intervals cancel the global basis; spanning intervals cannot isolate an individual unweighted joint. Neither a match nor a mismatch supplies a runtime pose correction.",
        },
        "worst_observations": sorted(
            deviations, key=lambda item: item["translation_deviation"], reverse=True
        )[:20],
        "runtime_modified": False,
        "non_claim": "A failed gate does not identify the cause: authored prefab pose, mesh/bind space, importer basis or mapping need separate investigation.",
    }


def export_files(
    bindings_path: Path,
    model_path: Path,
    contract_path: Path,
    output: Path,
    avatar_path: Path | None = None,
    raw_mesh_dir: Path | None = None,
) -> None:
    if output.exists():
        raise FileExistsError(f"Refusing to overwrite {output}")
    paths = [bindings_path, model_path, contract_path]
    inputs = [json.loads(path.read_text(encoding="utf-8-sig")) for path in paths]
    bindings, model, contract = inputs
    if (avatar_path is None) != (raw_mesh_dir is None):
        raise ValueError("Pass both source Avatar and raw mesh directory")
    provenance = None
    if avatar_path is not None and raw_mesh_dir is not None:
        raw_paths = sorted(raw_mesh_dir.glob("*.json"))
        avatar = json.loads(avatar_path.read_text(encoding="utf-8-sig"))
        raw_meshes = [
            json.loads(path.read_text(encoding="utf-8-sig")) for path in raw_paths
        ]
        provenance = audit_model_provenance(model, avatar, raw_meshes)
        paths.extend([avatar_path, *raw_paths])
    mapping = map_bones(bindings, model["bones"], contract)
    result = {
        "schema_version": 1,
        "runtime_modified": False,
        "identity_mapping_pass": True,
        "mapping": mapping,
        "basis_audit": audit_basis(bindings, mapping, model),
        "source_model_provenance": provenance,
        "physics_binding_plan": physics_binding_plan(
            bindings,
            mapping,
            {index for mesh in model["meshes"] for index in mesh["bones"]},
        ),
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
    parser.add_argument("--avatar", type=Path)
    parser.add_argument("--raw-mesh-dir", type=Path)
    args = parser.parse_args()
    export_files(
        args.bindings,
        args.model,
        args.contract,
        args.output,
        args.avatar,
        args.raw_mesh_dir,
    )
    print(f"Offline skeleton mapping/basis audit: {args.output}")


if __name__ == "__main__":
    main()
