#ifndef ENDFIELD_OFFICIAL_HAIR_NORMALS_INCLUDED
#define ENDFIELD_OFFICIAL_HAIR_NORMALS_INCLUDED

// Actual frame 6411 / event 875 / PS22257, _499.._576 (b126, not b125).
// Raw raster-interpolated geometry N/T are intentionally NOT renormalized here.
struct EFHairNormals
{
    float3 diffuse;
    float3 specular;
};

float3 EFHairNormalTS(float2 encoded, float scale)
{
    float2 xy = encoded * 2.0 - 1.0;
    float z = max(1e-16, sqrt(1.0 - clamp(dot(xy, xy), 0.0, 1.0)));
    return float3(xy * scale, z);
}

EFHairNormals EFHairDecodeSplitNormals(float4 packed, float diffuseScale,
    float specularScale, float3 geometryN, float4 tangent, float backfaceFactor)
{
    float3x3 basis = float3x3(tangent.xyz, cross(geometryN, tangent.xyz) * tangent.w, geometryN);
    float3 diffuseWS = mul(EFHairNormalTS(packed.rg, diffuseScale), basis);
    float3 specularWS = mul(EFHairNormalTS(packed.ba, specularScale), basis);
    EFHairNormals result;
    result.diffuse = diffuseWS * rsqrt(max(dot(diffuseWS, diffuseWS), 1.175494351e-38)) * backfaceFactor;
    // Source uses ordinary normalize and no backface factor for the specular N.
    // A zero basis is outside the captured nondegenerate domain, not sanitized.
    result.specular = normalize(specularWS);
    return result;
}

#endif
