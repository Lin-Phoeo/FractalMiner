using UnityEditor;
using UnityEngine;

namespace EndfieldShaderPack
{
    public static class TyphoeusSkinDiag
    {
        // 诊断：烘焙蒙皮结果 vs 原始网格，并用无光照材质截图，隔离 shader 与蒙皮问题。
        public static void Run()
        {
            TyphoeusSceneSetup.SetupShowcaseScene();
            var model = GameObject.Find("chr_0034_typhoea_rebuilt");
            var plain = new Material(Shader.Find("Universal Render Pipeline/Unlit"));
            plain.color = new Color(0.8f, 0.6f, 0.6f);
            foreach (var smr in model.GetComponentsInChildren<SkinnedMeshRenderer>())
            {
                var baked = new Mesh();
                smr.BakeMesh(baked);
                Debug.Log($"[Diag] {smr.name} shared={smr.sharedMesh.bounds.size} baked={baked.bounds.size} bones={smr.bones.Length} bindposes={smr.sharedMesh.bindposes.Length}");
                var mats = smr.sharedMaterials;
                for (int i = 0; i < mats.Length; i++) mats[i] = plain;
                smr.sharedMaterials = mats;
            }
            var cam = Camera.main;
            var b = model.GetComponentInChildren<Renderer>().bounds;
            foreach (var r in model.GetComponentsInChildren<Renderer>()) b.Encapsulate(r.bounds);
            cam.transform.position = b.center + new Vector3(0, 0, -b.size.magnitude * 1.2f);
            cam.transform.LookAt(b.center);
            cam.clearFlags = CameraClearFlags.SolidColor; cam.backgroundColor = new Color(0.15f,0.15f,0.18f);
            var rt = new RenderTexture(1280, 720, 24); cam.targetTexture = rt; cam.Render();
            RenderTexture.active = rt; var tex = new Texture2D(1280, 720, TextureFormat.RGBA32, false);
            tex.ReadPixels(new Rect(0, 0, 1280, 720), 0, 0); tex.Apply();
            System.IO.File.WriteAllBytes("a:/Hypergryph Launcher/games/Arknights Endfield/typhoeus_diag.png", tex.EncodeToPNG());
            Debug.Log("[Diag] saved");
        }
    }
}
