using System;
using System.Collections.Generic;
using System.IO;
using System.Text;
using UnityEditor;
using UnityEngine;
using UnityEngine.Rendering;

namespace EndfieldShaderPack
{
    public static class EndfieldMaterialValidation
    {
        [MenuItem("Endfield/Validate Material Data and Capture Channels", false, 52)]
        public static void Run()
        {
            var report = new StringBuilder();
            int floats = 0, vectors = 0, textures = 0, unsupported = 0, staleTypes = 0;
            var unknown = new SortedSet<string>();
            string directory = Path.Combine(Application.dataPath, "Typhoeus/Materials");
            foreach (var path in Directory.GetFiles(directory, "*.json"))
            {
                var source = (Dictionary<string, object>)MiniJson.Parse(File.ReadAllText(path));
                var properties = (Dictionary<string, object>)source["m_SavedProperties"];
                string asset = "Assets/Typhoeus/Materials/" + Path.GetFileNameWithoutExtension(path) + ".mat";
                var material = AssetDatabase.LoadAssetAtPath<Material>(asset);
                if (material == null) throw new InvalidOperationException("Missing material: " + asset);
                foreach (var group in properties)
                {
                    if (!(group.Value is Dictionary<string, object> entries)) continue;
                    foreach (var entry in entries)
                    {
                        int index = material.shader.FindPropertyIndex(entry.Key);
                        if (index < 0) { unsupported++; unknown.Add(group.Key + "/" + entry.Key); continue; }
                        var type = material.shader.GetPropertyType(index);
                        if (group.Key == "m_Floats")
                        {
                            if (type != ShaderPropertyType.Float && type != ShaderPropertyType.Range) { staleTypes++; continue; }
                            // These source render states are intentionally adapted to URP.
                            if (entry.Key == "_ZTest" || entry.Key == "_ZWrite" || entry.Key.Contains("Blend")) continue;
                            float expected = Convert.ToSingle(entry.Value);
                            if (Mathf.Abs(material.GetFloat(entry.Key) - expected) > 0.0001f)
                                throw new InvalidOperationException(asset + " scalar mismatch: " + entry.Key);
                            floats++;
                        }
                        else if (group.Key == "m_Colors")
                        {
                            if (type != ShaderPropertyType.Vector && type != ShaderPropertyType.Color) { staleTypes++; continue; }
                            var c = (Dictionary<string, object>)entry.Value;
                            var expected = new Vector4(Convert.ToSingle(c["r"]), Convert.ToSingle(c["g"]), Convert.ToSingle(c["b"]), Convert.ToSingle(c["a"]));
                            if (Vector4.Distance(material.GetVector(entry.Key), expected) > 0.0001f)
                                throw new InvalidOperationException(asset + " vector mismatch: " + entry.Key);
                            vectors++;
                        }
                        else if (group.Key == "m_TexEnvs")
                        {
                            if (type != ShaderPropertyType.Texture) { staleTypes++; continue; }
                            var env = (Dictionary<string, object>)entry.Value;
                            var texture = (Dictionary<string, object>)env["m_Texture"];
                            string expected = texture["Name"] as string;
                            if (string.IsNullOrEmpty(expected)) continue;
                            var actual = material.GetTexture(entry.Key);
                            if (actual == null || actual.name != expected)
                                throw new InvalidOperationException(asset + " texture mismatch: " + entry.Key);
                            textures++;
                            if (entry.Key == "_MetallicGlossMap" || entry.Key == "_SplitNormalMap" || entry.Key == "_BumpMap")
                            {
                                var importer = (TextureImporter)AssetImporter.GetAtPath(AssetDatabase.GetAssetPath(actual));
                                if (importer.sRGBTexture || importer.textureType != TextureImporterType.Default
                                    || importer.textureCompression != TextureImporterCompression.Uncompressed)
                                    throw new InvalidOperationException("Packed channels not preserved: " + expected);
                            }
                        }
                    }
                }
            }
            report.AppendLine($"PASS declared source values: scalars={floats}, colors/vectors={vectors}, bound textures={textures}");
            report.AppendLine($"Ignored obsolete cross-type entries={staleTypes}; unsupported source entries={unsupported}");
            report.AppendLine("Unsupported entries below are NOT an assertion that these features are restored:");
            foreach (string name in unknown) report.AppendLine(name);
            Directory.CreateDirectory(Path.Combine(Application.dataPath, "../Validation"));
            File.WriteAllText(Path.Combine(Application.dataPath, "../Validation/material-report.txt"), report.ToString());
            CaptureChannels();
            Debug.Log(report.ToString().Split('\n')[0]);
        }

        static void CaptureChannels()
        {
            var root = GameObject.Find("chr_0034_typhoea_rebuilt");
            if (root == null) throw new InvalidOperationException("Open the showcase first");
            var renderers = root.GetComponentsInChildren<SkinnedMeshRenderer>();
            var originals = new Dictionary<SkinnedMeshRenderer, Material[]>();
            var temporary = new List<Material>();
            try
            {
                foreach (var renderer in renderers)
                {
                    originals[renderer] = renderer.sharedMaterials;
                    var copies = renderer.sharedMaterials;
                    for (int i = 0; i < copies.Length; i++)
                    {
                        copies[i] = new Material(copies[i]);
                        copies[i].SetFloat("_EnableOutline", 0);
                        copies[i].SetShaderPassEnabled("SRPDefaultUnlit", false);
                        temporary.Add(copies[i]);
                    }
                    renderer.sharedMaterials = copies;
                }
                string[] names = { "albedo", "normal", "metal-or-strand", "specular-mask", "shadow-mask", "smoothness" };
                for (int view = 1; view <= names.Length; view++)
                {
                    foreach (var material in temporary) material.SetFloat("_DebugView", view);
                    TyphoeusGeometryValidation.SaveImage(Camera.main, "channel-" + names[view-1] + ".png", 1280, 1280);
                }
            }
            finally
            {
                foreach (var entry in originals) entry.Key.sharedMaterials = entry.Value;
                foreach (var material in temporary) UnityEngine.Object.DestroyImmediate(material);
            }
        }
    }
}
