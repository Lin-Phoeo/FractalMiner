#ifndef ENDFIELD_OFFICIAL_CLOTH_INCLUDED
#define ENDFIELD_OFFICIAL_CLOTH_INCLUDED

// CharacterNPR ForwardLit, dry opaque / flat-environment capture subset.
// Primary evidence: characternpr/Sub0_Pass0_Fragment_b471.hlsl (ramp cloth)
// and Sub0_Pass0_Fragment_b401.hlsl (analytic clearcoat formula reference), under
// _dump_1.5.3/AllShader_1.5.3/Assets/packages/com.hg.render-pipelines/runtime/
// shaders/materials/characternpr/. Source temporary names below identify the
// expressions, not the imperfect prose reconstruction in the research docs.
//
// Include after the material/global/texture declarations and SampleSkinLUT3D.
// Preconditions: CP1.y=1; dry weather; opaque alpha with _AlphaPremultiply=0.
// CP2/CP5 are the cloth's captured environment/light colors. Face AND body
// use the separate Skin helper and CP3/CP4; the old b401 body match was false.
// Weather, irradiance volumes, local lights, motion vectors, screen-depth rims,
// and transparent premultiplication are outside this bounded implementation.
// The omitted capture rims are zero with CP8.rgb=0 and CP12.x=1.
//
// N must already contain the source (R*A,G) normal decode, normal scale, TBN,
// normalization and backface sign. The overload taking vertexNormalWS preserves
// b401's separate clearcoat normal. Both normals use the same backface sign.
// UVs are RAW mesh coordinates. Per-texture STs deliberately preserve imported
// DDS orientation; source vertices supplied a shared BaseMap-transformed UV.
// Source uses bias zero here (the original global mip bias is unavailable).

static const float3 EFClothLuminance = float3(0.2126729041, 0.7151522040, 0.0721750036);

float EFClothLuma(float3 color)
{
    return dot(color, EFClothLuminance);
}

float3 EFClothNormalize(float3 direction)
{
    return direction * rsqrt(max(dot(direction, direction), 1.175494351e-38));
}

struct EFClothLightingTerms
{
    float3 lightTerm;
    float3 diffuseTerm;
    float3 specLight;
    float specLightMultiplier;
    float ambientPeak;
};

// b471 _2063.._2182 / b401 _2089.._2192. The blue P-map channel participates
// in litMask/litView only; no uniform AO multiplier follows this computation.
EFClothLightingTerms EFClothDiffuseLighting(
    float3 diffuseColor, float3 shadowDiffuse, float3 N,
    float3 lightColor, float3 lightColorI, float4 ramp, float viewRampAlpha,
    float directionalShadow, float selfShadow, float shadowMask)
{
    EFClothLightingTerms result;
    float3 shadowDeep = shadowDiffuse * _CharacterParams0.z;
    float3 shadowDeep2 = shadowDeep * 0.65;
    float rampChroma = max(max(ramp.r, ramp.g), ramp.b) - min(min(ramp.r, ramp.g), ramp.b);
    float occlusion = shadowMask * selfShadow;
    float litMask = min(min(selfShadow, shadowMask), ramp.a);
    float litView = viewRampAlpha * occlusion;

    result.ambientPeak = lerp(_EnvironmentGlobalParams0.x, 1.0, _CharacterParams12.w)
        * _ExposureWithMiscParams.x;
    float ambientGradient = saturate(dot(N, _CharacterParams6.xyz) + _CharacterParams7.x)
        * _CharacterParams7.y + _CharacterParams7.z;
    float3 ambient = ambientGradient
        * lerp(_CharacterParams2.rgb, 1.0.xxx, _CharacterParams1.y * litMask);
    float3 shadowLight = ambient
        * lerp(min(lerp(0.65, 1.0, result.ambientPeak), 1.5),
               clamp(result.ambientPeak, 1.25, 1.75), _CharacterParams1.x)
        * _CharacterParams0.w;
    float3 directLight = (lerp(EFClothLuma(lightColorI).xxx, lightColorI, litMask)
        + ambient * clamp(result.ambientPeak, 0.0, 1.5)
            * ((1.0 - _CharacterParams12.y).xxx + lightColor * _CharacterParams12.y))
        * _CharacterParams0.y;
    result.lightTerm = lerp(shadowLight, directLight, directionalShadow);

    float3 baseSelected = lerp(
        lerp(lerp(EFClothLuma(shadowDeep2).xxx, shadowDeep2, 1.2),
             shadowDeep, saturate(occlusion * viewRampAlpha + ramp.a)),
        diffuseColor, litMask);
    float3 rampTinted = baseSelected * ((1.0 - rampChroma).xxx + ramp.rgb * rampChroma);
    float preserveLuminance = clamp(
        EFClothLuma(baseSelected) / max(EFClothLuma(rampTinted), 0.001), 0.0, 1.5);
    result.diffuseTerm = lerp(
        lerp(shadowDeep, lerp(EFClothLuma(diffuseColor).xxx, diffuseColor, 1.2), litView),
        rampTinted * preserveLuminance, directionalShadow);
    float litBlend = lerp(litView, litMask, directionalShadow);
    result.specLightMultiplier = lerp(_CharacterParams0.z, 1.0, litBlend);
    result.specLight = result.lightTerm * ((litBlend * 0.5 + 0.5) * result.specLightMultiplier);
    return result;
}

// Source compact environment BRDF, b401 _2399.._2423 / b471 _2362.._2385.
// The right-side polynomial inputs are ROUGHNESS^2 and ROUGHNESS^6, whereas
// the left side uses NdotV/NdotV^2/NdotV^3. They must not all become NdotV.
float3 EFClothEnvironmentBRDF(float NdotV, float roughness, float3 specColor)
{
    float nv2 = NdotV * NdotV;
    float nv3 = nv2 * NdotV;
    float r2 = roughness * roughness;
    float2 rhs2 = float2(1.0, r2);
    float3 rhs3 = float3(1.0, r2, r2 * r2 * r2);
    float2 nv = float2(1.0, NdotV);
    float fresA = dot(mul(nv, float2x2(
        float2(0.0365463011, 9.063199997), float2(3.327069998, -9.047559738))), rhs2)
        / dot(mul(float3(1.0, nv2, nv3), float3x3(
            float3(1.0, 9.044010162, 5.565889835),
            float3(3.596849918, -16.31739998, 19.78860092),
            float3(-1.367720008, 9.22949028, -20.21229935))), rhs3);
    float fresB = dot(mul(nv, float2x2(
        float2(0.990440011, 1.29677999), float2(-1.285140038, -0.7559069991))), rhs2)
        / dot(mul(float3(1.0, NdotV, nv3), float3x3(
            float3(1.0, 20.32250023, 121.5630035),
            float3(2.923379898, -27.03019905, 626.1300049),
            float3(59.41880035, 222.5919952, 316.6270142))), rhs3);
    float3 envFresnel = specColor * fresA + fresB.xxx;
    float envFresnelSum = fresA + fresB;
    return envFresnel + specColor * ((1.0 - envFresnelSum) / envFresnelSum) * envFresnel;
}

float3 EFClothSampleEnvironment(float3 N, float3 V, float roughness, float3 specColor)
{
    // Unity may supply a nonblack default for an unbound cube. Only evaluate
    // IBL when the profile explicitly binds recovered environment data.
    if (_EndfieldCapturedCubemapAvailable < 0.5) return 0.0.xxx;
    float lod = 1.2 * log2(max(roughness, 0.001)) + 5.0;
    return SAMPLE_TEXTURECUBE_LOD(_CharMaxCubemap, sampler_Endfield_LinearRepeat,
        reflect(-V, N), lod).rgb
        * EFClothEnvironmentBRDF(saturate(dot(N, V)), roughness, specColor);
}

float3 EndfieldShadeOfficialCloth(
    float2 uv, float3 albedo, float3 N, float3 vertexNormalWS, float3 V,
    float3 positionWS, float3 L, float3 lightColorI,
    float directionalShadow, float selfShadow)
{
    // L/lightColorI and directionalShadow arrive fully resolved by the caller:
    // L=lerp(-DirectionalLightDirection,CP11.xyz,CP1.w), WITHOUT normalization;
    // lightColorI=lerp(CustomData1.rgb,CP5.rgb,CP12.y)*lerp(CustomData1.w,1,CP12.w);
    // directionalShadow=lerp(lerp(1,SSM.r,DirectionalShadowParams.x),1,CP1.z).
    // selfShadow=SSM.g. A URP shadow/constant self-shadow at the call site is an
    // explicit approximation; the original HGRP screen-space mask is absent.
    // positionWS is unused because weather, volume sampling and rims are omitted.
    float lightIntensity = lerp(_EndfieldCapturedLightIntensity, 1.0, _CharacterParams12.w);
    float3 lightColor = lightColorI / max(lightIntensity, 1e-6);
    float4 packed = float4(_Metallic, _Specular, 1.0, _Smoothness);
    if (_UseMetallicGlossMap > 0.5)
        packed = SAMPLE_TEXTURE2D(_MetallicGlossMap, sampler_Endfield_LinearClamp,
            TRANSFORM_TEX(uv, _MetallicGlossMap));
    float metallic = packed.r;
    float specularMask = packed.g;
    float shadowMask = packed.b;
    float roughness = 1.0 - packed.a;
    float roughSq = max(roughness * roughness, 0.0078125);
    float a4 = roughSq * roughSq;
    float nonmetalDiffuse = 0.96 - metallic * 0.96;
    float3 diffuseColor = albedo * nonmetalDiffuse;
    float3 specColor = lerp((0.04 * specularMask).xxx, albedo, metallic);
    float3 shadowColor;
    if (_UseShadowLutTex > 0.5)
        shadowColor = SampleSkinLUT3D(_ShadowLutTex, sampler_Endfield_LinearClamp, albedo);
    else
    {
        float3 shadowBase = albedo * _ShadowColorBrightness;
        shadowColor = lerp(EFClothLuma(shadowBase).xxx, shadowBase, _ShadowColorSaturation);
    }

    float3 cameraAxisZ = mul((float3x3)UNITY_MATRIX_I_V, float3(0.0, 0.0, 1.0));
    float3 horizontalLight = EFClothNormalize(float3(L.x, 6.103515625e-5, L.z));
    float2 cameraHorizontal = cameraAxisZ.xz
        * rsqrt(max(dot(cameraAxisZ.xz, cameraAxisZ.xz), 1.175494351e-38));
    float backlit = saturate(-dot(horizontalLight.xz, cameraHorizontal));
    float NdotL = dot(N, L);
    float wrappedNdotL = -NdotL * (NdotL * 0.5 - 1.0) + 0.5;
    float rampInput = clamp(lerp(NdotL, wrappedNdotL,
        backlit * smoothstep(0.25, 0.75, 1.0 - abs(cameraAxisZ.y)) * (1.0 - _CharacterParams12.x))
        + _CharacterParams11.w * _CharacterParams12.x, -1.0, 1.0);
    float analyticRamp = smoothstep(0.25, 1.0, rampInput);
    float4 ramp = analyticRamp.xxxx;
    float viewRampAlpha = smoothstep(0.25, 1.0, dot(N, cameraAxisZ));
    if (_UseDiffRampMap > 0.5)
    {
        // b471 explicitly uses LinearRepeat and LOD 0 for both ramp samples.
        float2 rampUV = float2(rampInput * 0.5 + 0.5, 0.5);
        ramp = SAMPLE_TEXTURE2D_LOD(_DiffRampMap, sampler_Endfield_LinearRepeat,
            TRANSFORM_TEX(rampUV, _DiffRampMap), 0);
        float2 viewRampUV = float2(dot(N, cameraAxisZ) * 0.5 + 0.5, 0.5);
        viewRampAlpha = SAMPLE_TEXTURE2D_LOD(_DiffRampMap, sampler_Endfield_LinearRepeat,
            TRANSFORM_TEX(viewRampUV, _DiffRampMap), 0).a;
    }
    EFClothLightingTerms lighting = EFClothDiffuseLighting(
        diffuseColor, shadowColor * nonmetalDiffuse, N, lightColor, lightColorI,
        ramp, viewRampAlpha, directionalShadow, selfShadow, shadowMask);

    // b471 _2190.._2238 / b401 _2200.._2234: pseudo-light GGX half-vector.
    float3 pseudoLight = float3(cameraAxisZ.x, lerp(0.5, L.y, directionalShadow), cameraAxisZ.z);
    float3 H = EFClothNormalize(L * directionalShadow + EFClothNormalize(pseudoLight) * 2.0
        + V * (2.0 + directionalShadow));
    float NdotV = saturate(dot(N, V));
    float NdotH = dot(N, H);
    float denominator = ((NdotH * a4) - NdotH) * NdotH + 1.0;
    float denominatorSquared = denominator * denominator;
    float distribution = a4 != denominatorSquared ? a4 / denominatorSquared : 1.0;
    float ggx = clamp(distribution * (0.5 / (2.0 * NdotV + roughSq + 1e-4))
        - 6.103515625e-5, 0.0, 20.0);
    float3 directSpecColor = specColor;
    float3 environmentSpecColor = specColor;
    if (_UseSpecRampMap > 0.5)
    {
        float2 specRampUV = float2(
            lerp(distribution / min(1.0 / (a4 + 1e-4), 65504.0),
                 NdotV * NdotV, _SpecRampIridescentMode),
            roughness * (1.0 - metallic));
        directSpecColor *= SAMPLE_TEXTURE2D_LOD(_SpecRampMap, sampler_Endfield_LinearRepeat,
            TRANSFORM_TEX(specRampUV, _SpecRampMap), 0).rgb;
        environmentSpecColor = lerp(specColor, directSpecColor, _SpecRampIridescentMode);
    }
    float3 specular = directSpecColor * ggx;

    // b401 _1129.._1147 / _2235.._2278: actual five-power Schlick Fresnel.
    float clearcoatMask = 0.0;
    if (_ClearCoat > 0.5)
        clearcoatMask = SAMPLE_TEXTURE2D(_ClearCoatMask, sampler_Endfield_LinearClamp,
            TRANSFORM_TEX(uv, _ClearCoatMask)).r;
    float clearcoatRoughness = 1.0 - _ClearCoatSmoothness;
    float clearcoatRoughSq = max(clearcoatRoughness * clearcoatRoughness, 0.0078125);
    float3 clearcoatF0 = _ClearCoatColor.rgb * lerp(0.04, 1.0, _ClearCoatMetallic);
    float3 clearcoatN = lerp(vertexNormalWS, N, _ClearCoatNormalMode);
    float3 diffuseAttenuation = 1.0.xxx;
    if (clearcoatMask > 0.001)
    {
        float oneMinusVdotH = 1.0 - saturate(dot(V, H));
        float fresnel2 = oneMinusVdotH * oneMinusVdotH;
        float fresnel5 = oneMinusVdotH * fresnel2 * fresnel2;
        float3 clearcoatFresnel = (clearcoatF0 * (1.0 - fresnel5) + fresnel5.xxx) * clearcoatMask;
        float3 transmittance = 1.0.xxx - clearcoatFresnel;
        diffuseAttenuation = lerp(1.0.xxx, transmittance, clearcoatMask);
        float clearcoatNdotH = dot(clearcoatN, H);
        float clearcoatNdotV = saturate(dot(clearcoatN, V));
        float clearcoatA4 = clearcoatRoughSq * clearcoatRoughSq;
        float clearcoatDenom = ((clearcoatNdotH * clearcoatA4) - clearcoatNdotH) * clearcoatNdotH + 1.0;
        float clearcoatDenom2 = clearcoatDenom * clearcoatDenom;
        float clearcoatDistribution = clearcoatA4 != clearcoatDenom2 ? clearcoatA4 / clearcoatDenom2 : 1.0;
        float3 clearcoatSpecular = clamp(clearcoatFresnel * clearcoatDistribution
            * (0.5 / (2.0 * clearcoatNdotV + clearcoatRoughSq + 1e-4)), 0.0.xxx, 20.0.xxx);
        specular = specular * transmittance * transmittance + clearcoatSpecular;
    }

    float3 color = lighting.lightTerm * lighting.diffuseTerm * diffuseAttenuation
        + specular * lighting.specLight * _CharacterParams13.w;
    float luminance = EFClothLuma(color);
    float saturationBoost = clamp(luminance - 0.5, 0.0, 0.5);
    color = lerp(luminance.xxx, color, 1.0 + saturationBoost * saturationBoost);

    // Source orders IBL AFTER the direct-light saturation boost. Its scale uses
    // specLightMultiplier rather than the complete directional specLight term.
    float3 environment = EFClothSampleEnvironment(N, V, roughness, environmentSpecColor);
    if (clearcoatMask > 0.001)
        environment += EFClothSampleEnvironment(clearcoatN, V, clearcoatRoughness, clearcoatF0)
            * clearcoatMask;
    color += environment * (clamp(lighting.ambientPeak, 0.5, 1.5) * _CharacterParams0.w)
        * lighting.specLightMultiplier * _CharacterParams2.rgb;
    return color; // Linear RGB before VFX, output exposure and fog; do not boost saturation again.
}

// Minimal API: callers without a separate geometric normal can still shade
// cloth. For b401 clearcoat NormalMode=0, call the overload above for fidelity.
float3 EndfieldShadeOfficialCloth(
    float2 uv, float3 albedo, float3 N, float3 V,
    float3 positionWS, float3 L, float3 lightColorI,
    float directionalShadow, float selfShadow)
{
    return EndfieldShadeOfficialCloth(uv, albedo, N, N, V,
        positionWS, L, lightColorI, directionalShadow, selfShadow);
}

#endif
