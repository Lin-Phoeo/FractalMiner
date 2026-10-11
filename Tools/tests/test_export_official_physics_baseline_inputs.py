"""Sealed two-document production rejects mixed runtime IDs/provenance."""

import copy
import hashlib
import json
import runpy
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from export_official_physics_baseline_inputs import build_document, export_file


def fixture():
    imported = {
        "schema_version": 1,
        "getter_scope": "synthetic",
        "full_proxy_inputs_generated": False,
        "states": [
            {
                "name": "rest",
                "groups": [
                    {
                        "name": "fixture",
                        "component_identity": "fixture:7",
                        "skin_bone_count": 3,
                        "runtime_instance_ids": (-10, 20, -30, 90),
                        "runtime_parent_ids": (50, -10, 20, 50),
                        "runtime_root_ids": (-10,),
                        "snapshots": ({},) * 4,
                        "vertices": {
                            "frames": {
                                "positions": ((0, 0, 0), (1, 0, 0), (1, 2, 0)),
                                "normals": ((0, 1, 0),) * 3,
                                "tangents": ((0, 0, 1),) * 3,
                            }
                        },
                    }
                ],
            }
        ],
    }
    frames = {
        "schema_version": 1,
        "getter_scope": "synthetic",
        "import_context": "explicit fresh empty ordinary BoneCloth import; unchanged unreduced skin order",
        "override_context": "explicit empty overrides for reconstructed reference only; not observed game state",
        "triangle_context": "explicit zero-triangle Line reference; not observed game proxy",
        "line_frame_reference_generated": True,
        "optimization_preserves_source_slots_on_selected_route": True,
        "none_alignment_identity_caller_contract": True,
        "full_proxy_inputs_generated": False,
        "states": [
            {
                "name": "rest",
                "groups": [
                    {
                        "name": "fixture",
                        "component_identity": "fixture:7",
                        "skin_bone_count": 3,
                        "source_vertex_indices": (0, 1, 2),
                        "proxy_attributes": (1, 2, 2),
                        "transform_flags": (11, 13, 13, 1),
                    }
                ],
            }
        ],
    }
    return imported, frames


def test_complete_outputs_keep_source_and_render_slot_separate():
    values = fixture()
    before = copy.deepcopy(values)
    result = build_document(
        *values, fresh_serial_no_resize=True, cleared_output_buffers=True
    )
    group = result["states"][0]["groups"][0]
    assert group["parents"] == (-1, 0, 1)
    assert group["baselines"]["data"] == (0, 1, 2)
    assert group["root_depth"]["lengths"] == (0, 1, 3)
    assert group["transform_flags"] == (11, 13, 13, 1)
    assert result["baseline_reference_generated"] is True
    assert result["official_solver_integrated"] is False
    assert result["native_arrays_published"] is False
    assert values == before


@pytest.mark.parametrize("key", ["fresh_serial_no_resize", "cleared_output_buffers"])
def test_premise_required(key):
    with pytest.raises(ValueError):
        build_document(
            *fixture(),
            **(
                {"fresh_serial_no_resize": True, "cleared_output_buffers": True}
                | {key: False}
            )
        )


@pytest.mark.parametrize(
    "corruption",
    [
        "schema",
        "scope",
        "context",
        "override",
        "triangle",
        "optimized",
        "not_line",
        "full_proxy",
        "empty_states",
        "state_count",
        "state_name",
        "duplicate_state",
        "group_count",
        "group_name",
        "duplicate_group",
        "identity",
        "skin_count",
        "snapshots",
        "ids",
        "parents",
        "slots",
        "flags",
        "render_root",
    ],
)
def test_bad_provenance_shapes_and_routes_refused(corruption):
    imported, frames = fixture()
    source, final = imported["states"][0]["groups"][0], frames["states"][0]["groups"][0]
    if corruption == "schema":
        imported["schema_version"] = True
    elif corruption == "scope":
        frames["getter_scope"] = "different"
    elif corruption == "context":
        frames["import_context"] = "unknown"
    elif corruption == "override":
        frames["override_context"] = "unknown"
    elif corruption == "triangle":
        frames["triangle_context"] = "unknown"
    elif corruption == "optimized":
        frames["optimization_preserves_source_slots_on_selected_route"] = False
    elif corruption == "not_line":
        frames["line_frame_reference_generated"] = False
    elif corruption == "full_proxy":
        frames["full_proxy_inputs_generated"] = True
    elif corruption == "empty_states":
        imported["states"] = frames["states"] = []
    elif corruption == "state_count":
        frames["states"] = []
    elif corruption == "state_name":
        frames["states"][0]["name"] = "other"
    elif corruption == "duplicate_state":
        for doc in (imported, frames):
            doc["states"] *= 2
    elif corruption == "group_count":
        frames["states"][0]["groups"] = []
    elif corruption == "group_name":
        final["name"] = "other"
    elif corruption == "duplicate_group":
        for doc in (imported, frames):
            doc["states"][0]["groups"] *= 2
    elif corruption == "identity":
        final["component_identity"] = "other:8"
    elif corruption == "skin_count":
        final["skin_bone_count"] = 4
    elif corruption == "snapshots":
        source["snapshots"] = []
    elif corruption == "ids":
        source["runtime_instance_ids"] = (1, 2, 3)
    elif corruption == "parents":
        source["runtime_parent_ids"] = (1, 2, 3)
    elif corruption == "slots":
        final["source_vertex_indices"] = (2, 1, 0)
    elif corruption == "flags":
        final["transform_flags"] = (11, 13, 13, 13)
    elif corruption == "render_root":
        source["runtime_root_ids"] = (90,)
    with pytest.raises(ValueError):
        build_document(
            imported, frames, fresh_serial_no_resize=True, cleared_output_buffers=True
        )


def test_seals_output_exclusive_cli_and_nested_input_provenance(
    tmp_path, monkeypatch, capsys
):
    docs = fixture()
    paths = (tmp_path / "imports.json", tmp_path / "frames.json")
    output = tmp_path / "output.json"
    paths[0].write_text(json.dumps(docs[0]), encoding="utf-8")
    imports_seal = hashlib.sha256(paths[0].read_bytes()).hexdigest()
    docs[1]["input_sha256"] = {"imports": "0" * 64}
    paths[1].write_text(json.dumps(docs[1]), encoding="utf-8")
    seals = (imports_seal, hashlib.sha256(paths[1].read_bytes()).hexdigest())
    kwargs = {"fresh_serial_no_resize": True, "cleared_output_buffers": True}
    with pytest.raises(ValueError):
        export_file(*paths, output, ("x", seals[1]), **kwargs)
    with pytest.raises(ValueError):
        export_file(*paths, output, ("0" * 64, seals[1]), **kwargs)
    with pytest.raises(ValueError):
        export_file(*paths, output, seals, **kwargs)
    docs[1]["input_sha256"]["imports"] = imports_seal
    paths[1].write_text(json.dumps(docs[1]), encoding="utf-8")
    seals = (imports_seal, hashlib.sha256(paths[1].read_bytes()).hexdigest())
    args = [
        "export",
        "--fresh-serial-no-resize",
        "--cleared-output-buffers",
        "--output",
        str(output),
    ]
    for name, path, seal in zip(("imports", "frames"), paths, seals, strict=True):
        args += ["--" + name, str(path), "--" + name + "-sha256", seal]
    monkeypatch.setattr(sys, "argv", args)
    runpy.run_path(
        str(
            Path(__file__).resolve().parents[1]
            / "export_official_physics_baseline_inputs.py"
        ),
        run_name="__main__",
    )
    assert "Baseline reference exported" in capsys.readouterr().out
    assert (
        json.loads(output.read_text(encoding="utf-8"))["input_sha256"]["imports"]
        == imports_seal
    )
    with pytest.raises(FileExistsError):
        export_file(*paths, output, seals, **kwargs)
