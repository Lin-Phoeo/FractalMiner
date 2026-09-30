using System;
using System.Collections.Generic;
using System.Reflection;
using UnityEngine;

namespace EndfieldShaderPack.EditorTools
{
    public static class EndfieldShadowPropertyBlockValidation
    {
        public static void Run()
        {
            var root = new GameObject("ShadowPropertyBlockValidation");
            var material = new Material(Shader.Find("Endfield/CharacterLit"));
            var pass = new CharacterShadowPass(null, 64);
            try
            {
                var quad = GameObject.CreatePrimitive(PrimitiveType.Cube);
                quad.transform.SetParent(root.transform, false);
                var renderer = quad.GetComponent<Renderer>();
                renderer.sharedMaterials = new[] { material, material };
                var caster = root.AddComponent<EndfieldCharacterShadowCaster>();
                caster.slot = 2;
                var block = new MaterialPropertyBlock();
                block.SetFloat("_UserRendererValue", 17);
                renderer.SetPropertyBlock(block);
                for (int slot = 0; slot < 2; slot++)
                {
                    block.Clear();
                    block.SetFloat("_EndfieldSkinBasisEnabled", 1);
                    block.SetVector("_EndfieldSkinBasisRow0", new Vector4(1,0,0,slot));
                    block.SetFloat("_UserSlotValue", 31+slot);
                    renderer.SetPropertyBlock(block, slot);
                }
                var method = typeof(CharacterShadowPass).GetMethod("ApplyPerRendererShadowState", BindingFlags.Instance | BindingFlags.NonPublic);
                if (method == null) throw new Exception("Shadow binding entry missing");
                foreach (Vector3 travel in new[] { Vector3.forward, new Vector3(.2f,-.5f,.8f).normalized })
                {
                    method.Invoke(pass, new object[] { new List<EndfieldCharacterShadowCaster> { caster }, travel });
                    for (int slot = 0; slot < 2; slot++)
                    {
                        renderer.GetPropertyBlock(block, slot);
                        if ((block.GetVector(CharacterShadowPass.IndexEncodeName) - CharacterShadowPass.IndexEncode(2)).sqrMagnitude > 1e-10f)
                            throw new Exception("Per-material block masks shadow index: slot " + slot);
                        if (block.GetMatrix(CharacterShadowPass.AtlasClipMatrixName) == Matrix4x4.zero)
                            throw new Exception("Per-material shadow matrix missing");
                        if (block.GetFloat("_UserSlotValue") != 31+slot || block.GetFloat("_EndfieldSkinBasisEnabled") != 1
                            || block.GetVector("_EndfieldSkinBasisRow0").w != slot)
                            throw new Exception("Shadow binding overwrote existing slot data");
                    }
                    renderer.GetPropertyBlock(block);
                    if (block.GetFloat("_UserRendererValue") != 17) throw new Exception("Renderer block discarded");
                }
                Debug.Log("[ShadowPropertyBlockValidation] PASS: two slots x two shadow updates; root/user data retained at both levels");
            }
            finally
            {
                pass.Dispose();
                UnityEngine.Object.DestroyImmediate(root);
                UnityEngine.Object.DestroyImmediate(material);
            }
        }
    }
}
