// ============================================================
//  CoralCoastOutfit.cs
//  把珊瑚海岸 mod 的贴图套到现有提弗洛斯模型上。
//
//  原理：珊瑚海岸是 EnteleJiang 的换色时装 mod（XXMI 格式），
//  贴图从游戏运行时 RenderDoc 抓帧获得。mod 的 mesh 是 GPU 蒙皮
//  后的高细分数据（顶点数远超官方，且缺 normal/tangent），完整
//  重建 mesh 是多日工程。但**时装通常不改 UV**——所以复用现有
//  官方 mesh，只换贴图即可看到珊瑚海岸配色。
//
//  贴图对应推断（基于 .ini 的 Components-X 命名 + BC 格式 + 尺寸）：
//    Components-4  (8K BC7-sRGB) → body albedo (_BaseMap)
//    Components-4  (8K BC5-Linear) → body normal (_BumpMap)
//    Components-8-9(8K BC7-sRGB) → cloth albedo (_BaseMap)
//    Components-8-9(8K BC5-Linear) → cloth normal (_BumpMap)
//    Components-1  (2K BC7-sRGB) → hair albedo (_BaseMap)
//    Components-0-2-10(2K BC7-sRGB) → face albedo (_BaseMap)
//
//  用法：菜单 Endfield/珊瑚海岸/① 生成珊瑚海岸材质并套用
//  注：贴图对应是推断，可能需要手动微调（在 Inspector 里换贴图槽）。
// ============================================================
using UnityEditor;
using UnityEngine;
using System.IO;

namespace EndfieldShaderPack
{
    public static class CoralCoastOutfit
    {
        const string TexDir = "Assets/Typhoeus/CoralCoast";
        const string MatDir = "Assets/Typhoeus/Materials/CoralCoast";
        const string RootName = "chr_0034_typhoea_rebuilt";

        // mod 贴图 → (官方材质名, 槽位) 对应推断
        // 每条：(mod贴图文件名片段, 官方材质前缀, 槽位)
        static readonly (string fileFragment, string matPrefix, string slot)[] Mapping =
        {
            // body
            ("Components-4 t=57b75235 BC7-sRGB.png",  "M_actor_typhoea_body_01",  "_BaseMap"),
            ("Components-4 t=e5439823 BC5-Linear.png", "M_actor_typhoea_body_01",  "_BumpMap"),
            // cloth_01 / cloth_02（大件衣服共用 8K Atlas）
            ("Components-8-9 t=9e71626f BC7-sRGB.png",  "M_actor_typhoea_cloth_01", "_BaseMap"),
            ("Components-8-9 t=0060974e BC5-Linear.png", "M_actor_typhoea_cloth_01", "_BumpMap"),
            ("Components-8-9 t=9e71626f BC7-sRGB.png",  "M_actor_typhoea_cloth_02", "_BaseMap"),
            ("Components-8-9 t=0060974e BC5-Linear.png", "M_actor_typhoea_cloth_02", "_BumpMap"),
            // hair
            ("Components-1 t=637eee72 BC7-sRGB.png", "M_actor_typhoea_hair_01", "_BaseMap"),
            // face
            ("Components-0-2-10 t=28ef925d BC7-sRGB.png", "M_actor_typhoea_face_01", "_BaseMap"),
        };

        [MenuItem("Endfield/珊瑚海岸/① 生成珊瑚海岸材质并套用", false, 200)]
        public static void Apply()
        {
            if (!AssetDatabase.IsValidFolder(MatDir))
                AssetDatabase.CreateFolder("Assets/Typhoeus/Materials", "CoralCoast");

            var root = GameObject.Find(RootName);
            if (root == null)
            {
                var scene = UnityEngine.SceneManagement.SceneManager.GetActiveScene();
                Debug.LogError($"[珊瑚海岸] 当前场景「{scene.name}」找不到 {RootName}。请先 Endfield/Setup Typhoeus Showcase Scene。");
                return;
            }

            // 1. 为每个官方材质创建珊瑚海岸变体
            int created = 0;
            foreach (var (frag, matPrefix, slot) in Mapping)
            {
                string texPath = $"{TexDir}/{frag}";
                Texture tex = AssetDatabase.LoadAssetAtPath<Texture>(texPath);
                if (tex == null)
                {
                    Debug.LogWarning($"[珊瑚海岸] 找不到贴图 {texPath}，跳过");
                    continue;
                }

                // 复制现有材质
                string srcMatPath = $"Assets/Typhoeus/Materials/{matPrefix}.mat";
                Material srcMat = AssetDatabase.LoadAssetAtPath<Material>(srcMatPath);
                string ccMatPath = $"{MatDir}/{matPrefix}_CoralCoast.mat";

                Material ccMat = AssetDatabase.LoadAssetAtPath<Material>(ccMatPath);
                if (ccMat == null && srcMat != null)
                {
                    ccMat = new Material(srcMat);
                    ccMat.name = matPrefix + "_CoralCoast";
                    AssetDatabase.CreateAsset(ccMat, ccMatPath);
                }
                if (ccMat == null)
                {
                    Debug.LogWarning($"[珊瑚海岸] 找不到源材质 {srcMatPath}，跳过 {matPrefix}");
                    continue;
                }

                ccMat.SetTexture(slot, tex);
                EditorUtility.SetDirty(ccMat);
                created++;
            }
            AssetDatabase.SaveAssets();
            Debug.Log($"[珊瑚海岸] 已生成/更新 {created} 条材质贴图绑定，材质在 {MatDir}/");

            // 2. 把珊瑚海岸材质套到模型 SMR
            var smrs = root.GetComponentsInChildren<SkinnedMeshRenderer>(true);
            int applied = 0;
            foreach (var smr in smrs)
            {
                string meshName = smr.name.Replace("_lod0", "").Replace("_LOD0", "");
                // 尝试匹配材质名
                string matKey = meshName.Replace("S_actor_typhoea_", "M_actor_typhoea_")
                                       .Replace("S_actor_Typhoea_", "M_actor_typhoea_");
                if (matKey.EndsWith("_01")) matKey = matKey.Substring(0, matKey.Length - 3);

                string ccMatPath = $"{MatDir}/{matKey}_CoralCoast.mat";
                Material ccMat = AssetDatabase.LoadAssetAtPath<Material>(ccMatPath);
                if (ccMat != null)
                {
                    var mats = smr.sharedMaterials;
                    for (int i = 0; i < mats.Length; i++) mats[i] = ccMat;
                    smr.sharedMaterials = mats;
                    applied++;
                }
            }
            EditorUtility.SetDirty(root);
            AssetDatabase.SaveAssets();
            Debug.Log($"[珊瑚海岸] 已套用到 {applied} 个 SMR。如贴图错位，在 Inspector 手动调整材质贴图槽。");
        }

        [MenuItem("Endfield/珊瑚海岸/② 恢复默认时装材质", false, 201)]
        public static void Revert()
        {
            var root = GameObject.Find(RootName);
            if (root == null) { Debug.LogError($"[珊瑚海岸] 找不到 {RootName}"); return; }
            var smrs = root.GetComponentsInChildren<SkinnedMeshRenderer>(true);
            int reverted = 0;
            foreach (var smr in smrs)
            {
                string meshName = smr.name.Replace("_lod0", "").Replace("_LOD0", "");
                string matKey = meshName.Replace("S_actor_typhoea_", "M_actor_typhoea_")
                                       .Replace("S_actor_Typhoea_", "M_actor_typhoea_");
                if (matKey.EndsWith("_01")) matKey = matKey.Substring(0, matKey.Length - 3);
                string defMatPath = $"Assets/Typhoeus/Materials/{matKey}.mat";
                Material defMat = AssetDatabase.LoadAssetAtPath<Material>(defMatPath);
                if (defMat != null)
                {
                    var mats = smr.sharedMaterials;
                    for (int i = 0; i < mats.Length; i++) mats[i] = defMat;
                    smr.sharedMaterials = mats;
                    reverted++;
                }
            }
            EditorUtility.SetDirty(root);
            Debug.Log($"[珊瑚海岸] 已恢复 {reverted} 个 SMR 为默认时装材质。");
        }
    }
}
