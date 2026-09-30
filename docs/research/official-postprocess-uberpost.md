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

**代表变体内部顺序，不是所有 keyword 的统一顺序**:帧 6411 匹配的 Pass0 b354(`BLOOM PERFORM_SHARPEN VIGNETTE`)为主输入及四邻域 → 锐化 → 主色曝光 → Bloom 合成 → 暗角 → log 编码 → 2D 条带 LUT → 线性→sRGB 编码(OETF) → RGB 抖动(`Sub0_Pass0_Fragment_b354.hlsl:198–257`)。b336 也先曝光主色再合成 Bloom。不可把锐化/暗角移到 LUT 后，也不可把曝光移到 Bloom 合成后：Bloom 输入已经过其生成端的曝光，后者会重复曝光 Bloom。其他 keyword 的交互须核对对应组合源码，而不是拼接单开变体。

**[校正 2026-09-30]** §4.4 是 OETF，不是解码。LUT 采样值按线性结果处理，此 shader 写出显示域 sRGB 数值；帧 6411 event1205 输出 ResourceId 19599 为 `R8G8B8A8_UNORM`，不能由此推断所有平台/其他 pass 的最终 backbuffer 格式。这里没有独立 tonemap keyword，已检查的 LUT 调色/tonemap 见 lutbuilder2d 文档；不能据此证明全游戏不存在其他 tonemap 路径。

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
src = _InputTexture.SampleLevel(uv); input = src.rgb × _ExposureWithMiscParams.x        // :198-199
bloom = _BloomTexture.SampleLevel(uv).rgb                                               // :200
bloomKnee = bloom × (1.0f - _BloomParams.z)                                              // :201
bloomHi  = (bloomKnee > 0.300000011920928955078125f) 逐通道                               // :202
bloomCurve = pow(bloom, 0.3300000131130218505859375f.xxx) × 1.49380004405975341796875f - 0.699999988079071044921875f.xxx   // :203
bright = max3(input)                                                                     // :204
knee   = clamp(bright - _BloomThreshold.y, 0, _BloomThreshold.z)                          // :205
提取   = input - (input × (max((_BloomThreshold.w × knee) × knee, bright - _BloomThreshold.x) / max(bright, 9.9999997473787516355514526367188e-05)) × _BloomParams.z   // :206 内
合成   = lerp(input, 提取 + (bloomHi ? bloomCurve : bloom) × _BloomTint.xyz, _BloomParams.x.xxx)   // :206 内
```
即对已曝光主色扣除阈值亮部、叠加 Bloom 曲线值/染色，随后进入 log 编码。Bloom 的曝光在生成端，不能在这里再次对整个合成色乘曝光。

### 4.2 曝光与 log 编码(须区分输入域)
```
c = clamp( (log2( max( logInput × _Lut_Params.w × 5.555555820465087890625f + 0.04799599945545196533203125f.xxx, 0 ) )
        × 0.3010300099849700927734375f × 0.24416099488735198974609375f ) + 0.3860360085964202880859375f.xxx, 0, 1 )
```
`logInput` 在 b288:198 是 `src.rgb × Exposure.x`；在 b336:206 是 §4.1 的合成色(已包含曝光)；在 b354:246 是曝光/Bloom 后再乘暗角的色。上述常数形成 LogC 型编码；5.5555…≈1/0.18、0.30103≈log10(2)。

### 4.3 LUT 采样(b288:199-204)
```
row = c.z × _Lut_Params.z; rowFloor = floor(row)
uv  = (c.xy × _Lut_Params.z) × _Lut_Params.xy + _Lut_Params.xy × 0.5f
uv.x += rowFloor × _Lut_Params.y
lut  = lerp(_LogLut2D.SampleLevel(uv), _LogLut2D.SampleLevel(uv + ( _Lut_Params.y, 0)), frac(row))
```

### 4.4 线性→sRGB 编码 / OETF(b288:205-207)
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
(每通道不同哈希系数 = 逐通道抖动；`frac-0.5` 的范围是 [-0.5,0.5)，故幅度为 [-0.175/255,+0.175/255)，不是 ±0.35/255。)

### 4.6 keyword 门控步骤(b304/b336/b727/b756 变体补记)
- **VIGNETTE(Pass0 版,b304:196-201,在曝光前乘入 input)**:
```
d = |uv - _VignetteParams1.xy(center)| × lerp(_VignetteParams2.x(intensity), 1.0f, _VignetteParams1.w)      // :196
d.x = d.x × lerp(1.0f, 1.5f × clamp(_VignetteParams2.x × 1.0499999523162841796875f, 0, 1), _VignetteParams1.w)   // :197
d.y = clamp((d.y × lerp(1.0f, _VignetteParams2.x × 2.0f, w)) + (clamp(_VignetteParams2.x - 2.7999999523162841796875f, 0, 1) × 5.0f), 0, 1)   // :198
d.x ×= lerp(lerp(1.0f, _ExposureWithMiscParams.z, _VignetteParams2.w), _ExposureWithMiscParams.z × 0.5625f, _VignetteParams1.w) // :200，内外两权重不同
v  = pow(clamp(d, 0, 1), _VignetteParams2.z(power))                                                          // :201
input ×= lerp(_VignetteColor.xyz, 1.0f.xxx, pow(clamp(1.0f - dot(v, v), 0, 1), _VignetteParams2.y(smoothness)))   // :202
```
  CompositeUI 版(b727:198-201)为简式:`d = |uv - center| × c32.x;v = pow(clamp(d,0,1), c32.z);rgb ×= lerp(c64(vignette color), 1, pow(clamp(1-dot(v,v),0,1), c32.y))`。
- **RADIAL_BLUR / CHROMATIC_ABERRATION**(b756:201-213):`off = (uv - center) × pow(dist, exp) × lerp(1, 1/max(0.01, dist), radialZ)`;`sum = 本像素 + Σ5 次采样(uv - off × 表值 × strength)`;`avg = sum × 0.16666667163372039794921875f`(6 除)。
- **BWFlash(黑白闪光,b756/b748)**：b748:55–69把输入`.r`用于BW mask，但完整`.rgb`进入LUT链；没有先把全色灰度化，也不能证明输入已预灰度打包。b756径向均值后的`.r`供mask。BW阈值、LUT及颜色混合由对应源码决定；`_Stripped_112.w`是该分支LUT输入缩放，匿名槽不是已证明的全局曝光别名。极坐标贴图同时出现在BWFLASHTEX与BWMASKTEX，槽位按文首修正及R2.7分别绑定，不能混用。
- 其余(DIRTY_LENS、LENS_DISTORTION、VIGNETTE_MASK、BLOOM_DIRT、USER_LUT、PERFORM_SHARPEN)未逐行抽取 ⚠待核(常量槽 `_DirtyLensParams1/_DistortionParams1/2/_UserLut_Params/_BloomDirtScaleOffset/_SharpenStrengthAndPadding` 已定位,b288:153/155-156/158/162/174)。

## 5. Pass1/Pass2 说明
- **CompositeUI**:无 LUT/曝光,直接采样 UI 纹理(t2,space3,匿名 `_9`)+ 可选 vignette;b726 全关 = `out = (tex.rgb, clamp(tex.a,0,1))` 透传(f_b726,27 行)。
- **BWFlash全关b748**：匿名输入`.r`驱动mask、`.rgb`驱动LUT，输入生产者/打包语义待核；无径向模糊/极坐标LUT。
- **FisheyeEffect/FisheyeEffectDepth**:源码内联在 wrapper，不是缺失实现。`uberpost.shader:2223–2231` 以 `aspect=ScreenParams.x/ScreenParams.y`、`p=uv*2-1`、`p.x/=aspect`、`q=p/(1+FisheyeParams1.x)`、`r=length(q)`、`q*=1+FisheyeParams1.x*r*r`、`q.x*=aspect` 得采样 UV `(q+1)/2`；Pass3 取输入 RGBA。Pass4 同形坐标，在 `:2512–2521` 写输入纹理 `.x` 到 `SV_Depth`，且 ColorMask 0。启用条件/资源生产者仍待核。

## 6. _Property 清单
**uberpost.shader 没有 Properties 块**(L1-30 直接 SubShader)。cbuffer 中存在参数并不证明生产端使用 C#、MaterialPropertyBlock 或 ComputeBuffer；只确认 GPU 缓冲布局，CPU/C++ 生产方式待核。`_ExposureWithMiscParams/_ScreenSize` 位于 ShaderVariablesGlobal。

## 7. ⚠待核汇总
1. DIRTY_LENS/LENS_DISTORTION/VIGNETTE_MASK/BLOOM_DIRT/USER_LUT/PERFORM_SHARPEN 的逐行公式(对应含 keyword 变体未读;参数槽已定位)。
2. FisheyeEffect/FisheyeEffectDepth 已确认内联源码；实际启用条件、深度附件写入状态及绑定仍待核。
3. `_91[5]`(径向模糊采样表)的具体数值(声明在 f_b756 静态区,未抄录)。
4. BWFlash 灰度输入纹理 `_7`(b748)的打包来源(C# 侧哪一 pass 产出)。

---
*仅静态转写,行号指 uberpost.shader 与 uberpost\Sub0_Pass*.hlsl;无测试/参考实现。*

---

## 补充抽取(round 2,2026-09-28)

以下为 round 1 标 ⚠待核 的 keyword 分支;方法 = 各 keyword 首个单开变体(DIRTY_LENS→b289、PERFORM_SHARPEN→b290、USER_LUT→b292、LENS_DISTORTION→b296、VIGNETTE_MASK→b320、BLOOM_DIRT→b384)与 b288 归一化 diff 后抄录差异行。寄存器变化不再赘述。

### R2.1 DIRTY_LENS(b289,单开)
```
dirty = _DirtyTex.SampleLevel(LinearRepeat, uv, 0)                       // Sub0_Pass0_Fragment_b289.hlsl:200
强度因子 = lerp(_DirtyLensParams1.x, clamp((_DirtyLensParams1.x × 3.0f) - 2.0f, 0, 1), step(0, min3(dirty.rgb) - 0.20000000298023223876953125))   // :201
曝光输入 = c × _ExposureWithMiscParams.x × lerp(1.0f.xxx, dirty.rgb, 强度因子)      // :201(乘进标准 log 编码前)
```
即脏镜头贴图既调强度又染色;亮度高于 0.2 后强度换用 ×3-2 曲线。其余链路同 §4.2-4.5(含同式抖动,输出 alpha `min(w,1)`,b289:211-212)。

### R2.2 PERFORM_SHARPEN(b290,单开)——CAS 型自适应锐化
```
N/S/E/W 四向 1 texel 采样(offset = (0,_ScreenSize.w) / (_ScreenSize.z,0),b290:198-204)
per 通道:mn = min(四邻), mx = max(四邻)(:225-230)
amp = max(-0.1875f, min(max(max(-mn×(0.25f/mx), (1-mx)×(1/(4mn-4))), 同式(另两通道)), 0))
      × _SharpenStrengthAndPadding.x
      × (1.0f + (-0.5f) × clamp(|0.25×(lN+lS+lE+lW)-lCenter| / (max(lN,lS,lE,lW,lCenter)-min(lN,lS,lE,lW,lCenter)), 0, 1)) // :231
pc  = 1/(4×amp + 1)                                                      // :232
锐化色 = ((amp × (N+E+W+S per通道和) + center) × pc) per 通道               // :233 内
再进标准曝光/log/LUT 链(:233)
```
这里 `l(c)=0.5*c.r+c.g+0.5*c.b`，范围含中心且不是各通道的 mx-mn；锐化色为 `((N+S+E+W)*amp+center)/(4*amp+1)`。公式是 CAS 型自适应锐化；仅凭常数不能证明其具体上游版权/版本。没有除零保护的源码分支不得擅自添加后称逐字一致。

### R2.9 审核范围与封存限制（2026-09-30）

已回源复核代表 b288/b290/b304/b336/b354、LUT/OETF、曝光/Bloom 次序及 wrapper 内联鱼眼。round 2 其余单开/黑白分支是既有抽取，不代表 432 个组合已逐式核查。帧 6411 的 LUT、Bloom、输出格式有离线清单证据；动态 LUT 生产、曲线来源、完整尾链/其他视角启用条件仍不闭合，不能用历史像素门禁替代这些契约。

### R2.3 USER_LUT(b292,单开)
```
主 LUT 链照常(§4.2-4.4),得到 sRGB 编码(OETF)后 clamp[0,1] 的色 _143        // Sub0_Pass0_Fragment_b292.hlsl:210
bl = _143.z × _UserLut_Params.z; fl = floor(bl)                      // :211-212(z = 条带数)
uv  = ((_143.xy × _UserLut_Params.z) × _UserLut_Params.xy) + (_UserLut_Params.xy × 0.5f)   // :213
uv.x += fl × _UserLut_Params.y                                        // :215(y = 条带宽)
user = lerp(_UserLut(uv), _UserLut(uv + (_UserLut_Params.y, 0)), frac(bl))   // :216
out  = lerp(_143, user, _UserLut_Params.w) + RGB 三通道抖动(同 §4.5)   // :216
```
**USER_LUT 是主 LUT 之后的二级 LUT**;`_UserLut_Params.w` 为混合强度,采样后仍走抖动。

### R2.4 LENS_DISTORTION(b296,单开)
```
uv0 = (uv - 0.5) × _DistortionParams2.z                                // :197(整体缩放)
d   = _DistortionParams1.zw × (uv0 - _DistortionParams1.xy)            // :199(中心 + 纵横比)
r   = length(d)                                                        // :200
if (_DistortionParams2.w > 0):  uv = uv0 + d × ((tan(r × _DistortionParams2.x) × (1/(r × _DistortionParams2.y))) - 1)     // :205(桶形,tan)
else:                           uv = uv0 + d × (((1/r) × _DistortionParams2.x × atan(r × _DistortionParams2.y)) - 1)     // :209(枕形,atan)
之后 + 0.5 回 UV 空间并采样输入(:210 之后,与 b288 链衔接)
```

### R2.5 VIGNETTE_MASK(b320,单开)——贴图暗角(与 §4.6 VIGNETTE 参数式互斥同槽)
```
m = _VignetteMask.SampleLevel(uv).w                                    // Sub0_Pass0_Fragment_b320.hlsl:200-201
衰减多项式 = m × ((m × ((m × 0.305306017398834228515625) + 0.6821711063385009765625)) + 0.01252287812530994415283203125)   // :202(三次多项式,逐字)
遮色 = lerp(1.0f.xxx, lerp(_VignetteColor.xyz, 1.0f.xxx, 衰减多项式), _VignetteColor.w)   // :202(w = 强度)
曝光输入 = c × _ExposureWithMiscParams.x × 遮色                          // :202(乘进 log 编码前,与 VIGNETTE 同槽)
```
其余同 b288 链(:208 LUT、:212 抖动、:213 alpha)。

### R2.6 BLOOM_DIRT(b384,单开;在 BLOOM 基础上加镜头脏污)
```
bloom   = _BloomTexture(uv)                                            // Sub0_Pass0_Fragment_b384.hlsl:201
curve   = pow(bloom, 0.3300000131130218505859375)×1.49380004405975341796875 - 0.699999988079071044921875   // :204
bloomHi = (bloom×(1-_BloomParams.z) > 0.300000011920928955078125) ? curve : bloom   // :202-205
提取    = input - (input × (max((_BloomThreshold.w×knee)×knee, bright-_BloomThreshold.x)/max(bright,1e-5))) × _BloomParams.z   // :208 内(同 §4.1)
dirt    = _BloomDirtTexture((uv × _BloomDirtScaleOffset.xy) + _BloomDirtScaleOffset.zw)   // :208 内
合成    = lerp(input, 提取 + bloomHi × _BloomTint.xyz, _BloomParams.x) + (bloomHi × dirt.xyz) × _BloomParams.y   // :208
```
**dirt 项在 lerp 之后追加**(不受 _BloomParams.x 强度影响,由 _BloomParams.y 单独控制),随后进曝光/log 链(:208)。

### R2.7 BW 双路径极坐标 LUT 槽位核实(round 1 验收修正的补全)
两路径共用 atan2 多项式(同描边 atan 系数族;分支:`((x<0 ? -|a| : |a|) + ((y>=0 ? 3.141592502593994140625 : -3.141592502593994140625)×(y<0)) - (-3.1415927410125732421875)) × 0.15915493667125701904296875`,即方位角/2π):
- **BWFLASHTEX**(b754:223 与 b756:237,两文件逐字同式):
```
arg = (float2(atan2 分支值, length(向心向量) × 2.0f) × _15_Stripped_288.xy) + _15_Stripped_288.zw
      + (_15_Stripped_272.zw × _6_Stripped_320.y)                       // 追加动画偏移
bw = smoothstep((1-thr) - _15_Stripped_256.y, thr - _15_Stripped_256.y,
      clamp((灰度 × _11.SampleBias(LinearRepeat, arg, mip).x × _15_Stripped_320.x) + (灰度 × _15_Stripped_320.y), 0, 1))
```
槽位:**_288**(极坐标 LUT 的 uv scale/offset)、**_272.zw×c320.y**(动画偏移,round 1 未列)、**_320.x**(贴图强度)、**_320.y**(贴图外加项)、**_256.y**(smoothstep 宽度);`thr` = BWFlash 阈值合成(round 1 §4.6 的 `_80`)。
- **BWMASKTEX**(b751:224):
```
arg = ((float2(atan2 分支值, length × 2.0f) × _15_Stripped_256.w) + (_110 × (1.0f - _15_Stripped_256.w))) × _15_Stripped_304.xy + _15_Stripped_304.zw
bw = smoothstep((1-thr) - _15_Stripped_256.y, thr - _15_Stripped_256.y,
      (_95 - (_95 × _15_Stripped_320.z)) + (_95 × _11.SampleBias(LinearRepeat, arg, mip).x × _15_Stripped_320.z))
```
槽位:**_256.w**(极坐标/UV 直接混合权重——极坐标 LUT 与直通 UV 的插值)、**_304.xy/.zw**(uv 变换)、**_320.z**(贴图与灰度的混合强度)、**_256.y**(smoothstep 宽度)。与派单核对一致,另补:_256.y(两路径共用)、_272.zw×c320.y(仅 BWFLASHTEX)。

### R2.8 _91[5] 径向采样表(round 1 待核项 3)
`Sub0_Pass2_Fragment_b756.hlsl:5`:`static const float _91[5] = { 0.5f, 1.0f, 1.5f, 2.0f, 2.5f };`
用法(b756:209):`sum += 采样(uv - (径向向量 × (_91[i] × _15_Stripped_0.z)))`——**RADIAL_BLUR_CHROMATIC_ABERRATION 路径的 5 步距离系数** {0.5,1,1.5,2,2.5},乘全局强度。
