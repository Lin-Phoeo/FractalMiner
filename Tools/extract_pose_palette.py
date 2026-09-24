# -*- coding: utf-8 -*-
"""Extract per-draw bone palettes (vertex-stage 65536B cbuffer) from the
frame-6411 replay details export.

Each character draw carries a 256-slot palette at set 2 / binding 0. Slot i is
a struct whose first member is a 4x4 float matrix (row-vector convention,
translation in row 3, same layout note as the captured view matrix), followed
by extra float4 members whose meaning is not yet mapped.

Outputs:
  palette.json  - per event: all 256 slots (matrix + extra float4s)
  report.txt    - consistency checks across events and vs identity
"""
import json
import math
import os
import sys

CAP = r"A:/Hypergryph Launcher/games/Arknights Endfield/FractalMiner/Validation/Captures/tifuluosi-front-20260917"
SRC = os.path.join(CAP, "replay-details-01", "draw-details.json")
OUT = os.path.join(CAP, "pose-palette-01")
EVENTS = [776, 786, 835, 850, 860, 875]
PART = {776: "iris", 786: "body", 835: "cloth_01", 850: "cloth_02", 860: "face", 875: "hair"}

IDENT = [1.0, 0.0, 0.0, 0.0,
         0.0, 1.0, 0.0, 0.0,
         0.0, 0.0, 1.0, 0.0,
         0.0, 0.0, 0.0, 1.0]


def mat_of(slot):
    for m in slot.get("members", []):
        if m.get("rows") == 4 and m.get("columns") == 4 and len(m.get("value", [])) == 16:
            return m["value"]
    return None


def extras_of(slot):
    out = []
    for m in slot.get("members", []):
        if m.get("rows") == 4 and m.get("columns") == 4:
            continue
        v = m.get("value")
        if isinstance(v, list) and len(v) == 4:
            out.append(v)
    return out


def max_abs_diff(a, b):
    return max(abs(x - y) for x, y in zip(a, b))


def is_zero_mat(m):
    return all(abs(v) < 1e-30 for v in m)


def main():
    os.makedirs(OUT, exist_ok=True)
    data = json.load(open(SRC, encoding="utf-8"))
    draws = data["draws_and_dispatches"]

    palettes = {}
    report = []
    for ev in EVENTS:
        entry = next((e for e in draws if e["event"] == ev), None)
        if entry is None:
            report.append(f"event {ev}: NOT FOUND")
            continue
        vconst = [c for c in entry["stages"]["ShaderStage.Vertex"]["constants"]
                  if c.get("size") == 65536]
        if not vconst:
            report.append(f"event {ev}: no 65536B vertex cbuffer")
            continue
        slots = vconst[0]["variables"][0]["members"]
        mats = [mat_of(s) for s in slots]
        extras = [extras_of(s) for s in slots]
        n_null = sum(1 for m in mats if m is None)
        n_zero = sum(1 for m in mats if m is not None and is_zero_mat(m))
        n_ident = sum(1 for m in mats if m is not None and max_abs_diff(m, IDENT) < 1e-6)
        palettes[ev] = {"part": PART[ev], "matrices": mats, "extras": extras}
        report.append(
            f"event {ev} ({PART[ev]}): slots={len(slots)} null={n_null} "
            f"zero={n_zero} identity={n_ident} used={len(slots)-n_null-n_zero-n_ident}")

    # pairwise comparison against the hair draw (875)
    if 875 in palettes:
        ref = palettes[875]["matrices"]
        for ev in EVENTS:
            if ev == 875 or ev not in palettes:
                continue
            mats = palettes[ev]["matrices"]
            worst = 0.0
            worst_i = -1
            n_diff = 0
            for i, (a, b) in enumerate(zip(ref, mats)):
                if a is None or b is None:
                    continue
                d = max_abs_diff(a, b)
                if d > 1e-5:
                    n_diff += 1
                if d > worst:
                    worst, worst_i = d, i
            report.append(f"event {ev} vs 875: slots differing >1e-5 = {n_diff}, "
                          f"max diff = {worst:.6g} (slot {worst_i})")

    # slot usage profile: which slots are non-identity, non-zero
    if 875 in palettes:
        used = []
        for i, m in enumerate(palettes[875]["matrices"]):
            if m is None or is_zero_mat(m) or max_abs_diff(m, IDENT) < 1e-6:
                continue
            used.append(i)
        report.append(f"event 875 non-trivial slots: {used[:64]}"
                      + (" ..." if len(used) > 64 else ""))
        # first three used slots: translation rows for eyeballing
        for i in used[:3]:
            m = palettes[875]["matrices"][i]
            report.append(f"  slot {i}: t=({m[12]:.4f},{m[13]:.4f},{m[14]:.4f}) "
                          f"r00={m[0]:.4f} r01={m[1]:.4f} r02={m[2]:.4f}")

    slim = {str(ev): {"part": palettes[ev]["part"],
                      "matrices": palettes[ev]["matrices"],
                      "extras": palettes[ev]["extras"]}
            for ev in palettes}
    with open(os.path.join(OUT, "palette.json"), "w", encoding="utf-8") as f:
        json.dump(slim, f)
    with open(os.path.join(OUT, "report.txt"), "w", encoding="utf-8") as f:
        f.write("\n".join(report) + "\n")
    print("\n".join(report))
    print("wrote", os.path.join(OUT, "palette.json"))


if __name__ == "__main__":
    sys.exit(main())
