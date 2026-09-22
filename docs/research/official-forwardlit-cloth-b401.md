# 官方 CharacterNPR(布料/身体) ForwardLit 片元着色器还原(变体 b401)

来源:`_dump_1.5.3/.../characternpr/characternpr/Sub0_Pass0_Fragment_b401.hlsl`(1499 行,SPIR-V-Cross 输出),
配套顶点 `Sub0_Pass0_Vertex_b401.hlsl`(同一 keyword 行,输出结构 TEXCOORD0..8 与片元输入完全一致),
属性/关键字来自 `characternpr.shader`(Pass "ForwardLit",`#pragma target 5.0`,dxc)。
下文中所有数字、swizzle、clamp、pow 指数均按原码保留;`mad`/位运算已改写为普通算式。
本变体 **无** `_SpecRampMap`/`_DiffRampMap`/`_LineMap` 采样(无 `_SPEC_RAMP_ON`/`_DIFF_RAMP_ON`/`_SPECULAR_LINE`),
漫反射 ramp 是**解析平滑阶跃**而非贴图驱动;**无** 视差/流动分支(`_PARALLAX_MAP` 未开,见第 1 节)。

## 1. 变体识别

`characternpr.shader:284-315` 的 `multi_compile_local` 全集里,本变体(vertices/fragment 头注释一致)命中:

```
ON : SRP_INSTANCING_ON  HG_ENABLE_PER_OBJECT_MV  HG_ENABLE_SCREEN_SPACE_SHADOW_MASK
     _NORMALMAP  _METALLICSPECGLOSSMAP  _CLEARCOAT
OFF: _EMISSION  _ALPHATEST_ON  _ALPHABLEND_ON  _REALISTIC_LIGHTING  _SPEC_RAMP_ON
     _ANISOTROPY_SPECULAR_ON  BAKED_SKINNING_ANIMATION_TEXTURE  _SILK_STOCKINGS  _STYLIZED_FRESNEL
     _CHARACTER_EROSION  _CHARACTER_FUR  _CHARACTER_FUR_DYE  _UV2_COLOR  _CHARACTER_VFX_SPECIAL
     _PUPPET  _PUPPET_PROCEDURAL_DCURVE  _MATCAP_ENV_REFLECTION_ON  _ENEMY_HIT_FLASH  DITHER_SPHERE
     _SHADOW_LUT_TEX  _PLANAR_REFLECTION  VFX_CHARACTER_DISSOLVE  DITHER  _CUSTOMIZE_AVATAR
     _PARALLAX_MAP  _DIFF_RAMP_ON
```

后果(与 hair b125 的关键差异):

| 项 | hair b125 | 本变体 b401(布料/身体) |
|---|---|---|
| ramp 来源 | `_DiffRampMap`+`_SpecRampMap` 贴图 | **解析式**:smoothstep 包裹 + 环境梯度,无 ramp 贴图 |
| 高光 | 各向异性发丝高光 | **GGX 解析高光** + 紧凑式环境 BRDF(Stylized Fresnel)加权立方体反射 |
| ClearCoat | 关 | **开**(`_CLEARCOAT`,逐像素由 `_ClearCoatMask` 门控) |
| 视差/流动 | 关 | **关**(`_PARALLAX_MAP` 未开 → 视差代码已编译剔除;属于 b1005/b1011 相邻变体) |
| 屏幕空间深度边缘光 | 有(`_CameraDepthTexture` t46) | **无**——本变体不声明 `_CameraDepthTexture`,rim 仅为 NdotV Fresnel 边,且本帧 CP8=0、CP12.x=1 使其为 0 |
| 法线贴图 wrap | LinearRepeat | **LinearClamp**(`sampler_LinearClamp` = s4) |
| 金属/光滑来源 | `_MetallicGlossMap`(4 通道 mask) | 同左(`_METALLICSPECGLOSSMAP` 开) |

阴影完全来自 `_ScreenSpaceShadowMask`(`.r` 方向光阴影,`.g` 角色遮挡/自阴影),无任何 CSM / `_CharacterWorldToShadow` 采样(本变体无 `_SHADOW_LUT_TEX`、无角色投影矩阵读取)。
`_Smoothness/_Specular/_Metallic` 虽在 cbuffer 里,但 `_METALLICSPECGLOSSMAP` 开时函数体只从 `_MetallicGlossMap` 读,这三个标量未被读取。

### 纹理寄存器 -> 名称 -> 采样方式 -> 必然对应的贴图(body 捕获 event 786)

| 寄存器 | HLSL 名 | 采样表达式 | 判据 | body 对应绑定 / 捕获 |
|---|---|---|---|---|
| t4,space1 | `_BaseMap` | `SampleBias(LinearClamp, uv0, _GlobalMipBias)`,rgb*`_BaseColor` | 唯一乘 BaseColor 的 sRGB 图 | set1 b4 = RId 57032,512² BC7_SRGB |
| t3,space1 | `_BumpMap` | `SampleBias(LinearClamp, uv0)`,`a*=r` 后 `n.xy=(A*R,G)*2-1`(BC5 法线:实际 A=1,等价于 RG 解包) | 法线解包 | set1 b3 = RId 38218,512² BC5_UNORM |
| t1,space1 | `_MetallicGlossMap` | `SampleBias(LinearClamp, uv0)`,x=metallic, y=gloss 遮罩, z=AO/阴影遮罩, w=smoothness(取 `1-w`) | 4 通道 PBR mask | set1 b1 = RId 30336,1024×32 BC7_SRGB |
| t2,space1 | `_ClearCoatMask` | `SampleBias(LinearClamp, uv0)`,`.x`=清漆强度 | 256×1 单/多通道 | set1 b2 = RId 8869,256×1 R8G8B8A8_UNORM |
| t45,space0 | `_CharMaxCubemap` | `SampleLevel(LinearRepeat, reflect(-V,N), LOD)` | 角色"最大立方体"环境反射 | 全局绑定(同 hair 帧 set0) |
| t44,space0 | `_CharacterRainEffectTex` | 仅雨分支 `SampleBias(LinearClamp)` | 三平面雨涟漪 | 本帧天气掩码≈0 不采样 |
| t41,space0 | `_CharacterRainStreakTex` | 仅雨分支 | 雨痕 | 同上 |
| t39,space0 | `_CharacterSnowEffectTex` | 仅雪分支 `SampleBias(LinearClamp)` | 三平面雪 | 同上 |

Set0 全局纹理(与 hair 同族,本帧 event 875 捕获):`_ScreenSpaceShadowMask`(t22,Load 像素)、`_CameraDepthTexture`(t46,**本变体未声明/未采样**)、`_PunctualLightShadowTexV2`(t27,仅点光源 PCF)、`_IrradianceVolumeClipmapTexture{A,B}Lod{0,1,3}`(t30-t35,仅 `CP1.y<0.5` 时)、`_IntegratedLightScattering`(t36,体积雾,仅 `_VolumetricFogParams0.z>0`)、`_LightCookie`(t29)。

## 2. 输入插值器

顶点着色器输出(`_13.._20`,`_22`)-> 片元输入(`_3.._10`,`_12`);本变体比 hair 少一个 TEXCOORD(无 TEXCOORD9):

| 语义 | 片元名 | 内容(由顶点 b401 推得) |
|---|---|---|
| TEXCOORD0 float2 | `uv0` | 顶点 slot1(float2)`* _BaseMap_ST.xy + _BaseMap_ST.zw` |
| TEXCOORD1 float3 | `positionRWS` | 世界坐标 − `_WorldSpaceCameraPos_Internal`(camera-relative) |
| TEXCOORD2 float3 | `normalWS` | 归一化世界法线(顶点里支持 10:10:10 八面体压缩法线) |
| TEXCOORD3 float4 | `tangentWS` | xyz 归一化世界切线,w = 副切线符号(±1) |
| TEXCOORD4 float3 | `clipCur` | 当前帧非抖动裁剪坐标 `.xyw`(运动矢量) |
| TEXCOORD5 float3 | `clipPrev` | 上一帧裁剪坐标 `.xyw` |
| TEXCOORD6 float3 | `restNormalOS` | 物体空间法线(GPU 蒙皮时取第二套法线流),仅雨/雪三平面用 |
| TEXCOORD7 float3 | `restPosOS` | 顶点 TEXCOORD1 原样透传(绑定姿态/静止坐标),仅雨/雪三平面 UV 用 |
| TEXCOORD8 uint (nointerp) | `instanceID` | 索引 `_SRP_UnityPerDraw_UnityPerDrawArray[256]` |
| SV_Position | `fragCoord` | `.xy` 像素坐标(阴影掩码 Load、光源分箱);`1/w` 转回线性视深 `eyeDepth` |
| SV_IsFrontFace | `isFront` | 背面法线翻转、雪只在正面 |

**顶点色未被片元使用**(顶点 COLOR0 槽位实际承载切线)。没有 uv1。

## 3. 片元着色器整洁重构

```hlsl
// ===== 0. 通用量 =====
float  eyeDepth  = 1.0 / fragCoord.w;                       // _426 = 线性视深
float3 viewVec   = lerp(-positionRWS, ViewMatrix[2].xyz, _unity_OrthoParams.w);
float  viewDist  = length(viewVec);                         // _446 (用 rsqrt(max(dot,1e-8)) 实现)
float3 V         = viewVec / viewDist;                     // _445
bool   skinned   = (asuint(PerDraw.Stripped_64.w) & 16u) != 0;
float4 row0,row2;   // objectToWorld 第0/2行:蒙皮时从 _VertexSkinMatrices[Stripped_80.x + {0,2}] 读,否则 PerDraw.Stripped_0[0]/[2]
float3x3 M_o2w   = float3x3(row0.xyz, PerDraw.Stripped_0[1].xyz, row2.xyz);
float3 positionWS = positionRWS + _WorldSpaceCameraPos_Internal.xyz;     // _529
float3 rootToPixelH = normalize(float3(positionWS.x - row0.w, 6.103515625e-05, positionWS.z - row2.w)); // 角色根到像素的水平方向
float3 camAxisZ  = float3(InvViewMatrix[0].z, InvViewMatrix[1].z, InvViewMatrix[2].z); // 相机 +Z(指向观察者) _569
float2 screenUV  = fragCoord.xy * _ScreenSize.zw;
int2   pixel     = int2(fragCoord.xy);                      // _559
const float3 LUM = float3(0.2126729, 0.7151522, 0.0721750);

// ===== 1. 反照率 / PBR 金属-光滑 / 阴影色 =====
float4 baseMap = _BaseMap.SampleBias(sampler_LinearClamp, uv0, _GlobalMipBias);
float3 albedo  = baseMap.rgb * _BaseColor.rgb;             // _479
float  alpha   = baseMap.w   * _BaseColor.w;               // _492
float4 mg      = _MetallicGlossMap.SampleBias(sampler_LinearClamp, uv0, _GlobalMipBias); // _483
float  metallic  = mg.x;        // _484  (body 捕获 = 0)
float  glossMask= mg.y;         // _483.y (清漆/高光遮罩)
float  shadowMask=mg.z;         // _486  (AO / 自阴影遮罩)
float  sm01     = 1.0 - mg.w;   // _488  = 1 - smoothness
float3 sc       = albedo * _ShadowColorBrightness;         // _497
float3 shadowColor = lerp(dot(sc, LUM).xxx, sc, _ShadowColorSaturation); // _501 (body: _ShadowColorBrightness=0 -> 全黑)

// ===== 2. 法线(本变体 diffuse/specular 共用同一法线)=====
float4 nm = _BumpMap.SampleBias(sampler_LinearClamp, uv0, _GlobalMipBias);  // _505
nm.a *= nm.r;                       // BC5 下 A=1,等价于 RG 解包
float2 nTSxy = (nm.aw * 2.0 - 1.0); // _514 = (A*R*2-1, G*2-1)
float3 nTS = float3(nTSxy, sqrt(max(1e-16, 1.0 - clamp(dot(nTSxy, nTSxy), 0, 1)))); // _515
nTS.xy *= _BumpScale;               // _524
float3 T = tangentWS.xyz, B = cross(normalWS, tangentWS.xyz) * tangentWS.w, Nv0 = normalWS;
float3 nWS = nTS.x * T + nTS.y * B + nTS.z * Nv0;          // _546
float  faceSign = isFront ? 1.0 : (-1.0 + 2.0 * _BackFaceNormalFlip);
float3 N  = normalize(nWS) * faceSign;        // 贴图法线 _556
float3 Nv = normalize(normalWS) * faceSign;   // 顶点法线 _557

// ===== 3. 天气掩码(雨/水位/雪),来自 _CharacterParams10 或 per-object =====
uint  wmask   = asuint(_CharacterParams10.x > 0.5 ? _CharacterParams10.y : PerDraw.Stripped_208.x); // CP10.x=0 -> per-object
float4 wm     = float4(wmask & 255, (wmask >> 8) & 255, (wmask >> 16) & 255, (wmask >> 24) & 255) / 255.0; // x=雨湿,y=水位使能,z=常湿,w=雪
float rainWet  = wm.x;                 // _592
float snowW    = wm.w;                 // _595
float waterLine = lerp(PerDraw.Stripped_208.y, _CharacterParams10.w, _CharacterParams10.x); // CP10.x=0 -> per-object.y
float wetWater  = max(wm.z, smoothstep(-0.2, 0.15, waterLine - positionWS.y) * wm.y);       // _604
float wetness   = max(wm.z, wetWater);  // _605
float ambientScale = lerp(_EnvironmentGlobalParams0.x, 1.0, _CharacterParams12.w) * _ExposureWithMiscParams.x; // _614 = 0.2877*1

// ===== 4. 环境光:辐照度体 clipmap + _IVDefaultSH 回退;本帧 CP1.y=1 走平坦分支 =====
float4 shDominant; float3 ambientRGB, ambientTint; float ambientPeak;
if (_CharacterParams1.y < 0.5) {
    // 三层 clipmap(同 hair 文档结构,半径 464/29/116,斜率 1/32 / 1/2 / 1/8,
    //   LOD3 仅当 fade1>0;权重 w0=1-fade0,w1=fade0*(1-fade1),w3=fade1*(1-fadeOuter);
    //   A 纹理 LinearClamp 取 L0 幅值,B 纹理 LinearRepeat 取 (R/G/B) 通道 L1 方向 *4-2;
    //   shC = accC + IVDefaultSH*lerp 系数)。本帧不执行。
    ambientRGB = max(float3(dot(shR, float4(N,1)), dot(shG, float4(N,1)), dot(shB, float4(N,1))), 0) * ambientScale;
    // ... (HSV 色调化同 hair)
    ambientTint = HSVtoRGB(...); shDominant = float4(dir,1);
} else {                                   // 捕获帧走这里(CP1.y = 1)
    shDominant = 0; ambientRGB = 1; ambientTint = _CharacterParams2.rgb; ambientPeak = ambientScale; // _1108/1109/1110/1111
}

// ===== 5. ClearCoat 参数(ClearCoat 开关开)=====
float  ccRough0 = 1.0 - _ClearCoatSmoothness;          // _1129 = 0.2
float  ccRough0sq = ccRough0 * ccRough0;               // _1130 = 0.04
float  ccRough = max(ccRough0sq, 0.0078125);           // _1131 = 0.04
float4 ccMask = _ClearCoatMask.SampleBias(sampler_LinearClamp, uv0, _GlobalMipBias); // _1135
float  ccMaskV = ccMask.x;                             // _1136 逐像素清漆强度
float3 ccF0    = _ClearCoatColor.xyz * lerp(0.04, 1.0, _ClearCoatMetallic);   // _1143 = ClearCoatColor*0.04 (Metallic=0)
float3 Ncc     = lerp(Nv, N, _ClearCoatNormalMode);   // _1147 (Mode=0 -> 顶点法线 Nv)

// ===== 6. 雨滴(程序化涟漪)/雪(三平面)分支 =====
// [branch] if (clamp(rainWet + wetness,0,1) - _DisableRainEffectOnMaterial > 0.01) { ... 约 400 行 hash 涟漪 + 雨痕 ...
//   -> 输出 _1855(扰动法线),_1856(雨强度),_1857(雨 roughness),_1858(雨高光 boost),_1859(=sm01),_1860(=shadowColor),_1861(=albedo)
// } else { _1855=N; _1856=0; _1857=0.01; _1858=0; _1859=sm01; _1860=shadowColor; _1861=albedo; }
// [branch] if (snowW - _DisableRainEffectOnMaterial > 0.01) { ... 三平面雪覆盖 + 法线扰动 ...
//   -> _1991(雪法线),_1992(雪 roughness),_1993(雪阴影色),_1994(雪反照率),_1995(雪 metallic)
// } else { _1991=_1855; _1992=_1859; _1993=_1860; _1994=_1861; _1995=_484; }
// 本帧天气掩码≈0 -> 两分支均跳过,_1855=N,_1991=N,_1992=sm01,_1993=shadowColor(=0),_1994=albedo,_1995=metallic

// ===== 7. PBR 组合(金属-光滑路径)=====
float3 Nlit    = _1991;                       // 最终光照法线
float  roughSq = max(_1992 * _1992, 0.0078125); // _2004 = (1-smoothness)^2
float3 diffuseColor = _1994 * (0.96 - _1995 * 0.96);          // _1998 = albedo*0.96 (metallic=0)
float3 specColor    = lerp(0.04 * glossMask, _1994, _1995);    // _2001 = 0.04*glossMask (metallic=0)
float3 shadowDiff   = _1993 * (0.96 - _1995 * 0.96);          // _2002 (shadowColor=0 -> 0)

// ===== 8. 运动矢量 (SV_Target1) =====
float2 mv = clipCur.xy / max(clipCur.z, 1e-8) - clipPrev.xy / max(clipPrev.z, 1e-8);
mv.y = -mv.y;
float2 mvEnc = sqrt(sqrt(abs(mv * 0.5))) * sign(mv) * 0.5 + 0.5;
float4 target1 = float4(mvEnc, 1.0, (_1858 > 0.1 ? 0.7 : 0.4));   // _2033 (本帧雨=0 -> 0.4)

// ===== 9. 光方向 / 光颜色 / 阴影 =====
float3 L  = lerp(-DirectionalLightDirection.xyz, _CharacterParams11.xyz, _CharacterParams1.w);   // CP1.w=1 -> L = CP11.xyz
float3 Lh = normalize(float3(L.x, 6.103515625e-05, L.z));
float3 lightColor  = lerp(DirectionalLightCustomData1.rgb, _CharacterParams5.rgb, _CharacterParams12.y); // CP12.y=1 -> CP5=(1,1,1)
float3 lightColorI = lightColor * lerp(DirectionalLightCustomData1.w, 1.0, _CharacterParams12.w);         // CP12.w=0 -> *1.624
float4 ssm = _ScreenSpaceShadowMask.Load(int3(pixel, 0));
float  ssmG = ssm.g;                                                        // .g 角色遮挡/自阴影
float  shadowDir = lerp(lerp(1.0, ssm.r, _DirectionalShadowParams.x), 1.0, _CharacterParams1.z);   // CP1.z=0 -> 受 _DirectionalShadowParams.x
float  NdotL = dot(Nlit, L);
float3 shadowDeep  = shadowDiff * _CharacterParams0.z;      // _2089 (shadowDiff=0 -> 0)
float  lumDiffuse  = dot(diffuseColor, LUM);                // _2094
float  backlit = clamp(-dot(Lh.xz, normalize(camAxisZ.xz)), 0.0, 1.0);   // _2107 光在角色背后=1
float  cp12xInv = 1.0 - _CharacterParams12.x;               // _2111 = 0 (CP12.x=1)

// ===== 10. 漫反射 ramp(解析式,无贴图)=====
float wrapT = -NdotL * (NdotL * 0.5 - 1.0) + 0.5;                     // 标准半 Lambert 包裹
float t = smoothstep(0.25, 1.0, clamp(lerp(NdotL, wrapT, backlit * smoothstep(0.25, 0.75, 1.0 - abs(camAxisZ.y)) * cp12xInv)
        + _CharacterParams11.w * _CharacterParams12.x, -1.0, 1.0));    // _2119 = smoothstep(0.25,1, clamp(NdotL - 0.1, -1, 1))
float  rampChroma = t - t;                                            // _2126 = 0 (无 ramp 贴图 -> 无色度差)
float  litView  = smoothstep(0.25, 1.0, dot(Nlit, camAxisZ)) * (shadowMask * ssmG); // _2137
float  litMask  = min(min(ssmG, shadowMask), t);                      // _2136
float  occl     = shadowMask * ssmG;                                  // _2129
float  ambientGrad = saturate(dot(N, _CharacterParams6.xyz) + _CharacterParams7.x) * _CharacterParams7.y + _CharacterParams7.z; // _2141
float3 ambient = ambientGrad * lerp(ambientTint, 1.0, _CharacterParams1.y * litMask);   // CP1.y=1 -> 受 litMask 推向 1

// ===== 11. 光能量项(同 hair 框架)=====
float3 lightTerm = lerp(
    ambient * lerp(min(lerp(0.65, 1.0, ambientPeak), 1.5), clamp(ambientPeak, 1.25, 1.75), _CharacterParams1.x) * _CharacterParams0.w,
    (lerp(dot(lightColorI, LUM).xxx, lightColorI, litMask)
       + ambient * clamp(ambientPeak, 0.0, 1.5) * ((1.0 - _CharacterParams12.y) + lightColor * _CharacterParams12.y)) * _CharacterParams0.y,
    shadowDir);                                                                                // _2167
float3 baseSel = lerp(lerp(lerp(dot(shadowDeep, LUM).xxx, shadowDeep, 1.2), shadowDeep, saturate(occl * litView + t)), diffuseColor, litMask); // _2168
float3 rampTinted = baseSel * ((1.0 - rampChroma) + baseSel * rampChroma);    // _2174 = baseSel (chroma=0)
float3 diffuseTerm = lerp(lerp(shadowDeep, lerp(lumDiffuse.xxx, diffuseColor, 1.2), litView),
    rampTinted * clamp(dot(baseSel, LUM) / max(dot(rampTinted, LUM), 0.001), 0.0, 1.5), shadowDir); // _2183
float  litBlend  = lerp(litView, litMask, shadowDir);                          // _2189
float  specLightMul = lerp(_CharacterParams0.z, 1.0, litBlend);                // _2192

// ===== 12. 方向光 GGX 高光(基础层)=====
float3 pseudoL = float3(camAxisZ.x, lerp(0.5, L.y, shadowDir), camAxisZ.z);   // _2200
float3 H = normalize((L * shadowDir) + (normalize(pseudoL) * 2.0) + (V * (2.0 + shadowDir))); // _2211 (GGX 半程近似)
float  NdotV = clamp(dot(Nlit, V), 0.0, 1.0);                                  // _2213
float  NdotH = dot(Nlit, H);                                                   // _2214
float  a4 = roughSq * roughSq;                                                 // _2215
float  denom = ((NdotH * a4) - NdotH) * NdotH + 1.0;                           // _2219 = NdotH^2*(a4-1)+1 (GGX D 分母)
float  denom2 = denom * denom;                                                 // _2220
float  ggxD = ((a4 != denom2) ? (a4 / denom2) : 1.0) * (0.5 / ((2.0 * NdotV) + (roughSq * 1.0) + 1e-5)) - 6.103515625e-05; // _2234
float3 baseSpec = specColor * clamp(ggxD, 0.0, 20.0);                          // 方向光基础层 GGX 高光

// ===== 13. ClearCoat 层(逐像素由 ccMaskV 门控)=====
bool   ccOn = ccMaskV > 0.001;                                  // _2235
float3 ccAtten = 1.0;                                           // _2277 基础层被清漆衰减的乘数
float3 ccSpec  = baseSpec;                                       // _2278 最终高光(基础层衰减后 + 清漆层)
if (ccOn) {
    float cNdotH = dot(Ncc, H);                                  // _2240
    float cNdotV = clamp(dot(Ncc, V), 0.0, 1.0);                 // _2242
    float oneMinusVdotH = 1.0 - clamp(dot(V, H), 0.0, 1.0);      // _2243
    float fSchlick = oneMinusVdotH * oneMinusVdotH * oneMinusVdotH;  // _2246 (清漆 Schlick,指数 3 非 5)
    float3 ccFres = ((ccF0 * (1.0 - fSchlick)) + fSchlick.xxx) * ccMaskV; // _2251 = 清漆 Fresnel*mask
    ccAtten = lerp(1.0, 1.0 - ccFres, ccMaskV);                  // _2277 = 1 - 清漆反射率*mask
    float  ccA4 = ccRough * ccRough;                             // _2255
    float  ccDenom = ((cNdotH * ccA4) - cNdotH) * cNdotH + 1.0;  // _2259
    float  ccDenom2 = ccDenom * ccDenom;                        // _2260
    float3 ccGGX = clamp((((ccF0 * (1.0 - (oneMinusVdotH*oneMinusVdotH*oneMinusVdotH*oneMinusVdotH))) + (oneMinusVdotH*oneMinusVdotH*oneMinusVdotH*oneMinusVdotH).xxx) * ccMaskV)
                    * ((ccA4 != ccDenom2) ? (ccA4 / ccDenom2) : 1.0)) * (0.5 / ((2.0 * cNdotV) + (ccRough * ((1.0 + cNdotV) - cNdotV)) + 1e-5)), 0.0, 20.0); // _2278
    // 注:上式 ccGGX 为清漆层 GGX 高光(基色 ccF0,粗糙度 ccRough);最终:
    ccSpec = baseSpec * ((1.0 - ccFres) * (1.0 - ccFres)) + ccGGX;   // _2278 = 基础层*清漆Fresnel^2 + 清漆层
} else {
    ccAtten = 1.0; ccSpec = baseSpec;
}

// ===== 14. 合成基础层 + 高光 =====
float  premul = (1.0 - _AlphaPremultiply) + alpha * _AlphaPremultiply;  // _2288 = 1 (body)
float3 color = ((lightTerm * diffuseTerm) * ccAtten) * premul
             + (ccSpec * (lightTerm * ((litBlend * 0.5 + 0.5) * specLightMul)) * _CharacterParams13.w); // _2290 (CP13.w=1)
//   = diffuse*ccAtten + 清漆高光*lightTerm*((litBlend*0.5+0.5)*specLightMul)

// ===== 15. Stylized Fresnel(紧凑式环境 BRDF,恒开)+ 立方体 IBL =====
float  lum = dot(color, LUM);
float  s = clamp(lum - 0.5, 0.0, 0.5);
color = lerp(lum.xxx, color, 1.0 + s * s);                 // _2493 前段:饱和度提升(同 hair)
float3 rimAxis = lerp(float3(_CharacterParams9.xy, 0.0), ViewMatrix[0].xyz * _CharacterParams9.x + ViewMatrix[1].xyz * _CharacterParams9.y, _CharacterParams15.w); // CP15.w=0 -> 世界轴
float3 rimDir  = normalize(cross(camAxisZ, rimAxis));       // CP9.xy≈(0,-1) -> 屏幕右侧
float  NdotVf = dot(V, Nlit);
float  fresnelRim = 1.0 - abs(NdotVf);                      // _2338
float  LhN = dot(Lh, Nlit);
float  shInv = 1.0 - shadowDir;
// 深度 rim(CP8=0 -> 黑色,贡献为 0):
float3 rim = _CharacterParams8.xyz * smoothstep(lerp(0.8, 0.2, _CharacterParams9.w), lerp(0.9, 0.5, _CharacterParams9.w), fresnelRim) * _CharacterParams8.w
           * min(min(clamp(dot(N, rimDir) + 1.0, 0.0, 1.0), shadowMask), ssmG)
           * (lerp(0.25.xxx, diffuseColor, _CharacterParams9.z) * clamp(dot(rimDir, Nlit), 0.0, 1.0));
// 逆光 Fresnel 边缘光(CP12.x=1 -> cp12xInv=0 -> 整项为 0):
float3 edgeLight = lerp(ambientRGB / max(max(ambientRGB) * 0.5, 1.0), lightColorI, shadowDir)
    * clamp(lerp(dot(shDominant.xyz, Nlit) * shDominant.w, -LhN * (LhN * 0.5 - 1.0) + 0.5, shadowDir), 0.0, 1.0)
    * ((shInv + backlit * shadowDir) * cp12xInv)            // = 0
    * smoothstep(0.6, 0.8, fresnelRim) * min(shadowMask, ssmG)
    * (shInv + smoothstep(0.1, 0.04, lumDiffuse) * shadowDir) * max(0.15.xxx, diffuseColor);
color += rim + edgeLight;                                   // 本帧 rim=edgeLight=0 -> color 不变

// 紧凑式 Stylized Fresnel(解析环境 BRDF,NdotV 的有理多项式):
float  nvv = NdotV * NdotV;                                 // _2400
float  nv3 = nvv * NdotV;                                   // _2401/_2402
float  fresA = dot(mul(float2(1.0, NdotV), float2x2(float2(0.03654630109667778, 9.06319999694824), float2(3.32706999778748, -9.04755973815918))), float2(1.0, nvv))
            / dot(mul(float3(1.0, nvv, nv3), float3x3(float3(1.0, 9.04401016235352, 5.56588983535767), float3(3.59684991836548, -16.3173999786377, 19.7886009216309), float3(-1.36772000789642, 9.22949028015137, -20.2122993469238))), float3(1.0, nvv, nvv * nvv)); // _2414
float  fresB = dot(mul(float2(1.0, NdotV), float2x2(float2(0.990440011024475, 1.29677999019623), float2(-1.28514003753662, -0.755906999111175))), float2(1.0, nvv))
            / dot(mul(float3(1.0, NdotV, nv3), float3x3(float3(1.0, 20.3225002288818, 121.563003540039), float3(2.92337989807129, -27.0301990509033, 626.130004882812), float3(59.4188003540039, 222.591995239258, 316.627014160156))), float3(1.0, nvv, nvv * nvv)); // _2419
float3 envFres = specColor * fresA + fresB.xxx;            // _2422 Fresnel 加权的环境反射率
float  envFresSum = fresA + fresB;                         // _2423
float  envRough = lerp(_1992, _1857, _1856);               // _2399 = 1-smoothness (IBL 模糊度)
float3 cubeRefl = _CharMaxCubemap.SampleLevel(sampler_LinearRepeat, reflect(-V, Nlit),
                    (1.2 * log2(max(envRough, 0.001)) + 5.0).xxx)
                  * (envFres + (specColor * ((1.0 - envFresSum) / envFresSum)) * envFres);  // _2441

// 清漆层立方体反射(若 ccOn):
float3 cubeReflAll = cubeRefl;
if (ccOn) {
    float  cNdotV2 = clamp(dot(Ncc, V), 0.0, 1.0);
    float  cfA = dot(mul(float2(1.0, cNdotV2), float2x2(float2(0.03654630109667778, 9.06319999694824), float2(3.32706999778748, -9.04755973815918))), float2(1.0, cNdotV2*cNdotV2))
              / dot(mul(float3(1.0, cNdotV2*cNdotV2, cNdotV2*cNdotV2*cNdotV2), float3x3(float3(1.0, 9.04401016235352, 5.56588983535767), float3(3.59684991836548, -16.3173999786377, 19.7886009216309), float3(-1.36772000789642, 9.22949028015137, -20.2122993469238))), float3(1.0, cNdotV2*cNdotV2, cNdotV2*cNdotV2*cNdotV2*cNdotV2)); // _2469
    float  cfB = dot(mul(float2(1.0, cNdotV2), float2x2(float2(0.990440011024475, 1.29677999019623), float2(-1.28514003753662, -0.755906999111175))), float2(1.0, cNdotV2*cNdotV2))
              / dot(mul(float3(1.0, cNdotV2, cNdotV2*cNdotV2), float3x3(float3(1.0, 20.3225002288818, 121.563003540039), float3(2.92337989807129, -27.0301990509033, 626.130004882812), float3(59.4188003540039, 222.591995239258, 316.627014160156))), float3(1.0, cNdotV2*cNdotV2, cNdotV2*cNdotV2*cNdotV2)); // _2474
    float3 ccEnvFres = ccF0 * cfA + cfB.xxx;               // _2477
    float  ccEnvSum = cfA + cfB;                           // _2478
    cubeReflAll = cubeRefl + (_CharMaxCubemap.SampleLevel(sampler_LinearRepeat, reflect(-V, Ncc),
                    (1.2 * log2(max(ccRough0, 0.001)) + 5.0).xxx)
                  * (ccEnvFres + (ccF0 * ((1.0 - ccEnvSum) / ccEnvSum)) * ccEnvFres)) * ccMaskV;  // _2487
}
color += cubeReflAll * (clamp(ambientPeak, 0.5, 1.5) * _CharacterParams0.w) * specLightMul * ambientTint; // _2520 IBL 以环境色(CP2)着色

// ===== 16. 点光源(tile 32px × z-bin,_GlobalBinningBuffer)=====
// 与 hair 第 13 节结构完全一致:每光 PunctualLightData[i*8+k];盒形/距离衰减、聚光 cone、管状 LTC、cookie、
//   阴影 3x3 tent PCF(_PunctualLightShadowTexV2);类型 0/1/2/3/4 的 diffuse/spec 合成,清漆层额外用 Ncc 再算一次 GGX。
// 本帧无命中点光源 -> 不改 color。

// ===== 17. VFX 调色、曝光、雾、输出 =====
if (_EnableVFXColorAdjustment > 0.5) { /* 同 hair,本帧关 */ }
float4 outColor = float4(color * _ExposureWithMiscParams.y, (_SurfaceType == 1.0) ? alpha : 1.0); // _3434 (SurfaceType=0 -> a=1)
if (_CharacterParams12.w < 0.5) {   // CP12.w=0 -> 雾开
    // 大气雾 / 指数高度雾 / 体积雾:同 hair 第 14 节结构。本帧雾参数多为 0
    //   (_AtmosphereFogParams3.w=-1 使大气消光 T≈1;_ExponentialFogParams2.w=1、_ExponentialFogParams5.w=1 使雾因子≈1;
    //    _VolumetricFogParams0.z=0 跳过体积雾) -> 实际不掺雾。
}
SV_Target0 = outColor;   SV_Target1 = target1;
```

## 4. `_CharacterParamsN` 用途表(捕获值来自 event 875 全局块,body 复用)

| 分量 | 用法推断 | 捕获值 |
|---|---|---|
| CP0.y | 受光侧 lightTerm 总乘数 | 1 |
| CP0.z | 阴影色深度系数(`shadowDeep = shadowDiff*CP0.z`)以及 specLight 里 `lerp(CP0.z,1,litBlend)` | 0.65 |
| CP0.w | 阴影侧/光照项/IBL 总乘数 | 0.9 |
| CP1.x | 环境峰值映射选择:0 -> `min(lerp(0.65,1,peak),1.5)`,1 -> `clamp(peak,1.25,1.75)` | 0 |
| CP1.y | <0.5 采样辐照度体;>=0.5 用平坦环境(ambientRGB=1,tint=CP2);同时 `lerp(tint,1,CP1.y*litMask)` 权重 | 1 |
| CP1.z | 1 = 忽略屏幕空间方向光阴影 | 0 |
| CP1.w | 1 = 用 CP11.xyz 替代 `-DirectionalLightDirection` 作为光方向 | 1 |
| CP2.xyz | 平坦环境色调(同时作 IBL 着色色) | (0.849,0.896,1.151) |
| CP5.xyz | 光颜色覆盖(权重 CP12.y);本帧因 CP12.y=1 完全取代 CustomData1.rgb | (1,1,1) |
| CP6.xyz | 环境梯度方向(`dot(N, CP6)`) | (0,1,~0) |
| CP7.x/y/z | 环境梯度 offset / scale / base:`sat(d+0.15)*1.5+0.5` ∈ [0.5,2] | 0.15 / 1.5 / 0.5 |
| CP8.xyz / w | 深度边缘光颜色 / 强度;**本帧 xyz=0 -> rim 为 0** | (0,0,0,1) |
| CP9.xy | 边缘光轴(世界或相机空间 xy),`rimDir = normalize(cross(camAxisZ, axis))` | (~0,-1) |
| CP9.z | 边缘光颜色 `lerp(0.25, diffuseColor, CP9.z)` | 0 |
| CP9.w | 边缘光阈值宽度(smoothstep 两端 lerp) | 0.4 |
| CP10.x | >0.5 用全局天气掩码 CP10.y 与水位 CP10.w,否则 per-object `Stripped_208.xy` | 0 |
| CP10.y | 打包 uint8x4 天气掩码 (雨湿, 水位使能, 常湿, 雪) | ~0 (9.1e-41) |
| CP10.z | 雨/雪三平面 UV 缩放 | 2.25 |
| CP10.w | 全局水位高度 | -100 |
| CP11.xyz | 角色专用"指向光源"方向 | (0.176,0.530,0.830) |
| CP11.w | ramp 输入 NdotL 偏移(乘 CP12.x);本帧 = -0.1 | -0.1 |
| CP12.x | 1 = 关闭逆光暗部抬亮与逆光边缘光(`cp12xInv=0`);**本帧 edgeLight=0** | 1 |
| CP12.y | 光颜色覆盖权重(`(1-CP12.y)+lightColor*CP12.y`);本帧=1 -> 光色=CP5 | 1 |
| CP12.z | 点光源"角色灯层"门槛加数 | 1 |
| CP12.w | >=0.5:环境不乘 `_EnvironmentGlobalParams0.x`、光强不乘 CustomData1.w、跳过雾;**本帧=0(雾开、环境乘 0.2877)** | 0 |
| CP13.w | 高光/清漆合成总乘数 | 1 |
| CP15.w | 0 = CP9.xy 为世界轴,1 = 相机 right/up 轴;本帧=0 | 0 |

`_CharacterParams3/4/14` 未被本着色器引用(cbuffer 中被 strip,偏移 1760/1776/1936)。

## 5. 使用到的全局常量与纹理

| 缓冲/寄存器 | 成员 | 用途 |
|---|---|---|
| TransformVariables b12 | `ViewMatrix` | 正交视向、`rimAxis`(行0/1)、`NdotV`;`InvViewMatrix` 列 2 -> camAxisZ;`WorldSpaceCameraPos_Internal`;`PrevCamPosRWS`(顶点) |
| ShaderVariablesGlobal b16 | `_ScreenSize.zw`,`_ScreenParams`,`_ZBufferParams`(本变体未用)、`_ProjectionParams.y`、`_unity_OrthoParams.w`、`_Time.x`(雨/雪)、`_GlobalMipBias`、`_FrameCount`(体积雾抖动) | 见上 |
| 同上 | `_ExposureWithMiscParams.x`(乘 ambientScale)、`.y`(输出前乘 rgb);`.z/.w` 未用 | 捕获 (1,1,1.6,0.1) |
| 同上 | `_EnvironmentGlobalParams0.x` | ambientScale 基值,捕获 0.2877 |
| 同上 | `_IVParam0/1/2`、`_IVDefaultSHAr/g/b` | 辐照度体(捕获帧 CP1.y=1 不执行) |
| 同上 | `_CharacterParams0..15` | 第 4 节 |
| 同上 | `_AtmosphereFogParams0..5`、`_ExponentialFogParams0..5`、`_VolumetricFogParams0..4` | 雾(本帧≈不掺雾) |
| LightDataBuffer b14 | `DirectionalLightDirection.xyz`,`DirectionalLightCustomData1.rgb/w`,`PunctualLightData[2048]` | 角色用 CustomData1=(1,1,1)*1.624;方向光颜色偏移 16/32 未读 |
| ShadowData b15 | `_DirectionalShadowParams.x`(屏幕阴影强度)、`_PunctualLightWorldToShadow/ShadowParams/ShadowParams2/ShadowTexelSize` | 无 CSM、无角色阴影矩阵读取 |
| LightBinningConstants b48 | `NumTilesX`,`NumZBinSlice`,`InvZBinSlice` | 点光源 tile/z-bin |
| LightCookieCB b50 | `_lightCookieData/_lightCookieMatrices` | 点光源 cookie |
| UnityPerDraw (space2) | `Stripped_0`(O2W),`Stripped_64.w` bit4 蒙皮,`Stripped_80.x` 蒙皮矩阵起点,`Stripped_208.xy` per-object 天气掩码/水位 | |
| t4 `_BaseMap`(space1) | 反照率 | LinearClamp + bias |
| t3 `_BumpMap`(space1) | 法线(BC5) | LinearClamp + bias |
| t1 `_MetallicGlossMap`(space1) | metallic/gloss/AO/smoothness | LinearClamp + bias |
| t2 `_ClearCoatMask`(space1) | 清漆强度 | LinearClamp + bias |
| t45 `_CharMaxCubemap`(space0) | 角色环境立方体反射 | LinearRepeat,LOD 由 `(1.2*log2(rough)+5)` |
| t22 `_ScreenSpaceShadowMask` | `.r` 方向光阴影,`.g` 角色遮挡/自阴影 | Load 像素 |
| t27 `_PunctualLightShadowTexV2` | 点光源 PCF | LinearMirrorOnce (cmp) |
| t30-t35 IV clipmap A/B Lod0/1/3 | 环境 SH | A: LinearClamp,B: LinearRepeat |
| t36 `_IntegratedLightScattering` | 体积雾 froxel | LinearMirror |
| t39/44/41 `_CharacterSnow/Rain/RainStreakEffectTex` | 雪/雨三平面 | LinearClamp + bias |
| t29 `_LightCookie` | 点光源 cookie | LinearMirror |
| t51 `_GlobalBinningBuffer`,t18 `_VertexSkinMatrices` | 光源位掩码 / 蒙皮矩阵 | ByteAddressBuffer |

**本变体缺 `_CameraDepthTexture`(t46)**:hair 的屏幕空间深度边缘光在此被编译剔除,边缘光退化为纯 NdotV Fresnel(且本帧 CP8=0、CP12.x=1 使其为 0)。

## 6. 未解析 / 待确认点

1. **视差/流动不在本变体**:任务所述"cloth 走 `_UseParallax=1` + `_ParallaxTex` 流动"对应的是 **b1005/b1011**(cloth_01/02,相邻变体,其关键字含 `_PARALLAX_MAP`)。b401 的 keyword 列表**不含** `_PARALLAX_MAP`,且片元不声明 `_ParallaxTex`,视差代码已编译剔除。如需视差分支,应另译 b1005/b1011 并注明差异(寄存器/采样会多出 `_ParallaxTex` 流动 UV 偏移)。
2. **`_ClearCoatMask` 逐像素值未捕获**:set1 b2 绑定 256×1 R8G8B8A8_UNORM,但捕获未给像素级 mask;清漆层(第 13 节)整体由 `ccMaskV>0.001` 门控。body 材质一般应有非零清漆(服装外涂层),但精确反射强度取决于该贴图。
3. **per-object 天气掩码未知**:CP10.x=0 时取 `PerDraw.Stripped_208.x`;该值未在 event 786 捕获(全局块不含 per-object)。本帧按任务给的"天气掩码≈0"假设雨/雪分支跳过;若 `Stripped_208.x` 低 8 位非零,会打开雨湿分支(改动法线/粗糙度/反照率),但不影响非雨区域主体亮度。
4. **`_DirectionalShadowParams.x` 未捕获**:`shadowDir = lerp(lerp(1, ssm.r, x), 1, CP1.z=0)` 仍依赖它;CP1.z=0 表示方向光屏幕阴影参与。捕获未给该值。
5. **`_CharacterParams3/4/14`(偏移 1760/1776/1936)与本帧无关**:cbuffer 中 strip,函数体不引用,但与 hair 全局块同地址,已在第 4 节排除。
6. **Stylized Fresnel 魔数来源**:第 15 节的 `fresA/fresB` 12 个常量(0.0365463/9.0632/3.32707/-9.04756/9.04401/5.56589/3.59685/-16.3174/19.7886/-1.36772/9.22949/-20.2123 与 0.99044/1.29678/-1.28514/-0.755907/20.3225/121.563/2.92338/-27.0302/626.13/59.4188/222.592/316.627)是引擎的**紧凑式解析环境 BRDF(Stylized Fresnel)**仿射逼近(NdotV 的有理多项式,类似 Karis/Filament 环境 BRDF 紧凑拟合),恒开、用于加权 `_CharMaxCubemap` 反射。注意 `_STYLIZED_FRESNEL` 关键字(额外着色 Fresnel 边,见 event 892 overlay 的 `_StylizedFresnelColor/Pow/Amount`)在 b401 为 OFF,与这里的恒开 IBL Fresnel 是两回事。
7. **雨滴涟漪/雪三平面/点光源 PCF-cookie-LTC 细节**:仅给出结构与输出(同 hair 第 13 节),未逐行还原;捕获帧天气掩码≈0、无点光源命中时它们不改变结果。
8. **`_MetallicGlossMap` 为 BC7_SRGB**:光滑/AO 数据图本应为线性,但捕获显示为 sRGB 编码;采样走 `LinearClamp` 会做 sRGB->线性解码。若原美术以 sRGB 导出该图,则 metallic/gloss/AO 数值会偏高,需与实际贴图确认。
