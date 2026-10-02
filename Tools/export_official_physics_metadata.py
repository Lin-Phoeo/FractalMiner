"""Read-only physics enum/interface audit for the observed Endfield v29 layout.

Not a native call graph or an official solver. Layout follows the existing local
Il2CppDumper-end vendor variant; compressed integer format follows Perfare's
Il2CppDumper (MIT), see THIRD_PARTY_IL2CPP_NOTICE.txt. No game process is opened.
"""

import argparse
import hashlib
import json
import struct
from pathlib import Path
from typing import Any


def compressed_i32(data: bytes, offset: int) -> tuple[int, int]:
    if not 0 <= offset < len(data):
        raise ValueError("Missing compressed integer")
    lead = data[offset]
    if lead < 0x80:
        encoded, size = lead, 1
    elif lead < 0xC0:
        size = 2
        if offset + size > len(data):
            raise ValueError("Truncated two-byte integer")
        encoded = ((lead & 0x7F) << 8) | data[offset + 1]
    elif lead < 0xE0:
        size = 4
        if offset + size > len(data):
            raise ValueError("Truncated four-byte integer")
        encoded = ((lead & 0x3F) << 24) | int.from_bytes(
            data[offset + 1 : offset + 4], "big"
        )
    elif lead == 0xF0:
        size = 5
        if offset + size > len(data):
            raise ValueError("Truncated five-byte integer")
        encoded = int.from_bytes(data[offset + 1 : offset + 5], "little")
    elif lead in (0xFE, 0xFF):
        encoded, size = 0xFFFFFFFE + (lead == 0xFF), 1
    else:
        raise ValueError("Reserved compressed integer prefix")
    if encoded == 0xFFFFFFFF:
        return -2147483648, size
    value = encoded >> 1
    return (-value - 1 if encoded & 1 else value), size


class Metadata:
    def __init__(self, data: bytes):
        if len(data) < 264:
            raise ValueError("Truncated vendor metadata header")
        header = struct.unpack_from("<66I", data)
        if header[0] != 0xFAB11BAF or header[1] != 29 or header[2] != 0x108:
            raise ValueError("Not the observed Endfield v29 vendor header")
        self.data = data

        def table(slot: int, stride: int = 1) -> bytes:
            offset, size = header[slot : slot + 2]
            if size % stride or offset + size > len(data) or (size and offset < 264):
                raise ValueError("Invalid metadata table bounds/stride")
            return data[offset : offset + size]

        self.strings = table(6)
        types = table(40, 92)
        if not types or len(types) % 88 == 0:
            raise ValueError("Ambiguous vendor type-definition stride")
        fields = table(24, 12)
        methods = table(12, 32)
        self.values = table(18)
        self.value_file_offset = header[18]
        self.fields = list(struct.iter_unpack("<IiI", fields))
        self.methods = [methods[p : p + 32] for p in range(0, len(methods), 32)]
        self.defaults = {}
        for field, type_index, data_index in struct.iter_unpack("<iii", table(16, 12)):
            if field in self.defaults or not 0 <= field < len(self.fields):
                raise ValueError("Duplicate/out-of-range field default")
            self.defaults[field] = (type_index, data_index)
        self.types = []
        for index, p in enumerate(range(0, len(types), 92)):
            name, namespace, byval = struct.unpack_from("<IIi", types, p)
            method_count = struct.unpack_from("<H", types, p + 68)[0]
            field_count = struct.unpack_from("<H", types, p + 72)[0]
            self.types.append(
                {
                    "definition_index": index,
                    "qualified_name": ".".join(
                        filter(None, (self.string(namespace), self.string(name)))
                    ),
                    "byval_type_index": byval,
                    "declaring_type_index": struct.unpack_from("<i", types, p + 12)[0],
                    "element_type_index": struct.unpack_from("<i", types, p + 20)[0],
                    "field_start": struct.unpack_from("<i", types, p + 32)[0],
                    "field_count": field_count,
                    "method_start": struct.unpack_from("<i", types, p + 36)[0],
                    "method_count": method_count,
                    "is_value_type": bool(
                        struct.unpack_from("<I", types, p + 84)[0] & 1
                    ),
                    "is_enum": bool(struct.unpack_from("<I", types, p + 84)[0] & 2),
                    "token_hex": f"0x{struct.unpack_from('<I', types, p + 88)[0]:08x}",
                }
            )
        byval_rows = {row["byval_type_index"]: row for row in self.types}
        if len(byval_rows) != len(self.types):
            raise ValueError("Ambiguous byval type identity")
        resolved: dict[int, str] = {}

        def full_name(row: dict[str, Any], pending: set[int]) -> str:
            index = row["definition_index"]
            if index in pending:
                raise ValueError("Cyclic nested type ownership")
            if index not in resolved:
                parent = row["declaring_type_index"]
                if parent == -1:
                    resolved[index] = row["qualified_name"]
                elif parent not in byval_rows:
                    raise ValueError("Unresolved nested type ownership")
                else:
                    resolved[index] = (
                        full_name(byval_rows[parent], pending | {index})
                        + "+"
                        + row["qualified_name"].rsplit(".", 1)[-1]
                    )
            return resolved[index]

        # Compute every name before mutating rows, preserving unqualified leafs.
        full_names = [full_name(row, set()) for row in self.types]
        for row, name in zip(self.types, full_names, strict=True):
            row["qualified_name"] = name

    def string(self, index: int) -> str:
        if not 0 <= index < len(self.strings):
            raise ValueError("String index out of bounds")
        end = self.strings.find(b"\0", index)
        if end == -1:
            raise ValueError("Unterminated metadata string")
        return self.strings[index:end].decode("utf-8", errors="strict")

    def type(self, qualified_name: str) -> dict[str, Any]:
        matches = [row for row in self.types if row["qualified_name"] == qualified_name]
        if len(matches) != 1:
            raise ValueError("Missing/ambiguous qualified type")
        return matches[0]

    @staticmethod
    def indices(start: int, count: int, length: int) -> range:
        if count and (start < 0 or start + count > length):
            raise ValueError("Field/method range out of bounds")
        return range(start, start + count)

    def inventory(self, name: str) -> dict[str, Any]:
        row = self.type(name)
        fields = []
        for index in self.indices(
            row["field_start"], row["field_count"], len(self.fields)
        ):
            name_index, type_index, token = self.fields[index]
            fields.append(
                {
                    "name": self.string(name_index),
                    "field_index": index,
                    "type_index": type_index,
                    "token_hex": f"0x{token:08x}",
                }
            )
        methods = []
        for index in self.indices(
            row["method_start"], row["method_count"], len(self.methods)
        ):
            raw = self.methods[index]
            name_index, declaring = struct.unpack_from("<Ii", raw)
            if declaring != row["definition_index"]:
                raise ValueError("Method declaring-type mismatch")
            methods.append(
                {
                    "name": self.string(name_index),
                    "method_index": index,
                    "parameter_count": struct.unpack_from("<H", raw, 30)[0],
                    "token_hex": f"0x{struct.unpack_from('<I', raw, 20)[0]:08x}",
                }
            )
        return {
            **row,
            "fields": fields,
            "methods": methods,
            "native_body_inspected": False,
        }

    def enum(self, name: str) -> dict[str, Any]:
        return self.enum_row(self.type(name))

    def enum_row(self, row: dict[str, Any]) -> dict[str, Any]:
        int32 = self.type("System.Int32")
        if not row["is_enum"] or row["element_type_index"] != int32["byval_type_index"]:
            raise ValueError("Target is not a verified System.Int32-backed enum")
        literals = []
        for index in self.indices(
            row["field_start"], row["field_count"], len(self.fields)
        ):
            name_index, _, token = self.fields[index]
            name = self.string(name_index)
            if name == "value__":
                continue
            default = self.defaults.get(index)
            if default is None or default[0] != int32["byval_type_index"]:
                raise ValueError("Missing/mismatched enum default type")
            offset = default[1]
            value, size = compressed_i32(self.values, offset)
            literals.append(
                {
                    "name": name,
                    "value": value,
                    "field_index": index,
                    "token_hex": f"0x{token:08x}",
                    "data_index": offset,
                    "file_offset": self.value_file_offset + offset,
                    "raw_hex": self.values[offset : offset + size].hex(),
                    "consumed_bytes": size,
                }
            )
        if not literals:
            raise ValueError("Enum has no certified literal defaults")
        return {**row, "underlying_type": "System.Int32", "literals": literals}

    def enum_for_field(self, owner: str, field: str) -> dict[str, Any]:
        matches = [
            row for row in self.inventory(owner)["fields"] if row["name"] == field
        ]
        if len(matches) != 1:
            raise ValueError("Missing/ambiguous consuming field")
        target = [
            row
            for row in self.types
            if row["byval_type_index"] == matches[0]["type_index"]
        ]
        if len(target) != 1:
            raise ValueError("Unresolved/ambiguous field enum type")
        return {"owner": owner, "field": field, **self.enum_row(target[0])}


DEFAULT_SPEC = {
    "enums": [
        "BeyondDynamicBone.ClothUpdateMode",
        "UnityEngine.AnimatorUpdateMode",
        "BeyondDynamicBone.ClothProcess+ClothType",
        "BeyondDynamicBone.BeyondBoneCapsuleCollider+Direction",
        "BeyondDynamicBone.RenderSetupData+BoneConnectionMode",
    ],
    # Field type indices may be attribute-bearing native variants, not a type
    # definition's canonical byval index. Do not guess a +/-1 or +/-2 identity.
    # Interfaces retain their exact field indices; native registration is pending.
    "enum_fields": [],
    "inventories": [
        "BeyondDynamicBone." + name
        for name in (
            "BeyondBoneCloth",
            "ClothSerializeData",
            "BeyondBoneCapsuleCollider",
            "BeyondBoneSphereCollider",
            "MagicaManager",
            "ClothManager",
            "SimulationManager",
            "TimeManager",
            "TeamManager",
            "DynamicBoneTransformManager",
        )
    ]
    + [
        "Beyond.NPC.Animation." + name
        for name in (
            "ClothCalculator",
            "AnimatorClothCalculator",
            "AnimationStreamClothCalculator",
            "NPCCPUAnimator",
        )
    ],
}


def export_files(
    source: Path, output: Path, spec: dict[str, Any] = DEFAULT_SPEC
) -> None:
    if output.exists():
        raise FileExistsError(f"Refusing to overwrite {output}")
    data = source.read_bytes()
    metadata = Metadata(data)
    result = {
        "schema_version": 1,
        "source": str(source.resolve()),
        "source_sha256": hashlib.sha256(data).hexdigest(),
        "layout": "observed Endfield v29 header 0x108, typeDef 92, field 12, method 32",
        "enums": [metadata.enum(name) for name in spec["enums"]],
        "enum_fields": [
            metadata.enum_for_field(row["owner"], row["field"])
            for row in spec["enum_fields"]
        ],
        "inventories": [metadata.inventory(name) for name in spec["inventories"]],
        "runtime_modified": False,
        "runtime_call_order_verified": False,
        "simulation_frequency_verified": False,
        "attribute_bearing_native_field_types_resolved": False,
        "non_claim": "Literal values and interface inventories only; method names are not native bodies, call edges, runtime ordering or solver equivalence.",
    }
    with output.open("x", encoding="utf-8", newline="\n") as stream:
        json.dump(result, stream, ensure_ascii=False, indent=2, allow_nan=False)
        stream.write("\n")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--metadata", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    export_files(args.metadata, args.output)
    print(f"Offline physics enum/interface audit: {args.output}")


if __name__ == "__main__":
    main()
