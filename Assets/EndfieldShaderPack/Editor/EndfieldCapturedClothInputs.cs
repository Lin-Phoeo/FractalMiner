using System;
using System.Collections.Generic;
using System.IO;
using UnityEditor;
using UnityEngine;

namespace EndfieldShaderPack
{
    // Local private payloads stay outside Assets/Git. Manifest is pinned after
    // offline actual-draw/view/sampler/per-mip verification, not hand-authored.
    [InitializeOnLoad]
    public static class EndfieldCapturedClothInputs
    {
        public const string ManifestSha256 = "37b3fb48aaef2eb0d8d6e9359f8e116065fc25ae449d6b2b93471a1f543dde0f";
        public const string DefaultExport = "Validation/Captures/native-cloth-inputs-20261001-02";
        public static string Source => Environment.GetEnvironmentVariable("ENDFIELD_CLOTH_NATIVE_EXPORT")
            ?? Path.GetFullPath(Path.Combine(Application.dataPath, "../" + DefaultExport));
        static Bundle active;
        static EndfieldCapturedClothInputs()
        {
            AssemblyReloadEvents.beforeAssemblyReload += Restore;
            EditorApplication.quitting += Restore;
            EditorApplication.playModeStateChanged += _ => Restore();
            UnityEditor.SceneManagement.EditorSceneManager.sceneClosing += (_, __) => Restore();
        }

        public readonly struct NativeSample
        {
            public readonly int mip, x, y;
            public readonly Color rgba;
            internal NativeSample(int level, int u, int v, Color value) { mip = level; x = u; y = v; rgba = value; }
        }
        public sealed class Bundle : IDisposable
        {
            public Texture2D Cloth01 { get; private set; }
            public Texture2D Cloth02 { get; private set; }
            EndfieldCapturedClothNormals.Binding binding;
            readonly List<NativeSample>[] samples;
            internal Bundle(Texture2D first, Texture2D second, List<NativeSample>[] capturedSamples)
            { Cloth01 = first; Cloth02 = second; samples = capturedSamples; }
            public IReadOnlyList<NativeSample> NativeSamples(int material) => samples[material].AsReadOnly();
            public int SlotCount => binding?.SlotCount ?? 0;
            public void Bind(Transform root, bool preserveLaterChanges = false)
            {
                if (binding != null) throw new InvalidOperationException("Bundle already bound; restore before rebinding.");
                binding = EndfieldCapturedClothNormals.Bind(root, Cloth01, Cloth02, preserveLaterChanges);
            }
            public void Dispose()
            {
                binding?.Dispose(); binding = null;
                EndfieldCapturedClothNormals.Release(Cloth01); EndfieldCapturedClothNormals.Release(Cloth02);
                Cloth01 = Cloth02 = null;
            }
        }

        public static Bundle Load(string folder = null)
        {
            folder = Path.GetFullPath(folder ?? Source);
            byte[] manifest = File.ReadAllBytes(Path.Combine(folder, "complete.json"));
            if (EndfieldCapturedClothNormals.Hash(manifest) != ManifestSha256)
                throw new InvalidDataException("Unreviewed native cloth manifest; do not auto-trust a new capture.");
            var parsed = (Dictionary<string, object>)MiniJson.Parse(System.Text.Encoding.UTF8.GetString(manifest));
            if ((string)parsed["status"] != "ok" || Convert.ToInt32(parsed["frame"]) != 6411)
                throw new InvalidDataException("Native cloth capture not complete.");
            var entries = (List<object>)parsed["textures"];
            if (entries.Count != 2) throw new InvalidDataException("Expected two reviewed cloth inputs.");
            byte[][] payloads = new byte[2][];
            var samples = new List<NativeSample>[2];
            string[] hashes = { EndfieldCapturedClothNormals.Cloth01Hash, EndfieldCapturedClothNormals.Cloth02Hash };
            for (int i = 0; i < entries.Count; i++)
            {
                var entry = (Dictionary<string, object>)entries[i];
                string expected = "cloth0" + (i + 1) + ".bc5";
                if ((string)entry["file"] != expected || (string)entry["sha256"] != hashes[i])
                    throw new InvalidDataException("Unexpected cloth payload path/identity.");
                payloads[i] = File.ReadAllBytes(Path.Combine(folder, expected));
                if (payloads[i].Length != EndfieldCapturedClothNormals.PayloadBytes || EndfieldCapturedClothNormals.Hash(payloads[i]) != hashes[i])
                    throw new InvalidDataException("Native BC5 payload checksum/size mismatch: " + expected);
                samples[i] = new List<NativeSample>();
                foreach (Dictionary<string, object> value in (List<object>)entry["native_samples"])
                {
                    var rgba = (List<object>)value["rgba"];
                    samples[i].Add(new NativeSample(Convert.ToInt32(value["mip"]), Convert.ToInt32(value["x"]), Convert.ToInt32(value["y"]),
                        new Color(Convert.ToSingle(rgba[0]), Convert.ToSingle(rgba[1]), Convert.ToSingle(rgba[2]), Convert.ToSingle(rgba[3]))));
                }
                if (samples[i].Count != 60) throw new InvalidDataException("Incomplete captured native sample evidence.");
            }
            Texture2D first = null, second = null;
            try
            {
                first = EndfieldCapturedClothNormals.CreateTexture(payloads[0], hashes[0], "CapturedCloth01NormalBC5");
                second = EndfieldCapturedClothNormals.CreateTexture(payloads[1], hashes[1], "CapturedCloth02NormalBC5");
                return new Bundle(first, second, samples);
            }
            catch { EndfieldCapturedClothNormals.Release(first); EndfieldCapturedClothNormals.Release(second); throw; }
        }

        public static Bundle BindIfRequested(Transform root, List<string> report)
        {
            if (Environment.GetEnvironmentVariable("ENDFIELD_CLOTH_NATIVE_INPUTS") != "1") return null;
            var bundle = Load();
            try
            {
                bundle.Bind(root);
                report?.Add("verified native BC5 Cloth01/02 normals; original 12 mips; captured bilinear Repeat/mip-point sampler; slots=" + bundle.SlotCount);
                return bundle;
            }
            catch { bundle.Dispose(); throw; }
        }

        [MenuItem("Endfield/Captured Inputs/Bind native cloth normals (selected character, memory only)")]
        public static void BindSelected()
        {
            var root = Selection.activeTransform;
            if (root == null) throw new InvalidOperationException("Select the Typhoeus character root in the Hierarchy.");
            while (root.parent != null && root.name != "chr_0034_typhoea_rebuilt") root = root.parent;
            Restore();
            var bundle = Load();
            try { bundle.Bind(root, preserveLaterChanges: true); active = bundle; }
            catch { bundle.Dispose(); throw; }
            Debug.Log("Native cloth normals bound in memory only: " + active.SlotCount + " slots. No scene/material/import writes.");
        }

        [MenuItem("Endfield/Captured Inputs/Restore native cloth normals")]
        public static void Restore() { active?.Dispose(); active = null; }
    }
}
