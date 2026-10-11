"""Sealed reference import + fresh attributes + explicit zero-triangle route."""

import copy
import hashlib
import json
import runpy
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from export_official_physics_line_frames import build_document, export_file


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
                        "skin_bone_count": 1,
                        "snapshots": [{"rotation": (0, 0, 0, 1)}] * 2,
                        "vertices": {
                            "frames": {
                                "positions": ((1, 2, 3),),
                                "normals": ((0, 1, 0),),
                                "tangents": ((0, 0, 1),),
                            }
                        },
                    }
                ],
            }
        ],
    }
    buffers = {
        "schema_version": 1,
        "getter_scope": "synthetic",
        "preoptimization_attributes_and_flags_composed": True,
        "import_context": "explicit fresh empty ordinary BoneCloth import; unchanged unreduced skin order",
        "override_context": "explicit empty overrides for reconstructed reference only; not observed game state",
        "states": [
            {
                "name": "rest",
                "groups": [
                    {
                        "name": "fixture",
                        "component_identity": "fixture:7",
                        "skin_bone_count": 1,
                        "proxy_attributes": (2,),
                        "transform_flags": (13, 1),
                        "skin_transform_indices": (0,),
                    }
                ],
            }
        ],
    }
    config = {
        "groups": [
            {
                "boneClothName": "fixture",
                "boneClothData": {
                    "clothType": 1,
                    "connectionMode": 0,
                    "normalAlignmentSetting": {"alignmentMode": 0},
                    "customSkinningSetting": {"enable": 0},
                },
            }
        ]
    }
    return imported, buffers, config


def test_outputs_reference_frames_and_preserves_scope():
    values = fixture()
    before = copy.deepcopy(values)
    result = build_document(*values, zero_triangle_line=True)
    group = result["states"][0]["groups"][0]
    assert group["vertex_bindpose"]["positions"] == ((-1, -2, -3),)
    assert group["vertex_to_transform_rotations"] == ((0, 0, 0, 1),)
    assert group["proxy_attributes"] == (2,) and group["transform_flags"] == (13, 1)
    assert result["full_proxy_inputs_generated"] is False
    assert result["generic_fill_actual_writes_proved"] is False
    assert values == before


@pytest.mark.parametrize("premise", [False, None, 1])
def test_premise_required(premise):
    with pytest.raises(ValueError):
        build_document(*fixture(), zero_triangle_line=premise)


@pytest.mark.parametrize(
    "corruption",
    [
        "schema",
        "scope",
        "stage",
        "context",
        "overrides",
        "state",
        "group",
        "count",
        "snapshot",
        "indices",
        "flags",
        "config",
        "custom",
    ],
)
def test_bad_provenance_shape_or_route_refused(corruption):
    imported, buffers, config = fixture()
    if corruption == "schema":
        imported["schema_version"] = True
    elif corruption == "scope":
        buffers["getter_scope"] = "different"
    elif corruption == "stage":
        buffers["preoptimization_attributes_and_flags_composed"] = False
    elif corruption == "context":
        buffers["import_context"] = "unknown"
    elif corruption == "overrides":
        buffers["override_context"] = "unknown"
    elif corruption == "state":
        buffers["states"][0]["name"] = "other"
    elif corruption == "group":
        buffers["states"][0]["groups"][0]["component_identity"] = "other:8"
    elif corruption == "count":
        buffers["states"][0]["groups"][0]["skin_bone_count"] = 2
    elif corruption == "snapshot":
        imported["states"][0]["groups"][0]["snapshots"] = []
    elif corruption == "indices":
        buffers["states"][0]["groups"][0]["skin_transform_indices"] = (1,)
    elif corruption == "flags":
        buffers["states"][0]["groups"][0]["transform_flags"] = (13, 13)
    elif corruption == "config":
        config["groups"][0]["boneClothName"] = "other"
    else:
        config["groups"][0]["boneClothData"]["customSkinningSetting"]["enable"] = 1
    with pytest.raises(ValueError):
        build_document(imported, buffers, config, zero_triangle_line=True)


def test_export_seals_and_cli(tmp_path, monkeypatch, capsys):
    paths = (tmp_path / "0.json", tmp_path / "1.json", tmp_path / "2.json")
    output = tmp_path / "output.json"
    for path, data in zip(paths, fixture(), strict=True):
        path.write_text(json.dumps(data), encoding="utf-8")
    seals = tuple(hashlib.sha256(p.read_bytes()).hexdigest() for p in paths)
    with pytest.raises(ValueError):
        export_file(*paths, output, ("x", *seals[1:]), zero_triangle_line=True)
    with pytest.raises(ValueError):
        export_file(*paths, output, ("0" * 64, *seals[1:]), zero_triangle_line=True)
    args = ["export", "--zero-triangle-line", "--output", str(output)]
    for name, path, seal in zip(
        ("imports", "buffers", "config"), paths, seals, strict=True
    ):
        args += ["--" + name, str(path), "--" + name + "-sha256", seal]
    monkeypatch.setattr(sys, "argv", args)
    runpy.run_path(
        str(
            Path(__file__).resolve().parents[1]
            / "export_official_physics_line_frames.py"
        ),
        run_name="__main__",
    )
    assert "Line frame reference" in capsys.readouterr().out and output.exists()
    with pytest.raises(FileExistsError):
        export_file(*paths, output, seals, zero_triangle_line=True)
