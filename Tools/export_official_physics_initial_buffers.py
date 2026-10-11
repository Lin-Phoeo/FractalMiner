"""Sealed Line match inputs -> explicit fresh BoneCloth attribute/flag composition.

Only fresh/unreduced/source-order stage, NOT optimized final proxy, Team or solver.
Empty runtime overrides remain an explicit reference premise, not game evidence.
"""

import argparse
import hashlib
import json
import re
from dataclasses import asdict
from pathlib import Path
from typing import Any

from official_physics_angle_baseline import _integer
from official_physics_initial_buffers import compose_fresh_bone_buffers

_OVERRIDE_PREMISE = (
    "explicit empty overrides for reconstructed reference only; not observed game state"
)


def build_document(matched: dict[str, Any], *, fresh_import: bool) -> dict[str, Any]:
    if (
        type(matched["schema_version"]) is not int
        or matched["schema_version"] != 1
        or matched["matched_selection_bytes_generated"] is not True
        or matched["full_proxy_attributes_generated"] is not False
        or matched["override_context"] != _OVERRIDE_PREMISE
        or not matched["states"]
    ):
        raise ValueError(
            "Require sealed Line matching producer with explicit reference context"
        )
    states, labels, order = [], set(), None
    for state in matched["states"]:
        name = state["name"]
        if (
            not isinstance(name, str)
            or not name
            or name in labels
            or not state["groups"]
        ):
            raise ValueError("Require nonempty unique states and groups")
        labels.add(name)
        groups, identities, group_names = [], [], set()
        for group in state["groups"]:
            group_name = group["name"]
            if (
                not isinstance(group_name, str)
                or not group_name
                or group_name in group_names
            ):
                raise ValueError("Require unique nonempty group labels within state")
            group_names.add(group_name)
            count = _integer(group["skin_bone_count"], 65535)
            if len(group["matched_selection_bytes"]) != count:
                raise ValueError("Matched vertex bytes differ from source skin window")
            buffers = compose_fresh_bone_buffers(
                group["matched_selection_bytes"],
                count + 1,
                count,
                fresh_import=fresh_import,
            )
            identities.append((group_name, group["component_identity"], count))
            groups.append(
                dict(
                    name=group_name,
                    component_identity=group["component_identity"],
                    skin_bone_count=count,
                    render_transform_index=count,
                    **asdict(buffers),
                )
            )
        if order is not None and identities != order:
            raise ValueError(
                "Group identity/order/count differs across reference states"
            )
        order = identities
        states.append({"name": name, "groups": groups})
    return {
        "schema_version": 1,
        "getter_scope": matched["getter_scope"],
        "override_context": _OVERRIDE_PREMISE,
        "import_context": "explicit fresh empty ordinary BoneCloth import; unchanged unreduced skin order",
        "states": states,
        "initial_proxy_bytes_generated": True,
        "initial_transform_flags_generated": True,
        "preoptimization_attributes_and_flags_composed": True,
        "full_proxy_inputs_generated": False,
        "runtime_overrides_observed": False,
        "optimized_proxy_generated": False,
        "normal_axis_consumed": False,
        "native_arrays_published": False,
        "official_solver_integrated": False,
        "original_runtime_executed": False,
        "stage_modified": False,
    }


def export_file(
    source: Path, output: Path, source_sha256: str, *, fresh_import: bool
) -> None:
    if fresh_import is not True or re.fullmatch(r"[0-9a-f]{64}", source_sha256) is None:
        raise ValueError(
            "Require source seal and explicit fresh-import reference premise"
        )
    if output.exists():
        raise FileExistsError(f"Refusing to overwrite {output}")
    raw = source.read_bytes()
    if hashlib.sha256(raw).hexdigest() != source_sha256:
        raise ValueError("Matched input differs from explicit source seal")
    document = build_document(json.loads(raw), fresh_import=fresh_import)
    document["matched_input_sha256"] = source_sha256
    with output.open("x", encoding="utf-8", newline="\n") as stream:
        json.dump(document, stream, ensure_ascii=False, indent=2, allow_nan=False)
        stream.write("\n")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ("matched-input", "output"):
        parser.add_argument("--" + name, type=Path, required=True)
    parser.add_argument("--matched-sha256", required=True)
    parser.add_argument("--fresh-ordinary-import", action="store_true", required=True)
    args = parser.parse_args()
    export_file(
        args.matched_input,
        args.output,
        args.matched_sha256,
        fresh_import=args.fresh_ordinary_import,
    )
    print(f"Fresh BoneCloth attribute and flag reference exported: {args.output}")


if __name__ == "__main__":
    main()
