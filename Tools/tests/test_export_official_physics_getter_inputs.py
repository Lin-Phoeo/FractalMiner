"""Getter-schema and sealed CLI fixtures, not original game execution."""

import copy
import hashlib
import json
import runpy
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from export_official_physics_getter_inputs import build_document, export_file

BINDINGS_SHA = "a" * 64


def matrices(x=0):
    return {
        "c0": [1, 0, 0, 0],
        "c1": [0, 1, 0, 0],
        "c2": [0, 0, 1, 0],
        "c3": [x, 0, 0, 1],
    }


def fixture():
    bindings = {
        "schema_version": 1,
        "transform_count": 2,
        "transforms": [
            {
                "id": "file:1",
                "path_id": 1,
                "parent_path_id": 9,
                "children_path_ids": [],
            },
            {
                "id": "file:9",
                "path_id": 9,
                "parent_path_id": 0,
                "children_path_ids": [1],
            },
        ],
        "groups": [
            {
                "name": "fixture",
                "component_id": "file:77",
                "owner_transform_id": "file:9",
                "roots": [{"id": "file:1"}],
                "ignored": [],
            }
        ],
    }
    samples = []
    for n, parent, x in [(1, 109, 7), (9, 0, 4)]:
        samples.append(
            {
                "identity": f"file:{n}",
                "instance_id": 100 + n,
                "parent_instance_id": parent,
                "position": [x, 0, 0],
                "rotation": [0, 0, 0, 1],
                "local_position": [2, 0, 0],
                "local_rotation": [0, 0, 0, 1],
                "local_to_world": matrices(x),
                "world_to_local": matrices(-x),
            }
        )
    capture = {
        "schema_version": 1,
        "bindings_sha256": BINDINGS_SHA,
        "unity_version": "2022.3.30f1",
        "scope": "synthetic fixture, no runtime oracle",
        "synthetic_getter_checks_passed": True,
        "states": [{"name": "fixture", "samples": samples}],
    }
    return bindings, capture


def test_capture_preserves_provenance_and_outputs_skin_vertices_not_render():
    bindings, capture = fixture()
    before = copy.deepcopy((bindings, capture))
    output = build_document(bindings, capture, BINDINGS_SHA)
    group = output["states"][0]["groups"][0]
    assert group["vertices"]["frames"]["positions"] == ((3, 0, 0),)
    assert group["runtime_instance_ids"] == (101, 109)
    assert output["getter_scope"] == capture["scope"]
    assert output["full_proxy_inputs_generated"] is False
    assert output["selection_attributes_generated"] is False
    assert (bindings, capture) == before


@pytest.mark.parametrize(
    "change",
    [
        "schema",
        "bool_schema",
        "seal",
        "empty_states",
        "duplicate_state",
        "empty_name",
        "duplicate_sample",
        "missing_sample",
        "extra_sample",
        "bad_matrix",
        "missing_matrix_column",
        "bad_world",
        "nan_world",
        "zero_runtime",
        "same_runtime",
        "bad_parent",
    ],
)
def test_capture_corruption_refused(change):
    bindings, capture = fixture()
    state = capture["states"][0]
    if change == "schema":
        capture["schema_version"] = 2
    elif change == "bool_schema":
        capture["schema_version"] = True
    elif change == "seal":
        capture["bindings_sha256"] = "b" * 64
    elif change == "empty_states":
        capture["states"] = []
    elif change == "duplicate_state":
        capture["states"].append(copy.deepcopy(state))
    elif change == "empty_name":
        state["name"] = ""
    elif change == "duplicate_sample":
        state["samples"].append(copy.deepcopy(state["samples"][0]))
    elif change == "missing_sample":
        state["samples"].pop()
    elif change == "extra_sample":
        sample = copy.deepcopy(state["samples"][0])
        sample["identity"] = "file:2"
        state["samples"].append(sample)
    elif change == "bad_matrix":
        state["samples"][0]["local_to_world"]["c0"] = [1, 0]
    elif change == "missing_matrix_column":
        del state["samples"][0]["local_to_world"]["c0"]
    elif change == "bad_world":
        state["samples"][0]["position"] = [1, 2]
    elif change == "nan_world":
        state["samples"][0]["position"][0] = float("nan")
    elif change == "zero_runtime":
        state["samples"][0]["instance_id"] = 0
    elif change == "same_runtime":
        state["samples"][0]["instance_id"] = 109
    else:
        state["samples"][0]["parent_instance_id"] = 101
    with pytest.raises(ValueError):
        build_document(bindings, capture, BINDINGS_SHA)


def test_two_states_keep_distinct_instances_and_data_without_cross_state_join():
    bindings, capture = fixture()
    second = copy.deepcopy(capture["states"][0])
    second["name"] = "second"
    second["samples"][0]["instance_id"] = 201
    second["samples"][0]["parent_instance_id"] = 209
    second["samples"][1]["instance_id"] = 209
    capture["states"].append(second)
    output = build_document(bindings, capture, BINDINGS_SHA)
    assert output["states"][1]["groups"][0]["runtime_instance_ids"] == (201, 209)


def test_export_hash_guards_and_overwrite_refusal(tmp_path):
    bindings, capture = fixture()
    raw_b = json.dumps(bindings).encode()
    bs = hashlib.sha256(raw_b).hexdigest()
    capture["bindings_sha256"] = bs
    raw_c = json.dumps(capture).encode()
    cs = hashlib.sha256(raw_c).hexdigest()
    b, c, o = tmp_path / "b.json", tmp_path / "c.json", tmp_path / "output.json"
    b.write_bytes(raw_b)
    c.write_bytes(raw_c)
    with pytest.raises(ValueError):
        export_file(b, c, o, "0" * 64, cs)
    with pytest.raises(ValueError):
        export_file(b, c, o, bs, "0" * 64)
    with pytest.raises(ValueError):
        export_file(b, c, o, "x", cs)
    export_file(b, c, o, bs, cs)
    output = json.loads(o.read_text(encoding="utf-8"))
    assert output["source_sha256"] == {"bindings": bs, "getter_capture": cs}
    with pytest.raises(FileExistsError):
        export_file(b, c, o, bs, cs)
    assert b.read_bytes() == raw_b and c.read_bytes() == raw_c


def test_cli(tmp_path, monkeypatch, capsys):
    bindings, capture = fixture()
    raw_b = json.dumps(bindings).encode()
    bs = hashlib.sha256(raw_b).hexdigest()
    capture["bindings_sha256"] = bs
    raw_c = json.dumps(capture).encode()
    cs = hashlib.sha256(raw_c).hexdigest()
    b, c, o = tmp_path / "b.json", tmp_path / "c.json", tmp_path / "output.json"
    b.write_bytes(raw_b)
    c.write_bytes(raw_c)
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "export",
            "--bindings",
            str(b),
            "--getter-capture",
            str(c),
            "--bindings-sha256",
            bs,
            "--getter-sha256",
            cs,
            "--output",
            str(o),
        ],
    )
    runpy.run_path(
        str(
            Path(__file__).resolve().parents[1]
            / "export_official_physics_getter_inputs.py"
        ),
        run_name="__main__",
    )
    assert "Getter-based" in capsys.readouterr().out and o.exists()
