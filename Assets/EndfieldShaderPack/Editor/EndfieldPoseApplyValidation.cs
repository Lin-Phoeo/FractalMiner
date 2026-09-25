// Pose-apply validation: drive the recovered-scene skeleton with the captured
// frame-6411 pose (pose-full-01/pose_apply.txt) and render the official camera.
//
// The pose file stores per-bone model-space pose matrices (math row-major,
// M x v convention, translation in column 3) recovered from the capture SSBO
// (see Tools/export_pose_full.py + build_pose_apply.py). Mapped bones get the
// captured pose; unmapped bones keep their bind local transform. The scene is
// never saved.
//
// Evidence contract (thresholds fixed BEFORE running):
//   G1: Bip001_Head WORLD y within [1.15, 1.40]
//   G2: Bip001_L_Hand / Bip001_R_Hand WORLD y within [0.85, 1.25]
//        and |x| within [0.05, 0.45] (book held in front of chest)
//   (world == capture model coords once pose is pre-multiplied by
//    inverse(armature.localToWorldMatrix); char root sits at origin)
//   render: Validation/pose-apply-01/pose-applied.png (1280x720)
//   report: Validation/pose-apply-01/pose-apply-report.json
using System;
using System.Collections.Generic;
using System.Globalization;
using System.IO;
using UnityEditor;
using UnityEditor.SceneManagement;
using UnityEngine;

namespace EndfieldShaderPack.EditorTools
{
    public static class EndfieldPoseApplyValidation
    {
        const string ScenePath = "Assets/Scenes/Typhoeus_OfficialFrame_Recovered.unity";
        const string PosePath = "Validation/Captures/tifuluosi-front-20260917/pose-full-01/pose_apply.txt";
        const string OutDir = "Validation/pose-apply-01";
        const int Width = 1280;
        const int Height = 720;

        public static void RunPoseApply()
        {
            Directory.CreateDirectory(OutDir);
            var report = new List<string>();
            var scene = EditorSceneManager.OpenScene(ScenePath, OpenSceneMode.Single);
            var poses = LoadPose(PosePath);
            report.Add("pose file bones: " + poses.Count);

            // Scene root order: Main Camera, Directional Light, Typhoeus_SourceFBX
            // (INACTIVE FBX prefab with its OWN full Bip001 rig), chr_0034_typhoea_rebuilt
            // (the VISIBLE rebuilt character), CharacterLight. A blind FindDeep hits the
            // inactive prefab rig first — its transforms accept pose writes (and probes
            // read back fine) but drive no renderer. Anchor explicitly on the ACTIVE
            // rebuilt character root. (Runtime-verified: hairSmr.bones[head] instanceID
            // != FindDeep(prefab-root) head instanceID.)
            Transform charRoot = null;
            foreach (var sceneRoot in scene.GetRootGameObjects())
            {
                if (sceneRoot.name == "chr_0034_typhoea_rebuilt") { charRoot = sceneRoot.transform; break; }
            }
            if (charRoot == null) throw new InvalidOperationException("chr_0034_typhoea_rebuilt not found in " + ScenePath);
            Transform pelvis = FindDeep(charRoot, "Bip001_Pelvis");
            if (pelvis == null) throw new InvalidOperationException("Bip001_Pelvis not found under " + charRoot.name);
            Transform armature = pelvis;
            while (armature.parent != null &&
                   (armature.parent.name == "Bip001" || armature.parent.name == "Root"))
                armature = armature.parent;
            report.Add("skeleton walk root: " + armature.name);

            var byName = new Dictionary<string, Transform>();
            Collect(armature, byName);
            report.Add("scene bones under Armature: " + byName.Count);

            // Top-down order (parents before children).
            var ordered = new List<Transform>();
            OrderDeep(armature, ordered);

            // bind locals
            var bindLocal = new Dictionary<Transform, Matrix4x4>();
            foreach (var t in ordered)
                bindLocal[t] = Matrix4x4.TRS(t.localPosition, t.localRotation, t.localScale);

            // PRE-apply probes (scene on-disk state) — tells whether on-disk == captured pose.
            var preJson = new List<string>();
            foreach (var name in new[] { "Bip001_Head", "Bip001_L_Hand", "Bip001_R_Hand" })
            {
                Transform t = FindDeep(armature, name);
                if (t == null) continue;
                Vector3 rel = t.position;
                preJson.Add(string.Format(CultureInfo.InvariantCulture,
                    "{{\"name\":\"{0}\",\"preApplyWorld\":[{1:F4},{2:F4},{3:F4}]}}", name, rel.x, rel.y, rel.z));
            }

            // Frame conversion: pose matrices are capture model space (Y-up). The rig's
            // walk root "Root" sits under chr_0034_typhoea_rebuilt which carries a -90degX
            // (Root-local frame is Z-up: bind head reads z=+1.27). newWorld values below
            // are ARMATURE-RELATIVE, so mapped bones must be pre-multiplied by
            // rootFix = inverse(armature.localToWorldMatrix) to land upright in world.
            // (First attempt without rootFix rendered a face-down heap; probes passed
            // because they were also armature-relative — gates now probe WORLD frame.)
            Matrix4x4 rootFix = armature.localToWorldMatrix.inverse;
            var newWorld = new Dictionary<Transform, Matrix4x4>();
            int applied = 0, keptBind = 0;
            foreach (var t in ordered)
            {
                Matrix4x4 parentWorld = t.parent != null && newWorld.ContainsKey(t.parent)
                    ? newWorld[t.parent]
                    : Matrix4x4.identity;
                Matrix4x4 pose;
                if (t != armature && poses.TryGetValue(t.name, out pose))
                {
                    newWorld[t] = rootFix * pose;
                    applied++;
                }
                else
                {
                    newWorld[t] = parentWorld * bindLocal[t];
                    keptBind++;
                }
            }
            report.Add(string.Format("applied pose: {0}, kept bind: {1}", applied, keptBind));

            foreach (var t in ordered)
            {
                if (t == armature) continue;
                Matrix4x4 parentWorld = t.parent != null && newWorld.ContainsKey(t.parent)
                    ? newWorld[t.parent]
                    : Matrix4x4.identity;
                Matrix4x4 local = parentWorld.inverse * newWorld[t];
                t.localPosition = local.GetColumn(3);
                t.localRotation = local.rotation;
                t.localScale = local.lossyScale;
            }

            // G1/G2 bone evidence — WORLD frame (char root at origin, upright after
            // rootFix, so world coords == capture model coords).
            string[] probes = { "Bip001_Head", "Bip001_L_Hand", "Bip001_R_Hand", "Bip001_Pelvis" };
            bool g1 = false, g2l = false, g2r = false;
            var probeJson = new List<string>();
            foreach (var name in probes)
            {
                Transform t;
                if (!byName.TryGetValue(name, out t)) { probeJson.Add("{\"name\":\"" + name + "\",\"missing\":true}"); continue; }
                Vector3 rel = t.position;
                probeJson.Add(string.Format(CultureInfo.InvariantCulture,
                    "{{\"name\":\"{0}\",\"world\":[{1:F4},{2:F4},{3:F4}]}}", name, rel.x, rel.y, rel.z));
                if (name == "Bip001_Head") g1 = rel.y >= 1.15f && rel.y <= 1.40f;
                if (name == "Bip001_L_Hand") g2l = rel.y >= 0.85f && rel.y <= 1.25f && Mathf.Abs(rel.x) >= 0.05f && Mathf.Abs(rel.x) <= 0.45f;
                if (name == "Bip001_R_Hand") g2r = rel.y >= 0.85f && rel.y <= 1.25f && Mathf.Abs(rel.x) >= 0.05f && Mathf.Abs(rel.x) <= 0.45f;
            }

            var camera = Camera.main;
            if (camera == null) throw new InvalidOperationException("No main camera in scene.");
            RenderPng(camera, Path.Combine(OutDir, "pose-applied.png"));

            bool pass = g1 && g2l && g2r;
            string json = "{\"gate_head_y\":" + (g1 ? "true" : "false")
                + ",\"gate_lhand\":" + (g2l ? "true" : "false")
                + ",\"gate_rhand\":" + (g2r ? "true" : "false")
                + ",\"pass\":" + (pass ? "true" : "false")
                + ",\"notes\":[" + string.Join(",", report.ConvertAll(s => "\"" + s + "\"").ToArray()) + "]"
                + ",\"preApply\":[" + string.Join(",", preJson.ToArray()) + "]"
                + ",\"probes\":[" + string.Join(",", probeJson.ToArray()) + "]}";
            File.WriteAllText(Path.Combine(OutDir, "pose-apply-report.json"), json);
            Debug.Log("[PoseApply] pass=" + pass + " | " + string.Join(" | ", report.ToArray()));
            if (!pass) throw new InvalidOperationException("Pose-apply gates failed, see pose-apply-report.json");
            // Never save the scene.
        }

        static Dictionary<string, Matrix4x4> LoadPose(string path)
        {
            var inv = CultureInfo.InvariantCulture;
            var poses = new Dictionary<string, Matrix4x4>();
            foreach (var line in File.ReadAllLines(path))
            {
                if (line.Length == 0) continue;
                int tab = line.IndexOf('\t');
                string name = line.Substring(0, tab);
                string[] parts = line.Substring(tab + 1).Split(' ');
                if (parts.Length != 16) throw new InvalidDataException("bad pose line for " + name);
                var m = new Matrix4x4();
                for (int r = 0; r < 4; r++)
                    for (int c = 0; c < 4; c++)
                        m[r, c] = float.Parse(parts[r * 4 + c], inv);
                poses[name] = m;
            }
            return poses;
        }

        static Transform FindDeep(Transform root, string name)
        {
            if (root.name == name) return root;
            foreach (Transform child in root)
            {
                var hit = FindDeep(child, name);
                if (hit != null) return hit;
            }
            return null;
        }

        static void Collect(Transform root, Dictionary<string, Transform> map)
        {
            if (!map.ContainsKey(root.name)) map.Add(root.name, root);
            foreach (Transform child in root) Collect(child, map);
        }

        static void OrderDeep(Transform root, List<Transform> list)
        {
            list.Add(root);
            foreach (Transform child in root) OrderDeep(child, list);
        }

        static void RenderPng(Camera camera, string path)
        {
            var target = new RenderTexture(Width, Height, 24, RenderTextureFormat.ARGB32, RenderTextureReadWrite.sRGB);
            var previousTarget = camera.targetTexture;
            var previousActive = RenderTexture.active;
            try
            {
                camera.targetTexture = target;
                camera.Render();
                var readback = new Texture2D(Width, Height, TextureFormat.RGB24, false);
                RenderTexture.active = target;
                readback.ReadPixels(new Rect(0, 0, Width, Height), 0, 0);
                readback.Apply();
                File.WriteAllBytes(path, readback.EncodeToPNG());
                UnityEngine.Object.DestroyImmediate(readback);
            }
            finally
            {
                camera.targetTexture = previousTarget;
                RenderTexture.active = previousActive;
                target.Release();
            }
        }
    }
}
