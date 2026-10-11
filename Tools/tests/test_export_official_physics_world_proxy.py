"""Sealed actual matrix joins, not snapshot TRS or official runtime publication."""

import copy
import hashlib
import json
import runpy
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from export_official_physics_world_proxy import build_document, export_file

I = ((1, 0, 0, 0), (0, 1, 0, 0), (0, 0, 1, 0), (10, 0, 0, 1))
IDENTITY = I[:3] + ((0, 0, 0, 1),)
SEAL = "a" * 64


def fixture():
    imported = {
        "schema_version": 1,
        "getter_scope": "synthetic",
        "full_proxy_inputs_generated": False,
        "source_sha256": {"bindings": "b" * 64, "getter_capture": SEAL},
        "states": [
            {
                "name": "rest",
                "groups": [
                    {
                        "name": "fixture",
                        "component_identity": "fixture:7",
                        "skin_bone_count": 1,
                        "runtime_instance_ids": (1, 2),
                        "runtime_parent_ids": (0, 0),
                        "vertices": {
                            "frames": {
                                "positions": ((1, 2, 3),),
                                "normals": ((0, 1, 0),),
                                "tangents": ((0, 0, 1),),
                            },
                            "bone_weights": [
                                {"weights": (1, 0, 0, 0), "bone_indices": (0, 0, 0, 0)}
                            ],
                            "skin_bone_bindposes": (IDENTITY,),
                        },
                    }
                ],
            }
        ],
    }
    getters = {
        "schema_version": 1,
        "scope": "synthetic",
        "bindings_sha256": "b" * 64,
        "states": [
            {
                "name": "rest",
                "samples": [
                    {
                        "identity": "fixture:1",
                        "instance_id": 1,
                        "parent_instance_id": 0,
                        "position": (999, 999, 999),
                        "rotation": (0, 0, 0, 3),
                        "local_to_world": dict(
                            zip(("c0", "c1", "c2", "c3"), I, strict=True)
                        ),
                    },
                    {
                        "identity": "fixture:2",
                        "instance_id": 2,
                        "parent_instance_id": 0,
                        "local_to_world": dict(
                            zip(("c0", "c1", "c2", "c3"), IDENTITY, strict=True)
                        ),
                    },
                ],
            }
        ],
    }
    return imported, getters


def build(imported=None, getters=None, **kwargs):
    source, capture = fixture()
    return build_document(
        imported or source,
        getters or capture,
        getter_capture_sha256=kwargs.pop("getter_capture_sha256", SEAL),
        experiment_layout=kwargs.pop("experiment_layout", True),
        **kwargs
    )


def test_matrix_world_output_reset14_and_limits():
    source, capture = fixture()
    before = copy.deepcopy((source, capture))
    result = build(source, capture)
    group = result["states"][0]["groups"][0]
    assert group["world"]["positions"] == ((11, 2, 3),)
    assert group["world"]["rotations"] == ((0, 0, 0, 1),)
    assert group["reset"]["fully_reset"] is True
    assert len(group["reset"]["results"][0]["writes"]) == 14
    assert group["reset"]["states"][0]["next_position"] == (11, 2, 3)
    assert group["reset"]["states"][0]["velocity"] == (0, 0, 0)
    assert group["matrix_identities"] == ("fixture:1", "fixture:2")
    assert result["native_arrays_published"] is False
    assert result["official_solver_integrated"] is False
    assert result["changing_animation_verified"] is False
    assert (source, capture) == before


@pytest.mark.parametrize("premise", [False, 1, None])
def test_explicit_experiment_not_native_layout(premise):
    with pytest.raises(ValueError):
        build(experiment_layout=premise)


def test_missing_document_structure_has_one_value_error_contract():
    source, capture = fixture()
    del source["states"][0]["groups"][0]["vertices"]
    with pytest.raises(ValueError, match="incomplete"):
        build(source, capture)


@pytest.mark.parametrize(
    "corruption",
    [
        "schema",
        "binding",
        "capture",
        "scope",
        "full",
        "states",
        "duplicate_state",
        "duplicate_id",
        "duplicate_identity",
        "bad_id",
        "empty_identity",
        "missing_id",
        "parent",
        "runtime_ids",
        "duplicate_group",
        "duplicate_component",
        "count",
        "frames",
        "bindposes",
        "weights",
        "columns",
        "empty_groups",
    ],
)
def test_inconsistent_provenance_identity_or_data_fails(corruption):
    source, capture = fixture()
    group = source["states"][0]["groups"][0]
    samples = capture["states"][0]["samples"]
    if corruption == "schema":
        source["schema_version"] = True
    elif corruption == "binding":
        capture["bindings_sha256"] = "c" * 64
    elif corruption == "capture":
        source["source_sha256"]["getter_capture"] = "c" * 64
    elif corruption == "scope":
        capture["scope"] = "other"
    elif corruption == "full":
        source["full_proxy_inputs_generated"] = True
    elif corruption == "states":
        capture["states"][0]["name"] = "other"
    elif corruption == "duplicate_state":
        source["states"] *= 2
        capture["states"] *= 2
    elif corruption == "duplicate_id":
        samples[1]["instance_id"] = 1
    elif corruption == "duplicate_identity":
        samples[1]["identity"] = "fixture:1"
    elif corruption == "bad_id":
        samples[0]["instance_id"] = True
    elif corruption == "empty_identity":
        samples[0]["identity"] = ""
    elif corruption == "missing_id":
        samples.pop(0)
    elif corruption == "parent":
        samples[0]["parent_instance_id"] = 9
    elif corruption == "runtime_ids":
        group["runtime_instance_ids"] = (1, 1)
    elif corruption in ("duplicate_group", "duplicate_component"):
        extra = copy.deepcopy(group)
        if corruption == "duplicate_component":
            extra["name"] = "different"
        source["states"][0]["groups"].append(extra)
    elif corruption == "count":
        group["skin_bone_count"] = 0
    elif corruption == "frames":
        group["vertices"]["frames"]["normals"] = ()
    elif corruption == "bindposes":
        group["vertices"]["skin_bone_bindposes"] = ()
    elif corruption == "weights":
        group["vertices"]["bone_weights"] = ()
    elif corruption == "columns":
        del samples[0]["local_to_world"]["c3"]
    else:
        source["states"][0]["groups"] = []
    with pytest.raises(ValueError):
        build(source, capture)


def test_export_seals_and_cli_never_overwrites(tmp_path, monkeypatch, capsys):
    source, capture = fixture()
    imported, getters, output = (
        tmp_path / n for n in ("imports.json", "getters.json", "out.json")
    )
    getters.write_text(json.dumps(capture), encoding="utf-8")
    getter_seal = hashlib.sha256(getters.read_bytes()).hexdigest()
    source["source_sha256"]["getter_capture"] = getter_seal
    imported.write_text(json.dumps(source), encoding="utf-8")
    seals = (hashlib.sha256(imported.read_bytes()).hexdigest(), getter_seal)
    for bad in [("x", getter_seal), ("0" * 64, getter_seal), ()]:
        with pytest.raises(ValueError):
            export_file(imported, getters, output, bad, experiment_layout=True)
    args = ["export", "--experiment-layout", "--output", str(output)]
    for name, path, seal in zip(
        ("imports", "getters"), (imported, getters), seals, strict=True
    ):
        args += ["--" + name, str(path), "--" + name + "-sha256", seal]
    monkeypatch.setattr(sys, "argv", args)
    runpy.run_path(
        str(
            Path(__file__).resolve().parents[1]
            / "export_official_physics_world_proxy.py"
        ),
        run_name="__main__",
    )
    saved = json.loads(output.read_text(encoding="utf-8"))
    assert saved["input_sha256"] == dict(
        zip(("imports", "getters"), seals, strict=True)
    )
    assert saved["states"][0]["groups"][0]["world"]["positions"] == [[11, 2, 3]]
    assert "World proxy reference exported" in capsys.readouterr().out
    with pytest.raises(FileExistsError):
        export_file(imported, getters, output, seals, experiment_layout=True)
