#ifndef ENDFIELD_OFFICIAL_EYE_INCLUDED
#define ENDFIELD_OFFICIAL_EYE_INCLUDED

// Opaque, dry, flat-environment CharacterNPR_Eye ForwardLit b28 adapter.
// Primary source: _dump_1.5.3/AllShader_1.5.3/Assets/packages/
// com.hg.render-pipelines/runtime/shaders/materials/characternpr/
// characternpr_eye/Sub0_Pass0_Fragment_b28.hlsl, _399.._1479.
// Returns source _1479: after saturation/backlight/eye accents, before VFX,
// exposure and fog. The caller owns those output stages.
// Frame scope excludes snow, irradiance clipmaps, local lights, motion vectors
// and HGRP fog. Texture mip bias is zero at the unit rendering scale.
// The input UV is the original mesh UV; per-slot ST corrects exported texture
// orientation only at the texture fetch, never the analytic iris coordinates.

float EFEyeLuminance(float3 color)
{
    return dot(color, float3(0.2126729041, 0.7151522040, 0.07217500359));
}

float3 EFEyeNormalize(float3 value)
{
    return value * rsqrt(max(dot(value, value), 1.175494351e-38));
}

float3 EndfieldShadeOfficialEye(
    float2 uv, float3 N, float3 V, float4 tangentWS, float3 positionWS,
    float3 L, float3 lightColorI, float directionalShadow, float selfShadow)
{
    // b28 only reads the directional mask R; the shared selfShadow argument
    // is deliberately unused (the source's _1319 is min(1, 1)). positionWS
    // is only needed by the omitted weather/irradiance/local-light branches.
    float3 T = tangentWS.xyz;
    float3 crossNT = cross(N, T);
    float3 B = crossNT * tangentWS.w;
    float3x3 tangentToWorld = float3x3(T, B, N);

    // _399.._431: BaseMap alpha supplies pupil depth after parallax. The
    // offset itself does NOT sample alpha or divide by tangent-view Z.
    float2 cellUV = frac(uv);
    float2 centeredUV = cellUV - 0.5;
    float radiusSquared = dot(centeredUV, centeredUV);
    float outerDiskMask = step(0.25, radiusSquared);
    float inverseNormalLength = rcp(max(length(N), 1.0e-8));
    float3x3 worldToTangent = float3x3(
        T * inverseNormalLength,
        crossNT * (tangentWS.w > 0.0 ? 1.0 : -1.0) * inverseNormalLength,
        N * inverseNormalLength);
    float3 viewTS = EFEyeNormalize(mul(worldToTangent, V));
    float2 parallaxOffset = viewTS.xy * _ParallaxScale * float2(1.0, 0.25)
        * smoothstep(0.25, 0.05, radiusSquared);
    float2 baseUV = (uv - parallaxOffset) * _BaseMap_ST.xy + _BaseMap_ST.zw;
    float4 baseSample = SAMPLE_TEXTURE2D_BIAS(
        _BaseMap, sampler_Endfield_LinearClamp, baseUV, 0.0);
    float3 albedo = baseSample.rgb * _BaseColor.rgb;
    float pupilDepth = baseSample.a * _BaseColor.a;
    float3 shadowAlbedo = albedo * _ShadowColorBrightness;
    shadowAlbedo = lerp(EFEyeLuminance(shadowAlbedo).xxx,
        shadowAlbedo, _ShadowColorSaturation);

    // _478.._507: the lighting normal is gently curved; matcap uses the
    // separate full-strength spherical normal. Neither sees shifted UVs.
    float2 sphereXY = cellUV * 2.0 - 1.0;
    float sphereZ = max(1.0e-16, sqrt(1.0 - saturate(dot(sphereXY, sphereXY))));
    float3 matcapNormalTS = float3(sphereXY * (-_MatcapNormalScale), sphereZ);
    float3 shadingNormalTS = lerp(matcapNormalTS * float3(-0.125, -0.125, 1.0),
        float3(0.0, 0.0, 1.0), outerDiskMask);
    float3 shadingNormalWS = EFEyeNormalize(mul(shadingNormalTS, tangentToWorld));
    float3 cameraAxisZ = mul((float3x3)UNITY_MATRIX_I_V, float3(0.0, 0.0, 1.0));
    float3 horizontalNormalWS = EFEyeNormalize(
        float3(shadingNormalWS.x, 6.103515625e-5, shadingNormalWS.z));

    // _530 and flat-environment branch _1028.._1031 (CP1.y == 1).
    float ambientPeak = lerp(_EnvironmentGlobalParams0.x, 1.0, _CharacterParams12.w)
        * _ExposureWithMiscParams.x;
    float3 ambientRGB = 1.0;
    float3 ambientTint = _CharacterParams2.rgb;
    float3 diffuseColor = albedo * (0.96 - _Metallic * 0.96);
    float3 shadowDiffuse = shadowAlbedo * (0.96 - _Metallic * 0.96);

    // _1206.._1233: the ramp projects the light onto the character's XZ
    // plane, whereas backlighting uses the world's horizontal light.
    float3 horizontalLightWS = EFEyeNormalize(float3(L.x, 6.103515625e-5, L.z));
    float3x3 objectToWorld = (float3x3)unity_ObjectToWorld;
    float3 objectLight = EFEyeNormalize(mul(L, objectToWorld));
    objectLight.y = 0.0;
    float3 rampLightWS = EFEyeNormalize(mul(objectToWorld, objectLight));
    // lightColorI already contains the caller's directional intensity and
    // CP5 override; source _1216 is needed separately by the ambient term.
    float intensity = lerp(_EndfieldCapturedLightIntensity, 1.0, _CharacterParams12.w);
    float3 lightColor = lightColorI / max(intensity, 1.0e-8);
    // The caller already resolved the directional mask and CP1.z override.
    float shadowDir = directionalShadow;
    float3 shadowDeep = shadowDiffuse * _CharacterParams0.z;
    float3 shadowDeep2 = shadowDeep * 0.65;

    // _1271.._1281: mask and alpha have different roles. The source
    // variant enables both accents unconditionally; alpha is not opacity.
    float3 eyeHighLight = _EyeHighLightColor.rgb * outerDiskMask;
    float3 eyeScattering = _EyeScatteringColor.rgb * pupilDepth;
    float3 eyeDiffuse = diffuseColor
        * ((1.0 - outerDiskMask).xxx + eyeHighLight)
        * ((1.0 - pupilDepth).xxx + eyeScattering);

    // _1295.._1324: preserve all four ramp channels and repeat addressing.
    float rampU = clamp(dot(shadingNormalWS, rampLightWS)
        + _CharacterParams11.w * _CharacterParams12.x, -1.0, 1.0) * 0.5 + 0.5;
    float4 ramp = SAMPLE_TEXTURE2D_LOD(
        _DiffRampMap, sampler_Endfield_LinearRepeat, float2(rampU, 0.5), 0.0);
    float litMask = min(1.0, ramp.a);
    float rampChroma = max(max(ramp.r, ramp.g), ramp.b) - min(min(ramp.r, ramp.g), ramp.b);
    float rampV = SAMPLE_TEXTURE2D_LOD(_DiffRampMap, sampler_Endfield_LinearRepeat,
        float2(dot(shadingNormalWS, cameraAxisZ) * 0.5 + 0.5, 0.5), 0.0).a;
    float ambientGradient = saturate(dot(horizontalNormalWS, _CharacterParams6.xyz)
        + _CharacterParams7.x) * _CharacterParams7.y + _CharacterParams7.z;
    float3 ambientGrad = ambientGradient
        * lerp(ambientTint, 1.0.xxx, _CharacterParams1.y * litMask);

    // _1350.._1372: shadow/view-ramp and lit-ramp terms remain separate.
    float shadowAmbient = lerp(min(lerp(0.65, 1.0, ambientPeak), 1.5),
        clamp(ambientPeak, 1.25, 1.75), _CharacterParams1.x);
    float3 shadowLightTerm = ambientGrad * shadowAmbient * _CharacterParams0.w;
    float3 litLightTerm = (lerp(EFEyeLuminance(lightColorI).xxx, lightColorI, litMask)
        + ambientGrad * clamp(ambientPeak, 0.0, 1.5)
        * ((1.0 - _CharacterParams12.y).xxx + lightColor * _CharacterParams12.y))
        * _CharacterParams0.y;
    float3 lightTerm = lerp(shadowLightTerm, litLightTerm, shadowDir);
    float3 baseSel = lerp(lerp(lerp(EFEyeLuminance(shadowDeep2).xxx, shadowDeep2, 1.2),
        shadowDeep, saturate(rampV + ramp.a)), eyeDiffuse, litMask);
    float3 rampTinted = baseSel * ((1.0 - rampChroma).xxx + ramp.rgb * rampChroma);
    float rampEnergy = clamp(EFEyeLuminance(baseSel)
        / max(EFEyeLuminance(rampTinted), 0.001), 0.0, 1.5);
    float3 diffuseTerm = lerp(lerp(shadowDeep, eyeDiffuse, rampV),
        rampTinted * rampEnergy, shadowDir);
    float litBlend = lerp(rampV, litMask, shadowDir);
    float3 specLight = lightTerm * ((litBlend * 0.5 + 0.5)
        * lerp(_CharacterParams0.z, 1.0, litBlend));

    // _1395.._1413: the RGB/alpha cross blend is not a normal tint multiply.
    float3 matcapNormalVS = EFEyeNormalize(mul((float3x3)UNITY_MATRIX_V,
        mul(matcapNormalTS, tangentToWorld)));
    float2 matcapUV = matcapNormalVS.xy * 0.5 + 0.5;
    float4 matcap = SAMPLE_TEXTURE2D_BIAS(
        _MatcapTex, sampler_Endfield_LinearRepeat, matcapUV, 0.0);
    float3 color = lightTerm * diffuseTerm
        + (matcap.rgb * _MatcapColor.a + _MatcapColor.rgb * matcap.a) * specLight;

    // _1414.._1479: opaque premultiply is 1. Flat ambient SH direction is
    // zero, so its directional backlight factor is also zero before lerp.
    float luminance = EFEyeLuminance(color);
    float saturationBoost = clamp(luminance - 0.5, 0.0, 0.5);
    float horizontalNdotL = dot(horizontalLightWS, shadingNormalWS);
    float NdotV = dot(V, shadingNormalWS);
    float inverseShadow = 1.0 - shadowDir;
    float2 cameraHorizontal = cameraAxisZ.xz
        * rsqrt(max(dot(cameraAxisZ.xz, cameraAxisZ.xz), 1.175494351e-38));
    float backLightShape = saturate(lerp(0.0,
        -horizontalNdotL * (horizontalNdotL * 0.5 - 1.0) + 0.5, shadowDir));
    float backLightFacing = (inverseShadow
        + saturate(-dot(horizontalLightWS.xz, cameraHorizontal)) * shadowDir)
        * (1.0 - _CharacterParams12.x);
    float darkDiffuseWeight = inverseShadow
        + smoothstep(0.1, 0.04, EFEyeLuminance(diffuseColor)) * shadowDir;
    float3 edgeLight = lerp(ambientRGB, lightColorI, shadowDir) * backLightShape
        * backLightFacing * smoothstep(0.6, 0.8, 1.0 - abs(NdotV))
        * darkDiffuseWeight * max(0.15.xxx, diffuseColor);
    float3 eyeAccents = eyeHighLight * _CharacterParams13.y
        + eyeScattering * _CharacterParams13.z + albedo * _CharacterParams13.x;
    return lerp(luminance.xxx, color, 1.0 + saturationBoost * saturationBoost)
        + edgeLight + eyeAccents;
}

#endif
