#ifndef ENDFIELD_OFFICIAL_CLOTH_NORMALS_INCLUDED
#define ENDFIELD_OFFICIAL_CLOTH_NORMALS_INCLUDED

// Actual frame6411: PS22255 _502.._554 / PS37669 _504.._568.
// Inputs are raw raster-interpolated world N/T, not a per-part root matrix.
struct EFClothNormals
{
    float3 mapped;
    float3 geometry;
};

float3 EFClothNormalTS(float4 packed, float scale)
{
    float2 xy = float2(packed.r * packed.a, packed.g) * 2.0 - 1.0;
    float z = max(1e-16, sqrt(1.0 - clamp(dot(xy, xy), 0.0, 1.0)));
    return float3(xy * scale, z);
}

EFClothNormals EFClothDecodeNormals(float4 packed, float scale,
    float3 geometryN, float4 tangent, float backfaceFactor)
{
    float3x3 basis = float3x3(tangent.xyz, cross(geometryN, tangent.xyz) * tangent.w, geometryN);
    float3 world = mul(EFClothNormalTS(packed, scale), basis);
    EFClothNormals result;
    result.mapped = world * rsqrt(max(dot(world, world), 1.175494351e-38)) * backfaceFactor;
    // Source plain normalize; zero geometry N is outside the captured domain.
    result.geometry = normalize(geometryN) * backfaceFactor;
    return result;
}

#endif
