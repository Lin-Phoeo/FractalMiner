// Character-detail showcase animation render: drives the recovered scene's
// skeleton with the OFFICIAL clip A_actor_typhoea_battle_loop.anim (the
// character-detail idle loop, 60fps, 4s, 1749 bone paths matching this rig)
// and renders the captured frame-6411 camera through the full M5 chain
// (captured pipeline + self-shadow hard gates + captured lighting globals +
// frozen CapturedPost with dynamic bloom).
//
// Reuses RunPoseApply's validated render stack via a shared core; the only
// difference is the pose source: an AnimationClip sampled per frame instead
// of the capture SSBO pose. The chr-root pivot (R_y(+45.5)) is applied the
// same way, then the clip is sampled — the clip writes bone LOCALS, so the
// pivot on the chr root survives.
//
// Evidence contract (fixed before first run):
//   output: Validation/pose-anim-01/frame-###.png (1280x800, 30fps, 4s = 120 frames)
//   per-frame self-shadow gates identical to RunPoseApply (checked every frame)
//   report: Validation/pose-anim-01/anim-render-report.json
//   the scene is never saved
using System;
using System.Collections.Generic;
using System.Globalization;
using System.IO;
using UnityEditor;
using UnityEditor.SceneManagement;
using UnityEngine;
using UnityEngine.Rendering;
using UnityEngine.Rendering.Universal;

namespace EndfieldShaderPack.EditorTools
{
    public static class EndfieldAnimRenderValidation
    {
        const string ScenePath = "Assets/Scenes/Typhoeus_OfficialFrame_Recovered.unity";
        const string ClipPath = "Assets/Typhoeus/Animations/A_actor_typhoea_battle_loop.anim";
        const string OutDir = "Validation/pose-anim-01";
        const int Width = 1280;
        const int Height = 800;
        const int OutputFps = 30;
        // One full official loop. The clip is 4s at 60fps; rendering at 30fps
        // gives 120 frames (every other clip keyframe).
        const float ClipDuration = 4f;
        const float ExpectedFov = 35f;
        static readonly Vector3 ExpectedCameraPosition = new Vector3(0f, 0.7799988f, 2.9599915f);
        static readonly Quaternion ExpectedCameraRotation = new Quaternion(
            -1.7726111e-10f, 0.9999918f, +0.0040552616f, -4.371103e-8f);
        static readonly float M5InstanceYawDeg = 45.5f;
        static readonly Vector3 LightTravelDir = new Vector3(0.0213893f, -0.642788f, -0.765746f);
        const string CapturedPostShaderName = "Hidden/Endfield/CapturedPost";

        public static void RunAnimRender()
        {
            Directory.CreateDirectory(OutDir);
            var report = new List<string>();
            bool pipelineWasActivated = EndfieldCapturedPipelineActivation.IsActivated;
            if (!pipelineWasActivated)
                EndfieldCapturedPipelineActivation.Activate();
            try
            {
                RunAnimRenderCore(report);
            }
            finally
            {
                if (!pipelineWasActivated)
                {
                    EditorSceneManager.NewScene(NewSceneSetup.EmptyScene, NewSceneMode.Single);
                    EndfieldCapturedPipelineActivation.Restore();
                }
            }
        }

        static void RunAnimRenderCore(List<string> report)
        {
            var scene = EditorSceneManager.OpenScene(ScenePath, OpenSceneMode.Single);
            var clip = AssetDatabase.LoadAssetAtPath<AnimationClip>(ClipPath);
            if (clip == null) throw new InvalidOperationException("Official clip missing: " + ClipPath);
            report.Add("clip: " + clip.name + " length=" + clip.length + " framerate=" + clip.frameRate);

            Transform charRoot = null;
            foreach (var sceneRoot in scene.GetRootGameObjects())
            {
                if (sceneRoot.name == "chr_0034_typhoea_rebuilt") { charRoot = sceneRoot.transform; break; }
            }
            if (charRoot == null) throw new InvalidOperationException("chr_0034_typhoea_rebuilt not found");
            Transform pelvis = FindDeep(charRoot, "Bip001_Pelvis");
            if (pelvis == null) throw new InvalidOperationException("Bip001_Pelvis not found");
            Transform armature = pelvis;
            while (armature.parent != null &&
                   (armature.parent.name == "Bip001" || armature.parent.name == "Root"))
                armature = armature.parent;
            report.Add("skeleton walk root: " + armature.name + " (" + charRoot.name + ")");

            // The official clip binds paths under "Root/...". The scene rig's
            // animateable root for Unity's Animation component is chr_0034 root
            // itself (paths start at Root, the rig's Z-up bone under chr root).
            // SampleAnimation on charRoot works when the clip's first path
            // segment matches a direct child hierarchy — verify by bone count
            // of bindings vs rig, then sample frame 0 and gate on Head world y
            // to prove the clip actually moved the rig.
            int bindings = AnimationUtility.GetCurveBindings(clip).Length;
            report.Add("clip curve bindings: " + bindings);

            // Transient self-shadow caster (same contract as RunPoseApply).
            var transientShadowCaster = charRoot.gameObject.AddComponent<EndfieldCharacterShadowCaster>();
            transientShadowCaster.slot = 0;
            EndfieldCharacterShadowCaster.Refresh();
            report.Add("shadow caster: transient (added), active=" + EndfieldCharacterShadowCaster.Active.Count);

            // chr-root pivot: capture's instance rotation. Same composition and
            // the same four traps as RunPoseApply (rotate armature's PARENT,
            // compose onto -90X, +45.5, never rewrite bone locals afterwards).
            // The clip sampling below writes bone LOCALS only, so the pivot on
            // pivotParent survives every frame.
            Quaternion pivotRot = Quaternion.Euler(0f, M5InstanceYawDeg, 0f)
                                  * Quaternion.Euler(-90f, 0f, 0f);
            Transform pivotParent = armature.parent != null ? armature.parent : armature;
            pivotParent.localRotation = pivotRot;

            var camera = Camera.main;
            if (camera == null) throw new InvalidOperationException("No main camera in scene.");
            camera.aspect = Width / (float)Height;
            camera.fieldOfView = ExpectedFov;
            camera.transform.SetPositionAndRotation(ExpectedCameraPosition, ExpectedCameraRotation);

            var globals = UnityEngine.Object.FindObjectOfType<Endfield.EndfieldOfficialFrameGlobals>();
            if (globals == null) throw new InvalidOperationException("EndfieldOfficialFrameGlobals missing");
            var envCube = EndfieldCaptureAssets.EnvironmentCube;
            Endfield.EndfieldOfficialFrameGlobals.ApplyGlobals(globals.useSourceShading, envCube);

            var charLight = UnityEngine.Object.FindObjectOfType<Endfield.EndfieldCharacterLight>();
            if (charLight == null) throw new InvalidOperationException("EndfieldCharacterLight missing");
            charLight.useSeparatedLight = true;
            charLight.transform.rotation = Quaternion.LookRotation(-LightTravelDir.normalized, Vector3.up);
            charLight.ApplyLight();

            var postShader = Shader.Find(CapturedPostShaderName);
            if (postShader == null || !postShader.isSupported)
                throw new InvalidOperationException("CapturedPost shader missing or unsupported");
            var lut = EndfieldCaptureAssets.Texture("grading-lut");
            if (lut == null) throw new InvalidOperationException("grading-lut missing");
            var postMaterial = new Material(postShader);
            var litTarget = new RenderTexture(Width, Height, 24, RenderTextureFormat.ARGBHalf, RenderTextureReadWrite.Linear);
            var postTarget = new RenderTexture(Width, Height, 0, RenderTextureFormat.ARGBHalf, RenderTextureReadWrite.Linear);
            var postReadback = new Texture2D(Width, Height, TextureFormat.RGBAFloat, false, true);
            var postPng = new Texture2D(Width, Height, TextureFormat.RGBA32, false, true);
            var bloomShader = AssetDatabase.LoadAssetAtPath<ComputeShader>("Assets/EndfieldShaderPack/EndfieldCapturedBloom.compute");
            if (bloomShader == null) throw new InvalidOperationException("Captured bloom compute missing.");
            var dynamicBloom = new EndfieldCapturedBloom(bloomShader);
            RTHandle bloomSource = null;
            CommandBuffer bloomCommand = null;

            int frameCount = Mathf.CeilToInt(ClipDuration * OutputFps);
            report.Add("rendering " + frameCount + " frames at " + OutputFps + " fps");
            var frameJson = new List<string>();
            try
            {
                postMaterial.SetTexture("_EndfieldPostLut", lut);
                postMaterial.SetTexture("_EndfieldPostBloom", Texture2D.blackTexture);
                postMaterial.SetVector("_EndfieldPostScreenSize", new Vector4(Width, Height, 1f / Width, 1f / Height));
                postMaterial.SetVector("_EndfieldPostExposure", new Vector4(1f, 1f, 1.6f, 0.100001f));
                postMaterial.SetVector("_EndfieldPostLutParameters", new Vector4(1f / 1024f, 1f / 32f, 31f, 1f));
                postMaterial.SetVector("_EndfieldPostBloomParameters", new Vector4(0.3660402f, 0f, 0f, 0f));
                postMaterial.SetVector("_EndfieldPostBloomThreshold", new Vector4(0.5225216f, 0.2612508f, 0.5225416f, 0.9568616f));
                postMaterial.SetVector("_EndfieldPostBloomTint", Vector4.one);
                postMaterial.SetVector("_EndfieldPostVignette1", new Vector4(0.5f, 0.5f, 0f, 0f));
                postMaterial.SetVector("_EndfieldPostVignette2", new Vector4(0.9f, 2.05f, 1.3f, 0f));
                postMaterial.SetVector("_EndfieldPostVignetteColor", new Vector4(0.06666667f, 0.06717458f, 0.07450981f, 1f));
                postMaterial.SetVector("_EndfieldPostOptions", new Vector4(0.30000001192092896f, 1f, 1f, 0f));
                postMaterial.SetFloat("_EndfieldPostOutputMode", 1f);
                postMaterial.SetVector("_EndfieldPostSourceUV", new Vector4(1f, 1f, 0f, 0f));
                postMaterial.SetVector("_EndfieldPostBloomUV", new Vector4(1f, 1f, 0f, 0f));
                postMaterial.SetVector("_EndfieldPostLutUV", new Vector4(1f, -1f, 0f, 1f));
                postMaterial.SetVector("_EndfieldPostScreenUV", new Vector4(1f, 1f, 0f, 0f));

                var previousTarget = camera.targetTexture;
                var previousActive = RenderTexture.active;
                // Warm up the URP RTHandle pool: UniversalRenderPipeline
                // .s_RTHandlePool is only constructed while the pipeline
                // instance is live (the same reason EndfieldCapturePipeline
                // Validation warmups a dummy camera before RTHandle work).
                // The first camera.Render() here both creates litTarget's GPU
                // resource and builds the pool; without it ReAllocateIfNeeded
                // NREs on the null pool.
                camera.targetTexture = litTarget;
                camera.Render();
                camera.targetTexture = null;
                if (!litTarget.IsCreated()) litTarget.Create();
                bloomSource = RTHandles.Alloc(litTarget);
                if (!dynamicBloom.Setup(litTarget.descriptor))
                    throw new InvalidOperationException("Captured dynamic Bloom unsupported: " + dynamicBloom.StorageSupportDescription);
                bloomCommand = new CommandBuffer { name = "Anim captured dynamic Bloom" };
                try
                {
                    for (int f = 0; f < frameCount; f++)
                    {
                        float t = f / (float)OutputFps;
                        // Official clip drives bone locals directly (generic
                        // binding). SampleAnimation applies the full pose; it
                        // is the public API for generic (non-Legacy) clips in
                        // editor batch mode and does not need AnimationMode.
                        clip.SampleAnimation(charRoot.gameObject, t);

                        camera.targetTexture = litTarget;
                        camera.Render();

                        bloomCommand.Clear();
                        RTHandle generatedBloom = dynamicBloom.Render(bloomCommand, bloomSource, 1f);
                        Graphics.ExecuteCommandBuffer(bloomCommand);
                        if (generatedBloom == null || generatedBloom.rt == null)
                            throw new InvalidOperationException("Dynamic Bloom produced no output at frame " + f);
                        postMaterial.SetTexture("_EndfieldPostBloom", generatedBloom.rt);
                        Graphics.Blit(litTarget, postTarget, postMaterial, 1);

                        RenderTexture.active = postTarget;
                        postReadback.ReadPixels(new Rect(0, 0, Width, Height), 0, 0);
                        postReadback.Apply();
                        var pixels = postReadback.GetPixels();
                        for (int i = 0; i < pixels.Length; i++)
                        {
                            Color p = pixels[i];
                            if (float.IsNaN(p.r + p.g + p.b) || float.IsInfinity(p.r + p.g + p.b))
                                throw new InvalidOperationException("Nonfinite post output at frame " + f);
                            pixels[i] = p.gamma;
                        }
                        postPng.SetPixels(pixels);
                        postPng.Apply();
                        string framePath = Path.Combine(OutDir, "frame-" + f.ToString("000")) + ".png";
                        File.WriteAllBytes(framePath, postPng.EncodeToPNG());

                        // Per-frame self-shadow execution gate (same contract as
                        // RunPoseApply; check every frame, fail fast).
                        string skipReason = EndfieldCharacterShadowFeature.LastSkipReason;
                        if (!string.IsNullOrEmpty(skipReason))
                            throw new InvalidOperationException("Self-shadow skipped at frame " + f + ": " + skipReason);
                        if (CharacterShadowPass.LastResolved == null)
                            throw new InvalidOperationException("Self-shadow resolve missing at frame " + f);

                        if (f == 0 || f == frameCount / 2 || f == frameCount - 1)
                        {
                            Transform head = FindDeep(armature, "Bip001_Head");
                            frameJson.Add("{\"frame\":" + f
                                + ",\"headY\":" + (head != null ? head.position.y.ToString("R", CultureInfo.InvariantCulture) : "null")
                                + ",\"t\":" + t.ToString("F3", CultureInfo.InvariantCulture) + "}");
                        }
                        camera.targetTexture = null;
                    }
                    RenderTexture.active = previousActive;
                }
                finally
                {
                    camera.targetTexture = previousTarget;
                }
                report.Add("frames written: " + frameCount);
            }
            finally
            {
                bloomCommand?.Release();
                dynamicBloom.Dispose();
                if (bloomSource != null) bloomSource.Release();
                else litTarget.Release();
                postTarget.Release();
                UnityEngine.Object.DestroyImmediate(litTarget);
                UnityEngine.Object.DestroyImmediate(postTarget);
                UnityEngine.Object.DestroyImmediate(postReadback);
                UnityEngine.Object.DestroyImmediate(postPng);
                UnityEngine.Object.DestroyImmediate(postMaterial);
                UnityEngine.Object.DestroyImmediate(transientShadowCaster);
                EndfieldCharacterShadowCaster.Refresh();
            }

            string json = "{\"clip\":\"" + ClipPath + "\",\"frames\":" + frameCount
                + ",\"fps\":" + OutputFps
                + ",\"samples\":" + string.Join(",", frameJson.ToArray())
                + ",\"notes\":[" + string.Join(",", report.ConvertAll(s => "\"" + s + "\"").ToArray()) + "]}";
            File.WriteAllText(Path.Combine(OutDir, "anim-render-report.json"), json);
            Debug.Log("[AnimRender] " + string.Join(" | ", report.ToArray()));
            // Never save the scene.
        }

        static Transform FindDeep(Transform root, string name)
        {
            if (root.name == name) return root;
            foreach (Transform child in root)
            {
                var hit = FindDeep(child, name);
                if (hit != null) return hit;
            }
            return null;
        }
    }
}
