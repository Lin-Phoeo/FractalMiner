using System;
using System.Collections.Generic;
using System.IO;
using System.Reflection;
using UnityEditor;
using UnityEditor.SceneManagement;
using UnityEngine;
using UnityEngine.Rendering;
using UnityEngine.Rendering.Universal;
using UnityEngine.SceneManagement;
using Object = UnityEngine.Object;

namespace EndfieldShaderPack
{
    // Isolated lifecycle tests, not a shadow-formula or screenshot oracle.
    public static class EndfieldShadowLifecycleValidation
    {
        static void Require(bool condition, string message)
        {
            if (!condition) throw new InvalidOperationException(message);
        }
        static void Set(object target, string name, object value) =>
            target.GetType().GetField(name, BindingFlags.NonPublic | BindingFlags.Instance).SetValue(target, value);
        static long Sequence() => Convert.ToInt64(typeof(CharacterShadowPass).GetField("LastRenderSequence").GetValue(null));
        static void RenderCamera(Camera camera) => RenderPipeline.SubmitRenderRequest(camera,
            new UniversalRenderPipeline.SingleCameraRequest { destination = camera.targetTexture });
        static void Seed(Texture texture)
        {
            Shader.SetGlobalTexture(CharacterShadowPass.ScreenTextureName, texture);
            Shader.SetGlobalFloat(CharacterShadowPass.SelfShadowGateName, 1);
            Shader.SetGlobalVector(CharacterShadowPass.ScreenSizeName, Vector4.one);
        }
        static void Cleared()
        {
            Require(Shader.GetGlobalFloat(CharacterShadowPass.SelfShadowGateName) == 0, "stale G gate");
            Require(Shader.GetGlobalTexture(CharacterShadowPass.ScreenTextureName) == Texture2D.whiteTexture, "stale G texture");
            Require(Shader.GetGlobalVector(CharacterShadowPass.ScreenSizeName) == Vector4.zero, "stale G size");
            Require(Shader.GetGlobalTexture("_EndfieldDirectionalShadowScreen") == Texture2D.blackTexture &&
                Shader.GetGlobalFloat("_EndfieldDirectionalScreenShadow") == .75f, "independent R owner modified");
        }
        public static void RunBatch()
        {
            string output = Environment.GetEnvironmentVariable("ENDFIELD_SHADOW_LIFECYCLE_REPORT");
            Require(Application.isBatchMode && !string.IsNullOrEmpty(output) && !File.Exists(output), "fresh isolated batch required");
            Require(SceneManager.sceneCount == 1 && string.IsNullOrEmpty(SceneManager.GetActiveScene().path) &&
                SceneManager.GetActiveScene().rootCount == 0, "empty isolated batch scene required");
            var lines = new List<string>(); int cases = 0, failed = 0;
            Action<string, Action> check = (name, body) =>
            {
                cases++;
                try { body(); lines.Add("PASS " + name); }
                catch (Exception error) { failed++; lines.Add("FAIL " + name + ": " + error.GetBaseException().Message); }
            };
            Texture savedG = Shader.GetGlobalTexture(CharacterShadowPass.ScreenTextureName), savedR = Shader.GetGlobalTexture("_EndfieldDirectionalShadowScreen");
            float savedGate = Shader.GetGlobalFloat(CharacterShadowPass.SelfShadowGateName), savedRGate = Shader.GetGlobalFloat("_EndfieldDirectionalScreenShadow");
            Vector4 savedSize = Shader.GetGlobalVector(CharacterShadowPass.ScreenSizeName);
            Vector4 savedLightDir = Shader.GetGlobalVector("_CharacterLightDir"), savedLightColor = Shader.GetGlobalVector("_CharacterLightColor"), savedAmbient = Shader.GetGlobalVector("_CharacterAmbient");
            try
            {
                Shader.SetGlobalTexture("_EndfieldDirectionalShadowScreen", Texture2D.blackTexture);
                Shader.SetGlobalFloat("_EndfieldDirectionalScreenShadow", .75f);
                var feature = ScriptableObject.CreateInstance<EndfieldCharacterShadowFeature>();
                try
                {
                    var data = new RenderingData { cameraData = new CameraData { cameraType = CameraType.Game, renderType = CameraRenderType.Base, resolveFinalTarget = true,
                        cameraTargetDescriptor = new RenderTextureDescriptor(16, 16, RenderTextureFormat.ARGBHalf, 24) { msaaSamples = 1 } } };
                    check("missing resolve guard clears stale G", () => { Seed(Texture2D.blackTexture); feature.AddRenderPasses(null, ref data); Cleared(); });
                    var settings = new SerializedObject(feature);
                    settings.FindProperty("resolveShader").objectReferenceValue = AssetDatabase.LoadAssetAtPath<ComputeShader>("Assets/EndfieldShaderPack/EndfieldCharacterShadowResolve.compute");
                    settings.ApplyModifiedPropertiesWithoutUndo(); feature.Create();
                    foreach (string guard in new[] { "SceneView", "Overlay", "nonfinal", "MSAA", "dynamic", "no casters" })
                    {
                        string current = guard;
                        check("skip guard " + current, () =>
                        {
                            var copy = data;
                            if (current == "SceneView") copy.cameraData.cameraType = CameraType.SceneView;
                            if (current == "Overlay") copy.cameraData.renderType = CameraRenderType.Overlay;
                            if (current == "nonfinal") copy.cameraData.resolveFinalTarget = false;
                            var descriptor = copy.cameraData.cameraTargetDescriptor;
                            if (current == "MSAA") descriptor.msaaSamples = 2;
                            if (current == "dynamic") descriptor.useDynamicScale = true;
                            copy.cameraData.cameraTargetDescriptor = descriptor;
                            Seed(Texture2D.blackTexture); feature.AddRenderPasses(null, ref copy); Cleared();
                        });
                    }
                    check("queued setup reset precedes early-return paths", () =>
                    {
                        var pass = new CharacterShadowPass(null, 64); var command = new CommandBuffer();
                        try { Seed(Texture2D.blackTexture); pass.OnCameraSetup(command, ref data); Graphics.ExecuteCommandBuffer(command); Cleared(); }
                        finally { command.Release(); pass.Dispose(); }
                    });
                    check("queued camera cleanup clears G only", () =>
                    {
                        var pass = new CharacterShadowPass(null, 64); var command = new CommandBuffer();
                        try { Seed(Texture2D.blackTexture); pass.OnCameraCleanup(command); Graphics.ExecuteCommandBuffer(command); Cleared(); }
                        finally { command.Release(); pass.Dispose(); }
                    });
                    check("owned disposal clears bindings, diagnostic refs and destroys RT", () =>
                    {
                        var pass = new CharacterShadowPass(null, 64); var rt = new RenderTexture(16, 16, 0); rt.Create();
                        Set(pass, "resolved", rt); CharacterShadowPass.LastResolved = rt; Seed(rt);
                        pass.Dispose(); pass.Dispose(); Cleared();
                        Require(CharacterShadowPass.LastResolved == null && rt == null, "released texture or diagnostic retained");
                    });
                    check("unowned disposal leaves other producer state intact", () =>
                    {
                        Seed(Texture2D.blackTexture); CharacterShadowPass.LastResolved = null;
                        new CharacterShadowPass(null, 64).Dispose();
                        Require(Shader.GetGlobalFloat(CharacterShadowPass.SelfShadowGateName) == 1 &&
                            Shader.GetGlobalTexture(CharacterShadowPass.ScreenTextureName) == Texture2D.blackTexture, "unowned G cleared");
                    });
                    check("resize destroys old owned RT", () =>
                    {
                        var pass = new CharacterShadowPass(null, 64); var command = new CommandBuffer();
                        try
                        {
                            pass.OnCameraSetup(command, ref data); Graphics.ExecuteCommandBuffer(command); command.Clear();
                            var old = (RenderTexture)typeof(CharacterShadowPass).GetField("resolved", BindingFlags.NonPublic | BindingFlags.Instance).GetValue(pass);
                            var resized = data; var descriptor = data.cameraData.cameraTargetDescriptor; descriptor.width = 24; resized.cameraData.cameraTargetDescriptor = descriptor;
                            pass.OnCameraSetup(command, ref resized); Graphics.ExecuteCommandBuffer(command);
                            Require(old == null, "resized texture was released but not destroyed");
                        }
                        finally { command.Release(); pass.Dispose(); }
                    });
                }
                finally { feature.Dispose(); Object.DestroyImmediate(feature); }
                check("actual URP multi-camera / disable / early return sequence", () => RenderSequence(lines));
                lines.Add($"RESULT {(failed == 0 ? "PASS" : "FAIL")} cases={cases} failures={failed}; lifecycle only, no source-formula/full-scene/MMD certificate.");
                using (var stream = new FileStream(output, FileMode.CreateNew, FileAccess.Write))
                using (var writer = new StreamWriter(stream)) foreach (string line in lines) writer.WriteLine(line);
                Require(failed == 0, "Shadow lifecycle failures: " + failed);
                Debug.Log("Shadow lifecycle PASS: " + output);
            }
            finally
            {
                Shader.SetGlobalTexture(CharacterShadowPass.ScreenTextureName, savedG); Shader.SetGlobalTexture("_EndfieldDirectionalShadowScreen", savedR);
                Shader.SetGlobalFloat(CharacterShadowPass.SelfShadowGateName, savedGate); Shader.SetGlobalFloat("_EndfieldDirectionalScreenShadow", savedRGate);
                Shader.SetGlobalVector(CharacterShadowPass.ScreenSizeName, savedSize);
                Shader.SetGlobalVector("_CharacterLightDir", savedLightDir); Shader.SetGlobalVector("_CharacterLightColor", savedLightColor); Shader.SetGlobalVector("_CharacterAmbient", savedAmbient);
            }
        }
        static void RenderSequence(List<string> lines)
        {
            var previousPipeline = QualitySettings.renderPipeline; var previousDefault = GraphicsSettings.defaultRenderPipeline; var original = GraphicsSettings.currentRenderPipeline as UniversalRenderPipelineAsset;
            Require(original != null, "URP required"); var owned = new List<Object>(); Scene scene = default;
            try
            {
                scene = EditorSceneManager.NewScene(NewSceneSetup.EmptyScene, NewSceneMode.Single);
                var originalData = new SerializedObject(original);
                int index = originalData.FindProperty("m_DefaultRendererIndex").intValue;
                var renderer = Object.Instantiate(originalData.FindProperty("m_RendererDataList").GetArrayElementAtIndex(index).objectReferenceValue as UniversalRendererData); owned.Add(renderer);
                renderer.rendererFeatures.Clear();
                var feature = ScriptableObject.CreateInstance<EndfieldCharacterShadowFeature>(); owned.Add(feature);
                var settings = new SerializedObject(feature); settings.FindProperty("resolveShader").objectReferenceValue = AssetDatabase.LoadAssetAtPath<ComputeShader>("Assets/EndfieldShaderPack/EndfieldCharacterShadowResolve.compute");
                settings.FindProperty("atlasResolution").intValue = 64; settings.ApplyModifiedPropertiesWithoutUndo(); feature.Create(); renderer.rendererFeatures.Add(feature); renderer.SetDirty();
                var probe = ScriptableObject.CreateInstance<EndfieldShadowLifecycleProbe>(); owned.Add(probe);
                probe.shader = AssetDatabase.LoadAssetAtPath<ComputeShader>("Assets/EndfieldShaderPack/Editor/EndfieldShadowLifecycleProbe.compute");
                probe.Create(); renderer.rendererFeatures.Add(probe); renderer.SetDirty();
                var pipeline = Object.Instantiate(original); owned.Add(pipeline); pipeline.msaaSampleCount = 1; pipeline.renderScale = 1;
                var pipelineData = new SerializedObject(pipeline); var renderers = pipelineData.FindProperty("m_RendererDataList"); renderers.arraySize = 1; renderers.GetArrayElementAtIndex(0).objectReferenceValue = renderer;
                pipelineData.FindProperty("m_DefaultRendererIndex").intValue = 0; pipelineData.ApplyModifiedPropertiesWithoutUndo(); QualitySettings.renderPipeline = pipeline; GraphicsSettings.defaultRenderPipeline = pipeline;
                // A synchronous executeMethod has no intervening Editor loop
                // after switching assets. Prepare the test pipeline explicitly;
                // otherwise Camera.Render can use the previous pipeline instance.
                var prepare = typeof(RenderPipelineManager).GetMethod("PrepareRenderPipeline", BindingFlags.NonPublic | BindingFlags.Static);
                Require(prepare != null, "Installed Unity pipeline preparation hook missing");
                var root = new GameObject("ShadowLifecycleFixture"); owned.Add(root); SceneManager.MoveGameObjectToScene(root, scene);
                var cube = GameObject.CreatePrimitive(PrimitiveType.Cube); cube.transform.SetParent(root.transform); cube.layer = 30;
                var material = new Material(Shader.Find("Endfield/CharacterLit")); owned.Add(material); cube.GetComponent<Renderer>().sharedMaterial = material;
                var caster = root.AddComponent<EndfieldCharacterShadowCaster>();
                lines.Add("Fixture caster: enabled=" + caster.enabled + " active=" + caster.gameObject.activeInHierarchy + " isActiveAndEnabled=" + caster.isActiveAndEnabled + " registry=" + EndfieldCharacterShadowCaster.Active.Count + " found=" + Object.FindObjectsOfType<EndfieldCharacterShadowCaster>().Length + " scene=" + caster.gameObject.scene.name);
                var light = root.AddComponent<Endfield.EndfieldCharacterLight>();
                EndfieldCharacterShadowCaster.Refresh();
                lines.Add("Fixture pipeline: selected=" + (GraphicsSettings.currentRenderPipeline == pipeline) + " rendererFeatures=" + renderer.rendererFeatures.Count + " refreshed casters=" + EndfieldCharacterShadowCaster.Active.Count);
                var cameras = new List<Camera>();
                foreach (string name in new[] { "A", "B" })
                {
                    var go = new GameObject("LifecycleCamera" + name); go.transform.SetParent(root.transform); go.transform.position = new Vector3(0, 0, -3);
                    var camera = go.AddComponent<Camera>(); camera.enabled = false; camera.allowMSAA = false; camera.cullingMask = 1 << 30;
                    camera.scene = scene; var rt = new RenderTexture(name == "A" ? 64 : 72, 48, 24, RenderTextureFormat.ARGBHalf); owned.Add(rt); rt.Create(); camera.targetTexture = rt; cameras.Add(camera);
                }
                prepare.Invoke(null, new object[] { pipeline });
                Require(RenderPipelineManager.currentPipeline != null, "Temporary pipeline instance not created");
                lines.Add("Fixture active instance=" + RenderPipelineManager.currentPipeline.GetType().Name);
                foreach (int cameraIndex in new[] { 0, 0, 1, 0 })
                {
                    long before = Sequence(); RenderCamera(cameras[cameraIndex]);
                    Require(Sequence() > before && (Camera)typeof(CharacterShadowPass).GetField("LastRenderedCamera").GetValue(null) == cameras[cameraIndex], "stale completion/camera diagnostic; skip=" + EndfieldCharacterShadowFeature.LastSkipReason);
                    Vector4 observed = probe.Read();
                    Require(probe.camera == cameras[cameraIndex] && observed.x == 1 && observed.y == cameras[cameraIndex].targetTexture.width && observed.z == cameras[cameraIndex].targetTexture.height && float.IsFinite(observed.w), "G not bound during opaque rendering: " + observed);
                    Require(CharacterShadowPass.LastResolved != null && CharacterShadowPass.LastResolved.width == cameras[cameraIndex].targetTexture.width, "wrong camera mask size"); Cleared();
                    lines.Add("PASS fresh render " + cameras[cameraIndex].name + " seq=" + Sequence());
                }
                feature.SetActive(false); long inactive = Sequence(); RenderCamera(cameras[1]); Require(Sequence() == inactive && probe.Read().x == 0, "inactive feature executed or leaked G during rendering"); Cleared(); lines.Add("PASS feature disabled camera B");
                feature.SetActive(true); RenderCamera(cameras[0]); Cleared();
                caster.enabled = false; long skipped = Sequence(); RenderCamera(cameras[1]); Require(Sequence() == skipped && CharacterShadowPass.LastResolved == null && probe.Read().x == 0, "no-caster render reused diagnostic/G"); Cleared(); lines.Add("PASS no-caster skip camera B");
                caster.enabled = true; light.enabled = false; long noLight = Sequence(); RenderCamera(cameras[0]); Require(Sequence() == noLight && CharacterShadowPass.LastResolved == null && probe.Read().x == 0, "disabled light reused diagnostic/G"); Cleared(); lines.Add("PASS disabled-light early return camera A");
                light.enabled = true; RenderCamera(cameras[0]); Cleared(); Require(Sequence() > noLight, "failed to recover after early return"); lines.Add("PASS recovered render after early return");
            }
            finally
            {
                QualitySettings.renderPipeline = previousPipeline; GraphicsSettings.defaultRenderPipeline = previousDefault;
                typeof(RenderPipelineManager).GetMethod("PrepareRenderPipeline", BindingFlags.NonPublic | BindingFlags.Static)?.Invoke(null, new object[] { GraphicsSettings.currentRenderPipeline });
                for (int i = owned.Count - 1; i >= 0; i--)
                {
                    if (owned[i] is ScriptableRendererFeature feature) feature.Dispose();
                    if (owned[i] is RenderTexture rt) rt.Release();
                    if (owned[i] != null) Object.DestroyImmediate(owned[i]);
                }
                if (scene.IsValid()) EditorSceneManager.NewScene(NewSceneSetup.EmptyScene, NewSceneMode.Single);
                EndfieldCharacterShadowCaster.Refresh();
            }
        }
    }

    // Test-only observer records bindings during the actual URP opaque phase,
    // before OnCameraCleanup clears G. It does not change shader globals.
    public sealed class EndfieldShadowLifecycleProbe : ScriptableRendererFeature
    {
        public Camera camera;
        public ComputeShader shader;
        ComputeBuffer buffer;
        ProbePass pass;
        public override void Create() => pass = new ProbePass(this) { renderPassEvent = RenderPassEvent.AfterRenderingOpaques };
        public override void AddRenderPasses(ScriptableRenderer renderer, ref RenderingData renderingData) => renderer.EnqueuePass(pass);
        public Vector4 Read() { var value = new Vector4[1]; buffer.GetData(value); return value[0]; }
        protected override void Dispose(bool disposing) { buffer?.Release(); buffer = null; }
        sealed class ProbePass : ScriptableRenderPass
        {
            readonly EndfieldShadowLifecycleProbe owner;
            public ProbePass(EndfieldShadowLifecycleProbe owner) { this.owner = owner; }
            public override void Execute(ScriptableRenderContext context, ref RenderingData renderingData)
            {
                owner.camera = renderingData.cameraData.camera;
                if (owner.buffer == null) owner.buffer = new ComputeBuffer(1, 16);
                var command = CommandBufferPool.Get("Test shadow bindings during opaque rendering");
                try
                {
                    command.SetComputeBufferParam(owner.shader, 0, "_LifecycleProbe", owner.buffer);
                    command.DispatchCompute(owner.shader, 0, 1, 1, 1);
                    context.ExecuteCommandBuffer(command);
                }
                finally { CommandBufferPool.Release(command); }
            }
        }
    }
}
