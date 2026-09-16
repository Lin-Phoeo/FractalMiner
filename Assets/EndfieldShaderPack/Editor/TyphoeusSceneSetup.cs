// ============================================================
//  TyphoeusSceneSetup.cs
//  一键搭建提弗洛斯(Typhoeus)展示场景 + 配置 Humanoid(MMD 前置)。
//  说明：
//    - 模型/材质/贴图已由 EndfieldMaterialImporter 就绪，
//      本脚本只负责把模型放进场景、摆好相机与分离式角色光。
//    - Humanoid 配置用于后续 MMD 动作重定向(VMD -> Avatar)。
//  菜单：
//    Endfield / Setup Typhoeus Showcase Scene —— 新建并保存展示场景
//    Endfield / Configure FBX as Humanoid (MMD)   —— FBX 转 Humanoid
//    Endfield / Full Typhoeus Setup                —— 先 Humanoid 再建场景
// ============================================================
using UnityEditor;
using UnityEditor.SceneManagement;
using UnityEngine;

namespace EndfieldShaderPack
{
    public static class TyphoeusSceneSetup
    {
        const string FbxPath   = "Assets/Typhoeus/chr_0034_typhoea_uimodel.fbx";
        const string ScenePath = "Assets/Scenes/Typhoeus_Showcase.unity";

        [MenuItem("Endfield/Setup Typhoeus Showcase Scene", false, 40)]
        public static void SetupShowcaseScene()
        {
            GameObject fbx = AssetDatabase.LoadAssetAtPath<GameObject>(FbxPath);
            if (fbx == null)
            {
                Debug.LogError("[Endfield] 找不到 FBX: " + FbxPath);
                return;
            }

            // 新建一个干净场景（自带 Main Camera + Directional Light）
            var scene = EditorSceneManager.NewScene(NewSceneSetup.DefaultGameObjects, NewSceneMode.Single);

            // 实例化模型
            GameObject root = PrefabUtility.InstantiatePrefab(fbx) as GameObject;
            if (root == null) root = Object.Instantiate(fbx);
            root.name = "Typhoeus";
            root.transform.SetPositionAndRotation(Vector3.zero, Quaternion.identity);

            // 分离式角色光照：独立于场景主光
            var lightGo = new GameObject("CharacterLight");
            lightGo.transform.rotation = Quaternion.Euler(50f, -30f, 0f);
            var cl = lightGo.AddComponent<Endfield.EndfieldCharacterLight>();
            cl.useSeparatedLight = true;
            cl.lightColor = Color.white;
            cl.intensity = 1f;
            cl.ApplyLight();

            // 相机自动取景对准角色
            FrameCamera(root);

            // 校验材质绑定
            VerifyMaterials(root);

            EditorSceneManager.SaveScene(scene, ScenePath);
            AssetDatabase.SaveAssets();
            Debug.Log("[Endfield] 展示场景已生成: " + ScenePath);
        }

        [MenuItem("Endfield/Configure FBX as Humanoid (MMD)", false, 41)]
        public static void ConfigureHumanoid()
        {
            var importer = AssetImporter.GetAtPath(FbxPath) as ModelImporter;
            if (importer == null)
            {
                Debug.LogError("[Endfield] FBX importer 不可用: " + FbxPath);
                return;
            }

            importer.animationType = ModelImporterAnimationType.Human;
            importer.avatarSetup = ModelImporterAvatarSetup.CreateFromThisModel;
            importer.SaveAndReimport();

            Debug.Log("[Endfield] FBX 已配置为 Humanoid，Avatar 已生成（MMD 重定向前置完成）。" +
                      "如 Console 有骨骼映射告警，可手动在 Inspector 的 Rig 面板微调。");
        }

        [MenuItem("Endfield/Full Typhoeus Setup", false, 42)]
        public static void FullSetup()
        {
            ConfigureHumanoid();
            SetupShowcaseScene();
        }

        // ----------------------------------------------------------

        static void FrameCamera(GameObject target)
        {
            var cam = Camera.main;
            if (cam == null) return;

            Bounds b = ComputeWorldBounds(target);
            if (b.size.sqrMagnitude < 1e-6f)
            {
                // 取不到包围盒时用保守默认值
                cam.transform.position = new Vector3(0f, 1.6f, -4f);
                cam.transform.LookAt(new Vector3(0f, 1.2f, 0f));
                return;
            }

            float fovVert = cam.fieldOfView * Mathf.Deg2Rad;
            float fitDist = b.extents.magnitude / Mathf.Tan(fovVert * 0.5f);
            float dist = Mathf.Max(fitDist, 2f) * 1.1f;

            Vector3 dir = new Vector3(0f, 0.15f, -1f).normalized; // 略俯视
            cam.transform.position = b.center - dir * dist;
            cam.transform.LookAt(b.center);
        }

        static Bounds ComputeWorldBounds(GameObject root)
        {
            var renderers = root.GetComponentsInChildren<Renderer>();
            if (renderers.Length == 0)
                return new Bounds(root.transform.position, Vector3.zero);

            Bounds b = renderers[0].bounds;
            for (int i = 1; i < renderers.Length; i++)
                b.Encapsulate(renderers[i].bounds);
            return b;
        }

        static void VerifyMaterials(GameObject root)
        {
            int missing = 0;
            foreach (var smr in root.GetComponentsInChildren<SkinnedMeshRenderer>())
            {
                foreach (var m in smr.sharedMaterials)
                {
                    if (m == null) missing++;
                }
            }
            if (missing > 0)
                Debug.LogWarning("[Endfield] 有 " + missing + " 个材质槽为空，请先执行 Endfield / Build & Assign Typhoeus (Full)。");
            else
                Debug.Log("[Endfield] 模型材质绑定完整（SkinnedMeshRenderer 材质槽无空）。");
        }
    }
}