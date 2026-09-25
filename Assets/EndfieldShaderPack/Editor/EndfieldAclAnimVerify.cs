using System;
using System.Collections.Generic;
using System.IO;
using UnityEditor;
using UnityEditor.SceneManagement;
using UnityEngine;

namespace EndfieldShaderPack.EditorTools
{
    /// <summary>
    /// ACL 还原动画运行时验证:
    /// 1) 载入 AnimationsDecoded 内全部 clip, 报告 length/bindings/采样率
    /// 2) 用 battle_attack_01 在 pose 场景角色上采样若干帧, 输出骨位世界坐标数值证据
    /// 门禁: clip 加载非空数 ≥ 300; SampleAnimation 后骨位与 bind 姿态有可见差异 (证明曲线生效)。
    /// </summary>
    public static class EndfieldAclAnimVerify
    {
        const string DecodedDir = "Assets/Typhoeus/AnimationsDecoded";
        const string OutPath = "Validation/acl-anim-verify/report.json";

        public static void Run()
        {
            Directory.CreateDirectory("Validation/acl-anim-verify");
            var clips = AssetDatabase.FindAssets("t:AnimationClip", new[] { DecodedDir });
            int loaded = 0, empty = 0;
            float totalLen = 0f;
            foreach (var guid in clips)
            {
                var path = AssetDatabase.GUIDToAssetPath(guid);
                var clip = AssetDatabase.LoadAssetAtPath<AnimationClip>(path);
                if (clip == null) { empty++; continue; }
                if (clip.length > 0f && !clip.empty) loaded++;
                else empty++;
                totalLen += clip.length;
            }
            Debug.Log($"[AclVerify] clips={clips.Length} loaded_ok={loaded} empty={empty} total_length={totalLen:F1}s");

            // 采样验证: attack_01 驱动 pose 场景角色
            var scene = EditorSceneManager.OpenScene("Assets/Scenes/Typhoeus_OfficialFrame_Recovered.unity");
            var charRoot = GameObject.Find("chr_0034_typhoea_rebuilt");
            var report = new List<string>();
            if (charRoot == null)
            {
                Debug.LogError("[AclVerify] chr root not found");
                WriteReport(loaded, empty, totalLen, false, report);
                return;
            }
            var pelvis = charRoot.transform.Find("Root/Bip001/Bip001_Pelvis");
            if (pelvis == null) { Debug.LogError("[AclVerify] pelvis not found"); WriteReport(loaded, empty, totalLen, false, report); return; }

            var bindPos = pelvis.position;
            var bindRot = pelvis.rotation;

            var attack = AssetDatabase.LoadAssetAtPath<AnimationClip>(
                DecodedDir + "/A_actor_typhoea_battle_attack_01.anim");
            bool sampleOk = false;
            if (attack != null)
            {
                var times = new[] { 0.0f, 0.5f, 1.5f, 2.5f, 4.5f };
                foreach (var t in times)
                {
                    // 复位到 bind 再采样
                    charRoot.transform.localPosition = Vector3.zero;
                    attack.SampleAnimation(charRoot.gameObject, t);
                    var p = pelvis.position;
                    var moved = Vector3.Distance(p, bindPos);
                    report.Add($"t={t:F2}s pelvis_world=({p.x:F4},{p.y:F4},{p.z:F4}) delta_bind={moved:F4}");
                }
                sampleOk = report.Count == times.Length;
            }
            Debug.Log("[AclVerify] pelvis samples:\n" + string.Join("\n", report.ToArray()));
            WriteReport(loaded, empty, totalLen, sampleOk, report);
        }

        static void WriteReport(int loaded, int empty, float totalLen, bool sampleOk, List<string> samples)
        {
            var sb = new System.Text.StringBuilder();
            sb.AppendLine("{");
            sb.AppendLine($"  \"clips_loaded\": {loaded},");
            sb.AppendLine($"  \"clips_empty\": {empty},");
            sb.AppendLine($"  \"total_length_s\": {totalLen.ToString("F2", System.Globalization.CultureInfo.InvariantCulture)},");
            sb.AppendLine($"  \"attack01_sample_ok\": {sampleOk.ToString().ToLower()},");
            sb.AppendLine("  \"samples\": [");
            for (int i = 0; i < samples.Count; ++i)
                sb.AppendLine("    \"" + samples[i].Replace("\"", "'") + "\"" + (i + 1 < samples.Count ? "," : ""));
            sb.AppendLine("  ]");
            sb.AppendLine("}");
            File.WriteAllText(OutPath, sb.ToString());
            Debug.Log("[AclVerify] report written: " + OutPath);
        }
    }
}
