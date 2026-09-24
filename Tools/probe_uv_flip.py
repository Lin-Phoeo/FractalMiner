from PIL import Image
import struct, os
TexDir = r"A:/Hypergryph Launcher/games/Arknights Endfield/FractalMiner/Assets/Typhoeus/CoralCoast"
MeshDir = r"C:/Users/Administrator/Downloads/Typhoeus-Coral Coast RT.RX07-v1.1-SFW/Typhoeus-Coral Coast RT.RX07-v1.1-SFW/Meshes"

def vb1stride(c): return 16 if c==8 else (8 if c in (5,6,7) else 12)
def uv_range(c):
    d = open(os.path.join(MeshDir,f"Component{c}_VB1.buf"),'rb').read()
    s = vb1stride(c); n = len(d)//s
    us,vs = [],[]
    for i in range(0, n, max(1,n//5000)):
        u,v = struct.unpack_from('<ff', d, i*s)
        us.append(u); vs.append(v)
    return min(us),max(us),min(vs),max(vs)

def tex_rows(filename, thresh=20):
    im = Image.open(os.path.join(TexDir, filename)).convert("RGBA")
    w,h = im.size
    alpha = im.getchannel("A")
    top_row = None; bot_row = None
    # 每 4 行采样一次（够判断范围）
    for y in range(0, h, 4):
        row_data = alpha.crop((0, y, w, y+4)).getdata()
        if any(v > thresh for v in row_data):
            if top_row is None: top_row = y
            bot_row = y + 3
    if top_row is None: return None
    # PIL 行0=顶, 行h=底. Unity UV V=0=底, V=1=顶. 行→V = 1 - row/h
    return (1.0 - bot_row/h, 1.0 - top_row/h), im.size

for name, c, f in [("face",0,"Components-0-2-10 t=28ef925d BC7-sRGB.png"),
                    ("body",4,"Components-4 t=57b75235 BC7-sRGB.png"),
                    ("cloth",8,"Components-8-9 t=9e71626f BC7-sRGB.png")]:
    umin,umax,vmin,vmax = uv_range(c)
    print(f"\n=== {name} (C{c}) ===")
    print(f"  mod UV: U[{umin:.3f},{umax:.3f}]  V[{vmin:.3f},{vmax:.3f}]")
    r = tex_rows(f)
    if r:
        (vbot,vtop), size = r
        print(f"  贴图内容 V[{vbot:.3f},{vtop:.3f}]  size={size}")
        overlap = not (vmin > vtop or vmax < vbot)
        print(f"  UV vs 贴图: {'✓重叠（不翻转OK）' if overlap else '❌不重叠！'}")
        if not overlap:
            fvmin, fvmax = 1-vmax, 1-vmin
            ov2 = not (fvmin > vtop or fvmax < vbot)
            print(f"  翻转后 V[{fvmin:.3f},{fvmax:.3f}] → {'✓重叠（需要翻转）' if ov2 else '✗仍不重叠'}")
