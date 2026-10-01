"""Actual depth-writer provenance; never a screenshot-fitting oracle."""

import importlib
import json
import runpy
import sys
from pathlib import Path
from types import SimpleNamespace as NS
from unittest.mock import patch

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))


def tool():
    return importlib.import_module("capture_shadow_atlas_writers")


def test_prepare_pins_all_23_writers_and_archive_programs():
    plan = tool().prepare(Path(__file__).resolve().parents[2])
    assert len(plan) == 23
    assert [p["event"] for p in plan][0::22] == [272, 376]
    assert sum(p["indices"] for p in plan) == 303756
    assert plan[11]["stages"]["Vertex"]["program"] == 9064
    assert plan[12]["stages"]["Vertex"]["program"] == 9043
    assert plan[-1]["stages"]["Pixel"]["program"] == 9050


def test_prepare_rejects_program_archive_drift():
    with (
        patch.object(tool(), "sha", return_value="drift"),
        pytest.raises(ValueError, match="archive"),
    ):
        tool().prepare(Path(__file__).resolve().parents[2])


def sd(name, basic, value=None, children=()):
    pod_field = {
        "Float": "d",
        "Resource": "id",
        "Boolean": "b",
        "SignedInteger": "i",
        "Character": "c",
    }.get(basic, "u")
    return NS(
        name=name,
        type=NS(basetype="SDBasic." + basic, name=basic, byteSize=4, flags=0),
        data=NS(basic=NS(**{pod_field: value}), str=value),
        NumChildren=lambda: len(children),
        GetChild=lambda i: children[i],
    )


@pytest.mark.parametrize(
    "basic,value",
    [
        ("Float", 0.0),
        ("UnsignedInteger", 12),
        ("Enum", 1),
        ("GPUAddress", 123),
        ("SignedInteger", -5),
        ("Resource", "ResourceId::32538"),
        ("Boolean", True),
        ("Character", "x"),
        ("String", "zero"),
        ("Null", None),
    ],
)
def test_sd_preserves_only_correct_union_member(basic, value):
    assert tool().sd_record(sd("depth", basic, value))["value"] == value


@pytest.mark.parametrize("basic", ["Struct", "Array", "Chunk"])
def test_sd_keeps_all_children_without_truncation(basic):
    result = tool().sd_record(sd("clear", basic, children=[sd("depth", "Float", 0)]))
    assert result["children"][0]["value"] == 0


@pytest.mark.parametrize("fault", ["depth", "nodes", "type"])
def test_sd_fails_closed_on_unknown_or_oversized_tree(fault):
    with pytest.raises(ValueError):
        tool().sd_record(
            sd("x", "Buffer" if fault == "type" else "Float", 0),
            depth=17 if fault == "depth" else 0,
            budget=[0] if fault == "nodes" else None,
        )


@pytest.mark.parametrize("fault", ["", "events", "chunk", "name"])
def test_clear_chunk_uses_exact_event_chunk_association(fault):
    action = NS(
        eventId=260,
        events=[NS(eventId=259, chunkIndex=0), NS(eventId=260, chunkIndex=1)],
    )
    if fault == "events":
        action.events = []
    if fault == "chunk":
        action.events[-1].chunkIndex = 7
    chunk = sd("bad" if fault == "name" else "vkCmdBeginRenderPass", "Chunk")
    structured = NS(chunks=[sd("unrelated", "Chunk"), chunk])
    if fault:
        with pytest.raises(ValueError):
            tool().clear_record(action, structured)
    else:
        result = tool().clear_record(action, structured)
        assert result["chunk_index"] == 1
        assert result["chunk"]["name"] == "vkCmdBeginRenderPass"


@pytest.mark.parametrize(
    "fault",
    [
        "",
        "frame",
        "api",
        "usage",
        "pipeline",
        "indices",
        "depth",
        "storage",
        "sampler_count",
        "sampler_type",
    ],
)
def test_collect_writers_checks_actual_program_state_and_raw_cb(tmp_path, fault):
    from test_capture_shadow_producers import descriptor, fixture_vk

    m = tool()
    pin = {"program": 1, "sha256": m.sha(b"shader")}
    spec = {
        "event": 272,
        "pipeline": 7,
        "indices": 3,
        "stages": {"Vertex": pin, "Pixel": pin},
    }
    rd = NS(
        ShaderStage=NS(Vertex="VS", Pixel="PS"),
        DescriptorRange=lambda a: a,
        DescriptorType=NS(Sampler="Sampler", ImageSampler="ImageSampler"),
    )
    block = NS(name="matrix", byteSize=64, fixedBindSetOrSpace=0, fixedBindNumber=8)
    reflected = NS(
        rawBytes=b"shader",
        constantBlocks=[block],
        readOnlyResources=[
            NS(name="palette", fixedBindSetOrSpace=0, fixedBindNumber=9)
        ],
        samplers=[NS(name="base", fixedBindSetOrSpace=0, fixedBindNumber=11)],
    )
    desc = descriptor("ResourceId::32538")
    desc.format.Name = lambda: "D16"
    access = NS(
        index=0,
        arrayElement=0,
        descriptorStore="store",
        byteOffset=0,
        byteSize=1,
        stage="VS",
        type="Buffer",
        staticallyUnused=False,
    )
    buffer_desc = NS(
        resource="ResourceId::99",
        view="buffer-view",
        type="ReadOnlyBuffer",
        byteOffset=16,
        byteSize=64,
        elementByteSize=16,
    )
    texture_desc = descriptor("ResourceId::32538")
    state = NS(
        GetGraphicsPipelineObject=lambda: (
            "bad" if fault == "pipeline" else "ResourceId::7"
        ),
        GetShader=lambda s: "ResourceId::1",
        GetShaderReflection=lambda s: reflected,
        GetOutputTargets=list,
        GetDepthTarget=lambda: descriptor("bad") if fault == "depth" else desc,
        GetConstantBlock=lambda *a: NS(
            descriptor=NS(resource="CB", byteOffset=128, byteSize=64)
        ),
        GetReadOnlyResources=lambda s: [
            NS(access=access, descriptor=buffer_desc if s == "VS" else texture_desc)
        ],
        GetSamplers=lambda s: [NS(access=access)],
        GetVBuffers=lambda: [
            NS(resourceId="VB", byteOffset=16, byteSize=64, byteStride=16)
        ],
        GetIBuffer=lambda: NS(resourceId="IB", byteOffset=0, byteSize=6, byteStride=2),
        GetVertexInputs=lambda: [
            NS(
                name="position",
                vertexBuffer=0,
                byteOffset=0,
                perInstance=False,
                instanceRate=0,
                used=True,
                genericEnabled=False,
                format=NS(Name=lambda: "R32G32B32_FLOAT"),
            )
        ],
    )
    atlas = NS(
        resourceId="ResourceId::32538",
        width=4096,
        height=2048,
        depth=1,
        mips=1,
        arraysize=1,
        msSamp=1,
        format=NS(Name=lambda: "D16"),
    )
    if fault == "storage":
        atlas.width = 2048
    action = NS(eventId=272, numIndices=0 if fault == "indices" else 3, children=[])
    clear = NS(eventId=260, children=[])
    ctl = NS(
        GetFrameInfo=lambda: NS(frameNumber=0 if fault == "frame" else 6411),
        GetAPIProperties=lambda: NS(
            pipelineType="bad" if fault == "api" else "GraphicsAPI.Vulkan"
        ),
        GetTextures=lambda: [atlas],
        GetRootActions=lambda: [clear, action],
        GetStructuredFile=lambda: "structured",
        GetUsage=lambda r: [
            NS(eventId=260, usage="ResourceUsage.Clear"),
            NS(
                eventId=273 if fault == "usage" else 272,
                usage="ResourceUsage.DepthStencilTarget",
            ),
        ],
        SetFrameEvent=lambda *a: None,
        GetPipelineState=lambda: state,
        GetVulkanPipelineState=fixture_vk,
        GetBufferData=lambda *a: bytes(64),
        GetSamplerDescriptors=lambda *a: (
            []
            if fault == "sampler_count"
            else [NS(type="bad" if fault == "sampler_type" else "Sampler")]
        ),
    )
    with (
        patch.object(m, "clear_record", return_value={"event": 260}),
        patch.object(m, "action_record", return_value={"event": 272}),
        patch.object(m, "sampler_record", return_value={"addressU": "Wrap"}),
    ):
        if fault:
            with pytest.raises(ValueError):
                m.collect(rd, ctl, tmp_path, [spec])
        else:
            result = m.collect(rd, ctl, tmp_path, [spec])
            vs = result[0]["stages"]["Vertex"]
            assert vs["blocks"][0]["byte_offset"] == 128
            assert vs["resources"][0]["descriptor"]["byte_offset"] == 16
            assert (
                result[0]["stages"]["Pixel"]["resources"][0]["view"]["resource"]
                == atlas.resourceId
            )
            assert (tmp_path / "272-VS-set0-b8.raw").read_bytes() == bytes(64)
            assert json.loads((tmp_path / "272.json").read_text())["event"] == 272


@pytest.mark.parametrize("failure", ["", "controller", "capture"])
def test_complete_written_only_after_both_shutdowns(tmp_path, failure):
    m = tool()
    output = tmp_path / "result"
    capture = tmp_path / "frame.rdc"
    capture.touch()
    order = []

    def close(name):
        order.append(name)
        if failure == name:
            raise ValueError(name)

    with (
        patch.dict(
            "os.environ",
            ENDFIELD_TOOLS_PATH=str(tmp_path / "Tools"),
            ENDFIELD_CAPTURE_PATH=str(capture),
            ENDFIELD_CAPTURE_OUTPUT=str(output),
        ),
        patch.object(m, "prepare", return_value=[]),
        patch.object(
            m, "collect", side_effect=lambda *a: order.append("collect") or []
        ),
        patch.object(
            m.native,
            "open_controller",
            return_value=(
                NS(Shutdown=lambda: close("capture")),
                NS(Shutdown=lambda: close("controller")),
            ),
        ),
        patch.dict(sys.modules, renderdoc=NS()),
    ):
        if failure:
            with pytest.raises(ValueError):
                m.run()
            assert not (output / "complete.json").exists()
        else:
            m.run()
            assert json.loads((output / "complete.json").read_text())["status"] == "ok"
    assert order == ["collect", "controller", "capture"]


def test_main_exits_even_if_run_fails():
    with patch.dict("os.environ", {}, clear=True), pytest.raises(SystemExit):
        runpy.run_path(
            str(
                Path(__file__).resolve().parents[1] / "capture_shadow_atlas_writers.py"
            ),
            run_name="__main__",
        )
