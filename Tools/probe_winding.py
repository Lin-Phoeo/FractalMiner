import struct, os
MeshDir = r"C:/Users/Administrator/Downloads/Typhoeus-Coral Coast RT.RX07-v1.1-SFW/Typhoeus-Coral Coast RT.RX07-v1.1-SFW/Meshes"
def vb0stride(c): return 40 if c==8 else 16
def vb1stride(c): return 16 if c==8 else (8 if c in (5,6,7) else 12)

def load(c):
    d0 = open(os.path.join(MeshDir,f"Component{c}_VB0.buf"),'rb').read()
    s0 = vb0stride(c); nv = len(d0)//s0
    V = [struct.unpack_from('<fff', d0, i*s0) for i in range(nv)]
    di = open(os.path.join(MeshDir,f"Component{c}_IB.buf"),'rb').read()
    fmt = 4 if nv>65535 else 2
    ni = len(di)//fmt
    if fmt==4: I = [struct.unpack_from('<I', di, i*4)[0] for i in range(ni)]
    else:      I = [struct.unpack_from('<H', di, i*2)[0] for i in range(ni)]
    return V, I, nv

# 1) 绕序检测：swap 到 Unity 空间 (x, z, -y) 后，三角形法线 vs 径向朝外方向
for c in [0, 4, 8]:
    V, I, nv = load(c)
    used = set(I)
    dots = []
    step = max(1, len(I)//6 // 3 * 3)
    for t in range(0, len(I)-2, step*3 if step*3<=len(I)-2 else 3):
        pass
    # 简化：遍历所有三角形（步长采样三角形）
    ntri = len(I)//3
    tstep = max(1, ntri//4000)
    for t in range(0, ntri, tstep):
        a,b,cc = I[t*3], I[t*3+1], I[t*3+2]
        if a>=nv or b>=nv or cc>=nv: continue
        ax,ay,az = V[a]; bx,by,bz = V[b]; cx,cy,cz = V[cc]
        # Z-up -> Y-up: (x, z, -y)
        A=(ax,az,-ay); B=(bx,bz,-by); C=(cx,cz,-cy)
        ux,uy,uz = B[0]-A[0], B[1]-A[1], B[2]-A[2]
        vx,vy,vz = C[0]-A[0], C[1]-A[1], C[2]-A[2]
        nx,ny,nz = uy*vz-uz*vy, uz*vx-ux*vz, ux*vy-uy*vx
        cxm = (A[0]+B[0]+C[0])/3; cym=(A[1]+B[1]+C[1])/3; czm=(A[2]+B[2]+C[2])/3
        # 径向：水平面内 (x, z) 相对身体中轴 (0, czm)
        rx, rz = cxm, czm
        rl = (rx*rx+rz*rz) ** 0.5
        if rl < 1e-4: continue
        dot = (nx*rx + nz*rz) / rl
        dots.append(dot)
    pos = sum(1 for d in dots if d > 0)
    print(f"C{c}: 采样三角形 {len(dots)}，法线朝外占比 = {pos/len(dots)*100:.1f}%  ({'✓ 绕序OK' if pos/len(dots)>0.7 else '✗ 绕序反了！' if pos/len(dots)<0.3 else '? 混合'})")

# 2) C13/C14 只用 IB 引用顶点的 bounds
for c in [13, 14]:
    V, I, nv = load(c)
    used = [V[i] for i in set(I) if i < nv]
    xs=[p[0] for p in used]; ys=[p[1] for p in used]; zs=[p[2] for p in used]
    print(f"C{c}: 引用顶点 {len(used)}/{nv}，bounds X[{min(xs):.3f},{max(xs):.3f}] Y[{min(ys):.3f},{max(ys):.3f}] Z[{min(zs):.3f},{max(zs):.3f}]")

# 3) C6 iris 中心（作为眼部锚点，posed 空间）
V6, I6, nv6 = load(6)
used6 = [V6[i] for i in set(I6) if i < nv6]
cx = sum(p[0] for p in used6)/len(used6); cy = sum(p[1] for p in used6)/len(used6); cz = sum(p[2] for p in used6)/len(used6)
print(f"C6 iris: 引用顶点 {len(used6)}，质心 raw=({cx:.3f},{cy:.3f},{cz:.3f}) → Unity=({cx:.3f},{cz:.3f},{-cy:.3f})")
