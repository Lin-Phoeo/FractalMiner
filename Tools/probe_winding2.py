import struct, os
MeshDir = r"C:/Users/Administrator/Downloads/Typhoeus-Coral Coast RT.RX07-v1.1-SFW/Typhoeus-Coral Coast RT.RX07-v1.1-SFW/Meshes"
def vb0stride(c): return 40 if c==8 else 16
def load(c):
    d0 = open(os.path.join(MeshDir,f"Component{c}_VB0.buf"),'rb').read()
    s0 = vb0stride(c); nv = len(d0)//s0
    P=[]; N=[]
    for i in range(nv):
        x,y,z = struct.unpack_from('<fff', d0, i*s0)
        P.append((x,y,z))
        if c==8:
            nx,ny,nz = struct.unpack_from('<fff', d0, i*s0+12)
            N.append((nx,ny,nz))
    di = open(os.path.join(MeshDir,f"Component{c}_IB.buf"),'rb').read()
    fmt = 4 if nv>65535 else 2
    ni = len(di)//fmt
    I = ([struct.unpack_from('<I', di, i*4)[0] for i in range(ni)] if fmt==4
         else [struct.unpack_from('<H', di, i*2)[0] for i in range(ni)])
    return P, N, I, nv

# 1) 决定性绕序测试：C8 几何法线(绕序) vs 存储法线，都在 swap 后的 Unity 空间
P,N,I,nv = load(8)
agree=0; tot=0
ntri = len(I)//3
tstep = max(1, ntri//6000)
for t in range(0, ntri, tstep):
    a,b,c = I[t*3], I[t*3+1], I[t*3+2]
    if a>=nv or b>=nv or c>=nv: continue
    A=(P[a][0],P[a][2],-P[a][1]); B=(P[b][0],P[b][2],-P[b][1]); C=(P[c][0],P[c][2],-P[c][1])
    ux,uy,uz = B[0]-A[0],B[1]-A[1],B[2]-A[2]
    vx,vy,vz = C[0]-A[0],C[1]-A[1],C[2]-A[2]
    g=(uy*vz-uz*vy, uz*vx-ux*vz, ux*vy-uy*vx)
    n=(N[a][0],N[a][2],-N[a][1])   # 存储法线同样 swap
    gl=(g[0]*g[0]+g[1]*g[1]+g[2]*g[2])**0.5
    nl=(n[0]*n[0]+n[1]*n[1]+n[2]*n[2])**0.5
    if gl<1e-9 or nl<1e-9: continue
    d=(g[0]*n[0]+g[1]*n[1]+g[2]*n[2])/(gl*nl)
    tot+=1
    if d>0: agree+=1
print(f"C8 绕序 vs 存储法线一致率 = {agree/tot*100:.1f}% ({tot} 采样) → {'RecalculateNormals 方向正确' if agree/tot>0.5 else 'RecalculateNormals 会算反！需要交换索引'}")

# 2) 各 posed 组件引用质心（Unity 空间）
for c in [0,1,2,3,4,6,10]:
    P,N,I,nv = load(c)
    used=[P[i] for i in set(I) if i<nv]
    cx=sum(p[0] for p in used)/len(used); cy=sum(p[1] for p in used)/len(used); cz=sum(p[2] for p in used)/len(used)
    ys=[p[2] for p in used]
    print(f"C{c}: 引用{len(used)} 质心Unity=({cx:.3f},{cz:.3f},{-cy:.3f}) 高度范围[{min(ys):.2f},{max(ys):.2f}]")
