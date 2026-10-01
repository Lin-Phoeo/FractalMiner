using System;
using System.Collections.Generic;
using System.IO;
using UnityEngine;

namespace EndfieldShaderPack
{
    public static class EndfieldCapturedClothMaterialInputs
    {
        public const string ManifestSha256 = "325b1baea5838c66002566a5c2b020f976c3d015a5633d7a4642b6c0be610383";
        public const string DefaultExport = "Validation/Captures/native-cloth-materials-20261001-02";
        public static string Source => Environment.GetEnvironmentVariable("ENDFIELD_CLOTH_MATERIAL_EXPORT")
            ?? Path.GetFullPath(Path.Combine(Application.dataPath, "../" + DefaultExport));
        public readonly struct Sample
        {
            public readonly int Mip, X, Y;
            public readonly Color Rgba;
            internal Sample(int mip, int x, int y, Color value) { Mip = mip; X = x; Y = y; Rgba = value; }
        }
        public sealed class Bundle : IDisposable
        {
            readonly Texture2D[] textures;
            readonly List<Sample>[] samples;
            readonly EndfieldCapturedClothInputs.Bundle normals;
            EndfieldCapturedClothMaterials.Binding binding;
            bool disposed;
            public IReadOnlyList<Texture2D> Textures => Array.AsReadOnly(textures);
            public IReadOnlyList<Sample> NativeSamples(int index) => samples[index].AsReadOnly();
            public int SlotCount => binding?.SlotCount ?? 0;
            internal Bundle(Texture2D[] maps, List<Sample>[] evidence, EndfieldCapturedClothInputs.Bundle normalInputs)
            { textures = maps; samples = evidence; normals = normalInputs; }
            public void Bind(Transform root)
            {
                if (disposed || binding != null) throw new InvalidOperationException("Disposed/already bound captured material bundle.");
                EndfieldCapturedClothMaterials.ValidateTextures(textures);
                // s4 is associated with BumpMap in the production shader. Reuse
                // verified native normal textures in the SAME ownership scope.
                binding = EndfieldCapturedClothMaterials.Bind(root, textures, normals.Cloth01, normals.Cloth02);
            }
            public void Dispose()
            {
                if (disposed) return; disposed = true;
                binding?.Dispose(); binding = null; normals.Dispose();
                foreach (var texture in textures) EndfieldCapturedClothNormals.Release(texture);
            }
        }
        public static Bundle Load(string folder = null)
        {
            folder = Path.GetFullPath(folder ?? Source);
            byte[] manifest = File.ReadAllBytes(Path.Combine(folder, "complete.json"));
            if (EndfieldCapturedClothNormals.Hash(manifest) != ManifestSha256)
                throw new InvalidDataException("Unreviewed native cloth materials manifest.");
            var parsed = (Dictionary<string, object>)MiniJson.Parse(System.Text.Encoding.UTF8.GetString(manifest));
            if ((string)parsed["status"] != "ok" || Convert.ToInt32(parsed["frame"]) != 6411) throw new InvalidDataException("Incomplete material capture.");
            var entries = (List<object>)parsed["textures"];
            if (entries.Count != 9) throw new InvalidDataException("Nine draw bindings / seven images expected.");
            var payloads = new byte[7][]; var samples = new List<Sample>[7];
            for (int i = 0; i < 7; i++)
            {
                var spec = EndfieldCapturedClothMaterials.Specs[i]; Dictionary<string, object> entry = null;
                foreach (Dictionary<string, object> candidate in entries)
                    if (Convert.ToInt32(candidate["event"]) == spec.Event && (string)candidate["role"] == spec.Role)
                    { if (entry != null) throw new InvalidDataException("Duplicate material evidence."); entry = candidate; }
                if (entry == null || (string)entry["file"] != spec.File || (string)entry["sha256"] != spec.Hash
                    || (string)entry["sample_cast"] != (spec.Srgb ? "CompType.UNormSRGB" : "CompType.UNorm"))
                    throw new InvalidDataException("Unexpected payload path/identity/view sample domain.");
                payloads[i] = File.ReadAllBytes(Path.Combine(folder, spec.File));
                if (payloads[i].Length != spec.Bytes || EndfieldCapturedClothNormals.Hash(payloads[i]) != spec.Hash)
                    throw new InvalidDataException("Native material payload changed: " + spec.File);
                samples[i] = new List<Sample>();
                foreach (Dictionary<string, object> value in (List<object>)entry["native_samples"])
                {
                    var rgba = (List<object>)value["rgba"];
                    samples[i].Add(new Sample(Convert.ToInt32(value["mip"]), Convert.ToInt32(value["x"]), Convert.ToInt32(value["y"]),
                        new Color(Convert.ToSingle(rgba[0]), Convert.ToSingle(rgba[1]), Convert.ToSingle(rgba[2]), Convert.ToSingle(rgba[3]))));
                }
                if (samples[i].Count != spec.Mips * 5) throw new InvalidDataException("Incomplete native sample evidence.");
            }
            var maps = new Texture2D[7]; EndfieldCapturedClothInputs.Bundle normals = null;
            try
            {
                for (int i = 0; i < maps.Length; i++) maps[i] = EndfieldCapturedClothMaterials.CreateTexture(i, payloads[i]);
                normals = EndfieldCapturedClothInputs.Load();
                return new Bundle(maps, samples, normals);
            }
            catch { normals?.Dispose(); foreach (var texture in maps) EndfieldCapturedClothNormals.Release(texture); throw; }
        }
        public static Bundle BindIfRequested(Transform root, List<string> report)
        {
            if (Environment.GetEnvironmentVariable("ENDFIELD_CLOTH_NATIVE_MATERIALS") != "1") return null;
            var bundle = Load();
            try
            {
                bundle.Bind(root);
                report?.Add("native captured cloth D/P/E + shared Diff/Spec ramps + native normals; sRGB RGB / linear alpha; unchanged source formulas; slots=" + bundle.SlotCount);
                return bundle;
            }
            catch { bundle.Dispose(); throw; }
        }
    }
}
