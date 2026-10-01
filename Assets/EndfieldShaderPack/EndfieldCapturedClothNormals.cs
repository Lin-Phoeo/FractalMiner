using System;
using System.Collections.Generic;
using System.IO;
using System.Security.Cryptography;
using UnityEngine;
using Object = UnityEngine.Object;

namespace EndfieldShaderPack
{
    // Only the two reviewed frame-6411 cloth normals. No transcoding/import edits.
    public static class EndfieldCapturedClothNormals
    {
        public const int PayloadBytes = 5592432;
        public const string Cloth01Hash = "e96d6fd9c9a1850ab0655f8fe42fd156beb992d19008fea1a5ac45e5c6c62841";
        public const string Cloth02Hash = "9c7ab3cb6d4c7e85284f4caee838c5dd8978495ed147b38856808758b7db35d8";
        static readonly int Bump = Shader.PropertyToID("_BumpMap");

        public static string Hash(byte[] data)
        {
            using (var sha = SHA256.Create())
                return BitConverter.ToString(sha.ComputeHash(data)).Replace("-", "").ToLowerInvariant();
        }

        public static Texture2D CreateTexture(byte[] data, string expectedSha, string name)
        {
            if (data == null || data.Length != PayloadBytes
                || (expectedSha != Cloth01Hash && expectedSha != Cloth02Hash) || Hash(data) != expectedSha)
                throw new InvalidDataException("Native cloth BC5 payload identity/length mismatch.");
            if (!SystemInfo.SupportsTextureFormat(TextureFormat.BC5))
                throw new NotSupportedException("Native BC5 required; no performance/transcode fallback.");
            var texture = new Texture2D(2048, 2048, TextureFormat.BC5, 12, true)
            {
                name = name, hideFlags = HideFlags.HideAndDontSave,
                filterMode = FilterMode.Bilinear, wrapMode = TextureWrapMode.Repeat,
                anisoLevel = 0, mipMapBias = 0, ignoreMipmapLimit = true
            };
            try
            {
                texture.LoadRawTextureData(data);
                texture.Apply(false, false); // Keep all original mips; retain bytes for checks.
                if (texture.mipmapCount != 12 || texture.graphicsFormat != UnityEngine.Experimental.Rendering.GraphicsFormat.RG_BC5_UNorm)
                    throw new InvalidDataException("GPU BC5 format/mip contract not supported.");
                return texture;
            }
            catch { Release(texture); throw; }
        }

        public static void Release(Object value)
        {
            if (value == null) return;
            if (Application.isPlaying) Object.Destroy(value); else Object.DestroyImmediate(value);
        }

        // Binding is memory-only and reversible. Root-level blocks are inherited
        // when adding the first slot override, so unrelated root properties survive.
        public sealed class Binding : IDisposable
        {
            internal sealed class Slot
            {
                internal Renderer renderer;
                internal int index;
                internal MaterialPropertyBlock previous, working;
                internal Texture ownedTexture;
            }
            readonly List<Slot> slots;
            readonly bool preserveLaterChanges;
            bool disposed;
            public int SlotCount => slots.Count;
            internal Binding(List<Slot> records, bool preserveChanges) { slots = records; preserveLaterChanges = preserveChanges; }
            public void Dispose()
            {
                if (disposed) return;
                disposed = true;
                foreach (var slot in slots)
                    if (slot.renderer != null)
                    {
                        var current = new MaterialPropertyBlock();
                        slot.renderer.GetPropertyBlock(current, slot.index);
                        // Never clobber a later writer that replaced our texture.
                        if (current.GetTexture(Bump) != slot.ownedTexture) continue;
                        if (!preserveLaterChanges)
                            slot.renderer.SetPropertyBlock(slot.previous.isEmpty ? null : slot.previous, slot.index);
                        else
                        {
                            // Long-lived editor preview: restore only our input;
                            // live shadow/animation/user MPB updates remain intact.
                            Texture restore = slot.previous.GetTexture(Bump);
                            if (!slot.previous.HasTexture(Bump))
                            {
                                if (slot.previous.isEmpty)
                                {
                                    var root = new MaterialPropertyBlock();
                                    slot.renderer.GetPropertyBlock(root);
                                    restore = root.GetTexture(Bump);
                                }
                                if (restore == null)
                                {
                                    var materials = slot.renderer.sharedMaterials;
                                    if (slot.index < materials.Length && materials[slot.index] != null)
                                        restore = materials[slot.index].GetTexture(Bump);
                                }
                            }
                            current.SetTexture(Bump, restore != null ? restore : Texture2D.normalTexture);
                            slot.renderer.SetPropertyBlock(current, slot.index);
                        }
                    }
            }
        }

        public static Binding Bind(Transform root, Texture2D cloth01, Texture2D cloth02, bool preserveLaterChanges = false)
        {
            if (root == null) throw new ArgumentNullException(nameof(root));
            var textures = new[] { cloth01, cloth02 };
            string[] expectedHashes = { Cloth01Hash, Cloth02Hash };
            for (int i = 0; i < textures.Length; i++)
            {
                var texture = textures[i];
                if (texture == null || texture.width != 2048 || texture.height != 2048
                    || texture.format != TextureFormat.BC5 || texture.mipmapCount != 12
                    || texture.filterMode != FilterMode.Bilinear || texture.wrapModeU != TextureWrapMode.Repeat
                    || texture.wrapModeV != TextureWrapMode.Repeat || texture.mipMapBias != 0 || texture.anisoLevel != 0
                    || !texture.ignoreMipmapLimit || texture.activeMipmapLimit != 0)
                    throw new InvalidDataException("Native cloth normal sampler/texture contract mismatch.");
                if (!texture.isReadable || Hash(texture.GetRawTextureData<byte>().ToArray()) != expectedHashes[i])
                    throw new InvalidDataException("Native cloth normal payload changed before binding.");
            }
            var slots = new List<Binding.Slot>();
            bool found01 = false, found02 = false;
            foreach (var renderer in root.GetComponentsInChildren<Renderer>(true))
            {
                var materials = renderer.sharedMaterials;
                for (int s = 0; s < materials.Length; s++)
                {
                    var material = materials[s];
                    if (material == null) continue;
                    bool first = material.name == "M_actor_typhoea_cloth_01";
                    bool second = material.name == "M_actor_typhoea_cloth_02";
                    if (!first && !second) continue;
                    if (material.shader == null || material.shader.name != "Endfield/CharacterLit"
                        || !material.HasProperty("_MaterialFamily") || material.GetFloat("_MaterialFamily") != 0
                        || material.GetFloat("_UseBumpMap") != 1)
                        throw new InvalidDataException("Unexpected captured cloth material: " + material.name);
                    var previous = new MaterialPropertyBlock();
                    renderer.GetPropertyBlock(previous, s);
                    var working = new MaterialPropertyBlock();
                    if (previous.isEmpty) renderer.GetPropertyBlock(working);
                    else renderer.GetPropertyBlock(working, s);
                    working.SetTexture(Bump, first ? cloth01 : cloth02);
                    slots.Add(new Binding.Slot { renderer = renderer, index = s, previous = previous, working = working,
                        ownedTexture = first ? cloth01 : cloth02 });
                    found01 |= first; found02 |= second;
                }
            }
            // Validate the entire target before the first mutation.
            if (!found01 || !found02) throw new InvalidDataException("Both reviewed Cloth01/02 slots must exist under the selected character.");
            var binding = new Binding(slots, preserveLaterChanges);
            try
            {
                foreach (var slot in slots) slot.renderer.SetPropertyBlock(slot.working, slot.index);
                return binding;
            }
            catch { binding.Dispose(); throw; }
        }
    }
}
