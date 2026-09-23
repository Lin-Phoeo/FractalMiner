#ifndef ENDFIELD_OFFICIAL_HAIR_INCLUDED
#define ENDFIELD_OFFICIAL_HAIR_INCLUDED

// CharacterNPR_Hair ForwardLit b125, dry/flat-environment subset.
// Evidence: _dump_1.5.3/.../characternpr_hair/Sub0_Pass0_Fragment_b125.hlsl
// (source identifiers below refer to that file), and
// docs/research/official-forwardlit-hair-b125.md.
//
// Include after EndfieldCharacterLit's material/global/texture declarations.
// Preconditions: CP1.y >= .5 (captured value 1), dry opaque material with
// _AlphaPremultiply = 0, and the b125 normal/diffuse/spec/line texture variant.
// N is already decoded from BumpMap RGorAG: x = (R*A)*2-1, y = G*2-1,
// z = max(1e-16, sqrt(1-saturate(dot(xy,xy)))), THEN xy *= _BumpScale;
// transform through the geometric TBN, normalize, then apply the backface sign.
// There is NO split RG/BA specular normal in b125; diffuse/spec use the same N.
//
// Explicitly unsupported: irradiance clipmaps/SH (CP1.y < .5), rain/wetness/
// water/snow, screen-depth rim, punctual lights/cookies/shadows, motion vectors,
// transparent premultiplication, and the original HGRP fog composition.
// Skinned per-draw matrices are supplied here by Unity's object transform.
// Source uv0 already has BaseMap_ST applied; this port deliberately accepts RAW
// mesh UVs and applies each texture's own ST, preserving independent imported
// texture orientation. Ramp STs default to identity, as in source b125.
// No legacy diffuse/shade, extra material AO, or generic specular tint is used.

// Unity inline sampler naming selects linear filtering and mirror addressing.
// Private name avoids collision with URP's version-dependent global samplers.
SAMPLER(sampler_EFHair_LinearMirror);

static const float3 EFHairLuminance = float3(0.2126729041, 0.7151522040, 0.0721750036);

float EFHairLuma(float3 color)
{
    return dot(color, EFHairLuminance);
}

float EFHairMax3(float3 value)
{
    return max(max(value.x, value.y), value.z);
}

float3 EFHairNormalize(float3 value)
{
    // Same finite lower bound used by source _560 and _569. For a degenerate
    // imported direction, zero remains zero instead of generating NaNs.
    return value * rsqrt(max(dot(value, value), 1.175494351e-38));
}

float2 EFHairNormalizeXZ(float2 value)
{
    return value * rsqrt(max(dot(value, value), 1.175494351e-38));
}

float EFHairSineLobe(float tangentDotHalf, float exponent)
{
    // Saturation only protects the roundoff case |dot| > 1. Source writes
    // sqrt(1-dot*dot), then clamps the sine to 1e-4 before exponentiation.
    return pow(max(sqrt(saturate(1.0 - tangentDotHalf * tangentDotHalf)), 1e-4), exponent);
}

struct EFHairLightingTerms
{
    float3 lightTerm;
    float3 diffuseTerm;
    float3 specLight;
    float3 diffuseColor;
};

// b125 _2085, _2174.._2296. Keeping samples as explicit inputs allows synthetic
// ramp-alpha / shadow numerical probes without relying on texture content.
EFHairLightingTerms EFHairDiffuseLighting(
    float3 albedo, float3 N, float3 lightColor, float3 lightColorI,
    float4 ramp, float viewRampAlpha,
    float directionalShadow, float selfShadow, float shadowMask)
{
    EFHairLightingTerms result;
    result.diffuseColor = albedo * 0.96;
    float3 shadowBase = albedo * _ShadowColorBrightness;
    shadowBase = lerp(EFHairLuma(shadowBase).xxx, shadowBase, _ShadowColorSaturation);
    float3 shadowDeep = shadowBase * (0.96 * _CharacterParams0.z);
    float3 shadowDeep2 = shadowDeep * 0.65;
    float lumDiffuse = EFHairLuma(result.diffuseColor);

    float rampChroma = EFHairMax3(ramp.rgb) - min(min(ramp.r, ramp.g), ramp.b);
    float occlusion = shadowMask * selfShadow;
    float litMask = min(min(selfShadow, shadowMask), ramp.a);
    float litView = viewRampAlpha * occlusion;

    // Flat environment branch: _1147=0, _1148=1, _1149=CP2, _1150=_653.
    float ambientPeak = lerp(_EnvironmentGlobalParams0.x, 1.0, _CharacterParams12.w)
        * _ExposureWithMiscParams.x;
    float ambientGradient = saturate(dot(N, _CharacterParams6.xyz) + _CharacterParams7.x)
        * _CharacterParams7.y + _CharacterParams7.z;
    float3 ambient = ambientGradient
        * lerp(_CharacterParams2.rgb, 1.0.xxx, _CharacterParams1.y * litMask);
    float3 shadowLight = ambient
        * lerp(min(lerp(0.65, 1.0, ambientPeak), 1.5),
               clamp(ambientPeak, 1.25, 1.75), _CharacterParams1.x)
        * _CharacterParams0.w;
    float3 directLight = (lerp(EFHairLuma(lightColorI).xxx, lightColorI, litMask)
        + ambient * clamp(ambientPeak, 0.0, 1.5)
            * ((1.0 - _CharacterParams12.y).xxx + lightColor * _CharacterParams12.y))
        * _CharacterParams0.y;
    result.lightTerm = lerp(shadowLight, directLight, directionalShadow);

    float3 baseSelected = lerp(
        lerp(lerp(EFHairLuma(shadowDeep2).xxx, shadowDeep2, 1.2),
             shadowDeep, saturate(occlusion * viewRampAlpha + ramp.a)),
        result.diffuseColor, litMask);
    float3 rampTinted = baseSelected * ((1.0 - rampChroma).xxx + ramp.rgb * rampChroma);
    float preserveLuminance = clamp(
        EFHairLuma(baseSelected) / max(EFHairLuma(rampTinted), 0.001), 0.0, 1.5);
    result.diffuseTerm = lerp(
        lerp(shadowDeep, lerp(lumDiffuse.xxx, result.diffuseColor, 1.2), litView),
        rampTinted * preserveLuminance, directionalShadow);

    float litBlend = lerp(litView, litMask, directionalShadow);
    result.specLight = result.lightTerm * ((litBlend * 0.5 + 0.5)
        * lerp(_CharacterParams0.z, 1.0, litBlend));
    return result;
}

float3 EndfieldShadeOfficialHair(
    float2 uv, float3 albedo, float3 N, float3 V, float4 tangentWS,
    float3 positionWS, float3 L, float3 lightColorI,
    float directionalShadow, float selfShadow)
{
    // L and lightColorI are already resolved by the caller. In b125:
    // L = lerp(-DirectionalLightDirection, CP11.xyz, CP1.w), WITHOUT normalize;
    // lightColorI = lerp(CustomData1.rgb, CP5.rgb, CP12.y)
    //             * lerp(CustomData1.w, 1, CP12.w).
    // _EndfieldCapturedLightIntensity stores CustomData1.w (capture: 1.6243868).
    // directionalShadow must be the already-resolved source _2166:
    // lerp(lerp(1, SSM.r, DirectionalShadowParams.x), 1, CP1.z).
    // selfShadow is SSM.g. URP main-light shadow/constant selfShadow are explicit
    // approximations at the call site; neither recovers the missing HGRP SSM.
    // positionWS is intentionally unused in the flat, dry, no-depth-rim subset.

    float lightIntensity = lerp(_EndfieldCapturedLightIntensity, 1.0, _CharacterParams12.w);
    float3 lightColor = lightColorI / max(lightIntensity, 1e-6);
    // No global mip-bias input is exposed by this port; Sample uses bias zero.
    float4 packed = SAMPLE_TEXTURE2D(_MetallicGlossMap, sampler_Endfield_LinearRepeat,
        TRANSFORM_TEX(uv, _MetallicGlossMap));
    float anisotropySelector = packed.r;
    float specularMask = packed.g;
    float shadowMask = packed.b;
    float secondarySpecularMask = packed.a;

    float3 cameraAxisZ = mul((float3x3)UNITY_MATRIX_I_V, float3(0.0, 0.0, 1.0));
    float3 horizontalLight = EFHairNormalize(float3(L.x, 6.103515625e-5, L.z));
    float backlit = saturate(-dot(horizontalLight.xz, EFHairNormalizeXZ(cameraAxisZ.xz)));
    float backlightEnabled = 1.0 - _CharacterParams12.x;
    float NdotL = dot(N, L);
    float wrappedNdotL = -NdotL * (NdotL * 0.5 - 1.0) + 0.5;
    float rampInput = lerp(NdotL, wrappedNdotL,
        backlit * smoothstep(0.25, 0.75, 1.0 - abs(cameraAxisZ.y)) * backlightEnabled)
        + _CharacterParams11.w * _CharacterParams12.x;
    float2 rampUV = float2(clamp(rampInput, -1.0, 1.0) * 0.5 + 0.5, 0.5);
    float4 ramp = SAMPLE_TEXTURE2D_LOD(_DiffRampMap, sampler_EFHair_LinearMirror,
        TRANSFORM_TEX(rampUV, _DiffRampMap), 0);
    float2 viewRampUV = float2(dot(N, cameraAxisZ) * 0.5 + 0.5, 0.5);
    float viewRampAlpha = SAMPLE_TEXTURE2D_LOD(_DiffRampMap, sampler_EFHair_LinearMirror,
        TRANSFORM_TEX(viewRampUV, _DiffRampMap), 0).a;
    EFHairLightingTerms lighting = EFHairDiffuseLighting(albedo, N, lightColor, lightColorI,
        ramp, viewRampAlpha, directionalShadow, selfShadow, shadowMask);

    // b125 _568.._592: source uses the transpose of object-to-world for N/V,
    // not world-to-object. Preserve it (including non-uniform scale behavior).
    float3x3 objectToWorld = (float3x3)GetObjectToWorldMatrix();
    float3 objectUp = EFHairNormalize(mul(objectToWorld, float3(_AnisotropyDirX, 1.0, 0.0)));
    float3 strandDirection = cross(N,
        lerp(cross(N, objectUp), tangentWS.xyz, anisotropySelector))
        * lerp(1.0, tangentWS.w, anisotropySelector);
    // Do not normalize strandDirection before adding the lobe normal shifts.
    float3 viewObject = mul(V, objectToWorld);
    float3 normalObject = mul(N, objectToWorld);
    float edgeFade = pow(saturate(dot(EFHairNormalizeXZ(normalObject.xz),
        EFHairNormalizeXZ(viewObject.xz))), _AnisotropyEdgeFade);

    // b125 _2299.._2315: pseudo-light is essential to the captured hair band.
    float lightY = lerp(0.5, L.y, directionalShadow);
    float3 pseudoLight = mul(objectToWorld, float3(viewObject.x, lightY, viewObject.z));
    float3 H = EFHairNormalize(L * directionalShadow + pseudoLight * 2.0) + V;
    H *= rsqrt(max(6.103515625e-5, dot(H, H)));
    float3 primaryTangent = EFHairNormalize(strandDirection + N * (_AnisotropyValue * 2.0 - 1.0));
    float primaryDotHalf = dot(primaryTangent, H);
    float primaryLobe = saturate(EFHairSineLobe(primaryDotHalf, 200.0) * specularMask);
    float2 specRampUV = float2(primaryLobe, (primaryDotHalf > 0.0 ? 1.0 : 0.0) * edgeFade * edgeFade);
    float3 primaryRamp = SAMPLE_TEXTURE2D_LOD(_SpecRampMap, sampler_EFHair_LinearMirror,
        TRANSFORM_TEX(specRampUV, _SpecRampMap), 0).rgb;
    float3 primarySpecular = primaryLobe * primaryRamp * edgeFade;
    float primaryPeak = EFHairMax3(primarySpecular);

    float3 secondaryTangent = EFHairNormalize(strandDirection + N * (_AnisotropyValue2 * 2.0 - 1.0));
    float secondaryExponent = (float)((int)(200.0 * max(1.0 - _AnisotropyRange2, 0.0)));
    float3 secondarySpecular = EFHairSineLobe(dot(secondaryTangent, H), secondaryExponent)
        * edgeFade * _AnisotropyColor2.rgb * secondarySpecularMask;

    float3 lineTangent = EFHairNormalize(strandDirection + N * (2.0 * _LineValue - 1.0));
    float lineExponent = (float)((int)(200.0 * max(1.0 - _LineRange, 0.0)));
    float lineWidth = saturate(EFHairSineLobe(dot(lineTangent, H), lineExponent));
    float lineProcedural = ceil(saturate(frac(uv.x * _LineAmount) - 0.5));
    float lineSample = SAMPLE_TEXTURE2D(_LineMap, sampler_Endfield_LinearRepeat,
        TRANSFORM_TEX(uv, _LineMap)).r;
    float lineMask = lerp(lineProcedural, 1.0 - lineSample, _UseLineMap);
    float lineFactor = lerp(1.0,
        lerp(1.0, lerp(lerp(1.0 - _LineIntensity, 1.0, lineMask), 1.0, primaryPeak), lineWidth),
        specularMask);
    float3 specular = (primarySpecular * (0.04 * specularMask) * _AnisotropyIntensity * 5.0
        + lerp(secondarySpecular, 0.0.xxx, primaryPeak))
        * lighting.specLight * _CharacterParams13.w;
    float3 diffuseLit = lighting.lightTerm * lighting.diffuseTerm * lineFactor;
    float3 diffuse = lerp(EFHairLuma(diffuseLit).xxx, diffuseLit,
        lerp(_LineSaturation, 1.0, lineFactor));
    float3 color = diffuse + specular;

    // b125 _2470.._2616: source saturation boost, then non-depth backlight rim.
    // Caller must skip the legacy saturation boost to avoid applying it twice.
    float luminance = EFHairLuma(color);
    float saturationBoost = clamp(luminance - 0.5, 0.0, 0.5);
    color = lerp(luminance.xxx, color, 1.0 + saturationBoost * saturationBoost);
    float horizontalNdotL = dot(horizontalLight, N);
    float inverseShadow = 1.0 - directionalShadow;
    float3 edgeLight = lerp(1.0.xxx, lightColorI, directionalShadow)
        * saturate(lerp(0.0, -horizontalNdotL * (horizontalNdotL * 0.5 - 1.0) + 0.5, directionalShadow))
        * ((inverseShadow + backlit * directionalShadow) * backlightEnabled)
        * smoothstep(0.6, 0.8, 1.0 - abs(dot(V, N)))
        * min(shadowMask, selfShadow)
        * (inverseShadow + smoothstep(0.1, 0.04, EFHairLuma(lighting.diffuseColor)) * directionalShadow)
        * max(0.15.xxx, lighting.diffuseColor);

    // Final linear RGB BEFORE VFX/fog/output exposure. The source applies VFX
    // first, then _ExposureWithMiscParams.y, then HGRP fog. Caller owns those.
    return color + edgeLight;
}

#endif
