using UnityEditor;
using UnityEditor.SceneManagement;
using UnityEngine;

namespace EndfieldShaderPack
{
    /// Aligns the showcase scene with the captured official front frame
    /// (Validation/Captures/tifuluosi-front-20260917, event 875 constants).
    public static class TyphoeusOfficialFrame
    {
        const string ScenePath = "Assets/Scenes/Typhoeus_Showcase.unity";
        const string RootName  = "chr_0034_typhoea_rebuilt";

        // Captured projection: vertical FOV 35°, aspect 2560/1600, camera forward (0,-0.0081,-1).
        const float FovDeg      = 35f;
        const float Aspect      = 1.6f;
        const float PitchDeg    = 0.4647f;
        // Character spans rows ~100..1490 of the 1600px official frame.
        const float FrameFill   = 0.869f;
        // Official backdrop is neutral grey: ~0.55 top, 0.75 wall, 0.50 floor (sRGB).
        static readonly Color Backdrop = new Color(0.60f, 0.60f, 0.59f);
        // _LightDataBuffer_DirectionalLightDirection is the travel direction of the light.
        static readonly Vector3 LightTravelDir = new Vector3(0.0213893f, -0.642788f, -0.765746f);

        [MenuItem("Endfield/Apply Official Front Frame", false, 60)]
        public static void Apply()
        {
            var root = GameObject.Find(RootName);
            if (root == null) throw new System.InvalidOperationException("Rebuilt model missing: " + RootName);

            var cam = Camera.main;
            cam.orthographic = false;
            cam.fieldOfView = FovDeg;
            cam.aspect = Aspect;
            cam.nearClipPlane = 0.05f;
            cam.farClipPlane = 100f;
            cam.clearFlags = CameraClearFlags.SolidColor;
            cam.backgroundColor = Backdrop;

            Bounds b = TyphoeusSceneSetup.ComputeWorldBounds(root);
            float halfFov = FovDeg * 0.5f * Mathf.Deg2Rad;
            float dist = b.size.y / (2f * FrameFill * Mathf.Tan(halfFov)) + b.extents.z;
            cam.transform.rotation = Quaternion.Euler(PitchDeg, 180f, 0f);
            // Camera looks down -Z; the character faces +Z toward it.
            cam.transform.position = b.center + new Vector3(0f, dist * Mathf.Tan(PitchDeg * Mathf.Deg2Rad), dist);

            var light = Object.FindObjectOfType<Endfield.EndfieldCharacterLight>();
            if (light == null) throw new System.InvalidOperationException("EndfieldCharacterLight missing");
            // EndfieldCharacterLight treats transform.forward as the direction toward the light.
            light.transform.rotation = Quaternion.LookRotation(-LightTravelDir.normalized, Vector3.up);
            light.useSeparatedLight = true;
            light.ApplyLight();

            // 注入官方 HGRP _CharacterParamsN 捕获值（详见 docs/research/official-forwardlit-*-b*.md §4）
            // 让 shader 走捕获帧分支：CP1.y=1 平坦环境、CP1.w=1 光方向覆盖、CP13.w 各向异性总乘数等
            ApplyCharacterParams();

            Debug.Log($"[OfficialFrame] bounds={b.size} dist={dist:F3} camPos={cam.transform.position} L={-LightTravelDir}");
        }

        /// 注入捕获帧已知的 _CharacterParamsN 全局值（来自 front-frame constants 提取）。
        static void ApplyCharacterParams()
        {
            Shader.SetGlobalVector(Shader.PropertyToID("_CharacterParams0"),  new Vector4(0.0f, 1.0f, 0.65f, 0.9f));
            Shader.SetGlobalVector(Shader.PropertyToID("_CharacterParams1"),  new Vector4(0.0f, 1.0f, 0.0f, 1.0f));
            Shader.SetGlobalVector(Shader.PropertyToID("_CharacterParams2"),  new Vector4(0.849f, 0.896f, 1.151f, 0.0f));
            Shader.SetGlobalVector(Shader.PropertyToID("_CharacterParams5"),  new Vector4(1.0f, 1.0f, 1.0f, 1.62439f));
            Shader.SetGlobalVector(Shader.PropertyToID("_CharacterParams6"),  new Vector4(0.0f, 1.0f, 0.0f, 0.0f));
            Shader.SetGlobalVector(Shader.PropertyToID("_CharacterParams7"),  new Vector4(0.15f, 1.5f, 0.5f, 0.0f));
            Shader.SetGlobalVector(Shader.PropertyToID("_CharacterParams8"),  new Vector4(0.0f, 0.0f, 0.0f, 1.0f));
            Shader.SetGlobalVector(Shader.PropertyToID("_CharacterParams9"),  new Vector4(0.0f, -1.0f, 0.0f, 0.4f));
            Shader.SetGlobalVector(Shader.PropertyToID("_CharacterParams10"), new Vector4(0.0f, 0.0f, 2.25f, -100.0f));
            Shader.SetGlobalVector(Shader.PropertyToID("_CharacterParams11"), new Vector4(0.176f, 0.530f, 0.830f, -0.1f));
            Shader.SetGlobalVector(Shader.PropertyToID("_CharacterParams12"), new Vector4(1.0f, 1.0f, 1.0f, 0.0f));
            Shader.SetGlobalVector(Shader.PropertyToID("_CharacterParams13"), new Vector4(0.0f, 0.0f, 0.0f, 1.0f));
            Shader.SetGlobalVector(Shader.PropertyToID("_CharacterParams15"), new Vector4(0.0f, 0.0f, 0.0f, 0.0f));

            // cloth b401 环境/曝光全局参数（docs/research/official-forwardlit-cloth-b401.md §5）
            //   _EnvironmentGlobalParams0.x = ambientScale 基值 (捕获 0.2877)
            //   _ExposureWithMiscParams = (1,1,1.6,0.1)：x 乘 ambientScale，y 输出前乘 rgb
            Shader.SetGlobalVector(Shader.PropertyToID("_EnvironmentGlobalParams0"), new Vector4(0.2877f, 0.0f, 0.0f, 0.0f));
            Shader.SetGlobalVector(Shader.PropertyToID("_ExposureWithMiscParams"), new Vector4(1.0f, 1.0f, 1.6f, 0.1f));
        }

        /// Batch entry: open saved scene, apply official camera/light, render 1600x1000.
        public static void RenderFrontAlign()
        {
            EditorSceneManager.OpenScene(ScenePath, OpenSceneMode.Single);
            Apply();
            var cam = Camera.main;
            TyphoeusGeometryValidation.SaveImage(cam, "front-align.png", 1600, 1000);
            EditorSceneManager.SaveScene(EditorSceneManager.GetActiveScene());
            Debug.Log("[OfficialFrame] Saved Validation/front-align.png");
        }
    }
}
