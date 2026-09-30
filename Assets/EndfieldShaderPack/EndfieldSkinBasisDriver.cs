using System;
using System.Collections.Generic;
using UnityEngine;

namespace Endfield
{
    // Typhoeus adapter, not a generic inference from SMR.rootBone (the builder
    // assigns bones[1] there). Official bit16 fragment input is a PART root.
    // Frame6411: body root = Spine2; face/iris/hair root = Head with native-to-source
    // axis columns [-Z,-X,+Y]. Keep translation/scale; do not invert the matrix
    // or freeze capture rows. Invoke AFTER the complete animation/IK pose and
    // BEFORE rendering, also for synchronous Camera.Render batch workflows.
    public static class EndfieldSkinBasisDriver
    {
        public static void ApplyForTyphoeus(Transform root)
        {
            if (root == null) throw new ArgumentNullException(nameof(root));
            var bones = root.GetComponentsInChildren<Transform>();
            var prepared = new List<(SkinnedMeshRenderer renderer, int slot, Matrix4x4 basis)>();
            foreach (var renderer in root.GetComponentsInChildren<SkinnedMeshRenderer>())
            {
                bool face = renderer.name.EndsWith("_typhoea_face_01_lod0", StringComparison.Ordinal);
                bool body = renderer.name.EndsWith("_typhoea_body_01_lod0", StringComparison.Ordinal);
                bool iris = renderer.name.EndsWith("_typhoea_iris_01_lod0", StringComparison.Ordinal);
                bool hair = renderer.name.EndsWith("_typhoea_hair_01_lod0", StringComparison.Ordinal);
                if (!face && !body && !iris && !hair) continue;
                float family = iris ? 3 : hair ? 2 : 1;
                string boneName = body ? "Bip001_Spine2" : "Bip001_Head";
                Transform source = null;
                foreach (var bone in bones)
                    if (bone.name == boneName)
                    {
                        if (source != null) throw new InvalidOperationException("Ambiguous skin basis bone: " + boneName);
                        source = bone;
                    }
                if (source == null) throw new InvalidOperationException("Missing skin basis bone: " + boneName);
                Matrix4x4 basis = source.localToWorldMatrix;
                if (!body)
                {
                    Matrix4x4 native = basis;
                    basis.SetColumn(0, -native.GetColumn(2));
                    basis.SetColumn(1, -native.GetColumn(0));
                    basis.SetColumn(2, native.GetColumn(1));
                }
                for (int row = 0; row < 3; row++)
                for (int column = 0; column < 4; column++)
                    if (float.IsNaN(basis[row, column]) || float.IsInfinity(basis[row, column]))
                        throw new InvalidOperationException("Non-finite skin basis: " + boneName);
                var materials = renderer.sharedMaterials;
                for (int slot = 0; slot < materials.Length; slot++)
                {
                    var material = materials[slot];
                    // Do not change foreign/debug/label shaders on the same renderer.
                    if (material == null || !material.HasProperty("_EndfieldSkinBasisEnabled")
                        || !material.HasProperty("_MaterialFamily") || material.GetFloat("_MaterialFamily") != family) continue;
                    prepared.Add((renderer, slot, basis));
                }
            }
            foreach (var item in prepared)
            {
                var block = new MaterialPropertyBlock();
                item.renderer.GetPropertyBlock(block, item.slot);
                block.SetFloat("_EndfieldSkinBasisEnabled", 1);
                for (int row = 0; row < 3; row++) block.SetVector("_EndfieldSkinBasisRow" + row, item.basis.GetRow(row));
                item.renderer.SetPropertyBlock(block, item.slot);
            }
        }
    }
}
