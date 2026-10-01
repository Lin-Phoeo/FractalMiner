using System;
using System.Collections.Generic;
using System.IO;
using UnityEngine;
using UnityEngine.Experimental.Rendering;

namespace EndfieldShaderPack
{
    // Reviewed frame6411 inputs only. The view's sRGB bit is part of identity.
    // No material/scene/import writes, transcoding, new mips or fitting constants.
    public static class EndfieldCapturedClothMaterials
    {
        public sealed class Spec
        {
            public readonly int Event, Width, Height, Mips, Bytes;
            public readonly string Role, Hash, Property;
            public readonly bool Srgb;
            public bool Ramp => Role.EndsWith("Ramp", StringComparison.Ordinal);
            public string File => Event + "-" + Role + ".raw";
            internal Spec(int draw, string role, string property, string hash, bool srgb = false)
            {
                Event = draw; Role = role; Property = property; Hash = hash; Srgb = srgb;
                Width = Ramp ? 256 : 2048; Height = role == "DiffRamp" ? 1 : Width;
                Mips = Ramp ? 1 : 12; Bytes = Ramp ? Width * Height * 4 : 5592432;
            }
        }
        public static readonly IReadOnlyList<Spec> Specs = Array.AsReadOnly(new[] {
            new Spec(835, "Base", "_BaseMap", "27f50de5a07fc1b86ba195236a18beab4f254413ca0a8ef35708629e491eee15", true),
            new Spec(835, "P", "_MetallicGlossMap", "258f59db1a976fb51b7f947bcad79101c7df3045858f1ec117ff6463ef352480"),
            new Spec(850, "Base", "_BaseMap", "8cd4c98c7c829e674e885fd5e66fa5c6f364468d038cc224229d8af9d6b0d45d", true),
            new Spec(850, "P", "_MetallicGlossMap", "b581a8c3bbad96d707c0e051b842f42af7eaf4a795e876942695d8d26ebb97f0"),
            new Spec(850, "E", "_EmissionMap", "4f6007669e944e1e61f3ca2881ea55a52d037e3f95561dd3a7c625192d776f21", true),
            new Spec(835, "DiffRamp", "_DiffRampMap", "b067b42b9818b576ec9e9dba39493731f17346fc1c0dae22d2ace53a52c2b538"),
            new Spec(835, "SpecRamp", "_SpecRampMap", "538181418de6d5f0f9529923b74966d080ffeb8f85e08a0c07ebce2cdd9cd607")
        });
        public static int LevelBytes(Spec spec, int mip)
        {
            int w = Math.Max(1, spec.Width >> mip), h = Math.Max(1, spec.Height >> mip);
            return spec.Ramp ? w * h * 4 : ((w + 3) / 4) * ((h + 3) / 4) * 16;
        }
        public static Texture2D CreateTexture(int index, byte[] data)
        {
            var spec = Specs[index];
            if (data == null || data.Length != spec.Bytes || EndfieldCapturedClothNormals.Hash(data) != spec.Hash)
                throw new InvalidDataException("Captured cloth payload identity mismatch: " + spec.File);
            var format = spec.Ramp ? TextureFormat.RGBA32 : TextureFormat.BC7;
            if (!SystemInfo.SupportsTextureFormat(format)) throw new NotSupportedException("Native cloth format required: " + format);
            var texture = new Texture2D(spec.Width, spec.Height, format, spec.Mips, !spec.Srgb) {
                name = "CapturedCloth_" + spec.File, hideFlags = HideFlags.HideAndDontSave,
                filterMode = FilterMode.Bilinear, wrapMode = spec.Ramp ? TextureWrapMode.Clamp : TextureWrapMode.Repeat,
                anisoLevel = 0, mipMapBias = 0, ignoreMipmapLimit = true
            };
            try { texture.LoadRawTextureData(data); texture.Apply(false, false); ValidateTexture(index, texture); return texture; }
            catch { EndfieldCapturedClothNormals.Release(texture); throw; }
        }
        static void ValidateTexture(int index, Texture2D texture)
        {
            var spec = Specs[index];
            var format = spec.Ramp ? GraphicsFormat.R8G8B8A8_UNorm : spec.Srgb ? GraphicsFormat.RGBA_BC7_SRGB : GraphicsFormat.RGBA_BC7_UNorm;
            var wrap = spec.Ramp ? TextureWrapMode.Clamp : TextureWrapMode.Repeat;
            if (texture == null || texture.width != spec.Width || texture.height != spec.Height || texture.mipmapCount != spec.Mips
                || texture.graphicsFormat != format || texture.filterMode != FilterMode.Bilinear
                || texture.wrapModeU != wrap || texture.wrapModeV != wrap || texture.wrapModeW != wrap
                || texture.anisoLevel != 0 || texture.mipMapBias != 0 || !texture.ignoreMipmapLimit || texture.activeMipmapLimit != 0
                || !texture.isReadable || EndfieldCapturedClothNormals.Hash(texture.GetRawTextureData<byte>().ToArray()) != spec.Hash)
                throw new InvalidDataException("Captured cloth texture/view/sampler changed: " + spec.File);
        }
        public static void ValidateTextures(IReadOnlyList<Texture2D> textures)
        {
            if (textures == null || textures.Count != Specs.Count) throw new InvalidDataException("Seven reviewed material textures required.");
            for (int i = 0; i < textures.Count; i++) ValidateTexture(i, textures[i]);
        }

        // Exclusive short-lived render scope, including the native normals.
        // A replaced owned texture signals a foreign writer: preserve that field
        // while detaching other owned inputs before their textures are released.
        // Not an asynchronous long-lived animation editor override.
        public sealed class Binding : IDisposable
        {
            internal sealed class Slot
            {
                internal Renderer Renderer;
                internal int Index;
                internal MaterialPropertyBlock Previous, Working;
                internal readonly Dictionary<string, Texture> Owned = new Dictionary<string, Texture>();
                internal readonly Dictionary<string, Texture> Restore = new Dictionary<string, Texture>();
            }
            readonly List<Slot> slots;
            bool disposed;
            public int SlotCount => slots.Count;
            internal Binding(List<Slot> value) { slots = value; }
            public void Dispose()
            {
                if (disposed) return; disposed = true;
                foreach (var slot in slots)
                {
                    if (slot.Renderer == null) continue;
                    var current = new MaterialPropertyBlock(); slot.Renderer.GetPropertyBlock(current, slot.Index);
                    bool owns = true;
                    foreach (var input in slot.Owned) owns &= current.GetTexture(input.Key) == input.Value;
                    if (owns) slot.Renderer.SetPropertyBlock(slot.Previous.isEmpty ? null : slot.Previous, slot.Index);
                    else
                    {
                        // Preserve a foreign texture replacement but detach every
                        // other texture still owned by this bundle before release.
                        foreach (var input in slot.Owned)
                            if (current.GetTexture(input.Key) == input.Value) current.SetTexture(input.Key, slot.Restore[input.Key]);
                        slot.Renderer.SetPropertyBlock(current, slot.Index);
                    }
                }
            }
        }
        public static Binding Bind(Transform root, IReadOnlyList<Texture2D> textures, Texture2D normal01, Texture2D normal02)
        {
            if (root == null) throw new ArgumentNullException(nameof(root));
            ValidateTextures(textures);
            EndfieldCapturedClothNormals.ValidateTextures(normal01, normal02);
            var slots = new List<Binding.Slot>(); bool firstFound = false, secondFound = false;
            foreach (var renderer in root.GetComponentsInChildren<Renderer>(true))
            {
                var materials = renderer.sharedMaterials;
                for (int s = 0; s < materials.Length; s++)
                {
                    var material = materials[s]; if (material == null) continue;
                    bool first = material.name == "M_actor_typhoea_cloth_01", second = material.name == "M_actor_typhoea_cloth_02";
                    if (!first && !second) continue;
                    if (material.shader == null || material.shader.name != "Endfield/CharacterLit" || material.GetFloat("_MaterialFamily") != 0
                        || material.GetFloat("_UseBumpMap") != 1 || material.GetFloat("_UseMetallicGlossMap") != 1
                        || material.GetFloat("_UseDiffRampMap") != 1 || material.GetFloat("_UseSpecRampMap") != 1
                        || material.GetFloat("_UseShadowLutTex") != 0 || material.GetFloat("_UseEmission") != (second ? 1 : 0))
                        throw new InvalidDataException("Not the reviewed cloth variant: " + material.name);
                    var slot = new Binding.Slot { Renderer = renderer, Index = s,
                        Previous = new MaterialPropertyBlock(), Working = new MaterialPropertyBlock() };
                    renderer.GetPropertyBlock(slot.Previous, s);
                    if (slot.Previous.isEmpty) renderer.GetPropertyBlock(slot.Working); else renderer.GetPropertyBlock(slot.Working, s);
                    slot.Owned.Add("_BumpMap", first ? normal01 : normal02);
                    for (int i = 0; i < Specs.Count; i++)
                        if (Specs[i].Ramp || Specs[i].Event == (first ? 835 : 850))
                            slot.Owned.Add(Specs[i].Property, textures[i]);
                    foreach (var input in slot.Owned)
                    {
                        var old = slot.Working.GetTexture(input.Key);
                        slot.Restore.Add(input.Key, old != null ? old : material.GetTexture(input.Key) ?? (input.Key == "_BumpMap" ? Texture2D.normalTexture : Texture2D.whiteTexture));
                        slot.Working.SetTexture(input.Key, input.Value);
                    }
                    slots.Add(slot); firstFound |= first; secondFound |= second;
                }
            }
            if (!firstFound || !secondFound) throw new InvalidDataException("Both reviewed cloth slots required before mutation.");
            var binding = new Binding(slots);
            try { foreach (var slot in slots) slot.Renderer.SetPropertyBlock(slot.Working, slot.Index); return binding; }
            catch { binding.Dispose(); throw; }
        }
    }
}
