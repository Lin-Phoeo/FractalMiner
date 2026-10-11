"""Sealed reference imports and attributes -> bounded Line proxy frame outputs.

Explicit zero-triangle Line reference premise, not observed game topology.
None identity is a caller contract, not proof of generic FillJob actual writes.
No final proxy topology/work-lists, normalAxis solver consumption or Unity.
"""

import argparse
import hashlib
import json
import re
from dataclasses import asdict
from pathlib import Path
from typing import Any

from export_official_physics_line_inputs import _serialized_bool
from official_physics_angle_baseline import _integer
from official_physics_angle_cache import quaternion_inverse
from official_physics_initial_buffers import compose_fresh_bone_buffers
from official_physics_line_frames import compose_line_proxy_frames

_IMPORT = (
    "explicit fresh empty ordinary BoneCloth import; unchanged unreduced skin order"
)
_OVERRIDE = (
    "explicit empty overrides for reconstructed reference only; not observed game state"
)


def build_document(
    imports: dict[str, Any],
    buffers: dict[str, Any],
    config: dict[str, Any],
    *,
    zero_triangle_line: bool,
) -> dict[str, Any]:
    if (
        zero_triangle_line is not True
        or any(
            type(doc["schema_version"]) is not int or doc["schema_version"] != 1
            for doc in (imports, buffers)
        )
        or imports["full_proxy_inputs_generated"] is not False
        or imports["getter_scope"] != buffers["getter_scope"]
        or buffers["preoptimization_attributes_and_flags_composed"] is not True
        or buffers["import_context"] != _IMPORT
        or buffers["override_context"] != _OVERRIDE
        or not imports["states"]
        or len(imports["states"]) != len(buffers["states"])
    ):
        raise ValueError(
            "Require sealed matching reference provenance and zero-triangle premise"
        )
    states, names = [], set()
    for imported, initial in zip(imports["states"], buffers["states"], strict=True):
        name = imported["name"]
        if (
            not isinstance(name, str)
            or not name
            or name in names
            or name != initial["name"]
        ):
            raise ValueError("Require unique matching reference states")
        names.add(name)
        groups, group_names = [], set()
        if not imported["groups"] or not (
            len(imported["groups"]) == len(initial["groups"]) == len(config["groups"])
        ):
            raise ValueError("Require complete matching ordered groups")
        for source, attr, saved in zip(
            imported["groups"], initial["groups"], config["groups"], strict=True
        ):
            label = source["name"]
            count = _integer(source["skin_bone_count"], 65535)
            if (
                not isinstance(label, str)
                or not label
                or label in group_names
                or label != attr["name"]
                or label != saved["boneClothName"]
                or source["component_identity"] != attr["component_identity"]
                or count != _integer(attr["skin_bone_count"], 65535)
                or len(source["snapshots"]) != count + 1
            ):
                raise ValueError(
                    "Require matched identity, count, source order and render snapshot"
                )
            group_names.add(label)
            checked = compose_fresh_bone_buffers(
                attr["proxy_attributes"], count + 1, count, fresh_import=True
            )
            if (
                len(checked.proxy_attributes) != count
                or tuple(_integer(i, 65535) for i in attr["skin_transform_indices"])
                != checked.skin_transform_indices
                or tuple(_integer(f, 255) for f in attr["transform_flags"])
                != checked.transform_flags
            ):
                raise ValueError(
                    "Fresh attribute/flag mapping differs from sealed route"
                )
            data = saved["boneClothData"]
            if _serialized_bool(data["customSkinningSetting"]["enable"]):
                raise ValueError("Custom skinning route is not restored")
            frames = source["vertices"]["frames"]
            if len(frames["positions"]) != count:
                raise ValueError("Imported skin frame count differs")
            result = compose_line_proxy_frames(
                tuple(tuple(v) for v in frames["positions"]),
                tuple(tuple(v) for v in frames["normals"]),
                tuple(tuple(v) for v in frames["tangents"]),
                tuple(tuple(s["rotation"]) for s in source["snapshots"][:count]),
                quaternion_inverse(tuple(source["snapshots"][count]["rotation"])),
                cloth_type=data["clothType"],
                connect_mode=data["connectionMode"],
                triangle_count=0,
                alignment_mode=data["normalAlignmentSetting"]["alignmentMode"],
            )
            groups.append(
                dict(
                    name=label,
                    component_identity=source["component_identity"],
                    skin_bone_count=count,
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
        "triangle_context": "explicit zero-triangle Line reference; not observed game proxy",
        "states": states,
        "line_frame_reference_generated": True,
        "optimization_preserves_source_slots_on_selected_route": True,
        "none_alignment_identity_caller_contract": True,
        "generic_fill_actual_writes_proved": False,
        "full_proxy_inputs_generated": False,
        "native_arrays_published": False,
        "official_solver_integrated": False,
        "original_runtime_executed": False,
        "runtime_overrides_observed": False,
        "stage_modified": False,
    }


def export_file(
    imports: Path,
    buffers: Path,
    config: Path,
    output: Path,
    seals: tuple[str, ...],
    *,
    zero_triangle_line: bool,
) -> None:
    if len(seals) != 3 or any(
        re.fullmatch(r"[0-9a-f]{64}", seal) is None for seal in seals
    ):
        raise ValueError("Require three explicit SHA256 seals")
    if output.exists():
        raise FileExistsError(f"Refusing to overwrite {output}")
    raw = tuple(path.read_bytes() for path in (imports, buffers, config))
    if any(
        hashlib.sha256(data).hexdigest() != seal
        for data, seal in zip(raw, seals, strict=True)
    ):
        raise ValueError("Reference input differs from explicit seal")
    result = build_document(
        *(json.loads(data) for data in raw), zero_triangle_line=zero_triangle_line
    )
    result["input_sha256"] = dict(
        zip(("imports", "buffers", "config"), seals, strict=True)
    )
    with output.open("x", encoding="utf-8", newline="\n") as stream:
        json.dump(result, stream, ensure_ascii=False, indent=2, allow_nan=False)
        stream.write("\n")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ("imports", "buffers", "config"):
        parser.add_argument("--" + name, type=Path, required=True)
        parser.add_argument("--" + name + "-sha256", required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--zero-triangle-line", action="store_true", required=True)
    args = parser.parse_args()
    export_file(
        args.imports,
        args.buffers,
        args.config,
        args.output,
        (args.imports_sha256, args.buffers_sha256, args.config_sha256),
        zero_triangle_line=args.zero_triangle_line,
    )
    print(f"Line frame reference exported: {args.output}")


if __name__ == "__main__":
    main()
