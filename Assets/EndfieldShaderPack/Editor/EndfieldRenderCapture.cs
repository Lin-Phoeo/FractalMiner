// ============================================================
//  EndfieldRenderCapture.cs
//  batchmode 下用真 GPU 渲染提弗洛斯一帧并保存 PNG，供无头调参。
//  -executeMethod EndfieldShaderPack.EndfieldRenderCapture.Capture
// ============================================================
using System.IO;
using UnityEditor;
using UnityEditor.SceneManagement;
using UnityEngine;

namespace EndfieldShaderPack
{
    public static class EndfieldRenderCapture
    {
        const string ScenePath = "Assets/Scenes/Typhoeus_Showcase.unity";
        const string OutPath   = "a:/Hypergryph Launcher/games/Arknights Endfield/typhoeus_shot.png";

        [MenuItem("Endfield/Capture Showcase Screenshot", false, 50)]
        public static void Capture()
        {
            // 1) 强制重建干净场景（模型 + 分离角色光），避免旧场景陈旧状态
            TyphoeusSceneSetup.SetupShowcaseScene();

            GameObject model = GameObject.Find("Typhoeus");
            if (model == null)
            {
                Debug.LogError("[Capture] 找不到 Typhoeus 模型，无法截图。");
                return;
            }

            // 1.5) 诊断场景根对象 + 放大模型到正常体型
            foreach (var go in UnityEngine.SceneManagement.SceneManager.GetActiveScene().GetRootGameObjects())
                Debug.Log("[Capture] 场景根对象: " + go.name);
            var rod = model.GetComponentInChildren<Renderer>();
            float targetH = 1.7f;
            float curH = rod.bounds.size.y;
            if (curH > 0.001f)
            {
                float s = targetH / curH;
                model.transform.localScale = model.transform.localScale * s;
                Debug.Log("[Capture] 模型放大倍率 = " + s + " (原高 " + curH + ")");
            }

            // 2) 确保分离角色光已注入全局 shader 参数
            var cl = Object.FindObjectOfType<Endfield.EndfieldCharacterLight>();
            if (cl != null && cl.useSeparatedLight)
                cl.ApplyLight();

            // 3) 相机
            Camera cam = Camera.main;
            if (cam == null) cam = Object.FindObjectOfType<Camera>();
            if (cam == null)
            {
                Debug.LogError("[Capture] 找不到相机。");
                return;
            }

            // 3.5) 诊断 + 固定取景
            var renderers = model.GetComponentsInChildren<SkinnedMeshRenderer>();
            Debug.Log($"[Capture] SkinnedMeshRenderer 数量 = {renderers.Length}");
            int nullMat = 0, totalMat = 0;
            foreach (var r in renderers)
            {
                foreach (var m in r.sharedMaterials)
                {
                    totalMat++;
                    if (m == null || m.shader == null) nullMat++;
                    else if (m.shader.name != "Endfield/CharacterLit") Debug.Log($"[Capture] 非目标 shader 材质: {m.name} -> {m.shader.name}");
                }
            }
            Debug.Log($"[Capture] 材质槽 = {totalMat}, 空/坏 = {nullMat}");
            var b = model.GetComponentInChildren<Renderer>().bounds;
            Debug.Log($"[Capture] 模型包围盒 center={b.center} size={b.size}");

            // 固定取景（按模型真实包围盒取景，绕过可能出错的 ComputeWorldBounds）
            cam.orthographic = false;
            cam.fieldOfView = 60f;
            cam.nearClipPlane = 0.05f;
            cam.farClipPlane = 100f;
            cam.clearFlags = CameraClearFlags.SolidColor;
            cam.backgroundColor = new Color(0.15f, 0.15f, 0.18f);
            float dist = b.size.magnitude * 0.9f;
            cam.transform.position = b.center + new Vector3(0f, 0.05f, -dist);
            cam.transform.LookAt(b.center);
            Debug.Log($"[Capture] 相机位置={cam.transform.position} FOV={cam.fieldOfView} dist={dist}");

            // 4) 渲染到 RenderTexture 并存 PNG
            int w = 1920, h = 1080;
            var rt = new RenderTexture(w, h, 24);
            cam.targetTexture = rt;
            cam.Render();
            RenderTexture.active = rt;
            var tex = new Texture2D(w, h, TextureFormat.RGBA32, false);
            tex.ReadPixels(new Rect(0, 0, w, h), 0, 0);
            tex.Apply();
            byte[] png = tex.EncodeToPNG();
            Directory.CreateDirectory(Path.GetDirectoryName(OutPath));
            File.WriteAllBytes(OutPath, png);
            Debug.Log("[Capture] 截图已保存: " + OutPath);

            RenderTexture.active = null;
            cam.targetTexture = null;
            Object.DestroyImmediate(rt);
            Object.DestroyImmediate(tex);
        }
    }
}