// ============================================================
//  EndfieldNormalDecompress.cs
//  终末地压缩法线解压工具
//
//  终末地把切线空间法线的 xyz 三个分量压缩进一个 float：
//    bit 0..9   -> x (10bit 有符号)
//    bit 10..19 -> y (10bit 有符号)
//    bit 20..29 -> z (10bit 有符号)
//    bit 31     -> 原 float 的符号位 (存第 4 个分量，通常用于
//                  记录切线镜像/另一法线的符号信息)
//
//  用法：
//    1. 把压缩后的法线贴图设为瑞读、单通道 float 格式
//       (Texture2D, format = TextureFormat.RFloat 或 R16/R32),
//       压缩值放在 R 通道。
//    2. 在菜单 Assets → Endfield → Decode Normal Map 对选中贴图
//       执行解码，输出 RGBA 法线贴图 (xyz=法线, w=符号信息)。
//    3. 把输出贴图赋给 shader 的 _BumpMap。
//
//  参考：死夢めぐり 的源码中明确指出"未实现法线解码函数"，本工具
//  补齐这块；算法来自公开的终末地法线压缩分析 (tajourney.games/7980)。
// ============================================================
using UnityEngine;

#if UNITY_EDITOR
using UnityEditor;
#endif

namespace Endfield
{
    public static class NormalDecompress
    {
        /// <summary>
        /// 解压单个压缩 float，返回 (x, y, z, 符号分量)。
        /// xyz 已映射到 [-1, 1] 区间。
        /// </summary>
        public static Vector4 Decompress(float compressed)
        {
            uint bits = (uint)BitConverterToUInt(compressed);

            int x = Extract10BitSigned(bits, 22); // bits 0..9
            int y = Extract10BitSigned(bits, 12); // bits 10..19
            int z = Extract10BitSigned(bits, 2);  // bits 20..29

            // 10bit 有符号数范围 [-512, 511]，除以 512 映射到 [-1, 1]
            const float scale = 1.0f / 512.0f;
            float w = ((bits >> 31) & 1u) == 1u ? 1.0f : -1.0f;

            return new Vector4(x * scale, y * scale, z * scale, w);
        }

        // 从 bit offset 处提取 10bit 有符号整数（符号位为 bit offset+9）
        static int Extract10BitSigned(uint value, int shift)
        {
            return (int)(value << shift) >> 22;
        }

        static uint BitConverterToUInt(float f)
        {
            // 安全重解释 float -> 原始位模式（避免 unsafe）
            return (uint)System.BitConverter.ToInt32(System.BitConverter.GetBytes(f), 0);
        }

        /// <summary>
        /// 把单通道 float 贴图逐像素解压成切线空间法线贴图
        /// (RGB = 法线, A = 符号分量)。
        /// </summary>
        public static Texture2D DecodeTexture(Texture2D source)
        {
            int w = source.width;
            int h = source.height;

            // 读取时强制为可读的 float 数据
            var rt = RenderTexture.GetTemporary(w, h, 0, RenderTextureFormat.RFloat);
            Graphics.Blit(source, rt);
            var prev = RenderTexture.active;
            RenderTexture.active = rt;

            Texture2D src = new Texture2D(w, h, TextureFormat.RFloat, false);
            src.ReadPixels(new Rect(0, 0, w, h), 0, 0);
            src.Apply();

            Color[] srcPixels = src.GetPixels();
            RenderTexture.active = prev;
            RenderTexture.ReleaseTemporary(rt);

            Texture2D result = new Texture2D(w, h, TextureFormat.RGBA32, true);
            Color[] dst = new Color[w * h];
            for (int i = 0; i < srcPixels.Length; i++)
            {
                Vector4 n = Decompress(srcPixels[i].r);
                dst[i] = new Color(n.x * 0.5f + 0.5f,      // R: x -> [0,1]
                                   n.y * 0.5f + 0.5f,      // G: y -> [0,1]
                                   n.z * 0.5f + 0.5f,      // B: z -> [0,1]
                                   n.w * 0.5f + 0.5f);     // A: 符号 -> [0,1]
            }
            result.SetPixels(dst);
            result.Apply(true);
            Object.DestroyImmediate(src);
            return result;
        }
    }

#if UNITY_EDITOR
    public static class NormalDecompressMenu
    {
        [MenuItem("Assets/Endfield/Decode Normal Map", false, 30)]
        static void DecodeSelected()
        {
            var tex = Selection.activeObject as Texture2D;
            if (tex == null)
            {
                EditorUtility.DisplayDialog("Endfield", "请先在 Project 中选中一张压缩法线贴图。", "OK");
                return;
            }
            Texture2D decoded = NormalDecompress.DecodeTexture(tex);
            string path = AssetDatabase.GetAssetPath(tex);
            string dir = System.IO.Path.GetDirectoryName(path);
            string name = System.IO.Path.GetFileNameWithoutExtension(path) + "_Normal.png";
            string outPath = System.IO.Path.Combine(dir, name);
            System.IO.File.WriteAllBytes(outPath, decoded.EncodeToPNG());
            AssetDatabase.Refresh();
            Object.DestroyImmediate(decoded);
            Debug.Log("Decoded normal map written to: " + outPath);
        }
    }
#endif
}