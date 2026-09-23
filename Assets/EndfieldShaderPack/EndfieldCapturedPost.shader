Shader "Hidden/Endfield/CapturedPost"
{
    Properties
    {
        _MainTex ("Reference HDR input (linear)", 2D) = "black" {}
        _EndfieldPostLut ("Captured linear LogC LUT", 2D) = "black" {}
        _EndfieldPostBloom ("Linear bloom, black if unavailable", 2D) = "black" {}
        _EndfieldPostOutputMode ("0 raw encoded reference, 1 Unity linear", Float) = 1
    }
    SubShader
    {
        Tags { "RenderPipeline"="UniversalPipeline" }
        Cull Off ZWrite Off ZTest Always

        HLSLINCLUDE
        #include "Packages/com.unity.render-pipelines.universal/ShaderLibrary/Core.hlsl"
        #include "Packages/com.unity.render-pipelines.core/Runtime/Utilities/Blit.hlsl"

        TEXTURE2D(_MainTex);
        TEXTURE2D(_EndfieldPostLut);
        TEXTURE2D(_EndfieldPostBloom);

        float4 _EndfieldPostScreenSize;
        float4 _EndfieldPostExposure;
        float4 _EndfieldPostLutParameters;
        float4 _EndfieldPostBloomParameters;
        float4 _EndfieldPostBloomThreshold;
        float4 _EndfieldPostBloomTint;
        float4 _EndfieldPostVignette1;
        float4 _EndfieldPostVignette2;
        float4 _EndfieldPostVignetteColor;
        float4 _EndfieldPostOptions;
        float4 _EndfieldPostSourceUV;
        float4 _EndfieldPostBloomUV;
        float4 _EndfieldPostLutUV;
        float4 _EndfieldPostScreenUV;
        float _EndfieldPostOutputMode;

        float2 EFPostTransformUV(float2 uv, float4 transform)
        {
            return uv * transform.xy + transform.zw;
        }

        float4 EFPostReadInput(float2 uv, bool reference)
        {
            uv = EFPostTransformUV(uv, _EndfieldPostSourceUV);
            if (reference) return SAMPLE_TEXTURE2D_LOD(_MainTex, sampler_LinearClamp, uv, 0);
            return SAMPLE_TEXTURE2D_X_LOD(_BlitTexture, sampler_LinearClamp, uv, 0);
        }

        float EFPostSharpenLuma(float3 color)
        {
            return color.r * 0.5 + color.g + color.b * 0.5;
        }

        float EFPostSharpenChannelLimit(float low, float high)
        {
            // b354 has literal divisions. Define their continuous flat-black/
            // flat-white limit explicitly so uniform test inputs cannot create NaN.
            float hitMin = abs(high) > 1e-8 ? -low / (4.0 * high) : 0.0;
            float denominator = 4.0 * low - 4.0;
            float hitMax = abs(denominator) > 1e-8 ? (1.0 - high) / denominator : 0.0;
            return max(hitMin, hitMax);
        }

        float3 EFPostSharpen(float2 uv, float3 center, bool reference)
        {
            if (_EndfieldPostOptions.x == 0.0) return center;
            float2 dx = float2(_EndfieldPostScreenSize.z, 0);
            float2 dy = float2(0, _EndfieldPostScreenSize.w);
            float3 north = EFPostReadInput(uv + dy, reference).rgb;
            float3 west = EFPostReadInput(uv - dx, reference).rgb;
            float3 east = EFPostReadInput(uv + dx, reference).rgb;
            float3 south = EFPostReadInput(uv - dy, reference).rgb;
            float ln = EFPostSharpenLuma(north), lw = EFPostSharpenLuma(west);
            float le = EFPostSharpenLuma(east), ls = EFPostSharpenLuma(south);
            float lc = EFPostSharpenLuma(center);
            float lmin = min(min(ln, min(lw, lc)), min(le, ls));
            float lmax = max(max(ln, max(lw, lc)), max(le, ls));
            float contrast = lmax - lmin;
            float noise = contrast > 1e-8 ? saturate(abs(0.25 * (ln + lw + le + ls) - lc) / contrast) : 0.0;
            float3 low = min(min(north, min(west, east)), south);
            float3 high = max(max(north, max(west, east)), south);
            float3 limits = float3(EFPostSharpenChannelLimit(low.r, high.r),
                EFPostSharpenChannelLimit(low.g, high.g), EFPostSharpenChannelLimit(low.b, high.b));
            float lobe = max(-0.1875, min(max(limits.r, max(limits.g, limits.b)), 0.0));
            lobe *= _EndfieldPostOptions.x * (1.0 - 0.5 * noise);
            return (center + lobe * (north + west + south + east)) / (1.0 + 4.0 * lobe);
        }

        float3 EFPostBloom(float3 color, float2 uv)
        {
            float3 bloom = SAMPLE_TEXTURE2D_LOD(_EndfieldPostBloom, sampler_LinearClamp,
                EFPostTransformUV(uv, _EndfieldPostBloomUV), 0).rgb;
            float3 compressed = pow(max(bloom, 0.0), 0.33000001311302185) * 1.4938000440597534 - 0.699999988079071;
            float3 thresholdInput = bloom * (1.0 - _EndfieldPostBloomParameters.z);
            bloom = float3(thresholdInput.r > 0.30000001192092896 ? compressed.r : bloom.r,
                thresholdInput.g > 0.30000001192092896 ? compressed.g : bloom.g,
                thresholdInput.b > 0.30000001192092896 ? compressed.b : bloom.b);
            float brightness = max(color.r, max(color.g, color.b));
            float knee = clamp(brightness - _EndfieldPostBloomThreshold.y, 0.0, _EndfieldPostBloomThreshold.z);
            float contribution = max(_EndfieldPostBloomThreshold.w * knee * knee,
                brightness - _EndfieldPostBloomThreshold.x) / max(brightness, 0.000099999997473787516);
            float3 combined = color - color * contribution * _EndfieldPostBloomParameters.z
                + bloom * _EndfieldPostBloomTint.rgb;
            return lerp(color, combined, _EndfieldPostBloomParameters.x);
        }

        float3 EFPostVignette(float3 color, float2 uv)
        {
            if (_EndfieldPostOptions.y < 0.5) return color;
            float4 p1 = _EndfieldPostVignette1;
            float4 p2 = _EndfieldPostVignette2;
            float2 delta = abs(uv - p1.xy) * lerp(p2.x, 1.0, p1.w);
            float x = delta.x * lerp(1.0, 1.5 * saturate(p2.x * 1.0499999523162842), p1.w);
            float y = saturate(delta.y * lerp(1.0, p2.x * 2.0, p1.w)
                + saturate(p2.x - 2.7999999523162842) * 5.0);
            x *= lerp(lerp(1.0, _EndfieldPostExposure.z, p2.w), _EndfieldPostExposure.z * 0.5625, p1.w);
            float2 shaped = pow(saturate(float2(x, y)), p2.z);
            float weight = pow(saturate(1.0 - dot(shaped, shaped)), p2.y);
            return color * lerp(_EndfieldPostVignetteColor.rgb, 1.0, weight);
        }

        float3 EFPostEncodeLogC(float3 color)
        {
            // This exact logarithmic branch, not a generic ACES or piecewise LogC.
            float3 value = max(color * 5.555555820465088 + 0.047995999455451965, 0.0);
            return saturate(log2(value) * 0.3010300099849701 * 0.24416099488735199 + 0.3860360085964203);
        }

        float3 EFPostApplyLut(float3 logColor)
        {
            float4 p = _EndfieldPostLutParameters;
            float slice = logColor.b * p.z;
            float sliceFloor = floor(slice);
            float2 uv = logColor.rg * p.z * p.xy + p.xy * 0.5;
            uv.x += sliceFloor * p.y;
            float3 lower = SAMPLE_TEXTURE2D_LOD(_EndfieldPostLut, sampler_LinearClamp,
                EFPostTransformUV(uv, _EndfieldPostLutUV), 0).rgb;
            float3 upper = SAMPLE_TEXTURE2D_LOD(_EndfieldPostLut, sampler_LinearClamp,
                EFPostTransformUV(uv + float2(p.y, 0), _EndfieldPostLutUV), 0).rgb;
            return lerp(lower, upper, slice - sliceFloor);
        }

        float3 EFPostEncodeSRGB(float3 value)
        {
            float3 low = value * 12.920000076293945;
            float3 high = pow(abs(value), 0.4166666567325592) * 1.0549999475479126 - 0.054999999701976776;
            return float3(value.r <= 0.0031308000907301903 ? low.r : high.r,
                value.g <= 0.0031308000907301903 ? low.g : high.g,
                value.b <= 0.0031308000907301903 ? low.b : high.b);
        }

        float3 EFPostDecodeSRGB(float3 value)
        {
            float3 low = value / 12.92;
            float3 high = pow(max((value + 0.055) / 1.055, 0.0), 2.4);
            return float3(value.r <= 0.04045 ? low.r : high.r,
                value.g <= 0.04045 ? low.g : high.g, value.b <= 0.04045 ? low.b : high.b);
        }

        float4 EFPostProcess(float2 uv, bool reference)
        {
            float4 input = EFPostReadInput(uv, reference);
            float3 color = EFPostSharpen(uv, input.rgb, reference) * _EndfieldPostExposure.x;
            color = EFPostBloom(color, uv);
            float2 screenUV = EFPostTransformUV(uv, _EndfieldPostScreenUV);
            color = EFPostVignette(color, screenUV);
            color = EFPostEncodeLogC(color * _EndfieldPostLutParameters.w);
            color = EFPostEncodeSRGB(EFPostApplyLut(color));
            if (_EndfieldPostOptions.z > 0.5)
            {
                float noiseSeed = dot(float2(171.0, 231.0), screenUV * _EndfieldPostScreenSize.xy);
                float3 noise = frac(noiseSeed * float3(0.009708737954497337,
                    0.014084506779909134, 0.010309278033673763)) - 0.5;
                color += noise * 0.0039215688593685627 * 0.3499999940395355;
            }
            // Original target is RGBA8_UNORM, not SRGB. Unity live output is
            // linear again to prevent a second sRGB encoding at final presentation.
            if (_EndfieldPostOutputMode > 0.5) color = EFPostDecodeSRGB(saturate(color));
            return float4(color, min(input.a, 1.0));
        }

        float4 FragLive(Varyings input) : SV_Target
        {
            UNITY_SETUP_STEREO_EYE_INDEX_POST_VERTEX(input);
            return EFPostProcess(input.texcoord, false);
        }

        struct ReferenceAttributes
        {
            float4 positionOS : POSITION;
            float2 uv : TEXCOORD0;
        };
        struct ReferenceVaryings
        {
            float4 positionCS : SV_POSITION;
            float2 uv : TEXCOORD0;
        };
        ReferenceVaryings VertReference(ReferenceAttributes input)
        {
            ReferenceVaryings output;
            output.positionCS = TransformObjectToHClip(input.positionOS.xyz);
            output.uv = input.uv;
            return output;
        }
        float4 FragReference(ReferenceVaryings input) : SV_Target
        {
            return EFPostProcess(input.uv, true);
        }
        ENDHLSL

        Pass
        {
            Name "LiveBlitterLinear"
            HLSLPROGRAM
            #pragma target 4.5
            #pragma vertex Vert
            #pragma fragment FragLive
            ENDHLSL
        }
        Pass
        {
            Name "ReferenceGraphicsBlit"
            HLSLPROGRAM
            #pragma target 4.5
            #pragma vertex VertReference
            #pragma fragment FragReference
            ENDHLSL
        }
    }
    Fallback Off
}
