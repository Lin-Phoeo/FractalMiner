using System;
using System.Collections.Generic;
using System.Globalization;
using System.IO;
using System.Security.Cryptography;
using UnityEditor;
using UnityEngine;

namespace EndfieldShaderPack
{
    // Local-only import of the frame-6411 character self-shadow evidence produced by
    // Tools/capture_character_shadow_evidence.py. Every file is checksum-verified
    // against its manifest before it is copied, so a partial or stale export cannot
    // be mistaken for evidence. Never edits original game or user assets.
    public static class EndfieldCharacterShadowAssets
    {
        public const string Root = EndfieldCaptureAssets.Root + "/CharacterShadow";
        public const string DefaultExport =
            "Validation/Captures/tifuluosi-front-20260917/character-shadow-01";
        public const string DefaultConstants =
            "Validation/Captures/tifuluosi-front-20260917/character-shadow-constants-02";

        public const int AtlasWidth = 4096;
        public const int AtlasHeight = 2048;
        public const int FrameWidth = 2560;
        public const int FrameHeight = 1600;
        public const int Slots = 15;

        public static readonly string[] TextureNames =
        {
            "character-shadow-atlas", "gbuffer0-character-index", "gbuffer1-normal",
            "camera-depth", "screen-shadow-resolved"
        };

        static string Resolve(string variable, string fallback)
        {
            string value = Environment.GetEnvironmentVariable(variable);
            if (!string.IsNullOrEmpty(value)) return value;
            return Path.GetFullPath(Path.Combine(Application.dataPath, "../" + fallback));
        }

        public static string Source => Resolve("ENDFIELD_CHARACTER_SHADOW_EXPORT", DefaultExport);
        public static string ConstantsSource => Resolve("ENDFIELD_CHARACTER_SHADOW_CONSTANTS", DefaultConstants);

        public sealed class Constants
        {
            public Matrix4x4[] worldToShadow = new Matrix4x4[Slots];
            public Vector4[] biases = new Vector4[Slots];
            public Vector4[] lightDir = new Vector4[Slots];
            public Vector4[] atlasParams = new Vector4[Slots];
            public Vector4 texelSize;
            public Vector4 parameters;
            public Matrix4x4 invViewProj;
            public Matrix4x4 viewProj;
            public Vector4 cameraPos;
            public Vector4 screenSize;
            public int validSlots;
        }

        public static void ImportAll()
        {
            VerifyManifest(Source);
            Directory.CreateDirectory(Root);
            foreach (string name in TextureNames) ImportEXR(name);
            AssetDatabase.SaveAssets();
            Debug.Log("[CharacterShadow] Imported 5 checksum-verified frame-6411 textures: atlas as filterable R16_UNORM, the four Load-only inputs as uncompressed RGBAFloat.");
        }

        static void VerifyManifest(string folder)
        {
            string completePath = Path.Combine(folder, "complete.json");
            if (!File.Exists(completePath))
                throw new InvalidDataException("Missing " + completePath +
                    "; run Tools/capture_character_shadow_evidence.py against the frame-6411 capture first.");
            var complete = (Dictionary<string, object>)MiniJson.Parse(File.ReadAllText(completePath));
            if ((string)complete["status"] != "ok" || Convert.ToInt32(complete["frame"]) != 6411)
                throw new InvalidDataException("Export is not a completed frame-6411 export.");
            if (Convert.ToInt32(complete["event"]) != 748)
                throw new InvalidDataException("Export is not from the character resolve event 748.");
            int checkedFiles = 0;
            foreach (Dictionary<string, object> texture in (List<object>)complete["textures"])
                foreach (Dictionary<string, object> file in (List<object>)texture["files"])
                {
                    string name = (string)file["file"];
                    if (Path.GetFileName(name) != name) throw new InvalidDataException("Unsafe manifest filename.");
                    string source = Path.Combine(folder, name);
                    if (!File.Exists(source)) throw new InvalidDataException("Manifest lists a missing file: " + name);
                    using (var hash = SHA256.Create())
                    using (var stream = File.OpenRead(source))
                    {
                        string actual = BitConverter.ToString(hash.ComputeHash(stream)).Replace("-", "").ToLowerInvariant();
                        if (actual != (string)file["sha256"] || new FileInfo(source).Length != Convert.ToInt64(file["bytes"]))
                            throw new InvalidDataException("Export checksum/size mismatch: " + name);
                    }
                    checkedFiles++;
                }
            if (checkedFiles == 0)
                throw new InvalidDataException("Manifest verified no files; this looks like a constants-only export." +
                    " Point ENDFIELD_CHARACTER_SHADOW_EXPORT at the full export directory.");
        }

        static void ImportEXR(string name)
        {
            string path = Root + "/" + name + ".exr";
            File.Copy(Path.Combine(Source, name + ".exr"), path, true);
            AssetDatabase.ImportAsset(path, ImportAssetOptions.ForceSynchronousImport);
            var importer = (TextureImporter)AssetImporter.GetAtPath(path);
            importer.textureType = TextureImporterType.Default;
            importer.textureShape = TextureImporterShape.Texture2D;
            importer.sRGBTexture = false;
            importer.mipmapEnabled = false;
            importer.isReadable = true;
            importer.alphaIsTransparency = false;
            importer.alphaSource = TextureImporterAlphaSource.FromInput;
            importer.npotScale = TextureImporterNPOTScale.None;
            importer.maxTextureSize = 4096;
            importer.textureCompression = TextureImporterCompression.Uncompressed;
            importer.filterMode = FilterMode.Bilinear;
            // The atlas is addressed with an inline sampler_LinearMirror in the resolve
            // shader, which governs at sample time; Mirror here keeps the importer
            // consistent with that instead of silently disagreeing.
            importer.wrapMode = name == "character-shadow-atlas" ? TextureWrapMode.Mirror : TextureWrapMode.Clamp;
            var platform = importer.GetPlatformTextureSettings("Standalone");
            platform.overridden = true;
            platform.maxTextureSize = 4096;
            // The atlas is the only texture the resolve shader *samples* (SampleLevel
            // and GatherRed through sampler_LinearMirror); the other four are read
            // with Load, which needs no filtering.
            //
            // 128-bit float is Load/Store only on D3D11, so RGBAFloat cannot be
            // sampled or gathered -- the same capability wall this project already hit
            // with R11G11B10 during the bloom work. The atlas comes from a D16 target,
            // so R16_UNORM is both filterable and bit-exact against the source, while
            // RGBAFloat for the Load-only textures keeps their wider channels lossless.
            platform.format = name == "character-shadow-atlas"
                ? TextureImporterFormat.R16
                : TextureImporterFormat.RGBAFloat;
            importer.SetPlatformTextureSettings(platform);
            importer.SaveAndReimport();
        }

        public static Texture2D Texture(string name) =>
            AssetDatabase.LoadAssetAtPath<Texture2D>(Root + "/" + name + ".exr");

        public static Constants LoadConstants()
        {
            string path = Path.Combine(ConstantsSource, "constants.json");
            if (!File.Exists(path))
                throw new InvalidDataException("Missing " + path +
                    "; run the exporter in constants mode against the frame-6411 capture first.");
            var root = (Dictionary<string, object>)MiniJson.Parse(File.ReadAllText(path));
            if (Convert.ToInt32(root["event"]) != 748)
                throw new InvalidDataException("Constants are not from the character resolve event 748.");
            var constants = (Dictionary<string, object>)root["constants"];
            var transform = (Dictionary<string, object>)root["transform"];

            var result = new Constants();
            var worldToShadow = (List<object>)constants["characterWorldToShadow"];
            var biases = (List<object>)constants["characterShadowBiases"];
            var lightDir = (List<object>)constants["characterShadowLightDir"];
            var atlasParams = (List<object>)constants["characterShadowAtlasParams"];
            if (worldToShadow.Count != Slots || biases.Count != Slots ||
                lightDir.Count != Slots || atlasParams.Count != Slots)
                throw new InvalidDataException("Expected " + Slots + " entries in every character shadow array.");
            for (int i = 0; i < Slots; i++)
            {
                result.worldToShadow[i] = MatrixFromFlat(ToFloats(worldToShadow[i]), "characterWorldToShadow[" + i + "]");
                result.biases[i] = VectorFrom(ToFloats(biases[i]), "characterShadowBiases[" + i + "]");
                result.lightDir[i] = VectorFrom(ToFloats(lightDir[i]), "characterShadowLightDir[" + i + "]");
                result.atlasParams[i] = VectorFrom(ToFloats(atlasParams[i]), "characterShadowAtlasParams[" + i + "]");
            }
            result.texelSize = VectorFrom(ToFloats(((List<object>)constants["characterShadowTexelSize"])[0]), "texelSize");
            result.parameters = VectorFrom(ToFloats(((List<object>)constants["characterShadowParams"])[0]), "params");
            result.invViewProj = MatrixFromFlat(ToFloats(((List<object>)transform["invViewProjMatrix"])[0]), "invViewProjMatrix");
            result.cameraPos = VectorFrom(ToFloats(((List<object>)transform["worldSpaceCameraPos"])[0]), "cameraPos");
            result.screenSize = VectorFrom(ToFloats((List<object>)root["screen_size"]), "screenSize");
            result.viewProj = result.invViewProj.inverse;
            result.validSlots = (int)result.parameters.z;

            if (result.validSlots < 1 || result.validSlots > Slots)
                throw new InvalidDataException("CharacterShadowParams.z = " + result.validSlots +
                    " is not a usable slot count (expected 1.." + Slots + ").");
            if ((int)result.screenSize.x != FrameWidth || (int)result.screenSize.y != FrameHeight)
                throw new InvalidDataException("ScreenSize " + result.screenSize +
                    " does not match the " + FrameWidth + "x" + FrameHeight + " resolve target.");
            return result;
        }

        // The capture stores float4x4 column-major: floats 4j..4j+3 are column j.
        // Unity's Matrix4x4 constructor also takes columns, so this is a direct
        // mapping and mul(M, v) in HLSL then matches the official pass.
        static Matrix4x4 MatrixFromFlat(List<float> f, string label)
        {
            if (f.Count != 16) throw new InvalidDataException(label + " must have 16 floats, got " + f.Count);
            return new Matrix4x4(
                new Vector4(f[0], f[1], f[2], f[3]),
                new Vector4(f[4], f[5], f[6], f[7]),
                new Vector4(f[8], f[9], f[10], f[11]),
                new Vector4(f[12], f[13], f[14], f[15]));
        }

        static Vector4 VectorFrom(List<float> f, string label)
        {
            if (f.Count != 4) throw new InvalidDataException(label + " must have 4 floats, got " + f.Count);
            return new Vector4(f[0], f[1], f[2], f[3]);
        }

        static List<float> ToFloats(object value)
        {
            var result = new List<float>();
            foreach (object item in (List<object>)value)
                result.Add(Convert.ToSingle(item, CultureInfo.InvariantCulture));
            return result;
        }

        [MenuItem("Endfield/Import Character Shadow Evidence", false, 70)]
        public static void ImportFromMenu() => ImportAll();
    }
}
