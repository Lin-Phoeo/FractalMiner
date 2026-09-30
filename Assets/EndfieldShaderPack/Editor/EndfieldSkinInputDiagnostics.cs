using System;
using System.Globalization;
using System.IO;
using System.Text;
using UnityEditor;
using UnityEngine;

namespace EndfieldShaderPack.EditorTools
{
    public static class EndfieldSkinInputDiagnostics
    {
        static string outputDirectory;
        static readonly CultureInfo Invariant = CultureInfo.InvariantCulture;

        public static void Run()
        {
            string folder = Environment.GetEnvironmentVariable("ENDFIELD_SKIN_DIAGNOSTICS")
                ?? "Validation/skin-input-" + DateTime.UtcNow.ToString("yyyyMMdd-HHmmss");
            if (Directory.Exists(folder)) throw new IOException("Use a fresh diagnostic directory: " + folder);
            Directory.CreateDirectory(folder);
            outputDirectory = folder;
            try
            {
                CheckReadback();
                EndfieldPoseApplyValidation.RunPoseApply();
                Debug.Log("[SkinInputDiagnostics] Saved " + Path.GetFullPath(folder));
            }
            finally { outputDirectory = null; }
        }

        static void CheckReadback()
        {
            var target = new RenderTexture(2, 2, 0, RenderTextureFormat.ARGBFloat, RenderTextureReadWrite.Linear);
            var previous = RenderTexture.active;
            bool previousSRGB = GL.sRGBWrite;
            try
            {
                target.Create();
                RenderTexture.active = target;
                GL.sRGBWrite = false;
                GL.Clear(false, true, new Color(.18f, 2f, -.25f, .5f));
                SaveRenderTexture(target, "readback-check");
                using (var reader = new BinaryReader(File.OpenRead(Path.Combine(outputDirectory, "readback-check.rgba32f"))))
                {
                    float[] expected = { .18f, 2f, -.25f, .5f };
                    for (int pixel = 0; pixel < 4; pixel++)
                    foreach (float value in expected)
                    {
                        float actual = reader.ReadSingle();
                        if (float.IsNaN(actual) || float.IsInfinity(actual) || Mathf.Abs(actual - value) > 1e-5f)
                            throw new InvalidOperationException("Linear HDR readback contract failed: " + actual + " vs " + value);
                    }
                }
                if (RenderTexture.active != target) throw new InvalidOperationException("Readback changed the active target.");
            }
            finally
            {
                GL.sRGBWrite = previousSRGB;
                RenderTexture.active = previous;
                target.Release();
                UnityEngine.Object.DestroyImmediate(target);
            }
        }

        public static void Record(Camera camera, Transform root, RenderTexture litTarget)
        {
            if (outputDirectory == null) return;
            SaveRenderTexture(litTarget, "current-prepost");
            var official = EndfieldCaptureAssets.Texture("post-input");
            if (official == null || !official.isReadable)
                throw new InvalidOperationException("Readable captured post-input is required.");
            SavePixels(official, "official-prepost");
            var text = new StringBuilder();
            text.AppendLine("utc=" + DateTime.UtcNow.ToString("O"));
            text.AppendLine("officialSource=" + AssetDatabase.GetAssetPath(official));
            text.AppendLine("colorSpace=" + QualitySettings.activeColorSpace);
            text.AppendLine("cameraToWorld=" + camera.cameraToWorldMatrix.ToString("R"));
            foreach (string name in new[] { "_EndfieldOfficialFrameEnabled", "_EndfieldOfficialShadingEnabled",
                "_EndfieldCapturedLightIntensity" })
                text.AppendLine(name + "=" + Shader.GetGlobalFloat(name).ToString("R", Invariant));
            for (int i = 0; i < 16; i++)
                text.AppendLine("_CharacterParams" + i + "=" + Shader.GetGlobalVector("_CharacterParams" + i).ToString("R"));
            foreach (string name in new[] { "_EnvironmentGlobalParams0", "_ExposureWithMiscParams",
                "_CharacterLightDir", "_CharacterLightColor", "_CharacterAmbient" })
                text.AppendLine(name + "=" + Shader.GetGlobalVector(name).ToString("R"));
            foreach (var renderer in root.GetComponentsInChildren<SkinnedMeshRenderer>())
                foreach (var material in renderer.sharedMaterials)
                {
                    if (material == null || !material.HasProperty("_MaterialFamily")
                        || material.GetFloat("_MaterialFamily") <= .5f || material.GetFloat("_MaterialFamily") >= 1.5f) continue;
                    text.AppendLine("\nrenderer=" + renderer.name + "; material=" + AssetDatabase.GetAssetPath(material));
                    text.AppendLine("shader=" + material.shader.name + "; enabled=" + renderer.enabled
                        + "; propertyBlock=" + renderer.HasPropertyBlock());
                    text.AppendLine("objectToWorld=" + renderer.localToWorldMatrix.ToString("R"));
                    bool sourceShading = Shader.GetGlobalFloat("_EndfieldOfficialFrameEnabled") > .5f
                        && Shader.GetGlobalFloat("_EndfieldOfficialShadingEnabled") > .5f
                        && Shader.GetGlobalVector("_CharacterParams1").y >= .5f
                        && material.GetFloat("_SurfaceType") < .5f && material.GetFloat("_DebugView") < .5f
                        && material.GetFloat("_UseParallax") < .5f;
                    text.AppendLine("sourceShading=" + sourceShading + " (material/global gate; property blocks reported separately)");
                    foreach (string name in new[] { "_MaterialFamily", "_SurfaceType", "_DebugView", "_UseParallax",
                        "_UseBumpMap", "_BumpScale", "_UseSDFLightmap", "_UseDiffRampMap", "_UseShadowLutTex",
                        "_UseEmotionMap", "_EmotionIndex", "_EmotionBlend", "_SkinRimOffScale", "_FaceRimOffScale",
                        "_Smoothness", "_Metallic", "_Specular", "_BackFaceNormalFlip", "_EnableVFXColorAdjustment" })
                        if (material.HasProperty(name)) text.AppendLine(name + "=" + material.GetFloat(name).ToString("R", Invariant));
                    foreach (string name in new[] { "_BaseColor", "_SDFRimColor", "_HighlightMapVector" })
                        if (material.HasProperty(name)) text.AppendLine(name + "=" + material.GetVector(name).ToString("R"));
                    foreach (string name in new[] { "_BaseMap", "_BumpMap", "_SDFMask", "_SDFLightmap",
                        "_DiffRampMap", "_ShadowLutTex", "_EmotionMap", "_HighlightMap" })
                    {
                        if (!material.HasProperty(name)) continue;
                        var texture = material.GetTexture(name);
                        string path = AssetDatabase.GetAssetPath(texture);
                        var importer = AssetImporter.GetAtPath(path) as TextureImporter;
                        text.AppendLine(name + "=" + path + "; format=" + (texture != null ? texture.graphicsFormat.ToString() : "NULL")
                            + "; sRGB=" + (importer != null ? importer.sRGBTexture.ToString() : "n/a")
                            + "; scale=" + material.GetTextureScale(name).ToString("R")
                            + "; offset=" + material.GetTextureOffset(name).ToString("R"));
                    }
                }
            File.WriteAllText(Path.Combine(outputDirectory, "runtime-inputs.txt"), text.ToString());
        }

        static void SaveRenderTexture(RenderTexture source, string name)
        {
            var previous = RenderTexture.active;
            var readback = new Texture2D(source.width, source.height, TextureFormat.RGBAFloat, false, true);
            try
            {
                RenderTexture.active = source;
                readback.ReadPixels(new Rect(0, 0, source.width, source.height), 0, 0, false);
                readback.Apply(false, false);
                SavePixels(readback, name);
            }
            finally
            {
                RenderTexture.active = previous;
                UnityEngine.Object.DestroyImmediate(readback);
            }
        }

        static void SavePixels(Texture2D texture, string name)
        {
            using (var writer = new BinaryWriter(File.Create(Path.Combine(outputDirectory, name + ".rgba32f"))))
                foreach (Color c in texture.GetPixels())
                {
                    writer.Write(c.r); writer.Write(c.g); writer.Write(c.b); writer.Write(c.a);
                }
            File.WriteAllText(Path.Combine(outputDirectory, name + ".json"),
                "{\"width\":" + texture.width + ",\"height\":" + texture.height
                + ",\"encoding\":\"linear\",\"rowOrder\":\"Unity bottom-to-top\",\"storage\":\"little-endian RGBA float32\"}");
        }
    }
}
