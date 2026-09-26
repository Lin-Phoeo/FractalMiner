// EndfieldMmdStudio.cs — MMD 一体化工作台（唯一入口：播放 + 出片）。
// 编辑器内实时播放 VMD（场景/游戏视图可见），并可离线批渲染出 MP4。
// 播放核心复用 Mmd/ 共享库（MmdPlayer/MmdCameraDriver/MmdFace），帧级保存与
// ffmpeg 合成复用 EndfieldVmdBatchRender —— 面板预览与成片所见即所得。
// 菜单: Endfield/MMD Studio
using System;
using System.Collections;
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
    public class EndfieldMmdStudio : EditorWindow
    {
        const string ScenePath = "Assets/Scenes/Typhoeus_OfficialFrame_Recovered.unity";
        const string CharRootName = "chr_0034_typhoea_rebuilt";

        // ---- 状态 ----
        Transform charRoot;
        Camera cam;
        MmdPlayer player;
        readonly MmdCameraDriver camDriver = new MmdCameraDriver();

        // 最近一次载入的文件组合（会话内存）
        string lastMotionPath = "";
        string lastCameraPath = "";
        string lastAudioPath = "";

        // ---- 播放参数 ----
        bool playing;
        double lastTime;
        float time;                     // 秒（VMD 30fps 域）
        float duration => player != null && player.clip != null ? (float)player.clip.Duration : 0f;
        float scale = 0.08f;
        bool inPlace = true;
        float height;
        bool camDrive;                  // 镜头驱动开关
        bool loop = true;
        int outFps = 30;
        VmdIkMode ikMode = VmdIkMode.FollowMotion;
        // 分部位幅度（Poser 语义：0=回基准,1=原样,2=夸张;最终=整体×部位）
        float amp = 1f, ampArms = 1f, ampLegs = 1f, ampHead = 1f;
        bool showAmp;
        string info = "打开动作 VMD 开始。播放/镜头/出片都在这一个面板。";
        string status = "";
        Vector2 scroll;

        [MenuItem("Endfield/MMD Studio")]
        static void Open()
        {
            var w = GetWindow<EndfieldMmdStudio>("MMD Studio");
            w.minSize = new Vector2(460, 560);
        }

        void OnEnable()
        {
            EditorApplication.update += Tick;
            EditorApplication.update += StepRoutine;
        }

        void OnDisable()
        {
            playing = false;
            if (camDrive) { camDrive = false; camDriver.Restore(); }
            EditorApplication.update -= Tick;
            EditorApplication.update -= StepRoutine;
        }

        // ================= 编辑器内实时播放 =================
        void Tick()
        {
            if (!playing || player == null || charRoot == null) return;
            var now = EditorApplication.timeSinceStartup;
            time += (float)(now - lastTime);
            lastTime = now;
            if (time > duration)
            {
                if (loop) time = 0f;
                else { time = duration; playing = false; }
            }
            ApplyAt(time);
            Repaint();
        }

        void ApplyAt(float t)
        {
            if (player == null || charRoot == null) return;
            player.Reset();
            player.ApplyFrame(t, scale, inPlace, height, ikMode, amp, ampArms, ampLegs, ampHead);
            if (camDrive && camDriver.HasKeys)
                camDriver.Apply(t, scale, charRoot, player.bindRootWorld);
            SceneView.RepaintAll();
        }

        // ================= 载入 =================
        // 初始化人物模型（MMD 载入标准第一步）：确认重建角色在场景——不在就开官方基线场景，
        // 然后复位 M5 枢轴/捕获光照/官方后期/自阴影，并把残留骨骼姿态清回绑定。
        // 返回 false = 初始化失败（角色缺失），info 已带原因。
        bool InitCharacter()
        {
            try
            {
                EnsureScene(true);            // 强制重开基线场景 = 干净绑定姿态（校准标准前提）
                player = null;               // 旧播放器绑的 Transform 已随旧场景销毁
                lastMotionPath = "";         // 动作也需重载（重新校准）
                playing = false; time = 0;
                if (camDrive) { camDrive = false; camDriver.Restore(); }
                info = "人物已初始化: chr_0034_typhoea_rebuilt + M5 枢轴 + 捕获光照 + 官方后期 + 自阴影\n" +
                       "下一步: 打开动作 VMD（校准自动完成，成功与否看信息行）";
                ApplyAt(0);
                Repaint();
                return true;
            }
            catch (Exception e)
            {
                info = "初始化失败: " + e.Message;
                Repaint();
                return false;
            }
        }

        void LoadMotion(string path)
        {
            try
            {
                // 强制重开基线场景：FromUnity 按当前骨态建 rest，
                // 脏姿态（上次播放/Studio 遗留）会让 T-pose 校准失败——干净绑定是校准前提
                EnsureScene(true);
                player = null;   // 旧播放器引用的 Transform 已随旧场景销毁
                camDriver.target = cam;   // 旧相机句柄随场景更替刷新
                var clip = Vmd.ReadFile(path);
                player = MmdPlayer.Load(clip, charRoot);
                scale = player.suggestedScale;
                camDriver.UseMotionClip(clip);
                if (camDriver.target == null) camDriver.target = cam;
                lastMotionPath = path;
                // 同目录常见配套文件自动带出（未手动指定过镜头时）
                string dir = Path.GetDirectoryName(path);
                string camGuess = Path.Combine(dir, "Camera.vmd");
                if (File.Exists(camGuess) && string.IsNullOrEmpty(lastCameraPath))
                    LoadCamera(camGuess, true);
                time = 0; playing = false;
                info = Path.GetFileName(path) + "\n" + player.loadInfo +
                       "\n表情: " + MmdFace.Describe(charRoot) +
                       (camDriver.HasKeys ? "\n" + camDriver.info : "");
                ApplyAt(0);
            }
            catch (Exception e) { info = "载入失败: " + e.Message; }
            Repaint();
        }

        void LoadCamera(string path, bool auto = false)
        {
            try
            {
                EnsureScene(true);   // 镜头驱动也贴干净场景（相机句柄随场景更替刷新）
                camDriver.target = cam;
                if (camDriver.target == null) camDriver.target = cam;
                if (camDrive) camDriver.Restore();
                camDriver.LoadFile(path);
                lastCameraPath = path;
                camDrive = camDriver.HasKeys;
                if (camDrive) camDriver.CaptureRestore();
                if (!auto) info = Path.GetFileName(path) + " → " + camDriver.info;
                ApplyAt(time);
            }
            catch (Exception e) { info = "镜头载入失败: " + e.Message; }
            Repaint();
        }

        void PickAudio()
        {
            string p = EditorUtility.OpenFilePanel("选择音频（wav/mp3）", "", "wav,mp3");
            if (!string.IsNullOrEmpty(p)) lastAudioPath = p;
        }

        // ================= 观察工具 =================
        void AlignSceneViewToCamera()
        {
            var c = camDriver.target != null ? camDriver.target : cam;
            if (c == null) return;
            var sv = SceneView.lastActiveSceneView;
            if (sv == null) return;
            sv.Frame(new Bounds(c.transform.position + c.transform.forward * 2f, Vector3.one * 1.5f), false);
            sv.LookAt(c.transform.position + c.transform.forward * Mathf.Max(1f, 5f * camDriver.distanceScale), c.transform.rotation, 0f);
            sv.Repaint();
        }

        // ================= 场景引导（与批渲染器同参数） =================
        // forceFreshScene: 放弃当前场景（丢弃脏骨态/枢轴改动），重开官方基线场景。
        void EnsureScene(bool forceFreshScene = false)
        {
            if (!forceFreshScene && charRoot != null && cam != null) return;
            charRoot = null;
            if (forceFreshScene)
            {
                // 找当前场景里的角色（可能有脏姿态）；强制重开基线场景获得干净绑定
                EditorSceneManager.OpenScene(ScenePath, OpenSceneMode.Single);
                foreach (var go in EditorSceneManager.GetActiveScene().GetRootGameObjects())
                {
                    var hit = Find(go.transform, CharRootName);
                    if (hit != null) { charRoot = hit; break; }
                }
            }
            else
            {
                foreach (var go in EditorSceneManager.GetActiveScene().GetRootGameObjects())
                {
                    var hit = Find(go.transform, CharRootName);
                    if (hit != null) { charRoot = hit; break; }
                }
            }
            if (charRoot == null)
            {
                var scene = EditorSceneManager.OpenScene(ScenePath, OpenSceneMode.Single);
                foreach (var go in scene.GetRootGameObjects())
                {
                    var hit = Find(go.transform, CharRootName);
                    if (hit != null) { charRoot = hit; break; }
                }
            }
            if (charRoot == null) throw new InvalidOperationException(
                "找不到角色 " + CharRootName);

            var pelvis = Find(charRoot, "Bip001_Pelvis");
            if (pelvis != null)
            {
                var armature = pelvis;
                while (armature.parent != null &&
                       (armature.parent.name == "Bip001" || armature.parent.name == "Root"))
                    armature = armature.parent;
                (armature.parent != null ? armature.parent : armature).localRotation =
                    Quaternion.Euler(0f, 45.5f, 0f) * Quaternion.Euler(-90f, 0f, 0f);
            }

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
            if (!EndfieldCapturedPipelineActivation.IsActivated)
                EndfieldCapturedPipelineActivation.Activate();
            var caster = charRoot.GetComponent<EndfieldCharacterShadowCaster>();
            if (caster == null) caster = charRoot.gameObject.AddComponent<EndfieldCharacterShadowCaster>();
            caster.slot = 0;
            EndfieldCharacterShadowCaster.Refresh();

            cam = Camera.main;
            if (cam == null) throw new InvalidOperationException("场景没有 Main Camera");
        }

        static Transform Find(Transform root, string name)
        {
            if (root == null) return null;
            if (root.name == name) return root;
            foreach (Transform c in root)
            {
                var hit = Find(c, name);
                if (hit != null) return hit;
            }
            return null;
        }

        // ================= UI =================
        void OnGUI()
        {
            scroll = GUILayout.BeginScrollView(scroll);
            GUILayout.Label("MMD 工作台（播放 + 出片）", EditorStyles.boldLabel);
            EditorGUILayout.HelpBox(info, MessageType.None);

            // ---- 文件 ----
            using (new EditorGUILayout.HorizontalScope())
            {
                if (GUILayout.Button("① 初始化人物模型", GUILayout.Height(26)))
                    InitCharacter();
                if (GUILayout.Button("② 打开动作 VMD...", GUILayout.Height(26)))
                {
                    string p = EditorUtility.OpenFilePanel("动作 VMD", "", "vmd");
                    if (!string.IsNullOrEmpty(p)) LoadMotion(p);
                }
            }
            if (GUILayout.Button("重载动作（保持镜头/参数）", GUILayout.Height(20)) &&
                !string.IsNullOrEmpty(lastMotionPath) && File.Exists(lastMotionPath))
                LoadMotion(lastMotionPath);
            using (new EditorGUILayout.HorizontalScope())
            {
                if (GUILayout.Button("镜头 VMD...", GUILayout.Width(110)))
                {
                    string p = EditorUtility.OpenFilePanel("镜头 VMD（如 Camera.vmd）", "", "vmd");
                    if (!string.IsNullOrEmpty(p)) LoadCamera(p);
                }
                if (GUILayout.Button("音频: " + (string.IsNullOrEmpty(lastAudioPath) ? "无" : Path.GetFileName(lastAudioPath)), GUILayout.Width(220)))
                    PickAudio();
            }

            GUILayout.Space(6);

            // ---- 播放 ----
            using (new EditorGUI.DisabledScope(player == null))
            {
                using (new EditorGUILayout.HorizontalScope())
                {
                    if (GUILayout.Button(playing ? "|| 暂停" : "> 播放", GUILayout.Height(28)))
                    {
                        playing = !playing;
                        lastTime = EditorApplication.timeSinceStartup;
                        if (!playing) ApplyAt(time);
                    }
                    if (GUILayout.Button("|< 重置", GUILayout.Width(64))) { time = 0; ApplyAt(0); }
                    if (GUILayout.Button("+1帧", GUILayout.Width(58)))
                    { playing = false; time = Mathf.Min(time + 1f / 30f, duration); ApplyAt(time); }
                    loop = GUILayout.Toggle(loop, "循环", GUILayout.Width(56));
                }
                using (new EditorGUILayout.HorizontalScope())
                {
                    GUILayout.Label(time.ToString("F2") + "s / " + duration.ToString("F1") + "s", GUILayout.Width(110));
                    float nt = GUILayout.HorizontalSlider(time, 0f, Mathf.Max(0.01f, duration));
                    if (Mathf.Abs(nt - time) > 1e-4f) { playing = false; time = nt; ApplyAt(time); }
                }
            }

            GUILayout.Space(6);

            // ---- 参数 ----
            if (player != null)
            {
                scale = EditorGUILayout.Slider("位移比例", scale, 0f, 0.3f);
                inPlace = EditorGUILayout.Toggle("原地播放（锁水平位移）", inPlace);
                height = EditorGUILayout.Slider("高度修正", height, -1f, 1f);
                if (GUILayout.Button("重校准 T-pose", GUILayout.Width(110)))
                {
                    bool ok = player.Recalibrate();
                    info += "\n重校准 " + (ok ? "成功" : "失败");
                    ApplyAt(time);
                }

                GUILayout.Space(4);
                // ---- 适配区（Poser 语义：调这些救"腿僵/夸张/不像MMD"） ----
                ikMode = (VmdIkMode)EditorGUILayout.EnumPopup("动作 IK", ikMode);
                if (ikMode != VmdIkMode.FollowMotion && Event.current.type == EventType.Layout)
                    ApplyAt(time);
                showAmp = EditorGUILayout.Foldout(showAmp, "动作幅度（分部位）");
                if (showAmp)
                {
                    amp = EditorGUILayout.Slider("整体", amp, 0f, 2f);
                    ampArms = EditorGUILayout.Slider("手臂/手", ampArms, 0f, 2f);
                    ampLegs = EditorGUILayout.Slider("腿/脚", ampLegs, 0f, 2f);
                    ampHead = EditorGUILayout.Slider("头颈", ampHead, 0f, 2f);
                    if (GUILayout.Button("复位幅度", GUILayout.Width(70)))
                    { amp = ampArms = ampLegs = ampHead = 1f; ApplyAt(time); }
                }
                if (showAmp && Event.current.type == EventType.Layout) ApplyAt(time);

                // 镜头
                using (new EditorGUI.DisabledScope(!camDriver.HasKeys))
                {
                    bool nc = EditorGUILayout.Toggle("镜头驱动", camDrive);
                    if (nc != camDrive)
                    {
                        if (nc) camDriver.CaptureRestore(); else camDriver.Restore();
                        camDrive = nc;
                        ApplyAt(time);
                    }
                }
                if (camDriver.HasKeys && camDrive)
                {
                    camDriver.yaw = EditorGUILayout.Slider("机位偏航", camDriver.yaw, -180f, 360f);
                    camDriver.distanceScale = EditorGUILayout.Slider("距离缩放", camDriver.distanceScale, 0.1f, 3f);
                    camDriver.fovOffset = EditorGUILayout.Slider("FOV 偏移", camDriver.fovOffset, -20f, 20f);
                    camDriver.follow = EditorGUILayout.Toggle("机位跟随", camDriver.follow);
                    if (Event.current.type == EventType.Layout) ApplyAt(time);
                }

                // ---- 观察工具：进入镜头视角 ----
                GUILayout.Space(4);
                using (new EditorGUILayout.HorizontalScope())
                {
                    if (GUILayout.Button("Scene 视图 = 镜头视角", GUILayout.Width(150)))
                        AlignSceneViewToCamera();
                    if (GUILayout.Button("选中相机", GUILayout.Width(80)))
                        Selection.activeObject = camDriver.target != null ? camDriver.target.gameObject : null;
                }
                EditorGUILayout.HelpBox(
                    "进入镜头视角后 Scene 视图就是成片构图。Inspector 相机上勾 Camera Preview 也有小窗预览；" +
                    "Game 视图（顶部标签）默认就是主相机画面。", MessageType.None);
            }

            GUILayout.Space(8);

            // ---- 出片 ----
            GUILayout.Label("出片（离线渲染，所见即所得）", EditorStyles.boldLabel);
            if (player == null)
                EditorGUILayout.HelpBox("载入动作后可渲染。", MessageType.Info);
            else
            {
                outFps = EditorGUILayout.IntSlider("输出帧率", outFps, 24, 60);
                using (new EditorGUILayout.HorizontalScope())
                {
                    if (GUILayout.Button("渲染整段 -> MP4", GUILayout.Height(30)))
                        StartCoroutine(RunRender(0));
                    if (GUILayout.Button("试拍 5 帧", GUILayout.Width(90)))
                        StartCoroutine(RunRender(5));
                    if (GUILayout.Button("渲当前帧", GUILayout.Width(80)))
                        StartCoroutine(RunRender(1, time));
                }
                if (!string.IsNullOrEmpty(status))
                    GUILayout.Label(status, EditorStyles.wordWrappedMiniLabel);
            }

            GUILayout.EndScrollView();
        }

        // ================= 批渲染（EditorApplication.update 分帧驱动） =================
        IEnumerator RunRender(int frameCount, float atTime = -1f)
        {
            if (player == null || charRoot == null) yield break;
            EnsureScene();
            playing = false;

            string dir = Path.GetFullPath(Path.Combine(Application.dataPath, "..",
                "Validation", "mmd-" + Path.GetFileNameWithoutExtension(
                    string.IsNullOrEmpty(lastMotionPath) ? "clip" : lastMotionPath)));
            Directory.CreateDirectory(dir);

            int count;
            float t0;
            if (frameCount == 1 && atTime >= 0f) { count = 1; t0 = atTime; }
            else if (frameCount > 0) { count = frameCount; t0 = 0f; }
            else { count = (int)player.clip.lastFrame + 1; t0 = 0f; }

            status = string.Format("渲染 {0} 帧 → {1}", count, dir);
            Repaint();
            yield return null;

            var sw = Stopwatch.StartNew();
            const int w = 1920, h = 1080;
            for (int k = 0; k < count; k++)
            {
                float t = t0 + k / 30f;   // VMD 30fps 帧域
                player.Reset();
                player.ApplyFrame(t, scale, inPlace, height, ikMode, amp, ampArms, ampLegs, ampHead);
                if (camDrive && camDriver.HasKeys)
                    camDriver.Apply(t, scale, charRoot, player.bindRootWorld);
                EndfieldVmdBatchRender.SaveFrame(cam, Path.Combine(dir,
                    "frame_" + k.ToString("D4") + ".png"), w, h, true);

                if (k % 10 == 0)
                {
                    status = string.Format("渲染中 {0}/{1}  ({2:F1}s)", k + 1, count, sw.Elapsed.TotalSeconds);
                    Repaint();
                }
                yield return null;   // 让出编辑器响应
            }
            sw.Stop();

            string mp4 = null;
            if (!string.IsNullOrEmpty(lastAudioPath) && File.Exists(lastAudioPath) &&
                EndfieldVmdBatchRender.FindFfmpeg() != null)
            {
                status += "\n合成 MP4（ffmpeg）...";
                Repaint();
                yield return null;
                mp4 = EndfieldVmdBatchRender.Mux(dir, lastAudioPath, outFps, w, h, out string muxLog);
            }
            status = (mp4 != null ? "完成: " + mp4 : status + "\n（未合成 MP4：无音频或 ffmpeg）")
                     + string.Format("\n渲染 {0} 帧 耗时 {1:F1}s", count, sw.Elapsed.TotalSeconds);
            if (mp4 != null) EditorUtility.RevealInFinder(mp4);
            Repaint();
        }

        // ---- 迭代器驱动（EditorWindow 无协程，用 update 手动泵） ----
        IEnumerator _routine;
        void StartCoroutine(IEnumerator routine) { _routine = routine; }
        void StepRoutine()
        {
            if (_routine == null) return;
            bool done;
            try { done = !_routine.MoveNext(); }
            catch (Exception e)
            {
                status = "渲染异常: " + e.Message;
                Debug.LogException(e);
                done = true;
            }
            if (done) _routine = null;
        }
    }
}
