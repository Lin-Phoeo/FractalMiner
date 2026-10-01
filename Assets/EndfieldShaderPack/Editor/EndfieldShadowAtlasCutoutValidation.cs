using System;
using System.Collections.Generic;
using System.IO;
using UnityEditor;
using UnityEditor.SceneManagement;
using UnityEngine;
using UnityEngine.Rendering;
using UnityEngine.SceneManagement;
using Object = UnityEngine.Object;

namespace EndfieldShaderPack
{
    // Tests the actual production atlas pass against PS9065's alpha expression.
    // Synthetic mip/alpha inputs only; not a certificate for atlas depth/packing.
    public static class EndfieldShadowAtlasCutoutValidation
    {
        const int Size = 16;
        const float Tolerance = 2e-4f;
        const string SourceHash = "8fc35f32117da406580c7e2bd01af2a11ae235304a5c1f14e0c5c946bcd747fe";

        static void Require(bool value, string reason)
        {
            if (!value) throw new InvalidDataException(reason);
        }

        public static void RunBatch()
        {
            string output = Environment.GetEnvironmentVariable("ENDFIELD_SHADOW_ATLAS_CUTOUT_REPORT");
            string source = Environment.GetEnvironmentVariable("ENDFIELD_SHADOW_ATLAS_CUTOUT_HLSL");
            Require(Application.isBatchMode && !string.IsNullOrEmpty(output) && Path.IsPathRooted(output)
                && !File.Exists(output) && !string.IsNullOrEmpty(source), "fresh batch/report + actual PS9065 required");
            Require(EndfieldCapturedClothNormals.Hash(File.ReadAllBytes(source)) == SourceHash, "Actual PS9065 HLSL changed");
            Require(SystemInfo.graphicsDeviceType == GraphicsDeviceType.Direct3D11
                && QualitySettings.activeColorSpace == ColorSpace.Linear, "Reviewed D3D11/Linear required");
            var lines = new List<string> { "Production atlas alpha gate; actual PS9065 SHA256=" + SourceHash,
                "GPU=" + SystemInfo.graphicsDeviceName, "tolerance=" + Tolerance };
            var owned = new List<Object>();
            Scene preview = default;
            RenderTexture previous = RenderTexture.active;
            string[] names = { "_EndfieldOfficialFrameEnabled", "_EndfieldOfficialShadingEnabled", "_EndfieldCapturedGlobalMipBias" };
            float[] saved = Array.ConvertAll(names, Shader.GetGlobalFloat);
            int cases = 0, failed = 0;
            try
            {
                preview = EditorSceneManager.NewPreviewScene();
                var go = new GameObject("AtlasCutoutWarmup"); owned.Add(go);
                SceneManager.MoveGameObjectToScene(go, preview);
                var target = new RenderTexture(Size, Size, 16, RenderTextureFormat.R16, RenderTextureReadWrite.Linear);
                owned.Add(target); target.Create();
                var reader = new Texture2D(Size, Size, TextureFormat.RGBAFloat, false, true); owned.Add(reader);
                var camera = go.AddComponent<Camera>(); camera.enabled = false; camera.targetTexture = target; camera.scene = preview;
                camera.Render(); Require(RenderPipelineManager.currentPipeline != null, "URP warmup failed");
                var material = new Material(Shader.Find("Endfield/CharacterLit")); owned.Add(material);
                // A real camera render populates the SRP pass metadata lazily.
                var warm = GameObject.CreatePrimitive(PrimitiveType.Quad); owned.Add(warm);
                SceneManager.MoveGameObjectToScene(warm, preview);
                warm.GetComponent<Renderer>().sharedMaterial = material;
                camera.transform.position = new Vector3(0, 0, -2); camera.Render();
                int pass = material.FindPass(CharacterShadowPass.AtlasPassName);
                Require(pass >= 0, "Production atlas pass metadata unavailable");
                lines.Add("Production atlas pass index=" + pass);
                var mesh = new Mesh(); owned.Add(mesh);
                mesh.vertices = new[] { new Vector3(-1,-1,.5f), new Vector3(1,-1,.5f),
                    new Vector3(1,1,.5f), new Vector3(-1,1,.5f) };
                mesh.normals = new[] { Vector3.forward, Vector3.forward, Vector3.forward, Vector3.forward };
                mesh.uv = new[] { Vector2.zero, Vector2.right, Vector2.one, Vector2.up };
                mesh.triangles = new[] { 0,1,2,0,2,3 };
                var block = new MaterialPropertyBlock(); block.SetMatrix(CharacterShadowPass.AtlasClipMatrixName, Matrix4x4.identity);
                Shader.SetGlobalFloat(names[0], 1); Shader.SetGlobalFloat(names[1], 1);
                material.SetFloat("_EnableAlphaTest", 1);
                var texture = new Texture2D(64, 64, TextureFormat.RGBAFloat, true, true)
                    { filterMode = FilterMode.Bilinear, wrapMode = TextureWrapMode.Repeat };
                owned.Add(texture); material.SetTexture("_BaseMap", texture);
                Action<string, float> check = (name, expected) =>
                {
                    cases++;
                    float actual = Draw(mesh, material, pass, block, target, reader);
                    bool ok = float.IsFinite(actual) && Mathf.Abs(actual - expected) <= Tolerance;
                    if (!ok) failed++;
                    lines.Add((ok ? "PASS " : "FAIL ") + name + " expected=" + expected + " actual=" + actual);
                };
                // Texture alpha x material alpha; equality is kept, not discarded.
                foreach (float alpha in new[] { .25f, .75f })
                {
                    Fill(texture, new[] { alpha, alpha, alpha, alpha, alpha, alpha, alpha });
                    foreach (float scale in new[] { 0f, .5f, 1f }) foreach (float cutoff in new[] { 0f, .25f, .5f })
                    {
                        material.SetColor("_BaseColor", new Color(1, 1, 1, scale));
                        material.SetFloat("_AlphaClipThreshold", cutoff);
                        check("alpha=" + alpha + " scale=" + scale + " cutoff=" + cutoff,
                            alpha * scale < cutoff ? 0 : .5f);
                    }
                }
                // 64px texture / 16px full-screen quad => implicit LOD2, bias then changes mip.
                float[] levels = { .85f, .25f, .75f, .15f, .95f, .35f, .55f };
                Fill(texture, levels); material.SetColor("_BaseColor", Color.white);
                material.SetFloat("_AlphaClipThreshold", .5f);
                foreach (int bias in new[] { -2, -1, 0, 1 })
                {
                    Shader.SetGlobalFloat(names[2], bias);
                    check("actual SampleBias expression bias=" + bias, levels[2 + bias] < .5f ? 0 : .5f);
                }
                Shader.SetGlobalFloat(names[2], -1);
                material.SetTextureScale("_BaseMap", new Vector2(2, 2));
                check("BaseST applied once before alpha sampling", .5f);
                material.SetTextureScale("_BaseMap", Vector2.one);
                Fill(texture, new[] { .75f, .75f, .75f, .75f, .75f, .75f, .75f });
                material.SetColor("_BaseColor", new Color(1, 1, 1, 0));
                Shader.SetGlobalFloat(names[0], 0);
                check("legacy alpha behavior preserved", .5f);
                Shader.SetGlobalFloat(names[0], 1); material.SetFloat("_EnableAlphaTest", 0);
                check("opaque variant ignores alpha", .5f);
                material.SetFloat("_EnableAlphaTest", 1); Shader.SetGlobalFloat(names[1], 0);
                check("source shading disabled preserves legacy", .5f);
            }
            finally
            {
                for (int i = 0; i < names.Length; i++) Shader.SetGlobalFloat(names[i], saved[i]);
                RenderTexture.active = previous;
                for (int i = owned.Count - 1; i >= 0; i--)
                    if (owned[i] != null) { if (owned[i] is RenderTexture rt) rt.Release(); Object.DestroyImmediate(owned[i]); }
                if (preview.IsValid()) EditorSceneManager.ClosePreviewScene(preview);
            }
            lines.Add("RESULT " + (failed == 0 ? "PASS" : "FAIL") + " cases=" + cases + " failures=" + failed
                + "; alpha expression only; no depth-bias/packing/stencil/dither certificate");
            using (var stream = new FileStream(output, FileMode.CreateNew, FileAccess.Write))
            using (var writer = new StreamWriter(stream)) foreach (string line in lines) writer.WriteLine(line);
            EditorApplication.Exit(failed == 0 ? 0 : 1);
        }

        static void Fill(Texture2D texture, float[] levels)
        {
            for (int mip = 0; mip < texture.mipmapCount; mip++)
            {
                int width = Mathf.Max(1, texture.width >> mip);
                var pixels = new Color[width * width];
                for (int i = 0; i < pixels.Length; i++) pixels[i] = new Color(1, 1, 1, levels[mip]);
                texture.SetPixels(pixels, mip);
            }
            texture.Apply(false, false);
        }

        static float Draw(Mesh mesh, Material material, int pass, MaterialPropertyBlock block,
            RenderTexture target, Texture2D reader)
        {
            var command = new CommandBuffer { name = "Production atlas cutout expression" };
            try
            {
                command.SetRenderTarget(target);
                command.SetViewport(new Rect(0, 0, Size, Size));
                command.ClearRenderTarget(RTClearFlags.All, Color.clear, 1f, 0);
                command.DrawMesh(mesh, Matrix4x4.identity, material, 0, pass, block);
                Graphics.ExecuteCommandBuffer(command);
                RenderTexture.active = target;
                reader.ReadPixels(new Rect(0, 0, Size, Size), 0, 0); reader.Apply();
                return reader.GetPixel(Size / 2, Size / 2).r;
            }
            finally { command.Release(); }
        }
    }
}
