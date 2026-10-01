"""Offline native material inputs for the two reviewed frame6411 PS variants.

Actual shader/reflection/view/sampler evidence; no live game access, PNG exports,
resampling or guessed ShadowLUT binding. Output must be fresh; complete.json is
written only after replay shutdown. A new manifest is not automatically trusted.
"""

import hashlib
import os
import sys
import traceback
from pathlib import Path

sys.path.insert(
    0, os.environ.get("ENDFIELD_TOOLS_PATH") or str(Path(__file__).resolve().parent)
)
from capture_bloom_evidence import sampler_record
from capture_cloth_normals import binding
from capture_replay_inventory import open_controller, validate_paths, write_new_json

ROLES = {
    835: {"SpecRamp": 1, "P": 2, "DiffRamp": 3, "Base": 5},
    850: {"SpecRamp": 1, "P": 2, "E": 3, "DiffRamp": 4, "Base": 6},
}
PROGRAMS = {835: 22255, 850: 37669}
IDENTITY = ["TextureSwizzle." + c for c in ("Red", "Green", "Blue", "Alpha")]


def level_bytes(width, height, format_name):
    if any(type(v) is not int or v < 1 for v in (width, height)):
        raise ValueError("Positive integer native extents required")
    family = format_name.replace("_SRGB", "_UNORM")
    if family in ("BC1_UNORM", "BC3_UNORM", "BC5_UNORM", "BC7_UNORM"):
        return (
            ((width + 3) // 4)
            * ((height + 3) // 4)
            * (8 if family == "BC1_UNORM" else 16)
        )
    if family == "R8G8B8A8_UNORM":
        return width * height * 4
    raise ValueError("Unreviewed native material format: " + format_name)


def validate_view(image, view):
    same_storage = image["format"].replace("_SRGB", "_UNORM") == view["format"].replace(
        "_SRGB", "_UNORM"
    )
    expected = {
        "textureType": "TextureType.Texture2D",
        "firstMip": 0,
        "numMips": image["mips"],
        "firstSlice": 0,
        "numSlices": 1,
        "minLODClamp": 0,
        "swizzle": IDENTITY,
    }
    if (
        image["depth"] != 1
        or image["arraysize"] != 1
        or not same_storage
        or any(view.get(k) != v for k, v in expected.items())
    ):
        raise ValueError("Unexpected native material image/view domain: " + str(view))
    level_bytes(image["width"], image["height"], image["format"])


def validate_sampler(record, number):
    address = "AddressMode.Wrap" if number == 4 else "AddressMode.ClampEdge"
    expected: dict = {k: address for k in ("addressU", "addressV", "addressW")}
    expected.update(
        filter={
            "minify": "FilterMode.Linear",
            "magnify": "FilterMode.Linear",
            "mip": "FilterMode.Point",
            "filter": "FilterFunction.Normal",
        },
        maxAnisotropy=0,
        minLOD=0,
        maxLOD=1000,
        mipBias=0,
        unnormalized=False,
        compareFunction="CompareFunction.Never",
    )
    if number not in (4, 6) or any(record.get(k) != v for k, v in expected.items()):
        raise ValueError("Unreviewed material sampler")


def collect(
    rd, controller, output, roles_by_event=None, programs=None, role_samplers=None, resource_set=1
):
    if type(resource_set) is not int or resource_set not in (0, 1):
        raise ValueError("Only reviewed global/material descriptor sets 0/1 supported")
    roles_by_event = ROLES if roles_by_event is None else roles_by_event
    programs = PROGRAMS if programs is None else programs
    if set(roles_by_event) != set(programs):
        raise ValueError("Every reviewed draw requires an exact PS identity")
    if controller.GetFrameInfo().frameNumber != 6411:
        raise ValueError("Requires frame6411")
    textures = {str(t.resourceId): t for t in controller.GetTextures()}
    results = []
    for event, roles in roles_by_event.items():
        controller.SetFrameEvent(event, True)
        state, stage = controller.GetPipelineState(), rd.ShaderStage.Pixel
        if str(state.GetShader(stage)) != "ResourceId::" + str(programs[event]):
            raise ValueError("PS identity mismatch")
        reflection = state.GetShaderReflection(stage)
        resources = {}
        for used in state.GetReadOnlyResources(stage):
            record = binding(used, reflection.readOnlyResources)
            if record["set"] == resource_set and record["binding"] in roles.values():
                if record["binding"] in resources:
                    raise ValueError("Duplicate material descriptor")
                resources[record["binding"]] = (used, record)
        if set(resources) != set(roles.values()):
            raise ValueError("Missing material descriptor")
        samplers = {}
        for used in state.GetSamplers(stage):
            record = binding(used, reflection.samplers)
            if record["set"] != 0 or record["binding"] not in (4, 6):
                continue
            resolved = controller.GetSamplerDescriptors(
                used.access.descriptorStore, [rd.DescriptorRange(used.access)]
            )
            if len(resolved) != 1 or resolved[0].type not in (
                rd.DescriptorType.Sampler,
                rd.DescriptorType.ImageSampler,
            ):
                raise ValueError("Unresolved material sampler")
            record["sampler"] = sampler_record(resolved[0])
            validate_sampler(record["sampler"], record["binding"])
            if record["binding"] in samplers:
                raise ValueError("Duplicate material sampler")
            samplers[record["binding"]] = record
        if set(samplers) != {4, 6}:
            raise ValueError("Both s4 and s6 evidence required")
        for role, number in roles.items():
            used, record = resources[number]
            d = used.descriptor
            texture = textures[str(d.resource)]
            image = {
                k: getattr(texture, k)
                for k in ("width", "height", "depth", "arraysize", "mips")
            }
            image["format"] = texture.format.Name()
            view: dict = {
                k: getattr(d, k)
                for k in (
                    "firstMip",
                    "numMips",
                    "firstSlice",
                    "numSlices",
                    "minLODClamp",
                )
            }
            view.update(
                format=d.format.Name(),
                textureType=str(d.textureType),
                resource=str(d.resource),
                view=str(d.view),
            )
            view["swizzle"] = [
                str(getattr(d.swizzle, c)) for c in ("red", "green", "blue", "alpha")
            ]
            validate_view(image, view)
            sample_cast = (
                rd.CompType.UNormSRGB
                if view["format"].endswith("_SRGB")
                else rd.CompType.UNorm
            )
            levels, samples, payload = [], [], bytearray()
            for mip in range(texture.mips):
                w, h = max(1, texture.width >> mip), max(1, texture.height >> mip)
                raw = bytes(
                    controller.GetTextureData(
                        texture.resourceId, rd.Subresource(mip, 0, 0)
                    )
                )
                if len(raw) != level_bytes(w, h, image["format"]):
                    raise ValueError("Native material mip size mismatch")
                levels.append(
                    {
                        "mip": mip,
                        "width": w,
                        "height": h,
                        "offset": len(payload),
                        "bytes": len(raw),
                        "sha256": hashlib.sha256(raw).hexdigest(),
                    }
                )
                payload.extend(raw)
                for x, y in (
                    (0, 0),
                    (w - 1, 0),
                    (0, h - 1),
                    (w - 1, h - 1),
                    (w // 2, h // 2),
                ):
                    picked = controller.PickPixel(
                        texture.resourceId, x, y, rd.Subresource(mip, 0, 0), sample_cast
                    )
                    samples.append(
                        {"mip": mip, "x": x, "y": y, "rgba": list(picked.floatValue)}
                    )
            filename = str(event) + "-" + role + ".raw"
            with (output / filename).open("xb") as stream:
                stream.write(payload)
            results.append(
                {
                    "event": event,
                    "shader": programs[event],
                    "shader_sha256": hashlib.sha256(
                        bytes(reflection.rawBytes)
                    ).hexdigest(),
                    "role": role,
                    "file": filename,
                    "bytes": len(payload),
                    "sha256": hashlib.sha256(payload).hexdigest(),
                    "image": image,
                    "view": view,
                    "binding": record,
                    "sampler": samplers[
                        role_samplers[role]
                        if role_samplers is not None
                        else (6 if role.endswith("Ramp") else 4)
                    ],
                    "levels": levels,
                    "sample_cast": str(sample_cast),
                    "native_samples": samples,
                }
            )
    return results


def run(roles_by_event=None, programs=None, role_samplers=None, resource_set=1):
    capture = Path(os.environ["ENDFIELD_CAPTURE_PATH"]).resolve()
    output = Path(os.environ["ENDFIELD_CAPTURE_OUTPUT"]).resolve()
    validate_paths(capture, output)
    write_new_json(output / "started.json", {"capture": str(capture)})
    cap = controller = None
    try:
        try:
            import renderdoc as rd  # pyright: ignore[reportMissingImports]

            cap, controller = open_controller(rd, capture)
            results = collect(
                rd, controller, output, roles_by_event, programs, role_samplers, resource_set
            )
        finally:
            try:
                if controller is not None:
                    controller.Shutdown()
            finally:
                if cap is not None:
                    cap.Shutdown()
        write_new_json(
            output / "complete.json",
            {
                "status": "ok",
                "frame": 6411,
                "textures": results,
                "contract": "actual material PS bindings; native draw-time blocks/full mip/view/sampler; PickPixel typeCast explicitly matches reviewed view sRGB/UNorm, RGB linear shader-domain and alpha unchanged",
            },
        )
    except BaseException:
        write_new_json(output / "error.json", {"traceback": traceback.format_exc()})
        raise


if __name__ == "__main__":
    try:
        run()
    finally:
        sys.exit()
