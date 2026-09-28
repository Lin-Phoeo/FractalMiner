// TyphoeusRigRepair.cs — WP1.1 regression recovery.
//
// The pose-apply baseline scene Typhoeus_OfficialFrame_Recovered.unity was
// modified on 2026-09-26 by MMD/anim drivers that open it; its chr_0034 rig
// bind pose drifted, dropping the pose-apply silhouette IoU 0.765 -> 0.399.
// The scene is not version-controlled, so recovery re-derives the canonical
// bone LOCAL transforms from the same deterministic source the builder uses
// (_typhoea_model_data.json) and writes them back onto the existing rig,
// touching ONLY bone transforms — SMRs, materials, mesh bindings and the
// camera/light/globals objects are left exactly as they are.
//
// Diagnose: dry run, logs the drifted bones. Repair: writes canonical locals
// and saves the scene once.
using System;
using System.Collections.Generic;
using System.IO;
using System.Linq;
using UnityEditor;
using UnityEditor.SceneManagement;
using UnityEngine;

namespace Endfield
{
    public static class TyphoeusRigRepair
    {
        const string ScenePath = "Assets/Scenes/Typhoeus_OfficialFrame_Recovered.unity";
        const string DataPath = "Assets/Typhoeus/_typhoea_model_data.json";
        const string CharacterRoot = "chr_0034_typhoea_rebuilt";
        const float PosEps = 1e-4f;   // metres
        const float RotEps = 0.05f;   // degrees

        public static void Diagnose() => Run(false);
        public static void Repair() => Run(true);

        // Whole-character rebuild: drop the (possibly component-contaminated) rig and
        // regenerate a fresh one from _typhoea_model_data.json via the canonical
        // builder, preserving the chr-root transform/parent/layer so pose-apply's
        // rootFix and scene wiring are unchanged. Removes any 2026-09-26 additions
        // (cloth/IK/anim components) that a bone-only repair could not.
        public static void RebuildCharacter()
        {
            var scene = EditorSceneManager.OpenScene(ScenePath, OpenSceneMode.Single);
            Transform old = null;
            foreach (var go in scene.GetRootGameObjects())
                if (go.name == CharacterRoot) { old = go.transform; break; }
            if (old == null) throw new InvalidOperationException(CharacterRoot + " not found in " + ScenePath);

            var pos = old.localPosition;
            var rot = old.localRotation;
            var scale = old.localScale;
            var parent = old.parent;
            int sibling = old.GetSiblingIndex();
            int layer = old.gameObject.layer;
            string tag = old.gameObject.tag;
            Debug.Log($"[RigRepair] old chr root: pos={pos} rot={rot} scale={scale} parent={(parent ? parent.name : "<root>")} layer={layer}");

            UnityEngine.Object.DestroyImmediate(old.gameObject);
            TyphoeusModelBuilder.Rebuild();

            Transform fresh = null;
            foreach (var go in scene.GetRootGameObjects())
                if (go.name == CharacterRoot) { fresh = go.transform; break; }
            if (fresh == null) throw new InvalidOperationException("Rebuild did not produce " + CharacterRoot);
            if (parent != null) fresh.SetParent(parent, false);
            fresh.localPosition = pos;
            fresh.localRotation = rot;
            fresh.localScale = scale;
            fresh.SetSiblingIndex(sibling);
            SetLayerRecursive(fresh.gameObject, layer);
            fresh.gameObject.tag = tag;

            int smrs = fresh.GetComponentsInChildren<SkinnedMeshRenderer>(true).Length;
            EditorSceneManager.MarkSceneDirty(scene);
            EditorSceneManager.SaveScene(scene, ScenePath);
            Debug.Log($"[RigRepair] rebuilt character ({smrs} SMRs), restored chr-root transform, saved {ScenePath}");
        }

        static void SetLayerRecursive(GameObject go, int layer)
        {
            go.layer = layer;
            foreach (Transform c in go.transform) SetLayerRecursive(c.gameObject, layer);
        }

        static void Run(bool repair)
        {
            var canonical = CanonicalLocals();
            var scene = EditorSceneManager.OpenScene(ScenePath, OpenSceneMode.Single);
            Transform root = null;
            foreach (var go in scene.GetRootGameObjects())
                if (go.name == CharacterRoot) { root = go.transform; break; }
            if (root == null) throw new InvalidOperationException(CharacterRoot + " not found in " + ScenePath);

            var byName = new Dictionary<string, Transform>();
            Collect(root, byName);

            var drift = new List<(string name, float dp, float dr)>();
            int matched = 0;
            foreach (var kv in canonical)
            {
                if (!byName.TryGetValue(kv.Key, out var t)) continue;
                matched++;
                float dp = Vector3.Distance(t.localPosition, kv.Value.pos);
                float dr = Quaternion.Angle(t.localRotation, kv.Value.rot);
                if (dp > PosEps || dr > RotEps) drift.Add((kv.Key, dp, dr));
            }
            drift.Sort((a, b) => (b.dr + b.dp * 1000f).CompareTo(a.dr + a.dp * 1000f));

            Debug.Log($"[RigRepair] canonical bones={canonical.Count} matched in scene={matched} drifted={drift.Count}");
            foreach (var d in drift.Take(30))
                Debug.Log($"[RigRepair] drift {d.name}: dPos={d.dp:F5}m dRot={d.dr:F3}deg");

            if (!repair)
            {
                Debug.Log("[RigRepair] Diagnose only; no changes written.");
                return;
            }

            int fixedCount = 0;
            foreach (var kv in canonical)
            {
                if (!byName.TryGetValue(kv.Key, out var t)) continue;
                if (Vector3.Distance(t.localPosition, kv.Value.pos) <= PosEps
                    && Quaternion.Angle(t.localRotation, kv.Value.rot) <= RotEps) continue;
                t.localPosition = kv.Value.pos;
                t.localRotation = kv.Value.rot;
                t.localScale = Vector3.one;
                fixedCount++;
            }
            // Root carries the Z-up -> Y-up correction; keep whatever pose-apply
            // expects (it overwrites root rotation at render time anyway).
            EditorSceneManager.MarkSceneDirty(scene);
            EditorSceneManager.SaveScene(scene, ScenePath);
            Debug.Log($"[RigRepair] repaired {fixedCount} bone locals and saved {ScenePath}");
        }

        struct Local { public Vector3 pos; public Quaternion rot; }

        // Same derivation as TyphoeusModelBuilder.Rebuild (bind pose -> world ->
        // parent-relative local), keyed by bone name.
        static Dictionary<string, Local> CanonicalLocals()
        {
            string full = Path.Combine(Application.dataPath, "Typhoeus", "_typhoea_model_data.json");
            if (!File.Exists(full)) throw new FileNotFoundException(full);
            var data = JsonUtility.FromJson<TyphoeaModelData>(File.ReadAllText(full));

            int n = data.bones.Count;
            var bindPoses = new Matrix4x4[n];
            var hasBind = new bool[n];
            for (int i = 0; i < n; i++) bindPoses[i] = Matrix4x4.identity;
            foreach (var m in data.meshes)
                for (int b = 0; b < m.bones.Length; b++)
                {
                    int gi = m.bones[b];
                    if (gi >= 0 && gi < n) { bindPoses[gi] = ReadMatrix(m.bindPoses, b); hasBind[gi] = true; }
                }

            var result = new Dictionary<string, Local>(n);
            for (int i = 0; i < n; i++)
            {
                Matrix4x4 world = hasBind[i] ? bindPoses[i].inverse : Matrix4x4.identity;
                int p = data.bones[i].parent;
                Matrix4x4 local;
                if (p >= 0 && p < n)
                {
                    Matrix4x4 parentWorld = hasBind[p] ? bindPoses[p].inverse : Matrix4x4.identity;
                    local = parentWorld.inverse * world;
                }
                else local = world;
                result[data.bones[i].name] = new Local { pos = local.GetColumn(3), rot = local.rotation };
            }
            return result;
        }

        static Matrix4x4 ReadMatrix(float[] flat, int index)
        {
            Matrix4x4 m = Matrix4x4.identity;
            if (flat == null || index * 16 + 15 >= flat.Length) return m;
            int o = index * 16;
            m.m00 = flat[o];      m.m10 = flat[o + 1];  m.m20 = flat[o + 2];  m.m30 = flat[o + 3];
            m.m01 = flat[o + 4];  m.m11 = flat[o + 5];  m.m21 = flat[o + 6];  m.m31 = flat[o + 7];
            m.m02 = flat[o + 8];  m.m12 = flat[o + 9];  m.m22 = flat[o + 10]; m.m32 = flat[o + 11];
            m.m03 = flat[o + 12]; m.m13 = flat[o + 13]; m.m23 = flat[o + 14]; m.m33 = flat[o + 15];
            return m;
        }

        static void Collect(Transform root, Dictionary<string, Transform> map)
        {
            if (!map.ContainsKey(root.name)) map.Add(root.name, root);
            foreach (Transform child in root) Collect(child, map);
        }
    }
}
