# 官方 CharacterNPR_Skin CharacterOutline 描边 pass 译读(变体 b273)

来源:`FractalMiner\_dump_1.5.3\AllShader_1.5.3\Assets\packages\com.hg.render-pipelines\runtime\shaders\materials\characternpr\`
- 顶点 `characternpr_skin\Sub0_Pass1_Vertex_b273.hlsl`(509 行，含 main 适配层)
- 片元 `characternpr_skin\Sub0_Pass1_Fragment_b273.hlsl`(1012 行，含 main 适配层)
- 属性/pass 定义 `characternpr_skin.shader`(2116 行)

格式沿用 `docs/research/official-forwardlit-skin-b138.md`。本文只写文件,不改工程。

> 2026-09-30 回源复核：本译文只提供指定 dump 变体的证据，不等于生产端/实际调度闭合。原“视图旋转”应为NonJitteredVP的3×3；切线sign(0)、蒙皮组用途与上一帧条件极性已更正。属性顺序借名、运行时b273/b274、掩码贴图实际身份保持未确认；原末尾“最小改法”仅为近似路线，不是官方基线验收方案。

## 0. 结论速览

1. **官方描边不是"纯色背面壳"**:`CharacterOutline` pass 的片元是一套**缩水的 ForwardLit 全打光**(环境辐照度体、方向光、屏幕空间阴影、点光源分箱循环、雾、VFX 调色全套都在),只是把漫反射 albedo 换成"BaseMap × 描边色调 × 亮度 → 饱和度 → 覆盖色",并且**没有高光/SSS/LUT/雨雪**。
2. **打光法线不是自己的平滑法线,而是 GBuffer 法线**:片元把**未外扩**的世界坐标重投影回屏幕、`Load` `_GBufferTexture1` 并做八面体解码,用"这个顶点挤出来源处那个像素"的法线参与所有光照计算。写这张 GBuffer 的是各部件的 **PreGBuffer** pass(eye 的 PreGBuffer 片元就是 5 路 MRT 输出,见 §7.4)。
3. 顶点外扩公式是 **FOV 补偿的屏幕空间外扩 + 像素下限钳制 + 深度偏移**,平滑法线来自网格里 2 通道半球编码(`_OutlineAverageNormal`),切线/法线来自 TANGENT0 的 10bit 八面体打包。
4. b273 是 Pass1 的 **catch-all 变体**(shader:903/1023 的 `#else`),关键字 = 三个常开项。捕获帧材质在 Pass0 开着 `_DIFF_RAMP_ON`(b138 头注释),Pass1 也声明了同一关键字,所以**运行时脸的描边大概率走 b274(ramp 贴图版)而非 b273**【推断,见 §6.1】。

## 1. 变体识别与 pass 状态

`characternpr_skin.shader:751-768`(Pass "CharacterOutline"):
`Blend 0 [_SrcBlend][_DstBlend], [_AlphaSrcBlend][_AlphaDstBlend]`、`ZClip On`、**`ZTest Less`**、`ZWrite [_ZWrite]`、**`Cull Front`**、`Stencil { Ref 36 / Comp Always / Pass Replace }`、`LIGHTMODE="CharacterOutline"`。

`#pragma multi_compile_local`(775-785 行,共 11 个):`SRP_INSTANCING_ON`、`HG_ENABLE_PER_OBJECT_MV`、`HG_ENABLE_SCREEN_SPACE_SHADOW_MASK`、`_DIFF_RAMP_ON`、`_EMISSION`、`BAKED_SKINNING_ANIMATION_TEXTURE`、`_SDFLIGHTMAP`、`_SHADOW_LUT_TEX`、`_OUTLINE_MASK`、`VFX_CHARACTER_DISSOLVE`、`DITHER`。

b273 头注释(文件 1-2 行)关键字 = `HG_ENABLE_PER_OBJECT_MV HG_ENABLE_SCREEN_SPACE_SHADOW_MASK SRP_INSTANCING_ON`,即全部可选关键字关闭;dispatch 表(shader:903、1023)里它是 `#else // Catch-all` —— 与关键字自洽(该组合没有单列分支,由 catch-all 承接)。皮肤部件的属性开关(71-81 行):`_EnableOutline`(总开关)、`_OutlineTransparent`、`_OutlineWidth`、`_OutlineOffsetZ`、`_OutlineColorBrightness`、`_OutlineColorSaturation`、`_EnableOutlineMask [Toggle(_OUTLINE_MASK)]`、`_OutlineAverageNormal`、`_OutlineMask`、`_OutlineZTest`(默认 4)。

## 2. 顶点着色器(b273)

### 2.1 输入(layout 与 ForwardLit 不同,描边专用)

| 槽位 | 变量 | 内容 | 证据 |
|---|---|---|---|
| POSITION0 | `_3` float3 | 物体空间顶点 | 276 行 |
| NORMAL0 | `_4` float2 | **UV0**(法线槽让位给 UV,描边不需要顶点法线) | 477 行 `_12 = (_4*_ST.xy)+_ST.zw` 是 UV 输出 |
| TANGENT0 | `_5` float3 | 打包法线/切线:x 的 bit30=打包标志;打包时低 30 bit = 3×10bit | 300-301 行 |
| COLOR0 | `_6` float4 | 未打包时的切线 xyz + w=副切线符号 | 334 行 |
| TEXCOORD0 | `_7` float2 | 2 通道半球编码平滑法线(`_OutlineAverageNormal` 数据源) | 435-439 行 |
| TEXCOORD1 | `_8` float4 | 烘焙蒙皮动画位置(非烘焙时不用) | 349/431 行 |
| TEXCOORD2/3 | `_10`/`_11` | 骨权重 float4 / 骨索引 uint4 | 371-404 行 |

### 2.2 10bit 八面体法线/切线解包(300-332 行,即任务点名的 300-330 段)

- `_137 = asuint(_5.x)`;`_139 = (bit30) > 0` → 打包模式。
- 三个 10bit 字段:`_145 = bit[0..9]`、`_148 = bit[10..19]`、`_151 = bit[20..29]`,各按 `(v>=512)? v-1024 : v` 转有符号,乘 `0.001956947147846221923828125`(= **1/511**,即 [-511,511] → [-1,1];注意有符号化后范围是 [-512,511],负端会略超 -1)。
- 前两个字段做八面体解码(`_171 = 1-|x|-|y|`,`_174` 负半球翻转)→ 单位法线 `_185`(309-316 行)。
- 第三个字段(切线)**不是**第二个八面体:解码为有符号标量(实际负端可略小于-1),经 `_197 = (w<0)?-1:1`、`_200 = 1-(w*_197)*2`，再 `normalize(float2(_200,_197*(1-abs(_200))))` 投到 `float2x3(_193,normalize(cross(N,_193)))` 重构切线。0 的符号为 +1，不能替换 `sign(w)`。`_193=normalize((N.yzx-N.zxy)-dot(N.yzx-N.zxy,N).xxx)` 必须保留广播减法，不能擅改成乘 N 的常见正交投影。`_208.w=bit31?1:-1`（317–324行）。
- 未打包模式:`_212 = _5`(TANGENT0 即法线)、切线取 COLOR0(330-334 行)。

### 2.3 蒙皮(335-422 行)

`asuint(Stripped_64.w)` bit5=GPU 蒙皮、`_226=asuint(Stripped_64.w)&~0x20` 作骨骼数(≥2用2骨、≥4用4骨)。矩阵从 `_VertexSkinMatrices` 的 `asuint(Stripped_80.x/y)+3+idx*3` 起读，每项×16转字节地址。80.x 组同时作用于法线、切线和当前位置 `_405`（415–419行），80.y 组只输出 `_406`（420行）；不能当成“切线组”。_406 的生产语义仍待资产/引擎证据，而非仅凭位置推定烘焙动画。

### 2.4 世界变换与运动矢量源(423-431 行)

- `_415` = objectToWorld 3×3(UnityPerDraw Stripped_0);`_425` = 相机相对世界坐标。
- `_494` = 上一帧裁剪坐标；当 `UnityPerDraw.Stripped_160.x<1` 时选实时位置 `_405`，否则选 `_406`（430–431行）。无蒙皮时 `_406=_8.xyz`，启用蒙皮时来自80.y组。字段语义待生产端证据，不能把条件真/假写反。

### 2.5 平滑法线分支(432-444 行,任务点名 432-441 段)

```
if (_30_Stripped_240 > 0.5) {            // _OutlineAverageNormal
    _502 = float3(uv7.xy, sqrt(1 - clamp(dot(uv7.xy,uv7.xy),0,1)))   // 半球重建 z
    _509 = normalize(世界切线)
    _514 = mul(_502, float3x3(_509, cross(世界法线,_509)*手性, 世界法线))  // TS→WS
} else _514 = 世界法线(几何)
```
`_514` 作为 TEXCOORD2 输出给片元(479 行)——但片元打光用的不是它(见 §4.2),它只作为"输出法线"存在。

### 2.6 屏幕空间外扩 + FOV 补偿 + 像素钳制(445-460 行,任务点名 442-470 段)

```hlsl
// 445-452 行以分段五次多项式近似 atan(-1/ProjMatrix[1].y)，保留符号。
// 它不是精确 atan；完整系数见逐行层/原始源，不能换成绝对半角。
fovHalf = _543
vp3 = float3x3(NonJitteredViewNoTransProjMatrix[0].xyz,
               NonJitteredViewNoTransProjMatrix[1].xyz,
               NonJitteredViewNoTransProjMatrix[2].xyz)
n2 = normalize(mul(vp3, _514).xy) * float2(BackBufferSize.y/x,1)
offset = n2 * (_OutlineWidth * (0.3926990330219268798828125/fovHalf))
          * clamp(w*(fovHalf*114.5915679931640625)*0.039999999105930328369140625,0,1)
          * 0.004999999888241291046142578125
```
逐项拆解(453 行):
- `π/8 = 0.39269908`、`114.59156 = 360/π`,故距离项 = `clamp(视深 w × deg(fovY) × 0.04, 0, 1)` —— 外扩随距离线性增长,到 `w = 25/deg(fovY)` 米封顶(fovY=40° 时约 0.625 m 处饱和)。
- 总尺度 `0.005`。
- **逐轴下限钳制**(454–458行)：`cap=BackBufferSize.zw*clamp(w,0,1.57079613208770751953125/_543)`；仅当某轴 `abs(offset)<cap` 才取该轴 `cap*sign(offset)`。最终还需透视除法和目标尺寸才能换成实际像素，不可直接称 `min(w,π/fovY)` 像素；`_BackBufferSize.zw` 的输入值及符号约定需捕获/生产端证明。
- 去掉当前帧 TAA 抖动后加 offset(459 行):`clip.xy = clip.xy - jitter·w + offset`(offset 单位是裁剪空间)。

### 2.7 深度偏移(461-474 行)

```
viewZ' = -w + _OutlineOffsetZ × (-0.1)           // 464 行;OffsetZ>0 → 更远
clip.z = ((viewZ'·P[2].z + P[2].w) × w) / (-viewZ')   // 透视;正交分支直接加 OffsetZ×-0.1/far(472 行)
```
配合 pass 的 `ZTest Less`:OffsetZ 正值把描边往身后推,压进角色深度之内,避免内轮廓闪面。

### 2.8 输出

`_12`=UV(经 c10 的 ST)、`_13`=positionRWS(未外扩)、`_14`=_514、`_16/_17`=当前/上一帧裁剪 xyw(**两者都加了同一外扩 offset**,476-481 行,故 MV 描述的是外扩轮廓自身的运动)、`_19`=instanceID。`gl_Position.y` 取反(484 行,Vulkan 语义)。

## 3. 材质常量映射(`_44_Stripped_N` → 属性名;顶点里叫 `_30_Stripped_N`,同一 cbuffer b0,space1 两种命名)

**先说结构**:Pass0(ForwardLit,b138)的材质 cbuffer 是具名 `type_UnityPerMaterial`(b138:263-319 行,成员名可从反射恢复),Pass1(描边,b273)的 cbuffer 是**独立结构**(匿名 `_43_44`,尾部比 b138 少一个 `_DissolveTex_ST` 槽,且 `_AnimationTexture_TexelSize` 等槽位语义不同)。两者共享前缀槽位(c0-c13 一带槽形/用法一致,下表标"共享"的即按此前缀借名),描边专属参数集中在 c14-c16。dump 工具对描边 cbuffer 的成员全部标为"无 CPU 属性匹配"(`_44_Stripped_N`),因此描边专属名的依据是 **shaderlab 属性声明顺序与槽位的连续对应**(width→offsetZ→brightness→saturation→avgNormal 恰好连续占 c14.x→c15.x,与 shader:74-79 行的声明顺序一致)。

**认证边界**：ShaderLab Properties 顺序不是 cbuffer ABI 证据。下表“强(顺序对应)”只表示静态借名的较强假说，不可提升为已确认生产端字段名；公式和字节偏移可逐字认证，属性名仍须真实反射/上传值/逐属性变更证据。不同 pass/部件必须独立验证。

| 偏移 | 常量 | 用途(公式位置) | 对应属性 | 证据强度 |
|---|---|---|---|---|
| c10 (160) | xy/zw | UV 缩放/偏移(顶点 477 行) | **`_BaseMap_ST`**(共享前缀;b138 c10 同名同槽) | 强 |
| c14.x (224) | float | 外扩宽度系数(453 行) | **`_OutlineWidth`**(shader:74,Range(0,2) 默认 0.5) | 强(顺序对应) |
| c14.y (228) | float | 深度偏移 ×(-0.1)(464/472 行) | **`_OutlineOffsetZ`**(shader:75,Range(0,1)) | 强(顺序对应) |
| c14.z (232) | float | 受光侧 albedo 乘数:`_367 = BaseMap.rgb × _BaseColor.rgb × 232`(395 行) | **`_OutlineColorBrightness`**(shader:76,Range(0,1)) | 强(顺序对应;c4.z 已被 _ShadowColorBrightness 占名,二选一消解) |
| c14.w (236) | float | 受光侧灰度插值权重:`_371 = lerp(luma(_367), _367, 236)`(396 行) | **`_OutlineColorSaturation`**(shader:77,Range(0,2)):lerp 权重 >1 外插过饱和,与 Range(0,2) 吻合 | 强(顺序对应) |
| c15.x (240) | float | >0.5 走平滑法线分支(433 行) | **`_OutlineAverageNormal`**(shader:79,Toggle 默认 1) | 强(顺序对应) |
| c15.w (252) | float | `(_44_Stripped_252 != 0).xxx` 逐通道覆盖使能(393 行) | 无同名 UI 属性【未确认】 | — |
| c16 (256) | float3 | 覆盖描边色 `_372 = enable ? 256 : _371`(397 行) | 无同名 UI 属性(可能由 C# 或部件配置驱动)【未确认】 | — |
| c6 (96) | xyz / w | xyz=BaseMap 色调乘数(395 行);w 在布料/头发描边里作 alpha 强度(布料 f1088:393 行) | **`_BaseColor`**(共享前缀;b138 c6 同名同槽) | 强 |
| c4.z (72) | float | 阴影侧 albedo 乘数 `_377 = _372 × 72`(398 行) | **`_ShadowColorBrightness`**(共享前缀;b138 c4.z 具名;语义吻合:无 LUT 时的阴影色亮度) | 强 |
| c4.w (76) | float | 阴影侧灰度插值 `_963 = lerp(luma(_377), _377, 76) × 0.96`(577 行) | **`_ShadowColorSaturation`**(共享前缀;b138 c4.w 具名) | 强 |
| c12.x (192) | float | rim 权重乘数(575 行 `_953`) | 疑 **`_SkinRimOffScale`**(b138 c12.x 具名且语义同为 rim scale;但已进入疑似描边专属区)【未确认】 | 中 |
| c13.xyz (208) | float3 | rim 染色(576 行) | 疑 **`_SDFRimColor.rgb`**(b138 c13 具名且语义同为 rim 色)【未确认】 | 中 |
| c3.x..w (48..60) | 4×float | `_EnableVFXColorAdjustment / _ColorAdjustmentBrightness / _ColorAdjustmentSaturation / _ColorAdjustmentContrast`(924-926 行) | 同名属性;与 ForwardLit b138 相同偏移 | 强 |
| c4.x/y (64/68) | float | `_ColorAdjustmentRimWidth / _ColorAdjustmentRimIntensity`(926 行) | 同名属性 | 强 |
| c8 (128) / c9 (144) | float4 | `_ColorAdjustmentColorBlend / _ColorAdjustmentRimColor`(926 行) | 同名属性 | 强 |

布局注意:每个部件 shader 的 Pass1 材质 cbuffer **各不相同**(布料的亮度/饱和度在 c12.z/c12.w,见 §7.1),上面的偏移**只对 characternpr_skin 的描边 pass 有效**;但"c4.z/w=_ShadowColorBrightness/Saturation、c6=_BaseColor、c10=_BaseMap_ST"这组共享前缀名在布料/头发的描边里同样成立(用法逐字一致)。

## 4. 片元着色器整洁重构(b273,995 行)

### 4.0 输入纹理与全局常量一览(描边颜色的全部输入)

| 寄存器 | 名称 | 采样方式 | 用途 |
|---|---|---|---|
| t1,space1 | `_BaseMap` | SampleBias(LinearClamp, uv0, _GlobalMipBias) | 描边 albedo 底图(§4.3) |
| t38,space0 | `_GBufferTexture1` | Load(像素) | 八面体法线,描边打光法线(§4.2) |
| t22,space0 | `_ScreenSpaceShadowMask` | Load(像素) | .r=方向光阴影、.g=角色遮挡(ssmG,进 litMask 与 CP8 门控) |
| t27,space0 | `_PunctualLightShadowTexV2` | SampleCmpLevelZero(LinearMirror) | 点光源 9-tap tent PCF |
| t30-t35,space0 | `_IrradianceVolumeClipmapTexture{A,B}Lod{0,1,3}` | SampleLevel(A=LinearClamp,B=LinearRepeat) | 三层辐照度体 clipmap 环境光(CP1.y<0.5 时) |
| t36,space0 | `_IntegratedLightScattering` | SampleLevel(LinearRepeat) | 体积雾 froxel(_VolumetricFogParams0.z>0 时) |

全局常量(cbuffer):TransformVariables(ViewMatrix/InvViewMatrix/ProjMatrix/NonJittered&Prev VP/CamPos);ShaderVariablesGlobal(`_ScreenSize`、`_BackBufferSize`(外扩纵横比与像素钳制)、`_TaaJitterStrength`、`_ProjectionParams`(z-bin)、`_ExposureWithMiscParams`、`_GlobalMipBias`、`_EnvironmentGlobalParams0.x`(环境缩放)、`_CharacterParams0/1/4/6/7/8/9/11/12/15`、`_IVParam0/1/2`+`_IVDefaultSH*`、雾参数组、`_BinningBufferOffsets`、`_FrameCount`);LightDataBuffer(`DirectionalLightDirection`、`DirectionalLightCustomData1`、`PunctualLightData[2048]`);ShadowData(`_DirectionalShadowParams`、`_PunctualLightWorldToShadow/ShadowParams/2/TexelSize`);LightBinningConstants(分箱);UnityPerDraw(O2W/prev-O2W/蒙皮参数/`Stripped_64.yz` MV 标志)。材质 cbuffer 见 §3。

**CharacterParams 在描边片元中的实际使用**:CP0.z(阴影深色系数)/CP0.y、CP0.w(受光/阴影侧 lightTerm 乘数)、CP1.x(环境峰值映射)/CP1.y(IV vs 平坦环境)/CP1.z(忽略 SS 阴影)/CP1.w(用 CP11 作光向)、CP3(平坦环境色调)、CP4(光色覆盖)、CP6/CP7(环境梯度方向/offset·scale·base)、CP8/CP9/CP15(深度边缘光,§4.5)、CP11.xyz(角色光向)/CP11.w(ramp 偏移)、CP12.x(ramp 偏移权重)/CP12.y(光色覆盖权重)/CP12.z(角色灯层)/CP12.w(展示模式:环境不乘全局缩放、光强不乘 CustomData1.w、跳过雾)。CP2/CP5/CP10/CP13/CP14 在皮肤描边片元中未引用。

### 4.1 通用量(373-415 行)

```
eyeDepth = 1/fragCoord.w; V = normalize(-positionRWS 或正交视向); viewDist
rootToPixelH = normalize(positionWS.xz - (o2w 平移 xz))     // 400-403 行,根到像素水平向
camAxisZ = mul(InvViewMatrix 3x3, (0,0,1))
像素 = uint2(把 _4(positionRWS) 过 NonJitteredVP、去 TAA 抖动、转屏幕 UV 再 ×_ScreenSize.xy)  // 405-415 行
```

### 4.2 GBuffer 法线重投影(416-431 行)——本 pass 的核心机制

```
n2 = _GBufferTexture1.Load(int3(像素, 0)).xy * 2 - 1        // 416 行
octa 解码(n2) → _464(单位世界法线)                            // 417-431 行,八面体:z=1-|x|-|y|,负半球翻转
```
`_4` 是顶点输出的**未外扩** positionRWS,重投影得到的像素即"该描边片元被挤出前的原始表面位置"。因此:
- 描边片元的光照法线 = **角色自身在源像素处的 GBuffer 法线**(由 PreGBuffer pass 写入,见 §7.4);
- 当外扩落到角色轮廓之外的背景上时,Load 到的是**背景像素**的 GBuffer 法线(PreGBuffer 只写角色)——即描边外侧拾取场景法线打光。视觉意图(让描边融进场景光)为推断【未确认】。

### 4.3 描边 albedo 链(392-398 行)

```hlsl
base  = _BaseMap.SampleBias(sampler_LinearClamp, uv0, _GlobalMipBias)      // LinearClamp!
lit   = base.rgb × _BaseColor.rgb × _OutlineColorBrightness                // c6.xyz × c14.z
lit   = lerp(luma(lit), lit, _OutlineColorSaturation)                      // c14.w,>1 外插提饱和
albedo= (_44_Stripped_252 != 0) 逐通道 ? _44_Stripped_256 : lit
shadowAlbedo = albedo × _ShadowColorBrightness; shadowAlbedo = lerp(luma, ·, _ShadowColorSaturation) × 0.96   // 398/577 行
diffuseColor = albedo × ((1-rimI) + (疑_SDFRimColor.rgb×rimI)) × 0.96      // 576 行,rimI 见 4.5
```
(0.96 = 1-0.04,与 ForwardLit `0.96 - metallic×0.96` 同源的漫反射能量系数,描边 metallic≡0。)

### 4.4 环境 / 光照(与 ForwardLit b138 同构,差异点加粗)

- 环境辐照度体三层 clipmap(435-574 行,结构与 b138 一致),`_CharacterParams1.y >= 0.5` 时退化为平坦环境 **CP3**(572 行;皮肤 ForwardLit 亦用 CP3)。环境梯度 `sat(dot(N,CP6)+CP7.x)×CP7.y+CP7.z`(595 行,N=GBuffer 法线)作为 lightTerm 的梯度因子,与 b138 第 10 节同构。
- 光方向 `L = lerp(-DirLightDir, CP11.xyz, CP1.w)`,光色 `lerp(CustomData1.rgb, CP4.rgb, CP12.y)`,强度 `× lerp(CustomData1.w, 1, CP12.w)`(585-586 行)。
- 屏幕空间阴影 `_ScreenSpaceShadowMask.Load(像素)`:r=方向光阴影、g=角色自阴影/遮挡(587-589 行)。
- **明暗 ramp(b273 无 ramp 贴图)**:
  ```
  _1058 = smoothstep(-0.5, 0.5, clamp(dot(_464 /*GBuffer法线*/, L) + CP11.w×CP12.x, -1, 1))   // 592 行
  litMask = min(ssm.g, _1058)                                                                 // 594 行
  ```
- 漫反射组合(598-601 行)与 b138 的 `_1647/_1662` 同构:`阴影深色(_963×CP0.z×0.65) 与 diffuseColor 按 litMask/shadowDir 混合,再乘 lightTerm`(602 行),带 `dot/1.2` 灰度钳制与 0.001~1.5 的亮度比 clamp。
- **无**:高光 GGX、`_ShadowLutTex`、`_HighlightMap`、`_DiffRampMap`(catch-all 下)、雨、雪、SDF 次表面 —— 描边是纯漫反射。

### 4.5 边缘光(CP8,615 行)——与 ForwardLit 第 12 节同构

```
rimAxis = normalize(cross(camAxisZ, lerp((CP9.xy,0), view 轴组合, CP15.w)))
color += CP8.xyz × smoothstep(lerp(0.8,0.2,CP9.w), lerp(0.9,0.5,CP9.w), 1-|dot(V,_464)|)
         × CP8.w × min(min(sat(dot(rootToPixelH, rimAxis)+1), 1), ssm.g)
         × (lerp(0.25, diffuseColor, CP9.z) × sat(dot(rimAxis, _464)))
```
与 skin ForwardLit 的差别:门控用的 `1-|N·V|` 里 N 是 **GBuffer 法线**;捕获帧 CP8=0 时整项为 0。

### 4.6 点光源 / VFX 调色 / 雾(617-992 行)

- 点光源 tile(32px)× z-bin 双重位掩码循环,类型 0/1/3/4 与 b138 第 13 节一致,代入 `diffuseColor=_962`、`shadowColor 路径=_963`;类型 0 的环境混入常数是 **0.5**(856 行 `lerp(0.5×k4.x, 1, ...)`)。
- VFX 调色块(922-931 行)与 ForwardLit 完全同构(常量 c3/c4/c8/c9)。
- 曝光 `_ExposureWithMiscParams.y`、大气/指数/体积雾(934-992 行)与 b138 同构。**输出 alpha 恒 1**(933 行;皮肤 catch-all 无 _OutlineTransparent 分支)。
- SV_Target1 = 运动矢量编码(579-584 行):`mv` 经 `sqrt(sqrt(|mv×0.5|))·sign×0.5+0.5`;**w = 0.7(当 `1-max(Stripped_64.y, Stripped_64.z) < 0.99`)否则 0.4**(584 行)——ForwardLit b138 恒 0.4,这里出现了 0.7 分支。

## 5. 与 _OUTLINE_MASK(b283)、DITHER(b311)、_DIFF_RAMP_ON(b274)的差异

| 变体 | 关键字增量(shader 行) | 顶点差异 | 片元差异 |
|---|---|---|---|
| b274 | +`_DIFF_RAMP_ON`(789-790) | 无(fc 全等) | 新增 1D ramp 贴图(调试名 `_BumpMap`,t1,space1;此名跨变体漂移、工具命名可信度低,按用法即 `_DiffRampMap`):`SampleLevel(LinearRepeat, (clamp(dot(GBufferN,L)+CP11.w×CP12.x,-1,1)×0.5+0.5, 0.5), 0)`,用 ramp **.w 取代硬 smoothstep(-0.5,0.5)** 作明暗;并用 ramp.rgb 经 chroma(=max3-min3)加权染色 `×((1-chroma)+ramp.rgb×chroma)`(f274:593-604 行)——与 ForwardLit 的 rampTinted(_1653)同构。b273 里同一位置也有该染色式,但因输入是标量、chroma≡0 而退化为 ×1;`_BaseMap` 挪到 t2 |
| b283 | +`_OUTLINE_MASK`(807-808) | 顶点采样调试名 **`_SDFMask`**(t0,space1,LinearClamp,变换后 uv0;**b284 同样读 `_SDFMask`,命名跨变体一致,可信**):**R 通道乘外扩向量**(v283:463 行 `…× _533.x`)、**G 通道乘深度偏移**(449 行 `_538 = c14.y × mask.g` → 469/477 行);cbuffer 从 b0 挪到 b1 | "albedo"采样槽从 `_BaseMap`(t1)换成 `_DiffRampMap`(t2),下游公式不变 |
| b311 | +`DITHER`(863-864) | 无(fc 全等) | 无(fc 全等)——描边 pass 中 DITHER 无操作 |

要点与存疑:
1. **掩码系列的片元贴图命名不稳定**:b283 片元 t2 恢复名 `_DiffRampMap`,而 +`_DIFF_RAMP_ON` 的 b284 片元却是 t2=`_EmissionMap`、t3=`_DiffRampMap`——同一逻辑槽位的恢复名随变体漂移,工具侧命名不可单独采信。稳定的只有顶点侧 `_SDFMask`(b283/b284 一致)。
2. **`_SDFMask` vs 属性表 `_OutlineMask`**：两份 dump 中该槽恢复名一致，只证明文本标识符/使用方式一致，不证明真实材质绑定就是 SDFMask。确定项仅为该采样的 R 乘宽度、G 乘深度偏移；纹理资产/属性映射必须依赖反射与实际绑定，不能以“恢复名跨变体稳定”跳过闭环。
3. **运行时变体判定**:捕获帧脸材质 Pass0 关键字含 `_DIFF_RAMP_ON`(b138 文件头),而 `_DIFF_RAMP_ON` 同样是 Pass1 的 multi_compile_local 关键字(778 行),材质关键字跨 pass 共享 → 实际运行的描边变体应为 b274(ramp 版)而非 b273【推断】。

## 6. 未能解析的点

1. ~~`_OutlineColorBrightness/_OutlineColorSaturation` 的归属~~ **已解决**(复核):受光侧 = (c14.z, c14.w),阴影侧 = (c4.z=`_ShadowColorBrightness`, c4.w=`_ShadowColorSaturation`,b138 cbuffer 具名)。
2. c12.x(疑 `_SkinRimOffScale`)、c13.xyz(疑 `_SDFRimColor.rgb`):共享前缀借名,语义吻合但 Pass1 cbuffer 是独立结构【未确认】。
3. c6.w(`_BaseColor.a`)在皮肤描边未使用、布料/头发作 alpha 强度;c15.w/c16(覆盖使能/覆盖色)无 UI 属性,应由渲染脚本按部件/角色设置【未确认】。
4. GBuffer1 的具体内容(是否含材质 ID、是否就是 PreGBuffer 的某个 MRT):八面体解码与 eye PreGBuffer 的编码完全互逆(§7.4),对应关系是强推断,帧内绑定未验证【未确认】。
5. `_ScreenSpaceShadowMask.g`(ssmG)在 594/615 行参与 litMask 与边缘光门控,其与 `.r` 的生成管线(角色自阴影 atlas resolve)未在本次文件范围内。
6. 运行时变体(b273 vs b274)无捕获常量验证。
7. `_OUTLINE_MASK` 的 `_SDFMask` 采样与 `_OutlineMask` 属性的关系(§5.2)【未确认】。

## 7. 其他部件 CharacterOutline 与 skin 版的差异(只写差异)

### 7.1 characternpr(布料)b1088(catch-all)

- **材质 cbuffer 布局不同**:亮度=c12.z(200)、饱和度=c12.w(204)、覆盖使能=c13.w(220)、覆盖色=c14(224)(f1088:388-392 行)。共享前缀名仍成立:c6=`_BaseColor`、c4.z/w=`_ShadowColorBrightness/_ShadowColorSaturation`(用法与 skin 逐字一致);albedo 槽 t1 恢复名为匿名 `_46`(按采样方式即 BaseMap 槽)。跨部件不能复用 skin 的 c14+ 偏移。
- **BaseMap alpha 参与调光**:`_375 = clamp((BaseMap.a × _BaseColor.a) × 2, 0, 1)`(393 行),最终光项乘 `(1-c1.x) + _375×c1.x`(600 行)——布料可按贴图 alpha 压暗描边。
- **ramp 不同**:硬 smoothstep 换成 `smoothstep(0.25, 1.0, clamp(lerp(NdotL, 逆光项, w) + CP11.w×CP12.x, -1, 1))`(589 行),逆光项 `((-NdotL)(NdotL×0.5-1))+0.5` 的混合权重含 `clamp(-dot(L.xz, camAxisZ.xz),0,1) × smoothstep(0.25,0.75,1-|camAxisZ.y|) × (1-CP12.x)` —— 即 ForwardLit 的"逆光 SDF 抬亮"同构项;另有 `smoothstep(0.25,1.0, dot(N_gbuffer, camAxisZ))` 因子参与受光组合(591/596/598 行)。
- **无 rim 染色**:受光 albedo 直接 `×0.96`(571 行),skin 的 `(1-rimI)+rimColor×rimI` 混合被删。
- 环境平坦色用 **CP2**、光色覆盖用 **CP5**(568/581 行;skin 用 CP3/CP4)。
- 点光类型 0 环境混入常数 **0.25**(skin 0.5)。
- **输出带 alpha**:`out.a = (_44_Stripped_32 == 1) ? _375 : 1`(932 行)——即 `_OutlineTransparent` 语义(c2.x);skin b273 恒 1。

### 7.2 characternpr_hair b306(catch-all)

- 与布料同构:CP2/CP5、smoothstep(0.25,1.0)+逆光项、alpha 门控 `(1-c1.z)+(α×c1.z)`(607 行,α=`_377 = clamp((BaseMap.a × _BaseColor.a) × 2, 0, 1)`,f306:399 行)、alpha 输出分支(940 行);共享前缀名(c6=_BaseColor、c4.z/w)同样成立,albedo 槽 t1 恢复名即 `_BaseMap`。
- **CP8 边缘光门控改为深度差**(622 行):采样 t46(恢复名为匿名 `_25`;按 b138 文档该寄存器即 `_CameraDepthTexture`)于 `screenUV + 视图空间法线xy×纵横比×CP9.w×0.006` 偏移点,转线性深度减自身深度,`smoothstep(0.10, 0.20, 深度差)` 作门控 —— 头发描边亮边只出现在**与背景有深度差**(即剪影贴着背景)处;skin/布料用的是视角门控 `1-|N·V|`。这是 hair 与 skin 最显著的图形差异。

### 7.3 DepthOnlyOutline(skin/cloth/hair 都有,skin:1030-1118 行)

`LIGHTMODE="DepthOnly"`、`Cull Front`、`Stencil Ref 36 Always Replace`、无 Blend(默认写深度)。即描边几何还会写一份**深度**,供后续深度差类效果(hair 的 CP8 边缘光、屏幕空间处理)使用。工程里如做深度差边缘光,必须补这个 pass。

### 7.4 characternpr_eye:**没有 CharacterOutline pass**

eye 的 pass 列表(eye.shader:88/276/341/567/625):ForwardLit、**PreGBuffer**、RayTracingReflection、ShadowCaster、TextureStreamingFeedback。其第二个 pass(b64,即我最初按编号误判的对象)是 **PreGBuffer**:
- 顶点:八面体法线解包(仅法线,无切线重构)、GPU 蒙皮(权重 TEXCOORD1/索引 TEXCOORD2),**无任何外扩**,输出基线裁剪位置(v_b64:276-393 行)。
- 片元:**5 路 MRT**(f_b64:238-245 行):Target0=0、Target1=运动矢量、Target2=打包对象 ID(`Stripped_80.z` 3×10bit+2bit,279 行)、Target3=八面体编码世界法线(w=0.7,269-272 行)、Target4=`BaseMap × 色调`(273-274 行)。
- 结论:eye 走的是 GBuffer 预通道而不是描边;**PreGBuffer 正是描边片元所采样的 GBuffer 法线的写入者**(八面体编码互逆)。

## 8. 对我们实现的含义(对照 `FractalMiner\Assets\EndfieldShaderPack\EndfieldCharacterLit.shader:1004-1087`)

现状:我们的 Outline pass = Cull Front、ZTest LEqual、ZWrite Off、屏幕像素恒宽外扩(`_OutlineMinWidth..MaxWidth` lerp × mask × 顶点色 r,1061-1070 行)、TEXCOORD7 平滑法线(0..1 打包)、片元纯 unlit(BaseMap×BaseColor→饱和→亮度→可选染色,1075-1085 行)。差异与建议(文字,不动文件):

1. **宽度模型**：依§2.6 的 VP3×3 投影、有符号近似半角、逐轴裁剪空间下限和§2.7深度偏移逐项实现；“视图旋转/固定像素下限”不是等价替代。
2. **深度偏移缺失**:官方有 `_OutlineOffsetZ`(把描边推到角色身后、配合 ZTest Less 消内轮廓闪面);我们的 ZTest LEqual + ZWrite Off 在内轮廓处会闪。建议加等价的 clip.z 偏移。
3. **描边颜色是打光的**：官方使用未外扩位置重投影采样的 GBuffer 法线、环境、方向光 ramp、屏幕空间阴影与点光源（不是 SSR 反射）。此前“复用主体 N·L 而不采 GBuffer”的最小改法仅为近似实现，不符合官方结构基线；正式路线需要先补全对应 PreGBuffer 输入/编码/绑定，再移植消费链。插值法线还参与点光 receiver bias（F402/F786），不能把它与 GBuffer 打光法线合并。
4. **平滑法线数据格式**:官方网格给 2 通道半球编码(顶点 TEXCOORD0 专用槽),我们的 TEXCOORD7 是 0..1 两通道+阈值判空(1045-1056 行)。若后续做 GPU 蒙皮,注意官方平滑法线是随骨骼变换的 TBN(顶点级),我们是 draw 时 TBN。
5. **_OUTLINE_MASK 语义**:官方掩码版是"R 乘宽度、G 乘深度偏移"(且采样源疑似 SDFMask 而非 _OutlineMask,§5.1);我们只用 R 乘宽度(1039 行)。如需对齐,把掩码 G 也接到深度偏移上。
6. **运动矢量缺失**:官方描边 pass 写 SV_Target1(0.4/0.7 编码),我们无 MV 输出,TAA 下描边会拖影。若开 TAA 需要 MV。
7. **可补充项**:DepthOnlyOutline(写深度,官方 hair 深度差边缘光的前置)、`_OutlineTransparent`(布料版 alpha 语义)、描边 DITHER 无操作(无需实现)。
8. eye 部件不需要描边 pass(官方就没有);若我们给眼睛也套了 Outline,应改为不启用。

---
*生成说明:仅静态阅读 SPIR-V-Cross 反编译 HLSL 与 .shader 文本,未运行游戏/未截帧/未动工程。所有行号指 `FractalMiner\_dump_1.5.3\AllShader_1.5.3\Assets\packages\com.hg.render-pipelines\runtime\shaders\materials\characternpr\` 下相应文件。*
