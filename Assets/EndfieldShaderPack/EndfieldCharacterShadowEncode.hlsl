#ifndef ENDFIELD_CHARACTER_SHADOW_ENCODE_INCLUDED
#define ENDFIELD_CHARACTER_SHADOW_ENCODE_INCLUDED

// Inverse of the resolve's DecodeNormalOctahedralY. The official GBuffer1 stores the
// world normal octahedrally with Y as the polar axis (the reconstructed component lands
// in the middle slot and the fold tests it), in 10-bit UNORM per channel. The runtime
// prepass writes exactly that, into an R10G10B10A2 target so the hardware performs the
// same quantisation the captured evidence carries.
//
// The pair is checked numerically by
// EndfieldCharacterShadowProjectionValidation (encode/decode round-trip over a
// Fibonacci sphere, 10-bit quantised) and on the GPU by the debug-sphere gate in
// EndfieldCharacterShadowLiveValidation.
float2 EndfieldOctahedralEncodeY(float3 direction)
{
    float l1 = abs(direction.x) + abs(direction.y) + abs(direction.z);
    float3 d = direction / max(l1, 1e-12);
    if (d.y >= 0.0)
    {
        return d.xz;
    }
    float2 signXZ = float2(d.x >= 0.0 ? 1.0 : -1.0, d.z >= 0.0 ? 1.0 : -1.0);
    return float2((1.0 - abs(d.z)) * signXZ.x, (1.0 - abs(d.x)) * signXZ.y);
}

// The official resolve reads GBuffer0 as one uint and takes log2(pack) - 8 as the slot,
// so a slot has to be written as a value whose exponent is 8 + slot. (1 << (8 + slot))
// alone lands exactly on an integer and float error could push it below, which the
// resolve's indexF >= 0 test would reject; the measured frame-6411 value is 258 for
// slot 0, i.e. the power of two plus a 2 in the low bits, giving 0.011 of margin below
// and 0.989 above. That encoding is reproduced here rather than invented.
float4 EndfieldCharacterIndexEncode(int slot)
{
    uint raw = (1u << (8 + slot)) + 2u;
    return float4((float)(raw & 1023u) / 1023.0,
                  (float)((raw >> 10) & 1023u) / 1023.0,
                  (float)((raw >> 20) & 1023u) / 1023.0,
                  (float)((raw >> 30) & 3u) / 3.0);
}

#endif
