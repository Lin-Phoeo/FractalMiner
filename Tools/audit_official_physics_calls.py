"""Bounded offline x64 call-site inspection; not a runtime order/CFG proof.

Requires capstone==5.0.9. Reads exact AMD64 RUNTIME_FUNCTION ranges from the PE
exception directory, never infers body length from adjacent managed methods.
No DLL execution, attachment, bytecode publication or game file writes.
"""

import argparse
import hashlib
import importlib.metadata
import json
import struct
from pathlib import Path
from typing import Any

from capstone import CS_ARCH_X86, CS_MODE_64, Cs
from capstone.x86_const import X86_OP_IMM
from export_official_physics_native import PE64


class FunctionBounds:
    def __init__(self, pe: PE64):
        pos = struct.unpack_from("<I", pe.data, 60)[0] + 24
        count = struct.unpack_from("<I", pe.data, pos + 108)[0]
        optional_size = struct.unpack_from("<H", pe.data, pos - 4)[0]
        if count < 4 or optional_size < 112 + 4 * 8:
            raise ValueError("No complete AMD64 exception directory")
        rva, size = struct.unpack_from("<II", pe.data, pos + 112 + 3 * 8)
        if not rva or not size or size % 12:
            raise ValueError("Invalid RUNTIME_FUNCTION directory")
        offset = pe.offset(pe.base + rva, size)
        self.rows: dict[int, tuple[int, int]] = {}
        previous = -1
        for start, end, unwind in struct.iter_unpack(
            "<III", pe.data[offset : offset + size]
        ):
            if start < previous or start >= end or start in self.rows:
                raise ValueError("Invalid/overlapping RUNTIME_FUNCTION ranges")
            pe.offset(pe.base + start, end - start, executable=True)
            pe.offset(pe.base + unwind, 4)
            self.rows[start] = (end, unwind)
            previous = end

    def exact(self, rva: int) -> tuple[int, int]:
        if rva not in self.rows:
            raise ValueError("No exact RUNTIME_FUNCTION entry: refuse guessed bounds")
        return self.rows[rva]


def inspect_body(
    pe: PE64, bounds: FunctionBounds, rva: int, aliases: dict[int, list[dict[str, Any]]]
) -> dict[str, Any]:
    end, unwind = bounds.exact(rva)
    offset = pe.offset(pe.base + rva, end - rva, executable=True)
    code = pe.data[offset : offset + end - rva]
    disassembler = Cs(CS_ARCH_X86, CS_MODE_64)
    disassembler.detail = True
    instructions = list(disassembler.disasm(code, rva))
    if sum(i.size for i in instructions) != len(code):
        raise ValueError("Incomplete instruction decode; refuse partial body")
    transfers, indirect, branches, returns = [], [], [], []
    for ins in instructions:
        if ins.mnemonic.startswith("ret"):
            returns.append(f"0x{ins.address:x}")
        if ins.mnemonic in ("call", "jmp"):
            row: dict[str, Any] = {
                "site_rva_hex": f"0x{ins.address:x}",
                "kind": ins.mnemonic,
            }
            if len(ins.operands) == 1 and ins.operands[0].type == X86_OP_IMM:
                target = ins.operands[0].imm
                try:
                    pe.offset(pe.base + target, executable=True)
                    valid = True
                except ValueError:
                    valid = False
                row.update(
                    {
                        "target_rva_hex": f"0x{target:x}",
                        "target_aliases": aliases.get(target, []),
                        "target_file_backed_executable": valid,
                    }
                )
                transfers.append(row)
            else:
                row["operand"] = ins.op_str
                indirect.append(row)
        elif ins.mnemonic.startswith("j") or ins.mnemonic.startswith("loop"):
            target = (
                ins.operands[0].imm
                if ins.operands and ins.operands[0].type == X86_OP_IMM
                else None
            )
            branches.append(
                {
                    "site_rva_hex": f"0x{ins.address:x}",
                    "kind": ins.mnemonic,
                    "target_rva_hex": f"0x{target:x}" if target is not None else None,
                }
            )
    return {
        "rva_hex": f"0x{rva:x}",
        "end_rva_hex": f"0x{end:x}",
        "unwind_rva_hex": f"0x{unwind:x}",
        "file_offset": offset,
        "body_bytes": len(code),
        "decoded_bytes": sum(i.size for i in instructions),
        "instruction_count": len(instructions),
        "body_sha256": hashlib.sha256(code).hexdigest(),
        "native_body_inspected": True,
        "direct_transfers": transfers,
        "indirect_transfers": indirect,
        "conditional_branches": branches,
        "return_sites": returns,
        "control_flow_verified": False,
        "runtime_order_verified": False,
        "non_claim": "Linear instruction call sites only; reachability, branch predicates, virtual dispatch and dynamic order are not resolved.",
    }


DEFAULT_METHODS = (
    [
        "BeyondDynamicBone." + owner + "." + method
        for owner, methods in {
            "MagicaManager": [
                "InitCustomGameLoop",
                "SetCustomGameLoop",
                "CheckRegist",
                "SetSimulationFrequency",
                "SetUpdateLocation",
                "SetUseCrossFrameJob",
                "DoAOVAfterAnimatorUpdate",
            ],
            "ClothManager": [
                "ClothUpdate",
                "CompleteMasterJob",
                "ForceCompleteAllJob",
                "OnEarlyClothUpdate",
                "OnAfterUpdate",
                "OnBeforeLateUpdate",
                "OnAfterLateUpdate",
            ],
            "TimeManager": [
                "FrameUpdate",
                "AfterFixedUpdate",
                "AfterRenderring",
                ".ctor",
            ],
            "DynamicBoneTransformManager": [
                "ReadAnimatorBufferData",
                "WriteAnimatorBufferData",
                "ReadTransform",
                "WriteTransform",
                "CopyDoubleBuffer",
                "WriteDoubleBufferTransform",
            ],
            "SimulationManager": [
                "PreSimulationUpdate",
                "SimulationStepUpdate",
                "CalcDisplayPosition",
            ],
            "TeamManager": [
                "UpdateTeamAnimatorData",
                "ShouldResetSimulationToAnimationPose",
                "ApplyWeightDrivenSimulationPosePolicy",
            ],
        }.items()
        for method in methods
    ]
    + ["Beyond.NPC.Animation.NPCCPUAnimator._UpdateBeyondBoneCloth"]
    + [
        "Beyond.NPC.Animation.ClothCalculator." + name
        for name in ["CalcCloth", "UpdateDynamicBone", "UpdateBeyondClothEnabled"]
    ]
)


def export_files(
    binary: Path,
    native_manifest: Path,
    output: Path,
    selections: list[str] = DEFAULT_METHODS,
) -> None:
    if output.exists():
        raise FileExistsError(f"Refusing to overwrite {output}")
    data, manifest_bytes = binary.read_bytes(), native_manifest.read_bytes()
    manifest = json.loads(manifest_bytes)
    if hashlib.sha256(data).hexdigest() != manifest["sources"]["binary_sha256"]:
        raise ValueError("Native manifest binary SHA256 mismatch")
    pe = PE64(data)
    bounds = FunctionBounds(pe)
    aliases: dict[int, list[dict[str, Any]]] = {}
    methods: dict[str, list[dict[str, Any]]] = {}
    for row in manifest["inventories"]:
        for method in row["methods"]:
            key = row["qualified_name"] + "." + method["name"]
            methods.setdefault(key, []).append(method)
            if method["rva_hex"]:
                rva = int(method["rva_hex"], 16)
                if pe.offset(pe.base + rva, executable=True) != method[
                    "file_offset"
                ] or pe.base + rva != int(method["va_hex"], 16):
                    raise ValueError("Native manifest address identity mismatch")
                aliases.setdefault(rva, []).append(
                    {
                        "owner": row["qualified_name"],
                        "method": method["name"],
                        "method_index": method.get("method_index"),
                        "image": method.get("image"),
                        "token_hex": method.get("token_hex"),
                    }
                )
    bodies = []
    for key in selections:
        matches = methods.get(key, [])
        if len(matches) != 1 or not matches[0]["rva_hex"]:
            raise ValueError("Missing/ambiguous/null selected native method")
        rva = int(matches[0]["rva_hex"], 16)
        if rva not in bounds.rows:
            bodies.append(
                {
                    "method": key,
                    "rva_hex": f"0x{rva:x}",
                    "native_body_inspected": False,
                    "pending_reason": "No exact RUNTIME_FUNCTION entry; no guessed body",
                }
            )
        else:
            bodies.append({"method": key, **inspect_body(pe, bounds, rva, aliases)})
    result = {
        "schema_version": 1,
        "binary": str(binary.resolve()),
        "binary_sha256": hashlib.sha256(data).hexdigest(),
        "native_manifest": str(native_manifest.resolve()),
        "native_manifest_sha256": hashlib.sha256(manifest_bytes).hexdigest(),
        "capstone_version": importlib.metadata.version("capstone"),
        "bodies": bodies,
        "runtime_modified": False,
        "runtime_call_order_verified": False,
        "simulation_frequency_verified": False,
        "full_cfg_verified": False,
        "non_claim": "Entry identities require the referenced native audit. Call-site file order is not an unconditional runtime pipeline. Solver mathematics and selected character paths remain pending.",
    }
    with output.open("x", encoding="utf-8", newline="\n") as stream:
        json.dump(result, stream, ensure_ascii=False, indent=2, allow_nan=False)
        stream.write("\n")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--binary", type=Path, required=True)
    parser.add_argument("--native-manifest", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    export_files(args.binary, args.native_manifest, args.output)
    print(f"Offline bounded native call-site audit: {args.output}")


if __name__ == "__main__":
    main()
