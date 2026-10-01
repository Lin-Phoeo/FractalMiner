"""Map by parent identity; aliases need explicit expected source names."""

import copy
import hashlib
import json
import sys
import zlib
from pathlib import Path

import numpy as np
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from export_official_physics_bindings import build_bindings
from map_official_physics_skeleton import (
    audit_basis,
    audit_model_provenance,
    export_files,
    map_bones,
    physics_binding_plan,
    trs,
)
from test_export_official_physics_bindings import fixture


def inputs():
    objects, groups = fixture()
    bindings = build_bindings(objects, groups)
    bones = [
        {"name": "Armature", "parent": -1},
        {"name": "Root", "parent": -1},
        {"name": "left", "parent": 1},
        {"name": "same", "parent": 1},
    ]
    contract = {
        "source_anchor_names": [],
        "synthetic_model_roots": ["Armature"],
        "aliases": {
            "Root/left": {"source_id": "CAB-test:2", "expected_source_name": "same"},
            "Root/same": {"source_id": "CAB-test:3", "expected_source_name": "same"},
        },
    }
    return bindings, bones, contract


def test_id_mapping_preserves_aliases_and_synthetic_root():
    bindings, bones, contract = inputs()
    result = map_bones(bindings, bones, contract)
    assert result[0]["synthetic"] is True
    assert result[2]["source_id"] == "CAB-test:2"
    assert result[3]["source_id"] == "CAB-test:3"
    assert result[2]["alias_used"] is True
    contract["source_anchor_names"] = ["Root"]
    bones[1]["name"] = "same"
    bones[2]["parent"] = -1
    with pytest.raises(ValueError):
        map_bones(bindings, bones, contract)


@pytest.mark.parametrize(
    "case",
    [
        "missing_alias",
        "wrong_name",
        "wrong_parent",
        "cycle",
        "bad_index",
        "synthetic_child",
        "unused_alias",
        "reused_id",
    ],
)
def test_invalid_identity_maps_stop(case):
    bindings, bones, contract = inputs()
    if case == "missing_alias":
        del contract["aliases"]["Root/same"]
    elif case == "wrong_name":
        contract["aliases"]["Root/left"]["expected_source_name"] = "other"
    elif case == "wrong_parent":
        contract["aliases"]["Root/left"]["source_id"] = "CAB-test:1"
    elif case == "cycle":
        bones[1]["parent"] = 2
    elif case == "bad_index":
        bones[2]["parent"] = 99
    elif case == "synthetic_child":
        bones[1]["parent"] = 0
    elif case == "unused_alias":
        contract["aliases"]["missing"] = copy.deepcopy(contract["aliases"]["Root/left"])
    elif case == "reused_id":
        contract["aliases"]["Root/same"]["source_id"] = "CAB-test:2"
    with pytest.raises(ValueError):
        map_bones(bindings, bones, contract)


def model_for_basis(bones):
    matrices = []
    for x in (0.1, 0.2):
        matrix = np.eye(4)
        matrix[0, 3] = -x
        matrices.extend(matrix.flatten(order="F").tolist())
    return {
        "bones": bones,
        "meshes": [{"name": "mesh", "bones": [1, 2], "bindPoses": matrices}],
    }


def provenance_inputs():
    _, bones, _ = inputs()
    model = model_for_basis(bones)
    avatar = {
        "bonePathsStr": ["", "Root", "left", "same"],
        "bonePaths": [{"boneIdxs": path} for path in ([0], [1], [1, 2], [1, 3])],
    }
    mesh = model["meshes"][0]
    raw = {
        "m_Name": "mesh",
        "m_BoneNameHashes": [
            zlib.crc32(path.encode()) for path in ("Root", "Root/left")
        ],
        "m_BindPose": [
            {
                f"M{row}{col}": mesh["bindPoses"][offset * 16 + row * 4 + col]
                for row in range(4)
                for col in range(4)
            }
            for offset in range(2)
        ],
    }
    return model, avatar, [raw]


def test_model_provenance_matches_original_avatar_and_raw_bindposes():
    model, avatar, raw = provenance_inputs()
    report = audit_model_provenance(model, avatar, raw)
    assert report["source_model_bone_definitions_match"] is True
    assert report["raw_palette_and_bindposes_exact_match"] is True
    assert report["bindpose_matrices"] == 2


@pytest.mark.parametrize(
    "case",
    [
        "bone_name",
        "bone_parent",
        "palette",
        "matrix",
        "missing",
        "duplicate",
        "count",
        "path",
        "palette_index",
        "matrix_count",
        "matrix_field",
        "nonfinite",
    ],
)
def test_model_provenance_stops_on_reconstruction_drift(case):
    model, avatar, raw = provenance_inputs()
    if case == "bone_name":
        model["bones"][2]["name"] = "other"
    elif case == "bone_parent":
        model["bones"][2]["parent"] = -1
    elif case == "palette":
        raw[0]["m_BoneNameHashes"][0] = 999
    elif case == "matrix":
        raw[0]["m_BindPose"][0]["M30"] += 0.001
    elif case == "missing":
        raw.clear()
    elif case == "duplicate":
        raw.append(copy.deepcopy(raw[0]))
    elif case == "count":
        avatar["bonePathsStr"].pop()
    elif case == "path":
        avatar["bonePaths"][2]["boneIdxs"] = [1, 99, 2]
    elif case == "palette_index":
        model["meshes"][0]["bones"][0] = -1
    elif case == "matrix_count":
        raw[0]["m_BindPose"].pop()
    elif case == "matrix_field":
        del raw[0]["m_BindPose"][0]["M00"]
    elif case == "nonfinite":
        raw[0]["m_BindPose"][0]["M00"] = float("nan")
    with pytest.raises(ValueError):
        audit_model_provenance(model, avatar, raw)


def test_basis_gate_separates_identity_from_pose_compatibility():
    bindings, bones, contract = inputs()
    mapping = map_bones(bindings, bones, contract)
    model = model_for_basis(bones)
    result = audit_basis(bindings, mapping, model)
    assert result["constant_left_basis_pass"] is True
    assert result["bone_observations"] == 2
    assert result["repeated_palette_bindpose_pass"] is True
    np.testing.assert_allclose(result["candidate_basis"], np.eye(4), atol=1e-8)
    model["meshes"][0]["bindPoses"][28] -= 0.25
    result = audit_basis(bindings, mapping, model)
    assert result["constant_left_basis_pass"] is False
    assert result["maximum_translation_deviation"] == pytest.approx(0.25)


def test_repeated_palette_gate_distinguishes_per_mesh_conflicts():
    bindings, bones, contract = inputs()
    mapping = map_bones(bindings, bones, contract)
    model = model_for_basis(bones)
    model["meshes"].append(copy.deepcopy(model["meshes"][0]))
    model["meshes"][1]["name"] = "second"
    result = audit_basis(bindings, mapping, model)
    assert result["repeated_palette_bindpose_pass"] is True
    assert result["repeated_palette_bones"] == 2
    assert result["maximum_repeated_bindpose_entry_deviation"] == 0
    model["meshes"][1]["bindPoses"][12] += 0.02
    result = audit_basis(bindings, mapping, model)
    assert result["repeated_palette_bindpose_pass"] is False
    assert result["maximum_repeated_bindpose_entry_deviation"] == pytest.approx(0.02)


def test_local_interval_audit_cancels_global_basis():
    bindings, bones, contract = inputs()
    mapping = map_bones(bindings, bones, contract)
    model = model_for_basis(bones)
    basis = trs(
        {
            "local_position": [1, 2, 3],
            "local_rotation_xyzw": [0, 0, np.sqrt(0.5), np.sqrt(0.5)],
            "local_scale": [1, 1, 1],
        }
    )
    for offset in range(2):
        matrix = np.array(
            model["meshes"][0]["bindPoses"][16 * offset : 16 * (offset + 1)]
        )
        matrix = matrix.reshape((4, 4), order="F") @ basis
        model["meshes"][0]["bindPoses"][16 * offset : 16 * (offset + 1)] = (
            matrix.flatten(order="F").tolist()
        )
    result = audit_basis(bindings, mapping, model)["local_interval_audit"]
    assert result["matched_intervals"] == 1
    assert result["mismatched_intervals"] == 0
    assert result["unanchored_palette_roots"] == [1]
    assert result["intervals"][0]["ancestor_model_index"] == 1
    assert result["intervals"][0]["model_index"] == 2


def test_local_interval_audit_identifies_first_changed_joint():
    bindings, bones, contract = inputs()
    mapping = map_bones(bindings, bones, contract)
    model = model_for_basis(bones)
    model["meshes"][0]["bindPoses"][28] -= 0.25
    interval = audit_basis(bindings, mapping, model)["local_interval_audit"]
    assert interval["mismatched_intervals"] == 1
    assert interval["intervals"][0]["translation_deviation"] == pytest.approx(0.25)
    assert interval["intervals"][0]["direct_parent"] is True


def test_local_interval_audit_spans_unweighted_helper():
    bindings, bones, contract = inputs()
    helper = copy.deepcopy(bindings["transforms"][1])
    helper.update(id="CAB-test:5", path_id=5, name="helper", parent_path_id=1)
    helper["local_position"] = [0.0, 0.0, 0.0]
    bindings["transforms"].append(helper)
    child = next(node for node in bindings["transforms"] if node["path_id"] == 2)
    child["parent_path_id"] = 5
    bones.append({"name": "helper", "parent": 1})
    bones[2]["parent"] = 4
    contract["aliases"]["Root/helper/left"] = contract["aliases"].pop("Root/left")
    mapping = map_bones(bindings, bones, contract)
    result = audit_basis(bindings, mapping, model_for_basis(bones))[
        "local_interval_audit"
    ]
    assert result["matched_intervals"] == 1
    assert result["intervals"][0]["direct_parent"] is False
    assert result["intervals"][0]["unweighted_intermediate_indices"] == [4]


def test_physics_plan_retains_extra_collider_mount_chain():
    bindings, bones, contract = inputs()
    mapping = map_bones(bindings, bones, contract)
    plan = physics_binding_plan(bindings, mapping, {1, 2})
    assert plan["runtime_ready"] is False
    assert plan["groups"][0]["root_model_indices"] == [2, 3]
    mount = plan["colliders"][0]
    assert mount["anchor_model_index"] == 1
    assert [node["id"] for node in mount["source_local_chain"]] == ["CAB-test:4"]
    np.testing.assert_allclose(
        mount["anchor_local_matrix"], trs(bindings["transforms"][3])
    )
    assert mount["class_resolved"] is False
    bindings["colliders"][0]["transform_id"] = "CAB-test:1"
    mount = physics_binding_plan(bindings, mapping, {1, 2})["colliders"][0]
    assert mount["source_local_chain"] == []
    np.testing.assert_allclose(mount["anchor_local_matrix"], np.eye(4))


@pytest.mark.parametrize("case", ["root", "ignored", "unanchored", "cycle"])
def test_physics_plan_stops_on_unresolved_mount_or_bone(case):
    bindings, bones, contract = inputs()
    mapping = map_bones(bindings, bones, contract)
    if case == "root":
        bindings["groups"][0]["roots"][0]["id"] = "absent"
    elif case == "ignored":
        bindings["groups"][0]["ignored"] = [{"id": "absent"}]
    else:
        collider = next(node for node in bindings["transforms"] if node["path_id"] == 4)
        collider["parent_path_id"] = 0 if case == "unanchored" else 4
    with pytest.raises(ValueError):
        physics_binding_plan(bindings, mapping, {1, 2})


def test_nonuniform_scaled_quaternion_trs():
    node = {
        "local_position": [1, 2, 3],
        "local_rotation_xyzw": [0, 0, np.sqrt(0.5), np.sqrt(0.5)],
        "local_scale": [2, 3, 4],
    }
    np.testing.assert_allclose(
        trs(node), [[0, -3, 0, 1], [2, 0, 0, 2], [0, 0, 4, 3], [0, 0, 0, 1]], atol=1e-8
    )


@pytest.mark.parametrize(
    "case", ["synthetic", "length", "nonfinite", "singular", "empty"]
)
def test_corrupt_bindpose_inputs_stop(case):
    bindings, bones, contract = inputs()
    mapping = map_bones(bindings, bones, contract)
    model = model_for_basis(bones)
    if case == "synthetic":
        model["meshes"][0]["bones"][0] = 0
    elif case == "length":
        model["meshes"][0]["bindPoses"].pop()
    elif case == "nonfinite":
        model["meshes"][0]["bindPoses"][0] = float("nan")
    elif case == "singular":
        model["meshes"][0]["bindPoses"][:16] = [0.0] * 16
    elif case == "empty":
        model["meshes"].clear()
    with pytest.raises(ValueError):
        audit_basis(bindings, mapping, model)


def test_export_records_hashes_preserves_inputs_and_refuses_overwrite(tmp_path):
    bindings, bones, contract = inputs()
    model = model_for_basis(bones)
    paths = [
        tmp_path / name for name in ("bindings.json", "model.json", "contract.json")
    ]
    for path, data in zip(paths, (bindings, model, contract), strict=True):
        path.write_text(json.dumps(data), encoding="utf-8")
    originals = [path.read_bytes() for path in paths]
    bindings_path, model_path, contract_path = paths
    output = tmp_path / "audit.json"
    export_files(bindings_path, model_path, contract_path, output)
    report = json.loads(output.read_text(encoding="utf-8"))
    assert report["identity_mapping_pass"] is True
    assert report["runtime_modified"] is False
    assert report["basis_audit"]["constant_left_basis_pass"] is True
    assert report["source_sha256"] == {
        str(path.resolve()): hashlib.sha256(raw).hexdigest()
        for path, raw in zip(paths, originals, strict=True)
    }
    before = output.read_bytes()
    with pytest.raises(FileExistsError):
        export_files(bindings_path, model_path, contract_path, output)
    assert output.read_bytes() == before
    assert [path.read_bytes() for path in paths] == originals


def test_export_can_verify_raw_sources_but_requires_both_options(tmp_path):
    bindings, _, contract = inputs()
    model, avatar, raw = provenance_inputs()
    inputs_paths = [
        tmp_path / name
        for name in ("bindings.json", "model.json", "contract.json", "avatar.json")
    ]
    for path, data in zip(
        inputs_paths, (bindings, model, contract, avatar), strict=True
    ):
        path.write_text(json.dumps(data), encoding="utf-8")
    bindings_path, model_path, contract_path, avatar_path = inputs_paths
    raw_dir = tmp_path / "raw"
    raw_dir.mkdir()
    raw_path = raw_dir / "mesh.json"
    raw_path.write_text(json.dumps(raw[0]), encoding="utf-8")
    output = tmp_path / "verified.json"
    with pytest.raises(ValueError):
        export_files(bindings_path, model_path, contract_path, output, avatar_path)
    assert not output.exists()
    export_files(bindings_path, model_path, contract_path, output, avatar_path, raw_dir)
    report = json.loads(output.read_text(encoding="utf-8"))
    assert report["source_model_provenance"]["bindpose_matrices"] == 2
    assert report["physics_binding_plan"]["runtime_ready"] is False
    assert str(avatar_path.resolve()) in report["source_sha256"]
    assert str(raw_path.resolve()) in report["source_sha256"]
