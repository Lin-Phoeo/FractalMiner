Shader "Hidden/Endfield/ClothNormalProbe"
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
            #include "../EndfieldOfficialClothNormals.hlsl"
            float4 _ProbePacked, _ProbeGeometry, _ProbeTangent, _ProbeParams;
            float4 Probe(v2f_img input) : SV_Target
            {
                if (_ProbeParams.z > 1.5)
                    return float4(EFClothNormalTS(_ProbePacked, _ProbeParams.x), 1);
                EFClothNormals n = EFClothDecodeNormals(_ProbePacked, _ProbeParams.x,
                    _ProbeGeometry.xyz, _ProbeTangent, _ProbeParams.y);
                return float4(_ProbeParams.z < 0.5 ? n.mapped : n.geometry, 1);
            }
            ENDHLSL
        }
    }
}
