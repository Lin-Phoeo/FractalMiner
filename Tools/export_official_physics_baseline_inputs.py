"""Sealed isolated getter/Line frames -> baseline/local-pose/root-depth inputs.

Source vertex slots preserved; render-only snapshot never becomes a proxy vertex.
No allocator/Job publication, Team/work-lists, game execution or Unity backend.
"""

import argparse
import hashlib
import json
import re
from dataclasses import asdict
from pathlib import Path
from typing import Any

from official_physics_angle_baseline import _integer
from official_physics_baseline_inputs import compose_baseline_inputs
from official_physics_initial_buffers import compose_fresh_bone_buffers

_IMPORT = (
    "explicit fresh empty ordinary BoneCloth import; unchanged unreduced skin order"
)
_OVERRIDE = (
    "explicit empty overrides for reconstructed reference only; not observed game state"
)
_TRIANGLE = "explicit zero-triangle Line reference; not observed game proxy"


def build_document(
    imports: dict[str, Any],
    frames: dict[str, Any],
    *,
    fresh_serial_no_resize: bool,
    cleared_output_buffers: bool,
) -> dict[str, Any]:
    if (
        fresh_serial_no_resize is not True
        or cleared_output_buffers is not True
        or any(
            type(doc["schema_version"]) is not int or doc["schema_version"] != 1
            for doc in (imports, frames)
        )
        or imports["full_proxy_inputs_generated"] is not False
        or frames["full_proxy_inputs_generated"] is not False
        or imports["getter_scope"] != frames["getter_scope"]
        or frames["import_context"] != _IMPORT
        or frames["override_context"] != _OVERRIDE
        or frames["triangle_context"] != _TRIANGLE
        or frames["line_frame_reference_generated"] is not True
        or frames["optimization_preserves_source_slots_on_selected_route"] is not True
        or frames["none_alignment_identity_caller_contract"] is not True
        or not imports["states"]
        or len(imports["states"]) != len(frames["states"])
    ):
        raise ValueError(
            "Require matching sealed reference route and explicit premises"
        )
    states, names = [], set()
    for imported, final in zip(imports["states"], frames["states"], strict=True):
        name = imported["name"]
        if (
            not isinstance(name, str)
            or not name
            or name in names
            or name != final["name"]
        ):
            raise ValueError("Require unique ordered reference state names")
        names.add(name)
        if not imported["groups"] or len(imported["groups"]) != len(final["groups"]):
            raise ValueError("Require complete ordered reference groups")
        groups, labels = [], set()
        for source, proxy in zip(imported["groups"], final["groups"], strict=True):
            label = source["name"]
            count = _integer(source["skin_bone_count"], 65535)
            if (
                not isinstance(label, str)
                or not label
                or label in labels
                or label != proxy["name"]
                or source["component_identity"] != proxy["component_identity"]
                or count != _integer(proxy["skin_bone_count"], 65535)
                or any(
                    len(source[key]) != count + 1
                    for key in (
                        "snapshots",
                        "runtime_instance_ids",
                        "runtime_parent_ids",
                    )
                )
            ):
                raise ValueError("Require matched identity, count and render snapshot")
            labels.add(label)
            checked = compose_fresh_bone_buffers(
                proxy["proxy_attributes"], count + 1, count, fresh_import=True
            )
            if (
                len(checked.proxy_attributes) != count
                or tuple(_integer(i, 65535) for i in proxy["source_vertex_indices"])
                != checked.skin_transform_indices
                or tuple(_integer(f, 255) for f in proxy["transform_flags"])
                != checked.transform_flags
            ):
                raise ValueError(
                    "Reference attributes/flags or skin source slots changed"
                )
            source_frames = source["vertices"]["frames"]
            result = compose_baseline_inputs(
                source["runtime_instance_ids"][:count],
                source["runtime_parent_ids"][:count],
                source["runtime_root_ids"],
                checked.proxy_attributes,
                tuple(tuple(v) for v in source_frames["positions"]),
                tuple(tuple(v) for v in source_frames["normals"]),
                tuple(tuple(v) for v in source_frames["tangents"]),
                fresh_serial_no_resize=fresh_serial_no_resize,
                cleared_output_buffers=cleared_output_buffers,
            )
            groups.append(
                dict(
                    name=label,
                    component_identity=source["component_identity"],
                    skin_bone_count=count,
                    source_vertex_indices=checked.skin_transform_indices,
                    proxy_attributes=checked.proxy_attributes,
                    transform_flags=checked.transform_flags,
                    **asdict(result),
                )
            )
        states.append({"name": name, "groups": groups})
    return {
        "schema_version": 1,
        "getter_scope": imports["getter_scope"],
        "import_context": _IMPORT,
        "override_context": _OVERRIDE,
        "triangle_context": _TRIANGLE,
        "child_map_context": "explicit fresh empty serial map; capacity 3*n; at most n inserts; no resize",
        "output_buffer_context": "fresh NativeArray ClearMemory1; unlisted quaternion zero, not identity",
        "states": states,
        "baseline_reference_generated": True,
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
    output: Path,
    seals: tuple[str, ...],
    *,
    fresh_serial_no_resize: bool,
    cleared_output_buffers: bool,
) -> None:
    if len(seals) != 2 or any(
        re.fullmatch(r"[0-9a-f]{64}", seal) is None for seal in seals
    ):
        raise ValueError("Require two explicit SHA256 seals")
    if output.exists():
        raise FileExistsError(f"Refusing to overwrite {output}")
    raw = tuple(path.read_bytes() for path in (imports, frames))
    if any(
        hashlib.sha256(data).hexdigest() != seal
        for data, seal in zip(raw, seals, strict=True)
    ):
        raise ValueError("Reference input differs from explicit seal")
    docs = tuple(json.loads(data) for data in raw)
    if docs[1].get("input_sha256", {}).get("imports") != seals[0]:
        raise ValueError("Line frame provenance refers to a different getter import")
    result = build_document(
        *docs,
        fresh_serial_no_resize=fresh_serial_no_resize,
        cleared_output_buffers=cleared_output_buffers,
    )
    result["input_sha256"] = dict(zip(("imports", "frames"), seals, strict=True))
    with output.open("x", encoding="utf-8", newline="\n") as stream:
        json.dump(result, stream, ensure_ascii=False, indent=2, allow_nan=False)
        stream.write("\n")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ("imports", "frames"):
        parser.add_argument("--" + name, type=Path, required=True)
        parser.add_argument("--" + name + "-sha256", required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--fresh-serial-no-resize", action="store_true", required=True)
    parser.add_argument("--cleared-output-buffers", action="store_true", required=True)
    args = parser.parse_args()
    export_file(
        args.imports,
        args.frames,
        args.output,
        (args.imports_sha256, args.frames_sha256),
        fresh_serial_no_resize=args.fresh_serial_no_resize,
        cleared_output_buffers=args.cleared_output_buffers,
    )
    print(f"Baseline reference exported: {args.output}")


if __name__ == "__main__":
    main()
