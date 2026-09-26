// MmdPlayer.cs — shared MMD playback core: bind capture, per-frame bone apply,
// stateful camera driver, and the morph (expression) layer.
// The interactive window (EndfieldAnimStudio) and the offline batch renderer
// (EndfieldVmdBatchRender) both drive these classes so there is exactly one
// implementation of the retarget/camera/morph logic.
// Derived from OedoSoldier/Endfield-Poser (AGPL-3.0) src/math/mmd_*.h + retarget.h.
using System;
using System.Collections.Generic;
using UnityEngine;

namespace EndfieldShaderPack.EditorTools.Mmd
{
    public class MmdPlayer
    {
        public VmdMotionClip clip;
        public MmdRigDefinition sourceRig;
        public MmdRetargetProfile profile;
        public MmdRetargeter retargeter;
        public bool calibrationOk;
        public string loadInfo = "";
        public Transform charRoot { get; private set; }
        public float suggestedScale => retargeter != null ? retargeter.suggestedScale : .08f;

        readonly List<Transform> _bones = new List<Transform>();
        readonly List<Quaternion> _bindRot = new List<Quaternion>();
        readonly List<Vector3> _bindPos = new List<Vector3>();
        Vector3 _bindRoot;
        Transform _leftFoot, _rightFoot;
        float _bindMinFootY;
        public bool captured { get; private set; }
        public Vector3 bindRootWorld => _bindRoot;
        public float bindMinFootY => _bindMinFootY;

        public static MmdPlayer Load(VmdMotionClip clip, Transform charRoot)
        {
            var p = new MmdPlayer();
            p.clip = clip;
            p.charRoot = charRoot;
            p.sourceRig = MmdRigDefinition.StandardMmd();
            p.profile = MmdRetargetProfile.FromUnity(charRoot);
            p.calibrationOk = MmdCalibration.MakeTPose(p.profile);
            p.retargeter = new MmdRetargeter();
            p.retargeter.Bind(p.sourceRig, clip, p.profile);
            p.CaptureBind();
            p.loadInfo = string.Format(
                "MMD 载入: {0} 骨骼轨, {1} 关键帧, {2} 镜头帧, 时长 {3:F1}s | " +
                "T-pose 校准{4} | 未映射轨道 {5} | scale={6:F3} | 表情 {7}",
                clip.bones.Count, clip.boneKeys, clip.cameras.Count, clip.Duration,
                p.calibrationOk ? "成功" : "失败: " + p.profile.calibrationError,
                p.retargeter.unmapped.Count, p.retargeter.suggestedScale,
                clip.morphs.Count);
            return p;
        }

        public bool Recalibrate()
        {
            if (charRoot == null || clip == null || retargeter == null) return false;
            Reset();
            profile = MmdRetargetProfile.FromUnity(charRoot);
            calibrationOk = MmdCalibration.MakeTPose(profile);
            retargeter.Bind(sourceRig, clip, profile);
            CaptureBind();
            return calibrationOk;
        }

        public void CaptureBind()
        {
            if (charRoot == null || profile == null) return;
            _bones.Clear(); _bindRot.Clear(); _bindPos.Clear();
            foreach (var b in profile.bones)
            {
                if (b.transform == null) continue;
                _bones.Add(b.transform);
                _bindRot.Add(b.transform.localRotation);
                _bindPos.Add(b.transform.localPosition);
            }
            _bindRoot = charRoot.position;
            _leftFoot = profile.roles[5] >= 0 ? profile.bones[profile.roles[5]].transform : null;
            _rightFoot = profile.roles[6] >= 0 ? profile.bones[profile.roles[6]].transform : null;
            if (_leftFoot != null && _rightFoot != null)
                _bindMinFootY = Mathf.Min(_leftFoot.position.y, _rightFoot.position.y);
            captured = true;
        }

        /// <summary>
        /// Prevent the lowest foot bone from crossing its bind-pose floor.
        /// Apply after the retargeted pose and before a following VMD camera.
        /// A raised foot stays raised, so authored jumps remain intact.
        /// </summary>
        public float KeepFeetAboveBindFloor(float soleBelowFootBone = 0f)
        {
            if (!captured || charRoot == null || _leftFoot == null || _rightFoot == null) return 0f;
            float correction = Mathf.Max(0f,
                _bindMinFootY - Mathf.Max(0f, soleBelowFootBone) -
                Mathf.Min(_leftFoot.position.y, _rightFoot.position.y));
            if (correction > 0f) charRoot.position += Vector3.up * correction;
            return correction;
        }

        public void Reset()
        {
            if (!captured) return;
            for (int i = 0; i < _bones.Count; i++)
            {
                if (_bones[i] == null) continue;
                _bones[i].localRotation = _bindRot[i];
                _bones[i].localPosition = _bindPos[i];
            }
            charRoot.position = _bindRoot;
        }

        /// <summary>Reset to bind, sample VMD at timeSec, write bones + root + morphs.</summary>
        public void ApplyFrame(float timeSec, float scale, bool inPlace, float height,
            VmdIkMode mode = VmdIkMode.FollowMotion, float ampBody = 1f, float ampArms = 1f,
            float ampLegs = 1f, float ampHead = 1f)
        {
            if (clip == null || profile == null || retargeter == null) return;
            if (!captured) CaptureBind();
            retargeter.ampBody = ampBody;
            retargeter.ampArms = ampArms;
            retargeter.ampLegs = ampLegs;
            retargeter.ampHead = ampHead;
            retargeter.Sample(timeSec * 30.0, scale, inPlace, height, mode);
            var outPose = retargeter.output;
            for (int i = 0; i < profile.bones.Count; i++)
            {
                var b = profile.bones[i];
                if (b.transform == null) continue;
                if (outPose.write[i]) b.transform.localRotation = outPose.localRot[i];
            }
            charRoot.position = _bindRoot + outPose.rootOffset;
            MmdFace.ApplyMorphs(clip, timeSec * 30.0, charRoot);
        }
    }

    // ---- stateful VMD camera driver ----
    public class MmdCameraDriver
    {
        public List<VmdCameraKey> keys;
        public string info = "镜头: 未载入";
        public bool loadedFromFile;      // true = 独立镜头文件优先于动作文件内嵌轨
        public Camera target;
        public bool follow = true;       // 机位跟随角色位移
        public bool followVertical = true;
        public float yaw;                // basis 偏航（角色背对镜头时 ±180）
        public float distanceScale = 1f;
        public float fovOffset;
        public Vector3 offset;

        // MMD 世界系 → Unity 世界系的纯方向 basis。
        // 不能用 followRoot.rotation：chr 根带着 M5 枢轴（Euler(0,45.5,0)*Euler(-90,0,0)），
        // 其 -90°X 会当作相机俯仰角混进取景。retarget 的 _basis 约定是
        // MMD +Y(上) → Unity +Y、MMD +Z(前) → Unity +Z，与骨骼映射同系。
        public static Quaternion WorldBasis(Transform followRoot, float yaw)
        {
            if (followRoot == null) return Quaternion.Euler(0f, yaw, 0f);
            // 世界到根的旋转，取其"绕世界 Y 的偏航"分量，剔除其他欧拉分量。
            var q = followRoot.rotation;
            Vector3 fwd = q * Vector3.forward;
            fwd.y = 0f;
            if (fwd.sqrMagnitude < 1e-6f) fwd = Vector3.forward;
            return Quaternion.LookRotation(fwd.normalized, Vector3.up) * Quaternion.Euler(0f, yaw, 0f);
        }

        bool _restoreValid;
        Vector3 _pos; Quaternion _rot; float _fov, _ortho; bool _orthoFlag;

        public void LoadFile(string path)
        {
            var clip = Vmd.ReadFile(path);
            keys = clip.cameras;
            loadedFromFile = true;
            info = keys.Count > 0
                ? string.Format("镜头文件: {0} 帧, 时长 {1:F1}s", keys.Count, clip.Duration)
                : "镜头文件内没有镜头帧: " + path;
        }

        public void UseMotionClip(VmdMotionClip clip)
        {
            if (loadedFromFile) return;  // 独立镜头文件优先
            keys = clip.cameras;
            info = keys.Count > 0
                ? string.Format("镜头: 动作文件内嵌 {0} 帧", keys.Count)
                : "镜头: 动作文件无镜头轨（可单独打开 Camera.vmd）";
        }

        public bool HasKeys => keys != null && keys.Count > 0;

        public void CaptureRestore()
        {
            if (target == null) return;
            _restoreValid = true;
            _pos = target.transform.position;
            _rot = target.transform.rotation;
            _fov = target.fieldOfView;
            _ortho = target.orthographicSize;
            _orthoFlag = target.orthographic;
        }

        public void Restore()
        {
            if (!_restoreValid || target == null) return;
            target.transform.position = _pos;
            target.transform.rotation = _rot;
            target.fieldOfView = _fov;
            target.orthographicSize = _ortho;
            target.orthographic = _orthoFlag;
        }

        public void Apply(float timeSec, float scale, Transform followRoot, Vector3 bindRoot)
        {
            if (target == null || !HasKeys || followRoot == null) return;
            // 镜头帧域 = VMD 30fps 帧（与 ApplyFrame 的 retarget 采样同域）
            var key = VmdCameraTrack.SampleKey(keys, timeSec * 30.0);
            Vector3 origin = follow ? followRoot.position : bindRoot;
            if (follow && !followVertical) origin = new Vector3(origin.x, bindRoot.y, origin.z);
            var settings = new VmdCameraSettings
            {
                origin = origin,
                basis = WorldBasis(followRoot, yaw),
                offset = offset,
                scale = scale,
                distanceScale = distanceScale,
                fovOffset = fovOffset
            };
            VmdCameraTrack.Apply(target, VmdCameraTrack.Place(key, settings));
        }
    }

    // ---- morph / expression layer (Phase 5) ----
    // VMD morph tracks (あ/い/う/お/まばたき/下 ...) are written onto matching
    // SkinnedMeshRenderer blendshapes under the character root. Degrades to a
    // no-op with diagnostics when the rebuilt face has no blendshapes.
    public static class MmdFace
    {
        public static int ApplyMorphs(VmdMotionClip clip, double frame, Transform charRoot,
            bool logMisses = false)
        {
            if (clip == null || clip.morphs.Count == 0 || charRoot == null) return 0;
            var cache = MmdFaceCache.Get(charRoot);
            if (cache.map.Count == 0) return 0;
            int matched = 0;
            foreach (var kv in clip.morphs)
            {
                float w = Vmd.SampleMorph(kv.Value, frame) * 100f;
                if (cache.Apply(kv.Key, w)) matched++;
                else if (logMisses && w > 0f) Debug.Log("[MmdFace] 无对应 blendshape: " + kv.Key);
            }
            return matched;
        }

        public static string Describe(Transform charRoot)
        {
            if (charRoot == null) return "角色缺失";
            var cache = MmdFaceCache.Get(charRoot, true);
            return cache.map.Count > 0
                ? string.Format("表情: 可用 blendshape {0} 个", cache.map.Count)
                : "表情: 角色骨骼网格无 blendshape（烘焙脸不支持形变）";
        }

        static string Norm(string s)
        {
            var sb = new System.Text.StringBuilder(s.Length);
            foreach (char c in s)
            {
                if (c == '　') { sb.Append(' '); continue; }
                sb.Append(char.ToLowerInvariant(c));
            }
            return sb.ToString().Trim();
        }

        // 常见日→英 blendshape 别名（只做精确匹配，避免误伤）
        static readonly Dictionary<string, string[]> Aliases = new Dictionary<string, string[]>
        {
            { "まばたき", new[] { "blink", "eye blink", "eyeclose", "eye close", "close eyes" } },
            { "あ", new[] { "mouth_a", "mouth a" } },
            { "い", new[] { "mouth_i", "mouth i" } },
            { "う", new[] { "mouth_u", "mouth u" } },
            { "お", new[] { "mouth_o", "mouth o" } },
            { "下", new[] { "brow down", "browdown" } },
        };

        class MmdFaceCache
        {
            public readonly Dictionary<string, KeyValuePair<SkinnedMeshRenderer, int>> map =
                new Dictionary<string, KeyValuePair<SkinnedMeshRenderer, int>>();
            readonly List<SkinnedMeshRenderer> _renderers = new List<SkinnedMeshRenderer>();
            Transform _root;

            public static MmdFaceCache Get(Transform root, bool rebuild = false)
            {
                var cache = _cache;
                if (!rebuild && cache != null && cache._root == root && cache._renderers.TrueForAll(r => r != null))
                    return cache;
                cache = new MmdFaceCache { _root = root };
                foreach (var smr in root.GetComponentsInChildren<SkinnedMeshRenderer>())
                {
                    if (smr.sharedMesh == null) continue;
                    cache._renderers.Add(smr);
                    int n = smr.sharedMesh.blendShapeCount;
                    for (int i = 0; i < n; i++)
                    {
                        string key = Norm(smr.sharedMesh.GetBlendShapeName(i));
                        if (!cache.map.ContainsKey(key))
                            cache.map[key] = new KeyValuePair<SkinnedMeshRenderer, int>(smr, i);
                    }
                }
                _cache = cache;
                return cache;
            }

            public bool Apply(string morph, float weight)
            {
                string m = Norm(morph);
                if (map.TryGetValue(m, out var hit))
                {
                    if (hit.Key == null) { _cache = null; return false; }
                    hit.Key.SetBlendShapeWeight(hit.Value, Mathf.Clamp(weight, 0f, 100f));
                    return true;
                }
                if (Aliases.TryGetValue(morph, out var alts))
                {
                    foreach (var a in alts)
                        if (map.TryGetValue(Norm(a), out hit))
                        {
                            if (hit.Key == null) { _cache = null; return false; }
                            hit.Key.SetBlendShapeWeight(hit.Value, Mathf.Clamp(weight, 0f, 100f));
                            return true;
                        }
                }
                if (m.Length >= 2)
                {
                    foreach (var kv in map)
                    {
                        if (kv.Key.Contains(m) || m.Contains(kv.Key))
                        {
                            if (kv.Value.Key == null) { _cache = null; return false; }
                            kv.Value.Key.SetBlendShapeWeight(kv.Value.Value, Mathf.Clamp(weight, 0f, 100f));
                            return true;
                        }
                    }
                }
                return false;
            }

            static MmdFaceCache _cache;
        }
    }
}
