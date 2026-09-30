using System;
using UnityEngine;

namespace EndfieldShaderPack.EditorTools
{
    public static class EndfieldEyePassValidation
    {
        // Official CharacterNPR_Eye has no inverted-hull Outline pass.
        // Test importer policy on transient materials, never rebuild assets.
        public static void Run()
        {
            var material = new Material(Shader.Find("Endfield/CharacterLit"));
            try
            {
                foreach (int family in new[] { 0, 1, 2, 3 })
                foreach (bool outline in new[] { false, true })
                {
                    material.SetFloat("_MaterialFamily", family);
                    material.SetFloat("_EnableOutline", outline ? 1 : 0);
                    EndfieldMaterialImporter.ConfigureUrpRenderState(material);
                    bool expected = outline && family != 3;
                    if (material.GetShaderPassEnabled("SRPDefaultUnlit") != expected)
                        throw new Exception("Outline policy mismatch: family=" + family + ", requested=" + outline);
                }
                Debug.Log("[EyePassValidation] PASS: eight family/outline states, iris has no generic outline");
            }
            finally { UnityEngine.Object.DestroyImmediate(material); }
        }
    }
}
