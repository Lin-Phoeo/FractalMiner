using UnityEngine;

namespace Endfield
{
    // Captured front frame 6411 / event 875. Keep the profile alive after scene reload.
    [ExecuteAlways]
    public sealed class EndfieldOfficialFrameGlobals : MonoBehaviour
    {
        [Tooltip("Use source-derived dry character shading; disable to compare the previous reconstruction.")]
        public bool useSourceShading = true;
        [Tooltip("Optional recovered character environment cube. Missing data contributes no IBL, not Unity's default cube.")]
        public Cubemap capturedEnvironment;
        static readonly Vector4[] Character =
        {
            new Vector4(1, 1, .65f, .9f),
            new Vector4(0, 1, 0, 1),
            new Vector4(.8490771055f, .8957685828f, 1.1509230137f, 1),
            new Vector4(1.260404f, .739596f, .739596f, 1),
            new Vector4(1, .913683f, .911321f, 1),
            Vector4.one,
            new Vector4(0, 1, 4.37114e-8f, 0),
            new Vector4(.15f, 1.5f, .5f, 0),
            new Vector4(0, 0, 0, 1),
            new Vector4(8.74228e-8f, -1, 0, .4f),
            new Vector4(0, 9.14768e-41f, 2.25f, -100),
            new Vector4(.1763191968f, .5299192667f, .8295161724f, -.1f),
            new Vector4(1, 1, 1, 0),
            new Vector4(0, 0, 0, 1),
            new Vector4(0, 0, 0, 1),
            new Vector4(0, .001f, -1, 0)
        };

        public static void ApplyGlobals(bool useSourceShading = true, Cubemap capturedEnvironment = null)
        {
            for (int i = 0; i < Character.Length; i++) Shader.SetGlobalVector("_CharacterParams" + i, Character[i]);
            Shader.SetGlobalVector("_EnvironmentGlobalParams0", new Vector4(.287722f, .287722f, 1, 0));
            Shader.SetGlobalVector("_ExposureWithMiscParams", new Vector4(1, 1, 1.6f, .100001f));
            Shader.SetGlobalFloat("_EndfieldOfficialFrameEnabled", 1);
            Shader.SetGlobalFloat("_EndfieldCapturedLightIntensity", 1.6243867874f);
            Shader.SetGlobalFloat("_EndfieldOfficialShadingEnabled", useSourceShading ? 1 : 0);
            Shader.SetGlobalFloat("_EndfieldCapturedCubemapAvailable", capturedEnvironment != null ? 1 : 0);
            if (capturedEnvironment != null) Shader.SetGlobalTexture("_CharMaxCubemap", capturedEnvironment);
        }

        void OnEnable() { ApplyGlobals(useSourceShading, capturedEnvironment); }
        void Update() { ApplyGlobals(useSourceShading, capturedEnvironment); }
        void OnDisable()
        {
            Shader.SetGlobalFloat("_EndfieldOfficialFrameEnabled", 0);
            Shader.SetGlobalFloat("_EndfieldOfficialShadingEnabled", 0);
            Shader.SetGlobalFloat("_EndfieldCapturedCubemapAvailable", 0);
            Shader.SetGlobalVector("_CharacterParams1", Vector4.zero);
        }
    }
}
