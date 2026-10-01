"""Reviewed global inputs; independent replay descriptors, no union-name lookup."""

import importlib
import runpy
import struct
import sys
from pathlib import Path
from types import SimpleNamespace as NS
from unittest.mock import patch

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))


def tool():
    return importlib.import_module("capture_character_lighting")


def test_real_source_selection_layout():
    module = tool()
    plan = module.prepare(Path(__file__).resolve().parents[2])
    assert len(plan) == 6
    for record in plan:
        assert [b["binding"] for b in record["blocks"]] == [14, 16]
        assert len(record["blocks"][0]["named"]) == 2
        assert len(record["blocks"][1]["named"]) == 4
        assert record["blocks"][0]["named"][1]["offset"] == 48


@pytest.mark.parametrize("fault", ["layout", "missing", "duplicate"])
def test_prepare_labels_fail_closed(fault):
    module = tool()
    a = {
        "name": "_0",
        "type": "float4",
        "size": 16,
        "offset": 0,
        "count": None,
        "major": None,
    }
    n = dict(a, name="_Tint")
    original = {"size": 16, "members": [a]}
    named = {"size": 16, "members": [dict(n)]}
    if fault == "layout":
        named["members"][0]["offset"] = 4
    elif fault == "missing":
        named["members"][0]["name"] = "Stripped"
    else:
        original["members"].append(dict(a))
        named["members"].append(dict(n))
    with (
        patch.object(
            module,
            "material_prepare",
            return_value=[
                {
                    "event": 875,
                    "program": 7,
                    "reference": "reference.hlsl",
                    "body": "_0",
                }
            ],
        ),
        patch.object(module, "FIELDS", {14: ("_Tint",)}),
        patch.object(module, "block", side_effect=[original, named]),
        pytest.raises(ValueError),
    ):
        module.prepare(Path("fixture"))


@pytest.mark.parametrize("fault", ["missing", "duplicate"])
def test_unique_block_fail_closed(fault):
    module = tool()
    block = {"space": 0, "binding": 14}
    with (
        patch.object(
            module,
            "parse_hlsl",
            return_value={
                "cbuffers": {} if fault == "missing" else {"a": block, "b": block}
            },
        ),
        pytest.raises(ValueError, match="Unique"),
    ):
        module.block(Path("fixture"), 14)


class Fixture:
    def __init__(self, fault=""):
        self.fault = fault
        self.rd = NS(ShaderStage=NS(Pixel="PS"))
        self.reflection = NS(
            rawBytes=b"shader",
            constantBlocks=[NS(fixedBindNumber=14, fixedBindSetOrSpace=0, byteSize=16)],
        )
        if fault == "block":
            self.reflection.constantBlocks = []
        if fault == "size":
            self.reflection.constantBlocks[0].byteSize = 8
        self.state = NS(
            GetShader=lambda stage: (
                "ResourceId::8" if fault == "program" else "ResourceId::7"
            ),
            GetShaderReflection=lambda stage: self.reflection,
            GetConstantBlock=lambda *args: NS(
                descriptor=NS(
                    resource="CB",
                    byteOffset=-1 if fault == "offset" else 64,
                    byteSize=8 if fault == "descriptor" else 16,
                )
            ),
        )

    def GetFrameInfo(self):
        return NS(frameNumber=0 if self.fault == "frame" else 6411)

    def SetFrameEvent(self, *args):
        assert args == (875, True)

    def GetPipelineState(self):
        return self.state

    def GetBufferData(self, resource, offset, size):
        assert (resource, offset, size) == ("CB", 64, 16)
        return b"short" if self.fault == "payload" else struct.pack("<4f", 1, 2, 3, 4)


def plan():
    module = tool()
    member = {
        "name": "_0",
        "type": "float4",
        "size": 16,
        "offset": 0,
        "count": None,
        "major": None,
    }
    named = dict(member, name="_Tint")
    return [
        {
            "event": 875,
            "program": 7,
            "shader_sha256": module.sha(b"shader"),
            "blocks": [
                {
                    "binding": 14,
                    "bytes": 16,
                    "actual": [member],
                    "named": [named],
                    "body": "_0",
                }
            ],
        }
    ]


@pytest.mark.parametrize(
    "fault",
    [
        "",
        "frame",
        "program",
        "hash",
        "block",
        "size",
        "offset",
        "descriptor",
        "payload",
    ],
)
def test_collect_raw_descriptor_and_guards(tmp_path, fault):
    module = tool()
    fixture = Fixture(fault)
    if fault == "hash":
        fixture.reflection.rawBytes = b"wrong"
    if fault:
        with pytest.raises(ValueError):
            module.collect(fixture.rd, fixture, tmp_path, plan())
    else:
        result = module.collect(fixture.rd, fixture, tmp_path, plan())
        record = result[0]["blocks"][0]
        assert record["uniforms"][0]["value"] == [1, 2, 3, 4]
        assert record["byte_offset"] == 64
        assert (tmp_path / record["file"]).read_bytes() == struct.pack(
            "<4f", 1, 2, 3, 4
        )


@pytest.mark.parametrize(
    "fault", ["", "collect", "controller_shutdown", "capture_shutdown", "prepare"]
)
def test_completion_only_after_both_shutdowns(tmp_path, monkeypatch, fault):
    module = tool()
    capture = tmp_path / "fixture.rdc"
    capture.write_bytes(b"offline")
    output = tmp_path / "export"
    monkeypatch.setenv("ENDFIELD_TOOLS_PATH", str(tmp_path / "Tools"))
    monkeypatch.setenv("ENDFIELD_CAPTURE_PATH", str(capture))
    monkeypatch.setenv("ENDFIELD_CAPTURE_OUTPUT", str(output))
    order = []

    def step(name):
        order.append(name)
        if fault == name:
            raise RuntimeError(name)
        return []

    with (
        patch.dict(sys.modules, renderdoc=NS()),
        patch.object(module, "prepare", side_effect=lambda *a: step("prepare")),
        patch.object(module, "collect", side_effect=lambda *a: step("collect")),
        patch.object(
            module,
            "open_controller",
            return_value=(
                NS(Shutdown=lambda: step("capture_shutdown")),
                NS(Shutdown=lambda: step("controller_shutdown")),
            ),
        ),
    ):
        if fault:
            with pytest.raises(RuntimeError):
                module.run()
            assert (output / "error.json").exists()
            assert not (output / "complete.json").exists()
        else:
            module.run()
            assert (output / "complete.json").exists()
    assert order == (
        ["prepare"]
        if fault == "prepare"
        else ["prepare", "collect", "controller_shutdown", "capture_shutdown"]
    )


def test_open_failure_never_emits_completion(tmp_path, monkeypatch):
    module = tool()
    capture = tmp_path / "fixture.rdc"
    capture.write_bytes(b"offline")
    monkeypatch.setenv("ENDFIELD_TOOLS_PATH", str(tmp_path / "Tools"))
    monkeypatch.setenv("ENDFIELD_CAPTURE_PATH", str(capture))
    monkeypatch.setenv("ENDFIELD_CAPTURE_OUTPUT", str(tmp_path / "export"))
    with (
        patch.dict(sys.modules, renderdoc=NS()),
        patch.object(module, "prepare", return_value=[]),
        patch.object(
            module, "open_controller", side_effect=RuntimeError("open failed")
        ),
        pytest.raises(RuntimeError),
    ):
        module.run()
    assert not (tmp_path / "export/complete.json").exists()
    assert (tmp_path / "export/error.json").exists()


def test_embedded_main_exits_on_failure(tmp_path, monkeypatch):
    capture = tmp_path / "fixture.rdc"
    capture.write_bytes(b"offline")
    monkeypatch.setenv("ENDFIELD_TOOLS_PATH", str(tmp_path / "Tools"))
    monkeypatch.setenv("ENDFIELD_CAPTURE_PATH", str(capture))
    monkeypatch.setenv("ENDFIELD_CAPTURE_OUTPUT", str(tmp_path / "export"))
    with pytest.raises(SystemExit):
        runpy.run_path(str(tool().__file__), run_name="__main__")
    assert (tmp_path / "export/error.json").exists()
    assert not (tmp_path / "export/complete.json").exists()
