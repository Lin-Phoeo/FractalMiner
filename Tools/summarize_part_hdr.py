"""Unclamped, linear-HDR part statistics. Not a same-surface fidelity gate.

Official changed-pixel masks and Unity renderer labels describe different
surfaces/poses; their means must not be used to fit an exposure correction.
"""
import argparse
import json
from pathlib import Path

import numpy as np
from PIL import Image

from capture_part_hdr import decode_unsigned_float


def decode_r11g11b10(packed):
    packed = np.asarray(packed, dtype=np.uint32)
    lut11 = np.array([decode_unsigned_float(i, 6) for i in range(2048)], dtype=np.float32)
    lut10 = np.array([decode_unsigned_float(i, 5) for i in range(1024)], dtype=np.float32)
    return np.stack((lut11[packed & 2047], lut11[(packed >> 11) & 2047],
                     lut10[packed >> 22]), axis=-1)


def masked_stats(rgb, mask):
    rgb, mask = np.asarray(rgb), np.asarray(mask, dtype=bool)
    if rgb.shape != mask.shape + (3,):
        raise ValueError("RGB/mask shape mismatch")
    samples = rgb[mask].astype(np.float64)
    if len(samples) == 0 or not np.isfinite(samples).all():
        raise ValueError("Empty or non-finite masked HDR samples")
    return {"pixels": len(samples), "mean_rgb": samples.mean(axis=0).tolist(),
            "median_rgb": np.median(samples, axis=0).tolist(),
            "p95_rgb": np.percentile(samples, 95, axis=0).tolist(),
            "mean_luminance": float((samples @ [0.2126, 0.7152, 0.0722]).mean())}


def load_packed(path, width, height):
    if path.stat().st_size != width * height * 4:
        raise ValueError("Packed HDR byte length mismatch: " + str(path))
    return decode_r11g11b10(np.fromfile(path, dtype="<u4").reshape(height, width))


def run(args):
    evidence = json.loads((args.capture / "evidence.json").read_text(encoding="utf-8"))
    target = evidence["target"]
    width, height = target["width"], target["height"]
    final = load_packed(args.capture / "scene-final.r11g11b10", width, height)
    meta = json.loads((args.current / "current-prepost.json").read_text(encoding="utf-8"))
    if meta["encoding"] != "linear" or meta["storage"] != "little-endian RGBA float32":
        raise ValueError("Unknown current HDR encoding")
    path = args.current / "current-prepost.rgba32f"
    if path.stat().st_size != meta["width"] * meta["height"] * 16:
        raise ValueError("Current HDR byte length mismatch")
    current = np.fromfile(path, dtype="<f4").reshape(meta["height"], meta["width"], 4)[..., :3]
    if meta["rowOrder"] != "Unity bottom-to-top":
        raise ValueError("Unknown Unity HDR row order")
    current = current[::-1]
    labels = np.asarray(Image.open(args.labels).convert("RGB"))
    if labels.shape != current.shape:
        raise ValueError("Label/HDR resolution mismatch")
    label_meta = json.loads(args.labels.with_suffix(".json").read_text(encoding="utf-8"))
    renderers = label_meta["renderers"]
    results = {}
    for part in evidence["parts"]:
        changed_path = args.capture / (part + "-changed.u8")
        if changed_path.stat().st_size != width * height:
            raise ValueError("Changed-pixel mask byte length mismatch")
        mask = np.fromfile(changed_path, dtype=np.uint8).reshape(height, width) != 0
        forward = load_packed(args.capture / (part + "-forward.r11g11b10"), width, height)
        matches = [r for r in renderers if part in r["name"]]
        if len(matches) != 1:
            raise ValueError("Missing/ambiguous renderer for " + part)
        row = matches[0]
        current_mask = (labels[..., 0] == row["index"] + 1) & (labels[..., 2] == 128)
        results[part] = {"official_forward_changed": masked_stats(forward, mask),
                         "official_final_same_changed_mask": masked_stats(final, mask),
                         "current_renderer_interior": masked_stats(current, current_mask)}
    report = {"status": "diagnostic_only", "same_surface_verified": False,
              "warning": "Different poses/masks: means are not exposure fits or colour acceptance gates.",
              "encoding": "linear HDR, unclamped", "capture_frame": evidence["frame"],
              "sources": {"capture": str(args.capture.resolve()), "current": str(args.current.resolve()),
                          "labels": str(args.labels.resolve())}, "parts": results}
    args.out.parent.mkdir(parents=True, exist_ok=True)
    with args.out.open("x", encoding="utf-8") as stream:
        json.dump(report, stream, indent=2, allow_nan=False)
    print(str(args.out))


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--capture", type=Path, required=True)
    parser.add_argument("--current", type=Path, required=True)
    parser.add_argument("--labels", type=Path, required=True)
    parser.add_argument("--out", type=Path, required=True)
    run(parser.parse_args())
