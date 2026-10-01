Shader "Hidden/Endfield/ClothEnvironmentProbe"
{
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
            TextureCube<float4> _CharMaxCubemap;
            SamplerState sampler_CharMaxCubemap;
            SamplerState sampler_Endfield_LinearClamp;
            SamplerState sampler_Endfield_PointClamp;
            float4 _ProbeDirectionLOD;
            float _ProbeMode;
            float4 Probe(v2f_img input) : SV_Target
            {
                if (_ProbeMode < 0.5)
                    return _CharMaxCubemap.SampleLevel(sampler_CharMaxCubemap,
                        _ProbeDirectionLOD.xyz, _ProbeDirectionLOD.w);
                if (_ProbeMode > 1.5)
                    return _CharMaxCubemap.SampleLevel(sampler_Endfield_PointClamp,
                        _ProbeDirectionLOD.xyz, _ProbeDirectionLOD.w);
                return _CharMaxCubemap.SampleLevel(sampler_Endfield_LinearClamp,
                    _ProbeDirectionLOD.xyz, _ProbeDirectionLOD.w);
            }
            ENDHLSL
        }
    }
}
