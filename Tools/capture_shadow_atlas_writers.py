"""Pinned frame6411 depth-atlas writers, raw CBs, alpha inputs and VK states.

Offline RDC only. Names/usage alone are not writer certification. This evidence
does not reconstruct dynamic allocation or approve the live URP adapter.
Python3.8 compatible with official qrenderdoc1.46 --python.
"""

import os
import sys
from pathlib import Path

sys.path.insert(
    0, os.environ.get("ENDFIELD_TOOLS_PATH") or str(Path(__file__).resolve().parent)
)
import capture_character_lighting as native
from capture_shadow_producers import (
    action_record,
    binding,
    fields,
    flatten_actions,
    program_reflection,
    raw_block,
    sampler_record,
    sha,
    texture_view,
    vk_state,
    write_new_json,
)

SHADERS = {
    9043: "c1ef70da06556dae800ea6f6cc3421dec3f566488c84d1e760e656826609f674",
    9044: "c2508a8fcd63e61a44168953688cef5e9aa5300c7a803ebd7de48cc23453cf1b",
    9045: "c1ef70da06556dae800ea6f6cc3421dec3f566488c84d1e760e656826609f674",
    9046: "c2508a8fcd63e61a44168953688cef5e9aa5300c7a803ebd7de48cc23453cf1b",
    9049: "0c82a411bdb500f604799828b7d1459a6763ae8da7feaf5edc7aa0c27de49042",
    9050: "6066195850029e2be475bf8fe92d87a78fef467cefe9cdc3f615d3db56e153b8",
    9060: "c1ef70da06556dae800ea6f6cc3421dec3f566488c84d1e760e656826609f674",
    9061: "c2508a8fcd63e61a44168953688cef5e9aa5300c7a803ebd7de48cc23453cf1b",
    9062: "c1ef70da06556dae800ea6f6cc3421dec3f566488c84d1e760e656826609f674",
    9063: "c2508a8fcd63e61a44168953688cef5e9aa5300c7a803ebd7de48cc23453cf1b",
    9064: "0c82a411bdb500f604799828b7d1459a6763ae8da7feaf5edc7aa0c27de49042",
    9065: "2dd37825cb653cd9e956bc4c001f3fbdc51f9ddc28d32f3fe6307588853fd322",
    65355: "8c9c250e85b2a7ffabce612c6075e110865359023e497a1c78e6232966e1f5c2",
    65356: "743b47f92bcf42b2aa87914ba3c22ba1a79146d42087643a223995d36bd75048",
}
# event, actual pipeline, VS, PS, index count: pinned from original raw archive.
DRAWS = (
    (272, 37685, 9062, 9063, 1566),
    (277, 22311, 9060, 9061, 4248),
    (282, 22306, 9064, 9065, 624),
    (286, 22306, 9064, 9065, 168),
    (291, 63942, 9064, 9065, 1230),
    (296, 22306, 9064, 9065, 624),
    (300, 22306, 9064, 9065, 1008),
    (304, 22306, 9064, 9065, 624),
    (308, 22306, 9064, 9065, 624),
    (312, 22306, 9064, 9065, 906),
    (316, 22306, 9064, 9065, 624),
    (321, 62044, 9064, 9065, 52296),
    (326, 37686, 9043, 9044, 94791),
    (331, 22314, 9043, 9044, 16101),
    (336, 37687, 9043, 9044, 5778),
    (341, 22314, 9043, 9044, 36852),
    (346, 37687, 9043, 9044, 17232),
    (351, 22311, 9060, 9061, 10686),
    (356, 37688, 9060, 9061, 420),
    (361, 22312, 9064, 9065, 276),
    (366, 22315, 9045, 9046, 54816),
    (371, 68927, 65355, 65356, 246),
    (376, 37689, 9049, 9050, 2016),
)


def prepare(project):
    for program, expected in SHADERS.items():
        path = project / (
            "Validation/Captures/tifuluosi-front-20260917/replay-details-01/shader-"
            + str(program)
            + ".spv"
        )
        if sha(path.read_bytes()) != expected:
            raise ValueError("Original archive program hash differs")
    return [
        {
            "event": e,
            "pipeline": p,
            "indices": n,
            "stages": {
                "Vertex": {"program": v, "sha256": SHADERS[v]},
                "Pixel": {"program": f, "sha256": SHADERS[f]},
            },
        }
        for e, p, v, f, n in DRAWS
    ]


def sd_record(obj, depth=0, budget=None):
    """Serialize the correct POD union member by type, never all casts/defaults."""
    if budget is None:
        budget = [10000]
    budget[0] -= 1
    if depth > 16 or budget[0] < 0:
        raise ValueError("Structured clear tree exceeds reviewed bounds")
    kind = str(obj.type.basetype).split(".")[-1]
    result = {
        "name": obj.name,
        "type": obj.type.name,
        "basic": kind,
        "bytes": obj.type.byteSize,
        "flags": int(obj.type.flags),
    }
    if kind in ("Chunk", "Struct", "Array"):
        result["children"] = [
            sd_record(obj.GetChild(i), depth + 1, budget)
            for i in range(obj.NumChildren())
        ]
    elif kind == "Null":
        result["value"] = None
    elif kind == "String":
        result["value"] = obj.data.str
    else:
        member = {
            "Float": "d",
            "Boolean": "b",
            "Character": "c",
            "Resource": "id",
            "SignedInteger": "i",
            "UnsignedInteger": "u",
            "GPUAddress": "u",
            "Enum": "u",
        }.get(kind)
        if member is None:
            raise ValueError("Unsupported structured scalar " + kind)
        value = getattr(obj.data.basic, member)
        result["value"] = str(value) if kind == "Resource" else value
    return result


def clear_record(action, structured):
    events = [e for e in action.events if e.eventId == action.eventId]
    if len(events) != 1 or not 0 <= events[0].chunkIndex < len(structured.chunks):
        raise ValueError("Unique clear API-event/chunk association required")
    chunk = structured.chunks[events[0].chunkIndex]
    if chunk.name != "vkCmdBeginRenderPass":
        raise ValueError("Unexpected clear command")
    return {
        "event": action.eventId,
        "chunk_index": events[0].chunkIndex,
        "chunk": sd_record(chunk),
    }


def resources(controller, rd, state, stage, reflection, textures):
    result = []
    for used in state.GetReadOnlyResources(stage):
        item = binding(used, reflection.readOnlyResources)
        d = used.descriptor
        if str(d.resource) in textures:
            item["view"] = texture_view(d)
            t = textures[str(d.resource)]
            item["storage"] = fields(
                t, "width", "height", "depth", "mips", "arraysize", "msSamp"
            )
            item["storage"]["format"] = t.format.Name()
        else:
            # Skin palettes are buffer views, not textures. Record actual range.
            item["descriptor"] = {
                "resource": str(d.resource),
                "view": str(d.view),
                "type": str(d.type),
                "byte_offset": d.byteOffset,
                "bytes": d.byteSize,
                "element_bytes": d.elementByteSize,
            }
        result.append(item)
    samplers = []
    for used in state.GetSamplers(stage):
        item = binding(used, reflection.samplers)
        actual = controller.GetSamplerDescriptors(
            used.access.descriptorStore, [rd.DescriptorRange(used.access)]
        )
        if len(actual) != 1 or actual[0].type not in (
            rd.DescriptorType.Sampler,
            rd.DescriptorType.ImageSampler,
        ):
            raise ValueError("Unresolved actual sampler")
        item["sampler"] = sampler_record(actual[0])
        samplers.append(item)
    return result, samplers


def vertex_inputs(state):
    buffer_fields = ("resourceId", "byteOffset", "byteSize", "byteStride")
    attrs = []
    for a in state.GetVertexInputs():
        item = fields(
            a,
            "name",
            "vertexBuffer",
            "byteOffset",
            "perInstance",
            "instanceRate",
            "used",
            "genericEnabled",
        )
        item["format"] = a.format.Name()
        attrs.append(item)
    return {
        "vertex_buffers": [fields(b, *buffer_fields) for b in state.GetVBuffers()],
        "index_buffer": fields(state.GetIBuffer(), *buffer_fields),
        "attributes": attrs,
    }


def collect(rd, controller, output, plan):
    if controller.GetFrameInfo().frameNumber != 6411:
        raise ValueError("Requires frame6411")
    if str(controller.GetAPIProperties().pipelineType) != "GraphicsAPI.Vulkan":
        raise ValueError("Requires reviewed Vulkan capture")
    textures = {str(t.resourceId): t for t in controller.GetTextures()}
    atlas = textures["ResourceId::32538"]
    if (
        atlas.width,
        atlas.height,
        atlas.depth,
        atlas.mips,
        atlas.arraysize,
        atlas.msSamp,
        atlas.format.Name(),
    ) != (4096, 2048, 1, 1, 1, 1, "D16"):
        raise ValueError("Actual atlas storage differs")
    actions = {a.eventId: a for a in flatten_actions(controller.GetRootActions())}
    structured = controller.GetStructuredFile()
    usage = list(controller.GetUsage(atlas.resourceId))
    writers = [
        u.eventId for u in usage if str(u.usage) == "ResourceUsage.DepthStencilTarget"
    ]
    clears = [u.eventId for u in usage if str(u.usage) == "ResourceUsage.Clear"]
    if writers != [p["event"] for p in plan] or clears != [260]:
        raise ValueError("Actual atlas clear/writer event set differs")
    write_new_json(output / "clear.json", clear_record(actions[260], structured))
    records = []
    for spec in plan:
        event = spec["event"]
        controller.SetFrameEvent(event, True)
        state = controller.GetPipelineState()
        if (
            str(state.GetGraphicsPipelineObject())
            != "ResourceId::" + str(spec["pipeline"])
            or actions[event].numIndices != spec["indices"]
        ):
            raise ValueError("Actual pipeline/index count differs")
        depth = texture_view(state.GetDepthTarget())
        if depth["resource"] != "ResourceId::32538" or depth["format"] != "D16":
            raise ValueError("Unexpected actual depth target")
        record = {
            "event": event,
            "pipeline": spec["pipeline"],
            "action": action_record(actions[event], structured),
            "depth": depth,
            "outputs": [texture_view(d) for d in state.GetOutputTargets()],
            "vk_state": vk_state(controller.GetVulkanPipelineState()),
            "vertex_inputs": vertex_inputs(state),
            "stages": {},
        }
        for stage_name, pin in spec["stages"].items():
            stage = getattr(rd.ShaderStage, stage_name)
            reflection = program_reflection(rd, state, stage_name, pin)
            filename = "{}-{}-{}.spv".format(event, stage_name, pin["program"])
            with (output / filename).open("xb") as stream:
                stream.write(bytes(reflection.rawBytes))
            inputs, samplers = resources(
                controller, rd, state, stage, reflection, textures
            )
            record["stages"][stage_name] = dict(
                pin,
                file=filename,
                resources=inputs,
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
        "endfield-shadow-atlas-writer-evidence-v1",
        "frame6411 23 actual D16 writers, raw CBs and explicit states; no dynamic allocator/live certification",
        collect,
    )


if __name__ == "__main__":
    try:
        run()
    finally:
        sys.exit()
