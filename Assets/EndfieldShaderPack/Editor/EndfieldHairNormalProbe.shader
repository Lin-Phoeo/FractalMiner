Shader "Hidden/Endfield/HairNormalProbe"
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
            #include "../EndfieldOfficialHairNormals.hlsl"
            float4 _ProbePacked, _ProbeGeometry, _ProbeTangent, _ProbeScales;
            float4 Probe(v2f_img input) : SV_Target
            {
                EFHairNormals n = EFHairDecodeSplitNormals(_ProbePacked,
                    _ProbeScales.x, _ProbeScales.y, _ProbeGeometry.xyz,
                    _ProbeTangent, _ProbeScales.z);
                return float4(_ProbeScales.w < 0.5 ? n.diffuse : n.specular, 1);
            }
            ENDHLSL
        }
    }
}
