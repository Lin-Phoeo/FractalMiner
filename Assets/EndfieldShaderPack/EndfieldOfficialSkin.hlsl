#ifndef ENDFIELD_OFFICIAL_SKIN_INCLUDED
#define ENDFIELD_OFFICIAL_SKIN_INCLUDED

// Bounded port of characternpr_skin/Sub0_Pass0_Fragment_b138.hlsl (SDF face)
// and b114 (body). Line references below are b138 unless explicitly marked.
// Frame 6411: dry, opaque, flat environment (CP1.y=1), CP8.rgb=CP14.rgb=0,
// no punctual lights. Caller supplies original decoded N, view direction V,
// source light direction L and intensity-scaled lightColorI, plus albedo after
// EmotionMap but BEFORE the legacy skin-rim tint. Return is linear RGB after
// source saturation, before VFX adjustment, exposure and fog.
// Auxiliary textures use original UVs; only BaseMap applies its imported ST.
// Implicit-LOD fetches assume a zero source _GlobalMipBias.

float3 EndfieldSkinSafeNormalize(float3 v)
{
    // The source uses this float-min guard for several normalizations. Extend
    // it to its unguarded normalize calls so a degenerate axis stays finite.
    return v * rsqrt(max(dot(v, v), 1.1754943508222875e-38));
}

float2 EndfieldSkinSafeNormalize(float2 v)
{
    return v * rsqrt(max(dot(v, v), 1.1754943508222875e-38));
}

float3 EndfieldSkinShadowLUT(float3 albedo)
{
    // b138:429-438. The 32^3 LUT indexes sRGB values, and both fetches are
    // explicitly level 0 / repeat. Do not use a post-rim albedo as the index.
    float3 low = albedo * 12.92;
    float3 high = pow(abs(albedo), 0.4166666567325592) * 1.055 - 0.055;
    float3 indexColor = saturate(float3(
        albedo.r <= 0.00313080009073019 ? low.r : high.r,
        albedo.g <= 0.00313080009073019 ? low.g : high.g,
        albedo.b <= 0.00313080009073019 ? low.b : high.b));
    float blue = indexColor.b * 31.0;
    float slice = floor(blue);
    float2 lutUV = indexColor.rg * 31.0 * float2(1.0 / 1024.0, 1.0 / 32.0)
                 + float2(0.5 / 1024.0, 0.5 / 32.0);
    lutUV.x += slice / 32.0;
    float3 first = SAMPLE_TEXTURE2D_LOD(_ShadowLutTex, sampler_Endfield_LinearRepeat, lutUV, 0).rgb;
    float3 second = SAMPLE_TEXTURE2D_LOD(_ShadowLutTex, sampler_Endfield_LinearRepeat,
                                       lutUV + float2(1.0 / 32.0, 0), 0).rgb;
    return lerp(first, second, blue - slice);
}

float3 EndfieldShadeOfficialSkin(float2 uv, float3 albedo, float3 N, float3 V,
                                float3 positionWS, float3 L, float3 lightColorI,
                                float directionalShadow, float selfShadow)
{
    const float3 luminanceWeights = float3(0.2126729041337967, 0.7151522040367126, 0.07217500358819962);
    const float horizontalEpsilon = 6.103515625e-05;

    // b138:424-426,439-442,450-475. Alpha is a lighting mask even on an
    // opaque face, and is not multiplied by BaseColor.a or EmotionMap.a.
    float baseAlpha = SAMPLE_TEXTURE2D(_BaseMap, sampler_Endfield_LinearClamp,
                                      uv * _BaseMap_ST.xy + _BaseMap_ST.zw).a;
    // Body b114 has no SDF descriptors. It is the normal-weight=1 skin path,
    // NOT the cloth b401 variant suggested by the old buffer-size matcher.
    bool hasSDF = _UseSDFLightmap > 0.5;
    float4 mask = hasSDF ? SAMPLE_TEXTURE2D(_SDFMask, sampler_Endfield_LinearRepeat, uv)
                        : float4(1.0, 1.0, 1.0, 0.0);
    float normalWeight = mask.y; // 0 selects SDF; 1 selects normal-based light.
    float4x4 objectToWorld = GetObjectToWorldMatrix();
    float3x3 objectBasis = (float3x3)objectToWorld;
    float3 rootToPixel = positionWS - float3(objectToWorld[0].w, 0, objectToWorld[2].w);
    rootToPixel.y = horizontalEpsilon;
    float3 rootToPixelHorizontal = EndfieldSkinSafeNormalize(rootToPixel);
    float3 horizontalN = EndfieldSkinSafeNormalize(float3(N.x, horizontalEpsilon, N.z));
    float3 ambientN = EndfieldSkinSafeNormalize(lerp(rootToPixelHorizontal, horizontalN, normalWeight));

    // _580 is the world-space view +Z axis, not the per-pixel view vector.
    // mul(worldDirection, objectBasis) preserves the source's O2W transpose
    // operation, including scale; an inverse-transform helper would differ.
    float3 cameraAxis = mul((float3x3)UNITY_MATRIX_I_V, float3(0, 0, 1));
    float3 cameraAxisOS = mul(cameraAxis, objectBasis);
    float cameraHorizontalZ = EndfieldSkinSafeNormalize(cameraAxisOS.xz).y;

    // b138:626-632,664-720. _SkinRimOff is a UI property and is not read by
    // this compiled variant: its mask/scale-controlled rim tint is unconditional.
    float3 shadowColor = EndfieldSkinShadowLUT(albedo);
    float rimMask = mask.x * lerp(saturate(cameraHorizontalZ + 0.5), 1.0, normalWeight);
    float NdotV = saturate(dot(N, V));
    float rimAmount = saturate((1.0 - saturate(NdotV * 0.85 + 0.15))
                               * rimMask * lerp(_FaceRimOffScale, _SkinRimOffScale, mask.z));
    float3 diffuseBase = albedo * ((1.0 - rimAmount) + _SDFRimColor.rgb * rimAmount);
    float specStrength = _Specular * normalWeight;
    float diffuseScale = 0.96 - _Metallic * 0.96;
    float3 diffuseColor = diffuseBase * diffuseScale;
    float3 specColor = lerp(0.04 * specStrength, diffuseBase, _Metallic);
    float3 shadowDiffuse = shadowColor * diffuseScale;
    float perceptualRoughness = 1.0 - _Smoothness;
    float roughness = max(perceptualRoughness * perceptualRoughness, 0.0078125);

    // b138:727-757. Caller has already resolved the shadow strength and CP1.z
    // ignore-directional-shadow override; do not apply that override twice.
    float shadowDir = directionalShadow;
    float lightIntensity = lerp(_EndfieldCapturedLightIntensity, 1.0, _CharacterParams12.w);
    float3 lightColor = lightColorI / max(lightIntensity, 1.1754943508222875e-38);
    float3 shadowDeep = shadowDiffuse * _CharacterParams0.z;
    float3 shadowDeep2 = shadowDeep * 0.65;
    float normalLight = clamp(dot(N, L) + _CharacterParams11.w * _CharacterParams12.x, -1.0, 1.0);
    float rampX = normalLight * 0.5 + 0.5;
    if (hasSDF)
    {
        float3 lightHorizontalOS = mul(L, objectBasis);
        lightHorizontalOS.y = horizontalEpsilon;
        lightHorizontalOS = EndfieldSkinSafeNormalize(lightHorizontalOS);
        float side = lightHorizontalOS.x > 0.0 ? 1.0 : 0.0;
        float2 sdfUV = float2(lerp(1.0 - uv.x, uv.x, side), uv.y);
        float4 sdf = SAMPLE_TEXTURE2D_LOD(_SDFLightmap, sampler_Endfield_LinearRepeat, sdfUV, 0);
        // sdf.z supplies _1529 only for excluded rim/punctual-light branches.
        // sdf.a (_1530) is likewise only consumed by punctual lighting (line 1110).
        float lightFront = lightHorizontalOS.z;
        float backlightWeight = saturate(-dot(
            EndfieldSkinSafeNormalize(float3(L.x, horizontalEpsilon, L.z)).xz,
            EndfieldSkinSafeNormalize(cameraAxis.xz)))
            * saturate(-lightFront) * (1.0 - _CharacterParams12.x);
        float sdfBack = lerp(lightFront, (-lightFront) * (lightFront * 0.5 - 1.0) + 0.5,
                             backlightWeight) * 0.5;
        float sdfCenter = clamp(0.5 - sdfBack, 0.001, 0.999);
        float sdfGradient = (sdf.x + sdf.y) * 0.5;
        float sdfTransition = smoothstep(max(sdfCenter - (1.0 - sdfCenter), 0.0),
                                        min(sdfCenter + sdfCenter, 1.0), sdfGradient);
        // Keep the subtraction INSIDE abs: this is the exact source expression.
        float sdfLight = lerp(-1.0, 1.0, abs(-sdfTransition - sdfBack * ceil(sdfBack)));
        rampX = lerp(sdfLight, normalLight, normalWeight) * 0.5 + 0.5;
    }
    float4 ramp = SAMPLE_TEXTURE2D_LOD(_DiffRampMap, sampler_Endfield_LinearRepeat, float2(rampX, 0.5), 0);

    // b138:758-777. Ramp alpha is the lit-mask gate; RGB supplies chroma.
    float rampChroma = max(max(ramp.r, ramp.g), ramp.b) - min(min(ramp.r, ramp.g), ramp.b);
    float selfShadowWeight = max(normalWeight, mask.z * smoothstep(0.75, 0.25, cameraHorizontalZ));
    float occlusion = (1.0 - selfShadowWeight) + selfShadow * selfShadowWeight;
    float litMask = min(min(occlusion, baseAlpha), ramp.a);
    float occlusionAlpha = baseAlpha * occlusion;
    float ambientPeak = lerp(_EnvironmentGlobalParams0.x, 1.0, _CharacterParams12.w) * _ExposureWithMiscParams.x;
    float ambientGradient = saturate(dot(ambientN, _CharacterParams6.xyz) + _CharacterParams7.x)
                            * _CharacterParams7.y + _CharacterParams7.z;
    float3 ambient = ambientGradient * lerp(_CharacterParams3.rgb, 1.0, _CharacterParams1.y * litMask);
    float shadowAmbient = lerp(min(lerp(0.65, 1.0, ambientPeak), 1.5),
                              clamp(ambientPeak, 1.25, 1.75), _CharacterParams1.x);
    float3 lightTerm = lerp(ambient * shadowAmbient * _CharacterParams0.w,
        (lerp(dot(lightColorI, luminanceWeights), lightColorI, litMask)
         + ambient * clamp(ambientPeak, 0.0, 1.5)
           * ((1.0 - _CharacterParams12.y) + lightColor * _CharacterParams12.y)) * _CharacterParams0.y,
        shadowDir);
    float3 baseSelection = lerp(lerp(
        lerp(dot(shadowDeep2, luminanceWeights), shadowDeep2, 1.2), shadowDeep,
        saturate(baseAlpha * ((1.0 - normalWeight) + occlusion * normalWeight) + ramp.a)),
        diffuseColor, litMask);
    float3 rampTinted = baseSelection * ((1.0 - rampChroma) + ramp.rgb * rampChroma);
    float rampLuminanceScale = clamp(dot(baseSelection, luminanceWeights)
                                    / max(dot(rampTinted, luminanceWeights), 0.001), 0.0, 1.5);
    float3 diffuseTerm = lerp(
        lerp(shadowDeep, lerp(dot(diffuseColor, luminanceWeights), diffuseColor, 1.2), occlusionAlpha),
        rampTinted * rampLuminanceScale, shadowDir);
    float litBlend = lerp(occlusionAlpha, litMask, shadowDir);
    float3 specLight = lightTerm * ((litBlend * 0.5 + 0.5) * lerp(_CharacterParams0.z, 1.0, litBlend));

    // b138:778-796. Direct GGX uses original N (_1266), NOT the SDF normal
    // _1529. Normalize the artificial light before its factor of two. CP13.w
    // scales GGX only; the separately added highlight map is not multiplied.
    float3 artificialLight = EndfieldSkinSafeNormalize(float3(cameraAxis.x, lerp(0.5, L.y, shadowDir), cameraAxis.z));
    float3 H = EndfieldSkinSafeNormalize(L * shadowDir + artificialLight * 2.0 + V * (2.0 + shadowDir));
    float NdotH = dot(N, H);
    float roughnessSquared = roughness * roughness;
    float denominator = ((NdotH * roughnessSquared - NdotH) * NdotH) + 1.0;
    float denominatorSquared = denominator * denominator;
    float distribution = roughnessSquared != denominatorSquared ? roughnessSquared / denominatorSquared : 1.0;
    float visibility = 0.5 / (2.0 * NdotV + roughness * ((1.0 + NdotV) - NdotV) + 0.0001);
    float specular = clamp(distribution * visibility - horizontalEpsilon, 0.0, 20.0);
    float2 highlightUV = uv + mul(V, objectBasis).xy * _HighlightMapVector.xy;
    float3 highlight = hasSDF ? SAMPLE_TEXTURE2D(_HighlightMap, sampler_Endfield_LinearClamp, highlightUV).rgb
                              : 0.0.xxx;
    float3 color = lightTerm * diffuseTerm
                 + specColor * specular * specLight * _CharacterParams13.w
                 + highlight * specLight;

    // b138:797-803; the frame's two zero-color rim terms contribute zero.
    float luminance = dot(color, luminanceWeights);
    float saturation = clamp(luminance - 0.5, 0.0, 0.5);
    return lerp(luminance, color, saturation * saturation + 1.0);
}

#endif
