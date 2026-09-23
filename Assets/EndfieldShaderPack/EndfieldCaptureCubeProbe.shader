Shader "Hidden/Endfield/CaptureCubeProbe"
{
    Properties { _Cube("Cube",Cube)="black"{} _Reference2D("Reference",2D)="black"{} _Face("Face",Float)=0 }
    SubShader
    {
        Cull Off ZWrite Off ZTest Always
        Pass
        {
            HLSLPROGRAM
            #pragma vertex vert_img
            #pragma fragment frag
            #pragma target 3.0
            #include "UnityCG.cginc"
            samplerCUBE _Cube;
            sampler2D _Reference2D;
            float _Face;
            float _Mode;
            float _ReferenceFlip;
            float4 frag(v2f_img i):SV_Target
            {
                if(_Mode>.5)return tex2Dlod(_Reference2D,float4(i.uv.x,lerp(i.uv.y,1-i.uv.y,_ReferenceFlip),0,0));
                float2 p=i.uv*2-1;
                float3 d;
                if(_Face<.5)d=float3(1,-p.y,-p.x);
                else if(_Face<1.5)d=float3(-1,-p.y,p.x);
                else if(_Face<2.5)d=float3(p.x,1,p.y);
                else if(_Face<3.5)d=float3(p.x,-1,-p.y);
                else if(_Face<4.5)d=float3(p.x,-p.y,1);
                else d=float3(-p.x,-p.y,-1);
                return texCUBElod(_Cube,float4(d,0));
            }
            ENDHLSL
        }
    }
}
