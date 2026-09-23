using System;
using System.Collections.Generic;
using System.Globalization;
using System.IO;
using System.Text;
using UnityEditor;
using UnityEngine;

namespace EndfieldShaderPack
{
    // Fixed-capture reproduction gate for the official character self-shadow resolve.
    //
    // Stage 1 of the experiment is a 1-tap pass whose only job is to prove the
    // plumbing: world reconstruction, character index decode, matrix orientation,
    // atlas rect and depth sign. Stage 2 adds the official 16-tap Poisson gather and
    // softening, and is compared against the captured G channel pixel by pixel.
    //
    // Thresholds below were fixed before any result was observed. They must not be
    // relaxed to make a run pass; if a run fails, the cause is in the reproduction.
    public static class EndfieldCharacterShadowValidation
    {
        const string ReportPath = "Logs/character-shadow-resolve.txt";
        const string ShaderPath = "Assets/EndfieldShaderPack/EndfieldCharacterShadowResolve.compute";
        const int Width = EndfieldCharacterShadowAssets.FrameWidth;
        const int Height = EndfieldCharacterShadowAssets.FrameHeight;

        const float MaxRoundTripErrorPixels = 1.0f;
        const float MinTruncationMargin = 1e-3f;
        const float MinInRangeFraction = 0.90f;
        const float MaxMeanByteError = 1.0f;
        const float MinWithinOneLsb = 0.99f;
        const float MinShadowIoU = 0.90f;
        // The recorded evidence figure 116890 corresponds to byte/255 < 0.99, i.e.
        // byte < 253. Using byte < round(0.99*255) = 252 instead yields 115618 and
        // differs by exactly count(252) = 1272, which would look like a resolve bug.
        const int ShadowByteLimit = 253;

        [MenuItem("Endfield/Validate Character Shadow Resolve (fixed capture)", false, 71)]
        public static void RunAll()
        {
            var report = new StringBuilder();
            int failures = 0;
            report.AppendLine("Endfield character self-shadow resolve gate (fixed frame-6411 capture)");
            report.AppendLine("utc: " + DateTime.UtcNow.ToString("o", CultureInfo.InvariantCulture));
            report.AppendLine("thresholds: roundTrip<=" + MaxRoundTripErrorPixels +
                              "px, truncationMargin>" + MinTruncationMargin +
                              ", inRange>=" + MinInRangeFraction +
                              ", meanByteErr<=" + MaxMeanByteError +
                              ", withinOneLsb>=" + MinWithinOneLsb +
                              ", shadowIoU>=" + MinShadowIoU);
            report.AppendLine();

            if (EndfieldCharacterShadowAssets.Texture("character-shadow-atlas") == null)
                EndfieldCharacterShadowAssets.ImportAll();
            var constants = EndfieldCharacterShadowAssets.LoadConstants();
            var atlas = Require("character-shadow-atlas", EndfieldCharacterShadowAssets.AtlasWidth, EndfieldCharacterShadowAssets.AtlasHeight);
            var gbuffer0 = Require("gbuffer0-character-index", Width, Height);
            var gbuffer1 = Require("gbuffer1-normal", Width, Height);
            var cameraDepth = Require("camera-depth", Width, Height);
            var reference = Require("screen-shadow-resolved", Width, Height);

            report.AppendLine("validSlots: " + constants.validSlots + " (CharacterShadowParams = " + constants.parameters + ")");
            report.AppendLine("texelSize: " + constants.texelSize);
            report.AppendLine("screenSize: " + constants.screenSize);
            report.AppendLine("cameraPos: " + constants.cameraPos);
            report.AppendLine("atlas format: " + atlas.format + "  reference format: " + reference.format);
            report.AppendLine();

            // Component-boundary probe. The GPU resolve reported every tap as
            // "gather < refDepth", which is either a broken atlas import or wrong
            // sampling. Reading the imported texture back on the CPU separates those:
            // the DDS export of the same resource is known to hold 195042 non-zero
            // D16 texels with a maximum of 55636 (0.848951 unorm), all inside slot 0's
            // declared atlas rect. If Unity's imported copy disagrees, the import is
            // the failing component and no shader change can help.
            report.AppendLine("--- boundary probe: imported textures vs the DDS export ---");
            Check(report, ref failures, "imported atlas is not degenerate after the EXR->R16 conversion", () =>
            {
                if (atlas.format != TextureFormat.R16)
                    report.AppendLine("    WARNING atlas imported as " + atlas.format + ", not R16");
                var raw = atlas.GetRawTextureData<ushort>();
                int nonZero = 0; ushort max = 0;
                int minRow = int.MaxValue, maxRow = int.MinValue;
                int minCol = int.MaxValue, maxCol = int.MinValue;
                int width = atlas.width;
                for (int i = 0; i < raw.Length; i++)
                {
                    if (raw[i] == 0) continue;
                    nonZero++;
                    if (raw[i] > max) max = raw[i];
                    int row = i / width, column = i % width;
                    if (row < minRow) minRow = row;
                    if (row > maxRow) maxRow = row;
                    if (column < minCol) minCol = column;
                    if (column > maxCol) maxCol = column;
                }
                report.AppendLine("    atlas texels=" + raw.Length + " nonZero=" + nonZero +
                                  " (" + (100.0 * nonZero / raw.Length).ToString("F3", CultureInfo.InvariantCulture) + "%)" +
                                  " maxRaw=" + max + " maxAsUnorm=" + (max / 65535.0).ToString("F6", CultureInfo.InvariantCulture));
                report.AppendLine("    atlas nonZero bounds in Unity memory order: columns[" + minCol + "," + maxCol +
                                  "] rows[" + minRow + "," + maxRow + "] of " + width + "x" + atlas.height);
                report.AppendLine("    DDS ground truth: nonZero=195042 (2.325%) maxRaw=55636 maxAsUnorm=0.848951," +
                                  " columns[3191,3943] top-down rows[122,848]; flipped rows would be [1200,1926]");
                report.AppendLine("    slot0 atlas rect uv = [0.75,1.0] x [0,0.5] -> rows[0,1024) if uv.v grows with memory row");
                Require(nonZero == 195042,
                    "imported atlas has " + nonZero + " non-zero texels but the D16 DDS export of the same" +
                    " resource has 195042; the EXR->R16 import path lost data.");
                // Exact equality is wrong here: the value travels D16 -> UINT32 EXR ->
                // float -> R16_UNORM, so the single extreme texel can move by a few LSB.
                // The non-zero count above is the exact structural invariant; this only
                // has to prove the scale was not mangled.
                Require(Mathf.Abs(max - 55636) <= 64,
                    "imported atlas max raw is " + max + " but the DDS export's is 55636;" +
                    " a difference beyond 64 LSB means the value scale changed, not just rounding.");
            });

            Check(report, ref failures, "imported GBuffer0 reproduces the four distinct packed values", () =>
            {
                // The DDS holds exactly four distinct R10G10B10A2 values across the
                // frame: 258 (character, 365226 px), 1047552 (1633999 px),
                // 665844736 (2094636 px) and 0 (2139 px).
                var pixels = gbuffer0.GetPixels();
                var seen = new Dictionary<long, int>();
                for (int i = 0; i < pixels.Length; i++)
                {
                    Color p = pixels[i];
                    long packed = ((long)Mathf.RoundToInt(p.a * 3f) << 30)
                                | ((long)Mathf.RoundToInt(p.b * 1023f) << 20)
                                | ((long)Mathf.RoundToInt(p.g * 1023f) << 10)
                                | (long)Mathf.RoundToInt(p.r * 1023f);
                    seen[packed] = seen.TryGetValue(packed, out int n) ? n + 1 : 1;
                }
                var keys = new List<long>(seen.Keys); keys.Sort();
                foreach (long key in keys)
                    report.AppendLine("    packed=" + key + " count=" + seen[key]);
                Require(seen.ContainsKey(258L) && seen[258L] == 365226,
                    "expected 365226 pixels with packed value 258, got " +
                    (seen.TryGetValue(258L, out int characterPixels) ? characterPixels.ToString() : "none"));
                Require(keys.Count == 4, "expected exactly 4 distinct packed values, got " + keys.Count);
            });
            report.AppendLine();

            // Orientation measurement, not a gate: the atlas is a DEPTH render target
            // while GBuffer0 and the resolved shadow are COLOUR targets, and RenderDoc
            // is not obliged to export the two classes with the same row order. The
            // atlas probe above proved the atlas arrives vertically flipped relative to
            // its DDS. This measures whether the colour targets did too, using the mean
            // row of the official shadowed pixels, which differs by 219 rows between
            // the two hypotheses and so cannot be confused.
            {
                var pixels = reference.GetPixels();
                var g0 = gbuffer0.GetPixels();
                long shadowRowSum = 0; int shadowCount = 0, shadowMinRow = int.MaxValue, shadowMaxRow = int.MinValue;
                long charCount = 0; int charMinRow = int.MaxValue, charMaxRow = int.MinValue;
                for (int y = 0; y < Height; y++)
                {
                    int rowBase = y * Width;
                    for (int x = 0; x < Width; x++)
                    {
                        int i = rowBase + x;
                        if (Quantize(pixels[i].g) < ShadowByteLimit)
                        {
                            shadowRowSum += y; shadowCount++;
                            if (y < shadowMinRow) shadowMinRow = y;
                            if (y > shadowMaxRow) shadowMaxRow = y;
                        }
                        Color p = g0[i];
                        long packed = ((long)Mathf.RoundToInt(p.a * 3f) << 30)
                                    | ((long)Mathf.RoundToInt(p.b * 1023f) << 20)
                                    | ((long)Mathf.RoundToInt(p.g * 1023f) << 10)
                                    | (long)Mathf.RoundToInt(p.r * 1023f);
                        if (packed == 258L)
                        {
                            charCount++;
                            if (y < charMinRow) charMinRow = y;
                            if (y > charMaxRow) charMaxRow = y;
                        }
                    }
                }
                report.AppendLine("--- orientation measurement (Unity memory row order, row 0 first) ---");
                report.AppendLine("    reference shadowed : count=" + shadowCount + " rows[" + shadowMinRow + "," + shadowMaxRow +
                                  "] meanRow=" + (shadowCount == 0 ? 0.0 : (double)shadowRowSum / shadowCount).ToString("F2", CultureInfo.InvariantCulture));
                report.AppendLine("    DDS ground truth   : count=116890 top-down rows[87,1524] meanRow=909.23; vertically flipped meanRow=689.77");
                report.AppendLine("    gbuffer0 character : count=" + charCount + " rows[" + charMinRow + "," + charMaxRow + "]");
                report.AppendLine("    DDS ground truth   : count=365226 top-down rows[86,1530]; vertically flipped rows[69,1513]");
                report.AppendLine("    atlas already measured as flipped; a meanRow near 689.77 means the colour targets flipped too, near 909.23 means they did not.");
                report.AppendLine();
            }

            var shader = AssetDatabase.LoadAssetAtPath<ComputeShader>(ShaderPath);
            if (shader == null) throw new InvalidOperationException("Missing resolve compute shader at " + ShaderPath);
            int kernel = shader.FindKernel("CSResolve");
            if (kernel < 0) throw new InvalidOperationException("CSResolve kernel not found.");
            // ShaderUtil.GetShaderMessages only accepts Shader, not ComputeShader, so
            // there is no pre-flight compile check here. A compute shader that fails to
            // compile makes Dispatch throw, and stale or uninitialised targets would
            // fail the numeric gates below rather than pass silently.

            var g = CreateTarget(RenderTextureFormat.RFloat);
            var diag0 = CreateTarget(RenderTextureFormat.ARGBFloat);
            var diag1 = CreateTarget(RenderTextureFormat.ARGBFloat);
            var diag2 = CreateTarget(RenderTextureFormat.RFloat);
            ComputeBuffer w2s = null, biases = null, lightDir = null, atlasParams = null;
            try
            {
                w2s = FillMatrixColumns(constants.worldToShadow);
                biases = FillVectors(constants.biases);
                lightDir = FillVectors(constants.lightDir);
                atlasParams = FillVectors(constants.atlasParams);
                Bind(shader, kernel, atlas, gbuffer0, gbuffer1, cameraDepth, constants,
                     w2s, biases, lightDir, atlasParams, g, diag0, diag1, diag2);

                // ---- stage 1: 1-tap, plumbing only ----
                shader.SetInt("_Mode", 0);
                shader.Dispatch(kernel, Width / 8, Height / 8, 1);
                var oneTapG = ReadBack(g, TextureFormat.RFloat);
                var oneTapDiag0 = ReadBack(diag0, TextureFormat.RGBAFloat);
                var oneTapDiag1 = ReadBack(diag1, TextureFormat.RGBAFloat);

                report.AppendLine("--- stage 1: 1-tap plumbing ---");
                Check(report, ref failures, "world position round-trips through the view-projection", () =>
                {
                    double sum = 0; float max = 0f; int counted = 0; int nonFinite = 0;
                    for (int i = 0; i < oneTapDiag1.Length; i++)
                    {
                        Color d = oneTapDiag1[i];
                        if (!IsFinite(d.r) || !IsFinite(d.g) || !IsFinite(d.b)) { nonFinite++; continue; }
                        sum += d.a; counted++;
                        if (d.a > max) max = d.a;
                    }
                    report.AppendLine("    pixels=" + counted + " nonFiniteWorld=" + nonFinite +
                                      " maxRoundTripError=" + max.ToString("F6", CultureInfo.InvariantCulture) + "px" +
                                      " mean=" + (counted == 0 ? 0 : sum / counted).ToString("F6", CultureInfo.InvariantCulture) + "px");
                    Require(nonFinite == 0, nonFinite + " pixels reconstructed a non-finite world position.");
                    Require(max <= MaxRoundTripErrorPixels,
                        "round-trip reprojection error " + max + "px exceeds " + MaxRoundTripErrorPixels +
                        "px; the matrix layout or depth convention is wrong.");
                });

                Check(report, ref failures, "character index decodes into the valid slot range with unambiguous truncation", () =>
                {
                    // Official semantics: validity is tested on the FRACTIONAL value
                    // (indexF >= 0 && indexF < Params.z) and the slot is int(indexF),
                    // i.e. truncation. The packed value is not a power of two -- the
                    // capture holds exactly four distinct R10G10B10A2 values and the
                    // low bits carry data that is not the slot index -- so requiring an
                    // exact integer would contradict the source. What must hold instead
                    // is that truncation cannot be flipped by float error.
                    var histogram = new Dictionary<int, int>();
                    var distinct = new Dictionary<float, int>();
                    float minMargin = float.MaxValue; int invalid = 0, valid = 0; float maxIndex = float.MinValue;
                    for (int i = 0; i < oneTapDiag0.Length; i++)
                    {
                        float index = oneTapDiag0[i].r;
                        if (!IsFinite(index) || index < 0f || index >= constants.validSlots) { invalid++; continue; }
                        valid++;
                        maxIndex = Mathf.Max(maxIndex, index);
                        int slot = (int)index;
                        histogram[slot] = histogram.TryGetValue(slot, out int n) ? n + 1 : 1;
                        float rounded = Mathf.Round(index * 1e6f) / 1e6f;
                        distinct[rounded] = distinct.TryGetValue(rounded, out int m) ? m + 1 : 1;
                        float margin = Mathf.Ceil(index) - index;
                        if (margin > 1e-9f) minMargin = Mathf.Min(minMargin, margin);
                    }
                    var slots = new List<int>(histogram.Keys); slots.Sort();
                    var breakdown = new StringBuilder();
                    foreach (int slot in slots)
                        breakdown.Append(" slot").Append(slot).Append('=').Append(histogram[slot]);
                    var values = new StringBuilder();
                    foreach (var pair in distinct)
                        values.Append(" ").Append(pair.Key.ToString("F6", CultureInfo.InvariantCulture))
                              .Append("(x").Append(pair.Value).Append(")");
                    report.AppendLine("    validIndexPixels=" + valid + " backgroundPixels=" + invalid +
                                      " maxIndex=" + maxIndex.ToString("F6", CultureInfo.InvariantCulture) +
                                      " distinctSlots=" + slots.Count + breakdown);
                    report.AppendLine("    distinctIndexValues=" + distinct.Count + values);
                    report.AppendLine("    minMarginToNextInteger=" +
                                      (minMargin == float.MaxValue ? 1f : minMargin).ToString("F6", CultureInfo.InvariantCulture) +
                                      " (must exceed " + MinTruncationMargin + " so int() cannot flip)");
                    Require(valid > 0, "no pixel decoded to a valid character index.");
                    foreach (int slot in slots)
                        Require(slot >= 0 && slot < constants.validSlots,
                            "truncated slot " + slot + " is outside [0," + constants.validSlots + ").");
                    Require(maxIndex < constants.validSlots,
                        "decoded index " + maxIndex + " reached CharacterShadowParams.z = " + constants.validSlots);
                    Require(minMargin == float.MaxValue || minMargin > MinTruncationMargin,
                        "some pixel sits within " + minMargin + " of the next integer, so float error could" +
                        " change which slot int() selects.");
                });

                Check(report, ref failures, "biased shadow-space position lands inside its atlas cell", () =>
                {
                    int valid = 0, inRange = 0; float minRef = float.MaxValue, maxRef = float.MinValue;
                    int shadowed = 0;
                    for (int i = 0; i < oneTapDiag0.Length; i++)
                    {
                        Color d = oneTapDiag0[i];
                        float index = d.r;
                        if (!IsFinite(index) || index < 0f || index >= constants.validSlots) continue;
                        valid++;
                        if (d.g > 0.5f)
                        {
                            inRange++;
                            minRef = Mathf.Min(minRef, d.b);
                            maxRef = Mathf.Max(maxRef, d.b);
                            if (oneTapG[i].r < 0.5f) shadowed++;
                        }
                    }
                    float fraction = valid == 0 ? 0f : (float)inRange / valid;
                    report.AppendLine("    validIndexPixels=" + valid + " inAtlasCell=" + inRange +
                                      " fraction=" + fraction.ToString("F6", CultureInfo.InvariantCulture) +
                                      " refDepthRange=[" + minRef.ToString("F6", CultureInfo.InvariantCulture) + "," +
                                      maxRef.ToString("F6", CultureInfo.InvariantCulture) + "]" +
                                      " oneTapShadowed=" + shadowed);
                    Require(valid > 0, "no valid-index pixels to test.");
                    Require(fraction >= MinInRangeFraction,
                        "only " + fraction.ToString("F4", CultureInfo.InvariantCulture) +
                        " of character pixels project inside their atlas cell; a wrong matrix orientation," +
                        " atlas rect or depth sign would push most of them outside [0,1].");
                    Require(minRef >= 0.01f - 1e-6f && maxRef <= 1.0f,
                        "refDepth escaped (0,1]: [" + minRef + "," + maxRef + "]");
                    float shadowFraction = inRange == 0 ? 0f : (float)shadowed / inRange;
                    Require(shadowFraction > 0.001f && shadowFraction < 0.999f,
                        "1-tap shadowed fraction " + shadowFraction +
                        " is degenerate; the atlas would carry no usable depth variation.");
                });

                // ---- stage 2: full 16-tap official gather + softening ----
                shader.SetInt("_Mode", 1);
                shader.Dispatch(kernel, Width / 8, Height / 8, 1);
                var fullG = ReadBack(g, TextureFormat.RFloat);
                var fullDiag2 = ReadBack(diag2, TextureFormat.RFloat);
                var referencePixels = reference.GetPixels();

                report.AppendLine();
                report.AppendLine("--- stage 2: 16-tap Poisson gather against the captured G channel ---");
                Check(report, ref failures, "reference R channel is constant 1 as the capture recorded", () =>
                {
                    int off = 0;
                    for (int i = 0; i < referencePixels.Length; i++)
                        if (Quantize(referencePixels[i].r) != 255) off++;
                    report.AppendLine("    referencePixels=" + referencePixels.Length + " R!=255 count=" + off);
                    Require(off == 0, off + " reference pixels do not have R=255; wrong texture or channel order.");
                });

                long byteErrorSum = 0; int withinOne = 0, exact = 0, nonFinite = 0, countLitZero = 0;
                int mineShadowed = 0, officialShadowed = 0, bothShadowed = 0;
                long referenceZero = 0;
                for (int i = 0; i < referencePixels.Length; i++)
                {
                    float raw = fullG[i].r;
                    if (!IsFinite(raw)) nonFinite++;
                    if (fullDiag2[i].r < 0.5f) countLitZero++;
                    int mine = Quantize(raw);
                    int official = Quantize(referencePixels[i].g);
                    if (official == 0) referenceZero++;
                    int difference = Math.Abs(mine - official);
                    byteErrorSum += difference;
                    if (difference == 0) exact++;
                    if (difference <= 1) withinOne++;
                    bool mineIsShadowed = mine < ShadowByteLimit;
                    bool officialIsShadowed = official < ShadowByteLimit;
                    if (mineIsShadowed) mineShadowed++;
                    if (officialIsShadowed) officialShadowed++;
                    if (mineIsShadowed && officialIsShadowed) bothShadowed++;
                }
                int total = referencePixels.Length;
                double meanByteError = (double)byteErrorSum / total;
                double withinOneLsb = (double)withinOne / total;
                double exactFraction = (double)exact / total;
                int union = mineShadowed + officialShadowed - bothShadowed;
                double iou = union == 0 ? 1.0 : (double)bothShadowed / union;

                // Visual evidence alongside the numbers. Greyscale G channel for both
                // sides and an 8x-amplified absolute difference, so the 0.16% of pixels
                // that disagree are visible instead of buried in an average.
                var officialPng = new Texture2D(Width, Height, TextureFormat.RGBA32, false, true);
                var minePng = new Texture2D(Width, Height, TextureFormat.RGBA32, false, true);
                var diffPng = new Texture2D(Width, Height, TextureFormat.RGBA32, false, true);
                var o = new Color[total]; var m = new Color[total]; var df = new Color[total];
                try
                {
                    for (int i = 0; i < total; i++)
                    {
                        float ov = Quantize(referencePixels[i].g) / 255f;
                        float mv = Quantize(fullG[i].r) / 255f;
                        o[i] = new Color(ov, ov, ov, 1f);
                        m[i] = new Color(mv, mv, mv, 1f);
                        float d = Mathf.Min(1f, Mathf.Abs(ov - mv) * 8f);
                        df[i] = new Color(d, 0f, 0f, 1f);
                    }
                    officialPng.SetPixels(o); minePng.SetPixels(m); diffPng.SetPixels(df);
                    Directory.CreateDirectory("Validation");
                    File.WriteAllBytes("Validation/character-shadow-official.png", officialPng.EncodeToPNG());
                    File.WriteAllBytes("Validation/character-shadow-reproduced.png", minePng.EncodeToPNG());
                    File.WriteAllBytes("Validation/character-shadow-diff-x8.png", diffPng.EncodeToPNG());
                    report.AppendLine("    wrote Validation/character-shadow-official.png, -reproduced.png and -diff-x8.png");
                }
                finally
                {
                    UnityEngine.Object.DestroyImmediate(officialPng);
                    UnityEngine.Object.DestroyImmediate(minePng);
                    UnityEngine.Object.DestroyImmediate(diffPng);
                }

                report.AppendLine("    meanByteError=" + meanByteError.ToString("F6", CultureInfo.InvariantCulture) +
                                  " withinOneLsb=" + withinOneLsb.ToString("F8", CultureInfo.InvariantCulture) +
                                  " exact=" + exactFraction.ToString("F8", CultureInfo.InvariantCulture));
                report.AppendLine("    shadowed(byte<" + ShadowByteLimit + "): mine=" + mineShadowed +
                                  " official=" + officialShadowed + " both=" + bothShadowed +
                                  " IoU=" + iou.ToString("F6", CultureInfo.InvariantCulture));
                report.AppendLine("    nonFiniteG=" + nonFinite + " pixelsWithZeroOccludingTaps(incl. background)=" +
                                  countLitZero + " official G byte==0 pixels=" + referenceZero);
                report.AppendLine("    note: sumPositive/countLit is a 0/0 when no tap occludes. It never becomes NaN" +
                                  " because HLSL min/max return the non-NaN operand; see the gate below.");

                Check(report, ref failures, "16-tap resolve reproduces the captured G channel", () =>
                {
                    Require(meanByteError <= MaxMeanByteError,
                        "mean byte error " + meanByteError.ToString("F6", CultureInfo.InvariantCulture) +
                        " exceeds " + MaxMeanByteError);
                    Require(withinOneLsb >= MinWithinOneLsb,
                        "only " + withinOneLsb.ToString("F6", CultureInfo.InvariantCulture) +
                        " of pixels are within one LSB; required " + MinWithinOneLsb);
                    Require(iou >= MinShadowIoU,
                        "shadowed-region IoU " + iou.ToString("F6", CultureInfo.InvariantCulture) +
                        " is below " + MinShadowIoU);
                });

                Check(report, ref failures, "zero-occluder pixels resolve to fully lit without producing NaN", () =>
                {
                    Require(nonFinite == 0, nonFinite +
                        " non-finite values reached the output; the comparison against the R8G8 target" +
                        " would then be measuring the target's NaN flush instead of the resolve.");
                    // diag0's index/inRange/refDepth fields do not depend on _Mode, so the
                    // mode-0 readback is still valid here; only centerAtlasDepth differs.
                    int noOccluder = 0, wrong = 0;
                    for (int i = 0; i < total; i++)
                    {
                        Color d = oneTapDiag0[i];
                        float index = d.r;
                        if (!IsFinite(index) || index < 0f || index >= constants.validSlots || d.g < 0.5f) continue;
                        if (fullDiag2[i].r >= 0.5f) continue;
                        noOccluder++;
                        if (Quantize(fullG[i].r) != 255) wrong++;
                    }
                    report.AppendLine("    character pixels with zero occluding taps=" + noOccluder +
                                      ", of which G!=255: " + wrong);
                    report.AppendLine("    step(0, gathered-refDepth) counts taps whose stored depth is nearer the" +
                                      " light, i.e. OCCLUDING taps, so zero of them means fully lit and G must be 1.");
                    report.AppendLine("    The official 0/0 is resolved by HLSL itself, not flushed: min/max return the" +
                                      " non-NaN operand, so clamp(0*inf,0,1)=1, lerp(o^3,o,1)=o=0 and");
                    report.AppendLine("    G=min(1, 0.5-0.5*((1-0)*(-1)))=1. Reproducing that path matters because a" +
                                      " NaN guard added here would silently change fully lit pixels.");
                    Require(wrong == 0, wrong + " pixels with zero occluding taps did not resolve to G=1.");
                });
            }
            finally
            {
                Release(g); Release(diag0); Release(diag1); Release(diag2);
                if (w2s != null) w2s.Release();
                if (biases != null) biases.Release();
                if (lightDir != null) lightDir.Release();
                if (atlasParams != null) atlasParams.Release();
            }

            report.AppendLine();
            report.AppendLine(failures == 0
                ? "PASS: fixed-capture character self-shadow resolve reproduces the official G channel within tolerance."
                : "FAIL: " + failures + " character shadow resolve check(s) failed.");
            Directory.CreateDirectory("Logs");
            File.WriteAllText(ReportPath, report.ToString());
            Debug.Log(report.ToString());
            if (failures != 0)
                throw new InvalidOperationException(failures + " character shadow resolve check(s) failed; see " + ReportPath);
        }

        static Texture2D Require(string name, int width, int height)
        {
            var texture = EndfieldCharacterShadowAssets.Texture(name);
            if (texture == null)
                throw new InvalidOperationException("Missing imported capture texture: " + name +
                    ". Run Endfield/Import Character Shadow Evidence.");
            if (texture.width != width || texture.height != height)
                throw new InvalidOperationException(name + " imported as " + texture.width + "x" + texture.height +
                    ", expected " + width + "x" + height);
            return texture;
        }

        static bool IsFinite(float value) => !float.IsNaN(value) && !float.IsInfinity(value);

        // The official target is R8G8_UNORM, so the comparison has to happen on the
        // same quantisation the GPU store performed. Non-finite values are flushed to
        // zero by that store, which is the behaviour being tested, not assumed away.
        static int Quantize(float value)
        {
            if (!IsFinite(value)) return 0;
            float clamped = value < 0f ? 0f : (value > 1f ? 1f : value);
            return Mathf.RoundToInt(clamped * 255f);
        }

        static RenderTexture CreateTarget(RenderTextureFormat format)
        {
            var target = new RenderTexture(Width, Height, 0, format, RenderTextureReadWrite.Linear)
            {
                enableRandomWrite = true,
                filterMode = FilterMode.Point,
                wrapMode = TextureWrapMode.Clamp
            };
            target.Create();
            return target;
        }

        // Reads back and destroys the staging texture immediately: four 2560x1600
        // RGBAFloat targets would otherwise hold ~65MB of GPU-backed memory each on
        // top of the Color[] copies the gates actually work with.
        static Color[] ReadBack(RenderTexture source, TextureFormat format)
        {
            var previous = RenderTexture.active;
            var texture = new Texture2D(source.width, source.height, format, false, true);
            try
            {
                RenderTexture.active = source;
                texture.ReadPixels(new Rect(0, 0, source.width, source.height), 0, 0);
                texture.Apply();
                return texture.GetPixels();
            }
            finally
            {
                RenderTexture.active = previous;
                UnityEngine.Object.DestroyImmediate(texture);
            }
        }

        static ComputeBuffer FillMatrixColumns(Matrix4x4[] matrices)
        {
            var values = new Vector4[matrices.Length * 4];
            for (int i = 0; i < matrices.Length; i++)
                for (int column = 0; column < 4; column++)
                    values[i * 4 + column] = matrices[i].GetColumn(column);
            var buffer = new ComputeBuffer(values.Length, 16);
            buffer.SetData(values);
            return buffer;
        }

        static ComputeBuffer FillVectors(Vector4[] values)
        {
            var buffer = new ComputeBuffer(values.Length, 16);
            buffer.SetData(values);
            return buffer;
        }

        static void Bind(ComputeShader shader, int kernel, Texture atlas, Texture2D gbuffer0,
            Texture2D gbuffer1, Texture2D cameraDepth, EndfieldCharacterShadowAssets.Constants constants,
            ComputeBuffer w2s, ComputeBuffer biases, ComputeBuffer lightDir, ComputeBuffer atlasParams,
            RenderTexture g, RenderTexture diag0, RenderTexture diag1, RenderTexture diag2)
        {
            shader.SetTexture(kernel, "_AtlasTex", atlas);
            shader.SetTexture(kernel, "_GBuffer0", gbuffer0);
            shader.SetTexture(kernel, "_GBuffer1", gbuffer1);
            shader.SetTexture(kernel, "_CameraDepth", cameraDepth);
            shader.SetBuffer(kernel, "_CharacterWorldToShadow", w2s);
            shader.SetBuffer(kernel, "_CharacterShadowBiases", biases);
            shader.SetBuffer(kernel, "_CharacterShadowLightDir", lightDir);
            shader.SetBuffer(kernel, "_CharacterShadowAtlasParams", atlasParams);
            shader.SetVector("_CharacterShadowTexelSize", constants.texelSize);
            shader.SetVector("_CharacterShadowParams", constants.parameters);
            shader.SetVector("_ScreenSize", constants.screenSize);
            shader.SetMatrix("_InvViewProj", constants.invViewProj);
            shader.SetMatrix("_ViewProj", constants.viewProj);
            // Captured frame data arrives vertically mirrored in Unity memory; this is
            // the measured orientation of all five imported textures. A live atlas
            // rendered by Unity must pass 0 instead.
            shader.SetInt("_CaptureFlipY", 1);
            shader.SetTexture(kernel, "_OutG", g);
            shader.SetTexture(kernel, "_OutDiag0", diag0);
            shader.SetTexture(kernel, "_OutDiag1", diag1);
            shader.SetTexture(kernel, "_OutDiag2", diag2);
        }

        static void Release(RenderTexture target)
        {
            if (target == null) return;
            target.Release();
            UnityEngine.Object.DestroyImmediate(target);
        }

        static void Check(StringBuilder report, ref int failures, string name, Action body)
        {
            try
            {
                body();
                report.AppendLine("PASS  " + name);
            }
            catch (Exception e)
            {
                failures++;
                report.AppendLine("FAIL  " + name + " :: " + e.GetType().Name + ": " + e.Message);
            }
        }

        static void Require(bool condition, string message)
        {
            if (!condition) throw new InvalidOperationException(message);
        }
    }
}
