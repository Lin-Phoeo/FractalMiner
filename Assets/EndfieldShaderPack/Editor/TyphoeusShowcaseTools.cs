using System.Collections.Generic;
using System.IO;
using System.Text;
using UnityEditor;
using UnityEngine;

namespace EndfieldShaderPack
{
    /// <summary>
    /// 展示工具：
    /// ① 诊断角色部件 —— 输出每个 SkinnedMeshRenderer 的骨骼/权重/绑定姿势状态
    /// ② 修复掉落部件 —— 权重全局索引→局部索引重映射 / 重建恒等 bindpose
    /// ③ 创建展示场景 —— 地面 + 轨道相机 + 角色光
    /// </summary>
    public static class TyphoeusShowcaseTools
    {
        const string RootName = "chr_0034_typhoea_rebuilt";
        const string DiagPath = "Validation/parts_diagnosis.txt";

        // ---------- ① 诊断 ----------
        [MenuItem("Endfield/展示/① 诊断角色部件", false, 100)]
        public static void Diagnose()
        {
            var root = GameObject.Find(RootName);
            if (root == null) { Debug.LogError($"[Showcase] 找不到 {RootName}"); return; }

            var sb = new StringBuilder();
            sb.AppendLine($"# Typhoeus parts diagnosis — {System.DateTime.Now:yyyy-MM-dd HH:mm:ss}");
            var smrs = root.GetComponentsInChildren<SkinnedMeshRenderer>(true);
            sb.AppendLine($"# total SMRs = {smrs.Length}\n");
            int problems = 0;
            foreach (var smr in smrs)
            {
                var mesh = smr.sharedMesh;
                string verdict = "OK";
                int bcount = smr.bones != null ? smr.bones.Length : 0;
                int nullBones = 0;
                for (int b = 0; b < bcount; b++) if (smr.bones[b] == null) nullBones++;

                int maxUsed = -1, minUsed = int.MaxValue;
                if (mesh != null)
                {
                    var bws = mesh.boneWeights;
                    for (int i = 0; i < bws.Length; i++)
                    {
                        var w = bws[i];
                        if (w.weight0 > 0f) { if (w.boneIndex0 > maxUsed) maxUsed = w.boneIndex0; if (w.boneIndex0 < minUsed) minUsed = w.boneIndex0; }
                        if (w.weight1 > 0f) { if (w.boneIndex1 > maxUsed) maxUsed = w.boneIndex1; if (w.boneIndex1 < minUsed) minUsed = w.boneIndex1; }
                        if (w.weight2 > 0f) { if (w.boneIndex2 > maxUsed) maxUsed = w.boneIndex2; if (w.boneIndex2 < minUsed) minUsed = w.boneIndex2; }
                        if (w.weight3 > 0f) { if (w.boneIndex3 > maxUsed) maxUsed = w.boneIndex3; if (w.boneIndex3 < minUsed) minUsed = w.boneIndex3; }
                    }
                }

                int identBp = 0;
                var bps = mesh != null ? mesh.bindposes : new Matrix4x4[0];
                for (int b = 0; b < bps.Length; b++)
                {
                    var m = bps[b];
                    if (Approx(m, Matrix4x4.identity)) identBp++;
                }

                if (nullBones > 0) verdict = $"NULL_BONES({nullBones}/{bcount})";
                else if (maxUsed >= bcount) verdict = $"WEIGHTS_GLOBAL(max={maxUsed}, bcount={bcount})";
                else if (bps.Length > 0 && identBp >= bps.Length * 0.9) verdict = $"IDENTITY_BINDPOSES({identBp}/{bps.Length})";

                if (verdict != "OK") problems++;
                Vector3 c = smr.bounds.center, e = smr.bounds.extents;
                sb.AppendLine($"{smr.name}\tverdict={verdict}\tbones={bcount}\tweightRange=[{minUsed},{maxUsed}]\tidentBP={identBp}\tworldCenter=({c.x:F2},{c.y:F2},{c.z:F2})\textents=({e.x:F2},{e.y:F2},{e.z:F2})");
            }
            sb.AppendLine($"\n# problem parts = {problems}");
            File.WriteAllText(DiagPath, sb.ToString());
            Debug.Log($"[Showcase] 诊断完成：{smrs.Length} 个部件，{problems} 个异常。已写入 {DiagPath}\n" + sb.ToString());
        }

        static bool Approx(Matrix4x4 a, Matrix4x4 b)
        {
            for (int i = 0; i < 16; i++)
                if (Mathf.Abs(a[i] - b[i]) > 1e-4f) return false;
            return true;
        }

        // ---------- 骨骼全局顺序（pre-order DFS = builder 创建顺序）----------
        static List<Transform> CollectGlobalBones(Transform modelRoot)
        {
            var list = new List<Transform>();
            Collect(modelRoot, list);
            return list;
        }
        static void Collect(Transform node, List<Transform> list)
        {
            for (int i = 0; i < node.childCount; i++)
            {
                var c = node.GetChild(i);
                if (c.GetComponent<SkinnedMeshRenderer>() != null) continue; // mesh 节点不是骨骼
                list.Add(c);
                Collect(c, list);
            }
        }

        // ---------- ② 修复 ----------
        [MenuItem("Endfield/展示/② 修复掉落部件", false, 101)]
        public static void FixDetachedParts()
        {
            var root = GameObject.Find(RootName);
            if (root == null) { Debug.LogError($"[Showcase] 找不到 {RootName}"); return; }

            var globalBones = CollectGlobalBones(root.transform);
            Debug.Log($"[Showcase] 全局骨骼 DFS 顺序收集：{globalBones.Count} 个");
            var smrs = root.GetComponentsInChildren<SkinnedMeshRenderer>(true);
            int fixedCount = 0;

            foreach (var smr in smrs)
            {
                var mesh = smr.sharedMesh;
                if (mesh == null) continue;
                int bcount = smr.bones != null ? smr.bones.Length : 0;

                // 扫描权重范围
                var bws = mesh.boneWeights;
                int maxUsed = -1;
                for (int i = 0; i < bws.Length; i++)
                {
                    var w = bws[i];
                    if (w.weight0 > 0f && w.boneIndex0 > maxUsed) maxUsed = w.boneIndex0;
                    if (w.weight1 > 0f && w.boneIndex1 > maxUsed) maxUsed = w.boneIndex1;
                    if (w.weight2 > 0f && w.boneIndex2 > maxUsed) maxUsed = w.boneIndex2;
                    if (w.weight3 > 0f && w.boneIndex3 > maxUsed) maxUsed = w.boneIndex3;
                }

                bool hasNull = false;
                for (int b = 0; b < bcount; b++) if (smr.bones[b] == null) hasNull = true;

                // Case A：权重是全局索引（>= bcount），重映射到局部
                if (!hasNull && maxUsed >= bcount && bcount > 0)
                {
                    var localToGlobal = new int[bcount];
                    for (int b = 0; b < bcount; b++)
                        localToGlobal[b] = globalBones.IndexOf(smr.bones[b]);

                    var newBws = new BoneWeight[bws.Length];
                    bool ok = true;
                    for (int i = 0; i < bws.Length && ok; i++)
                    {
                        var w = bws[i];
                        int l0 = Map(w.boneIndex0, localToGlobal), l1 = Map(w.boneIndex1, localToGlobal),
                            l2 = Map(w.boneIndex2, localToGlobal), l3 = Map(w.boneIndex3, localToGlobal);
                        if (l0 < 0 || l1 < 0 || l2 < 0 || l3 < 0) { ok = false; break; }
                        w.boneIndex0 = l0; w.boneIndex1 = l1; w.boneIndex2 = l2; w.boneIndex3 = l3;
                        newBws[i] = w;
                    }
                    if (!ok) { Debug.LogError($"[Showcase] {smr.name}: 权重重映射失败（有骨骼索引无法定位）"); continue; }

                    mesh.boneWeights = newBws;
                    EditorUtility.SetDirty(mesh);
                    EditorUtility.SetDirty(smr);
                    Debug.Log($"[Showcase] ✅ {smr.name}: 权重全局→局部重映射完成（原 max={maxUsed}, bcount={bcount}）");
                    fixedCount++;
                    continue;
                }

                // Case B：smr.bones 有 null —— 数据层问题，场景级修不了
                if (hasNull)
                {
                    Debug.LogError($"[Showcase] ❌ {smr.name}: smr.bones 含 null（数据骨骼索引越界），需修 TyphoeaModelBuilder 数据源后重建模型");
                    continue;
                }

                // Case C：bindpose 全恒等 → 用当前姿势重建（当前姿势 == 绑定姿势时正确）
                var bps = mesh.bindposes;
                int identBp = 0;
                for (int b = 0; b < bps.Length; b++) if (Approx(bps[b], Matrix4x4.identity)) identBp++;
                if (bps.Length > 0 && identBp >= bps.Length * 0.9)
                {
                    var rootL2W = root.transform.localToWorldMatrix;
                    var newBps = new Matrix4x4[bcount];
                    for (int b = 0; b < bcount; b++)
                        newBps[b] = smr.bones[b].worldToLocalMatrix * rootL2W;
                    mesh.bindposes = newBps;
                    EditorUtility.SetDirty(mesh);
                    Debug.Log($"[Showcase] ✅ {smr.name}: 从当前姿势重建 {bcount} 个 bindpose（假设当前=绑定姿势）");
                    fixedCount++;
                }
            }

            AssetDatabase.SaveAssets();
            Debug.Log($"[Showcase] 修复完成：{fixedCount} 个部件。若仍有问题请运行 ① 诊断 查看 {DiagPath}");
        }

        static int Map(int globalIdx, int[] localToGlobal)
        {
            for (int l = 0; l < localToGlobal.Length; l++)
                if (localToGlobal[l] == globalIdx) return l;
            return -1;
        }

        // ---------- ③ 展示场景 ----------
        [MenuItem("Endfield/展示/③ 创建展示场景（地面+轨道相机+角色光）", false, 102)]
        public static void SetupShowcaseScene()
        {
            var root = GameObject.Find(RootName);
            if (root == null) { Debug.LogError($"[Showcase] 找不到 {RootName}"); return; }

            // 地面
            var ground = GameObject.Find("Showcase_Ground");
            if (ground == null)
            {
                ground = GameObject.CreatePrimitive(PrimitiveType.Plane);
                ground.name = "Showcase_Ground";
                ground.transform.localScale = new Vector3(0.8f, 1f, 0.8f); // 8m x 8m
                var mr = ground.GetComponent<MeshRenderer>();
                var mat = new Material(Shader.Find("Universal Render Pipeline/Lit"));
                mat.color = new Color(0.55f, 0.55f, 0.54f);
                mat.name = "Showcase_GroundMat";
                AssetDatabase.CreateAsset(mat, "Assets/EndfieldShowcaseRef/Showcase_GroundMat.mat");
                mr.sharedMaterial = mat;
            }

            // 轨道相机
            var cam = Camera.main;
            if (cam != null)
            {
                var orbit = cam.GetComponent<ShowcaseOrbitCamera>();
                if (orbit == null) orbit = cam.gameObject.AddComponent<ShowcaseOrbitCamera>();
                orbit.target = root.transform;
                var b = TyphoeusSceneSetup.ComputeWorldBounds(root);
                orbit.distance = Mathf.Max(2.2f, b.size.y * 1.35f);
                orbit.targetHeight = b.center.y;
                orbit.autoRotate = true;
                EditorUtility.SetDirty(cam.gameObject);
            }

            // 角色光（分离式角色光照）
            if (Object.FindObjectOfType<Endfield.EndfieldCharacterLight>() == null)
            {
                var lightGo = new GameObject("CharacterLight");
                lightGo.AddComponent<Endfield.EndfieldCharacterLight>();
                Debug.Log("[Showcase] 已创建 CharacterLight（EndfieldCharacterLight）");
            }

            Debug.Log("[Showcase] 展示场景就绪：右键拖动环绕 / 滚轮缩放 / T 自动旋转 / R 重置。");
        }
    }
}
