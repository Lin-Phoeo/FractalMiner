# 官方 CharacterNPR_Skin ForwardLit 片元着色器还原(变体 b138)

来源:`_dump_1.5.3/.../characternpr/characternpr_skin/Sub0_Pass0_Fragment_b138.hlsl`(1279 行,SPIR-V-Cross 输出),
配套顶点 `Sub0_Pass0_Vertex_b138.hlsl`(同一 keyword 行,输出结构 TEXCOORD0..8 与片元输入完全一致),
属性/关键字来自 `characternpr_skin.shader`(Pass "ForwardLit",LightMode `ForwardCharacterOnly`,`#pragma target` 见下,dxc)。
下文中所有数字、swizzle、clamp、pow 指数均按原码保留;`mad`/位运算已改写为普通算式。

本变体是 **皮肤(face)部位** 的专用着色器,与 hair 变体(b125)最大的差异在于:
- 反照率经 linear→sRGB 后查 **_ShadowLutTex** 得到 SSS/厚度阴影色;
- 通过 **_SDFMask / _SDFLightmap** 做"朝向根部的次表面散射法线"与 SDF 光照方向混合;
- 高光来自 **_HighlightMap**(脸颊高光图)与 GGX,而非各向异性发丝高光;
- 雨走 **_CharacterRainFaceDripTex / _CharacterRainFaceDropletTex**(面部雨滴),雪为三平面 **_CharacterSnowEffectTex**;
- 边缘光/脸缘光分别由 `_CharacterParams8`(深度边缘光,本帧=0)与 `_CharacterParams14`(脸缘 SDF,本帧=0)控制,且**不使用 _CameraDepthTexture**(hair 的深度边缘光被替换为 rooted 方向 + sdfMask.w 门控)。

## 1. 变体识别

`characternpr_skin.shader:158-171` 的 `#pragma multi_compile_local` 全部关键字(片元头行 2 给出命中的 ON 集合):

```
ON : HG_ENABLE_PER_OBJECT_MV  HG_ENABLE_SCREEN_SPACE_SHADOW_MASK  SRP_INSTANCING_ON
     _NORMALMAP  _DIFF_RAMP_ON  _EMOTION_MAP  _SDFLIGHTMAP  _SHADOW_LUT_TEX  _HIGHLIGHT_MAP
OFF: _EMISSION  BAKED_SKINNING_ANIMATION_TEXTURE  _CUSTOMIZE_AVATAR  VFX_CHARACTER_DISSOLVE  DITHER
```

后果:只有**一张**法线贴图(`_BumpMap`,`_NormalMap` 解包 `a*=r` 即 Unity RG/AG 法线);无自发光、无溶解、无自定义形象、无抖动;
`_BaseMap` 用 `sampler_LinearClamp`(**不是** LinearRepeat);存在 **_EmotionMap**(表情混合)、**_SDFMask/_SDFLightmap**(SDF 次表面)、
**_ShadowLutTex**(SSS LUT 阴影色)、**_HighlightMap**(脸部高光图)。阴影仍来自 `_ScreenSpaceShadowMask`,无 CSM 采样。

### 纹理寄存器 -> 名称 -> 采样方式 -> 必然对应的贴图(event 860 实际命中)

| 寄存器 | HLSL 名 | 采样表达式 | 判据 | 本皮肤对应贴图 / 捕获 binding |
|---|---|---|---|---|
| t8,space1 | `_BaseMap` | `SampleBias(LinearClamp, uv0, _GlobalMipBias)`,rgb*`_BaseColor` | 唯一乘 BaseColor 的 sRGB 图 | `_D` 1024² BC7_SRGB = **b8** |
| t7,space1 | `_BumpMap` | `SampleBias(LinearClamp, uv0)`,后 `w*=r; n.xy=(w,y)*2-1`(Unity RGorAG 解包) | 法线解包 | `_HN` 1024² BC5_UNORM = **b7** |
| t1,space1 | `_ShadowLutTex` | `SampleLevel(LinearRepeat, lutUV, 0)` 两次插值 | 256x32 / 1024x32 的 SSS LUT,索引 = linearToSRGB(albedo) | `shadow_lut` 1024x32 BC7_SRGB = **b1** |
| t2,space1 | `_SDFMask` | `SampleBias(LinearRepeat, uv0)` | 4 通道:R=rim 掩码,G=SDF 权重混合,B=skin/face 选择,W=脸缘强度 | `sdf_mask` 512² BC7_UNORM = **b2** |
| t3,space1 | `_SDFLightmap` | `SampleLevel(LinearRepeat, flipUV(uv0), 0)` | 2D SDF 光照方向图(RG=方向,B=范围,A=遮罩) | `sdf_lightmap` 1024² R8G8B8A8_UNORM = **b3** |
| t4,space1 | `_HighlightMap` | `SampleBias(LinearClamp, uv0 + mul(V,M_o2w).xy*_HighlightMapVector.xy)` | 无 mip、按视角偏移的脸部高光图 | `highlight` 512² BC7_UNORM = **b4** |
| t5,space1 | `_EmotionMap` | `SampleBias(LinearClamp, emotionTile + 0.5*uv0)` | 表情图,带 tile 偏移与 `_EmotionIndex/_EmotionBlend` 混合 | `emotion` 1024² BC7_SRGB = **b5** |
| t6,space1 | `_DiffRampMap` | `SampleLevel(LinearRepeat, float2(x, 0.5), 0)` | 一维 ramp,v 固定 0.5 | `ramp` 256x1 R8G8B8A8_UNORM = **b6** |

Set0 全局纹理:`_ScreenSpaceShadowMask`(t22,Load 像素),`_PunctualLightShadowTexV2`(t27,仅点光源 PCF),
`_IrradianceVolumeClipmapTexture{A,B}Lod{0,1,3}`(t30-t35,CP1.y=1 时不采样),`_IntegratedLightScattering`(t36,体积雾),
`_CharacterSnowEffectTex`(t39,雪三平面),`_CharacterRainFaceDripTex`(t43),`_CharacterRainFaceDropletTex`(t42),`_LightCookie`(t29)。
**注意:本皮肤变体不声明 `_CameraDepthTexture`(hair 的 t46),故无场景深度边缘光。**

## 2. 输入插值器

顶点着色器输出(`_13.._22`)-> 片元输入(`_3.._12`),由顶点 b138 推得:

| 语义 | 片元名 | 内容 |
|---|---|---|
| TEXCOORD0 float2 | `uv0` | 顶点 slot1(float2)`* _BaseMap_ST.xy + _BaseMap_ST.zw` |
| TEXCOORD1 float3 | `positionRWS` | 世界坐标 − `_WorldSpaceCameraPos_Internal`(camera-relative) |
| TEXCOORD2 float3 | `normalWS` | 归一化世界法线(支持 10:10:10 八面体压缩法线) |
| TEXCOORD3 float4 | `tangentWS` | xyz 归一化世界切线,w = 副切线符号(±1) |
| TEXCOORD4 float3 | `clipCur` | 当前帧非抖动裁剪坐标 `.xyw`(运动矢量) |
| TEXCOORD5 float3 | `clipPrev` | 上一帧裁剪坐标 `.xyw` |
| TEXCOORD6 float3 | `restNormalOS` | 物体空间法线(GPU 蒙皮时取第二套法线流),仅雪三平面用 |
| TEXCOORD7 float4 | `restTangentOS` | 物体空间切线;**雪分支把它当 restPosOS 用**(`_10.xzy` 即 restPosOS 近似) |
| TEXCOORD8 uint (nointerp) | `instanceID` | 索引 `_SRP_UnityPerDraw_UnityPerDrawArray[256]` |
| SV_Position | `fragCoord` | `.xy` 像素坐标(阴影掩码 Load、光源分箱);`1/w` 转回线性视深 `eyeDepth` |
| SV_IsFrontFace | `isFront` | 背面法线翻转、雪只在正面 |

**顶点色未被片元使用**(顶点 COLOR0 槽位承载切线/法线)。没有 uv1。

## 3. 片元着色器整洁重构

```hlsl
// ===== 0. 通用量 =====
float  eyeDepth  = 1.0 / fragCoord.w;                       // _384: 线性视深
float3 viewVec   = lerp(-positionRWS, ViewMatrix[2].xyz, _unity_OrthoParams.w.xxx);
float  viewDist  = length(viewVec);                          // _400,_402,_404 = viewDist
float3 V         = viewVec / viewDist;                      // _403
bool   skinned   = (asuint(PerDraw.Stripped_64.w) & 16u) != 0;
float4 row0,row1,row2;   // objectToWorld 三行:蒙皮时从 _VertexSkinMatrices[Stripped_80.x + {0,1,2}] 读,否则 PerDraw.Stripped_0[0..2]
float3x3 M_o2w   = float3x3(row0.xyz, row1.xyz, row2.xyz);  // 这里 _584
float3 positionWS = positionRWS + _WorldSpaceCameraPos_Internal.xyz;   // _540
float3 rootToPixelH = normalize(positionWS.xz - float2(row0.w, row2.w).xy); // _544.y=6.1e-5 -> _547
float3 camAxisZ  = mul((float3x3)InvViewMatrix, float3(0,0,1)); // _580
float2 screenUV  = fragCoord.xy * _ScreenSize.zw;
int2   pixel     = int2(fragCoord.xy);
const float3 LUM = float3(0.2126729, 0.7151522, 0.0721750);

// ===== 1. 反照率 / SSS 阴影色 =====
float4 baseMap   = _BaseMap.SampleBias(sampler_LinearClamp, uv0, _GlobalMipBias);    // _437 (LinearClamp!)
float  alpha     = baseMap.w;                                                   // _450
float4 emo       = _EmotionMap.SampleBias(sampler_LinearClamp,
                       float2(fmod(_EmotionIndex,2)*0.5, floor(_EmotionIndex*0.5)*0.5) + 0.5*uv0, _GlobalMipBias); // _464
float3 albedo    = lerp(baseMap.xyz * _BaseColor.xyz, emo.xyz, (emo.w * _EmotionBlend).xxx);  // _471
// linear->sRGB 近似(供 LUT 索引):_472=*12.92 小值分支, _476=pow(x,1/2.4)*1.055-0.055 大值分支
float3 sRGBalbedo = linearToSRGB(albedo);                                       // _479 (clamp 0..1)
// LUT 坐标: B 通道 *31 取行, R/G *31 取列,各 1/32 步进 + 半纹素偏移,行间线性插值
float3 _489 = lutCoords(sRGBalbedo);                                           // _483.._489
float3 shadowColor0 = _ShadowLutTex.SampleLevel(sampler_LinearRepeat, _489.xy, 0).xyz;        // _504 前
float3 shadowColor1 = _ShadowLutTex.SampleLevel(sampler_LinearRepeat, _489.xy + float2(0.03125,0), 0).xyz;
float3 shadowColor  = lerp(shadowColor0, shadowColor1, (_483 - floor(_483)).xxx);             // _504

// ===== 2. 法线 =====
float4 sdfMask   = _SDFMask.SampleBias(sampler_LinearRepeat, uv0, _GlobalMipBias);   // _508
float  sdfRimR   = sdfMask.x;   // _510 下方命名沿用:见下
float  sdfW      = sdfMask.y;   // _510 = sdfMask.y (SDF 权重/混合)
float  sdfSkin   = sdfMask.z;   // _511 = sdfMask.z (skin vs face 选择)
float  sdfFace   = sdfMask.w;   // _512 = sdfMask.w (脸缘强度)
float4 nm = _BumpMap.SampleBias(sampler_LinearClamp, uv0, _GlobalMipBias);          // _516
nm.w *= nm.r;                                                                    // _516.w = w*r (RGorAG 解包)
float3 nTS; nTS.xy = (nm.wy * 2.0 - 1.0); nTS.z = max(1e-16, sqrt(1 - saturate(dot(nTS.xy,nTS.xy))));
nTS.xy *= _BumpScale;                                                          // _535
float3 T = tangentWS.xyz, B = cross(normalWS, tangentWS.xyz) * tangentWS.w, Nv0 = normalWS;
float3 nWS = nTS.x*T + nTS.y*B + nTS.z*Nv0;                                    // _557
float  faceSign = isFront ? 1.0 : (-1.0 + 2.0*_BackFaceNormalFlip);
float3 N  = normalize(nWS) * faceSign;                                         // _567 (贴图法线)
float3 Nv = normalize(normalWS) * faceSign;                                    // _568 (顶点法线,仅点光源分支用)
float  Nz = N.z;                                                               // _639

// ===== 3. 天气掩码(雨/水位/雪),来自 _CharacterParams10 或 per-object =====
uint  wmask   = asuint(_CharacterParams10.x > 0.5 ? _CharacterParams10.y : PerDraw.Stripped_208.x);  // _601
float4 wm     = float4(wmask & 255, (wmask>>8)&255, (wmask>>16)&255, (wmask>>24)&255) / 255.0;       // _614 x=雨湿,y=水位使能,z=常湿,w=雪
float waterLine = lerp(PerDraw.Stripped_208.y, _CharacterParams10.w, _CharacterParams10.x);
float wetWater  = max(wm.z, smoothstep(-0.2, 0.15, waterLine - positionWS.y) * wm.y);   // _628
float wetness   = max(wm.x, wetWater);                                                 // _629
float ambientScale = lerp(_EnvironmentGlobalParams0.x, 1.0, _CharacterParams12.w) * _ExposureWithMiscParams.x;  // _637

// ===== 4. 环境光:辐照度体 clipmap + _CharacterParams3 回退(平坦) =====
float3 ambientTint; float ambientPeak;
if (_CharacterParams1.y < 0.5) {
    // 三层 clipmap(结构同 hair,中心/半径/LOD 系数一致:_IVParam0/1/2、_IVDefaultSHA{r,g,b});
    // 捕获帧走 else,此处不执行,仅列出签名:ambientTint=SH(N),ambientPeak=max(SH)
} else {                                   // 捕获帧走这里(CP1.y = 1)
    ambientTint = _CharacterParams3.xyz;    // _1135 = (1.2604, 0.7396, 0.7396)
    ambientPeak = ambientScale;             // _1136
}

// ===== 5. SDF 边缘 / 脸缘(皮肤特有)=====
float _592 = normalize(mul(camAxisZ, M_o2w).xz).y;        // _591,_592:角色-相机水平朝向
float sdfRimMask = sdfMask.x * lerp(clamp(_592 + 0.5, 0, 1), 1.0, sdfW);   // _1155
float rimI = clamp(1.0 - clamp((clamp(dot(N, V), 0, 1) * 0.85 + 0.15, 0, 1))
                       * (sdfRimMask * lerp(_FaceRimOffScale, _SkinRimOffScale, sdfSkin)), 0, 1);   // _1169
float3 diffuseBase = albedo * ((1.0 - rimI).xxx + (_SDFRimColor.xyz * rimI));   // _1177 (脸缘被 SDFRimColor 染)
float  specStrength = lerp(0.0, _Specular, sdfW);                              // _1178

// ===== 6. 雨(面部雨滴/水痕,非发丝涟漪)=====
// if (clamp(wm.x + wetWater, 0,1) - _DisableRainEffectOnMaterial > 0.01):
//   _1191 = Time.x*0.8; drip = _CharacterRainFaceDripTex.SampleBias(LinearClamp, uv0+(0,frac(_1191)))
//   drop = _CharacterRainFaceDropletTex.SampleBias(LinearClamp, uv0)
//   重组法线 _1230(由 drip.xy*2-1)、rim/droplet 强度 _1226/_1227、高光提到 3.0、alpha 与 wetness 调制
//   specStrength = lerp(specStrength, 3.0, clamp((_1226*2+_1227),0,1)*wetness)
//   alpha        = baseAlpha * ((1-_1226) + (lerp((1-_1245)+(0.8*_1245), 0.9, sdfW) * _1226))
//   rainNormal   = normalize(mul(_1230, TBN)) * faceSign ; smooth = lerp(1-_Smoothness, 0.5, wetness)
//   rainAmt      = clamp(clamp(_1226+_1227,0,1),0,1)
// 捕获帧天气≈0 -> else 分支:
float  specStrength2 = specStrength;     // _1264
float  alpha2        = alpha;            // _1265
float3 useN          = N;                // _1266
float  smooth        = 1.0 - _Smoothness; // _1267 = 0.742
float  rainAmt       = 0.0;              // _1268

// ===== 7. 雪(三平面,restPosOS 来自 _10.xzy,restNormalOS 来自 _9.xzy)=====
// if (wm.w - _DisableRainEffectOnMaterial > 0.01):
//   权重 = normalize(pow(abs(restNormalOS)-0.2,3)) 三平面 _CharacterSnowEffectTex
//   coverage = smoothstep(2-_1328, 2.35-_1328, lerp(0,(smoothstep(-1,0,restN.y)+snowTex.z)*0.6, sdfW*_1155)) * (alpha2^2 * isFront)
//   useN = 由 snowTex.rg 扰动的法线;smooth = lerp(smooth,0.9,clamp(coverage*4,0,1))
//   shadowColor = lerp(shadowColor, 0.308, coverage); diffuseBase = lerp(diffuseBase, 0.88, coverage); metallic = lerp(_Metallic,0,coverage)
// 捕获帧天气≈0 -> else 分支:
float3 finalN     = useN;                // _1387 = N
float  smooth2    = smooth;              // _1388
float3 shadowCol2 = shadowColor;         // _1389
float3 diffuseB2  = diffuseBase;         // _1390
float  metallic   = _Metallic;           // _1391 = 0

// ===== 8. 漫反射/高光基础量 =====
float  metalOut     = 0.0;                                  // skin 无金属,metalOut 恒为 0
float3 diffuseColor = diffuseB2 * (0.96 - metallic*0.96);   // _1394 (0.96 系数)
float3 specColor    = lerp(0.04.xxx * specStrength2, diffuseB2, metallic.xxx); // _1397 (金属走 albedo,否则 0.04*高光强度)
float3 shadowDiff   = shadowCol2 * (0.96 - metallic*0.96);  // _1398
float  shininess    = max(smooth2*smooth2, 0.0078125);      // _1400 (smoothness^2, 下限 1/128)

// 运动矢量 (SV_Target1):同 hair,_1427 = (enc.x, enc.y, 1.0, 0.4)
float2 mv = clipCur.xy/max(clipCur.z,1e-8) - clipPrev.xy/max(clipPrev.z,1e-8); mv.y = -mv.y;
float2 mvEnc = sqrt(sqrt(abs(mv*0.5)))*sign(mv)*0.5 + 0.5;
float4 target1 = float4(mvEnc, 1.0, 0.4);

// ===== 9. 光方向 / 光颜色 / 阴影 / SDF 光照 =====
float3 L  = lerp(-DirectionalLightDirection.xyz, _CharacterParams11.xyz, _CharacterParams1.w);   // 捕获:CP1.w=1 -> L = CP11.xyz
float3 lightColor  = lerp(DirectionalLightCustomData1.rgb, _CharacterParams4.rgb, _CharacterParams12.y);   // 捕获:CP4, CP12.y=1
float3 lightColorI = lightColor * lerp(DirectionalLightCustomData1.w, 1.0, _CharacterParams12.w);  // 捕获:(1,1,1)*1.624
float4 ssm = _ScreenSpaceShadowMask.Load(int3(pixel, 0));
float  ssmG = ssm.g;                                                        // 角色自阴影/遮挡
float  shadowDir = lerp(lerp(1.0, ssm.r, _DirectionalShadowParams.x), 1.0, _CharacterParams1.z);   // 捕获:CP1.z=0 -> lerp(1, ssm.r, CP12? 实际=lerp(1,ssm.r,_DirectionalShadowParams.x)
float3 shadowDeep  = shadowDiff * _CharacterParams0.z;      // _1483 (×0.65)
float3 shadowDeep2 = shadowDeep * 0.65;                     // _1484
// SDF 光照方向(物体空间水平光 Lh,按 Lh.x 左右翻转 uv)
float3 Lh = normalize(mul(L, M_o2w)); Lh.y = 6.103515625e-05; Lh = normalize(Lh);   // _1501
float  lhSide = Lh.x > 0 ? 1.0 : 0.0;
float2 sdfUV = float2(lerp(1.0-uv0.x, uv0.x, lhSide), uv0.y);
float4 sdfLM = _SDFLightmap.SampleLevel(sampler_LinearRepeat, sdfUV, 0);          // _1512
float  sdfRange = sdfLM.z * 2.0;
float  sdfAng = lerp(1.0 - sdfRange, sdfRange - 1.0, lhSide);
float3 sdfLDir = normalize(mul(M_o2w, normalize(float3(sdfAng, 6.103515625e-05, 1.0 - abs(sdfAng))))); // _1522
float3 sdfN   = normalize(lerp(sdfLDir, finalN, sdfW));     // _1529 (SDF 方向混合表面法线,权重 sdfW)
float3 sssN   = normalize(lerp(rootToPixelH, normalize(float3(N.x, 6.103515625e-05, Nz)), sdfW)); // _644 (SSS 法线:根方向↔水平法线)
// 背光 SDF 项(_1547.._1549,用于 ramp 输入与脸缘)
float  sdfBack = lerp(Lh.z, (-Lh.z)*((Lh.z*0.5)-1)+0.5,
                      (clamp(-dot(normalize(float3(L.x,6.1e-5,L.z)).xz), normalize(camAxisZ.xz)),0,1)
                       * clamp(-Lh.z,0,1) * (1.0 - _CharacterParams12.x)) * 0.5;  // _1547
float  sdfBackClamped = clamp(0.5 - sdfBack, 0.001, 0.999);   // _1549
float  sdfGrad = (sdfLM.x + sdfLM.y) * 0.5;                   // _1555
float  faceRimCenter = clamp(0.5 - _CharacterParams15.z*0.5, 0.001, 0.999);  // _1568 (CP15.z=-1 -> 0.999)
// 漫反射 ramp
float4 ramp = _DiffRampMap.SampleLevel(sampler_LinearRepeat,
    float2((lerp(lerp(-1.0, 1.0, abs(-smoothstep(max(sdfBackClamped-(1-sdfBackClamped),0),
                    min(sdfBackClamped+sdfBackClamped,1), sdfGrad)) - (sdfBack*ceil(sdfBack)))),
                clamp(dot(finalN, L) + (_CharacterParams11.w * _CharacterParams12.x), -1.0, 1.0), sdfW) * 0.5) + 0.5, 0.5), 0);  // _1589
float  rampA    = ramp.w;                                     // _1590
float  rampChroma = max3(ramp.rgb) - min3(ramp.rgb);          // _1599
float  rimSel   = max(sdfW, sdfSkin * smoothstep(0.75, 0.25, _592));   // _1602
float  occ      = (1.0 - rimSel) + (ssmG * rimSel);           // _1605
float  noSdf    = 1.0 - sdfW;                                  // _1606
float  litMask  = min(min(occ, alpha2), rampA);               // _1615
float  occA     = alpha2 * occ;                                // _1616

// ===== 10. 环境项 & 光能量项 =====
float  ambientGrad = (clamp(dot(sssN, _CharacterParams6.xyz) + _CharacterParams7.x, 0,1)
                      * _CharacterParams7.y + _CharacterParams7.z);               // _1620 前
float3 ambient = ambientGrad.xxx * lerp(ambientTint, 1.0, _CharacterParams1.y * litMask);   // _1620 (CP1.y=1 -> lerp(tint,1,litMask))
float3 lightTerm = lerp(
    ambient * lerp(min(lerp(0.65, 1.0, ambientPeak), 1.5), clamp(ambientPeak, 1.25, 1.75), _CharacterParams1.x) * _CharacterParams0.w,
    (lerp(dot(lightColorI, LUM).xxx, lightColorI, litMask.xxx)
       + ambient * clamp(ambientPeak, 0.0, 1.5) * ((1.0 - _CharacterParams12.y) + lightColor * _CharacterParams12.y)) * _CharacterParams0.y,
    shadowDir);                                                                                // _1646
float3 baseSel = lerp(lerp(lerp(dot(shadowDeep2, LUM).xxx, shadowDeep2, 1.2), shadowDeep,
                       clamp((alpha2*(noSdf + occ*sdfW)) + rampA, 0, 1).xxx), diffuseColor, litMask.xxx); // _1647
float3 rampTinted = baseSel * ((1.0 - rampChroma) + ramp.rgb * rampChroma);                          // _1653
float3 diffuseTerm = lerp(
    lerp(shadowDeep, lerp(dot(diffuseColor, LUM).xxx, diffuseColor, 1.2), occA.xxx),
    rampTinted * clamp(dot(baseSel, LUM) / max(dot(rampTinted, LUM), 0.001), 0.0, 1.5),
    shadowDir);                                                                                // _1662
float4 diffuseLit = float4(diffuseTerm, shadowDir);                                           // _1666
float  litBlend  = lerp(occA, litMask, shadowDir);                                           // _1668
float3 specLight = lightTerm * ((litBlend * 0.5 + 0.5) * lerp(_CharacterParams0.z, 1.0, litBlend)); // _1674

// ===== 11. 脸部高光(GGX 近似)+ SDF 高光图 =====
float3 Lh2  = float3(camAxisZ.x, lerp(0.5, L.y, shadowDir), camAxisZ.z);   // _1679 伪光向(用于半角)
float  NdotV = clamp(dot(useN, V), 0, 1);                                  // _1692
float  HdotN = dot(useN, normalize((L * shadowDir) + (Lh2 * 2.0) + (V * (2.0 + shadowDir)))); // _1693
float  shin4 = shininess * shininess;                                      // _1694
float  d     = (((HdotN * shin4) - HdotN) * HdotN) + 1.0;                   // _1698
float  d2    = d * d;                                                      // _1699
float  specNDL = clamp((((shin4 != d2) ? (shin4 / d2) : 1.0)
                     * (0.5 / ((2.0*NdotV + shininess*1.0) + 1e-5))) - 6.103515625e-05, 0.0, 20.0);  // _1763 内
float3 highlightMap = _HighlightMap.SampleBias(sampler_LinearClamp,
                      uv0 + mul(V, M_o2w).xy * _HighlightMapVector.xy, _GlobalMipBias).rgb;  // _1728
// 雨滴高光(仅 rainAmt>0.001):_1760 = … * (clamp(ambientPeak,0.5,1.5)*CP0.w) * rainAmt^2 ;捕获 rainAmt=0
float3 diffuseFinal = lightTerm * diffuseTerm;                            // _1646*_1662 部分
float3 color = diffuseFinal
             + (specColor * specNDL * specLight * _CharacterParams13.w)   // _1397 * specNDL * _1674 * CP13.w
             + (highlightMap * specLight)                                 // _1728.xyz * _1674
             + 0.0;                                                       // 雨滴高光(本帧 0)

// ===== 12. 饱和度提升 + 屏幕 SDF 边缘光 + 脸缘光(skin 特有)=====
float lum = dot(color, LUM); float s = clamp(lum - 0.5, 0.0, 0.5);
color = lerp(lum.xxx, color, (s*s + 1.0).xxx);                            // _1855 主体(饱和度提升)
// 边缘光(CP8,本帧=0):rimAxis = normalize(cross(camAxisZ, float3(CP9.xy,0)));与 hair 同构但门控用 sdfMask.w 与 rooted 方向,且 _CameraDepthTexture 不读
//   输出 = _CharacterParams8.xyz * rimTerm * _CharacterParams8.w * min(min(clamp(dot(rootToPixelH,rimAxis)+1,0,1),alpha2),ssmG)
//          * (lerp(0.25, diffuseColor, CP9.z) * clamp(dot(rimAxis, sdfN),0,1)) ;捕获 CP8=0 -> 0
// 脸缘光(CP14,本帧=0):同构项 * _CharacterParams14.xyz * _1394 ;捕获 CP14=0 -> 0
// color += 0 (两项均为 0)

// ===== 13. 点光源(tile 32px × z-bin,_GlobalBinningBuffer;结构与 hair 一致,但 _1394/_1398/_1397/sdfN 代入)=====
// 每光:PunctualLightData[i*8+k]。k=5.w 位1 -> 盒形衰减((max|p|-(r+0.5))/(0.5-r))^2);k=3.w 类型:16 跳过,
//   (k=3.z + _CharacterParams12.z) < 0.5 跳过(角色灯层)。距离衰减:k=1.w 为 1/range,k=6.w 或 2*k=4.y 为指数(<0 用 (1-(d²r²)²)²/(d²+1));
//   聚光:cone 由 k=2.xy 八面体解码方向,(dot-k2.z)*k2.w 平方;管状灯 k=2.z>0 走 LTC 近似;cookie k=7.w>=0。
//   阴影:k=3.x 索引 _PunctualLightWorldToShadow,3x3 tent PCF 九次 SampleCmpLevelZero(_PunctualLightShadowTexV2, LinearMirrorOnce)。
//   类型 4:color = lerp(color, lightRGB, atten * k4.x * ((1-k4.w) + smoothstep(-0.5,0.5,dot(sdfN,Ldir))*k4.w))  (体积/环境灯)
//   类型 0:diffuse = lightRGB * ((1-k4.y) + (1/max(1, max3(lightRGB*atten)*lerp(0.75,0.5,1-shadowDir)))*k4.y)
//            * lerp(0.5*k4.x, 1, clamp(dot(normalize(lerp(float3(rootToPixelH.x,6.1e-5,rootToPixelH.z), sdfN, sdfW)), Ldir)+0.5,0,1))
//           color += diffuse*atten * lerp(diffuseLit, diffuseLit, sat(NdotL_p)) * premul + diffuse*atten * spec_p * sat(NdotL_p)
//   类型 1(NdotL_p = saturate(clamp(NdotL_p + k4.x,-1,1)) * shadow_p):色 = lerp(shadowDiff*k4.y, diffuseColor, NdotL_p)
//   类型 2:metallic 分支(lerp 到 _1394 用 step(0.5,metallic))
//   类型 3:深度/朝向边缘灯(同第 12 节朝向 rim 但用 _547 与 sdfMask.w 门控),NdotL_p = sat(dot(sdfN, -normalize(cross(camAxisZ, cross(camAxisZ, Ldir))))),色 = lerp(0.5, diffuseColor, k4.y),无高光
//   spec_p(类型≠3):同主高光公式(H=normalize(Ldir+V);× specColor × CP13.w),代入 useN 与 shininess
color += punctualLightsAccum;   // _1881

// ===== 14. VFX 调色、曝光、雾、输出 =====
if (_EnableVFXColorAdjustment > 0.5)
    color = lerp(lerp(0.5.xxx, lerp(dot(color,LUM).xxx, color, _ColorAdjustmentSaturation), _ColorAdjustmentContrast) * _ColorAdjustmentBrightness,
                 _ColorAdjustmentColorBlend.rgb, _ColorAdjustmentColorBlend.a)
          + _ColorAdjustmentRimColor.rgb * smoothstep(1.0 - _ColorAdjustmentRimWidth, 1.0, 1.0 - saturate(NdotV)) * _ColorAdjustmentRimIntensity;
float4 outColor = float4(color * _ExposureWithMiscParams.y, 1.0);
if (_CharacterParams12.w < 0.5) {
    // 大气雾 / 指数高度雾(_ExponentialFogParams0..5)/ 体积雾(_VolumetricFogParams0.z>0 + _IntegratedLightScattering)
    // 结构与 hair 完全一致(本帧 _VolumetricFogParams0.z=0,走 exp 雾分支);组合:rgb = outColor.rgb*(T*fogFactor)+inS*(1-T)*fogFactor+fogColor
}
SV_Target0 = outColor;   SV_Target1 = target1;   // _3167, _1427
```

## 4. `_CharacterParamsN` 用途表

| 分量 | 用法推断 | 捕获值(event 860) |
|---|---|---|
| CP0.y | 受光侧 lightTerm 总乘数 | 1 |
| CP0.z | 阴影色深度系数(`shadowDeep = shadowDiff*CP0.z`)以及 specLight 里 `lerp(CP0.z,1,litBlend)` | 0.65 |
| CP0.w | 阴影侧 lightTerm 总乘数 | 0.9 |
| CP1.x | 环境峰值映射选择:0 -> `min(lerp(0.65,1,peak),1.5)`,1 -> `clamp(peak,1.25,1.75)` | 0 |
| CP1.y | <0.5 采样辐照度体;>=0.5 用平坦环境(ambientTint=**CP3**, 非 hair 的 CP2);同时是 `lerp(tint,1,CP1.y*litMask)` 权重 | 1 |
| CP1.z | 1 = 忽略屏幕空间方向光阴影 | 0 |
| CP1.w | 1 = 用 CP11.xyz 替代 `-DirectionalLightDirection` 作为光方向 | 1 |
| CP2.xyz | **皮肤变体未引用**(hair 中作平坦环境色调) | (0.849,0.896,1.151) |
| CP3.xyz | **皮肤平坦环境色调**(仅阴影侧,受光侧被 lerp 到 1);CP1.y=1 时使用 | (1.260,0.740,0.740) |
| CP4.xyz | **皮肤光颜色覆盖**(权重 CP12.y);hair 用的是 CP5 | (1,0.914,0.911) |
| CP5.xyz | **皮肤变体未引用**(hair 作光颜色覆盖) | (1,1,1) |
| CP6.xyz | 环境梯度方向(`dot(sssN, CP6)`) | (0,1,~0) |
| CP7.x/y/z | 环境梯度 offset / scale / base:`sat(d+0.15)*1.5+0.5` ∈ [0.5,2] | 0.15 / 1.5 / 0.5 |
| CP8.xyz / w | 深度 SDF 边缘光颜色 / 强度(本帧=0,且皮肤不用 _CameraDepthTexture) | (0,0,0,1) |
| CP9.xy | 边缘光轴(世界空间 xy),`rimAxis = normalize(cross(camAxisZ, axis))` | (~0,-1) |
| CP9.z | 边缘/脸缘光颜色 `lerp(0.25, diffuseColor, CP9.z)` | 0 |
| CP9.w | 边缘光朝向衰减偏移量(×10-3 阈值) | 0.4 |
| CP10.x | >0.5 用全局天气掩码 CP10.y 与水位 CP10.w,否则 per-object `Stripped_208.xy` | 0 |
| CP10.y | 打包 uint8x4 天气掩码 (雨湿, 水位使能, 常湿, 雪) | ~0 |
| CP10.z | 雨/雪三平面 UV 缩放 | 2.25 |
| CP10.w | 全局水位高度 | -100 |
| CP11.xyz | 角色专用"指向光源"方向 | (0.176,0.530,0.830) |
| CP11.w | ramp 输入 NdotL 偏移(权重 CP12.x) | -0.1 |
| CP12.x | 1 = 关闭逆光 SDF 暗部抬亮(权重项 `(1-CP12.x)`) | 未捕获(置 1) |
| CP12.y | 光颜色覆盖权重(同时改变受光侧环境项乘 lightColor) | 1 |
| CP12.z | 点光源"角色灯层"门槛加数 | 1 |
| CP12.w | >=0.5:环境不乘 `_EnvironmentGlobalParams0.x`、光强不乘 CustomData1.w、跳过雾(UI/展示模式) | 0 |
| CP13.w | 高光(主 GGX + _HighlightMap + 点光 spec)总乘数 | 1 |
| CP14.xyz / w | 脸缘光颜色 / 强度(本帧=0) | (0,0,0,1) |
| CP15.z | 脸缘中心 `clamp(0.5 - CP15.z*0.5, ...)` | -1 |
| CP15.w | 0 = CP9.xy 为世界轴(rimAxis 用 cross(camAxisZ, CP9.xy)) | 0 |

`_CharacterParams2/5` 在皮肤变体 cbuffer 中存在但**函数体从不读取**(被 hair 专用的平坦环境/光颜色覆盖取代为 CP3/CP4)。

## 5. 使用到的全局常量与纹理

| 缓冲/寄存器 | 成员 | 用途 |
|---|---|---|
| TransformVariables b12 | `ViewMatrix`(正交视向、rimAxis 行0/1)、`InvViewMatrix`(mul 得 camAxisZ)、`WorldSpaceCameraPos_Internal`、`PrevCamPosRWS`(顶点) | 视向、相机轴 |
| ShaderVariablesGlobal b16 | `_ScreenSize.zw`、`_ZBufferParams`(本变体未用深度)、`_ProjectionParams.y`(z-bin)、`_unity_OrthoParams.w`、`_Time.x`(雨)、`_GlobalMipBias`、`_FrameCount`(体积雾抖动) | 见上 |
| 同上 | `_ExposureWithMiscParams.x`(乘 ambientScale)、`.y`(输出前乘 rgb);`.z/.w` 未用 | 捕获 (1,1,1.6,0.1) |
| 同上 | `_EnvironmentGlobalParams0.x` | ambientScale 基值,捕获 0.2877 |
| 同上 | `_IVParam0/1/2`、`_IVDefaultSHA{r,g,b}` | 辐照度体(捕获帧 CP1.y=1 未执行) |
| 同上 | `_CharacterParams0,1,3,4,6,7,8,9,10,11,12,13,14,15` | 第 4 节(注意 CP3/CP4 取代 hair 的 CP2/CP5) |
| 同上 | `_AtmosphereFogParams0..5`、`_ExponentialFogParams0..5`、`_VolumetricFogParams0..4`、`_BinningBufferOffsets.y` | 雾 / 光源分箱 |
| LightDataBuffer b14 | `DirectionalLightDirection.xyz`、`DirectionalLightCustomData1.rgb/w`、`PunctualLightData[2048]` | 角色用 CustomData1 = (1,1,1)*1.624;CP1.w=1 时光方向用 CP11 |
| ShadowData b15 | `_DirectionalShadowParams.x`(屏幕阴影强度)、`_PunctualLightWorldToShadow/ShadowParams/ShadowParams2/ShadowTexelSize` | 无 CSM、点光源 PCF |
| LightBinningConstants b48 | `NumTilesX`、`NumZBinSlice`、`InvZBinSlice` | 点光源 tile/z-bin |
| LightCookieCB b50 | `_lightCookieData/_lightCookieMatrices` | 点光源 cookie |
| UnityPerDraw (space2) | `Stripped_0`(O2W)、`Stripped_64.w` bit4 蒙皮、`Stripped_80.x` 蒙皮矩阵起点、`Stripped_208.xy` per-object 天气掩码/水位、`Stripped_208.x` 天气打包 | |
| t22 `_ScreenSpaceShadowMask` | `.r` 方向光阴影,`.g` 角色遮挡/自阴影 | Load 像素 |
| t27 `_PunctualLightShadowTexV2` | 点光源 PCF | LinearMirrorOnce (cmp) |
| t30-t35 IV clipmap A/B Lod0/1/3 | 环境 SH | A: LinearClamp,B: LinearRepeat(CP1.y=1 未用) |
| t36 `_IntegratedLightScattering` | 体积雾 froxel | LinearRepeat(本帧 z=0 跳过) |
| t39 `_CharacterSnowEffectTex` | 雪三平面 | LinearClamp + bias |
| t42/t43 `_CharacterRainFaceDropletTex/_DripTex` | 面部雨滴 | LinearClamp |
| t29 `_LightCookie` | 点光源 cookie | LinearRepeat |
| t51 `_GlobalBinningBuffer`,t18 `_VertexSkinMatrices` | 光源位掩码 / 蒙皮矩阵 | ByteAddressBuffer |

## 6. 未能解析的点

1. **`_BaseMap` 用 `sampler_LinearClamp` 而非 LinearRepeat**:与 hair 不同,皮肤 BaseMap 采样不重复;若 uv0 越界会被钳制,需确认模型 uv 是否严格在 [0,1]。
2. **`_10`(restTangentOS)被当作 restPosOS 用于雪三平面**:原码 `_1276 = _10.xzy * (1,1,-1)`,与通用 restPosOS 语义不符,可能是该变体顶点流复用;捕获帧雪≈0 不影响结果,但换有雪场景时坐标基准需重新核对。
3. **`linearToSRGB` 近似的精确意图**:`_472=*12.92`、`_476=pow(x,0.4167)*1.055-0.055` 是标准 linear→sRGB,但仅用于索引 `_ShadowLutTex`(SSS LUT 在 sRGB 空间),并非最终输出;确认 LUT 本身的色彩空间。
4. **`_CharacterParams3/4` 取代 hair 的 `_CharacterParams2/5`**:皮肤平坦环境色调与光颜色覆盖分别走 CP3/CP4。若其它角色(身体/头发)共用同一 CP 向量,需确认 CP3/CP4 是否也由同一驱动设置(hair 文档里 CP3/CP4 标"未捕获")。
5. **`_CharacterParams8`、`_CharacterParams14` 捕获均为 0**:皮肤/脸缘边缘光在本帧完全关闭;其完整公式(朝向衰减、sdfMask.w 门控、rooted 方向)已按原码还原结构,但缺少非零捕获值验证视觉效果。
6. **`_CharacterParams12.x` 捕获值**:summary 表 event 860 段未单列 CP12.x,按 hair 同名项推断为 1(关闭逆光 SDF 抬亮);若实际为 0,逆光分支会启用。
7. **点光源 PCF/cookie/LTC/类型 0/1/2/3/4 细节**:结构与 hair 文档一致,但皮肤代入的是 `diffuseColor(_1394)`、`shadowDiff(_1398)`、`specColor(_1397)`、`sdfN(_1529)`、`rooted 方向(_547)`;捕获帧无点光源命中,不改变结果。
8. **`_SDFMask` 四通道语义**:R=rim 掩码,G=SDF 权重混合(`sdfW`,门控 SSS 法线/SDF 方向/ramp 输入),B=skin vs face 选择(`sdfSkin`,切换 FaceRimOffScale 与 ramp 混合),W=脸缘强度(`sdfFace`);需贴图资源确认各通道含义。
9. **`_ShadowLutTex` 尺寸**:捕获为 1024x32 BC7_SRGB,`_489` 的步进(1/32 列、1/32 行)与 1024 宽匹配(1024/32=32 行?),但实际 LUT 布局需贴图确认。

---

*生成说明:本文件仅作渲染逆向研究文档,不修改任何 shader/代码资源。所有推断基于 SPIR-V-Cross 反编译输出与 event 860 捕获帧(face)常量。*
