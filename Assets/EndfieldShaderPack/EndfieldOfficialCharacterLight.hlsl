#ifndef ENDFIELD_OFFICIAL_CHARACTER_LIGHT_INCLUDED
#define ENDFIELD_OFFICIAL_CHARACTER_LIGHT_INCLUDED

// Reviewed actual PS 22259/22250/22255/37669/37671/22257: set0/b14
// c0 = world-space light TRAVEL, c3.rgb = unscaled linear RGB, c3.w =
// intensity. set0/b16 CP1.w, CP12.y/w select three independent lerps.
// No normalization, clamp, legacy separated-light/URP color substitution,
// double intensity multiplication, or division to recover unscaled RGB.
struct EFOfficialCharacterLight
{
    float3 direction;
    float3 color;
    float3 colorIntensity;
};

EFOfficialCharacterLight EFResolveOfficialCharacterLight(bool skin)
{
    EFOfficialCharacterLight result;
    result.direction = lerp(-_EndfieldCapturedDirectionalTravel.xyz,
        _CharacterParams11.xyz, _CharacterParams1.w);
    result.color = lerp(_EndfieldCapturedDirectionalColor.rgb,
        skin ? _CharacterParams4.rgb : _CharacterParams5.rgb, _CharacterParams12.y);
    result.colorIntensity = result.color
        * lerp(_EndfieldCapturedLightIntensity, 1.0, _CharacterParams12.w);
    return result;
}

#endif
