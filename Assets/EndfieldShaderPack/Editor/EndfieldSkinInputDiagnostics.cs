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
            var boneMatrices = new System.Collections.Generic.List<object>();
            foreach (var bone in root.GetComponentsInChildren<Transform>())
            {
                Matrix4x4 matrix = bone.localToWorldMatrix;
                boneMatrices.Add(new { name = bone.name, rows = new[] {
                    new[] { matrix.m00, matrix.m01, matrix.m02, matrix.m03 },
                    new[] { matrix.m10, matrix.m11, matrix.m12, matrix.m13 },
                    new[] { matrix.m20, matrix.m21, matrix.m22, matrix.m23 },
                } });
            }
            File.WriteAllText(Path.Combine(outputDirectory, "bone-world-matrices.json"),
                Newtonsoft.Json.JsonConvert.SerializeObject(boneMatrices, Newtonsoft.Json.Formatting.Indented));
            var skinWorld = new System.Collections.Generic.List<object>();
            foreach (var renderer in root.GetComponentsInChildren<SkinnedMeshRenderer>())
            {
                if (!renderer.name.EndsWith("_face_01_lod0", StringComparison.Ordinal)
                    && !renderer.name.EndsWith("_body_01_lod0", StringComparison.Ordinal)
                    && !renderer.name.EndsWith("_iris_01_lod0", StringComparison.Ordinal)
                    && !renderer.name.EndsWith("_hair_01_lod0", StringComparison.Ordinal)) continue;
                var baked = new Mesh();
                try
                {
                    renderer.BakeMesh(baked);
                    var points = new System.Collections.Generic.List<float[]>();
                    foreach (Vector3 point in baked.vertices)
                    {
                        Vector3 world = renderer.localToWorldMatrix.MultiplyPoint3x4(point);
                        points.Add(new[] { world.x, world.y, world.z });
                    }
                    skinWorld.Add(new { name = renderer.name, vertices = points });
                }
                finally { UnityEngine.Object.DestroyImmediate(baked); }
            }
            File.WriteAllText(Path.Combine(outputDirectory, "skin-world-vertices.json"),
                Newtonsoft.Json.JsonConvert.SerializeObject(skinWorld));
            var text = new StringBuilder();
            text.AppendLine("utc=" + DateTime.UtcNow.ToString("O"));
            text.AppendLine("officialSource=" + AssetDatabase.GetAssetPath(official));
            text.AppendLine("colorSpace=" + QualitySettings.activeColorSpace);
            text.AppendLine("cameraToWorld=" + camera.cameraToWorldMatrix.ToString("R"));
            text.AppendLine("shadowSkipReason=" + EndfieldCharacterShadowFeature.LastSkipReason);
            text.AppendLine("shadowGate=" + Shader.GetGlobalFloat("_EndfieldCharacterSelfShadow"));
            foreach (string name in new[] { "_EndfieldOfficialFrameEnabled", "_EndfieldOfficialShadingEnabled",
                "_EndfieldCapturedLightIntensity" })
                text.AppendLine(name + "=" + Shader.GetGlobalFloat(name).ToString("R", Invariant));
            for (int i = 0; i < 16; i++)
                text.AppendLine("_CharacterParams" + i + "=" + Shader.GetGlobalVector("_CharacterParams" + i).ToString("R"));
            foreach (string name in new[] { "_EnvironmentGlobalParams0", "_ExposureWithMiscParams",
                "_CharacterLightDir", "_CharacterLightColor", "_CharacterAmbient" })
                text.AppendLine(name + "=" + Shader.GetGlobalVector(name).ToString("R"));
            foreach (var renderer in root.GetComponentsInChildren<SkinnedMeshRenderer>())
                for (int slot = 0; slot < renderer.sharedMaterials.Length; slot++)
                {
                    var material = renderer.sharedMaterials[slot];
                    if (material == null || !material.HasProperty("_MaterialFamily")) continue;
                    float family = material.GetFloat("_MaterialFamily");
                    if (family <= .5f || family > 3.5f) continue;
                    text.AppendLine("\nrenderer=" + renderer.name + "; slot=" + slot + "; material=" + AssetDatabase.GetAssetPath(material));
                    text.AppendLine("shader=" + material.shader.name + "; enabled=" + renderer.enabled
                        + "; propertyBlock=" + renderer.HasPropertyBlock());
                    text.AppendLine("objectToWorld=" + renderer.localToWorldMatrix.ToString("R"));
                    text.AppendLine("rootBone=" + (renderer.rootBone != null ? renderer.rootBone.name : "NULL"));
                    var propertyBlock = new MaterialPropertyBlock();
                    renderer.GetPropertyBlock(propertyBlock, slot);
                    text.AppendLine("propertyBlock.skinBasisEnabled=" + propertyBlock.GetFloat("_EndfieldSkinBasisEnabled"));
                    for (int row = 0; row < 3; row++) text.AppendLine("propertyBlock.skinBasisRow" + row + "="
                        + propertyBlock.GetVector("_EndfieldSkinBasisRow" + row).ToString("R"));
                    text.AppendLine("propertyBlock.shadowIndex=" + propertyBlock.GetVector(CharacterShadowPass.IndexEncodeName).ToString("R"));
                    text.AppendLine("propertyBlock.shadowClip=" + propertyBlock.GetMatrix(CharacterShadowPass.AtlasClipMatrixName).ToString("R"));
                    bool sourceShading = Shader.GetGlobalFloat("_EndfieldOfficialFrameEnabled") > .5f
                        && Shader.GetGlobalFloat("_EndfieldOfficialShadingEnabled") > .5f
                        && Shader.GetGlobalVector("_CharacterParams1").y >= .5f
                        && material.GetFloat("_SurfaceType") < .5f && material.GetFloat("_DebugView") < .5f
                        && (material.GetFloat("_UseParallax") < .5f || family > 2.5f);
                    text.AppendLine("sourceShading=" + sourceShading + " (material/global gate; property blocks reported separately)");
                    foreach (string name in new[] { "_MaterialFamily", "_SurfaceType", "_DebugView", "_UseParallax",
                        "_UseBumpMap", "_BumpScale", "_UseSDFLightmap", "_UseDiffRampMap", "_UseShadowLutTex",
                        "_UseEmotionMap", "_EmotionIndex", "_EmotionBlend", "_SkinRimOffScale", "_FaceRimOffScale",
                        "_Smoothness", "_Metallic", "_Specular", "_BackFaceNormalFlip", "_EnableVFXColorAdjustment",
                        "_ParallaxScale", "_MatcapNormalScale", "_Anisotropy" })
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
