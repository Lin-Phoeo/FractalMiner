using System;
using System.Globalization;
using System.IO;
using System.Security.Cryptography;
using System.Text;
using System.Text.RegularExpressions;
using UnityEditor;
using UnityEngine;

namespace EndfieldShaderPack
{
    // Synthetic boundary cases against actual PS2261 tables, not image fitting.
    public static class EndfieldShadowProducerSamplerValidation
    {
        const int Size = 4, AtlasWidth = 32, AtlasHeight = 16;
        const float Depth = 0.37f, Tolerance = 2e-4f;
        static readonly Vector2[] Centers = {
            // Binary-exact quarter-texel centers avoid ambiguous filter weights
            // under the API's >=8-bit subtexel precision requirement.
            new Vector2(.0078125f,.015625f), new Vector2(.9921875f,.015625f),
            new Vector2(.0078125f,.984375f), new Vector2(.9921875f,.984375f),
            new Vector2(.5078125f,.515625f), new Vector2(.2421875f,.484375f),
            new Vector2(.7578125f,.484375f), new Vector2(.4921875f,.765625f) };

        public static void RunBatch()
        {
            string reportPath = Environment.GetEnvironmentVariable("ENDFIELD_SHADOW_PRODUCER_REPORT");
            string sourcePath = Environment.GetEnvironmentVariable("ENDFIELD_SHADOW_PRODUCER_HLSL");
            if (!Application.isBatchMode || string.IsNullOrEmpty(reportPath) || !Path.IsPathRooted(reportPath)
                || File.Exists(reportPath) || string.IsNullOrEmpty(sourcePath))
                throw new InvalidOperationException("Batch + fresh absolute report + actual PS2261 required");
            var report = new StringBuilder("Synthetic production resolve atlas sampler gate\n");
            int failures = 0, tests = 0;
            RenderTexture previous = RenderTexture.active;
            var owned = new System.Collections.Generic.List<UnityEngine.Object>();
            var buffers = new System.Collections.Generic.List<ComputeBuffer>();
            try
            {
                if (SystemInfo.graphicsDeviceType != UnityEngine.Rendering.GraphicsDeviceType.Direct3D11)
                    throw new InvalidOperationException("This sampling reference requires D3D11");
                using (SHA256 sha = SHA256.Create())
                {
                    string actual = BitConverter.ToString(sha.ComputeHash(File.ReadAllBytes(sourcePath)))
                        .Replace("-", "").ToLowerInvariant();
                    if (actual != "f96c291b3839ec500bda03d1ba5b6d58c3b3d336232e23aded3eb7c8062bf9ad")
                        throw new InvalidDataException("Pinned actual PS2261 HLSL differs");
                    report.AppendLine("actual PS2261 hlsl sha256=" + actual);
                }
                string text = File.ReadAllText(sourcePath);
                Vector2[] poisson = ReadTable(text, "_247"), rotation = ReadTable(text, "_248");
                var shader = AssetDatabase.LoadAssetAtPath<ComputeShader>(
                    "Assets/EndfieldShaderPack/EndfieldCharacterShadowResolve.compute");
                if (shader == null) throw new InvalidOperationException("Production resolve missing");
                int kernel = shader.FindKernel("CSResolve");
                var atlas = new Texture2D(AtlasWidth, AtlasHeight, TextureFormat.R16, false, true);
                owned.Add(atlas);
                ushort[] raw = new ushort[AtlasWidth * AtlasHeight];
                for (int y = 0; y < AtlasHeight; y++) for (int x = 0; x < AtlasWidth; x++)
                    raw[y * AtlasWidth + x] = (ushort)(x == 0 ? 0 : x == AtlasWidth - 1 ? 65535
                        : ((x * 97 + y * 53) % 256) * 257);
                atlas.SetPixelData(raw, 0); atlas.Apply(false, false);
                // Deliberately conflicting texture wrap: inline sampler must own address mode.
                atlas.wrapMode = TextureWrapMode.Mirror;
                var index = Uniform(new Color(258f / 1023f, 0, 0, 0), owned);
                var normal = Uniform(new Color(.5f, .5f, 0, 0), owned);
                var depth = Uniform(new Color(.5f, 0, 0, 0), owned);
                var output = Target(RenderTextureFormat.RFloat, owned);
                var diag0 = Target(RenderTextureFormat.ARGBFloat, owned);
                var diag1 = Target(RenderTextureFormat.ARGBFloat, owned);
                var diag2 = Target(RenderTextureFormat.RFloat, owned);
                var matrix = Buffer(new Vector4[4], buffers);
                var bias = Buffer(new[] { Vector4.zero }, buffers);
                var light = Buffer(new[] { new Vector4(0,-1,0,0) }, buffers);
                var rect = Buffer(new[] { new Vector4(0,0,1,1) }, buffers);
                shader.SetTexture(kernel, "_AtlasTex", atlas); shader.SetTexture(kernel, "_GBuffer0", index);
                shader.SetTexture(kernel, "_GBuffer1", normal); shader.SetTexture(kernel, "_CameraDepth", depth);
                shader.SetTexture(kernel, "_OutG", output); shader.SetTexture(kernel, "_OutDiag0", diag0);
                shader.SetTexture(kernel, "_OutDiag1", diag1); shader.SetTexture(kernel, "_OutDiag2", diag2);
                shader.SetBuffer(kernel, "_CharacterWorldToShadow", matrix); shader.SetBuffer(kernel, "_CharacterShadowBiases", bias);
                shader.SetBuffer(kernel, "_CharacterShadowLightDir", light); shader.SetBuffer(kernel, "_CharacterShadowAtlasParams", rect);
                shader.SetVector("_CharacterShadowTexelSize", new Vector4(1f / AtlasWidth,1f / AtlasHeight,AtlasWidth,AtlasHeight));
                shader.SetVector("_CharacterShadowParams", new Vector4(1,1,1,0));
                shader.SetVector("_ScreenSize", new Vector4(Size,Size,1f / Size,1f / Size));
                shader.SetMatrix("_InvViewProj", Matrix4x4.identity); shader.SetMatrix("_ViewProj", Matrix4x4.identity);
                for (int profile = 0; profile < 3; profile++)
                {
                if (profile > 0)
                {
                    for (int i = 0; i < raw.Length; i++) raw[i] = profile == 1 ? (ushort)0 : (ushort)65535;
                    atlas.SetPixelData(raw, 0); atlas.Apply(false, false);
                }
                report.AppendLine("profile=" + profile + " (pattern / zero occluders / all occluders)");
                for (int flip = 0; flip <= 1; flip++) foreach (Vector2 center in Centers)
                {
                    matrix.SetData(new[] { Vector4.zero, Vector4.zero, Vector4.zero, new Vector4(center.x, center.y, Depth, 1) });
                    shader.SetInt("_CaptureFlipY", flip);
                    for (int mode = 0; mode <= 1; mode++)
                    {
                        shader.SetInt("_Mode", mode); shader.Dispatch(kernel,1,1,1);
                        Color[] g = Read(output), centerData = Read(diag0), counts = Read(diag2);
                        for (int y = 0; y < Size; y++) for (int x = 0; x < Size; x++)
                        {
                            int i = y * Size + x;
                            float expected, count = 0;
                            if (mode == 0)
                            {
                                Vector2 uv = Flip(center, flip);
                                float sample = Linear(raw, uv);
                                expected = sample >= Depth ? 1 : 0;
                                bool ok = Mathf.Abs(centerData[i].a - sample) <= Tolerance;
                                if (!ok) failures++;
                                tests++;
                                if (!ok) report.AppendLine("FAIL linear flip=" + flip + " uv=" + center + " pixel=" + i
                                    + " actual=" + centerData[i].a + " expected=" + sample);
                            }
                            else
                            {
                                Vector2 basis = rotation[x * 4 + (flip == 0 ? y : Size - 1 - y)];
                                float sum = 0;
                                foreach (Vector2 p in poisson)
                                {
                                    Vector2 delta = new Vector2(p.x * basis.x - p.y * basis.y, p.x * basis.y + p.y * basis.x);
                                    Vector2 uv = Flip(center + delta * (4f / AtlasWidth), flip);
                                    int loX = Mathf.FloorToInt(SnapTexel(uv.x * AtlasWidth - .5f));
                                    int loY = Mathf.FloorToInt(SnapTexel(uv.y * AtlasHeight - .5f));
                                    for (int dy = 0; dy <= 1; dy++) for (int dx = 0; dx <= 1; dx++)
                                    {
                                        float diff = Fetch(raw, loX + dx, loY + dy) - Depth;
                                        if (diff >= 0) { sum += diff; count++; }
                                    }
                                }
                                float spread = 2f * Mathf.Clamp01(count / 64f) - 1f;
                                float sign = spread > 0 ? 1 : spread < 0 ? -1 : 0;
                                float oneMinus = 1f - sign * spread;
                                // Target-backend zero-occluder observable boundary, not universal NaN law.
                                expected = count == 0 ? 1 : Mathf.Min(1, .5f - .5f *
                                    (1f - Mathf.Lerp(oneMinus * oneMinus * oneMinus, oneMinus,
                                        Mathf.Clamp01(sum / count / Depth))) * sign);
                                bool ok = counts[i].r == count;
                                if (!ok) failures++;
                                tests++;
                                if (!ok) report.AppendLine("FAIL gather-count flip=" + flip + " uv=" + center + " pixel=" + i
                                    + " actual=" + counts[i].r + " expected=" + count);
                            }
                            bool equal = !float.IsNaN(g[i].r) && Mathf.Abs(g[i].r - expected) <= Tolerance;
                            if (!equal) failures++;
                            tests++;
                            if (!equal) report.AppendLine("FAIL G mode=" + mode + " flip=" + flip + " uv=" + center + " pixel=" + i
                                + " actual=" + g[i].r + " expected=" + expected);
                        }
                    }
                }
                }
            }
            catch (Exception e) { failures++; report.AppendLine(e.ToString()); }
            finally
            {
                RenderTexture.active = previous;
                foreach (ComputeBuffer b in buffers) b.Release();
                foreach (UnityEngine.Object o in owned) UnityEngine.Object.DestroyImmediate(o);
            }
            report.AppendLine("checks=" + tests + " failures=" + failures + " tolerance=" + Tolerance);
            report.AppendLine(failures == 0 && tests == 3072 ? "PASS" : "FAIL");
            File.WriteAllText(reportPath, report.ToString());
            EditorApplication.Exit(failures == 0 && tests == 3072 ? 0 : 1);
        }

        static Vector2[] ReadTable(string source, string name)
        {
            Match m = Regex.Match(source, @"static const float2 " + name + @"\[16\] = \{(.*?)\};");
            MatchCollection values = Regex.Matches(m.Groups[1].Value, @"float2\(([^,]+),\s*([^\)]+)\)");
            if (!m.Success || values.Count != 16) throw new InvalidOperationException("Actual table missing: " + name);
            var result = new Vector2[16];
            for (int i = 0; i < 16; i++) result[i] = new Vector2(
                float.Parse(values[i].Groups[1].Value.TrimEnd('f'), CultureInfo.InvariantCulture),
                float.Parse(values[i].Groups[2].Value.TrimEnd('f'), CultureInfo.InvariantCulture));
            return result;
        }
        static Vector2 Flip(Vector2 uv, int flip) => flip == 0 ? uv : new Vector2(uv.x, 1 - uv.y);
        static float Fetch(ushort[] data, int x, int y) => data[Mathf.Clamp(y,0,AtlasHeight - 1) * AtlasWidth
            + Mathf.Clamp(x,0,AtlasWidth - 1)] / 65535f;
        static float Linear(ushort[] data, Vector2 uv)
        {
            float x = SnapTexel(uv.x * AtlasWidth - .5f), y = SnapTexel(uv.y * AtlasHeight - .5f);
            int ix = Mathf.FloorToInt(x), iy = Mathf.FloorToInt(y);
            return Mathf.Lerp(Mathf.Lerp(Fetch(data,ix,iy),Fetch(data,ix+1,iy),x-ix),
                Mathf.Lerp(Fetch(data,ix,iy+1),Fetch(data,ix+1,iy+1),x-ix),y-iy);
        }
        // D3D11.3 functional spec 7.18.5 / 7.18.16.1: texture address conversion
        // requires >=8 fractional bits. CPU ideal continuous filtering is not this
        // device's 8-bit implementation; binary-exact centers constrain weights.
        // This fixture certifies the tested D3D11 backend, not all Vulkan devices.
        static float SnapTexel(float texel) => Mathf.Round(texel * 256f) / 256f;
        static ComputeBuffer Buffer(Vector4[] data, System.Collections.Generic.List<ComputeBuffer> owned)
        { var b = new ComputeBuffer(data.Length,16); owned.Add(b); b.SetData(data); return b; }
        static Texture2D Uniform(Color value, System.Collections.Generic.List<UnityEngine.Object> owned)
        {
            var t = new Texture2D(Size,Size,TextureFormat.RGBAFloat,false,true); owned.Add(t);
            var pixels = new Color[Size*Size]; for (int i=0;i<pixels.Length;i++) pixels[i]=value;
            t.SetPixels(pixels); t.Apply(); return t;
        }
        static RenderTexture Target(RenderTextureFormat format, System.Collections.Generic.List<UnityEngine.Object> owned)
        { var t = new RenderTexture(Size,Size,0,format,RenderTextureReadWrite.Linear) { enableRandomWrite=true }; owned.Add(t); t.Create(); return t; }
        static Color[] Read(RenderTexture target)
        {
            RenderTexture previous = RenderTexture.active;
            var t = new Texture2D(Size,Size,TextureFormat.RGBAFloat,false,true);
            try { RenderTexture.active=target; t.ReadPixels(new Rect(0,0,Size,Size),0,0); t.Apply(); return t.GetPixels(); }
            finally { RenderTexture.active=previous; UnityEngine.Object.DestroyImmediate(t); }
        }
    }
}
