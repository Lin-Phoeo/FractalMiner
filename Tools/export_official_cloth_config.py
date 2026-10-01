"""Strict, offline AnimeStudio Dump -> reviewed character cloth data.

Not a physics solver or a Magica runtime preset. Preserve raw scalar lexemes,
full curves, selection and 64-bit references. Never silently default settings.
Game binaries/assets are read-only; export to a new local file only.
"""

import argparse
import hashlib
import json
import math
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any


@dataclass
class Node:
    text: str
    line: int
    children: list["Node"] = field(default_factory=list)


@dataclass
class ParsedDump:
    data: dict[str, Any]
    scalars: list[dict[str, Any]]


INTEGER_RANGES = {
    "int": (-(2**31), 2**31 - 1),
    "SInt64": (-(2**63), 2**63 - 1),
    "UInt8": (0, 255),
    "UInt16": (0, 65535),
    "SInt16": (-32768, 32767),
    "unsigned int": (0, 2**32 - 1),
}


def scalar_value(kind: str, raw: str) -> Any:
    if kind in INTEGER_RANGES:
        if not re.fullmatch(r"-?\d+", raw):
            raise ValueError(f"Noninteger {kind}: {raw}")
        value = int(raw)
        low, high = INTEGER_RANGES[kind]
        if not low <= value <= high:
            raise ValueError(f"Out of range {kind}: {raw}")
        return value
    if kind in ("float", "double"):
        value = float(raw)
        if not math.isfinite(value):
            raise ValueError(f"Nonfinite {kind}: {raw}")
        return value
    if kind == "bool" and raw in ("True", "False"):
        return raw == "True"
    if kind == "string":
        value = json.loads(raw)
        if isinstance(value, str):
            return value
    raise ValueError(f"Unsupported scalar {kind}: {raw}")


def fields(node: Node) -> tuple[str, str, str | None]:
    declaration, separator, raw = node.text.partition(" = ")
    kind, space, name = declaration.rpartition(" ")
    if not space or not kind or not name:
        raise ValueError(f"Malformed field at line {node.line}: {node.text}")
    return kind, name, raw if separator else None


def parse_dump(text: str) -> ParsedDump:
    roots: list[Node] = []
    stack: list[Node] = []
    for line_number, line in enumerate(text.splitlines(), 1):
        if not line.strip():
            continue
        depth = len(line) - len(line.lstrip("\t"))
        content = line[depth:]
        if content.startswith(" ") or depth > len(stack):
            raise ValueError(f"Invalid indentation at line {line_number}")
        stack = stack[:depth]
        node = Node(content, line_number)
        if depth:
            stack[-1].children.append(node)
        else:
            roots.append(node)
        stack.append(node)
    if len(roots) != 1:
        raise ValueError("Expected exactly one Dump root")
    scalars: list[dict[str, Any]] = []

    def convert(node: Node, path: list[str | int]) -> Any:
        kind, _, raw = fields(node)
        if raw is not None:
            if node.children:
                raise ValueError(f"Scalar has children at line {node.line}")
            value = scalar_value(kind, raw)
            scalars.append({"path": path, "type": kind, "raw": raw, "line": node.line})
            return value
        children = node.children
        if children and children[0].text == "Array Array":
            if children[0].children or len(children) != 2:
                raise ValueError(f"Malformed array at line {node.line}")
            size_kind, size_name, size_raw = fields(children[1])
            if (size_kind, size_name) != ("int", "size") or size_raw is None:
                raise ValueError(f"Missing array size at line {node.line}")
            # AnimeStudio nests array entries below the size line, not below
            # its empty "Array Array" marker. Ordinary scalars cannot do this.
            size = scalar_value(size_kind, size_raw)
            scalars.append(
                {
                    "path": path + ["$size"],
                    "type": size_kind,
                    "raw": size_raw,
                    "line": children[1].line,
                }
            )
            entries = children[1].children
            if size < 0 or len(entries) != 2 * size:
                raise ValueError(f"Array size mismatch at line {node.line}")
            values = []
            for index in range(size):
                marker, item = entries[2 * index : 2 + 2 * index]
                if marker.text != f"[{index}]" or marker.children:
                    raise ValueError(f"Invalid array index at line {marker.line}")
                if fields(item)[1] != "data":
                    raise ValueError(f"Missing array data at line {item.line}")
                values.append(convert(item, path + [index]))
            return values
        values = {}
        for child in children:
            name = fields(child)[1]
            if name in values:
                raise ValueError(f"Duplicate field {name} at line {child.line}")
            values[name] = convert(child, path + [name])
        return values

    data = convert(roots[0], [])
    if not isinstance(data, dict):
        # This is malformed file content, not an invalid Python argument type.
        raise ValueError("Dump root must be a structure")  # noqa: TRY004
    return ParsedDump(data, scalars)


def root_key(data: dict[str, Any], expected_file: int) -> tuple[int, ...]:
    roots = data.get("rootBones")
    if not isinstance(roots, list) or not roots:
        raise ValueError("Missing cloth rootBones")
    keys = []
    for root in roots:
        if not isinstance(root, dict) or set(root) != {"m_FileID", "m_PathID"}:
            raise ValueError("Invalid root PPtr")
        if (
            type(root["m_FileID"]) is not int
            or root["m_FileID"] != expected_file
            or type(root["m_PathID"]) is not int
            or root["m_PathID"] == 0
        ):
            raise ValueError("Unresolved or invalid cloth root reference")
        keys.append(root["m_PathID"])
    return tuple(keys)


def normalized_references(value: Any, expected_file: int) -> Any:
    if isinstance(value, list):
        return [normalized_references(item, expected_file) for item in value]
    if isinstance(value, dict):
        if set(value) == {"m_FileID", "m_PathID"}:
            if type(value["m_FileID"]) is not int or type(value["m_PathID"]) is not int:
                raise ValueError("PPtr indices must retain integer types")
            allowed = expected_file if value["m_PathID"] != 0 else 0
            if value["m_FileID"] != allowed:
                raise ValueError("Unexpected external PPtr fileID")
            return {"m_PathID": value["m_PathID"]}
        return {
            key: normalized_references(item, expected_file)
            for key, item in value.items()
        }
    return value


def scalar_signature(
    scalars: list[dict[str, Any]], prefix: list[str | int]
) -> list[dict[str, Any]]:
    """Compare types and original spellings too, not just Python 0 == 0.0."""
    return [
        {"path": item["path"][len(prefix) :], "type": item["type"], "raw": item["raw"]}
        for item in scalars
        if item["path"][: len(prefix)] == prefix and item["path"][-1:] != ["m_FileID"]
    ]


def build_manifest(
    avatar_text: str, prefab_texts: dict[str, str], expected_groups: int = 11
) -> dict[str, Any]:
    parsed = parse_dump(avatar_text)
    groups = parsed.data.get("boneClothItems")
    if (
        not isinstance(groups, list)
        or len(groups) != expected_groups
        or expected_groups < 1
    ):
        raise ValueError(
            f"Expected {expected_groups} boneClothItems, no defaults allowed"
        )
    candidates: dict[tuple[int, ...], list[tuple[str, dict[str, Any]]]] = {}
    prefab_scalars = {}
    prefab_components = {}
    for name, text in sorted(prefab_texts.items()):
        component = parse_dump(text)
        data = component.data
        if "serializeData" not in data:
            continue
        key = root_key(data["serializeData"], 0)
        candidates.setdefault(key, []).append((name, data))
        prefab_scalars[name] = component.scalars
        prefab_components[name] = data
    names: set[str] = set()
    verification = []
    total = 0
    for index, group in enumerate(groups):
        name = group.get("boneClothName")
        if (
            not isinstance(name, str)
            or not name.startswith("MBC_Typhoea_")
            or name in names
        ):
            raise ValueError("Missing, duplicate or unexpected character cloth name")
        names.add(name)
        settings = group.get("boneClothData", {})
        if settings.get("clothType") != 1:
            raise ValueError(f"Expected BoneCloth=1: {name}")
        key = root_key(settings, 2)
        matches = candidates.get(key, [])
        if len(matches) != 1:
            raise ValueError(f"Missing or ambiguous prefab root binding: {name}")
        prefab_name, prefab = matches[0]
        if prefab.get("m_Enabled") != 1:
            raise ValueError(f"Disabled prefab cloth component: {name}")
        if normalized_references(settings, 2) != normalized_references(
            prefab["serializeData"], 0
        ):
            raise ValueError(f"Complete cloth parameters differ: {name}")
        if scalar_signature(
            parsed.scalars, ["boneClothItems", index, "boneClothData"]
        ) != scalar_signature(prefab_scalars[prefab_name], ["serializeData"]):
            raise ValueError(f"Cloth scalar type/lexeme differs: {name}")
        selection = group.get("selectionData", {})
        positions, attributes = selection.get("positions"), selection.get("attributes")
        if (
            not isinstance(positions, list)
            or not isinstance(attributes, list)
            or len(positions) != len(attributes)
        ):
            raise ValueError(f"Selection position/attribute mismatch: {name}")
        if selection != prefab.get("serializeData2", {}).get("selectionData"):
            raise ValueError(f"Complete selection data differ: {name}")
        if scalar_signature(
            parsed.scalars, ["boneClothItems", index, "selectionData"]
        ) != scalar_signature(
            prefab_scalars[prefab_name], ["serializeData2", "selectionData"]
        ):
            raise ValueError(f"Selection scalar type/lexeme differs: {name}")
        if len(group.get("rootBoneList", [])) != len(key):
            raise ValueError(f"Root name/reference count differs: {name}")
        total += len(positions)
        verification.append(
            {
                "group_index": index,
                "name": name,
                "prefab": prefab_name,
                "root_binding_unique": True,
                "component_enabled": True,
                "parameters_equal": True,
                "selection_equal": True,
            }
        )
    return {
        "schema_version": 1,
        "runtime_restored": False,
        "reference_normalization": "AvatarMesh external fileID=2 / prefab local fileID=0; PathIDs retained",
        "groups": groups,
        "selection_positions_total": total,
        "verification": verification,
        "avatar_raw_scalars": [
            item for item in parsed.scalars if item["path"][:1] == ["boneClothItems"]
        ],
        "prefab_raw_scalars": prefab_scalars,
        "prefab_components": prefab_components,
    }


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def export_files(
    avatar: Path, prefab_dir: Path, output: Path, expected_groups: int = 11
) -> None:
    if output.exists():
        raise FileExistsError(f"Refusing to overwrite {output}")
    avatar_bytes = avatar.read_bytes()
    prefab_bytes = {
        str(path.resolve()): path.read_bytes()
        for path in sorted(prefab_dir.glob("*.txt"))
    }
    manifest = build_manifest(
        avatar_bytes.decode("utf-8-sig"),
        {name: data.decode("utf-8-sig") for name, data in prefab_bytes.items()},
        expected_groups,
    )
    manifest["source"] = {
        "avatar": {"path": str(avatar.resolve()), "sha256": sha256_bytes(avatar_bytes)},
        "prefabs": {name: sha256_bytes(data) for name, data in prefab_bytes.items()},
    }
    # Exclusive creation also protects against a file appearing during the audit.
    with output.open("x", encoding="utf-8", newline="\n") as stream:
        json.dump(manifest, stream, ensure_ascii=False, indent=2, allow_nan=False)
        stream.write("\n")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--avatar", type=Path, required=True)
    parser.add_argument("--prefab-dir", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    export_files(args.avatar, args.prefab_dir, args.output)
    print(f"Verified 11 original cloth groups; local manifest: {args.output}")


if __name__ == "__main__":
    main()
