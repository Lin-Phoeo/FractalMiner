using System;
using System.Globalization;
using System.IO;
using System.Text;
using Unity.Collections;
using UnityEditor;
using UnityEngine;

namespace EndfieldShaderPack
{
    /// Gates for the light-space construction that the runtime character shadow atlas
    /// is built from. Everything here is measured against the frame-6411 capture; none
    /// of it needs a scene, a pose or a GPU, so it runs before the atlas pass exists.
    ///
    /// Atlas lookup convention, measured rather than assumed: the official cell for
    /// slot 0 is v in [0,0.5] and the reconstructed visible surface spans v in
    /// [0.059,0.414], while the imported atlas holds its 195042 non-zero texels at
    /// Unity memory rows [1199,1925] -- the vertical flip of the DDS top-down rows
    /// [122,848]. So raw row = (1-v)*H, which is also what the shipped resolve reads
    /// when it samples at FlipAtlasV(uv) = 1-v. The unflipped mapping is evaluated too
    /// and reported, so a silent convention change shows up as a collapsed agreement
    /// fraction instead of a plausible-looking number.
    public static class EndfieldCharacterShadowProjectionValidation
    {
        const string ReportPath = "Logs/character-shadow-projection.txt";
        const int Width = EndfieldCharacterShadowAssets.FrameWidth;
        const int Height = EndfieldCharacterShadowAssets.FrameHeight;
        const int AtlasWidth = EndfieldCharacterShadowAssets.AtlasWidth;
        const int AtlasHeight = EndfieldCharacterShadowAssets.AtlasHeight;

        // Fixed before the first run. The captured constants are float32, so 1e-6
        // relative is round-off; anything larger means the formula is wrong.
        const float MaxMatrixRelativeError = 1e-6f;
        const float MaxBasisError = 1e-6f;
        // The captured world coordinates are O(200) and the box maps them to [0,1], so
        // every clip-space component is a sum of O(100) terms that cancels to O(1):
        // one ulp of 200 is 1.5e-5. 1e-4 is a handful of ulps, still four orders of
        // magnitude below the O(1) error a wrong construction would produce.
        const float MaxClipAbsoluteError = 1e-4f;
        const float MaxRoundTripPixels = 1.0f;
        const float MinInsideBoxFraction = 0.999f;
        const float MinTightness = 0.70f;
        const float MinLightSideFill = 0.50f;
        // The measured slot-0 depth extent is 1.984 world units, so 2e-3 of the
        // normalised range is about 4mm: far above 16-bit quantisation (3e-5) and the
        // largest receiver bias on a light-facing surface (4.2e-4), far below the O(1)
        // error a transposed or unflipped matrix would produce.
        const float MaxAtlasDepthTolerance = 2e-3f;
        // The median signed error must sit on zero: the atlas is D16 over the same
        // light box, so a correct mapping leaves only quantisation (1.5e-5). 2e-4 is
        // 13x that and still 1/20 of the tolerance above.
        const float MaxMedianSignedError = 2e-4f;
        // A pixel whose normal faces the light at N.L >= 0.9 cannot be hidden behind
        // its own atlas texel's footprint: one 1024-cell texel spans 1.16mm x 2.03mm
        // of light-space area, and at that incidence the depth spread across it is at
        // most about 2.6e-4 normalised, an eighth of MaxAtlasDepthTolerance. So nearly
        // every such pixel must find the atlas at or in front of its own depth.
        const float StrongLightDot = 0.9f;
        // A strongly-lit pixel whose own atlas texel AND its 2x2 neighbourhood hold no
        // caster at or in front of the visible surface means the atlas is missing that
        // geometry. Measured on frame 6411: 0.735% of strongly-lit pixels (364 px,
        // 0.16% of the character), all specks at the eyes and alpha-tested hair-card
        // edges, where GBuffer1 stores a shading normal rather than the geometric one
        // and this gate's front-facing selection therefore mis-sorts a few pixels. A
        // body part absent from the caster set would be tens of percent, so 1% still
        // separates "construction correct, known speckle" from "wrong caster set".
        const float MinStrongNotBehind = 0.99f;
        // The official shadow is the raw atlas comparison grown by the receiver bias and
        // the 16-tap penumbra (offsetScale = 4 atlas texels ~ 4.6mm, a couple of screen
        // pixels at this framing), so the two populations are compared after dilating
        // each by DilationPixels screen pixels. 0.95 leaves the boundary rasterisation
        // difference between the camera and light views and nothing more.
        const int DilationPixels = 2;
        const float MinDilatedContainment = 0.95f;
        // Same plateau convention as the end-to-end resolve gate: the R8G8 target's lit
        // value quantises to 255, so 253 and below is shadow.
        const int ShadowByteLimit = 253;
        // 10-bit octahedral quantisation is worth about 0.11 degrees, twice that in the
        // folded octants; 0.5 degrees leaves room for the fold without hiding a wrong axis.
        const float MaxOctahedralDegrees = 0.5f;

        [MenuItem("Endfield/Validate Character Shadow Projection (fixed capture)", false, 72)]
        public static void RunAll()
        {
            var report = new StringBuilder();
            int failures = 0;
            report.AppendLine("Endfield character shadow light-space gate (fixed frame-6411 capture)");
            report.AppendLine("utc: " + DateTime.UtcNow.ToString("o", CultureInfo.InvariantCulture));
            report.AppendLine("thresholds: matrixRelErr<=" + MaxMatrixRelativeError +
                              ", basisErr<=" + MaxBasisError +
                              ", clipAbsErr<=" + MaxClipAbsoluteError +
                              ", roundTrip<=" + MaxRoundTripPixels + "px" +
                              ", insideBox>=" + MinInsideBoxFraction +
                              ", inPlaneTightness>=" + MinTightness +
                              ", lightSideDepth>=" + MinLightSideFill +
                              ", medianSignedErr<=" + MaxMedianSignedError +
                              ", strongMissingCaster<=" + (1f - MinStrongNotBehind) +
                              ", dilatedContainment>=" + MinDilatedContainment +
                              ", octahedral<=" + MaxOctahedralDegrees + "deg");
            report.AppendLine();

            if (EndfieldCharacterShadowAssets.Texture("character-shadow-atlas") == null)
                EndfieldCharacterShadowAssets.ImportAll();
            var constants = EndfieldCharacterShadowAssets.LoadConstants();
            var atlas = Require("character-shadow-atlas", AtlasWidth, AtlasHeight);
            var gbuffer0 = Require("gbuffer0-character-index", Width, Height);
            var gbuffer1 = Require("gbuffer1-normal", Width, Height);
            var cameraDepth = Require("camera-depth", Width, Height);
            var reference = Require("screen-shadow-resolved", Width, Height);

            NativeArray<ushort> atlasRaw = atlas.GetRawTextureData<ushort>();
            NativeArray<float> indexRaw = gbuffer0.GetRawTextureData<float>();
            NativeArray<float> normalRaw = gbuffer1.GetRawTextureData<float>();
            NativeArray<float> depthRaw = cameraDepth.GetRawTextureData<float>();
            NativeArray<float> referenceRaw = reference.GetRawTextureData<float>();
            report.AppendLine("validSlots=" + constants.validSlots +
                              " atlasRaw=" + atlasRaw.Length + " indexRaw=" + indexRaw.Length +
                              " normalRaw=" + normalRaw.Length + " depthRaw=" + depthRaw.Length);
            report.AppendLine();

            Check(report, ref failures, "captured light basis equals cross(worldUp, towardLight) for every valid slot", () =>
            {
                for (int slot = 0; slot < constants.validSlots; slot++)
                {
                    Matrix4x4 captured = constants.worldToShadow[slot];
                    var box = EndfieldCharacterShadowProjection.Decompose(captured);
                    Vector3 towardFromConstant = EndfieldCharacterShadowProjection.TowardLight(
                        new Vector3(constants.lightDir[slot].x, constants.lightDir[slot].y, constants.lightDir[slot].z));
                    float depthAxisError = Vector3.Distance(box.towardLight, towardFromConstant);
                    Require(depthAxisError <= MaxBasisError,
                        "slot " + slot + " depth axis is " + depthAxisError + " away from -CharacterShadowLightDir," +
                        " so the reversed-Z axis is not the light direction.");

                    EndfieldCharacterShadowProjection.Basis(towardFromConstant, out Vector3 right, out Vector3 up);
                    Require(Vector3.Distance(box.right, right) <= MaxBasisError,
                        "slot " + slot + " u axis differs from cross(worldUp, towardLight) by " +
                        Vector3.Distance(box.right, right));
                    Require(Vector3.Distance(box.up, up) <= MaxBasisError,
                        "slot " + slot + " v axis differs from cross(towardLight, right) by " +
                        Vector3.Distance(box.up, up));

                    Matrix4x4 rebuilt = EndfieldCharacterShadowProjection.WorldToShadow(box);
                    float worst = MaxRelativeError(captured, rebuilt);
                    Require(worst <= MaxMatrixRelativeError,
                        "slot " + slot + " rebuilt matrix differs by " + worst.ToString("E3", CultureInfo.InvariantCulture) +
                        " relative; the scale/translation construction is not the official one.");
                    report.AppendLine("    slot " + slot + " extent=" + box.Extent.ToString("F5", CultureInfo.InvariantCulture) +
                                      " worstRelativeError=" + worst.ToString("E3", CultureInfo.InvariantCulture));
                }
                // The gate has to be able to fail. A one-degree basis rotation is a
                // plausible-looking bug; if that passed, the tolerance proves nothing.
                Matrix4x4 reference = constants.worldToShadow[0];
                var mutated = EndfieldCharacterShadowProjection.Decompose(reference);
                mutated.right = Quaternion.AngleAxis(1f, mutated.towardLight) * mutated.right;
                mutated.up = Quaternion.AngleAxis(1f, mutated.towardLight) * mutated.up;
                float mutatedError = MaxRelativeError(reference, EndfieldCharacterShadowProjection.WorldToShadow(mutated));
                Require(mutatedError > MaxMatrixRelativeError,
                    "a 1 degree basis rotation only moved the matrix by " + mutatedError +
                    ", so the tolerance above cannot detect a wrong basis.");
                report.AppendLine("    mutation check: 1deg basis rotation moves the matrix by " +
                                  mutatedError.ToString("E3", CultureInfo.InvariantCulture));
            });

            Check(report, ref failures, "clip-space variant maps the box to [-1,1] in x and y and leaves z in [0,1]", () =>
            {
                var box = EndfieldCharacterShadowProjection.Decompose(constants.worldToShadow[0]);
                Matrix4x4 clip = EndfieldCharacterShadowProjection.WorldToShadowClip(box);
                Vector3[] corners =
                {
                    Vector3.zero, Vector3.one,
                    new Vector3(0f, 0f, 1f),
                    new Vector3(1f, 1f, 0f)
                };
                foreach (Vector3 light in corners)
                {
                    Vector3 world = WorldPoint(box, light);
                    Vector4 clipped = clip * new Vector4(world.x, world.y, world.z, 1f);
                    Require(Mathf.Abs(clipped.w - 1f) <= 1e-6f, "clip variant is not affine: w=" + clipped.w);
                    Require(Mathf.Abs(Mathf.Abs(clipped.x) - 1f) <= MaxClipAbsoluteError &&
                            Mathf.Abs(Mathf.Abs(clipped.y) - 1f) <= MaxClipAbsoluteError,
                        "box corner " + light + " mapped to clip " + clipped + ", expected |x|=|y|=1.");
                    Require(Mathf.Abs(clipped.z - light.z) <= MaxClipAbsoluteError,
                        "clip variant changed the depth: " + clipped.z + " vs " + light.z);
                }
            });

            Check(report, ref failures, "octahedral encode/decode round-trips inside 10-bit quantisation", () =>
            {
                float worst = 0f;
                Vector3 worstDirection = Vector3.zero;
                const int samples = 4096;
                float golden = Mathf.PI * (3f - Mathf.Sqrt(5f));
                for (int i = 0; i < samples; i++)
                {
                    float y = 1f - 2f * (i + 0.5f) / samples;
                    float radius = Mathf.Sqrt(Mathf.Max(0f, 1f - y * y));
                    float theta = golden * i;
                    var direction = new Vector3(Mathf.Cos(theta) * radius, y, Mathf.Sin(theta) * radius);
                    Vector2 encoded = EncodeNormalOctahedralY(direction);
                    // The official GBuffer1 is R10G10B10A2_UNORM: encode to [0,1], store
                    // 10 bits, read back. The runtime prepass must quantise identically.
                    var stored = new Vector2(
                        Mathf.Round(Mathf.Clamp01(encoded.x * 0.5f + 0.5f) * 1023f) / 1023f,
                        Mathf.Round(Mathf.Clamp01(encoded.y * 0.5f + 0.5f) * 1023f) / 1023f);
                    Vector3 decoded = DecodeNormalOctahedralY(stored * 2f - Vector2.one);
                    float degrees = Vector3.Angle(direction, decoded);
                    if (degrees > worst) { worst = degrees; worstDirection = direction; }
                }
                report.AppendLine("    worst round-trip angle " + worst.ToString("F4", CultureInfo.InvariantCulture) +
                                  " deg at " + worstDirection.ToString("F3", CultureInfo.InvariantCulture));
                Require(worst <= MaxOctahedralDegrees,
                    "octahedral round-trip reached " + worst + " degrees, above the " +
                    MaxOctahedralDegrees + " degree budget of a 10-bit encode.");
            });

            // Reconstructs the visible character surface exactly the way the shipped
            // compute does (D3D row for the NDC, integer pixel corner, no +0.5) so the
            // light-space evidence below is tied to the already validated resolve.
            report.AppendLine("--- slot 0 light-space reconstruction over every index-0 pixel ---");
            var statistics = new Reconstruction();
            Check(report, ref failures, "reconstructed surface round-trips and stays inside the captured light box", () =>
            {
                statistics.image = new Color[Width * Height];
                statistics.occludedMask = new bool[Width * Height];
                statistics.officialMask = new bool[Width * Height];
                for (int i = 0; i < statistics.image.Length; i++) statistics.image[i] = Color.black;
                var box = EndfieldCharacterShadowProjection.Decompose(constants.worldToShadow[0]);
                Vector4 atlasParams = constants.atlasParams[0];
                float worstRoundTrip = 0f;
                int character = 0, inside = 0, frontFacing = 0;
                Vector3 fillMin = new Vector3(float.MaxValue, float.MaxValue, float.MaxValue);
                Vector3 fillMax = new Vector3(float.MinValue, float.MinValue, float.MinValue);

                for (int row = 0; row < Height; row++)
                {
                    int d3dRow = Height - 1 - row;
                    for (int col = 0; col < Width; col++)
                    {
                        int pixel = row * Width + col;
                        if (PackCharacterIndex(indexRaw, pixel) != 258u) continue;
                        character++;
                        float depth = depthRaw[pixel * 4];
                        Vector2 ndc = new Vector2(col * constants.screenSize.z, d3dRow * constants.screenSize.w) * 2f - Vector2.one;
                        Vector4 clip = constants.invViewProj * new Vector4(ndc.x, -ndc.y, depth, 1f);
                        Vector3 world = new Vector3(clip.x, clip.y, clip.z) / clip.w;
                        Vector4 back = constants.viewProj * new Vector4(world.x, world.y, world.z, 1f);
                        Vector2 pixelBack = new Vector2(back.x / back.w, -(back.y / back.w)) * 0.5f + new Vector2(0.5f, 0.5f);
                        float roundTrip = Vector2.Distance(pixelBack * new Vector2(Width, Height), new Vector2(col, d3dRow));
                        if (roundTrip > worstRoundTrip) worstRoundTrip = roundTrip;

                        Vector3 light = box.Project(world);
                        if (light.x >= 0f && light.x <= 1f && light.y >= 0f && light.y <= 1f && light.z >= 0f && light.z <= 1f)
                        {
                            inside++;
                            fillMin = Vector3.Min(fillMin, light);
                            fillMax = Vector3.Max(fillMax, light);
                        }
                        Vector3 normal = DecodeNormalOctahedralY(new Vector2(
                            normalRaw[pixel * 4] * 2f - 1f, normalRaw[pixel * 4 + 1] * 2f - 1f));
                        float lightDot = Vector3.Dot(normal, box.towardLight);
                        bool facesLight = lightDot >= 0.5f;
                        if (facesLight) frontFacing++;
                        bool officialShadowed =
                            Mathf.RoundToInt(Mathf.Clamp01(referenceRaw[pixel * 4 + 1]) * 255f) < ShadowByteLimit;
                        statistics.Record(world, light, normal, atlasRaw, atlasParams, facesLight,
                            lightDot >= StrongLightDot, officialShadowed, pixel);
                    }
                }

                statistics.characterPixels = character;
                report.AppendLine("    index-0 pixels=" + character + " insideBox=" + inside +
                                  " (" + Fraction(inside, character) + ") frontFacing=" + frontFacing);
                report.AppendLine("    worst round-trip " + worstRoundTrip.ToString("F5", CultureInfo.InvariantCulture) + " px");
                Require(character > 100000, "only " + character + " index-0 pixels; the GBuffer0 read is wrong.");
                Require(worstRoundTrip <= MaxRoundTripPixels,
                    "world reconstruction round-tripped " + worstRoundTrip + " px, above " + MaxRoundTripPixels);
                float insideFraction = Fraction(inside, character);
                Require(insideFraction >= MinInsideBoxFraction,
                    "only " + insideFraction.ToString("F6", CultureInfo.InvariantCulture) +
                    " of the reconstructed surface falls inside the captured light box;" +
                    " a wrong matrix layout would scatter it.");
                Vector3 extent = fillMax - fillMin;
                // Only the two in-plane axes set atlas texel density. The depth axis is
                // expected to be a thin shell near z=1: the camera sits on the light side
                // (its own light-space depth is above the box), so the surfaces it sees
                // are the ones nearest the light. That is also what makes fillMax.z a
                // reversed-Z orientation probe -- a flipped depth axis would pile the
                // visible surface against z=0 instead.
                float tightness = Mathf.Min(extent.x, extent.y);
                report.AppendLine("    visible-surface fill in box units: min=" + fillMin.ToString("F4", CultureInfo.InvariantCulture) +
                                  " max=" + fillMax.ToString("F4", CultureInfo.InvariantCulture));
                report.AppendLine("    in-plane tightness = " + tightness.ToString("F4", CultureInfo.InvariantCulture) +
                                  "   light-side depth fill max = " + fillMax.z.ToString("F4", CultureInfo.InvariantCulture));
                Require(tightness >= MinTightness,
                    "the visible surface fills only " + tightness + " of the box in plane;" +
                    " the official box would not be a tight fit and reproducing it from renderer bounds would waste resolution.");
                Require(fillMax.z >= MinLightSideFill,
                    "the visible surface only reaches light-space depth " + fillMax.z + "; a reversed-Z box would put" +
                    " the light-facing surface near 1, so the depth axis is pointing away from the light.");
            });

            Check(report, ref failures, "captured atlas stores the light-space depth this construction predicts", () =>
            {
                statistics.Finish();
                report.AppendLine("    front-facing pixels=" + statistics.frontFacingCount);
                Require(statistics.frontFacingCount > 10000,
                    "only " + statistics.frontFacingCount + " front-facing pixels to test against the atlas.");
                report.AppendLine("    signed error (atlas - predicted) using file row (1-v)*H: mean|e|=" +
                                  Mean(statistics.agreementSum, statistics.frontFacingCount).ToString("E4", CultureInfo.InvariantCulture) +
                                  " max|e|=" + statistics.agreementMax.ToString("E4", CultureInfo.InvariantCulture));
                report.AppendLine("    percentiles p1/p5/p25/p50/p75/p95/p99 = " +
                                  string.Join(" / ", Array.ConvertAll(statistics.percentiles,
                                      value => value.ToString("E3", CultureInfo.InvariantCulture))));
                report.AppendLine("    populations: agrees=" + Fraction(statistics.agreementCount, statistics.frontFacingCount) +
                                  " occludedByNearerCaster=" + Fraction(statistics.frontFacingCount - statistics.agreementCount - statistics.behindCount, statistics.frontFacingCount) +
                                  " atlasBehindSurface=" + Fraction(statistics.behindCount, statistics.frontFacingCount) +
                                  " emptyAtlasTexel=" + Fraction(statistics.emptyTexelCount, statistics.frontFacingCount));
                report.AppendLine("    agreement when the 2x2 neighbourhood may answer: " +
                                  Fraction(statistics.neighbourhoodAgreementCount, statistics.frontFacingCount) +
                                  " -- a big jump over " +
                                  Fraction(statistics.agreementCount, statistics.frontFacingCount) +
                                  " means half-texel addressing, not occlusion.");
                report.AppendLine("    alternative mapping v*H agreement: " +
                                  Fraction(statistics.alternativeAgreementCount, statistics.frontFacingCount) +
                                  " -- must stay low, otherwise the row convention is ambiguous.");

                var png = new Texture2D(Width, Height, TextureFormat.RGBA32, false, true);
                try
                {
                    // Memory row 0 of the imported capture is the bottom of the game
                    // image, and SetPixels starts at the bottom, so flip the row here to
                    // make the PNG read the same way the official frame does.
                    var pixels = new Color[Width * Height];
                    for (int row = 0; row < Height; row++)
                    {
                        int target = (Height - 1 - row) * Width;
                        Array.Copy(statistics.image, row * Width, pixels, target, Width);
                    }
                    png.SetPixels(pixels);
                    Directory.CreateDirectory("Validation");
                    File.WriteAllBytes("Validation/character-shadow-atlas-agreement.png", png.EncodeToPNG());
                    report.AppendLine("    wrote Validation/character-shadow-atlas-agreement.png" +
                                      " (green agrees, blue nearer caster, red behind surface, yellow empty texel)");
                }
                finally { UnityEngine.Object.DestroyImmediate(png); }

                // Self-occlusion is the feature, not a failure: 22% of light-facing
                // pixels legitimately find a nearer caster (bangs over the face, cloak
                // over the legs, arms over the torso -- see the agreement PNG). The
                // invariants that can actually fail are therefore one-sided: the stored
                // depth must sit exactly on the predicted one in the median, it must
                // never sit behind the visible surface where the texel footprint cannot
                // explain it, and the occlusion population must be the official's.
                float median = statistics.percentiles[3];
                float strongBehind = Fraction(statistics.strongCount - statistics.strongNotBehind -
                                              statistics.strongNotBehindNeighbourhood, statistics.strongCount);
                int officialCovered = CountCovered(statistics.officialMask, statistics.occludedMask);
                int mineCovered = CountCovered(statistics.occludedMask, statistics.officialMask);
                float officialContainment = Fraction(officialCovered, statistics.officialShadowedCount);
                float mineContainment = Fraction(mineCovered, statistics.occludedCount);
                report.AppendLine("    median signed error = " + median.ToString("E4", CultureInfo.InvariantCulture) +
                                  " (must sit on zero: the mapping itself)");
                report.AppendLine("    strongly lit (N.L>=" + StrongLightDot + ") pixels=" + statistics.strongCount +
                                  ": own texel in front " + Fraction(statistics.strongNotBehind, statistics.strongCount) +
                                  ", 2x2 neighbourhood in front " + Fraction(statistics.strongNotBehindNeighbourhood, statistics.strongCount) +
                                  ", nothing in front " + strongBehind + " (magenta in the PNG)");
                report.AppendLine("    dilated containment: official shadow inside atlas-nearer " + officialContainment +
                                  ", atlas-nearer inside official shadow " + mineContainment);
                Require(Mathf.Abs(median) <= MaxMedianSignedError,
                    "median signed atlas error is " + median + ", above " + MaxMedianSignedError +
                    "; the cell mapping, orientation or reversed-Z assumption is off by more than quantisation.");
                Require(strongBehind <= 1f - MinStrongNotBehind,
                    strongBehind + " of strongly lit pixels found no caster at or in front of the visible" +
                    " surface even allowing the 2x2 texel neighbourhood; those are parts missing from the" +
                    " atlas, not shadowing.");
                Require(officialContainment >= MinDilatedContainment,
                    "only " + officialContainment + " of the official's shadowed pixels sit within " +
                    DilationPixels + "px of a pixel where the atlas holds a nearer caster.");
                Require(mineContainment >= MinDilatedContainment,
                    "only " + mineContainment + " of the atlas-nearer pixels sit within " + DilationPixels +
                    "px of an officially shadowed pixel.");
                Require(Fraction(statistics.alternativeAgreementCount, statistics.frontFacingCount) <
                        Fraction(statistics.agreementCount, statistics.frontFacingCount),
                    "the alternative row mapping agrees at least as well, so this gate cannot tell the conventions apart.");
            });

            report.AppendLine();
            report.AppendLine(failures == 0
                ? "PASS: the runtime light-space construction reproduces the captured character shadow atlas."
                : "FAIL: " + failures + " character shadow projection check(s) failed.");
            Directory.CreateDirectory("Logs");
            File.WriteAllText(ReportPath, report.ToString());
            Debug.Log(report.ToString());
            if (failures != 0)
                throw new InvalidOperationException(failures +
                    " character shadow projection check(s) failed; see " + ReportPath);
        }

        /// Accumulates the atlas comparison while the pixel loop above walks the frame.
        /// Errors are kept signed: atlas - predicted. A positive value means the atlas
        /// holds a surface nearer the light, which is what real self-occlusion (hair over
        /// face, cloak over legs) and any caster-side bias both look like. A negative
        /// value means the atlas holds a surface behind the one the camera sees, which
        /// geometry cannot produce, so it is the population that decides whether a
        /// disagreement is physics or a bug.
        sealed class Reconstruction
        {
            public int characterPixels;
            public int frontFacingCount;
            public int agreementCount;
            public int notBehindCount;
            public int alternativeAgreementCount;
            public int behindCount;
            public int emptyTexelCount;
            public int neighbourhoodAgreementCount;
            public int strongCount;
            public int strongNotBehind;
            public int strongNotBehindNeighbourhood;
            public int occludedCount;
            public int officialShadowedCount;
            public int bothCount;
            public bool[] occludedMask;
            public bool[] officialMask;
            public double agreementSum;
            public float agreementMax;
            public float[] percentiles = new float[7];
            public Color[] image;
            readonly System.Collections.Generic.List<float> errors = new System.Collections.Generic.List<float>();

            public void Record(Vector3 world, Vector3 light, Vector3 normal, NativeArray<ushort> atlasRaw,
                Vector4 atlasParams, bool facesLight, bool stronglyLit, bool officialShadowed, int pixel)
            {
                if (!facesLight) return;
                if (light.x < 0f || light.x > 1f || light.y < 0f || light.y > 1f || light.z < 0f || light.z > 1f) return;
                frontFacingCount++;
                float u = atlasParams.x + light.x * atlasParams.z;
                float v = atlasParams.y + light.y * atlasParams.w;
                int column = Mathf.Clamp(Mathf.FloorToInt(u * AtlasWidth), 0, AtlasWidth - 1);
                int fileRow = Mathf.Clamp(Mathf.FloorToInt((1f - v) * AtlasHeight), 0, AtlasHeight - 1);
                float stored = atlasRaw[fileRow * AtlasWidth + column] / 65535f;
                float error = stored - light.z;
                agreementSum += Mathf.Abs(error);
                if (Mathf.Abs(error) > agreementMax) agreementMax = Mathf.Abs(error);
                errors.Add(error);
                bool agrees = Mathf.Abs(error) <= MaxAtlasDepthTolerance;
                if (agrees) agreementCount++;
                if (error < -MaxAtlasDepthTolerance) behindCount++;
                if (stored >= light.z - MaxAtlasDepthTolerance) notBehindCount++;
                if (stored == 0f) emptyTexelCount++;
                bool occluded = error > MaxAtlasDepthTolerance;
                if (occluded) occludedCount++;
                if (officialShadowed) officialShadowedCount++;
                if (occluded && officialShadowed) bothCount++;

                // A half-texel addressing error would show up as disagreement that
                // disappears as soon as the 2x2 neighbourhood is allowed to answer.
                float best = Mathf.Abs(error);
                for (int dy = 0; dy <= 1; dy++)
                {
                    int row = Mathf.Clamp(fileRow + dy, 0, AtlasHeight - 1);
                    for (int dx = 0; dx <= 1; dx++)
                    {
                        int col = Mathf.Clamp(column + dx, 0, AtlasWidth - 1);
                        float candidate = Mathf.Abs(atlasRaw[row * AtlasWidth + col] / 65535f - light.z);
                        if (candidate < best) best = candidate;
                    }
                }
                if (best <= MaxAtlasDepthTolerance) neighbourhoodAgreementCount++;
                if (stronglyLit)
                {
                    strongCount++;
                    if (error >= -MaxAtlasDepthTolerance) strongNotBehind++;
                    else if (best <= MaxAtlasDepthTolerance) strongNotBehindNeighbourhood++;
                }
                occludedMask[pixel] = occluded;
                officialMask[pixel] = officialShadowed;

                int alternativeRow = Mathf.Clamp(Mathf.FloorToInt(v * AtlasHeight), 0, AtlasHeight - 1);
                float alternative = atlasRaw[alternativeRow * AtlasWidth + column] / 65535f;
                if (Mathf.Abs(alternative - light.z) <= MaxAtlasDepthTolerance) alternativeAgreementCount++;

                // Green agrees, blue is occluded by something nearer the light, magenta
                // is a strongly-lit pixel whose own texel AND its 2x2 neighbourhood sit
                // behind the visible surface (a caster missing from the atlas), dark red
                // is the same situation at grazing incidence, yellow an empty texel.
                Color mark = stored == 0f ? Color.yellow
                    : agrees ? Color.green
                    : error > 0f ? new Color(0.2f, 0.4f, 1f)
                    : stronglyLit && best > MaxAtlasDepthTolerance ? Color.magenta
                    : new Color(0.4f, 0f, 0f);
                image[pixel] = mark;
            }

            public void Finish()
            {
                if (errors.Count == 0) return;
                errors.Sort();
                float[] marks = { 0.01f, 0.05f, 0.25f, 0.50f, 0.75f, 0.95f, 0.99f };
                for (int i = 0; i < marks.Length; i++)
                    percentiles[i] = errors[Mathf.Min(errors.Count - 1, (int)(errors.Count * marks[i]))];
            }
        }

        static Vector3 WorldPoint(EndfieldCharacterShadowProjection.LightBox box, Vector3 light)
        {
            return box.right * (box.min.x + light.x * box.Extent.x)
                 + box.up * (box.min.y + light.y * box.Extent.y)
                 + box.towardLight * (box.min.z + light.z * box.Extent.z);
        }

        // Mirrors the shipped compute: GBuffer0 is R10G10B10A2_UNORM repacked into one
        // uint, and the official reads log2(pack) - 8 as the slot. 258 is the measured
        // frame-6411 value for the slot-0 character.
        static uint PackCharacterIndex(NativeArray<float> raw, int pixel)
        {
            uint x = (uint)(raw[pixel * 4] * 1023f + 0.5f);
            uint y = (uint)(raw[pixel * 4 + 1] * 1023f + 0.5f);
            uint z = (uint)(raw[pixel * 4 + 2] * 1023f + 0.5f);
            uint w = (uint)(raw[pixel * 4 + 3] * 3f + 0.5f);
            return (w << 30) | (z << 20) | (y << 10) | x;
        }

        public static Vector3 DecodeNormalOctahedralY(Vector2 encoded)
        {
            float z = 1f - (Mathf.Abs(encoded.x) + Mathf.Abs(encoded.y));
            var n = new Vector3(encoded.x, z, encoded.y);
            if (z < 0f)
            {
                float signX = n.x >= 0f ? 1f : -1f;
                float signZ = n.z >= 0f ? 1f : -1f;
                n = new Vector3((1f - Mathf.Abs(n.z)) * signX, n.y, (1f - Mathf.Abs(n.x)) * signZ);
            }
            return n.normalized;
        }

        public static Vector2 EncodeNormalOctahedralY(Vector3 direction)
        {
            float l1 = Mathf.Abs(direction.x) + Mathf.Abs(direction.y) + Mathf.Abs(direction.z);
            if (l1 < 1e-12f) throw new ArgumentException("Cannot octahedrally encode " + direction);
            Vector3 d = direction / l1;
            if (d.y >= 0f) return new Vector2(d.x, d.z);
            float signX = d.x >= 0f ? 1f : -1f;
            float signZ = d.z >= 0f ? 1f : -1f;
            return new Vector2((1f - Mathf.Abs(d.z)) * signX, (1f - Mathf.Abs(d.x)) * signZ);
        }

        static float MaxRelativeError(Matrix4x4 expected, Matrix4x4 actual)
        {
            float worst = 0f;
            for (int i = 0; i < 16; i++)
            {
                float e = expected[i], a = actual[i];
                float error = Mathf.Abs(e - a) / Mathf.Max(1f, Mathf.Abs(e));
                if (error > worst) worst = error;
            }
            return worst;
        }

        static float Fraction(int part, int total)
        {
            return total == 0 ? 0f : (float)part / total;
        }

        // Fraction of source pixels that have any target pixel within DilationPixels
        // (Chebyshev). Used both ways so neither population can hide outside the other.
        static int CountCovered(bool[] source, bool[] target)
        {
            int covered = 0;
            for (int row = 0; row < Height; row++)
            {
                for (int col = 0; col < Width; col++)
                {
                    if (!source[row * Width + col]) continue;
                    bool found = false;
                    for (int dy = -DilationPixels; dy <= DilationPixels && !found; dy++)
                    {
                        int r = row + dy;
                        if (r < 0 || r >= Height) continue;
                        for (int dx = -DilationPixels; dx <= DilationPixels; dx++)
                        {
                            int c = col + dx;
                            if (c >= 0 && c < Width && target[r * Width + c]) { found = true; break; }
                        }
                    }
                    if (found) covered++;
                }
            }
            return covered;
        }

        static double Mean(double sum, int total)
        {
            return total == 0 ? 0.0 : sum / total;
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

        static void Require(bool condition, string message)
        {
            if (!condition) throw new InvalidOperationException(message);
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
    }
}
