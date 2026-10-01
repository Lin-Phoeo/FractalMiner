#ifndef ENDFIELD_OFFICIAL_CHARACTER_SHADOW_INCLUDED
#define ENDFIELD_OFFICIAL_CHARACTER_SHADOW_INCLUDED

// Actual six PS: screen mask set0/t22 .r, ShadowData set0/b15 offset544.x,
// CP1.z. Integer SV_POSITION -> mip0 Load, then strength, THEN ignore.
// The current live G producer writes R=1; it is NOT a directional producer.
// Independent R texture/gate prevents that producer overwriting an actual R
// input. With no official R input, the legacy URP fallback remains explicit.
float EndfieldOfficialDirectionalShadow(float2 pixelPosition, float legacyShadow)
{
    float rawR = legacyShadow;
    if (_EndfieldDirectionalScreenShadow > 0.5)
        rawR = LOAD_TEXTURE2D(_EndfieldDirectionalShadowScreen, int2(pixelPosition)).r;
    return lerp(lerp(1.0, rawR, _EndfieldCapturedDirectionalShadowParams.x),
        1.0, _CharacterParams1.z);
}

#endif
