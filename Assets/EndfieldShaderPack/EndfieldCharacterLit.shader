// ============================================================
//  EndfieldCharacterLit.shader
//  对齐终末地官方 HGRP/CharacterNPR 的属性命名与 feature 开关，
//  运行在 Unity 2022.3 LTS / URP 14 上(官方为 HG 自研 SRP，
//  本 shader 用 URP 光照适配角色材质逻辑)。
//
//  属性名以游戏 material JSON (M_actor_typhoea_*.json) 为准，
//  这样 EndfieldMaterialImporter 可把游戏原始参数 1:1 喂进来。
//
//  已还原的官方算法(材质层面):
//    - 法线 _UseBumpMap + _BumpScale
//    - 金属/光泽 _UseMetallicGlossMap + _MetallicGlossMap(R:A smooth)
//    - 自发光 _UseEmission + _EmissionMap/_EmissionColor/_EmissionBrightness
//    - 漫反射/高光 ramp _UseDiffRampMap(_DiffRampMap) / _UseSpecRampMap(_SpecRampMap)
//    - 颜色 LUT(皮肤 SSS) _UseShadowLutTex + _ShadowLutTex + 明度/饱和度
//    - 重阴影 _CharacterHeavyShadow*  /  假菲涅尔 _FakeFresnel*
//    - Stylized Fresnel _EnableStylizedFresnel + _StylizedFresnel*
//    - 清漆 _ClearCoat + _ClearCoatMask
//    - 视差 _UseParallax + _ParallaxTex/_ParallaxScale
//    - 头发 Kajiya-Kay 各向异性(_Anisotropy* 旧版接口)
//    - 眼睛 Matcap _UseMatcap + _MatcapTex
//    - 色彩调节 _ColorAdjustment*(brightness/contrast/saturation/rim)
//    - 描边 _EnableOutline + _Outline*(亮度/饱和度/遮罩/平滑法线)
//
//  法线说明：终末地法线为 10bit×3 有符号 + 1bit 符号的单 float
//  压缩格式，需先经 EndfieldNormalDecompress.cs 还原为标准切线
//  空间 RGB 法线贴图，再挂到 _BumpMap。
// ============================================================
Shader "Endfield/CharacterLit"
{
    Properties
    {
        // ---- 基础 / 混合 ----
        [MainTexture] _BaseMap ("Albedo", 2D) = "white" {}
        _BaseColor ("Color", Color) = (1,1,1,1)
        [Enum(Cloth,0,Skin,1,Hair,2,Eye,3)] _MaterialFamily ("Material Family", Float) = 0
        [Enum(Final,0,Albedo,1,Normal,2,MetalOrTangentBlend,3,SpecularMask,4,ShadowMask,5,Smoothness,6)] _DebugView ("Diagnostic View", Float) = 0
        [Enum(Opaque, 0, Transparent, 1)] _SurfaceType ("Surface Type", Float) = 0
        [Enum(Alpha, 0, Additive, 1, Premultiply, 4)] _BlendMode ("Blend Type", Float) = 0
        [Enum(Off, 0, On, 1)] _TransparentDepthWrite ("Transparent Depth Write", Float) = 1
        [Enum(Both, 0, Back, 1, Front, 2)] _Cull ("Render Face", Float) = 2
        [ToggleUI] _BackFaceNormalFlip ("Back Face Normal Flip", Float) = 0
        [HideInInspector] _SrcBlend ("__src", Float) = 1
        [HideInInspector] _DstBlend ("__dst", Float) = 0
        [HideInInspector] _AlphaSrcBlend ("__alphaSrc", Float) = 1
        [HideInInspector] _AlphaDstBlend ("__alphaDst", Float) = 0
        [HideInInspector] _ZTest ("__zw", Float) = 4
        [HideInInspector] _ZWrite ("__zw", Float) = 1
        [Toggle(_ALPHATEST_ON)] _EnableAlphaTest ("Alpha Test", Float) = 0
        _AlphaClipThreshold ("Clip Threshold", Range(0,1)) = 0.5

        // ---- 法线 ----
        [Toggle(_NORMALMAP)] _UseBumpMap ("Use NormalMap", Float) = 0
        _BumpScale ("Normal Scale", Float) = 1
        _BumpMap ("Normal Map", 2D) = "bump" {}

        // ---- PBR 金属/光泽 ----
        [Toggle(_METALLICSPECGLOSSMAP)] _UseMetallicGlossMap ("Use MetallicGlossMap", Float) = 0
        _Metallic ("Metallic", Range(0,1)) = 0
        _Specular ("Specular Scale", Range(0,1)) = 1
        _Smoothness ("Smoothness", Range(0,1)) = 0.5
        _MetallicGlossMap ("RGBA: Metallic/Spec/Shadow/Smooth", 2D) = "white" {}
        _OcclusionStrength ("Occlusion Strength", Range(0,1)) = 1

        // ---- 自发光 ----
        [Toggle(_EMISSION)] _UseEmission ("Use Emission", Float) = 0
        _EmissionColor ("Emission Color", Color) = (0,0,0,1)
        _EmissionBrightness ("Emission Brightness", Float) = 1
        _EmissionMap ("Emission", 2D) = "black" {}

        // ---- NPR ramp ----
        [Toggle(_DIFF_RAMP_ON)] _UseDiffRampMap ("Diffuse Ramp", Float) = 0
        _DiffRampMap ("Diffuse Ramp", 2D) = "white" {}
        [Toggle(_SPEC_RAMP_ON)] _UseSpecRampMap ("Specular Ramp", Float) = 0
        _SpecRampMap ("Specular Ramp", 2D) = "white" {}
        [ToggleUI] _SpecRampIridescentMode ("Spec Ramp Iridescent Mode", Float) = 0

        // ---- 阴影塑形 + 颜色 LUT(皮肤 SSS) ----
        _SceneShadowCenter ("Scene Shadow Center", Range(-1,1)) = 0.0
        _SceneShadowSharpness ("Scene Shadow Sharpness", Range(-1,1)) = 0.1
        _HalfLambertShadowCenter ("Half Lambert Shadow Center", Range(-1,1)) = 0.0
        _HalfLambertShadowSharpness ("Half Lambert Shadow Sharpness", Range(-1,1)) = 0.1
        [Toggle(_SHADOW_LUT_TEX)] _UseShadowLutTex ("Use Shadow Color LUT Tex", Float) = 0
        _ShadowLutTex ("Shadow Color LUT", 2D) = "white" {}
        _ShadowColorBrightness ("Shadow Color Brightness", Range(0,1)) = 0.5
        _ShadowColorSaturation ("Shadow Color Saturation", Range(0,2)) = 1
        _SkinRimOff ("Skin Rim Off", Range(0,1)) = 1
        _SkinRimOffScale ("Skin Rim Off Scale", Range(0,2)) = 0.8
        _FaceRimOffScale ("Face Rim Off Scale", Range(0,2)) = 1
        _SDFRimColor ("SDF Rim Color", Color) = (1,1,1,1)

        // ---- 重阴影(服装) ----
        _CharacterHeavyShadow ("Heavy Shadow", Range(0,1)) = 0
        [ToggleUI] _EnableLegacyShaping ("Legacy Shadow/Fresnel (not in 1.5.3 schema)", Float) = 0
        _CharacterHeavyShadowInt ("Heavy Shadow Intensity", Range(0,2)) = 0.52
        _CharacterHeavyShadowColor ("Heavy Shadow Color", Color) = (0.6,0.69,0.86,1)
        _CharacterHeavyShadowBackFaceFade ("Heavy Shadow BackFace Fade", Range(0,1)) = 1
        _CharacterHeavyShadowBackFaceFadeRange ("Heavy Shadow BackFace Fade Range", Range(0,1)) = 0.2

        // ---- 假菲涅尔(服装边缘) ----
        _FakeFresnel ("Fake Fresnel", Range(0,1)) = 0
        _FakeFresnelIntensity ("Fake Fresnel Intensity", Range(0,5)) = 2.42
        _FakeFresnelRange ("Fake Fresnel Range", Range(0,1)) = 0.486
        _FakeFresnelFade ("Fake Fresnel Fade", Range(0,1)) = 0.482
        _FakeFresnelColor ("Fake Fresnel Color", Color) = (1,1,1,1)
        [ToggleUI] _FakeFresnelWithAlbedo ("Fake Fresnel With Albedo", Float) = 0

        // ---- Stylized Fresnel ----
        [Toggle(_STYLIZED_FRESNEL)] _EnableStylizedFresnel ("Stylized Fresnel", Float) = 0
        _StylizedFresnelColor ("Color (A = Emission)", Color) = (0,0,0,0)
        _StylizedFresnelPow ("Pow", Range(0,10)) = 2
        _StylizedFresnelAmount ("Amount", Float) = 2
        _StylizedFresnelNoiseMap ("Noise Tex", 2D) = "white" {}
        _StylizedFresnelNoiseSpeed ("Noise Speed", Float) = 0
        _StylizedNoiseContrast ("Noise Contrast", Range(0,10)) = 1

        // ---- 清漆 Clear Coat ----
        [Toggle(_CLEARCOAT)] _ClearCoat ("ClearCoat Effect", Float) = 0
        _ClearCoatMask ("ClearCoat Mask", 2D) = "white" {}
        _ClearCoatColor ("ClearCoat Color", Color) = (1,1,1,1)
        _ClearCoatSmoothness ("ClearCoat Smoothness", Range(0,1)) = 0.95
        _ClearCoatMetallic ("ClearCoat Metallic", Range(0,1)) = 0
        [Enum(Vertex, 0, Texture, 1)] _ClearCoatNormalMode ("ClearCoat Normal", Float) = 0

        // ---- 视差 Parallax(布料流动) ----
        [Toggle(_PARALLAX_MAP)] _UseParallax ("Use Parallax", Float) = 0
        _ParallaxTex ("Parallax Tex", 2D) = "white" {}
        [ToggleUI] _ParallaxUseNormal ("Parallax Use Normal Map", Float) = 0
        _ParallaxMarchNum ("Parallax March Num", Range(1,5)) = 3
        _ParallaxScale ("Parallax Scale", Range(0,1)) = 0.5
        [HDR] _ParallaxColor ("Parallax Color", Color) = (0,0,0,1)

        // ---- 头发：split normal(RG 漫反射 / BA 高光发丝法线) ----
        [ToggleUI] _UseSpecBumpMap ("Split Diffuse/Specular Normal", Float) = 0
        _SplitNormalMap ("Hair Normal Map", 2D) = "bump" {}
        _SpecBumpScale ("Spec Bump Scale", Float) = 1

        // ---- 头发：Kajiya-Kay + 发丝线 ----
        [Toggle(_ANISOTROPY_SPECULAR_ON)] _UseAnisotropy ("Use Anisotropy", Float) = 0
        [ToggleUI] _AnisotropyUseGeometryTangent ("Use Geometry Tangent", Float) = 1
        _AnisotropyDirectionMain ("Anisotropy Direction Main", Range(-1,1)) = 0
        _AnisotropyIntensityMultiplier ("Anisotropy Intensity Multiplier", Range(0,2)) = 1
        _AnisotropyDirectionAdditional ("Anisotropy Direction Additional", Range(-1,1)) = 0
        _AnisotropyOffsetAdditional ("Anisotropy Offset Additional", Range(-1,1)) = 0
        _AnisotropyColorAdditional ("Anisotropy Color Additional", Color) = (0.2,0.2,0.2,1)

        // (旧版头发接口，Typhoeus hair 材质沿用)
        _Anisotropy ("Legacy Anisotropy", Range(0,1)) = 0
        _AnisotropyDirX ("Legacy Anisotropy Dir X", Range(-1,1)) = 0
        _AnisotropyValue ("Legacy Anisotropy Value", Range(0,1)) = 0.495
        _AnisotropyValue2 ("Legacy Anisotropy Value2", Range(0,1)) = 0.22
        _AnisotropyIntensity ("Legacy Anisotropy Intensity", Range(0,3)) = 1
        _AnisotropyEdgeFade ("Legacy Anisotropy Edge Fade", Range(0.01,10)) = 1
        _AnisotropyRange2 ("Legacy Anisotropy Range2", Range(0,1)) = 0.7
        _AnisotropyColor ("Anisotropy Color", Color) = (1,1,1,1)
        [HDR] _AnisotropyColor2 ("Anisotropy Color2", Color) = (0,0,0,1)
        [ToggleUI] _UseLineMap ("Use Line Map", Float) = 0
        _LineMap ("Hairline Map", 2D) = "white" {}
        _LineAmount ("Hairline Amount", Range(0,1000)) = 300
        _LineIntensity ("Hairline Intensity", Range(0,2)) = 0.3
        _LineRange ("Hairline Range", Range(0,1)) = 0.97
        _LineSaturation ("Hairline Saturation", Range(0,4)) = 2
        _LineValue ("Hairline Value", Range(0,1)) = 0.65

        // ---- 眼睛：Matcap ----
        [Toggle(_MATCAP_ENV_REFLECTION_ON)] _UseMatcap ("Use Matcap", Float) = 0
        _MatcapTex ("Matcap", 2D) = "white" {}
        [HDR] _MatcapColor ("Matcap Color", Color) = (1,1,1,1)
        _MatcapNormalScale ("Matcap Normal Scale", Float) = 1
        _EyeHighLight ("Eye Highlight", Range(0,1)) = 0
        [HDR] _EyeHighLightColor ("Eye Highlight Color", Color) = (1,1,1,1)
        [HDR] _EyeScatteringColor ("Eye Scattering Color", Color) = (1,1,1,1)
        _EyeTintColor ("Eye Tint Color", Color) = (1,1,1,1)

        // ---- 色彩调节(终末地统一后期调色 + 边缘光) ----
        [ToggleUI] _EnableVFXColorAdjustment ("VFX Color Adjustment", Float) = 0
        _ColorAdjustmentBrightness ("CA Brightness", Range(0.5,1.5)) = 1
        _ColorAdjustmentSaturation ("CA Saturation", Range(0,2)) = 1
        _ColorAdjustmentContrast ("CA Contrast", Range(0,2)) = 1
        _ColorAdjustmentColorBlend ("CA Color Blend", Color) = (1,1,1,0)
        _ColorAdjustmentRimWidth ("CA Rim Width", Range(0,1)) = 0.35
        _ColorAdjustmentRimIntensity ("CA Rim Intensity", Range(0,10)) = 4
        _ColorAdjustmentRimColor ("CA Rim Color", Color) = (1,1,1,1)

        // ---- 面部：SDF 光照 / 表情图集 / 高光 ----
        [Toggle(_SDF_LIGHTMAP_ON)] _UseSDFLightmap ("Use SDF Lightmap", Float) = 0
        _SDFLightmap ("SDF Lightmap (xy=soft shadow, z=sdf)", 2D) = "white" {}
        _SDFMask ("SDF Mask (x=rimoff y=normal z=side w=highlight)", 2D) = "white" {}
        [Toggle(_EMOTION_MAP_ON)] _UseEmotionMap ("Use Emotion Map", Float) = 0
        _EmotionMap ("Emotion Atlas (2x2)", 2D) = "black" {}
        _EmotionIndex ("Emotion Index", Range(0,3)) = 0
        _EmotionBlend ("Emotion Blend", Range(0,1)) = 1
        [Toggle(_FACE_HIGHLIGHT_ON)] _FaceHighlightMap ("Face Highlight Map", Float) = 0
        _HighlightMap ("Face Highlight Map", 2D) = "black" {}
        _HighlightMapVector ("Highlight UV Offset", Vector) = (0.04,-0.01,0,0)

        // ---- 发际/眉下阴影 ----
        [Toggle(_HAIR_BROW_MASK_ON)] _DrawUnderBrow ("Draw Under Brow", Float) = 0
        _HairBrowMask ("Hair Brow Mask", 2D) = "white" {}
        _HairBrowMaskThreshold ("Hair Brow Mask Threshold", Range(0,1)) = 0.5

        // ---- 描边 ----
        [ToggleUI] _EnableOutline ("Enable Outline", Float) = 1
        _OutlineWidth ("Outline Width", Range(0,2)) = 0.5
        _OutlineOffsetZ ("Outline Offset Z", Range(0,1)) = 0
        [ToggleUI] _OutlineTintEnable ("Outline Tint Color Enable", Float) = 0
        _OutlineTintColor ("Outline Tint Color", Color) = (1,1,1,1)
        _OutlineColorBrightness ("Outline Color Brightness", Range(0,1)) = 0.5
        _OutlineColorSaturation ("Outline Color Saturation", Range(0,2)) = 1.5
        [Toggle(_OUTLINE_MASK)] _EnableOutlineMask ("Outline Mask Enable", Float) = 0
        _OutlineMask ("Outline Mask", 2D) = "white" {}
        [ToggleUI] _OutlineAverageNormal ("Use Smooth Normal", Float) = 1
        _OutlineMinWidth ("Outline Min Width (Pixels)", Range(0,8)) = 0.2
        _OutlineMaxWidth ("Outline Max Width (Pixels)", Range(0,8)) = 3
    }

    SubShader
    {
        Tags { "RenderType"="Opaque" "RenderPipeline"="UniversalPipeline" "Queue"="Geometry" }

        HLSLINCLUDE
        #include "Packages/com.unity.render-pipelines.universal/ShaderLibrary/Core.hlsl"
        #include "Packages/com.unity.render-pipelines.universal/ShaderLibrary/Lighting.hlsl"
        #include "Packages/com.unity.render-pipelines.universal/ShaderLibrary/Shadows.hlsl"

        CBUFFER_START(UnityPerMaterial)
            float4 _BaseMap_ST;          float4 _BaseColor;
            float _MaterialFamily;      float _DebugView;
            float  _SurfaceType;         float  _BlendMode;          float _Cull;
            float  _BackFaceNormalFlip;  float  _EnableAlphaTest;    float _AlphaClipThreshold;
            float  _UseBumpMap;          float  _BumpScale;          float4 _BumpMap_ST;
            float  _UseMetallicGlossMap; float  _Metallic;           float _Specular;          float _Smoothness;
            float4 _MetallicGlossMap_ST; float  _OcclusionStrength;
            float  _UseEmission;         float4 _EmissionColor;      float _EmissionBrightness; float4 _EmissionMap_ST;
            float  _UseDiffRampMap;      float4 _DiffRampMap_ST;
            float  _UseSpecRampMap;      float4 _SpecRampMap_ST;     float _SpecRampIridescentMode;
            float  _SceneShadowCenter;   float  _SceneShadowSharpness;
            float  _HalfLambertShadowCenter; float _HalfLambertShadowSharpness;
            float  _UseShadowLutTex;     float4 _ShadowLutTex_ST;
            float  _ShadowColorBrightness; float _ShadowColorSaturation;
            float  _SkinRimOff;          float  _SkinRimOffScale;  float4 _SDFRimColor;
            float  _FaceRimOffScale;
            float  _CharacterHeavyShadow; float _CharacterHeavyShadowInt; float _EnableLegacyShaping;
            float4 _CharacterHeavyShadowColor;
            float  _CharacterHeavyShadowBackFaceFade; float _CharacterHeavyShadowBackFaceFadeRange;
            float  _FakeFresnel;         float  _FakeFresnelIntensity; float _FakeFresnelRange;
            float  _FakeFresnelFade;     float4 _FakeFresnelColor;   float _FakeFresnelWithAlbedo;
            float  _EnableStylizedFresnel; float4 _StylizedFresnelColor;
            float  _StylizedFresnelPow;  float  _StylizedFresnelAmount;
            float4 _StylizedFresnelNoiseMap_ST; float _StylizedFresnelNoiseSpeed; float _StylizedNoiseContrast;
            float  _ClearCoat;           float4 _ClearCoatMask_ST;   float4 _ClearCoatColor;
            float  _ClearCoatSmoothness; float  _ClearCoatMetallic;  float _ClearCoatNormalMode;
            float  _UseParallax;         float4 _ParallaxTex_ST;     float _ParallaxUseNormal;
            float  _ParallaxMarchNum;    float  _ParallaxScale;      float4 _ParallaxColor;
            float  _UseSpecBumpMap;      float4 _SplitNormalMap_ST;   float _SpecBumpScale;
            float  _UseAnisotropy;       float  _AnisotropyUseGeometryTangent;
            float  _AnisotropyDirectionMain; float _AnisotropyIntensityMultiplier;
            float  _AnisotropyDirectionAdditional; float _AnisotropyOffsetAdditional;
            float4 _AnisotropyColorAdditional;
            float  _Anisotropy;          float  _AnisotropyDirX;     float _AnisotropyValue;
            float  _AnisotropyValue2;    float  _AnisotropyIntensity; float _AnisotropyEdgeFade;
            float  _AnisotropyRange2;    float4 _AnisotropyColor;    float4 _AnisotropyColor2;
            float  _UseLineMap;          float4 _LineMap_ST;         float _LineAmount;
            float  _LineIntensity;      float  _LineRange;          float _LineSaturation; float _LineValue;
            float  _UseMatcap;           float4 _MatcapTex_ST;       float4 _MatcapColor;
            float  _MatcapNormalScale;   float  _EyeHighLight;       float4 _EyeHighLightColor;
            float4 _EyeScatteringColor;  float4 _EyeTintColor;
            float  _EnableVFXColorAdjustment;
            float  _ColorAdjustmentBrightness; float _ColorAdjustmentSaturation; float _ColorAdjustmentContrast;
            float4 _ColorAdjustmentColorBlend;
            float  _ColorAdjustmentRimWidth;  float _ColorAdjustmentRimIntensity; float4 _ColorAdjustmentRimColor;
            float  _EnableOutline;       float  _OutlineWidth;       float _OutlineOffsetZ;
            float  _OutlineTintEnable;   float4 _OutlineTintColor;
            float  _OutlineColorBrightness; float _OutlineColorSaturation;
            float  _EnableOutlineMask;   float4 _OutlineMask_ST;     float _OutlineAverageNormal;
            float  _OutlineMinWidth;     float  _OutlineMaxWidth;
            float  _UseSDFLightmap;      float4 _SDFLightmap_ST;     float4 _SDFMask_ST;
            float  _UseEmotionMap;       float4 _EmotionMap_ST;      float _EmotionIndex;  float _EmotionBlend;
            float  _FaceHighlightMap;    float4 _HighlightMap_ST;    float4 _HighlightMapVector;
            float  _DrawUnderBrow;       float4 _HairBrowMask_ST;    float _HairBrowMaskThreshold;
        CBUFFER_END

        // 分离式角色光照 · 由 C# Shader.SetGlobal* 注入
        float4 _CharacterLightDir;    // xyz=指向光源, w=启用标记
        float4 _CharacterLightColor;
        float4 _CharacterAmbient;     // 环境/补光颜色
        float _EndfieldOfficialFrameEnabled;
        float _EndfieldOfficialShadingEnabled;
        float _EndfieldCapturedCubemapAvailable;
        float _EndfieldCapturedLightIntensity;

        // 官方 HGRP _CharacterParamsN 全局参数（捕获帧已知值，由 C# SetGlobalVector 注入）
        // 详见 docs/research/official-forwardlit-{hair-b125,skin-b138,cloth-b401,eye-b28}.md §4
        float4 _CharacterParams0;   // x=? y=受光侧lightTerm乘数 z=阴影色深度系数(0.65) w=阴影侧lightTerm乘数(0.9)
        float4 _CharacterParams1;   // x=环境峰值映射 y=1=平坦环境(不采样辐照度体) z=1=忽略屏幕空间方向光阴影 w=1=用CP11.xyz覆盖光方向
        float4 _CharacterParams2;   // xyz=平坦环境色调 (捕获 0.849,0.896,1.151)
        float4 _CharacterParams3;   // skin 用（hair 不引用）
        float4 _CharacterParams4;   // skin 用
        float4 _CharacterParams5;   // xyz=光颜色覆盖(权重CP12.y)
        float4 _CharacterParams6;   // xyz=环境梯度方向
        float4 _CharacterParams7;   // x/y/z=环境梯度 offset/scale/base (0.15/1.5/0.5)
        float4 _CharacterParams8;   // xyz=深度边缘光颜色 w=强度
        float4 _CharacterParams9;   // xy=边缘光轴 z=边缘光颜色lerp w=深度采样偏移
        float4 _CharacterParams10;  // x=>0.5用全局天气 y=天气掩码 z=雨雪UV缩放 w=水位
        float4 _CharacterParams11;  // xyz=角色专用光方向(0.176,0.530,0.830) w=ramp偏移
        float4 _CharacterParams12;  // x=1关逆光抬亮 y=光颜色覆盖权重 z=点光角色灯门槛 w=>=0.5展示模式
        float4 _CharacterParams13;  // w=各向异性高光总乘数（hair/cloth 用）
        float4 _CharacterParams14;
        float4 _CharacterParams15;  // w=0=CP9.xy世界轴 1=相机轴

        // 官方 HGRP 全局环境/曝光（cloth b401 环境光 & IBL 用，捕获帧值）
        float4 _EnvironmentGlobalParams0;   // x=ambientScale 基值 (捕获 0.2877)
        float4 _ExposureWithMiscParams;     // x=乘 ambientScale, y=输出前乘 rgb (捕获 1,1,1.6,0.1)

        TEXTURE2D(_BaseMap);
        TEXTURE2D(_BumpMap);
        TEXTURE2D(_MetallicGlossMap);
        TEXTURE2D(_DiffRampMap);
        TEXTURE2D(_SpecRampMap);
        TEXTURE2D(_ShadowLutTex);
        TEXTURE2D(_EmissionMap);
        TEXTURE2D(_StylizedFresnelNoiseMap);
        TEXTURE2D(_ClearCoatMask);
        TEXTURE2D(_ParallaxTex);
        TEXTURE2D(_SplitNormalMap);
        TEXTURE2D(_LineMap);
        TEXTURE2D(_MatcapTex);
        TEXTURE2D(_OutlineMask);
        TEXTURE2D(_SDFLightmap);
        TEXTURE2D(_SDFMask);
        TEXTURE2D(_EmotionMap);
        TEXTURE2D(_HighlightMap);
        TEXTURE2D(_HairBrowMask);
        // cloth b401 角色环境立方体反射（官方全局绑定，LOD 由 rough 决定）
        TEXTURECUBE(_CharMaxCubemap);

        // Private inline sampler avoids version-dependent URP global declarations.
        SAMPLER(sampler_Endfield_LinearRepeat);
        SAMPLER(sampler_Endfield_LinearClamp);
        SAMPLER(sampler_CharMaxCubemap);

        struct Attributes
        {
            float4 positionOS : POSITION;
            float3 normalOS   : NORMAL;
            float4 tangentOS  : TANGENT;
            float2 uv         : TEXCOORD0;
        };

        struct Varyings
        {
            float4 positionCS  : SV_POSITION;
            float2 uv          : TEXCOORD0;
            float3 positionWS  : TEXCOORD1;
            float3 normalWS    : TEXCOORD2;
            float4 tangentWS   : TEXCOORD3; // xyz=tangent, w=sign
            float3 viewDirWS   : TEXCOORD4;
            float  fogFactor   : TEXCOORD6;
        };

        Varyings CharVert(Attributes input)
        {
            Varyings output = (Varyings)0;
            output.positionWS = TransformObjectToWorld(input.positionOS.xyz);
            output.positionCS = TransformWorldToHClip(output.positionWS);
            output.normalWS   = SafeNormalize(TransformObjectToWorldNormal(input.normalOS));
            float3 tangentWS  = TransformObjectToWorldDir(input.tangentOS.xyz);
            if (dot(tangentWS, tangentWS) < 1e-8)
            {
                float3 axis = abs(output.normalWS.y) < 0.99 ? float3(0,1,0) : float3(1,0,0);
                tangentWS = cross(axis, output.normalWS);
            }
            output.tangentWS  = float4(SafeNormalize(tangentWS), input.tangentOS.w < 0 ? -1 : 1);
            output.viewDirWS  = GetWorldSpaceViewDir(output.positionWS);
            // Retain source UVs: each texture has its own transform. In particular,
            // mod DDS exports need a V flip while inherited SDF/normal maps do not.
            output.uv         = input.uv;
            output.fogFactor  = ComputeFogFactor(output.positionCS.z);
            return output;
        }

        float3x3 CharTBN(Varyings input, half3 normalWS)
        {
            float3 tangentWS = normalize(input.tangentWS.xyz);
            float3 bitangentWS = normalize(cross(normalWS, tangentWS)) * input.tangentWS.w;
            return float3x3(tangentWS, bitangentWS, normalWS);
        }

        void GetCharacterLight(float3 positionWS, out half3 L, out half3 lightColor, out half shadowAttenuation)
        {
            if (_CharacterLightDir.w > 0.0)
            {
                L = normalize(_CharacterLightDir.xyz);
                lightColor = _CharacterLightColor.rgb;
                shadowAttenuation = 1.0;
            }
            else
            {
                float4 shadowCoord = TransformWorldToShadowCoord(positionWS);
                Light mainLight = GetMainLight(shadowCoord);
                L = mainLight.direction;
                lightColor = mainLight.color * mainLight.distanceAttenuation;
                shadowAttenuation = mainLight.shadowAttenuation;
            }
            if (_EndfieldOfficialFrameEnabled > 0.5)
            {
                L = SafeNormalize(lerp(L, _CharacterParams11.xyz, _CharacterParams1.w));
                // Keep the previous reconstruction's light mapping for A/B.
                // The source path below corrects body to skin b114 and CP4;
                // the historical buffer-size-only b401 body match was false.
                half3 capturedColor = _UseSDFLightmap > 0.5 ? _CharacterParams4.rgb : _CharacterParams5.rgb;
                lightColor = lerp(lightColor, capturedColor, _CharacterParams12.y) * _EndfieldCapturedLightIntensity;
            }
        }

        half3 ApplyColorAdjustment(half3 c)
        {
            c *= _ColorAdjustmentBrightness;
            c = (c - 0.5) * _ColorAdjustmentContrast + 0.5;
            half lum = dot(c, half3(0.2126729, 0.7151522, 0.0721750));
            c = lerp(lum.xxx, c, _ColorAdjustmentSaturation);
            c = lerp(c, c * _ColorAdjustmentColorBlend.rgb, _ColorAdjustmentColorBlend.a);
            return c;
        }

        half SigmoidSharp(half x, half center, half sharpness)
        {
            return rcp(pow(100000.0, (x - center) * (-3.0 * sharpness)) + 1.0);
        }

        // 终末地皮肤 LUT 是 32³ 3D 颜色分级表，打包为 1024x32 纹理：
        //   X = 蓝(高5bit)*32 + 红(低5bit)，Y = 绿(5bit)
        // 红/绿靠硬件双线性采样，蓝通道做相邻切片手动插值。
        half3 SampleSkinLUT3D(Texture2D lut, SamplerState ss, half3 linearColor)
        {
            // Official skin/cloth fragments index this LUT in sRGB, not linear.
            half3 c = saturate(LinearToSRGB(linearColor));
            half b = c.b * 31.0;
            half bIdx = floor(b);
            half bFrac = b - bIdx;
            half2 uv;
            uv.x = (bIdx * 32.0 + c.r * 31.0 + 0.5) / 1024.0;
            uv.y = (c.g * 31.0 + 0.5) / 32.0;
            half3 c0 = SAMPLE_TEXTURE2D(lut, ss, uv).rgb;
            half3 c1 = SAMPLE_TEXTURE2D(lut, ss, uv + half2(32.0 / 1024.0, 0.0)).rgb;
            return lerp(c0, c1, bFrac);
        }

        // 终末地法线解码 —— 与官方 HGRP/CharacterNPR 反编译逐行一致：
        //   (characternpr_skin/Sub0_Pass0_Fragment_b95.hlsl L418-424)
        //     _466.w = _466.w * _466.x;              -> X = A * R
        //     _475  = (_466.wy * 2.0f) - 1.0f;       -> X=(A*R)*2-1, Y=G*2-1
        //     _476.z = sqrt(1 - dot(XY,XY));          -> Z 重建
        //   即：X 分量被拆到 R/A 两通道相乘，Y 存 G 通道，Z 由单位长度重建。
        half3 UnpackEndfieldNormal(half4 packed, half scale)
        {
            half3 n;
            n.x = (packed.a * packed.r) * 2.0 - 1.0;
            n.y = packed.g * 2.0 - 1.0;
            n.z = sqrt(max(1e-16, 1.0 - clamp(dot(n.xy, n.xy), 0.0, 1.0)));
            n.xy *= scale;
            return n;
        }
        #include "EndfieldOfficialHair.hlsl"
        #include "EndfieldOfficialSkin.hlsl"
        #include "EndfieldOfficialCloth.hlsl"
        #include "EndfieldOfficialEye.hlsl"
        ENDHLSL

        // ============================================================
        // Pass 0 : 主光照 (UniversalForward)
        // ============================================================
        Pass
        {
            Name "UniversalForward"
            Tags { "LightMode"="UniversalForward" }

            Cull [_Cull]
            ZWrite [_ZWrite]
            ZTest [_ZTest]
            Blend [_SrcBlend] [_DstBlend], [_AlphaSrcBlend] [_AlphaDstBlend]

            HLSLPROGRAM
            #pragma target 5.0
            #pragma vertex vert
            #pragma fragment frag
            #pragma multi_compile _ _MAIN_LIGHT_SHADOWS _MAIN_LIGHT_SHADOWS_CASCADE
            #pragma multi_compile_fog

            Varyings vert(Attributes input) { return CharVert(input); }

            half4 frag(Varyings input, FRONT_FACE_TYPE frontFace : FRONT_FACE_SEMANTIC) : SV_Target
            {
                float2 uv = input.uv;
                bool sourceShading = _EndfieldOfficialFrameEnabled > 0.5
                    && _EndfieldOfficialShadingEnabled > 0.5 && _CharacterParams1.y >= 0.5
                    && _SurfaceType < 0.5 && _DebugView < 0.5
                    && (_UseParallax < 0.5 || _MaterialFamily > 2.5);

                // ---- 视差(布料流动)：采样前偏移 UV ----
                if (!sourceShading && _UseParallax > 0.5)
                {
                    half3 T, B, Ntg;
                    Ntg = normalize(input.normalWS);
                    T = normalize(input.tangentWS.xyz);
                    B = normalize(cross(Ntg, T)) * input.tangentWS.w;
                    half3 viewDirTS = half3(
                        dot(input.viewDirWS, T),
                        dot(input.viewDirWS, B),
                        dot(input.viewDirWS, Ntg));
                    half h = SAMPLE_TEXTURE2D(_ParallaxTex, sampler_Endfield_LinearRepeat, uv).r;
                    uv -= (h - 0.5) * _ParallaxScale * viewDirTS.xy;
                }

                bool sourceClamp = sourceShading && (_MaterialFamily < 1.5 || _MaterialFamily > 2.5);
                half4 baseMap = sourceClamp
                    ? SAMPLE_TEXTURE2D(_BaseMap, sampler_Endfield_LinearClamp, TRANSFORM_TEX(uv, _BaseMap))
                    : SAMPLE_TEXTURE2D(_BaseMap, sampler_Endfield_LinearRepeat, TRANSFORM_TEX(uv, _BaseMap));
                half3 albedo  = baseMap.rgb * _BaseColor.rgb;
                // 终末地角色为不透明表面，漫反射 _D 贴图 alpha 通道存的是其它数据(AO/mask)，
                // 不是透明度，绝不能拿 baseMap.a 当 alpha，否则身体/布料会"像空气一样透明"。
                half  alpha   = _BaseColor.a * ((_SurfaceType > 0.5 || _EnableAlphaTest > 0.5) ? baseMap.a : 1.0);

                // ---- 面部表情图集(2x2)：按 _EmotionIndex 取格 + alpha 加权 lerp 叠加 ----
                // (对应官方 characternpr_skin: fmod(idx,2)*0.5 / floor(idx*0.5)*0.5 定格子, 0.5*uv 定格内坐标)
                if (_UseEmotionMap > 0.5)
                {
                    half2 euv = half2(fmod(_EmotionIndex, 2.0) * 0.5, floor(_EmotionIndex * 0.5) * 0.5) + 0.5 * uv;
                    half4 emo = sourceClamp ? SAMPLE_TEXTURE2D(_EmotionMap, sampler_Endfield_LinearClamp, euv)
                        : SAMPLE_TEXTURE2D(_EmotionMap, sampler_Endfield_LinearRepeat, euv);
                    albedo = lerp(albedo, emo.rgb, emo.a * _EmotionBlend);
                }

                if (_EnableAlphaTest > 0.5) clip(alpha - _AlphaClipThreshold);

                // ---- 法线 ----
                half3 N = normalize(input.normalWS);
                if (!sourceShading && _MaterialFamily > 1.5 && _MaterialFamily < 2.5 && _UseSpecBumpMap > 0.5)
                {
                    // Hair HN RG is the diffuse normal; BA is a separate specular normal.
                    half2 xy = SAMPLE_TEXTURE2D(_SplitNormalMap, sampler_Endfield_LinearRepeat, uv).rg * 2.0 - 1.0;
                    half3 normalTS = half3(xy * _BumpScale, sqrt(saturate(1.0 - dot(xy, xy))));
                    N = SafeNormalize(mul(normalTS, CharTBN(input, N)));
                }
                else if (_UseBumpMap > 0.5)
                {
                    half4 normalSample = sourceClamp
                        ? SAMPLE_TEXTURE2D(_BumpMap, sampler_Endfield_LinearClamp, TRANSFORM_TEX(uv, _BumpMap))
                        : SAMPLE_TEXTURE2D(_BumpMap, sampler_Endfield_LinearRepeat, TRANSFORM_TEX(uv, _BumpMap));
                    half3 normalTS = UnpackEndfieldNormal(normalSample, _BumpScale);
                    N = normalize(mul(normalTS, CharTBN(input, N)));
                }
                // Source enum: 0 flips backface normals; 1 leaves them unchanged.
                N *= IS_FRONT_VFACE(frontFace, 1.0, -1.0 + 2.0 * _BackFaceNormalFlip);

                half3 V = normalize(input.viewDirWS);

                half3 L; half3 lightColor; half shadowAtten;
                GetCharacterLight(input.positionWS, L, lightColor, shadowAtten);
                half signedNdotL = dot(N, L);
                half NdotL = saturate(signedNdotL);
                half halfLambert = signedNdotL * 0.5 + 0.5;
                half3 H = normalize(L + V);
                half NdotH = saturate(dot(N, H));
                half NdotV = saturate(dot(N, V));

                if (sourceShading)
                {
                    // These are the dry flat-environment character paths, before the
                    // former generic diffuse/specular approximation changes N or albedo.
                    float3 sourceL = lerp(L, _CharacterParams11.xyz, _CharacterParams1.w);
                    bool sourceSkin = _MaterialFamily > 0.5 && _MaterialFamily < 1.5;
                    float3 sourceLightColor = sourceSkin ? _CharacterParams4.rgb : _CharacterParams5.rgb;
                    float3 sourceLightI = sourceLightColor * lerp(_EndfieldCapturedLightIntensity, 1.0, _CharacterParams12.w);
                    // HGRP's two-channel screen shadow buffer is not yet reproduced.
                    // Keep selfShadow=1 explicit; separated light currently has no URP shadow.
                    float directionalShadow = lerp(shadowAtten, 1.0, _CharacterParams1.z);
                    float selfShadow = 1.0;
                    float3 sourceColor;
                    if (_MaterialFamily > 2.5)
                        sourceColor = EndfieldShadeOfficialEye(input.uv, input.normalWS, V, input.tangentWS,
                            input.positionWS, sourceL, sourceLightI, directionalShadow, selfShadow);
                    else if (_MaterialFamily > 1.5)
                        sourceColor = EndfieldShadeOfficialHair(uv, albedo, N, V, input.tangentWS,
                            input.positionWS, sourceL, sourceLightI, directionalShadow, selfShadow);
                    else if (sourceSkin)
                        sourceColor = EndfieldShadeOfficialSkin(uv, albedo, N, V,
                            input.positionWS, sourceL, sourceLightI, directionalShadow, selfShadow);
                    else
                    {
                        float3 vertexN = SafeNormalize(input.normalWS)
                            * IS_FRONT_VFACE(frontFace, 1.0, -1.0 + 2.0 * _BackFaceNormalFlip);
                        sourceColor = EndfieldShadeOfficialCloth(uv, albedo, N, vertexN, V,
                            input.positionWS, sourceL, sourceLightI, directionalShadow, selfShadow);
                    }
                    // The emission-enabled cloth variants add it after saturation.
                    if (_MaterialFamily < 0.5 && _UseEmission > 0.5)
                        sourceColor += SAMPLE_TEXTURE2D(_EmissionMap, sampler_Endfield_LinearClamp,
                            TRANSFORM_TEX(uv, _EmissionMap)).rgb * _EmissionColor.rgb * _EmissionBrightness;
                    // Source order: saturation is already in each family helper,
                    // then VFX, then output exposure. Never multiply the result by light again.
                    if (_EnableVFXColorAdjustment > 0.5)
                    {
                        float sourceLum = dot(sourceColor, float3(.2126729, .7151522, .0721750));
                        sourceColor = lerp(0.5.xxx, lerp(sourceLum.xxx, sourceColor, _ColorAdjustmentSaturation),
                            _ColorAdjustmentContrast) * _ColorAdjustmentBrightness;
                        sourceColor = lerp(sourceColor, _ColorAdjustmentColorBlend.rgb, _ColorAdjustmentColorBlend.a);
                        sourceColor += _ColorAdjustmentRimColor.rgb * smoothstep(1.0 - _ColorAdjustmentRimWidth, 1.0,
                            1.0 - saturate(dot(V, N))) * _ColorAdjustmentRimIntensity;
                    }
                    return half4(sourceColor * _ExposureWithMiscParams.y, alpha);
                }

                // 皮肤 rim（官方 characternpr_skin 反编译 L611-613）：
                //   _1100 = clamp((1 - clamp(NdotV*0.85+0.15)) * _SkinRimOffScale)
                //   albedo *= (1 - _1100) + _SDFRimColor * _1100
                //   即掠射角处用 _SDFRimColor 给皮肤加暖色边缘。
                if (_SkinRimOff > 0.5)
                {
                    half skinRim = clamp((1.0 - clamp(NdotV * 0.85 + 0.15, 0.0, 1.0)) * _SkinRimOffScale, 0.0, 1.0);
                    albedo = albedo * ((1.0 - skinRim) + _SDFRimColor.rgb * skinRim);
                }

                // 硬边阴影塑形：半兰伯特 + 场景阴影 分别 sigmoid 后取小
                half shade = saturate(min(
                    SigmoidSharp(halfLambert, _HalfLambertShadowCenter, _HalfLambertShadowSharpness),
                    SigmoidSharp(shadowAtten, _SceneShadowCenter, _SceneShadowSharpness)));
                // SigmoidSharp 以 center=0 为过渡中心，halfLambert/shadowAtten ∈[0,1] 恒 >=0，
                // 输出被压在 [0.5,1]。重新映射到 [0,1]，让背光/阴影区域真正降到 0（对齐官方阴影侧 diffuse→0）。
                shade = saturate(shade * 2.0 - 1.0);

                // ---- 漫反射 + 漫反射 ramp ----
                half3 diffuse;
                if (_UseDiffRampMap > 0.5)
                {
                    half3 ramped = SAMPLE_TEXTURE2D(_DiffRampMap, sampler_Endfield_LinearClamp, half2(halfLambert, 0.5)).rgb;
                    diffuse = albedo * ramped;
                }
                else
                {
                    diffuse = albedo * shade;
                }

                // ==== 面部 SDF / 高光 / 发际 (官方 b138 §9 对齐) ====
                // SDF 面光：官方 _SDFLightmap.xy = 预烘焙面光照度(官方 _1553)，喂入 diffuse ramp
                //   官方按物体空间水平光 Lh.x 左右翻转 UV，消除鼻子投影问题 (b138 §9 L1501-1512)
                half3 _highlightSpec = 0;  // 延迟到 specular 段应用的 _HighlightMap 高光
                half _sdfSpecW = 1.0;      // SDF specular 门控权重(=sdfW)，1=全 specular
                if (_UseSDFLightmap > 0.5)
                {
                    // 官方 b138 §9: Lh = normalize(mul(L, M_o2w)), Y≈0, lhSide = Lh.x>0 ? 1:0
                    half3 objL = TransformWorldToObjectDir(L);
                    half3 Lh = SafeNormalize(half3(objL.x, 6.103515625e-05, objL.z));
                    half lhSide = Lh.x > 0.0 ? 1.0 : 0.0;
                    // SDF UV 翻转：左/右半脸根据光方向
                    half2 sdfUV = half2(lerp(1.0 - uv.x, uv.x, lhSide), uv.y);
                    half3 sdf = SAMPLE_TEXTURE2D(_SDFLightmap, sampler_Endfield_LinearRepeat, sdfUV).rgb;
                    half sdfLight = saturate((sdf.r + sdf.g) * 0.5);
                    // 官方 _508 = _SDFMask.y，控制 SDF 面部光照强度(面部区域=1)
                    half4 sdfMask4 = SAMPLE_TEXTURE2D(_SDFMask, sampler_Endfield_LinearRepeat, uv);
                    half sdfW = sdfMask4.y;
                    half sdfSkin = sdfMask4.z;  // skin vs face 选择
                    // sdfN：混合 SDF 光照方向与表面法线 (b138 §9 _1529)
                    half sdfRange = sdf.b * 2.0;
                    half sdfAng = lerp(1.0 - sdfRange, sdfRange - 1.0, lhSide);
                    half3 sdfLDirObj = half3(sdfAng, 6.103515625e-05, 1.0 - abs(sdfAng));
                    half3 sdfLDir = SafeNormalize(TransformObjectToWorldDir(sdfLDirObj));
                    half3 sdfN = SafeNormalize(lerp(sdfLDir, N, sdfW));
                    if (_UseDiffRampMap > 0.5)
                    {
                        half3 ramped = SAMPLE_TEXTURE2D(_DiffRampMap, sampler_Endfield_LinearClamp, half2(sdfLight, 0.5)).rgb;
                        diffuse = lerp(diffuse, albedo * ramped, sdfW);
                    }
                    else
                    {
                        diffuse = lerp(diffuse, albedo * sdfLight, sdfW);
                    }
                    // 用 sdfN 替代 N 用于后续 specular 计算（仅 SDF 权重区域）
                    N = lerp(N, sdfN, sdfW);
                    // 存 SDF 权重，稍后门控 specularMask (官方 _1178 specStrength = lerp(0, _Specular, sdfW))
                    _sdfSpecW = sdfW;
                }

                // 面部高光图：官方 b138 §11 _1728 — .rgb 采样，随视角偏移 UV，作为高光项(specLight 乘数)
                if (_FaceHighlightMap > 0.5)
                {
                    half2 highlightUV = uv + TransformWorldToObjectDir(V).xy * _HighlightMapVector.xy;
                    _highlightSpec = SAMPLE_TEXTURE2D(_HighlightMap, sampler_Endfield_LinearClamp, highlightUV).rgb;
                }

                // 发际/眉下阴影：官方 _DrawUnderBrow + _HairBrowMask(sw_M)
                if (_DrawUnderBrow > 0.5)
                {
                    half brow = SAMPLE_TEXTURE2D(_HairBrowMask, sampler_Endfield_LinearRepeat, uv).r;
                    half browAmt = saturate((brow - _HairBrowMaskThreshold) * 8.0);
                    diffuse *= lerp(1.0, 0.72, browAmt * saturate(L.y));
                }

                // ---- 阴影颜色 LUT(皮肤 SSS)/色彩调节 ----
                if (_UseShadowLutTex > 0.5)
                {
                    // 皮肤颜色 LUT：阴影区域用 LUT 采样基色作为阴影基色
                    // (精确 3D LUT 采样公式待读官方 _SHADOW_LUT_TEX 变体后进一步对齐)
                    half3 lutCol = SampleSkinLUT3D(_ShadowLutTex, sampler_Endfield_LinearClamp, albedo);
                    // b138 reads the LUT result directly (_504). Its declared
                    // ShadowColorBrightness/Saturation are not read by this variant.
                    // Multiplying by the captured brightness=0 made skin shadows black.
                    diffuse = lerp(diffuse, lutCol, 1.0 - shade);
                }

                // ---- 重阴影(服装冷色重影) ----
                if (_EnableLegacyShaping > 0.5 && _CharacterHeavyShadow > 0.5)
                {
                    half3 heavy = albedo * _CharacterHeavyShadowColor.rgb * _CharacterHeavyShadowInt;
                    half backFace = saturate((dot(N, V) + 1.0) - _CharacterHeavyShadowBackFaceFadeRange);
                    half heavyAmt = (1.0 - NdotL) * _CharacterHeavyShadow;
                    heavyAmt *= lerp(1.0, backFace, _CharacterHeavyShadowBackFaceFade);
                    diffuse = lerp(diffuse, heavy, heavyAmt);
                }

                // ---- 金属/光泽 ----
                half metallic = _Metallic;
                half smoothness = _Smoothness;
                half specularMask = _Specular;
                half ao = 1.0;
                if (_UseMetallicGlossMap > 0.5)
                {
                    half4 mg = SAMPLE_TEXTURE2D(_MetallicGlossMap, sampler_Endfield_LinearRepeat, TRANSFORM_TEX(uv, _MetallicGlossMap));
                    metallic = mg.r;
                    specularMask = mg.g;
                    smoothness = mg.a;
                    ao = lerp(1.0, mg.b, _OcclusionStrength);
                }
                // 官方 b138 §5: specStrength = lerp(0, _Specular, sdfW) — SDF 权重区域才允许高光
                specularMask = lerp(0.0, specularMask, _sdfSpecW);
                // SDF 修改了 N 后重算半角/光照相关量 (官方 b138 §11 用 sdfN 做高光)
                NdotH = saturate(dot(N, H));
                NdotV = saturate(dot(N, V));
                signedNdotL = dot(N, L);
                NdotL = saturate(signedNdotL);
                if (_DebugView > 0.5)
                {
                    half3 debugColor = albedo;
                    if (_DebugView > 1.5) debugColor = N * 0.5 + 0.5;
                    if (_DebugView > 2.5) debugColor = metallic.xxx;
                    if (_DebugView > 3.5) debugColor = specularMask.xxx;
                    if (_DebugView > 4.5) debugColor = ao.xxx;
                    if (_DebugView > 5.5) debugColor = smoothness.xxx;
                    return half4(debugColor, alpha);
                }

                // ---- 高光 ----
                half3 specular = 0;
                half isHair = (_Anisotropy > 0.5) || (_UseAnisotropy > 0.5 && _AnisotropyIntensityMultiplier > 0.0);

                if (isHair)
                {
                    // 发丝法线：split normal 的 BA 通道作为高光发丝法线
                    half3 Nhair = N;
                    if (_UseSpecBumpMap > 0.5)
                    {
                        half4 sn = SAMPLE_TEXTURE2D(_SplitNormalMap, sampler_Endfield_LinearRepeat, uv);
                        half2 snXY = sn.zw * 2.0 - 1.0;
                        half3 snTS = half3(snXY, 0.0);
                        snTS.z = sqrt(saturate(1.0 - dot(snXY, snXY)));
                        snTS.xy *= _SpecBumpScale;
                        Nhair = SafeNormalize(mul(snTS, CharTBN(input, SafeNormalize(input.normalWS))));
                    }

                    // hair b100: object-space direction, P.r blends geometry tangent.
                    half3 anisoDir = SafeNormalize(TransformObjectToWorldDir(half3(_AnisotropyDirX, 1.0, 0.0)));
                    half3 strand = lerp(cross(Nhair, anisoDir), input.tangentWS.xyz, metallic);
                    float3 T = cross(Nhair, strand) * lerp(1.0, input.tangentWS.w, metallic);
                    float3 primaryT = SafeNormalize(T + Nhair * (_AnisotropyValue * 2.0 - 1.0));
                    half tDotH = dot(primaryT, H);
                    half sinTH = sqrt(saturate(1.0 - tDotH * tDotH));

                    // 官方 edgeFade：N/V 在 XZ 平面投影的 _AnisotropyEdgeFade 次幂
                    half3 objectN = TransformWorldToObjectDir(Nhair);
                    half3 objectV = TransformWorldToObjectDir(V);
                    half3 nXZ = SafeNormalize(half3(objectN.x, 0.0, objectN.z));
                    half3 vXZ = SafeNormalize(half3(objectV.x, 0.0, objectV.z));
                    half edgeFade = pow(saturate(dot(nXZ, vXZ)), _AnisotropyEdgeFade);

                    // 官方主高光：sin(T,H)^200 塑形后采样 _SpecRampMap (b125 §10)
                    half specVal = saturate(pow(max(sinTH, 1e-4), 200.0) * specularMask);
                    half3 specRamp = SAMPLE_TEXTURE2D(_SpecRampMap, sampler_Endfield_LinearClamp, half2(specVal, (tDotH > 0.0 ? 1.0 : 0.0) * edgeFade * edgeFade)).rgb;
                    half3 primaryRamp = specVal * specRamp * edgeFade;     // 官方 anisoSpec1 (_2337)
                    half pmax = saturate(max(max(primaryRamp.r, primaryRamp.g), primaryRamp.b));  // spec1Max
                    half3 specColor = half3(0.04, 0.04, 0.04) * specularMask;  // 官方 _2088（hair 非金属）
                    half3 primary = primaryRamp * specColor * (_AnisotropyIntensity * 5.0);

                    // 发丝线宽度 TL + LineMap (官方 b125 §10)
                    half2 lineUV = uv * _LineMap_ST.xy + _LineMap_ST.zw;
                    half4 lineMap = SAMPLE_TEXTURE2D(_LineMap, sampler_Endfield_LinearRepeat, lineUV);
                    half lineProc = ceil(saturate(frac(lineUV.x * _LineAmount) - 0.5));
                    half lineMask = lerp(lineProc, 1.0 - lineMap.r, _UseLineMap);
                    // 第三切线 TL = T + N*(2*_LineValue-1)，宽度 sin(TL,H)^(200*(1-_LineRange))
                    float3 lineT = SafeNormalize(T + Nhair * (2.0 * _LineValue - 1.0));
                    half lineDotH = dot(lineT, H);
                    half lineSin = sqrt(saturate(1.0 - lineDotH * lineDotH));
                    half lineWidth = saturate(pow(max(lineSin, 1e-4), 200.0 * max(1.0 - _LineRange, 0.0)));
                    // 官方嵌套 lineFactor：specMask 门控 → lineWidth → spec1Max(pmax) → lineMask/_LineIntensity
                    half lineFactor = lerp(1.0,
                        lerp(1.0, lerp(lerp(1.0 - _LineIntensity, 1.0, lineMask), 1.0, pmax), lineWidth),
                        specularMask);
                    // 官方：lineFactor 调制 diffuse（非 specular）+ 饱和度 (b125 §10 _2424)
                    diffuse *= lineFactor;
                    diffuse = lerp(dot(diffuse, half3(0.2126729, 0.7151522, 0.0721750)).xxx, diffuse,
                                   lerp(_LineSaturation, 1.0, lineFactor));

                    // 官方次高光：sin(T2,H)^(200*(1-_AnisotropyRange2)) 用 _AnisotropyColor2 * spec2Mask(=smoothness)
                    half exponent2 = 200.0 * max(1.0 - _AnisotropyRange2, 0.0);
                    float3 secondaryT = SafeNormalize(T + Nhair * (_AnisotropyValue2 * 2.0 - 1.0));
                    half secondaryDot = dot(secondaryT, H);
                    half secondarySin = sqrt(saturate(1.0 - secondaryDot * secondaryDot));
                    half3 secondary = pow(max(secondarySin, 1e-4), exponent2) * _AnisotropyColor2.rgb * smoothness * edgeFade;

                    // 官方合成：specTotal = (primary + lerp(secondary, 0, spec1Max)) * _Anisotropy * CP13.w
                    //   CP1.w 门控：未接入 CP 全局时乘 1（no-op），捕获帧模式(CP1.w=1)时用 CP13.w
                    half cp13w = lerp(1.0, _CharacterParams13.w, _CharacterParams1.w);
                    specular = (primary + lerp(secondary, 0.0, pmax)) * _Anisotropy * cp13w;
                }
                else if (_UseMatcap > 0.5)
                {
                    // 官方 b28 §2: 球面法线从 UV 圆盘构造，非反射向量
                    half2 fracUV = frac(uv);
                    half2 ndc = fracUV * 2.0 - 1.0;
                    half3 sphereN;
                    sphereN.xy = ndc * (-_MatcapNormalScale);
                    sphereN.z = sqrt(saturate(1.0 - dot(ndc, ndc)));
                    // matcapUV = normalize(mul(ViewMatrix, mul(mcRaw, TBN))).xy * 0.5 + 0.5 (b28 §10)
                    float3x3 tbn = CharTBN(input, N);
                    half3 matcapWS = mul(sphereN, tbn);
                    half3 matcapVS = mul((float3x3)UNITY_MATRIX_V, matcapWS);
                    half2 matcapUV = SafeNormalize(matcapVS).xy * 0.5 + 0.5;
                    // 官方 b28 §10: matcap.rgb * _MatcapColor.w + _MatcapColor.rgb * matcap.a (rgba 交叉混合)
                    half4 matcap = SAMPLE_TEXTURE2D(_MatcapTex, sampler_Endfield_LinearRepeat, matcapUV);
                    // specLight 近似（同 skin: (shade*0.5+0.5) * lerp(CP0.z, 1, shade)）
                    half cp0z = lerp(0.65, _CharacterParams0.z, _CharacterParams1.w);
                    half specLightEye = (shade * 0.5 + 0.5) * lerp(cp0z, 1.0, shade);
                    specular = (matcap.rgb * _MatcapColor.w + _MatcapColor.rgb * matcap.a)
                             * lightColor * specLightEye
                             + _EyeScatteringColor.rgb * (1.0 - NdotV)
                             + _EyeHighLightColor.rgb * _EyeHighLight * pow(NdotH, 64.0);
                }
                else
                {
                    // ==== cloth/body b401：解析式 GGX 高光 + ClearCoat 双层 (§12-13) ====
                    half rough = 1.0 - smoothness;
                    half roughSq = max(rough * rough, 0.0078125);
                    // b401 §7: specColor = lerp(0.04*glossMask, albedo, metallic)
                    half3 specColor = lerp(half3(0.04, 0.04, 0.04) * specularMask, albedo, metallic);

                    if (_UseSpecRampMap > 0.5)
                    {
                        // 非 cloth 材质保留 ramp 高光路径
                        half3 specRamp = SAMPLE_TEXTURE2D(_SpecRampMap, sampler_Endfield_LinearClamp, half2(NdotH, 0.5)).rgb;
                        half3 F0 = lerp(half3(0.04,0.04,0.04) * specularMask, albedo, metallic);
                        specular = specRamp * F0 * NdotL;
                    }
                    else
                    {
                        // b401 §12: 解析 GGX（基础层）
                        half a4 = roughSq * roughSq;
                        half denom = ((NdotH * a4) - NdotH) * NdotH + 1.0;
                        half denom2 = denom * denom;
                        half ggxD = ((a4 != denom2) ? (a4 / denom2) : 1.0) * (0.5 / ((2.0 * NdotV) + roughSq + 1e-5)) - 6.103515625e-05;
                        half3 baseSpec = specColor * clamp(ggxD, 0.0, 20.0);

                        // b401 §13: ClearCoat 双层（逐像素 ccMaskV 门控）
                        half ccMaskV = 0.0;
                        if (_ClearCoat > 0.5)
                            ccMaskV = SAMPLE_TEXTURE2D(_ClearCoatMask, sampler_Endfield_LinearRepeat, uv).x;
                        half3 ccAtten = 1.0;
                        half3 ccSpec = baseSpec;
                        if (ccMaskV > 0.001)
                        {
                            half ccRough0 = 1.0 - _ClearCoatSmoothness;
                            half ccRough = max(ccRough0 * ccRough0, 0.0078125);
                            half3 ccF0 = _ClearCoatColor.rgb * lerp(0.04, 1.0, _ClearCoatMetallic);
                            half cNdotH = dot(N, H);
                            half cNdotV = clamp(dot(N, V), 0.0, 1.0);
                            half oneMinusVdotH = 1.0 - clamp(dot(V, H), 0.0, 1.0);
                            half f3 = oneMinusVdotH * oneMinusVdotH * oneMinusVdotH;
                            half3 ccFres = (ccF0 * (1.0 - f3) + f3.xxx) * ccMaskV;
                            ccAtten = lerp(1.0, 1.0 - ccFres, ccMaskV);
                            half ccA4 = ccRough * ccRough;
                            half ccDenom = ((cNdotH * ccA4) - cNdotH) * cNdotH + 1.0;
                            half ccDenom2 = ccDenom * ccDenom;
                            half f4 = f3 * oneMinusVdotH;
                            // Preserve the legacy scalar/red-channel approximation explicitly.
                            half ccGGX = clamp((((ccF0 * (1.0 - f4) + f4.xxx) * ccMaskV) * ((ccA4 != ccDenom2) ? (ccA4 / ccDenom2) : 1.0)) * (0.5 / ((2.0 * cNdotV) + ccRough + 1e-5)), 0.0, 20.0).x;
                            ccSpec = baseSpec * ((1.0 - ccFres) * (1.0 - ccFres)) + ccGGX;
                        }
                        specular = ccSpec;
                    }

                    // ==== cloth b401 §15：Stylized Fresnel 环境 BRDF + _CharMaxCubemap ====
                    half nvv = NdotV * NdotV;
                    half nv3 = nvv * NdotV;
                    half fresA = dot(mul(half2(1.0, NdotV), half2x2(half2(0.03654630109667778, 9.06319999694824), half2(3.32706999778748, -9.04755973815918))), half2(1.0, nvv))
                               / dot(mul(half3(1.0, nvv, nv3), half3x3(half3(1.0, 9.04401016235352, 5.56588983535767), half3(3.59684991836548, -16.3173999786377, 19.7886009216309), half3(-1.36772000789642, 9.22949028015137, -20.2122993469238))), half3(1.0, nvv, nvv * nvv));
                    half fresB = dot(mul(half2(1.0, NdotV), half2x2(half2(0.990440011024475, 1.29677999019623), half2(-1.28514003753662, -0.755906999111175))), half2(1.0, nvv))
                               / dot(mul(half3(1.0, NdotV, nv3), half3x3(half3(1.0, 20.3225002288818, 121.563003540039), half3(2.92337989807129, -27.0301990509033, 626.130004882812), half3(59.4188003540039, 222.591995239258, 316.627014160156))), half3(1.0, nvv, nvv * nvv));
                    half3 envFres = specColor * fresA + fresB.xxx;
                    half envFresSum = fresA + fresB;
                    half envRough = rough;
                    half3 cubeRefl = SAMPLE_TEXTURECUBE_LOD(_CharMaxCubemap, sampler_CharMaxCubemap, reflect(-V, N),
                                       (1.2 * log2(max(envRough, 0.001)) + 5.0)).rgb
                                   * (envFres + (specColor * ((1.0 - envFresSum) / max(envFresSum, 1e-5))) * envFres);
                    specular += cubeRefl * _CharacterParams0.w;
                }

                // ---- 假菲涅尔(服装边缘) ----
                if (_EnableLegacyShaping > 0.5 && _FakeFresnel > 0.5)
                {
                    half ff = pow(1.0 - NdotV, _FakeFresnelRange * 10.0) * _FakeFresnelIntensity;
                    ff *= smoothstep(0.0, max(_FakeFresnelFade, 1e-4), 1.0 - NdotV);
                    half3 fcol = _FakeFresnelWithAlbedo > 0.5 ? albedo : _FakeFresnelColor.rgb;
                    specular += fcol * ff;
                }

                // ---- Stylized Fresnel ----
                if (_EnableStylizedFresnel > 0.5)
                {
                    half fresnel = pow(saturate(1.0 - NdotV), _StylizedFresnelPow) * _StylizedFresnelAmount;
                    half3 sc = _StylizedFresnelColor.rgb;
                    half2 nu = uv + half2(_Time.y * _StylizedFresnelNoiseSpeed, _Time.y * _StylizedFresnelNoiseSpeed);
                    half noise = SAMPLE_TEXTURE2D(_StylizedFresnelNoiseMap, sampler_Endfield_LinearRepeat, nu).r;
                    fresnel *= lerp(1.0, noise, _StylizedNoiseContrast);
                    specular += sc * fresnel;
                }

                // ---- 自发光 ----
                half3 emission = 0;
                if (_UseEmission > 0.5)
                {
                    emission = SAMPLE_TEXTURE2D(_EmissionMap, sampler_Endfield_LinearRepeat, uv).rgb
                             * _EmissionColor.rgb * _EmissionBrightness;
                }

                // ---- 面部高光 specLight (官方 b138 §10-11) ----
                // specLight = (litBlend*0.5+0.5) * lerp(CP0.z, 1, litBlend)
                //   litBlend ≈ shade, CP0.z = _CharacterParams0.z (捕获=0.65), CP1.w 门控
                half cp0z = lerp(0.65, _CharacterParams0.z, _CharacterParams1.w);
                half specLightSkin = (shade * 0.5 + 0.5) * lerp(cp0z, 1.0, shade);
                specular += _highlightSpec * lightColor * specLightSkin;

                // ---- 合成 + AO ----
                // 环境光乘 shade：阴影区域环境光随之减弱，避免明暗被压平（官方阴影侧漫反射→0）
                half3 color = (diffuse * lightColor + specular * lightColor + albedo * _CharacterAmbient.rgb * shade) * ao + emission;

                // ---- 官方 b138 §12: 饱和度提升 ----
                // color = lerp(lum.xxx, color, (s*s+1).xxx) where s = clamp(lum-0.5, 0, 0.5)
                {
                    half lum = dot(color, half3(0.2126729, 0.7151522, 0.0721750));
                    half sat = clamp(lum - 0.5, 0.0, 0.5);
                    color = lerp(lum.xxx, color, (sat * sat + 1.0).xxx);
                }

                // ---- 色彩调节（含边缘光，仅在 _EnableVFXColorAdjustment 开启时生效）----
                if (_EnableVFXColorAdjustment > 0.5)
                {
                    color = ApplyColorAdjustment(color);

                    half rim = pow(saturate(1.0 - NdotV), _ColorAdjustmentRimWidth * 10.0 + 1.0)
                             * _ColorAdjustmentRimIntensity;
                    color += _ColorAdjustmentRimColor.rgb * rim;
                }

                half fog = _CharacterLightDir.w > 0.0 ? 1.0 : input.fogFactor;
                color = MixFog(color, fog);

                return half4(color, alpha);
            }
            ENDHLSL
        }

        // ============================================================
        // Pass 1 : 背面描边 (Outline)
        // ============================================================
        Pass
        {
            Name "Outline"
            Tags { "LightMode"="SRPDefaultUnlit" }

            Cull Front
            ZWrite Off
            ZTest LEqual

            HLSLPROGRAM
            #pragma target 5.0
            #pragma vertex vert
            #pragma fragment frag

            struct Attr
            {
                float4 positionOS : POSITION;
                float3 normalOS   : NORMAL;
                float4 tangentOS  : TANGENT;
                float2 uv         : TEXCOORD0;
                float4 color      : COLOR;
                float3 smoothedNormal : TEXCOORD7;
            };

            struct Vary
            {
                float4 positionCS : SV_POSITION;
                float2 uv         : TEXCOORD0;
            };

            Vary vert(Attr input)
            {
                Vary output = (Vary)0;
                float mask = 1.0;
                if (_EnableOutlineMask > 0.5)
                    mask = SAMPLE_TEXTURE2D_LOD(_OutlineMask, sampler_Endfield_LinearRepeat, TRANSFORM_TEX(input.uv, _OutlineMask), 0).r;

                float3 normalWS = SafeNormalize(TransformObjectToWorldNormal(input.normalOS));
                float3 smoothWS = normalWS;
                // JSON meshes may omit UV7 and tangents. Missing UV7 is zero,
                // not an encoded (-1,-1,-1) smooth normal.
                if (_OutlineAverageNormal > 0.5 && dot(input.smoothedNormal, input.smoothedNormal) > 1e-8
                    && dot(input.tangentOS.xyz, input.tangentOS.xyz) > 1e-8)
                {
                    float3 smoothTS = input.smoothedNormal * 2.0 - 1.0;
                    if (dot(smoothTS, smoothTS) > 1e-4)
                    {
                        float3 tangentWS = TransformObjectToWorldDir(input.tangentOS.xyz);
                        float3 bitangentWS = SafeNormalize(cross(normalWS, tangentWS)) * input.tangentOS.w;
                        float3x3 tbn = float3x3(SafeNormalize(tangentWS), bitangentWS, normalWS);
                        smoothWS = SafeNormalize(mul(smoothTS, tbn));
                    }
                }

                // Source material values reach 3. They cannot be interpreted as
                // meters: that inflated a 1.6 m character by up to 1.6 m per vertex.
                // URP adaptation uses bounded screen-pixel widths.
                float w = clamp(lerp(_OutlineMinWidth, _OutlineMaxWidth, saturate(_OutlineWidth)), 0, 8);
                float widthMask = saturate(mask * input.color.r);
                float3 positionWS = TransformObjectToWorld(input.positionOS.xyz);
                output.positionCS = TransformWorldToHClip(positionWS);
                float3 normalVS = mul((float3x3)UNITY_MATRIX_V, smoothWS);
                float2 projected = mul((float2x2)UNITY_MATRIX_P, normalVS.xy);
                float2 pixelDirection = projected * _ScaledScreenParams.xy;
                pixelDirection *= rsqrt(max(dot(pixelDirection, pixelDirection), 1e-8));
                output.positionCS.xy += pixelDirection * (2.0 * w * widthMask / _ScaledScreenParams.xy)
                    * output.positionCS.w * step(0.5, _EnableOutline);
                output.uv = input.uv;
                return output;
            }

            half4 frag(Vary input) : SV_Target
            {
                clip(_EnableOutline - 0.5);
                half3 base = SAMPLE_TEXTURE2D(_BaseMap, sampler_Endfield_LinearRepeat, TRANSFORM_TEX(input.uv, _BaseMap)).rgb * _BaseColor.rgb;
                half lum = dot(base, half3(0.2126729, 0.7151522, 0.0721750));
                half3 c = lerp(lum.xxx, base, _OutlineColorSaturation);
                c *= _OutlineColorBrightness;
                if (_OutlineTintEnable > 0.5)
                    c = lerp(c, c * _OutlineTintColor.rgb, 0.5);
                return half4(c, 1.0);
            }
            ENDHLSL
        }

        // ============================================================
        // Pass 2 : 阴影投射
        // ============================================================
        Pass
        {
            Name "ShadowCaster"
            Tags { "LightMode"="ShadowCaster" }

            ZWrite On
            ZTest LEqual
            ColorMask 0

            HLSLPROGRAM
            #pragma target 5.0
            #pragma vertex vert
            #pragma fragment frag

            float3 _LightDirection; // URP 阴影投射光源方向(自定义 shader 需自行声明)

            Varyings vert(Attributes input)
            {
                Varyings output = (Varyings)0;
                float3 positionWS = TransformObjectToWorld(input.positionOS.xyz);
                float3 normalWS   = TransformObjectToWorldNormal(input.normalOS);
                output.positionCS = TransformWorldToHClip(ApplyShadowBias(positionWS, normalWS, _LightDirection));
                output.uv = TRANSFORM_TEX(input.uv, _BaseMap);
                return output;
            }

            half4 frag(Varyings input) : SV_Target
            {
                half alpha = SAMPLE_TEXTURE2D(_BaseMap, sampler_Endfield_LinearRepeat, input.uv).a;
                if (_EnableAlphaTest > 0.5) clip(alpha - _AlphaClipThreshold);
                return 0;
            }
            ENDHLSL
        }
    }

    Fallback "Universal Render Pipeline/Lit"
}
