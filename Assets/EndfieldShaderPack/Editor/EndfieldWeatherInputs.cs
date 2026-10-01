using System;
using System.Collections.Generic;
using System.IO;
using UnityEngine;

namespace EndfieldShaderPack
{
    public sealed class EndfieldWeatherInputs : IDisposable
    {
        public const string Source = "Validation/Captures/character-weather-20261001-02";
        public const string ManifestHash = "97a4ec882d4eaa27a459167bc3f254f3b57ae782dc2c84d3ab2164b983630b96";
        public Texture2D Rain { get; private set; }
        public Texture2D Streak { get; private set; }
        public Dictionary<string, object> Manifest { get; private set; }
        public static EndfieldWeatherInputs Load()
        {
            string folder = Path.GetFullPath(Path.Combine(Application.dataPath, "../" + Source));
            byte[] json = File.ReadAllBytes(Path.Combine(folder, "complete.json"));
            if (EndfieldCapturedClothNormals.Hash(json) != ManifestHash)
                throw new InvalidDataException("Unreviewed weather manifest; do not auto-trust another capture.");
            var manifest = (Dictionary<string, object>)MiniJson.Parse(System.Text.Encoding.UTF8.GetString(json));
            if ((string)manifest["status"] != "ok" || Convert.ToInt32(manifest["frame"]) != 6411)
                throw new InvalidDataException("Incomplete weather export.");
            if (!SystemInfo.SupportsTextureFormat(TextureFormat.BC7)) throw new NotSupportedException("Native BC7 required.");
            var bundle = new EndfieldWeatherInputs { Manifest = manifest };
            try
            {
                bundle.Rain = Read(folder, "835-Rain.raw", 1024, 11, 1398128,
                    "72e3d00a34c5d8edf00b98444af9ae8fae92789bd4c90f15431408e9f04dd92a");
                bundle.Streak = Read(folder, "835-Streak.raw", 256, 9, 87408,
                    "05f5a7d6ed00cdeeeff63cf6a0380d77421e8272b22f86d94c47a660770b316c");
                return bundle;
            }
            catch { bundle.Dispose(); throw; }
        }
        static Texture2D Read(string folder, string file, int size, int mipCount, int bytes, string hash)
        {
            byte[] raw = File.ReadAllBytes(Path.Combine(folder, file));
            if (raw.Length != bytes || EndfieldCapturedClothNormals.Hash(raw) != hash)
                throw new InvalidDataException("Changed weather payload: " + file);
            var texture = new Texture2D(size, size, TextureFormat.BC7, mipCount, true)
                { name = file, hideFlags = HideFlags.HideAndDontSave, filterMode = FilterMode.Bilinear,
                  wrapMode = TextureWrapMode.Repeat, anisoLevel = 0, ignoreMipmapLimit = true };
            try { texture.LoadRawTextureData(raw); texture.Apply(false, false); return texture; }
            catch { UnityEngine.Object.DestroyImmediate(texture); throw; }
        }
        public void Dispose()
        {
            if (Rain != null) UnityEngine.Object.DestroyImmediate(Rain);
            if (Streak != null) UnityEngine.Object.DestroyImmediate(Streak);
            Rain = Streak = null;
        }
    }
}
