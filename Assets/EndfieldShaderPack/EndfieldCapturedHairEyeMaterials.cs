using System;
using System.Collections.Generic;
using System.IO;
using UnityEngine;
using UnityEngine.Experimental.Rendering;

namespace EndfieldShaderPack
{
    // Offline frame6411 PS22257/22259 only. Raw payload/view identity is
    // immutable; no assets/import settings, format fallback or mip synthesis.
    public static class EndfieldCapturedHairEyeMaterials
    {
        public sealed class Spec
        {
            public readonly int Event,Width,Height,Mips,Bytes;
            public readonly string Role,Property,Hash;
            public readonly bool Srgb,Clamp,Rgba8;
            public string File=>Event+"-"+Role+".raw";
            internal Spec(int draw,string role,string property,int width,int height,int mips,int bytes,bool srgb,bool clamp,bool rgba8,string hash)
            {Event=draw;Role=role;Property=property;Width=width;Height=height;Mips=mips;Bytes=bytes;Srgb=srgb;Clamp=clamp;Rgba8=rgba8;Hash=hash;}
        }
        public static readonly IReadOnlyList<Spec> Specs=Array.AsReadOnly(new[]{
            new Spec(875,"HN","_SplitNormalMap",2048,2048,12,5592432,false,false,false,"ec2c3f98377c635526ff9712f8ddb5e10fa870fd1fbe544d2e9b0d430a57edd9"),
            new Spec(875,"SpecRamp","_SpecRampMap",256,256,1,262144,false,true,true,"63021b62a4612607215756d0ab2805781fa3e25bafe1e47069e6fd47a3feeec2"),
            new Spec(875,"P","_MetallicGlossMap",2048,2048,12,5592432,false,false,false,"9c41f5216aaf6c25248d56d0219925a391bb923fd2b9e73ffbd63a2ac6059c1c"),
            new Spec(875,"Line","_LineMap",512,512,10,349552,false,false,false,"a1970f341cefe9d76ee365b5ea9e281187d439de7e506bf64c8c26ca491641ed"),
            new Spec(875,"DiffRamp","_DiffRampMap",256,1,1,1024,false,true,true,"cdefb217e17f41c0235d2e231eee39bd8355cc2d654494b44631911075acaf9a"),
            new Spec(875,"Base","_BaseMap",2048,2048,12,5592432,true,false,false,"92d7abe5f1092a920869c4f453ca59d1b9c6d0bb2e877792245557d31882c1c6"),
            new Spec(776,"Matcap","_MatcapTex",256,256,9,87408,true,true,false,"2f324c01f1a72a54ffc3766f9f2b4d1a2d850d6a7dd6cd5b1071d4cb614011cc"),
            new Spec(776,"DiffRamp","_DiffRampMap",256,1,1,1024,false,true,true,"4b06cc25fd7266c6c8bf83d6946f4ee7c94458e8d08f5bc9d41e1d3202c28f6b"),
            new Spec(776,"Base","_BaseMap",512,512,10,349552,true,false,false,"a34b9fb8a4406d6105fd5394d7fd30d35e07ee187acdcacf2482ae98a1edf0b5")
        });
        public static int LevelBytes(Spec spec,int mip)
        {
            int w=Math.Max(1,spec.Width>>mip),h=Math.Max(1,spec.Height>>mip);
            return spec.Rgba8?w*h*4:((w+3)/4)*((h+3)/4)*16;
        }
        public static Texture2D CreateTexture(int index,byte[] data)
        {
            var s=Specs[index];
            if(data==null||data.Length!=s.Bytes||EndfieldCapturedClothNormals.Hash(data)!=s.Hash)throw new InvalidDataException("Captured hair/eye payload changed: "+s.File);
            var format=s.Rgba8?TextureFormat.RGBA32:TextureFormat.BC7;
            if(!SystemInfo.SupportsTextureFormat(format))throw new NotSupportedException("Native hair/eye format required: "+format);
            var t=new Texture2D(s.Width,s.Height,format,s.Mips,!s.Srgb){name="CapturedHairEye_"+s.File,hideFlags=HideFlags.HideAndDontSave,
                filterMode=FilterMode.Bilinear,wrapMode=s.Clamp?TextureWrapMode.Clamp:TextureWrapMode.Repeat,anisoLevel=0,mipMapBias=0,ignoreMipmapLimit=true};
            try{t.LoadRawTextureData(data);t.Apply(false,false);ValidateTexture(index,t);return t;}
            catch{EndfieldCapturedClothNormals.Release(t);throw;}
        }
        static void ValidateTexture(int index,Texture2D t)
        {
            var s=Specs[index];var format=s.Rgba8?GraphicsFormat.R8G8B8A8_UNorm:s.Srgb?GraphicsFormat.RGBA_BC7_SRGB:GraphicsFormat.RGBA_BC7_UNorm;
            var wrap=s.Clamp?TextureWrapMode.Clamp:TextureWrapMode.Repeat;
            if(t==null||t.width!=s.Width||t.height!=s.Height||t.mipmapCount!=s.Mips||t.graphicsFormat!=format
                ||t.filterMode!=FilterMode.Bilinear||t.wrapModeU!=wrap||t.wrapModeV!=wrap||t.wrapModeW!=wrap
                ||t.anisoLevel!=0||t.mipMapBias!=0||!t.ignoreMipmapLimit||t.activeMipmapLimit!=0||!t.isReadable
                ||EndfieldCapturedClothNormals.Hash(t.GetRawTextureData<byte>().ToArray())!=s.Hash)
                throw new InvalidDataException("Captured hair/eye texture/view/sampler changed: "+s.File);
        }
        public static void ValidateTextures(IReadOnlyList<Texture2D> textures)
        {
            if(textures==null||textures.Count!=Specs.Count)throw new InvalidDataException("Nine reviewed hair/eye inputs required.");
            for(int i=0;i<textures.Count;i++)ValidateTexture(i,textures[i]);
        }
        public static EndfieldCapturedClothMaterials.Binding Bind(Transform root,IReadOnlyList<Texture2D> textures)
        {
            if(root==null)throw new ArgumentNullException(nameof(root));ValidateTextures(textures);
            // Reuse the already tested generic MPB ownership mechanism housed
            // in ClothMaterials; its slot dictionaries are texture-role agnostic.
            var slots=new List<EndfieldCapturedClothMaterials.Binding.Slot>();bool hairFound=false,eyeFound=false;
            foreach(var renderer in root.GetComponentsInChildren<Renderer>(true))
            {
                var materials=renderer.sharedMaterials;
                for(int index=0;index<materials.Length;index++)
                {
                    var m=materials[index];if(m==null)continue;
                    bool hair=m.name=="M_actor_typhoea_hair_01",eye=m.name=="M_actor_typhoea_iris_01";if(!hair&&!eye)continue;
                    if(m.shader==null||m.shader.name!="Endfield/CharacterLit"||m.GetFloat("_MaterialFamily")!=(hair?2:3)
                        ||m.GetFloat("_UseDiffRampMap")!=1||m.GetFloat("_UseShadowLutTex")!=0
                        ||(hair&&(m.GetFloat("_UseSpecBumpMap")!=1||m.GetFloat("_UseMetallicGlossMap")!=1||m.GetFloat("_UseSpecRampMap")!=1||m.GetFloat("_UseLineMap")!=1))
                        ||(eye&&m.GetFloat("_UseMatcap")!=1))throw new InvalidDataException("Not the reviewed hair/eye variant: "+m.name);
                    var slot=new EndfieldCapturedClothMaterials.Binding.Slot{Renderer=renderer,Index=index,Previous=new MaterialPropertyBlock(),Working=new MaterialPropertyBlock()};
                    renderer.GetPropertyBlock(slot.Previous,index);if(slot.Previous.isEmpty)renderer.GetPropertyBlock(slot.Working);else renderer.GetPropertyBlock(slot.Working,index);
                    for(int i=0;i<Specs.Count;i++)
                    {
                        var s=Specs[i];if(s.Event!=(hair?875:776))continue;var old=slot.Working.GetTexture(s.Property);
                        slot.Restore.Add(s.Property,old!=null?old:m.GetTexture(s.Property)??Texture2D.whiteTexture);slot.Owned.Add(s.Property,textures[i]);slot.Working.SetTexture(s.Property,textures[i]);
                    }
                    slots.Add(slot);hairFound|=hair;eyeFound|=eye;
                }
            }
            if(!hairFound||!eyeFound)throw new InvalidDataException("Both reviewed hair/eye slots required before mutation.");
            var binding=new EndfieldCapturedClothMaterials.Binding(slots);
            try{foreach(var slot in slots)slot.Renderer.SetPropertyBlock(slot.Working,slot.Index);return binding;}
            catch{binding.Dispose();throw;}
        }
    }
}
