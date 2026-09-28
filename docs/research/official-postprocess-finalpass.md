# 官方后处理 FinalPass 源码抽取(Hidden/HGRP/FinalPass)——最终输出合成/上屏

来源:`_dump_1.5.3/AllShader_1.5.3/Assets/packages/com.hg.render-pipelines/runtime/shaders/postprocessing/finalpass.shader`(45903 B)+ `finalpass\Sub0_Pass0_{Vertex,Fragment}_b8..b103.hlsl`;以及**同名**的 `blitbackbuffer.shader`(14516 B,单变体内联)。

> **重要发现**:`blitbackbuffer.shader:1` 与 `finalpass.shader:1` 的 Shader 名**完全相同**,都是 `"Hidden/HGRP/FinalPass"`——dump 里同一逻辑 shader 的两份形态(finalpass.shader 是全 keyword 版,blitbackbuffer.shader 是单变体纯 blit 版)。Unity 同名 shader 以后加载者为准 ⚠待核哪份生效。

**本文不含任何单元测试或参考实现**(独立 oracle 由验收方另写),仅忠实转写源码。简写:`f_bN` = finalpass/Sub0_Pass0_Fragment_bN.hlsl,`v_bN` = 同名 Vertex。

## 1. Pass/变体识别

单 Pass(finalpass.shader:6-10:ZClip On/ZTest Always/ZWrite Off/Cull Off,无 Pass Name),`#pragma target 5.0` + `use_dxc`(:12-13),**无 Properties 块**。7 个独立 bool keyword(:17-23):
`CATMULL_ROM_4 / BYPASS / APPLY_AFTER_POST / ENABLE_ALPHA / DITHER / GRAIN / FXAA`。

7 bool 理论 128 组合,dump 实际编译 **96 组合**(f_b8–f_b103,无 b2–b7)——缺失的 32 组是游戏从未用过的组合 ⚠待核具体哪 32 组。派发顺序(f_bN 编号与 v_bN 一一对应,finalpass.shader:27 起逐条 `#if/#elif`,fragment 段与 vertex 段条件相同):b9=CM4、b10=BYPASS、b11=AAP、b14=ALPHA、b20=DITHER、b32=GRAIN、b56=FXAA,其余按二进制位组合。

**归一化 diff 结论**(96 个 fragment 全部与 f_b8 做 `_[0-9]+`→`_N` 归一化后 Compare-Object,已完成):差异只有六档,全部由 {APPLY_AFTER_POST, DITHER, GRAIN} 三个开关组合而来:

| diff 行数 | 开关组合 | 成员(全部列出) |
|---|---|---|
| 4(仅头注释/寄存器名) | 基线 blit | b9(CM4)、b10(BYPASS)、b14(ALPHA)、b15、b16、b56(FXAA)、b57、b58、b62、b63、b64 |
| 17 | +AAP 和/或 +GRAIN(无 DITHER) | b11-b13、b17-b19、b32-b34、b38-b40、b59-b61、b65-b67、b80-b82、b86-b88 |
| 21 | GRAIN+AAP | b35-b37、b41-b43、b83-b85、b89-b91 |
| 26 | +DITHER(±CM4/ALPHA/BYPASS/FXAA) | b20-b22、b26-b28、b68-b70、b74-b76 |
| 29–30 | DITHER+GRAIN(±AAP) | b23-b25、b29-b31、b44-b46、b50-b52、b71-b73、b77-b79、b92-b94、b98-b100 |
| 32 | AAP+DITHER+GRAIN(满配) | b47-b49、b53-b55、b95-b97、b101-b103 |

**因此:CATMULL_ROM_4、BYPASS、ENABLE_ALPHA、FXAA 四个 keyword 在全部 96 个已编译 fragment 中均无代码效果**(证据:b56/b57 单独开 FXAA 与 b8 仅头注释不同;b10(BYPASS)/b14(ALPHA) 与 b8 的 diff 仅头注释;b103 同开 6 个 keyword 也无 FXAA/CM4 代码;ENABLE_ALPHA 三组组合对见 §3)。它们疑似只影响 CPU 侧(换 RT/换链路)或为预留 ⚠待核。

## 2. 顶点与插值器(全变体相同形态)

**输入插值器**:仅 1 项——`float2 _2 : TEXCOORD0`(f_b8:164-167);输出 `float4 _3 : SV_Target0`(f_b8:169-172)。(DITHER/GRAIN 变体里静态变量改名为 `_3`/`_4`,语义相同,f_b20:176 起。)

全屏三角形:`_23 = float((VertexIndex << 1) & 2); _25 = float(VertexIndex & 2); _28 = (float2(_23,_25)×2)-1;` 位置 `float4(_28,1,1)` 且 `_31.y = -_28.y`(**常量 Y 翻转,无 cbuffer**);UV `_4 = float2(_23, 1-_25)`(v_b8:19-28,与 lutbuilder2d 顶点逐字相同)。

## 3. 资源绑定(按 ParamBlob 分列)

ParamBlob 编号随启用功能递增(资源布局 blob):

| 变体 | ParamBlob | cbuffer | 采样器 | 纹理 | 行号 |
|---|---|---|---|---|---|
| b8(全关) | 0 | ShaderVariablesGlobal b2 / Globals b3 | s0 LinearClamp | t1 `_InputTexture` | f_b8:5/148/158/159 |
| b11(AAP) | 1 | b4 / b5 | s0 Clamp + s1 Repeat | t2 `_InputTexture`、t3 `_AfterPostProcessTexture` | f_b11:5/148/158-161 |
| b20(DITHER) | 2 | b4 / b5 | s1 Repeat + s0 Clamp | t2 `_InputTexture`、t3 `_BlueNoiseTexture`(**Texture2DArray**) | f_b20:5/148/158-161 |
| b103(6 开) | 7 | b7 / b8 | s0 Clamp + s1 Repeat + s2 Mirror | t3 `_InputTexture`、t4 `_GrainTexture`、t5 `_BlueNoiseTexture`(Array)、t6 `_AfterPostProcessTexture` | f_b103:5/148/158-164 |

**ParamBlob = {AAP=1, DITHER=2, GRAIN=4} 的位掩码**(b8=0、b11=1、b20=2、b32=4、b103=7=1+2+4;实测 b17/b11 同为 1、b26/b20 同为 2、b38/b32 同为 4)。

**ENABLE_ALPHA、BYPASS、CATMULL_ROM_4、FXAA 对 fragment/ParamBlob 均无任何可见效果**:三组组合对 b17-vs-b11、b26-vs-b20、b38-vs-b32 的归一化 diff 都只有头注释两行(ParamBlob 不变);b14/b10 与 b8 同。疑为 CPU 侧开关或预留 ⚠待核。

**cbuffer type_ShaderVariablesGlobal**(b2/b4/b7…,space3,f_b8:5-146):仅 `_ScreenSize`(c0)与 `_GlobalMipBias`(c26)被读,其余 ~160 个 Stripped 槽未读。

**cbuffer type_Globals**(f_b8:148-156,逐字):
```
float2 _Globals_GrainParams        packoffset(c0)      // .x 强度、.y 亮度权重混合
float4 _Globals_GrainTextureParams packoffset(c1)      // .xy 缩放、.zw 偏移
float4 _Globals_DitherParams       packoffset(c2)      // .xy 噪声 uv 缩放、.z 切片索引(.w 未读)
float4 _Globals_UVTransform        packoffset(c3)      // .xy 缩放、.zw 偏移(像素单位)
float4 Stripped_64                 packoffset(c4)      // 未读
float  Stripped_80                 packoffset(c5)      // 未读
```

## 4. 基线 blit(所有变体第一步,f_b8:176 = f_b9:176 = blitbackbuffer 同式)

```
uv  = float2( uint2( ( float2(uint2(_2 × _ScreenSize.xy)) × _Globals_UVTransform.xy )
                     + (_Globals_UVTransform.zw × (_ScreenSize.xy - 1.0f.xx)) ) ) × _ScreenSize.zw
out = _InputTexture.SampleBias(sampler_LinearClamp, uv, _GlobalMipBias)
```
即:**先把自己像素坐标量化成整数像素(`uint2(uv×屏幕尺寸)`),再套 UVTransform(源像素 → 目标像素的 scale+offset),最后 ×1/尺寸转回 UV**——像素对齐的重采样 blit(分辨率缩放/平移),`_GlobalMipBias` 走 SampleBias。UV = `(_23, 1-_25)`(v_b8:27)。

blitbackbuffer.shader 内联 fragment 与此**逐字同式**(blitbackbuffer.shader:228-231;其 Globals b3 只有 `_Globals_UVTransform` c0,:206-210;纹理 t1 `_InputTexture` :213;sampler s0 LinearClamp :212;cbuffer ShaderVariablesGlobal b2 同 f_b8 结构 :63-204)。

## 5. APPLY_AFTER_POST(f_b11:176-182;b59-b61/b65-b67 同体)

```
c   = _InputTexture.SampleBias(sampler_LinearRepeat, 像素对齐uv(同§4), _GlobalMipBias)      // f_b11:178(采样器改 LinearRepeat)
aft = _AfterPostProcessTexture.SampleLevel(sampler_LinearClamp, (uv × UVTransform.xy) + UVTransform.zw, 0.0f)   // :179(连续 uv,无像素量化!)
out = float4((c.xyz × aft.w) + aft.xyz, c.w)                                                 // :180-181
```
即 **after-post 纹理按预乘 alpha 叠加在 blit 结果上**(`rgb×a + aft.rgb`),输出 alpha 沿用输入。aft 的采样坐标不走像素量化(:179)——两纹理坐标系不同,注意。

## 6. GRAIN(f_b32:176-182;b103:184 同式)

```
c   = clamp(_InputTexture.SampleBias(sampler_LinearRepeat, 像素对齐uv(同§4), _GlobalMipBias), 0, 1)   // f_b32:178
g   = _GrainTexture.SampleBias(sampler_LinearClamp, ((uv×UVTransform.xy)+UVTransform.zw) × GrainTextureParams.xy + GrainTextureParams.zw, _GlobalMipBias).w   // :180 内
n   = (g - 0.5) × 2.0                                                                          // :180 内(→[-1,1])
out.rgb = c.rgb + ((c.rgb × n) × GrainParams.x) × lerp(1.0, 1.0 - sqrt(dot(c.rgb, (0.21267290413379669189453125, 0.715152204036712646484375, 0.072175003588199615478515625))), GrainParams.y)   // :180
out.a   = c.a                                                                                  // :181
```
`GrainParams.x` = 强度;`GrainParams.y` = 暗部加权(0=均匀,1=按 `1-sqrt(luma709)` 加权,暗处颗粒更强)。噪声取 `_GrainTexture` 的 **.w 通道**。亮度权重为 Rec709。**在线性域直接加减,无色彩空间往返**。

## 7. DITHER(f_b20:176-191;b103:185-193 同式)

```
c   = clamp(_InputTexture.SampleBias(sampler_LinearRepeat, 像素对齐uv(同§4), _GlobalMipBias), 0, 1)          // f_b20:178
// 线性 → sRGB 编码(精确分段式):
s1  = c.rgb × 12.9200000762939453125                                                  (低段)        // :180
s2  = pow(abs(c.rgb), 0.4166666567325592041015625) × 1.05499994754791259765625 - 0.054999999701976776123046875   // :181
sel = c.rgb ≤ 0.003130800090730190277099609375 ? s1 : s2                                              // :182
σ   = _BlueNoiseTexture.SampleBias(sampler_LinearClamp, float3(((uv×UVTransform.xy)+UVTransform.zw) × DitherParams.xy, DitherParams.z), _GlobalMipBias).w × 2.0 - 1.0   // :183(→[-1,1],取 .w,数组切片 = DitherParams.z)
d   = (σ ≥ 0 ? 1.0 : -1.0) × (1.0 - sqrt(1.0 - abs(σ))) × 0.0039215688593685626983642578125           // :184-185(符号重映射,幅度 1/255)
d'  = sel + d                                                                                          // :185(sRGB 域加抖动)
// sRGB → 线性解码(精确分段式):
l1  = d' × 0.077399380505084991455078125                                              (低段)        // :186(=1/12.92)
l2  = pow(abs((d' + 0.054999999701976776123046875) × 0.947867333889007568359375), 2.400000095367431640625)       // :187(0.9478… = 1/1.055)
out = float3(d' ≤ 0.040449999272823333740234375 ? l1 : l2, c.a)                                       // :188-190
```
要点:① 抖动在 **sRGB 编码域按 ±1/255 量子**施加(蓝噪声经 `sign×(1-√(1-|σ|))` 重映射,σ→0 附近斜率 0 起步、σ=±1 时幅度 ±1/255);② 随后立即解码回线性输出——**说明 finalpass 输出是线性色,交给 sRGB 格式的目标 RT 由硬件编码**(与 uberpost 末端抖动直接加在 sRGB 值上不同,那边输出即显示域)⚠待核 RT 格式;③ 蓝噪声是 **Texture2DArray**,`DitherParams.z` 选切片、`.xy` 缩放 uv。

## 8. 组合顺序(满配 f_b103:179-197,已全文)

```
uvCont = (uv × UVTransform.xy) + UVTransform.zw                          // :181(连续坐标,grain/dither/afterpost 共用)
c      = clamp(_InputTexture.SampleBias(sampler_LinearMirror, 像素对齐uv, _GlobalMipBias), 0, 1)   // :182
rgb    = GRAIN(c.rgb)                                                    // :184(式同 §6)
rgb    = DITHER(rgb)(sRGB 往返,蓝噪声 uv = uvCont × DitherParams.xy)      // :185-193(式同 §7)
aft    = _AfterPostProcessTexture.SampleLevel(sampler_LinearClamp, uvCont, 0.0f)          // :194
out    = float4(rgb × aft.w + aft.xyz, c.w)                              // :195-196
```
即顺序 = **blit → grain → dither → afterpost 叠加**;sampler 组合随 keyword 变(此处输入用 LinearMirror、grain/噪声用 LinearRepeat、afterpost 用 LinearClamp——各变体并不统一,f_b11 用 Repeat/f_b32 用 Repeat,f_b20 输入 Repeat+噪声 Clamp ⚠待核是否有意)。

## 9. blitbackbuffer.shader(同名单变体版)

`Shader "Hidden/HGRP/FinalPass"`(blitbackbuffer.shader:1);单 Pass 无 keyword(:6-16);顶点同 §2(:20-55);fragment = §4 基线 blit 逐字同式(:228-231),Globals 只有 UVTransform(:206-210)。即它是**纯像素对齐 blit 版的 FinalPass**。两个同名 shader 的加载/覆盖关系在 dump 内不可见 ⚠待核。

## 10. ⚠待核汇总

1. 两个同名 `Hidden/HGRP/FinalPass`(finalpass.shader vs blitbackbuffer.shader)哪份生效(Unity 按加载顺序覆盖)。
2. CATMULL_ROM_4 / BYPASS / ENABLE_ALPHA / FXAA 四个无代码效果 keyword 的实际用途(CPU 侧换 RT/换链路?预留?)。
3. 输出 RT 格式(§7 的 sRGB 往返暗示线性写入 + sRGB RT 硬件编码)。
4. 96 组合之外缺失的 32 组 keyword 组合。
5. `_AfterPostProcessTexture` 的产出方(C# 侧哪个 pass 写入;大概率是 UI/透明叠加或镜头特效层)。
6. `_BlueNoiseTexture`(Texture2DArray)切片数与 `DitherParams.z` 的取值范围。
7. 各变体 sampler(Clamp/Repeat/Mirror)分配是否有意(边缘行为差异)。

---
*仅静态转写,行号指 finalpass.shader、finalpass\Sub0_Pass0_*.hlsl、blitbackbuffer.shader;无测试/参考实现。*
