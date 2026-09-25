using System;
using System.IO;
using System.Text;
using UnityEditor;
using UnityEditor.SceneManagement;
using UnityEngine;
using System.Linq;

namespace EndfieldShaderPack.EditorTools
{
    public static class EndfieldClipBindDiag
    {
        public static void Run()
        {
            var sb = new StringBuilder();
            var clip = AssetDatabase.LoadAssetAtPath<AnimationClip>(
                "Assets/Typhoeus/AnimationsDecoded/A_actor_typhoea_battle_attack_01.anim");
            var bindings = AnimationUtility.GetCurveBindings(clip);
            sb.AppendLine("clip bindings: " + bindings.Length);
            var paths = bindings.Select(b => b.path).Distinct().Take(5);
            foreach (var p in paths) sb.AppendLine("  clipPath: " + p);
            sb.AppendLine("clip legacy: " + clip.legacy + " framerete: " + clip.frameRate);

            var scene = EditorSceneManager.OpenScene(
                "Assets/Scenes/Typhoeus_OfficialFrame_Recovered.unity", OpenSceneMode.Single);
            Transform charRoot = null;
            foreach (var root in scene.GetRootGameObjects())
                if (root.name == "chr_0034_typhoea_rebuilt") { charRoot = root.transform; break; }
            sb.AppendLine("charRoot children:");
            foreach (Transform c in charRoot) sb.AppendLine("  child: " + c.name);
            // 直接找 clip 第一条 path 的 transform
            string first = bindings.Select(b => b.path).First();
            var t = charRoot.Find(first);
            sb.AppendLine("charRoot.Find(\"" + first + "\") = " + (t != null ? t.name : "NULL"));
            // legacy 测试: 置 legacy 再 Sample
            var go = new GameObject("probe");
            var before = new Pose(charRoot.transform.Find("Root/Bip001/Bip001_Pelvis").position,
                charRoot.transform.Find("Root/Bip001/Bip001_Pelvis").rotation);
            clip.SampleAnimation(charRoot.gameObject, 0f);
            var pelvis = charRoot.transform.Find("Root/Bip001/Bip001_Pelvis");
            sb.AppendLine("pelvis before: " + before.position.ToString("F4") + " after(0s): " + pelvis.position.ToString("F4"));
            clip.SampleAnimation(charRoot.gameObject, 2.0f);
            sb.AppendLine("pelvis after(2s): " + pelvis.position.ToString("F4"));
            File.WriteAllText("Validation/clip-bind-diag.txt", sb.ToString());
            Debug.Log("[BindDiag]\n" + sb.ToString());
        }
    }
}
