using System;
using System.Collections.Generic;
using System.IO;
using System.Security.Cryptography;
using UnityEditor;
using UnityEngine;

namespace EndfieldShaderPack
{
    // Reproducible, local-only imports; never edits original game or user assets.
    public static class EndfieldCaptureAssets
    {
        public const string Root = "Assets/EndfieldShaderPack/GeneratedCapture";
        public const string DefaultExport = "Validation/Captures/tifuluosi-front-20260917/pipeline-textures-01";
        public static string Source => Environment.GetEnvironmentVariable("ENDFIELD_PIPELINE_EXPORT")
            ?? Path.GetFullPath(Path.Combine(Application.dataPath, "../" + DefaultExport));

        public static void ImportAll()
        {
            var complete = (Dictionary<string, object>)MiniJson.Parse(File.ReadAllText(Path.Combine(Source, "complete.json")));
            if ((string)complete["status"] != "ok" || Convert.ToInt32(complete["frame"]) != 6411)
                throw new InvalidDataException("Export is not a completed frame-6411 export.");
            foreach (Dictionary<string, object> texture in (List<object>)complete["textures"])
                foreach (Dictionary<string, object> file in (List<object>)texture["files"])
                {
                    string name = (string)file["file"];
                    if (Path.GetFileName(name) != name) throw new InvalidDataException("Unsafe manifest filename.");
                    string source = Path.Combine(Source, name);
                    using (var hash = SHA256.Create())
                    using (var stream = File.OpenRead(source))
                    {
                        string actual = BitConverter.ToString(hash.ComputeHash(stream)).Replace("-", "").ToLowerInvariant();
                        if (actual != (string)file["sha256"] || new FileInfo(source).Length != Convert.ToInt64(file["bytes"]))
                            throw new InvalidDataException("Export checksum/size mismatch: " + name);
                    }
                }
            Directory.CreateDirectory(Root);
            foreach (string name in new[] { "grading-lut", "post-input", "bloom", "post-output", "screen-shadow" })
                ImportEXR(name);
            for (int face = 0; face < 6; face++) ImportEXR("character-environment-face" + face);
            ImportCube();
            AssetDatabase.SaveAssets();
            Debug.Log("[CaptureAssets] Imported verified linear EXR and original BC6H cube with all 8 captured mips.");
        }

        public static void ImportBloomEvidence()
        {
            string folder=Environment.GetEnvironmentVariable("ENDFIELD_BLOOM_EXPORT")
                ?? Path.GetFullPath(Path.Combine(Application.dataPath,"../Validation/Captures/tifuluosi-front-20260917/bloom-evidence-01"));
            var complete=(Dictionary<string,object>)MiniJson.Parse(File.ReadAllText(Path.Combine(folder,"complete.json")));
            if((string)complete["status"]!="ok" || Convert.ToInt32(complete["frame"])!=6411
                || ((List<object>)complete["events"]).Count!=17)
                throw new InvalidDataException("Expected complete 17-event frame-6411 bloom export.");
            Directory.CreateDirectory(Root);
            foreach(Dictionary<string,object> ev in (List<object>)complete["events"])
                foreach(Dictionary<string,object> file in (List<object>)ev["files"])
                {
                    string name=(string)file["file"];
                    if(Path.GetFileName(name)!=name)throw new InvalidDataException("Unsafe bloom filename.");
                    using(var hash=SHA256.Create())
                    using(var stream=File.OpenRead(Path.Combine(folder,name)))
                    {
                        string actual=BitConverter.ToString(hash.ComputeHash(stream)).Replace("-","").ToLowerInvariant();
                        if(actual!=(string)file["sha256"] || stream.Length!=Convert.ToInt64(file["bytes"]))
                            throw new InvalidDataException("Bloom checksum/size mismatch: "+name);
                    }
                    if(name.EndsWith(".exr",StringComparison.Ordinal))ImportEXR(Path.GetFileNameWithoutExtension(name),folder);
                }
        }

        static void ImportEXR(string name,string sourceFolder=null)
        {
            string path = Root + "/" + name + ".exr";
            File.Copy(Path.Combine(sourceFolder ?? Source, name + ".exr"), path, true);
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
            importer.wrapMode = TextureWrapMode.Clamp;
            var platform = importer.GetPlatformTextureSettings("Standalone");
            platform.overridden = true; platform.maxTextureSize = 4096;
            platform.format = TextureImporterFormat.RGBAFloat;
            importer.SetPlatformTextureSettings(platform);
            importer.SaveAndReimport();
        }

        static uint U32(byte[] bytes, int offset) => BitConverter.ToUInt32(bytes, offset);

        static void ImportCube()
        {
            byte[] bytes = File.ReadAllBytes(Path.Combine(Source, "character-environment.dds"));
            // DDS + DDS_HEADER + DDS_HEADER_DXT10; source is BC6H_UF16.
            if (bytes.Length < 148 || U32(bytes,0) != 0x20534444 || U32(bytes,4) != 124
                || U32(bytes,12) != 128 || U32(bytes,16) != 128 || U32(bytes,28) != 8
                || U32(bytes,84) != 0x30315844 || U32(bytes,128) != 95
                || U32(bytes,132) != 3 || (U32(bytes,136) & 4) == 0 || U32(bytes,140) != 1)
                throw new InvalidDataException("Expected single 128x128 BC6H_UF16 DX10 cubemap with 8 mips.");
            if (!SystemInfo.SupportsTextureFormat(TextureFormat.BC6H))
                throw new NotSupportedException("BC6H sampling required; do not silently transcode to LDR.");
            var cube = new Cubemap(128, TextureFormat.BC6H, true)
                { name = "CapturedCharacterEnvironment", filterMode = FilterMode.Trilinear, wrapMode = TextureWrapMode.Clamp };
            try
            {
                int offset = 148;
                for (int face = 0; face < 6; face++)
                    for (int mip = 0; mip < 8; mip++)
                    {
                        int size = Mathf.Max(1, 128 >> mip);
                        int length = Mathf.Max(1, (size+3)/4) * Mathf.Max(1, (size+3)/4) * 16;
                        if (offset + length > bytes.Length) throw new InvalidDataException("Truncated cubemap.");
                        cube.SetPixelData(bytes, mip, (CubemapFace)face, offset);
                        offset += length;
                    }
                if (offset != bytes.Length) throw new InvalidDataException("Unexpected cubemap trailing data.");
                cube.Apply(false, false); // Never regenerate the captured prefiltered mips.
                string path = Root + "/CapturedCharacterEnvironment.asset";
                var existing = AssetDatabase.LoadAssetAtPath<Cubemap>(path);
                if (existing == null) { AssetDatabase.CreateAsset(cube,path); cube=null; }
                else { EditorUtility.CopySerialized(cube,existing); EditorUtility.SetDirty(existing); }
            }
            finally { if (cube != null) UnityEngine.Object.DestroyImmediate(cube); }
        }

        public static Texture2D Texture(string name) => AssetDatabase.LoadAssetAtPath<Texture2D>(Root + "/" + name + ".exr");
        public static Cubemap EnvironmentCube => AssetDatabase.LoadAssetAtPath<Cubemap>(Root + "/CapturedCharacterEnvironment.asset");
    }
}
