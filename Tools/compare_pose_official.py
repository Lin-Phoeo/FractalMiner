# -*- coding: utf-8 -*-
"""M5 gate: compare the pose-applied Unity render with the captured official frame.

The acceptance thresholds below are intentionally fixed in source before the first
measurement run.  The script uses Pillow only (the project venv has no NumPy).
It writes a machine-readable report plus silhouette and absolute-difference images.
"""
from __future__ import annotations

import argparse
import json
import math
from collections import deque
from pathlib import Path
from typing import Iterable

from PIL import Image, ImageChops, ImageDraw

# Fixed before the first M5 measurement run on 2026-09-25.
THRESHOLDS = {
    "bbox_center_linf_max": 0.020,
    "bbox_size_relative_error_max": 0.050,
    "silhouette_iou_min": 0.850,
    "region_mean_abs_rgb_max": 4.0,
    "region_p95_abs_rgb_max": 16.0,
    "region_within_8_lsb_min": 0.900,
}

WORK_SIZE = (640, 400)
SEARCH_BOX_NORM = (0.28, 0.01, 0.78, 0.94)
OFFICIAL_CHARACTER_Y_MAX_NORM = 0.83
BACKGROUND_DELTA = 22
MAX_GROW_DISTANCE = 12


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--official",
        default="Validation/Captures/tifuluosi-front-20260917/official-front-1280.png",
    )
    parser.add_argument("--current", default="Validation/pose-apply-01/pose-applied.png")
    parser.add_argument("--out", default="Validation/pose-official-compare-01")
    parser.add_argument(
        "--truth",
        action="store_true",
        help="Baseline is the frame-6411 post-input texture (already tonemapped "
        "and vertically flipped: post-input-flipped.png) instead of the official "
        "screenshot. The truth image has NO segmentation truncation at y=0.83, "
        "so no official-floor-band exclusion is applied to it. Thresholds are "
        "the same fixed set — this flag only changes the baseline image and the "
        "mask-truncation behavior, never the acceptance limits.",
    )
    return parser.parse_args()


def rgb_distance(a: tuple[int, int, int], b: tuple[int, int, int]) -> float:
    return math.sqrt(sum((int(a[i]) - int(b[i])) ** 2 for i in range(3)))


def row_backgrounds(image: Image.Image) -> list[tuple[int, int, int]]:
    """Estimate slowly varying backdrop color from the outer 20% of each row."""
    w, h = image.size
    px = image.load()
    edge = max(1, int(w * 0.20))
    result = []
    for y in range(h):
        samples = [px[x, y] for x in range(edge)]
        samples.extend(px[x, y] for x in range(w - edge, w))
        channels = []
        for c in range(3):
            values = sorted(p[c] for p in samples)
            channels.append(values[len(values) // 2])
        result.append(tuple(channels))
    return result


def largest_character_mask(image: Image.Image) -> Image.Image:
    """Extract the largest foreground component in the known central character area."""
    image = image.convert("RGB").resize(WORK_SIZE, Image.Resampling.LANCZOS)
    w, h = image.size
    x0 = int(SEARCH_BOX_NORM[0] * w)
    y0 = int(SEARCH_BOX_NORM[1] * h)
    x1 = int(SEARCH_BOX_NORM[2] * w)
    y1 = int(SEARCH_BOX_NORM[3] * h)
    backgrounds = row_backgrounds(image)
    px = image.load()
    candidate = bytearray(w * h)
    seeds: list[int] = []
    for y in range(y0, y1):
        bg = backgrounds[y]
        for x in range(x0, x1):
            r, g, b = px[x, y]
            chroma = max(r, g, b) - min(r, g, b)
            delta = rgb_distance((r, g, b), bg)
            idx = y * w + x
            if delta >= BACKGROUND_DELTA or chroma >= 18:
                candidate[idx] = 1
            if chroma >= 10 and delta >= 18:
                seeds.append(idx)

    # Background grid/floor lines can be connected to the boots in the official
    # frame. Keep only candidate pixels within a fixed geodesic distance of a
    # chromatic character pixel; this removes those long achromatic tendrils
    # without changing any acceptance threshold.
    near_seed = bytearray(w * h)
    distance = [-1] * (w * h)
    queue = deque()
    for idx in seeds:
        near_seed[idx] = 1
        distance[idx] = 0
        queue.append(idx)
    while queue:
        idx = queue.popleft()
        if distance[idx] >= MAX_GROW_DISTANCE:
            continue
        cy, cx = divmod(idx, w)
        for ny in range(max(y0, cy - 1), min(y1, cy + 2)):
            base = ny * w
            for nx in range(max(x0, cx - 1), min(x1, cx + 2)):
                nidx = base + nx
                if candidate[nidx] and distance[nidx] < 0:
                    distance[nidx] = distance[idx] + 1
                    near_seed[nidx] = 1
                    queue.append(nidx)
    candidate = near_seed

    seen = bytearray(w * h)
    best: list[int] = []
    for y in range(y0, y1):
        for x in range(x0, x1):
            start = y * w + x
            if not candidate[start] or seen[start]:
                continue
            queue = deque([start])
            seen[start] = 1
            component: list[int] = []
            while queue:
                idx = queue.popleft()
                component.append(idx)
                cy, cx = divmod(idx, w)
                for ny in range(max(y0, cy - 1), min(y1, cy + 2)):
                    base = ny * w
                    for nx in range(max(x0, cx - 1), min(x1, cx + 2)):
                        nidx = base + nx
                        if candidate[nidx] and not seen[nidx]:
                            seen[nidx] = 1
                            queue.append(nidx)
            if len(component) > len(best):
                best = component

    mask = Image.new("1", WORK_SIZE, 0)
    out = mask.load()
    for idx in best:
        y, x = divmod(idx, w)
        out[x, y] = 1
    return mask


def bbox_metrics(mask: Image.Image) -> dict:
    bbox = mask.getbbox()
    if bbox is None:
        raise RuntimeError("character mask is empty")
    w, h = mask.size
    x0, y0, x1, y1 = bbox
    return {
        "pixels": sum(1 for value in mask.getdata() if value),
        "bbox_px": [x0, y0, x1, y1],
        "bbox_norm": [x0 / w, y0 / h, x1 / w, y1 / h],
        "center_norm": [(x0 + x1) / (2 * w), (y0 + y1) / (2 * h)],
        "size_norm": [(x1 - x0) / w, (y1 - y0) / h],
    }


def mask_iou(a: Image.Image, b: Image.Image) -> float:
    ap = a.load()
    bp = b.load()
    w, h = a.size
    intersection = 0
    union = 0
    for y in range(h):
        for x in range(w):
            av = bool(ap[x, y])
            bv = bool(bp[x, y])
            intersection += av and bv
            union += av or bv
    return intersection / union if union else 1.0


def percentile(values: list[int], q: float) -> float:
    if not values:
        return 0.0
    values.sort()
    return float(values[min(len(values) - 1, int((len(values) - 1) * q))])


def region_color_metrics(
    official: Image.Image,
    current: Image.Image,
    union_mask: Image.Image,
    official_bbox: tuple[int, int, int, int],
) -> dict:
    op = official.load()
    cp = current.load()
    mp = union_mask.load()
    x0, y0, x1, y1 = official_bbox
    cuts = [y0, y0 + (y1 - y0) // 3, y0 + 2 * (y1 - y0) // 3, y1]
    names = ("head", "torso", "legs")
    result = {}
    for i, name in enumerate(names):
        diffs: list[int] = []
        channel_sums = [0, 0, 0]
        count = 0
        within = 0
        for y in range(max(0, cuts[i]), min(official.height, cuts[i + 1])):
            for x in range(max(0, x0), min(official.width, x1)):
                if not mp[x, y]:
                    continue
                pixel_diffs = [abs(int(op[x, y][c]) - int(cp[x, y][c])) for c in range(3)]
                for c, value in enumerate(pixel_diffs):
                    channel_sums[c] += value
                    diffs.append(value)
                count += 1
                if max(pixel_diffs) <= 8:
                    within += 1
        denom = max(1, count)
        result[name] = {
            "pixels": count,
            "mean_abs_rgb": [value / denom for value in channel_sums],
            "mean_abs_rgb_max": max(value / denom for value in channel_sums),
            "p95_abs_rgb": percentile(diffs, 0.95),
            "within_8_lsb": within / denom,
        }
    return result


def draw_overlay(official: Image.Image, current: Image.Image, off_mask: Image.Image, cur_mask: Image.Image) -> Image.Image:
    canvas = Image.blend(official, current, 0.5)
    draw = ImageDraw.Draw(canvas)
    draw.rectangle(off_mask.getbbox(), outline=(255, 64, 64), width=2)
    draw.rectangle(cur_mask.getbbox(), outline=(64, 255, 255), width=2)
    draw.text((8, 8), "official bbox = red | current bbox = cyan", fill=(255, 255, 255))
    return canvas


def main() -> int:
    args = parse_args()
    official_path = Path(args.official)
    current_path = Path(args.current)
    out_dir = Path(args.out)
    out_dir.mkdir(parents=True, exist_ok=True)

    official_source = Image.open(official_path).convert("RGB")
    current_source = Image.open(current_path).convert("RGB")
    official = official_source.resize(WORK_SIZE, Image.Resampling.LANCZOS)
    current = current_source.resize(WORK_SIZE, Image.Resampling.LANCZOS)
    official_mask = largest_character_mask(official_source)
    # The official screenshot includes a long achromatic floor shadow connected to
    # the boots. It is lighting evidence, not the character silhouette, so exclude
    # the known floor-only band from the official geometry mask. The current mask
    # is intentionally not clipped: a vertical framing error must remain visible.
    # In --truth mode the baseline is the frame-6411 post-input texture, which
    # has no segmentation truncation (its legs band 0.84-0.94 is real geometry
    # proven by projection probes), so the exclusion band is NOT applied.
    if not args.truth:
        official_mask_draw = ImageDraw.Draw(official_mask)
        official_mask_draw.rectangle(
            (0, int(WORK_SIZE[1] * OFFICIAL_CHARACTER_Y_MAX_NORM), WORK_SIZE[0], WORK_SIZE[1]),
            fill=0,
        )
    current_mask = largest_character_mask(current_source)
    off_stats = bbox_metrics(official_mask)
    cur_stats = bbox_metrics(current_mask)

    center_delta = max(abs(a - b) for a, b in zip(off_stats["center_norm"], cur_stats["center_norm"]))
    size_error = max(
        abs(a - b) / max(abs(a), 1e-9)
        for a, b in zip(off_stats["size_norm"], cur_stats["size_norm"])
    )
    iou = mask_iou(official_mask, current_mask)
    union_mask = ImageChops.lighter(official_mask.convert("L"), current_mask.convert("L")).convert("1")
    regions = region_color_metrics(official, current, union_mask, official_mask.getbbox())

    gates = {
        "bbox_center": center_delta <= THRESHOLDS["bbox_center_linf_max"],
        "bbox_size": size_error <= THRESHOLDS["bbox_size_relative_error_max"],
        "silhouette_iou": iou >= THRESHOLDS["silhouette_iou_min"],
    }
    for name, metrics in regions.items():
        gates[f"{name}_color"] = (
            metrics["mean_abs_rgb_max"] <= THRESHOLDS["region_mean_abs_rgb_max"]
            and metrics["p95_abs_rgb"] <= THRESHOLDS["region_p95_abs_rgb_max"]
            and metrics["within_8_lsb"] >= THRESHOLDS["region_within_8_lsb_min"]
        )

    difference = ImageChops.difference(official, current)
    difference = difference.point(lambda value: min(255, value * 4))
    difference.save(out_dir / "abs-diff-x4.png")
    draw_overlay(official, current, official_mask, current_mask).save(out_dir / "silhouette-overlay.png")
    official_mask.convert("L").save(out_dir / "official-mask.png")
    current_mask.convert("L").save(out_dir / "current-mask.png")

    report = {
        "inputs": {
            "official": str(official_path),
            "official_size": list(official_source.size),
            "current": str(current_path),
            "current_size": list(current_source.size),
            "work_size": list(WORK_SIZE),
            "truth_mode": bool(args.truth),
        },
        "thresholds_fixed_before_first_run": THRESHOLDS,
        "segmentation": {
            "search_box_norm": SEARCH_BOX_NORM,
            "official_character_y_max_norm": OFFICIAL_CHARACTER_Y_MAX_NORM,
            "background_delta": BACKGROUND_DELTA,
            "seed_chroma_min": 10,
            "seed_background_delta_min": 18,
            "max_grow_distance": MAX_GROW_DISTANCE,
        },
        "official_silhouette": off_stats,
        "current_silhouette": cur_stats,
        "metrics": {
            "bbox_center_linf": center_delta,
            "bbox_size_relative_error": size_error,
            "silhouette_iou": iou,
            "regions": regions,
        },
        "gates": gates,
        "pass": all(gates.values()),
        "known_exclusions": [
            "The official frame contains a separate book prop absent from the 17-SMR Unity character.",
            "The current pose render does not yet include the frozen captured post-processing chain or official background.",
        ],
    }
    if args.truth:
        report["known_exclusions"].append(
            "Truth mode: baseline = frame-6411 post-input (Reinhard-tonemapped, "
            "vertically flipped). No official floor-band exclusion applied; the "
            "current render still lacks the captured post chain, so the current "
            "background/backdrop tone is the dominant expected residual."
        )
    (out_dir / "report.json").write_text(json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8")
    print(json.dumps(report, indent=2, ensure_ascii=False))
    return 0 if report["pass"] else 2


if __name__ == "__main__":
    raise SystemExit(main())
