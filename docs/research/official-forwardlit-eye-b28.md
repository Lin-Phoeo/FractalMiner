# 官方 CharacterNPR_Eye ForwardLit 片元着色器还原(变体 b28)

来源:`_dump_1.5.3/.../characternpr/characternpr_eye/Sub0_Pass0_Fragment_b28.hlsl`(1134 行,SPIR-V-Cross 输出),
配套顶点 `Sub0_Pass0_Vertex_b28.hlsl`(同一 keyword 行,输出结构 TEXCOORD0..7 与片元输入完全一致),
属性/关键字来自 `characternpr_eye.shader`(Pass "ForwardLit",LightMode `ForwardCharacterOnly`,`#pragma target 5.0`,dxc)。
下文中所有数字、swizzle、clamp、pow 指数均按原码保留;`mad`/位运算已改写为普通算式。

本变体是 **iris(虹膜)专属**:没有法线贴图、没有 spec/metallic gloss mask、没有深度边缘 rim(无 `_CameraDepthTexture`/`_ScreenSize`/`_CharacterParams8/9`),
但有 **视差瞳孔折射(parallax pupil)**、**Matcap 采样**、以及 **EyeHighLightColor / EyeScatteringColor** 按 UV 圆盘与 alpha 通道调制的虹膜特殊项。

## 1. 变体识别

`characternpr_eye.shader:127`(顶点)/`:205`(片元)命中的组合(对比 `:120` 全 OFF 的 b25):

```
ON : SRP_INSTANCING_ON  HG_ENABLE_PER_OBJECT_MV  HG_ENABLE_SCREEN_SPACE_SHADOW_MASK
     _DIFF_RAMP_ON  _EYE_HIGHLIGHT  _MATCAP_ON
OFF: _EMISSION  _CUSTOMIZE_AVATAR  _SHADOW_LUT_TEX  BAKED_SKINNING_ANIMATION_TEXTURE
     VFX_CHARACTER_DISSOLVE  DITHER  _ALPHATEST_ON  _SPECULAR_NORMALMAP(本 shader 无此 keyword)
```

后果:
- 只有**一张** albedo 图 `_BaseMap`(同时承载 rgb 反照率与 **a = 瞳孔深度**);没有 `_BumpMap`、没有 `_MetallicGlossMap`、没有 `_LineMap`、没有 `_SpecRampMap`。
- 没有自发光、没有 LUT 阴影色、没有 VAT、没有 Dissolve、没有 Dither、没有 AlphaTest。
- `_EYE_HIGHLIGHT` 让 `EyeHighLightColor` 参与虹膜调制;`_MATCAP_ON` 打开 Matcap 采样。
- 阴影只来自 `_ScreenSpaceShadowMask.Load(...).r`(方向光阴影);**`.g` 未被读取**,所以 iris 没有 hair 那样的 `ssmG` 门控(litMask 直接取 ramp.a)。
- 没有深度边缘 rim:`_ScreenSize`、`_ScreenParams`、`_ZBufferParams`、`_CameraDepthTexture` 在本变体均未声明,`_CharacterParams8/9/15` 也不在 cbuffer 中。

### 纹理寄存器 -> 名称 -> 采样方式 -> 必然对应的贴图

| 寄存器 | HLSL 名 | 采样表达式 | 判据 | 本 iris 对应贴图 / 捕获 binding |
|---|---|---|---|---|
| t3,space1 | `_BaseMap` | `SampleBias(sampler_LinearClamp, uv0 - parallax, _GlobalMipBias)`,rgb*`_BaseColor`,a*`_BaseColor.a` | 唯一乘 BaseColor 的 sRGB 图;a 通道当作瞳孔深度 | 需参照 capture 纹理 binding 表(已知 UnityPerMaterial 色,未知 bN 序号) |
| t2,space1 | `_DiffRampMap` | `SampleLevel(sampler_LinearRepeat, float2(rampU,0.5),0)` 两次 | v 固定 0.5 的一维 ramp(u=受光,第二采样 u=dot(N,camAxisZ)) | 同上 |
| t1,space1 | `_MatcapTex` | `SampleBias(sampler_LinearRepeat, matcapUV, _GlobalMipBias)`,matcapUV 由 `_489`→view 空间法线 | 视线空间 matcap | 同上 |

> 注意:hair 文档里给出的 b1/b2/b3/b6 是 hair 的捕获 binding 序号,**eye 的已知捕获值只给了 4 个 UnityPerMaterial 色**(`_EyeScatteringColor`/`_EyeHighLightColor`/`_MatcapColor`/`_MatcapNormalScale`),没有给 `_BaseMap`/`_MatcapTex`/`_DiffRampMap` 的 bN 序号。三者都在 `space1`,寄存器 t1/t2/t3 已确定,具体哪张贴图命中需对照 `tifuluosi-front` 的纹理 binding 表。

Set0 全局纹理:`_ScreenSpaceShadowMask`(t22,Load 像素,仅 `.r`)、`_CharacterSnowEffectTex`(t39,仅雪分支)、`_PunctualLightShadowTexV2`(t27,仅点光源 PCF)、
`_IrradianceVolumeClipmapTexture{A,B}Lod{0,1,3}`(t30-t35,仅 CP1.y<0.5)、`_IntegratedLightScattering`(t36,体积雾)、`_LightCookie`(t29)。
**没有** `_CameraDepthTexture` / `_ScreenSize` / `_ScreenParams` / `_ZBufferParams`。

## 2. 输入插值器

顶点着色器输出(`_13.._20` + `_22`)-> 片元输入(`_3.._10` + `_12`):

| 语义 | 片元名 | 内容(由顶点 b28 推得) |
|---|---|---|
| TEXCOORD0 float2 | `uv0` | 顶点 slot1(float2)`* _BaseMap_ST.xy + _BaseMap_ST.zw` |
| TEXCOORD1 float3 | `positionRWS` | 世界坐标 − `_WorldSpaceCameraPos_Internal`(camera-relative) |
| TEXCOORD2 float3 | `normalWS` | 归一化世界法线(顶点支持 10:10:10 八面体压缩法线,`_5` 解包) |
| TEXCOORD3 float4 | `tangentWS` | xyz 归一化世界切线,w = 副切线符号(±1) |
| TEXCOORD4 float3 | `clipCur` | 当前帧非抖动裁剪坐标 `.xyw`(运动矢量),`gl_Position.xyw` |
| TEXCOORD5 float3 | `clipPrev` | 上一帧裁剪坐标 `.xyw`(`PrevNonJitteredViewNoTransProj` + rest pos) |
| TEXCOORD6 float3 | `restNormalOS` | 物体空间法线(顶点 `_19`,八面体或原始 `_9`),仅雪三平面用 |
| TEXCOORD7 float3 | `restPosOS` | 静止姿态位置(顶点 `_20` = 输入 `_8`,绑定姿态坐标),仅雪三平面 UV 用 |
| TEXCOORD8 uint (nointerp) | `instanceID` | 索引 `_SRP_UnityPerDraw_UnityPerDrawArray[256]` |
| SV_Position | `fragCoord` | `.xy` 像素坐标;`1/w` 经 main 翻转为 `w` 本身 = 线性视深 `eyeDepth` |
| SV_IsFrontFace | `isFront` | 背面法线翻转 |

**与 hair 的差异**:hair 有 TEXCOORD7=restTangentOS、TEXCOORD8=restPosOS 两个;eye 只有 TEXCOORD6/7 且分别是 restNormalOS / restPosOS,**没有独立 restTangentOS**(雪分支不需要切线框架)。顶点色 `COLOR0` 槽位承载八面体解码法线,未被片元用作颜色。

## 3. 片元着色器整洁重构

```hlsl
// ===== 0. 通用量 =====
float  eyeDepth  = 1.0 / fragCoord.w;                       // main 里 w 已被翻转为原 w,故这里 = 线性视深
float3 viewVec   = lerp(-positionRWS, ViewMatrix[2].xyz, _unity_OrthoParams.w);
float  viewDist  = sqrt(dot(viewVec, viewVec));             // _371
float3 V         = viewVec / viewDist;                     // _370
bool   skinned   = (asuint(PerDraw.Stripped_64.w) & 16u) != 0;
float4 row0,row1,row2;   // objectToWorld 三行:蒙皮时从 _VertexSkinMatrices[Stripped_80.x + {0,1,2}] 读,否则 PerDraw.Stripped_0[0..2]
float3x3 M_o2w   = float3x3(row0.xyz, row1.xyz, row2.xyz);  // mul(M_o2w, v): OS->WS ; mul(v, M_o2w): WS->OS
float3 positionWS = positionRWS + _WorldSpaceCameraPos_Internal.xyz;
float3 rootToPixelH = normalize(float3(positionWS.x - row0.w, 6.103515625e-05, positionWS.z - row2.w)); // 角色根到像素的水平方向
float3x3 TBN = float3x3(tangentWS.xyz, cross(normalWS, tangentWS.xyz) * tangentWS.w, normalWS);        // _467
float3 Nv  = normalize(normalWS) * (isFront ? 1.0 : ((-1.0) + (2.0 * _BackFaceNormalFlip)));            // _473 顶点法线
const float3 LUM = float3(0.2126729, 0.7151522, 0.0721750);

// ===== 1. UV 圆盘 / 视差瞳孔折射(parallax pupil)=====
float2 fracUV    = frac(uv0);
float2 centered  = fracUV - 0.5;
float  d2        = dot(centered, centered);
float  pupilMask = step(0.25, d2);                         // _402:1 = UV cell 边角(虹膜外环),0 = 圆心附近(瞳孔盘)
float  nLenInv   = 1.0 / length(normalWS);
float3  Vts = normalize(mul(float3x3(TBN[0]*nLenInv, TBN[1]*nLenInv, TBN[2]*nLenInv), V)); // 切线空间视线
float2 parallaxOff = Vts.xy * _ParallaxScale * float2(1.0, 0.25)
                   * smoothstep(0.25, 0.0500000007450580596923828125, d2);  // 仅圆心附近(瞳孔)才有折射偏移
float4 baseMap   = _BaseMap.SampleBias(sampler_LinearClamp, uv0 - parallaxOff, _GlobalMipBias); // 注意:LinearClamp
float3 albedo    = baseMap.rgb * _BaseColor.rgb;
float  alpha     = baseMap.a   * _BaseColor.a;             // a 即瞳孔深度 / 透明度
float3 shadowColor = lerp(dot(albedo * _ShadowColorBrightness, LUM).xxx,
                          albedo * _ShadowColorBrightness, _ShadowColorSaturation); // _451(无雪时透传给 _1156)

// ===== 2. Matcap 法线(由 UV 圆盘构造的"虹膜球面"法线)=====
float2 ndc       = fracUV * 2.0 - 1.0;                      // _478 UV 中心 -> [-1,1]
float3 sphereN; sphereN.xy = ndc; sphereN.z = max(1.000000016862383526387164645044e-16, sqrt(1.0 - clamp(dot(ndc, ndc), 0.0, 1.0))); // _479 球面法线
float3 mcRaw = float3(sphereN.xy * (-_MatcapNormalScale), sphereN.z);   // _489 (_MatcapNormalScale=1 -> 原样)
// 瞳孔盘(_402=0)用弯曲的虹膜法线;外环(_402=1)退化为几何法线(0,0,1)
float3 matcapNormalWS = normalize(mul(lerp(mcRaw * float3(-0.125, -0.125, 1.0), float3(0.0,0.0,1.0), pupilMask), TBN)); // _494
float2 pixel = fragCoord.xy;
float3 camAxisZ = mul((float3x3)InvViewMatrix, float3(0,0,1));  // _507 相机 +Z(指向观察者)

// ===== 3. 天气掩码(雪),来自 _CharacterParams10 或 per-object =====
uint  wmaskHi = asuint(_CharacterParams10.x > 0.5 ? _CharacterParams10.y : PerDraw.Stripped_208.x) >> 24u; // _521.w 为雪字节
float snowMask = (wmaskHi & 255u) * 0.0039215688593685626983642578125;  // _522 (=1/255)
float ambientScale = lerp(_EnvironmentGlobalParams0.x, 1.0, _CharacterParams12.w) * _ExposureWithMiscParams.x; // _530

// ===== 4. 环境光:辐照度体 clipmap + _IVDefaultSH 回退(与 hair 完全一致)====
float4 shDominant; float3 ambientRGB, ambientTint; float ambientPeak;
if (_CharacterParams1.y < 0.5) {
    // 三层 clipmap(LOD0/1/3,中心/半径/斜率同 hair §4),权重 w0=1-fade0,w1=fade0*(1-fade1),w3=fade1*(1-fadeOuter);
    // 每层 A=TexA.SampleLevel(LinearClamp,uvw,0)(rgb=各通道 L0 幅值),Bk=TexB.SampleLevel(LinearRepeat,uvB+k/3,0)(rgb*4-2=R/G/B 的 L1 方向);
    // shC = accC + float4(D.x*wDef, D.y*wDef+D.w*wDir*0.5, D.z*wDef, D.w*wDef+D.y*wDir*0.375),D=_IVDefaultSH{A,B,C}
    ambientRGB = max(float3(dot(shR,float4(N,1)), dot(shG,float4(N,1)), dot(shB,float4(N,1))), 0) * ambientScale; // N 此处为 matcapNormalWS
    float3 dir = normalize(shR.xyz*0.2126 + shG.xyz*0.7152 + shB.xyz*0.0722); dir.y = abs(dir.y);
    shDominant = float4(dir, 1.0);
    ambientPeak = max(max3(max(float3(dot(shR,shDominant), dot(shG,shDominant), dot(shB,shDominant)), 0)), 0) * ambientScale;
    // 色调:RGB->HSV, s' = min(s, lerp(0.7,0.35, smoothstep(0.45,0.35,|h-0.5|))*saturate(v)), v' = 2/(2-s')
    ambientTint = HSVtoRGB(h, s', v');
} else {                                   // 捕获帧走这里(_CharacterParams1.y = 1)
    shDominant = 0; ambientRGB = 1; ambientTint = _CharacterParams2.xyz; ambientPeak = ambientScale;
}

// ===== 5. 雪(程序化三平面,仅 snowMask - _DisableRainEffectOnMaterial > 0.01)=====
float3 N  = matcapNormalWS;                 // _1155 着色法线(默认 = matcapNormalWS)
float3 shadowDiffB = shadowColor;           // _1156
float3 albedoB     = albedo;                // _1157
float  metalOut    = _Metallic;             // _1158
if ((snowMask - _DisableRainEffectOnMaterial) > 0.00999999977648258209228515625) {
    // 三平面坐标 restPosOS(.xzy*(1,1,-1) 蒙皮时)*_CharacterParams10.z;权重 pow(max(|restNormalOS|-0.2,0),3) 归一;
    // snowTex = 三平面 _CharacterSnowEffectTex.SampleBias(...).xy*2-1 扰动法线;
    // coverage = smoothstep(2-c(2-c), 2.35-c(2-c), 0)*isFront;N = 扰动法线;shadowDiffB = lerp(shadowColor,0.308,coverage);
    // albedoB = lerp(albedo, 0.88, coverage);metalOut = lerp(_Metallic,0,coverage)
    // 捕获帧 snowMask≈0 -> 走 else
} else {
    N = matcapNormalWS; shadowDiffB = shadowColor; albedoB = albedo; metalOut = _Metallic;
}
float  metalK     = 0.959999978542327880859375 - (metalOut * 0.959999978542327880859375); // _1160 = 0.96*(1-metal)
float3 diffuseColor = albedoB * metalK;     // _1161
float3 shadowDiff   = shadowDiffB * metalK; // _1162

// ===== 6. 运动矢量 (SV_Target1) =====
float2 mv = clipCur.xy / max(clipCur.z, 9.9999999392252902907785028219223e-09)
          - clipPrev.xy / max(clipPrev.z, 9.9999999392252902907785028219223e-09);
mv.y = -mv.y;
float2 mvEnc = sqrt(sqrt(abs(mv * 0.5))) * sign(mv) * 0.5 + 0.5;
float4 target1 = float4(mvEnc, 1.0, 0.4000000059604644775390625);

// ===== 7. 光方向 / 光颜色 / 阴影 / 虹膜特殊项 =====
float3 L  = lerp(-DirectionalLightDirection.xyz, _CharacterParams11.xyz, _CharacterParams1.w);   // 捕获:CP1.w=1 -> L = CP11.xyz
float3 Lh = normalize(float3(L.x, 6.103515625e-05, L.z));
float3 lightColor  = lerp(DirectionalLightCustomData1.rgb, _CharacterParams5.rgb, _CharacterParams12.y);
float3 lightColorI = lightColor * lerp(DirectionalLightCustomData1.w, 1.0, _CharacterParams12.w);  // 捕获:(1,1,1)*1.624
float3 Lhws = mul(M_o2w, normalize(mul(L, M_o2w)).xzy0).xyz;  // _1233 水平方向光(物体空间去 y 再回世界)
float  shadowDir = lerp(lerp(1.0, _ScreenSpaceShadowMask.Load(int3(pixel,0)).x, _DirectionalShadowParams.x), 1.0, _CharacterParams1.z); // 1=受光
float3 shadowDeep  = shadowDiff * _CharacterParams0.z;        // _1261 (×0.65)
float3 shadowDeep2 = shadowDeep * 0.64999997615814208984375;  // _1262
// —— 虹膜核心:HighLight 按瞳孔盘、Scattering 按 alpha ——
float3 eyeHighLight  = _EyeHighLightColor.xyz * pupilMask;    // _1271
float3 eyeScattering = _EyeScatteringColor.xyz * alpha;       // _1278
float3 eyeDiffuse = diffuseColor * (((1.0 - pupilMask).xxx + eyeHighLight)   // 圆心(_402=1)偏 HighLightColor
                                   * ((1.0 - alpha).xxx + eyeScattering));    // alpha 高(_442=1)偏 ScatteringColor

// ===== 8. 漫反射 ramp =====
float4 ramp  = _DiffRampMap.SampleLevel(sampler_LinearRepeat,
                  float2((clamp(dot(N, normalize(Lhws)) + _CharacterParams11.w * _CharacterParams12.x, -1.0, 1.0) * 0.5) + 0.5, 0.5), 0); // _1295
float  litMask   = min(1.0, ramp.w);                          // _1320 = ramp.a(iris 无 ssmG 门控)
float  rampChroma = max3(ramp.rgb) - min3(ramp.rgb);          // _1305
float  rampV = _DiffRampMap.SampleLevel(sampler_LinearRepeat,
                  float2(dot(N, camAxisZ) * 0.5 + 0.5, 0.5), 0).w;        // _1314
float3 ambientGrad = (clamp(dot(normalize(float3(matcapNormalWS.x, 6.103515625e-05, matcapNormalWS.z)), // _534 水平投影
                              _CharacterParams6.xyz) + _CharacterParams7.x, 0.0, 1.0) * _CharacterParams7.y + _CharacterParams7.z).xxx
                    * lerp(ambientTint, 1.0, _CharacterParams1.y * litMask);  // _1324

// ===== 9. 光能量项 =====
float3 lightTerm = lerp(
    ambientGrad * lerp(min(lerp(0.64999997615814208984375, 1.0, ambientPeak), 1.5),
                       clamp(ambientPeak, 1.25, 1.75), _CharacterParams1.x) * _CharacterParams0.w,
    (lerp(dot(lightColorI, LUM).xxx, lightColorI, litMask)
       + (ambientGrad * clamp(ambientPeak, 0.0, 1.5))
          * ((1.0 - _CharacterParams12.y) + (lightColor * _CharacterParams12.y))) * _CharacterParams0.y,
    shadowDir);                                               // _1350
float3 baseSel = lerp(lerp(lerp(dot(shadowDeep2, LUM).xxx, shadowDeep2, 1.2), shadowDeep, clamp(rampV + litMask, 0.0, 1.0)),
                      eyeDiffuse, litMask);                   // _1351
float3 rampTinted = baseSel * ((1.0 - rampChroma) + ramp.rgb * rampChroma);  // _1357
float3 diffuseTerm = lerp(lerp(shadowDeep, eyeDiffuse, rampV),
                          rampTinted * clamp(dot(baseSel, LUM) / max(dot(rampTinted, LUM), 0.001), 0.0, 1.5),
                          shadowDir);                         // _1366
float  litBlend  = lerp(rampV, litMask, shadowDir);          // _1372

// ===== 10. Matcap 采样 =====
float2 matcapUV = normalize(mul((float3x3)ViewMatrix, mul(mcRaw, TBN))).xy * 0.5 + 0.5; // _1395 用原始球面法线 mcRaw
float4 matcap = _MatcapTex.SampleBias(sampler_LinearRepeat, matcapUV, _GlobalMipBias);
float  premul = (1.0 - _AlphaPremultiply) + (alpha * _AlphaPremultiply);  // _1411
float3 color = lightTerm * diffuseTerm * premul
             + (matcap.rgb * _MatcapColor.w + _MatcapColor.rgb * matcap.a)  // matcap 与 MatcapColor 的 rgb/a 交叉混合
               * (lightTerm * ((litBlend * 0.5 + 0.5) * lerp(_CharacterParams0.z, 1.0, litBlend))); // _1413

// ===== 11. 饱和度提升 + 逆光菲涅尔边缘光(无深度 rim)+ 虹膜高光叠加 =====
float lum = dot(color, LUM);  float sBoost = clamp(lum - 0.5, 0.0, 0.5);
float NdotL_mc = dot(Lh, N);  float NdotV = dot(V, N);  float shInv = 1.0 - shadowDir;
float3 edgeLight = lerp(ambientRGB / max(max3(ambientRGB) * 0.5, 1.0), lightColorI, shadowDir)
    * saturate(lerp(dot(shDominant.xyz, N) * shDominant.w, -NdotL_mc * (NdotL_mc * 0.5 - 1.0) + 0.5, shadowDir))
    * ((shInv + clamp(-dot(Lh.xz, normalize(camAxisZ.xz)), 0.0, 1.0) * shadowDir) * (1.0 - _CharacterParams12.x))
    * smoothstep(0.6, 0.8, 1.0 - abs(NdotV))
    * (shInv + smoothstep(0.1, 0.04, dot(diffuseColor, LUM)) * shadowDir)
    * max(0.15.xxx, diffuseColor);                           // _1479 前半
float3 eyeSpec = (albedo * _CharacterParams13.x + eyeHighLight * _CharacterParams13.y + eyeScattering * _CharacterParams13.z) * premul; // _1479 后半
float3 color2 = lerp(lum.xxx, color, 1.0 + sBoost * sBoost) + edgeLight + eyeSpec;  // _1479

// ===== 12. 点光源(tile 32px × z-bin,_GlobalBinningBuffer)=====
// 与 hair §13 同一套共享库,仅本变体映射:N = matcapNormalWS(_1155),diffuseColor = _1161,shadowDiff = _1162,
// diffuseTerm 源 = _1366/_1370.xyz,顶点法线 = Nv,rootToPixelH = _462。
// 每光:PunctualLightData[i*8+k]。k=5.w 位1 -> 盒形衰减;k=3.w 类型:16 跳过,(k=3.z + CP12.z)<0.5 跳过(角色灯层)。
//   距离衰减:k=1.w 为 1/range,k=6.w 或 2*k=4.y 为指数(<0 用 (1-(d²r²)²)²/(d²+1));聚光 cone 由 k=2.xy 八面体解码;
//   管状灯 k=2.z>0 走 LTC;cookie k=7.w>=0。阴影:k=3.x 索引 _PunctualLightWorldToShadow,3x3 tent PCF 九次 SampleCmpLevelZero(_PunctualLightShadowTexV2, LinearMirrorOnce)。
//   类型 0:diffuse = lightRGB * ((1-k4.y)+k4.y/max(1,max3(lightRGB*atten)*lerp(0.75,0.5,shInv))) * lerp(0.25*k4.x,1,sat(NdotL_p+0.5)),
//           color += diffuse*atten * lerp(diffuseTerm, diffuseTerm, sat(NdotL_p)) * premul + diffuse*atten * spec_p * sat(NdotL_p)
//   类型 1:NdotL_p = sat(clamp(NdotL_p + k4.x,-1,1)) * shadow_p;色 = lerp(shadowDiff*k4.y, diffuseColor, NdotL_p)
//   类型 3:深度边缘灯(用 rootToPixelH 与 camAxisZ),NdotL_p = sat(dot(N, -normalize(cross(camAxisZ, cross(camAxisZ, Ldir))))),色 = lerp(0.5, diffuseColor, k4.y),无高光
//   spec_p(类型≠3):同 hair 但 H = normalize(Ldir + V);× 0(*iris 无各向异性高光,此处 spec_p 实际不参与额外高光增益)
float3 colorFinal = color2;   // _1505 起始 = _1479,循环内累加 _2266*_2265*lerp(_2269,_2268,_2267)*premul

// ===== 13. VFX 调色、曝光、雾、输出 =====
if (_EnableVFXColorAdjustment > 0.5)
    colorFinal = lerp(lerp(0.5.xxx, lerp(dot(colorFinal,LUM).xxx, colorFinal, _ColorAdjustmentSaturation), _ColorAdjustmentContrast) * _ColorAdjustmentBrightness,
                      _ColorAdjustmentColorBlend.rgb, _ColorAdjustmentColorBlend.a)
              + _ColorAdjustmentRimColor.rgb * smoothstep(1.0 - _ColorAdjustmentRimWidth, 1.0, 1.0 - saturate(NdotV)) * _ColorAdjustmentRimIntensity;
float4 outColor = float4(colorFinal * _ExposureWithMiscParams.y, (_SurfaceType == 1.0) ? alpha : 1.0); // _2326
if (_CharacterParams12.w < 0.5) {
    // 大气雾 / 指数高度雾 / 体积雾:公式与 hair §14 完全相同(_AtmosphereFogParams0..5,_ExponentialFogParams0..5,_VolumetricFogParams0..4)。
    // 体积雾 _IntegratedLightScattering.SampleLevel(LinearRepeat, froxel uv) 与 exp 雾按 froxel.a 组合。
    // 捕获帧 CP12.w 行为与 0 一致(未提供精确值,但天气掩码≈0、无点光源,雾不改变虹膜结果)。
}
SV_Target0 = outColor;   SV_Target1 = target1;
```

## 4. `_CharacterParamsN` 用途表

| 分量 | 用法推断 | 捕获值 |
|---|---|---|
| CP0.y | 受光侧 lightTerm 总乘数 | 1(推测,同 hair) |
| CP0.z | 阴影色深度系数(`shadowDeep = shadowDiff*CP0.z` ×0.65)以及 Matcap 可见度 `lerp(CP0.z,1,litBlend)` | 0.65 |
| CP0.w | 阴影侧 lightTerm 总乘数 | 0.9(推测) |
| CP1.x | 环境峰值映射选择:0 -> `min(lerp(0.65,1,peak),1.5)`,1 -> `clamp(peak,1.25,1.75)` | 0 |
| CP1.y | <0.5 采样辐照度体;>=0.5 用平坦环境(ambientRGB=1, tint=CP2);同时是 `lerp(tint,1,CP1.y*litMask)` 权重 | 1 |
| CP1.z | 1 = 忽略屏幕空间方向光阴影 | 0 |
| CP1.w | 1 = 用 CP11.xyz 替代 `-DirectionalLightDirection` 作为光方向 | 1 |
| CP2.xyz | 平坦环境色调(仅阴影侧,受光侧被 lerp 到 1) | 未捕获(同 hair 推测 (0.849,0.896,1.151)) |
| CP5.xyz | 光颜色覆盖(权重 CP12.y) | 未捕获 |
| CP6.xyz | 环境梯度方向(`dot(水平 matcap 法线, CP6)`) | 未捕获(推测 (0,1,0)) |
| CP7.x/y/z | 环境梯度 offset / scale / base:`sat(d+CP7.x)*CP7.y+CP7.z` ∈ [0.5,~2] | 0.15 / 1.5 / 0.5(推测) |
| CP10.x | >0.5 用全局天气掩码 CP10.y,否则 per-object `Stripped_208.x` | 0 |
| CP10.y | 打包 uint8x4 天气掩码,高 8 位 = 雪(`>>24 & 255`) | ~0 |
| CP10.z | 雪三平面 UV 缩放 | 2.25(推测) |
| CP10.w | 本变体片元未直接读取 | 未捕获 |
| CP11.xyz | 角色专用"指向光源"方向 | (0.176,0.530,0.830) |
| CP11.w | ramp 输入 NdotL 偏移(仅 CP12.x=1 时生效) | -0.1(推测) |
| CP12.x | 1 = 关闭逆光菲涅尔边缘光(`*(1-CP12.x)`) | 未捕获 |
| CP12.y | 光颜色覆盖权重(同时改变受光侧环境项乘 lightColor) | 未捕获 |
| CP12.z | 点光源"角色灯层"门槛加数 | 未捕获 |
| CP12.w | >=0.5:环境不乘 `_EnvironmentGlobalParams0.x`、光强不乘 CustomData1.w、跳过雾(UI/展示模式) | 未捕获(捕获行为与 0 一致) |
| CP13.x | 虹膜高光中 **albedo 基项**强度(`albedo*CP13.x`) | 未捕获 |
| CP13.y | 虹膜高光中 **EyeHighLightColor** 强度(`eyeHighLight*CP13.y`) | 未捕获 |
| CP13.z | 虹膜高光中 **EyeScatteringColor** 强度(`eyeScattering*CP13.z`) | 未捕获 |
| CP13.w | 本变体未使用(无各向异性高光) | — |

`_CharacterParams3/4`(Stripped_1760/1776)未被引用;`_CharacterParams8/9/14/15` **不在本变体 cbuffer 中**(iris 没有深度 rim 与边缘光轴)。

## 5. 使用到的全局常量与纹理

| 缓冲/寄存器 | 成员 | 用途 |
|---|---|---|
| TransformVariables b12 | `ViewMatrix` | 正交视向、matcap 法线投影(行0/1/2)、camAxisZ;`InvViewMatrix` 列 2 -> camAxisZ;`WorldSpaceCameraPos_Internal`;`PrevCamPosRWS`(顶点) |
| ShaderVariablesGlobal b16 | `_ScreenSize`/`_ScreenParams`/`_ZBufferParams` | **本变体未声明**(无深度 rim) |
| 同上 | `_ExposureWithMiscParams.x`(乘 ambientScale)、`.y`(输出前乘 rgb);`.z/.w` 未用 | 捕获 (1,1,1.6,0.1) |
| 同上 | `_EnvironmentGlobalParams0.x` | ambientScale 基值,捕获 0.2877 |
| 同上 | `_GlobalMipBias` | 所有 SampleBias |
| 同上 | `_IVParam0/1/2`、`_IVDefaultSHAr/g/b` | 辐照度体(捕获帧未执行,CP1.y=1) |
| 同上 | `_CharacterParams0,1,2,5,6,7,10,11,12,13` | 第 4 节 |
| 同上 | `_AtmosphereFogParams0..5`,`_ExponentialFogParams0..5`,`_VolumetricFogParams0..4` | 雾(CP12.w<0.5 时) |
| LightDataBuffer b14 | `DirectionalLightDirection.xyz`,`DirectionalLightCustomData1.rgb/w`,`PunctualLightData[2048]` | 角色用 CustomData1 = (1,1,1)*1.624 |
| ShadowData b15 | `_DirectionalShadowParams.x`(屏幕阴影强度);`_PunctualLightWorldToShadow/ShadowParams/ShadowTexelSize` | 无 CSM |
| LightBinningConstants b48 | `NumTilesX`,`NumZBinSlice`,`InvZBinSlice` | 点光源 tile/z-bin |
| LightCookieCB b50 | `_lightCookieData/_lightCookieMatrices` | 点光源 cookie |
| UnityPerMaterial b0,space1 | `_BaseColor`,`_ShadowColorBrightness/Saturation`,`_Metallic`,`_BackFaceNormalFlip`,`_AlphaPremultiply`,`_SurfaceType`,`_EnableVFXColorAdjustment` + VFX 调色 7 项 | 见下 |
| 同上(虹膜特有) | `_EyeScatteringColor` = (1.51309, 2.72357, 4.28709, 1) | 散射色(蓝紫偏),按 alpha 调制 |
| 同上 | `_EyeHighLightColor` = (4.23709, 2.90607, 3.34975, 1) | 高光色(粉白),按瞳孔盘调制 |
| 同上 | `_MatcapColor` = (0, 0.21636, 0.601, 0.54902) | matcap rgb/a 交叉混合 |
| 同上 | `_MatcapNormalScale` = 1 | 虹膜球面法线 xy 缩放 |
| 同上 | `_ParallaxScale`(c12.y,默认 0.1,Range 0..0.15) | 瞳孔视差折射强度 |
| t1 `_MatcapTex`(space1) | matcap 查找 | LinearRepeat + bias |
| t2 `_DiffRampMap`(space1) | 一维漫反射 ramp | LinearRepeat, v=0.5 |
| t3 `_BaseMap`(space1) | albedo(rgb)+ 瞳孔深度(a) | **LinearClamp** + bias(注意:hair 用 LinearRepeat) |
| t22 `_ScreenSpaceShadowMask` | `.r` 方向光阴影(仅) | Load 像素 |
| t39 `_CharacterSnowEffectTex` | 雪三平面 | LinearClamp + bias(仅雪分支) |
| t27 `_PunctualLightShadowTexV2` | 点光源 PCF | LinearMirrorOnce(cmp) |
| t30-t35 IV clipmap A/B Lod0/1/3 | 环境 SH | A: LinearClamp,B: LinearRepeat |
| t36 `_IntegratedLightScattering` | 体积雾 froxel | LinearRepeat |
| t29 `_LightCookie` | 点光源 cookie | LinearRepeat |
| t51 `_GlobalBinningBuffer`,t18 `_VertexSkinMatrices` | 光源位掩码 / 蒙皮矩阵 | ByteAddressBuffer |

## 6. 未能解析的点

1. **`_BaseMap`/`_MatcapTex`/`_DiffRampMap` 的捕获 bN 序号未给**:已知只提供了 4 个 UnityPerMaterial 色,没有 hair 那样配套的纹理 binding 序号。三者寄存器(t1/t2/t3,space1)确定,具体贴图命中需对照 `tifuluosi-front-20260917` 的纹理 binding 表。
2. **`_MatcapTex` 采样用 `mcRaw`(原始球面法线)而非 `_494`(TBN+lerp 后的 matcap 法线)**:两者在瞳孔盘处差别明显(前者带 `-0.125` 偏置的弯曲法线,后者外环退化为几何法线)。官方此处特意用未 lerp 的 `mcRaw`,意味着 matcap 贴图始终反映"虹膜球面"视角,与着色法线 `_494` 解耦,原因待确认。
3. **`_CharacterParams5/6/7/12/13` 与 `_DirectionalShadowParams.x` 捕获值未给**:其中 CP6(环境梯度方向)、CP13.xyz(虹膜高光三路强度)、CP12.x(逆光边缘开关)直接影响虹膜亮度与高光,是复现关键未知数。
4. **`_EyeScatteringColor` 为何乘 `alpha`(`_442`)**:baseMap 的 a 通道在 iris 里被当作"瞳孔深度/透明度"。capture 值 `(1.513, 2.723, 4.287)` 是偏蓝的散射光,在 alpha 高(瞳孔中心)处显现。需确认 baseMap.a 在 tifuluosi 贴图中的实际语义(是瞳孔镂空还是角膜厚度)。
5. **`pupilMask = step(0.25, d2)` 基于 `frac(uv0)`**:即假设 iris 贴图按 UV cell 平铺、每格中心是瞳孔。若实际贴图不是平铺(单眼一张、瞳孔不在 cell 中心),该圆盘掩码会错位。需对照实际 UV 布局确认。
6. **雪/雨分支(约 80 行程序化三平面)与点光源 PCF/cookie/LTC** 只给出结构,未逐行还原;捕获帧天气掩码≈0、无点光源命中,不改变结果(同 hair)。
7. **`_CharacterParams10.z`(雪三平面 UV 缩放)与 CP10.w**:片元只用了 `CP10.y>>24`(雪)与 `CP10.z`(三平面缩放);CP10.x 选择全局/per-object 天气源,捕获=0(走 per-object `Stripped_208.x`)。具体值未给。
8. **逆光边缘光没有 hair 的"屏幕法线深度 rim"**:本变体 cbuffer 中确实无 `_CharacterParams8/9` 与 `_ScreenSize`/`_CameraDepthTexture`,确认 iris 不做屏幕空间深度边缘光,与 hair 的结构性差异需在下个 pass(如 GBuffer/Depth)里单独处理。
