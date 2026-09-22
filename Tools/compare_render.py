# -*- coding: utf-8 -*-
"""对比当前渲染 front-align.png 与官方帧 official-front-1280.png，
量化色调/亮度/饱和度差异，定位"不像原游戏"的客观原因。"""
import sys, io
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')
from PIL import Image

OFFICIAL = r"Validation/Captures/tifuluosi-front-20260917/official-front-1280.png"
CURRENT  = r"Validation/front-align.png"

def load(p, size=(640, 400)):
    im = Image.open(p).convert('RGB').resize(size, Image.LANCZOS)
    return im

off = load(OFFICIAL)
cur = load(CURRENT)
W, H = off.size

def stats(im):
    px = list(im.getdata())
    n = len(px)
    r = sum(p[0] for p in px)/n
    g = sum(p[1] for p in px)/n
    b = sum(p[2] for p in px)/n
    # 亮度
    lum = sum(0.299*p[0]+0.587*p[1]+0.114*p[2] for p in px)/n
    # 饱和度（max-min 平均）
    sat = sum(max(p)-min(p) for p in px)/n
    return r, g, b, lum, sat

def region_stats(im, y0, y1):
    box = im.crop((0, y0, W, y1))
    return stats(box)

print("="*90)
print("整体对比（缩放到 640x400，含背景）")
print("="*90)
or_, og, ob, ol, os_ = stats(off)
cr, cg, cb, cl, cs = stats(cur)
print(f"{'指标':<10} {'官方帧':>22} {'当前渲染':>22} {'差值(当前-官方)':>20}")
print(f"{'R':<10} {or_:>22.1f} {cr:>22.1f} {cr-or_:>+20.1f}")
print(f"{'G':<10} {og:>22.1f} {cg:>22.1f} {cg-og:>+20.1f}")
print(f"{'B':<10} {ob:>22.1f} {cb:>22.1f} {cb-ob:>+20.1f}")
print(f"{'亮度Y':<10} {ol:>22.1f} {cl:>22.1f} {cl-ol:>+20.1f}")
print(f"{'饱和度':<10} {os_:>22.1f} {cs:>22.1f} {cs-os_:>+20.1f}")

print()
print("="*90)
print("分区域对比（上=头/发 中=胸/衣 下=腿/裙，各 1/3 高度）")
print("="*90)
for name, y0, y1 in [("上1/3(头)", 0, H//3), ("中1/3(身)", H//3, 2*H//3), ("下1/3(腿)", 2*H//3, H)]:
    or_, og, ob, ol, os_ = region_stats(off, y0, y1)
    cr, cg, cb, cl, cs = region_stats(cur, y0, y1)
    print(f"\n[{name}]  官方(R,G,B,亮度,饱和)=({or_:.0f},{og:.0f},{ob:.0f},{ol:.0f},{os_:.0f})  "
          f"当前=({cr:.0f},{cg:.0f},{cb:.0f},{cl:.0f},{cs:.0f})")
    print(f"    差值  R={cr-or_:+.0f}  G={cg-og:+.0f}  B={cb-ob:+.0f}  亮度={cl-ol:+.0f}  饱和={cs-os_:+.0f}")

print()
print("="*90)
print("亮度直方图对比（0-255 分 8 档，% 像素占比）")
print("="*90)
def hist(im):
    px = list(im.getdata())
    bins = [0]*8
    for p in px:
        y = int(0.299*p[0]+0.587*p[1]+0.114*p[2])
        bins[min(y//32, 7)] += 1
    n = len(px)
    return [b/n*100 for b in bins]
ho, hc = hist(off), hist(cur)
print(f"{'亮度区间':<16} {'官方%':>8} {'当前%':>8} {'差':>8}")
for i in range(8):
    print(f"{i*32:>3}-{i*32+31:<6} {ho[i]:>8.1f} {hc[i]:>8.1f} {hc[i]-ho[i]:>+8.1f}")
