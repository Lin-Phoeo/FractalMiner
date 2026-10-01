"""ShadowData offset labels from pinned actual programs, not old dump unions."""

import importlib
import runpy
import sys
from pathlib import Path
from types import SimpleNamespace as NS
from unittest.mock import patch

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))


def tool():
    return importlib.import_module("capture_character_shadows")


def test_actual_shadow_and_override_layout():
    plan = tool().prepare(Path(__file__).resolve().parents[2])
    assert len(plan) == 6
    for spec in plan:
        assert [b["binding"] for b in spec["blocks"]] == [15, 16]
        assert [
            (b["named"][0]["name"], b["named"][0]["offset"]) for b in spec["blocks"]
        ] == [("_DirectionalShadowParams", 544), ("_CharacterParams1", 1728)]
        assert "Load(int3" in spec["body"]


@pytest.mark.parametrize("fault", ["layout", "missing", "duplicate"])
def test_invalid_field_mapping_rejected(fault):
    module = tool()
    m = {
        "name": "_0",
        "type": "float4",
        "offset": 544,
        "size": 16,
        "count": None,
        "major": None,
    }
    a = {"size": 560, "members": [m]}
    n = {"size": 560, "members": [dict(m, name="_DirectionalShadowParams")]}
    if fault == "layout":
        n["members"][0]["offset"] = 16
    elif fault == "missing":
        n["members"][0]["name"] = "Stripped"
    else:
        a["members"].append(dict(m))
        n["members"].append(dict(n["members"][0]))
    with (
        patch.object(
            module.native,
            "material_prepare",
            return_value=[
                {"event": 875, "program": 7, "reference": "ref", "body": "_0"}
            ],
        ),
        patch.object(module.native, "block", side_effect=[a, n]),
        pytest.raises(ValueError),
    ):
        module.prepare(Path("fixture"))


def test_reuses_fail_closed_replay_lifecycle():
    module = tool()
    with patch.object(module.native, "run", return_value="result") as run:
        assert module.run() == "result"
    assert run.call_args.args[0] is module.prepare
    assert run.call_args.args[1] == "endfield-shadow-selection-v1"
    assert run.call_args.args[3] is module.collect


@pytest.mark.parametrize(
    "fault", ["", "missing", "duplicate", "format", "swizzle", "bytes", "changed"]
)
def test_native_mask_storage_view_and_identity(tmp_path, fault):
    module = tool()
    fmt = NS(Name=lambda: "R16_UNORM" if fault == "format" else "R8G8_UNORM")
    t = NS(
        resourceId="mask", format=fmt, width=2, height=2, depth=1, arraysize=1, mips=1
    )
    d = NS(
        resource="mask",
        view="view",
        format=fmt,
        textureType="TextureType.Texture2D",
        firstMip=0,
        numMips=1,
        firstSlice=0,
        numSlices=1,
        minLODClamp=0,
        swizzle=NS(
            **{
                c: "TextureSwizzle." + c.title()
                for c in ("red", "green", "blue", "alpha")
            }
        ),
    )
    if fault == "swizzle":
        d.swizzle.red = "TextureSwizzle.Green"
    used = NS(descriptor=d)
    state = NS(
        GetShaderReflection=lambda *a: NS(readOnlyResources=[]),
        GetReadOnlyResources=lambda *a: (
            []
            if fault == "missing"
            else [used, used]
            if fault == "duplicate"
            else [used]
        ),
    )
    event = [0]
    controller = NS(
        GetTextures=lambda: [t],
        SetFrameEvent=lambda e, f: event.__setitem__(0, e),
        GetPipelineState=lambda: state,
        GetTextureData=lambda *a: (
            bytes(7)
            if fault == "bytes"
            else bytes([event[0] if fault == "changed" else 0] * 8)
        ),
    )
    rd = NS(ShaderStage=NS(Pixel="PS"), Subresource=lambda *a: a)
    with (
        patch.object(
            module.native, "collect", return_value=[{"event": 1}, {"event": 2}]
        ),
        patch.object(module, "binding", return_value={"set": 0, "binding": 22}),
    ):
        if fault:
            with pytest.raises(ValueError):
                module.collect(rd, controller, tmp_path, [])
        else:
            result = module.collect(rd, controller, tmp_path, [])
            assert result[0]["screen_mask"]["bytes"] == 8
            assert (tmp_path / "screen-mask.raw").read_bytes() == bytes(8)


@pytest.mark.parametrize("fail", [False, True])
def test_custom_collector_keeps_shutdown_completion_contract(
    tmp_path, monkeypatch, fail
):
    module = tool()
    capture = tmp_path / "fixture.rdc"
    capture.write_bytes(b"offline")
    monkeypatch.setenv("ENDFIELD_TOOLS_PATH", str(tmp_path / "Tools"))
    monkeypatch.setenv("ENDFIELD_CAPTURE_PATH", str(capture))
    monkeypatch.setenv("ENDFIELD_CAPTURE_OUTPUT", str(tmp_path / "export"))
    order = []

    def collect(*args):
        order.append("collect")
        if fail:
            raise ValueError("failed collector")
        return []

    cap = NS(Shutdown=lambda: order.append("capture_shutdown"))
    controller = NS(Shutdown=lambda: order.append("controller_shutdown"))
    with (
        patch.dict(sys.modules, renderdoc=NS()),
        patch.object(module, "prepare", return_value=[]),
        patch.object(module, "collect", side_effect=collect),
        patch.object(module.native, "open_controller", return_value=(cap, controller)),
    ):
        if fail:
            with pytest.raises(ValueError):
                module.run()
        else:
            module.run()
    assert order == ["collect", "controller_shutdown", "capture_shutdown"]
    assert (tmp_path / "export/complete.json").exists() is not fail


def test_embedded_main_exits_without_false_completion(tmp_path, monkeypatch):
    capture = tmp_path / "fixture.rdc"
    capture.write_bytes(b"offline")
    monkeypatch.setenv("ENDFIELD_TOOLS_PATH", str(tmp_path / "Tools"))
    monkeypatch.setenv("ENDFIELD_CAPTURE_PATH", str(capture))
    monkeypatch.setenv("ENDFIELD_CAPTURE_OUTPUT", str(tmp_path / "export"))
    with pytest.raises(SystemExit):
        runpy.run_path(str(tool().__file__), run_name="__main__")
    assert (tmp_path / "export/error.json").exists()
    assert not (tmp_path / "export/complete.json").exists()
