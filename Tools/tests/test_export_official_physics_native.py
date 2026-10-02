"""Synthetic PE/registration tests, with deliberately non-adjacent type variants."""

import json
import struct
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from export_official_physics_metadata import Metadata
from export_official_physics_native import PE64, NativeAudit, export_files
from test_export_official_physics_metadata import fixture

BASE = 0x180000000
SPEC = {
    "fields": [
        {
            "owner": "BeyondDynamicBone.ClothSerializeData",
            "field": "updateMode",
            "enum": "BeyondDynamicBone.ClothUpdateMode",
        }
    ],
    "inventories": ["BeyondDynamicBone.ClothSerializeData"],
}


def samples():
    meta = bytearray(fixture())
    header = list(struct.unpack_from("<66I", meta))
    strings = header[6]
    # Fixture already has suitable strings; method name is irrelevant to lookup.
    owner_name = struct.unpack_from("<I", meta, header[40] + 2 * 92)[0]
    method_name = struct.unpack_from("<I", meta, header[24] + 3 * 12)[0]
    # A real native field index, deliberately far from canonical enum index 22.
    struct.pack_into("<i", meta, header[24] + 3 * 12 + 4, 37)
    struct.pack_into("<i", meta, header[40] + 2 * 92 + 36, 0)
    struct.pack_into("<H", meta, header[40] + 2 * 92 + 68, 1)
    header[12:14] = [len(meta), 32]
    raw = bytearray(32)
    struct.pack_into("<Ii", raw, 0, method_name, 2)
    struct.pack_into("<I", raw, 20, 0x06000001)
    meta.extend(raw)
    # One image owns all three types; use owner's existing name as module name.
    header[42:44] = [len(meta), 40]
    meta.extend(
        struct.pack(
            "<10I", owner_name, 0, 0, 3, 0xFFFFFFFF, 0, 0xFFFFFFFF, 0x20000001, 0, 0
        )
    )
    struct.pack_into("<66I", meta, 0, *header)
    module_name = b"ClothSerializeData\0"
    assert (
        meta[strings + owner_name : strings + owner_name + len(module_name)]
        == module_name
    )

    data = bytearray(0x4600)
    data[:2] = b"MZ"
    struct.pack_into("<I", data, 60, 0x80)
    data[0x80:0x84] = b"PE\0\0"
    struct.pack_into("<HH", data, 0x84, 0x8664, 2)
    struct.pack_into("<H", data, 0x94, 0xF0)
    opt = 0x98
    struct.pack_into("<H", data, opt, 0x20B)
    struct.pack_into("<Q", data, opt + 24, BASE)
    struct.pack_into("<I", data, opt + 56, 0x6000)
    for i, (name, vs, rva, size, off, flags) in enumerate(
        [
            (b".text", 0x200, 0x1000, 0x200, 0x400, 0x60000020),
            (b".rdata", 0x5000, 0x2000, 0x4000, 0x600, 0x40000040),
        ]
    ):
        pos = opt + 0xF0 + 40 * i
        data[pos : pos + 8] = name.ljust(8, b"\0")
        struct.pack_into("<4I", data, pos + 8, vs, rva, size, off)
        struct.pack_into("<I", data, pos + 36, flags)

    def va(offset):
        return BASE + (offset - 0x600 + 0x2000)

    # Registration table at 0x800, types array at 0x1000, records at 0x1200.
    reg = [0, 0, 0, 0, 0, 0, 40, va(0x1000), 0, 0, 3, va(0x1600), 3, va(0x1700), 0, 0]
    struct.pack_into("<16Q", data, 0x800, *reg)
    for i in range(40):
        struct.pack_into("<Q", data, 0x1000 + i * 8, va(0x1200 + i * 16))
    for i in range(3):
        struct.pack_into("<Q", data, 0x1700 + i * 8, va(0x1800 + 16 * i))
    for i, definition, bits in [(22, 1, 0x80110000), (37, 1, 0x80110006)]:
        struct.pack_into("<QI", data, 0x1200 + i * 16, definition, bits)
    data[0x1900 : 0x1900 + len(module_name)] = module_name
    struct.pack_into("<3Q", data, 0x1A00, va(0x1900), 1, va(0x1B00))
    struct.pack_into("<Q", data, 0x1B00, BASE + 0x1000)
    data[0x400] = 0xC3
    return meta, data


def test_non_adjacent_variant_is_resolved_by_native_definition_identity():
    meta, data = samples()
    report = NativeAudit(PE64(bytes(data)), Metadata(bytes(meta))).report(SPEC)
    field = report["enum_fields"][0]
    assert field["field_type"]["definition_index"] == 1
    assert field["field_type"]["type_index"] == 37
    assert field["canonical_type"]["type_index"] == 22
    assert field["field_type"]["attrs"] == 6
    assert field["identity_verified"] is True


def test_method_is_owned_by_image_and_resolves_token_rid_not_global_index():
    meta, data = samples()
    report = NativeAudit(PE64(bytes(data)), Metadata(bytes(meta))).report(SPEC)
    method = report["inventories"][0]["methods"][0]
    assert method["rva_hex"] == "0x1000"
    assert method["file_offset"] == 0x400
    assert method["image"] == "ClothSerializeData"
    assert report["runtime_call_order_verified"] is False


@pytest.mark.parametrize(
    "rva,size,offset", [(0x1000, 1, 0x400), (0x2000, 8, 0x600), (0x11FF, 1, 0x5FF)]
)
def test_file_backed_rva_mapping(rva, size, offset):
    _, data = samples()
    assert PE64(bytes(data)).offset(BASE + rva, size) == offset


@pytest.mark.parametrize(
    "rva,size", [(0x1200, 1), (0x5FFF, 2), (0x6000, 1), (0x1000, 0), (-1, 1)]
)
def test_bss_out_of_bounds_zero_length_and_gaps_rejected(rva, size):
    _, data = samples()
    with pytest.raises(ValueError):
        PE64(bytes(data)).offset(BASE + rva, size)


@pytest.mark.parametrize(
    "offset,raw",
    [
        (0, b"XX"),
        (0x80, b"BAD!"),
        (0x84, b"\x4c\x01"),
        (0x98, b"\x0b\x01"),
        (0x94, b"\x01\x00"),
        (0x84 + 2, b"\0\0"),
        (0x188 + 20, b"\xff\xff\xff\x7f"),
    ],
)
def test_invalid_pe_headers_rejected(offset, raw):
    _, data = samples()
    data[offset : offset + len(raw)] = raw
    with pytest.raises(ValueError):
        PE64(bytes(data))


def test_overlapping_raw_or_virtual_sections_rejected():
    _, data = samples()
    struct.pack_into("<I", data, 0x1B0 + 12, 0x1000)
    with pytest.raises(ValueError, match="overlap"):
        PE64(bytes(data))


@pytest.mark.parametrize(
    "offset,raw",
    [
        (0x800 + 6 * 8, struct.pack("<Q", 10)),
        (0x800 + 7 * 8, struct.pack("<Q", BASE + 0x6000)),
        (0x800 + 13 * 8, struct.pack("<Q", BASE + 0x6000)),
        (0x1700, struct.pack("<Q", BASE + 0x6000)),
    ],
)
def test_invalid_registration_is_not_accepted(offset, raw):
    meta, data = samples()
    data[offset : offset + len(raw)] = raw
    with pytest.raises(ValueError, match="registration"):
        NativeAudit(PE64(bytes(data)), Metadata(bytes(meta)))


def test_duplicate_registration_is_ambiguous():
    meta, data = samples()
    data[0x900:0x980] = data[0x800:0x880]
    with pytest.raises(ValueError, match="registration"):
        NativeAudit(PE64(bytes(data)), Metadata(bytes(meta)))


@pytest.mark.parametrize(
    "bits,definition",
    [(0x80110006, 2), (0x80120006, 1), (0xA0110006, 1), (0x81110006, 1)],
)
def test_wrong_class_kind_byref_or_modifiers_cannot_certify_enum(bits, definition):
    meta, data = samples()
    struct.pack_into("<QI", data, 0x1200 + 37 * 16, definition, bits)
    with pytest.raises(ValueError):
        NativeAudit(PE64(bytes(data)), Metadata(bytes(meta))).report(SPEC)


def test_bad_type_pointer_rejected():
    meta, data = samples()
    struct.pack_into("<Q", data, 0x1000 + 37 * 8, BASE + 0x6000)
    with pytest.raises(ValueError):
        NativeAudit(PE64(bytes(data)), Metadata(bytes(meta))).report(SPEC)


@pytest.mark.parametrize("offset,value", [(0x1A00 + 8, 2), (0x1B00, BASE + 0x2000)])
def test_module_count_and_executable_pointer_checks(offset, value):
    meta, data = samples()
    struct.pack_into("<Q", data, offset, value)
    with pytest.raises(ValueError, match="module"):
        NativeAudit(PE64(bytes(data)), Metadata(bytes(meta))).report(SPEC)


def test_null_method_pointer_is_explicit_not_an_invented_rva():
    meta, data = samples()
    struct.pack_into("<Q", data, 0x1B00, 0)
    report = NativeAudit(PE64(bytes(data)), Metadata(bytes(meta))).report(SPEC)
    assert report["inventories"][0]["methods"][0]["rva_hex"] is None


def test_missing_image_or_bad_method_token_stops():
    meta, data = samples()
    h = struct.unpack_from("<66I", meta)
    struct.pack_into("<I", meta, h[12] + 20, 0x04000001)
    with pytest.raises(ValueError):
        NativeAudit(PE64(bytes(data)), Metadata(bytes(meta))).report(SPEC)


def test_exclusive_report_and_inputs_are_preserved(tmp_path):
    meta, data = samples()
    m, b, out = tmp_path / "m", tmp_path / "b", tmp_path / "report.json"
    m.write_bytes(meta)
    b.write_bytes(data)
    export_files(b, m, out, SPEC)
    report = json.loads(out.read_text(encoding="utf-8"))
    assert report["attribute_bearing_native_field_types_resolved"] is True
    assert m.read_bytes() == meta and b.read_bytes() == data
    before = out.read_bytes()
    with pytest.raises(FileExistsError):
        export_files(b, m, out, SPEC)
    assert out.read_bytes() == before


def layout_sample():
    meta, data = samples()
    struct.pack_into("<QI", data, 0x1200 + 33 * 16, 2, 0x120000)
    struct.pack_into("<Q", data, 0x1600 + 2 * 8, BASE + 0x3800)
    struct.pack_into("<i", data, 0x1E00, 0x18)
    struct.pack_into("<Q", data, 0x2000, 0x20000000 | (33 << 1) | 1)
    return meta, data


def test_native_field_offset_and_static_attribute_are_separate():
    meta, data = layout_sample()
    audit = NativeAudit(PE64(bytes(data)), Metadata(bytes(meta)))
    layout = audit.field_layout("BeyondDynamicBone.ClothSerializeData")
    assert layout["fields"][0]["offset"] == 0x18
    assert layout["fields"][0]["is_static"] is False
    assert layout["fields"][0]["qualified_type"] == "BeyondDynamicBone.ClothUpdateMode"
    struct.pack_into("<QI", data, 0x1200 + 37 * 16, 1, 0x80110016)
    audit = NativeAudit(PE64(bytes(data)), Metadata(bytes(meta)))
    assert (
        audit.field_layout("BeyondDynamicBone.ClothSerializeData")["fields"][0][
            "is_static"
        ]
        is True
    )


def value_layout_sample():
    meta, data = layout_sample()
    h = struct.unpack_from("<66I", meta)
    struct.pack_into("<I", meta, h[40] + 2 * 92 + 84, 1)
    struct.pack_into("<QI", data, 0x1200 + 33 * 16, 2, 0x80110000)
    return meta, data


def test_value_layout_distinguishes_registration_and_unboxed_offsets():
    meta, data = value_layout_sample()
    layout = NativeAudit(PE64(bytes(data)), Metadata(bytes(meta))).field_layout(
        "BeyondDynamicBone.ClothSerializeData"
    )
    assert layout["is_value_type"] is True
    assert layout["fields"][0]["offset"] == 0x18
    assert layout["fields"][0]["offset_base"] == "boxed_object"
    assert layout["fields"][0]["unboxed_offset"] == 8
    struct.pack_into("<i", data, 0x1E00, 0x10)
    layout = NativeAudit(PE64(bytes(data)), Metadata(bytes(meta))).field_layout(
        "BeyondDynamicBone.ClothSerializeData"
    )
    assert layout["fields"][0]["unboxed_offset"] == 0


def test_value_static_offset_is_never_adjusted_for_object_header():
    meta, data = value_layout_sample()
    struct.pack_into("<QI", data, 0x1200 + 37 * 16, 1, 0x80110016)
    struct.pack_into("<i", data, 0x1E00, 0)
    field = NativeAudit(PE64(bytes(data)), Metadata(bytes(meta))).field_layout(
        "BeyondDynamicBone.ClothSerializeData"
    )["fields"][0]
    assert field["offset"] == 0
    assert field["offset_base"] == "static_storage"
    assert field["unboxed_offset"] is None


@pytest.mark.parametrize("change", ["kind", "flag", "byref", "mods", "pinned", "short"])
def test_value_layout_rejects_mismatched_identity_or_unboxed_basis(change):
    meta, data = value_layout_sample()
    bits = {
        "kind": 0x80120000,
        "flag": 0x00110000,
        "byref": 0xA0110000,
        "mods": 0x81110000,
        "pinned": 0xC0110000,
        "short": 0x80110000,
    }[change]
    struct.pack_into("<QI", data, 0x1200 + 33 * 16, 2, bits)
    if change == "short":
        struct.pack_into("<i", data, 0x1E00, 15)
    with pytest.raises(ValueError):
        NativeAudit(PE64(bytes(data)), Metadata(bytes(meta))).field_layout(
            "BeyondDynamicBone.ClothSerializeData"
        )


def test_class_layout_keeps_registered_object_relative_offset():
    meta, data = layout_sample()
    layout = NativeAudit(PE64(bytes(data)), Metadata(bytes(meta))).field_layout(
        "BeyondDynamicBone.ClothSerializeData"
    )
    assert layout["is_value_type"] is False
    assert layout["fields"][0]["offset_base"] == "object"
    assert layout["fields"][0]["unboxed_offset"] is None


@pytest.mark.parametrize("change", ["owner", "table", "offset"])
def test_field_layout_identity_bounds_and_unsupported_offsets_rejected(change):
    meta, data = layout_sample()
    if change == "owner":
        struct.pack_into("<Q", data, 0x1200 + 33 * 16, 1)
    elif change == "table":
        struct.pack_into("<Q", data, 0x1600 + 2 * 8, BASE + 0x7000)
    else:
        struct.pack_into("<i", data, 0x1E00, -1)
    with pytest.raises(ValueError):
        NativeAudit(PE64(bytes(data)), Metadata(bytes(meta))).field_layout(
            "BeyondDynamicBone.ClothSerializeData"
        )


def test_tagged_typeinfo_cell_resolves_owner_not_neighbour_or_name_guess():
    meta, data = layout_sample()
    result = NativeAudit(PE64(bytes(data)), Metadata(bytes(meta))).type_info_cell(
        BASE + 0x3A00, "BeyondDynamicBone.ClothSerializeData"
    )
    assert result["type_index"] == 33
    assert result["definition_index"] == 2


@pytest.mark.parametrize("value", [0x20000042, 0x40000043, 0x20000045, 1 << 40])
def test_invalid_typeinfo_usage_tag_or_target_rejected(value):
    meta, data = layout_sample()
    struct.pack_into("<Q", data, 0x2000, value)
    with pytest.raises(ValueError):
        NativeAudit(PE64(bytes(data)), Metadata(bytes(meta))).type_info_cell(
            BASE + 0x3A00, "BeyondDynamicBone.ClothSerializeData"
        )


def test_usage_cell_resolves_type_variant_and_method_definition_independently():
    meta, data = layout_sample()
    audit = NativeAudit(PE64(bytes(data)), Metadata(bytes(meta)))
    result = audit.metadata_usage_cell(BASE + 0x3A00)
    assert result["usage_kind"] == 1
    assert result["owner"] == "BeyondDynamicBone.ClothSerializeData"
    struct.pack_into("<Q", data, 0x2000, 0x20000000 | (37 << 1) | 1)
    result = NativeAudit(PE64(bytes(data)), Metadata(bytes(meta))).metadata_usage_cell(
        BASE + 0x3A00
    )
    assert result["owner"] == "BeyondDynamicBone.ClothUpdateMode"
    assert result["canonical_type_index"] == 22
    struct.pack_into("<Q", data, 0x2000, 0x60000001)
    result = NativeAudit(PE64(bytes(data)), Metadata(bytes(meta))).metadata_usage_cell(
        BASE + 0x3A00
    )
    assert result["usage_kind"] == 3
    assert result["method"]["method_index"] == 0
    assert result["method"]["rva_hex"] == "0x1000"
    assert result["runtime_pointer_inspected"] is False


@pytest.mark.parametrize(
    "value", [0, 0x20000042, 0xC0000001, 0x60000003, 0x200000FF, 1 << 40]
)
def test_usage_cell_rejects_unsupported_tag_kind_and_index(value):
    meta, data = layout_sample()
    struct.pack_into("<Q", data, 0x2000, value)
    with pytest.raises(ValueError):
        NativeAudit(PE64(bytes(data)), Metadata(bytes(meta))).metadata_usage_cell(
            BASE + 0x3A00
        )


def test_usage_cell_rejects_unaligned_address_and_mismatched_canonical_type():
    meta, data = layout_sample()
    with pytest.raises(ValueError):
        NativeAudit(PE64(bytes(data)), Metadata(bytes(meta))).metadata_usage_cell(
            BASE + 0x3A01
        )
    struct.pack_into("<Q", data, 0x2000, 0x20000000 | (37 << 1) | 1)
    struct.pack_into("<QI", data, 0x1200 + 22 * 16, 0, 0x80110000)
    with pytest.raises(ValueError):
        NativeAudit(PE64(bytes(data)), Metadata(bytes(meta))).metadata_usage_cell(
            BASE + 0x3A00
        )


def test_usage_cells_export_is_opt_in_and_never_a_runtime_pointer(tmp_path):
    meta, data = layout_sample()
    binary, metadata, out = (
        tmp_path / "b.dll",
        tmp_path / "m.dat",
        tmp_path / "out.json",
    )
    binary.write_bytes(data)
    metadata.write_bytes(meta)
    export_files(
        binary, metadata, out, {**SPEC, "metadata_usage_cells": [BASE + 0x3A00]}
    )
    result = json.loads(out.read_text())
    assert (
        result["metadata_usage_cells"][0]["owner"]
        == "BeyondDynamicBone.ClothSerializeData"
    )
    assert result["runtime_modified"] is False


def test_il2cpp_type_handle_usage_is_not_a_typeinfo_or_live_class_pointer():
    meta, data = layout_sample()
    struct.pack_into("<Q", data, 0x2000, 0x40000000 | (33 << 1) | 1)
    result = NativeAudit(PE64(bytes(data)), Metadata(bytes(meta))).metadata_usage_cell(
        BASE + 0x3A00
    )
    assert result["usage_kind"] == 2
    assert result["owner"] == "BeyondDynamicBone.ClothSerializeData"
    assert result["runtime_pointer_inspected"] is False


def test_usage_cell_rejects_primitive_type_and_method_declaring_owner_mismatch():
    meta, data = layout_sample()
    struct.pack_into("<QI", data, 0x1200 + 33 * 16, 2, 0x80000)
    with pytest.raises(ValueError):
        NativeAudit(PE64(bytes(data)), Metadata(bytes(meta))).metadata_usage_cell(
            BASE + 0x3A00
        )
    struct.pack_into("<Q", data, 0x2000, 0x60000001)
    header = struct.unpack_from("<66I", meta)
    struct.pack_into("<i", meta, header[12] + 4, 1)
    with pytest.raises(ValueError):
        NativeAudit(PE64(bytes(data)), Metadata(bytes(meta))).metadata_usage_cell(
            BASE + 0x3A00
        )


def literal_sample():
    meta, data = layout_sample()
    header = list(struct.unpack_from("<66I", meta))
    meta[264:264] = struct.pack("<Ii", 11, 0)
    for slot in range(4, 66, 2):
        if header[slot] >= 264:
            header[slot] += 8
    header[3] = 8
    header[4:6] = [len(meta), 11]
    meta.extend(b"LateUpdate!")
    struct.pack_into("<66I", meta, 0, *header)
    struct.pack_into("<Q", data, 0x2000, 0xA0000001)
    return meta, data


def test_usage_string_literal_uses_length_and_data_index_not_cstring_scan():
    meta, data = literal_sample()
    result = NativeAudit(PE64(bytes(data)), Metadata(bytes(meta))).metadata_usage_cell(
        BASE + 0x3A00
    )
    assert result["usage_kind"] == 5
    assert result["literal"] == "LateUpdate!"
    assert result["runtime_pointer_inspected"] is False


@pytest.mark.parametrize("change", ["index", "stride", "data_index", "length", "utf8"])
def test_usage_literal_rejects_unproved_table_or_payload(change):
    meta, data = literal_sample()
    if change == "index":
        struct.pack_into("<Q", data, 0x2000, 0xA0000003)
    elif change == "stride":
        struct.pack_into("<I", meta, 3 * 4, 7)
    elif change == "data_index":
        struct.pack_into("<i", meta, 268, -1)
    elif change == "length":
        struct.pack_into("<I", meta, 264, 12)
    else:
        meta[-1] = 0xFF
    with pytest.raises(ValueError):
        NativeAudit(PE64(bytes(data)), Metadata(bytes(meta))).metadata_usage_cell(
            BASE + 0x3A00
        )
