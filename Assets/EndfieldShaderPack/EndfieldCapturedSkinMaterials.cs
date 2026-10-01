using System;
using System.Collections.Generic;
using System.IO;
using UnityEngine;
using UnityEngine.Experimental.Rendering;

namespace EndfieldShaderPack
{
    // Reviewed offline frame6411 PS22250/37671 inputs. No asset writes,
    // transcode, regenerated mips, adjustable identity or format fallback.
    public static class EndfieldCapturedSkinMaterials
    {
        public sealed class Spec
        {
            public readonly int Event, Width, Height, Mips, Bytes;
            public readonly string Role, Property, Hash;
            public readonly TextureFormat Format;
            public readonly bool Srgb, Clamp;
            public string File => Event + "-" + Role + ".raw";
            internal Spec(int draw, string role, string property, int width, int height, int mips, int bytes,
                TextureFormat format, bool srgb, bool clamp, string hash)
            { Event=draw; Role=role; Property=property; Width=width; Height=height; Mips=mips; Bytes=bytes; Format=format; Srgb=srgb; Clamp=clamp; Hash=hash; }
        }
        public static readonly IReadOnlyList<Spec> Specs = Array.AsReadOnly(new[] {
            new Spec(786,"ShadowLUT","_ShadowLutTex",1024,32,11,44048,TextureFormat.BC7,true,true,"8b4782f6485be2d361f29743eccaee900c269512c659fe69e4bb3f9f2a733828"),
            new Spec(786,"DiffRamp","_DiffRampMap",256,1,1,1024,TextureFormat.RGBA32,false,true,"4b06cc25fd7266c6c8bf83d6946f4ee7c94458e8d08f5bc9d41e1d3202c28f6b"),
            new Spec(786,"Normal","_BumpMap",512,512,10,349552,TextureFormat.BC5,false,false,"4f34bb4177e7ccf9db28cb065f340d7b65aa2cda3bed160a6b0bf10a1a1bc07e"),
            new Spec(786,"Base","_BaseMap",512,512,10,349552,TextureFormat.BC7,true,false,"0563c228ea706da12b9f796983dd5787bd246362ef679f9267d4fe19a3ce7ef9"),
            new Spec(860,"SDFMask","_SDFMask",512,512,10,349552,TextureFormat.BC7,false,true,"3ab55f5b4f76fba4ce5824b05c5c63569551503c5bcacf198a0678e201bd9192"),
            new Spec(860,"SDF","_SDFLightmap",1024,1024,1,4194304,TextureFormat.RGBA32,false,true,"7284db29e3edaafb0585385a033207b1bdc56580a73ceb0097cac430b1c6bfad"),
            new Spec(860,"Highlight","_HighlightMap",512,512,10,349552,TextureFormat.BC7,false,false,"8cf0e8d95fdbf17a7f393353a32585a32473465b5f067130bf122bc67fb49114"),
            new Spec(860,"Emotion","_EmotionMap",1024,1024,11,1398128,TextureFormat.BC7,true,false,"601e9c612d9a36024d86673f857a25bce73eb137ad90df2ebd2c0e012b46b6a3"),
            new Spec(860,"Normal","_BumpMap",1024,1024,11,1398128,TextureFormat.BC5,false,false,"314159f16c55cf8f7a16388c00191498994ef094bd11e8e44c532aba3e5f0e11"),
            new Spec(860,"Base","_BaseMap",1024,1024,11,1398128,TextureFormat.BC7,true,false,"e0f29a84f05e74b1cf52d73466bb2f2c73954d0a37c1ff4a13c5cf36369de6e2")
        });
        public static int LevelBytes(Spec spec, int mip)
        {
            int w=Math.Max(1,spec.Width>>mip),h=Math.Max(1,spec.Height>>mip);
            return spec.Format==TextureFormat.RGBA32 ? w*h*4 : ((w+3)/4)*((h+3)/4)*16;
        }
        public static Texture2D CreateTexture(int index, byte[] data)
        {
            var spec=Specs[index];
            if(data==null || data.Length!=spec.Bytes || EndfieldCapturedClothNormals.Hash(data)!=spec.Hash)
                throw new InvalidDataException("Captured skin payload identity mismatch: "+spec.File);
            if(!SystemInfo.SupportsTextureFormat(spec.Format))throw new NotSupportedException("Native skin format required: "+spec.Format);
            var texture=new Texture2D(spec.Width,spec.Height,spec.Format,spec.Mips,!spec.Srgb) {
                name="CapturedSkin_"+spec.File,hideFlags=HideFlags.HideAndDontSave,
                filterMode=FilterMode.Bilinear,wrapMode=spec.Clamp?TextureWrapMode.Clamp:TextureWrapMode.Repeat,
                anisoLevel=0,mipMapBias=0,ignoreMipmapLimit=true
            };
            try {texture.LoadRawTextureData(data);texture.Apply(false,false);ValidateTexture(index,texture);return texture;}
            catch {EndfieldCapturedClothNormals.Release(texture);throw;}
        }
        static void ValidateTexture(int index, Texture2D texture)
        {
            var s=Specs[index];
            var format=s.Format==TextureFormat.BC5?GraphicsFormat.RG_BC5_UNorm:s.Format==TextureFormat.RGBA32?GraphicsFormat.R8G8B8A8_UNorm:s.Srgb?GraphicsFormat.RGBA_BC7_SRGB:GraphicsFormat.RGBA_BC7_UNorm;
            var wrap=s.Clamp?TextureWrapMode.Clamp:TextureWrapMode.Repeat;
            if(texture==null || texture.width!=s.Width || texture.height!=s.Height || texture.mipmapCount!=s.Mips
                || texture.graphicsFormat!=format || texture.filterMode!=FilterMode.Bilinear
                || texture.wrapModeU!=wrap || texture.wrapModeV!=wrap || texture.wrapModeW!=wrap
                || texture.anisoLevel!=0 || texture.mipMapBias!=0 || !texture.ignoreMipmapLimit || texture.activeMipmapLimit!=0
                || !texture.isReadable || EndfieldCapturedClothNormals.Hash(texture.GetRawTextureData<byte>().ToArray())!=s.Hash)
                throw new InvalidDataException("Captured skin texture/view/sampler changed: "+s.File);
        }
        public static void ValidateTextures(IReadOnlyList<Texture2D> textures)
        {
            if(textures==null || textures.Count!=Specs.Count)throw new InvalidDataException("Ten reviewed skin images required.");
            for(int i=0;i<textures.Count;i++)ValidateTexture(i,textures[i]);
        }
        // Exclusive short-lived render scope. A foreign texture replacement is
        // preserved while still-owned textures are detached before release.
        public sealed class Binding : IDisposable
        {
            internal sealed class Slot
            {
                internal Renderer Renderer;
                internal int Index;
                internal MaterialPropertyBlock Previous, Working;
                internal readonly Dictionary<string,Texture> Owned=new Dictionary<string,Texture>();
                internal readonly Dictionary<string,Texture> Restore=new Dictionary<string,Texture>();
            }
            readonly List<Slot> slots; bool disposed;
            public int SlotCount=>slots.Count;
            internal Binding(List<Slot> value){slots=value;}
            public void Dispose()
            {
                if(disposed)return;disposed=true;
                foreach(var slot in slots)
                {
                    if(slot.Renderer==null)continue;
                    var current=new MaterialPropertyBlock();slot.Renderer.GetPropertyBlock(current,slot.Index);
                    bool owns=true;foreach(var input in slot.Owned)owns&=current.GetTexture(input.Key)==input.Value;
                    if(owns)slot.Renderer.SetPropertyBlock(slot.Previous.isEmpty?null:slot.Previous,slot.Index);
                    else
                    {
                        foreach(var input in slot.Owned)
                            if(current.GetTexture(input.Key)==input.Value)current.SetTexture(input.Key,slot.Restore[input.Key]);
                        slot.Renderer.SetPropertyBlock(current,slot.Index);
                    }
                }
            }
        }
        public static Binding Bind(Transform root,IReadOnlyList<Texture2D> textures)
        {
            if(root==null)throw new ArgumentNullException(nameof(root));ValidateTextures(textures);
            var slots=new List<Binding.Slot>();bool bodyFound=false,faceFound=false;
            foreach(var renderer in root.GetComponentsInChildren<Renderer>(true))
            {
                var materials=renderer.sharedMaterials;
                for(int i=0;i<materials.Length;i++)
                {
                    var m=materials[i];if(m==null)continue;
                    bool body=m.name=="M_actor_typhoea_body_01",face=m.name=="M_actor_typhoea_face_01";
                    if(!body&&!face)continue;
                    if(m.shader==null || m.shader.name!="Endfield/CharacterLit" || m.GetFloat("_MaterialFamily")!=1
                        || m.GetFloat("_UseBumpMap")!=1 || m.GetFloat("_UseShadowLutTex")!=1 || m.GetFloat("_UseDiffRampMap")!=1
                        || m.GetFloat("_UseSDFLightmap")!=(face?1:0) || m.GetFloat("_UseEmotionMap")!=(face?1:0))
                        throw new InvalidDataException("Not the reviewed skin variant: "+m.name);
                    var slot=new Binding.Slot{Renderer=renderer,Index=i,Previous=new MaterialPropertyBlock(),Working=new MaterialPropertyBlock()};
                    renderer.GetPropertyBlock(slot.Previous,i);
                    if(slot.Previous.isEmpty)renderer.GetPropertyBlock(slot.Working);else renderer.GetPropertyBlock(slot.Working,i);
                    for(int t=0;t<Specs.Count;t++)
                    {
                        var spec=Specs[t];if(t>1&&spec.Event!=(body?786:860))continue;
                        var old=slot.Working.GetTexture(spec.Property);
                        slot.Restore.Add(spec.Property,old!=null?old:m.GetTexture(spec.Property)??Texture2D.whiteTexture);
                        slot.Owned.Add(spec.Property,textures[t]);slot.Working.SetTexture(spec.Property,textures[t]);
                    }
                    slots.Add(slot);bodyFound|=body;faceFound|=face;
                }
            }
            if(!bodyFound||!faceFound)throw new InvalidDataException("Both reviewed skin slots required before mutation.");
            var binding=new Binding(slots);
            try {foreach(var slot in slots)slot.Renderer.SetPropertyBlock(slot.Working,slot.Index);return binding;}
            catch {binding.Dispose();throw;}
        }
    }
}
