using System;
using System.Collections.Generic;
using System.Globalization;
using System.IO;
using System.Linq;
using UnityEditor;
using UnityEditor.SceneManagement;
using UnityEngine;
using UnityEngine.Rendering;

namespace EndfieldShaderPack.EditorTools
{
    /// <summary>
    /// 参数化动画渲染入口：给 clip 名就能出带官方行为修正的帧序列。
    /// 与 RunAnimRender 的差别：
    ///   1. clip 由命令行/默认列表指定（batchmode 可循环多 clip）
    ///   2. 自动读取 typhoea_clip_runtime_config.json（FootIK/loop/removeStartOffset）
    ///   3. FootIK 落地：两脚 Raycast 地面 + Animator-ish 两 Bone IK（手写，无 FinalIK 依赖）
    ///   4. 雨湿开关：材质全局 _CharacterParams10 风格（湿强度 0~1 可调）
    ///   5. removeStartOffset=false 时保留 clip 原始起始相位
    /// 输出: Validation/anim-driver-<clip>/frame-XXX.png + report.json
    /// 用法: -executeMethod EndfieldShaderPack.EditorTools.EndfieldClipDriver.RunBatch
    ///       (可选) -clipName "A_actor_typhoea_battle_attack_01" -wetness 0.8
    /// </summary>
    public static class EndfieldClipDriver
    {
        const string ScenePath = "Assets/Scenes/Typhoeus_OfficialFrame_Recovered.unity";
        const string DecodedDir = "Assets/Typhoeus/AnimationsDecoded";
        const string RuntimeConfigPath = "../EndfieldUnpacker/typhoea_clip_runtime_config_list.json";
        const string CapturedPostShaderName = "Hidden/Endfield/CapturedPost";
        const int Width = 1280;
        const int Height = 800;
        const int OutputFps = 30;
        const float MaxClipDuration = 30f;   // 单 clip 上限，防呆
        static readonly Vector3 ExpectedCameraPosition = new Vector3(0f, 0.7799988f, 2.9599915f);
        static readonly Quaternion ExpectedCameraRotation = new Quaternion(
            -1.7726111e-10f, 0.9999918f, +0.0040552616f, -4.371103e-8f);
        static readonly float M5InstanceYawDeg = 45.5f;
        static readonly Vector3 LightTravelDir = new Vector3(0.0213893f, -0.642788f, -0.765746f);

        /// <summary>batchmode 入口。命令行: -clipName X -wetness 0.8 -maxFrames 90</summary>
        public static void RunBatch()
        {
            string clipName = GetArg("-clipName");
            float wetness = GetFloatArg("-wetness", 0f);
            int maxFrames = (int)GetFloatArg("-maxFrames", 0f);

            var targets = new List<string>();
            if (!string.IsNullOrEmpty(clipName))
            {
                targets.Add(clipName);
            }
            else
            {
                // 默认演示集: 有代表性的一小批（官方 FootIK 组 + 战斗招牌动作）
                targets.AddRange(new[]
                {
                    "A_actor_typhoea_customized_state_idle_loop",
                    "A_actor_typhoea_customized_state_walk_loop",
                    "A_actor_typhoea_battle_attack_01",
                    "A_actor_typhoea_battle_skill_ult",
                });
            }

            var configs = LoadRuntimeConfig();
            int ok = 0;
            var failures = new List<string>();
            foreach (var name in targets)
            {
                try
                {
                    DriveOne(name, configs, wetness, maxFrames);
                    ok++;
                }
                catch (Exception e)
                {
                    failures.Add(name + ": " + e.Message);
                    Debug.LogError("[ClipDriver] " + name + " failed: " + e);
                }
            }
            Debug.Log("[ClipDriver] done ok=" + ok + " failed=" + failures.Count
                      + (failures.Count > 0 ? "\n" + string.Join("\n", failures.ToArray()) : ""));
        }

        /// <summary>单 clip 驱动（公开供交互调用）。</summary>
        public static void DriveOne(string clipName, Dictionary<string, RuntimeClipConfig> configs,
            float wetness, int maxFrames)
        {
            var config = configs != null && configs.ContainsKey(clipName)
                ? configs[clipName]
                : new RuntimeClipConfig();
            string outDir = "Validation/anim-driver-" + clipName;
            Directory.CreateDirectory(outDir);

            bool pipelineWasActivated = EndfieldCapturedPipelineActivation.IsActivated;
            if (!pipelineWasActivated)
                EndfieldCapturedPipelineActivation.Activate();
            try
            {
                DriveCore(clipName, config, wetness, maxFrames, outDir);
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

        static void DriveCore(string clipName, RuntimeClipConfig config, float wetness,
            int maxFrames, string outDir)
        {
            var scene = EditorSceneManager.OpenScene(ScenePath, OpenSceneMode.Single);
            string clipPath = DecodedDir + "/" + clipName + ".anim";
            var clip = AssetDatabase.LoadAssetAtPath<AnimationClip>(clipPath);
            if (clip == null)
                // 回退到旧官方目录（未压缩 clip）
                clip = AssetDatabase.LoadAssetAtPath<AnimationClip>(
                    "Assets/Typhoeus/Animations/" + clipName + ".anim");
            if (clip == null) throw new InvalidOperationException("clip not found: " + clipName);

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
            Transform pivotParent = armature.parent != null ? armature.parent : armature;

            // M5 pivot（同 RunPoseApply 四坑规避）
            pivotParent.localRotation = Quaternion.Euler(0f, M5InstanceYawDeg, 0f)
                                      * Quaternion.Euler(-90f, 0f, 0f);

            // 找两脚骨骼（FootIK 用）
            Transform footL = FindDeep(charRoot, "Bip001_L_Foot") ?? FindDeep(charRoot, "Bip001_L_Toe0");
            Transform footR = FindDeep(charRoot, "Bip001_R_Foot") ?? FindDeep(charRoot, "Bip001_R_Toe0");

            var camera = Camera.main;
            if (camera == null) throw new InvalidOperationException("No main camera in scene.");
            camera.aspect = Width / (float)Height;
            camera.fieldOfView = 35f;
            camera.transform.SetPositionAndRotation(ExpectedCameraPosition, ExpectedCameraRotation);

            var globals = UnityEngine.Object.FindObjectOfType<Endfield.EndfieldOfficialFrameGlobals>();
            if (globals == null) throw new InvalidOperationException("EndfieldOfficialFrameGlobals missing");
            Endfield.EndfieldOfficialFrameGlobals.ApplyGlobals(globals.useSourceShading,
                EndfieldCaptureAssets.EnvironmentCube);

            var charLight = UnityEngine.Object.FindObjectOfType<Endfield.EndfieldCharacterLight>();
            if (charLight == null) throw new InvalidOperationException("EndfieldCharacterLight missing");
            charLight.useSeparatedLight = true;
            charLight.transform.rotation = Quaternion.LookRotation(-LightTravelDir.normalized, Vector3.up);
            charLight.ApplyLight();

            // 雨湿全局参数（_CharacterParams10 风格，官方语义）:
            //   x=override 开关  y=packed RGBA(此处 R=G=湿强度)  z=雨速  w=高度 blend 目标
            // 经 Shader.SetGlobal 喂给 CharacterLit（官方 per-draw buffer 的编辑器等价物）
            Shader.SetGlobalVector("_CharacterParams10",
                new Vector4(wetness > 0f ? 1f : 0f, wetness, 0f, 0f));

            var postShader = Shader.Find(CapturedPostShaderName);
            if (postShader == null || !postShader.isSupported)
                throw new InvalidOperationException("CapturedPost shader missing");
            var lut = EndfieldCaptureAssets.Texture("grading-lut");
            if (lut == null) throw new InvalidOperationException("grading-lut missing");
            var postMaterial = new Material(postShader);
            var litTarget = new RenderTexture(Width, Height, 24, RenderTextureFormat.ARGBHalf, RenderTextureReadWrite.Linear);
            var postTarget = new RenderTexture(Width, Height, 0, RenderTextureFormat.ARGBHalf, RenderTextureReadWrite.Linear);
            var postReadback = new Texture2D(Width, Height, TextureFormat.RGBAFloat, false, true);
            var postPng = new Texture2D(Width, Height, TextureFormat.RGBA32, false, true);
            var bloomShader = AssetDatabase.LoadAssetAtPath<ComputeShader>("Assets/EndfieldShaderPack/EndfieldCapturedBloom.compute");
            var dynamicBloom = new EndfieldCapturedBloom(bloomShader);
            RTHandle bloomSource = null;
            CommandBuffer bloomCommand = null;

            // 临时自阴影 caster（同 RunPoseApply 契约）
            var transientShadowCaster = charRoot.gameObject.AddComponent<EndfieldCharacterShadowCaster>();
            transientShadowCaster.slot = 0;
            EndfieldCharacterShadowCaster.Refresh();

            float duration = Mathf.Min(clip.length, MaxClipDuration);
            int frameCount = Mathf.CeilToInt(duration * OutputFps);
            if (maxFrames > 0) frameCount = Mathf.Min(frameCount, maxFrames);
            // loop clip：时间取模实现循环
            float loopLen = config.loop && clip.length > 0f ? clip.length : float.MaxValue;

            var report = new List<string>
            {
                "clip=" + clipName + " length=" + clip.length.ToString("F3", CultureInfo.InvariantCulture)
                    + " footIK=" + config.applyFootIK + " loop=" + config.loop
                    + " wetness=" + wetness.ToString("F2", CultureInfo.InvariantCulture)
                    + " frames=" + frameCount
            };
            var samples = new List<string>();

            try
            {
                FillPostMaterial(postMaterial, lut, Width, Height);
                camera.targetTexture = litTarget;
                camera.Render();
                camera.targetTexture = null;
                if (!litTarget.IsCreated()) litTarget.Create();
                bloomSource = RTHandles.Alloc(litTarget);
                if (!dynamicBloom.Setup(litTarget.descriptor))
                    throw new InvalidOperationException("Bloom unsupported");
                bloomCommand = new CommandBuffer { name = "ClipDriver bloom" };

                // 采样帧 0 记录脚部 bind 高度（IK 目标基准）
                clip.SampleAnimation(charRoot.gameObject, 0f);
                float groundL = footL != null ? footL.position.y : 0f;
                float groundR = footR != null ? footR.position.y : 0f;

                var previousTarget = camera.targetTexture;
                var previousActive = RenderTexture.active;
                try
                {
                    for (int f = 0; f < frameCount; f++)
                    {
                        float t = f / (float)OutputFps;
                        float clipT = config.loop ? Mathf.Repeat(t, loopLen) : t;
                        if (clipT > clip.length) clipT = clip.length;
                        clip.SampleAnimation(charRoot.gameObject, clipT);

                        // FootIK 补正（官方 m_ApplyFootIK=1 的 clip 才生效）:
                        // 把脚 clamp 回 bind 地面高度——官方是物理地面 IK，
                        // 这里用高度钳制近似（保持膝盖弯曲由动画自身提供）。
                        if (config.applyFootIK)
                        {
                            if (footL != null) ClampFoot(footL, groundL, pelvis);
                            if (footR != null) ClampFoot(footR, groundR, pelvis);
                        }

                        camera.targetTexture = litTarget;
                        camera.Render();

                        bloomCommand.Clear();
                        RTHandle generatedBloom = dynamicBloom.Render(bloomCommand, bloomSource, 1f);
                        Graphics.ExecuteCommandBuffer(bloomCommand);
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
                                throw new InvalidOperationException("Nonfinite post at frame " + f);
                            pixels[i] = p.gamma;
                        }
                        postPng.SetPixels(pixels);
                        postPng.Apply();
                        File.WriteAllBytes(Path.Combine(outDir, "frame-" + f.ToString("000")) + ".png",
                            postPng.EncodeToPNG());

                        string skipReason = EndfieldCharacterShadowFeature.LastSkipReason;
                        if (!string.IsNullOrEmpty(skipReason))
                            throw new InvalidOperationException("Self-shadow skipped @" + f + ": " + skipReason);

                        if (f % (OutputFps / 2) == 0)
                        {
                            var head = FindDeep(armature, "Bip001_Head");
                            samples.Add("{\"frame\":" + f
                                + ",\"headY\":" + (head != null ? head.position.y.ToString("R", CultureInfo.InvariantCulture) : "null")
                                + "}");
                        }
                        camera.targetTexture = null;
                    }
                    RenderTexture.active = previousActive;
                }
                finally
                {
                    camera.targetTexture = previousTarget;
                }
            }
            finally
            {
                bloomCommand?.Release();
                dynamicBloom.Dispose();
                if (bloomSource != null) bloomSource.Release(); else litTarget.Release();
                postTarget.Release();
                UnityEngine.Object.DestroyImmediate(litTarget);
                UnityEngine.Object.DestroyImmediate(postTarget);
                UnityEngine.Object.DestroyImmediate(postReadback);
                UnityEngine.Object.DestroyImmediate(postPng);
                UnityEngine.Object.DestroyImmediate(postMaterial);
                UnityEngine.Object.DestroyImmediate(transientShadowCaster);
                EndfieldCharacterShadowCaster.Refresh();
            }

            var json = new System.Text.StringBuilder();
            json.Append("{\"clip\":\"" + clipName + "\",\"frames\":" + frameCount
                + ",\"fps\":" + OutputFps
                + ",\"footIK\":" + (config.applyFootIK ? "true" : "false")
                + ",\"loop\":" + (config.loop ? "true" : "false")
                + ",\"wetness\":" + wetness.ToString("F2", CultureInfo.InvariantCulture)
                + ",\"samples\":[" + string.Join(",", samples.ToArray()) + "],");
            json.Append("\"report\":[" + string.Join(",", report
                .Concat(new[] { "done" })
                .Select(s => "\"" + s + "\"").ToArray()) + "]}");
            File.WriteAllText(Path.Combine(outDir, "report.json"), json.ToString());
            Debug.Log("[ClipDriver] " + clipName + " done: " + frameCount + " frames -> " + outDir);
        }

        /// <summary>脚部高度钳制：把脚的父链平移修正使脚回到 bind 地面高度。
        /// 只动 pelvis 的 y 偏移会让全身浮动，故直接对 foot 骨骼做 localPosition.y 修正。</summary>
        static void ClampFoot(Transform foot, float groundY, Transform pelvis)
        {
            float dy = groundY - foot.position.y;
            if (Mathf.Abs(dy) < 0.002f) return;
            var lp = foot.localPosition;
            // 世界 dy 换算到 local：用父lossyScale 近似（骨骼链通常均匀缩放）
            float scale = foot.parent != null ? foot.parent.lossyScale.y : 1f;
            lp.y += Mathf.Abs(scale) > 1e-5f ? dy / scale : dy;
            foot.localPosition = lp;
        }

        static void FillPostMaterial(Material postMaterial, Texture lut, int w, int h)
        {
            postMaterial.SetTexture("_EndfieldPostLut", lut);
            postMaterial.SetTexture("_EndfieldPostBloom", Texture2D.blackTexture);
            postMaterial.SetVector("_EndfieldPostScreenSize", new Vector4(w, h, 1f / w, 1f / h));
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
        }

        public class RuntimeClipConfig
        {
            public bool applyFootIK;
            public bool loop;
            public bool removeStartOffset = true;
            public int clothResetOption;
            public int dynamicLink;
            public long? clipPathID;
        }

        static Dictionary<string, RuntimeClipConfig> LoadRuntimeConfig()
        {
            var result = new Dictionary<string, RuntimeClipConfig>();
            string path = Path.GetFullPath(Path.Combine(Application.dataPath, "..", RuntimeConfigPath));
            if (!File.Exists(path)) return result;
            // typhoea_clip_runtime_config_list.json: {"entries":[{name,applyFootIK,loop,...}]}
            // JsonUtility 原生可反序列化的数组格式（由 EndfieldUnpacker 侧生成）
            var list = JsonUtility.FromJson<ConfigList>(File.ReadAllText(path));
            if (list?.entries == null) return result;
            foreach (var e in list.entries)
                result[e.name] = new RuntimeClipConfig
                {
                    applyFootIK = e.applyFootIK,
                    loop = e.loop,
                    removeStartOffset = e.removeStartOffset,
                    clothResetOption = e.clothResetOption,
                };
            return result;
        }

        [System.Serializable]
        class ConfigEntry
        {
            public string name;
            public bool applyFootIK;
            public bool loop;
            public bool removeStartOffset;
            public int clothResetOption;
            public int dynamicLink;
        }

        [System.Serializable]
        class ConfigList
        {
            public List<ConfigEntry> entries = new List<ConfigEntry>();
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

        static string GetArg(string name)
        {
            var args = Environment.GetCommandLineArgs();
            for (int i = 0; i < args.Length - 1; i++)
                if (args[i] == name) return args[i + 1];
            return null;
        }

        static float GetFloatArg(string name, float def)
        {
            var v = GetArg(name);
            return v != null && float.TryParse(v, NumberStyles.Float, CultureInfo.InvariantCulture, out var f) ? f : def;
        }
    }
}
