# -*- coding: utf-8 -*-
"""Phase-1 render fidelity: per-material-family colour A/B (same-family overlap only).

"Does it shade like official." Reuses compare_pose_official's work-size/mask and
attribute_render_gap's label loaders, so results are same-domain. Pose/silhouette
mismatch is excluded by construction: only pixels where official family == current
family are compared.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

from PIL import Image

from compare_pose_official import WORK_SIZE, largest_character_mask, percentile
from attribute_render_gap import (
    load_official_labels, official_part, decode_unity_label, part_from_renderer_name,
)

FAMILIES = ("skin", "hair", "cloth", "eye")
MAE_MAX = 4.0
P95_MAX = 16.0
WITHIN8_MIN = 0.90
MIN_PIXELS = 200

_FAMILY = {
    "body_01": "skin", "face_01": "skin",
    "hair_01": "hair", "hairshadow_01": "hair",
    "iris_01": "eye", "eyeshadow_01": "eye", "brow_01": "eye",
}


def part_base(label: str) -> str:
    return label.split("/", 1)[0]


def family_of(label: str) -> str:
    base = part_base(label)
    if base.startswith("cloth_"):
        return "cloth"
    return _FAMILY.get(base, "other")


def compare_families(official, current, official_parts, current_parts, mask) -> dict:
    op, cp, mp = official.load(), current.load(), mask.load()
    w, h = official.size
    acc = {f: {"chan": [0, 0, 0], "diffs": [], "count": 0, "within": 0} for f in FAMILIES}
    for y in range(h):
        for x in range(w):
            if not mp[x, y]:
                continue
            fo = family_of(official_parts[y][x])
            if fo not in acc or fo != family_of(current_parts[y][x]):
                continue
            pd = [abs(int(op[x, y][c]) - int(cp[x, y][c])) for c in range(3)]
            slot = acc[fo]
            for c, v in enumerate(pd):
                slot["chan"][c] += v
                slot["diffs"].append(v)
            slot["count"] += 1
            if max(pd) <= 8:
                slot["within"] += 1
    families = {}
    for f in FAMILIES:
        s = acc[f]
        n = s["count"]
        denom = max(1, n)
        mean = [c / denom for c in s["chan"]]
        p95 = percentile(s["diffs"], 0.95)
        within = s["within"] / denom
        low = n < MIN_PIXELS
        families[f] = {
            "pixels": n, "low_sample": low,
            "mean_abs_rgb": mean, "mean_abs_rgb_max": max(mean),
            "p95_abs_rgb": p95, "within_8_lsb": within,
            "pass": (not low) and max(mean) <= MAE_MAX and p95 <= P95_MAX and within >= WITHIN8_MIN,
        }
    return families


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
    p.add_argument("--flip-official-labels", choices=("yes", "no"), default="yes")
    p.add_argument("--out", default="Validation/shading-compare-01")
    return p.parse_args()


def render_md(report: dict) -> str:
    lines = ["# 逐部件比色 A/B（阶段1 渲染保真）", "", f"总判定 pass = {report['pass']}", "",
             "| 家族 | 重叠像素 | 通道 MAE | p95 | 8色阶内 | low_sample | pass |", "|---|---|---|---|---|---|---|"]
    for f, v in report["families"].items():
        lines.append(f"| {f} | {v['pixels']} | {v['mean_abs_rgb_max']:.1f} | {v['p95_abs_rgb']:.0f} | "
                     f"{v['within_8_lsb']:.2f} | {v['low_sample']} | {v['pass']} |")
    return "\n".join(lines) + "\n"


def main() -> int:
    a = parse_args()
    out = Path(a.out); out.mkdir(parents=True, exist_ok=True)
    official_src = Image.open(a.official).convert("RGB")
    current_src = Image.open(a.current).convert("RGB")
    official = official_src.resize(WORK_SIZE, Image.Resampling.LANCZOS)
    current = current_src.resize(WORK_SIZE, Image.Resampling.LANCZOS)
    off_mask = largest_character_mask(official_src)
    cur_mask = largest_character_mask(current_src)
    inter = Image.new("1", WORK_SIZE, 0)
    ip, om, cm = inter.load(), off_mask.load(), cur_mask.load()
    for y in range(WORK_SIZE[1]):
        for x in range(WORK_SIZE[0]):
            if om[x, y] and cm[x, y]:
                ip[x, y] = 1
    target = json.loads(Path(a.official_draws).read_text(encoding="utf-8"))["target"]
    size = (target["width"], target["height"])
    parts_map = json.loads(Path(a.official_parts).read_text(encoding="utf-8"))
    flip = a.flip_official_labels == "yes"
    labels = load_official_labels(Path(a.official_labels), size, flip).resize(WORK_SIZE, Image.Resampling.NEAREST)
    lp = labels.load()
    official_parts = [[official_part(lp[x, y], parts_map) for x in range(WORK_SIZE[0])] for y in range(WORK_SIZE[1])]
    meta = json.loads(Path(a.current_labels_json).read_text(encoding="utf-8"))
    renderer_parts = {r["index"]: part_from_renderer_name(r["name"]) for r in meta["renderers"]}
    clabels = Image.open(a.current_labels).convert("RGB").resize(WORK_SIZE, Image.Resampling.NEAREST)
    clp = clabels.load()
    current_parts = [[decode_unity_label(clp[x, y], renderer_parts) for x in range(WORK_SIZE[0])] for y in range(WORK_SIZE[1])]
    families = compare_families(official, current, official_parts, current_parts, inter)
    report = {"inputs": vars(a), "families": families, "pass": all(v["pass"] for v in families.values())}
    (out / "report.json").write_text(json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8")
    (out / "report.md").write_text(render_md(report), encoding="utf-8")
    print(json.dumps({"pass": report["pass"], "families": {f: {"mae": round(v["mean_abs_rgb_max"], 1),
          "px": v["pixels"], "pass": v["pass"]} for f, v in families.items()}}, ensure_ascii=False))
    return 0 if report["pass"] else 2


if __name__ == "__main__":
    raise SystemExit(main())
