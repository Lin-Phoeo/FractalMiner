import struct, os
MeshDir = r"C:/Users/Administrator/Downloads/Typhoeus-Coral Coast RT.RX07-v1.1-SFW/Typhoeus-Coral Coast RT.RX07-v1.1-SFW/Meshes"
def vb0stride(c): return 40 if c==8 else 16
def vb1stride(c): return 16 if c==8 else (8 if c in (5,6,7) else 12)
def ibfmt(c, nv): return 4 if nv>65535 else 2
for c in [9,11,12,13,14]:
    p0 = os.path.join(MeshDir, f"Component{c}_VB0.buf")
    p1 = os.path.join(MeshDir, f"Component{c}_VB1.buf")
    pi = os.path.join(MeshDir, f"Component{c}_IB.buf")
    if not os.path.exists(p0): print(f"C{c}: no VB0"); continue
    d0 = open(p0,'rb').read(); s0 = vb0stride(c); nv = len(d0)//s0
    # raw bounds (Z-up: z=height)
    xs,ys,zs = [],[],[]
    step = max(1, nv//3000)
    for i in range(0, nv, step):
        x,y,z = struct.unpack_from('<fff', d0, i*s0)
        xs.append(x); ys.append(y); zs.append(z)
    print(f"C{c}: verts={nv} VB0stride={s0} raw bounds X[{min(xs):.2f},{max(xs):.2f}] Y[{min(ys):.2f},{max(ys):.2f}] Z[{min(zs):.2f},{max(zs):.2f}]")
    if os.path.exists(p1):
        d1 = open(p1,'rb').read(); s1 = vb1stride(c); n1 = len(d1)//s1
        us,vs = [],[]
        for i in range(0, n1, max(1,n1//2000)):
            u,v = struct.unpack_from('<ff', d1, i*s1)
            us.append(u); vs.append(v)
        print(f"      UV[{min(us):.2f},{max(us):.2f}]x[{min(vs):.2f},{max(vs):.2f}]")
    if os.path.exists(pi):
        di = open(pi,'rb').read(); ni = len(di)//ibfmt(c,nv)
        print(f"      IB: {ni} indices ({'u32' if ibfmt(c,nv)==4 else 'u16'})")
