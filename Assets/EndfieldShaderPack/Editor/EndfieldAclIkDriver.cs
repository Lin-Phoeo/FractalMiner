using System;
using System.Collections.Generic;
using System.Globalization;
using System.IO;
using UnityEditor;
using UnityEditor.SceneManagement;
using UnityEngine;
using UnityEngine.Rendering;

namespace EndfieldShaderPack.EditorTools
{
    /// <summary>
    /// ACL 姿态 + 解析式两骨 IK 驱动器（v2，修"手臂/腿不动"问题）：
    /// 终末地 ACL 数据里四肢主骨（UpperArm/Forearm/Hand/Thigh/Calf/Foot）不是轨
    /// （attack_01 362 轨中只有 corrective/头发/手指/脸/IK 目标/武器轨），官方运行时
    /// 由 IK 求解四肢。Animation Rigging 的 RigLayer.Update() 只同步 job 参数不求解
    /// （求解在 PlayableGraph 动画管线里，batch 编辑器模式下图从不 evaluate）——已实测无效。
    /// 方案 v2：每帧 SampleAnimation 播放 ACL 解码 clip（驱动头发/手指/武器/修正骨/
    /// IK 目标轨），然后解析式两骨 IK（余弦定理）把手/脚末端钉到解码 IK 目标位姿：
    ///   - 链长 l1/l2 从模型当前姿态测量（绑定即当前，因为主骨恒为绑定局部值）
    ///   - 肘/膝弯向：腿用解码 IK_Knee_*_001 位置作极向量（有动画）；手臂无肘目标，
    ///     用绑定姿态肘方向相对肩-手轴的平面法线作极向量（跟随躯干坐标系）
    ///   - 末端旋转 = IK 目标旋转 × 绑定相对偏移（保持自然手腕/脚踝朝向）
    /// 输出: Validation/anim-ik-<clip>/frame-XXX.png + report.json（含手脚世界坐标采样）
    /// </summary>
    public static class EndfieldAclIkDriver
    {
        const string ScenePath = "Assets/Scenes/Typhoeus_OfficialFrame_Recovered.unity";
        const string DecodedDir = "Assets/Typhoeus/AnimationsDecoded";
        const string CapturedPostShaderName = "Hidden/Endfield/CapturedPost";
        const int Width = 1280;
        const int Height = 800;
        const int OutputFps = 30;
        const float MaxClipDuration = 30f;
        static readonly Vector3 ExpectedCameraPosition = new Vector3(0f, 0.7799988f, 2.9599915f);
        static readonly Quaternion ExpectedCameraRotation = new Quaternion(
            -1.7726111e-10f, 0.9999918f, +0.0040552616f, -4.371103e-8f);
        static readonly float M5InstanceYawDeg = 45.5f;
        static readonly Vector3 LightTravelDir = new Vector3(0.0213893f, -0.642788f, -0.765746f);

        /// <summary>batchmode 入口: -clipName X -maxFrames N [-wetness 0.8]</summary>
        public static void RunBatch()
        {
            string clipName = GetArg("-clipName") ?? "A_actor_typhoea_battle_attack_01";
            int maxFrames = (int)GetFloatArg("-maxFrames", 90f);
            float wetness = GetFloatArg("-wetness", 0f);
            Drive(clipName, maxFrames, wetness);
        }

        public static void Drive(string clipName, int maxFrames, float wetness)
        {
            string outDir = "Validation/anim-ik-" + clipName;
            Directory.CreateDirectory(outDir);
            bool pipelineWasActivated = EndfieldCapturedPipelineActivation.IsActivated;
            if (!pipelineWasActivated) EndfieldCapturedPipelineActivation.Activate();
            try { DriveCore(clipName, maxFrames, wetness, outDir); }
            finally
            {
                if (!pipelineWasActivated)
                {
                    EditorSceneManager.NewScene(NewSceneSetup.EmptyScene, NewSceneMode.Single);
                    EndfieldCapturedPipelineActivation.Restore();
                }
            }
        }

        static void DriveCore(string clipName, int maxFrames, float wetness, string outDir)
        {
            var scene = EditorSceneManager.OpenScene(ScenePath, OpenSceneMode.Single);
            string clipPath = DecodedDir + "/" + clipName + ".anim";
            var clip = AssetDatabase.LoadAssetAtPath<AnimationClip>(clipPath);
            if (clip == null) throw new InvalidOperationException("clip not found: " + clipPath);

            Transform charRoot = null;
            foreach (var root in scene.GetRootGameObjects())
                if (root.name == "chr_0034_typhoea_rebuilt") { charRoot = root.transform; break; }
            if (charRoot == null) throw new InvalidOperationException("chr root missing");

            // ---- 解析式 IK 链定义（不用 Animation Rigging，batch 下确定性求解）----
            var chains = new List<IkChain2>();
            foreach (var side in new[] { "R", "L" })
            {
                // 手臂: UpperArm->Forearm->Hand，target=IK_Hand_side_001（动画轨），无肘目标→绑定极向量
                var arm = BuildChain(charRoot, "Arm" + side,
                    "Bip001_" + side + "_UpperArm", "Bip001_" + side + "_Forearm", "Bip001_" + side + "_Hand",
                    "IK_Hand_" + side + "_001", null);
                if (arm != null) chains.Add(arm);
                // 腿: Thigh->Calf->Foot，target=IK_Foot_side_001，极向量=IK_Knee_side_001（动画轨）
                var leg = BuildChain(charRoot, "Leg" + side,
                    "Bip001_" + side + "_Thigh", "Bip001_" + side + "_Calf", "Bip001_" + side + "_Foot",
                    "IK_Foot_" + side + "_001", "IK_Knee_" + side + "_001");
                if (leg != null) chains.Add(leg);
            }
            if (chains.Count == 0) throw new InvalidOperationException("no IK chains built");

            // M5 pivot
            Transform pelvis = FindDeep(charRoot, "Bip001_Pelvis");
            Transform armature = pelvis;
            while (armature.parent != null && (armature.parent.name == "Bip001" || armature.parent.name == "Root"))
                armature = armature.parent;
            (armature.parent != null ? armature.parent : armature).localRotation =
                Quaternion.Euler(0f, M5InstanceYawDeg, 0f) * Quaternion.Euler(-90f, 0f, 0f);

            var camera = Camera.main;
            if (camera == null) throw new InvalidOperationException("No main camera");
            camera.aspect = Width / (float)Height;
            camera.fieldOfView = 35f;
            camera.transform.SetPositionAndRotation(ExpectedCameraPosition, ExpectedCameraRotation);

            var globals = UnityEngine.Object.FindObjectOfType<Endfield.EndfieldOfficialFrameGlobals>();
            Endfield.EndfieldOfficialFrameGlobals.ApplyGlobals(globals.useSourceShading,
                EndfieldCaptureAssets.EnvironmentCube);
            var charLight = UnityEngine.Object.FindObjectOfType<Endfield.EndfieldCharacterLight>();
            charLight.useSeparatedLight = true;
            charLight.transform.rotation = Quaternion.LookRotation(-LightTravelDir.normalized, Vector3.up);
            charLight.ApplyLight();
            Shader.SetGlobalVector("_CharacterParams10",
                new Vector4(wetness > 0f ? 1f : 0f, wetness, 0f, 0f));

            var postShader = Shader.Find(CapturedPostShaderName);
            var lut = EndfieldCaptureAssets.Texture("grading-lut");
            var postMaterial = new Material(postShader);
            var litTarget = new RenderTexture(Width, Height, 24, RenderTextureFormat.ARGBHalf, RenderTextureReadWrite.Linear);
            var postTarget = new RenderTexture(Width, Height, 0, RenderTextureFormat.ARGBHalf, RenderTextureReadWrite.Linear);
            var postReadback = new Texture2D(Width, Height, TextureFormat.RGBAFloat, false, true);
            var postPng = new Texture2D(Width, Height, TextureFormat.RGBA32, false, true);
            var bloomShader = AssetDatabase.LoadAssetAtPath<ComputeShader>("Assets/EndfieldShaderPack/EndfieldCapturedBloom.compute");
            var dynamicBloom = new EndfieldCapturedBloom(bloomShader);
            RTHandle bloomSource = null;
            CommandBuffer bloomCommand = null;
            var transientShadowCaster = charRoot.gameObject.AddComponent<EndfieldCharacterShadowCaster>();
            transientShadowCaster.slot = 0;
            EndfieldCharacterShadowCaster.Refresh();

            float duration = Mathf.Min(clip.length, MaxClipDuration);
            int frameCount = Mathf.CeilToInt(duration * OutputFps);
            if (maxFrames > 0) frameCount = Mathf.Min(frameCount, maxFrames);

            var samples = new List<string>();
            try
            {
                FillPostMaterial(postMaterial, lut, Width, Height);
                camera.targetTexture = litTarget;
                camera.Render();
                camera.targetTexture = null;
                if (!litTarget.IsCreated()) litTarget.Create();
                bloomSource = RTHandles.Alloc(litTarget);
                if (!dynamicBloom.Setup(litTarget.descriptor)) throw new InvalidOperationException("Bloom unsupported");
                bloomCommand = new CommandBuffer { name = "IkDriver bloom" };

                var prevTarget = camera.targetTexture;
                var prevActive = RenderTexture.active;
                try
                {
                    for (int f = 0; f < frameCount; f++)
                    {
                        float t = f / (float)OutputFps;
                        float clipT = Mathf.Min(t, clip.length);
                        // 1) ACL 姿态（头发/手指/武器/修正骨/IK 目标轨被动画驱动）
                        clip.SampleAnimation(charRoot.gameObject, clipT);
                        // 2) 解析式两骨 IK：把手/脚末端钉到解码 IK 目标
                        foreach (var chain in chains)
                            SolveChain(chain);
                        // 3) 渲染
                        camera.targetTexture = litTarget;
                        camera.Render();
                        bloomCommand.Clear();
                        RTHandle gb = dynamicBloom.Render(bloomCommand, bloomSource, 1f);
                        Graphics.ExecuteCommandBuffer(bloomCommand);
                        postMaterial.SetTexture("_EndfieldPostBloom", gb.rt);
                        Graphics.Blit(litTarget, postTarget, postMaterial, 1);
                        RenderTexture.active = postTarget;
                        postReadback.ReadPixels(new Rect(0, 0, Width, Height), 0, 0);
                        postReadback.Apply();
                        var pixels = postReadback.GetPixels();
                        for (int i = 0; i < pixels.Length; i++)
                        {
                            Color p = pixels[i];
                            if (float.IsNaN(p.r + p.g + p.b) || float.IsInfinity(p.r + p.g + p.b))
                                throw new InvalidOperationException("nonfinite @" + f);
                            pixels[i] = p.gamma;
                        }
                        postPng.SetPixels(pixels);
                        postPng.Apply();
                        File.WriteAllBytes(Path.Combine(outDir, "frame-" + f.ToString("000")) + ".png",
                            postPng.EncodeToPNG());
                        if (string.IsNullOrEmpty(EndfieldCharacterShadowFeature.LastSkipReason) == false)
                            throw new InvalidOperationException("shadow skip @" + f);
                        if (f % (OutputFps / 2) == 0)
                        {
                            var sb = new System.Text.StringBuilder("{\"frame\":" + f);
                            foreach (var chain in chains)
                            {
                                if (chain.tip == null) continue;
                                sb.Append(",\"" + chain.name + "\":[" +
                                    chain.tip.position.x.ToString("R", CultureInfo.InvariantCulture) + "," +
                                    chain.tip.position.y.ToString("R", CultureInfo.InvariantCulture) + "," +
                                    chain.tip.position.z.ToString("R", CultureInfo.InvariantCulture) + "]");
                            }
                            sb.Append("}");
                            samples.Add(sb.ToString());
                        }
                        camera.targetTexture = null;
                    }
                    RenderTexture.active = prevActive;
                }
                finally { camera.targetTexture = prevTarget; }
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

            var json = "{\"clip\":\"" + clipName + "\",\"frames\":" + frameCount
                + ",\"ikChains\":" + chains.Count
                + ",\"samples\":[" + string.Join(",", samples.ToArray()) + "]}";
            File.WriteAllText(Path.Combine(outDir, "report.json"), json);
            Debug.Log("[AclIkDriver] " + clipName + " done: " + frameCount + " frames, chains=" + chains.Count);
        }

        class IkChain2
        {
            public string name;
            public Transform root;      // 肩/大腿
            public Transform mid;       // 肘/膝
            public Transform tip;       // 手/脚
            public Transform target;    // 解码动画驱动的 IK 目标骨（IK_Hand/IK_Foot_*_001）
            public Transform poleHint;  // 可选：IK_Knee_*_001（动画轨）作极向量
            public float l1, l2;        // 链长（当前姿态测量）
            public Vector3 bindMidDir;  // 绑定时 mid 相对 root 的方向（世界系）
            public Vector3 bindTipDir;  // 绑定时 tip 相对 root 的方向（世界系）
            public Vector3 bendNormal;  // 绑定弯折平面法线 = normalize(cross(tipDir, midDir))
            public Quaternion tipRotOffset = Quaternion.identity; // target 绑定旋转 → tip 绑定旋转
            public bool captured;       // 首次求解时惰性捕获（在 M5 yaw 之后，坐标系才正确）
        }

        static IkChain2 BuildChain(Transform charRoot, string name,
            string rootName, string midName, string tipName, string targetName, string poleName)
        {
            Transform root = FindDeep(charRoot, rootName);
            Transform mid = FindDeep(charRoot, midName);
            Transform tip = FindDeep(charRoot, tipName);
            if (root == null || mid == null || tip == null)
            {
                Debug.LogWarning("[AclIkDriver] chain " + name + " bones missing: " + rootName);
                return null;
            }
            var c = new IkChain2
            {
                name = name,
                root = root, mid = mid, tip = tip,
                target = FindDeep(charRoot, targetName),
                poleHint = poleName != null ? FindDeep(charRoot, poleName) : null
            };
            c.l1 = Vector3.Distance(root.position, mid.position);
            c.l2 = Vector3.Distance(mid.position, tip.position);
            // bindMidDir/bindTipDir/bendNormal/tipRotOffset 在首次 SolveChain 时捕获
            // （BuildChain 时 M5 yaw 尚未应用，世界系参考会错一个 yaw）
            return c;
        }

        /// <summary>解析式两骨 IK（余弦定理）。调用前须已 SampleAnimation。</summary>
        static void SolveChain(IkChain2 c)
        {
            if (c.target == null) return;
            if (!c.captured)
            {
                c.bindMidDir = (c.mid.position - c.root.position).normalized;
                c.bindTipDir = (c.tip.position - c.root.position).normalized;
                c.bendNormal = Vector3.Cross(c.bindTipDir, c.bindMidDir).normalized;
                c.tipRotOffset = Quaternion.Inverse(c.target.rotation) * c.tip.rotation;
                c.captured = true;
            }
            Vector3 rootPos = c.root.position;
            Vector3 targetPos = c.target.position;

            float reach = Vector3.Distance(rootPos, targetPos);
            float d = Mathf.Clamp(reach,
                Mathf.Abs(c.l1 - c.l2) + 1e-4f, c.l1 + c.l2 - 1e-4f);
            Vector3 dir = reach > 1e-5f ? (targetPos - rootPos) / reach : c.bindTipDir;

            // 弯折平面法线：腿用动画 IK_Knee 位置（投影到垂直 dir 平面），手臂用绑定法线
            Vector3 n = c.bendNormal;
            if (c.poleHint != null)
            {
                Vector3 ph = c.poleHint.position - rootPos;
                ph -= dir * Vector3.Dot(ph, dir);
                if (ph.sqrMagnitude > 1e-8f) n = ph.normalized;
            }
            else
            {
                n -= dir * Vector3.Dot(n, dir);
                if (n.sqrMagnitude > 1e-8f) n = n.normalized;
                else n = c.bendNormal;
            }

            // 余弦定理求肘/膝世界位
            float alongDist = (c.l1 * c.l1 - c.l2 * c.l2 + d * d) / (2f * d);
            float heightSq = Mathf.Max(0f, c.l1 * c.l1 - alongDist * alongDist);
            Vector3 midPos = rootPos + dir * alongDist + n * Mathf.Sqrt(heightSq);

            // 旋转 root 使 mid 方向对准（保留躯干坐标系内的滚动）
            Vector3 midDirNow = (c.mid.position - rootPos).normalized;
            if (midDirNow.sqrMagnitude > 0.5f)
            {
                Quaternion delta1 = Quaternion.FromToRotation(midDirNow, (midPos - rootPos).normalized);
                c.root.rotation = delta1 * c.root.rotation;
            }
            // 旋转 mid 使 tip 指向 target
            Vector3 tipDirNow = (c.tip.position - c.mid.position).normalized;
            Vector3 tipDirWant = (targetPos - c.mid.position).normalized;
            if (tipDirNow.sqrMagnitude > 0.5f && tipDirWant.sqrMagnitude > 0.5f)
            {
                Quaternion delta2 = Quaternion.FromToRotation(tipDirNow, tipDirWant);
                c.mid.rotation = delta2 * c.mid.rotation;
            }
            // 末端旋转跟随 IK 目标（保持绑定相对偏移）
            c.tip.rotation = c.target.rotation * c.tipRotOffset;
        }

        static void FillPostMaterial(Material m, Texture lut, int w, int h)
        {
            m.SetTexture("_EndfieldPostLut", lut);
            m.SetTexture("_EndfieldPostBloom", Texture2D.blackTexture);
            m.SetVector("_EndfieldPostScreenSize", new Vector4(w, h, 1f / w, 1f / h));
            m.SetVector("_EndfieldPostExposure", new Vector4(1f, 1f, 1.6f, 0.100001f));
            m.SetVector("_EndfieldPostLutParameters", new Vector4(1f / 1024f, 1f / 32f, 31f, 1f));
            m.SetVector("_EndfieldPostBloomParameters", new Vector4(0.3660402f, 0f, 0f, 0f));
            m.SetVector("_EndfieldPostBloomThreshold", new Vector4(0.5225216f, 0.2612508f, 0.5225416f, 0.9568616f));
            m.SetVector("_EndfieldPostBloomTint", Vector4.one);
            m.SetVector("_EndfieldPostVignette1", new Vector4(0.5f, 0.5f, 0f, 0f));
            m.SetVector("_EndfieldPostVignette2", new Vector4(0.9f, 2.05f, 1.3f, 0f));
            m.SetVector("_EndfieldPostVignetteColor", new Vector4(0.06666667f, 0.06717458f, 0.07450981f, 1f));
            m.SetVector("_EndfieldPostOptions", new Vector4(0.30000001192092896f, 1f, 1f, 0f));
            m.SetFloat("_EndfieldPostOutputMode", 1f);
            m.SetVector("_EndfieldPostSourceUV", new Vector4(1f, 1f, 0f, 0f));
            m.SetVector("_EndfieldPostBloomUV", new Vector4(1f, 1f, 0f, 0f));
            m.SetVector("_EndfieldPostLutUV", new Vector4(1f, -1f, 0f, 1f));
            m.SetVector("_EndfieldPostScreenUV", new Vector4(1f, 1f, 0f, 0f));
        }

        static Transform FindDeep(Transform root, string name)
        {
            if (root == null) return null;
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
