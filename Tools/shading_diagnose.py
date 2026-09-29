# -*- coding: utf-8 -*-
"""Diagnostic only: report per-family colour means and same-pixel errors.

Region means and signed overlap bias do not establish shading fidelity or isolate
pose errors: opposite errors cancel, and visibility, normals and shadows change
with pose. These statistics describe the supplied images, not a causal split.

Reuses shading_compare's loaders so the measurement domain matches that tool.
"""
from __future__ import annotations

import argparse
import json
import statistics
from pathlib import Path

from PIL import Image

from compare_pose_official import WORK_SIZE, largest_character_mask
from attribute_render_gap import (
    load_official_labels, official_part, decode_unity_label, part_from_renderer_name,
)
from shading_compare import family_of, FAMILIES


def region_pixels(img, mask, parts, family):
    px, mp = img.load(), mask.load()
    out = [[], [], []]
    for y in range(img.height):
        for x in range(img.width):
            if not mp[x, y] or family_of(parts[y][x]) != family:
                continue
            for c in range(3):
                out[c].append(px[x, y][c])
    return out


def stats(chans):
    n = len(chans[0])
    if n == 0:
        return {"n": 0, "mean": [0, 0, 0], "median": [0, 0, 0]}
    return {"n": n,
            "mean": [sum(c) / n for c in chans],
            "median": [statistics.median(c) for c in chans]}


def overlap_mae(official, current, off_parts, cur_parts, off_mask, cur_mask, family):
    op, cp, om, cm = official.load(), current.load(), off_mask.load(), cur_mask.load()
    chan = [0, 0, 0]
    signed = [0, 0, 0]
    n = 0
    for y in range(official.height):
        for x in range(official.width):
            if not (om[x, y] and cm[x, y]):
                continue
            if family_of(off_parts[y][x]) != family or family_of(cur_parts[y][x]) != family:
                continue
            for c in range(3):
                d = int(op[x, y][c]) - int(cp[x, y][c])
                chan[c] += abs(d)
                signed[c] += d
            n += 1
    denom = max(1, n)
    return {"n": n, "mae": [c / denom for c in chan], "signed": [s / denom for s in signed]}


def parse_args() -> argparse.Namespace:
    cap = "Validation/Captures/tifuluosi-front-20260917"
    p = argparse.ArgumentParser()
    p.add_argument("--official", default=f"{cap}/pipeline-textures-01/post-output-flipped.png")
    p.add_argument("--current", default="Validation/pose-apply-01/pose-applied-lit-post.png")
    p.add_argument("--official-labels", default=f"{cap}/draw-labels-01/labels-u16.bin")
    p.add_argument("--official-draws", default=f"{cap}/draw-labels-01/draws.json")
    p.add_argument("--official-parts", default="Tools/data/frame6411_draw_parts.json")
    p.add_argument("--current-labels", default="Validation/pose-apply-01/pose-applied-labels.png")
    p.add_argument("--current-labels-json", default="Validation/pose-apply-01/pose-applied-labels.json")
    return p.parse_args()


def main() -> int:
    a = parse_args()
    official_src = Image.open(a.official).convert("RGB")
    current_src = Image.open(a.current).convert("RGB")
    official = official_src.resize(WORK_SIZE, Image.Resampling.LANCZOS)
    current = current_src.resize(WORK_SIZE, Image.Resampling.LANCZOS)
    off_mask = largest_character_mask(official_src)
    cur_mask = largest_character_mask(current_src)

    target = json.loads(Path(a.official_draws).read_text(encoding="utf-8"))["target"]
    size = (target["width"], target["height"])
    parts_map = json.loads(Path(a.official_parts).read_text(encoding="utf-8"))
    labels = load_official_labels(Path(a.official_labels), size, True).resize(WORK_SIZE, Image.Resampling.NEAREST)
    lp = labels.load()
    off_parts = [[official_part(lp[x, y], parts_map) for x in range(WORK_SIZE[0])] for y in range(WORK_SIZE[1])]
    meta = json.loads(Path(a.current_labels_json).read_text(encoding="utf-8"))
    renderer_parts = {r["index"]: part_from_renderer_name(r["name"]) for r in meta["renderers"]}
    clabels = Image.open(a.current_labels).convert("RGB").resize(WORK_SIZE, Image.Resampling.NEAREST)
    clp = clabels.load()
    cur_parts = [[decode_unity_label(clp[x, y], renderer_parts) for x in range(WORK_SIZE[0])] for y in range(WORK_SIZE[1])]

    print(f"{'family':6} | {'off_n':>6} {'cur_n':>6} | {'official mean RGB':>18} | {'current mean RGB':>18} | "
          f"{'|Δmean|':>8} | {'ovl_n':>6} {'ovl_MAEmax':>10} | {'ovl signed (off-cur) RGB':>26}")
    for f in FAMILIES:
        o = stats(region_pixels(official, off_mask, off_parts, f))
        c = stats(region_pixels(current, cur_mask, cur_parts, f))
        ov = overlap_mae(official, current, off_parts, cur_parts, off_mask, cur_mask, f)
        dmean = [abs(o["mean"][i] - c["mean"][i]) for i in range(3)]
        om = ", ".join(f"{v:3.0f}" for v in o["mean"])
        cm = ", ".join(f"{v:3.0f}" for v in c["mean"])
        sg = ", ".join(f"{v:+4.0f}" for v in ov["signed"])
        print(f"{f:6} | {o['n']:6} {c['n']:6} | ({om}) | ({cm}) | {max(dmean):8.1f} | "
              f"{ov['n']:6} {max(ov['mae']):10.1f} | ({sg})")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
