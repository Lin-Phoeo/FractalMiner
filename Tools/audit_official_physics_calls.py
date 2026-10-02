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
from itertools import pairwise
from pathlib import Path
from typing import Any

from capstone import CS_ARCH_X86, CS_MODE_64, Cs
from capstone.x86_const import X86_OP_IMM, X86_OP_MEM, X86_REG_RCX, X86_REG_RIP
from export_official_physics_native import PE64


class FunctionBounds:
    def __init__(self, pe: PE64):
        self.pe = pe
        self._families: dict[int, list[int]] | None = None
        self._roots: dict[int, int] = {}
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

    def family(self, rva: int) -> list[int]:
        """Only group ranges explicitly related by UNW_FLAG_CHAININFO triples.

        Shared UNWIND_INFO addresses alone are NOT a family relation. No claim
        about stack unwinding operations, leaf bodies or control-flow coverage.
        """
        self.exact(rva)
        if self._families is None:
            parents = {}
            for start, (_, unwind) in self.rows.items():
                p = self.pe.offset(self.pe.base + unwind, 4)
                header = self.pe.data[p : p + 4]
                version, flags = header[0] & 7, header[0] >> 3
                if not flags & 4:
                    continue
                if version != 1 or flags & 3:
                    raise ValueError(
                        "Unsupported version/illegal handler flags in unwind chain"
                    )
                chain_va = self.pe.base + unwind + 4 + 2 * ((header[2] + 1) & ~1)
                cp = self.pe.offset(chain_va, 12)
                owner, end, owner_unwind = struct.unpack_from("<III", self.pe.data, cp)
                if self.rows.get(owner) != (end, owner_unwind):
                    raise ValueError(
                        "Unwind chain triple is not an actual RUNTIME_FUNCTION"
                    )
                parents[start] = owner
            families: dict[int, list[int]] = {}
            for start in self.rows:
                pending = set()
                current = start
                while current in parents and current not in self._roots:
                    if current in pending:
                        raise ValueError("Cyclic unwind chain")
                    pending.add(current)
                    current = parents[current]
                root = self._roots.get(current, current)
                for seen in pending | {start}:
                    self._roots[seen] = root
                families.setdefault(root, []).append(start)
            self._families = families
        return self._families[self._roots[rva]]


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
    transfers, indirect, branches, returns, references = [], [], [], [], []
    for ins in instructions:
        for index, operand in enumerate(ins.operands):
            if (
                operand.type != X86_OP_MEM
                or operand.mem.base != X86_REG_RIP
                or operand.mem.index
                or operand.mem.segment
            ):
                continue
            target = ins.address + ins.size + operand.mem.disp
            is_address = ins.mnemonic == "lea"
            try:
                file_offset = pe.offset(
                    pe.base + target, 1 if is_address else operand.size
                )
            except ValueError:
                file_offset = None
            references.append(
                {
                    "site_rva_hex": f"0x{ins.address:x}",
                    "instruction": ins.mnemonic,
                    "operand_index": index,
                    "reference_kind": "address" if is_address else "memory",
                    "access": 0 if is_address else operand.access,
                    "target_rva_hex": f"0x{target:x}",
                    "target_va_hex": f"0x{pe.base + target:x}",
                    "target_file_offset": file_offset,
                    "target_file_backed": file_offset is not None,
                    "address_aliases": aliases.get(target, []) if is_address else [],
                    "indirect_call_target_resolved": False,
                }
            )
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
        "rip_references": references,
        "control_flow_verified": False,
        "runtime_order_verified": False,
        "non_claim": "Linear instruction call sites only; reachability, branch predicates, virtual dispatch and dynamic order are not resolved.",
    }


def inspect_family(
    pe: PE64, bounds: FunctionBounds, rva: int, aliases: dict[int, list[dict[str, Any]]]
) -> dict[str, Any]:
    fragments = [
        inspect_body(pe, bounds, start, aliases) for start in bounds.family(rva)
    ]
    primary = next(f for f in fragments if int(f["rva_hex"], 16) == rva)
    return {
        "rva_hex": primary["rva_hex"],
        "file_offset": primary["file_offset"],
        "primary_range_bytes": primary["body_bytes"],
        "body_bytes": sum(f["body_bytes"] for f in fragments),
        "decoded_bytes": sum(f["decoded_bytes"] for f in fragments),
        "native_body_inspected": True,
        "fragment_membership_verified": True,
        "family_fragments": fragments,
        "direct_transfers": [e for f in fragments for e in f["direct_transfers"]],
        "indirect_transfers": [e for f in fragments for e in f["indirect_transfers"]],
        "conditional_branches": [
            e for f in fragments for e in f["conditional_branches"]
        ],
        "return_sites": [e for f in fragments for e in f["return_sites"]],
        "rip_references": [e for f in fragments for e in f["rip_references"]],
        "full_cfg_verified": False,
        "runtime_order_verified": False,
        "non_claim": "Unwind-related ranges, not a contiguous whole-function slice. Branch reachability, stack operations, out-of-family tail targets and leaf functions remain unproved.",
    }


def inspect_r10_preservation(pe: PE64, rva: int) -> dict[str, Any]:
    """Prove R10 aliases are untouched on a restricted local helper CFG.

    Follow every direct JE/JNE/JMP path inside 96 file-backed bytes. Refuse
    calls, indirect/system control, writes to R10 or RSP, overlapping decode
    and missing normal returns. No unwind/whole-method length or termination
    claim; valid ordinary non-self-modifying memory inputs are assumed.
    """
    p = pe.offset(pe.base + rva, 96, executable=True)
    code = pe.data[p : p + 96]
    md = Cs(CS_ARCH_X86, CS_MODE_64)
    md.detail = True
    pending, nodes, returns = [rva], {}, set()
    allowed = {
        "mov",
        "lea",
        "shr",
        "and",
        "or",
        "xor",
        "cmp",
        "test",
        "bts",
        "lock cmpxchg",
        "prefetchw",
        "nop",
    }
    forbidden_writes = {"r10", "r10d", "r10w", "r10b", "rsp", "esp", "sp", "spl"}
    while pending:
        address = pending.pop()
        if address in nodes:
            continue
        if not rva <= address < rva + 96:
            raise ValueError("Helper control escapes audited bound")
        ins = next(md.disasm(code[address - rva :], address, count=1), None)
        if ins is None or ins.address + ins.size > rva + 96:
            raise ValueError("Incomplete helper decode")
        _, writes = ins.regs_access()
        names = [ins.reg_name(reg) for reg in writes]
        if ins.mnemonic != "ret" and forbidden_writes.intersection(names):
            raise ValueError("Helper modifies R10 alias or return stack pointer")
        nodes[address] = {
            "site_rva_hex": f"0x{address:x}",
            "instruction": ins.mnemonic,
            "size": ins.size,
            "register_writes": names,
        }
        if ins.mnemonic == "ret" and not ins.operands:
            returns.add(address)
        elif ins.mnemonic in ("je", "jne", "jmp"):
            if len(ins.operands) != 1 or ins.operands[0].type != X86_OP_IMM:
                raise ValueError("Indirect helper branch")
            pending.append(ins.operands[0].imm)
            if ins.mnemonic != "jmp":
                pending.append(address + ins.size)
        elif ins.mnemonic in allowed:
            pending.append(address + ins.size)
        else:
            raise ValueError("Unsupported helper instruction/control")
    ordered = sorted(nodes)
    if not returns or any(a + nodes[a]["size"] > b for a, b in pairwise(ordered)):
        raise ValueError("Missing normal return or overlapping helper instructions")
    raw = b"".join(code[a - rva : a - rva + nodes[a]["size"]] for a in ordered)
    return {
        "rva_hex": f"0x{rva:x}",
        "reachable_bytes": len(raw),
        "reachable_instruction_bytes_sha256": hashlib.sha256(raw).hexdigest(),
        "instructions": [nodes[a] for a in ordered],
        "return_sites": [f"0x{a:x}" for a in sorted(returns)],
        "preserves_r10_on_supported_normal_paths": True,
        "termination_verified": False,
        "non_claim": "Restricted static register preservation only; valid non-self-modifying memory inputs assumed. Faults, exceptions, concurrent changes and complete method bounds are not certified.",
    }


def inspect_leaf_writes(pe: PE64, rva: int, layout: dict[str, Any]) -> dict[str, Any]:
    """Prove a narrow straight-line MOV32-immediate/RET entry path.

    This is not a general scan-until-ret: any other instruction, branch, call,
    receiver, width, unknown field or missing terminal immediately rejects it.
    Only primitive Int32/UInt32/Single initializer writes are accepted.
    """
    offset = pe.offset(pe.base + rva, 128, executable=True)
    allowed = {f["offset"]: f for f in layout["fields"] if not f["is_static"]}
    md = Cs(CS_ARCH_X86, CS_MODE_64)
    md.detail = True
    writes = []
    for ins in md.disasm(pe.data[offset : offset + 128], rva):
        if ins.mnemonic == "ret" and not ins.operands and writes:
            length = ins.address + ins.size - rva
            return {
                "rva_hex": f"0x{rva:x}",
                "file_offset": offset,
                "body_bytes": length,
                "decoded_bytes": length,
                "body_sha256": hashlib.sha256(
                    pe.data[offset : offset + length]
                ).hexdigest(),
                "native_body_inspected": True,
                "proof_kind": "restricted straight-line immediate primitive field writes ending in RET",
                "initializer_writes": writes,
                "runtime_frequency_verified": False,
                "non_claim": "Constructor entry writes only. Later setters/configuration/zero-filled fields are not certified here.",
            }
        if ins.mnemonic != "mov" or len(ins.operands) != 2:
            raise ValueError("Unsupported instruction in leaf initializer entry path")
        dest, source = ins.operands
        if (
            dest.type != X86_OP_MEM
            or source.type != X86_OP_IMM
            or dest.size != 4
            or dest.mem.base != X86_REG_RCX
            or dest.mem.index
            or dest.mem.segment
            or dest.mem.disp not in allowed
        ):
            raise ValueError("Unproved leaf receiver/field/width/immediate")
        field = allowed[dest.mem.disp]
        kind = field["native_type"]["kind"]
        if kind not in (8, 9, 12) or any(w["offset"] == dest.mem.disp for w in writes):
            raise ValueError("Unsupported or repeated initializer field")
        raw = struct.pack("<I", source.imm & 0xFFFFFFFF)
        value = struct.unpack("<f" if kind == 12 else "<i" if kind == 8 else "<I", raw)[
            0
        ]
        writes.append(
            {
                "field": field["name"],
                "offset": dest.mem.disp,
                "site_rva_hex": f"0x{ins.address:x}",
                "raw_hex": raw.hex(),
                "value": value,
            }
        )
    raise ValueError("No proved terminal leaf initializer path within audit bound")


def inspect_leaf_counter(
    pe: PE64, rva: int, layout: dict[str, Any], reset: bool
) -> dict[str, Any]:
    """Accept only a known instance Int32 INC/RET or MOV-zero/RET pair.

    This certifies that two-instruction entry path, not a whole-function
    length inferred from neighbouring entries/padding. Faults, invocation
    count and external concurrent writes are outside this offline proof.
    """
    fields = [
        f for f in layout["fields"] if f["name"] == "<FixedUpdateCount>k__BackingField"
    ]
    if (
        len(fields) != 1
        or fields[0]["is_static"]
        or fields[0]["native_type"]["kind"] != 8
    ):
        raise ValueError("Counter requires unique native instance Int32 identity")
    field = fields[0]
    offset = pe.offset(pe.base + rva, 16, executable=True)
    md = Cs(CS_ARCH_X86, CS_MODE_64)
    md.detail = True
    pair = list(md.disasm(pe.data[offset : offset + 16], rva, count=2))
    if len(pair) != 2 or pair[1].mnemonic != "ret" or pair[1].operands:
        raise ValueError("Counter requires exactly one write followed by plain RET")
    ins = pair[0]
    if ins.mnemonic != ("mov" if reset else "inc") or len(ins.operands) != (
        2 if reset else 1
    ):
        raise ValueError("Unproved counter write operation")
    dest = ins.operands[0]
    if (
        dest.type != X86_OP_MEM
        or dest.size != 4
        or dest.mem.base != X86_REG_RCX
        or dest.mem.index
        or dest.mem.segment
        or dest.mem.disp != field["offset"]
    ):
        raise ValueError("Unproved counter receiver/field/width")
    if reset and (ins.operands[1].type != X86_OP_IMM or ins.operands[1].imm != 0):
        raise ValueError("Counter reset must write immediate zero")
    length = sum(i.size for i in pair)
    return {
        "rva_hex": f"0x{rva:x}",
        "file_offset": offset,
        "body_bytes": length,
        "decoded_bytes": length,
        "body_sha256": hashlib.sha256(pe.data[offset : offset + length]).hexdigest(),
        "native_body_inspected": True,
        "proof_kind": "restricted two-instruction instance Int32 counter entry path",
        "counter_write": {
            "field": field["name"],
            "offset": field["offset"],
            "site_rva_hex": f"0x{rva:x}",
            "operation": "reset_zero" if reset else "increment_modulo_2_32",
        },
        "return_sites": [f"0x{pair[1].address:x}"],
        "runtime_order_verified": False,
        "non_claim": "Valid ordinary receiver assumed. No invocation rate, concurrent write, fault or full scheduler proof.",
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
                "Initialize",
                ".cctor",
            ],
            "ClothManager": [
                "Initialize",
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
                "Initialize",
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
    + [
        "BeyondDynamicBone.MagicaManager+<>c.<SetCustomGameLoop>b__50_" + str(i)
        for i in range(7)
    ]
    + [
        "UnityEngine.LowLevel.PlayerLoop." + name
        for name in ("GetCurrentPlayerLoop", "SetPlayerLoop")
    ]
    + ["BeyondDynamicBone.PlayerLoopUtils.AddPlayerLoop"]
    + [
        "Unity.Jobs.JobHandle." + name
        for name in (
            "Complete",
            "CrossFrameComplete",
            "ScheduleBatchedCrossFrameJobsAndComplete",
        )
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
    layouts = {x["owner"]: x for x in manifest.get("field_layouts", [])}
    for key in selections:
        matches = methods.get(key, [])
        if len(matches) != 1 or not matches[0]["rva_hex"]:
            raise ValueError("Missing/ambiguous/null selected native method")
        rva = int(matches[0]["rva_hex"], 16)
        if rva not in bounds.rows:
            if (
                key == "BeyondDynamicBone.TimeManager..ctor"
                and "BeyondDynamicBone.TimeManager" in layouts
            ):
                bodies.append(
                    {
                        "method": key,
                        **inspect_leaf_writes(
                            pe, rva, layouts["BeyondDynamicBone.TimeManager"]
                        ),
                    }
                )
                continue
            if (
                key
                in (
                    "BeyondDynamicBone.TimeManager.AfterFixedUpdate",
                    "BeyondDynamicBone.TimeManager.AfterRenderring",
                )
                and "BeyondDynamicBone.TimeManager" in layouts
            ):
                bodies.append(
                    {
                        "method": key,
                        **inspect_leaf_counter(
                            pe,
                            rva,
                            layouts["BeyondDynamicBone.TimeManager"],
                            key.endswith("AfterRenderring"),
                        ),
                    }
                )
                continue
            bodies.append(
                {
                    "method": key,
                    "rva_hex": f"0x{rva:x}",
                    "native_body_inspected": False,
                    "pending_reason": "No exact RUNTIME_FUNCTION entry; no guessed body",
                }
            )
        else:
            bodies.append({"method": key, **inspect_family(pe, bounds, rva, aliases)})
    result = {
        "schema_version": 3,
        "binary": str(binary.resolve()),
        "binary_sha256": hashlib.sha256(data).hexdigest(),
        "native_manifest": str(native_manifest.resolve()),
        "native_manifest_sha256": hashlib.sha256(manifest_bytes).hexdigest(),
        "capstone_version": importlib.metadata.version("capstone"),
        "bodies": bodies,
        "helper_register_proofs": [inspect_r10_preservation(pe, 0x26B40)]
        if any(
            b["method"] == "BeyondDynamicBone.MagicaManager..cctor"
            and any(
                t["target_rva_hex"] == "0x26b40" for t in b.get("direct_transfers", [])
            )
            for b in bodies
        )
        else [],
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
