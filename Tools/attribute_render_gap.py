# -*- coding: utf-8 -*-
"""WP1.1: attribute the frame-6411 gate residual to parts, passes and unposed-bone coverage.

Diagnostic only; acceptance gates stay in compare_pose_official.py. Masks, regions and
the work-size resize are taken from that module so the attributed totals reconcile
with the gate numbers exactly.
"""
from __future__ import annotations

import argparse
import json
import re
from pathlib import Path

from PIL import Image

from compare_pose_official import WORK_SIZE, largest_character_mask, region_color_metrics

REGION_NAMES = ("head", "torso", "legs")
UNATTRIBUTED_MAX = 0.10
LABEL_COVERAGE_MIN = 0.90
UNDECODABLE_MAX = 0.005


def load_official_labels(path: Path, size: tuple[int, int], flip: bool) -> Image.Image:
    data = Path(path).read_bytes()
    expected = size[0] * size[1] * 2
    if len(data) != expected:
        raise ValueError(f"{path}: expected {expected} bytes for {size}, got {len(data)}")
    image = Image.frombytes("I;16", size, data)
    return image.transpose(Image.Transpose.FLIP_TOP_BOTTOM) if flip else image


def part_from_renderer_name(name: str) -> str:
    match = re.fullmatch(r"S_actor_typhoea_(.+)_lod0", name, flags=re.IGNORECASE)
    if not match:
        raise ValueError(f"unexpected renderer name {name!r}")
    return match.group(1).lower()


def decode_unity_label(rgb: tuple[int, int, int], parts: dict[int, str]) -> str:
    r, g, b = rgb[:3]
    if r == 0 and g == 0 and b == 0:
        return "none"
    index = r - 1
    if index not in parts or g < 1 or b not in (128, 255):
        return "undecodable"
    return parts[index] + ("/outline" if b == 255 else "")


def official_part(event: int, parts: dict[str, dict]) -> str:
    if event == 0:
        return "none"
    entry = parts.get(str(event))
    if entry is None:
        return "unmapped"
    return entry["part"] + ("/outline" if entry["pass"] == "outline" else "")


def region_cuts(bbox: tuple[int, int, int, int]) -> list[int]:
    _, y0, _, y1 = bbox
    return [y0, y0 + (y1 - y0) // 3, y0 + 2 * (y1 - y0) // 3, y1]


def attribute(official, current, official_mask, current_mask, official_parts, current_parts, unposed) -> dict:
    op, cp = official.load(), current.load()
    om, cm = official_mask.load(), current_mask.load()
    up = unposed.load() if unposed is not None else None
    w, h = official.size
    bbox = official_mask.getbbox()
    x0, _, x1, _ = bbox
    cuts = region_cuts(bbox)
    regions = {}
    total_err = 0
    unattributed_err = 0
    for i, name in enumerate(REGION_NAMES):
        sources: dict[tuple[str, str], list[int]] = {}
        err_sum = 0
        count = 0
        for y in range(max(0, cuts[i]), min(h, cuts[i + 1])):
            for x in range(max(0, x0), min(w, x1)):
                if not (om[x, y] or cm[x, y]):
                    continue
                err = sum(abs(int(op[x, y][c]) - int(cp[x, y][c])) for c in range(3))
                key = (official_parts[y][x], current_parts[y][x])
                slot = sources.setdefault(key, [0, 0, 0])
                slot[0] += err
                slot[1] += 1
                slot[2] += err if (up is not None and up[x, y]) else 0
                err_sum += err
                count += 1
                if key[0] in ("none", "unmapped") and key[1] in ("none", "undecodable"):
                    unattributed_err += err
        total_err += err_sum
        ranked = sorted(sources.items(), key=lambda item: -item[1][0])
        regions[name] = {
            "pixels": count,
            "err_sum": err_sum,
            "mean_abs_rgb_avg": err_sum / (3 * max(1, count)),
            "sources": [
                {"official": k[0], "current": k[1], "pixels": v[1], "err_sum": v[0],
                 "share": v[0] / err_sum if err_sum else 0.0,
                 "unposed_share": v[2] / v[0] if v[0] else 0.0}
                for k, v in ranked
            ],
        }

    intersection = union = 0
    missing: dict[str, list[int]] = {}
    extra: dict[str, list[int]] = {}
    for y in range(h):
        for x in range(w):
            a, b = bool(om[x, y]), bool(cm[x, y])
            intersection += a and b
            union += a or b
            flag = 1 if (up is not None and up[x, y]) else 0
            if a and not b:
                slot = missing.setdefault(official_parts[y][x], [0, 0])
                slot[0] += 1
                slot[1] += flag
            elif b and not a:
                slot = extra.setdefault(current_parts[y][x], [0, 0])
                slot[0] += 1
                slot[1] += flag

    def ranked_fixes(table, fixed_iou):
        rows = [{"part": part, "pixels": n, "unposed_pixels": u, "iou_if_fixed": fixed_iou(n)}
                for part, (n, u) in table.items()]
        return sorted(rows, key=lambda row: -row["pixels"])

    return {
        "regions": regions,
        "silhouette": {
            "iou": intersection / union if union else 1.0,
            "intersection": intersection,
            "union": union,
            "missing": ranked_fixes(missing, lambda n: (intersection + n) / union),
            "extra": ranked_fixes(extra, lambda n: intersection / (union - n)),
        },
        "unattributed_share": unattributed_err / total_err if total_err else 0.0,
    }


def label_coverage(mask: Image.Image, labels: Image.Image, parts: dict[str, dict]) -> float:
    mp, lp = mask.load(), labels.load()
    covered = total = 0
    for y in range(mask.height):
        for x in range(mask.width):
            if mp[x, y]:
                total += 1
                covered += official_part(lp[x, y], parts) not in ("none", "unmapped")
    return covered / total if total else 0.0


def parse_args() -> argparse.Namespace:
    capture = "Validation/Captures/tifuluosi-front-20260917"
    parser = argparse.ArgumentParser()
    parser.add_argument("--official", default=f"{capture}/pipeline-textures-01/post-output-flipped.png")
    parser.add_argument("--current", default="Validation/pose-apply-01/pose-applied-lit-post.png")
    parser.add_argument("--official-labels", default=f"{capture}/draw-labels-01/labels-u16.bin")
    parser.add_argument("--official-draws", default=f"{capture}/draw-labels-01/draws.json")
    parser.add_argument("--official-parts", default="Tools/data/frame6411_draw_parts.json")
    parser.add_argument("--current-labels", default="Validation/pose-apply-01/pose-applied-labels.png")
    parser.add_argument("--current-labels-json", default="Validation/pose-apply-01/pose-applied-labels.json")
    parser.add_argument("--current-unposed", default="Validation/pose-apply-01/pose-applied-unposed.png")
    parser.add_argument("--flip-official-labels", choices=("yes", "no"), default="yes")
    parser.add_argument("--out", default="Validation/render-gap-attribution-01")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    official_source = Image.open(args.official).convert("RGB")
    current_source = Image.open(args.current).convert("RGB")
    official = official_source.resize(WORK_SIZE, Image.Resampling.LANCZOS)
    current = current_source.resize(WORK_SIZE, Image.Resampling.LANCZOS)
    official_mask = largest_character_mask(official_source)
    current_mask = largest_character_mask(current_source)

    target = json.loads(Path(args.official_draws).read_text(encoding="utf-8"))["target"]
    size = (target["width"], target["height"])
    parts = json.loads(Path(args.official_parts).read_text(encoding="utf-8"))
    coverage = {}
    for flip in (True, False):
        labels = load_official_labels(Path(args.official_labels), size, flip).resize(WORK_SIZE, Image.Resampling.NEAREST)
        coverage["yes" if flip else "no"] = label_coverage(official_mask, labels, parts)
    flip = args.flip_official_labels == "yes"
    labels = load_official_labels(Path(args.official_labels), size, flip).resize(WORK_SIZE, Image.Resampling.NEAREST)
    lp = labels.load()
    official_parts = [[official_part(lp[x, y], parts) for x in range(WORK_SIZE[0])] for y in range(WORK_SIZE[1])]

    meta = json.loads(Path(args.current_labels_json).read_text(encoding="utf-8"))
    renderer_parts = {r["index"]: part_from_renderer_name(r["name"]) for r in meta["renderers"]}
    current_labels = Image.open(args.current_labels).convert("RGB").resize(WORK_SIZE, Image.Resampling.NEAREST)
    clp = current_labels.load()
    current_parts = [[decode_unity_label(clp[x, y], renderer_parts) for x in range(WORK_SIZE[0])] for y in range(WORK_SIZE[1])]
    unposed = Image.open(args.current_unposed).convert("L").resize(WORK_SIZE, Image.Resampling.NEAREST).point(lambda v: 255 if v > 127 else 0).convert("1")

    result = attribute(official, current, official_mask, current_mask, official_parts, current_parts, unposed)
    union_mask = Image.new("1", WORK_SIZE, 0)
    union_mask.paste(1, mask=official_mask)
    union_mask.paste(1, mask=current_mask)
    gate_regions = region_color_metrics(official, current, union_mask, official_mask.getbbox())
    reconcile = {name: abs(result["regions"][name]["mean_abs_rgb_avg"] - sum(gate_regions[name]["mean_abs_rgb"]) / 3)
                 for name in REGION_NAMES}
    undecodable_fraction = meta["undecodable_pixels"] / (current_source.width * current_source.height)
    checks = {
        "reconciles_with_gate": all(value < 1e-9 for value in reconcile.values()),
        "label_coverage": coverage["yes" if flip else "no"] >= LABEL_COVERAGE_MIN
            and coverage["yes" if flip else "no"] >= coverage["no" if flip else "yes"],
        "unattributed_below_10pct": result["unattributed_share"] < UNATTRIBUTED_MAX,
        "unity_labels_decodable": undecodable_fraction < UNDECODABLE_MAX,
    }
    report = {"inputs": vars(args), "label_coverage": coverage, "reconcile_abs_diff": reconcile,
              "undecodable_fraction": undecodable_fraction, "unposed_bones": meta["unposed_bones"],
              "checks": checks, "pass": all(checks.values()), **result}
    (out / "report.json").write_text(json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8")
    (out / "report.md").write_text(render_markdown(report), encoding="utf-8")
    print(json.dumps({"checks": checks, "silhouette_iou": result["silhouette"]["iou"]}, ensure_ascii=False))
    return 0 if report["pass"] else 2


def render_markdown(report: dict) -> str:
    lines = ["# 帧 6411 差距归因（WP1.1）", "", f"检查：{report['checks']}", ""]
    sil = report["silhouette"]
    lines += [f"## 轮廓（IoU {sil['iou']:.3f}）", "", "| 类型 | 部件 | 像素 | 其中未摆姿骨 | 修好后 IoU |", "|---|---|---|---|---|"]
    for kind in ("missing", "extra"):
        for row in sil[kind][:10]:
            lines.append(f"| {kind} | {row['part']} | {row['pixels']} | {row['unposed_pixels']} | {row['iou_if_fixed']:.3f} |")
    for name in REGION_NAMES:
        region = report["regions"][name]
        lines += ["", f"## {name}（通道平均误差 {region['mean_abs_rgb_avg']:.1f}）", "",
                  "| 官方部件 | 当前部件 | 像素 | 误差占比 | 其中未摆姿骨 |", "|---|---|---|---|---|"]
        for row in region["sources"][:15]:
            lines.append(f"| {row['official']} | {row['current']} | {row['pixels']} | {row['share']:.1%} | {row['unposed_share']:.1%} |")
    return "\n".join(lines) + "\n"


if __name__ == "__main__":
    raise SystemExit(main())
