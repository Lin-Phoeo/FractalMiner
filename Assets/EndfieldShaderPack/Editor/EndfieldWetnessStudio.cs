using System;
using System.Collections.Generic;
using System.IO;
using System.Reflection;
using UnityEditor;
using UnityEditor.SceneManagement;
using UnityEngine;
using UnityEngine.Rendering;
using UnityEngine.Rendering.Universal;
using EndfieldShaderPack.EditorTools.Mmd;
using Object = UnityEngine.Object;

namespace EndfieldShaderPack
{
    /// <summary>Reversible editor-only session. Does not save scene/settings/assets.</summary>
    public sealed class EndfieldWetnessSession : IDisposable
    {
        public Transform Root { get; private set; }
        public Camera Camera { get; private set; }
        public EndfieldCharacterWeather Weather { get; private set; }
        public MmdRetargetProfile InitialPose { get; private set; }
        EndfieldWeatherInputs weatherInputs;
        EndfieldCapturedClothMaterialInputs.Bundle cloth;
        EndfieldCapturedSkinMaterialInputs.Bundle skin;
        EndfieldCapturedHairEyeMaterialInputs.Bundle hairEye;
        EndfieldCapturedEnvironmentInputs.Bundle environment;
        readonly List<Object> owned = new List<Object>();
        RenderPipelineAsset previousQuality, previousDefault;
        bool pipelineChanged, disposed;
        readonly Dictionary<SkinnedMeshRenderer, bool> skinRefresh = new Dictionary<SkinnedMeshRenderer, bool>();
        Endfield.EndfieldOfficialFrameGlobals frameGlobals;
        Cubemap previousEnvironment;
        sealed class PoseState
        { public Transform transform; public Vector3 position, scale; public Quaternion rotation; }
        readonly List<PoseState> originalPose = new List<PoseState>();
        readonly Dictionary<Animator,bool> originalAnimators = new Dictionary<Animator,bool>();
        Vector3 cameraPosition; Quaternion cameraRotation;

        public EndfieldWetnessSession(bool openFreshStage)
        {
            try
            {
                if (openFreshStage)
                {
                    if (!Application.isBatchMode && !EditorSceneManager.SaveCurrentModifiedScenesIfUserWantsTo())
                        throw new OperationCanceledException("未切换场景，保留当前修改。");
                    EditorSceneManager.OpenScene(EndfieldMmdStageBuilder.DanceScenePath, OpenSceneMode.Single);
                }
                foreach (var go in EditorSceneManager.GetActiveScene().GetRootGameObjects())
                {
                    var found = Find(go.transform, "chr_0034_typhoea_rebuilt");
                    if (found == null) continue;
                    if (Root != null) throw new InvalidOperationException("Multiple rebuilt character roots.");
                    Root = found;
                }
                if (Root == null) throw new InvalidOperationException("重建角色缺失，请先构建 MMD 舞台。");
                Camera = UnityEngine.Camera.main;
                if (Camera == null) throw new InvalidOperationException("Main Camera missing.");
                cameraPosition=Camera.transform.position;cameraRotation=Camera.transform.rotation;
                foreach(var t in Root.GetComponentsInChildren<Transform>(true))
                    originalPose.Add(new PoseState {transform=t,position=t.localPosition,rotation=t.localRotation,scale=t.localScale});
                foreach (var animator in Root.GetComponentsInChildren<Animator>(true))
                { originalAnimators.Add(animator,animator.enabled);animator.enabled = false; }
                RestoreCanonicalBindPose(Root);
                foreach (var renderer in Root.GetComponentsInChildren<SkinnedMeshRenderer>(true))
                {
                    skinRefresh.Add(renderer, renderer.forceMatrixRecalculationPerRender);
                    renderer.forceMatrixRecalculationPerRender = true;
                }
                weatherInputs = EndfieldWeatherInputs.Load();
                environment = EndfieldCapturedEnvironmentInputs.Load();
                frameGlobals = Object.FindObjectOfType<Endfield.EndfieldOfficialFrameGlobals>();
                if (frameGlobals != null)
                { previousEnvironment = frameGlobals.capturedEnvironment; frameGlobals.capturedEnvironment = environment.Cube; }
                Endfield.EndfieldOfficialFrameGlobals.ApplyGlobals(true, environment.Cube);
                environment.Bind();
                var light = Object.FindObjectOfType<Endfield.EndfieldCharacterLight>();
                if (light != null)
                {
                    light.useSeparatedLight = true;
                    light.transform.rotation = Quaternion.LookRotation(-new Vector3(.0213892739f, -.6427876353f, -.7657459974f), Vector3.up);
                    light.ApplyLight();
                }
                cloth = EndfieldCapturedClothMaterialInputs.Load(); cloth.Bind(Root);
                skin = EndfieldCapturedSkinMaterialInputs.Load(); skin.Bind(Root);
                hairEye = EndfieldCapturedHairEyeMaterialInputs.Load(); hairEye.Bind(Root);
                Endfield.EndfieldSkinBasisDriver.ApplyForTyphoeus(Root);
                Weather = Root.GetComponent<EndfieldCharacterWeather>();
                if (Weather != null) throw new InvalidOperationException("已有 weather owner；请先关闭之前的预览会话。");
                Weather = Root.gameObject.AddComponent<EndfieldCharacterWeather>();
                Weather.hideFlags = HideFlags.DontSaveInEditor | HideFlags.HideInInspector;
                Weather.rainEffect = weatherInputs.Rain; Weather.rainStreak = weatherInputs.Streak;
                Weather.PrepareRestStreams();
                var caster = Root.GetComponent<EndfieldCharacterShadowCaster>();
                if (caster == null)
                {
                    caster = Root.gameObject.AddComponent<EndfieldCharacterShadowCaster>();
                    caster.hideFlags = HideFlags.DontSaveInEditor | HideFlags.HideInInspector; owned.Add(caster);
                }
                caster.slot = 0; EndfieldCharacterShadowCaster.Refresh();
                SelectMemoryPipeline();
            }
            catch { Dispose(); throw; }
        }

        void SelectMemoryPipeline()
        {
            previousQuality = QualitySettings.renderPipeline; previousDefault = GraphicsSettings.defaultRenderPipeline;
            var source = AssetDatabase.LoadAssetAtPath<UniversalRenderPipelineAsset>(EndfieldCapturedPipelineActivation.PipelinePath);
            if (source == null) throw new InvalidOperationException("CapturedPipeline asset missing.");
            var sourceData = new SerializedObject(source);
            int index = sourceData.FindProperty("m_DefaultRendererIndex").intValue;
            var originalRenderer = sourceData.FindProperty("m_RendererDataList").GetArrayElementAtIndex(index).objectReferenceValue as UniversalRendererData;
            var renderer = Object.Instantiate(originalRenderer); owned.Add(renderer); renderer.hideFlags = HideFlags.HideAndDontSave;
            renderer.rendererFeatures.Clear();
            foreach (var originalFeature in originalRenderer.rendererFeatures)
            {
                if (originalFeature == null) continue;
                var feature = Object.Instantiate(originalFeature); owned.Add(feature); feature.hideFlags = HideFlags.HideAndDontSave;
                renderer.rendererFeatures.Add(feature);
            }
            renderer.SetDirty();
            var pipeline = Object.Instantiate(source); owned.Add(pipeline); pipeline.hideFlags = HideFlags.HideAndDontSave;
            var data = new SerializedObject(pipeline); var renderers = data.FindProperty("m_RendererDataList");
            renderers.arraySize = 1; renderers.GetArrayElementAtIndex(0).objectReferenceValue = renderer;
            data.FindProperty("m_DefaultRendererIndex").intValue = 0; data.ApplyModifiedPropertiesWithoutUndo();
            pipelineChanged = true; QualitySettings.renderPipeline = pipeline; GraphicsSettings.defaultRenderPipeline = pipeline;
            typeof(RenderPipelineManager).GetMethod("PrepareRenderPipeline", BindingFlags.NonPublic | BindingFlags.Static)
                ?.Invoke(null, new object[] { pipeline });
        }
        public void InitializeMmdPose()
        {
            if (Root == null) throw new InvalidOperationException("Character was unloaded.");
            foreach (var animator in Root.GetComponentsInChildren<Animator>(true)) animator.enabled = false;
            RestoreCanonicalBindPose(Root);
            InitialPose = MmdRetargetProfile.FromUnity(Root);
            if (!MmdCalibration.MakeTPose(InitialPose))
                throw new InvalidOperationException("T-pose 校准失败: " + InitialPose.calibrationError);
            foreach (var bone in InitialPose.bones)
            {
                if (bone.transform == null) continue;
                bone.transform.localPosition = bone.localPos;
                bone.transform.localRotation = bone.localRot;
            }
            Endfield.EndfieldSkinBasisDriver.ApplyForTyphoeus(Root);
        }
        // Reproduce the unpacked model builder's complete bind pose, not the saved
        // scene's current pose or only the retargeter's 55 selected role bones.
        public static void RestoreCanonicalBindPose(Transform root)
        {
            var data = JsonUtility.FromJson<Endfield.TyphoeaModelData>(File.ReadAllText(
                Path.Combine(Application.dataPath, "Typhoeus/_typhoea_model_data.json")));
            var world = new Matrix4x4[data.bones.Count]; var known = new bool[world.Length];
            for (int i = 0; i < world.Length; i++) world[i] = Matrix4x4.identity;
            foreach (var mesh in data.meshes)
                for (int b = 0; b < mesh.bones.Length; b++)
                {
                    int index = mesh.bones[b]; var inverse = new Matrix4x4();
                    if (index < 0 || index >= world.Length || mesh.bindPoses.Length < (b+1)*16)
                        throw new InvalidDataException("Invalid unpacked bind palette.");
                    for (int k = 0; k < 16; k++) inverse[k] = mesh.bindPoses[b*16+k];
                    var bind = inverse.inverse;
                    if (known[index]) for (int k = 0; k < 16; k++)
                        if (Mathf.Abs(world[index][k] - bind[k]) > 2e-4f)
                            throw new InvalidDataException("Conflicting bind matrices: " + data.bones[index].name);
                    world[index] = bind; known[index] = true;
                }
            var transforms = new Transform[world.Length]; var local = new Matrix4x4[world.Length];
            // Resolve and validate everything before mutating any bone.
            for (int i = 0; i < transforms.Length; i++)
            {
                int parent = data.bones[i].parent;
                if (parent >= i) throw new InvalidDataException("Bind hierarchy is not parent-first.");
                var ancestor = parent >= 0 ? transforms[parent] : root;
                transforms[i] = ancestor.Find(data.bones[i].name);
                if (transforms[i] == null) throw new InvalidDataException("Missing canonical bone: " + data.bones[i].name);
                local[i] = parent >= 0 ? world[parent].inverse * world[i] : world[i];
                for (int k = 0; k < 16; k++) if (!float.IsFinite(local[i][k]))
                    throw new InvalidDataException("Nonfinite bind matrix.");
            }
            for (int i = 0; i < transforms.Length; i++)
            {
                transforms[i].localPosition = local[i].GetColumn(3);
                transforms[i].localRotation = local[i].rotation;
                transforms[i].localScale = Vector3.one;
            }
        }
        public static Transform Find(Transform root, string name)
        {
            if (root.name == name) return root;
            foreach (Transform child in root) { var found = Find(child, name); if (found != null) return found; }
            return null;
        }
        public void FrameFront(float distance = 2.5f)
        {
            var left = Find(Root,"Bip001_L_UpperArm"); var right = Find(Root,"Bip001_R_UpperArm");
            var pelvis = Find(Root,"Bip001_Pelvis"); var neck = Find(Root,"Bip001_Neck");
            if(left == null || right == null || pelvis == null || neck == null)
                throw new InvalidOperationException("Framing landmarks missing.");
            var up = (neck.position-pelvis.position).normalized;
            var across = (left.position-right.position).normalized;
            var front = Vector3.Cross(up,across).normalized;
            var target = new Vector3(pelvis.position.x,.77f,pelvis.position.z);
            Camera.transform.SetPositionAndRotation(target+front*distance,
                Quaternion.LookRotation(-front,Vector3.up));
        }
        public void SavePreview(string path, int width = 1280, int height = 800, bool cameraEvents = false)
        {
            var oldActive = RenderTexture.active; var oldTarget = Camera.targetTexture;
            var rt = new RenderTexture(width, height, 24, RenderTextureFormat.ARGB32, RenderTextureReadWrite.sRGB)
                { antiAliasing = 1 }; Texture2D image = null;
            try
            {
                rt.Create(); Camera.targetTexture = rt;
                if (cameraEvents)
                    RenderPipeline.SubmitRenderRequest(Camera, new RenderPipeline.StandardRequest { destination = rt });
                else using (Weather.BeginRenderScope())
                    RenderPipeline.SubmitRenderRequest(Camera, new UniversalRenderPipeline.SingleCameraRequest { destination = rt });
                RenderTexture.active = rt; image = new Texture2D(width, height, TextureFormat.RGBA32, false);
                image.ReadPixels(new Rect(0, 0, width, height), 0, 0); image.Apply();
                if (File.Exists(path)) throw new IOException("Preview output exists: " + path);
                File.WriteAllBytes(path, image.EncodeToPNG());
            }
            finally { Camera.targetTexture = oldTarget; RenderTexture.active = oldActive; if (image != null) Object.DestroyImmediate(image); rt.Release(); Object.DestroyImmediate(rt); }
        }
        public void Dispose()
        {
            if (disposed) return; disposed = true;
            if (Weather != null) Object.DestroyImmediate(Weather); Weather = null;
            hairEye?.Dispose(); hairEye = null; skin?.Dispose(); skin = null; cloth?.Dispose(); cloth = null;
            if (frameGlobals != null && environment != null && frameGlobals.capturedEnvironment == environment.Cube)
                frameGlobals.capturedEnvironment = previousEnvironment;
            foreach (var pair in skinRefresh) if (pair.Key != null) pair.Key.forceMatrixRecalculationPerRender = pair.Value;
            skinRefresh.Clear();
            foreach(var state in originalPose) if(state.transform != null)
            {state.transform.localPosition=state.position;state.transform.localRotation=state.rotation;state.transform.localScale=state.scale;}
            originalPose.Clear();
            foreach(var pair in originalAnimators) if(pair.Key != null) pair.Key.enabled=pair.Value;
            originalAnimators.Clear();
            if(Camera != null) Camera.transform.SetPositionAndRotation(cameraPosition,cameraRotation);
            environment?.Dispose(); environment = null; weatherInputs?.Dispose(); weatherInputs = null;
            if (pipelineChanged) { QualitySettings.renderPipeline = previousQuality; GraphicsSettings.defaultRenderPipeline = previousDefault; }
            for (int i = owned.Count - 1; i >= 0; i--) if (owned[i] != null) Object.DestroyImmediate(owned[i]); owned.Clear();
        }
    }

    public sealed class EndfieldWetnessStudio : EditorWindow
    {
        EndfieldWetnessSession session;
        string status = "先打开预览。使用官方 cloth01 b471 雨/浸湿公式及原始纹理；不是整套天气系统认证。";
        [MenuItem("Endfield/Wetness Studio")]
        public static void Open() { GetWindow<EndfieldWetnessStudio>("湿身预览").minSize = new Vector2(460, 320); }
        void OnEnable() { EditorSceneManager.sceneClosing += SceneClosing; EditorApplication.update += TickPreview; }
        void TickPreview()
        {
            if(session?.Weather != null && session.Weather.wetEnabled && !session.Weather.freezeTime)
                EditorApplication.QueuePlayerLoopUpdate();
        }
        void SceneClosing(UnityEngine.SceneManagement.Scene scene, bool removing) { Release(); }
        void OnDisable() { EditorSceneManager.sceneClosing -= SceneClosing; EditorApplication.update -= TickPreview; Release(); }
        void Release() { session?.Dispose(); session = null; }
        void OnGUI()
        {
            EditorGUILayout.HelpBox(status, MessageType.Info);
            if (GUILayout.Button("① 打开干燥/湿身测试舞台（不写原场景）"))
            {
                try { Release(); session = new EndfieldWetnessSession(true); status = "已加载原始天气纹理和原生角色贴图。Game 标签看效果。关闭面板恢复临时资源/管线。"; }
                catch (Exception error) { status = error.Message; Debug.LogException(error); }
            }
            if (session?.Weather == null) return;
            var w = session.Weather;
            w.wetEnabled = EditorGUILayout.Toggle("② 开启湿身（布料 b471）", w.wetEnabled);
            if (GUILayout.Button("正面全身镜头（仅预览相机）")) session.FrameFront();
            w.rain = EditorGUILayout.Slider("雨量 R", w.rain, 0, 1);
            w.immersion = EditorGUILayout.Slider("直接浸湿 B", w.immersion, 0, 1);
            w.waterlineAmount = EditorGUILayout.Slider("水线湿度幅度 G", w.waterlineAmount, 0, 1);
            w.waterlineHeight = EditorGUILayout.FloatField("水线世界高度（米）", w.waterlineHeight);
            w.freezeTime = EditorGUILayout.Toggle("冻结雨滴时间", w.freezeTime);
            if (w.freezeTime) w.seconds = EditorGUILayout.FloatField("时间（秒）", w.seconds);
            if (!string.IsNullOrEmpty(w.InputError)) EditorGUILayout.HelpBox(w.InputError, MessageType.Error);
            EditorGUILayout.HelpBox("目前仅 cloth01/02；皮肤/头发/眼睛仍干燥。雨雪遮挡、干燥过程和全部天气变体待接入。预览时请勿保存舞台：临时资源在关闭面板后释放。", MessageType.None);
            if (GUILayout.Button("保存当前预览 PNG"))
            {
                try
                {
                    string folder = Path.GetFullPath("Validation/wetness-user-" + DateTime.Now.ToString("yyyyMMdd-HHmmss-fff")); Directory.CreateDirectory(folder);
                    session.SavePreview(Path.Combine(folder, "preview.png")); status = "预览: " + folder;
                }
                catch (Exception error) { status = error.Message; }
            }
            if (GUILayout.Button("③ 湿身看完 → 打开 MMD Studio，初始化人物"))
            {
                Release(); EditorApplication.ExecuteMenuItem("Endfield/MMD Studio");
                status = "在 MMD Studio 按①初始化，再②打开 VMD。";
            }
            SceneView.RepaintAll();
            EditorApplication.QueuePlayerLoopUpdate();
        }
    }
}
