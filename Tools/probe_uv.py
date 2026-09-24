import struct, os
MeshDir = r"C:/Users/Administrator/Downloads/Typhoeus-Coral Coast RT.RX07-v1.1-SFW/Typhoeus-Coral Coast RT.RX07-v1.1-SFW/Meshes"
def vb1stride(c):
    return 16 if c==8 else (8 if c in (5,6,7) else 12)
for c in [0,1,4,8]:
    p = os.path.join(MeshDir, f"Component{c}_VB1.buf")
    if not os.path.exists(p):
        print(f"C{c}: VB1 missing"); continue
    d = open(p,'rb').read()
    s = vb1stride(c)
    n = len(d)//s
    umin=vmin=1e9; umax=vmax=-1e9
    for i in range(0,n, max(1,n//5000)):  # sample ~5000
        u,v = struct.unpack_from('<ff', d, i*s)
        umin=min(umin,u); umax=max(umax,u); vmin=min(vmin,v); vmax=max(vmax,v)
    print(f"C{c}: stride={s} verts={n} U=[{umin:.3f},{umax:.3f}] V=[{vmin:.3f},{vmax:.3f}] first3={[(round(struct.unpack_from('<ff',d,i*s)[0],3), round(struct.unpack_from('<ff',d,i*s)[1],3)) for i in range(3)]}")
