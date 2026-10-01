"""Map by parent identity; aliases need explicit expected source names."""

import copy
import hashlib
import json
import sys
from pathlib import Path

import numpy as np
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from export_official_physics_bindings import build_bindings
from map_official_physics_skeleton import audit_basis, export_files, map_bones, trs
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
