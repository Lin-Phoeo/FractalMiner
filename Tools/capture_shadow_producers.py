"""Pinned frame6411 resolve producers: offline programs, raw CBs and VK state.

No game access. Uses the shared post-Shutdown completion guard. This exporter
records states, it does not certify the full live atlas / directional producer.
Python3.8 compatible for official qrenderdoc1.46 --python.
"""

import os
import sys
from pathlib import Path

sys.path.insert(
    0, os.environ.get("ENDFIELD_TOOLS_PATH") or str(Path(__file__).resolve().parent)
)
import capture_character_lighting as native
from capture_bloom_evidence import sampler_record
from capture_cloth_normals import binding
from capture_material_uniforms import sha
from capture_replay_inventory import action_record, flatten_actions, write_new_json

VERTEX_HASH = "9fb0158d67a31be253954afba3c31d164c160e302fe1a0d62785b8645b871b82"
PLAN = [
    {
        "event": 744,
        "pipeline": 2416,
        "stages": {
            "Vertex": {"program": 2254, "sha256": VERTEX_HASH},
            "Pixel": {
                "program": 2255,
                "sha256": "508c936ed3c95b75d5effa6529f9909d48d30304144734c63452f3b257fc57a3",
            },
        },
    },
    {
        "event": 748,
        "pipeline": 2417,
        "stages": {
            "Vertex": {"program": 2260, "sha256": VERTEX_HASH},
            "Pixel": {
                "program": 2261,
                "sha256": "8c0f0c3bd1dc58c5d4560435dd7ff505662ec7c6870c64065810e3ca2e681685",
            },
        },
    },
]


def prepare(project):
    for plan in PLAN:
        for pin in plan["stages"].values():
            path = project / (
                "Validation/Captures/tifuluosi-front-20260917/replay-details-01/shader-"
                + str(pin["program"])
                + ".spv"
            )
            if sha(path.read_bytes()) != pin["sha256"]:
                raise ValueError("Original archive program hash differs")
    return PLAN


def fields(value, *names):
    """Only explicitly requested scalar/enum fields; missing fields hard fail."""
    record = {}
    for name in names:
        v = getattr(value, name)
        record[name] = v if type(v) in (str, bool, int, float) else str(v)
    return record


def texture_view(d):
    record = fields(
        d,
        "resource",
        "view",
        "type",
        "textureType",
        "firstMip",
        "numMips",
        "firstSlice",
        "numSlices",
        "minLODClamp",
    )
    record["format"] = d.format.Name()
    record["swizzle"] = fields(d.swizzle, "red", "green", "blue", "alpha")
    return record


def vk_state(vk):
    depth = fields(
        vk.depthStencil,
        "depthTestEnable",
        "depthWriteEnable",
        "depthBoundsEnable",
        "depthFunction",
        "stencilTestEnable",
        "minDepthBounds",
        "maxDepthBounds",
    )
    for side in ("frontFace", "backFace"):
        depth[side] = fields(
            getattr(vk.depthStencil, side),
            "failOperation",
            "depthFailOperation",
            "passOperation",
            "function",
            "reference",
            "compareMask",
            "writeMask",
        )
    blends = []
    for blend in vk.colorBlend.blends:
        record = fields(
            blend, "enabled", "logicOperationEnabled", "logicOperation", "writeMask"
        )
        for channel in ("colorBlend", "alphaBlend"):
            record[channel] = fields(
                getattr(blend, channel), "source", "destination", "operation"
            )
        blends.append(record)
    current = vk.currentPass
    rp = current.renderpass
    renderpass = fields(
        rp, "resourceId", "dynamic", "subpass", "depthstencilAttachment"
    )
    for name in ("inputAttachments", "colorAttachments", "resolveAttachments"):
        renderpass[name] = list(getattr(rp, name))
    fb = fields(current.framebuffer, "resourceId", "width", "height", "layers")
    fb["attachments"] = [texture_view(d) for d in current.framebuffer.attachments]
    return {
        "depth_stencil": depth,
        "blend": {
            "alphaToCoverageEnable": vk.colorBlend.alphaToCoverageEnable,
            "alphaToOneEnable": vk.colorBlend.alphaToOneEnable,
            "blendFactor": list(vk.colorBlend.blendFactor),
            "targets": blends,
        },
        "rasterizer": fields(
            vk.rasterizer,
            "depthClampEnable",
            "depthClipEnable",
            "rasterizerDiscardEnable",
            "frontCCW",
            "fillMode",
            "cullMode",
            "depthBiasEnable",
            "depthBias",
            "depthBiasClamp",
            "slopeScaledDepthBias",
        ),
        "multisample": fields(
            vk.multisample,
            "rasterSamples",
            "sampleShadingEnable",
            "minSampleShading",
            "sampleMask",
        ),
        "viewports": [
            {
                "viewport": fields(
                    v.vp, "x", "y", "width", "height", "minDepth", "maxDepth"
                ),
                "scissor": fields(v.scissor, "x", "y", "width", "height", "enabled"),
            }
            for v in vk.viewportScissor.viewportScissors
        ],
        "depthNegativeOneToOne": vk.viewportScissor.depthNegativeOneToOne,
        "discardRectangles": [
            fields(r, "x", "y", "width", "height")
            for r in vk.viewportScissor.discardRectangles
        ],
        "discardRectanglesExclusive": vk.viewportScissor.discardRectanglesExclusive,
        "renderpass": renderpass,
        "framebuffer": fb,
        "render_area": fields(current.renderArea, "x", "y", "width", "height"),
    }


def program_reflection(rd, state, stage_name, pin):
    stage = getattr(rd.ShaderStage, stage_name)
    reflection = state.GetShaderReflection(stage)
    if (
        reflection is None
        or str(state.GetShader(stage)) != "ResourceId::" + str(pin["program"])
        or sha(bytes(reflection.rawBytes)) != pin["sha256"]
    ):
        raise ValueError("Actual program identity/hash differs")
    return reflection


def raw_block(controller, state, stage, index, block, output, event):
    d = state.GetConstantBlock(stage, index, 0).descriptor
    if block.byteSize <= 0 or d.byteOffset < 0 or d.byteSize < block.byteSize:
        raise ValueError("Truncated or invalid CB descriptor range")
    data = bytes(controller.GetBufferData(d.resource, d.byteOffset, block.byteSize))
    if len(data) != block.byteSize:
        raise ValueError("Truncated raw CB bytes")
    filename = (
        f"{event}-{stage}-set{block.fixedBindSetOrSpace}-b{block.fixedBindNumber}.raw"
    )
    with (output / filename).open("xb") as stream:
        stream.write(data)
    return {
        "name": block.name,
        "set": block.fixedBindSetOrSpace,
        "binding": block.fixedBindNumber,
        "resource": str(d.resource),
        "byte_offset": d.byteOffset,
        "descriptor_bytes": d.byteSize,
        "bytes": len(data),
        "file": filename,
        "sha256": sha(data),
    }


def collect(rd, controller, output, plan):
    if controller.GetFrameInfo().frameNumber != 6411:
        raise ValueError("Requires frame6411")
    if str(controller.GetAPIProperties().pipelineType) != "GraphicsAPI.Vulkan":
        raise ValueError("Requires reviewed Vulkan capture")
    textures = {str(t.resourceId): t for t in controller.GetTextures()}
    actions = {a.eventId: a for a in flatten_actions(controller.GetRootActions())}
    structured = controller.GetStructuredFile()
    atlas = textures["ResourceId::32538"]
    # Resource usage is a discovery list, not a claim that every event is a writer.
    write_new_json(
        output / "atlas-usage.json",
        [
            {
                "event": u.eventId,
                "usage": str(u.usage),
                "action": action_record(actions[u.eventId], structured)
                if u.eventId in actions
                else None,
            }
            for u in controller.GetUsage(atlas.resourceId)
        ],
    )
    records = []
    for spec in plan:
        event = spec["event"]
        controller.SetFrameEvent(event, True)
        state = controller.GetPipelineState()
        if str(state.GetGraphicsPipelineObject()) != "ResourceId::" + str(
            spec["pipeline"]
        ):
            raise ValueError("Actual pipeline differs")
        record = {
            "event": event,
            "pipeline": spec["pipeline"],
            "action": action_record(actions[event], structured),
            "outputs": [texture_view(d) for d in state.GetOutputTargets()],
            "depth": texture_view(state.GetDepthTarget()),
            "vk_state": vk_state(controller.GetVulkanPipelineState()),
            "stages": {},
        }
        if record["outputs"][0]["resource"] != "ResourceId::58932":
            raise ValueError("Wrong resolved output")
        for stage_name, pin in spec["stages"].items():
            stage = getattr(rd.ShaderStage, stage_name)
            reflection = program_reflection(rd, state, stage_name, pin)
            filename = "{}-{}-{}.spv".format(event, stage_name, pin["program"])
            with (output / filename).open("xb") as stream:
                stream.write(bytes(reflection.rawBytes))
            resources = []
            for used in state.GetReadOnlyResources(stage):
                item = binding(used, reflection.readOnlyResources)
                item["view"] = texture_view(used.descriptor)
                t = textures[item["view"]["resource"]]
                item["storage"] = fields(
                    t, "width", "height", "depth", "mips", "arraysize", "msSamp"
                )
                item["storage"]["format"] = t.format.Name()
                resources.append(item)
            samplers = []
            for used in state.GetSamplers(stage):
                item = binding(used, reflection.samplers)
                descriptors = controller.GetSamplerDescriptors(
                    used.access.descriptorStore, [rd.DescriptorRange(used.access)]
                )
                if len(descriptors) != 1 or descriptors[0].type not in (
                    rd.DescriptorType.Sampler,
                    rd.DescriptorType.ImageSampler,
                ):
                    raise ValueError("Unresolved actual sampler")
                item["sampler"] = sampler_record(descriptors[0])
                samplers.append(item)
            record["stages"][stage_name] = dict(
                pin,
                file=filename,
                resources=resources,
                samplers=samplers,
                blocks=[
                    raw_block(controller, state, stage, i, b, output, event)
                    for i, b in enumerate(reflection.constantBlocks)
                ],
            )
        write_new_json(output / (str(event) + ".json"), record)
        records.append(record)
    return records


def run():
    return native.run(
        prepare,
        "endfield-shadow-producer-evidence-v1",
        "744/748 actual programs + raw CBs + explicit VK states only; atlas/directional live fidelity not certified",
        collect,
    )


if __name__ == "__main__":
    try:
        run()
    finally:
        sys.exit()
