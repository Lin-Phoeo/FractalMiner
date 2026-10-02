"""Real x64 byte vectors; .pdata bounds are independent of method spacing."""

import hashlib
import json
import struct
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from audit_official_physics_calls import FunctionBounds, export_files, inspect_body
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
