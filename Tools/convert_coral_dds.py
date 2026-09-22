# -*- coding: utf-8 -*-
"""把珊瑚海岸 mod 的 Components dds 转成 png，分析每张内容，
并对比解包贴图尺寸，判断 Atlas 布局是否一致。"""
import sys, io, os
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')
from PIL import Image

MOD_TEX = r"C:/Users/Administrator/Downloads/Typhoeus-Coral Coast RT.RX07-v1.1-SFW/Typhoeus-Coral Coast RT.RX07-v1.1-SFW/Textures"
OUT_DIR = r"A:/Hypergryph Launcher/games/Arknights Endfield/FractalMiner/Assets/Typhoeus/CoralCoast"
UNPACK = r"A:/Hypergryph Launcher/games/Arknights Endfield/FractalMiner/Assets/Typhoeus"

os.makedirs(OUT_DIR, exist_ok=True)

print("="*100)
print("mod 贴图转换 + 内容分析")
print("="*100)
mod_info = []
for f in sorted(os.listdir(MOD_TEX)):
    if not f.endswith('.dds'): continue
    path = os.path.join(MOD_TEX, f)
    im = Image.open(path).convert('RGBA')
    w, h = im.size
    # 缩小采样算平均色
    sm = im.resize((64, 64), Image.LANCZOS)
    px = list(sm.getdata())
    n = len(px)
    r = sum(p[0] for p in px)//n; g = sum(p[1] for p in px)//n; b = sum(p[2] for p in px)//n
    a = sum(p[3] for p in px)//n
    # 判断是否 Atlas：看 4 个象限的颜色差异（Atlas 各区域颜色不同）
    quads = []
    for qy in range(2):
        for qx in range(2):
            box = im.crop((qx*w//2, qy*h//2, (qx+1)*w//2, (qy+1)*h//2)).resize((16,16), Image.LANCZOS)
            qpx = list(box.getdata())
            qn = len(qpx)
            qr = sum(p[0] for p in qpx)//qn
            qg = sum(p[1] for p in qpx)//qn
            qb = sum(p[2] for p in qpx)//qn
            quads.append((qr,qg,qb))
    quad_var = max(max(abs(quads[i][0]-quads[j][0]),abs(quads[i][1]-quads[j][1]),abs(quads[i][2]-quads[j][2])) for i in range(4) for j in range(i+1,4))
    out = os.path.join(OUT_DIR, f.replace('.dds','.png'))
    im.save(out, 'PNG')
    fmt = 'sRGB' if 'sRGB' in f else ('Linear' if 'Linear' in f else '?')
    bc = 'BC5' if 'BC5' in f else ('BC7' if 'BC7' in f else '?')
    print(f"{f[:50]:<50} {w}x{h} avg=({r:3},{g:3},{b:3},a={a:3}) {bc}-{fmt:<6} quadVar={quad_var:3} {'[Atlas?]' if quad_var>30 else ''}")
    mod_info.append((f, w, h, bc, fmt))

print()
print("="*100)
print("解包贴图尺寸（对比 Atlas 布局）")
print("="*100)
for f in sorted(os.listdir(UNPACK)):
    if not f.startswith('T_actor_typhoea') or not f.endswith('.png'): continue
    im = Image.open(os.path.join(UNPACK, f))
    print(f"{f:<45} {im.size}")
