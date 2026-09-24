# -*- coding: utf-8 -*-
"""对比官方贴图与珊瑚海岸 mod 贴图的图集布局：
生成并排缩略图，并检查 UV 覆盖区域是否对应。"""
import sys, io, os
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')
from PIL import Image

ASSET = r"A:/Hypergryph Launcher/games/Arknights Endfield/FractalMiner/Assets/Typhoeus"
MOD   = r"A:/Hypergryph Launcher/games/Arknights Endfield/FractalMiner/Assets/Typhoeus/CoralCoast"
OUT   = r"A:/Hypergryph Launcher/games/Arknights Endfield/FractalMiner/Validation"
os.makedirs(OUT, exist_ok=True)

pairs = [
    ("hair  D", f"{ASSET}/T_actor_typhoea_hair_01_D.png",  f"{MOD}/Components-1 t=637eee72 BC7-sRGB.png"),
    ("face  D", f"{ASSET}/T_actor_typhoea_face_01_D.png",  f"{MOD}/Components-0-2-10 t=28ef925d BC7-sRGB.png"),
    ("body  D", f"{ASSET}/T_actor_typhoea_body_01_D.png",  f"{MOD}/Components-4 t=57b75235 BC7-sRGB.png"),
    ("cloth D", f"{ASSET}/T_actor_typhoea_cloth_01_D.png", f"{MOD}/Components-8-9 t=9e71626f BC7-sRGB.png"),
]

for name, official, mod in pairs:
    im_o = Image.open(official).convert("RGB")
    im_m = Image.open(mod).convert("RGB")
    print(f"{name}: official {im_o.size[0]}x{im_o.size[1]}  |  mod {im_m.size[0]}x{im_m.size[1]}")
    # 缩放到相同高度 512
    H = 512
    def th(im):
        w = int(im.size[0] * H / im.size[1])
        return im.resize((w, H), Image.LANCZOS)
    to, tm = th(im_o), th(im_m)
    canvas = Image.new("RGB", (to.size[0] + tm.size[0] + 20, H), (40, 40, 40))
    canvas.paste(to, (0, 0))
    canvas.paste(tm, (to.size[0] + 20, 0))
    out_path = f"{OUT}/atlas_compare_{name.split()[0]}.png"
    canvas.save(out_path)
    print(f"  -> {out_path}")
print("done")
