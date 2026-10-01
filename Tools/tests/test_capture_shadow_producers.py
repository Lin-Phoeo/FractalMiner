"""Fail-closed producer evidence, not screenshot/color fitting."""

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
    return importlib.import_module("capture_shadow_producers")


def test_plan_pins_both_actual_stages_against_original_exports():
    module = tool()
    root = Path(__file__).resolve().parents[2]
    plan = module.prepare(root)
    assert [p["event"] for p in plan] == [744, 748]
    assert [p["stages"]["Pixel"]["program"] for p in plan] == [2255, 2261]
    assert [p["stages"]["Vertex"]["program"] for p in plan] == [2254, 2260]
    assert [p["pipeline"] for p in plan] == [2416, 2417]


def test_pin_drift_rejected(tmp_path):
    module = tool()
    with (
        patch.object(module, "sha", return_value="drift"),
        pytest.raises(ValueError, match="archive"),
    ):
        module.prepare(Path(__file__).resolve().parents[2])


def test_explicit_fields_no_swig_pointer_or_optional_defaults():
    module = tool()
    value = NS(x=0.5, enum=NS(), this="opaque pointer", extra=9)
    assert module.fields(value, "x", "enum") == {"x": 0.5, "enum": "namespace()"}
    with pytest.raises(AttributeError):
        module.fields(value, "missing")


@pytest.mark.parametrize("fault", ["", "shader", "hash", "reflection"])
def test_actual_identity_validation(fault):
    module = tool()
    rd = NS(ShaderStage=NS(Pixel="PS"))
    reflection = None if fault == "reflection" else NS(rawBytes=b"shader")
    state = NS(
        GetShader=lambda stage: (
            "ResourceId::8" if fault == "shader" else "ResourceId::7"
        ),
        GetShaderReflection=lambda stage: reflection,
    )
    pin = {"program": 7, "sha256": "bad" if fault == "hash" else module.sha(b"shader")}
    if fault:
        with pytest.raises(ValueError):
            module.program_reflection(rd, state, "Pixel", pin)
    else:
        assert module.program_reflection(rd, state, "Pixel", pin) is reflection


@pytest.mark.parametrize("fault", ["", "range", "offset", "bytes"])
def test_raw_block_no_size_only_lookup(tmp_path, fault):
    module = tool()
    d = NS(
        resource="CB",
        byteOffset=-1 if fault == "offset" else 256,
        byteSize=8 if fault == "range" else 16,
    )
    block = NS(name="actual", fixedBindSetOrSpace=3, fixedBindNumber=13, byteSize=16)
    controller = NS(
        GetBufferData=lambda *args: b"short" if fault == "bytes" else bytes(16)
    )
    state = NS(GetConstantBlock=lambda *args: NS(descriptor=d))
    if fault:
        with pytest.raises(ValueError):
            module.raw_block(controller, state, "PS", 0, block, tmp_path, 748)
    else:
        record = module.raw_block(controller, state, "PS", 0, block, tmp_path, 748)
        assert record["set"] == 3 and record["binding"] == 13
        assert record["byte_offset"] == 256
        assert (tmp_path / record["file"]).read_bytes() == bytes(16)


def test_run_reuses_shutdown_guard():
    module = tool()
    with patch.object(module.native, "run", return_value="done") as run:
        assert module.run() == "done"
    assert run.call_args.args[0] is module.prepare
    assert run.call_args.args[3] is module.collect


def test_embedded_main_always_exits():
    module = tool()
    with patch.object(module.native, "run"), pytest.raises(SystemExit):
        runpy.run_path(str(module.__file__), run_name="__main__")


@pytest.mark.parametrize("failure", ["", "collect", "controller", "capture"])
def test_no_complete_until_both_shutdowns(tmp_path, monkeypatch, failure):
    module = tool()
    capture = tmp_path / "file.rdc"
    capture.write_bytes(b"offline")
    output = tmp_path / "export"
    monkeypatch.setenv("ENDFIELD_TOOLS_PATH", str(tmp_path / "Tools"))
    monkeypatch.setenv("ENDFIELD_CAPTURE_PATH", str(capture))
    monkeypatch.setenv("ENDFIELD_CAPTURE_OUTPUT", str(output))
    order = []

    def step(name):
        order.append(name)
        if name == failure:
            raise ValueError(name)
        return []

    with (
        patch.dict(sys.modules, renderdoc=NS()),
        patch.object(module, "prepare", return_value=[]),
        patch.object(module, "collect", side_effect=lambda *args: step("collect")),
        patch.object(
            module.native,
            "open_controller",
            return_value=(
                NS(Shutdown=lambda: step("capture")),
                NS(Shutdown=lambda: step("controller")),
            ),
        ),
    ):
        if failure:
            with pytest.raises(ValueError):
                module.run()
            assert not (output / "complete.json").exists()
            assert (output / "error.json").exists()
        else:
            module.run()
            assert json.loads((output / "complete.json").read_text())["status"] == "ok"
    assert order == ["collect", "controller", "capture"]


def descriptor(resource="ResourceId::58932"):
    return NS(
        resource=resource,
        view="view",
        type="Image",
        textureType="Texture2D",
        firstMip=0,
        numMips=1,
        firstSlice=0,
        numSlices=1,
        minLODClamp=0,
        format=NS(Name=lambda: "R8G8_UNORM"),
        swizzle=NS(red="Red", green="Green", blue="Blue", alpha="Alpha"),
    )


def fixture_vk():
    face = NS(
        failOperation="Keep",
        depthFailOperation="Keep",
        passOperation="Keep",
        function="Equal",
        reference=4,
        compareMask=7,
        writeMask=255,
    )
    equation = NS(source="One", destination="Zero", operation="Add")
    rect = NS(x=0, y=0, width=2560, height=1600, enabled=True, minDepth=0, maxDepth=1)
    return NS(
        depthStencil=NS(
            depthTestEnable=True,
            depthWriteEnable=False,
            depthBoundsEnable=False,
            depthFunction="Always",
            stencilTestEnable=True,
            minDepthBounds=0,
            maxDepthBounds=1,
            frontFace=face,
            backFace=face,
        ),
        colorBlend=NS(
            blends=[
                NS(
                    enabled=False,
                    logicOperationEnabled=False,
                    logicOperation="NoOp",
                    writeMask=15,
                    colorBlend=equation,
                    alphaBlend=equation,
                )
            ],
            blendFactor=[1] * 4,
            alphaToCoverageEnable=False,
            alphaToOneEnable=False,
        ),
        rasterizer=NS(
            depthClampEnable=False,
            depthClipEnable=True,
            rasterizerDiscardEnable=False,
            frontCCW=True,
            fillMode="Solid",
            cullMode="NoCull",
            depthBiasEnable=False,
            depthBias=0,
            depthBiasClamp=0,
            slopeScaledDepthBias=0,
        ),
        multisample=NS(
            rasterSamples=1,
            sampleShadingEnable=False,
            minSampleShading=1,
            sampleMask=0xFFFFFFFF,
        ),
        viewportScissor=NS(
            viewportScissors=[NS(vp=rect, scissor=rect)],
            depthNegativeOneToOne=False,
            discardRectangles=[rect],
            discardRectanglesExclusive=True,
        ),
        currentPass=NS(
            renderpass=NS(
                resourceId="renderpass",
                dynamic=False,
                subpass=0,
                depthstencilAttachment=1,
                inputAttachments=[],
                colorAttachments=[0],
                resolveAttachments=[],
            ),
            framebuffer=NS(
                resourceId="FB",
                width=2560,
                height=1600,
                layers=1,
                attachments=[descriptor()],
            ),
            renderArea=rect,
        ),
    )


def test_explicit_state_keeps_mask_stencil_and_view():
    module = tool()
    result = module.vk_state(fixture_vk())
    assert result["depth_stencil"]["frontFace"]["reference"] == 4
    assert result["depth_stencil"]["frontFace"]["compareMask"] == 7
    assert result["blend"]["targets"][0]["writeMask"] == 15
    assert result["framebuffer"]["attachments"][0]["format"] == "R8G8_UNORM"
    assert result["viewports"][0]["viewport"]["width"] == 2560


@pytest.mark.parametrize(
    "fault", ["", "frame", "api", "pipeline", "output", "sampler_count", "sampler_type"]
)
def test_collect_native_states_and_exact_raw_ranges(tmp_path, fault):
    module = tool()
    stages = NS(Pixel="PS", Vertex="VS")
    rd = NS(
        ShaderStage=stages,
        DescriptorRange=lambda a: a,
        DescriptorType=NS(Sampler="Sampler", ImageSampler="ImageSampler"),
    )
    b = NS(name="CB", fixedBindSetOrSpace=3, fixedBindNumber=13, byteSize=16)
    reflection = NS(
        rawBytes=b"shader",
        constantBlocks=[b],
        readOnlyResources=[NS(fixedBindNumber=7, fixedBindSetOrSpace=3, name="atlas")],
        samplers=[NS(fixedBindNumber=2, fixedBindSetOrSpace=3, name="atlas_sampler")],
    )
    pin = {"program": 7, "sha256": module.sha(b"shader")}
    plan = [{"event": 744, "pipeline": 2416, "stages": {"Pixel": pin, "Vertex": pin}}]
    access = NS(
        index=0,
        arrayElement=0,
        descriptorStore="store",
        byteOffset=0,
        byteSize=1,
        stage="PS",
        type="Image",
        staticallyUnused=False,
    )
    atlas = NS(
        resourceId="ResourceId::32538",
        width=32,
        height=16,
        depth=1,
        mips=1,
        arraysize=1,
        msSamp=1,
        format=NS(Name=lambda: "D16"),
    )
    state = NS(
        GetGraphicsPipelineObject=lambda: (
            "wrong" if fault == "pipeline" else "ResourceId::2416"
        ),
        GetShader=lambda s: "ResourceId::7",
        GetShaderReflection=lambda s: reflection,
        GetOutputTargets=lambda: [
            descriptor("wrong" if fault == "output" else "ResourceId::58932")
        ],
        GetDepthTarget=lambda: descriptor("DS"),
        GetReadOnlyResources=lambda s: (
            [NS(access=access, descriptor=descriptor(atlas.resourceId))]
            if s == "PS"
            else []
        ),
        GetSamplers=lambda s: [NS(access=access)] if s == "PS" else [],
        GetConstantBlock=lambda *args: NS(
            descriptor=NS(resource="CB", byteOffset=256, byteSize=16)
        ),
    )
    action = NS(eventId=744, children=[])
    ctl = NS(
        GetFrameInfo=lambda: NS(frameNumber=0 if fault == "frame" else 6411),
        GetAPIProperties=lambda: NS(
            pipelineType="wrong" if fault == "api" else "GraphicsAPI.Vulkan"
        ),
        GetTextures=lambda: [atlas],
        GetRootActions=lambda: [action],
        GetStructuredFile=lambda: "structured",
        GetUsage=lambda r: [
            NS(eventId=744, usage="PS_Resource"),
            NS(eventId=260, usage="Clear"),
        ],
        SetFrameEvent=lambda *args: None,
        GetPipelineState=lambda: state,
        GetVulkanPipelineState=fixture_vk,
        GetBufferData=lambda *args: bytes(16),
        GetSamplerDescriptors=lambda *args: (
            []
            if fault == "sampler_count"
            else [NS(type="wrong" if fault == "sampler_type" else "Sampler")]
        ),
    )
    with (
        patch.object(module, "action_record", return_value={"event": 744}),
        patch.object(module, "sampler_record", return_value={"addressU": "ClampEdge"}),
    ):
        if fault:
            with pytest.raises(ValueError):
                module.collect(rd, ctl, tmp_path, plan)
        else:
            records = module.collect(rd, ctl, tmp_path, plan)
            assert (
                records[0]["stages"]["Pixel"]["resources"][0]["storage"]["format"]
                == "D16"
            )
            assert records[0]["stages"]["Pixel"]["blocks"][0]["byte_offset"] == 256
            assert (tmp_path / "744-Pixel-7.spv").read_bytes() == b"shader"
            assert json.loads((tmp_path / "744.json").read_text())["event"] == 744
