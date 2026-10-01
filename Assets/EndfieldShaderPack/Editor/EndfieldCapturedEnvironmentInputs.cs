using System;
using System.Collections.Generic;
using System.IO;
using UnityEngine;

namespace EndfieldShaderPack
{
    public static class EndfieldCapturedEnvironmentInputs
    {
        public const string ManifestSha256 = "ea7b832f6ddbf7a13f1d2004e848ac109b19eddeeebcbd9abaf73360a928e2af";
        public const string DefaultExport = "Validation/Captures/native-cloth-environment-20261001-01";
        public static string Source => Environment.GetEnvironmentVariable("ENDFIELD_NATIVE_ENVIRONMENT_EXPORT")
            ?? Path.GetFullPath(Path.Combine(Application.dataPath, "../" + DefaultExport));

        public readonly struct NativeSample
        {
            public readonly int face, mip, x, y;
            public readonly Color rgba;
            internal NativeSample(int faceIndex, int level, int u, int v, Color value)
            { face = faceIndex; mip = level; x = u; y = v; rgba = value; }
        }
        public sealed class Bundle : IDisposable
        {
            public Cubemap Cube { get; private set; }
            public IReadOnlyList<NativeSample> Samples { get; }
            Texture previous;
            float previousAvailable;
            bool bound;
            internal Bundle(Cubemap cube, IReadOnlyList<NativeSample> samples) { Cube = cube; Samples = samples; }
            public void Bind()
            {
                if (bound || Cube == null) throw new InvalidOperationException("Native environment bundle unavailable or already bound.");
                // Validate all CPU blocks again before changing either global;
                // a public in-memory texture may have changed since Load().
                EndfieldCapturedEnvironment.ValidateTexture(Cube);
                previous = Shader.GetGlobalTexture("_CharMaxCubemap");
                previousAvailable = Shader.GetGlobalFloat("_EndfieldCapturedCubemapAvailable");
                Shader.SetGlobalTexture("_CharMaxCubemap", Cube);
                Shader.SetGlobalFloat("_EndfieldCapturedCubemapAvailable", 1);
                bound = true;
            }
            public void Dispose()
            {
                if (bound && Shader.GetGlobalTexture("_CharMaxCubemap") == Cube)
                {
                    Shader.SetGlobalTexture("_CharMaxCubemap", previous);
                    if (Shader.GetGlobalFloat("_EndfieldCapturedCubemapAvailable") == 1)
                        Shader.SetGlobalFloat("_EndfieldCapturedCubemapAvailable", previousAvailable);
                }
                bound = false;
                EndfieldCapturedEnvironment.Release(Cube); Cube = null;
            }
        }

        public static Bundle Load(string folder = null)
        {
            folder = Path.GetFullPath(folder ?? Source);
            byte[] manifest = File.ReadAllBytes(Path.Combine(folder, "complete.json"));
            if (EndfieldCapturedEnvironment.Hash(manifest) != ManifestSha256)
                throw new InvalidDataException("Unreviewed environment manifest.");
            var parsed = (Dictionary<string, object>)MiniJson.Parse(System.Text.Encoding.UTF8.GetString(manifest));
            if ((string)parsed["status"] != "ok" || Convert.ToInt32(parsed["frame"]) != 6411
                || (string)parsed["dds_sha256"] != EndfieldCapturedEnvironment.DdsSha256)
                throw new InvalidDataException("Incomplete native environment evidence.");
            var events = (List<object>)parsed["events"];
            if (events.Count != 2) throw new InvalidDataException("Expected both captured cloth programs.");
            var samples = new List<NativeSample>();
            var first = (Dictionary<string, object>)events[0];
            foreach (Dictionary<string, object> value in (List<object>)first["native_samples"])
            {
                var rgba = (List<object>)value["rgba"];
                samples.Add(new NativeSample(Convert.ToInt32(value["face"]), Convert.ToInt32(value["mip"]),
                    Convert.ToInt32(value["x"]), Convert.ToInt32(value["y"]),
                    new Color(Convert.ToSingle(rgba[0]), Convert.ToSingle(rgba[1]), Convert.ToSingle(rgba[2]), Convert.ToSingle(rgba[3]))));
            }
            if (samples.Count != 144) throw new InvalidDataException("Incomplete native GPU sample evidence.");
            var cube = EndfieldCapturedEnvironment.CreateTexture(File.ReadAllBytes(Path.Combine(folder, "character-environment.dds")));
            return new Bundle(cube, samples.AsReadOnly());
        }

        public static Bundle BindIfRequested(List<string> report)
        {
            if (Environment.GetEnvironmentVariable("ENDFIELD_NATIVE_ENVIRONMENT_INPUTS") != "1") return null;
            var bundle = Load();
            try
            {
                bundle.Bind();
                report?.Add("verified native unsigned BC6H cube; original 6 faces/8 mips; captured bilinear Clamp/mip-point sampler");
                return bundle;
            }
            catch { bundle.Dispose(); throw; }
        }
    }
}
