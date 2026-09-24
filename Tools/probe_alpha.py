from PIL import Image
import os
TexDir = r"A:/Hypergryph Launcher/games/Arknights Endfield/FractalMiner/Assets/Typhoeus/CoralCoast"
files = [
    "Components-0-2-10 t=28ef925d BC7-sRGB.png",   # face (黑!)
    "Components-4 t=57b75235 BC7-sRGB.png",        # bodyA (正常)
    "Components-1 t=637eee72 BC7-sRGB.png",        # hair (正常)
    "Components-8-9 t=9e71626f BC7-sRGB.png",      # cloth (正常)
]
for f in files:
    p = os.path.join(TexDir, f)
    im = Image.open(p)
    print(f"{f}: mode={im.mode} size={im.size}")
    if im.mode == "RGBA":
        a = im.getchannel("A")
        mn, mx = a.getextrema()
        hist_zero = sum(1 for v in a.getdata() if v < 10)
        total = im.size[0]*im.size[1]
        print(f"   alpha min={mn} max={mx} 零alpha占比={hist_zero/total*100:.1f}%")
    elif im.mode == "RGB":
        print("   无 alpha 通道（Unity 导入 alpha=1）")
