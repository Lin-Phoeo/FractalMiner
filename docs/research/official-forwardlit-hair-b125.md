# 官方 CharacterNPR_Hair ForwardLit 片元着色器还原(变体 b125)

来源:`_dump_1.5.3/.../characternpr/characternpr_hair/Sub0_Pass0_Fragment_b125.hlsl`(1517 行,SPIR-V-Cross 输出),
配套顶点 `Sub0_Pass0_Vertex_b125.hlsl`(同一 keyword 行,输出结构 TEXCOORD0..9 与片元输入完全一致),
属性/关键字来自 `characternpr_hair.shader`(Pass "ForwardLit",LightMode `ForwardCharacterOnly`,`#pragma target 5.0`,dxc)。
下文中所有数字、swizzle、clamp、pow 指数均按原码保留;`mad`/位运算已改写为普通算式。

## 1. 变体识别

`characternpr_hair.shader:586` 的条件(片元)/`:232`(顶点)完全相同:

```
ON : SRP_INSTANCING_ON  HG_ENABLE_PER_OBJECT_MV  HG_ENABLE_SCREEN_SPACE_SHADOW_MASK
     _NORMALMAP  _METALLICSPECGLOSSMAP  _SPEC_RAMP_ON  _DIFF_RAMP_ON  _SPECULAR_LINE
OFF: _SPECULAR_NORMALMAP  _ALPHATEST_ON  _EMISSION  BAKED_SKINNING_ANIMATION_TEXTURE
     _CUSTOMIZE_AVATAR  _SHADOW_LUT_TEX  _ALPHABLEND_ON  _STROKE_ON  VFX_CHARACTER_DISSOLVE  DITHER
```

后果:只有**一张**法线贴图(`_SpecBumpScale`、`_SplitNormalMap` 不出现);无 alpha clip、无自发光、无 Stroke 图、无 LUT 阴影色;
`_HairBaseTintColor/_HairAddTintColor/_Specular/_Metallic` 虽在 cbuffer 里但函数体从未读取。
阴影完全来自 `_ScreenSpaceShadowMask`,没有任何 CSM / `_CharacterWorldToShadow` 采样。

### 纹理寄存器 -> 名称 -> 采样方式 -> 必然对应的贴图

| 寄存器 | HLSL 名 | 采样表达式 | 判据 | 本发型对应贴图 / 捕获 binding |
|---|---|---|---|---|
| t6,space1 | `_BaseMap` | `SampleBias(LinearRepeat, uv0, _GlobalMipBias)`,rgb*`_BaseColor` | 唯一乘 BaseColor 的 sRGB 图 | `_D` 2048² BC7_SRGB = **b6** |
| t5,space1 | `_BumpMap` | `SampleBias(uv0)` 后 `a*=r; n.xy=ag*2-1`(Unity RGorAG 解包) | 法线解包 | `_HN` 2048² BC7_UNORM = b1 或 b3 |
| t2,space1 | `_MetallicGlossMap` | `SampleBias(uv0)`,4 通道分别当 R=aniso 方向选择, G=高光遮罩, B=阴影遮罩, A=次高光强度 | 4 通道 mask | `_P` 2048² BC7_UNORM = b3 或 b1 |
| t1,space1 | `_SpecRampMap` | `SampleLevel(LinearMirror, float2(spec1, sign(TdotH)*edgeFade²), 0)` | 二维 ramp(u=高光强度,v=边缘衰减) | `_RS` 256² RGBA8 = **b2** |
| t4,space1 | `_DiffRampMap` | `SampleLevel(LinearMirror, float2(x, 0.5), 0)` 两次 | 一维 ramp,v 固定 0.5 | `hair_04_RD` 256x1 RGBA8 = **b5** |
| t3,space1 | `_LineMap` | `Sample(LinearRepeat, uv0*_LineMap_ST.xy+_LineMap_ST.zw)`(无 mip bias) | 平铺 (8,1,-0.45,0) | `hairline_02_M` 512² BC7 = **b4** |

b1 与 b3 格式/尺寸相同,仅凭格式无法区分哪张是 `_HN`、哪张是 `_P`,见第 6 节。
注意:变体没有 `_SPECULAR_NORMALMAP`,所以 `_HN` 的 BA 通道并不会作为"高光法线"单独使用;解包公式 `n.x=(A*R)*2-1, n.y=G*2-1`,
只有当 A≈1(RG 法线图)或 R≈1(DXT5nm)时才正确。若 `_HN` 真的是 RG/BA 分裂图,官方在本变体下实际读到的 x 分量是 `R*A`。

Set0 全局纹理:`_ScreenSpaceShadowMask`(t22,Load 像素),`_CameraDepthTexture`(t46,LinearClamp),`_PunctualLightShadowTexV2`(t27,仅点光源 PCF),
`_IrradianceVolumeClipmapTexture{A,B}Lod{0,1,3}`(t30-t35),`_IntegratedLightScattering`(t36,体积雾),`_CharacterSnowEffectTex`(t39,雪),`_LightCookie`(t29)。

## 2. 输入插值器

顶点着色器输出(`_14.._24`)-> 片元输入(`_3.._13`):

| 语义 | 片元名 | 内容(由顶点 b125 推得) |
|---|---|---|
| TEXCOORD0 float2 | `uv0` | 顶点 slot1(float2)`* _BaseMap_ST.xy + _BaseMap_ST.zw` |
| TEXCOORD1 float3 | `positionRWS` | 世界坐标 − `_WorldSpaceCameraPos_Internal`(camera-relative) |
| TEXCOORD2 float3 | `normalWS` | 归一化世界法线(顶点里支持 10:10:10 八面体压缩法线) |
| TEXCOORD3 float4 | `tangentWS` | xyz 归一化世界切线,w = 副切线符号(±1) |
| TEXCOORD4 float3 | `clipCur` | 当前帧非抖动裁剪坐标 `.xyw`(运动矢量) |
| TEXCOORD5 float3 | `clipPrev` | 上一帧裁剪坐标 `.xyw` |
| TEXCOORD6 float3 | `restNormalOS` | 物体空间法线(GPU 蒙皮时取第二套法线流),仅雨/雪三平面用 |
| TEXCOORD7 float4 | `restTangentOS` | 物体空间切线,仅雨滴法线框架用 |
| TEXCOORD8 float3 | `restPosOS` | 顶点 TEXCOORD1 原样透传(绑定姿态/静止坐标),仅雨/雪三平面 UV 用 |
| TEXCOORD9 uint (nointerp) | `instanceID` | 索引 `_SRP_UnityPerDraw_UnityPerDrawArray[256]` |
| SV_Position | `fragCoord` | `.xy` 像素坐标(屏幕 UV、阴影掩码 Load、光源分箱);`1/w` 转回线性视深 `eyeDepth` |
| SV_IsFrontFace | `isFront` | 背面法线翻转、雪只在正面 |

**顶点色未被片元使用**(顶点 COLOR0 槽位实际承载切线)。没有 uv1。

## 3. 片元着色器整洁重构

```hlsl
// ===== 0. 通用量 =====
float  eyeDepth  = 1.0 / fragCoord.w;                       // SPIRV-Cross 已把 w 变成 1/w,故这里 = 线性视深
float3 viewVec   = lerp(-positionRWS, ViewMatrix[2].xyz, _unity_OrthoParams.w);
float  viewDist  = length(viewVec);            // _423,用 rsqrt(max(dot,1e-8)) 实现
float3 V         = viewVec / viewDist;         // _422
bool   skinned   = (asuint(PerDraw.Stripped_64.w) & 16u) != 0;
float4 row0,row1,row2;   // objectToWorld 三行:蒙皮时从 _VertexSkinMatrices[Stripped_80.x + {0,1,2}] 读,否则 PerDraw.Stripped_0[0..2]
float3x3 M_o2w   = float3x3(row0.xyz, row1.xyz, row2.xyz);  // mul(M_o2w, v): OS->WS ; mul(v, M_o2w): WS->OS
float3 positionWS = positionRWS + _WorldSpaceCameraPos_Internal.xyz;
float3 rootToPixelH = normalize(float3(positionWS.x - row0.w, 6.103515625e-05, positionWS.z - row2.w)); // 角色根到像素的水平方向
float3 camAxisZ  = float3(InvViewMatrix[0].z, InvViewMatrix[1].z, InvViewMatrix[2].z); // 相机 +Z(指向观察者)
float2 screenUV  = fragCoord.xy * _ScreenSize.zw;
int2   pixel     = int2(fragCoord.xy);
const float3 LUM = float3(0.2126729, 0.7151522, 0.0721750);

// ===== 1. 反照率 / 阴影色 =====
float4 baseMap   = _BaseMap.SampleBias(sampler_LinearRepeat, uv0, _GlobalMipBias);
float3 albedo    = baseMap.rgb * _BaseColor.rgb;
float  alpha     = baseMap.a   * _BaseColor.a;
float4 packed    = _MetallicGlossMap.SampleBias(sampler_LinearRepeat, uv0, _GlobalMipBias);
float  anisoSel  = packed.r;   // "metallic" 通道:0=按物体Y轴生成发丝方向,1=用网格切线
float  specMask  = packed.g;   // "specular"
float  shadowMask= packed.b;   // 自阴影/AO 遮罩
float  spec2Mask = packed.a;   // "smoothness":只乘在次级各向异性高光上
float3 sc        = albedo * _ShadowColorBrightness;
float3 shadowColor = lerp(dot(sc, LUM).xxx, sc, _ShadowColorSaturation);

// ===== 2. 法线(本变体 diffuse/specular 共用同一法线)=====
float4 nm = _BumpMap.SampleBias(sampler_LinearRepeat, uv0, _GlobalMipBias);
nm.a *= nm.r;
float3 nTS; nTS.xy = nm.ag * 2.0 - 1.0;
nTS.z = max(1e-16, sqrt(1.0 - saturate(dot(nTS.xy, nTS.xy))));
nTS.xy *= _BumpScale;
float4 lineMap = _LineMap.Sample(sampler_LinearRepeat, uv0 * _LineMap_ST.xy + _LineMap_ST.zw);
float3 T = tangentWS.xyz, B = cross(normalWS, tangentWS.xyz) * tangentWS.w, Nv0 = normalWS;
float3 nWS = nTS.x * T + nTS.y * B + nTS.z * Nv0;
float  faceSign = isFront ? 1.0 : (-1.0 + 2.0 * _BackFaceNormalFlip);
float3 N  = normalize(nWS) * faceSign;         // 贴图法线
float3 Nv = normalize(normalWS) * faceSign;    // 顶点法线(仅点光源分支用)
// 发丝方向:物体空间 (AnisotropyDirX, 1, 0) 投影到切平面(取反),按 anisoSel 与网格切线混合
float3 upWS  = normalize(mul(M_o2w, float3(_AnisotropyDirX, 1.0, 0.0)));
float3 anisoDir = cross(N, lerp(cross(N, upWS), tangentWS.xyz, anisoSel)) * lerp(1.0, tangentWS.w, anisoSel);
float3 Vos = mul(V, M_o2w);                      // 视线 -> 物体空间
float3 Nos = mul(N, M_o2w);
float  edgeFade = pow(saturate(dot(normalize(Nos.xz), normalize(Vos.xz))), _AnisotropyEdgeFade);   // _592

// ===== 3. 天气掩码(雨/水位/雪),来自 _CharacterParams10 或 per-object =====
uint  wmask   = asuint(_CharacterParams10.x > 0.5 ? _CharacterParams10.y : PerDraw.Stripped_208.x);
float4 wm     = float4(wmask & 255, (wmask >> 8) & 255, (wmask >> 16) & 255, (wmask >> 24) & 255) / 255.0; // x=雨湿, y=水位使能, z=常湿, w=雪
float waterLine = lerp(PerDraw.Stripped_208.y, _CharacterParams10.w, _CharacterParams10.x);
float wetWater  = max(wm.z, smoothstep(-0.2, 0.15, waterLine - positionWS.y) * wm.y);   // _644
float wetness   = max(wm.x, wetWater);                                                 // _645
float ambientScale = lerp(_EnvironmentGlobalParams0.x, 1.0, _CharacterParams12.w) * _ExposureWithMiscParams.x;  // _653

// ===== 4. 环境光:辐照度体 clipmap + _IVDefaultSH 回退 =====
float4 shDominant; float3 ambientRGB, ambientTint; float ambientPeak;
if (_CharacterParams1.y < 0.5) {
    // 三层 clipmap,中心 = _IVParam0.xyz - camAxisZ * offset;半径/过渡宽度:
    //   外包围 offset=_IVParam2.w  半径 xz 464, y 208, 斜率 1/32   -> fadeOuter
    //   LOD0   offset=_IVParam2.y  半径 xz 29,  y 13,  斜率 1/2    -> fade0 ; uvw = frac((posWS*2   +0.5)*_IVParam1.xyz)
    //   LOD1   offset=_IVParam2.z  半径 xz 116, y 52,  斜率 1/8    -> fade1 ; uvw = frac((posWS*0.5 +0.5)*_IVParam1.xyz)
    //   LOD3   (fade1>0 时)                                              uvw = clamp(frac((posWS*0.125+0.5)*_IVParam1.xyz), h, 1-h), h=_IVParam1.xyz*0.5
    // fade = max(saturate((max(|d.x|,|d.z|)-rXZ)*k), saturate((|d.y|-rY)*k)),d = posWS - center
    // 权重 w0 = 1-fade0, w1 = fade0*(1-fade1), w3 = fade1*(1-fadeOuter);整体仅当 _IVParam0.w != 0 && fadeOuter < 1
    // 每层:A = TexA.SampleLevel(LinearRepeat, uvw, 0)           (rgb = 各通道 L0 幅值)
    //       hy = _IVParam1.y*0.5; uvB = float3(uvw.x, clamp(uvw.y,hy,1-hy)/3, uvw.z)
    //       Bk = TexB.SampleLevel(LinearMirror, uvB + float3(0,k/3,0), 0), k=0,1,2   (rgb*4-2 = R/G/B 通道的 L1 方向)
    //       accR += float4((B0.rgb*4-2)*A.r, A.r)*w ; accG += ...B1,A.g ; accB += ...B2,A.b ; accW += B0.a*w  (accW 初值 = fadeOuter)
    // valid = saturate(accW*2-1); wDir = valid - fadeOuter; wDef = (valid+fadeOuter)*0.5   (体积不可用时 wDir=0,wDef=1)
    // shC = accC + float4(D.x*wDef, D.y*wDef + D.w*wDir*0.5, D.z*wDef, D.w*wDef + D.y*wDir*0.375), D = _IVDefaultSHA{r,g,b}
    ambientRGB = max(float3(dot(shR, float4(N,1)), dot(shG, float4(N,1)), dot(shB, float4(N,1))), 0) * ambientScale;
    float3 dir = normalize(shR.xyz*0.2126 + shG.xyz*0.7152 + shB.xyz*0.0722); dir.y = abs(dir.y);
    shDominant = float4(dir, 1.0);
    ambientPeak = max(max3(max(float3(dot(shR,shDominant), dot(shG,shDominant), dot(shB,shDominant)), 0)), 0) * ambientScale;
    // 色调:RGB->HSV(ambientRGB),s' = min(s, lerp(0.7, 0.35, smoothstep(0.45, 0.35, |h-0.5|)) * saturate(v)),v' = 2/(2-s')
    ambientTint = HSVtoRGB(h, s', v');    // = lerp(1, saturate(|frac(h+float3(1,2/3,1/3))*6-3|-1), s') * v'
} else {                                   // 捕获帧走这里(_CharacterParams1.y = 1)
    shDominant = 0; ambientRGB = 1; ambientTint = _CharacterParams2.rgb; ambientPeak = ambientScale;
}

// ===== 5. 雨滴(程序化涟漪,三平面)与雪 =====
// 雨:if (saturate(wm.x + wetWater) - _DisableRainEffectOnMaterial > 0.01)。三平面坐标 restPosOS(蒙皮时 .xzy*(1,1,-1)) * _CharacterParams10.z,
//   权重 pow(max(|restNormalOS|-0.2,0),10) 归一;每轴两套网格 (×32, ×48.3456) 的 hash 涟漪,时间 _Time.x。输出:
float3 rainN = N;  float rainSpecBoost = 1.0;  float rippleI = 0, rippleAdd = 0, specScale = 1.0; float3 shadowColorW = shadowColor, albedoW = albedo;
//   有雨时:rainN = 涟漪法线;rainSpecBoost = 1 + wetness;specScale = lerp(1, 0.8*lerp(0.5,1,s), r);albedoW/shadowColorW *= darken*(1-0.2*wetness)
// 雪:if (wm.w - _DisableRainEffectOnMaterial > 0.01)
float3 Ns = N; float3 diffuseBase = albedoW, shadowBase = shadowColorW;
//   coverage = smoothstep(2-c(2-c), 2.35-c(2-c), restNormalOS.y*0.4+0.6 + snowTex.b) * shadowMask² * isFront,
//   snowTex = 三平面 _CharacterSnowEffectTex.SampleBias(restPosOS*_CharacterParams10.z .xz/.xy/.zy),权重 max((|n|-0.2)³,6.1e-5)
//   Ns = 由 snowTex.rg 扰动的法线;diffuseBase = lerp(albedoW, 0.88, coverage);shadowBase = lerp(shadowColorW, 0.308, coverage)
float  metalOut     = 0.0;                                  // 原码 lerp(0,0,coverage) 恒为 0
float3 diffuseColor = diffuseBase * 0.96;                   // _2085  (0.96 - metalOut*0.96)
float3 specColor    = 0.04 * specMask;                      // _2088  lerp(0.04*specMask, albedo, metalOut)
float3 shadowDiff   = shadowBase * 0.96;                    // _2089

// ===== 6. 运动矢量 (SV_Target1) =====
float2 mv = clipCur.xy / max(clipCur.z, 1e-8) - clipPrev.xy / max(clipPrev.z, 1e-8);
mv.y = -mv.y;
float2 mvEnc = sqrt(sqrt(abs(mv * 0.5))) * sign(mv) * 0.5 + 0.5;
float4 target1 = float4(mvEnc, 1.0, rippleI > 0.1 ? 0.7 : 0.4);

// ===== 7. 光方向 / 光颜色 / 阴影 =====
float3 L  = lerp(-DirectionalLightDirection.xyz, _CharacterParams11.xyz, _CharacterParams1.w);   // 捕获:CP1.w=1 -> L = CP11.xyz
float3 Lh = normalize(float3(L.x, 6.103515625e-05, L.z));
float3 lightColor  = lerp(DirectionalLightCustomData1.rgb, _CharacterParams5.rgb, _CharacterParams12.y);
float3 lightColorI = lightColor * lerp(DirectionalLightCustomData1.w, 1.0, _CharacterParams12.w);  // 捕获:(1,1,1)*1.624
float4 ssm = _ScreenSpaceShadowMask.Load(int3(pixel, 0));
float  ssmG = ssm.g;                                                        // 第二通道:角色自阴影/遮挡
float  shadowDir = lerp(lerp(1.0, ssm.r, _DirectionalShadowParams.x), 1.0, _CharacterParams1.z);   // 1=受光
float  NdotL = dot(Ns, L);
float3 shadowDeep  = shadowDiff * _CharacterParams0.z;      // _2174  (×0.65)
float3 shadowDeep2 = shadowDeep * 0.65;                     // _2175
float  lumDiffuse  = dot(diffuseColor, LUM);
float  backlit = saturate(-dot(Lh.xz, normalize(camAxisZ.xz)));   // 光在角色背后(与相机相对)=1
float  cp12xInv = 1.0 - _CharacterParams12.x;

// ===== 8. 漫反射 ramp =====
float wrapT = -NdotL * (NdotL * 0.5 - 1.0) + 0.5;                     // 逆光时抬亮暗部的重映射
float t = lerp(NdotL, wrapT, backlit * smoothstep(0.25, 0.75, 1.0 - abs(camAxisZ.y)) * cp12xInv)
        + _CharacterParams11.w * _CharacterParams12.x;
float4 ramp  = _DiffRampMap.SampleLevel(sampler_LinearMirror, float2(clamp(t, -1, 1) * 0.5 + 0.5, 0.5), 0);
float  rampChroma = max3(ramp.rgb) - min3(ramp.rgb);
float  rampV = _DiffRampMap.SampleLevel(sampler_LinearMirror, float2(dot(Ns, camAxisZ) * 0.5 + 0.5, 0.5), 0).a;
float  litMask  = min(min(ssmG, shadowMask), ramp.a);                 // _2237
float  litView  = rampV * shadowMask * ssmG;                          // _2238
float  occl     = shadowMask * ssmG;                                  // _2230

// ===== 9. 环境项 & 光能量项 =====
float  ambientGrad = saturate(dot(N, _CharacterParams6.xyz) + _CharacterParams7.x) * _CharacterParams7.y + _CharacterParams7.z;
float3 ambient = ambientGrad * lerp(ambientTint, 1.0, _CharacterParams1.y * litMask);          // _2242
float3 lightTerm = lerp(
    ambient * lerp(min(lerp(0.65, 1.0, ambientPeak), 1.5), clamp(ambientPeak, 1.25, 1.75), _CharacterParams1.x) * _CharacterParams0.w,
    (lerp(dot(lightColorI, LUM).xxx, lightColorI, litMask)
       + ambient * clamp(ambientPeak, 0.0, 1.5) * ((1.0 - _CharacterParams12.y) + lightColor * _CharacterParams12.y)) * _CharacterParams0.y,
    shadowDir);                                                                                // _2268
float3 baseSel = lerp(lerp(lerp(dot(shadowDeep2, LUM).xxx, shadowDeep2, 1.2), shadowDeep, saturate(occl * rampV + ramp.a)), diffuseColor, litMask); // _2269
float3 rampTinted = baseSel * ((1.0 - rampChroma) + ramp.rgb * rampChroma);                                                   // _2275
float3 diffuseTerm = lerp(
    lerp(shadowDeep, lerp(lumDiffuse.xxx, diffuseColor, 1.2), litView),
    rampTinted * clamp(dot(baseSel, LUM) / max(dot(rampTinted, LUM), 0.001), 0.0, 1.5),
    shadowDir);                                                                                // _2284
float  litBlend  = lerp(litView, litMask, shadowDir);                                          // _2290
float3 specLight = lightTerm * ((litBlend * 0.5 + 0.5) * lerp(_CharacterParams0.z, 1.0, litBlend)); // _2296

// ===== 10. 各向异性高光(主/次)+ 发丝线 =====
float  Ly = lerp(0.5, L.y, shadowDir);
float3 pseudoL = mul(M_o2w, float3(Vos.x, Ly, Vos.z));               // 水平视向 + 光的高度,回到世界
float3 Lsh = L * shadowDir;
float3 H = normalize(Lsh + pseudoL * 2.0) + V;  H = H * rsqrt(max(6.103515625e-05, dot(H, H)));
float3 T1 = normalize(anisoDir + N * (_AnisotropyValue  * 2.0 - 1.0));
float3 T2 = normalize(anisoDir + N * (_AnisotropyValue2 * 2.0 - 1.0));
float3 TL = normalize(anisoDir + N * (2.0 * _LineValue  - 1.0));
float  TdotH1 = dot(T1, H), TdotH2 = dot(T2, H), TdotHL = dot(TL, H);
float  spec1 = saturate(pow(max(sqrt(1.0 - TdotH1 * TdotH1), 1e-4), 200.0) * specMask);
float3 specRamp = _SpecRampMap.SampleLevel(sampler_LinearMirror, float2(spec1, (TdotH1 > 0 ? 1.0 : 0.0) * edgeFade * edgeFade), 0).rgb;
float3 anisoSpec1 = spec1 * specRamp * edgeFade;                                          // _2337
float  spec1Max = max3(anisoSpec1);
int    e2 = int(200.0 * max(1.0 - _AnisotropyRange2, 0.0));                                // 捕获:60
float3 anisoSpec2 = pow(max(sqrt(1.0 - TdotH2 * TdotH2), 1e-4), e2) * edgeFade * (_AnisotropyColor2.rgb * spec2Mask);
int    eL = int(200.0 * max(1.0 - _LineRange, 0.0));                                       // 捕获:6
float  lineWidth = saturate(pow(max(sqrt(1.0 - TdotHL * TdotHL), 1e-4), eL));
float  lineProc  = ceil(saturate(frac(uv0.x * _LineAmount) - 0.5));
float  lineMask  = lerp(lineProc, 1.0 - lineMap.r, _UseLineMap);
float  lineFactor = lerp(1.0, lerp(1.0, lerp(lerp(1.0 - _LineIntensity, 1.0, lineMask), 1.0, spec1Max), lineWidth), specMask); // _2412
float3 specTotal = ((anisoSpec1 * specColor * _AnisotropyIntensity * 5.0 * rainSpecBoost)
                  + lerp(anisoSpec2 * rainSpecBoost, 0.0, spec1Max)) * specLight * _CharacterParams13.w;                        // _2416
float3 diffLit = lightTerm * diffuseTerm * lineFactor;
float3 diffuseFinal = lerp(dot(diffLit, LUM).xxx, diffLit, lerp(_LineSaturation, 1.0, lineFactor));                            // _2424

// ===== 11. 雨滴高光 + 合成 =====
float3 H2 = normalize(Lsh + normalize(float3(camAxisZ.x, Ly, camAxisZ.z)) * 2.0 + V * (2.0 + shadowDir));
float3 rt = normalize(float3(-rainN.z, 0.001, rainN.x));
float  ripple = smoothstep(0.15, 0.10, abs(dot(H2, rt))) * smoothstep(0.07, 0.02, abs(dot(H2, cross(rainN, rt)))) * max(0, dot(rainN, H2)) * 2.0 * rippleI;
float  premul = (1.0 - _AlphaPremultiply) + alpha * _AlphaPremultiply;
float3 color = diffuseFinal * premul + (specTotal * specScale + ((diffuseFinal + specTotal) * rippleAdd + ripple * specLight));  // _2469
//   无雨时:color = diffuseFinal * premul + specTotal

// ===== 12. 饱和度提升 + 屏幕空间深度边缘光 + 逆光菲涅尔边缘光 =====
float lum = dot(color, LUM);  float s = clamp(lum - 0.5, 0.0, 0.5);
color = lerp(lum.xxx, color, 1.0 + s * s);
float3 rimAxis = lerp(float3(_CharacterParams9.xy, 0.0), ViewMatrix[0].xyz * _CharacterParams9.x + ViewMatrix[1].xyz * _CharacterParams9.y, _CharacterParams15.w);
float3 rimDir  = normalize(cross(camAxisZ, rimAxis));       // CP9.xy=(0,-1) -> 屏幕右侧
float2 screenN = normalize(mul((float3x3)ViewMatrix, Ns).xy) * float2(_ScreenParams.y / _ScreenParams.x, 1.0);
float2 rimUV   = clamp(screenUV + screenN * _CharacterParams9.w * 0.006, _ScreenParams.zw - 1.0, 2.0 - _ScreenParams.zw);
float  sceneDepth = 1.0 / (_ZBufferParams.z * _CameraDepthTexture.SampleLevel(sampler_LinearClamp, rimUV, 0).r + _ZBufferParams.w);
float  depthRim = smoothstep(0.1, 0.2, sceneDepth - eyeDepth);
float3 rim = _CharacterParams8.rgb * depthRim * _CharacterParams8.w
           * min(min(saturate(dot(rootToPixelH, rimDir) + 1.0), shadowMask), ssmG)
           * (lerp(0.25.xxx, diffuseColor, _CharacterParams9.z) * saturate(dot(rimDir, Ns)));
float  LhN = dot(Lh, Ns);  float NdotV = dot(V, Ns);  float shInv = 1.0 - shadowDir;
float3 edgeLight = lerp(ambientRGB / max(max3(ambientRGB) * 0.5, 1.0), lightColorI, shadowDir)
    * saturate(lerp(dot(shDominant.xyz, Ns) * shDominant.w, -LhN * (LhN * 0.5 - 1.0) + 0.5, shadowDir))
    * ((shInv + backlit * shadowDir) * cp12xInv)
    * smoothstep(0.6, 0.8, 1.0 - abs(NdotV))
    * min(shadowMask, ssmG)
    * (shInv + smoothstep(0.1, 0.04, lumDiffuse) * shadowDir)
    * max(0.15.xxx, diffuseColor);
color += rim + edgeLight;                                                                     // _2616

// ===== 13. 点光源(tile 32px × z-bin,_GlobalBinningBuffer)=====
// 每光:PunctualLightData[i*8+k]。k=5.w 位1 -> 盒形衰减 (半精度 3x4 矩阵,(max|p|-(r+0.5))/(0.5-r) 平方);k=3.w 类型:16 跳过,
//   (k=3.z + _CharacterParams12.z) < 0.5 跳过(角色灯层)。距离衰减:k=1.w 为 1/range,k=6.w 或 2*k=4.y 为指数(<0 用 (1-(d²r²)²)²/(d²+1));
//   聚光:cone 由 k=2.xy 八面体解码方向,(dot-k2.z)*k2.w 平方;管状灯 k=2.z>0 走 LTC 近似;cookie k=7.w>=0 (2D 或 cube 展开 6 面)。
//   阴影:k=3.x 索引 _PunctualLightWorldToShadow,3x3 tent PCF 九次 SampleCmpLevelZero(_PunctualLightShadowTexV2, LinearMirrorOnce)。
//   类型 4:color = lerp(color, lightRGB, atten * k4.x * ((1-k4.w) + smoothstep(-0.5,0.5,dot(Nv,Ldir))*k4.w))  (体积/环境灯,用顶点法线)
//   类型 0:diffuse = lightRGB * ((1-k4.y) + k4.y / max(1, max3(lightRGB*atten)*lerp(0.75,0.5,shInv))) * lerp(0.25*k4.x, 1, saturate(NdotL_p+0.5)),
//           color += diffuse*atten * lerp(diffuseTerm, diffuseTerm, sat(NdotL_p)) * premul + diffuse*atten * spec_p * sat(NdotL_p)
//   类型 1:NdotL_p = saturate(clamp(NdotL_p + k4.x,-1,1)) * shadow_p;色 = lerp(shadowDiff*k4.y, diffuseColor, NdotL_p)
//   类型 3:深度边缘灯(同第 12 节的深度测试,偏移 k4.x),NdotL_p = sat(dot(Ns, -normalize(cross(camAxisZ, cross(camAxisZ, Ldir))))),色 = lerp(0.5, diffuseColor, k4.y),无高光
//   spec_p(类型≠3):同 anisoSpec1 公式但 H = normalize(Ldir + V);× specColor × _AnisotropyIntensity × 5 × rainSpecBoost × k7.z

// ===== 14. VFX 调色、曝光、雾、输出 =====
if (_EnableVFXColorAdjustment > 0.5)
    color = lerp(lerp(0.5.xxx, lerp(dot(color,LUM).xxx, color, _ColorAdjustmentSaturation), _ColorAdjustmentContrast) * _ColorAdjustmentBrightness,
                 _ColorAdjustmentColorBlend.rgb, _ColorAdjustmentColorBlend.a)
          + _ColorAdjustmentRimColor.rgb * smoothstep(1.0 - _ColorAdjustmentRimWidth, 1.0, 1.0 - saturate(NdotV)) * _ColorAdjustmentRimIntensity;
float4 outColor = float4(color * _ExposureWithMiscParams.y, (_SurfaceType == 1.0) ? alpha : 1.0);
if (_CharacterParams12.w < 0.5) {
    // 大气雾:h = posWS.y*_Atm3.w; k = max(0.01, h+_Atm4.w);
    //   T = exp(_Atm2.rgb * (-max(0, viewDist*_Atm1.w - _Atm0.w)) * ((1-exp(-k))/k) * exp(h+_Atm5.w))
    //   cosθ = dot(-V, _Atm1.xyz); g=_Atm2.w; inS = saturate(_Atm3.rgb*0.0596831*(1+cos²) + _Atm5.rgb + _Atm4.rgb*(1-g²)/max(12.566371*(1+g²-2g cos)^1.5, 0.001)) * 255
    // 指数高度雾 (_ExponentialFogParams0..5):两层 exp2 密度积分,fogFactor = saturate(max(sat(exp2(-dens*dist)), _Exp2.w) + sat(dist*_Exp1.y+_Exp1.x) + sat(dist*_Exp1.w+_Exp1.z))
    //   fogColor = _Exp2.rgb*(1-fogFactor) + _Exp5.rgb*pow(sat(dot(V,_Exp4.xyz)),_Exp5.w)*(1-sat(exp2(-dens*max(dist-_Exp4.w,0))))*(1-farTerm)
    // 体积雾 (_VolumetricFogParams0.z>0):_IntegratedLightScattering.SampleLevel(LinearMirror, float3(jitteredPixel*_Vol2.xy, log2(eyeDepth*_Vol1.x+_Vol1.y)*_Vol1.z/_Vol0.z)),
    //   与 exp 雾按 froxel.a 组合;此路径下 dist 先被投影到视轴上(_Vol0.w)
    // 组合:rgb = outColor.rgb * (T * fogFactor) + inS * (1 - T) * fogFactor + fogColor
}
SV_Target0 = outColor;   SV_Target1 = target1;
```

## 4. `_CharacterParamsN` 用途表

| 分量 | 用法推断 | 捕获值 |
|---|---|---|
| CP0.y | 受光侧 lightTerm 总乘数 | 1 |
| CP0.z | 阴影色深度系数(`shadowDeep = shadowDiff*CP0.z`)以及 specLight 里 `lerp(CP0.z,1,litBlend)` | 0.65 |
| CP0.w | 阴影侧 lightTerm 总乘数 | 0.9 |
| CP1.x | 环境峰值映射选择:0 -> `min(lerp(0.65,1,peak),1.5)`,1 -> `clamp(peak,1.25,1.75)` | 0 |
| CP1.y | <0.5 采样辐照度体;>=0.5 用平坦环境(ambientRGB=1, tint=CP2);同时是 `lerp(tint,1,CP1.y*litMask)` 权重 | 1 |
| CP1.z | 1 = 忽略屏幕空间方向光阴影 | 0 |
| CP1.w | 1 = 用 CP11.xyz 替代 `-DirectionalLightDirection` 作为光方向 | 1 |
| CP2.xyz | 平坦环境色调(仅阴影侧,受光侧被 lerp 到 1) | (0.849,0.896,1.151) |
| CP5.xyz | 光颜色覆盖(权重 CP12.y) | 未捕获 |
| CP6.xyz | 环境梯度方向(`dot(N, CP6)`) | 未捕获(推测 (0,1,0)) |
| CP7.x/y/z | 环境梯度 offset / scale / base:`sat(d+0.15)*1.5+0.5` ∈ [0.5,2] | 0.15 / 1.5 / 0.5 |
| CP8.xyz / w | 深度边缘光颜色 / 强度 | 未捕获 |
| CP9.xy | 边缘光轴(世界或相机空间 xy),`rimDir = normalize(cross(camAxisZ, axis))` | (0,-1) |
| CP9.z | 边缘光颜色 `lerp(0.25, diffuseColor, CP9.z)` | 0 |
| CP9.w | 深度采样沿屏幕法线偏移量(×0.006 UV) | 0.4 |
| CP10.x | >0.5 用全局天气掩码 CP10.y 与水位 CP10.w,否则 per-object `Stripped_208.xy` | 0 |
| CP10.y | 打包 uint8x4 天气掩码 (雨湿, 水位使能, 常湿, 雪) | ~0 |
| CP10.z | 雨/雪三平面 UV 缩放 | 2.25 |
| CP10.w | 全局水位高度 | -100 |
| CP11.xyz | 角色专用"指向光源"方向 | (0.176,0.530,0.830) |
| CP11.w | ramp 输入 NdotL 偏移(仅 CP12.x=1 时生效) | -0.1 |
| CP12.x | 1 = 关闭逆光暗部抬亮与逆光边缘光,改用 CP11.w 偏移 | 未捕获 |
| CP12.y | 光颜色覆盖权重(同时改变受光侧环境项乘 lightColor) | 未捕获 |
| CP12.z | 点光源"角色灯层"门槛加数 | 未捕获 |
| CP12.w | >=0.5:环境不乘 `_EnvironmentGlobalParams0.x`、光强不乘 CustomData1.w、跳过雾(UI/展示模式) | 未捕获(捕获行为与 0 一致) |
| CP13.w | 各向异性高光总乘数 | 未捕获 |
| CP15.w | 0 = CP9.xy 为世界轴,1 = 相机 right/up 轴 | 未捕获 |

`_CharacterParams3/4` 未被本着色器引用(cbuffer 中被 strip,偏移 1760/1776)。

## 5. 使用到的全局常量与纹理

| 缓冲/寄存器 | 成员 | 用途 |
|---|---|---|
| TransformVariables b12 | `ViewMatrix` | 正交视向、rimAxis(行0/1)、屏幕法线;`InvViewMatrix` 列 2 -> camAxisZ;`ProjMatrix[1].y` 雨滴距离衰减;`WorldSpaceCameraPos_Internal`;`PrevCamPosRWS`(顶点) |
| ShaderVariablesGlobal b16 | `_ScreenSize.zw`,`_ScreenParams`,`_ZBufferParams.zw`,`_ProjectionParams.y`,`_unity_OrthoParams.w`,`_Time.x`(雨),`_GlobalMipBias`,`_FrameCount`(体积雾抖动) | 见上 |
| 同上 | `_ExposureWithMiscParams.x`(乘 ambientScale)、`.y`(输出前乘 rgb);`.z/.w` 未用 | 捕获 (1,1,1.6,0.1) |
| 同上 | `_EnvironmentGlobalParams0.x` | ambientScale 基值,捕获 0.2877 |
| 同上 | `_IVParam0.xyz/.w`,`_IVParam1.xyz`,`_IVParam2.y/z/w`,`_IVDefaultSHAr/g/b` | 辐照度体(捕获帧未执行) |
| 同上 | `_CharacterParams0,1,2,5,6,7,8,9,10,11,12,13,15` | 第 4 节 |
| 同上 | `_AtmosphereFogParams0..5`,`_ExponentialFogParams0..5`,`_VolumetricFogParams0..4`,`_BinningBufferOffsets.y` | 雾 / 光源分箱 |
| LightDataBuffer b14 | `DirectionalLightDirection.xyz`,`DirectionalLightCustomData1.rgb/w`,`PunctualLightData[2048]` | **未读偏移 16/32 的方向光颜色 (2.7476)**;角色用 CustomData1 = (1,1,1)*1.624 |
| ShadowData b15 | `_DirectionalShadowParams.x`(屏幕阴影强度),`_PunctualLightWorldToShadow/ShadowParams/ShadowParams2/ShadowTexelSize` | 无 CSM、无角色阴影矩阵读取 |
| LightBinningConstants b48 | `NumTilesX`,`NumZBinSlice`,`InvZBinSlice` | 点光源 tile/z-bin |
| LightCookieCB b50 | `_lightCookieData/_lightCookieMatrices` | 点光源 cookie |
| UnityPerDraw (space2) | `Stripped_0`(O2W),`Stripped_64.w` bit4 蒙皮,`Stripped_80.x` 蒙皮矩阵起点,`Stripped_208.xy` per-object 天气掩码/水位 | |
| t22 `_ScreenSpaceShadowMask` | `.r` 方向光阴影,`.g` 角色遮挡/自阴影 | Load 像素 |
| t46 `_CameraDepthTexture` | 深度边缘光、类型 3 点光 | LinearClamp |
| t27 `_PunctualLightShadowTexV2` | 点光源 PCF | LinearMirrorOnce (cmp) |
| t30-t35 IV clipmap A/B Lod0/1/3 | 环境 SH | A: LinearRepeat,B: LinearMirror |
| t36 `_IntegratedLightScattering` | 体积雾 froxel | LinearMirror |
| t39 `_CharacterSnowEffectTex` | 雪三平面 | LinearRepeat + bias |
| t29 `_LightCookie` | 点光源 cookie | LinearMirror |
| t51 `_GlobalBinningBuffer`,t18 `_VertexSkinMatrices` | 光源位掩码 / 蒙皮矩阵 | ByteAddressBuffer |

## 6. 未能解析的点

1. **b1 与 b3 哪张是 `_HN`、哪张是 `_P`**:两者同为 2048² BC7_UNORM,寄存器 (t5 `_BumpMap`, t2 `_MetallicGlossMap`) 与捕获 binding 序号不是同一编号体系(t6 `_BaseMap` = b6 成立,但 t5 ≠ b5),只能按内容配对。
2. `_HN` 若真是 RG/BA 分裂法线,本变体读到的是 `x=(A*R)*2-1, y=G*2-1`;需要用实际贴图像素验证 A 通道是否≈1,否则官方也在"错误"解包。
3. `_CharacterParams5/6/8/12/13/15`、`_DirectionalShadowParams.x`、`PerDraw.Stripped_208.xy` 的捕获值未提供;其中 CP6(环境梯度方向)、CP13.w(高光总乘数)、CP12.w(展示模式)直接影响亮度。
4. `ScreenSpaceShadowMask.g` 的生产者未确认(推测是角色投影/接触阴影 pass);它同时门控 litMask、边缘光、雪。
5. 雨滴涟漪分支(约 300 行程序化 hash)与点光源 PCF/cookie/LTC 细节只给出结构与输出,没有逐行还原;捕获帧下天气掩码≈0、无点光源命中时它们不改变结果。
6. `_CharacterParams10.y` 捕获值"~0"若严格非零,低 8 位任何非零值都会打开雨湿分支;需确认精确 bit pattern。
7. `_IVParam1.xyz`、`_IVParam2` 未给捕获值;由于 CP1.y=1,本帧不采样辐照度体,对复现无影响,但换场景(CP1.y=0)时需要。
