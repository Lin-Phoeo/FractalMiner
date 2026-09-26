// MmdRig.cs — MMD standard rig definition + VMD pose evaluator.
// Derived from OedoSoldier/Endfield-Poser (AGPL-3.0) src/math/mmd_rig.h.
// Pure math uses UnityEngine types (identical Hamilton formulas to Poser's
// quat_math.h; Poser writes these values straight into the game skeleton).
using System;
using System.Collections.Generic;
using System.Globalization;
using UnityEngine;

namespace EndfieldShaderPack.EditorTools.Mmd
{
    // ---------------- rig definition ----------------
    public class MmdIkLink
    {
        public int bone = -1;
        public bool limited;
        public Vector3 minimum, maximum;
    }

    public class MmdRigBone
    {
        public string name;
        public Vector3 rest;
        public int parent = -1, layer;
        public int grant = -1;
        public float grantWeight;
        public bool grantRotation, grantPosition, grantLocal;
        public bool fixedAxis;
        public Vector3 axis;
        public int effector = -1, iterations;
        public float angleLimit;
        public List<MmdIkLink> links = new List<MmdIkLink>();
    }

    public class MmdRigDefinition
    {
        public string name;
        public bool builtin;
        public List<MmdRigBone> bones = new List<MmdRigBone>();
        public List<int> order = new List<int>();
        public Dictionary<string, int> names = new Dictionary<string, int>();
        public List<string> warnings = new List<string>();

        public int Find(string n)
        {
            return names.TryGetValue(MmdName.Normalize(n), out var i) ? i : -1;
        }

        int Add(string name, string parent, Vector3 p)
        {
            var b = new MmdRigBone { name = MmdName.Normalize(name), rest = p };
            b.parent = string.IsNullOrEmpty(parent) ? -1 : Find(parent);
            int i = bones.Count;
            names[b.name] = i;
            bones.Add(b);
            return i;
        }

        /// <summary>Topological order over parent+grant dependencies.</summary>
        public void Finish()
        {
            names.Clear();
            order.Clear();
            var mark = new int[bones.Count];
            var depths = new int[bones.Count];
            for (int i = 0; i < bones.Count; i++) names[bones[i].name] = i;

            void Visit(int i, int depth)
            {
                if (i < 0) return;
                if (i >= bones.Count) throw new InvalidOperationException("PMX bone index out of range");
                if (mark[i] == 1) throw new InvalidOperationException("Cyclic PMX skeleton or append dependency");
                if (mark[i] == 2) return;
                if (depth > 256) throw new InvalidOperationException("PMX dependency chain exceeds 256 bones");
                mark[i] = 1;
                Visit(bones[i].parent, depth + 1);
                depths[i] = 1 + Math.Max(bones[i].parent >= 0 ? depths[bones[i].parent] : 0,
                                         bones[i].grant >= 0 ? depths[bones[i].grant] : 0);
                if (depths[i] > 256) throw new InvalidOperationException("PMX dependency chain exceeds 256 bones");
                mark[i] = 2;
                order.Add(i);
            }
            for (int i = 0; i < bones.Count; i++) Visit(i, 0);
        }

        /// <summary>Same numeric roles as Unity HumanBodyBones (Poser RoleNames()).</summary>
        public static readonly string[] RoleNames = {
            "下半身", "左足", "右足", "左ひざ", "右ひざ",
            "左足首", "右足首", "上半身", "上半身2", "首",
            "頭", "左肩", "右肩", "左腕", "右腕",
            "左ひじ", "右ひじ", "左手首", "右手首", "左つま先",
            "右つま先", "左目", "右目", "あご", "左親指0",
            "左親指1", "左親指2", "左人指1", "左人指2", "左人指3",
            "左中指1", "左中指2", "左中指3", "左薬指1", "左薬指2",
            "左薬指3", "左小指1", "左小指2", "左小指3", "右親指0",
            "右親指1", "右親指2", "右人指1", "右人指2", "右人指3",
            "右中指1", "右中指2", "右中指3", "右薬指1", "右薬指2",
            "右薬指3", "右小指1", "右小指2", "右小指3", "上半身3" };

        /// <summary>Built-in standard MMD skeleton (centimeters), from Poser StandardRig.</summary>
        public static MmdRigDefinition StandardMmd()
        {
            var r = new MmdRigDefinition { name = "Standard MMD", builtin = true };
            int Add(string name, string parent, Vector3 p) => r.Add(name, parent, p);

            Add("全ての親", "", Vector3.zero);
            Add("センター", "全ての親", new Vector3(0, 10, 0));
            Add("グルーブ", "センター", new Vector3(0, 10, 0));
            Add("腰", "グルーブ", new Vector3(0, 10, 0));
            Add("下半身", "腰", new Vector3(0, 10, 0));
            Add("上半身", "腰", new Vector3(0, 11.3f, 0));
            Add("上半身2", "上半身", new Vector3(0, 13, 0));
            Add("上半身3", "上半身2", new Vector3(0, 14, 0));
            Add("首", "上半身3", new Vector3(0, 15.6f, 0));
            Add("頭", "首", new Vector3(0, 16.6f, 0));
            Add("両目", "頭", new Vector3(0, 17.1f, -0.5f));
            for (int side = 0; side < 2; side++)
            {
                string s = side != 0 ? "右" : "左";
                float x = side != 0 ? -1f : 1f;
                Add(s + "目", "両目", new Vector3(x * .35f, 17.1f, -.6f));
                Add(s + "肩P", "上半身3", new Vector3(x * .7f, 14.9f, 0));
                int shoulder = Add(s + "肩", s + "肩P", new Vector3(x * .9f, 14.9f, 0));
                int cancel = Add(s + "肩C", s + "肩", new Vector3(x * 1.7f, 14.8f, 0));
                {
                    // 肩C cancels the parent shoulder-P rotation (Poser grant semantics)
                    var cb = r.bones[cancel];
                    cb.grant = r.Find(s + "肩P");
                    cb.grantWeight = -1;
                    cb.grantRotation = true;
                    cb.grantLocal = true;
                    r.bones[cancel] = cb;
                }
                Add(s + "腕", s + "肩C", new Vector3(x * 1.7f, 14.8f, 0));
                Add(s + "腕捩", s + "腕", new Vector3(x * 2.5f, 14, 0));
                Add(s + "ひじ", s + "腕捩", new Vector3(x * 3.7f, 12.8f, 0));
                Add(s + "手捩", s + "ひじ", new Vector3(x * 4.6f, 11.9f, 0));
                Add(s + "手首", s + "手捩", new Vector3(x * 5.6f, 10.9f, 0));
                string[] fingers = { "親指", "人指", "中指", "薬指", "小指" };
                for (int f = 0; f < 5; f++)
                {
                    string parent = s + "手首";
                    for (int j = 0; j < 3; j++)
                    {
                        string fname = s + fingers[f] + (f == 0 ? j.ToString() : (j + 1).ToString());
                        int fi = Add(fname, parent,
                            new Vector3(x * (5.8f + j * .3f), 10.7f - j * .3f, (f - 2) * .17f));
                        parent = r.bones[fi].name;
                    }
                }
                Add(s + "足", "下半身", new Vector3(x * .85f, 9.5f, 0));
                Add(s + "ひざ", s + "足", new Vector3(x * .85f, 5, -.15f));
                Add(s + "足首", s + "ひざ", new Vector3(x * .85f, 1, 0));
                Add(s + "つま先", s + "足首", new Vector3(x * .85f, .25f, -1.2f));
                Add(s + "足IK親", "全ての親", new Vector3(x * .85f, 1, 0));
                int foot = Add(s + "足IK", s + "足IK親", new Vector3(x * .85f, 1, 0));
                {
                    var fb = r.bones[foot];
                    fb.effector = r.Find(s + "足首");
                    fb.iterations = 64;
                    fb.angleLimit = .6f;
                    fb.links.Add(new MmdIkLink { bone = r.Find(s + "ひざ"), limited = true,
                        minimum = new Vector3(-3.13f, 0, 0), maximum = new Vector3(-.001f, 0, 0) });
                    fb.links.Add(new MmdIkLink { bone = r.Find(s + "足") });
                    r.bones[foot] = fb;
                }
                int toe = Add(s + "つま先IK", s + "足IK", new Vector3(x * .85f, .25f, -1.2f));
                {
                    var tb = r.bones[toe];
                    tb.effector = r.Find(s + "つま先");
                    tb.iterations = 8;
                    tb.angleLimit = .5f;
                    tb.links.Add(new MmdIkLink { bone = r.Find(s + "足首") });
                    r.bones[toe] = tb;
                }
            }
            r.Finish();
            return r;
        }
    }

    // ---------------- pose evaluator ----------------
    public class MmdRigPose
    {
        public Vector3[] positions;
        public Quaternion[] rotations;
        public Quaternion[] localRot;
    }

    public class MmdRigEvaluator
    {
        MmdRigDefinition _rig;
        VmdMotionClip _clip;
        List<List<VmdBoneKey>> _tracks;
        List<string> _trackNames;
        VmdLocalPose[] _anim;
        Quaternion[] _ik;
        Quaternion[] _appendRot;
        Vector3[] _appendPos;
        List<int> _controllers = new List<int>();
        bool[] _needed;
        public List<string> unmapped = new List<string>();
        public MmdRigPose pose = new MmdRigPose();

        void World()
        {
            foreach (int i in _rig.order)
            {
                var b = _rig.bones[i];
                Quaternion q = _anim[i].rotation.ToQuat();
                Vector3 p = _anim[i].position.ToVec();
                _appendRot[i] = Quaternion.identity;
                _appendPos[i] = Vector3.zero;
                if (b.grant >= 0)
                {
                    var source = _rig.bones[b.grant];
                    Quaternion g = (b.grantLocal || source.grant < 0)
                        ? _anim[b.grant].rotation.ToQuat() : _appendRot[b.grant];
                    g = MmdQ.Normalize(_ik[b.grant] * g);
                    if (b.grantRotation)
                    {
                        float w = b.grantWeight;
                        if (w < 0) g = MmdQ.Conj(g);
                        _appendRot[i] = Quaternion.Slerp(Quaternion.identity, g, Math.Abs(w));
                        q = MmdQ.Normalize(q * _appendRot[i]);
                    }
                    if (b.grantPosition)
                    {
                        _appendPos[i] = ((b.grantLocal || source.grant < 0)
                            ? _anim[b.grant].position.ToVec() : _appendPos[b.grant]) * b.grantWeight;
                        p += _appendPos[i];
                    }
                }
                q = MmdQ.Normalize(_ik[i] * q);
                _poseLocal[i] = q;
                if (b.parent >= 0)
                {
                    pose.positions[i] = pose.positions[b.parent] +
                        pose.rotations[b.parent] * (b.rest - _rig.bones[b.parent].rest + p);
                    pose.rotations[i] = MmdQ.Normalize(pose.rotations[b.parent] * q);
                }
                else
                {
                    pose.positions[i] = b.rest + p;
                    pose.rotations[i] = q;
                }
            }
        }

        Quaternion[] _poseLocal;

        void SetWorld(int i, Quaternion q)
        {
            int p = _rig.bones[i].parent;
            Quaternion parent = p >= 0 ? pose.rotations[p] : Quaternion.identity;
            Quaternion local = MmdQ.Normalize(Quaternion.Inverse(parent) * q);
            Quaternion basis = MmdQ.Normalize(Quaternion.Inverse(_ik[i]) * _poseLocal[i]);
            _ik[i] = MmdQ.Normalize(local * Quaternion.Inverse(basis));
            World();
        }

        public void Bind(MmdRigDefinition rig, VmdMotionClip clip,
            Dictionary<string, string> bindings = null)
        {
            _rig = rig;
            _clip = clip;
            int n = rig.bones.Count;
            _tracks = new List<List<VmdBoneKey>>(new List<VmdBoneKey>[n]);
            _trackNames = new List<string>(new string[n]);
            _anim = new VmdLocalPose[n];
            _ik = new Quaternion[n];
            for (int i = 0; i < n; i++) _ik[i] = Quaternion.identity;
            _appendRot = new Quaternion[n];
            for (int i = 0; i < n; i++) _appendRot[i] = Quaternion.identity;
            _appendPos = new Vector3[n];
            _poseLocal = new Quaternion[n];
            pose.positions = new Vector3[n];
            pose.rotations = new Quaternion[n];
            pose.localRot = new Quaternion[n];
            _needed = new bool[n];
            unmapped.Clear();
            for (int i = 0; i < n; ++i)
            {
                string trackName = rig.bones[i].name;
                if (bindings != null && bindings.TryGetValue(rig.bones[i].name, out var mapped))
                    trackName = mapped;
                _trackNames[i] = trackName;
                if (!string.IsNullOrEmpty(trackName) && clip.bones.TryGetValue(trackName, out var track))
                    _tracks[i] = track;
            }
            void Need(int i)
            {
                if (i < 0 || _needed[i]) return;
                _needed[i] = true;
                Need(rig.bones[i].parent);
                Need(rig.bones[i].grant);
            }
            foreach (var roleName in MmdRigDefinition.RoleNames) Need(rig.Find(roleName));
            _controllers.Clear();
            for (int i = 0; i < n; ++i)
            {
                var b = rig.bones[i];
                bool relevant = false;
                foreach (var l in b.links) relevant = relevant || _needed[l.bone];
                if (b.effector >= 0 && relevant) { _controllers.Add(i); Need(i); }
            }
            _controllers.Sort((a, b) => rig.bones[a].layer.CompareTo(rig.bones[b].layer));
            var used = new HashSet<string>();
            for (int i = 0; i < n; i++)
                if (_needed[i] && _tracks[i] != null) used.Add(_trackNames[i]);
            foreach (var kv in clip.bones)
                if (!used.Contains(kv.Key)) unmapped.Add(kv.Key);
        }

        public bool HasTrack(int bone) =>
            bone >= 0 && bone < _tracks.Count && _tracks[bone] != null;

        public bool IkEnabled(int controller, double frame, VmdIkMode mode)
        {
            if (!_controllers.Contains(controller)) return false;
            // Follow mode preserves FK-only clips. Force-on uses even stationary IK
            // targets; force-off bypasses every IK chain. (Poser semantics)
            bool hasTrack = _tracks[controller] != null;
            if (mode == VmdIkMode.ForceOn) return true;
            if (mode == VmdIkMode.ForceOff) return false;
            // FollowMotion: use the clip's IK track; builtin rigs without a track
            // default to enabled (Poser: !rig_->builtin || tracks_[controller]).
            if (_rig.builtin && !hasTrack) return true;
            return _clip != null && Vmd.SampleIk(_clip, _trackNames[controller], frame);
        }

        public void Sample(double frame, VmdIkMode mode = VmdIkMode.FollowMotion)
        {
            for (int i = 0; i < _anim.Length; i++)
            {
                _anim[i] = _tracks[i] != null ? Vmd.SampleBone(_tracks[i], frame) : new VmdLocalPose();
                _ik[i] = Quaternion.identity;
            }
            World();
            // PMX deformation order is relevant when IK chains share links.
            foreach (int c in _controllers)
            {
                var controller = _rig.bones[c];
                if (!IkEnabled(c, frame, mode)) continue;
                Vector3 target = pose.positions[c];
                if (_rig.builtin && (controller.name == "左足IK" || controller.name == "右足IK"))
                {
                    int a = controller.links[1].bone, b = controller.links[0].bone,
                        e = controller.effector;
                    Vector3 pa = pose.positions[a], pb = pose.positions[b],
                             pc = pose.positions[e];
                    int parent = _rig.bones[a].parent;
                    Vector3 pole = pa + (parent >= 0 ? pose.rotations[parent] : Quaternion.identity)
                        * new Vector3(0, 0, -10);
                    Vector3 sa = pa, sb = pb, sc = pc;
                    MmdIk.SolveTwoBone(ref sa, ref sb, ref sc, target, pole, true);
                    SetWorld(a, MmdQ.Normalize(
                        Quaternion.FromToRotation(pb - pa, sb - sa) * pose.rotations[a]));
                    SetWorld(b, MmdQ.Normalize(
                        Quaternion.FromToRotation(pose.positions[e] - pose.positions[b], sc - sb)
                        * pose.rotations[b]));
                    continue;
                }
                for (int iter = 0; iter < controller.iterations; iter++)
                {
                    if ((pose.positions[controller.effector] - target).sqrMagnitude < 1e-8f) break;
                    foreach (var link in controller.links)
                    {
                        int i = link.bone;
                        Vector3 va = pose.positions[controller.effector] - pose.positions[i],
                                 vb = target - pose.positions[i];
                        if (va.sqrMagnitude < 1e-12f || vb.sqrMagnitude < 1e-12f) continue;
                        Quaternion d = Quaternion.FromToRotation(va, vb);
                        float angle = Quaternion.Angle(Quaternion.identity, d);
                        if (angle > controller.angleLimit && angle > 1e-6f)
                            d = Quaternion.Slerp(Quaternion.identity, d, controller.angleLimit / angle);
                        int parent = _rig.bones[i].parent;
                        Quaternion pr = parent >= 0 ? pose.rotations[parent] : Quaternion.identity;
                        Quaternion local = MmdQ.Normalize(Quaternion.Inverse(pr) * d * pose.rotations[i]);
                        if (link.limited)
                        {
                            var eul = local.eulerAngles;
                            eul = new Vector3(
                                Mathf.Clamp(eul.x, link.minimum.x, link.maximum.x),
                                Mathf.Clamp(eul.y, link.minimum.y, link.maximum.y),
                                Mathf.Clamp(eul.z, link.minimum.z, link.maximum.z));
                            local = Quaternion.Euler(eul);
                        }
                        Quaternion basis = MmdQ.Normalize(Quaternion.Inverse(_ik[i]) * _poseLocal[i]);
                        _ik[i] = MmdQ.Normalize(local * Quaternion.Inverse(basis));
                        World();
                    }
                }
            }
        }
    }

    // ---------------- quaternion helpers (Poser quat_math.h) ----------------
    public static class MmdQ
    {
        public static Quaternion Normalize(Quaternion q)
        {
            float l = (float)Math.Sqrt(q.x * q.x + q.y * q.y + q.z * q.z + q.w * q.w);
            return l > 1e-6f ? new Quaternion(q.x / l, q.y / l, q.z / l, q.w / l) : Quaternion.identity;
        }
        public static Quaternion Conj(Quaternion q) =>
            new Quaternion(-q.x, -q.y, -q.z, q.w);
    }

    // ---------------- two-bone IK (Poser ik_two_bone.h) ----------------
    public static class MmdIk
    {
        static Vector3 RotateAxis(Vector3 axis, Vector3 v, float rad)
        {
            var k = MmdV.Norm(axis);
            float c = Mathf.Cos(rad), s = Mathf.Sin(rad);
            return v * c + Vector3.Cross(k, v) * s + k * (Vector3.Dot(k, v) * (1f - c));
        }

        /// <summary>Analytic two-bone IK. a=root, b=elbow, c=end; pole = bend direction.</summary>
        public static void SolveTwoBone(ref Vector3 a, ref Vector3 b, ref Vector3 c,
            Vector3 target, Vector3 pole, bool enforcePole)
        {
            float lab = Vector3.Distance(b, a), lbc = Vector3.Distance(c, b);
            float d = Vector3.Distance(target, a);
            Vector3 at = d > 1e-6f ? MmdV.Norm(target - a) : MmdV.Norm(c - a);
            if (at.sqrMagnitude < 1e-12f) at = MmdV.Norm(b - a);
            if (at.sqrMagnitude < 1e-12f) at = new Vector3(0, -1, 0);
            if (lab < 1e-6f || lbc < 1e-6f) { b = a + at * lab; c = b + at * lbc; return; }
            float epsilon = Mathf.Min(1e-4f, Mathf.Min(lab, lbc) * .01f);
            d = Mathf.Max(Mathf.Abs(lab - lbc) + epsilon, Mathf.Min(lab + lbc - epsilon, d));
            Vector3 reachable = a + at * d;
            float cos1 = (lab * lab + d * d - lbc * lbc) / (2f * lab * d);
            cos1 = Mathf.Clamp(cos1, -1f, 1f);
            float ang1 = Mathf.Acos(cos1);
            Vector3 poleDir = MmdV.Norm(pole - a);
            Vector3 axis = MmdV.Norm(Vector3.Cross(at, poleDir));
            if (axis.sqrMagnitude < 1e-10f) axis = MmdV.Norm(Vector3.Cross(at, Vector3.up));
            if (axis.sqrMagnitude < 1e-10f) axis = MmdV.Norm(Vector3.Cross(at, Vector3.forward));
            Vector3 upperDir = RotateAxis(axis, at, ang1);
            b = a + upperDir * lab;
            Vector3 foreDir = MmdV.Norm(reachable - b);
            c = b + foreDir * lbc;
        }
    }

    public static class MmdV
    {
        public static Vector3 Norm(Vector3 a)
        {
            float l = a.magnitude;
            return l > 1e-6f ? a / l : Vector3.zero;
        }
    }
}
