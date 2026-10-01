"""Offline ShadowData / CP1 extraction using the pinned six actual programs.

The shared collector owns raw descriptors, PS hashes and both Shutdown guards.
This is source labeling/consumer input proof, not a screen-shadow producer.
"""

import os
import sys
from pathlib import Path

sys.path.insert(
    0, os.environ.get("ENDFIELD_TOOLS_PATH") or str(Path(__file__).resolve().parent)
)
import capture_character_lighting as native
from capture_cloth_normals import binding


def prepare(project):
    result = native.material_prepare(project)
    for spec in result:
        actual = project / (
            "Validation/draw-program-audit-20260930-01/event-"
            + str(spec["event"])
            + "-fragment-"
            + str(spec["program"])
            + ".hlsl"
        )
        named = project / spec["reference"]
        blocks = []
        for number, name in (
            (15, "_DirectionalShadowParams"),
            (16, "_CharacterParams1"),
        ):
            a, n = native.block(actual, number), native.block(named, number)
            if a["size"] != n["size"] or native.layout(a["members"]) != native.layout(
                n["members"]
            ):
                raise ValueError("Shadow/global layout differs")
            pairs = [
                (aa, nn)
                for aa, nn in zip(a["members"], n["members"])
                if nn["name"] == name
            ]
            if len(pairs) != 1:
                raise ValueError("Unique reviewed shadow field required")
            blocks.append(
                {
                    "binding": number,
                    "bytes": a["size"],
                    "actual": [pairs[0][0]],
                    "named": [pairs[0][1]],
                    "body": spec["body"],
                }
            )
        spec["blocks"] = blocks
    return result


def collect(rd, controller, output, plan):
    records = native.collect(rd, controller, output, plan)
    textures = {str(t.resourceId): t for t in controller.GetTextures()}
    first = None
    for record in records:
        controller.SetFrameEvent(record["event"], True)
        state = controller.GetPipelineState()
        reflection = state.GetShaderReflection(rd.ShaderStage.Pixel)
        candidates = [
            used.descriptor
            for used in state.GetReadOnlyResources(rd.ShaderStage.Pixel)
            if binding(used, reflection.readOnlyResources).get("set") == 0
            and binding(used, reflection.readOnlyResources).get("binding") == 22
        ]
        if len(candidates) != 1:
            raise ValueError("Unique screen mask set0/t22 required")
        d = candidates[0]
        t = textures[str(d.resource)]
        if (
            t.format.Name(),
            t.depth,
            t.arraysize,
            t.mips,
            d.format.Name(),
            str(d.textureType),
            d.firstMip,
            d.numMips,
            d.firstSlice,
            d.numSlices,
            d.minLODClamp,
        ) != (
            "R8G8_UNORM",
            1,
            1,
            1,
            "R8G8_UNORM",
            "TextureType.Texture2D",
            0,
            1,
            0,
            1,
            0,
        ):
            raise ValueError("Unreviewed screen mask storage/view")
        swizzle = [
            str(getattr(d.swizzle, c)) for c in ("red", "green", "blue", "alpha")
        ]
        if swizzle != [
            "TextureSwizzle." + c for c in ("Red", "Green", "Blue", "Alpha")
        ]:
            raise ValueError("Screen mask swizzle differs")
        raw = bytes(controller.GetTextureData(d.resource, rd.Subresource(0, 0, 0)))
        if len(raw) != t.width * t.height * 2:
            raise ValueError("Screen mask byte length differs")
        identity = (str(d.resource), t.width, t.height, native.sha(raw))
        if first is None:
            first = identity
            with (output / "screen-mask.raw").open("xb") as stream:
                stream.write(raw)
        elif first != identity:
            raise ValueError("Screen mask changed across reviewed draws")
        record["screen_mask"] = {
            "set": 0,
            "binding": 22,
            "resource": str(d.resource),
            "view": str(d.view),
            "format": t.format.Name(),
            "width": t.width,
            "height": t.height,
            "mips": 1,
            "swizzle": swizzle,
            "bytes": len(raw),
            "sha256": identity[3],
            "file": "screen-mask.raw",
            "sampling": "integer Load mip0; no sampler / UV / export flip",
        }
    return records


def run():
    return native.run(
        prepare,
        "endfield-shadow-selection-v1",
        "two reviewed float4 inputs per draw plus actual R8G8 screen mask; no full producer/weather certificate",
        collect,
    )


if __name__ == "__main__":
    try:
        run()
    finally:
        sys.exit()
