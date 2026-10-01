Shader "Hidden/Endfield/WetnessProbe"
{
    SubShader
    {
        Pass
        {
            ZTest Always ZWrite Off Cull Off
            HLSLPROGRAM
            #pragma vertex vert_img
            #pragma fragment frag
            #pragma target 4.5
            #include "UnityCG.cginc"
            float4 _CharacterParams10, _EndfieldObjectWeather, _EndfieldWeatherTime;
            float _EndfieldCapturedGlobalMipBias, _DisableRainEffectOnMaterial;
            Texture2D<float4> _CharacterRainEffectTex, _CharacterRainStreakTex;
            SamplerState sampler_Endfield_LinearRepeat;
            #define sampler_BumpMap sampler_Endfield_LinearRepeat
            float _ProbeMode, _ProbeY;
            float4 _ProbeLoad; // mip,x,y,texture selector
            #include "../EndfieldOfficialWetness.hlsl"
            float4 frag(v2f_img input) : SV_Target
            {
                if (_ProbeMode > 3.5)
                    return _ProbeLoad.w < .5 ? _CharacterRainEffectTex.Load(int3(_ProbeLoad.yz, _ProbeLoad.x))
                        : _CharacterRainStreakTex.Load(int3(_ProbeLoad.yz, _ProbeLoad.x));
                if (_ProbeMode < .5) return EFWetDecode(_CharacterParams10.x, _CharacterParams10.y, _EndfieldObjectWeather.x);
                if (_ProbeMode < 1.5) return EFWetInputs(_ProbeY);
                EFWetSurface wet = EFWetEvaluate471(float3(.4,.3,.2), float3(.2,.15,.1),
                    float3(0,0,1), .2, .6, float3(.031,.071,.113), float3(0,0,1), true, _ProbeY);
                if (_ProbeMode < 2.5) return float4(wet.roughness, wet.coverage, wet.albedo.r, wet.shadowAlbedo.r);
                return float4(wet.specNormal, 1);
            }
            ENDHLSL
        }
    }
}
