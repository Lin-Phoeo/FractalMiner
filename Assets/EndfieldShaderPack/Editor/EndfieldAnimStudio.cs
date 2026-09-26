using System;
using System.Collections.Generic;
using System.IO;
using UnityEditor;
using UnityEditor.SceneManagement;
using UnityEngine;
using UnityEngine.Rendering;
using EndfieldShaderPack.EditorTools.Mmd;

namespace EndfieldShaderPack.EditorTools
{
    /// <summary>
    /// Endfield/Anim Studio：交互式动画验证窗口（协作模式，替代 batchmode）。
    /// 用途：打开场景 → 选 clip → 播放/单帧/拖轴 → 三条探针实时显示
    ///   ① IK 目标世界位（曲线驱动，必须变化）
    ///   ② 解析 IK 后手/脚末端世界位（求解输出，必须跟随①）
    ///   ③ 末端误差 |②-①|（应 <1cm；若恒为绑定距离说明求解未生效）
    /// v2 新增 RootMotion 驱动：battle clips 的躯干/四肢主骨不在 ACL Transform 轨里，
    /// 它们的运行时驱动源 = RootMotionBufferData 的 4 根"根骨"
    /// （Root=整体位移, IK_Root=转向+前冲, 另两根=手臂摆动源，映射待验证）。
    /// RM 数据从 Assets/Typhoeus/rootmotion-<clip>.json 读取（由 EndfieldUnpacker 导出），
    /// 每帧直接覆盖 [tx,ty,tz,qx,qy,qz,qw]（游戏 Z-up 坐标，经 RmZupToUnity 转换）。
    /// 探针区显示 RM 各根骨位移，肉眼判断躯干是否跟随。
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

        // ---- RootMotion 驱动 ----
        class RmData
        {
            public float sampleRate = 60f;
            public int numBones;
            public int stride;             // numBones * 7
            public float[] flat;           // numSamples * stride
            public int FrameCount => (stride > 0 && flat != null) ? flat.Length / stride : 0;

            public float Get(int frame, int idx) => flat[frame * stride + idx];
        }
        RmData rm;
        bool useRm = true;
        string rmInfo = "no RM data";

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

            LoadRootMotion(clipName);

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
            EnsureRmVisualizers();

            time = 0f;
            SampleAndSolve();
            status = "ready: " + chains.Count + " chains, clip " + clip.length.ToString("F2") + "s"
                + (rm != null ? " + RM " + rm.numBones + " bones" : " (no RM)");
            Repaint();
        }

        // ---- Clavicle 跟随（v9）：锁骨朝 IK 目标限幅偏转，扩大手臂可达域 ----
        class ClavFollow
        {
            public Transform clav, upperArm, hand, ikTarget;
            public Quaternion bindLocalRot;
            public Vector3 bindDirLocal;   // 绑定时"肩→手"方向（clav.parent 局部空间）
        }
        readonly List<ClavFollow> clavs = new List<ClavFollow>();
        bool clavFollow = false;  // 默认关：待骨架快照验证坐标系后再开
        bool clavCaptured;

        void CaptureClavicles()
        {
            clavs.Clear();
            foreach (var side in new[] { "R", "L" })
            {
                var c = Find(charRoot, "Bip001_" + side + "_Clavicle");
                var ua = Find(charRoot, "Bip001_" + side + "_UpperArm");
                var hd = Find(charRoot, "Bip001_" + side + "_Hand");
                var tg = Find(charRoot, "IK_Hand_" + side + "_001");
                if (c == null || ua == null || hd == null || tg == null) continue;
                clavs.Add(new ClavFollow
                {
                    clav = c, upperArm = ua, hand = hd, ikTarget = tg,
                    bindLocalRot = c.localRotation,
                    bindDirLocal = c.parent.InverseTransformDirection(
                        (hd.position - ua.position).normalized)
                });
            }
            clavCaptured = clavs.Count > 0;
        }

        void ApplyClavicleFollow()
        {
            if (!clavCaptured) return;
            foreach (var cf in clavs)
            {
                Vector3 shoulder = cf.upperArm.position;
                Vector3 d = cf.ikTarget.position - shoulder;
                if (d.sqrMagnitude < 1e-6f) continue;
                Vector3 curDirLocal = cf.clav.parent.InverseTransformDirection(d.normalized);
                Quaternion delta = Quaternion.FromToRotation(cf.bindDirLocal, curDirLocal);
                // 限幅 ±55°
                float ang; Vector3 axis;
                delta.ToAngleAxis(out ang, out axis);
                if (float.IsInfinity(axis.x) || float.IsNaN(axis.x)) continue;
                ang = Mathf.Clamp(ang * Mathf.Rad2Deg, -55f, 55f) * Mathf.Deg2Rad;
                delta = Quaternion.AngleAxis(ang, axis);
                cf.clav.localRotation = cf.bindLocalRot * delta;
            }
        }

        // RM 可视化球（bone1/2/3 的世界位）
        GameObject rmVis;
        readonly Transform[] rmVisNodes = new Transform[4];

        void EnsureRmVisualizers()
        {
            if (rmVis != null) return;
            rmVis = new GameObject("EndfieldRmVis");
            rmVis.hideFlags = HideFlags.HideAndDontSave;
            for (int b = 0; b < 4; b++)
            {
                var s = GameObject.CreatePrimitive(PrimitiveType.Sphere);
                s.name = "RmBone" + b;
                s.transform.localScale = Vector3.one * (b == 0 ? 0.12f : 0.08f);
                var col = s.GetComponent<Collider>();
                if (col != null) UnityEngine.Object.DestroyImmediate(col);
                var r = s.GetComponent<MeshRenderer>();
                r.sharedMaterial = AssetDatabase.GetBuiltinExtraResource<Material>("Default-Material.mat");
                s.transform.SetParent(rmVis.transform, false);
                rmVisNodes[b] = s.transform;
            }
        }

        void DestroyRmVisualizers()
        {
            if (rmVis != null) { DestroyImmediate(rmVis); rmVis = null; }
            for (int i = 0; i < 4; i++) rmVisNodes[i] = null;
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
            DestroyRmVisualizers();
            if (rmVis != null) { DestroyImmediate(rmVis); }
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
            if (mmdMode && mmdPlayer != null && mmdPlayer.captured)
            {
                // VMD 驱动：重置绑定 → 采样 retarget → 写骨骼（不走 SampleAnimation）
                mmdPlayer.Reset();
                mmdPlayer.ApplyFrame(time, mmdScale, mmdInPlace, mmdHeight);
                ApplyMmdCamera();
                SceneView.RepaintAll();
                return;
            }
            clip.SampleAnimation(charRoot.gameObject, Mathf.Min(time, clip.length));
            if (useRm && rm != null) { ApplyRootMotion(); UpdateRmVisualizers(); }
            if (!clavCaptured && rm != null) CaptureClavicles();
            if (clavFollow) ApplyClavicleFollow();
            foreach (var c in chains) Solve(c);
            ApplyMmdCamera(); // 镜头轨独立于骨骼驱动方式
            SceneView.RepaintAll();
        }

        void UpdateRmVisualizers()
        {
            if (rm == null || rm.FrameCount == 0) return;
            EnsureRmVisualizers();
            // 挂到 chr 根下：RM 值直接作为 chr 局部坐标（无需换算）
            if (rmVis.transform.parent != charRoot) rmVis.transform.SetParent(charRoot, false);
            int idx = Mathf.Clamp(Mathf.RoundToInt(time * rm.sampleRate), 0, rm.FrameCount - 1);
            for (int b = 0; b < 4; b++)
            {
                if (rmVisNodes[b] == null) continue;
                if (b >= rm.numBones) { rmVisNodes[b].gameObject.SetActive(false); continue; }
                rmVisNodes[b].gameObject.SetActive(true);
                int o = b * 7;
                rmVisNodes[b].localPosition = new Vector3(
                    rm.Get(idx, o), rm.Get(idx, o + 1), rm.Get(idx, o + 2));
                rmVisNodes[b].localRotation = new Quaternion(
                    rm.Get(idx, o + 3), rm.Get(idx, o + 4), rm.Get(idx, o + 5), rm.Get(idx, o + 6));
            }
        }

        // ---- RootMotion ----
        /// <summary>读 rootmotion-<clip>.json（EndfieldUnpacker 导出，游戏 Z-up 坐标）。
        /// 格式: {"sampleRate":60,"numBones":4,"numSamples":301,"stride":28,"framesFlat":[28*n floats]}
        /// 每帧 stride 个浮点，bone-major: [tx,ty,tz,qx,qy,qz,qw]。
        /// 注意：JsonUtility 不支持 List<float[]>，必须用扁平数组 framesFlat。</summary>
        void LoadRootMotion(string name)
        {
            rm = null;
            rmInfo = "no RM data";
            string path = "Assets/Typhoeus/rootmotion-" + name + ".json";
            var asset = AssetDatabase.LoadAssetAtPath<TextAsset>(path);
            if (asset == null) { rmInfo = "RM asset missing: " + path; return; }
            try
            {
                var data = JsonUtility.FromJson<RmJson>(asset.text);
                if (data == null || data.framesFlat == null || data.framesFlat.Length == 0)
                { rmInfo = "RM empty/parse fail: " + path; return; }
                int stride = data.stride > 0 ? data.stride : data.numBones * 7;
                if (stride <= 0 || data.framesFlat.Length % stride != 0)
                { rmInfo = "RM size mismatch: len=" + data.framesFlat.Length + " stride=" + stride; return; }
                var parsed = new RmData
                {
                    sampleRate = data.sampleRate > 0 ? data.sampleRate : 60f,
                    numBones = data.numBones,
                    stride = stride,
                    flat = data.framesFlat
                };
                rm = parsed;
                rmInfo = string.Format("RM loaded: {0} bones x {1} frames @ {2}Hz",
                    parsed.numBones, parsed.FrameCount, parsed.sampleRate);
            }
            catch (Exception e)
            {
                rmInfo = "RM parse error: " + e.Message;
            }
        }

        [Serializable]
        class RmJson
        {
            public float sampleRate;
            public int numBones;
            public int numSamples;
            public int stride;
            public float[] framesFlat;   // 全部帧的扁平数组 = numSamples * stride
        }

        static readonly string[] RmBoneGuess = { "Root", "IK_Root", "IK_Hand_L_001", "IK_Hand_R_001" };

        /// <summary>RM 驱动 v8（躯干跟随近似）。实测结论：RM 坐标 = chr 根局部（Unity Y-up），
        /// 无需换算。bone1 ≈ bone0 + 常量肩锚偏移（f300: bone0=(0,0,2.26), bone1=(-0.02,0.97,2.25)）。
        /// v8 策略：
        ///   1. bone0 → Root.localPosition（整体位移，用户实测正确）
        ///   2. bone1 相对起始帧的 delta（位移+旋转）→ 写 Bip001_Pelvis（躯干跟随近似）
        ///   3. bone2/3 不写 IK_Hand 节点——IK_Hand 的 transform 轨已是正确的模型空间目标，
        ///      覆盖它们会双重叠加（v7 乱摆未收敛的原因之一）。bone2/3 仅保留可视化球。
        /// 注意：IK_Root/IK_Hand 的 local 轨保持恒零=模型空间语义，解析 IK 直接用其世界位。</summary>
        void ApplyRootMotion()
        {
            int idx = Mathf.Clamp(Mathf.RoundToInt(time * rm.sampleRate), 0, rm.FrameCount - 1);
            // 1) 整体位移
            var rootBone = Find(charRoot, "Root");
            if (rootBone != null)
            {
                rootBone.localPosition = new Vector3(
                    rm.Get(idx, 0), rm.Get(idx, 1), rm.Get(idx, 2));
                rootBone.localRotation = new Quaternion(
                    rm.Get(idx, 3), rm.Get(idx, 4), rm.Get(idx, 5), rm.Get(idx, 6));
            }
            // 2) 躯干跟随：bone1 相对 f0 的 delta 加到 Pelvis
            if (rm.numBones > 1)
            {
                int o = 7;
                var p0 = new Vector3(rm.Get(0, o), rm.Get(0, o + 1), rm.Get(0, o + 2));
                var pN = new Vector3(rm.Get(idx, o), rm.Get(idx, o + 1), rm.Get(idx, o + 2));
                var q0 = new Quaternion(rm.Get(0, o + 3), rm.Get(0, o + 4), rm.Get(0, o + 5), rm.Get(0, o + 6));
                var qN = new Quaternion(rm.Get(idx, o + 3), rm.Get(idx, o + 4), rm.Get(idx, o + 5), rm.Get(idx, o + 6));
                var pelvis = Find(charRoot, "Bip001_Pelvis");
                if (pelvis != null)
                {
                    if (!pelvisRmInit)
                    {
                        pelvisBindPos = pelvis.localPosition;
                        pelvisBindRot = pelvis.localRotation;
                        pelvisRmInit = true;
                    }
                    pelvis.localPosition = pelvisBindPos + (pN - p0);
                    pelvis.localRotation = Quaternion.Inverse(q0) * qN * pelvisBindRot;
                }
            }
        }
        bool pelvisRmInit;
        Vector3 pelvisBindPos;
        Quaternion pelvisBindRot;

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

        /// <summary>导出当前帧全部骨骼位姿（世界+局部），用于离线精确分析坐标系语义。</summary>
        void DumpSkeleton()
        {
            if (charRoot == null) { status = "先 Load Scene"; Repaint(); return; }
            var sb = new System.Text.StringBuilder();
            sb.Append("{\"clip\":\"").Append(clipName).Append("\",\"time\":")
              .Append(time.ToString("R", System.Globalization.CultureInfo.InvariantCulture))
              .Append(",\"ikOn\":").Append(clavFollow ? "true" : "false")
              .Append(",\"rmOn\":").Append(useRm ? "true" : "false")
              .Append(",\"bones\":[");
            bool first = true;
            DumpRec(charRoot, charRoot.name, sb, ref first);
            sb.Append("]}");
            string dir = "Validation";
            if (!System.IO.Directory.Exists(dir)) System.IO.Directory.CreateDirectory(dir);
            string path = System.IO.Path.Combine(dir, "skeleton-snapshot.json");
            System.IO.File.WriteAllText(path, sb.ToString());
            status = "骨架快照已写入 " + path + "（" + time.ToString("F2") + "s）";
            Repaint();
        }

        void DumpRec(Transform t, string path, System.Text.StringBuilder sb, ref bool first)
        {
            if (!first) sb.Append(",");
            first = false;
            var p = t.position; var lp = t.localPosition;
            var r = t.rotation; var lr = t.localRotation;
            sb.Append("{\"path\":\"").Append(path).Append("\",")
              .Append("\"wp\":[")
              .Append(p.x.ToString("R", System.Globalization.CultureInfo.InvariantCulture)).Append(",")
              .Append(p.y.ToString("R", System.Globalization.CultureInfo.InvariantCulture)).Append(",")
              .Append(p.z.ToString("R", System.Globalization.CultureInfo.InvariantCulture)).Append("],")
              .Append("\"lp\":[")
              .Append(lp.x.ToString("R", System.Globalization.CultureInfo.InvariantCulture)).Append(",")
              .Append(lp.y.ToString("R", System.Globalization.CultureInfo.InvariantCulture)).Append(",")
              .Append(lp.z.ToString("R", System.Globalization.CultureInfo.InvariantCulture)).Append("],")
              .Append("\"lr\":[")
              .Append(lr.x.ToString("R", System.Globalization.CultureInfo.InvariantCulture)).Append(",")
              .Append(lr.y.ToString("R", System.Globalization.CultureInfo.InvariantCulture)).Append(",")
              .Append(lr.z.ToString("R", System.Globalization.CultureInfo.InvariantCulture)).Append(",")
              .Append(lr.w.ToString("R", System.Globalization.CultureInfo.InvariantCulture)).Append("],")
              .Append("\"wr\":[")
              .Append(r.x.ToString("R", System.Globalization.CultureInfo.InvariantCulture)).Append(",")
              .Append(r.y.ToString("R", System.Globalization.CultureInfo.InvariantCulture)).Append(",")
              .Append(r.z.ToString("R", System.Globalization.CultureInfo.InvariantCulture)).Append(",")
              .Append(r.w.ToString("R", System.Globalization.CultureInfo.InvariantCulture)).Append("]}");
            foreach (Transform c in t)
                DumpRec(c, path + "/" + c.name, sb, ref first);
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

        // ---- MMD 播放（共享核心 MmdPlayer + MmdCameraDriver）----
        MmdPlayer mmdPlayer;
        MmdCameraDriver mmdCamDriver = new MmdCameraDriver();
        string mmdInfo = "MMD: 未载入";
        bool mmdMode;                 // true = VMD 驱动；false = ACL clip 驱动
        float mmdScale = 0.08f;
        bool mmdInPlace = true;
        float mmdHeight = 0f;
        bool mmdCamDrive;

        void MmdLoadVmd(string path)
        {
            try
            {
                var clip = Vmd.ReadFile(path);
                mmdPlayer = MmdPlayer.Load(clip, charRoot);
                mmdInfo = mmdPlayer.loadInfo;
                mmdScale = mmdPlayer.suggestedScale;
                if (mmdCamDriver.target == null) mmdCamDriver.target = Camera.main;
                mmdCamDriver.UseMotionClip(clip);
                mmdMode = true;
                time = 0;
                SampleAndSolve();
            }
            catch (Exception e)
            {
                mmdInfo = "MMD 载入失败: " + e.Message;
            }
            Repaint();
        }

        void MmdLoadCameraVmd(string path)
        {
            try
            {
                mmdCamDriver.LoadFile(path);
                if (mmdCamDriver.target == null) mmdCamDriver.target = Camera.main;
                mmdCamDrive = mmdCamDriver.HasKeys;
                if (mmdCamDrive) mmdCamDriver.CaptureRestore();
                SampleAndSolve();
            }
            catch (Exception e)
            {
                mmdCamDriver.info = "镜头载入失败: " + e.Message;
            }
            Repaint();
        }

        void ApplyMmdCamera()
        {
            if (!mmdCamDrive || mmdPlayer == null) return;
            mmdCamDriver.Apply(time, mmdScale, charRoot, mmdPlayer.bindRootWorld);
        }

        void OnGUI()
        {
            scroll = GUILayout.BeginScrollView(scroll);

            // 诊断导出
            if (GUILayout.Button("导出骨架快照 (当前帧全部骨骼位姿 → Validation/skeleton-snapshot.json)"))
                DumpSkeleton();

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
                bool nu = EditorGUILayout.Toggle("Apply RootMotion (驱动 Root 节点)", useRm);
                if (nu != useRm) { useRm = nu; SampleAndSolve(); }
                bool ncf = EditorGUILayout.Toggle("Clavicle 跟随 (扩大臂可达域)", clavFollow);
                if (ncf != clavFollow) { clavFollow = ncf; CaptureClavicles(); SampleAndSolve(); }
                GUILayout.Label(rmInfo, EditorStyles.wordWrappedMiniLabel);
                if (rm != null && rm.FrameCount > 0)
                {
                    int idx = Mathf.Clamp(Mathf.RoundToInt(time * rm.sampleRate), 0, rm.FrameCount - 1);
                    var sb = new System.Text.StringBuilder();
                    for (int b = 0; b < rm.numBones; b++)
                    {
                        int o = b * 7;
                        sb.AppendFormat("{0}: pos({1:F2},{2:F2},{3:F2})  ", RmBoneGuess[b],
                            rm.Get(idx, o), rm.Get(idx, o + 1), rm.Get(idx, o + 2));
                    }
                    GUILayout.Label(sb.ToString(), EditorStyles.miniLabel);
                }
            }

            GUILayout.Space(8);

            // ---- MMD 播放（定制化载入）----
            GUILayout.Label("MMD 播放器（VMD 定制载入）", EditorStyles.boldLabel);
            using (new EditorGUILayout.HorizontalScope())
            {
                if (GUILayout.Button("打开 VMD...") && charRoot != null)
                {
                    string p = EditorUtility.OpenFilePanel("选择 VMD 动作文件", "", "vmd");
                    if (!string.IsNullOrEmpty(p)) MmdLoadVmd(p);
                }
                using (new EditorGUI.DisabledScope(mmdPlayer == null))
                {
                    bool nm = GUILayout.Toggle(mmdMode, "VMD 驱动", GUILayout.Width(90));
                    if (nm != mmdMode)
                    {
                        mmdMode = nm;
                        if (!mmdMode && mmdPlayer != null) mmdPlayer.Reset();
                        SampleAndSolve();
                    }
                }
            }
            GUILayout.Label(mmdInfo, EditorStyles.wordWrappedMiniLabel);
            if (mmdPlayer != null)
            {
                mmdScale = EditorGUILayout.Slider("位移比例", mmdScale, 0f, 0.3f);
                mmdInPlace = EditorGUILayout.Toggle("原地播放（锁水平位移）", mmdInPlace);
                mmdHeight = EditorGUILayout.Slider("高度修正", mmdHeight, -1f, 1f);
                if (GUILayout.Button("重新校准 T-pose"))
                {
                    bool calib = mmdPlayer.Recalibrate();
                    mmdInfo += " | 重校准" + (calib ? "成功" : "失败");
                    SampleAndSolve();
                }
            }

            // ---- 镜头轨（MmdCameraDriver）----
            GUILayout.Label("镜头轨（VMD 相机）", EditorStyles.boldLabel);
            using (new EditorGUILayout.HorizontalScope())
            {
                if (GUILayout.Button("打开镜头 VMD...", GUILayout.Width(130)))
                {
                    string p = EditorUtility.OpenFilePanel("选择镜头 VMD（如 Camera.vmd）", "", "vmd");
                    if (!string.IsNullOrEmpty(p)) MmdLoadCameraVmd(p);
                }
                using (new EditorGUI.DisabledScope(!mmdCamDriver.HasKeys))
                {
                    bool nc = GUILayout.Toggle(mmdCamDrive, "镜头驱动", GUILayout.Width(90));
                    if (nc != mmdCamDrive)
                    {
                        if (nc) mmdCamDriver.CaptureRestore(); else mmdCamDriver.Restore();
                        mmdCamDrive = nc;
                        SampleAndSolve();
                    }
                    if (GUILayout.Button("复位相机", GUILayout.Width(80)))
                    {
                        mmdCamDriver.Restore();
                        mmdCamDrive = false;
                        SampleAndSolve();
                    }
                }
            }
            var newCam = (Camera)EditorGUILayout.ObjectField("目标相机", mmdCamDriver.target, typeof(Camera), true);
            if (newCam != mmdCamDriver.target)
            {
                if (mmdCamDrive) mmdCamDriver.Restore();
                mmdCamDriver.target = newCam;
                if (mmdCamDrive) mmdCamDriver.CaptureRestore();
                Repaint();
            }
            GUILayout.Label(mmdCamDriver.info, EditorStyles.wordWrappedMiniLabel);
            if (mmdCamDriver.HasKeys)
            {
                mmdCamDriver.yaw = EditorGUILayout.Slider("机位偏航（角色背对镜头时 ±180）", mmdCamDriver.yaw, -180f, 360f);
                mmdCamDriver.distanceScale = EditorGUILayout.Slider("距离缩放", mmdCamDriver.distanceScale, 0.1f, 3f);
                mmdCamDriver.fovOffset = EditorGUILayout.Slider("FOV 偏移", mmdCamDriver.fovOffset, -20f, 20f);
                mmdCamDriver.offset = EditorGUILayout.Vector3Field("目标偏移", mmdCamDriver.offset);
                mmdCamDriver.follow = EditorGUILayout.Toggle("机位跟随角色位移", mmdCamDriver.follow);
                mmdCamDriver.followVertical = EditorGUILayout.Toggle("跟随高度", mmdCamDriver.followVertical);
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
