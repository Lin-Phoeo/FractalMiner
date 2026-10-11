"""Sealed getter/Line frames/baselines -> local graph and Distance cache.

No Team IDs, allocator chunks, clock flags or actual work-lists are invented.
Original positions are imported render-local frames, not baseline local poses.
"""

import argparse
import hashlib
import json
import re
from dataclasses import asdict
from pathlib import Path
from typing import Any

from export_official_physics_baseline_inputs import build_document as build_baselines
from official_physics_distance_inputs import (
    build_distance_inputs,
    build_line_connectivity,
)
from official_physics_line_inputs import build_bone_lines


def build_document(
    imports: dict[str, Any],
    frames: dict[str, Any],
    baselines: dict[str, Any],
    *,
    fresh_serial_no_resize: bool,
    cleared_output_buffers: bool,
) -> dict[str, Any]:
    expected = build_baselines(
        imports,
        frames,
        fresh_serial_no_resize=fresh_serial_no_resize,
        cleared_output_buffers=cleared_output_buffers,
    )
    # Compare the FULL producer document, not only convenient identity fields.
    # JSON canonicalization reconciles in-memory tuples with sealed JSON arrays.
    actual = {k: v for k, v in baselines.items() if k != "input_sha256"}
    if type(baselines.get("schema_version")) is not int or json.dumps(
        actual, sort_keys=True, allow_nan=False
    ) != json.dumps(expected, sort_keys=True, allow_nan=False):
        raise ValueError("Baseline producer output/route differs from sealed imports")
    states = []
    for source_state, baseline_state in zip(
        imports["states"], baselines["states"], strict=True
    ):
        groups = []
        for source, group in zip(
            source_state["groups"], baseline_state["groups"], strict=True
        ):
            lines = build_bone_lines(group["parents"], 0)
            graph = build_line_connectivity(
                group["skin_bone_count"],
                lines,
                fresh_serial_no_resize=fresh_serial_no_resize,
            )
            distances = build_distance_inputs(
                source["vertices"]["frames"]["positions"],
                group["parents"],
                group["proxy_attributes"],
                graph.rows,
                fresh_serial_no_resize=fresh_serial_no_resize,
                zero_triangle_edge_map=True,
            )
            groups.append(
                {
                    "name": group["name"],
                    "component_identity": group["component_identity"],
                    "skin_bone_count": group["skin_bone_count"],
                    "source_vertex_indices": group["source_vertex_indices"],
                    "proxy_attributes": group["proxy_attributes"],
                    "transform_flags": group["transform_flags"],
                    "parents": group["parents"],
                    "lines": lines,
                    "connectivity": asdict(graph),
                    "distance": asdict(distances),
                }
            )
        states.append({"name": source_state["name"], "groups": groups})
    return {
        "schema_version": 1,
        "getter_scope": expected["getter_scope"],
        "import_context": expected["import_context"],
        "override_context": expected["override_context"],
        "triangle_context": expected["triangle_context"],
        "graph_context": "fresh empty serial UniqueAdd map capacity4*n; head-chain row publication",
        "conversion_context": "fresh map capacity=dataLength; serial per-key packed-row Add",
        "distance_context": "fresh positive/negative maps each capacity2*n; created-empty triangle map; Single rest length",
        "states": states,
        "distance_reference_generated": True,
        "full_proxy_inputs_generated": False,
        "real_constraint_work_lists_generated": False,
        "native_arrays_published": False,
        "official_solver_integrated": False,
        "original_runtime_executed": False,
        "runtime_overrides_observed": False,
        "stage_modified": False,
    }


def export_file(
    imports: Path,
    frames: Path,
    baselines: Path,
    output: Path,
    seals: tuple[str, ...],
    *,
    fresh_serial_no_resize: bool,
    cleared_output_buffers: bool,
) -> None:
    names = ("imports", "frames", "baselines")
    if len(seals) != 3 or any(re.fullmatch(r"[0-9a-f]{64}", s) is None for s in seals):
        raise ValueError("Require three explicit SHA256 seals")
    if output.exists():
        raise FileExistsError(f"Refusing to overwrite {output}")
    raw = tuple(p.read_bytes() for p in (imports, frames, baselines))
    if any(hashlib.sha256(b).hexdigest() != s for b, s in zip(raw, seals, strict=True)):
        raise ValueError("Reference input differs from explicit seal")
    docs = tuple(json.loads(b) for b in raw)
    if docs[1].get("input_sha256", {}).get("imports") != seals[0] or docs[2].get(
        "input_sha256"
    ) != dict(zip(names[:2], seals[:2], strict=True)):
        raise ValueError("Nested reference provenance refers to different inputs")
    result = build_document(
        *docs,
        fresh_serial_no_resize=fresh_serial_no_resize,
        cleared_output_buffers=cleared_output_buffers,
    )
    result["input_sha256"] = dict(zip(names, seals, strict=True))
    with output.open("x", encoding="utf-8", newline="\n") as stream:
        json.dump(result, stream, ensure_ascii=False, indent=2, allow_nan=False)
        stream.write("\n")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ("imports", "frames", "baselines"):
        parser.add_argument("--" + name, type=Path, required=True)
        parser.add_argument("--" + name + "-sha256", required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--fresh-serial-no-resize", action="store_true", required=True)
    parser.add_argument("--cleared-output-buffers", action="store_true", required=True)
    args = parser.parse_args()
    export_file(
        args.imports,
        args.frames,
        args.baselines,
        args.output,
        (args.imports_sha256, args.frames_sha256, args.baselines_sha256),
        fresh_serial_no_resize=args.fresh_serial_no_resize,
        cleared_output_buffers=args.cleared_output_buffers,
    )
    print(f"Distance reference exported: {args.output}")


if __name__ == "__main__":
    main()
