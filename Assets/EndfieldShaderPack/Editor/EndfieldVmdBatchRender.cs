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
        const string ScenePath = "Assets/Scenes/Typhoeus_OfficialFrame_Recovered.unity";
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
        string outDir = "Validation/vmd-unforgiven";
        int width = 1920, height = 1080;
        int fps = 30;
        int frameStart;
        int frameEnd;              // 0 = 自动（clip.lastFrame）
        float scale = 0.08f;       // 与 Studio 的 suggestedScale 一致
        bool inPlace = true;
        float heightOffset;
        bool driveCamera = true;
        float camYaw;              // 角色背对镜头时 ±180
        bool muxAudio = true;
        bool flipY = true;         // ReadPixels 是自下而上，出视频必须翻
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
            heightOffset = EditorGUILayout.Slider("高度修正", heightOffset, -1f, 1f);
            driveCamera = EditorGUILayout.Toggle("镜头驱动", driveCamera);
            using (new EditorGUI.DisabledScope(!driveCamera))
                camYaw = EditorGUILayout.Slider("机位偏航（±180）", camYaw, -180f, 360f);
            muxAudio = EditorGUILayout.Toggle("合成音频", muxAudio);
            flipY = EditorGUILayout.Toggle("垂直翻转（出视频必须开）", flipY);

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

        static Transform EnsureScene(out Camera cam, out bool openedNow)
        {
            openedNow = false;
            var root = GameObject.Find(CharRootName)?.transform;
            if (root == null)
            {
                var scene = EditorSceneManager.OpenScene(ScenePath, OpenSceneMode.Single);
                foreach (var go in scene.GetRootGameObjects())
                    if (go.name == CharRootName) { root = go.transform; break; }
                openedNow = true;
            }
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
            if (caster == null) caster = root.gameObject.AddComponent<EndfieldCharacterShadowCaster>();
            caster.slot = 0;
            EndfieldCharacterShadowCaster.Refresh();

            cam = Camera.main;
            if (cam != null && openedNow)
                cam.transform.SetPositionAndRotation(
                    new Vector3(0f, 0.7799988f, 2.9599915f),
                    new Quaternion(-1.7726111e-10f, 0.9999918f, 0.0040552616f, -4.371103e-8f));
            return root;
        }

        // ---------- render ----------
        void RunRender()
        {
            status = "";
            var root = EnsureScene(out var cam, out bool openedNow);
            if (root == null) { status = "场景里找不到 " + CharRootName; return; }
            if (cam == null) { status = "场景里没有 Main Camera"; return; }

            MmdPlayer player;
            var camDriver = new MmdCameraDriver();
            try
            {
                var motion = Vmd.ReadFile(motionPath);
                player = MmdPlayer.Load(motion, root);
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

            int last = frameEnd > 0 ? frameEnd : (int)player.clip.lastFrame;
            if (frameStart > last) { status = "起始帧超过结束帧"; return; }
            // 帧域约定（统一到 VMD 30fps）：VMD 帧号 f_vmd ∈ [frameStart, last]。
            // 渲染 fps 只决定输出时长：第 k 张 PNG 对应 vmd 帧号 k + frameStart，
            // 时间 t=(k+frameStart)/30 —— 与 MMD 原速一致，改 fps 只改输出密度。
            int total = last - frameStart + 1;

            string dir = Path.GetFullPath(Path.Combine(Application.dataPath, "..", outDir));
            Directory.CreateDirectory(dir);

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
                "driveCamera=" + driveCamera, "camYaw=" + camYaw,
                "loadInfo=" + player.loadInfo,
                "face=" + MmdFace.Describe(root),
            };
            File.WriteAllLines(Path.Combine(dir, "manifest.txt"), manifest);

            var sw = Stopwatch.StartNew();
            bool canceled = false;
            double vmdFps = 30.0;
            int index = 0;
            for (int vf = frameStart; vf <= last; vf++, index++)
            {
                float t = vf / (float)vmdFps;   // VMD 帧号 → 时间（30fps 域）
                player.Reset();
                player.ApplyFrame(t, scale, inPlace, heightOffset);
                if (driveCamera && camDriver.HasKeys)
                    camDriver.Apply(t, scale, root, player.bindRootWorld);
                SaveFrame(cam, Path.Combine(dir, "frame_" + index.ToString("D4") + ".png"), w, h, flipY);
                if (EditorUtility.DisplayCancelableProgressBar("VMD Batch Render",
                        string.Format("帧 {0}/{1}  ({2:F1}s)", vf, last, t), (float)index / total))
                { canceled = true; break; }
            }
            EditorUtility.ClearProgressBar();
            sw.Stop();

            string mp4 = "";
            if (!canceled && muxAudio && File.Exists(audioPath) && FindFfmpeg() != null)
            {
                mp4 = Mux(dir, audioPath, fps, w, h, out string muxLog);
                if (mp4 == null) status += "\nffmpeg 失败: " + muxLog;
            }
            status = string.Format(
                "{0}{1} 帧 → {2}\n耗时 {3:F1}s{4}",
                canceled ? "已取消，" : "", total, dir, sw.Elapsed.TotalSeconds,
                mp4 != null ? "\nMP4: " + mp4 : "");
            if (mp4 != null) EditorUtility.RevealInFinder(mp4);
            Repaint();
            Debug.Log("[VmdBatchRender] " + status);
        }

        static void SaveFrame(Camera cam, string path, int w, int h, bool flip)
        {
            var rt = new RenderTexture(w, h, 24);
            var prevActive = RenderTexture.active;
            cam.targetTexture = rt;
            cam.Render();
            RenderTexture.active = rt;
            var tex = new Texture2D(w, h, TextureFormat.RGBA32, false);
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
            cam.targetTexture = null;
            RenderTexture.active = prevActive;
            UnityEngine.Object.DestroyImmediate(tex);
            UnityEngine.Object.DestroyImmediate(rt);
        }

        static string Mux(string dir, string audio, int fps, int w, int h, out string log)
        {
            string outMp4 = Path.Combine(dir, "unforgiven.mp4");
            var psi = new ProcessStartInfo
            {
                FileName = FindFfmpeg(),
                WorkingDirectory = dir,
                UseShellExecute = false,
                RedirectStandardError = true,
                RedirectStandardOutput = true,
                Arguments = string.Format(
                    "-y -framerate {0} -i \"frame_%04d.png\" -i \"{1}\" " +
                    "-c:v libx264 -pix_fmt yuv420p -crf 18 -r {0} -shortest \"{2}\"",
                    fps, audio, outMp4),
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

        static string FindFfmpeg()
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
