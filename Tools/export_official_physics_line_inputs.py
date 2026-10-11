"""Sealed reference getter + valid saved selection -> ordinary Line match inputs.

Supports BoneCloth=1, connectionMode=Line(0), zero reduction, unchanged slot
order only. Output is matched selection bytes, NOT old proxy OR/Transform flags.
No runtime dictionary overrides, game build route, Team or solver are observed.
"""

import argparse
import hashlib
import json
import re
from collections.abc import Mapping, Sequence
from dataclasses import asdict
from pathlib import Path
from typing import Any

from export_official_physics_getter_inputs import build_document as import_getters
from export_official_physics_identity_inputs import build_document as import_identities
from official_physics_angle_baseline import _integer
from official_physics_constraints import _single
from official_physics_line_inputs import match_saved_line_selection
from official_physics_saved_selection import SavedSelection


def _serialized_bool(value: Any) -> bool:
    # Reviewed SceneProbe JSON preserves serialized Boolean fields as Int32 0/1.
    # Do not accept arbitrary truthiness, strings, floats or non-binary integers.
    if type(value) is bool:
        return value
    if type(value) is int and value in (0, 1):
        return value == 1
    raise ValueError("Require serialized Boolean or SceneProbe integer 0/1")


def _serialized_attribute(value: Any) -> int:
    if type(value) is dict:
        if set(value) != {"Value"}:
            raise ValueError("Require exact serialized VertexAttribute Value wrapper")
        value = value["Value"]
    return _integer(value, 255)


def build_document(
    bindings: dict[str, Any],
    config: dict[str, Any],
    capture: dict[str, Any],
    bindings_sha256: str,
    *,
    resolved_overrides: Mapping[str, Sequence[tuple[int, int]]],
) -> dict[str, Any]:
    identities = import_identities(bindings)
    imports = import_getters(bindings, capture, bindings_sha256)
    groups = config["groups"]
    names = {group["name"] for group in identities["groups"]}
    if len(groups) != len(names) or resolved_overrides.keys() != names:
        raise ValueError(
            "Require complete ordered config and explicit per-group overrides"
        )
    for saved, identity in zip(groups, identities["groups"], strict=True):
        if saved["boneClothName"] != identity["name"]:
            raise ValueError("Configuration group order differs from reviewed bindings")
        data = saved["boneClothData"]
        if type(data["clothType"]) is not int or data["clothType"] != 1:
            raise ValueError(
                "Producer supports ordinary BoneCloth only, not BoneSpring"
            )
        if type(data["connectionMode"]) is not int or data["connectionMode"] != 0:
            raise ValueError("Producer supports Line mode only")
        reduction = data["reductionSetting"]
        if any(
            _single(reduction[key]) != 0 for key in ("simpleDistance", "shapeDistance")
        ):
            raise ValueError("Producer excludes reduced/reordered proxy inputs")
    states = []
    for state in imports["states"]:
        outputs = []
        for imported, identity, saved in zip(
            state["groups"], identities["groups"], groups, strict=True
        ):
            selection = saved["selectionData"]
            positions = tuple(
                tuple(point[axis] for axis in "xyz") for point in selection["positions"]
            )
            value = SavedSelection(
                positions,
                tuple(
                    _serialized_attribute(value) for value in selection["attributes"]
                ),
                selection["maxConnectionDistance"],
                _serialized_bool(selection["userEdit"]),
            )
            inputs = match_saved_line_selection(
                imported["vertices"]["frames"]["positions"],
                identity["skin_parent_indices"],
                value,
                resolved_bone_overrides=resolved_overrides[identity["name"]],
            )
            outputs.append(
                dict(
                    name=identity["name"],
                    component_identity=identity["component_identity"],
                    skin_bone_count=identity["skin_bone_count"],
                    **asdict(inputs),
                )
            )
        states.append({"name": state["name"], "groups": outputs})
    return {
        "schema_version": 1,
        "getter_scope": imports["getter_scope"],
        "states": states,
        "matched_selection_bytes_generated": True,
        "full_proxy_attributes_generated": False,
        "initial_proxy_bytes_or_transform_flags_generated": False,
        "runtime_overrides_observed": False,
        "full_proxy_inputs_generated": False,
        "native_arrays_published": False,
        "official_solver_integrated": False,
        "original_runtime_executed": False,
        "stage_modified": False,
    }


def export_file(
    bindings: Path,
    config: Path,
    capture: Path,
    output: Path,
    bindings_sha256: str,
    config_sha256: str,
    capture_sha256: str,
    *,
    no_runtime_overrides: bool,
) -> None:
    if no_runtime_overrides is not True:
        raise ValueError("CLI requires explicit empty-override reference premise")
    seals = (bindings_sha256, config_sha256, capture_sha256)
    if any(re.fullmatch(r"[0-9a-f]{64}", seal) is None for seal in seals):
        raise ValueError("Require three explicit lowercase SHA256 seals")
    if output.exists():
        raise FileExistsError(f"Refusing to overwrite {output}")
    raw = tuple(path.read_bytes() for path in (bindings, config, capture))
    if any(
        hashlib.sha256(value).hexdigest() != seal
        for value, seal in zip(raw, seals, strict=True)
    ):
        raise ValueError("Input differs from explicit source seal")
    source_b, source_c, source_g = (json.loads(value) for value in raw)
    document = build_document(
        source_b,
        source_c,
        source_g,
        bindings_sha256,
        resolved_overrides={group["name"]: () for group in source_b["groups"]},
    )
    document["override_context"] = (
        "explicit empty overrides for reconstructed reference only; not observed game state"
    )
    document["source_sha256"] = dict(
        zip(("bindings", "config", "getter_capture"), seals, strict=True)
    )
    with output.open("x", encoding="utf-8", newline="\n") as stream:
        json.dump(document, stream, ensure_ascii=False, indent=2, allow_nan=False)
        stream.write("\n")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ("bindings", "config", "getter-capture", "output"):
        parser.add_argument("--" + name, type=Path, required=True)
    for name in ("bindings-sha256", "config-sha256", "getter-sha256"):
        parser.add_argument("--" + name, required=True)
    parser.add_argument("--no-runtime-overrides", action="store_true", required=True)
    args = parser.parse_args()
    export_file(
        args.bindings,
        args.config,
        args.getter_capture,
        args.output,
        args.bindings_sha256,
        args.config_sha256,
        args.getter_sha256,
        no_runtime_overrides=args.no_runtime_overrides,
    )
    print(f"Reference Line selection match inputs exported: {args.output}")


if __name__ == "__main__":
    main()
