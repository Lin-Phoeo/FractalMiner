using System;
using System.Linq;
using EndfieldShaderPack.CapturedData;
using Newtonsoft.Json;

internal static class Program
{
    static void Check(bool value, string label)
    {
        if (!value) throw new InvalidOperationException(label);
    }

    public static int Main(string[] args)
    {
        try
        {
            var bundle = NativeCapturedDrawData.Load(args[1], args[2]);
            if (args[0] == "unorm")
            {
                var weights = bundle.GetDraw(835).GetInput(8);
                Check(weights.ReadNormalizedComponent(0, 0) == 1.0, "UNORM denominator changed");
                Check(bundle.GetDraw(835).GetInput(9).ReadUnsignedComponent(0, 0) == 17, "u8 slot changed");
                bool badVertex = false, badComponent = false, badBits = false;
                try { weights.ReadNormalizedComponent(99, 0); } catch (ArgumentOutOfRangeException) { badVertex = true; }
                try { weights.ReadNormalizedComponent(0, -1); } catch (ArgumentOutOfRangeException) { badComponent = true; }
                try { weights.ReadUInt32Bits(0, 0); } catch (System.IO.InvalidDataException) { badBits = true; }
                Check(badVertex && badComponent && badBits, "Typed read bounds/width not enforced");
            }
            if (args[0] == "fixture")
            {
                var draw = bundle.GetDraw(835);
                var weights = draw.GetInput(8);
                var slots = draw.GetInput(9);
                Check(weights.ReadFloat32(0, 0) == .2f, "f32 weights changed");
                Check(weights.ReadUInt32Bits(1, 1) == 0x80000000u, "negative zero changed");
                Check(slots.ReadUnsignedComponent(0, 0) == 300, "u32 slot truncated");
                Check(draw.GetInput(2).ReadUInt32Bits(0, 0) == 0xffc00001u, "packed NaN bits changed");
                Check(draw.GetInput(6).ReadUInt32Bits(0, 0) == 0x400001ffu, "rest bits changed");
                Check(draw.GetInput(0).CopyBytes().SequenceEqual(draw.GetInput(5).CopyBytes()), "alias bytes changed");
                Check(!ReferenceEquals(draw.GetInput(0), draw.GetInput(5)), "logical inputs merged");
                var copy = weights.CopyBytes(); copy[0] ^= 255;
                Check(weights.ReadFloat32(0, 0) == .2f, "consumer mutated internal cache");
                Check(draw.CopyIndexBytes().SequenceEqual(new byte[] { 5, 0, 6, 0, 5, 0 }), "indices rebased");
                Check((int)draw.SourceRecord["base_vertex"] == -2, "base vertex lost");
                var mutable = draw.SourceRecord; mutable["base_vertex"] = 999;
                Check((int)draw.SourceRecord["base_vertex"] == -2, "source metadata mutable");
                bool missing = false;
                try { draw.GetInput(7); } catch (System.Collections.Generic.KeyNotFoundException) { missing = true; }
                Check(missing, "absent rest tangent fabricated");
                bool wrongType = false;
                try { weights.ReadNormalizedComponent(0, 0); } catch (System.IO.InvalidDataException) { wrongType = true; }
                Check(wrongType, "float weights treated as unorm");
            }
            Console.WriteLine(JsonConvert.SerializeObject(new {
                ok = true, rendering_certified = false, mesh_mapping_ready = false,
                draws = bundle.EventIds.Count, vertices = bundle.EventIds.Sum(id => bundle.GetDraw(id).VertexCount),
                streams = bundle.EventIds.Sum(id => bundle.GetDraw(id).Locations.Count),
                manifest_sha256 = bundle.ManifestSha256
            }));
            return 0;
        }
        catch (Exception error)
        {
            Console.Error.WriteLine(error.GetType().Name + ": " + error.Message);
            return 1;
        }
    }
}
