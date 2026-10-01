Shader "Hidden/Endfield/ClothEmissionProbe"
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
            #include "../EndfieldOfficialClothEmission.hlsl"
            float4 _ProbeSample, _ProbeColor, _ProbeParams;
            float4 Probe(v2f_img input) : SV_Target
            {
                float factor = EFClothCapturedAlphaFactor(_ProbeParams.x, _ProbeParams.y);
                return float4(EFClothCapturedEmission(_ProbeSample.rgb, _ProbeColor.rgb,
                    _ProbeParams.z, factor), factor);
            }
            ENDHLSL
        }
    }
}
