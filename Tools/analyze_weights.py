# -*- coding: utf-8 -*-
"""分析 _typhoea_model_data.json：判定每个 mesh 的权重索引空间（全局 vs 局部），
定位提弗洛斯角掉落地面问题的数据层根因。"""
import json, sys, io
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')

JSON_PATH = r"A:\Hypergryph Launcher\games\Arknights Endfield\FractalMiner\Assets\Typhoeus\_typhoea_model_data.json"

with open(JSON_PATH, 'r', encoding='utf-8') as f:
    data = json.load(f)

bones = data['bones']
nb = len(bones)
meshes = data['meshes']
print(f"total bones = {nb}, total meshes = {len(meshes)}")

# --- 检查骨骼数组是否 pre-order（parent index < self index）---
preorder_ok = all(b['parent'] < i for i, b in enumerate(bones) if b['parent'] >= 0)
print(f"bones array is pre-order (parent<self): {preorder_ok}")

# 骨骼名里找 horn 相关
horn_names = [i for i, b in enumerate(bones) if 'horn' in b['name'].lower() or 'jiao' in b['name'].lower()]
print(f"horn-like bone indices: {horn_names[:20]}")
for i in horn_names[:12]:
    print(f"  [{i}] {bones[i]['name']}  parent={bones[i]['parent']}")

print()
print("=" * 100)
print(f"{'mesh name':<42} {'bcount':>6} {'wMin':>5} {'wMax':>5} {'allInBonesSet':>13} {'allLocal':>9} {'identBP':>7} {'verdict'}")
print("=" * 100)

problem_meshes = []
for m in meshes:
    name = m['name']
    mb = m.get('bones') or []
    bcount = len(mb)
    bones_set = set(mb)
    # m.bones 自身越界检测
    bad_bones = [g for g in mb if g < 0 or g >= nb]

    bw_idx = m.get('boneWeightIndices') or []
    bw_val = m.get('boneWeightValues') or []
    vcount = len(m.get('vertices', [])) // 3
    idx_count = len(bw_idx) // 4

    wmin, wmax = (0, -1)
    if bw_idx:
        wmin, wmax = min(bw_idx), max(bw_idx)

    # 全部权重索引都是 m.bones 集合成员（含 -1 除外）→ 全局索引证据
    nonneg = [x for x in bw_idx if x >= 0]
    all_in_set = bool(nonneg) and all(x in bones_set for x in nonneg)
    # 全部 < bcount → 局部索引证据
    all_local = bool(bw_idx) and (wmax < bcount)

    # bindpose 恒等检测
    bps = m.get('bindPoses') or []
    ident = 0
    for b in range(bcount):
        off = b * 16
        if off + 15 >= len(bps):
            ident += 1
            continue
        chunk = bps[off:off + 16]
        if chunk[0] == 1 and chunk[5] == 1 and chunk[10] == 1 and chunk[15] == 1 and \
           all(chunk[i] == 0 for i in range(16) if i not in (0, 5, 10, 15)):
            ident += 1

    if bad_bones:
        verdict = f"M_BONES_OUT_OF_RANGE({len(bad_bones)})"
    elif all_in_set and not all_local:
        verdict = "WEIGHTS_GLOBAL"   # 权重是全局骨骼索引 → Unity 越界
    elif all_local and not all_in_set:
        verdict = "WEIGHTS_LOCAL"
    elif all_local and all_in_set:
        verdict = "AMBIGUOUS(idmap)"
    else:
        verdict = f"MIXED(min={wmin},max={wmax},bc={bcount})"
    if ident >= max(1, bcount * 0.9) and bcount > 0:
        verdict += f"+IDENT_BP({ident}/{bcount})"

    flag = " *** " if "GLOBAL" in verdict or "OUT_OF_RANGE" in verdict or "MIXED" in verdict else ""
    print(f"{name:<42} {bcount:>6} {wmin:>5} {wmax:>5} {str(all_in_set):>13} {str(all_local):>9} {ident:>7} {verdict}{flag}")
    if flag:
        problem_meshes.append(name)

print()
print(f"problem meshes: {len(problem_meshes)}")
for p in problem_meshes:
    print("  -", p)

# --- 对 horn mesh 深挖 ---
print()
print("=" * 100)
print("horn-like mesh deep dive:")
for m in meshes:
    if 'horn' in m['name'].lower():
        mb = m['bones']
        bcount = len(mb)
        bw_idx = m['boneWeightIndices']
        nonneg = [x for x in bw_idx if x >= 0]
        used_global = sorted(set(nonneg))
        print(f"\n  {m['name']}: bcount={bcount}, verts={len(m['vertices'])//3}, unique_used_global_idx={len(used_global)}")
        print(f"  m.bones = {mb}")
        print(f"  used_global(not in m.bones): {[x for x in used_global if x not in set(mb)][:30]}")
        # 显示引用的全局骨骼名
        names = [bones[x]['name'] for x in used_global if 0 <= x < nb][:15]
        print(f"  used bone names: {names}")
