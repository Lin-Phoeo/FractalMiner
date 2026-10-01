"""Offline frame6411 native cube/view/sampler audit; never inject a process.

Official qrenderdoc --python; ENDFIELD_CAPTURE_PATH, ENDFIELD_CAPTURE_OUTPUT
(fresh directory), ENDFIELD_TOOLS_PATH and ENDFIELD_ENVIRONMENT_DDS required.
The reviewed DDS is checked against every draw-time compressed subresource.
complete.json is emitted only after replay resources shut down successfully.
"""

import hashlib
import os
import struct
import sys
import traceback
from pathlib import Path

sys.path.insert(
    0, os.environ.get("ENDFIELD_TOOLS_PATH") or str(Path(__file__).resolve().parent)
)
from capture_bloom_evidence import sampler_record
from capture_cloth_normals import binding
from capture_replay_inventory import open_controller, validate_paths, write_new_json

DDS_SHA256 = "3b0aa26b56ede6b780c186add2778d7155931fa9797ee513db6cd7c2a345b223"
EXPECTED_VIEW: dict = {
    "format": "BC6_UFLOAT",
    "textureType": "TextureType.TextureCube",
    "firstMip": 0,
    "numMips": 8,
    "firstSlice": 0,
    "numSlices": 6,
    "minLODClamp": 0,
    "swizzle": ["TextureSwizzle." + c for c in ("Red", "Green", "Blue", "Alpha")],
}
EXPECTED_SAMPLER: dict = {
    "addressU": "AddressMode.ClampEdge",
    "addressV": "AddressMode.ClampEdge",
    "addressW": "AddressMode.ClampEdge",
    "compareFunction": "CompareFunction.Never",
    "filter": {
        "minify": "FilterMode.Linear",
        "magnify": "FilterMode.Linear",
        "mip": "FilterMode.Point",
        "filter": "FilterFunction.Normal",
    },
    "maxAnisotropy": 0,
    "minLOD": 0,
    "maxLOD": 1000,
    "mipBias": 0,
    "unnormalized": False,
    "seamlessCubemaps": True,
}


def cube_layout():
    rows, offset = [], 0
    for face in range(6):
        for mip in range(8):
            width = max(1, 128 >> mip)
            size = ((width + 3) // 4) ** 2 * 16
            rows.append(
                {
                    "face": face,
                    "mip": mip,
                    "width": width,
                    "offset": offset,
                    "bytes": size,
                }
            )
            offset += size
    return rows


def verify_payload(levels, payload):
    rows = cube_layout()
    if len(levels) != 48 or len(payload) != 131232:
        raise ValueError("Expected six full eight-mip BC6 cube faces")
    for data, row in zip(levels, rows):
        start, length = row["offset"], row["bytes"]
        if len(data) != length or data != payload[start : start + length]:
            raise ValueError("Draw-time cube differs from DDS at " + str(row))
        row.update(sha256=hashlib.sha256(data).hexdigest(), dds_equal=True)
    return rows


def validate_view(view):
    if any(view.get(key) != value for key, value in EXPECTED_VIEW.items()):
        raise ValueError("Cube view contract mismatch: " + str(view))


def validate_sampler(sampler):
    if any(sampler.get(key) != value for key, value in EXPECTED_SAMPLER.items()):
        raise ValueError("Cube sampler contract mismatch: " + str(sampler))


def read_dds(path):
    data = Path(path).read_bytes()
    if len(data) != 131380 or hashlib.sha256(data).hexdigest() != DDS_SHA256:
        raise ValueError("Unreviewed cube DDS size/hash")
    fields = {
        o: struct.unpack_from("<I", data, o)[0]
        for o in (0, 4, 12, 16, 28, 84, 128, 132, 136, 140)
    }
    if fields != {
        0: 0x20534444,
        4: 124,
        12: 128,
        16: 128,
        28: 8,
        84: 0x30315844,
        128: 95,
        132: 3,
        136: 4,
        140: 1,
    }:
        raise ValueError("Expected DX10 BC6H_UF16 single complete cube")
    return data


def collect(rd, controller, dds):
    if controller.GetFrameInfo().frameNumber != 6411:
        raise ValueError("Requires frame6411")
    textures = {str(t.resourceId): t for t in controller.GetTextures()}
    texture = textures["ResourceId::14188"]
    if (
        texture.width,
        texture.height,
        texture.depth,
        texture.arraysize,
        texture.mips,
        texture.format.Name(),
    ) != (128, 128, 1, 6, 8, "BC6_UFLOAT"):
        raise ValueError("Unexpected native environment image")
    results = []
    for event, shader in ((835, 22255), (850, 37669)):
        controller.SetFrameEvent(event, True)
        state, stage = controller.GetPipelineState(), rd.ShaderStage.Pixel
        if str(state.GetShader(stage)) != "ResourceId::" + str(shader):
            raise ValueError("PS identity mismatch")
        reflection = state.GetShaderReflection(stage)
        candidates = []
        for used in state.GetReadOnlyResources(stage):
            record = binding(used, reflection.readOnlyResources)
            if (record["set"], record["binding"]) != (0, 45):
                continue
            descriptor = used.descriptor
            if str(descriptor.resource) != "ResourceId::14188":
                raise ValueError("Cube binding resource mismatch")
            view: dict = {
                "format": descriptor.format.Name(),
                "textureType": str(descriptor.textureType),
                "resource": str(descriptor.resource),
                "view": str(descriptor.view),
            }
            for field in (
                "firstMip",
                "numMips",
                "firstSlice",
                "numSlices",
                "minLODClamp",
            ):
                view[field] = getattr(descriptor, field)
            view["swizzle"] = [
                str(getattr(descriptor.swizzle, c))
                for c in ("red", "green", "blue", "alpha")
            ]
            validate_view(view)
            candidates.append(dict(record, view=view))
        if len(candidates) != 1:
            raise ValueError("Expected one native cube descriptor")
        samplers = []
        for used in state.GetSamplers(stage):
            record = binding(used, reflection.samplers)
            if (record["set"], record["binding"]) != (0, 6):
                continue
            resolved = controller.GetSamplerDescriptors(
                used.access.descriptorStore, [rd.DescriptorRange(used.access)]
            )
            if len(resolved) != 1 or resolved[0].type not in (
                rd.DescriptorType.Sampler,
                rd.DescriptorType.ImageSampler,
            ):
                raise ValueError("Unresolved environment sampler")
            sampler = sampler_record(resolved[0])
            validate_sampler(sampler)
            samplers.append(dict(record, sampler=sampler))
        if len(samplers) != 1:
            raise ValueError("Expected one cube sampler")
        levels = [
            bytes(
                controller.GetTextureData(
                    texture.resourceId, rd.Subresource(r["mip"], r["face"], 0)
                )
            )
            for r in cube_layout()
        ]
        rows = verify_payload(levels, dds[148:])
        samples = []
        for row in rows:
            w, mip, face = row["width"], row["mip"], row["face"]
            # Interior texel centers avoid cross-face bilinear footprints; w=1
            # necessarily shares cube seams and is verified separately by Load.
            for x, y in (
                (w // 4, w // 4),
                (w // 2, w // 2),
                (max(0, w * 3 // 4 - 1), max(0, w * 3 // 4 - 1)),
            ):
                picked = controller.PickPixel(
                    texture.resourceId,
                    x,
                    y,
                    rd.Subresource(mip, face, 0),
                    rd.CompType.Float,
                )
                samples.append(
                    {
                        "face": face,
                        "mip": mip,
                        "x": x,
                        "y": y,
                        "rgba": list(picked.floatValue),
                    }
                )
        results.append(
            {
                "event": event,
                "shader": shader,
                "shader_sha256": hashlib.sha256(bytes(reflection.rawBytes)).hexdigest(),
                "cube": candidates[0],
                "sampler": samplers[0],
                "levels": rows,
                "native_samples": samples,
            }
        )
    return results


def run():
    capture = Path(os.environ["ENDFIELD_CAPTURE_PATH"]).resolve()
    output = Path(os.environ["ENDFIELD_CAPTURE_OUTPUT"]).resolve()
    source = Path(os.environ["ENDFIELD_ENVIRONMENT_DDS"]).resolve()
    validate_paths(capture, output)
    write_new_json(
        output / "started.json", {"capture": str(capture), "dds": str(source)}
    )
    cap = controller = None
    try:
        try:
            import renderdoc as rd  # pyright: ignore[reportMissingImports]

            dds = read_dds(source)
            cap, controller = open_controller(rd, capture)
            results = collect(rd, controller, dds)
            with (output / "character-environment.dds").open("xb") as stream:
                stream.write(dds)
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
                "dds_sha256": DDS_SHA256,
                "events": results,
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
