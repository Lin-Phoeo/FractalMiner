"""Offline raw global light selection inputs for six already-reviewed actual PS.

Reuse the material audit's pinned source identities and packoffset parser.
Names require identical full block layouts; only six reviewed float4 fields
are approved here. Neither this labeling nor a captured CP weight of one is
a certificate for weather, shadow producers, or whole-program equivalence.
"""

import os
import sys
import traceback
from pathlib import Path
from typing import cast

sys.path.insert(
    0, os.environ.get("ENDFIELD_TOOLS_PATH") or str(Path(__file__).resolve().parent)
)
from capture_material_uniforms import decode, layout, sha
from capture_material_uniforms import prepare as material_prepare
from capture_replay_inventory import open_controller, validate_paths, write_new_json
from extract_front_frame_constants import parse_hlsl

FIELDS = {
    14: (
        "_LightDataBuffer_DirectionalLightDirection",
        "_LightDataBuffer_DirectionalLightCustomData1",
    ),
    16: ("_CharacterParams1", "_CharacterParams11", "_CharacterParams12"),
}


def block(path, binding):
    blocks = [
        b
        for b in cast(dict, parse_hlsl(str(path))["cbuffers"]).values()
        if b["space"] == 0 and b["binding"] == binding
    ]
    if len(blocks) != 1:
        raise ValueError("Unique global block required")
    return blocks[0]


def prepare(project):
    result = material_prepare(project)
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
        for binding, names in FIELDS.items():
            if binding == 16:
                names = names + (
                    (
                        "_CharacterParams4"
                        if spec["event"] in (786, 860)
                        else "_CharacterParams5"
                    ),
                )
            a, n = block(actual, binding), block(named, binding)
            if a["size"] != n["size"] or layout(a["members"]) != layout(n["members"]):
                raise ValueError("Global layout differs")
            pairs = [
                (aa, nn)
                for aa, nn in zip(a["members"], n["members"])
                if nn["name"] in names
            ]
            if len(pairs) != len(names) or {nn["name"] for aa, nn in pairs} != set(
                names
            ):
                raise ValueError("Reviewed fields missing/duplicated")
            blocks.append(
                {
                    "binding": binding,
                    "bytes": a["size"],
                    "actual": [aa for aa, nn in pairs],
                    "named": [nn for aa, nn in pairs],
                    "body": spec["body"],
                }
            )
        spec["blocks"] = blocks
    return result


def collect(rd, controller, output, plan):
    if controller.GetFrameInfo().frameNumber != 6411:
        raise ValueError("Requires frame6411")
    records = []
    for spec in plan:
        controller.SetFrameEvent(spec["event"], True)
        state, stage = controller.GetPipelineState(), rd.ShaderStage.Pixel
        reflection = state.GetShaderReflection(stage)
        if (
            str(state.GetShader(stage)) != "ResourceId::" + str(spec["program"])
            or sha(bytes(reflection.rawBytes)) != spec["shader_sha256"]
        ):
            raise ValueError("Actual PS changed")
        records_blocks = []
        for b in spec["blocks"]:
            blocks = [
                (i, cb)
                for i, cb in enumerate(reflection.constantBlocks)
                if cb.fixedBindNumber == b["binding"] and cb.fixedBindSetOrSpace == 0
            ]
            if len(blocks) != 1 or blocks[0][1].byteSize != b["bytes"]:
                raise ValueError("Unexpected global block/range")
            descriptor = state.GetConstantBlock(stage, blocks[0][0], 0).descriptor
            if descriptor.byteOffset < 0 or descriptor.byteSize < b["bytes"]:
                raise ValueError("Truncated global descriptor")
            payload = bytes(
                controller.GetBufferData(
                    descriptor.resource, descriptor.byteOffset, b["bytes"]
                )
            )
            if len(payload) != b["bytes"]:
                raise ValueError("Truncated global payload")
            uniforms = decode(payload, b["actual"], b["named"], b["body"])
            filename = str(spec["event"]) + "-b" + str(b["binding"]) + ".raw"
            with (output / filename).open("xb") as stream:
                stream.write(payload)
            records_blocks.append(
                {
                    "binding": b["binding"],
                    "bytes": b["bytes"],
                    "file": filename,
                    "sha256": sha(payload),
                    "resource": str(descriptor.resource),
                    "byte_offset": descriptor.byteOffset,
                    "uniforms": uniforms,
                }
            )
        record = {
            k: v
            for k, v in spec.items()
            if k not in ("actual", "named", "body", "blocks", "bytes")
        }
        record["blocks"] = records_blocks
        records.append(record)
    return records


def run(
    prepare_plan=None,
    schema="endfield-character-light-selection-v1",
    scope=None,
    collect_records=None,
):
    project = Path(os.environ["ENDFIELD_TOOLS_PATH"]).parent
    capture, output = (
        Path(os.environ["ENDFIELD_CAPTURE_PATH"]),
        Path(os.environ["ENDFIELD_CAPTURE_OUTPUT"]),
    )
    validate_paths(capture, output)
    cap = controller = None
    try:
        plan = prepare(project) if prepare_plan is None else prepare_plan(project)
        try:
            import renderdoc as rd  # pyright: ignore[reportMissingImports]

            cap, controller = open_controller(rd, capture)
            records = (collect if collect_records is None else collect_records)(
                rd, controller, output, plan
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
                "schema": schema,
                "records": records,
                "scope": scope
                or "six reviewed float4 global inputs per draw only; no whole-render/weather certificate",
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
