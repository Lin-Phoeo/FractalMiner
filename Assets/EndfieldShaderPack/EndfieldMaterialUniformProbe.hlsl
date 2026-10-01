#ifndef ENDFIELD_MATERIAL_UNIFORM_PROBE_INCLUDED
#define ENDFIELD_MATERIAL_UNIFORM_PROBE_INCLUDED

// Explicit numeric diagnostic only (mode 100..120), normal output unaffected.
// Read the real production UnityPerMaterial upload, not Material.GetColor or
// another shader's copied declarations. Used by isolated Editor audit.
float4 EFMaterialUniformProbe(int index)
{
    switch(index)
    {
        case 0: return _BaseColor;
        case 1: return _EmissionColor;
        case 2: return _ColorAdjustmentColorBlend;
        case 3: return _ColorAdjustmentRimColor;
        case 4: return _BaseMap_ST;
        case 5: return _SDFRimColor;
        case 6: return _EyeScatteringColor;
        case 7: return _EyeHighLightColor;
        case 8: return _MatcapColor;
        case 9: return _AnisotropyColor2;
        case 10: return _HighlightMapVector;
        case 11: return _LineMap_ST;
        case 12: return float4(_Smoothness,_Specular,_Metallic,_BumpScale);
        case 13: return float4(_BackFaceNormalFlip,_AlphaPremultiply,_EmissionBrightness,_SurfaceType);
        case 14: return float4(_EnableVFXColorAdjustment,_ColorAdjustmentBrightness,_ColorAdjustmentSaturation,_ColorAdjustmentContrast);
        case 15: return float4(_ColorAdjustmentRimWidth,_ColorAdjustmentRimIntensity,_ShadowColorBrightness,_ShadowColorSaturation);
        case 16: return float4(_SkinRimOffScale,_FaceRimOffScale,_EmotionIndex,_EmotionBlend);
        case 17: return float4(_SpecBumpScale,_AnisotropyValue,_AnisotropyValue2,_AnisotropyIntensity);
        case 18: return float4(_AnisotropyEdgeFade,_AnisotropyRange2,_AnisotropyDirX,_SpecRampIridescentMode);
        case 19: return float4(_LineAmount,_LineValue,_LineRange,_LineIntensity);
        case 20: return float4(_LineSaturation,_UseLineMap,_ParallaxScale,_MatcapNormalScale);
    }
    return 0;
}
#endif
