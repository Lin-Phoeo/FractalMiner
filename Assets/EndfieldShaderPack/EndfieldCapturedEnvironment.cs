using System;
using System.IO;
using System.Security.Cryptography;
using UnityEngine;
using UnityEngine.Experimental.Rendering;

namespace EndfieldShaderPack
{
    // Reviewed native frame6411 cube. No asset import/save, conversion or mip generation.
    public static class EndfieldCapturedEnvironment
    {
        public const string DdsSha256 = "3b0aa26b56ede6b780c186add2778d7155931fa9797ee513db6cd7c2a345b223";
        public const string PayloadSha256 = "898ff663c8d447456666612e55697f7aecde13c03b19b74f9df5b73735e2c9df";
        public const int DdsBytes = 131380;
        public static string Hash(byte[] bytes)
        {
            using (var sha = SHA256.Create())
                return BitConverter.ToString(sha.ComputeHash(bytes)).Replace("-", "").ToLowerInvariant();
        }
        public static Cubemap CreateTexture(byte[] dds)
        {
            if (dds == null || dds.Length != DdsBytes || Hash(dds) != DdsSha256)
                throw new InvalidDataException("Unreviewed or damaged native environment DDS.");
            int[] offsets = { 0, 4, 12, 16, 28, 84, 128, 132, 136, 140 };
            uint[] values = { 0x20534444, 124, 128, 128, 8, 0x30315844, 95, 3, 4, 1 };
            for (int i = 0; i < offsets.Length; i++)
                if (BitConverter.ToUInt32(dds, offsets[i]) != values[i])
                    throw new InvalidDataException("Native cube DX10 contract mismatch.");
            if (!SystemInfo.SupportsTextureFormat(TextureFormat.BC6H))
                throw new NotSupportedException("Native unsigned BC6H required; no fallback conversion.");
            var cube = new Cubemap(128, TextureFormat.BC6H, true)
            {
                name = "CapturedCharacterEnvironmentNative",
                hideFlags = HideFlags.HideAndDontSave,
                filterMode = FilterMode.Bilinear,
                wrapMode = TextureWrapMode.Clamp,
                anisoLevel = 0,
                mipMapBias = 0
            };
            try
            {
                int offset = 148;
                for (int face = 0; face < 6; face++)
                    for (int mip = 0; mip < 8; mip++)
                    {
                        int w = Math.Max(1, 128 >> mip);
                        int length = ((w + 3) / 4) * ((w + 3) / 4) * 16;
                        cube.SetPixelData(dds, mip, (CubemapFace)face, offset);
                        offset += length;
                    }
                if (offset != dds.Length || cube.graphicsFormat != GraphicsFormat.RGB_BC6H_UFloat || cube.mipmapCount != 8)
                    throw new InvalidDataException("Native cube upload format/layout mismatch.");
                cube.Apply(false, false);
                ValidateTexture(cube);
                return cube;
            }
            catch { Release(cube); throw; }
        }
        public static void ValidateTexture(Cubemap cube)
        {
            if (cube == null || !cube.isReadable || cube.width != 128 || cube.mipmapCount != 8
                || cube.graphicsFormat != GraphicsFormat.RGB_BC6H_UFloat
                || cube.filterMode != FilterMode.Bilinear || cube.wrapMode != TextureWrapMode.Clamp
                || cube.anisoLevel != 0 || cube.mipMapBias != 0)
                throw new InvalidDataException("Native cube image/sampler contract changed.");
            var payload = new byte[DdsBytes - 148];
            int offset = 0;
            for (int face = 0; face < 6; face++)
                for (int mip = 0; mip < 8; mip++)
                {
                    int w = Math.Max(1, 128 >> mip);
                    int length = ((w + 3) / 4) * ((w + 3) / 4) * 16;
                    byte[] level = cube.GetPixelData<byte>(mip, (CubemapFace)face).ToArray();
                    if (level.Length != length) throw new InvalidDataException("Native cube mip size changed.");
                    level.CopyTo(payload, offset); offset += length;
                }
            if (offset != payload.Length || Hash(payload) != PayloadSha256)
                throw new InvalidDataException("Native cube modified after creation.");
        }
        public static void Release(Cubemap cube)
        {
            if (cube == null) return;
            if (Application.isPlaying) UnityEngine.Object.Destroy(cube);
            else UnityEngine.Object.DestroyImmediate(cube);
        }
    }
}
