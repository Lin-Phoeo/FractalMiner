using System;
using System.Collections.Generic;
using System.IO;
using System.Text;
using UnityEditor;
using UnityEditor.SceneManagement;
using UnityEngine;
using UnityEngine.Rendering;
using Object = UnityEngine.Object;

namespace EndfieldShaderPack
{
    // Synthetic, numeric checks only: no production textures or image comparisons.
    public static class EndfieldSkinShadingValidation
    {
        const int Resolution = 16;
        const int RampWidth = 256;
        const float Tolerance = .003f;
        const float LightIntensity = 1.6243867874f;
        const float AmbientPeak = .287722f;
        const float LightOffset = -.1f;
        static readonly Vector3 Luma = new Vector3(.212672904f, .715152204f, .072175004f);
        static readonly Vector3 Albedo = new Vector3(.2f, .3f, .4f);
        static readonly Vector3 LutColor = new Vector3(.12f, .16f, .22f);
        static readonly Vector3 AmbientTint = new Vector3(1.260404f, .739596f, .739596f);
        static readonly Vector3 LightColor = new Vector3(1f, .913683f, .911321f);
        static readonly Vector3 LightDirection = new Vector3(.6f, 0f, .8f);

        struct Case
        {
            public string Name;
            public float NormalWeight, SdfGradient, BaseAlpha, ConstantRampAlpha;
            public bool GradientRamp, UseSdf;

            public Case(string name, float normalWeight, float sdfGradient, float baseAlpha,
                        bool gradientRamp = true, float constantRampAlpha = 1f, bool useSdf = true)
            {
                Name = name; NormalWeight = normalWeight; SdfGradient = sdfGradient;
                BaseAlpha = baseAlpha; GradientRamp = gradientRamp; ConstantRampAlpha = constantRampAlpha;
                UseSdf = useSdf;
            }
        }

        sealed class Globals : IDisposable
        {
            readonly Dictionary<int, Vector4> vectors = new Dictionary<int, Vector4>();
            readonly Dictionary<int, float> floats = new Dictionary<int, float>();

            public Globals()
            {
                for (int i = 0; i < 16; i++) SaveVector("_CharacterParams" + i);
                foreach (string name in new[] { "_EnvironmentGlobalParams0", "_ExposureWithMiscParams",
                    "_CharacterLightDir", "_CharacterLightColor", "_CharacterAmbient" }) SaveVector(name);
                foreach (string name in new[] { "_EndfieldOfficialFrameEnabled", "_EndfieldOfficialShadingEnabled",
                    "_EndfieldCapturedLightIntensity" })
                {
                    int id = Shader.PropertyToID(name); floats.Add(id, Shader.GetGlobalFloat(id));
                }
            }

            void SaveVector(string name)
            {
                int id = Shader.PropertyToID(name); vectors.Add(id, Shader.GetGlobalVector(id));
            }

            public void Dispose()
            {
                foreach (var value in vectors) Shader.SetGlobalVector(value.Key, value.Value);
                foreach (var value in floats) Shader.SetGlobalFloat(value.Key, value.Value);
            }
        }

        static Vector3 Saturation(Vector3 color, float amount) =>
            Vector3.LerpUnclamped(Vector3.one * Vector3.Dot(color, Luma), color, amount);

        static float Smooth(float min, float max, float value)
        {
            float t = Mathf.Clamp01((value - min) / (max - min));
            return t * t * (3f - 2f * t);
        }

        // Independently model a repeat/bilinear texture read at texel centers.
        // This also checks the SDF ramp coordinates that cross the repeat seam.
        static float GradientAlpha(float u)
        {
            float texel = u * RampWidth - .5f;
            int left = Mathf.FloorToInt(texel);
            float fraction = texel - left;
            int first = ((left % RampWidth) + RampWidth) % RampWidth;
            int second = (first + 1) % RampWidth;
            return Mathf.Lerp((first + .5f) / RampWidth, (second + .5f) / RampWidth, fraction);
        }

        // b138 dry reduction: N=(0,0,1), identity object transform, CP12.x=1,
        // CP6=0, both shadow inputs=1, white ramp RGB, zero rim/spec/highlight.
        // In particular, skin's inner shadow blend is baseAlpha + rampAlpha,
        // not the hair/cloth expression 2 * rampAlpha.
        static Vector3 Expected(Case item, out float rampX, out float rampAlpha)
        {
            const float horizontalEpsilon = 1f / 16384f;
            float horizontalZ = LightDirection.z / Mathf.Sqrt(
                LightDirection.x * LightDirection.x + LightDirection.z * LightDirection.z
                + horizontalEpsilon * horizontalEpsilon);
            float back = horizontalZ * .5f;
            float center = Mathf.Clamp(.5f - back, .001f, .999f);
            float transition = Smooth(Mathf.Max(2f * center - 1f, 0f),
                                      Mathf.Min(2f * center, 1f), item.SdfGradient);
            float sdfLight = 2f * Mathf.Abs(-transition - back * Mathf.Ceil(back)) - 1f;
            float normalLight = Mathf.Clamp(LightDirection.z + LightOffset, -1f, 1f);
            rampX = Mathf.Lerp(sdfLight, normalLight, item.UseSdf ? item.NormalWeight : 1f) * .5f + .5f;
            rampAlpha = item.GradientRamp ? GradientAlpha(rampX) : item.ConstantRampAlpha;

            float litMask = Mathf.Min(item.BaseAlpha, rampAlpha);
            Vector3 diffuse = Albedo * .96f;
            Vector3 deep = LutColor * (.96f * .65f);
            Vector3 shadowSelection = Vector3.Lerp(Saturation(deep * .65f, 1.2f), deep,
                                                   Mathf.Clamp01(item.BaseAlpha + rampAlpha));
            Vector3 baseSelection = Vector3.Lerp(shadowSelection, diffuse, litMask);
            // White RGB gives zero ramp chroma and leaves luminance unchanged.
            float luminance = Vector3.Dot(baseSelection, Luma);
            Vector3 diffuseTerm = baseSelection * Mathf.Clamp(luminance / Mathf.Max(luminance, .001f), 0f, 1.5f);
            Vector3 ambient = .725f * Vector3.Lerp(AmbientTint, Vector3.one, litMask);
            Vector3 direct = LightColor * LightIntensity;
            Vector3 lightTerm = Vector3.Lerp(Vector3.one * Vector3.Dot(direct, Luma), direct, litMask)
                                + Vector3.Scale(ambient * AmbientPeak, LightColor);
            Vector3 color = Vector3.Scale(lightTerm, diffuseTerm);
            float boost = Mathf.Clamp(Vector3.Dot(color, Luma) - .5f, 0f, .5f);
            return Saturation(color, 1f + boost * boost);
        }

        static List<Case> Cases()
        {
            var result = new List<Case>();
            foreach (float gradient in new[] { .05f, .14f })
                foreach (float normalWeight in new[] { 0f, .5f, 1f })
                    result.Add(new Case($"sdf={gradient:F2}/maskG={normalWeight:F1}", normalWeight, gradient, 1f));
            foreach (float alpha in new[] { 0f, .35f, 1f })
                result.Add(new Case($"constant-ramp-alpha={alpha:F2}", 0f, .05f, 1f, false, alpha));
            foreach (float normalWeight in new[] { 0f, 1f })
                foreach (float alpha in new[] { 0f, .25f, .55f, 1f })
                    result.Add(new Case($"base-alpha={alpha:F2}/maskG={normalWeight:F1}", normalWeight, .05f, alpha));
            result.Add(new Case("both-alpha-low", .5f, .05f, .15f, false, .2f));
            // Body b114/b208 uses the same dry equations with normalWeight=1,
            // no SDF lightmap, no emotion and no highlight-map contribution.
            result.Add(new Case("body-no-sdf/full-alpha", 1f, .05f, 1f, useSdf: false));
            result.Add(new Case("body-no-sdf/base-alpha=.25", 1f, .14f, .25f, useSdf: false));
            result.Add(new Case("body-no-sdf/ramp-alpha=.35", 1f, .05f, 1f, false, .35f, false));
            return result;
        }

        static void Fill(Texture2D texture, Color value)
        {
            var pixels = new Color[texture.width * texture.height];
            for (int i = 0; i < pixels.Length; i++) pixels[i] = value;
            texture.SetPixels(pixels); texture.Apply(false, false);
        }

        static Texture2D Constant(List<Object> owned, string name, Color color, int width = 2, int height = 2)
        {
            var texture = new Texture2D(width, height, TextureFormat.RGBAFloat, false, true)
            { name = name, filterMode = FilterMode.Bilinear, wrapMode = TextureWrapMode.Repeat };
            owned.Add(texture); Fill(texture, color); return texture;
        }

        static void ConfigureGlobals()
        {
            for (int i = 0; i < 16; i++) Shader.SetGlobalVector("_CharacterParams" + i, Vector4.zero);
            Shader.SetGlobalVector("_CharacterParams0", new Vector4(1, 1, .65f, .9f));
            Shader.SetGlobalVector("_CharacterParams1", new Vector4(0, 1, 1, 1));
            Shader.SetGlobalVector("_CharacterParams3", new Vector4(AmbientTint.x, AmbientTint.y, AmbientTint.z, 1));
            Shader.SetGlobalVector("_CharacterParams4", new Vector4(LightColor.x, LightColor.y, LightColor.z, 1));
            Shader.SetGlobalVector("_CharacterParams7", new Vector4(.15f, 1.5f, .5f, 0));
            Shader.SetGlobalVector("_CharacterParams11", new Vector4(LightDirection.x, LightDirection.y, LightDirection.z, LightOffset));
            Shader.SetGlobalVector("_CharacterParams12", new Vector4(1, 1, 1, 0));
            Shader.SetGlobalVector("_EnvironmentGlobalParams0", new Vector4(AmbientPeak, AmbientPeak, 1, 0));
            Shader.SetGlobalVector("_ExposureWithMiscParams", Vector4.one);
            Shader.SetGlobalVector("_CharacterLightDir", new Vector4(0, 0, 1, 1));
            Shader.SetGlobalVector("_CharacterLightColor", Vector4.one);
            Shader.SetGlobalVector("_CharacterAmbient", Vector4.zero);
            Shader.SetGlobalFloat("_EndfieldOfficialFrameEnabled", 1);
            Shader.SetGlobalFloat("_EndfieldOfficialShadingEnabled", 1);
            Shader.SetGlobalFloat("_EndfieldCapturedLightIntensity", LightIntensity);
        }

        static void CheckShader(Shader shader, StringBuilder report, string stage)
        {
            var errors = new StringBuilder();
            foreach (var message in ShaderUtil.GetShaderMessages(shader))
            {
                report.AppendLine($"shader/{stage}: {message.severity}: {message.message} ({message.file}:{message.line})");
                if (message.severity.ToString() == "Error") errors.AppendLine(message.message);
            }
            if (errors.Length != 0) throw new InvalidOperationException("Skin shader compilation failed:\n" + errors);
            if (!shader.isSupported) throw new InvalidOperationException("Endfield/CharacterLit is unsupported by the current graphics device.");
        }

        [MenuItem("Endfield/Validate Official Skin Shading Numerically", false, 54)]
        public static void RunNumerical()
        {
            // Never discard an interactive editor's dirty scenes for a test.
            if (!Application.isBatchMode && !EditorSceneManager.SaveCurrentModifiedScenesIfUserWantsTo())
            {
                Debug.Log("[OfficialSkinShading] Cancelled; scene save was declined.");
                return;
            }
            if (EditorApplication.isPlayingOrWillChangePlaymode)
                throw new InvalidOperationException("Run skin validation in edit mode.");
            Shader shader = Shader.Find("Endfield/CharacterLit");
            if (shader == null) throw new InvalidOperationException("Endfield/CharacterLit was not found.");
            if (!SystemInfo.SupportsRenderTextureFormat(RenderTextureFormat.ARGBFloat)
                || !SystemInfo.SupportsTextureFormat(TextureFormat.RGBAFloat))
                throw new InvalidOperationException("This test requires RGBAFloat textures and an ARGBFloat render target.");

            string reportPath = Path.GetFullPath(Path.Combine(Application.dataPath, "../Logs/official-skin-shading-numerical.txt"));
            var report = new StringBuilder();
            report.AppendLine($"Device={SystemInfo.graphicsDeviceType}; colorSpace={QualitySettings.activeColorSpace}; tolerance={Tolerance}");
            report.AppendLine("Synthetic RGBAFloat inputs; N=+Z; CP6=0; rim/spec/highlight disabled; opaque output.");
            var scenes = EditorSceneManager.GetSceneManagerSetup();
            var globals = new Globals();
            var owned = new List<Object>();
            RenderTexture prior = RenderTexture.active;
            RenderTexture target = null;
            Camera camera = null;
            bool createdScene = false;
            try
            {
                CheckShader(shader, report, "before-render");
                EditorSceneManager.NewScene(NewSceneSetup.EmptyScene, NewSceneMode.Single);
                createdScene = true;
                ConfigureGlobals();

                var cameraObject = new GameObject("SkinNumericalCamera"); owned.Add(cameraObject);
                camera = cameraObject.AddComponent<Camera>();
                camera.transform.SetPositionAndRotation(new Vector3(0, 0, 2), Quaternion.Euler(0, 180, 0));
                camera.orthographic = true; camera.orthographicSize = .5f;
                camera.nearClipPlane = .01f; camera.farClipPlane = 4f;
                camera.allowHDR = true; camera.allowMSAA = false;
                camera.clearFlags = CameraClearFlags.SolidColor; camera.backgroundColor = Color.clear;

                var quad = new GameObject("SkinNumericalQuad"); owned.Add(quad);
                var mesh = new Mesh { name = "SkinValidationQuadNPlusZ" }; owned.Add(mesh);
                mesh.vertices = new[] { new Vector3(-.5f, -.5f, 0), new Vector3(.5f, -.5f, 0),
                    new Vector3(.5f, .5f, 0), new Vector3(-.5f, .5f, 0) };
                mesh.normals = new[] { Vector3.forward, Vector3.forward, Vector3.forward, Vector3.forward };
                mesh.tangents = new[] { new Vector4(1,0,0,1), new Vector4(1,0,0,1), new Vector4(1,0,0,1), new Vector4(1,0,0,1) };
                mesh.uv = new[] { Vector2.zero, Vector2.right, Vector2.one, Vector2.up };
                mesh.triangles = new[] { 0, 1, 2, 0, 2, 3 }; mesh.RecalculateBounds();
                quad.AddComponent<MeshFilter>().sharedMesh = mesh;
                var renderer = quad.AddComponent<MeshRenderer>();
                renderer.shadowCastingMode = ShadowCastingMode.Off; renderer.receiveShadows = false;
                var material = new Material(shader) { name = "SkinNumericalMaterial" }; owned.Add(material);
                renderer.sharedMaterial = material;
                foreach (string property in new[] { "_EnableOutline", "_UseBumpMap", "_UseSpecBumpMap", "_UseMetallicGlossMap",
                    "_UseEmotionMap", "_FaceHighlightMap", "_Specular", "_Metallic", "_SkinRimOffScale", "_FaceRimOffScale",
                    "_UseParallax", "_UseEmission", "_EnableVFXColorAdjustment", "_DebugView", "_SurfaceType", "_EnableAlphaTest", "_Cull" })
                    material.SetFloat(property, 0);
                foreach (string property in new[] { "_MaterialFamily", "_UseSDFLightmap", "_UseDiffRampMap", "_UseShadowLutTex", "_BackFaceNormalFlip", "_ZWrite" })
                    material.SetFloat(property, 1);
                material.SetFloat("_SrcBlend", 1); material.SetFloat("_DstBlend", 0);
                material.SetFloat("_AlphaSrcBlend", 1); material.SetFloat("_AlphaDstBlend", 0);
                material.SetColor("_BaseColor", Color.white); material.SetColor("_SDFRimColor", Color.white);
                material.SetTextureScale("_BaseMap", Vector2.one); material.SetTextureOffset("_BaseMap", Vector2.zero);
                material.SetShaderPassEnabled("Outline", false); material.SetShaderPassEnabled("SRPDefaultUnlit", false);

                var baseMap = Constant(owned, "SkinBase", new Color(Albedo.x, Albedo.y, Albedo.z, 1));
                var mask = Constant(owned, "SkinMask", Color.clear);
                var sdf = Constant(owned, "SkinSDF", Color.clear);
                var lut = Constant(owned, "SkinLUT", new Color(LutColor.x, LutColor.y, LutColor.z, 1), 1024, 32);
                var black = Constant(owned, "SkinHighlightBlack", Color.clear);
                var constantRamp = Constant(owned, "SkinConstantRamp", Color.white);
                var gradientRamp = Constant(owned, "SkinGradientRamp", Color.white, RampWidth, 1);
                var rampPixels = new Color[RampWidth];
                for (int i = 0; i < RampWidth; i++) rampPixels[i] = new Color(1, 1, 1, (i + .5f) / RampWidth);
                gradientRamp.SetPixels(rampPixels); gradientRamp.Apply(false, false);
                material.SetTexture("_BaseMap", baseMap); material.SetTexture("_SDFMask", mask);
                material.SetTexture("_SDFLightmap", sdf); material.SetTexture("_ShadowLutTex", lut);
                material.SetTexture("_HighlightMap", black);

                target = new RenderTexture(Resolution, Resolution, 24, RenderTextureFormat.ARGBFloat, RenderTextureReadWrite.Linear)
                    { name = "SkinNumericalTarget", antiAliasing = 1 };
                if (!target.Create()) throw new InvalidOperationException("Could not create skin float render target.");
                var readback = new Texture2D(Resolution, Resolution, TextureFormat.RGBAFloat, false, true); owned.Add(readback);
                camera.targetTexture = target;
                int failures = 0;
                var cases = Cases();
                foreach (Case item in cases)
                {
                    Fill(baseMap, new Color(Albedo.x, Albedo.y, Albedo.z, item.BaseAlpha));
                    Fill(mask, new Color(0, item.NormalWeight, 0, 0));
                    Fill(sdf, new Color(item.SdfGradient, item.SdfGradient, .5f, 1));
                    Fill(constantRamp, new Color(1, 1, 1, item.ConstantRampAlpha));
                    material.SetFloat("_UseSDFLightmap", item.UseSdf ? 1 : 0);
                    material.SetTexture("_DiffRampMap", item.GradientRamp ? gradientRamp : constantRamp);
                    camera.Render(); RenderTexture.active = target;
                    readback.ReadPixels(new Rect(0, 0, Resolution, Resolution), 0, 0); readback.Apply(false, false);
                    Color pixel = readback.GetPixel(Resolution / 2, Resolution / 2);
                    Vector3 gpu = new Vector3(pixel.r, pixel.g, pixel.b);
                    Vector3 expected = Expected(item, out float rampX, out float rampAlpha);
                    Vector3 delta = gpu - expected;
                    float error = Mathf.Max(Mathf.Abs(delta.x), Mathf.Abs(delta.y), Mathf.Abs(delta.z));
                    bool passed = !float.IsNaN(error) && !float.IsInfinity(error) && error <= Tolerance
                                  && !float.IsNaN(pixel.a) && Mathf.Abs(pixel.a - 1f) <= .002f;
                    if (!passed) failures++;
                    report.AppendLine($"{(passed ? "PASS" : "FAIL")} {item.Name}: rampX={rampX:F6} rampA={rampAlpha:F6} "
                        + $"gpu={gpu.ToString("F6")} cpu={expected.ToString("F6")} alpha={pixel.a:F6} maxError={error:G6}");
                }
                CheckShader(shader, report, "after-render");
                report.AppendLine($"Result: {cases.Count - failures}/{cases.Count} passed.");
                if (failures != 0) throw new InvalidOperationException($"Official skin GPU/CPU reference: {failures}/{cases.Count} failed. See {reportPath}");
                Debug.Log($"[OfficialSkinShading] PASS: {cases.Count} GPU/CPU reference cases. Report: {reportPath}");
            }
            catch (Exception exception)
            {
                report.AppendLine("ERROR: " + exception);
                throw;
            }
            finally
            {
                if (camera != null) camera.targetTexture = null;
                RenderTexture.active = prior;
                if (target != null) { target.Release(); Object.DestroyImmediate(target); }
                for (int i = owned.Count - 1; i >= 0; i--) if (owned[i] != null) Object.DestroyImmediate(owned[i]);
                try
                {
                    if (createdScene && scenes.Length != 0) EditorSceneManager.RestoreSceneManagerSetup(scenes);
                }
                finally
                {
                    globals.Dispose();
                    Directory.CreateDirectory(Path.GetDirectoryName(reportPath));
                    File.WriteAllText(reportPath, report.ToString());
                }
            }
        }
    }
}
