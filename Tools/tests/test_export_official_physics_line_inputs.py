"""Sealed Line selection input production, not completed proxy attributes."""

import copy
import hashlib
import json
import runpy
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from export_official_physics_line_inputs import build_document, export_file
from test_export_official_physics_getter_inputs import BINDINGS_SHA, fixture


def inputs():
    bindings, capture = fixture()
    config = {
        "groups": [
            {
                "boneClothName": "fixture",
                "boneClothData": {
                    "clothType": 1,
                    "connectionMode": 0,
                    "reductionSetting": {"simpleDistance": 0.0, "shapeDistance": 0.0},
                },
                "selectionData": {
                    "positions": [{"x": 3, "y": 0, "z": 0}, {"x": 8, "y": 0, "z": 0}],
                    "attributes": [1, 2],
                    "userEdit": False,
                    "maxConnectionDistance": 0.1,
                },
            }
        ]
    }
    return bindings, config, capture


def test_valid_saved_branch_joins_world_import_without_fabricating_old_bytes():
    bindings, config, capture = inputs()
    before = copy.deepcopy((bindings, config, capture))
    document = build_document(
        bindings, config, capture, BINDINGS_SHA, resolved_overrides={"fixture": ()}
    )
    group = document["states"][0]["groups"][0]
    assert group["matched_selection_bytes"] == (1,)
    assert len(group["selection"]["positions"]) == 2
    assert document["full_proxy_attributes_generated"] is False
    assert document["runtime_overrides_observed"] is False
    assert document["getter_scope"] == capture["scope"]
    assert (bindings, config, capture) == before


@pytest.mark.parametrize("raw,expected", [(0, False), (1, True)])
def test_sceneprobe_serialized_bool_zero_one_decoded_explicitly(raw, expected):
    bindings, config, capture = inputs()
    config["groups"][0]["selectionData"]["userEdit"] = raw
    document = build_document(
        bindings, config, capture, BINDINGS_SHA, resolved_overrides={"fixture": ()}
    )
    assert document["states"][0]["groups"][0]["selection"]["user_edit"] is expected


@pytest.mark.parametrize("raw", [2, -1, "0", None, 0.0])
def test_non_boolean_serialized_useredit_refused(raw):
    bindings, config, capture = inputs()
    config["groups"][0]["selectionData"]["userEdit"] = raw
    with pytest.raises(ValueError):
        build_document(
            bindings, config, capture, BINDINGS_SHA, resolved_overrides={"fixture": ()}
        )


def test_sceneprobe_vertex_attribute_value_wrapper_is_decoded():
    bindings, config, capture = inputs()
    config["groups"][0]["selectionData"]["attributes"] = [{"Value": 1}, {"Value": 2}]
    output = build_document(
        bindings, config, capture, BINDINGS_SHA, resolved_overrides={"fixture": ()}
    )
    assert output["states"][0]["groups"][0]["matched_selection_bytes"] == (1,)


@pytest.mark.parametrize(
    "raw", [{"value": 1}, {"Value": 1, "extra": 2}, {"Value": True}, {"Value": 256}]
)
def test_attribute_wrapper_rejects_unknown_shape_or_nonbyte(raw):
    bindings, config, capture = inputs()
    config["groups"][0]["selectionData"]["attributes"][0] = raw
    with pytest.raises(ValueError):
        build_document(
            bindings, config, capture, BINDINGS_SHA, resolved_overrides={"fixture": ()}
        )


@pytest.mark.parametrize(
    "corruption",
    [
        "group_count",
        "group_name",
        "mode",
        "spring",
        "reduction",
        "invalid_saved",
        "missing_override",
        "bool_mode",
        "bool_type",
    ],
)
def test_wrong_route_or_missing_explicit_context_refused(corruption):
    bindings, config, capture = inputs()
    group = config["groups"][0]
    overrides = {"fixture": ()}
    if corruption == "group_count":
        config["groups"] = []
    elif corruption == "group_name":
        group["boneClothName"] = "wrong"
    elif corruption == "mode":
        group["boneClothData"]["connectionMode"] = 1
    elif corruption == "spring":
        group["boneClothData"]["clothType"] = 2
    elif corruption == "reduction":
        group["boneClothData"]["reductionSetting"]["simpleDistance"] = 0.1
    elif corruption == "invalid_saved":
        group["selectionData"]["positions"] = []
    elif corruption == "missing_override":
        overrides = {}
    elif corruption == "bool_mode":
        group["boneClothData"]["connectionMode"] = False
    else:
        group["boneClothData"]["clothType"] = True
    with pytest.raises(ValueError):
        build_document(
            bindings, config, capture, BINDINGS_SHA, resolved_overrides=overrides
        )


def test_export_requires_all_source_seals_and_explicit_no_override_premise(tmp_path):
    bindings, config, capture = inputs()
    b = tmp_path / "bindings.json"
    c = tmp_path / "config.json"
    g = tmp_path / "getters.json"
    o = tmp_path / "result.json"
    b.write_text(json.dumps(bindings), encoding="utf-8")
    bs = hashlib.sha256(b.read_bytes()).hexdigest()
    capture["bindings_sha256"] = bs
    c.write_text(json.dumps(config), encoding="utf-8")
    g.write_text(json.dumps(capture), encoding="utf-8")
    seals = [
        bs,
        hashlib.sha256(c.read_bytes()).hexdigest(),
        hashlib.sha256(g.read_bytes()).hexdigest(),
    ]
    with pytest.raises(ValueError):
        export_file(b, c, g, o, *seals, no_runtime_overrides=False)
    for index in range(3):
        bad = list(seals)
        bad[index] = "0" * 64
        with pytest.raises(ValueError):
            export_file(b, c, g, o, *bad, no_runtime_overrides=True)
    with pytest.raises(ValueError):
        export_file(b, c, g, o, "x", *seals[1:], no_runtime_overrides=True)
    export_file(b, c, g, o, *seals, no_runtime_overrides=True)
    document = json.loads(o.read_text(encoding="utf-8"))
    assert document["source_sha256"]["bindings"] == bs
    assert (
        document["override_context"]
        == "explicit empty overrides for reconstructed reference only; not observed game state"
    )
    with pytest.raises(FileExistsError):
        export_file(b, c, g, o, *seals, no_runtime_overrides=True)


def test_cli(tmp_path, monkeypatch, capsys):
    bindings, config, capture = inputs()
    b, c, g, o = (tmp_path / name for name in ("b.json", "c.json", "g.json", "o.json"))
    b.write_text(json.dumps(bindings), encoding="utf-8")
    bs = hashlib.sha256(b.read_bytes()).hexdigest()
    capture["bindings_sha256"] = bs
    c.write_text(json.dumps(config), encoding="utf-8")
    g.write_text(json.dumps(capture), encoding="utf-8")
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "export",
            "--bindings",
            str(b),
            "--config",
            str(c),
            "--getter-capture",
            str(g),
            "--output",
            str(o),
            "--bindings-sha256",
            bs,
            "--config-sha256",
            hashlib.sha256(c.read_bytes()).hexdigest(),
            "--getter-sha256",
            hashlib.sha256(g.read_bytes()).hexdigest(),
            "--no-runtime-overrides",
        ],
    )
    runpy.run_path(
        str(
            Path(__file__).resolve().parents[1]
            / "export_official_physics_line_inputs.py"
        ),
        run_name="__main__",
    )
    assert o.exists() and "Reference Line selection" in capsys.readouterr().out
