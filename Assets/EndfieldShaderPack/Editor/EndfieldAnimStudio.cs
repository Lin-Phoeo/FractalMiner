using System;
using System.Collections.Generic;
using System.IO;
using UnityEditor;
using UnityEditor.SceneManagement;
using UnityEngine;
using UnityEngine.Rendering;

namespace EndfieldShaderPack.EditorTools
{
    /// <summary>
    /// Endfield/Anim Studio：交互式动画验证窗口（协作模式，替代 batchmode）。
    /// 用途：打开场景 → 选 clip → 播放/单帧/拖轴 → 三条探针实时显示
    ///   ① IK 目标世界位（曲线驱动，必须变化）
    ///   ② 解析 IK 后手/脚末端世界位（求解输出，必须跟随①）
    ///   ③ 末端误差 |②-①|（应 <1cm；若恒为绑定距离说明求解未生效）
    /// Scene 面板直接看模型动作，Mesh/骨骼开关用于肉眼判断"动了没有"。
    /// </summary>
    public class EndfieldAnimStudio : EditorWindow
    {
        const string ScenePath = "Assets/Scenes/Typhoeus_OfficialFrame_Recovered.unity";
        const string DecodedDir = "Assets/Typhoeus/AnimationsDecoded";

        AnimationClip clip;
        string clipName = "A_actor_typhoea_battle_attack_01";
        string[] clipNames;
        Transform charRoot;
        float time;
        bool playing;
        double lastTime;
        bool showBones = true;

        // 解析 IK 链
        class Chain
        {
            public string name;
            public Transform root, mid, tip, target, poleHint;
            public float l1, l2;
            public Vector3 bindMidDir, bindTipDir, bendNormal;
            public Quaternion tipRotOffset = Quaternion.identity;
            public bool captured;
            public Vector3 lastTipPos, lastTargetPos;
            public float lastError;
            public bool solved;
        }
        readonly List<Chain> chains = new List<Chain>();

        Vector2 scroll;
        string status = "";
        bool pipelineActivated;
        EndfieldCharacterShadowCaster shadowCaster;

        [MenuItem("Endfield/Anim Studio")]
        public static void Open() => GetWindow<EndfieldAnimStudio>("Anim Studio");

        void OnEnable()
        {
            EditorApplication.update += Tick;
            RefreshClipList();
        }

        void OnDisable()
        {
            EditorApplication.update -= Tick;
            Teardown();
        }

        void RefreshClipList()
        {
            var dir = Path.Combine(Directory.GetParent(Application.dataPath).FullName,
                DecodedDir.Replace("Assets/", "Assets" + Path.DirectorySeparatorChar));
            var guids = AssetDatabase.FindAssets("t:AnimationClip", new[] { DecodedDir });
            var names = new List<string>();
            foreach (var g in guids)
            {
                var p = AssetDatabase.GUIDToAssetPath(g);
                names.Add(Path.GetFileNameWithoutExtension(p));
            }
            names.Sort();
            clipNames = names.ToArray();
        }

        void Setup()
        {
            Teardown();
            var scene = EditorSceneManager.OpenScene(ScenePath, OpenSceneMode.Single);
            foreach (var root in scene.GetRootGameObjects())
                if (root.name == "chr_0034_typhoea_rebuilt") { charRoot = root.transform; break; }
            if (charRoot == null) { status = "chr root missing"; return; }

            clip = AssetDatabase.LoadAssetAtPath<AnimationClip>(DecodedDir + "/" + clipName + ".anim");
            if (clip == null) { status = "clip not found"; return; }

            chains.Clear();
            foreach (var side in new[] { "R", "L" })
            {
                var arm = Build("Arm" + side,
                    "Bip001_" + side + "_UpperArm", "Bip001_" + side + "_Forearm", "Bip001_" + side + "_Hand",
                    "IK_Hand_" + side + "_001", null);
                if (arm != null) chains.Add(arm);
                var leg = Build("Leg" + side,
                    "Bip001_" + side + "_Thigh", "Bip001_" + side + "_Calf", "Bip001_" + side + "_Foot",
                    "IK_Foot_" + side + "_001", "IK_Knee_" + side + "_001");
                if (leg != null) chains.Add(leg);
            }

            // M5 pivot（与 v2 相同）
            var pelvis = Find(charRoot, "Bip001_Pelvis");
            var armature = pelvis;
            while (armature.parent != null && (armature.parent.name == "Bip001" || armature.parent.name == "Root"))
                armature = armature.parent;
            (armature.parent != null ? armature.parent : armature).localRotation =
                Quaternion.Euler(0f, 45.5f, 0f) * Quaternion.Euler(-90f, 0f, 0f);

            // 相机
            var cam = Camera.main;
            if (cam != null)
            {
                cam.transform.SetPositionAndRotation(
                    new Vector3(0f, 0.7799988f, 2.9599915f),
                    new Quaternion(-1.7726111e-10f, 0.9999918f, 0.0040552616f, -4.371103e-8f));
            }

            // 光照（与 v2 相同）
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

            pipelineActivated = EndfieldCapturedPipelineActivation.IsActivated;
            if (!pipelineActivated) EndfieldCapturedPipelineActivation.Activate();
            shadowCaster = charRoot.gameObject.AddComponent<EndfieldCharacterShadowCaster>();
            shadowCaster.slot = 0;
            EndfieldCharacterShadowCaster.Refresh();

            time = 0f;
            SampleAndSolve();
            status = "ready: " + chains.Count + " chains, clip " + clip.length.ToString("F2") + "s";
            Repaint();
        }

        void Teardown()
        {
            if (shadowCaster != null)
            {
                DestroyImmediate(shadowCaster);
                shadowCaster = null;
                EndfieldCharacterShadowCaster.Refresh();
            }
            if (!pipelineActivated && EndfieldCapturedPipelineActivation.IsActivated)
            {
                EndfieldCapturedPipelineActivation.Restore();
            }
            pipelineActivated = false;
            chains.Clear();
            charRoot = null;
            clip = null;
        }

        Chain Build(string name, string rootName, string midName, string tipName,
            string targetName, string poleName)
        {
            var root = Find(charRoot, rootName);
            var mid = Find(charRoot, midName);
            var tip = Find(charRoot, tipName);
            if (root == null || mid == null || tip == null) return null;
            return new Chain
            {
                name = name,
                root = root, mid = mid, tip = tip,
                target = Find(charRoot, targetName),
                poleHint = poleName != null ? Find(charRoot, poleName) : null
            };
        }

        void Tick()
        {
            if (!playing || clip == null || charRoot == null) return;
            var now = EditorApplication.timeSinceStartup;
            float dt = (float)(now - lastTime);
            lastTime = now;
            time += dt;
            if (time > clip.length) time = 0f;
            SampleAndSolve();
            Repaint();
        }

        void SampleAndSolve()
        {
            if (clip == null || charRoot == null) return;
            clip.SampleAnimation(charRoot.gameObject, Mathf.Min(time, clip.length));
            foreach (var c in chains) Solve(c);
            SceneView.RepaintAll();
        }

        static Transform Find(Transform root, string name)
        {
            if (root == null) return null;
            if (root.name == name) return root;
            foreach (Transform child in root)
            {
                var hit = Find(child, name);
                if (hit != null) return hit;
            }
            return null;
        }

        static void Solve(Chain c)
        {
            if (c.target == null) { c.solved = false; c.lastError = -1f; return; }
            if (!c.captured)
            {
                c.l1 = Vector3.Distance(c.root.position, c.mid.position);
                c.l2 = Vector3.Distance(c.mid.position, c.tip.position);
                c.bindMidDir = (c.mid.position - c.root.position).normalized;
                c.bindTipDir = (c.tip.position - c.root.position).normalized;
                c.bendNormal = Vector3.Cross(c.bindTipDir, c.bindMidDir).normalized;
                c.tipRotOffset = Quaternion.Inverse(c.target.rotation) * c.tip.rotation;
                c.captured = true;
            }
            Vector3 rootPos = c.root.position;
            Vector3 targetPos = c.target.position;
            float reach = Vector3.Distance(rootPos, targetPos);
            float d = Mathf.Clamp(reach, Mathf.Abs(c.l1 - c.l2) + 1e-4f, c.l1 + c.l2 - 1e-4f);
            Vector3 dir = reach > 1e-5f ? (targetPos - rootPos) / reach : c.bindTipDir;

            Vector3 n = c.bendNormal;
            if (c.poleHint != null)
            {
                var ph = c.poleHint.position - rootPos;
                ph -= dir * Vector3.Dot(ph, dir);
                if (ph.sqrMagnitude > 1e-8f) n = ph.normalized;
            }
            else
            {
                n -= dir * Vector3.Dot(n, dir);
                if (n.sqrMagnitude > 1e-8f) n = n.normalized;
                else n = c.bendNormal;
            }
            float along = (c.l1 * c.l1 - c.l2 * c.l2 + d * d) / (2f * d);
            float h = Mathf.Sqrt(Mathf.Max(0f, c.l1 * c.l1 - along * along));
            Vector3 midPos = rootPos + dir * along + n * h;

            var midDirNow = (c.mid.position - rootPos).normalized;
            if (midDirNow.sqrMagnitude > 0.5f)
                c.root.rotation = Quaternion.FromToRotation(midDirNow, (midPos - rootPos).normalized) * c.root.rotation;
            var tipDirNow = (c.tip.position - c.mid.position).normalized;
            var tipDirWant = (targetPos - c.mid.position).normalized;
            if (tipDirNow.sqrMagnitude > 0.5f && tipDirWant.sqrMagnitude > 0.5f)
                c.mid.rotation = Quaternion.FromToRotation(tipDirNow, tipDirWant) * c.mid.rotation;
            c.tip.rotation = c.target.rotation * c.tipRotOffset;

            c.lastTargetPos = targetPos;
            c.lastTipPos = c.tip.position;
            c.lastError = Vector3.Distance(c.lastTipPos, targetPos);
            c.solved = true;
        }

        void OnGUI()
        {
            scroll = GUILayout.BeginScrollView(scroll);

            // clip 选择
            GUILayout.Label("Clip", EditorStyles.boldLabel);
            if (clipNames != null && clipNames.Length > 0)
            {
                int idx = Mathf.Max(0, Array.IndexOf(clipNames, clipName));
                int nsel = EditorGUILayout.Popup(idx, clipNames);
                if (nsel != idx) { clipName = clipNames[nsel]; Setup(); }
            }

            using (new EditorGUILayout.HorizontalScope())
            {
                if (GUILayout.Button(charRoot == null ? "Load Scene" : "Reload", GUILayout.Width(90)))
                    Setup();
                using (new EditorGUI.DisabledScope(clip == null))
                {
                    if (GUILayout.Button(playing ? "Pause" : "Play", GUILayout.Width(70)))
                    {
                        playing = !playing;
                        lastTime = EditorApplication.timeSinceStartup;
                    }
                    if (GUILayout.Button("Frame+1", GUILayout.Width(70)))
                    { playing = false; time = Mathf.Min(time + 1f / 60f, clip != null ? clip.length : time); SampleAndSolve(); }
                    if (GUILayout.Button("<<", GUILayout.Width(30)))
                    { time = 0; SampleAndSolve(); }
                }
            }

            using (new EditorGUI.DisabledScope(clip == null))
            {
                float nt = EditorGUILayout.Slider("Time", time, 0f, clip != null ? clip.length : 1f);
                if (!Mathf.Approximately(nt, time)) { time = nt; SampleAndSolve(); }
                showBones = EditorGUILayout.Toggle("Draw IK helpers (Scene 视图)", showBones);
            }

            GUILayout.Space(8);
            GUILayout.Label("Probes (realtime)", EditorStyles.boldLabel);
            foreach (var c in chains)
            {
                string line = c.target == null
                    ? string.Format("{0}: target bone MISSING", c.name)
                    : string.Format("{0}: tgt({1:F3},{2:F3},{3:F3}) tip({4:F3},{5:F3},{6:F3}) err={7:F4}m",
                        c.name, c.lastTargetPos.x, c.lastTargetPos.y, c.lastTargetPos.z,
                        c.lastTipPos.x, c.lastTipPos.y, c.lastTipPos.z, c.lastError);
                var style = new GUIStyle(EditorStyles.miniLabel);
                style.fontStyle = FontStyle.Bold;
                GUILayout.Label(line, style);
            }
            GUILayout.Space(4);
            GUILayout.Label(status, EditorStyles.miniLabel);
            GUILayout.Space(8);
            GUILayout.Label("判读：播放时 tgt 数值必须变化（曲线在动）；err 应 <0.01m。", EditorStyles.miniLabel);
            GUILayout.Label("若 tgt 变化而 tip 不跟随 → IK 求解问题；若 tgt 也不变 → Sample 问题。", EditorStyles.miniLabel);

            GUILayout.EndScrollView();
        }

        void OnSceneGUI()
        {
            if (!showBones || charRoot == null) return;
            foreach (var c in chains)
            {
                if (c.target == null) continue;
                Handles.color = Color.yellow;
                Handles.DrawLine(c.root.position, c.mid.position);
                Handles.DrawLine(c.mid.position, c.tip.position);
                Handles.color = Color.red;
                Handles.SphereHandleCap(0, c.target.position, Quaternion.identity, 0.04f, EventType.Repaint);
                Handles.color = Color.green;
                Handles.SphereHandleCap(0, c.tip.position, Quaternion.identity, 0.03f, EventType.Repaint);
            }
        }
    }
}
