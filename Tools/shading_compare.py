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
