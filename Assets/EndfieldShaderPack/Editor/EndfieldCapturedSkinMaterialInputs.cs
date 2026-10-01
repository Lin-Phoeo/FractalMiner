using System;
using System.Collections.Generic;
using System.IO;
using UnityEngine;

namespace EndfieldShaderPack
{
    public static class EndfieldCapturedSkinMaterialInputs
    {
        public const string ManifestSha256="e5dda0870d25bbe7411e95597ff2835c9086ae82b8612313c668d6ac4eb1840b";
        public const string DefaultExport="Validation/Captures/native-skin-inputs-20261001-01";
        public static string Source=>Environment.GetEnvironmentVariable("ENDFIELD_SKIN_MATERIAL_EXPORT")
            ??Path.GetFullPath(Path.Combine(Application.dataPath,"../"+DefaultExport));
        public readonly struct Sample
        {
            public readonly int Mip,X,Y;public readonly Color Rgba;
            internal Sample(int mip,int x,int y,Color value){Mip=mip;X=x;Y=y;Rgba=value;}
        }
        public sealed class Bundle : IDisposable
        {
            readonly Texture2D[] textures;readonly List<Sample>[] samples;
            EndfieldCapturedSkinMaterials.Binding binding;bool disposed;
            public IReadOnlyList<Texture2D> Textures=>Array.AsReadOnly(textures);
            public IReadOnlyList<Sample> NativeSamples(int index)=>samples[index].AsReadOnly();
            public int SlotCount=>binding?.SlotCount??0;
            internal Bundle(Texture2D[] maps,List<Sample>[] evidence){textures=maps;samples=evidence;}
            public void Bind(Transform root)
            {
                if(disposed||binding!=null)throw new InvalidOperationException("Disposed/already bound skin inputs.");
                binding=EndfieldCapturedSkinMaterials.Bind(root,textures);
            }
            public void Dispose()
            {
                if(disposed)return;disposed=true;binding?.Dispose();binding=null;
                foreach(var texture in textures)EndfieldCapturedClothNormals.Release(texture);
            }
        }
        public static Bundle Load(string folder=null)
        {
            folder=Path.GetFullPath(folder??Source);byte[] manifest=File.ReadAllBytes(Path.Combine(folder,"complete.json"));
            if(EndfieldCapturedClothNormals.Hash(manifest)!=ManifestSha256)throw new InvalidDataException("Unreviewed native skin manifest.");
            var parsed=(Dictionary<string,object>)MiniJson.Parse(System.Text.Encoding.UTF8.GetString(manifest));
            if((string)parsed["status"]!="ok"||Convert.ToInt32(parsed["frame"])!=6411)throw new InvalidDataException("Incomplete skin capture.");
            var entries=(List<object>)parsed["textures"];if(entries.Count!=12)throw new InvalidDataException("Twelve skin bindings expected.");
            var payloads=new byte[10][];var samples=new List<Sample>[10];
            for(int i=0;i<10;i++)
            {
                var spec=EndfieldCapturedSkinMaterials.Specs[i];Dictionary<string,object> entry=null;
                foreach(Dictionary<string,object> candidate in entries)
                    if(Convert.ToInt32(candidate["event"])==spec.Event&&(string)candidate["role"]==spec.Role)
                    {if(entry!=null)throw new InvalidDataException("Duplicate skin evidence.");entry=candidate;}
                if(entry==null||(string)entry["file"]!=spec.File||(string)entry["sha256"]!=spec.Hash
                    ||(string)entry["sample_cast"]!=(spec.Srgb?"CompType.UNormSRGB":"CompType.UNorm"))
                    throw new InvalidDataException("Unexpected skin payload path/identity/view domain.");
                payloads[i]=File.ReadAllBytes(Path.Combine(folder,spec.File));
                if(payloads[i].Length!=spec.Bytes||EndfieldCapturedClothNormals.Hash(payloads[i])!=spec.Hash)throw new InvalidDataException("Skin payload changed: "+spec.File);
                samples[i]=new List<Sample>();
                foreach(Dictionary<string,object> value in (List<object>)entry["native_samples"])
                {
                    var rgba=(List<object>)value["rgba"];
                    samples[i].Add(new Sample(Convert.ToInt32(value["mip"]),Convert.ToInt32(value["x"]),Convert.ToInt32(value["y"]),
                        new Color(Convert.ToSingle(rgba[0]),Convert.ToSingle(rgba[1]),Convert.ToSingle(rgba[2]),Convert.ToSingle(rgba[3]))));
                }
                if(samples[i].Count!=spec.Mips*5)throw new InvalidDataException("Incomplete native skin samples.");
            }
            var maps=new Texture2D[10];
            try {for(int i=0;i<maps.Length;i++)maps[i]=EndfieldCapturedSkinMaterials.CreateTexture(i,payloads[i]);return new Bundle(maps,samples);}
            catch {foreach(var texture in maps)EndfieldCapturedClothNormals.Release(texture);throw;}
        }
        public static Bundle BindIfRequested(Transform root,List<string> report)
        {
            if(Environment.GetEnvironmentVariable("ENDFIELD_SKIN_NATIVE_MATERIALS")!="1")return null;
            var bundle=Load();
            try {bundle.Bind(root);report?.Add("native captured body/face Base/N/LUT/ramp/SDFMask/SDF/Highlight/Emotion; slots="+bundle.SlotCount);return bundle;}
            catch {bundle.Dispose();throw;}
        }
    }
}
