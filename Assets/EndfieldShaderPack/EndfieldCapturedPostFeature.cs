using UnityEngine;
using UnityEngine.Rendering;
using UnityEngine.Rendering.Universal;

namespace EndfieldShaderPack
{
    /// <summary>
    /// Add to a dedicated renderer asset. Only an explicitly configured camera is
    /// affected. URP post processing must be disabled: b354 already owns grading,
    /// output transfer, vignette and sharpening, so a second stack is incorrect.
    /// </summary>
    public sealed class EndfieldCapturedPostFeature : ScriptableRendererFeature
    {
        [SerializeField] Shader shader;
        [SerializeField] ComputeShader bloomShader;
        Material material;
        CapturedPostPass pass;

        public override void Create()
        {
            pass?.Dispose();
            CoreUtils.Destroy(material);
            if (shader == null) shader = Shader.Find("Hidden/Endfield/CapturedPost");
            material = shader != null ? CoreUtils.CreateEngineMaterial(shader) : null;
            pass = new CapturedPostPass(bloomShader)
            {
                renderPassEvent = RenderPassEvent.BeforeRenderingPostProcessing
            };
            pass.ConfigureInput(ScriptableRenderPassInput.Color);
        }

        public override void AddRenderPasses(ScriptableRenderer renderer, ref RenderingData renderingData)
        {
            CameraData cameraData = renderingData.cameraData;
            if (material == null || !material.shader.isSupported || pass == null || cameraData.cameraType != CameraType.Game ||
                cameraData.renderType != CameraRenderType.Base || !cameraData.resolveFinalTarget ||
                cameraData.xrRendering || cameraData.cameraTargetDescriptor.useDynamicScale ||
                cameraData.cameraTargetDescriptor.msaaSamples > 1 || !cameraData.isHdrEnabled ||
                cameraData.postProcessEnabled || QualitySettings.activeColorSpace != ColorSpace.Linear)
                return;

            EndfieldCapturedPostProfile profile = cameraData.camera.GetComponent<EndfieldCapturedPostProfile>();
            if (profile == null || !profile.IsConfigured)
                return;

            pass.Setup(material, profile);
            renderer.EnqueuePass(pass);
        }

        protected override void Dispose(bool disposing)
        {
            pass?.Dispose();
            pass = null;
            CoreUtils.Destroy(material);
            material = null;
        }

        sealed class CapturedPostPass : ScriptableRenderPass
        {
            readonly ProfilingSampler sampler = new ProfilingSampler("Endfield captured b354 post");
            RTHandle temporaryColor;
            Material material;
            EndfieldCapturedPostProfile profile;
            readonly EndfieldCapturedBloom bloom;
            bool canGenerateBloom;

            public CapturedPostPass(ComputeShader bloomShader)
            {
                if (bloomShader != null) bloom = new EndfieldCapturedBloom(bloomShader);
            }

            public void Setup(Material postMaterial, EndfieldCapturedPostProfile cameraProfile)
            {
                material = postMaterial;
                profile = cameraProfile;
            }

            public override void OnCameraSetup(CommandBuffer cmd, ref RenderingData renderingData)
            {
                RenderTextureDescriptor descriptor = renderingData.cameraData.cameraTargetDescriptor;
                descriptor.depthBufferBits = 0;
                descriptor.msaaSamples = 1;
                descriptor.bindMS = false;
                descriptor.useMipMap = false;
                descriptor.autoGenerateMips = false;
                RenderingUtils.ReAllocateIfNeeded(ref temporaryColor, descriptor,
                    FilterMode.Bilinear, TextureWrapMode.Clamp, name: "_EndfieldCapturedPostColor");
                canGenerateBloom = profile != null && profile.generateBloom && bloom != null &&
                    bloom.IsSupported && bloom.Setup(renderingData.cameraData.cameraTargetDescriptor);
                ConfigureTarget(renderingData.cameraData.renderer.cameraColorTargetHandle);
            }

            public override void Execute(ScriptableRenderContext context, ref RenderingData renderingData)
            {
                if (profile == null || !profile.IsConfigured || material == null || temporaryColor == null)
                    return;

                RenderTextureDescriptor descriptor = renderingData.cameraData.cameraTargetDescriptor;
                if (!profile.ApplyTo(material, descriptor.width, descriptor.height))
                    return;

                RTHandle source = renderingData.cameraData.renderer.cameraColorTargetHandle;
                CommandBuffer cmd = CommandBufferPool.Get();
                bool usedDynamicBloom = false;
                try
                {
                    using (new ProfilingScope(cmd, sampler))
                    {
                        if (canGenerateBloom)
                        {
                            RTHandle generatedBloom = bloom.Render(cmd, source, profile.exposure.x);
                            if (generatedBloom != null && generatedBloom.rt != null)
                            {
                                material.SetTexture("_EndfieldPostBloom", generatedBloom.rt);
                                usedDynamicBloom = true;
                            }
                        }
                        Blitter.BlitCameraTexture(cmd, source, temporaryColor, material, 0);
                        Blitter.BlitCameraTexture(cmd, temporaryColor, source);
                    }
                    context.ExecuteCommandBuffer(cmd);
                    profile.executedFrames++;
                    profile.lastFrameUsedDynamicBloom = usedDynamicBloom;
                }
                finally { CommandBufferPool.Release(cmd); }
            }

            public void Dispose()
            {
                temporaryColor?.Release();
                temporaryColor = null;
                bloom?.Dispose();
            }
        }
    }
}
