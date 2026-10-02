"""Real x64 byte vectors; .pdata bounds are independent of method spacing."""

import hashlib
import json
import struct
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from audit_official_physics_calls import (
    FunctionBounds,
    export_files,
    inspect_body,
    inspect_family,
    inspect_leaf_writes,
    inspect_r10_preservation,
)
from export_official_physics_native import PE64
from test_export_official_physics_native import BASE, samples


def native_sample():
    _, data = samples()
    # Direct call + indirect call + conditional branch + return + truncated byte.
    code = bytes.fromhex("e81b000000ffd07401c3")
    data[0x400 : 0x400 + len(code)] = code
    struct.pack_into("<I", data, 0x98 + 108, 16)
    struct.pack_into("<II", data, 0x98 + 112 + 3 * 8, 0x3600, 24)
    struct.pack_into(
        "<6I", data, 0x1C00, 0x1000, 0x100A, 0x3700, 0x1020, 0x1021, 0x3700
    )
    data[0x1D00] = 1
    return data


def test_calls_branches_and_indirect_calls_are_distinguished():
    pe = PE64(bytes(native_sample()))
    bounds = FunctionBounds(pe)
    aliases = {0x1020: [{"owner": "A", "method": "M"}, {"owner": "B", "method": "N"}]}
    result = inspect_body(pe, bounds, 0x1000, aliases)
    assert result["body_bytes"] == 10
    assert result["decoded_bytes"] == 10
    assert result["direct_transfers"][0]["target_rva_hex"] == "0x1020"
    assert len(result["direct_transfers"][0]["target_aliases"]) == 2
    assert result["indirect_transfers"][0]["kind"] == "call"
    assert result["conditional_branches"][0]["target_rva_hex"] == "0x100a"
    assert result["return_sites"] == ["0x1009"]
    assert result["control_flow_verified"] is False


@pytest.mark.parametrize("rva", [0x1001, 0x1010, 0x1030])
def test_interior_and_unregistered_addresses_do_not_invent_function_bounds(rva):
    pe = PE64(bytes(native_sample()))
    with pytest.raises(ValueError):
        FunctionBounds(pe).exact(rva)


@pytest.mark.parametrize(
    "offset,value",
    [
        (0x98 + 108, 3),
        (0x98 + 112 + 3 * 8, 0),
        (0x98 + 112 + 3 * 8 + 4, 23),
        (0x1C00 + 4, 0x1000),
        (0x1C00 + 8, 0x7000),
        (0x1C00 + 12, 0x1000),
        (0x1C00 + 16, 0x7000),
    ],
)
def test_bad_exception_table_stops(offset, value):
    data = native_sample()
    struct.pack_into("<I", data, offset, value)
    with pytest.raises(ValueError):
        FunctionBounds(PE64(bytes(data)))


def test_partial_instruction_decode_is_not_accepted():
    data = native_sample()
    data[0x409] = 0x0F
    pe = PE64(bytes(data))
    with pytest.raises(ValueError, match="decode"):
        inspect_body(pe, FunctionBounds(pe), 0x1000, {})


def test_unmapped_direct_target_is_retained_but_not_certified():
    data = native_sample()
    struct.pack_into("<i", data, 0x401, 0x7000 - 0x1005)
    pe = PE64(bytes(data))
    transfer = inspect_body(pe, FunctionBounds(pe), 0x1000, {})["direct_transfers"][0]
    assert transfer["target_file_backed_executable"] is False


def test_report_hash_entry_point_and_exclusive_write_guards(tmp_path):
    data = native_sample()
    binary, native, out = (
        tmp_path / "bin",
        tmp_path / "native.json",
        tmp_path / "calls.json",
    )
    binary.write_bytes(data)
    source = {
        "sources": {"binary_sha256": hashlib.sha256(data).hexdigest()},
        "inventories": [
            {
                "qualified_name": "A",
                "methods": [
                    {
                        "name": "M",
                        "rva_hex": "0x1000",
                        "va_hex": hex(BASE + 0x1000),
                        "file_offset": 0x400,
                        "method_index": 0,
                        "image": "Test",
                        "token_hex": "0x06000001",
                    }
                ],
            }
        ],
    }
    native.write_text(json.dumps(source), encoding="utf-8")
    export_files(binary, native, out, ["A.M"])
    report = json.loads(out.read_text(encoding="utf-8"))
    assert report["bodies"][0]["body_bytes"] == 10
    assert report["runtime_call_order_verified"] is False
    before = out.read_bytes()
    with pytest.raises(FileExistsError):
        export_files(binary, native, out, ["A.M"])
    assert out.read_bytes() == before and binary.read_bytes() == data


def test_valid_entry_without_unwind_bounds_is_explicitly_pending(tmp_path):
    data = native_sample()
    binary, native, out = (
        tmp_path / "bin",
        tmp_path / "native.json",
        tmp_path / "calls.json",
    )
    binary.write_bytes(data)
    source = {
        "sources": {"binary_sha256": hashlib.sha256(data).hexdigest()},
        "inventories": [
            {
                "qualified_name": "A",
                "methods": [
                    {
                        "name": "Leaf",
                        "rva_hex": "0x1025",
                        "va_hex": hex(BASE + 0x1025),
                        "file_offset": 0x425,
                    }
                ],
            }
        ],
    }
    native.write_text(json.dumps(source), encoding="utf-8")
    export_files(binary, native, out, ["A.Leaf"])
    body = json.loads(out.read_text(encoding="utf-8"))["bodies"][0]
    assert body["native_body_inspected"] is False
    assert body["pending_reason"] == "No exact RUNTIME_FUNCTION entry; no guessed body"


@pytest.mark.parametrize("change", ["hash", "entry", "missing", "duplicate", "null"])
def test_mismatched_or_ambiguous_native_manifest_is_rejected(tmp_path, change):
    data = native_sample()
    binary, native, out = tmp_path / "bin", tmp_path / "native.json", tmp_path / "out"
    binary.write_bytes(data)
    source = {
        "sources": {"binary_sha256": hashlib.sha256(data).hexdigest()},
        "inventories": [
            {
                "qualified_name": "A",
                "methods": [
                    {
                        "name": "M",
                        "rva_hex": "0x1000",
                        "va_hex": hex(BASE + 0x1000),
                        "file_offset": 0x400,
                    }
                ],
            }
        ],
    }
    if change == "hash":
        source["sources"]["binary_sha256"] = "0" * 64
    elif change == "entry":
        source["inventories"][0]["methods"][0]["file_offset"] = 0x401
    elif change == "missing":
        source["inventories"][0]["methods"][0]["name"] = "Other"
    elif change == "duplicate":
        source["inventories"] *= 2
    elif change == "null":
        source["inventories"][0]["methods"][0]["rva_hex"] = None
    native.write_text(json.dumps(source), encoding="utf-8")
    with pytest.raises(ValueError):
        export_files(binary, native, out, ["A.M"])
    assert not out.exists()


def chained_sample():
    data = native_sample()
    # Odd unwind-code count: CHAININFO follows the padded two-slot array.
    struct.pack_into("<I", data, 0x98 + 112 + 3 * 8 + 4, 48)
    struct.pack_into(
        "<6I", data, 0x1C18, 0x1050, 0x1056, 0x3740, 0x1060, 0x1061, 0x3780
    )
    data[0x450:0x456] = bytes.fromhex("e8cbffffffc3")
    data[0x460] = 0xC3
    data[0x1D40:0x1D44] = bytes([0x21, 0, 1, 0])
    struct.pack_into("<3I", data, 0x1D48, 0x1000, 0x100A, 0x3700)
    data[0x1D80:0x1D84] = bytes([0x21, 0, 0, 0])
    struct.pack_into("<3I", data, 0x1D84, 0x1050, 0x1056, 0x3740)
    return data


def test_chain_family_includes_cold_nested_ranges_but_not_shared_unwind_peer():
    pe = PE64(bytes(chained_sample()))
    bounds = FunctionBounds(pe)
    assert bounds.family(0x1000) == [0x1000, 0x1050, 0x1060]
    assert bounds.family(0x1050) == [0x1000, 0x1050, 0x1060]
    assert bounds.family(0x1020) == [0x1020]


def test_family_report_reads_extra_call_and_does_not_certify_runtime_order():
    pe = PE64(bytes(chained_sample()))
    result = inspect_family(pe, FunctionBounds(pe), 0x1000, {})
    assert len(result["family_fragments"]) == 3
    assert result["body_bytes"] == 17
    assert len(result["direct_transfers"]) == 2
    assert result["primary_range_bytes"] == 10
    assert result["fragment_membership_verified"] is True
    assert result["full_cfg_verified"] is False


@pytest.mark.parametrize(
    "offset,value", [(0x1D48, 0x1010), (0x1D4C, 0x100B), (0x1D50, 0x3780)]
)
def test_chained_runtime_triple_must_match_actual_pdata_entry(offset, value):
    data = chained_sample()
    struct.pack_into("<I", data, offset, value)
    with pytest.raises(ValueError, match="chain"):
        FunctionBounds(PE64(bytes(data))).family(0x1000)


def test_chained_unwind_cycle_rejected():
    data = chained_sample()
    struct.pack_into("<3I", data, 0x1D48, 0x1060, 0x1061, 0x3780)
    with pytest.raises(ValueError, match="chain"):
        FunctionBounds(PE64(bytes(data))).family(0x1000)


@pytest.mark.parametrize("header", [0x29, 0x31, 0x22])
def test_illegal_handler_flags_or_unsupported_chained_version_rejected(header):
    data = chained_sample()
    data[0x1D40] = header
    with pytest.raises(ValueError, match="chain"):
        FunctionBounds(PE64(bytes(data))).family(0x1000)


def leaf_sample():
    data = native_sample()
    raw = bytes.fromhex("c741105a000000c7411403000000c3")
    data[0x480 : 0x480 + len(raw)] = raw
    fields = [
        {"name": name, "offset": offset, "is_static": False, "native_type": {"kind": 8}}
        for name, offset in [("rate", 0x10), ("steps", 0x14)]
    ]
    return data, {"fields": fields}


def test_leaf_initializer_uses_terminal_path_not_neighbour_distance():
    data, layout = leaf_sample()
    result = inspect_leaf_writes(PE64(bytes(data)), 0x1080, layout)
    assert result["body_bytes"] == 15
    assert [(x["field"], x["value"]) for x in result["initializer_writes"]] == [
        ("rate", 90),
        ("steps", 3),
    ]
    assert result["runtime_frequency_verified"] is False


@pytest.mark.parametrize(
    "change", ["branch", "call", "unknown_field", "wrong_receiver", "no_ret"]
)
def test_leaf_initializer_rejects_any_unproved_entry_path(change):
    data, layout = leaf_sample()
    if change == "branch":
        data[0x480:0x482] = bytes.fromhex("eb00")
    elif change == "call":
        data[0x480:0x485] = bytes.fromhex("e800000000")
    elif change == "unknown_field":
        data[0x482] = 0x18
    elif change == "wrong_receiver":
        data[0x481] = 0x42
    else:
        data[0x48E] = 0x90
    with pytest.raises(ValueError):
        inspect_leaf_writes(PE64(bytes(data)), 0x1080, layout)


def test_rip_references_distinguish_address_from_reads_writes_and_indirect_slot():
    data = native_sample()
    raw = bytes.fromhex("488d0519000000488b05120000004889050b000000ff1505000000c3")
    data[0x400 : 0x400 + len(raw)] = raw
    struct.pack_into("<I", data, 0x1C04, 0x1000 + len(raw))
    pe = PE64(bytes(data))
    result = inspect_body(pe, FunctionBounds(pe), 0x1000, {0x1020: [{"method": "M"}]})
    refs = result["rip_references"]
    assert [r["reference_kind"] for r in refs] == [
        "address",
        "memory",
        "memory",
        "memory",
    ]
    assert [r["access"] for r in refs] == [0, 1, 2, 1]
    assert all(r["target_rva_hex"] == "0x1020" for r in refs)
    assert refs[0]["address_aliases"] == [{"method": "M"}]
    assert refs[1]["address_aliases"] == []
    assert refs[3]["indirect_call_target_resolved"] is False


@pytest.mark.parametrize(
    "raw,target", [("488d05f9ffffffc3", "0x1000"), ("488b05f96f0000c3", "0x8000")]
)
def test_rip_signed_displacement_and_unmapped_reference(raw, target):
    data = native_sample()
    code = bytes.fromhex(raw)
    data[0x400 : 0x400 + len(code)] = code
    struct.pack_into("<I", data, 0x1C04, 0x1000 + len(code))
    pe = PE64(bytes(data))
    ref = inspect_body(pe, FunctionBounds(pe), 0x1000, {})["rip_references"][0]
    assert ref["target_rva_hex"] == target
    assert ref["target_file_backed"] == (target == "0x1000")


def test_register_and_segment_based_addresses_are_not_rip_file_references():
    data = native_sample()
    code = bytes.fromhex("488b0164488b0500000000c3")
    data[0x400 : 0x400 + len(code)] = code
    struct.pack_into("<I", data, 0x1C04, 0x1000 + len(code))
    pe = PE64(bytes(data))
    assert inspect_body(pe, FunctionBounds(pe), 0x1000, {})["rip_references"] == []


def test_family_retains_rip_references_in_cold_range():
    data = chained_sample()
    code = bytes.fromhex("488d05a9ffffffc3")
    data[0x450 : 0x450 + len(code)] = code
    struct.pack_into("<I", data, 0x1C1C, 0x1058)
    struct.pack_into("<I", data, 0x1D88, 0x1058)
    pe = PE64(bytes(data))
    result = inspect_family(pe, FunctionBounds(pe), 0x1000, {})
    assert result["rip_references"][0]["site_rva_hex"] == "0x1050"
    assert result["rip_references"][0]["target_rva_hex"] == "0x1000"


def test_narrow_helper_proves_r10_preservation_through_all_local_branch_paths():
    data = native_sample()
    data[0x480:0x488] = bytes.fromhex("74054831c0ebf9c3")
    result = inspect_r10_preservation(PE64(bytes(data)), 0x1080)
    assert result["preserves_r10_on_supported_normal_paths"] is True
    assert result["return_sites"] == ["0x1087"]
    assert result["reachable_bytes"] == 8
    assert result["termination_verified"] is False


@pytest.mark.parametrize(
    "raw",
    [
        "41ba01000000c3",
        "41b201c3",
        "4d31d2c3",
        "e800000000c3",
        "ffe0",
        "e97f000000",
        "0f05c3",
        "ebfe",
        "74014831c0c3",
    ],
)
def test_helper_rejects_alias_writes_calls_unknown_control_and_instruction_overlap(raw):
    data = native_sample()
    code = bytes.fromhex(raw)
    data[0x480 : 0x480 + len(code)] = code
    with pytest.raises(ValueError):
        inspect_r10_preservation(PE64(bytes(data)), 0x1080)


@pytest.mark.parametrize("raw", ["4889c4c3", "664531d2c3", "c20400"])
def test_helper_rejects_stack_pointer_r10_word_and_nonstandard_return(raw):
    data = native_sample()
    code = bytes.fromhex(raw)
    data[0x480 : 0x480 + len(code)] = code
    with pytest.raises(ValueError):
        inspect_r10_preservation(PE64(bytes(data)), 0x1080)


def test_helper_follows_reachable_branches_not_linear_padding_or_dead_instructions():
    data = native_sample()
    data[0x480:0x486] = bytes.fromhex("eb034531d2c3")
    result = inspect_r10_preservation(PE64(bytes(data)), 0x1080)
    assert result["reachable_bytes"] == 3
    assert len(result["instructions"]) == 2
