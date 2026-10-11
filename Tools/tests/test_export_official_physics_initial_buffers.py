"""Explicit fresh-import premise, sealed matched input, no output overwrite."""

import copy
import hashlib
import json
import runpy
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from export_official_physics_initial_buffers import build_document, export_file


def fixture():
    return {
        "schema_version": 1,
        "getter_scope": "synthetic reference only",
        "override_context": "explicit empty overrides for reconstructed reference only; not observed game state",
        "matched_selection_bytes_generated": True,
        "full_proxy_attributes_generated": False,
        "states": [
            {
                "name": "rest",
                "groups": [
                    {
                        "name": "fixture",
                        "component_identity": {"file": "fixture", "path_id": 7},
                        "skin_bone_count": 2,
                        "matched_selection_bytes": [1, 2],
                    }
                ],
            }
        ],
    }


def test_composes_all_states_without_promoting_to_full_proxy():
    source = fixture()
    before = copy.deepcopy(source)
    result = build_document(source, fresh_import=True)
    group = result["states"][0]["groups"][0]
    assert group["transform_flags"] == (11, 13, 1)
    assert group["proxy_attributes"] == (1, 2)
    assert result["full_proxy_inputs_generated"] is False
    assert result["runtime_overrides_observed"] is False
    assert result["getter_scope"] == source["getter_scope"]
    assert source == before


@pytest.mark.parametrize(
    "corruption",
    [
        "schema",
        "matched",
        "proxy",
        "override",
        "empty_states",
        "empty_groups",
        "count",
        "duplicate_state",
        "duplicate_group",
        "group_order",
    ],
)
def test_invalid_producer_or_shape_refused(corruption):
    source = fixture()
    group = source["states"][0]["groups"][0]
    if corruption == "schema":
        source["schema_version"] = True
    elif corruption == "matched":
        source["matched_selection_bytes_generated"] = False
    elif corruption == "proxy":
        source["full_proxy_attributes_generated"] = True
    elif corruption == "override":
        source["override_context"] = "unknown"
    elif corruption == "empty_states":
        source["states"] = []
    elif corruption == "empty_groups":
        source["states"][0]["groups"] = []
    elif corruption == "count":
        group["skin_bone_count"] = 3
    elif corruption == "duplicate_state":
        source["states"] *= 2
    elif corruption == "duplicate_group":
        source["states"][0]["groups"] *= 2
    else:
        state = copy.deepcopy(source["states"][0])
        state["name"] = "moved"
        state["groups"][0]["name"] = "other"
        source["states"].append(state)
    with pytest.raises(ValueError):
        build_document(source, fresh_import=True)


def test_export_pin_premise_and_overwrite(tmp_path):
    source, output = tmp_path / "input.json", tmp_path / "output.json"
    source.write_text(json.dumps(fixture()), encoding="utf-8")
    seal = hashlib.sha256(source.read_bytes()).hexdigest()
    with pytest.raises(ValueError):
        export_file(source, output, seal, fresh_import=False)
    for bad in ("x", "0" * 64):
        with pytest.raises(ValueError):
            export_file(source, output, bad, fresh_import=True)
    export_file(source, output, seal, fresh_import=True)
    assert (
        json.loads(output.read_text(encoding="utf-8"))["matched_input_sha256"] == seal
    )
    with pytest.raises(FileExistsError):
        export_file(source, output, seal, fresh_import=True)


def test_cli(tmp_path, monkeypatch, capsys):
    source, output = tmp_path / "input.json", tmp_path / "output.json"
    source.write_text(json.dumps(fixture()), encoding="utf-8")
    seal = hashlib.sha256(source.read_bytes()).hexdigest()
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "export",
            "--matched-input",
            str(source),
            "--matched-sha256",
            seal,
            "--output",
            str(output),
            "--fresh-ordinary-import",
        ],
    )
    runpy.run_path(
        str(
            Path(__file__).resolve().parents[1]
            / "export_official_physics_initial_buffers.py"
        ),
        run_name="__main__",
    )
    assert output.exists() and "Fresh BoneCloth" in capsys.readouterr().out
