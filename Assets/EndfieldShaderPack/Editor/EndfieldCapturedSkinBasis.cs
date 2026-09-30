using System;
using System.Collections.Generic;
using System.IO;
using Newtonsoft.Json.Linq;
using UnityEngine;

namespace EndfieldShaderPack.EditorTools
{
    // Diagnostic-only source rows: never save to a material/scene or use as a
    // frozen animation basis. A live adapter needs independently verified rest
    // frame/root-bone semantics, which are not inferred from a single capture.
    public static class EndfieldCapturedSkinBasis
    {
        public static void ApplyIfRequested(Transform root, List<string> report)
        {
            string path = Environment.GetEnvironmentVariable("ENDFIELD_CAPTURED_SKIN_BASIS");
            if (string.IsNullOrEmpty(path)) return;
            var capture = JObject.Parse(File.ReadAllText(path));
            if ((int?)capture["frame"] != 6411) throw new InvalidDataException("Skin basis is reviewed only for frame6411.");
            var prepared = new List<(SkinnedMeshRenderer renderer, int slot, Vector4[] rows)>();
            foreach (string part in new[] { "face", "body", "iris", "hair" })
            {
                var basis = capture["parts"]?[part] as JObject;
                if ((string)basis?["source"] != "skin-root-buffer" || (((int?)basis?["flags"] ?? 0) & 16) == 0)
                    throw new InvalidDataException("Missing skin root rows for " + part);
                var values = basis["rows_local_origin"] as JArray;
                if (values == null || values.Count != 3) throw new InvalidDataException("Invalid skin row count.");
                var rows = new Vector4[3];
                for (int row = 0; row < 3; row++)
                {
                    var components = values[row] as JArray;
                    if (components == null || components.Count != 4) throw new InvalidDataException("Invalid skin row width.");
                    for (int column = 0; column < 4; column++)
                    {
                        float value = (float)components[column];
                        if (float.IsNaN(value) || float.IsInfinity(value)) throw new InvalidDataException("Non-finite skin root row.");
                        rows[row][column] = value;
                    }
                }
                int found = 0;
                foreach (var renderer in root.GetComponentsInChildren<SkinnedMeshRenderer>())
                {
                    if (!renderer.name.EndsWith("_" + part + "_01_lod0", StringComparison.Ordinal)) continue;
                    found++;
                    for (int slot = 0; slot < renderer.sharedMaterials.Length; slot++)
                    {
                        var material = renderer.sharedMaterials[slot];
                        if (material == null || !material.HasProperty("_EndfieldSkinBasisEnabled")
                            || material.GetFloat("_MaterialFamily") != (part == "iris" ? 3 : part == "hair" ? 2 : 1))
                            throw new InvalidDataException("Skin basis renderer has unexpected material: " + renderer.name);
                        prepared.Add((renderer, slot, rows));
                    }
                }
                if (found != 1) throw new InvalidDataException(part + ": expected exactly one visible renderer.");
            }
            foreach (var item in prepared)
            {
                var block = new MaterialPropertyBlock();
                item.renderer.GetPropertyBlock(block, item.slot);
                block.SetFloat("_EndfieldSkinBasisEnabled", 1);
                for (int row = 0; row < 3; row++) block.SetVector("_EndfieldSkinBasisRow" + row, item.rows[row]);
                item.renderer.SetPropertyBlock(block, item.slot);
            }
            report.Add("diagnostic captured skin root basis applied from " + Path.GetFullPath(path));
        }
    }
}
