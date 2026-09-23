// ============================================================
//  CoralCoastOutfit.cs  v4
//  把珊瑚海岸 mod 的贴图套到现有提弗洛斯模型上。
//
//  ★★ 图集布局实测结论（Tools/compare_atlas_layout.py，见 Validation/atlas_compare_*.png）：
//    - hair  : 官方 2K vs mod 2K，布局一致 → 换贴图生效（粉发已验证）
//    - face  : 官方 1K vs mod 2K，布局一致 → 换贴图生效
//    - iris  : 布局一致 → 生效
//    - body  : 官方 512 vs mod 8K 四象限（左上=皮肤/右上=新衣/左下=手细节/右下=靴袜）
//              mod 重排了 UV → 官方 mesh UV 采样必乱码（皮肤象限可试 ST 重映射，见菜单④）
//    - cloth : 官方 2K vs mod 8K 密集网格，布局完全不同 → 官方 mesh + mod 贴图这条路不可行
//  ⇒ 珊瑚海岸是整套重制模型（288k 顶点）+ 自制图集，忠实还原必须重建 mod mesh。
//
//  匹配策略 v4：按 SMR 当前材质名匹配（剥 _CoralCoast 后缀），不再依赖 SMR 名推断。
//    这样 eyeshadow（当前材质 M_eyewhiteshadow_common_01）也能正确命中。
//
//  菜单：
//    ① 生成珊瑚海岸材质并套用（安全集：hair/face/brow/eyeshadow/iris）
//    ② 恢复默认时装材质
//    ③ 诊断材质绑定
//    ④ 实验：身体皮肤 ST 重映射套用（mod 图集皮肤象限 ≈ 官方布局 ×0.5，未必精确）
// ============================================================
using UnityEditor;
using UnityEngine;
using System.IO;
using System.Text;
using System.Linq;

namespace EndfieldShaderPack
{
    public static class CoralCoastOutfit
    {
        const string TexDir    = "Assets/Typhoeus/CoralCoast";
        const string MatDir    = "Assets/Typhoeus/Materials/CoralCoast";
        const string DefMatDir = "Assets/Typhoeus/Materials";
        const string RootName  = "chr_0034_typhoea_rebuilt";

        // 安全集：UV 布局已验证与官方一致
        // (mod 贴图文件名, 目标材质名, Unity 贴图槽, 需启用的 toggle)
        static readonly (string file, string mat, string slot, string toggle)[] SafeMapping =
        {
            // C3 is the face; C13/C14 are brow draws. C0/2/10 use the accessory atlas.
            ("Components-3-13-14 t=6b12e27e BC7-sRGB.png", "M_actor_typhoea_face_01", "_BaseMap", null),
            ("Components-3-13-14 t=6b12e27e BC7-sRGB.png", "M_actor_typhoea_brow_01", "_BaseMap", null),
            // hair（albedo + LightMap→PBR mask）
            ("Components-1 t=637eee72 BC7-sRGB.png",   "M_actor_typhoea_hair_01", "_BaseMap",          null),
            ("Components-1 t=61e8a38a BC7-Linear.png", "M_actor_typhoea_hair_01", "_MetallicGlossMap", "_UseMetallicGlossMap"),
            // iris
            ("Components-6 t=9d83f226 BC7-sRGB.png",   "M_actor_typhoea_iris_01", "_BaseMap",          null),
        };

        // 实验集：body 皮肤象限（mod 8K 图集左上 1/4 ≈ 官方 512 布局 ×0.5）
        static readonly (string file, string slot, string toggle, Vector2 scale, Vector2 offset)[] BodyMapping =
        {
            ("Components-4 t=57b75235 BC7-sRGB.png",   "_BaseMap", null,          new Vector2(0.5f, 0.5f), new Vector2(0f, 0.5f)),
            ("Components-4 t=e5439823 BC5-Linear.png",  "_BumpMap", "_UseBumpMap", new Vector2(0.5f, 0.5f), new Vector2(0f, 0.5f)),
        };

        /// <summary>SMR 当前材质名（剥掉 _CoralCoast 后缀）。</summary>
        static string CurMatKey(SkinnedMeshRenderer smr)
        {
            var m = smr.sharedMaterial;
            if (m == null) return null;
            string n = m.name;
            if (n.EndsWith("_CoralCoast")) n = n.Substring(0, n.Length - "_CoralCoast".Length);
            return n;
        }

        /// <summary>SMR 名 → 材质 key（兜底用）。S_→M_，去 _lod0。</summary>
        static string SmrToMatKey(string smrName)
        {
            string n = smrName.Replace("_lod0", "").Replace("_LOD0", "");
            if (n.StartsWith("S_")) n = "M_" + n.Substring(2);
            return n;
        }

        static Material GetOrCreateCoralMat(string matName)
        {
            string ccMatPath = $"{MatDir}/{matName}_CoralCoast.mat";
            Material ccMat = AssetDatabase.LoadAssetAtPath<Material>(ccMatPath);
            if (ccMat != null) return ccMat;
            Material srcMat = AssetDatabase.LoadAssetAtPath<Material>($"{DefMatDir}/{matName}.mat");
            if (srcMat == null) return null;
            ccMat = new Material(srcMat);
            ccMat.name = matName + "_CoralCoast";
            AssetDatabase.CreateAsset(ccMat, ccMatPath);
            return ccMat;
        }

        static void ApplyToggle(Material mat, string toggle)
        {
            if (toggle == null || !mat.HasProperty(toggle)) return;
            mat.SetFloat(toggle, 1f);
            if (toggle == "_UseBumpMap")          mat.EnableKeyword("_NORMALMAP");
            if (toggle == "_UseMetallicGlossMap") mat.EnableKeyword("_METALLICSPECGLOSSMAP");
            if (toggle == "_UseEmission")         mat.EnableKeyword("_EMISSION");
        }

        static GameObject FindRoot()
        {
            var root = GameObject.Find(RootName);
            if (root == null)
            {
                var scene = UnityEngine.SceneManagement.SceneManager.GetActiveScene();
                Debug.LogError($"[珊瑚海岸] 当前场景「{scene.name}」找不到 {RootName}。请先 Endfield/Setup Typhoeus Showcase Scene。");
            }
            return root;
        }

        [MenuItem("Endfield/珊瑚海岸/① 生成珊瑚海岸材质并套用（安全集）", false, 200)]
        public static void Apply()
        {
            if (!AssetDatabase.IsValidFolder(MatDir))
                AssetDatabase.CreateFolder("Assets/Typhoeus/Materials", "CoralCoast");

            var root = FindRoot();
            if (root == null) return;

            // 1. 创建/更新安全集材质
            int created = 0, skipped = 0;
            var matLog = new StringBuilder("--- 材质创建（安全集）---");
            foreach (var (file, matName, slot, toggle) in SafeMapping)
            {
                Texture tex = AssetDatabase.LoadAssetAtPath<Texture>($"{TexDir}/{file}");
                if (tex == null) { Debug.LogWarning($"[珊瑚海岸] 找不到贴图 {file}，跳过"); skipped++; continue; }

                Material ccMat = GetOrCreateCoralMat(matName);
                if (ccMat == null) { Debug.LogWarning($"[珊瑚海岸] 找不到源材质 {matName}，跳过"); skipped++; continue; }

                ccMat.SetTexture(slot, tex);
                ccMat.SetTextureScale(slot, new Vector2(1, -1));
                ccMat.SetTextureOffset(slot, new Vector2(0, 1));
                ApplyToggle(ccMat, toggle);
                EditorUtility.SetDirty(ccMat);
                created++;
            }
            AssetDatabase.SaveAssets();
            Debug.Log($"[珊瑚海岸] 材质绑定：{created} 条创建/更新，{skipped} 条跳过。\n{matLog}");

            // 2. 按「当前材质名」套到 SMR
            var smrs = root.GetComponentsInChildren<SkinnedMeshRenderer>(true);
            int applied = 0, unmatched = 0;
            var smrLog = new StringBuilder($"--- SMR 套用（共 {smrs.Length} 个）---");
            foreach (var smr in smrs)
            {
                string matKey = CurMatKey(smr) ?? SmrToMatKey(smr.name);
                // C7 has no texture override in the mod. Repair the old face-atlas
                // substitution and do not apply unrelated cached experimental materials.
                if (matKey == "M_eyewhiteshadow_common_01")
                {
                    var original = AssetDatabase.LoadAssetAtPath<Material>($"{DefMatDir}/{matKey}.mat");
                    if (original != null) smr.sharedMaterials = Enumerable.Repeat(original, smr.sharedMaterials.Length).ToArray();
                    continue;
                }
                if (!SafeMapping.Any(binding => binding.mat == matKey)) continue;
                Material ccMat = AssetDatabase.LoadAssetAtPath<Material>($"{MatDir}/{matKey}_CoralCoast.mat");
                if (ccMat != null)
                {
                    var mats = smr.sharedMaterials;
                    for (int i = 0; i < mats.Length; i++) mats[i] = ccMat;
                    smr.sharedMaterials = mats;
                    applied++;
                    smrLog.AppendLine($"\n  ✅ {smr.name} ← {matKey}_CoralCoast");
                }
                else { unmatched++; smrLog.AppendLine($"\n  ⬜ {smr.name} → {matKey}（无珊瑚海岸材质，保持官方）"); }
            }
            EditorUtility.SetDirty(root);
            AssetDatabase.SaveAssets();
            Debug.Log($"[珊瑚海岸] 已套用 {applied} 个 SMR，{unmatched} 个保持官方。\n{smrLog}");
            Debug.Log("[珊瑚海岸] cloth/body 官方 mesh 的 UV 与 mod 图集不兼容（见 Validation/atlas_compare_*.png），已排除。");
        }

        [MenuItem("Endfield/珊瑚海岸/② 恢复默认时装材质", false, 201)]
        public static void Revert()
        {
            var root = FindRoot();
            if (root == null) return;
            var smrs = root.GetComponentsInChildren<SkinnedMeshRenderer>(true);
            int reverted = 0, unmatched = 0;
            var log = new StringBuilder($"--- 恢复默认（共 {smrs.Length} 个）---");
            foreach (var smr in smrs)
            {
                string matKey = CurMatKey(smr) ?? SmrToMatKey(smr.name);
                Material defMat = AssetDatabase.LoadAssetAtPath<Material>($"{DefMatDir}/{matKey}.mat");
                if (defMat != null)
                {
                    var mats = smr.sharedMaterials;
                    for (int i = 0; i < mats.Length; i++) mats[i] = defMat;
                    smr.sharedMaterials = mats;
                    reverted++;
                    log.AppendLine($"\n  ✅ {smr.name} ← {matKey}");
                }
                else { unmatched++; log.AppendLine($"\n  ⬜ {smr.name} → {matKey}（无默认材质文件）"); }
            }
            EditorUtility.SetDirty(root);
            AssetDatabase.SaveAssets();
            Debug.Log($"[珊瑚海岸] 已恢复 {reverted} 个 SMR，{unmatched} 个无匹配。\n{log}");
        }

        [MenuItem("Endfield/珊瑚海岸/③ 诊断材质绑定", false, 202)]
        public static void Diagnose()
        {
            var root = FindRoot();
            if (root == null) return;
            var smrs = root.GetComponentsInChildren<SkinnedMeshRenderer>(true);
            var sb = new StringBuilder();
            sb.AppendLine($"# Coral Coast material diagnosis — {System.DateTime.Now:yyyy-MM-dd HH:mm:ss}");
            sb.AppendLine($"# total SMRs = {smrs.Length}\n");
            sb.AppendLine("SMR名\t当前材质\t匹配key\t珊瑚海岸材质\t默认材质");
            sb.AppendLine(new string('-', 100));
            foreach (var smr in smrs)
            {
                string matKey = CurMatKey(smr) ?? SmrToMatKey(smr.name);
                string curMat = smr.sharedMaterial != null ? smr.sharedMaterial.name : "(null)";
                bool ccExists  = File.Exists($"{MatDir}/{matKey}_CoralCoast.mat");
                bool defExists = File.Exists($"{DefMatDir}/{matKey}.mat");
                sb.AppendLine($"{smr.name}\t{curMat}\t{matKey}\t{(ccExists ? "YES" : "NO")}\t{(defExists ? "YES" : "NO")}");
            }
            Directory.CreateDirectory("Validation");
            File.WriteAllText("Validation/coral_coast_diagnosis.txt", sb.ToString());
            Debug.Log($"[珊瑚海岸] 诊断完成，已写入 Validation/coral_coast_diagnosis.txt\n{sb}");
        }

        // ---------- ④ 实验：body 皮肤象限 ST 重映射 ----------
        [MenuItem("Endfield/珊瑚海岸/④ 实验：身体皮肤 ST 重映射套用", false, 203)]
        public static void ApplyBodyExperimental()
        {
            if (!AssetDatabase.IsValidFolder(MatDir))
                AssetDatabase.CreateFolder("Assets/Typhoeus/Materials", "CoralCoast");

            var root = FindRoot();
            if (root == null) return;

            const string matName = "M_actor_typhoea_body_01";
            Material ccMat = GetOrCreateCoralMat(matName);
            if (ccMat == null) { Debug.LogError($"[珊瑚海岸] 找不到源材质 {matName}"); return; }

            foreach (var (file, slot, toggle, scale, offset) in BodyMapping)
            {
                Texture tex = AssetDatabase.LoadAssetAtPath<Texture>($"{TexDir}/{file}");
                if (tex == null) { Debug.LogWarning($"[珊瑚海岸] 找不到贴图 {file}"); continue; }
                ccMat.SetTexture(slot, tex);
                ccMat.SetTextureScale(slot, scale);
                ccMat.SetTextureOffset(slot, offset);
                ApplyToggle(ccMat, toggle);
            }
            EditorUtility.SetDirty(ccMat);
            AssetDatabase.SaveAssets();

            // 只套到 body SMR
            int applied = 0;
            foreach (var smr in root.GetComponentsInChildren<SkinnedMeshRenderer>(true))
            {
                string key = CurMatKey(smr) ?? SmrToMatKey(smr.name);
                if (key != matName) continue;
                var mats = smr.sharedMaterials;
                for (int i = 0; i < mats.Length; i++) mats[i] = ccMat;
                smr.sharedMaterials = mats;
                applied++;
            }
            Debug.Log($"[珊瑚海岸-实验] body 已套用 {applied} 个 SMR（ST scale=0.5,0.5 offset=0,0.5）。" +
                      "若皮肤仍乱码，说明 mod 皮肤象限布局与官方不完全一致 → 请点 ② 恢复。");
        }
    }
}
