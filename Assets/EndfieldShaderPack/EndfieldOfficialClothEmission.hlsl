#ifndef ENDFIELD_OFFICIAL_CLOTH_EMISSION_INCLUDED
#define ENDFIELD_OFFICIAL_CLOTH_EMISSION_INCLUDED

// Actual PS37669: _491 / _2265 / _2452. The caller supplies BaseMap.a *
// BaseColor.a, NOT opaque output alpha, clip alpha, or emission texture alpha.
float EFClothCapturedAlphaFactor(float sourceBaseAlpha, float premultiply)
{
    return (1.0 - premultiply) + sourceBaseAlpha * premultiply;
}

float3 EFClothCapturedEmission(float3 sampleRGB, float3 emissionColor,
    float brightness, float alphaFactor)
{
    return ((sampleRGB * emissionColor) * brightness) * alphaFactor;
}

#endif
