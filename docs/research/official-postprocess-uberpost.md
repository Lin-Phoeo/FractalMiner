# 官方后处理主链 UberPost 源码抽取(HGRP/PostProcessing/UberPost)

来源:`_dump_1.5.3/AllShader_1.5.3/Assets/packages/com.hg.render-pipelines/runtime/shaders/postprocessing/uberpost.shader`(335KB 巨型 dispatch 表)+ `uberpost\Sub0_Pass*_Vertex/Fragment_b*.hlsl`(Pass0 432 变体、Pass1 6、Pass2 24)。
代表变体:Pass0 b288(全关)/b336(+BLOOM)、Pass1 b726(全关)/b727(+VIGNETTE)、Pass2 b748(全关)/b751(+BWMASKTEX)/b754(+BWFLASHTEX)/b756(+BWFLASHTEX+RADIAL_BLUR_CHROMATIC_ABERRATION)。

> **验收修正(Claude 2026-09-28,已对源码核实)**:原稿把 b756 标为"BWMASK/BWFLASH/BLOOM"、并称极坐标 LUT 采样"属 BWMASKTEX(b756)"——**均误**。实测:`Sub0_Pass2_Fragment_b756.hlsl:2` 的关键字是 `BWFLASHTEX RADIAL_BLUR_CHROMATIC_ABERRATION`(非 BWMASKTEX);极坐标 atan2 LUT 采样(`0.15915493…`,t5=`_11`)在**两条**路径都出现且**常量槽不同**:BWFLASHTEX 路径(b754:223 / b756:237,用 cbuffer `_288`、`_320.x/.y`)与 BWMASKTEX 路径(b751:224,用 `_304`、`_256.w`、`_320.z`)。实现时按实际启用的 keyword 选对应槽位,勿照"仅 BWMASKTEX"抄。§4.6 BWFlash 段的 b756 行号正确,仅其"属 BWMASKTEX"归属描述按此更正。

**本文不含任何单元测试或参考实现**(独立 oracle 由验收方另写),仅忠实转写源码。

## 1. Pass 列表与顺序

| PassIdx | Name | 行号 | 状态 | 关键字 | 变体数 |
|---|---|---|---|---|---|
| 0 | UberPost | uberpost.shader:7-13 | ZTest Always、ZWrite Off、Cull Off | DIRTY_LENS、PERFORM_SHARPEN、USER_LUT、LENS_DISTORTION、VIGNETTE、VIGNETTE_MASK、BLOOM、BLOOM_DIRT、RADIAL_BLUR、RADIAL_BLUR_CHROMATIC_ABERRATION(:20-29) | 432 |
| 1 | UberPost_CompositeUI | :1773-1780 | **Blend SrcAlpha OneMinusSrcAlpha**(×2)、ZTest Always、ZWrite Off、Cull Off | VIGNETTE、VIGNETTE_MASK、BLOOM(:1787-1789) | 6 |
| 2 | UberPost_BWFlash | :1829-1835 | ZTest Always、ZWrite Off、Cull Off | RADIAL_BLUR、RADIAL_BLUR_CHROMATIC_ABERRATION、BWMASKTEX、BWFLASHTEX、BLOOM(:1842-1846) | 24 |
| 3 | UberPost_FisheyeEffect | :1958-1964 | ZTest Always、ZWrite Off、Cull Off | (无编译变体,include 计 0 ⚠待核) | 0 |
| 4 | UberPost_FisheyeEffectDepth | :2247-2253 | **ColorMask 0**、ZTest Always、Cull Off | 同上 ⚠待核 | 0 |

**链路顺序**(按 Pass0 片元内代码顺序):径向模糊(可选)→ 镜头脏污(可选)→ 镜头畸变(可选)→ **Bloom 合成(可选)** → 曝光 → **log 编码 → 2D 条带 LUT(分级/tone 曲线烧入 LUT)→ sRGB 解码** → 锐化(可选,在 LUT 前)→ 暗角(可选)→ **RGB 抖动**。**没有独立 tonemap keyword**——tone 曲线由 `lutbuilder2d` 烧进 LUT(本 shader 只做 log→LUT→sRGB)。

## 2. 输入纹理 / 寄存器(Pass0,b288)

| 寄存器 | 名称 | 用途 | 行号 |
|---|---|---|---|
| t3,space3 | `_InputTexture` | 主输入(HDR 线性) | Sub0_Pass0_Fragment_b288.hlsl:178 |
| t2,space3 | `_LogLut2D` | 2D 条带 LUT(分级 + tone) | :179 |
| t4,space3 | `_BloomTexture`(b336) | 预合成 bloom(来自 bloom.shader 链) | Sub0_Pass0_Fragment_b336.hlsl:179 |
| cb0(b4,space3) | `_RadialBlurParams/_VignetteParams1/2/_DirtyLensParams1/_VignetteColor/_DistortionParams1/2/_Lut_Params/_UserLut_Params/_BloomParams/_BloomThreshold/_BloomTint/_BloomDirtScaleOffset/_BWFlashThreshold/_BWFlashParams4/_BWFlashColor/_BWBackGroundColor/_FisheyeEffectParams1/_SharpenStrengthAndPadding/_RadialBlurParams2` | 各步骤参数 | Sub0_Pass0_Fragment_b288.hlsl:148-176 |

`_Lut_Params`:.xy = LUT 单条带尺寸、.z = 条带数、.w = 曝光前预缩放。

## 3. 顶点(全 Pass 共用形态)

全屏三角形:`_31 = float((VertexIndex << 1) & 2); _33 = float(VertexIndex & 2); pos = (xy×2 - 1)`;**翻转支持** `x × (1 - HGFlipX×2)`、`y = -(y × (1 - HGFlipY×2))`(PerPassConstants b0,space3,Sub0_Pass0_Vertex_b288.hlsl:33-43);UV = `(x, 1-y)`。

## 4. 逐步数学(Pass0)

### 4.1 Bloom 合成(BLOOM,b336:198-206)
```
input = _InputTexture.SampleLevel(uv); bloom = _BloomTexture.SampleLevel(uv)            // :198-200
bloomKnee = bloom × (1.0f - _BloomParams.z)                                              // :201
bloomHi  = (bloomKnee > 0.300000011920928955078125f) 逐通道                               // :202
bloomCurve = pow(bloom, 0.3300000131130218505859375f.xxx) × 1.49380004405975341796875f - 0.699999988079071044921875f.xxx   // :203
bright = max3(input)                                                                     // :204
knee   = clamp(bright - _BloomThreshold.y, 0, _BloomThreshold.z)                          // :205
提取   = input - (input × (max(_BloomThreshold.w × knee) × knee, bright - _BloomThreshold.x) / max(bright, 1e-5)) × _BloomParams.z   // :206 内
合成   = lerp(input, 提取 + (bloomHi ? bloomCurve : bloom) × _BloomTint.xyz, _BloomParams.x.xxx)   // :206 内
```
即"扣除阈值亮部 + 叠加 bloom 曲线值/染色"后进入曝光。

### 4.2 曝光 → log 编码(常驻,b288:198;与 b336:206 同式)
```
c = clamp( (log2( max( 合成 × _ExposureWithMiscParams.x × _Lut_Params.w × 5.555555820465087890625f + 0.04799599945545196533203125f.xxx, 0 ) )
        × 0.3010300099849700927734375f × 0.24416099488735198974609375f ) + 0.3860360085964202880859375f.xxx, 0, 1 )
```
(URP log 编码常数:5.5555… = 1/0.18 中灰、0.047996 偏置、0.30103 = log10(2)、0.244161、0.386036。)

### 4.3 LUT 采样(b288:199-204)
```
row = c.z × _Lut_Params.z; rowFloor = floor(row)
uv  = (c.xy × _Lut_Params.z) × _Lut_Params.xy + _Lut_Params.xy × 0.5f
uv.x += rowFloor × _Lut_Params.y
lut  = lerp(_LogLut2D.SampleLevel(uv), _LogLut2D.SampleLevel(uv + ( _Lut_Params.y, 0)), frac(row))
```

### 4.4 sRGB 解码(b288:205-207)
```
srgb = v ≤ 0.003130800090730190277099609375f ? v × 12.9200000762939453125f
                                              : pow(|v|, 0.4166666567325592041015625f) × 1.05499994754791259765625f - 0.054999999701976776123046875f
```

### 4.5 RGB 三通道抖动(b288:208,常驻最后一步)
```
dither = (frac( dot((171.0f, 231.0f), uv × _ScreenSize.xy) × (0.00970873795449733734130859375f, 0.0140845067799091339111328125f, 0.010309278033673763275146484375f) ) - 0.5f.xxx)
         × 0.0039215688593685626983642578125f.xxx × 0.3499999940395355224609375f
out = srgb + dither; out.a = min(src.a, 1.0f)
```
(每通道不同哈希系数 = 逐通道抖动,幅度 ±0.35/255。)

### 4.6 keyword 门控步骤(b304/b336/b727/b756 变体补记)
- **VIGNETTE(Pass0 版,b304:196-201,在曝光前乘入 input)**:
```
d = |uv - _VignetteParams1.xy(center)| × lerp(_VignetteParams2.x(intensity), 1.0f, _VignetteParams1.w)      // :196
d.x = d.x × lerp(1.0f, 1.5f × clamp(_VignetteParams2.x × 1.0499999523162841796875f, 0, 1), _VignetteParams1.w)   // :197
d.y = clamp((d.y × lerp(1.0f, _VignetteParams2.x × 2.0f, w)) + (clamp(_VignetteParams2.x - 2.7999999523162841796875f, 0, 1) × 5.0f), 0, 1)   // :198
d.x ×= lerp(lerp(1.0f, _ExposureWithMiscParams.z, w), _ExposureWithMiscParams.z × 0.5625f, w)               // :200 纵横比(0.5625 = 9/16)
v  = pow(clamp(d, 0, 1), _VignetteParams2.z(power))                                                          // :201
input ×= lerp(_VignetteColor.xyz, 1.0f.xxx, pow(clamp(1.0f - dot(v, v), 0, 1), _VignetteParams2.y(smoothness)))   // :202
```
  CompositeUI 版(b727:198-201)为简式:`d = |uv - center| × c32.x;v = pow(clamp(d,0,1), c32.z);rgb ×= lerp(c64(vignette color), 1, pow(clamp(1-dot(v,v),0,1), c32.y))`。
- **RADIAL_BLUR / CHROMATIC_ABERRATION**(b756:201-213):`off = (uv - center) × pow(dist, exp) × lerp(1, 1/max(0.01, dist), radialZ)`;`sum = 本像素 + Σ5 次采样(uv - off × 表值 × strength)`;`avg = sum × 0.16666667163372039794921875f`(6 除)。
- **BWFlash(黑白闪光,b756:214-238 与 b748:40-73)**:两版都先**灰度化**——b748(全关)直接取输入 `.x` 作灰度(`_72 = (_66.x, _66.yz, clamp(a,0,1))`,f_b748:44-45,即输入已预灰度打包);b756 为 5 采样均值后取 `.r`。BW 阈值 `_80 = c.z + c.x - c.x×c.z×2.0f`;常规 LUT 链(曝光/log/LUT/sRGB,常数同 §4.2-4.4,曝光缩放用 `_15_Stripped_112.w`);`mask = smoothstep((1-_80) - c.y, _80 - c.y, 灰度)`,输出 `lerp(LUT sRGB 色, _BWFlashColor × mask + _BWBackGroundColor × (1-mask), c320.w)`(b748:66-71 / b756:237-238)。**极坐标 LUT 采样出现在 BW 贴图路径**(BWFLASHTEX 或 BWMASKTEX,见文首验收修正;b756 走 BWFLASHTEX,:237)(`atan2 多项式(同描边 atan 系数 -0.3018949925899505615234375f/0.087292902171611785888671875f) + π 分支)× 0.15915493667125701904296875f, dist×2) × scale.zw + offset.zw` 采样遮罩 LUT 的 .x 后进入 mask 组合)。
- 其余(DIRTY_LENS、LENS_DISTORTION、VIGNETTE_MASK、BLOOM_DIRT、USER_LUT、PERFORM_SHARPEN)未逐行抽取 ⚠待核(常量槽 `_DirtyLensParams1/_DistortionParams1/2/_UserLut_Params/_BloomDirtScaleOffset/_SharpenStrengthAndPadding` 已定位,b288:153/155-156/158/162/174)。

## 5. Pass1/Pass2 说明
- **CompositeUI**:无 LUT/曝光,直接采样 UI 纹理(t2,space3,匿名 `_9`)+ 可选 vignette;b726 全关 = `out = (tex.rgb, clamp(tex.a,0,1))` 透传(f_b726,27 行)。
- **BWFlash 全关 b748(73 行,已全文)**:输入 t? 匿名纹理(预灰度打包,取 `.x`),BW 阈值 + 灰度直通 mask + 常规 LUT 链,核心见 4.6;无径向模糊/无极坐标 LUT。
- **FisheyeEffect/FisheyeEffectDepth**:无编译变体(include 0)⚠待核(可能仅 UI 参数化或未启用)。

## 6. _Property 清单
**uberpost.shader 没有 Properties 块**(L1-30 直接 SubShader)——所有参数(`_RadialBlurParams` 等)由 C# 侧 MaterialPropertyBlock/ComputeBuffer 注入,不暴露 inspector。`_ExposureWithMiscParams/_ScreenSize` 来自 ShaderVariablesGlobal。

## 7. ⚠待核汇总
1. DIRTY_LENS/LENS_DISTORTION/VIGNETTE_MASK/BLOOM_DIRT/USER_LUT/PERFORM_SHARPEN 的逐行公式(对应含 keyword 变体未读;参数槽已定位)。
2. FisheyeEffect/FisheyeEffectDepth 两个 pass 无变体的原因。
3. `_91[5]`(径向模糊采样表)的具体数值(声明在 f_b756 静态区,未抄录)。
4. BWFlash 灰度输入纹理 `_7`(b748)的打包来源(C# 侧哪一 pass 产出)。

---
*仅静态转写,行号指 uberpost.shader 与 uberpost\Sub0_Pass*.hlsl;无测试/参考实现。*
