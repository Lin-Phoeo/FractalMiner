"""Sealed source getter/frames/baselines to local Distance cache, not Teams."""

import copy
import hashlib
import json
import runpy
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from export_official_physics_baseline_inputs import build_document as build_baselines
from export_official_physics_distance_inputs import build_document, export_file


def fixture():
    imports = {
        "schema_version": 1,
        "getter_scope": "synthetic",
        "full_proxy_inputs_generated": False,
        "states": [
            {
                "name": "rest",
                "groups": [
                    {
                        "name": "fixture",
                        "component_identity": "fixture:9",
                        "skin_bone_count": 3,
                        "runtime_instance_ids": (-1, 2, -3, 99),
                        "runtime_parent_ids": (50, -1, 2, 50),
                        "runtime_root_ids": (-1,),
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
        "full_proxy_inputs_generated": False,
        "import_context": "explicit fresh empty ordinary BoneCloth import; unchanged unreduced skin order",
        "override_context": "explicit empty overrides for reconstructed reference only; not observed game state",
        "triangle_context": "explicit zero-triangle Line reference; not observed game proxy",
        "line_frame_reference_generated": True,
        "optimization_preserves_source_slots_on_selected_route": True,
        "none_alignment_identity_caller_contract": True,
        "states": [
            {
                "name": "rest",
                "groups": [
                    {
                        "name": "fixture",
                        "component_identity": "fixture:9",
                        "skin_bone_count": 3,
                        "source_vertex_indices": (0, 1, 2),
                        "proxy_attributes": (1, 2, 2),
                        "transform_flags": (11, 13, 13, 1),
                    }
                ],
            }
        ],
    }
    baselines = build_baselines(
        imports, frames, fresh_serial_no_resize=True, cleared_output_buffers=True
    )
    return imports, frames, json.loads(json.dumps(baselines))


def build(docs):
    return build_document(
        *docs, fresh_serial_no_resize=True, cleared_output_buffers=True
    )


def test_original_proxy_positions_and_domains_not_local_pose_or_render_snapshot():
    docs = fixture()
    before = copy.deepcopy(docs)
    result = build(docs)
    group = result["states"][0]["groups"][0]
    assert group["lines"] == ((0, 1), (1, 2))
    assert group["connectivity"]["rows"] == ((1,), (2, 0), (1,))
    assert group["distance"]["data"] == (1, 2, 0, 1)
    assert group["distance"]["signed_rest_lengths"] == (1, 2, 1, 2)
    assert group["distance"]["words"] == (1 << 20, (2 << 20) | 1, (1 << 20) | 3)
    assert group["skin_bone_count"] == 3 and len(group["transform_flags"]) == 4
    assert result["distance_reference_generated"] is True
    for flag in (
        "official_solver_integrated",
        "full_proxy_inputs_generated",
        "real_constraint_work_lists_generated",
        "native_arrays_published",
        "stage_modified",
    ):
        assert result[flag] is False
    assert docs == before


@pytest.mark.parametrize("key", ["fresh_serial_no_resize", "cleared_output_buffers"])
def test_premises_explicit(key):
    kwargs = {"fresh_serial_no_resize": True, "cleared_output_buffers": True}
    kwargs[key] = False
    with pytest.raises(ValueError):
        build_document(*fixture(), **kwargs)


@pytest.mark.parametrize(
    "corruption",
    [
        "parents",
        "depth",
        "attrs",
        "local_pose",
        "state_order",
        "scope",
        "integrated",
        "extra",
        "schema",
        "triangle",
        "bool_alias",
    ],
)
def test_mixed_or_tampered_baseline_route_rejected(corruption):
    imports, frames, baselines = fixture()
    group = baselines["states"][0]["groups"][0]
    if corruption == "parents":
        group["parents"][1] = -1
    elif corruption == "depth":
        group["root_depth"]["depths"][1] = 0.9
    elif corruption == "attrs":
        group["proxy_attributes"][0] = 2
    elif corruption == "local_pose":
        group["local_pose"]["positions"][2][0] = 2
    elif corruption == "state_order":
        baselines["states"][0]["name"] = "moved"
    elif corruption == "scope":
        baselines["getter_scope"] = "other"
    elif corruption == "integrated":
        baselines["official_solver_integrated"] = True
    elif corruption == "extra":
        baselines["unsupported_route"] = True
    elif corruption == "schema":
        baselines["schema_version"] = True
    elif corruption == "triangle":
        frames["triangle_context"] = "unknown"
    elif corruption == "bool_alias":
        baselines["baseline_reference_generated"] = 1
    with pytest.raises(ValueError):
        build((imports, frames, baselines))


def test_seals_nested_provenance_exclusive_output_and_cli(
    tmp_path, monkeypatch, capsys
):
    imports, frames, baselines = fixture()
    paths = (
        tmp_path / "imports.json",
        tmp_path / "frames.json",
        tmp_path / "baselines.json",
    )
    paths[0].write_text(json.dumps(imports), encoding="utf-8")
    seal0 = hashlib.sha256(paths[0].read_bytes()).hexdigest()
    frames["input_sha256"] = {"imports": seal0}
    paths[1].write_text(json.dumps(frames), encoding="utf-8")
    seal1 = hashlib.sha256(paths[1].read_bytes()).hexdigest()
    baselines["input_sha256"] = {"imports": seal0, "frames": seal1}
    paths[2].write_text(json.dumps(baselines), encoding="utf-8")
    seals = (seal0, seal1, hashlib.sha256(paths[2].read_bytes()).hexdigest())
    output = tmp_path / "output.json"
    kwargs = {"fresh_serial_no_resize": True, "cleared_output_buffers": True}
    with pytest.raises(ValueError):
        export_file(*paths, output, ("x", seal1, seals[2]), **kwargs)
    with pytest.raises(ValueError):
        export_file(*paths, output, seals[:2], **kwargs)
    with pytest.raises(ValueError):
        export_file(*paths, output, ("0" * 64, seal1, seals[2]), **kwargs)
    baselines["input_sha256"]["frames"] = "0" * 64
    paths[2].write_text(json.dumps(baselines), encoding="utf-8")
    changed = (seal0, seal1, hashlib.sha256(paths[2].read_bytes()).hexdigest())
    with pytest.raises(ValueError):
        export_file(*paths, output, changed, **kwargs)
    baselines["input_sha256"]["frames"] = seal1
    paths[2].write_text(json.dumps(baselines), encoding="utf-8")
    args = [
        "export",
        "--fresh-serial-no-resize",
        "--cleared-output-buffers",
        "--output",
        str(output),
    ]
    for name, path, seal in zip(
        ("imports", "frames", "baselines"), paths, seals, strict=True
    ):
        args += ["--" + name, str(path), "--" + name + "-sha256", seal]
    monkeypatch.setattr(sys, "argv", args)
    runpy.run_path(
        str(
            Path(__file__).resolve().parents[1]
            / "export_official_physics_distance_inputs.py"
        ),
        run_name="__main__",
    )
    assert "Distance reference exported" in capsys.readouterr().out
    assert (
        json.loads(output.read_text(encoding="utf-8"))["input_sha256"]["baselines"]
        == seals[2]
    )
    with pytest.raises(FileExistsError):
        export_file(*paths, output, seals, **kwargs)
