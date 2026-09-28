# 阶段 1 渲染保真 · 子系统 1：逐部件比色 A/B 度量 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 造出"像不像官方地渲染"的**客观尺子**——同姿态下我方渲染 vs 官方帧 6411，按材质家族（skin/hair/cloth/eye）只比"同家族重叠像素"的颜色，输出每部件/每家族的 MAE/p95/8色阶内比例与达标布尔，供后续每个着色项（描边/阴影/雨淋）验收。

**Architecture:** 复用官方逐像素 draw 标签（C5，`Tools/data/frame6411_draw_parts.json` + `labels-u16.bin`）与我方部件标签渲染（`pose-applied-labels.png`），把两侧像素各映射到材质家族；只在"官方家族==当前家族"的重叠像素上比色，从而**姿态/轮廓不齐的错位像素自动不计入**（这是 2026-09-28 用户校正的核心：不追姿态，只判着色）。度量口径与 `compare_pose_official.py` 复用同一套 `WORK_SIZE`/掩码/缩放，保证与既有工具同域。纯 Python + Pillow，无 NumPy。

**Tech Stack:** Python 3.13（项目 venv `../EndfieldUnpacker/.venv/Scripts/python.exe`，Pillow 12.3，无 NumPy/pytest；测试用 unittest）。系统 `python` 无 Pillow，禁用。

**Spec:** `docs/superpowers/plans/2026-09-27-mainline-roadmap.md` §A.4（2026-09-28 重定的出口门禁三条之①逐部件比色 A/B）+ §A.4 末「WP1.1 结果与阶段 1 排序」。

## Global Constraints

- 目标是"像不像官方地渲染"，**不追捕获帧姿态**；本工具只在同家族重叠像素比色，不产出/不使用整帧轮廓 IoU 作门禁。
- 阈值沿用 `compare_pose_official.THRESHOLDS`（MAE≤4、p95≤16、8色阶内≥0.9），只收紧不放宽。
- 真值与生成物（`Validation/**`、`*.rdc`）不进 Git；提交只走临时 `GIT_INDEX_FILE` → `fix/typhoeus-render-explosion-20260917` → `endfield-records`；`main` 工作树不动。
- 系统 `python` 无 Pillow，一律用 `../EndfieldUnpacker/.venv/Scripts/python.exe`。
- 不改冻结模块，不改 shader（本子系统纯度量，不动渲染）。

## Review Focus

1. 家族映射漏项（新部件未登记）→ 该部件像素被丢进 "other" 不参与比色，虚高达标。测试：`test_family_of_covers_vocabulary` 断言 C5 词表与 Unity renderer 词表的每个部件都映到 skin/hair/cloth/eye 或显式 other。
2. `/outline` 后缀未剥离 → 同部件的前向与描边像素被判为不同家族、重叠像素漏算。测试：`test_part_base_strips_outline`。
3. 官方标签方向翻转错 → 家族重叠全错但数字"看着合理"。测试：沿用 `attribute_render_gap` 的 `flip=yes` 覆盖率断言（≥0.9 且高于反向），在 main 里复用并写进报告。
4. 某家族重叠像素过少（如 eye 只几十像素）→ 均值不稳被误判达标/不达标。测试：`test_family_min_pixels_flag`——重叠像素 < 阈值（默认 200）时该家族标 `low_sample=true`，不参与"全绿"判定。
5. 与既有工具同域漂移（掩码/缩放不一致）→ 结果对不上 `compare_pose_official`。测试：`test_reuses_workspace_symbols`——断言 `shading_compare.WORK_SIZE is compare_pose_official.WORK_SIZE`，且家族内通道均值对同一 RGB 输入的直接手算一致；main() 取掩码一律用 `compare_pose_official.largest_character_mask`（Task 2 集成步骤核对）。

---

## 文件结构

| 文件 | 职责 | 动作 |
|---|---|---|
| `Tools/shading_compare.py` | 家族映射 + 同家族重叠比色 + 报告/门禁 | Create |
| `Tools/tests/test_shading_compare.py` | 上面的单测（合成数据） | Create |
| `Tools/tests/test_shading_formulas.py` | 着色公式参考实现单测（模板，先钉描边宽度公式） | Create |
| `Validation/shading-compare-01/{report.json,report.md}` | 每部件/家族基线数字（不入库） | 运行产出 |

本子系统只做**度量**。后续 WP1.4 各着色项（描边全打光 / overlayshadow 刘海投脸 / shadowreceiver 地面投影 / liquidag 雨淋湿身 / dither / 透明 / clearcoat）与展示场景/可操作性各自独立成计划，每个都用本工具 + 各自的着色单测验收。

### Task 1：家族映射 + 同家族重叠比色（纯函数）

**Files:**
- Create: `Tools/shading_compare.py`
- Test: `Tools/tests/test_shading_compare.py`

**Interfaces:**
- Consumes: `compare_pose_official.WORK_SIZE`/`largest_character_mask`/`percentile`；`attribute_render_gap.load_official_labels`/`official_part`/`decode_unity_label`/`part_from_renderer_name`。
- Produces:
  - `part_base(label: str) -> str`（剥离 `/outline` 后缀）
  - `family_of(label: str) -> str`（返回 `"skin"|"hair"|"cloth"|"eye"|"other"`）
  - `compare_families(official, current, official_parts, current_parts, mask) -> dict`，返回 `{family: {pixels, low_sample, mean_abs_rgb[3], mean_abs_rgb_max, p95_abs_rgb, within_8_lsb, pass}}`；`*_parts` 为 `list[list[str]]`（每像素部件字符串），只统计 `family_of(official)==family_of(current)` 且都在 `FAMILIES` 内、且 `mask` 为真的像素。
  - 常量 `FAMILIES=("skin","hair","cloth","eye")`、`MAE_MAX=4.0`、`P95_MAX=16.0`、`WITHIN8_MIN=0.90`、`MIN_PIXELS=200`、`WORK_SIZE`（转自 compare_pose_official）。

- [ ] **Step 1：写失败测试**

```python
import sys, unittest
from pathlib import Path
from PIL import Image
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import shading_compare as sc
import compare_pose_official as cmp


def grid(rows): return [list(r) for r in rows]
def solid(size, color): return Image.new("RGB", size, color)


class ShadingCompareTests(unittest.TestCase):
    def test_part_base_strips_outline(self):
        self.assertEqual(sc.part_base("cloth_01/outline"), "cloth_01")
        self.assertEqual(sc.part_base("hair_01"), "hair_01")
        self.assertEqual(sc.part_base("none"), "none")

    def test_family_of_covers_vocabulary(self):
        for p in ("body_01", "face_01"): self.assertEqual(sc.family_of(p), "skin")
        for p in ("hair_01", "hairshadow_01"): self.assertEqual(sc.family_of(p), "hair")
        for p in ("cloth_01", "cloth_07", "cloth_03/outline"): self.assertEqual(sc.family_of(p), "cloth")
        for p in ("iris_01", "eyeshadow_01", "brow_01"): self.assertEqual(sc.family_of(p), "eye")
        for p in ("book", "background", "other", "none", "unmapped", "undecodable", "vfxpart_01"):
            self.assertEqual(sc.family_of(p), "other")

    def test_overlap_only_same_family_counted(self):
        size = (2, 2)
        official = solid(size, (100, 100, 100)); current = solid(size, (100, 100, 100))
        current.putpixel((0, 0), (110, 100, 100))   # skin∩skin, R err 10
        current.putpixel((1, 0), (200, 100, 100))   # official skin vs current cloth -> excluded
        mask = Image.new("1", size, 1)
        op = grid([["body_01", "body_01"], ["hair_01", "hair_01"]])
        cp = grid([["body_01", "cloth_01"], ["hair_01", "hair_01"]])
        fam = sc.compare_families(official, current, op, cp, mask)
        self.assertEqual(fam["skin"]["pixels"], 1)
        self.assertEqual(fam["skin"]["mean_abs_rgb_max"], 10)
        self.assertEqual(fam["hair"]["pixels"], 2)
        self.assertEqual(fam["hair"]["mean_abs_rgb_max"], 0)
        self.assertEqual(fam["cloth"]["pixels"], 0)   # no cloth∩cloth overlap

    def test_family_min_pixels_flag(self):
        size = (1, 1); img = solid(size, (0, 0, 0)); mask = Image.new("1", size, 1)
        fam = sc.compare_families(img, img, grid([["body_01"]]), grid([["body_01"]]), mask)
        self.assertTrue(fam["skin"]["low_sample"])   # 1 px < MIN_PIXELS
        self.assertFalse(fam["skin"]["pass"])         # low sample never passes

    def test_reuses_workspace_symbols(self):
        self.assertIs(sc.WORK_SIZE, cmp.WORK_SIZE)
        size = (4, 4)
        official = Image.new("RGB", size); current = Image.new("RGB", size)
        for y in range(4):
            for x in range(4):
                official.putpixel((x, y), (x * 10, y * 10, 20)); current.putpixel((x, y), (x * 13, y * 7, 25))
        mask = Image.new("1", size, 1)
        op = grid([["body_01"] * 4] * 4); cp = grid([["body_01"] * 4] * 4)
        fam = sc.compare_families(official, current, op, cp, mask)
        opx, cpx = official.load(), current.load()
        exp0 = sum(abs(opx[x, y][0] - cpx[x, y][0]) for y in range(4) for x in range(4)) / 16
        self.assertAlmostEqual(fam["skin"]["mean_abs_rgb"][0], exp0)


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 2：运行确认失败**

Run: `cd "A:/Hypergryph Launcher/games/Arknights Endfield/FractalMiner" && ../EndfieldUnpacker/.venv/Scripts/python.exe -m unittest discover -s Tools/tests -p "test_shading_compare.py" -v`
Expected: `ModuleNotFoundError: No module named 'shading_compare'`。

- [ ] **Step 3：实现纯函数（`Tools/shading_compare.py` 顶部到 `compare_families`）**

```python
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
```

- [ ] **Step 4：运行确认通过 + 全量不回归**

Run: `cd "A:/Hypergryph Launcher/games/Arknights Endfield/FractalMiner" && PY=../EndfieldUnpacker/.venv/Scripts/python.exe && $PY -m unittest discover -s Tools/tests -p "test_shading_compare.py" -v && $PY -m unittest discover -s Tools/tests`
Expected: 5 个新测试全 PASS；全量 = 既有基线（`test_export_pmx_motion_rig`/`test_inspect_mmd_compat` 缺 pytest 导入失败、`test_iterative_ik_converts_radian_limits_to_unity_degrees` 失败，均与本 WP 无关）+ 新增通过，无新失败。

- [ ] **Step 5：提交（临时 index）**

`git add -- Tools/shading_compare.py Tools/tests/test_shading_compare.py`，信息 `feat(render): per-family shading A/B core (same-family overlap)`。命令模板同 §B 记录分支提交流程。

### Task 2：CLI + 跑出基线每家族报告

**Files:**
- Modify: `Tools/shading_compare.py`（追加 `parse_args`/`render_md`/`main`）
- Output（不入库）: `Validation/shading-compare-01/{report.json,report.md}`

**Interfaces:**
- Consumes: Task 1 的 `compare_families`/`family_of`；`attribute_render_gap` 的加载函数；任务 1（C5）产物 `labels-u16.bin`/`draws.json`/`frame6411_draw_parts.json`；任务 2（Unity）产物 `pose-applied-labels.png`/`.json`。
- Produces: 每家族达标表 + `pass` 布尔；退出码 0=全绿、2=未达标。

- [ ] **Step 1：追加 main（接在 `compare_families` 之后）**

```python
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
```

- [ ] **Step 2：跑出当前基线**

Run: `cd "A:/Hypergryph Launcher/games/Arknights Endfield/FractalMiner" && ../EndfieldUnpacker/.venv/Scripts/python.exe Tools/shading_compare.py`
Expected: 打印每家族 `mae/px/pass`；`Validation/shading-compare-01/report.md` 生成。退出码可能为 2（尚未开始补着色，预期不达标）。**核对**：`skin`/`hair`/`cloth` 重叠像素应 > MIN_PIXELS（`eye` 可能 low_sample）；`flip=yes`。这份数字就是 WP1.4 各着色项的起点与排序依据。

- [ ] **Step 3：提交（临时 index）**

`git add -- Tools/shading_compare.py`，信息 `feat(render): per-family shading A/B CLI + baseline report`。

### Task 3：着色公式单测脚手架（模板 + 先钉描边宽度 FOV 补偿）

确立"着色数学单测"的做法：把每个官方公式的**确定性子式**用纯 Python 镜像实现，对手推/已知值断言，钉住公式常量的转写正确性（防止 WP1.4 实现时抄错系数）。本任务先钉描边的 FOV 补偿 atan 多项式（C6 已核 `characternpr_skin/Sub0_Pass1_Vertex_b273.hlsl:531-543`），作为后续 skin/hair/cloth/eye/湿身各公式单测的模板。HLSL 侧的"渲染已知输入读回比对"测试随各 WP1.4 项实现时补。

**Files:**
- Create: `Tools/tests/test_shading_formulas.py`

- [ ] **Step 1：写测试 + 参考实现（同文件）**

```python
import math
import unittest


# Mirror of characternpr_skin/Sub0_Pass1_Vertex_b273.hlsl:531-543 (C6-verified).
# The official outline computes a FOV-half angle via this atan polynomial to keep
# screen-space outline width constant across FOV. Pins the poly-constant transcription.
def outline_fov_atan(proj_m11: float) -> float:
    f = -1.0 / proj_m11
    a = abs(f)
    small = a < 1.0
    r = a if small else 1.0 / a
    r2 = r * r
    poly = (1.0 + ((-0.3018949925899505615234375 + 0.087292902171611785888671875 * r2) * r2)) * r
    val = poly if small else (1.57079637050628662109375 - poly)
    return -val if f < 0 else val


class ShadingFormulaTests(unittest.TestCase):
    def test_outline_fov_atan_matches_atan(self):
        # URP ProjMatrix[1].y = 1/tan(fovY/2); f = -1/that = -tan(fovY/2) (<0 for fovY<180).
        # |got| should approximate atan(tan(fovY/2)) = fovY/2 for fovY < 90 (|f|<1).
        for fov_deg in (20, 35, 50, 70):
            half = math.radians(fov_deg) / 2
            m11 = 1.0 / math.tan(half)
            got = outline_fov_atan(m11)
            self.assertAlmostEqual(abs(got), half, places=2)


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 2：运行确认通过**

Run: `cd "A:/Hypergryph Launcher/games/Arknights Endfield/FractalMiner" && ../EndfieldUnpacker/.venv/Scripts/python.exe -m unittest discover -s Tools/tests -p "test_shading_formulas.py" -v`
Expected: PASS。

- [ ] **Step 3：提交（临时 index）**

`git add -- Tools/tests/test_shading_formulas.py`，信息 `test(render): shading-formula unit-test scaffold (outline FOV atan)`。

---

## 后续计划（本计划之外，各自成篇，均以本工具 + 各自着色单测验收）

1. **WP1.4a 描边全打光**：官方 CharacterOutline 片元（缩水 ForwardLit，借 GBuffer 八面体法线）；C6 `official-outline-skin-b273.md` + line-by-line 为源。
2. **WP1.4b 刘海投脸 overlayshadow + 地面投影 shadowreceiver**：两个官方独立 shader，需新 pass/材质 + 场景接线；C6 `official-overlayshadow-b5.md`/`official-shadowreceiver.md`。
3. **WP1.4c 雨淋湿身 liquidag**：`docs/research/official-wetness-b400-excerpt.txt` + `characternpr_liquidag`；接 `_CharacterParams10` + `_SilkStockings*`。
4. **WP1.4d dither / 透明 / clearcoat 矢量化**。
5. **WP1.3 网格通道补全 + 官方描边顶点**（切线/uv1/顶点色）。
6. **展示场景 + 可操作性**：`Typhoeus_Showcase.unity` 接入还原后角色，材质/后处理/雨淋参数 inspector 暴露；MMD 接入落地场景。

## Self-Review

- **Spec 覆盖**：§A.4 出口门禁①逐部件比色 A/B → Task 1+2；③展示场景与②着色单测的"做法"→ Task 3 立模板 + 后续计划列明。②③的完整落地在后续计划（本篇是度量子系统，spec 明确一子系统一计划）。
- **Placeholder 扫描**：无 TBD/TODO；所有代码步给出完整可执行代码。
- **类型一致**：`compare_families` 返回结构在 Task 1 Interfaces 与 Task 2 `render_md`/`main` 消费处一致（`mean_abs_rgb_max`/`p95_abs_rgb`/`within_8_lsb`/`low_sample`/`pass`/`pixels`）。`part_base`/`family_of`/`FAMILIES`/`WORK_SIZE` 命名前后一致。
- **Review Focus**：5 条各有测试（family 覆盖、outline 剥离、翻转方向复用、low_sample、WORK_SIZE 复用 + 均值手算）。




