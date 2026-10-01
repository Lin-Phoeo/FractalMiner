Shader "Hidden/Endfield/NativeClothProbe"
{
    Properties { _BumpMap ("Native normal sampler", 2D) = "bump" {} }
    SubShader
    {
        Pass
        {
            ZTest Always ZWrite Off Cull Off
            HLSLPROGRAM
            #pragma target 4.5
            #pragma vertex vert_img
            #pragma fragment Probe
            #include "UnityCG.cginc"
            Texture2D<float4> _BumpMap;
            SamplerState sampler_BumpMap;
            float4 _ProbeUVLOD;
            float4 Probe(v2f_img input) : SV_Target
            {
                if (_ProbeUVLOD.w > 0.5)
                {
                    uint width, height, levels;
                    _BumpMap.GetDimensions((uint)_ProbeUVLOD.z, width, height, levels);
                    return _BumpMap.Load(int3(int2(_ProbeUVLOD.xy * float2(width,height)), (int)_ProbeUVLOD.z));
                }
                return _BumpMap.SampleLevel(sampler_BumpMap, _ProbeUVLOD.xy, _ProbeUVLOD.z);
            }
            ENDHLSL
        }
    }
}
