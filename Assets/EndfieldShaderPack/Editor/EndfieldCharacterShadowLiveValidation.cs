using System;
using System.Globalization;
using System.IO;
using System.Text;
using UnityEditor;
using UnityEditor.SceneManagement;
using UnityEngine;
using UnityEngine.Rendering;

namespace EndfieldShaderPack
{
    /// Gates the live forward-renderer character shadow chain end to end: build the
    /// generated renderer, activate the captured pipeline, render one frame and read
    /// back what the passes actually wrote. The fixed-capture gate proves the resolve
    /// arithmetic; this one proves the runtime plumbing around it -- formats, atlas
    /// orientation, the reversed-Z depth test keeping the nearest caster, and that the
    /// G channel reaches EndfieldCharacterLit at all.
    ///
    /// The atlas row convention here is the opposite of the captured gate's: a runtime
    /// atlas has no importer flip, WorldToShadowClip negates y instead, and Unity's
    /// sampler addresses memory row v*(H-1), so the CPU lookup uses row = v*(H-1).
    public static class EndfieldCharacterShadowLiveValidation
    {
        const string ReportPath = "Logs/character-shadow-live.txt";
        const int Width = 1000;
        const int Height = 1000;

        // The captured full-body frame fills 195042 of the 1024x1024 cell; the atlas is
        // in light space so the camera framing cannot change that much, while a wrong
        // matrix or a failed caster pass collapses it to zero or fills the cell.
        const int MinAtlasTexels = 50000;
        const int MaxAtlasTexels = 600000;
        const float MinAtlasMax = 0.05f;
        const float MinInsideBoxFraction = 0.999f;
        const float MinAtlasPresence = 0.99f;
        // Same bound as the captured gate: R16 quantisation is 1.5e-5, so a correct
        // round trip through the runtime atlas leaves the median at quantisation scale.
        const float MaxMedianSignedError = 2e-4f;
        const float MinShadowFraction = 0.01f;
        const float MaxShadowFraction = 0.60f;
        // With the gate off the character is uniformly lit; the captured frame's shadow
        // covers about a third of the character, so the two renders must differ visibly.
        const float MinAbDifference = 0.005f;
        const int ShadowByteLimit = 253;

        [MenuItem("Endfield/Validate Live Character Shadow", false, 73)]
        public static void RunAll()
        {
            var report = new StringBuilder();
            int failures = 0;
            report.AppendLine("Endfield live character self-shadow gate (forward renderer, runtime atlas)");
            report.AppendLine("utc: " + DateTime.UtcNow.ToString("o", CultureInfo.InvariantCulture));
            report.AppendLine("thresholds: atlasTexels in [" + MinAtlasTexels + "," + MaxAtlasTexels +
                              "], atlasMax>=" + MinAtlasMax +
                              ", insideBox>=" + MinInsideBoxFraction +
                              ", presence>=" + MinAtlasPresence +
                              ", medianSignedErr<=" + MaxMedianSignedError +
                              ", shadowFraction in [" + MinShadowFraction + "," + MaxShadowFraction +
                              "], A/B difference>=" + MinAbDifference);
            report.AppendLine();

            if (EndfieldCapturedPipelineActivation.IsActivated)
                throw new InvalidOperationException("An activation is already in progress; restore it first.");

            try
            {
                EndfieldCapturedSceneBuilder.Build();
                EndfieldCapturedPipelineActivation.Activate();
                try
                {
                EditorSceneManager.OpenScene(EndfieldCapturedSceneBuilder.ScenePath, OpenSceneMode.Single);
                var camera = Camera.main;
                if (camera == null) throw new InvalidOperationException("Generated scene has no main camera.");
                var caster = UnityEngine.Object.FindObjectOfType<EndfieldCharacterShadowCaster>();
                if (caster == null) throw new InvalidOperationException("Generated scene has no shadow caster.");
                var light = UnityEngine.Object.FindObjectOfType<Endfield.EndfieldCharacterLight>();
                if (light == null) throw new InvalidOperationException("Generated scene has no character light.");
                report.AppendLine("pre-render: registryBeforeRefresh=" + EndfieldCharacterShadowCaster.Active.Count +
                                  " afterRefresh=" + EndfieldCharacterShadowCaster.Refresh().Count +
                                  " found=" + (caster != null) + " enabled=" + caster.enabled +
                                  " activeInHierarchy=" + caster.gameObject.activeInHierarchy +
                                  " scene=" + caster.gameObject.scene.name +
                                  " skipReason='" + EndfieldCharacterShadowFeature.LastSkipReason +
                                  "' pipeline=" + (GraphicsSettings.currentRenderPipeline != null
                                      ? GraphicsSettings.currentRenderPipeline.name : "none"));

                // An empty atlas and an empty index buffer have exactly two possible
                // causes: the pass lookup misses on every material, or the draws run and
                // write nothing. This probe separates them before any GPU evidence.
                var probe = new StringBuilder("pass probe:");
                bool shaderMessagesDumped = false;
                foreach (var renderer in caster.Casters)
                {
                    probe.AppendLine();
                    probe.Append("    ").Append(renderer.name).Append(' ').Append(renderer.GetType().Name)
                        .Append(" enabled=").Append(renderer.enabled)
                        .Append(" mats=").Append(renderer.sharedMaterials.Length);
                    foreach (var material in renderer.sharedMaterials)
                    {
                        if (material == null) { probe.Append(" | [null]"); continue; }
                        probe.Append(" | ").Append(material.shader.name)
                            .Append(" passes=").Append(material.passCount)
                            .Append(" atlas=").Append(material.FindPass(CharacterShadowPass.AtlasPassName))
                            .Append(" gbuf=").Append(material.FindPass(CharacterShadowPass.GBufferPassName))
                            .Append(" fwd=").Append(material.FindPass("UniversalForward"));
                        probe.Append(" matPath=").Append(AssetDatabase.GetAssetPath(material))
                            .Append(" shaderPath=").Append(AssetDatabase.GetAssetPath(material.shader))
                            .Append(" supported=").Append(material.shader.isSupported)
                            .Append(" foundEq=").Append(Shader.Find("Endfield/CharacterLit") == material.shader);
                        if (!shaderMessagesDumped)
                        {
                            shaderMessagesDumped = true;
                            var messages = ShaderUtil.GetShaderMessages(material.shader);
                            probe.Append(" shaderMsgs=").Append(messages.Length);
                            foreach (var message in messages)
                                probe.AppendLine().Append("        [").Append(message.severity).Append("] ")
                                    .Append(message.message).Append(" @").Append(message.file)
                                    .Append(':').Append(message.line);
                        }
                    }
                }
                report.AppendLine(probe.ToString());

                // Control: if name lookup also misses on a stock URP shader whose passes
                // demonstrably render, the miss is an environment property of
                // Material.FindPass, not a defect of EndfieldCharacterLit.
                var control = new Material(Shader.Find("Universal Render Pipeline/Lit"));
                report.AppendLine("control URP/Lit passes=" + control.passCount +
                                  " forwardLit=" + control.FindPass("ForwardLit") +
                                  " shadowCaster=" + control.FindPass("ShadowCaster") +
                                  " depthOnly=" + control.FindPass("DepthOnly"));
                UnityEngine.Object.DestroyImmediate(control);

                Color[] withShadow = RenderAndCapture(camera, "live-shadow-on.png");
                var atlas = ReadBack(CharacterShadowPass.LastAtlas);
                var index = ReadBack(CharacterShadowPass.LastIndex);
                var normal = ReadBack(CharacterShadowPass.LastNormal);
                var depth = ReadBack(CharacterShadowPass.LastDepth);
                var resolved = ReadBack(CharacterShadowPass.LastResolved);
                int atlasWidth = CharacterShadowPass.LastAtlas.width;
                int atlasHeight = CharacterShadowPass.LastAtlas.height;
                report.AppendLine("atlas " + atlasWidth + "x" + atlasHeight +
                                  " screen " + Width + "x" + Height +
                                  " slots=" + CharacterShadowPass.LastSlots);

                caster.enabled = false;
                Shader.SetGlobalFloat(CharacterShadowPass.SelfShadowGateName, 0f);
                Color[] withoutShadow = RenderAndCapture(camera, "live-shadow-off.png");
                caster.enabled = true;

                Check(report, ref failures, "runtime atlas holds a plausible character silhouette", () =>
                {
                    int nonZero = 0; ushort max = 0;
                    for (int i = 0; i < atlasWidth * atlasHeight; i++)
                    {
                        ushort value = (ushort)(atlas[i * 2] | (atlas[i * 2 + 1] << 8));
                        if (value == 0) continue;
                        nonZero++;
                        if (value > max) max = value;
                    }
                    report.AppendLine("    atlas nonZero=" + nonZero + " (" +
                                      (100.0 * nonZero / (atlasWidth * atlasHeight)).ToString("F2", CultureInfo.InvariantCulture) +
                                      "% of the cell) max=" + (max / 65535.0).ToString("F6", CultureInfo.InvariantCulture));
                    Require(nonZero >= MinAtlasTexels && nonZero <= MaxAtlasTexels,
                        "the runtime atlas holds " + nonZero + " texels; the captured full-body frame holds 195042," +
                        " so this is either a failed caster pass or a box that does not fit the character.");
                    Require(max / 65535f >= MinAtlasMax,
                        "atlas maximum depth is " + (max / 65535.0) + "; a reversed-Z atlas whose nearest caster" +
                        " sits near the light must reach well above " + MinAtlasMax + ".");
                });

                var statistics = new LiveStatistics();
                Check(report, ref failures, "runtime index, depth and atlas agree in light space", () =>
                {
                    Matrix4x4 invViewProj = CharacterShadowPass.LastViewProj.inverse;
                    Vector3 toward = EndfieldCharacterShadowProjection.TowardLight(-light.transform.forward);
                    var errors = new System.Collections.Generic.List<float>();
                    for (int row = 0; row < Height; row++)
                    {
                        for (int col = 0; col < Width; col++)
                        {
                            int pixel = row * Width + col;
                            uint pack = (uint)(index[pixel * 4] | (index[pixel * 4 + 1] << 8) |
                                               (index[pixel * 4 + 2] << 16) | (index[pixel * 4 + 3] << 24));
                            float indexF = Mathf.Log(pack, 2f) - 8f;
                            if (!(indexF >= 0f && indexF < CharacterShadowPass.LastSlots)) continue;
                            statistics.characterPixels++;
                            float deviceDepth = BitConverter.ToSingle(depth, pixel * 4);
                            var ndc = new Vector2((col + 0.5f) / Width * 2f - 1f, 1f - (row + 0.5f) / Height * 2f);
                            Vector4 clip = invViewProj * new Vector4(ndc.x, ndc.y, deviceDepth, 1f);
                            Vector3 world = new Vector3(clip.x, clip.y, clip.z) / clip.w;
                            Vector3 lightSpace = CharacterShadowPass.LastWorldToShadow.MultiplyPoint3x4(world);
                            bool inside = lightSpace.x >= 0f && lightSpace.x <= 1f &&
                                          lightSpace.y >= 0f && lightSpace.y <= 1f &&
                                          lightSpace.z >= 0f && lightSpace.z <= 1f;
                            if (inside) statistics.insideBox++;
                            uint normalRaw = (uint)(normal[pixel * 4] | (normal[pixel * 4 + 1] << 8) |
                                                    (normal[pixel * 4 + 2] << 16) | (normal[pixel * 4 + 3] << 24));
                            var encoded = new Vector2(
                                (normalRaw & 1023u) / 1023f * 2f - 1f,
                                ((normalRaw >> 10) & 1023u) / 1023f * 2f - 1f);
                            bool facesLight = Vector3.Dot(
                                EndfieldCharacterShadowProjectionValidation.DecodeNormalOctahedralY(encoded), toward) >= 0.5f;
                            if (!facesLight || !inside) continue;
                            int atlasCol = Mathf.Clamp(Mathf.RoundToInt(lightSpace.x * (atlasWidth - 1)), 0, atlasWidth - 1);
                            int atlasRow = Mathf.Clamp(Mathf.RoundToInt(lightSpace.y * (atlasHeight - 1)), 0, atlasHeight - 1);
                            int atlasPixel = atlasRow * atlasWidth + atlasCol;
                            ushort storedRaw = (ushort)(atlas[atlasPixel * 2] | (atlas[atlasPixel * 2 + 1] << 8));
                            if (storedRaw != 0) statistics.present++;
                            errors.Add(storedRaw / 65535f - lightSpace.z);
                            float g = BitConverter.ToSingle(resolved, pixel * 8 + 4);
                            if (Mathf.RoundToInt(Mathf.Clamp01(g) * 255f) < ShadowByteLimit) statistics.shadowed++;
                        }
                    }
                    errors.Sort();
                    statistics.median = errors.Count == 0 ? float.NaN : errors[errors.Count / 2];
                    report.AppendLine("    character pixels=" + statistics.characterPixels +
                                      " insideBox=" + Fraction(statistics.insideBox, statistics.characterPixels) +
                                      " frontFacingWithCaster=" + errors.Count);
                    report.AppendLine("    median signed atlas error=" +
                                      statistics.median.ToString("E4", CultureInfo.InvariantCulture) +
                                      " shadowFraction=" +
                                      Fraction(statistics.shadowed, statistics.characterPixels).ToString("F4", CultureInfo.InvariantCulture));
                    Require(statistics.characterPixels > 10000,
                        "only " + statistics.characterPixels + " pixels carry a character index; the prepass did not run.");
                    Require(Fraction(statistics.insideBox, statistics.characterPixels) >= MinInsideBoxFraction,
                        "the reconstructed surface falls outside its own light box more than " +
                        (1f - MinInsideBoxFraction) + " of the time; the runtime matrix and the rasterised atlas disagree.");
                    Require(Fraction(statistics.present, errors.Count) >= MinAtlasPresence,
                        "the atlas is empty at " + (1f - Fraction(statistics.present, errors.Count)) +
                        " of the character's own texels; the atlas orientation or cell mapping is wrong.");
                    Require(Mathf.Abs(statistics.median) <= MaxMedianSignedError,
                        "median signed atlas error is " + statistics.median + "; the runtime atlas does not store" +
                        " the depth its own matrix predicts (orientation or reversed-Z test wrong).");
                    float shadowFraction = Fraction(statistics.shadowed, statistics.characterPixels);
                    Require(shadowFraction >= MinShadowFraction && shadowFraction <= MaxShadowFraction,
                        "the resolved G channel shadows " + shadowFraction + " of the character; the captured" +
                        " frame shadows about a third, so this is either a dead or an all-shadow resolve.");
                });

                Check(report, ref failures, "the G channel visibly reaches the character shader", () =>
                {
                    int different = 0;
                    for (int i = 0; i < withShadow.Length; i++)
                    {
                        float delta = Mathf.Max(Mathf.Abs(withShadow[i].r - withoutShadow[i].r),
                            Mathf.Max(Mathf.Abs(withShadow[i].g - withoutShadow[i].g),
                                      Mathf.Abs(withShadow[i].b - withoutShadow[i].b)));
                        if (delta > 8f / 255f) different++;
                    }
                    float fraction = (float)different / withShadow.Length;
                    report.AppendLine("    pixels differing by more than 8/255 between gate on/off: " +
                                      different + " (" + fraction.ToString("F4", CultureInfo.InvariantCulture) + ")");
                    report.AppendLine("    wrote Validation/live-shadow-on.png and live-shadow-off.png");
                    Require(fraction >= MinAbDifference,
                        "switching the self-shadow gate changed only " + fraction +
                        " of the frame; the resolved G channel is not reaching EndfieldCharacterLit.");
                });
            }
            finally
            {
                EndfieldCapturedPipelineActivation.Restore();
            }
            }
            catch (Exception exception)
            {
                failures++;
                report.AppendLine("FAIL  harness aborted before the report: " + exception.Message);
                report.AppendLine("      skipReason='" + EndfieldCharacterShadowFeature.LastSkipReason + "'");
            }

            report.AppendLine();
            report.AppendLine(failures == 0
                ? "PASS: the live forward chain renders the official character self-shadow."
                : "FAIL: " + failures + " live character shadow check(s) failed.");
            Directory.CreateDirectory("Logs");
            File.WriteAllText(ReportPath, report.ToString());
            Debug.Log(report.ToString());
            if (failures != 0)
                throw new InvalidOperationException(failures + " live character shadow check(s) failed; see " + ReportPath);
        }

        sealed class LiveStatistics
        {
            public int characterPixels;
            public int insideBox;
            public int present;
            public int shadowed;
            public float median;
        }

        static float Fraction(int part, int total)
        {
            return total == 0 ? 0f : (float)part / total;
        }

        static void Require(bool condition, string message)
        {
            if (!condition) throw new InvalidOperationException(message);
        }

        static void Check(StringBuilder report, ref int failures, string name, Action body)
        {
            try
            {
                body();
                report.AppendLine("PASS  " + name);
            }
            catch (Exception exception)
            {
                failures++;
                report.AppendLine("FAIL  " + name);
                report.AppendLine("      " + exception.Message);
            }
        }

        static byte[] ReadBack(RenderTexture texture)
        {
            if (texture == null) throw new InvalidOperationException("The shadow pass produced no target to read back.");
            var request = AsyncGPUReadback.Request(texture);
            request.WaitForCompletion();
            if (request.hasError) throw new InvalidOperationException("GPU readback failed for " + texture.name);
            var data = request.GetData<byte>();
            var bytes = new byte[data.Length];
            data.CopyTo(bytes);
            return bytes;
        }

        static Color[] RenderAndCapture(Camera camera, string name)
        {
            var target = new RenderTexture(Width, Height, 24, RenderTextureFormat.ARGBHalf, RenderTextureReadWrite.Linear);
            var readback = new Texture2D(Width, Height, TextureFormat.RGBAFloat, false, true);
            var png = new Texture2D(Width, Height, TextureFormat.RGBA32, false, true);
            var previousTarget = camera.targetTexture;
            var previousActive = RenderTexture.active;
            try
            {
                camera.targetTexture = target;
                camera.Render();
                RenderTexture.active = target;
                readback.ReadPixels(new Rect(0, 0, Width, Height), 0, 0);
                readback.Apply();
                var pixels = readback.GetPixels();
                for (int i = 0; i < pixels.Length; i++) pixels[i] = pixels[i].gamma;
                png.SetPixels(pixels);
                png.Apply();
                Directory.CreateDirectory("Validation");
                File.WriteAllBytes("Validation/" + name, png.EncodeToPNG());
                return pixels;
            }
            finally
            {
                camera.targetTexture = previousTarget;
                RenderTexture.active = previousActive;
                target.Release();
                UnityEngine.Object.DestroyImmediate(target);
                UnityEngine.Object.DestroyImmediate(readback);
                UnityEngine.Object.DestroyImmediate(png);
            }
        }
    }
}
