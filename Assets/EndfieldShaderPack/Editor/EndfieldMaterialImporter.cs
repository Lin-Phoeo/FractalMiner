// ============================================================
//  EndfieldMaterialImporter.cs
//  从终末地 material JSON (M_actor_*.json) 一键重建 Unity 材质，
//  并把纹理/float/color 按游戏原始数值 1:1 写入 Endfield/CharacterLit。
//  菜单：
//    Endfield / Build Typhoeus Materials From JSON   —— 重建 .mat
//    Endfield / Assign Typhoeus Materials To Model   —— 重映射到 FBX
// ============================================================
using System;
using System.Collections.Generic;
using System.Globalization;
using System.IO;
using System.Linq;
using UnityEditor;
using UnityEngine;
using UnityEngine.Rendering;

namespace EndfieldShaderPack
{
    public static class EndfieldMaterialImporter
    {
        const string ModelDir = "Assets/Typhoeus";
        const string MaterialJsonDir = ModelDir + "/Materials";
        const string FbxPath = ModelDir + "/chr_0034_typhoea_uimodel.fbx";
        const string ShaderName = "Endfield/CharacterLit";
        static readonly HashSet<string> DataTextureSlots = new HashSet<string>
        {
            "_BumpMap", "_SplitNormalMap", "_MetallicGlossMap", "_SDFLightmap",
            "_SDFMask", "_OutlineMask", "_LineMap", "_HairBrowMask", "_ClearCoatMask"
        };

        [MenuItem("Endfield/Repair Packed Texture Imports")]
        public static void RepairPackedTextureImports()
        {
            var texMap = BuildTextureMap();
            var paths = new HashSet<string>();
            foreach (var path in Directory.GetFiles(Full(MaterialJsonDir), "*.json"))
            {
                var root = MiniJson.Parse(File.ReadAllText(path)) as Dictionary<string, object>;
                if (root == null || !root.TryGetValue("m_SavedProperties", out var properties)) continue;
                var saved = properties as Dictionary<string, object>;
                if (saved == null || !saved.TryGetValue("m_TexEnvs", out var environments)) continue;
                foreach (var entry in (Dictionary<string, object>)environments)
                {
                    if (!DataTextureSlots.Contains(entry.Key)) continue;
                    var env = entry.Value as Dictionary<string, object>;
                    if (env == null || !env.TryGetValue("m_Texture", out var textureObject)) continue;
                    var texture = textureObject as Dictionary<string, object>;
                    if (texture == null || !texture.TryGetValue("Name", out var name)) continue;
                    if (texMap.TryGetValue(name as string ?? "", out var asset)) paths.Add(AssetDatabase.GetAssetPath(asset));
                }
            }
            int changed = 0;
            foreach (string path in paths)
            {
                var importer = AssetImporter.GetAtPath(path) as TextureImporter;
                if (importer == null) continue;
                if (importer.textureType == TextureImporterType.Default && !importer.sRGBTexture
                    && importer.textureCompression == TextureImporterCompression.Uncompressed && !importer.alphaIsTransparency) continue;
                // Keep raw channels: HN contains TWO normal maps, and P is data.
                importer.textureType = TextureImporterType.Default;
                importer.sRGBTexture = false;
                importer.alphaIsTransparency = false;
                importer.textureCompression = TextureImporterCompression.Uncompressed;
                importer.SaveAndReimport();
                changed++;
            }
            Debug.Log($"[Endfield] Packed textures verified={paths.Count}, repaired={changed}");
        }

        [MenuItem("Endfield/Build Typhoeus Materials From JSON")]
        public static void BuildMaterialsFromJson()
        {
            Shader shader = Shader.Find(ShaderName);
            if (shader == null)
            {
                Debug.LogError("[Endfield] 找不到 shader: " + ShaderName);
                return;
            }

            Dictionary<string, Texture2D> texMap = BuildTextureMap();
            string[] jsonPaths = Directory.GetFiles(Full(MaterialJsonDir), "*.json");
            if (jsonPaths.Length == 0)
            {
                Debug.LogWarning("[Endfield] Materials 目录下没有 json 文件: " + MaterialJsonDir);
                return;
            }

            int created = 0, updated = 0;
            foreach (string jsonPath in jsonPaths)
            {
                string json = File.ReadAllText(jsonPath);
                object rootObj = MiniJson.Parse(json);
                var root = rootObj as Dictionary<string, object>;
                if (root == null) continue;

                string matName = root.TryGetValue("m_Name", out var n) ? n as string : Path.GetFileNameWithoutExtension(jsonPath);
                if (string.IsNullOrEmpty(matName)) matName = Path.GetFileNameWithoutExtension(jsonPath);

                Material mat = LoadOrCreateMaterial(matName, shader);
                bool isNew = false;
                if (mat == null) { Debug.LogError("[Endfield] 无法创建材质: " + matName); continue; }

                // 已存在则更新，新建则标记
                string matAssetPath = MaterialJsonDir + "/" + matName + ".mat";
                if (AssetDatabase.LoadAssetAtPath<Material>(matAssetPath) == null) isNew = true;

                ApplyJsonToMaterial(mat, root, texMap);
                if (mat.HasProperty("_MaterialFamily"))
                    mat.SetFloat("_MaterialFamily", matName.Contains("hair_01") ? 2 : matName.Contains("iris") ? 3
                        : (matName.Contains("face") || matName.Contains("body")) ? 1 : 0);
                ConfigureUrpRenderState(mat);

                if (isNew)
                {
                    AssetDatabase.CreateAsset(mat, matAssetPath);
                    created++;
                }
                else
                {
                    EditorUtility.SetDirty(mat);
                    updated++;
                }
            }

            AssetDatabase.SaveAssets();
            AssetDatabase.Refresh();
            Debug.Log($"[Endfield] 材质重建完成：新建 {created}，更新 {updated}。");
        }

        [MenuItem("Endfield/Assign Typhoeus Materials To Model")]
        public static void AssignMaterialsToModel()
        {
            if (!File.Exists(Full(FbxPath)))
            {
                Debug.LogWarning("[Endfield] 找不到 FBX: " + FbxPath);
                return;
            }

            Dictionary<string, Material> built = LoadBuiltMaterials();
            if (built.Count == 0)
            {
                Debug.LogWarning("[Endfield] 未找到已构建材质，请先执行 Build Typhoeus Materials From JSON。");
                return;
            }

            var importer = AssetImporter.GetAtPath(FbxPath) as ModelImporter;
            if (importer == null)
            {
                Debug.LogError("[Endfield] FBX importer 不可用: " + FbxPath);
                return;
            }

            var srcMats = AssetDatabase.LoadAllAssetsAtPath(FbxPath)
                .Where(a => a is Material)
                .Cast<Material>();

            int remapped = 0;
            var unmatched = new List<string>();
            foreach (Material src in srcMats)
            {
                if (built.TryGetValue(src.name, out Material target))
                {
                    importer.AddRemap(
                        new AssetImporter.SourceAssetIdentifier(typeof(Material), src.name),
                        target);
                    remapped++;
                }
                else
                {
                    unmatched.Add(src.name);
                }
            }

            importer.SaveAndReimport();
            AssetDatabase.SaveAssets();
            Debug.Log($"[Endfield] 重映射材质 {remapped} 个。" +
                      (unmatched.Count > 0 ? " 未匹配: " + string.Join(", ", unmatched) : ""));
        }

        [MenuItem("Endfield/Build & Assign Typhoeus (Full)")]
        public static void BuildAndAssign()
        {
            BuildMaterialsFromJson();
            AssignMaterialsToModel();
        }

        // ----------------------------------------------------------

        static void ApplyJsonToMaterial(Material mat, Dictionary<string, object> root, Dictionary<string, Texture2D> texMap)
        {
            if (!root.TryGetValue("m_SavedProperties", out var spObj) || !(spObj is Dictionary<string, object> saved))
                return;

            // 纹理
            if (saved.TryGetValue("m_TexEnvs", out var teObj) && teObj is Dictionary<string, object> texEnvs)
            {
                foreach (var kv in texEnvs)
                {
                    if (!PropertyIs(mat, kv.Key, ShaderPropertyType.Texture)) continue;
                    if (!(kv.Value is Dictionary<string, object> texEnv)) continue;
                    if (!texEnv.TryGetValue("m_Texture", out var tObj) || !(tObj is Dictionary<string, object> mTex)) continue;

                    bool isNull = mTex.TryGetValue("IsNull", out var nObj) && nObj is bool b && b;
                    string texName = mTex.TryGetValue("Name", out var nameObj) ? nameObj as string : "";
                    if (isNull || string.IsNullOrEmpty(texName)) continue;

                    if (texMap.TryGetValue(texName, out Texture2D tex))
                    {
                        mat.SetTexture(kv.Key, tex);

                        if (texEnv.TryGetValue("m_Scale", out var scObj) && scObj is Dictionary<string, object> sc)
                            mat.SetTextureScale(kv.Key, new Vector2(AsFloat(sc, "X"), AsFloat(sc, "Y")));
                        if (texEnv.TryGetValue("m_Offset", out var ofObj) && ofObj is Dictionary<string, object> of)
                            mat.SetTextureOffset(kv.Key, new Vector2(AsFloat(of, "X"), AsFloat(of, "Y")));
                    }
                    else
                    {
                        Debug.LogWarning($"[Endfield] 纹理缺失: {texName}");
                    }
                }
            }

            // 单值 float
            if (saved.TryGetValue("m_Floats", out var fObj) && fObj is Dictionary<string, object> floats)
            {
                foreach (var kv in floats)
                {
                    // ClearCoatMask, for example, has stale float AND texture entries.
                    if (!PropertyIs(mat, kv.Key, ShaderPropertyType.Float, ShaderPropertyType.Range)) continue;
                    if (kv.Value is double d)
                        mat.SetFloat(kv.Key, (float)d);
                    else if (kv.Value is long l)
                        mat.SetFloat(kv.Key, (float)l);
                    else if (kv.Value is float f)
                        mat.SetFloat(kv.Key, f);
                }
            }

            // 颜色
            if (saved.TryGetValue("m_Colors", out var cObj) && cObj is Dictionary<string, object> colors)
            {
                foreach (var kv in colors)
                {
                    if (kv.Value is Dictionary<string, object> c)
                    {
                        var value = new Vector4(AsFloat(c, "r"), AsFloat(c, "g"), AsFloat(c, "b"), AsFloat(c, "a"));
                        if (PropertyIs(mat, kv.Key, ShaderPropertyType.Vector)) mat.SetVector(kv.Key, value);
                        else if (PropertyIs(mat, kv.Key, ShaderPropertyType.Color)) mat.SetColor(kv.Key, value);
                    }
                }
            }
        }

        static bool PropertyIs(Material material, string name, params ShaderPropertyType[] types)
        {
            int index = material.shader.FindPropertyIndex(name);
            return index >= 0 && Array.IndexOf(types, material.shader.GetPropertyType(index)) >= 0;
        }

        // HGRP's Equal depth test depends on its own depth prepass. This URP
        // forward shader must write and test its own depth.
        public static void ConfigureUrpRenderState(Material mat)
        {
            mat.SetFloat("_ZTest", (float)UnityEngine.Rendering.CompareFunction.LessEqual);
            bool transparent = mat.GetFloat("_SurfaceType") > 0.5f;
            mat.SetFloat("_ZWrite", transparent ? 0f : 1f);
            if (!transparent)
            {
                mat.SetFloat("_SrcBlend", (float)UnityEngine.Rendering.BlendMode.One);
                mat.SetFloat("_DstBlend", (float)UnityEngine.Rendering.BlendMode.Zero);
                mat.SetFloat("_AlphaSrcBlend", (float)UnityEngine.Rendering.BlendMode.One);
                mat.SetFloat("_AlphaDstBlend", (float)UnityEngine.Rendering.BlendMode.Zero);
            }
            mat.renderQueue = transparent ? (int)RenderQueue.Transparent
                : mat.GetFloat("_EnableAlphaTest") > 0.5f ? (int)RenderQueue.AlphaTest : (int)RenderQueue.Geometry;
            mat.SetOverrideTag("RenderType", transparent ? "Transparent" : "Opaque");
            mat.SetShaderPassEnabled("SRPDefaultUnlit", mat.GetFloat("_EnableOutline") > 0.5f);
            EditorUtility.SetDirty(mat);
        }

        static float AsFloat(Dictionary<string, object> map, string key)
        {
            if (map.TryGetValue(key, out var v))
            {
                if (v is double d) return (float)d;
                if (v is long l) return (float)l;
                if (v is float f) return f;
            }
            return 0f;
        }

        static Material LoadOrCreateMaterial(string name, Shader shader)
        {
            string path = MaterialJsonDir + "/" + name + ".mat";
            var existing = AssetDatabase.LoadAssetAtPath<Material>(path);
            if (existing != null) return existing;
            return new Material(shader) { name = name };
        }

        static Dictionary<string, Texture2D> BuildTextureMap()
        {
            var map = new Dictionary<string, Texture2D>(StringComparer.OrdinalIgnoreCase);
            foreach (string guid in AssetDatabase.FindAssets("t:Texture2D", new[] { ModelDir }))
            {
                string p = AssetDatabase.GUIDToAssetPath(guid);
                var tex = AssetDatabase.LoadAssetAtPath<Texture2D>(p);
                if (tex != null)
                    map[Path.GetFileNameWithoutExtension(p)] = tex;
            }
            return map;
        }

        static Dictionary<string, Material> LoadBuiltMaterials()
        {
            var map = new Dictionary<string, Material>(StringComparer.OrdinalIgnoreCase);
            foreach (string guid in AssetDatabase.FindAssets("t:Material", new[] { MaterialJsonDir }))
            {
                string p = AssetDatabase.GUIDToAssetPath(guid);
                var m = AssetDatabase.LoadAssetAtPath<Material>(p);
                if (m != null) map[m.name] = m;
            }
            return map;
        }

        static string Full(string assetPath)
        {
            return Path.Combine(Application.dataPath, assetPath.Substring("Assets/".Length))
                .Replace('/', Path.DirectorySeparatorChar);
        }
    }

    // ------------------------------------------------------------
    // 极简 JSON 解析器 (仅支持本导出文件所需的对象/数组/字符串/数值/布尔/null)
    // ------------------------------------------------------------
    internal static class MiniJson
    {
        public static object Parse(string s)
        {
            int i = 0;
            object v = ParseValue(s, ref i);
            return v;
        }

        static void SkipWs(string s, ref int i)
        {
            while (i < s.Length && char.IsWhiteSpace(s[i])) i++;
        }

        static object ParseValue(string s, ref int i)
        {
            SkipWs(s, ref i);
            if (i >= s.Length) return null;
            char c = s[i];
            switch (c)
            {
                case '{': return ParseObject(s, ref i);
                case '[': return ParseArray(s, ref i);
                case '"': return ParseString(s, ref i);
                default:
                    if (c == 't' && Match(s, i, "true")) { i += 4; return true; }
                    if (c == 'f' && Match(s, i, "false")) { i += 5; return false; }
                    if (c == 'n' && Match(s, i, "null")) { i += 4; return null; }
                    return ParseNumber(s, ref i);
            }
        }

        static bool Match(string s, int i, string word)
        {
            return i + word.Length <= s.Length && s.Substring(i, word.Length) == word;
        }

        static object ParseNumber(string s, ref int i)
        {
            int start = i;
            while (i < s.Length)
            {
                char c = s[i];
                if ("-+.eE0123456789".IndexOf(c) < 0) break;
                i++;
            }
            // 可能有超大 PathID 整型，统一按 double 容错解析
            string num = s.Substring(start, i - start);
            if (double.TryParse(num, NumberStyles.Float, CultureInfo.InvariantCulture, out double d))
                return d;
            return 0.0;
        }

        static string ParseString(string s, ref int i)
        {
            i++; // 跳过开引号
            var sb = new System.Text.StringBuilder();
            while (i < s.Length)
            {
                char c = s[i];
                if (c == '\\') { i++; if (i < s.Length) { sb.Append(s[i]); i++; } continue; }
                if (c == '"') { i++; break; }
                sb.Append(c);
                i++;
            }
            return sb.ToString();
        }

        static Dictionary<string, object> ParseObject(string s, ref int i)
        {
            i++; // {
            var map = new Dictionary<string, object>();
            SkipWs(s, ref i);
            if (i < s.Length && s[i] == '}') { i++; return map; }
            while (i < s.Length)
            {
                SkipWs(s, ref i);
                string key = ParseString(s, ref i);
                SkipWs(s, ref i);
                i++; // :
                object val = ParseValue(s, ref i);
                map[key] = val;
                SkipWs(s, ref i);
                if (i < s.Length && s[i] == ',') { i++; continue; }
                if (i < s.Length && s[i] == '}') { i++; break; }
            }
            return map;
        }

        static List<object> ParseArray(string s, ref int i)
        {
            i++; // [
            var list = new List<object>();
            SkipWs(s, ref i);
            if (i < s.Length && s[i] == ']') { i++; return list; }
            while (i < s.Length)
            {
                list.Add(ParseValue(s, ref i));
                SkipWs(s, ref i);
                if (i < s.Length && s[i] == ',') { i++; continue; }
                if (i < s.Length && s[i] == ']') { i++; break; }
            }
            return list;
        }
    }
}
