# -*- coding: utf-8 -*-
"""探测 mod Component 缓冲的 stride/格式：
IB(uint16/uint32?), VB0(位置 stride), VB1(UV stride), VB2(混合)。
并输出全局 bbox（确认世界坐标范围与身高尺度）。"""
import sys, io, os, struct
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')

MESH = r"C:/Users/Administrator/Downloads/Typhoeus-Coral Coast RT.RX07-v1.1-SFW/Typhoeus-Coral Coast RT.RX07-v1.1-SFW/Meshes"

# 先看 Components.buf 开头（可能是元数据）
with open(os.path.join(MESH, "Components.buf"), "rb") as f:
    head = f.read(64)
print("Components.buf head:", head[:32].hex(), "| ascii:", "".join(chr(b) if 32<=b<127 else "." for b in head[:32]))

print(f"\n{'C':<4} {'IB size':>9} {'idx(u16)':>9} {'maxIdx':>7} {'VB0':>9} {'v16':>7} {'v12':>7} {'VB1/v':>6} {'VB2/v':>6}")
gmin = [1e30]*3; gmax = [-1e30]*3
for c in range(15):
    ib_p = os.path.join(MESH, f"Component{c}_IB.buf")
    if not os.path.exists(ib_p): continue
    ib = open(ib_p,'rb').read()
    n16 = len(ib)//2
    idx = struct.unpack_from(f"<{n16}H", ib, 0) if n16 < 2000000 else []
    mx = max(idx) if idx else -1
    vb0 = os.path.getsize(os.path.join(MESH, f"Component{c}_VB0.buf"))
    vb1 = os.path.getsize(os.path.join(MESH, f"Component{c}_VB1.buf"))
    vb2 = os.path.getsize(os.path.join(MESH, f"Component{c}_VB2.buf"))
    v16 = vb0/16 if vb0%16==0 else -1
    v12 = vb0/12 if vb0%12==0 else -1
    s1 = f"{vb1/v16:.2f}" if v16 and vb1%v16==0 else "?"
    s2 = f"{vb2/v16:.2f}" if v16 and vb2%v16==0 else "?"
    print(f"C{c:<3} {len(ib):>9} {n16:>9} {mx:>7} {vb0:>9} {v16:>7.0f} {v12:>7.0f} {s1:>6} {s2:>6}")
    # 读 VB0 前 2000 顶点算 bbox（假设 stride 16：pos 可能是 float4，取前 3 分量）
    with open(os.path.join(MESH, f"Component{c}_VB0.buf"),'rb') as f:
        d = f.read(min(vb0, 16*20000))
    nv = len(d)//16
    for i in range(0, nv, max(1, nv//2000)):
        x,y,z = struct.unpack_from("fff", d, i*16)
        for k,v in enumerate((x,y,z)):
            gmin[k]=min(gmin[k],v); gmax[k]=max(gmax[k],v)

print(f"\n全局 bbox(采样, stride16): min=({gmin[0]:.2f},{gmin[1]:.2f},{gmin[2]:.2f}) max=({gmax[0]:.2f},{gmax[1]:.2f},{gmax[2]:.2f})")
print(f"尺寸: {gmax[0]-gmin[0]:.2f} x {gmax[1]-gmin[1]:.2f} x {gmax[2]-gmin[2]:.2f}")
