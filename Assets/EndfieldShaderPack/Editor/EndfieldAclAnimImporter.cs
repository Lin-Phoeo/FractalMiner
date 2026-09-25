using System;
using System.Collections.Generic;
using System.Globalization;
using System.IO;
using UnityEditor;
using UnityEngine;

namespace EndfieldShaderPack.EditorTools
{
    /// <summary>
    /// 把 ACL 解码帧姿态 JSON 转成标准 Unity .anim。
    /// 输入: <project>/_anim_decoded/*.frames.json (num_tracks x num_samples x [qx,qy,qz,qw,tx,ty,tz])
    ///        <project>/_anim_track_paths/*.paths.json (track 索引 -> 层级路径; hash_ 前缀=templet 外面部骨, 跳过)
    /// 输出: Assets/Typhoeus/AnimationsDecoded/<clip>.anim (未压缩, 每采样一关键点)
    /// 门禁: tracks 与 paths 数量一致 (允许跳过 hash_ 面); 导入后抽查关键帧数值 |Δ| ≤ 1e-4。
    /// </summary>
    public static class EndfieldAclAnimImporter
    {
        const string DecodedDir = "../EndfieldUnpacker/_anim_decoded";
        const string TrackPathsDir = "../EndfieldUnpacker/_anim_track_paths";
        const string OutDir = "Assets/Typhoeus/AnimationsDecoded";

        [MenuItem("Endfield/ACL/Import All Decoded Animations")]
        public static void ImportAll()
        {
            ImportFromList(null);
        }

        /// <summary>只导入 _fail_import_list.txt 中列出的 clip (batchmode 重试用)。</summary>
        [MenuItem("Endfield/ACL/Import Failed List")]
        public static void ImportFailedList()
        {
            string root = Path.GetDirectoryName(Application.dataPath);
            var listPath = Path.Combine(root, "../EndfieldUnpacker/_fail_import_list.txt");
            var names = new List<string>();
            if (File.Exists(listPath))
            {
                foreach (var line in File.ReadAllLines(listPath))
                    if (!string.IsNullOrWhiteSpace(line)) names.Add(line.Trim());
            }
            Debug.Log($"[AclImport] retry list: {names.Count}");
            ImportFromList(names);
        }

        static void ImportFromList(List<string> onlyNames)
        {
            Directory.CreateDirectory(OutDir);
            string root = Path.GetDirectoryName(Application.dataPath);
            var srcDir = Path.Combine(root, DecodedDir);
            var files = Directory.GetFiles(srcDir, "*.frames.json");
            if (onlyNames != null)
            {
                var set = new HashSet<string>(onlyNames);
                files = System.Array.FindAll(files, f => set.Contains(Path.GetFileNameWithoutExtension(f).Replace(".frames", "")));
            }
            int ok = 0, skip = 0;
            var fails = new List<string>();
            var skipped = new List<string>();
            foreach (var f in files)
            {
                string name = Path.GetFileNameWithoutExtension(f);
                name = name.Substring(0, name.Length - ".frames".Length);
                try
                {
                    var paths = ReadTrackPaths(root, name);
                    if (paths == null) { skip++; skipped.Add(name); continue; }
                    var clip = BuildClip(name, f, paths);
                    string outPath = Path.Combine(OutDir, name + ".anim");
                    if (AssetDatabase.LoadAssetAtPath<UnityEngine.Object>(outPath) != null)
                        AssetDatabase.DeleteAsset(outPath);
                    AssetDatabase.CreateAsset(clip, outPath);
                    ok++;
                    AssetDatabase.SaveAssets(); // 每个 clip 立刻落盘, 避免持久断言
                    if (ok % 50 == 0) Debug.Log($"[AclImport] {ok}...");
                }
                catch (Exception e)
                {
                    fails.Add(name + ": " + e.Message);
                }
            }
            AssetDatabase.SaveAssets();
            Debug.Log($"[AclImport] imported={ok} skipped={skip} failed={fails.Count}" +
                      (fails.Count > 0 ? "\n" + string.Join("\n", fails.GetRange(0, Math.Min(fails.Count, 15)).ToArray()) : ""));
        }

        /// <summary>运行单个 clip 的构建 (供批量入口与验证入口复用)。</summary>
        public static AnimationClip BuildClip(string clipName, string framesJsonPath, List<string> paths)
        {
            string text = File.ReadAllText(framesJsonPath);
            int numTracks = ParseIntAfter(text, "\"num_tracks\":");
            int numSamples = ParseIntAfter(text, "\"num_samples\":");
            float sampleRate = ParseFloatAfter(text, "\"sample_rate\":");
            int framesStart = text.IndexOf("\"frames\":[", StringComparison.Ordinal) + "\"frames\":[".Length;
            if (numTracks != paths.Count)
                throw new Exception($"tracks {numTracks} != paths {paths.Count}");

            var values = ParseAllFloats(text, framesStart, numSamples * numTracks * 7);
            if (values.Count != numSamples * numTracks * 7)
                throw new Exception($"floats {values.Count} != {numSamples * numTracks * 7}");

            var clip = new AnimationClip
            {
                name = clipName,
                frameRate = sampleRate,
                wrapMode = WrapMode.Clamp
            };
            float dt = 1f / sampleRate;
            string[] rotProps = { "m_LocalRotation.x", "m_LocalRotation.y", "m_LocalRotation.z", "m_LocalRotation.w" };
            string[] posProps = { "m_LocalPosition.x", "m_LocalPosition.y", "m_LocalPosition.z" };

            for (int t = 0; t < numTracks; ++t)
            {
                string path = paths[t];
                if (path.StartsWith("hash_", StringComparison.Ordinal)) continue; // templet 外面部骨
                for (int c = 0; c < 4; ++c)
                {
                    var keys = new Keyframe[numSamples];
                    for (int s = 0; s < numSamples; ++s)
                        keys[s] = new Keyframe(s * dt, values[s * numTracks * 7 + t * 7 + c]);
                    clip.SetCurve(path, typeof(Transform), rotProps[c], new AnimationCurve(keys));
                }
                for (int c = 0; c < 3; ++c)
                {
                    var keys = new Keyframe[numSamples];
                    for (int s = 0; s < numSamples; ++s)
                        keys[s] = new Keyframe(s * dt, values[s * numTracks * 7 + t * 7 + 4 + c]);
                    clip.SetCurve(path, typeof(Transform), posProps[c], new AnimationCurve(keys));
                }
            }
            return clip;
        }

        static List<string> ReadTrackPaths(string root, string name)
        {
            var p = Path.Combine(root, TrackPathsDir, name + ".paths.json");
            if (!File.Exists(p)) return null;
            var list = new List<string>();
            string json = File.ReadAllText(p);
            // ["a","b",...] 简单解析
            int i = json.IndexOf('[');
            int e = json.LastIndexOf(']');
            var parts = json.Substring(i + 1, e - i - 1).Split(',');
            foreach (var s in parts)
            {
                var v = s.Trim().Trim('"');
                if (v.Length > 0) list.Add(v);
            }
            return list;
        }

        static int ParseIntAfter(string text, string key)
        {
            int i = text.IndexOf(key, StringComparison.Ordinal);
            int s = i + key.Length;
            int e = s;
            while (e < text.Length && (char.IsDigit(text[e]) || text[e] == '-')) e++;
            return int.Parse(text.Substring(s, e - s), CultureInfo.InvariantCulture);
        }

        static float ParseFloatAfter(string text, string key)
        {
            int i = text.IndexOf(key, StringComparison.Ordinal);
            int s = i + key.Length;
            int e = s;
            while (e < text.Length && (char.IsDigit(text[e]) || text[e] == '-' || text[e] == '.' || text[e] == 'e' || text[e] == 'E' || text[e] == '+')) e++;
            return float.Parse(text.Substring(s, e - s), CultureInfo.InvariantCulture);
        }

        static List<float> ParseAllFloats(string text, int start, int expected)
        {
            var list = new List<float>(expected);
            int i = start;
            int n = text.Length;
            while (i < n && list.Count < expected)
            {
                char ch = text[i];
                if (ch == '-' || ch == '.' || (ch >= '0' && ch <= '9'))
                {
                    int e = i + 1;
                    while (e < n)
                    {
                        char c2 = text[e];
                        if (char.IsDigit(c2) || c2 == '.' || c2 == 'e' || c2 == 'E' || c2 == '+' || c2 == '-') e++;
                        else break;
                    }
                    list.Add(float.Parse(text.Substring(i, e - i), CultureInfo.InvariantCulture));
                    i = e;
                }
                else i++;
            }
            return list;
        }
    }
}
