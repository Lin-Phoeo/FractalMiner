"""Offline native type/entry-point audit, not a solver or runtime call graph.

Uses the observed Endfield v29 metadata parser and the IL2CPP registration/type/
module layout documented by Perfare Il2CppDumper (MIT); see third-party notice.
Does not load a DLL, attach to a process, bypass protection or change game files.
"""

import argparse
import hashlib
import json
import struct
from pathlib import Path
from typing import Any

from export_official_physics_metadata import DEFAULT_SPEC as METADATA_SPEC
from export_official_physics_metadata import Metadata


class PE64:
    """Bounded file-backed mapping for AMD64 PE32+, excluding BSS and gaps."""

    def __init__(self, data: bytes):
        self.data = data
        if len(data) < 64 or data[:2] != b"MZ":
            raise ValueError("Invalid DOS header")
        pos = struct.unpack_from("<I", data, 60)[0]
        if pos + 24 > len(data) or data[pos : pos + 4] != b"PE\0\0":
            raise ValueError("Invalid PE signature/header")
        machine, count = struct.unpack_from("<HH", data, pos + 4)
        size = struct.unpack_from("<H", data, pos + 20)[0]
        opt = pos + 24
        if (
            machine != 0x8664
            or not count
            or size < 112
            or opt + size + count * 40 > len(data)
        ):
            raise ValueError("Unsupported/truncated AMD64 optional/section headers")
        if struct.unpack_from("<H", data, opt)[0] != 0x20B:
            raise ValueError("Not PE32+")
        self.base = struct.unpack_from("<Q", data, opt + 24)[0]
        self.sections: list[dict[str, Any]] = []
        for i in range(count):
            p = opt + size + 40 * i
            virtual_size, rva, raw_size, raw = struct.unpack_from("<4I", data, p + 8)
            flags = struct.unpack_from("<I", data, p + 36)[0]
            if raw_size and (
                raw < opt + size + count * 40 or raw + raw_size > len(data)
            ):
                raise ValueError("Section raw range outside file")
            row = {
                "name": data[p : p + 8].rstrip(b"\0").decode("ascii", errors="strict"),
                "rva": rva,
                "virtual_size": virtual_size,
                "raw_size": raw_size,
                "raw_offset": raw,
                "mapped_size": min(raw_size, virtual_size),
                "readable": bool(flags & 0x40000000),
                "executable": bool(flags & 0x20000000),
            }
            for old in self.sections:
                if (
                    raw_size
                    and old["raw_size"]
                    and max(raw, old["raw_offset"])
                    < min(raw + raw_size, old["raw_offset"] + old["raw_size"])
                ):
                    raise ValueError("Section raw overlap")
                if max(rva, old["rva"]) < min(
                    rva + virtual_size, old["rva"] + old["virtual_size"]
                ):
                    raise ValueError("Section virtual overlap")
            self.sections.append(row)

    def offset(self, va: int, size: int = 1, executable: bool = False) -> int:
        rva = va - self.base
        matches = [
            s
            for s in self.sections
            if size > 0
            and s["readable"]
            and (not executable or s["executable"])
            and s["rva"] <= rva
            and rva + size <= s["rva"] + s["mapped_size"]
        ]
        if len(matches) != 1:
            raise ValueError("Unmapped/ambiguous/non-file-backed virtual range")
        s = matches[0]
        return s["raw_offset"] + rva - s["rva"]

    def va(self, offset: int, size: int = 1) -> int:
        matches = [
            s
            for s in self.sections
            if size > 0
            and s["raw_offset"] <= offset
            and offset + size <= s["raw_offset"] + s["mapped_size"]
        ]
        if len(matches) != 1:
            raise ValueError("Unmapped/ambiguous file range")
        s = matches[0]
        return self.base + s["rva"] + offset - s["raw_offset"]

    def pointers(self, va: int, count: int) -> tuple[int, ...]:
        if not 0 < count <= len(self.data) // 8:
            raise ValueError("Invalid pointer count")
        p = self.offset(va, count * 8)
        return struct.unpack_from(f"<{count}Q", self.data, p)

    def data_hits(self, needle: bytes):
        for s in self.sections:
            if not s["readable"] or s["executable"]:
                continue
            start, end = s["raw_offset"], s["raw_offset"] + s["mapped_size"]
            while (start := self.data.find(needle, start, end)) != -1:
                yield start
                start += 1


class NativeAudit:
    def __init__(self, pe: PE64, metadata: Metadata):
        self.pe, self.metadata = pe, metadata
        self.registration = self.find_registration()
        self.types = pe.pointers(
            self.registration["types_va"], self.registration["types_count"]
        )
        h = struct.unpack_from("<66I", metadata.data)
        offset, size = h[42:44]
        if not size or size % 40 or offset < 264 or offset + size > len(metadata.data):
            raise ValueError("Invalid vendor image table")
        self.images = []
        for index, p in enumerate(range(offset, offset + size, 40)):
            name, _, start, count = struct.unpack_from("<IiiI", metadata.data, p)
            if start < 0 or start + count > len(metadata.types):
                raise ValueError("Invalid image type range")
            self.images.append(
                {
                    "image_index": index,
                    "name": metadata.string(name),
                    "type_start": start,
                    "type_count": count,
                }
            )
        names = [x["name"] for x in self.images]
        owners = [
            i
            for x in self.images
            for i in range(x["type_start"], x["type_start"] + x["type_count"])
        ]
        if len(set(names)) != len(names) or sorted(owners) != list(
            range(len(metadata.types))
        ):
            raise ValueError("Ambiguous/incomplete image ownership")
        self.modules: dict[str, dict[str, Any]] = {}

    def find_registration(self) -> dict[str, Any]:
        pe, metadata = self.pe, self.metadata
        count = len(metadata.types)
        minimum = max(t["byval_type_index"] for t in metadata.types) + 1
        candidates = []
        for pos in pe.data_hits(struct.pack("<Q", count)):
            start = pos - 80
            if start < 0 or start % 8:
                continue
            try:
                va = pe.va(start, 128)
                values = struct.unpack_from("<16Q", pe.data, start)
                if values[10] != count or values[12] != count or values[6] < minimum:
                    continue
                pe.pointers(values[7], values[6])
                pe.pointers(values[11], count)
                sizes = pe.pointers(values[13], count)
                for address in sizes:
                    pe.offset(address, 16)
            except (ValueError, struct.error):
                continue
            candidates.append(
                {
                    "va_hex": f"0x{va:x}",
                    "file_offset": start,
                    "types_count": values[6],
                    "types_va": values[7],
                    "field_offsets_count": values[10],
                    "type_definition_sizes_count": values[12],
                    "validation": "unique 128-byte registration candidate; counts, full arrays and all size pointers file-backed",
                }
            )
        if len(candidates) != 1:
            raise ValueError(
                f"Missing/ambiguous metadata registration ({len(candidates)})"
            )
        return candidates[0]

    def native_type(self, index: int) -> dict[str, Any]:
        if not 0 <= index < len(self.types):
            raise ValueError("Native type index out of range")
        address = self.types[index]
        offset = self.pe.offset(address, 12)
        data, bits = struct.unpack_from("<QI", self.pe.data, offset)
        return {
            "type_index": index,
            "va_hex": f"0x{address:x}",
            "file_offset": offset,
            "data": data,
            "definition_index": data if (bits >> 16) & 255 in (0x11, 0x12) else None,
            "bits_hex": f"0x{bits:08x}",
            "kind": (bits >> 16) & 255,
            "attrs": bits & 65535,
            "num_mods": (bits >> 24) & 31,
            "byref": (bits >> 29) & 1,
            "pinned": (bits >> 30) & 1,
            "valuetype": bits >> 31,
        }

    def field_layout(self, owner: str) -> dict[str, Any]:
        row = self.metadata.inventory(owner)
        canonical = self.native_type(row["byval_type_index"])
        if (
            canonical["kind"] != 0x12
            or canonical["definition_index"] != row["definition_index"]
            or canonical["byref"]
            or canonical["num_mods"]
            or canonical["pinned"]
        ):
            raise ValueError("Native layout owner class identity mismatch")
        reg = struct.unpack_from("<16Q", self.pe.data, self.registration["file_offset"])
        table = self.pe.pointers(reg[11], len(self.metadata.types))
        count = len(row["fields"])
        p = self.pe.offset(table[row["definition_index"]], count * 4)
        fields = []
        for i, field in enumerate(row["fields"]):
            offset = struct.unpack_from("<i", self.pe.data, p + i * 4)[0]
            if offset < 0:
                raise ValueError("Unavailable/unsupported native field offset")
            native = self.native_type(field["type_index"])
            definition = native["definition_index"]
            if definition is not None and not 0 <= definition < len(
                self.metadata.types
            ):
                raise ValueError("Native field definition index out of range")
            fields.append(
                {
                    **field,
                    "offset": offset,
                    "offset_file_position": p + i * 4,
                    "is_static": bool(native["attrs"] & 0x10),
                    "native_type": native,
                    "qualified_type": self.metadata.types[definition]["qualified_name"]
                    if definition is not None
                    else None,
                }
            )
        return {
            "owner": owner,
            "definition_index": row["definition_index"],
            "fields": fields,
            "layout_identity_verified": True,
            "non_claim": "Static offsets are relative to static storage, instance offsets to the object; not interchangeable. Primitive/generic union data is not labelled a type-definition identity.",
        }

    def type_info_cell(self, va: int, owner: str) -> dict[str, Any]:
        offset = self.pe.offset(va, 8)
        encoded = struct.unpack_from("<Q", self.pe.data, offset)[0]
        if encoded > 0xFFFFFFFF or not encoded & 1 or (encoded & 0xE0000000) >> 29 != 1:
            raise ValueError("Not an observed tagged v29 type-info usage cell")
        index = (encoded & 0x1FFFFFFE) >> 1
        row = self.metadata.type(owner)
        native = self.native_type(index)
        if (
            index != row["byval_type_index"]
            or native["kind"] != 0x12
            or native["definition_index"] != row["definition_index"]
        ):
            raise ValueError("Type-info usage owner identity mismatch")
        return {
            "va_hex": f"0x{va:x}",
            "file_offset": offset,
            "encoded_hex": f"0x{encoded:x}",
            "type_index": index,
            "definition_index": row["definition_index"],
            "owner": owner,
            "runtime_class_pointer_or_static_storage_inspected": False,
        }

    def field_enum(self, owner: str, field: str, enum: str) -> dict[str, Any]:
        expected = self.metadata.enum(enum)
        fields = [
            f for f in self.metadata.inventory(owner)["fields"] if f["name"] == field
        ]
        if len(fields) != 1:
            raise ValueError("Missing/ambiguous consuming field")
        native = self.native_type(fields[0]["type_index"])
        canonical = self.native_type(expected["byval_type_index"])
        for t in (native, canonical):
            if (
                t["kind"] != 0x11
                or t["definition_index"] != expected["definition_index"]
                or t["byref"]
                or t["pinned"]
                or t["num_mods"]
                or not t["valuetype"]
            ):
                raise ValueError("Native enum definition/kind/flags mismatch")
        return {
            "owner": owner,
            "field": field,
            "field_index": fields[0]["field_index"],
            "enum": enum,
            "field_type": native,
            "canonical_type": canonical,
            "identity_verified": True,
            "literals": expected["literals"],
        }

    def image_for_type(self, index: int) -> dict[str, Any]:
        matches = [
            x
            for x in self.images
            if x["type_start"] <= index < x["type_start"] + x["type_count"]
        ]
        if len(matches) != 1:
            raise ValueError("Missing/ambiguous image owner")
        return matches[0]

    def module(self, image: dict[str, Any]) -> dict[str, Any]:
        name = image["name"]
        if name in self.modules:
            return self.modules[name]
        tokens = []
        for t in self.metadata.types[
            image["type_start"] : image["type_start"] + image["type_count"]
        ]:
            for i in self.metadata.indices(
                t["method_start"], t["method_count"], len(self.metadata.methods)
            ):
                token = struct.unpack_from("<I", self.metadata.methods[i], 20)[0]
                if token >> 24 != 6 or not token & 0xFFFFFF:
                    raise ValueError("Invalid method token in image")
                tokens.append(token & 0xFFFFFF)
        if (
            not tokens
            or len(set(tokens)) != len(tokens)
            or sorted(tokens) != list(range(1, max(tokens) + 1))
        ):
            raise ValueError("Incomplete/ambiguous image method RID inventory")
        candidates = []
        for pos in self.pe.data_hits(name.encode("utf-8") + b"\0"):
            name_va = self.pe.va(pos, len(name.encode("utf-8")) + 1)
            for p in self.pe.data_hits(struct.pack("<Q", name_va)):
                if p % 8:
                    continue
                try:
                    module_va = self.pe.va(p, 24)
                    _, count, pointers = struct.unpack_from("<3Q", self.pe.data, p)
                    if count != max(tokens):
                        continue
                    addresses = self.pe.pointers(pointers, count)
                    for address in addresses:
                        if address:
                            self.pe.offset(address, executable=True)
                except (ValueError, struct.error):
                    continue
                candidates.append(
                    {
                        "name": name,
                        "va_hex": f"0x{module_va:x}",
                        "file_offset": p,
                        "method_count": count,
                        "method_pointers_va_hex": f"0x{pointers:x}",
                        "pointers": addresses,
                        "validation": "unique module name pointer, exact complete metadata RID count; all non-null method pointers executable/file-backed",
                    }
                )
        if len(candidates) != 1:
            raise ValueError(
                f"Missing/ambiguous codegen module {name} ({len(candidates)})"
            )
        self.modules[name] = candidates[0]
        return candidates[0]

    def inventory(self, name: str) -> dict[str, Any]:
        row = self.metadata.inventory(name)
        image = self.image_for_type(row["definition_index"])
        module = self.module(image)
        for method in row["methods"]:
            token = int(method["token_hex"], 16)
            rid = token & 0xFFFFFF
            address = module["pointers"][rid - 1]
            method.update(
                {
                    "image": image["name"],
                    "token_rid": rid,
                    "va_hex": f"0x{address:x}" if address else None,
                    "rva_hex": f"0x{address - self.pe.base:x}" if address else None,
                    "file_offset": self.pe.offset(address, executable=True)
                    if address
                    else None,
                    "native_body_inspected": False,
                }
            )
        return {**row, "image": image, "native_body_inspected": False}

    def report(self, spec: dict[str, Any]) -> dict[str, Any]:
        fields = [self.field_enum(**f) for f in spec["fields"]]
        inventories = [self.inventory(name) for name in spec["inventories"]]
        return {
            "schema_version": 2,
            "registration": self.registration,
            "sections": self.pe.sections,
            "image_count": len(self.images),
            "enum_fields": fields,
            "field_layouts": [
                self.field_layout(owner) for owner in spec.get("layout_owners", [])
            ],
            "type_info_cells": [
                self.type_info_cell(**cell) for cell in spec.get("type_info_cells", [])
            ],
            "inventories": inventories,
            "modules": [
                {k: v for k, v in m.items() if k != "pointers"}
                for m in self.modules.values()
            ],
            "attribute_bearing_native_field_types_resolved": bool(fields),
            "runtime_modified": False,
            "runtime_call_order_verified": False,
            "simulation_frequency_verified": False,
            "native_bodies_inspected": False,
            "global_code_registration_verified": False,
            "non_claim": "Native field identities and structurally validated module entry points only. No native call graph, solver equivalence, runtime order or frequency claim. External prefab MonoScript CAB references remain unresolved.",
        }


DEFAULT_SPEC = {
    "fields": [
        {"owner": "BeyondDynamicBone.ClothSerializeData", "field": field, "enum": enum}
        for field, enum in (
            ("updateMode", "BeyondDynamicBone.ClothUpdateMode"),
            ("clothType", "BeyondDynamicBone.ClothProcess+ClothType"),
            ("connectionMode", "BeyondDynamicBone.RenderSetupData+BoneConnectionMode"),
        )
    ]
    + [
        {
            "owner": "BeyondDynamicBone.TimeManager",
            "field": "updateLocation",
            "enum": "BeyondDynamicBone.TimeManager+UpdateLocation",
        }
    ]
    + [
        {
            "owner": "BeyondDynamicBone.BeyondBoneCapsuleCollider",
            "field": "direction",
            "enum": "BeyondDynamicBone.BeyondBoneCapsuleCollider+Direction",
        }
    ],
    "inventories": METADATA_SPEC["inventories"],
    "layout_owners": [
        "BeyondDynamicBone." + name
        for name in ("MagicaManager", "TimeManager", "ClothManager")
    ],
}


def export_files(
    binary: Path, metadata: Path, output: Path, spec: dict[str, Any] = DEFAULT_SPEC
) -> None:
    if output.exists():
        raise FileExistsError(f"Refusing to overwrite {output}")
    b, m = binary.read_bytes(), metadata.read_bytes()
    result = NativeAudit(PE64(b), Metadata(m)).report(spec)
    result["sources"] = {
        "binary": str(binary.resolve()),
        "binary_sha256": hashlib.sha256(b).hexdigest(),
        "metadata": str(metadata.resolve()),
        "metadata_sha256": hashlib.sha256(m).hexdigest(),
    }
    with output.open("x", encoding="utf-8", newline="\n") as stream:
        json.dump(result, stream, ensure_ascii=False, indent=2, allow_nan=False)
        stream.write("\n")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--binary", type=Path, required=True)
    parser.add_argument("--metadata", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument(
        "--type-info-cell",
        action="append",
        default=[],
        metavar="OWNER=VA",
        help="Optional observed tagged type-info cell, preferred VA in decimal or hex",
    )
    args = parser.parse_args()
    cells = []
    for value in args.type_info_cell:
        try:
            owner, address = value.rsplit("=", 1)
            cells.append({"owner": owner, "va": int(address, 0)})
        except ValueError:
            parser.error("--type-info-cell expects OWNER=VA")
    export_files(
        args.binary,
        args.metadata,
        args.output,
        {**DEFAULT_SPEC, "type_info_cells": cells},
    )
    print(f"Offline physics native identity/entry-point audit: {args.output}")


if __name__ == "__main__":
    main()
