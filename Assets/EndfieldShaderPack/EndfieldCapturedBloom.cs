using System;
using UnityEngine;
using UnityEngine.Experimental.Rendering;
using UnityEngine.Rendering;
using UnityEngine.Rendering.Universal;

namespace EndfieldShaderPack
{
    public enum EndfieldBloomRounding
    {
        RoundToNearestEven = 1,
        RoundTowardZero = 2
    }

    /// <summary>
    /// Records the frame-6411 dynamic HDR bloom chain (20453/20455/20463).
    /// No captured screen image is used. Exact capture dimensions are 2560x1600;
    /// other dimensions retain nine levels and scale the same filter semantics.
    /// Own one instance per renderer pass and call Setup before Render.
    /// </summary>
    public sealed class EndfieldCapturedBloom : IDisposable
    {
        public const int LevelCount = 9;
        public static readonly Vector4 CapturedThreshold = new Vector4(
            .5225216150283813f, .2612507939338684f, .5225416421890259f, .9568615555763245f);
        public const float CapturedScatter = .7699999809265137f;
        // Frame-6411 RNE trial was above the captured output at every changed pixel,
        // with the bias accumulating at every store. Keep RNE available as a probe;
        // RTZ is the source hypothesis tested by the per-event GPU comparison.
        public EndfieldBloomRounding RoundingMode { get; set; } = EndfieldBloomRounding.RoundTowardZero;
        const GraphicsFormat NativeFormat = GraphicsFormat.B10G11R11_UFloatPack32;
        const GraphicsFormat FallbackFormat = GraphicsFormat.R32G32B32A32_SFloat;
        readonly ComputeShader shader;
        readonly int prefilter, downsample, upsample;
        readonly RTHandle[] down = new RTHandle[LevelCount];
        readonly RTHandle[] up = new RTHandle[LevelCount - 1];
        int width, height;
        bool ready, disposed;

        static readonly int Input = Shader.PropertyToID("_Input");
        static readonly int HighInput = Shader.PropertyToID("_HighInput");
        static readonly int Output = Shader.PropertyToID("_Output");
        static readonly int InputSize = Shader.PropertyToID("_InputSize");
        static readonly int OutputSize = Shader.PropertyToID("_OutputSize");
        static readonly int Threshold = Shader.PropertyToID("_Threshold");
        static readonly int Exposure = Shader.PropertyToID("_Exposure");
        static readonly int Scatter = Shader.PropertyToID("_Scatter");
        static readonly int QuantizeOutput = Shader.PropertyToID("_QuantizeOutput");

        static bool SupportsStorage(GraphicsFormat format) =>
            SystemInfo.IsFormatSupported(format, FormatUsage.LoadStore) &&
            SystemInfo.IsFormatSupported(format, FormatUsage.Sample) &&
            SystemInfo.IsFormatSupported(format, FormatUsage.Linear);

        public bool IsNativeStorage => SupportsStorage(NativeFormat);
        public GraphicsFormat StorageFormat => IsNativeStorage ? NativeFormat : FallbackFormat;
        public bool IsSupported => !disposed && shader != null && SystemInfo.supportsComputeShaders &&
            SupportsStorage(StorageFormat);

        public string StorageSupportDescription =>
            $"compute={SystemInfo.supportsComputeShaders}; " +
            $"native LoadStore={SystemInfo.IsFormatSupported(NativeFormat, FormatUsage.LoadStore)}, " +
            $"Sample={SystemInfo.IsFormatSupported(NativeFormat, FormatUsage.Sample)}, " +
            $"Linear={SystemInfo.IsFormatSupported(NativeFormat, FormatUsage.Linear)}; " +
            $"selected={StorageFormat}; selectedSupported={SupportsStorage(StorageFormat)}; rounding={RoundingMode}";

        public EndfieldCapturedBloom(ComputeShader computeShader)
        {
            shader = computeShader;
            if (shader != null)
            {
                prefilter = shader.FindKernel("Prefilter");
                downsample = shader.FindKernel("Downsample");
                upsample = shader.FindKernel("Upsample");
            }
        }

        // Independent round-to-nearest on original dimensions produces 25,13,6,3,
        // unlike recursively halving or using banker's rounding. Captured CB evidence.
        public static Vector2Int GetLevelSize(int sourceWidth, int sourceHeight, int level)
        {
            if (sourceWidth < 1 || sourceHeight < 1) throw new ArgumentOutOfRangeException(nameof(sourceWidth));
            if (level < 0 || level >= LevelCount) throw new ArgumentOutOfRangeException(nameof(level));
            int divisor = 1 << (level + 1);
            return new Vector2Int(Math.Max(1, (sourceWidth + divisor / 2) / divisor),
                Math.Max(1, (sourceHeight + divisor / 2) / divisor));
        }

        public bool Setup(RenderTextureDescriptor descriptor)
        {
            ready = false;
            if (!IsSupported || descriptor.width < 1 || descriptor.height < 1 ||
                descriptor.dimension != TextureDimension.Tex2D || descriptor.volumeDepth != 1 ||
                descriptor.useDynamicScale || descriptor.msaaSamples > 1)
                return false;
            width = descriptor.width;
            height = descriptor.height;
            // Fall back if any native storage, sampling or linear-filter capability
            // is missing. On the tested D3D11 device LoadStore=true, but Sample and
            // Linear=false; do not misdiagnose that as an unsupported typed store.
            // every compute store explicitly rounds RGB to the captured format,
            // while RGBAFloat holds those representable numbers without further loss.
            // GPU comparison is still required; this is not an untested bit-exact claim.
            descriptor.graphicsFormat = StorageFormat;
            descriptor.depthBufferBits = 0;
            descriptor.msaaSamples = 1;
            descriptor.bindMS = false;
            descriptor.enableRandomWrite = true;
            descriptor.useMipMap = false;
            descriptor.autoGenerateMips = false;
            descriptor.mipCount = 1;
            descriptor.sRGB = false;
            descriptor.memoryless = RenderTextureMemoryless.None;
            try
            {
                for (int i = 0; i < LevelCount; ++i)
                {
                    Vector2Int size = GetLevelSize(width, height, i);
                    descriptor.width = size.x;
                    descriptor.height = size.y;
                    RenderingUtils.ReAllocateIfNeeded(ref down[i], descriptor,
                        FilterMode.Bilinear, TextureWrapMode.Clamp, name: "_EndfieldBloomDown" + i);
                    if (i < up.Length)
                        RenderingUtils.ReAllocateIfNeeded(ref up[i], descriptor,
                            FilterMode.Bilinear, TextureWrapMode.Clamp, name: "_EndfieldBloomUp" + i);
                }
                ready = true;
                return true;
            }
            catch
            {
                ReleaseTextures();
                throw;
            }
        }

        public RTHandle Render(CommandBuffer cmd, RTHandle source, float exposure = 1f)
        {
            if (!ready || !IsSupported) return null;
            if (cmd == null) throw new ArgumentNullException(nameof(cmd));
            if (source == null) throw new ArgumentNullException(nameof(source));
            if (float.IsNaN(exposure) || float.IsInfinity(exposure) || exposure < 0)
                throw new ArgumentOutOfRangeException(nameof(exposure));
            if (RoundingMode != EndfieldBloomRounding.RoundToNearestEven &&
                RoundingMode != EndfieldBloomRounding.RoundTowardZero)
                throw new ArgumentOutOfRangeException(nameof(RoundingMode));
            cmd.SetComputeVectorParam(shader, Threshold, CapturedThreshold);
            cmd.SetComputeFloatParam(shader, Exposure, exposure);
            cmd.SetComputeFloatParam(shader, Scatter, CapturedScatter);
            // Explicit conversion even on native storage avoids dependence on the
            // target backend's unspecified rounding. Already representable values
            // are unchanged by the subsequent native-format store.
            cmd.SetComputeIntParam(shader, QuantizeOutput, (int)RoundingMode);
            Dispatch(cmd, prefilter, source, down[0], Size(width, height));
            for (int i = 1; i < LevelCount; ++i)
                Dispatch(cmd, downsample, down[i - 1], down[i], Size(down[i - 1]));
            RTHandle low = down[LevelCount - 1];
            for (int i = LevelCount - 2; i >= 0; --i)
            {
                cmd.SetComputeTextureParam(shader, upsample, HighInput, down[i]);
                Dispatch(cmd, upsample, low, up[i], Size(low));
                low = up[i];
            }
            return up[0];
        }

        void Dispatch(CommandBuffer cmd, int kernel, RTHandle source, RTHandle target, Vector4 inputSize)
        {
            cmd.SetComputeTextureParam(shader, kernel, Input, source);
            cmd.SetComputeTextureParam(shader, kernel, Output, target);
            cmd.SetComputeVectorParam(shader, InputSize, inputSize);
            cmd.SetComputeVectorParam(shader, OutputSize, Size(target));
            cmd.DispatchCompute(shader, kernel, (target.rt.width + 7) / 8, (target.rt.height + 7) / 8, 1);
        }

        static Vector4 Size(int w, int h) => new Vector4(w, h, 1f / w, 1f / h);
        static Vector4 Size(RTHandle handle) => Size(handle.rt.width, handle.rt.height);

        // Diagnostics: after executing the recorded command, compare every level
        // against exported HDR capture resources, not just the final tone-mapped PNG.
        public RTHandle GetDownsample(int level) => down[level];
        public RTHandle GetUpsample(int level) => up[level];

        void ReleaseTextures()
        {
            for (int i = 0; i < down.Length; ++i) { down[i]?.Release(); down[i] = null; }
            for (int i = 0; i < up.Length; ++i) { up[i]?.Release(); up[i] = null; }
            ready = false;
        }

        public void Dispose()
        {
            ReleaseTextures();
            disposed = true;
        }
    }
}
