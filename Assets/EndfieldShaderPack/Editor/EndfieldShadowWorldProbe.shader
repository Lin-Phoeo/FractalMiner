Shader "Hidden/Endfield/ShadowWorldProbe"
{
    SubShader
    {
        Tags { "RenderPipeline"="UniversalPipeline" }
        Pass
        {
            Cull Off ZWrite On ZTest LEqual
            HLSLPROGRAM
            #pragma vertex Vert
            #pragma fragment Frag
            #include "Packages/com.unity.render-pipelines.universal/ShaderLibrary/Core.hlsl"
            struct Input {float4 positionOS:POSITION;};
            struct Output {float4 positionCS:SV_POSITION;float3 positionWS:TEXCOORD0;};
            Output Vert(Input input)
            {Output o;o.positionWS=TransformObjectToWorld(input.positionOS.xyz);o.positionCS=TransformWorldToHClip(o.positionWS);return o;}
            float4 Frag(Output input):SV_Target {return float4(input.positionWS,1);}
            ENDHLSL
        }
    }
}
