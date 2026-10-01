"""Independent synthetic tables and byte vectors, never expected game values as parser input."""

import copy
import json
import struct
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from export_official_physics_metadata import Metadata, compressed_i32, export_files


@pytest.mark.parametrize(
    "raw,value",
    [
        (b"\x00", 0),
        (b"\x02", 1),
        (b"\x04", 2),
        (b"\x14", 10),
        (b"\x01", -1),
        (b"\x80\x80", 64),
        (b"\xc0\x01\x00\x00", 32768),
        (b"\xf0\x00\x00\x00\x20", 268435456),
        (b"\xfe", 2147483647),
        (b"\xff", -2147483648),
    ],
)
def test_compressed_i32_byte_vectors(raw, value):
    assert compressed_i32(raw, 0) == (value, len(raw))


@pytest.mark.parametrize(
    "raw", [b"", b"\x80", b"\xc0\x00", b"\xf0\x01", b"\xe0", b"\xf1"]
)
def test_truncated_or_reserved_integer_encodings_stop(raw):
    with pytest.raises(ValueError):
        compressed_i32(raw, 0)


def fixture():
    names = [
        "System",
        "Int32",
        "BeyondDynamicBone",
        "ClothUpdateMode",
        "ClothSerializeData",
        "value__",
        "Normal",
        "AnimatorLinkage",
        "updateMode",
    ]
    strings = bytearray()
    offsets = {}
    for name in names:
        offsets[name] = len(strings)
        strings.extend(name.encode() + b"\0")
    types = bytearray(3 * 92)
    for i, (ns, name, byval, start, count, bits, element) in enumerate(
        [
            ("System", "Int32", 11, 0, 0, 1, -1),
            ("BeyondDynamicBone", "ClothUpdateMode", 22, 0, 3, 3, 11),
            ("BeyondDynamicBone", "ClothSerializeData", 33, 3, 1, 0, -1),
        ]
    ):
        p = i * 92
        struct.pack_into("<IIi", types, p, offsets[name], offsets[ns], byval)
        struct.pack_into("<i", types, p + 12, -1)
        struct.pack_into("<i", types, p + 20, element)
        struct.pack_into("<i", types, p + 32, start)
        struct.pack_into("<H", types, p + 72, count)
        struct.pack_into("<II", types, p + 84, bits, 0x02000001 + i)
    fields = b"".join(
        struct.pack("<IiI", offsets[name], tid, 0x04000001 + i)
        for i, (name, tid) in enumerate(
            [
                ("value__", 11),
                ("Normal", 22),
                ("AnimatorLinkage", 22),
                ("updateMode", 22),
            ]
        )
    )
    defaults = struct.pack("<iii", 1, 11, 0) + struct.pack("<iii", 2, 11, 1)
    header = [0] * 66
    header[0:3] = [0xFAB11BAF, 29, 0x108]
    data = bytearray(264)
    for offset_index, content in [
        (6, strings),
        (40, types),
        (24, fields),
        (16, defaults),
        (18, b"\x00\x14"),
    ]:
        header[offset_index : offset_index + 2] = [len(data), len(content)]
        data.extend(content)
    struct.pack_into("<66I", data, 0, *header)
    return bytes(data)


def test_enum_identity_underlying_type_and_consuming_field():
    metadata = Metadata(fixture())
    enum = metadata.enum("BeyondDynamicBone.ClothUpdateMode")
    assert enum["underlying_type"] == "System.Int32"
    assert {row["name"]: row["value"] for row in enum["literals"]} == {
        "Normal": 0,
        "AnimatorLinkage": 10,
    }
    literal = enum["literals"][1]
    assert literal["raw_hex"] == "14"
    assert literal["consumed_bytes"] == 1
    enum_from_field = metadata.enum_for_field(
        "BeyondDynamicBone.ClothSerializeData", "updateMode"
    )
    assert enum_from_field["definition_index"] == enum["definition_index"]
    assert (
        metadata.inventory("BeyondDynamicBone.ClothSerializeData")["fields"][0]["name"]
        == "updateMode"
    )


@pytest.mark.parametrize(
    "case",
    [
        "magic",
        "version",
        "layout",
        "range",
        "stride",
        "string",
        "not_enum",
        "underlying",
        "default_type",
        "default_offset",
        "duplicate_default",
        "missing_default",
    ],
)
def test_invalid_metadata_cannot_certify_enum(case):
    data = bytearray(fixture())
    header = struct.unpack_from("<66I", data)
    types, defaults = header[40], header[16]
    if case == "magic":
        struct.pack_into("<I", data, 0, 0)
    elif case == "version":
        struct.pack_into("<I", data, 4, 28)
    elif case == "layout":
        struct.pack_into("<I", data, 8, 256)
    elif case == "range":
        struct.pack_into("<I", data, 6 * 4, len(data) + 1)
    elif case == "stride":
        struct.pack_into("<I", data, 41 * 4, 275)
    elif case == "string":
        struct.pack_into("<I", data, types + 92, 999999)
    elif case == "not_enum":
        struct.pack_into("<I", data, types + 92 + 84, 1)
    elif case == "underlying":
        struct.pack_into("<i", data, types + 92 + 20, 99)
    elif case == "default_type":
        struct.pack_into("<i", data, defaults + 4, 99)
    elif case == "default_offset":
        struct.pack_into("<i", data, defaults + 8, 999999)
    elif case == "duplicate_default":
        struct.pack_into("<i", data, defaults + 12, 1)
    elif case == "missing_default":
        struct.pack_into("<I", data, 17 * 4, 12)
    with pytest.raises(ValueError):
        Metadata(bytes(data)).enum("BeyondDynamicBone.ClothUpdateMode")


def test_missing_type_and_field_stop():
    metadata = Metadata(fixture())
    with pytest.raises(ValueError):
        metadata.enum("absent")
    with pytest.raises(ValueError):
        metadata.enum_for_field("BeyondDynamicBone.ClothSerializeData", "absent")


def test_nested_owner_uses_native_byval_identity_not_definition_index():
    data = bytearray(fixture())
    types = struct.unpack_from("<I", data, 40 * 4)[0]
    struct.pack_into("<i", data, types + 92 + 12, 33)
    row = Metadata(bytes(data)).enum(
        "BeyondDynamicBone.ClothSerializeData+ClothUpdateMode"
    )
    assert row["declaring_type_index"] == 33
    assert row["definition_index"] == 1


@pytest.mark.parametrize("parent", [22, 99999])
def test_cyclic_or_unresolved_nested_type_stops(parent):
    data = bytearray(fixture())
    types = struct.unpack_from("<I", data, 40 * 4)[0]
    struct.pack_into("<i", data, types + 92 + 12, parent)
    with pytest.raises(ValueError):
        Metadata(bytes(data))


def test_native_field_type_variant_is_not_guessed_by_adding_one():
    data = bytearray(fixture())
    fields = struct.unpack_from("<I", data, 24 * 4)[0]
    struct.pack_into("<i", data, fields + 3 * 12 + 4, 21)
    with pytest.raises(ValueError):
        Metadata(bytes(data)).enum_for_field(
            "BeyondDynamicBone.ClothSerializeData", "updateMode"
        )


def test_method_inventory_validates_declaring_type():
    data = bytearray(fixture())
    header = struct.unpack_from("<66I", data)
    types, strings = header[40], header[6]
    name_index = data.index(b"updateMode\0", strings) - strings
    raw = bytearray(32)
    struct.pack_into("<Ii", raw, 0, name_index, 2)
    struct.pack_into("<I", raw, 20, 0x06000001)
    struct.pack_into("<H", raw, 30, 2)
    struct.pack_into("<II", data, 12 * 4, len(data), 32)
    struct.pack_into("<H", data, types + 2 * 92 + 68, 1)
    data.extend(raw)
    row = Metadata(bytes(data)).inventory("BeyondDynamicBone.ClothSerializeData")
    assert row["methods"][0]["parameter_count"] == 2
    struct.pack_into("<i", data, header[18] + header[19] + 4, 0)
    with pytest.raises(ValueError):
        Metadata(bytes(data)).inventory("BeyondDynamicBone.ClothSerializeData")


def test_file_flow_and_overwrite_guard(tmp_path):
    source = tmp_path / "global-metadata.dat"
    source.write_bytes(fixture())
    output = tmp_path / "report.json"
    spec = {
        "enums": ["BeyondDynamicBone.ClothUpdateMode"],
        "enum_fields": [
            {"owner": "BeyondDynamicBone.ClothSerializeData", "field": "updateMode"}
        ],
        "inventories": ["BeyondDynamicBone.ClothSerializeData"],
    }
    export_files(source, output, spec)
    result = json.loads(output.read_text(encoding="utf-8"))
    assert result["runtime_modified"] is False
    assert result["runtime_call_order_verified"] is False
    before = output.read_bytes()
    with pytest.raises(FileExistsError):
        export_files(source, output, copy.deepcopy(spec))
    assert output.read_bytes() == before
