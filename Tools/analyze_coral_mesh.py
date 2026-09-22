# -*- coding: utf-8 -*-
"""读 mod 的 Component VB1（UV 缓冲，R32G32_FLOAT），算每个 Component 的 UV 范围，
确定 Atlas 布局（每个部件在 Atlas 大图里的位置），为拆分贴图提供依据。
同时读 VB0（position）确认顶点数，对比官方 mesh 判断 mesh 是否一致。"""
import sys, io, os, struct
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')

MOD = r"C:/Users/Administrator/Downloads/Typhoeus-Coral Coast RT.RX07-v1.1-SFW/Typhoeus-Coral Coast RT.RX07-v1.1-SFW/Meshes"

def read_floats(path, fmt='ff', stride=8):
    """读二进制为 (x,y) float 对"""
    with open(path, 'rb') as f:
        data = f.read()
    n = len(data) // stride
    return [struct.unpack_from(fmt, data, i*stride) for i in range(n)]

print("="*110)
print("Component 顶点数 / UV 范围 / position 范围（判断 Atlas 布局 + mesh 是否与官方一致）")
print("="*110)
print(f"{'Comp':<6} {'VB0顶点':>8} {'VB1顶点':>8} {'UV_min':>22} {'UV_max':>22} {'pos_z_range':>20}")
for c in range(15):
    vb0 = os.path.join(MOD, f"Component{c}_VB0.buf")
    vb1 = os.path.join(MOD, f"Component{c}_VB1.buf")
    if not os.path.exists(vb0): continue
    # VB0: R32G32B32_FLOAT (position, stride 12)
    with open(vb0,'rb') as f: d0 = f.read()
    n0 = len(d0)//12
    pos = [struct.unpack_from('fff', d0, i*12) for i in range(min(n0,5000))]  # 采样前5000
    zs = [p[2] for p in pos]
    # VB1: R32G32_FLOAT (uv, stride 8)
    uv = read_floats(vb1, 'ff', 8)
    n1 = len(uv)
    if n1 > 0:
        umin = min(u[0] for u in uv); umax = max(u[0] for u in uv)
        vmin = min(u[1] for u in uv); vmax = max(u[1] for u in uv)
        uvstr = f"({umin:.3f},{vmin:.3f})-({umax:.3f},{vmax:.3f})"
    else:
        uvstr = "no VB1"
    zstr = f"[{min(zs):.2f},{max(zs):.2f}]" if zs else "?"
    print(f"C{c:<5} {n0:>8} {n1:>8} {uvstr:<46} {zstr}")

print()
print("="*110)
print("官方 mesh 顶点数对比（从 _typhoea_model_data.json）")
print("="*110)
import json
data = json.load(open(r"A:/Hypergryph Launcher/games/Arknights Endfield/FractalMiner/Assets/Typhoeus/_typhoea_model_data.json", encoding='utf-8'))
for m in data['meshes']:
    vc = len(m['vertices'])//3
    print(f"  {m['name']:<42} verts={vc}")
