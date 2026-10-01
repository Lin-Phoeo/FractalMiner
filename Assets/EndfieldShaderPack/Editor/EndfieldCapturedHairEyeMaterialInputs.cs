using System;
using System.Collections.Generic;
using System.IO;
using UnityEngine;

namespace EndfieldShaderPack
{
    public static class EndfieldCapturedHairEyeMaterialInputs
    {
        public const string ManifestSha256="879c9064fbabdaafed25d798928cc20f730e235ea709abe1f3d91d63c70a158b";
        public const string DefaultExport="Validation/Captures/native-hair-eye-inputs-20261001-01";
        public static string Source=>Environment.GetEnvironmentVariable("ENDFIELD_HAIR_EYE_MATERIAL_EXPORT")??Path.GetFullPath(Path.Combine(Application.dataPath,"../"+DefaultExport));
        public readonly struct Sample
        {
            public readonly int Mip,X,Y;public readonly Color Rgba;
            internal Sample(int mip,int x,int y,Color rgba){Mip=mip;X=x;Y=y;Rgba=rgba;}
        }
        public sealed class Bundle : IDisposable
        {
            readonly Texture2D[] textures;readonly List<Sample>[] samples;EndfieldCapturedClothMaterials.Binding binding;bool disposed;
            public IReadOnlyList<Texture2D> Textures=>Array.AsReadOnly(textures);
            public IReadOnlyList<Sample> NativeSamples(int index)=>samples[index].AsReadOnly();
            public int SlotCount=>binding?.SlotCount??0;
            internal Bundle(Texture2D[] maps,List<Sample>[] evidence){textures=maps;samples=evidence;}
            public void Bind(Transform root)
            {if(disposed||binding!=null)throw new InvalidOperationException("Disposed/already bound hair/eye inputs.");binding=EndfieldCapturedHairEyeMaterials.Bind(root,textures);}
            public void Dispose()
            {if(disposed)return;disposed=true;binding?.Dispose();binding=null;foreach(var t in textures)EndfieldCapturedClothNormals.Release(t);}
        }
        public static Bundle Load(string folder=null)
        {
            folder=Path.GetFullPath(folder??Source);byte[] manifest=File.ReadAllBytes(Path.Combine(folder,"complete.json"));
            if(EndfieldCapturedClothNormals.Hash(manifest)!=ManifestSha256)throw new InvalidDataException("Unreviewed native hair/eye manifest.");
            var parsed=(Dictionary<string,object>)MiniJson.Parse(System.Text.Encoding.UTF8.GetString(manifest));
            if((string)parsed["status"]!="ok"||Convert.ToInt32(parsed["frame"])!=6411)throw new InvalidDataException("Incomplete hair/eye capture.");
            var entries=(List<object>)parsed["textures"];if(entries.Count!=9)throw new InvalidDataException("Nine hair/eye bindings expected.");
            var payloads=new byte[9][];var samples=new List<Sample>[9];
            for(int i=0;i<9;i++)
            {
                var s=EndfieldCapturedHairEyeMaterials.Specs[i];Dictionary<string,object> entry=null;
                foreach(Dictionary<string,object> candidate in entries)
                    if(Convert.ToInt32(candidate["event"])==s.Event&&(string)candidate["role"]==s.Role)
                    {if(entry!=null)throw new InvalidDataException("Duplicate hair/eye evidence.");entry=candidate;}
                if(entry==null||(string)entry["file"]!=s.File||(string)entry["sha256"]!=s.Hash||(string)entry["sample_cast"]!=(s.Srgb?"CompType.UNormSRGB":"CompType.UNorm"))
                    throw new InvalidDataException("Unexpected hair/eye payload path/identity/view domain.");
                payloads[i]=File.ReadAllBytes(Path.Combine(folder,s.File));
                if(payloads[i].Length!=s.Bytes||EndfieldCapturedClothNormals.Hash(payloads[i])!=s.Hash)throw new InvalidDataException("Hair/eye payload changed: "+s.File);
                samples[i]=new List<Sample>();
                foreach(Dictionary<string,object> value in (List<object>)entry["native_samples"])
                {
                    var rgba=(List<object>)value["rgba"];samples[i].Add(new Sample(Convert.ToInt32(value["mip"]),Convert.ToInt32(value["x"]),Convert.ToInt32(value["y"]),
                        new Color(Convert.ToSingle(rgba[0]),Convert.ToSingle(rgba[1]),Convert.ToSingle(rgba[2]),Convert.ToSingle(rgba[3]))));
                }
                if(samples[i].Count!=s.Mips*5)throw new InvalidDataException("Incomplete hair/eye native samples.");
            }
            var maps=new Texture2D[9];
            try{for(int i=0;i<maps.Length;i++)maps[i]=EndfieldCapturedHairEyeMaterials.CreateTexture(i,payloads[i]);return new Bundle(maps,samples);}
            catch{foreach(var t in maps)EndfieldCapturedClothNormals.Release(t);throw;}
        }
        public static Bundle BindIfRequested(Transform root,List<string> report)
        {
            if(Environment.GetEnvironmentVariable("ENDFIELD_HAIR_EYE_NATIVE_MATERIALS")!="1")return null;var bundle=Load();
            try{bundle.Bind(root);report?.Add("native captured Hair HN/P/Line/Base/ramps and Eye Matcap/Base/ramp; slots="+bundle.SlotCount);return bundle;}
            catch{bundle.Dispose();throw;}
        }
    }
}
