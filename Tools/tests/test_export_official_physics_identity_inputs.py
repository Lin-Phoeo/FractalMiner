"""Hash-sealed file adapter and original identity graph integration fixtures."""

import copy
import hashlib
import json
import runpy
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from export_official_physics_identity_inputs import build_document, export_file


def document():
    return {
        "schema_version": 1,
        "transform_count": 3,
        "transforms": [
            {
                "id": "asset:9",
                "path_id": 9,
                "parent_path_id": 0,
                "children_path_ids": [1],
            },
            {
                "id": "asset:1",
                "path_id": 1,
                "parent_path_id": 9,
                "children_path_ids": [2],
            },
            {
                "id": "asset:2",
                "path_id": 2,
                "parent_path_id": 1,
                "children_path_ids": [],
            },
        ],
        "groups": [
            {
                "name": "fixture",
                "component_id": "asset:77",
                "owner_transform_id": "asset:9",
                "roots": [{"id": "asset:1"}],
                "ignored": [],
                "collider_ids": ["asset:88"],
            }
        ],
    }


def test_compile_document_keeps_serialized_order_and_ordinary_component_center():
    source = document()
    old = copy.deepcopy(source)
    result = build_document(source)
    group = result["groups"][0]
    assert group["ordered_transform_identities"] == ["asset:1", "asset:2", "asset:9"]
    assert group["snapshot_parent_indices"] == [2, 0, -1]
    assert group["skin_parent_indices"] == [-1, 0]
    assert group["root_indices"] == [0]
    assert group["collision_bone_indices"] is None
    assert (
        group["constructor_collision_argument_scope"]
        == "Init BoneCloth call passes null; runtime/prebuilt calls not inferred"
    )
    assert result["full_proxy_inputs_generated"] is False
    assert result["runtime_instance_ids_generated"] is False
    assert source == old


def test_names_are_labels_only_and_collider_refs_are_not_constructor_bones():
    source = document()
    source["transforms"][0]["name"] = "same"
    source["transforms"][1]["name"] = "same"
    source["groups"][0]["collider_ids"] = ["missing:123"]
    assert build_document(source)["groups"][0]["collision_bone_indices"] is None


@pytest.mark.parametrize(
    "change",
    [
        "version",
        "bool_version",
        "count",
        "bool_count",
        "duplicate_node",
        "path_mismatch",
        "null_node",
        "noncanonical",
        "duplicate_component",
        "missing_owner",
        "bad_parent",
        "bad_child",
        "bool_parent",
        "bool_child",
        "missing_root",
        "missing_ignore",
        "empty_groups",
    ],
)
def test_malformed_document_is_refused(change):
    source = document()
    if change == "version":
        source["schema_version"] = 2
    elif change == "bool_version":
        source["schema_version"] = True
    elif change == "count":
        source["transform_count"] = 4
    elif change == "bool_count":
        source["transform_count"] = True
    elif change == "duplicate_node":
        source["transforms"].append(source["transforms"][0])
        source["transform_count"] = 4
    elif change == "path_mismatch":
        source["transforms"][0]["path_id"] = 5
    elif change == "null_node":
        source["transforms"][0]["id"] = "asset:0"
    elif change == "noncanonical":
        source["transforms"][0]["id"] = "asset:09"
    elif change == "duplicate_component":
        source["groups"].append(source["groups"][0])
    elif change == "missing_owner":
        source["groups"][0]["owner_transform_id"] = "asset:8"
    elif change == "bad_parent":
        source["transforms"][1]["parent_path_id"] = 2**63
    elif change == "bad_child":
        source["transforms"][0]["children_path_ids"] = [2**63]
    elif change == "bool_parent":
        source["transforms"][0]["parent_path_id"] = False
    elif change == "bool_child":
        source["transforms"][0]["children_path_ids"] = [True]
    elif change == "missing_root":
        source["groups"][0]["roots"][0]["id"] = "asset:8"
    elif change == "missing_ignore":
        source["groups"][0]["ignored"] = [{"id": "asset:8"}]
    else:
        source["groups"] = []
    with pytest.raises(ValueError):
        build_document(source)


@pytest.mark.parametrize(
    "identity", [None, 1, "nocolon", "asset:x", ":1", "asset:+1", "asset: 1"]
)
def test_bad_component_identity_refused(identity):
    source = document()
    source["groups"][0]["component_id"] = identity
    with pytest.raises(ValueError):
        build_document(source)


def test_same_name_groups_are_kept_if_component_identity_differs():
    source = document()
    source["groups"].append(copy.deepcopy(source["groups"][0]))
    source["groups"][1]["component_id"] = "asset:78"
    result = build_document(source)
    assert len(result["groups"]) == 2


def test_hash_sealed_export_refuses_mismatch_or_existing_output(tmp_path):
    source, target = tmp_path / "source.json", tmp_path / "output.json"
    raw = json.dumps(document()).encode()
    source.write_bytes(raw)
    digest = hashlib.sha256(raw).hexdigest()
    with pytest.raises(ValueError):
        export_file(source, target, "0" * 64)
    assert not target.exists()
    export_file(source, target, digest)
    output = json.loads(target.read_text(encoding="utf-8"))
    assert output["source_sha256"] == digest
    with pytest.raises(FileExistsError):
        export_file(source, target, digest)
    assert source.read_bytes() == raw


@pytest.mark.parametrize("digest", ["", "abc", "G" * 64, "A" * 64])
def test_invalid_sha_argument_refused_before_reading(tmp_path, digest):
    with pytest.raises(ValueError):
        export_file(tmp_path / "absent", tmp_path / "output", digest)


def test_cli_exports_sealed_bindings(tmp_path, monkeypatch, capsys):
    source, target = tmp_path / "source.json", tmp_path / "output.json"
    raw = json.dumps(document()).encode()
    source.write_bytes(raw)
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "export",
            "--bindings",
            str(source),
            "--bindings-sha256",
            hashlib.sha256(raw).hexdigest(),
            "--output",
            str(target),
        ],
    )
    runpy.run_path(
        str(
            Path(__file__).resolve().parents[1]
            / "export_official_physics_identity_inputs.py"
        ),
        run_name="__main__",
    )
    assert "Identity-only" in capsys.readouterr().out
    assert (
        json.loads(target.read_text(encoding="utf-8"))["groups"][0]["skin_bone_count"]
        == 2
    )


def test_schema_noninteger_rejected():
    source = document()
    source["schema_version"] = "1"
    with pytest.raises(ValueError):
        build_document(source)
