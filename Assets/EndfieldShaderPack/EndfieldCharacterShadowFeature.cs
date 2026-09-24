using System.Collections.Generic;
using UnityEngine;
using UnityEngine.Rendering;
using UnityEngine.Rendering.Universal;

namespace EndfieldShaderPack
{
    /// Runs HGRP's character self-shadow chain inside URP's forward renderer:
    /// shadow atlas -> character index/normal prepass -> ScreenSpaceShadowResolve
    /// -> the G channel EndfieldCharacterLit reads as selfShadow.
    ///
    /// The official is deferred: it resolves from GBuffer0/GBuffer1 written by the
    /// character prepass. This project's pipeline asset is a forward renderer
    /// (m_RenderingMode 0), so those buffers do not exist and are rebuilt here as a
    /// character-only prepass with the official's own formats (R10G10B10A2 index and
    /// normal, R16 atlas, R8G8-equivalent resolved output). The resolve stays the
    /// validated compute kernel: its arithmetic is per pixel over integer coordinates
    /// with no derivatives or interpolation, so a dispatch evaluates the same
    /// expression per pixel as the official fullscreen pass, and it is the exact code
    /// the fixed-capture gate measured at 99.84% byte-exact.
    public sealed class EndfieldCharacterShadowFeature : ScriptableRendererFeature
    {
        [SerializeField] ComputeShader resolveShader;
        [SerializeField] int atlasResolution = 1024;

        CharacterShadowPass pass;

        // Diagnostics: which guard last kept the chain out of the frame. Empty means the
        // pass was enqueued. Without this a silent skip is indistinguishable from a
        // chain that ran and produced nothing.
        public static string LastSkipReason = "AddRenderPasses never ran";

        public override void Create()
        {
            pass?.Dispose();
            pass = new CharacterShadowPass(resolveShader, Mathf.Max(64, atlasResolution))
            {
                renderPassEvent = RenderPassEvent.BeforeRenderingOpaques
            };
        }

        public override void AddRenderPasses(ScriptableRenderer renderer, ref RenderingData renderingData)
        {
            CameraData cameraData = renderingData.cameraData;
            if (pass == null || !pass.IsReady)
            {
                LastSkipReason = "pass missing or resolve shader has no CSResolveScreen kernel";
                return;
            }
            if (cameraData.cameraType != CameraType.Game || cameraData.renderType != CameraRenderType.Base ||
                !cameraData.resolveFinalTarget || cameraData.xrRendering ||
                cameraData.cameraTargetDescriptor.useDynamicScale ||
                cameraData.cameraTargetDescriptor.msaaSamples > 1 ||
                QualitySettings.activeColorSpace != ColorSpace.Linear)
            {
                LastSkipReason = "camera not eligible: type=" + cameraData.cameraType +
                                 " renderType=" + cameraData.renderType +
                                 " resolveFinalTarget=" + cameraData.resolveFinalTarget +
                                 " xr=" + cameraData.xrRendering +
                                 " dynamicScale=" + cameraData.cameraTargetDescriptor.useDynamicScale +
                                 " msaa=" + cameraData.cameraTargetDescriptor.msaaSamples +
                                 " colorSpace=" + QualitySettings.activeColorSpace;
                return;
            }
            if (EndfieldCharacterShadowCaster.Active.Count == 0)
            {
                EndfieldCharacterShadowCaster.Refresh();
                if (EndfieldCharacterShadowCaster.Active.Count == 0)
                {
                    LastSkipReason = "no active EndfieldCharacterShadowCaster in the scene";
                    return;
                }
            }
            LastSkipReason = "";
            pass.Setup(cameraData);
            renderer.EnqueuePass(pass);
        }

        protected override void Dispose(bool disposing)
        {
            pass?.Dispose();
            pass = null;
        }
    }

    public sealed class CharacterShadowPass : ScriptableRenderPass
    {
        public const string AtlasPassName = "EndfieldCharacterShadowAtlas";
        public const string GBufferPassName = "EndfieldCharacterShadowGBuffer";
        // The two passes are selected by their LightMode tag through
        // ScriptableRenderContext.DrawRenderers, the same mechanism URP uses for
        // UniversalForward in this frame. Material.FindPass cannot be used to resolve
        // pass indices here: in this project's Editor runs it returns -1 for every pass
        // of every shader, including "ForwardLit" on a stock URP/Lit material that
        // visibly renders in that pass, and Material.passCount reports 1 for shaders
        // with six passes. CommandBuffer.DrawRenderer with a hardcoded index was tried
        // and silently drew nothing.
        static readonly ShaderTagId AtlasPassTag = new ShaderTagId(AtlasPassName);
        static readonly ShaderTagId GBufferPassTag = new ShaderTagId(GBufferPassName);
        public const string AtlasClipMatrixName = "_EndfieldWorldToShadowClip";
        public const string IndexEncodeName = "_EndfieldCharacterShadowIndexEncode";
        public const string ScreenTextureName = "_EndfieldCharacterShadowScreen";
        public const string ScreenSizeName = "_EndfieldCharacterShadowScreenSize";
        public const string SelfShadowGateName = "_EndfieldCharacterSelfShadow";

        // Validation hooks. The live gate reads back exactly what the last frame
        // rendered instead of re-deriving it, so a format or orientation mistake shows
        // up as data rather than as a plausible-looking render.
        public static RenderTexture LastAtlas;
        public static RenderTexture LastIndex;
        public static RenderTexture LastNormal;
        public static RenderTexture LastDepth;
        public static RenderTexture LastResolved;
        public static Matrix4x4 LastWorldToShadow = Matrix4x4.identity;
        public static Matrix4x4 LastViewProj = Matrix4x4.identity;
        public static int LastSlots;

        readonly ProfilingSampler sampler = new ProfilingSampler("Endfield character self shadow");
        readonly ComputeShader resolve;
        readonly int atlasResolution;

        ComputeBuffer worldToShadow;
        ComputeBuffer biases;
        ComputeBuffer lightDirs;
        ComputeBuffer atlasParams;
        RenderTexture atlasColor;
        RenderTexture indexTarget;
        RenderTexture normalTarget;
        RenderTexture depthTarget;
        RenderTexture resolved;
        CameraData cameraData;
        Endfield.EndfieldCharacterLight light;

        public CharacterShadowPass(ComputeShader resolveShader, int atlasResolution)
        {
            resolve = resolveShader;
            this.atlasResolution = atlasResolution;
        }

        public bool IsReady => resolve != null && resolve.FindKernel("CSResolveScreen") >= 0;

        public void Setup(CameraData cameraData)
        {
            this.cameraData = cameraData;
        }

        public override void OnCameraSetup(CommandBuffer cmd, ref RenderingData renderingData)
        {
            var screen = renderingData.cameraData.cameraTargetDescriptor;
            atlasColor = Ensure(atlasColor, new RenderTextureDescriptor(atlasResolution, atlasResolution,
                RenderTextureFormat.R16, 16)
            {
                useMipMap = false,
                autoGenerateMips = false
            }, "EndfieldCharacterShadowAtlas", FilterMode.Bilinear);

            var packed = new RenderTextureDescriptor(screen.width, screen.height)
            {
                graphicsFormat = UnityEngine.Experimental.Rendering.GraphicsFormat.A2B10G10R10_UNormPack32,
                // The index target owns the prepass depth surface; the three colour
                // targets share it through SetRenderTarget below.
                depthBufferBits = 24,
                msaaSamples = 1,
                useMipMap = false,
                autoGenerateMips = false
            };
            indexTarget = Ensure(indexTarget, packed, "EndfieldCharacterShadowIndex");
            normalTarget = Ensure(normalTarget, packed, "EndfieldCharacterShadowNormal");

            var depth = new RenderTextureDescriptor(screen.width, screen.height)
            {
                graphicsFormat = UnityEngine.Experimental.Rendering.GraphicsFormat.R32_SFloat,
                depthBufferBits = 0,
                msaaSamples = 1,
                useMipMap = false,
                autoGenerateMips = false
            };
            depthTarget = Ensure(depthTarget, depth, "EndfieldCharacterShadowDepth");

            var screenShadow = new RenderTextureDescriptor(screen.width, screen.height)
            {
                graphicsFormat = UnityEngine.Experimental.Rendering.GraphicsFormat.R32G32_SFloat,
                depthBufferBits = 0,
                msaaSamples = 1,
                useMipMap = false,
                autoGenerateMips = false,
                enableRandomWrite = true
            };
            resolved = Ensure(resolved, screenShadow, ScreenTextureName);
        }

        public override void Execute(ScriptableRenderContext context, ref RenderingData renderingData)
        {
            var casters = EndfieldCharacterShadowCaster.Active;
            if (casters.Count == 0 || atlasColor == null || resolved == null) return;
            if (light == null) light = Object.FindObjectOfType<Endfield.EndfieldCharacterLight>();
            if (light == null) return;

            int slots = 0;
            foreach (var caster in casters) slots = Mathf.Max(slots, caster.slot + 1);
            EnsureBuffers(slots);

            var cmd = CommandBufferPool.Get();
            try
            {
                using (new ProfilingScope(cmd, sampler))
                {
                    Vector3 travel = -light.transform.forward;
                    FillSlotArrays(casters, travel, slots);
                    ApplyPerRendererShadowState(casters, travel);

                    var sorting = new SortingSettings(renderingData.cameraData.camera);
                    var filtering = new FilteringSettings(RenderQueueRange.opaque);

                    // DrawRenderers submits immediately, so each target's bind and clear
                    // has to reach the GPU before its draw call.
                    cmd.SetRenderTarget(atlasColor);
                    // Reversed-Z light space: an empty atlas is 0, which the resolve reads
                    // as "nothing nearer than the receiver", i.e. fully lit.
                    cmd.ClearRenderTarget(RTClearFlags.All, Color.clear,
                        SystemInfo.usesReversedZBuffer ? 0f : 1f, 0x00);
                    context.ExecuteCommandBuffer(cmd);
                    cmd.Clear();
                    var atlasDraw = new DrawingSettings(AtlasPassTag, sorting);
                    context.DrawRenderers(renderingData.cullResults, ref atlasDraw, ref filtering);

                    cmd.SetRenderTarget(new RenderTargetIdentifier[] { indexTarget, normalTarget, depthTarget },
                        new RenderTargetIdentifier(indexTarget));
                    cmd.ClearRenderTarget(RTClearFlags.All, Color.clear,
                        SystemInfo.usesReversedZBuffer ? 0f : 1f, 0x00);
                    context.ExecuteCommandBuffer(cmd);
                    cmd.Clear();
                    var gBufferDraw = new DrawingSettings(GBufferPassTag, sorting);
                    context.DrawRenderers(renderingData.cullResults, ref gBufferDraw, ref filtering);

                    DispatchResolve(cmd, slots);
                }
                context.ExecuteCommandBuffer(cmd);
            }
            finally { CommandBufferPool.Release(cmd); }
        }

        void FillSlotArrays(IReadOnlyList<EndfieldCharacterShadowCaster> casters, Vector3 travel, int slots)
        {
            var matrices = new Vector4[slots * 4];
            var biasValues = new Vector4[slots];
            var dirValues = new Vector4[slots];
            var rectValues = new Vector4[slots];
            for (int i = 0; i < slots; i++) rectValues[i] = new Vector4(0f, 0f, 1f, 1f);
            foreach (var caster in casters)
            {
                var box = EndfieldCharacterShadowProjection.Fit(
                    EndfieldCharacterShadowProjection.TowardLight(travel),
                    caster.WorldBounds(), caster.paddingFraction);
                Matrix4x4 matrix = EndfieldCharacterShadowProjection.WorldToShadow(box);
                for (int column = 0; column < 4; column++)
                    matrices[caster.slot * 4 + column] = matrix.GetColumn(column);
                if (caster.slot == 0) LastWorldToShadow = matrix;
                biasValues[caster.slot] = caster.biases;
                dirValues[caster.slot] = new Vector4(travel.x, travel.y, travel.z, 0f);
            }
            worldToShadow.SetData(matrices);
            biases.SetData(biasValues);
            lightDirs.SetData(dirValues);
            atlasParams.SetData(rectValues);
        }

        // DrawRenderers batches every caster into one call per pass, so the per-caster
        // light-box matrix and slot index travel as per-renderer property overrides
        // instead of the globals a manual DrawCasters loop could set between draws.
        readonly Dictionary<Renderer, MaterialPropertyBlock> shadowBlocks =
            new Dictionary<Renderer, MaterialPropertyBlock>();

        void ApplyPerRendererShadowState(IReadOnlyList<EndfieldCharacterShadowCaster> casters, Vector3 travel)
        {
            foreach (var caster in casters)
            {
                var box = EndfieldCharacterShadowProjection.Fit(
                    EndfieldCharacterShadowProjection.TowardLight(travel),
                    caster.WorldBounds(), caster.paddingFraction);
                Matrix4x4 clip = EndfieldCharacterShadowProjection.WorldToShadowClip(box);
                Vector4 encode = IndexEncode(caster.slot);
                foreach (var renderer in caster.Casters)
                {
                    if (!shadowBlocks.TryGetValue(renderer, out MaterialPropertyBlock block))
                    {
                        block = new MaterialPropertyBlock();
                        shadowBlocks[renderer] = block;
                    }
                    block.SetMatrix(AtlasClipMatrixName, clip);
                    block.SetVector(IndexEncodeName, encode);
                    renderer.SetPropertyBlock(block);
                }
            }
        }

        void DispatchResolve(CommandBuffer cmd, int slots)
        {
            int width = cameraData.cameraTargetDescriptor.width;
            int height = cameraData.cameraTargetDescriptor.height;
            Matrix4x4 viewProj = GL.GetGPUProjectionMatrix(cameraData.GetProjectionMatrix(), true) *
                                 cameraData.GetViewMatrix();
            int kernel = resolve.FindKernel("CSResolveScreen");
            cmd.SetComputeTextureParam(resolve, kernel, "_AtlasTex", atlasColor);
            cmd.SetComputeTextureParam(resolve, kernel, "_GBuffer0", indexTarget);
            cmd.SetComputeTextureParam(resolve, kernel, "_GBuffer1", normalTarget);
            cmd.SetComputeTextureParam(resolve, kernel, "_CameraDepth", depthTarget);
            cmd.SetComputeBufferParam(resolve, kernel, "_CharacterWorldToShadow", worldToShadow);
            cmd.SetComputeBufferParam(resolve, kernel, "_CharacterShadowBiases", biases);
            cmd.SetComputeBufferParam(resolve, kernel, "_CharacterShadowLightDir", lightDirs);
            cmd.SetComputeBufferParam(resolve, kernel, "_CharacterShadowAtlasParams", atlasParams);
            cmd.SetComputeVectorParam(resolve, "_CharacterShadowTexelSize",
                new Vector4(1f / atlasResolution, 1f / atlasResolution, atlasResolution, atlasResolution));
            cmd.SetComputeVectorParam(resolve, "_CharacterShadowParams", new Vector4(1f, 1f, slots, 0f));
            cmd.SetComputeVectorParam(resolve, "_ScreenSize",
                new Vector4(width, height, 1f / width, 1f / height));
            cmd.SetComputeMatrixParam(resolve, "_ViewProj", viewProj);
            cmd.SetComputeMatrixParam(resolve, "_InvViewProj", viewProj.inverse);
            cmd.SetComputeIntParam(resolve, "_Mode", 1);
            cmd.SetComputeIntParam(resolve, "_CaptureFlipY", 0);
            cmd.SetComputeTextureParam(resolve, kernel, "_OutScreen", resolved);
            cmd.DispatchCompute(resolve, kernel, (width + 7) / 8, (height + 7) / 8, 1);
            cmd.SetGlobalTexture(ScreenTextureName, resolved);
            cmd.SetGlobalVector(ScreenSizeName, new Vector4(width, height, 1f / width, 1f / height));
            cmd.SetGlobalFloat(SelfShadowGateName, 1f);
            LastViewProj = viewProj;
            LastSlots = slots;
            LastAtlas = atlasColor;
            LastIndex = indexTarget;
            LastNormal = normalTarget;
            LastDepth = depthTarget;
            LastResolved = resolved;
        }

        // Mirrors EndfieldCharacterIndexEncode in EndfieldCharacterShadowEncode.hlsl:
        // the value whose exponent the resolve reads back as the slot, plus a 2 in the
        // low bits so float error cannot push it below the integer.
        public static Vector4 IndexEncode(int slot)
        {
            uint raw = (1u << (8 + slot)) + 2u;
            return new Vector4((raw & 1023u) / 1023f, ((raw >> 10) & 1023u) / 1023f,
                ((raw >> 20) & 1023u) / 1023f, ((raw >> 30) & 3u) / 3f);
        }

        void EnsureBuffers(int slots)
        {
            int entries = slots * 4;
            if (worldToShadow == null || worldToShadow.count != entries)
            {
                worldToShadow?.Release();
                worldToShadow = new ComputeBuffer(entries, 16);
            }
            if (biases == null || biases.count != slots)
            {
                biases?.Release();
                biases = new ComputeBuffer(slots, 16);
                lightDirs?.Release();
                lightDirs = new ComputeBuffer(slots, 16);
                atlasParams?.Release();
                atlasParams = new ComputeBuffer(slots, 16);
            }
        }

        static RenderTexture Ensure(RenderTexture existing, RenderTextureDescriptor descriptor, string name,
            FilterMode filter = FilterMode.Point)
        {
            if (existing != null && existing.width == descriptor.width && existing.height == descriptor.height &&
                existing.graphicsFormat == descriptor.graphicsFormat &&
                existing.depth == descriptor.depthBufferBits &&
                existing.enableRandomWrite == descriptor.enableRandomWrite) return existing;
            if (existing != null) existing.Release();
            var texture = new RenderTexture(descriptor)
            {
                name = name,
                filterMode = filter,
                wrapMode = TextureWrapMode.Clamp
            };
            texture.Create();
            return texture;
        }

        public void Dispose()
        {
            worldToShadow?.Release();
            biases?.Release();
            lightDirs?.Release();
            atlasParams?.Release();
            worldToShadow = biases = lightDirs = atlasParams = null;
            Release(atlasColor); Release(indexTarget); Release(normalTarget);
            Release(depthTarget); Release(resolved);
            atlasColor = indexTarget = normalTarget = depthTarget = resolved = null;
        }

        static void Release(RenderTexture texture)
        {
            if (texture != null) texture.Release();
        }
    }
}
