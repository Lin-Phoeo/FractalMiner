using System;
using System.Collections.Generic;
using System.IO;
using System.Linq;
using System.Text.RegularExpressions;
using UnityEditor;
using UnityEngine;
using Object = UnityEngine.Object;

namespace EndfieldShaderPack
{
    // Offline importer. Roles come from vertex/UV comparison with the extracted model.
    public static class CoralCoastMeshImporter
    {
        const string ModDir = @"C:/Users/Administrator/Downloads/Typhoeus-Coral Coast RT.RX07-v1.1-SFW/Typhoeus-Coral Coast RT.RX07-v1.1-SFW";
        const string TexDir = "Assets/Typhoeus/CoralCoast";
        public const string OutDir = "Assets/EndfieldShowcaseRef/CoralCoast_Repaired";
        public const string RootName = "CoralCoast_typhoea_static";
        const string OffMatDir = "Assets/Typhoeus/Materials";
        const string FaceAtlas = "Components-3-13-14 t=6b12e27e BC7-sRGB.png";
        const string AccessoryAtlas = "Components-0-2-10 t=28ef925d BC7-sRGB.png";

        struct Sub { public int count, first; public string tex; }
        static Sub S(int count, int first, string tex) => new Sub { count = count, first = first, tex = tex };
        // Static preset matching the INI defaults: Main=0, Socks=1, other clothing
        // toggles=0. Do not combine mutually exclusive draw ranges.
        static readonly (int comp, Sub[] subs)[] DrawLists =
        {
            (0, new[] { S(5778, 0, "horns") }),
            (1, new[] { S(54816, 0, "hair") }),
            (2, new[] { S(144, 0, "accessory"), S(510, 2496, "accessory"), S(2652, 3006, "accessory"), S(1098, 5658, "accessory") }),
            (3, new[] { S(10686, 0, "face") }),
            (4, new[] { S(5736, 271392, "body"), S(143298, 128094, "body") }),
            (6, new[] { S(618, 0, "iris") }),
            (8, new[] {
                S(186,0,"cloth"), S(8016,186,"cloth"), S(2202,8202,"cloth"), S(83088,171372,"cloth"),
                S(10368,254460,"cloth"), S(33948,264828,"cloth"), S(1140,316344,"cloth"), S(17568,298776,"cloth"),
                S(27462,320412,"cloth"), S(26844,347874,"cloth"), S(77820,374718,"cloth"), S(8682,452538,"cloth"),
                S(40440,461220,"cloth"), S(33138,501660,"cloth"), S(15078,534798,"cloth"), S(16920,549876,"cloth"),
                S(8832,566796,"cloth"), S(5904,575628,"cloth"), S(14688,581532,"cloth"), S(23652,596220,"cloth"),
                S(2928,619872,"cloth"), S(19248,623796,"cloth"), S(28992,643044,"cloth"), S(5016,672036,"cloth"),
                S(29376,677052,"cloth"), S(69168,706428,"cloth"), S(329208,775596,"cloth") }),
            (10, new[] { S(16101, 0, "tail") })
        };

        struct Bind { public string file, slot; }
        static Bind B(string file, string slot) => new Bind { file = file, slot = slot };
        static readonly Dictionary<string, (string tmpl, Bind[] binds)> MatPlans = new Dictionary<string, (string, Bind[])>
        {
            {"horns", ("M_actor_typhoea_cloth_05", new[] { B(AccessoryAtlas, "_BaseMap") })},
            {"accessory", ("M_actor_typhoea_cloth_02", new[] { B(AccessoryAtlas, "_BaseMap") })},
            {"face", ("M_actor_typhoea_face_01", new[] { B(FaceAtlas, "_BaseMap") })},
            {"brow", ("M_actor_typhoea_brow_01", new[] { B(FaceAtlas, "_BaseMap") })},
            {"hair", ("M_actor_typhoea_hair_01", new[] {
                B("Components-1 t=637eee72 BC7-sRGB.png", "_BaseMap"), B("Components-1 t=61e8a38a BC7-Linear.png", "_MetallicGlossMap") })},
            {"iris", ("M_actor_typhoea_iris_01", new[] { B("Components-6 t=9d83f226 BC7-sRGB.png", "_BaseMap") })},
            {"body", ("M_actor_typhoea_body_01", new[] {
                B("Components-4 t=57b75235 BC7-sRGB.png", "_BaseMap"), B("Components-4 t=e5439823 BC5-Linear.png", "_BumpMap") })},
            {"cloth", ("M_actor_typhoea_cloth_01", new[] {
                B("Components-8-9 t=9e71626f BC7-sRGB.png", "_BaseMap"), B("Components-8-9 t=0060974e BC5-Linear.png", "_BumpMap"),
                B("Components-8-9 t=d899f1bd BC7-Linear.png", "_MetallicGlossMap") })},
            {"tail", ("M_actor_typhoea_cloth_04", new[] { B(AccessoryAtlas, "_BaseMap") })}
        };

        static Vector3 Upright(Vector3 raw) => new Vector3(raw.x, raw.z, -raw.y);
        static Vector3 Read3(byte[] data, int o) => new Vector3(BitConverter.ToSingle(data, o), BitConverter.ToSingle(data, o + 4), BitConverter.ToSingle(data, o + 8));
        static bool Finite(float v) => !float.IsNaN(v) && !float.IsInfinity(v);

        internal static string ResourceValue(string ini, string section, string key)
        {
            var block = Regex.Match(ini, @"(?ms)^\[" + Regex.Escape(section) + @"\]\s*\r?\n(.*?)(?=^\[|\z)");
            var value = Regex.Match(block.Groups[1].Value, @"(?m)^" + Regex.Escape(key) + @"\s*=\s*([^\r\n;]+)");
            if (!value.Success) throw new InvalidDataException($"Missing {section}/{key}");
            return value.Groups[1].Value.Trim();
        }

        // Validate buffers and draw ranges before mutating assets. Read index format from INI.
        static Mesh ReadComponent(int comp, Sub[] subs, string ini, Endfield.TyphoeaModelData source)
        {
            int s0 = int.Parse(ResourceValue(ini, $"Resource_Component{comp}_VB0", "stride"));
            int s1 = int.Parse(ResourceValue(ini, $"Resource_Component{comp}_VB1", "stride"));
            string format = ResourceValue(ini, $"Resource_Component{comp}_IB", "format");
            int indexSize = format == "DXGI_FORMAT_R32_UINT" ? 4 : format == "DXGI_FORMAT_R16_UINT" ? 2 : 0;
            if ((s0 != 16 && s0 != 40) || s1 < 8 || indexSize == 0) throw new InvalidDataException($"Unsupported C{comp} layout");
            byte[] vb0 = File.ReadAllBytes($"{ModDir}/Meshes/Component{comp}_VB0.buf");
            byte[] vb1 = File.ReadAllBytes($"{ModDir}/Meshes/Component{comp}_VB1.buf");
            byte[] ib = File.ReadAllBytes($"{ModDir}/Meshes/Component{comp}_IB.buf");
            int count = vb0.Length / s0;
            if (count == 0 || vb0.Length % s0 != 0 || vb1.Length != count * s1 || ib.Length % indexSize != 0)
                throw new InvalidDataException($"C{comp}: buffer size/stride mismatch");
            var vertices = new Vector3[count]; var uv = new Vector2[count];
            var normals = s0 == 40 ? new Vector3[count] : null;
            for (int i = 0; i < count; i++)
            {
                vertices[i] = Upright(Read3(vb0, i * s0));
                uv[i] = new Vector2(BitConverter.ToSingle(vb1, i * s1), BitConverter.ToSingle(vb1, i * s1 + 4));
                if (!Finite(vertices[i].sqrMagnitude) || !Finite(uv[i].sqrMagnitude)) throw new InvalidDataException($"C{comp}: nonfinite vertex {i}");
                if (normals != null) normals[i] = Upright(Read3(vb0, i * s0 + 12)).normalized;
            }
            // Unchanged parts retain artist-authored normals from the verified extraction.
            string original = comp == 0 ? "cloth_05" : comp == 1 ? "hair_01" : comp == 3 ? "face_01" : comp == 6 ? "iris_01" : null;
            if (original != null)
            {
                var reference = source.meshes.Single(m => m.name == $"S_actor_typhoea_{original}_lod0");
                if (reference.vertices.Length != count * 3) throw new InvalidDataException($"C{comp}: reference size mismatch");
                normals = new Vector3[count];
                for (int i = 0; i < count; i++)
                {
                    var p = Upright(new Vector3(reference.vertices[3*i], reference.vertices[3*i+1], reference.vertices[3*i+2]));
                    var u = new Vector2(reference.uvs[2*i], reference.uvs[2*i+1]);
                    if ((p - vertices[i]).magnitude > 1e-5f || (u - uv[i]).magnitude > 1e-5f)
                        throw new InvalidDataException($"C{comp}: reference vertex/UV mismatch at {i}");
                    normals[i] = Upright(new Vector3(reference.normals[3*i], reference.normals[3*i+1], reference.normals[3*i+2]));
                }
            }
            var triangles = new List<int[]>();
            foreach (var sub in subs)
            {
                if (sub.first < 0 || sub.count <= 0 || sub.count % 3 != 0 || (long)sub.first + sub.count > ib.Length / indexSize)
                    throw new InvalidDataException($"C{comp}: draw range {sub.first}+{sub.count} exceeds buffer");
                var indices = new int[sub.count];
                for (int i = 0; i < indices.Length; i++)
                {
                    int o = (sub.first + i) * indexSize;
                    uint index = indexSize == 4 ? BitConverter.ToUInt32(ib, o) : BitConverter.ToUInt16(ib, o);
                    if (index >= count) throw new InvalidDataException($"C{comp}: index {index} exceeds {count}");
                    indices[i] = (int)index;
                }
                triangles.Add(indices);
            }
            return BuildMesh($"CoralCoast_C{comp}", vertices, uv, normals, triangles);
        }

        static Mesh BuildMesh(string name, Vector3[] vertices, Vector2[] uv, Vector3[] normals, List<int[]> triangles)
        {
            var mesh = new Mesh { name = name, indexFormat = vertices.Length > 65535 ? UnityEngine.Rendering.IndexFormat.UInt32 : UnityEngine.Rendering.IndexFormat.UInt16 };
            mesh.vertices = vertices; mesh.uv = uv; mesh.subMeshCount = triangles.Count;
            for (int i = 0; i < triangles.Count; i++) mesh.SetTriangles(triangles[i], i);
            if (normals != null) mesh.normals = normals; else mesh.RecalculateNormals();
            mesh.RecalculateTangents(); mesh.RecalculateBounds();
            return mesh;
        }

        static Mesh ReadOriginalBrow(Endfield.TyphoeaModelData source)
        {
            // C13/C14 have 40-byte VB0 and a different space (gpu_posed=0).
            // Use the combined 638-vertex original brow in C3/C6's verified bind space.
            var m = source.meshes.Single(x => x.name == "S_actor_typhoea_brow_01_lod0");
            int count = m.vertices.Length / 3;
            var v = new Vector3[count]; var n = new Vector3[count]; var uv = new Vector2[count];
            for (int i = 0; i < count; i++)
            {
                v[i] = Upright(new Vector3(m.vertices[3*i], m.vertices[3*i+1], m.vertices[3*i+2]));
                n[i] = Upright(new Vector3(m.normals[3*i], m.normals[3*i+1], m.normals[3*i+2]));
                uv[i] = new Vector2(m.uvs[2*i], m.uvs[2*i+1]);
            }
            return BuildMesh("CoralCoast_Brow", v, uv, n, new List<int[]> { m.indices });
        }

        internal static T Persist<T>(T generated, string path) where T : Object
        {
            T existing = AssetDatabase.LoadAssetAtPath<T>(path);
            if (existing == null) { AssetDatabase.CreateAsset(generated, path); return generated; }
            EditorUtility.CopySerialized(generated, existing);
            Object.DestroyImmediate(generated); EditorUtility.SetDirty(existing);
            return existing;
        }

        static Material BuildPlanMaterial(string key)
        {
            var plan = MatPlans[key];
            var template = AssetDatabase.LoadAssetAtPath<Material>($"{OffMatDir}/{plan.tmpl}.mat");
            var material = new Material(template) { name = $"CoralCoastStatic_{key}" };
            foreach (var b in plan.binds)
            {
                string path = $"{TexDir}/{b.file}";
                var importer = (TextureImporter)AssetImporter.GetAtPath(path);
                bool srgb = b.file.Contains("sRGB");
                if (importer.textureType != TextureImporterType.Default || importer.sRGBTexture != srgb || importer.alphaIsTransparency)
                {
                    importer.textureType = TextureImporterType.Default;
                    importer.sRGBTexture = srgb; importer.alphaIsTransparency = false;
                    importer.SaveAndReimport();
                }
                material.SetTexture(b.slot, AssetDatabase.LoadAssetAtPath<Texture>(path));
                // Flip only DDS-converted textures; retain original UVs for auxiliary maps.
                material.SetTextureScale(b.slot, new Vector2(1, -1));
                material.SetTextureOffset(b.slot, new Vector2(0, 1));
                if (b.slot == "_BumpMap") material.SetFloat("_UseBumpMap", 1);
                if (b.slot == "_MetallicGlossMap") material.SetFloat("_UseMetallicGlossMap", 1);
            }
            EndfieldMaterialImporter.ConfigureUrpRenderState(material);
            return Persist(material, $"{OutDir}/CoralCoastStatic_{key}.mat");
        }

        [MenuItem("Endfield/珊瑚海岸/⑤ 导入 mod 静态模型", false, 204)]
        public static void Import()
        {
            string ini = File.ReadAllText($"{ModDir}/Typhoeus-SFW.ini");
            var source = JsonUtility.FromJson<Endfield.TyphoeaModelData>(File.ReadAllText("Assets/Typhoeus/_typhoea_model_data.json"));
            var meshes = new Dictionary<string, Mesh>(); GameObject replacement = null;
            try
            {
                foreach (var draw in DrawLists) meshes[$"C{draw.comp}"] = ReadComponent(draw.comp, draw.subs, ini, source);
                meshes["Brow"] = ReadOriginalBrow(source);
                foreach (var plan in MatPlans.Values)
                {
                    var template = AssetDatabase.LoadAssetAtPath<Material>($"{OffMatDir}/{plan.tmpl}.mat");
                    if (template == null || template.shader.name != "Endfield/CharacterLit") throw new InvalidDataException($"Missing reconstruction template: {plan.tmpl}");
                    foreach (var b in plan.binds)
                        if (AssetDatabase.LoadAssetAtPath<Texture>($"{TexDir}/{b.file}") == null) throw new FileNotFoundException($"Missing texture: {b.file}");
                }
                if (!AssetDatabase.IsValidFolder(OutDir)) AssetDatabase.CreateFolder("Assets/EndfieldShowcaseRef", "CoralCoast_Repaired");
                var materials = MatPlans.Keys.ToDictionary(k => k, BuildPlanMaterial);
                replacement = new GameObject(RootName + "_building");
                foreach (var draw in DrawLists)
                    AddPart(replacement, $"C{draw.comp}", meshes[$"C{draw.comp}"], draw.subs.Select(s => materials[s.tex]).ToArray());
                AddPart(replacement, "Brow", meshes["Brow"], new[] { materials["brow"] });
                var old = GameObject.Find(RootName);
                if (old != null)
                {
                    replacement.transform.SetParent(old.transform.parent, false);
                    replacement.transform.localPosition = old.transform.localPosition;
                    replacement.transform.localRotation = old.transform.localRotation;
                    replacement.transform.localScale = old.transform.localScale;
                }
                replacement.name = RootName;
                PrefabUtility.SaveAsPrefabAsset(replacement, $"{OutDir}/{RootName}.prefab");
                AssetDatabase.SaveAssets();
                if (old != null) Undo.DestroyObjectImmediate(old);
                Undo.RegisterCreatedObjectUndo(replacement, "Import Coral Coast");
                Debug.Log($"[CoralCoast] Imported {replacement.transform.childCount} parts; C0=horns, C3=face, C6=iris. Original brow restored. No extra face bake required.");
            }
            catch { if (replacement != null) Object.DestroyImmediate(replacement); throw; }
            finally
            {
                foreach (var mesh in meshes.Values)
                    if (mesh != null && !EditorUtility.IsPersistent(mesh)) Object.DestroyImmediate(mesh);
            }
        }

        static void AddPart(GameObject root, string name, Mesh mesh, Material[] materials)
        {
            var go = new GameObject(name); go.transform.SetParent(root.transform, false);
            go.AddComponent<MeshFilter>().sharedMesh = Persist(mesh, $"{OutDir}/{mesh.name}.asset");
            go.AddComponent<MeshRenderer>().sharedMaterials = materials;
        }

        [MenuItem("Endfield/珊瑚海岸/⑦ 校验脸部与眼部（无需烘焙）", false, 206)]
        public static void BakeEyesFromOriginal()
        {
            var root = GameObject.Find(RootName);
            if (root == null || root.transform.Find("C0") == null || root.transform.Find("C3") == null || root.transform.Find("C6") == null)
                throw new InvalidOperationException("请先运行⑤，恢复角、脸和瞳孔。旧版错位烘焙已停用。");
            Debug.Log("[CoralCoast] C0/C3/C6 present. No additional face bake needed.");
        }
    }
}
