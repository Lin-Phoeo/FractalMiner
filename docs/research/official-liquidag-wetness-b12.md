# 官方 CharacterNPR_LiquidAg(湿身/液体覆盖)源码抽取 —— 代表变体 b12 + 湿身锚点 b400

来源目录:`_dump_1.5.3/AllShader_1.5.3/Assets/packages/com.hg.render-pipelines/runtime/shaders/materials/characternpr/`
- wrapper:`characternpr_liquidag.shader`(592 行,全读)
- 代表变体(每 Pass 编号最小):Pass0 b12(片元 1137 / 顶点 440)、Pass1 b36(448/488)、Pass2 b52(291/402)、Pass3 b61(**GLSL** 1726/47)、Pass4 b76(9/243)、Pass5 b80(176/390)
- 湿身锚点:`characternpr\Sub0_Pass0_Fragment_b400.hlsl`(1626 行,cloth ForwardLit,湿身段 L605-1626),半成品参照 `docs/research/official-wetness-b400-excerpt.txt` 的来源
- 变体差异按 keyword 补记(b14/b24/b38/b53/b77/b81),未全文重复

本文是源码导读，不是可直接移植的等价实现；含中文占位量、省略号的伪码不能当作官方完整公式。2026-09-30 回源核查修正了天气通道、时间分支、粗糙度、高光及环境反射等错误。证据范围和仍未核实的部分见 [资料审计记录](source-contract-audit-20260930.md)。**本文不含参考实现，也不证明当前 Unity 工程已接入湿身。**

## 0. Shader 概览

`HGRP/CharacterNPR_LiquidAg`(liquidag.shader:1)。6 个 Pass:

| Pass | Name | LIGHTMODE | 状态要点 | 关键字数 | 代表变体 |
|---|---|---|---|---|---|
| 0 | ForwardLit | ForwardCharacterOnly | Blend[_SrcBlend][_DstBlend]、ZTest[_ZTest]、ZWrite[_ZWrite]、Cull[_Cull](liquidag.shader:119-129) | 12 | b12(catch-all) |
| 1 | CharacterOutline | ForwardOnly | ZTest Less、Cull Front、Stencil Ref 4 / ReadMask[_OutlineInnerClipStencilMask] / Comp NotEqual(235-250;**与 skin 的 Ref 36 Always Replace 不同**) | 8 | b36(catch-all) |
| 2 | PreGBuffer | DepthCharacterOnly | Cull[_Cull]、Stencil Ref 36/ReadMask 16/WriteMask 239/GEqual/Replace(331-344) | 5 | b52(catch-all) |
| 3 | RayTracingReflection | RayTracingReflection | 双 RT `Blend OneMinusSrcAlpha SrcAlpha`、ZTest Equal、ZWrite Off、Cull Off(398-409);**片元为 .glsl**(SPIRV-Cross GLSL 形态,含 buffer_reference/ECSPerDraw 等 RT 基础设施) | 7 | b61(catch-all) |
| 4 | ShadowCaster | SHADOWCASTER | Cull Off(482-489) | 4 | b76(catch-all) |
| 5 | TextureStreamingFeedback | TextureStreamingFeedback | ColorMask 0、ZTest Equal、ZWrite Off、Cull[_Cull](527-537) | 3 | b80 |

属性表见 §6(全部 _Property 及默认值)。

## 1. Pass0 ForwardLit 变体识别(b12 = catch-all)

multi_compile_local(liquidag.shader:136-147):`SRP_INSTANCING_ON`、`HG_ENABLE_PER_OBJECT_MV`、`HG_ENABLE_SCREEN_SPACE_SHADOW_MASK`、`_NORMALMAP`、`_EMISSION`、`_METALLICSPECGLOSSMAP`、`_ALPHA_SCENE_DEPTH_FADE`、`_CHARACTER_VFX_SPECIAL`、`_ENEMY_HIT_FLASH`、`_ALPHABLEND_ON`、`VFX_CHARACTER_DISSOLVE`、`DITHER`。

| ON(b12) | OFF(b12) |
|---|---|
| HG_ENABLE_PER_OBJECT_MV、HG_ENABLE_SCREEN_SPACE_SHADOW_MASK、SRP_INSTANCING_ON | _NORMALMAP、_EMISSION、_METALLICSPECGLOSSMAP、_ALPHA_SCENE_DEPTH_FADE、_CHARACTER_VFX_SPECIAL、_ENEMY_HIT_FLASH、_ALPHABLEND_ON、VFX_CHARACTER_DISSOLVE、DITHER |

变体 keyword 门控差异(补记,未全文):b14 = +_EMISSION/_METALLICSPECGLOSSMAP/_ALPHA_SCENE_DEPTH_FADE/_CHARACTER_VFX_SPECIAL(+84 行:发射/金属贴图/深度淡出/VFX 特效分支);b24 = +DITHER(仅 +1 行 = 头部,插值器 keyword 行,片元逻辑无操作,与 C6 描边结论一致);b18 = VFX_CHARACTER_DISSOLVE 且无 _NORMALMAP(dissolve 分支,结构同 Pass4 f_b77 的溶解裁剪,见 §5.6)。dispatch 全表见 liquidag.shader:151-229。

## 2. Pass0 纹理寄存器 → 名称 → 采样表达式 → 判据

| 寄存器 | HLSL 名 | 采样表达式 | 判据 |
|---|---|---|---|
| t1,space1 | `_BaseMap` | `SampleBias(sampler_LinearClamp, uv0, _GlobalMipBias)`(Sub0_Pass0_Fragment_b12.hlsl:401) | 唯一乘 _BaseColor 的 sRGB 图 |
| t39,space0 | `_CharacterSnowEffectTex` | `SampleBias(LinearClamp, uv0 × _CharacterParams10.z, _GlobalMipBias)`(f_b12:589) | 雪覆盖贴图(**单 UV,非三平面**;cloth b400 为三平面) |
| t45,space0 | `_CharMaxCubemap` | `SampleLevel(sampler_LinearRepeat, reflect(-V, Ngeo), 1.2×log2(max(roughOut,0.001))+5)`(f_b12:693) | b12 使用几何法线 `_474`，不是雪扰动法线 `_1103`；LOD 输入是粗糙度，不是其平方 |
| t29,space0 | `_LightCookie` | `SampleLevel(LinearRepeat, cookieUV, 0)`(f_b12:824) | 点光源 cookie(盒形/聚光两种 UV) |
| t22,space0 | `_ScreenSpaceShadowMask` | `Load(像素)`(f_b12:636) | .x=方向光阴影 |
| t27,space0 | `_PunctualLightShadowTexV2` | `SampleCmpLevelZero(sampler_LinearMirror, …)` 9-tap(f_b12:931) | 点光 PCF |
| t30-35,space0 | `_IrradianceVolumeClipmapTexture{A,B}Lod{0,1,3}` | `SampleLevel` 三层(f_b12:442-518) | 环境辐照度体 |
| t36,space0 | `_IntegratedLightScattering` | `SampleLevel(LinearRepeat, froxel UV, 0)`(f_b12:1112) | 体积雾 |

## 3. Pass0 输入插值器(顶点 → 片元)

顶点输出(Sub0_Pass0_Vertex_b12.hlsl:276-286)→ 片元输入(f_b12:349-360):

| 语义 | 顶点 | 片元 | 内容 |
|---|---|---|---|
| TEXCOORD0 | `_11` | `_3` | uv0 = uv×_BaseMap_ST(v_b12:419) |
| TEXCOORD1 | `_12` | `_4` | positionRWS(v_b12:420) |
| TEXCOORD2 | `_13` | `_5` | 世界法线(蒙皮混合后归一化,v_b12:421) |
| TEXCOORD3 | `_14` | `_6` | 当前帧裁剪 xyw(去 TAA 抖动,v_b12:414-416/422) |
| TEXCOORD4 | `_15` | `_7` | 上一帧裁剪 xyw(v_b12:423;Stripped_160.x<1 时改用 TEXCOORD0 烘焙位置) |
| TEXCOORD5 | `_16` | `_8` | **第二法线**(restNormal 性质:物体空间;蒙皮对象取 TEXCOORD2 流解包 `_197`,静态对象取 TANGENT0 解包 `_155`,v_b12:424;片元雪覆盖度用 `_8.y/_8.z`,f_b12:591)⚠待核:蒙皮取 z/静态取 y 的轴约定依据 |
| TEXCOORD6 | `_18` | `_10` | instanceID(nointerp) |

顶点内两套 10bit 八面体解包:bit30 标志 + 3×10bit、系数 `0.001956947147846221923828125`(= 1/511)(v_b12:290-327)。蒙皮:两组矩阵(`Stripped_80.x/y+3` 起,2/4 骨),第一组作用于法线/位置,第二组作用于烘焙位置(v_b12:333-411)。**无切线输出**(b12 无 _NORMALMAP;b13 顶点输出切线,片元做 TBN ⚠待核,未全文抽取)。

## 4. cbuffer 字段(Pass0 具名 `type_UnityPerMaterial`,f_b12:262-312)与湿身相关全局

逐字段(标注"被函数体读取"与否):

| 偏移 | 字段 | 读取? | 用途(行号) |
|---|---|---|---|
| c0 | _Smoothness/_Specular/_Metallic/_BumpScale | 是(除 _BumpScale) | `1-_Smoothness`→粗糙(403)、`0.04×_Specular` specColor(620)、`_Metallic`→雪分支(608) |
| c1.y/.z/.w | _BackFaceNormalFlip/_AlphaPremultiply/_EmissionBrightness | 是(前两) | 背面翻转(411)、预乘因子(666) |
| c2 | _SurfaceType | 是 | 输出 alpha 分支(1077) |
| c3/c4.x/y | _ColorAdjustment* | 是 | VFX 调色(1070) |
| c4.z/.w | _ShadowColorBrightness/_ShadowColorSaturation | 是 | 阴影 albedo(405-406) |
| c5 | _DisableRainEffectOnMaterial | 是 | **雪/湿分支门槛**(587) |
| c6/c7 | _BaseColor/_EmissionColor | 是(b12 只用 BaseColor) | albedo(402) |
| c8/c9 | _ColorAdjustmentColorBlend/RimColor | 是 | VFX 调色(1070) |
| c10/c11 | _BaseMap_ST/_BaseMap_TexelSize | ST 是(顶点 419);TexelSize 仅 Pass5 用(f_b80:83) | |
| c12 | _DepthFadeValue/_DepthFadeExp | **否**(b12 未读;_ALPHA_SCENE_DEPTH_FADE 变体 b14 分支用)⚠待核 | |
| c16/c17/c19/c20 | _VFXFresnel* 等 | **否**(b12 未读;_CHARACTER_VFX_SPECIAL 变体用)⚠待核 | |

全局湿身字段(f_b12 实际读取):
- `_CharacterParams10.x/.y/.z`:>0.5 用全局天气掩码 CP10.y,否则 per-object `Stripped_208.x`;`.z` = 天气 UV 缩放(589/414)。
- `_500.w = (掩码 >> 24) & 255 × 1/255` → `_501` = **雪量**(f_b12:414-415;注意 RGB 三字节 × _371(=0)填 0,即 catch-all 只有雪,无雨湿/水位)。
- `_CharacterParams12.w/.y/.z/.x`:展示模式/光色覆盖/角色灯层/逆光开关(587 无关,633/747/642)。
- `_CharacterParams11`(光向/ramp 偏移)、`_CharacterParams5`(光色覆盖)、`_CharacterParams0.y/.z/.w`(lightTerm/阴影深/环境乘数)、`_CharacterParams1.x/y/z/w`、`_CharacterParams6/7`(环境梯度)、`_CharacterParams8/9/15`(边缘光)、`_CharacterParams13.w`(高光总乘数):同 characternpr 家族约定。
- **`_SilkStockings*` 在 liquidag 中不存在**(属性表无、cbuffer 无;那是 cloth b400 的丝袜子材质系统,见 §7)。

## 5. Pass0 逐段湿身数学(b12)

### 5.1 雪覆盖度(f_b12:587-608)

```
若 (_501 - _DisableRainEffectOnMaterial) > 0.01:                    // f_b12:587
snowTex = _CharacterSnowEffectTex.SampleBias(LinearClamp, uv0 × _CharacterParams10.z, mipBias)   // :589
w = _501 × (2 - _501)                                              // :590 二次缓动
coverage = smoothstep(2 - w, 2.35 - w, ((蒙皮? _8.z : _8.y) × 0.64999997615814208984375f + 0.3499999940395355224609375f) + snowTex.z) × float(gl_FrontFacing)   // :591
snowN.xy = snowTex.xy × 2 - 1; snowN.z = max(1.000000016862383526387164645044e-16f, sqrt(1 - clamp(dot(xy,xy),0,1)))   // :593-596
snowN2.xy = snowN.xy × 2                                            // :597
bump0 = lerp((0,0,1), (snowN2.x, snowN2.y, snowN.z), coverage)
bumpN = bump0 * rsqrt(max(6.103515625e-05f, dot(bump0,bump0)))             // :598-599，保留归一化下限
```

### 5.2 雪法线 TS→WS(水平面切线框,f_b12:600-604)

```
ny = N.y; horizontal = step(0.00999999977648258209228515625f, 1 - ny²)      // :600-601
nz2 = lerp(N.z, ny, horizontal)                                             // :602
tangent = ((0, horizontal, 1-horizontal) - N × nz2) × rsqrt(max(9.9999997473787516355514526367188e-05f, 1 - nz2²))   // :603
wetN = (cross(tangent, N) × bumpN.x) + (tangent × bumpN.y) + (N × bumpN.z)  // :604
```

### 5.3 湿雪材质参数替换(f_b12:605-608)

```
roughOut = lerp(1 - _Smoothness, 0.89999997615814208984375f, clamp(coverage × 4, 0, 1))    // :605 粗糙度→0.9，不是平滑度→0.9
shadowAlbedo = lerp(_457 × 1.0, 0.3079999983310699462890625f.xxx, coverage)                // :606
albedo      = lerp(_437 × 1.0, 0.87999999523162841796875f.xxx, coverage)                    // :607
metallic    = lerp(_Metallic, 0.0f, coverage)                                               // :608
```

### 5.4 PBR 组装 + GGX 高光 + split-sum 环境反射(f_b12:618-623、656-667、673-693)

```
diffuseEnergy = 0.959999978542327880859375f - metallic×0.959999978542327880859375f          // :618 (0.96)
diffuseColor = albedo × diffuseEnergy; shadowDiff = shadowAlbedo × diffuseEnergy            // :619/621
specColor = lerp(0.039999999105930328369140625f.xxx × _Specular, albedo, metallic)          // :620
shininess = max(roughOut², 0.0078125f)                                                      // :622-623
// 明暗:ramp = smoothstep(0.25f, 1.0f, clamp(lerp(NdotL, 逆光项, 逆光权重) + CP11.w×CP12.x, -1, 1))   // :643(cloth 同款,非 skin 的 -0.5,0.5)
// GGX 主高光(H = normalize(L×shadowDir + PseudoL̂×2 + V×(2+shadowDir)),PseudoL = (camAxisZ.x, lerp(0.5, L.y, shadowDir), camAxisZ.z)):  // :658-667
// 注意 b12 的高光 NdotV/NdotH 实际使用几何法线 _474，并非雪法线 _1103 (:658-659)。
spec = specColor × clamp(D_GGX × (0.5 / (2NdotV + shininess × ((1+NdotV)-NdotV) + 9.9999997473787516355514526367188e-05f)) - 6.103515625e-05f, 0, 20) × lightTerm × CP13.w  // :666
// split-sum 环境反射(有理多项式拟合,_1472/_1477,常量逐字):
_1472 = dot(mul(float2(1, NdotV), float2x2(float2(0.0365463010966777801513671875f, 9.0631999969482421875f), float2(3.3270699977874755859375f, -9.0475597381591796875f))), float2(1, rough²))
        / dot(mul(float3(1, NdotV², NdotV³), float3x3(float3(1.0f, 9.044010162353515625f, 5.565889835357666015625f), float3(3.596849918365478515625f, -16.3173999786376953125f, 19.788600921630859375f), float3(-1.36772000789642333984375f, 9.2294902801513671875f, -20.212299346923828125f))), float3(1, rough², rough⁶))   // :680
_1477 = dot(mul(float2(1, NdotV), float2x2(float2(0.99044001102447509765625f, 1.29677999019622802734375f), float2(-1.28514003753662109375f, -0.755906999111175537109375f))), float2(1, rough²))
        / dot(mul(float3(1, NdotV, NdotV³), float3x3(float3(1.0f, 20.3225002288818359375f, 121.5630035400390625f), float3(2.9233798980712890625f, -27.0301990509033203125f, 626.1300048828125f), float3(59.41880035400390625f, 222.5919952392578125f, 316.62701416015625f))), float3(1, rough², rough⁶))   // :681，末向量不是 NdotV 的幂
envSpecColor = specColor × _1472 + _1477                                                    // :682-683
// 立方体反射:
reflectColor = _CharMaxCubemap.SampleLevel(LinearRepeat, reflect(-V, Ngeo), 1.2000000476837158203125f × log2(max(roughOut, 0.001f)) + 5.0f).xyz   // :693，Ngeo = _474
_1481 = _1472 + _1477                                                                    // :684
color += reflectColor × (envSpecColor + specColor × ((1-_1481)/_1481) × envSpecColor) × (clamp(峰值,0.5,1.5) × CP0.w × lerp(CP0.z,1,litBlend)) × 环境色调   // :693，分母是两项之和，不能只用 _1477
```

### 5.5 背光/透光项(f_b12:685)

```
color += SH环境归一 × clamp(lerp(dot(SH法线组, N)×alpha, 逆光SDF, shadowDir), 0, 1) × ((1-shadowDir + 逆光相机因子×shadowDir) × (1-CP12.x))
         × smoothstep(0.60000002384185791015625f, 0.800000011920928955078125f, 1-|NdotV_gbuffer|) × 1.0
         × (1-shadowDir + smoothstep(0.100000001490116119384765625f, 0.039999999105930328369140625f, luma(diffuseColor)) × shadowDir)
         × max(0.1500000059604644775390625f.xxx, diffuseColor)
```

### 5.6 点光源(cookie/类型 2 新增,f_b12:695-1065)

结构与 C6 描边点光同款;liquidag 特有:
- **LightCookie**(f_b12:799-830):`cookieIdx = int(PLD[k=7].w)`;非盒形按 cubemap 六面表 `_326[6]={int2(2,1),int2(2,1),int2(0,2),int2(0,2),int2(0,1),int2(0,1)}`、`_327[6]={(-1,1),(1,1),(1,-1),(1,1),(1,1),(-1,1)}` 做 face UV(f_b12:818-822,`0.000244140625f`、`0.5 - 0.000244140625f/_lightCookieData.w`);`atten × _LightCookie.SampleLevel(...).x`。
- **类型 2(材质响应灯,f_b12:998-1011)**:`atten2 = smoothstep(PLD[k4].x + 0.0500000007450580596923828125f, PLD[k4].x - 0.0500000007450580596923828125f, roughOut) × ((1-PLD[k4].z) + (step(0.5, metallic) × PLD[k4].z))` —— 按平滑度/金属度门控;diffuse 色 = `lerp(受光色, 0, type1外)`,高光乘 `PLD[k=7].z`。
- 类型 0/1/3/4 与家族一致(type0 环境混入常数 0.25,f_b12:958;type1 diffuse 用 shadowDiff × k4.y,f_b12:992)。

### 5.7 VFX 调色与输出(f_b12:1066-1136)

VFX 调色块同家族(1070);`out.a = (_SurfaceType == 1.0f) ? (BaseMap.a × _BaseColor.w) : 1.0f`(1076-1077);雾同家族(1078-1134)。SV_Target1 = MV 编码 w=0.4(624-629)。

## 6. Pass1-5 抽取要点(代表变体)

### Pass1 CharacterOutline(b36)
- 片元(Sub0_Pass1_Fragment_b36.hlsl):**简化描边**——`_BaseMap_b2`(t2,space1,疑 `_OutlineColorMap` ⚠待核)采样取 `.w`:`alpha源 = clamp((贴图.w × _BaseColor.w) × 2.0f, 0, 1)`(:336);颜色 = `_BaseMap.rgb × c14.xyz(疑 _OutlineTintColor)× lerp(min(luma(光色),1)×CP0.w, 光色×CP0.y, shadowDir)`(:372)。无主体完整点光/ramp 链，但有 VFX rim；不能笼统称“无边缘光”。GBuffer 法线(t38 匿名)用于 VFX rim(:349-363/377);`out.a = (c2.x == 1.0f) ? alpha源 : 1.0f`(:384)，匿名字段是否对应 `_OutlineTransparent` 未证实。MV 到 SV_Target1(:364-370)，w 由逐对象条件选择 0.7 或 0.4，不是固定 0.4。
- 顶点(Sub0_Pass1_Vertex_b36.hlsl):与 skin 描边同构(八面体解包 290-327、蒙皮 332-415、平滑法线 426-437、FOV 外扩 438-451 同公式、深度偏移 454-467);槽位差异:宽 = c12.x(`_30_Stripped_192`)、深度偏移 = c12.y(`_30_Stripped_196`)、平滑法线开关 = c13.x(`_30_Stripped_208`)、色调 = c14.xyz(`_29_Stripped_224`);**无自体法线输出**(描边打光用 GBuffer 法线)。
- b38(_OUTLINE_MASK):与 b36 算法全同;顶点多采样 t0,space1 匿名贴图(变换后 UV,`SampleLevel(LinearClamp)`),**mask.r 乘外扩、mask.g 乘深度偏移**(与 skin b283 同款);cbuffer b0→b1、纹理槽位整体平移(t1→t2、t2→t3)。

### Pass2 PreGBuffer(b52)
- 与 eye b64 同构的 5 路 MRT(f_b52:238-283):Target0=0、Target1=MV(w=0.4)、Target2=对象 ID(`Stripped_80.z` 3×10bit+2bit,系数 `0.000977517105638980865478515625f`/`0.3333333432674407958984375f`)、Target3=八面体法线(**w=0.0f**,eye 为 0.7 ⚠待核:w 通道语义)、Target4=`_BaseMap.rgb×_BaseColor.rgb`(a=1)。
- b53(+_NORMALMAP):+t2,space1(`_BumpMap`),`.w×.r` 解包、`×_BumpScale`、TBN、背面翻转 → 法线缓冲带贴图细节。
- v_b52:IO = POSITION0/NORMAL0(float2)/TANGENT0/TEXCOORD0(烘焙位置)/TEXCOORD1(权重)/TEXCOORD2(索引),输出 UV/法线/两帧 clip/instanceID。

### Pass3 RayTracingReflection(b61,GLSL)
- **顶点仅 SV_VertexID 输入**(v_b61:26-35,全屏形态;renderer 如何以角色材质驱动此 pass 属引擎侧,源码不可见 ⚠待核)。
- 片元 GLSL(Sub0_Pass3_Fragment_b61.glsl):RT 反射基础设施(`_RTLightBinningBuffer`、`RTPunctualLightGlobalData`、`_RTRCBuffer`、`_RTRVisibilityBuffer`、`_RayTracingMaterialHandleBuffer`、`_RayTracingGeomInstDataBuffer`、ECSPerDraw[1024],L259-405);主体 ~1600 行为完整 ForwardLit 复算(漫反射+GGX+IV+点光+雾,同 Pass0 结构);核心输出数学:
  - `_5`(RT0)= `float4(radiance / (max3(radiance) + 1.0), _RTRHitAlphaTexture.x)`；hit alpha 是独立 alpha 通道，不加到 RGB，也不能仅凭此式称为反照率。
  - `_6`(RT1)= `(clamp(log2(0.5 × sqrt(d1² + d2²)), 0, _RTRCBuffer.RTRParam4.x) / RTRParam4.x) × step(1e-4, roughness)`、w = `step(0.01, hitAlpha)`;其中 d1/d2 = 反射锥两边界点投影到屏幕后与相机投影点的距离(`_4451.._4488`,ViewNoTransProjMatrix)——**反射视差/半径等级编码**
  - 锥角:`_4405 = acos(pow(0.24400000274181365966796875, 1.0 / ((2.0 / roughness) + (-1.0))))`(GGX 可见锥,尾部)
  - 混合因子 `Blend OneMinusSrcAlpha SrcAlpha`：每个相应目标的合成为 `src × (1-src.a) + dst × src.a`，不是标准预乘 alpha 混合。
- b62(+_NORMALMAP):+188/-5 行——新增 t1,space1 匿名法线贴图采样与 TBN 构造(normalize/cross 组合),法线贴图细节进入 RT 复算的表面法线(diff 已定性,未逐行 ⚠待核)。

### Pass4 ShadowCaster(b76)
- 片元 catch-all **9 行,frag_main 为空**(纯深度写);b77(+VFX_CHARACTER_DISSOLVE):溶解裁剪 + IGN 抖动(f_b77:257-271):`discard` 条件 = `clamp(((_UseCutOff×(_CutOffPosY - dot(WS, _CutOffDirection.xyz))) + ((_DissolveTex.SampleBias(...).x - ((max(_DissolveScheduleOffset, Stripped_208.w) × 2.019999980926513671875f) - 1.0099999904632568359375f)) × _UseDissolve)) × _DissolveEdgeSharp, 0, 1) - 0.01 < 0`;UV = `lerp(UVSet 选择, viewUV, _DissolveUseViewUV) × _DissolveTex_ST.xy + .zw`;抖动 = `min(阈值项, (1-max(y,z)) - noise) < 0`(同 overlay)。
- v_b76:蒙皮(权重 TEXCOORD1/索引 TEXCOORD2)→ 阴影变换,输出仅 SV_Position。

### Pass5 TextureStreamingFeedback(b80)
- 无颜色输出;对 4 张贴图(句柄 = `PerDraw.Stripped_176.xyzw`):`uv × _BaseMap_TexelSize.wz` → ddx/ddy → `mip = uint(clamp(0.5f × log2(max(max(dot(ddx,ddx), dot(ddy,ddy)), 9.9999999747524270787835121154785e-07f)), 0, 15))`;位 = `1 << (((句柄 & 1u) × 16 + mip) & 31)`;字 = `句柄 / 2`(≥16384 跳过);`_TextureStreamingDesiredMipLevels.InterlockedOr(字×4, 位)`(f_b80:81-176)。
- b81(wave ops):+74 行——同功能的 wave 归约改写:`WaveActiveBitOr(候选位)` → `WaveReadLaneFirst` → `if (WaveIsFirstLane()) InterlockedOr`(先波内归约、仅首线程写位图),算法语义与 b80 一致(diff 已定性)。

## 7. 湿身锚点 b400(cloth ForwardLit)湿身段抽取

来源 `characternpr\Sub0_Pass0_Fragment_b400.hlsl`(1626 行;`official-wetness-b400-excerpt.txt` 只保留作历史原文摘录，不能单独证明输入闭合)。丝袜(631-655)→ 雨/涟漪(668-1012)→ 雪(1013-1060)，输出包 `_2138.._2149`/`_2279.._2283`→ PBR(1061-1131)。输入量：`_623`=R 雨量，`_626`=A 雪量，`_635`=水线局部湿度，`_636`=max(B 浸水量,水线局部湿度)，`_637`=max(雨量,浸湿量)。`_478` 是逐对象蒙皮位，不是独立“三平面开关”；`_9/_10/_11` 为静止法线/切线/位置输入。捕获中具体材质是否使用此变体须另核，不能给所有提弗洛斯材质强套 b400。

### 7.1 丝袜子材质(631-655)
```
specInt = _SilkStockingsSpecularInt × lerp(_SilkStockingsSpecularMinAtMinWetness, 1.0f, _637)      // :631
if (_SilkStockingsAdvance > 0.5f):                                                      // :637
  mask = _SilkStockingsMask.SampleBias(LinearClamp, uv0, mipBias)                       // :639
  _1201 = lerp(_512, 1 - mask.z, _637)          // 粗糙度，_512 = 1 - MetallicGlossMap.a
  _1202 = specInt × mask.x                       // 各向异性高光强度
  _1203 = clamp(mask.y×2 - 1, -0.949999988079071044921875f, 0.949999988079071044921875f)  // 各向异性方向
  _1204 = clamp((lerp(_516, mask.w, 湿度) + 1) - _SilkStockingsColor.w, 0, 1)             // 影响幂
else:
  _1203 = -lerp(_SilkStockingsAnisoDirection, 0.5f, clamp(_516×0.5, 0, 1))
  _1204 = clamp((_516 + 1) - _SilkStockingsColor.w, 0, 1)
tint = lerp(_SilkStockingsDryColor.xyz, _SilkStockingsWetColor.xyz, 湿度)               // :652 干/湿色
affect = lerp(_SilkStockingsMinAffect, _SilkStockingsMaxAffect, clamp(pow(1.0499999523162841796875f - clamp(dot(V, N), 0, 1), _1204×2), 0, 1))  // :653(菲涅尔幂 1.05-NdotV)
albedoS = lerp(_503 × tint, _SilkStockingsColor.xyz, affect); shadowS = lerp(_525 × tint, _SilkStockingsColor.xyz, affect)   // :654-655
```

### 7.2 程序化雨滴涟漪(668-947)
```
门:if ((clamp(_623+_636,0,1) - _DisableRainEffectOnMaterial) > 0.00999999977648258209228515625f) // :669
_1246 = (step(_623, 0.00999999977648258209228515625f) * step(0.00999999977648258209228515625f, _636)) != 0 // :673，边界包含等号
三平面基:uv3 = (蒙皮翻转? restPos.xzy×(1,1,-1) : restPos) × _CharacterParams10.z        // :675-676
雨向投影:dir3 = (0,-1,0) + Ngeo×Ngeo.y；proj = restT.xyz×dot(dir3,Tws) + (cross(restN,restT.xyz)×restT.w)×dot(dir3,Bws) + restN×dot(dir3,Ngeo) // :678-681，不是 restPos
贴图三平面权重:w = max((|restN|-0.2)³, 6.103515625e-05f) / dot(·,1)                    // :682-684
程序雨滴平面权重:pow(max(|restN|-0.2,0),10) / max(sum,6.103515625e-05f)                 // :704-705，与贴图权重不同
雨痕强度场:rain3 = _CharacterRainEffectTex 三平面(xz/xy/zy)加权                          // :685-690
  streakW = rain3.w;edge = 1.1 - streakW                                                // :691-692
  rippleN.xy = rain3.xy×2-1                                                             // :693
动画:period = 水中?(1-_636).xx:(3.0f, 4.340000152587890625f);t = 水中? 1 : _Time.x;anim = t×period // :696-701
程序雨滴：两组×三平面；粗网格 ×32，细网格 ×46×1.39999997615814208984375f，不是第三组“×1.4 大网格”。
  cell = floor(uv×32);h = frac(cell×(123.339996337890625f, 456.209991455078125f));h2 = h + dot(h, h+34.345001220703125f.xx);rand = frac((h2.x×h2.y, h2.x+h2.y))   // :709-714
  邻格哈希 +114.51399993896484375f                                                       // :715-719
  半径 r0 = 0.25f × lerp(0.6, 1.0, rand.x)                                              // :721
  cellN = ((frac(uv×32) + ((rand2×2-1)×0.25)) - 0.5) 旋转到雨向(dir 旋转矩阵,零长度保护 1e-5)  // :722-736
  shape = (cellN.x*1.25, cellN.y*(cellN.y<0 ? 1.25 : 0.75));dist = length(shape)         // :739-740，先做非对称缩放再算距离
  生命期:phase = 水中? lerp(0.2199999988079071044921875f, 0.85000002384185791015625f, clamp(anim+rand.x,0,1)) : frac(anim+rand.x)  // :742，水中/降雨分支不能反转
  ring = (smoothstep(0.2, 0.2199999988079071044921875f, phase) × smoothstep(0.85, 0.55, phase)) × step(0.001, smoothstep(r0, 0, dist)) × step(强度阈值, rand.y-0.1)  // :744
  扰动 = clamp(shape/r0, -1, 1) × lerp(0.25, 0.5, rand2.x) × ring × 平面权重             // :745-746
三平面合成:xy = Σ扰动; z = max(ring×权重);w = 优势平面 rand.y                    // :827-831
细网格(×46×1.39999997615814208984375f，半径 lerp(0.6,1)×0.3499999940395355224609375f，cell 偏移 ×0.71428573131561279296875f)重复三平面 // :832-939
两组合并：_1954 = step(_1641.x,0.00999999977648258209228515625f)；_1964 = max(_1651.zw*step(0.00999999977648258209228515625f,_1648),_1947.zw*_1954)；_1972 = _1651.xy + _1947.xy*_1954 // :940-944；强度 _1648 与半径相关包 _1641 不能混为同一变量，_1967 的完整 max 见源码 :942
```

### 7.3 雨痕条纹与法线合成(945-970)
```
_1987 = clamp(_637*2,0,1);scroll = (0,_Time.x*_CharacterParams10.z*0.75)               // :945-946
// :947-953，条纹为 xy/zy 两个竖直平面；水平化 restNormal 后重算权重 _2005。
streak = Sample(RainStreakTex,uv.xy)*_2005.z + Sample(RainStreakTex,uv.zy)*_2005.x
scrollW = Sample(RainStreakTex,uv.xy+scroll).w*_2005.z + Sample(RainStreakTex,uv.zy+scroll).w*_2005.x
dropTS = normalize(float3(_1972*2.5,max(1.000000016862383526387164645044e-16f,sqrt(1-clamp(dot(_1972,_1972),0,1)))))
_2040 = (_1305.xy*2-1) + dropTS.xy + (streak.xy*2-1)*scrollW*_1987                   // :954，不可遗漏程序雨滴归一化项
_2047 = smoothstep(1-streak.z,1.10000002384185791015625f-streak.z,smoothstep(1,0.800000011920928955078125f,_1204))*_1987 // :957
_2056 = normalize(float3(_2040,max(1.000000016862383526387164645044e-16f,sqrt(1-clamp(dot(_2040,_2040),0,1))))) // :960
// cross(_580,(0,1,0)) 退化时用 (1,0,0)；基 T=_2062，B=cross(_2062,_580)。
_2072 = normalize(_2062*_2056.x + cross(_2062,_580)*_2056.y + _580*_2056.z)            // :961-966，世界湿法线
_2073 = step(0.550000011920928955078125f,_1964.y);_2075 = clamp(dot(_469,_580),0,1)    // :967-968，视线与原表面法线
_2078 = _1968*(1-_2073)*_2075                                                        // :969，定向雨滴影响量
_2081 = max(max(step(1.0099999904632568359375f-((1-_1204*0.5)*_637),_1305.z),_2047),_1968*_2073)*_2075 // :970，总湿法线混合量
```

### 7.4 湿身对材质的作用(971-996)
```
darken = lerp(1, 1-|_SilkStockingsAlbedoAffectType|, max(smoothstep(0.8-streakW, 1.1-streakW, clamp(_623×_SilkStockingsRainWetMaskScale,0,1)), smoothstep(0.449999988079071044921875f-streakW, 1.1-streakW, clamp(_635,0,1))))  // :971，后项用水线局部湿度，不用雪量或直接浸水量
_2093 = _1967.x*4;_2103 = clamp(dot(_2056,normalize((0,-1,0.75))),0,1)                 // :976-977，方向增益用切线雨滴法线，不是世界湿法线
_2109 = 0.60000002384185791015625f*_2078*_2093
_2112 = (1-_2109) + clamp(clamp(_1967.y*17.54000091552734375f,0,1)+clamp(1.60000002384185791015625f*_2056.y,0,1),0,1)*_2109 // :980-981
albedo湿 = (AlbedoAffectType>0 ? 丝袜色×darken : lerp(原albedo, 丝袜色, darken)) × _2112 // :982
specBoost = smoothstep(0.6, 1.0, _2112)                                                 // :983
_2138 = normalize(lerp(_580,_2072,_2081))                                             // :985
_2139 = normalize(lerp(_580,_2072,_2081*step(_1968,0.00999999977648258209228515625f))) // :986，测试强度，不是半径
_2140 = _2072;_2141 = 1;_2142 = lerp(_1201,min(_1201,0.0500000007450580596923828125f),_2047) // :987-989，降粗糙度
_2143 = _2078*_2093                                                                  // :990
_2144 = lerp(0.05,1.7999999523162841796875f,_2103³)*_2093*specBoost*_2078*lerp(1,0.3,clamp(luma(albedo湿),0,1)) // :991
_2145 = lerp(1,0.8*lerp(0.5,1,specBoost),_2078)                                       // :992
_2146 = max(_1968,_2081);_2147 = lerp(_1201,min(_1201,0.05),_2081)                    // :993-994
无雨 else:_2138..2140 = N;_2142 = 0.01;_2145 = 1;_2147 = 粗糙度                           // :998-1011
```

### 7.5 雪三平面(1018-1051)
```
门:if (_626(雪量) - _DisableRainEffectOnMaterial > 0.00999999977648258209228515625f)       // :1019
snow3 = _CharacterSnowEffectTex 三平面(xz/xy/zy,权重 (y,z,x))                            // :1029
_2201 = clamp(雪量 + smoothstep(0.35, 0.2, restPos.y) × clamp(雪量×3,0,1), 0, 1)          // :1031，静止位置高度调制；不能凭此称“顶部”加成
coverage = smoothstep(2-_2207, 2.35-_2207, (restN.y×0.65+0.35) + snow3.z) × (遮挡² × gl_FrontFacing)  // :1032-1033(_2207 = _2201×(2-_2201))
tintDown = lerp(1, 0.5, ((_2201×(1-smoothstep(0.35,0.1, luma(雨色 albedo×(1-金属))))×snow3.w) × (restN.y×0.25+0.75)))   // :1034，输入不是 coverage/遮挡
法线/切线框同 liquidag 雪分支(:1036-1047);粗糙度→0.9、阴影底色先乘 tintDown 再向0.308混合、albedo先乘 tintDown 再向0.88混合、金属→0 // :1048-1051
无雪 else 的 _2279 = _580（原法线），不是 _2138（湿扰动法线）；必须保留源码中各法线的独立用途。 // :1055
```

### 7.6 PBR 组装 + 各向异性高光(1061-1131)
```
diffuseEnergy = 0.96 - metal×0.96;specColor = lerp(0.04×_507.y, albedo, metal)           // :1061-1063
shininess = max(roughness², 0.0078125f);shininess² = _2293                               // :1065-1066
anisoDir = _1203 × (1 - clamp(_1204 × _SilkStockingsSpecularFalloff, 0, 1))              // :1067 各向异性方向(湿度衰减)
anisoT = (1-anisoDir)×shininess;anisoB = (1+anisoDir)×shininess                          // :1068-1069，不再平方
MV w = (_2146 > 0.1) ? 0.7 : 0.4(湿身区域标记)                                           // :1075
// SpecRampMap 的 y 是 _2280(粗糙度)*(1-_2283(金属))，不是平滑度。x 的完整表达式见 :1118，含分母限幅，不能只写 D/denom 替代。
// 源码各向异性有理分布(spec = _1202 强度)；旧文笼统称 Ward 不应作为公式依据。H' = normalize(H + V×_SilkStockingsSpecularValue) // :1120
 a = _2302.y; b = _2305.y; ab = a*b;
 _2569 = (b*dot(_586,H'), a*dot(cross(_580,_586)*_6.w,H'), ab*dot(_2138,H'))
 d2 = dot(_2569,_2569); numerator = ab*ab*ab; denominator = d2*d2;
 anisoD = clamp(numerator != denominator ? numerator/denominator : 1, 0, 20)           // :1121-1128，删去不完整的猜测公式
color = diffuse×预乘因子 + (specGGX×_2145 + (diffuse+specGGX)×_2144 + 丝袜扫光×_2143×lightTerm)  // :1131(_2592 = 副扫光方向 normalize((-wetN.z, 0.001, wetN.x)),双 smoothstep 0.15/0.1、0.07/0.02)
```
其余边缘光、点光、VFX、雾段(1134-1626)仍需逐变体核查；“家族结构类似”不证明与其它部件逐项等价，不能据此整段替换。

## 8. b12 与 b400 的湿身实现对照(一句话版)

| | liquidag b12 | cloth b400 |
|---|---|---|
| 雨湿/浸湿/雨痕/程序雨滴 | 无(b12 只有雪) | 全有(两组程序雨滴 + RainStreakTex) |
| 雪 | 单 UV 平面采样(589) | 三平面 + 静止位置高度调制(1029-1033) |
| 丝袜系统 | 无 | 全有(SilkStockings 14+ 属性) |
| 反射/高光着色 | _CharMaxCubemap + 有理多项式 split-sum(680-693) | 本节只展开 SpecRampMap + 各向异性高光；不能因此断言整个 b400 没有其它反射项 |
| 高光 | GGX 项（保留源码伪光向和法线分工） | 各向同性 + 各向异性有理分布 + 扫光 |

## 9. ⚠待核汇总

1. `_8.y/_8.z`(雪覆盖度取分量)蒙皮/静态轴约定依据(f_b12:591)。
2. liquidag 描边 `_BaseMap_b2`(t2,space1)对应 `_OutlineColorMap` 还是 `_OutlineMask`(f_b36:334,工具命名未恢复真名)。
3. liquidag 描边 c14.xyz = `_OutlineTintColor`(f_b36:372)——按属性语义推断,未逐字验证。
4. 描边 c2.x == 1.0 的属性名(_OutlineTransparent 或 _SurfaceType 复用)⚠待核。
5. PreGBuffer 法线 w=0.0(eye 为 0.7)的语义(f_b52:272)。
6. Pass3 RTR 的 renderer 调用形态(全屏 vs 网格;顶点仅 SV_VertexID)与 `_39_40` 匿名 cbuffer 内容。
7. Pass0 c12(_DepthFadeValue/_DepthFadeExp)、c16-c20(VFX 组)在 b12 未读,b14(_ALPHA_SCENE_DEPTH_FADE/_CHARACTER_VFX_SPECIAL)分支未逐行。
8. b81 wave ops 76 行 diff 未逐行。
9. b13(+_NORMALMAP)顶点/片元未全文(切线输出与 TBN)。
10. b400 输入公式已回溯（见 R2.1），但天气掩码/水线高度的引擎生产端、实际天气帧绑定未核实；不能把源码读取公式当作生产端已闭合。

---
*仅静态转写,无测试/参考实现;行号均指上文所列源文件。*

---

## 补充抽取(round 2,2026-09-28)

> 修正一个 round 1 的路径笔误:liquidag 的变体目录是 `characternpr\characternpr_liquidag\`(wrapper 为 `characternpr_liquidag.shader`,keyword 表 :136-147;Pass0 fragment 派发 :192-229,b13 = SRP_INSTANCING+PER_OBJECT_MV+SHADOW_MASK+**_NORMALMAP** 单开最小变体),非 `characternpr\liquidag\`。

### R2.1 b400 湿身段的上游输入定义(characternpr\characternpr\Sub0_Pass0_Fragment_b400.hlsl:406-466,已全文)

§9-10 两条遗留闭合(注意 **b400 属 characternpr.shader 主角色 shader**,变体目录 `characternpr\characternpr\`):

```
贴图基色:_498 = _BaseMap.Sample(_3);_503 = _498.xyz × _BaseColor.xyz;_516 = _498.w × _BaseColor.w        // :428-429/:434
金属/高光:_507 = _MetallicGlossMap.Sample;_508 = _507.x(金属);_510 = _507.z;_512 = 1-_507.w(粗糙度)        // :430-433
阴影色:_521 = _503 × _ShadowColorBrightness;_525 = lerp(luma709(_521), _521, _ShadowColorSaturation)        // :435-436
法线:_529 = _BumpMap.Sample;_529.w = _529.w × _529.x;_538 = (w,y)×2-1;z=√(1-clamp(dot,0,1)) 重构;_548 = _539.xy × _BumpScale   // :437-443
TBN:T = _6.xyz;B = cross(_5,_6.xyz)×_6.w;N = _5;世界法线 = mul((_548,_539.z), TBN)→normalize×(gl_FrontFacing ? 1 : -1+2×_BackFaceNormalFlip)   // :448-453
切线重正交:_586 = normalize(_6.xyz - _580×dot(_6.xyz,_580))                                                  // :455
逐对象蒙皮开关(asuint(Stripped_64.w) & 16):蒙皮位走 _VertexSkinMatrices.Load,否则 UnityPerDraw.Stripped_0[2]/[0](:414-427)
```

**湿身掩码打包解码(核心,:458-465)**:
```
_609 = asuint((_CharacterParams10.x > 0.5f) ? _CharacterParams10.y : UnityPerDraw[_13].Stripped_208.x)    // :458(全局/逐对象切换)
_622 = (R=_609&255, G=(_609>>8)&255, B=(_609>>16)&255, A=(_609>>24)&255) × 0.0039215688593685626983642578125   // :459(RGBA8 字节拆包)
_623(雨量) = _622.x;_626(雪量) = _622.w                                                                     // :460-461
_635(湿度) = smoothstep(-0.20000000298023223876953125, 0.1500000059604644775390625, lerp(UnityPerDraw.Stripped_208.y, _CharacterParams10.w, _CharacterParams10.x) - 世界y) × _622.y   // :463(对象水线高度-像素高度,±0.2/0.15 过渡带)
_636 = max(_622.z(直接浸湿量), _635);_637 = max(_623, _636)                                                  // :464-465，不涉及雪量，没有通道优先级
曝光底:_645 = lerp(_EnvironmentGlobalParams0.x, 1.0f, _CharacterParams12.w) × _ExposureWithMiscParams.x       // :466
```
即 shader 读取端为：**RGBA8 位包（R=雨量、G=水线湿度幅度、B=直接浸湿量、A=雪量）+ 水线世界高度 + 像素世界 y**。这些中文标签按实际分支用途确定，不是引擎侧字段名。`asuint` 是 float 位重解释，不是数值转 uint；写入端也必须保持位模式。掩码选择用 CP10.x>0.5 的分支，而水线高度使用 CP10.x 连续 lerp，两者不能合并成一个布尔开关。生产端尚未证实。

### R2.2 liquidag b13(_NORMALMAP)切线/TBN 路径(f_b13:410-424,diff b12→b13;§9-9 闭合)

与 b400 法线路径**逐字同构**(差异仅变量号/寄存器):
```
_464 = _BumpMap.Sample;_464.w = _464.w × _464.x(AG 打包)                                                    // :410-411
_473 = (_464.wy × 2.0f) - 1.0f;_474.z = max(1.000000016862383526387164645044e-16, sqrt(1-clamp(dot(_475,_475),0,1)))   // :412-415
_483 = _474.xy × _BumpScale                                                                                  // :416
世界法线 = mul((_483.x,_483.y,_474.z), float3x3(_6.xyz, cross(_5,_6.xyz)×_6.w, _5))→normalize×(gl_FrontFacing ? 1 : -1+2×_BackFaceNormalFlip)   // :421-423
```
b13 相对 b12 新增插值器:`_6 : TEXCOORD3`(float4 切线+w 手性)、`_9 : TEXCOORD6`、`_11 : TEXCOORD7`(nointerpolation uint)(f_b13:356-360);b12(无 _NORMALMAP)无 _BumpMap 采样,直接用几何法线。
