// EndfieldVmdBatchRender.cs — offline batch render of VMD-driven frames through
// the recovered official pipeline (URP + captured post + live self-shadow), with
// optional ffmpeg mux of the WAV audio. Replaces screen recording: fixed frame
// rate, deterministic output, chosen resolution, no dropped frames.
// Menu: Endfield/VMD Batch Render
using System;
using System.Collections.Generic;
using System.Diagnostics;
using System.IO;
using UnityEditor;
using UnityEditor.SceneManagement;
using UnityEngine;
using EndfieldShaderPack.EditorTools.Mmd;
using Debug = UnityEngine.Debug;

namespace EndfieldShaderPack
{
    public class EndfieldVmdBatchRender : EditorWindow
    {
        const string ScenePath = EndfieldMmdStageBuilder.DanceScenePath;
        const string CharRootName = "chr_0034_typhoea_rebuilt";
        const string DefaultMotion =
            "D:/动作/UNFORGIVEN (CHALLENGE (Free Motion DL) update/UNFORGIVEN (CHALLENGE (Free Motion DL) update/230506 LE SSERAFIM - UNFORGIVEN (CHALLENGE (flle Motion DL)/Motion.vmd";
        const string DefaultCamera =
            "D:/动作/UNFORGIVEN (CHALLENGE (Free Motion DL) update/UNFORGIVEN (CHALLENGE (Free Motion DL) update/230506 LE SSERAFIM - UNFORGIVEN (CHALLENGE (flle Motion DL)/Camera.vmd";
        const string DefaultAudio =
            "D:/动作/UNFORGIVEN (CHALLENGE (Free Motion DL) update/UNFORGIVEN (CHALLENGE (Free Motion DL) update/230506 LE SSERAFIM - UNFORGIVEN (CHALLENGE (flle Motion DL)/UNFORGIVEN (CHALLENGE).wav";

        string motionPath = DefaultMotion;
        string cameraPath = DefaultCamera;
        string audioPath = DefaultAudio;
        string sourceRigJsonPath = "";
        string outDir = "Validation/vmd-unforgiven";
        int width = 1920, height = 1080;
        int fps = 30;
        int frameStart;
        int frameEnd;              // 0 = 自动（clip.lastFrame）
        float scale = 0.08f;       // 与 Studio 的 suggestedScale 一致
        bool inPlace = true;
        bool keepFeetAboveFloor = true;
        float soleBelowFootBone = 0.05f;
        float heightOffset;
        bool driveCamera = true;
        float camYaw = -90f;       // This Typhoeus rig faces world +X after the M5 pivot.
        bool muxAudio = true;
        bool flipY = false;        // 当前 D3D11 ReadPixels->PNG 路径已是正确朝向；再翻会倒立
        string status = "";
        Vector2 scroll;

        [MenuItem("Endfield/VMD Batch Render")]
        static void Open()
        {
            var w = GetWindow<EndfieldVmdBatchRender>("VMD Batch Render");
            w.minSize = new Vector2(420, 520);
        }

        void OnGUI()
        {
            scroll = GUILayout.BeginScrollView(scroll);
            GUILayout.Label("VMD 离线批渲染（出视频）", EditorStyles.boldLabel);
            EditorGUILayout.HelpBox(
                "逐帧渲染：VMD 驱动骨骼+镜头 → URP 官方管线 → PNG 序列 → ffmpeg 合成 MP4。\n" +
                "无需录屏：固定帧率不掉帧、分辨率自定、可直接接音轨。", MessageType.Info);

            motionPath = FileField("动作 VMD", motionPath);
            sourceRigJsonPath = EditorGUILayout.TextField("动作源骨架 JSON（可空）", sourceRigJsonPath);
            if (GUILayout.Button("选择本机骨架 JSON...", GUILayout.Width(170)))
            {
                string selected = EditorUtility.OpenFilePanel("选择 PMX 动作源骨架 JSON", "", "json");
                if (!string.IsNullOrEmpty(selected)) sourceRigJsonPath = selected;
            }
            cameraPath = FileField("镜头 VMD（可空）", cameraPath);
            audioPath = FileField("音频 WAV（可空）", audioPath);
            outDir = EditorGUILayout.TextField("输出目录（项目相对）", outDir);

            GUILayout.Space(4);
            width = EditorGUILayout.IntSlider("宽度", width, 320, 2560);
            height = EditorGUILayout.IntSlider("高度", height, 240, 1440);
            fps = EditorGUILayout.IntSlider("帧率", fps, 24, 60);
            frameStart = EditorGUILayout.IntField("起始帧", Mathf.Max(0, frameStart));
            frameEnd = EditorGUILayout.IntField("结束帧（0=自动）", Mathf.Max(0, frameEnd));

            GUILayout.Space(4);
            scale = EditorGUILayout.Slider("位移比例", scale, 0f, 0.3f);
            inPlace = EditorGUILayout.Toggle("原地播放（锁水平位移）", inPlace);
            keepFeetAboveFloor = EditorGUILayout.Toggle("脚底防穿地", keepFeetAboveFloor);
            if (keepFeetAboveFloor)
                soleBelowFootBone = EditorGUILayout.Slider("鞋底低于脚骨 (m)", soleBelowFootBone, 0f, 0.15f);
            heightOffset = EditorGUILayout.Slider("高度修正", heightOffset, -1f, 1f);
            driveCamera = EditorGUILayout.Toggle("镜头驱动", driveCamera);
            using (new EditorGUI.DisabledScope(!driveCamera))
                camYaw = EditorGUILayout.Slider("机位偏航（±180）", camYaw, -180f, 360f);
            muxAudio = EditorGUILayout.Toggle("合成音频", muxAudio);
            flipY = EditorGUILayout.Toggle("垂直翻转（仅兼容特殊图形后端）", flipY);

            GUILayout.Space(8);
            using (new EditorGUI.DisabledScope(!File.Exists(motionPath)))
            {
                if (GUILayout.Button("开始渲染", GUILayout.Height(30)))
                    RunRender();
            }
            GUILayout.Space(4);
            var ff = FindFfmpeg();
            GUILayout.Label("ffmpeg: " + (ff != null ? ff : "未找到（只出 PNG 序列，不合成 MP4）"),
                EditorStyles.miniLabel);
            if (!string.IsNullOrEmpty(status))
                GUILayout.Label(status, EditorStyles.wordWrappedMiniLabel);
            GUILayout.EndScrollView();
        }

        static string FileField(string label, string path)
        {
            using (new EditorGUILayout.HorizontalScope())
            {
                path = EditorGUILayout.TextField(label, path);
                if (GUILayout.Button("...", GUILayout.Width(30)))
                {
                    string p = EditorUtility.OpenFilePanel(label, "", "vmd,wav");
                    if (!string.IsNullOrEmpty(p)) path = p;
                }
            }
            return path;
        }

        // ---------- scene bootstrap（与 Anim Studio Setup 同参数） ----------
        static Transform Find(Transform root, string name)
        {
            if (root.name == name) return root;
            foreach (Transform c in root)
            {
                var hit = Find(c, name);
                if (hit != null) return hit;
            }
            return null;
        }

        static Transform EnsureScene(out Camera cam, out bool openedNow,
            out EndfieldCharacterShadowCaster addedCaster)
        {
            openedNow = false;
            addedCaster = null;
            // Always reopen the saved dance scene: calibration from an earlier
            // animated pose is invalid even when the character root still exists.
            if (!Application.isBatchMode && EditorSceneManager.GetActiveScene().isDirty &&
                !EditorUtility.DisplayDialog("VMD Batch Render 需要重开舞台场景",
                    "当前场景有未保存修改。继续会放弃这些修改并从干净绑定姿态渲染。",
                    "放弃修改并继续", "取消"))
            {
                cam = null;
                return null;
            }
            var scene = EditorSceneManager.OpenScene(ScenePath, OpenSceneMode.Single);
            Transform root = null;
            foreach (var go in scene.GetRootGameObjects())
                if (go.name == CharRootName) { root = go.transform; break; }
            openedNow = true;
            if (root == null) { cam = null; return null; }

            // M5 pivot（角色 R_y(+45.5°) 枢轴）
            var pelvis = Find(root, "Bip001_Pelvis");
            if (pelvis != null)
            {
                var armature = pelvis;
                while (armature.parent != null &&
                       (armature.parent.name == "Bip001" || armature.parent.name == "Root"))
                    armature = armature.parent;
                (armature.parent != null ? armature.parent : armature).localRotation =
                    Quaternion.Euler(0f, 45.5f, 0f) * Quaternion.Euler(-90f, 0f, 0f);
            }

            // 光照（捕获帧分支：CP1 平坦环境 + CP11 光方向覆盖）
            var globals = FindObjectOfType<Endfield.EndfieldOfficialFrameGlobals>();
            if (globals != null)
                Endfield.EndfieldOfficialFrameGlobals.ApplyGlobals(globals.useSourceShading,
                    EndfieldCaptureAssets.EnvironmentCube);
            var light = FindObjectOfType<Endfield.EndfieldCharacterLight>();
            if (light != null)
            {
                light.useSeparatedLight = true;
                light.transform.rotation = Quaternion.LookRotation(
                    -new Vector3(0.0213893f, -0.642788f, -0.765746f).normalized, Vector3.up);
                light.ApplyLight();
            }

            // 官方捕获后期 + 动态自阴影投射器（与 Studio 一致）
            if (!EndfieldCapturedPipelineActivation.IsActivated)
                EndfieldCapturedPipelineActivation.Activate();
            var caster = root.GetComponent<EndfieldCharacterShadowCaster>();
            if (caster == null)
            {
                caster = root.gameObject.AddComponent<EndfieldCharacterShadowCaster>();
                caster.hideFlags = HideFlags.DontSaveInEditor | HideFlags.HideInInspector;
                addedCaster = caster;
            }
            caster.slot = 0;
            EndfieldCharacterShadowCaster.Refresh();

            cam = Camera.main;
            return root;
        }

        // ---------- render ----------
        [MenuItem("Endfield/MMD/Validate 3 Second Video")]
        public static void RunPreviewValidation()
        {
            const string previewRoot = "Validation/mmd-stage-preview";
            string parent = Path.GetFullPath(previewRoot);
            var previousRuns = new HashSet<string>(Directory.Exists(parent)
                ? Directory.GetDirectories(parent, "run-*") : Array.Empty<string>());
            var window = CreateInstance<EndfieldVmdBatchRender>();
            try
            {
                window.outDir = previewRoot;
                window.width = 1280;
                window.height = 720;
                window.fps = 30;
                window.frameStart = 270;  // 9-12 seconds: exercises the actual dance, not just its intro.
                window.frameEnd = 359;
                window.muxAudio = true;
                window.RunRender();

                var runs = Directory.Exists(parent) ? Array.FindAll(
                    Directory.GetDirectories(parent, "run-*"), run => !previousRuns.Contains(run)) : Array.Empty<string>();
                Array.Sort(runs, StringComparer.Ordinal);
                if (runs.Length != 1) throw new InvalidOperationException("Video preview expected one new run directory: " + window.status);
                string latest = runs[runs.Length - 1];
                int frames = Directory.GetFiles(latest, "frame_*.png").Length;
                string video = Path.Combine(latest, "unforgiven.mp4");
                if (frames != 90 || !File.Exists(video) || new FileInfo(video).Length < 1024)
                    throw new InvalidOperationException("Video preview failed: " + frames +
                        " frames, mp4=" + File.Exists(video) + ", status=" + window.status);
                File.WriteAllText(Path.Combine(parent, "report.json"),
                    "{\"pass\":true,\"frames\":" + frames +
                    ",\"vmdFrameStart\":270,\"vmdFrameEnd\":359" +
                    ",\"size\":\"1280x720\",\"fps\":30,\"video\":\"" + EscapeJson(video) + "\"}");
                Debug.Log("[MmdPreview] PASS " + frames + " frames -> " + video);
            }
            finally { DestroyImmediate(window); }
        }

        public static void RunSmokeValidation()
        {
            string[] commandArgs = Environment.GetCommandLineArgs();
            string Arg(string key)
            {
                for (int ai = 0; ai + 1 < commandArgs.Length; ++ai)
                    if (commandArgs[ai] == key) return commandArgs[ai + 1];
                return null;
            }
            string validationDir = Arg("-mmdOutputDir") ?? "Validation/mmd-smoke-01";
            string sourceRigPath = Arg("-mmdRigPath");
            Directory.CreateDirectory(validationDir);
            bool pipelineWasActivated = EndfieldCapturedPipelineActivation.IsActivated;
            EndfieldCharacterShadowCaster addedCaster = null;
            var samples = new List<string>();
            try
            {
                if (!pipelineWasActivated) EndfieldCapturedPipelineActivation.Activate();
                var scene = EditorSceneManager.OpenScene(ScenePath, OpenSceneMode.Single);
                Transform root = null;
                foreach (var go in scene.GetRootGameObjects())
                {
                    root = Find(go.transform, CharRootName);
                    if (root != null) break;
                }
                if (root == null) throw new InvalidOperationException("Smoke: character root missing.");

                // Match MMD Studio/Batch initialization, including the M5 instance pivot.
                var pivotPelvis = Find(root, "Bip001_Pelvis");
                if (pivotPelvis == null) throw new InvalidOperationException("Smoke: pelvis missing.");
                var armature = pivotPelvis;
                while (armature.parent != null &&
                       (armature.parent.name == "Bip001" || armature.parent.name == "Root"))
                    armature = armature.parent;
                (armature.parent != null ? armature.parent : armature).localRotation =
                    Quaternion.Euler(0f, 45.5f, 0f) * Quaternion.Euler(-90f, 0f, 0f);

                var caster = root.GetComponent<EndfieldCharacterShadowCaster>();
                if (caster == null)
                {
                    caster = root.gameObject.AddComponent<EndfieldCharacterShadowCaster>();
                    caster.hideFlags = HideFlags.DontSaveInEditor | HideFlags.HideInInspector;
                    addedCaster = caster;
                }
                caster.slot = 0;
                EndfieldCharacterShadowCaster.Refresh();

                var globals = FindObjectOfType<Endfield.EndfieldOfficialFrameGlobals>();
                if (globals != null)
                    Endfield.EndfieldOfficialFrameGlobals.ApplyGlobals(globals.useSourceShading,
                        EndfieldCaptureAssets.EnvironmentCube);
                var light = FindObjectOfType<Endfield.EndfieldCharacterLight>();
                if (light != null)
                {
                    light.useSeparatedLight = true;
                    light.transform.rotation = Quaternion.LookRotation(
                        -new Vector3(0.0213893f, -0.642788f, -0.765746f).normalized, Vector3.up);
                    light.ApplyLight();
                }

                var camera = Camera.main;
                if (camera == null) throw new InvalidOperationException("Smoke: Main Camera missing.");
                var postProfile = camera.GetComponent<EndfieldCapturedPostProfile>();
                if (postProfile == null || !postProfile.IsConfigured)
                    throw new InvalidOperationException("Smoke: captured post profile is not configured on the dance camera.");
                if (!File.Exists(DefaultMotion)) throw new FileNotFoundException("Smoke motion missing", DefaultMotion);
                if (!File.Exists(DefaultCamera)) throw new FileNotFoundException("Smoke camera missing", DefaultCamera);

                var motion = Vmd.ReadFile(DefaultMotion);
                MmdRigDefinition sourceRig = string.IsNullOrEmpty(sourceRigPath) ? null :
                    MmdRigDefinition.FromFile(sourceRigPath);
                var player = MmdPlayer.Load(motion, root, sourceRig);
                if (!player.calibrationOk)
                    throw new InvalidOperationException("Smoke T-pose calibration failed: " + player.profile.calibrationError);
                for (int fingerRole = 24; fingerRole <= 53; ++fingerRole)
                    if (player.profile.ByRole(fingerRole) == null)
                        throw new InvalidOperationException("Smoke finger role missing from target rig: " + fingerRole);
                var sourceEvaluator = new MmdRigEvaluator();
                sourceEvaluator.Bind(player.sourceRig, motion);
                Vector3 targetLeft = player.profile.ByRole(13).restPos;
                Vector3 targetRight = player.profile.ByRole(14).restPos;
                Vector3 targetHip = player.profile.ByRole(0).restPos;
                Vector3 targetHead = player.profile.ByRole(10).restPos;
                Vector3 sourceLeft = player.sourceRig.bones[player.sourceRig.Find(MmdRigDefinition.RoleNames[13])].rest;
                Vector3 sourceRight = player.sourceRig.bones[player.sourceRig.Find(MmdRigDefinition.RoleNames[14])].rest;
                Vector3 sourceHip = player.sourceRig.bones[player.sourceRig.Find(MmdRigDefinition.RoleNames[0])].rest;
                Vector3 sourceHead = player.sourceRig.bones[player.sourceRig.Find(MmdRigDefinition.RoleNames[10])].rest;
                Quaternion BodyBasis(Vector3 left, Vector3 right, Vector3 hip, Vector3 head)
                {
                    Vector3 x = (left - right).normalized;
                    Vector3 y = (head - hip).normalized;
                    Vector3 z = Vector3.Cross(x, y).normalized;
                    y = Vector3.Cross(z, x).normalized;
                    return Quaternion.LookRotation(z, y);
                }
                Quaternion sourceToTarget = BodyBasis(targetLeft, targetRight, targetHip, targetHead) *
                    Quaternion.Inverse(BodyBasis(sourceLeft, sourceRight, sourceHip, sourceHead));
                int rootId = root.GetInstanceID();
                var cameraDriver = new MmdCameraDriver { target = camera, yaw = -90f };
                cameraDriver.LoadFile(DefaultCamera);
                if (player.charRoot == null || player.charRoot.GetInstanceID() != rootId)
                    throw new InvalidOperationException("Smoke camera load invalidated the MMD player root.");

                double duration = motion.Duration;
                double[] times = { 0.0, duration * 0.25, duration * 0.5, duration * 0.75, duration };
                string[] motionProbeNames =
                    { "Bip001_L_UpperArm", "Bip001_R_UpperArm", "Bip001_L_Thigh", "Bip001_R_Thigh" };
                var motionProbeBase = new Dictionary<string, Quaternion>();
                var fingerProbeBase = new Dictionary<int, Quaternion>();
                var bindVertices = new Dictionary<SkinnedMeshRenderer, Vector3[]>();
                float maxDeformP95 = 0f;
                var skinnedBones = new HashSet<Transform>();
                var weightedBoneCounts = new Dictionary<Transform, int>();
                var weightedNameCounts = new Dictionary<string, int>();
                foreach (var smr in root.GetComponentsInChildren<SkinnedMeshRenderer>(true))
                {
                    foreach (var bone in smr.bones)
                        if (bone != null) skinnedBones.Add(bone);
                    if (smr.sharedMesh == null) continue;
                    var weights = smr.sharedMesh.GetAllBoneWeights();
                    var bones = smr.bones;
                    Debug.Log("[MmdWeightAudit] mesh=" + smr.name + " vertices=" + smr.sharedMesh.vertexCount +
                        " bones=" + bones.Length + " bindposes=" + smr.sharedMesh.bindposes.Length +
                        " weights=" + weights.Length);
                    for (int wi = 0; wi < weights.Length; ++wi)
                    {
                        var weight = weights[wi];
                        if (weight.weight < 0.05f || weight.boneIndex >= bones.Length) continue;
                        var bone = bones[weight.boneIndex];
                        if (bone == null) continue;
                        weightedBoneCounts.TryGetValue(bone, out int count);
                        weightedBoneCounts[bone] = count + 1;
                        weightedNameCounts.TryGetValue(bone.name, out int nameCount);
                        weightedNameCounts[bone.name] = nameCount + 1;
                    }
                }
                foreach (string probeName in motionProbeNames)
                {
                    var probe = Find(root, probeName);
                    weightedBoneCounts.TryGetValue(probe, out int identityCount);
                    weightedNameCounts.TryGetValue(probeName, out int nameCount);
                    Debug.Log("[MmdWeightAudit] bone=" + probeName + " identity=" + identityCount +
                        " allSameName=" + nameCount + " instanceId=" + probe.GetInstanceID());
                }
                float maxProbeAngle = 0f;
                float maxFingerAngle = 0f;
                for (int i = 0; i < times.Length; ++i)
                {
                    float timeSec = (float)times[i];
                    player.Reset();
                    player.ApplyFrame(timeSec, player.suggestedScale, true, 0f);
                    sourceEvaluator.Sample(timeSec * 30.0);
                    float groundCorrection = player.KeepFeetAboveBindFloor(0.05f);
                    cameraDriver.Apply(timeSec, player.suggestedScale, root, player.bindRootWorld);
                    float leftFootY = Find(root, "Bip001_L_Foot").position.y;
                    float rightFootY = Find(root, "Bip001_R_Foot").position.y;
                    if (Mathf.Min(leftFootY, rightFootY) < player.bindMinFootY - 0.055f)
                        throw new InvalidOperationException("Smoke foot-ground gate failed at " +
                            timeSec.ToString("F3") + "s");
                    var head = Find(root, "Bip001_Head");
                    var pelvis = Find(root, "Bip001_Pelvis");
                    if (head == null || pelvis == null)
                        throw new InvalidOperationException("Smoke orientation probes missing.");
                    Vector3 headViewport = camera.WorldToViewportPoint(head.position);
                    Vector3 pelvisViewport = camera.WorldToViewportPoint(pelvis.position);
                    if (headViewport.z <= 0f || pelvisViewport.z <= 0f ||
                        headViewport.y <= pelvisViewport.y)
                        throw new InvalidOperationException(string.Format(
                            "Smoke orientation gate failed at {0:F3}s: headY={1:F4}, pelvisY={2:F4}",
                            timeSec, headViewport.y, pelvisViewport.y));
                    foreach (string probeName in motionProbeNames)
                    {
                        Transform probe = Find(root, probeName);
                        if (probe == null)
                            throw new InvalidOperationException("Smoke motion probe missing: " + probeName);
                        if (!skinnedBones.Contains(probe))
                            throw new InvalidOperationException("Smoke retarget bone not bound to any visible mesh: " + probeName);
                        weightedBoneCounts.TryGetValue(probe, out int directWeightedCount);
                        int effectiveWeightedCount = 0;
                        foreach (var pair in weightedBoneCounts)
                            if (pair.Key == probe || pair.Key.IsChildOf(probe))
                                effectiveWeightedCount += pair.Value;
                        if (effectiveWeightedCount < 100)
                            throw new InvalidOperationException("Smoke retarget bone subtree has too little visible skin influence: " +
                                probeName + " direct=" + directWeightedCount + " subtree=" + effectiveWeightedCount);
                        if (i == 0) motionProbeBase[probeName] = probe.localRotation;
                        else maxProbeAngle = Mathf.Max(maxProbeAngle,
                            Quaternion.Angle(motionProbeBase[probeName], probe.localRotation));
                    }
                    for (int fingerRole = 24; fingerRole <= 53; ++fingerRole)
                    {
                        Transform finger = player.profile.ByRole(fingerRole).transform;
                        if (i == 0) fingerProbeBase[fingerRole] = finger.localRotation;
                        else maxFingerAngle = Mathf.Max(maxFingerAngle,
                            Quaternion.Angle(fingerProbeBase[fingerRole], finger.localRotation));
                    }
                    Vector4 bounds = SkinnedViewportBounds(root, camera, bindVertices,
                        out float minWorldY, out float minNearFeetY,
                        out float deformMean, out float deformP95);
                    maxDeformP95 = Mathf.Max(maxDeformP95, deformP95);
                    float width = bounds.z - bounds.x;
                    if (!IsFinite(bounds) || width < 0.18f || bounds.w - bounds.y < 0.45f ||
                        bounds.w <= 0f || bounds.y >= 1f)
                        throw new InvalidOperationException(string.Format(
                            "Smoke composition gate failed at {0:F3}s: [{1:F4},{2:F4},{3:F4},{4:F4}] width={5:F4}",
                            timeSec, bounds.x, bounds.y, bounds.z, bounds.w, width));
                    string frame = Path.Combine(validationDir, "frame_" + i.ToString("D2") + ".png");
                    SaveFrame(camera, frame, 1280, 720, false);
                    var arm = Find(root, "Bip001_L_UpperArm");
                    float leftArmAngle = Quaternion.Angle(motionProbeBase["Bip001_L_UpperArm"], arm.localRotation);
                    Vector3 leftHandView = camera.WorldToViewportPoint(Find(root, "Bip001_L_Hand").position);
                    Vector3 rightHandView = camera.WorldToViewportPoint(Find(root, "Bip001_R_Hand").position);
                    float[] limbCos = new float[4];
                    int[] limbStarts = { 13, 14, 1, 2 }, limbEnds = { 15, 16, 3, 4 };
                    string[] limbStartNames = { "Bip001_L_UpperArm", "Bip001_R_UpperArm", "Bip001_L_Thigh", "Bip001_R_Thigh" };
                    string[] limbEndNames = { "Bip001_L_Forearm", "Bip001_R_Forearm", "Bip001_L_Calf", "Bip001_R_Calf" };
                    for (int li = 0; li < 4; ++li)
                    {
                        int si = player.sourceRig.Find(MmdRigDefinition.RoleNames[limbStarts[li]]);
                        int se = player.sourceRig.Find(MmdRigDefinition.RoleNames[limbEnds[li]]);
                        Vector3 expected = root.rotation * sourceToTarget *
                            (sourceEvaluator.pose.positions[se] - sourceEvaluator.pose.positions[si]);
                        Vector3 actual = Find(root, limbEndNames[li]).position - Find(root, limbStartNames[li]).position;
                        limbCos[li] = Vector3.Dot(expected.normalized, actual.normalized);
                    }
                    samples.Add("{\"time\":" + timeSec.ToString("F6", System.Globalization.CultureInfo.InvariantCulture) +
                        ",\"bbox\":[" + bounds.x.ToString("F6", System.Globalization.CultureInfo.InvariantCulture) +
                        "," + bounds.y.ToString("F6", System.Globalization.CultureInfo.InvariantCulture) +
                        "," + bounds.z.ToString("F6", System.Globalization.CultureInfo.InvariantCulture) +
                        "," + bounds.w.ToString("F6", System.Globalization.CultureInfo.InvariantCulture) +
                        "],\"width\":" + width.ToString("F6", System.Globalization.CultureInfo.InvariantCulture) +
                        ",\"rootY\":" + root.position.y.ToString("F6", System.Globalization.CultureInfo.InvariantCulture) +
                        ",\"groundCorrection\":" + groundCorrection.ToString("F6", System.Globalization.CultureInfo.InvariantCulture) +
                        ",\"deformMean\":" + deformMean.ToString("F6", System.Globalization.CultureInfo.InvariantCulture) +
                        ",\"deformP95\":" + deformP95.ToString("F6", System.Globalization.CultureInfo.InvariantCulture) +
                        ",\"leftArmAngleFromStart\":" + leftArmAngle.ToString("F6", System.Globalization.CultureInfo.InvariantCulture) +
                        ",\"limbDirectionCos\":[" + string.Join(",", Array.ConvertAll(limbCos,
                            value => value.ToString("F6", System.Globalization.CultureInfo.InvariantCulture))) + "]" +
                        ",\"leftHandViewport\":[" + leftHandView.x.ToString("F6", System.Globalization.CultureInfo.InvariantCulture) +
                        "," + leftHandView.y.ToString("F6", System.Globalization.CultureInfo.InvariantCulture) + "]," +
                        "\"rightHandViewport\":[" + rightHandView.x.ToString("F6", System.Globalization.CultureInfo.InvariantCulture) +
                        "," + rightHandView.y.ToString("F6", System.Globalization.CultureInfo.InvariantCulture) + "]" +
                        ",\"minWorldY\":" + minWorldY.ToString("F6", System.Globalization.CultureInfo.InvariantCulture) +
                        ",\"minNearFeetY\":" + minNearFeetY.ToString("F6", System.Globalization.CultureInfo.InvariantCulture) +
                        ",\"leftFootY\":" + leftFootY.ToString("F6", System.Globalization.CultureInfo.InvariantCulture) +
                        ",\"rightFootY\":" + rightFootY.ToString("F6", System.Globalization.CultureInfo.InvariantCulture) +
                        ",\"cameraForward\":[" + camera.transform.forward.x.ToString("F6", System.Globalization.CultureInfo.InvariantCulture) +
                        "," + camera.transform.forward.y.ToString("F6", System.Globalization.CultureInfo.InvariantCulture) +
                        "," + camera.transform.forward.z.ToString("F6", System.Globalization.CultureInfo.InvariantCulture) + "]}");
                }
                if (maxProbeAngle < 5f)
                    throw new InvalidOperationException("Smoke motion gate failed: max limb rotation=" +
                        maxProbeAngle.ToString("F3") + "deg");
                if (maxFingerAngle < 10f)
                    throw new InvalidOperationException("Smoke finger motion gate failed: max finger rotation=" +
                        maxFingerAngle.ToString("F3") + "deg");
                if (maxDeformP95 < 0.08f)
                    throw new InvalidOperationException("Smoke mesh deformation gate failed: maximum root-local P95 displacement=" +
                        maxDeformP95.ToString("F4") + "m");

                string skip = EndfieldCharacterShadowFeature.LastSkipReason;
                if (!string.IsNullOrEmpty(skip))
                    throw new InvalidOperationException("Smoke self-shadow skipped: " + skip);
                if (postProfile.executedFrames < times.Length || !postProfile.lastFrameUsedDynamicBloom)
                    throw new InvalidOperationException("Smoke captured post did not execute with dynamic bloom: frames=" +
                        postProfile.executedFrames + ", bloom=" + postProfile.lastFrameUsedDynamicBloom);
                File.WriteAllText(Path.Combine(validationDir, "report.json"),
                    "{\"pass\":true,\"calibration\":true,\"duration\":" +
                    duration.ToString("F6", System.Globalization.CultureInfo.InvariantCulture) +
                    ",\"frames30\":" + (Mathf.FloorToInt((float)duration * 30f + 1e-4f) + 1) +
                    ",\"frames60\":" + (Mathf.FloorToInt((float)duration * 60f + 1e-4f) + 1) +
                    ",\"maxProbeAngle\":" + maxProbeAngle.ToString("F6", System.Globalization.CultureInfo.InvariantCulture) +
                    ",\"maxFingerAngle\":" + maxFingerAngle.ToString("F6", System.Globalization.CultureInfo.InvariantCulture) +
                    ",\"maxDeformP95\":" + maxDeformP95.ToString("F6", System.Globalization.CultureInfo.InvariantCulture) +
                    ",\"postFrames\":" + postProfile.executedFrames +
                    ",\"dynamicBloom\":" + (postProfile.lastFrameUsedDynamicBloom ? "true" : "false") +
                    ",\"loadInfo\":\"" + EscapeJson(player.loadInfo) + "\"" +
                    ",\"rootInstanceId\":" + rootId + ",\"samples\":[" + string.Join(",", samples) + "]}");
                Debug.Log("[MmdSmoke] PASS calibration=true duration=" + duration.ToString("F3") +
                          " samples=" + samples.Count);
            }
            catch (Exception e)
            {
                File.WriteAllText(Path.Combine(validationDir, "report.json"),
                    "{\"pass\":false,\"error\":\"" + EscapeJson(e.Message) + "\"}");
                Debug.LogException(e);
                throw;
            }
            finally
            {
                if (addedCaster != null) DestroyImmediate(addedCaster);
                EndfieldCharacterShadowCaster.Refresh();
                if (!pipelineWasActivated && EndfieldCapturedPipelineActivation.IsActivated)
                {
                    EditorSceneManager.NewScene(NewSceneSetup.EmptyScene, NewSceneMode.Single);
                    EndfieldCapturedPipelineActivation.Restore();
                }
            }
        }

        static Vector4 SkinnedViewportBounds(Transform root, Camera camera,
            Dictionary<SkinnedMeshRenderer, Vector3[]> bindVertices,
            out float minWorldY, out float minNearFeetY,
            out float deformMean, out float deformP95)
        {
            Vector2 min = new Vector2(float.MaxValue, float.MaxValue);
            Vector2 max = new Vector2(float.MinValue, float.MinValue);
            minWorldY = float.MaxValue;
            minNearFeetY = float.MaxValue;
            deformMean = 0f;
            deformP95 = 0f;
            var leftFoot = Find(root, "Bip001_L_Foot");
            var rightFoot = Find(root, "Bip001_R_Foot");
            int visible = 0;
            var displacements = new List<float>();
            var mesh = new Mesh();
            var vertices = new List<Vector3>();
            try
            {
                foreach (var smr in root.GetComponentsInChildren<SkinnedMeshRenderer>(true))
                {
                    if (!smr.enabled || !smr.gameObject.activeInHierarchy) continue;
                    smr.BakeMesh(mesh);
                    mesh.GetVertices(vertices);
                    Matrix4x4 localToWorld = smr.localToWorldMatrix;
                    bool hasBind = bindVertices.TryGetValue(smr, out var bind);
                    if (hasBind && bind.Length != vertices.Count)
                        throw new InvalidOperationException("Smoke mesh topology changed: " + smr.name);
                    if (!hasBind) bind = new Vector3[vertices.Count];
                    for (int vi = 0; vi < vertices.Count; ++vi)
                    {
                        Vector3 world = localToWorld.MultiplyPoint3x4(vertices[vi]);
                        Vector3 local = root.InverseTransformPoint(world);
                        if (hasBind) displacements.Add(Vector3.Distance(local, bind[vi]));
                        else bind[vi] = local;
                        minWorldY = Mathf.Min(minWorldY, world.y);
                        if (leftFoot != null && rightFoot != null &&
                            (new Vector2(world.x - leftFoot.position.x, world.z - leftFoot.position.z).sqrMagnitude < 0.0324f ||
                             new Vector2(world.x - rightFoot.position.x, world.z - rightFoot.position.z).sqrMagnitude < 0.0324f) &&
                            world.y < Mathf.Min(leftFoot.position.y, rightFoot.position.y) + 0.2f)
                            minNearFeetY = Mathf.Min(minNearFeetY, world.y);
                        Vector3 viewport = camera.WorldToViewportPoint(world);
                        if (viewport.z <= 0f) continue;
                        min = Vector2.Min(min, viewport);
                        max = Vector2.Max(max, viewport);
                        visible++;
                    }
                    if (!hasBind) bindVertices.Add(smr, bind);
                }
            }
            finally { DestroyImmediate(mesh); }
            if (visible == 0) throw new InvalidOperationException("Smoke: no skinned vertices in front of camera.");
            if (displacements.Count > 0)
            {
                displacements.Sort();
                double sum = 0.0;
                foreach (float displacement in displacements) sum += displacement;
                deformMean = (float)(sum / displacements.Count);
                deformP95 = displacements[Mathf.CeilToInt(displacements.Count * 0.95f) - 1];
            }
            return new Vector4(min.x, min.y, max.x, max.y);
        }

        static bool IsFinite(Vector4 value) =>
            !(float.IsNaN(value.x + value.y + value.z + value.w) ||
              float.IsInfinity(value.x + value.y + value.z + value.w));

        static string EscapeJson(string value) => (value ?? "")
            .Replace("\\", "\\\\").Replace("\"", "\\\"").Replace("\r", "\\r").Replace("\n", "\\n");

        void RunRender()
        {
            status = "";
            bool pipelineWasActivated = EndfieldCapturedPipelineActivation.IsActivated;
            EndfieldCharacterShadowCaster transientShadowCaster = null;
            try
            {
                var root = EnsureScene(out var cam, out bool openedNow, out transientShadowCaster);
                if (root == null) { status = "场景里找不到 " + CharRootName; return; }
                if (cam == null) { status = "场景里没有 Main Camera"; return; }

            MmdPlayer player;
            var camDriver = new MmdCameraDriver();
            try
            {
                var motion = Vmd.ReadFile(motionPath);
                MmdRigDefinition sourceRig = string.IsNullOrEmpty(sourceRigJsonPath) ? null :
                    MmdRigDefinition.FromFile(sourceRigJsonPath);
                player = MmdPlayer.Load(motion, root, sourceRig);
                if (!player.calibrationOk)
                {
                    status = "T-pose 校准失败: " + player.profile.calibrationError;
                    return;
                }
                camDriver.target = cam;
                camDriver.yaw = camYaw;
                if (File.Exists(cameraPath)) camDriver.LoadFile(cameraPath);
                else camDriver.UseMotionClip(motion);
            }
            catch (Exception e)
            {
                status = "载入失败: " + e.Message;
                return;
            }

            var postProfile = cam.GetComponent<EndfieldCapturedPostProfile>();
            if (postProfile == null || !postProfile.IsConfigured)
            {
                status = "舞台相机缺少捕获后处理配置；请重建 MMD 舞台场景";
                return;
            }

            int last = frameEnd > 0 ? frameEnd : (int)player.clip.lastFrame;
            if (frameStart > last) { status = "起始帧超过结束帧"; return; }
            // frameStart/frameEnd 是 VMD 的 30fps 帧域；输出 fps 只改变采样密度，
            // 不改变动作时长。输出帧 k 对应 VMD 帧 frameStart+k*30/fps。
            double segmentSeconds = (last - frameStart) / 30.0;
            int total = Mathf.FloorToInt((float)(segmentSeconds * fps) + 1e-4f) + 1;

            string parentDir = Path.GetFullPath(Path.Combine(Application.dataPath, "..", outDir));
            string dir = CreateRunDirectory(parentDir);

            int w = width - width % 2, h = height - height % 2;
            cam.aspect = (float)w / h;
            double estMB = total * w * h * 2.6 / (1024.0 * 1024.0);
            status = string.Format("渲染 {0} 帧 → {1}（预计 PNG ~{2:F0} MB）", total, dir, estMB);
            Repaint();

            var manifest = new List<string>
            {
                "motion=" + motionPath,
                "camera=" + (camDriver.HasKeys ? cameraPath : "(none)"),
                "fps=" + fps, "size=" + w + "x" + h,
                "vmdFps=30",   // 采样来源：VMD 帧域固定 30fps；渲染 fps 只决定输出时长
                "frameStart=" + frameStart, "frameEnd=" + last,
                "scale=" + scale, "inPlace=" + inPlace, "heightOffset=" + heightOffset,
                "keepFeetAboveFloor=" + keepFeetAboveFloor,
                "soleBelowFootBone=" + soleBelowFootBone,
                "driveCamera=" + driveCamera, "camYaw=" + camYaw,
                "loadInfo=" + player.loadInfo,
                "face=" + MmdFace.Describe(root),
            };
            File.WriteAllLines(Path.Combine(dir, "manifest.txt"), manifest);

            var sw = Stopwatch.StartNew();
            bool canceled = false;
            for (int outputFrame = 0; outputFrame < total; outputFrame++)
            {
                double vmdFrame = Math.Min(last, frameStart + outputFrame * 30.0 / fps);
                float t = (float)(vmdFrame / 30.0);
                player.Reset();
                player.ApplyFrame(t, scale, inPlace, heightOffset);
                if (keepFeetAboveFloor) player.KeepFeetAboveBindFloor(soleBelowFootBone);
                if (driveCamera && camDriver.HasKeys)
                    camDriver.Apply(t, scale, root, player.bindRootWorld);
                SaveFrame(cam, Path.Combine(dir, "frame_" + outputFrame.ToString("D4") + ".png"), w, h, flipY);
                if (EditorUtility.DisplayCancelableProgressBar("VMD Batch Render",
                        string.Format("输出帧 {0}/{1}  ({2:F1}s)", outputFrame + 1, total, t),
                        (float)(outputFrame + 1) / total))
                { canceled = true; break; }
            }
            EditorUtility.ClearProgressBar();
            sw.Stop();

            string mp4 = null;
            if (!canceled && muxAudio && File.Exists(audioPath) && FindFfmpeg() != null)
            {
                mp4 = Mux(dir, audioPath, fps, w, h, out string muxLog, total);
                if (mp4 == null) status += "\nffmpeg 失败: " + muxLog;
            }
            status = string.Format(
                "{0}{1} 帧 → {2}\n耗时 {3:F1}s{4}",
                canceled ? "已取消，" : "", total, dir, sw.Elapsed.TotalSeconds,
                mp4 != null ? "\nMP4: " + mp4 : "");
            if (mp4 != null && !Application.isBatchMode) EditorUtility.RevealInFinder(mp4);
            Repaint();
            Debug.Log("[VmdBatchRender] " + status);
            }
            finally
            {
                if (transientShadowCaster != null)
                    DestroyImmediate(transientShadowCaster);
                EndfieldCharacterShadowCaster.Refresh();
                if (!pipelineWasActivated && EndfieldCapturedPipelineActivation.IsActivated)
                    EndfieldCapturedPipelineActivation.Restore();
            }
        }

        static string CreateRunDirectory(string parent)
        {
            string run = Path.Combine(parent, "run-" + DateTime.Now.ToString("yyyyMMdd-HHmmss-fff"));
            Directory.CreateDirectory(run);
            return run;
        }

        public static void SaveFrame(Camera cam, string path, int w, int h, bool flip)
        {
            var rt = new RenderTexture(w, h, 24);
            var previousActive = RenderTexture.active;
            var previousTarget = cam.targetTexture;
            Texture2D tex = null;
            try
            {
                cam.targetTexture = rt;
                cam.Render();
                RenderTexture.active = rt;
                tex = new Texture2D(w, h, TextureFormat.RGBA32, false);
                tex.ReadPixels(new Rect(0, 0, w, h), 0, 0);
                if (flip)
                {
                    var px = tex.GetPixels32();
                    for (int y = 0; y < h / 2; y++)
                    {
                        int a = y * w, b = (h - 1 - y) * w;
                        for (int x = 0; x < w; x++)
                        {
                            var tmp = px[a + x];
                            px[a + x] = px[b + x];
                            px[b + x] = tmp;
                        }
                    }
                    tex.SetPixels32(px);
                }
                tex.Apply();
                File.WriteAllBytes(path, tex.EncodeToPNG());
            }
            finally
            {
                cam.targetTexture = previousTarget;
                RenderTexture.active = previousActive;
                if (tex != null) UnityEngine.Object.DestroyImmediate(tex);
                rt.Release();
                UnityEngine.Object.DestroyImmediate(rt);
            }
        }

        public static string Mux(string dir, string audio, int fps, int w, int h,
            out string log, int frameCount = 0)
        {
            string outMp4 = Path.Combine(dir, "unforgiven.mp4");
            string audioInput = !string.IsNullOrEmpty(audio) && File.Exists(audio)
                ? " -i \"" + audio + "\"" : "";
            string shortest = string.IsNullOrEmpty(audioInput) ? "" : " -shortest";
            string frameLimit = frameCount > 0 ? " -frames:v " + frameCount : "";
            var psi = new ProcessStartInfo
            {
                FileName = FindFfmpeg(),
                WorkingDirectory = dir,
                UseShellExecute = false,
                RedirectStandardError = true,
                RedirectStandardOutput = true,
                Arguments = string.Format(
                    "-y -framerate {0} -i \"frame_%04d.png\"{1} " +
                    "-c:v libx264 -pix_fmt yuv420p -crf 18 -r {0}{2}{3} \"{4}\"",
                    fps, audioInput, frameLimit, shortest, outMp4),
            };
            try
            {
                var p = Process.Start(psi);
                log = p.StandardError.ReadToEnd();
                p.WaitForExit(600000);
                return p.ExitCode == 0 && File.Exists(outMp4) ? outMp4 : null;
            }
            catch (Exception e)
            {
                log = e.Message;
                return null;
            }
        }

        public static string FindFfmpeg()
        {
            var path = Environment.GetEnvironmentVariable("PATH");
            if (!string.IsNullOrEmpty(path))
                foreach (var d in path.Split(';'))
                {
                    try
                    {
                        var p = Path.Combine(d.Trim(), "ffmpeg.exe");
                        if (File.Exists(p)) return p;
                    }
                    catch { }
                }
            foreach (var c in new[]
            {
                @"C:\ProgramData\chocolatey\bin\ffmpeg.exe",
                @"C:\ProgramData\chocolatey\lib\ffmpeg\tools\ffmpeg\bin\ffmpeg.exe",
                @"C:\Program Files\ffmpeg\bin\ffmpeg.exe",
            })
                if (File.Exists(c)) return c;
            return null;
        }
    }
}
