using UnityEngine;
using UnityEngine.Experimental.Rendering;

namespace EndfieldShaderPack
{
    /// <summary>
    /// Camera-local, opt-in reproduction of frame 6411 / event 1205 (uberpost b354).
    /// The captured LUT is reusable; a captured bloom image is reference-only and
    /// must never be presented as dynamically generated bloom on a moving camera.
    /// </summary>
    [ExecuteAlways, DisallowMultipleComponent, RequireComponent(typeof(Camera))]
    public sealed class EndfieldCapturedPostProfile : MonoBehaviour
    {
        // Runtime-only evidence that the live feature actually submitted its pass.
        // A standalone reference shader test cannot establish scene integration.
        [System.NonSerialized] public int executedFrames;
        [System.NonSerialized] public bool lastFrameUsedDynamicBloom;

        [Tooltip("Explicit opt-in. Disable to leave the existing render unchanged.")]
        public bool applyCapturedPost;

        [Tooltip("Resource 19397: linear RGBA16F, 1024 x 32, Clamp, bilinear, no mipmaps.")]
        public Texture2D logLut;

        [Tooltip("Generate bloom from this camera using the captured compute kernels when the feature supports them.")]
        public bool generateBloom = true;

        [Tooltip("Optional CURRENT-CAMERA bloom. No static captured image is used by the live renderer.")]
        public RenderTexture liveBloomTexture;

        [Tooltip("Resource 58923. Only ApplyTo(..., allowReferenceBloom: true) can bind this.")]
        public Texture referenceBloomTexture;

        public bool sharpen = true;
        public bool vignette = true;
        public bool dither = true;
        [Range(0f, 1f)] public float sharpenStrength = 0.30000001192092896f;

        // Vectors deliberately avoid ShaderLab/Material Color sRGB conversions.
        public Vector4 exposure = new Vector4(1f, 1f, 1.600000023841858f, 0.10000099986791611f);
        public Vector4 lutParameters = new Vector4(1f / 1024f, 1f / 32f, 31f, 1f);
        public Vector4 bloomParameters = new Vector4(0.3660402297973633f, 0f, 0f, 0f);
        public Vector4 bloomThreshold = new Vector4(0.5225216150283813f, 0.2612507939338684f, 0.5225416421890259f, 0.9568615555763245f);
        public Vector4 bloomTint = Vector4.one * 0.9999998807907104f;
        public Vector4 vignetteParameters1 = new Vector4(0.5f, 0.5f, 0f, 0f);
        public Vector4 vignetteParameters2 = new Vector4(0.9000000357627869f, 2.049999952316284f, 1.2999999523162842f, 0f);
        public Vector4 vignetteColor = new Vector4(0.06666667014360428f, 0.06717457622289658f, 0.07450980693101883f, 1f);

        [Header("Explicit export orientation (scale XY, offset ZW)")]
        public Vector4 referenceSourceUV = new Vector4(1f, 1f, 0f, 0f);
        public Vector4 referenceBloomUV = new Vector4(1f, 1f, 0f, 0f);
        public Vector4 lutUV = new Vector4(1f, 1f, 0f, 0f);
        [Tooltip("Reference image coordinates for vignette/dither; does not flip texture sampling.")]
        public Vector4 referenceScreenUV = new Vector4(1f, 1f, 0f, 0f);

        public bool HasValidLut => logLut != null && logLut.width == 1024 &&
            logLut.height == 32 && logLut.mipmapCount == 1 &&
            !GraphicsFormatUtility.IsSRGBFormat(logLut.graphicsFormat);

        public bool IsConfigured => isActiveAndEnabled && applyCapturedPost && HasValidLut;

        /// <summary>
        /// rawEncodedOutput writes source sRGB+dither directly to a LINEAR float RT
        /// for reference tests. Live output decodes it back to linear so Unity's
        /// final sRGB write encodes exactly once. Reference textures are opt-in here.
        /// Does not change global shader state or texture import settings.
        /// </summary>
        public bool ApplyTo(Material material, int width, int height,
            bool rawEncodedOutput = false, bool allowReferenceBloom = false)
        {
            if (material == null || !HasValidLut || width <= 0 || height <= 0)
                return false;

            Texture bloom = liveBloomTexture != null && liveBloomTexture.IsCreated()
                ? (Texture)liveBloomTexture : Texture2D.blackTexture;
            if (allowReferenceBloom && referenceBloomTexture != null)
                bloom = referenceBloomTexture;

            material.SetTexture("_EndfieldPostLut", logLut);
            material.SetTexture("_EndfieldPostBloom", bloom);
            material.SetVector("_EndfieldPostScreenSize", new Vector4(width, height, 1f / width, 1f / height));
            material.SetVector("_EndfieldPostExposure", exposure);
            material.SetVector("_EndfieldPostLutParameters", lutParameters);
            material.SetVector("_EndfieldPostBloomParameters", bloomParameters);
            material.SetVector("_EndfieldPostBloomThreshold", bloomThreshold);
            material.SetVector("_EndfieldPostBloomTint", bloomTint);
            material.SetVector("_EndfieldPostVignette1", vignetteParameters1);
            material.SetVector("_EndfieldPostVignette2", vignetteParameters2);
            material.SetVector("_EndfieldPostVignetteColor", vignetteColor);
            material.SetVector("_EndfieldPostOptions", new Vector4(
                sharpen ? sharpenStrength : 0f, vignette ? 1f : 0f, dither ? 1f : 0f, 0f));
            material.SetFloat("_EndfieldPostOutputMode", rawEncodedOutput ? 0f : 1f);
            material.SetVector("_EndfieldPostSourceUV", allowReferenceBloom ? referenceSourceUV : new Vector4(1f, 1f, 0f, 0f));
            material.SetVector("_EndfieldPostBloomUV", allowReferenceBloom ? referenceBloomUV : new Vector4(1f, 1f, 0f, 0f));
            material.SetVector("_EndfieldPostLutUV", lutUV);
            material.SetVector("_EndfieldPostScreenUV", allowReferenceBloom ? referenceScreenUV : new Vector4(1f, 1f, 0f, 0f));
            return true;
        }
    }
}
