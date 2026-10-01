"""Raw per-material bytes and explicit offset/type mapping, never union names."""

import importlib
import json
import runpy
import struct
import sys
from pathlib import Path
from types import SimpleNamespace as NS
from unittest.mock import patch

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))


def tool():
    return importlib.import_module("capture_material_uniforms")


def member(name, offset, kind="float", size=4):
    return {
        "name": name,
        "offset": offset,
        "type": kind,
        "size": size,
        "count": None,
        "major": None,
    }


def test_decode_matches_offset_and_ignores_stale_union_names():
    source = [member("_7_m0", 0), member("_7_m1", 16, "float4", 16)]
    names = [member("_Scale", 0), member("_Tint", 16, "float4", 16)]
    raw = struct.pack("<8f", 0.125, 0, 0, 0, 1, 2, 3, 0.7)
    result = tool().decode(raw, source, names, "float v=_7_m0; float3 c=_7_m1.xyz;")
    assert [(r["name"], r["offset"], r["active"]) for r in result] == [
        ("_Scale", 0, True),
        ("_Tint", 16, True),
    ]
    assert result[1]["value"] == pytest.approx([1, 2, 3, 0.7])


@pytest.mark.parametrize("fault", ["offset", "type", "count", "major", "size"])
def test_layout_mismatch_rejected(fault):
    source = [member("_0", 0)]
    named = [member("_Scale", 0)]
    named[0][fault] = {
        "offset": 4,
        "type": "uint",
        "count": 2,
        "major": "row_major",
        "size": 8,
    }[fault]
    with pytest.raises(ValueError, match="layout"):
        tool().decode(bytes(16), source, named, "")


@pytest.mark.parametrize(
    "raw", [bytes(3), struct.pack("<f", float("nan")), struct.pack("<f", float("inf"))]
)
def test_truncated_nonfinite_rejected(raw):
    with pytest.raises(ValueError):
        tool().decode(raw, [member("_0", 0)], [member("_Scale", 0)], "_0")


def test_active_token_not_substring_and_stripped_kept_unapproved():
    source = [member("_8_m1", 0), member("_8_m10", 4)]
    named = [member("_Scale", 0), member("UnityPerMaterial_Stripped_4", 4)]
    result = tool().decode(bytes(16), source, named, "_8_m10")
    assert [r["active"] for r in result] == [False, True]
    assert result[1]["named"] is False


class Fixture:
    def __init__(self, fail=""):
        self.fail = fail
        self.rd = NS(ShaderStage=NS(Pixel="PS"))
        self.events = []
        self.block = NS(fixedBindNumber=0, fixedBindSetOrSpace=1, byteSize=16)
        self.reflection = NS(rawBytes=b"shader", constantBlocks=[self.block])
        self.state = NS(
            GetShader=lambda stage: "ResourceId::7",
            GetShaderReflection=lambda stage: self.reflection,
            GetConstantBlock=lambda stage, index, element: NS(
                descriptor=NS(resource="CB", byteOffset=64, byteSize=16)
            ),
        )

    def GetFrameInfo(self):
        return NS(frameNumber=0 if self.fail == "frame" else 6411)

    def SetFrameEvent(self, event, force):
        self.events.append((event, force))

    def GetPipelineState(self):
        return self.state

    def GetBufferData(self, resource, offset, size):
        assert (resource, offset, size) == ("CB", 64, 16)
        return bytes(15 if self.fail == "truncate" else 16)


def plan():
    return [
        {
            "event": 776,
            "program": 7,
            "shader_sha256": tool().sha(b"shader"),
            "bytes": 16,
            "actual": [member("_0", 0)],
            "named": [member("_Scale", 0)],
            "body": "_0",
            "material": "fixture",
        }
    ]


def test_collect_raw_bytes_and_descriptor_identity(tmp_path):
    f = Fixture()
    result = tool().collect(f.rd, f, tmp_path, plan())
    assert (tmp_path / "776-upm.raw").read_bytes() == bytes(16)
    assert result[0]["byte_offset"] == 64
    assert result[0]["uniforms"][0]["value"] == [0]
    assert f.events == [(776, True)]


@pytest.mark.parametrize(
    "fault", ["frame", "shader", "block", "duplicate", "range", "truncate"]
)
def test_collect_fail_closed(tmp_path, fault):
    f = Fixture(fault)
    if fault == "shader":
        f.reflection.rawBytes = b"unexpected"
    elif fault == "block":
        f.block.fixedBindSetOrSpace = 0
    elif fault == "duplicate":
        f.reflection.constantBlocks.append(f.block)
    elif fault == "range":
        f.block.byteSize = 32
    with pytest.raises(ValueError):
        tool().collect(f.rd, f, tmp_path, plan())
    assert not (tmp_path / "complete.json").exists()


def test_shader_hair_color_flags_match_official_schema():
    root = Path(__file__).resolve().parents[2]
    current = (
        root / "Assets/EndfieldShaderPack/EndfieldCharacterLit.shader"
    ).read_text("utf-8-sig")
    assert "[HDR] _AnisotropyColor2" not in current


@pytest.mark.parametrize(
    "kind,count,major",
    [("uint", None, None), ("float", 2, None), ("float", None, "column_major")],
)
def test_unreviewed_storage_rejected(kind, count, major):
    m = member("_0", 0, kind)
    m.update(count=count, major=major)
    with pytest.raises(ValueError, match="type"):
        tool().decode(bytes(16), [m], [m], "_0")


def test_prepare_actual_six_reviewed_sources():
    result = tool().prepare(Path(__file__).resolve().parents[2])
    assert [(r["event"], r["program"], r["bytes"]) for r in result] == [
        (776, 22259, 400),
        (786, 22250, 368),
        (835, 22255, 336),
        (850, 37669, 336),
        (860, 37671, 384),
        (875, 22257, 448),
    ]
    assert result[-1]["reference"].endswith("Fragment_b126.hlsl")


def prepared_fixture(tmp_path, monkeypatch):
    module = tool()
    actual = b"cbuffer _5_6 : register(b0, space1)\n{\n    float _6_m0 : packoffset(c0);\n};\nfloat x=_6_m0;"
    named = b"cbuffer type_UnityPerMaterial : register(b0, space1)\n{\n    float _Scale : packoffset(c0);\n};\n"
    folder = tmp_path / "Validation/draw-program-audit-20260930-01"
    folder.mkdir(parents=True)
    (folder / "actual.hlsl").write_bytes(actual)
    reference = (
        tmp_path
        / "_dump_1.5.3/AllShader_1.5.3/Assets/packages/com.hg.render-pipelines/runtime/shaders/materials/characternpr/family/Sub0_Pass0_Fragment_b1.hlsl"
    )
    reference.parent.mkdir(parents=True)
    reference.write_bytes(named)
    prov = json.dumps(
        {
            "programs": [
                {
                    "event": 776,
                    "stage": "fragment",
                    "shader": "ResourceId::7",
                    "hlsl": "Validation/draw-program-audit-20260930-01/actual.hlsl",
                    "hlsl_sha256": module.sha(actual),
                    "spv_sha256": module.sha(b"shader"),
                }
            ]
        }
    ).encode()
    (folder / "export-provenance.json").write_bytes(prov)
    monkeypatch.setattr(module, "PROVENANCE_SHA256", module.sha(prov))
    monkeypatch.setattr(
        module, "SOURCES", ((776, 7, "iris", "family", 1, module.sha(named)),)
    )
    return module, folder, reference


@pytest.mark.parametrize(
    "fault", ["", "provenance", "program", "source", "reference", "layout", "block"]
)
def test_prepare_pin_layout_and_body_tokens(tmp_path, monkeypatch, fault):
    module, folder, reference = prepared_fixture(tmp_path, monkeypatch)
    if fault == "provenance":
        monkeypatch.setattr(module, "PROVENANCE_SHA256", "wrong")
    elif fault == "program":
        monkeypatch.setattr(
            module,
            "SOURCES",
            ((777, 7, "iris", "family", 1, module.sha(reference.read_bytes())),),
        )
    elif fault == "source":
        (folder / "actual.hlsl").write_bytes(b"different")
    elif fault == "reference":
        reference.write_bytes(b"different")
    elif fault in ("layout", "block"):
        original = module.parse_hlsl

        def altered(path):
            value = original(path)
            if path.endswith("Fragment_b1.hlsl"):
                block = value["cbuffers"]["UnityPerMaterial"]
                if fault == "layout":
                    block["members"][0]["offset"] = 4
                else:
                    block["space"] = 0
            return value

        monkeypatch.setattr(module, "parse_hlsl", altered)
    if fault:
        with pytest.raises(ValueError):
            module.prepare(tmp_path)
    else:
        result = module.prepare(tmp_path)
        assert "packoffset" not in result[0]["body"]
        assert result[0]["actual"][0]["name"] == "_6_m0"


@pytest.mark.parametrize(
    "fault", ["", "collect", "shutdown", "capture_shutdown", "prepare"]
)
def test_completion_published_only_after_shutdown(tmp_path, monkeypatch, fault):
    module = tool()
    capture = tmp_path / "fixture.rdc"
    capture.write_bytes(b"offline fixture")
    output = tmp_path / "export"
    monkeypatch.setenv("ENDFIELD_TOOLS_PATH", str(tmp_path / "Tools"))
    monkeypatch.setenv("ENDFIELD_CAPTURE_PATH", str(capture))
    monkeypatch.setenv("ENDFIELD_CAPTURE_OUTPUT", str(output))
    order = []

    def shutdown(name):
        order.append(name)
        if fault == name:
            raise RuntimeError("Shutdown failed")

    cap, controller = (
        NS(Shutdown=lambda: shutdown("capture_shutdown")),
        NS(Shutdown=lambda: shutdown("shutdown")),
    )

    def collect(*args):
        order.append("collect")
        if fault == "collect":
            raise ValueError("collect failed")
        return []

    with (
        patch.dict(sys.modules, renderdoc=NS()),
        patch.object(module, "open_controller", return_value=(cap, controller)),
        patch.object(module, "collect", side_effect=collect),
        patch.object(
            module,
            "prepare",
            side_effect=ValueError("prepare failed")
            if fault == "prepare"
            else lambda project: [],
        ),
    ):
        if fault:
            with pytest.raises((ValueError, RuntimeError)):
                module.run()
            assert (output / "error.json").exists()
            assert not (output / "complete.json").exists()
        else:
            module.run()
            assert (output / "complete.json").exists()
        assert order == (
            [] if fault == "prepare" else ["collect", "shutdown", "capture_shutdown"]
        )


def test_descriptor_range_rejected(tmp_path):
    f = Fixture()
    f.state.GetConstantBlock = lambda *args: NS(
        descriptor=NS(resource="CB", byteOffset=0, byteSize=15)
    )
    with pytest.raises(ValueError, match="descriptor"):
        tool().collect(f.rd, f, tmp_path, plan())


def test_renderdoc_main_exits_after_run(tmp_path, monkeypatch):
    capture = tmp_path / "fixture.rdc"
    capture.write_bytes(b"offline fixture")
    monkeypatch.setenv("ENDFIELD_TOOLS_PATH", str(tmp_path / "Tools"))
    monkeypatch.setenv("ENDFIELD_CAPTURE_PATH", str(capture))
    monkeypatch.setenv("ENDFIELD_CAPTURE_OUTPUT", str(tmp_path / "output"))
    # A source failure still must execute sys.exit in the embedded GUI entry;
    # the main exception leaves error.json, never a stale completion marker.
    with pytest.raises(SystemExit) as stopped:
        runpy.run_path(str(tool().__file__), run_name="__main__")
    assert stopped.value.code is None
    assert (tmp_path / "output/error.json").exists()
    assert not (tmp_path / "output/complete.json").exists()
