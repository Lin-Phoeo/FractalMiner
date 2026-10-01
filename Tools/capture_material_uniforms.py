"""Offline raw UPM + explicitly reviewed offset/type labels, not variant scoring.

Uses the existing packoffset parser; no old union-name extraction or material
asset edits. Actual SPV/HLSL and named candidate hashes are required. Matching
layout permits labels only, never certifies whole-program equivalence/weather.
"""

import hashlib
import json
import math
import os
import re
import struct
import sys
import traceback
from pathlib import Path
from typing import cast

sys.path.insert(
    0, os.environ.get("ENDFIELD_TOOLS_PATH") or str(Path(__file__).resolve().parent)
)
from capture_replay_inventory import open_controller, validate_paths, write_new_json
from extract_front_frame_constants import parse_hlsl

PROVENANCE_SHA256 = "a6f177b4cfc56a24abd4f4560efe083bee50291181fda27be331e76f43c1a2ec"
SOURCES = (
    (
        776,
        22259,
        "iris",
        "characternpr_eye",
        28,
        "8496d455a64622f87ebbc1649de32a35946e52662679db6205349a9149b53671",
    ),
    (
        786,
        22250,
        "body",
        "characternpr_skin",
        114,
        "f6d39cd116f95eaa35a129e9da84a8258efa0502ef39479461b46ecb371012e0",
    ),
    (
        835,
        22255,
        "cloth_01",
        "characternpr",
        471,
        "0f449421ac189205b40978788a25dde7709e74a27d17756087a437497d48b19d",
    ),
    (
        850,
        37669,
        "cloth_02",
        "characternpr",
        472,
        "9079206b4a5da702773a0c789452c0f48c4e8538e522a00167180dccb5d72521",
    ),
    (
        860,
        37671,
        "face",
        "characternpr_skin",
        138,
        "8485341ac6de9e45e2ef25791f2d17bf975b8b567913fe740950307376cade7d",
    ),
    (
        875,
        22257,
        "hair",
        "characternpr_hair",
        126,
        "abc21b605de1fe108bed9473c69056abc996ce553357eecfbc467ea4500b7e43",
    ),
)


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


def layout(members):
    return [
        (m["offset"], m["type"], m["size"], m["count"], m["major"]) for m in members
    ]


def decode(raw, actual, named, body):
    if layout(actual) != layout(named):
        raise ValueError("Actual/named member layout differs")
    tokens = set(re.findall(r"\b\w+\b", body))
    records = []
    for source, reference in zip(actual, named):
        kind, size, offset = source["type"], source["size"], source["offset"]
        if (
            source["count"] is not None
            or source["major"] is not None
            or kind not in ("float", "float2", "float3", "float4")
        ):
            raise ValueError("Unreviewed UPM type")
        if size is None or offset < 0 or offset + size > len(raw):
            raise ValueError("Truncated UPM range")
        values = list(struct.unpack_from("<" + "f" * (size // 4), raw, offset))
        if not all(math.isfinite(x) for x in values):
            raise ValueError("Nonfinite UPM")
        records.append(
            {
                "name": reference["name"],
                "source": source["name"],
                "offset": offset,
                "type": kind,
                "active": source["name"] in tokens,
                "named": "Stripped" not in reference["name"],
                "value": values,
            }
        )
    return records


def material_block(path):
    blocks = [
        b
        for b in cast(dict, parse_hlsl(str(path))["cbuffers"]).values()
        if b["space"] == 1 and b["binding"] == 0
    ]
    if len(blocks) != 1:
        raise ValueError("Single set1/b0 UPM required")
    return blocks[0]


def prepare(project):
    provenance_path = (
        project / "Validation/draw-program-audit-20260930-01/export-provenance.json"
    )
    raw = provenance_path.read_bytes()
    if sha(raw) != PROVENANCE_SHA256:
        raise ValueError("Source provenance changed")
    provenance = json.loads(raw)
    base = (
        project
        / "_dump_1.5.3/AllShader_1.5.3/Assets/packages/com.hg.render-pipelines/runtime/shaders/materials/characternpr"
    )
    result = []
    for event, program, part, family, variant, reference_hash in SOURCES:
        candidates = [
            r
            for r in provenance["programs"]
            if r["event"] == event and r["stage"] == "fragment"
        ]
        if len(candidates) != 1 or candidates[0]["shader"] != "ResourceId::" + str(
            program
        ):
            raise ValueError("Actual source identity differs")
        source = candidates[0]
        actual_path = project / source["hlsl"]
        named_path = base / family / ("Sub0_Pass0_Fragment_b" + str(variant) + ".hlsl")
        actual_bytes, named_bytes = actual_path.read_bytes(), named_path.read_bytes()
        if (
            sha(actual_bytes) != source["hlsl_sha256"]
            or sha(named_bytes) != reference_hash
        ):
            raise ValueError("Actual/named shader bytes changed")
        actual, named = material_block(actual_path), material_block(named_path)
        if actual["size"] != named["size"] or layout(actual["members"]) != layout(
            named["members"]
        ):
            raise ValueError("UPM layout differs; cannot reuse labels")
        text = actual_bytes.decode("utf-8-sig")
        body = re.sub(r"cbuffer\s+\w+[^{}]*\{.*?\};", "", text, flags=re.DOTALL)
        result.append(
            {
                "event": event,
                "program": program,
                "material": "M_actor_typhoea_" + part + "_01"
                if part not in ("cloth_01", "cloth_02")
                else "M_actor_typhoea_" + part,
                "bytes": actual["size"],
                "actual": actual["members"],
                "named": named["members"],
                "body": body,
                "shader_sha256": source["spv_sha256"],
                "actual_hlsl_sha256": source["hlsl_sha256"],
                "reference_sha256": reference_hash,
                "reference": str(named_path.relative_to(project)).replace("\\", "/"),
            }
        )
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
        blocks = [
            (i, b)
            for i, b in enumerate(reflection.constantBlocks)
            if b.fixedBindNumber == 0 and b.fixedBindSetOrSpace == 1
        ]
        if len(blocks) != 1 or blocks[0][1].byteSize != spec["bytes"]:
            raise ValueError("Unexpected UPM block/range")
        descriptor = state.GetConstantBlock(stage, blocks[0][0], 0).descriptor
        if descriptor.byteOffset < 0 or descriptor.byteSize < spec["bytes"]:
            raise ValueError("Truncated UPM descriptor")
        payload = bytes(
            controller.GetBufferData(
                descriptor.resource, descriptor.byteOffset, spec["bytes"]
            )
        )
        if len(payload) != spec["bytes"]:
            raise ValueError("Truncated UPM payload")
        uniforms = decode(payload, spec["actual"], spec["named"], spec["body"])
        filename = str(spec["event"]) + "-upm.raw"
        with (output / filename).open("xb") as stream:
            stream.write(payload)
        record = {k: v for k, v in spec.items() if k not in ("actual", "named", "body")}
        record.update(
            file=filename,
            sha256=sha(payload),
            resource=str(descriptor.resource),
            byte_offset=descriptor.byteOffset,
            uniforms=uniforms,
        )
        records.append(record)
    return records


def run():
    project = Path(os.environ["ENDFIELD_TOOLS_PATH"]).parent
    capture, output = (
        Path(os.environ["ENDFIELD_CAPTURE_PATH"]),
        Path(os.environ["ENDFIELD_CAPTURE_OUTPUT"]),
    )
    validate_paths(capture, output)
    cap = controller = None
    try:
        plan = prepare(project)
        try:
            import renderdoc as rd  # pyright: ignore[reportMissingImports]

            cap, controller = open_controller(rd, capture)
            records = collect(rd, controller, output, plan)
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
                "schema": "endfield-upm-audit-v1",
                "records": records,
                "scope": "raw material bytes and explicit offset/type labels; no whole-program equivalence or weather certificate",
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
