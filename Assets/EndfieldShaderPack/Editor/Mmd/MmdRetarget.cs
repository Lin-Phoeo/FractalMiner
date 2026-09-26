// MmdRetarget.cs — MMD-to-Endfield retarget: profile, T-pose calibration,
// and per-frame retarget math. Derived from OedoSoldier/Endfield-Poser
// (AGPL-3.0) src/math/mmd_retarget.h. Unity hierarchy builds the profile;
// output localRotations are written back to Transforms.
using System;
using System.Collections.Generic;
using System.Linq;
using UnityEngine;

namespace EndfieldShaderPack.EditorTools.Mmd
{
    // ---------------- target (Endfield) profile ----------------
    public class MmdTargetBone
    {
        public string name;
        public Transform transform;     // Unity handle (null for virtual)
        public int parent = -1;
        public int role = -1;
        public Vector3 localPos;
        public Vector3 restPos;
        public Vector3 localScale = Vector3.one;
        public Quaternion localRot, restRot;
        public Matrix4x4 restMatrix = Matrix4x4.identity;
        public bool calibrated;
    }

    public class MmdRetargetProfile
    {
        public List<MmdTargetBone> bones = new List<MmdTargetBone>();
        public int[] roles = Repeat(-1, 55);

        static int[] Repeat(int v, int n) { var a = new int[n]; for (int i = 0; i < n; i++) a[i] = v; return a; }

        public void Globals()
        {
            roles = Repeat(-1, 55);
            for (int i = 0; i < bones.Count; i++)
            {
                var b = bones[i];
                if (b.parent >= i || b.parent < -1)
                    throw new InvalidOperationException("Invalid target hierarchy");
                if (b.role >= 0 && b.role < 55) roles[b.role] = i;
                if (b.parent >= 0)
                {
                    var p = bones[b.parent];
                    b.restMatrix = p.restMatrix * Matrix4x4.TRS(b.localPos, b.localRot, b.localScale);
                    b.restRot = MmdQ.Normalize(p.restRot * b.localRot);
                }
                else
                {
                    b.restMatrix = Matrix4x4.TRS(b.localPos, b.localRot, b.localScale);
                    b.restRot = b.localRot;
                }
                b.restPos = b.restMatrix.GetColumn(3);
            }
        }

        static readonly int[] RequiredRoles = { 0, 1, 2, 3, 4, 5, 6, 7, 9, 10, 13, 14, 15, 16, 17, 18 };

        public bool Valid()
        {
            foreach (int role in RequiredRoles)
            {
                int i = roles[role];
                if (i < 0 || !bones[i].calibrated) return false;
            }
            Vector3 across = bones[roles[13]].restPos - bones[roles[14]].restPos;
            Vector3 up = bones[roles[10]].restPos - bones[roles[0]].restPos;
            return across.magnitude > 1e-4f && up.magnitude > 1e-4f &&
                   Vector3.Cross(across, up).magnitude > 1e-5f;
        }

        public MmdTargetBone ByRole(int role) =>
            role >= 0 && role < 55 && roles[role] >= 0 ? bones[roles[role]] : null;

        /// <summary>Endfield skeleton role bindings (chr_0034 Biped naming).</summary>
        public static readonly (int role, string bone)[] RoleBindings = {
            (0,  "Bip001_Pelvis"),
            (7,  "Bip001_Spine"),
            (8,  "Bip001_Spine1"),
            (54, "Bip001_Spine2"),
            (9,  "Bip001_Neck"),
            (10, "Bip001_Head"),
            (11, "Bip001_L_Clavicle"),
            (12, "Bip001_R_Clavicle"),
            (13, "Bip001_L_UpperArm"),
            (14, "Bip001_R_UpperArm"),
            (15, "Bip001_L_Forearm"),
            (16, "Bip001_R_Forearm"),
            (17, "Bip001_L_Hand"),
            (18, "Bip001_R_Hand"),
            (1,  "Bip001_L_Thigh"),
            (2,  "Bip001_R_Thigh"),
            (3,  "Bip001_L_Calf"),
            (4,  "Bip001_R_Calf"),
            (5,  "Bip001_L_Foot"),
            (6,  "Bip001_R_Foot"),
            (19, "Bip001_L_Toe0"),
            (20, "Bip001_R_Toe0"),
        };

        /// <summary>Build the target profile from the rebuilt Unity hierarchy.</summary>
        public static MmdRetargetProfile FromUnity(Transform charRoot)
        {
            var prof = new MmdRetargetProfile();
            var index = new Dictionary<Transform, int>();

            // Bones that carry VMD roles: only the mapped subset is needed.
            var roleBones = new List<Transform>();
            foreach (var (role, boneName) in RoleBindings)
            {
                var t = FindRecursive(charRoot, boneName);
                if (t == null) throw new InvalidOperationException("bone missing: " + boneName);
                roleBones.Add(t);
            }

            // Include all ancestors of role bones so the hierarchy is complete.
            var included = new List<Transform>();
            var includedSet = new HashSet<Transform>();
            foreach (var t in roleBones)
            {
                var stack = new Stack<Transform>();
                for (var cur = t; cur != null && cur != charRoot; cur = cur.parent)
                    if (includedSet.Add(cur)) stack.Push(cur);
                while (stack.Count > 0) included.Add(stack.Pop());
            }

            included.Sort((a, b) => Depth(a).CompareTo(Depth(b)));
            foreach (var t in included)
            {
                var b = new MmdTargetBone
                {
                    name = t.name,
                    transform = t,
                    parent = t.parent != null && t.parent != charRoot && index.TryGetValue(t.parent, out var pi) ? pi : -1,
                    localPos = t.localPosition,
                    localRot = t.localRotation,
                    localScale = t.localScale,
                };
                foreach (var (role, boneName) in RoleBindings)
                    if (t.name == boneName) { b.role = role; break; }
                index[t] = prof.bones.Count;
                prof.bones.Add(b);
            }
            prof.Globals();
            return prof;

            int Depth(Transform t) { int d = 0; for (var c = t.parent; c != null && c != charRoot; c = c.parent) d++; return d; }
        }

        static Transform FindRecursive(Transform root, string name)
        {
            if (root.name == name) return root;
            foreach (Transform c in root)
            {
                var hit = FindRecursive(c, name);
                if (hit != null) return hit;
            }
            return null;
        }
    }

    // ---------------- T-pose calibration ----------------
    public static class MmdCalibration
    {
        /// <summary>
        /// MakeCalibrationTPose (Poser mmd_retarget.h): constructs each bone's rest
        /// orientation from anatomical landmarks so VMD rotations map cleanly.
        /// Never assumes local axes: a Biped pelvis may be rotated 90° at rest.
        /// </summary>
        public static bool MakeTPose(MmdRetargetProfile profile)
        {
            var p = ShallowClone(profile); // reject degenerate rigs without partial edit
            p.Globals();
            var up = Vector3.up;
            if (p.roles[0] < 0 || p.roles[7] < 0) return false;
            foreach (int role in MmdRetargetProfile.RequiredRoles)
                if (p.roles[role] < 0) return false;

            Vector3 Pos(int role) => p.bones[p.roles[role]].restPos;

            Vector3 leftV = Pos(13) - Pos(14);
            leftV = MmdV.Norm(leftV - up * Vector3.Dot(leftV, up));
            if (leftV.magnitude < 0.9f) return false;
            Vector3 forward = MmdV.Norm(Vector3.Cross(up, leftV));

            // Accurate basis extraction (Poser Basis()) via Unity Matrix4x4.
            Quaternion BasisQ(Vector3 x, Vector3 y, Vector3 z)
            {
                var m = Matrix4x4.identity;
                m.SetColumn(0, new Vector4(x.x, x.y, x.z, 0));
                m.SetColumn(1, new Vector4(y.x, y.y, y.z, 0));
                m.SetColumn(2, new Vector4(z.x, z.y, z.z, 0));
                return MmdQ.Normalize(m.rotation);
            }

            void SetWorld(int i, Quaternion rotation)
            {
                var b = p.bones[i];
                b.localRot = MmdQ.Normalize(
                    (b.parent < 0 ? Quaternion.identity : Quaternion.Inverse(p.bones[b.parent].restRot))
                    * rotation);
                p.bones[i] = b;
                p.Globals();
            }

            void Align(int role, int childRole, Vector3 direction)
            {
                int i = p.roles[role], j = p.roles[childRole];
                if (i < 0 || j < 0) return;
                Vector3 from = p.bones[j].restPos - p.bones[i].restPos;
                if (from.magnitude > 1e-5f)
                    SetWorld(i, Quaternion.FromToRotation(from, direction) * p.bones[i].restRot);
            }

            // Pelvis from anatomical landmarks (not its local Y).
            Vector3 across = Pos(1) - Pos(2), spine = Pos(7) - Pos(0);
            if (Vector3.Cross(across, spine).magnitude < 1e-6f) return false;
            int hip = p.roles[0];
            {
                var pelvisBasis = BasisQ(
                    MmdV.Norm(Pos(2) - Pos(1)), MmdV.Norm(Pos(7) - Pos(0)),
                    MmdV.Norm(Vector3.Cross(MmdV.Norm(Pos(1) - Pos(2)), MmdV.Norm(Pos(7) - Pos(0)))));
                SetWorld(hip, BasisQ(leftV, up, forward * -1) * Quaternion.Inverse(pelvisBasis)
                    * p.bones[hip].restRot);
            }

            // Spine chain upward.
            var spineRoles = new List<int> { 7 };
            foreach (int role in new[] { 8, 54, 9, 10 })
                if (p.roles[role] >= 0) spineRoles.Add(role);
            for (int i = 1; i < spineRoles.Count; ++i)
                Align(spineRoles[i - 1], spineRoles[i], up);

            // Arms and legs per side.
            for (int side = 0; side < 2; ++side)
            {
                Vector3 arm = leftV * (side != 0 ? -1f : 1f);
                int shoulder = 11 + side, upper = 13 + side, lower = 15 + side, hand = 17 + side;
                Align(shoulder, upper, arm);
                Align(upper, lower, arm);
                Align(lower, hand, arm);

                // Hand: aim along middle finger, palm down (uses finger landmarks).
                int index = 27 + side * 15, middle = 30 + side * 15, little = 36 + side * 15;
                Align(hand, middle, arm);
                if (p.roles[index] >= 0 && p.roles[little] >= 0)
                {
                    Vector3 width = Pos(index) - Pos(little);
                    width = MmdV.Norm(width - arm * Vector3.Dot(width, arm));
                    if (width.magnitude > 0.9f)
                    {
                        float angle = Mathf.Atan2(Vector3.Dot(arm, Vector3.Cross(width, forward)),
                            Vector3.Dot(width, forward));
                        int h = p.roles[hand];
                        SetWorld(h, Quaternion.AngleAxis(angle * Mathf.Rad2Deg, arm)
                            * p.bones[h].restRot);
                    }
                }

                // Fingers: straighten along arm.
                for (int finger = 0; finger < 4; ++finger)
                {
                    int proximal = index + finger * 3;
                    Align(proximal, proximal + 1, arm);
                    Align(proximal + 1, proximal + 2, arm);
                    int distal = p.roles[proximal + 2];
                    if (distal < 0) continue;
                    int child = -1, count = 0;
                    for (int j = 0; j < p.bones.Count; ++j)
                        if (p.bones[j].parent == distal) { child = j; ++count; }
                    if (count == 1)
                    {
                        Vector3 from = p.bones[child].restPos - p.bones[distal].restPos;
                        if (from.magnitude > 1e-5f)
                            SetWorld(distal, Quaternion.FromToRotation(from, arm)
                                * p.bones[distal].restRot);
                    }
                }

                // Legs: straighten down while preserving foot pitch (Poser note:
                // resetting a foot to identity makes heels point sideways on Biped rigs).
                int thigh = 1 + side, shin = 3 + side, foot = 5 + side;
                Quaternion footWorld = p.bones[p.roles[foot]].restRot;
                Align(thigh, shin, up * -1);
                Align(shin, foot, up * -1);
                SetWorld(p.roles[foot], footWorld);
                int toe = 19 + side;
                if (p.roles[toe] >= 0)
                {
                    Vector3 v = Pos(toe) - Pos(foot);
                    float vertical = Vector3.Dot(v, up);
                    Vector3 flat = v - up * vertical;
                    if (flat.magnitude > 1e-5f)
                        Align(foot, toe, forward * flat.magnitude + up * vertical);
                }
            }

            if (!p.Valid()) return false;
            profile.bones = p.bones;
            profile.roles = p.roles;
            return true;
        }

        static MmdRetargetProfile ShallowClone(MmdRetargetProfile src)
        {
            var dst = new MmdRetargetProfile { bones = new List<MmdTargetBone>(src.bones.Count), roles = (int[])src.roles.Clone() };
            foreach (var b in src.bones) dst.bones.Add(new MmdTargetBone
            {
                name = b.name, transform = b.transform, parent = b.parent, role = b.role,
                localPos = b.localPos, restPos = b.restPos, localScale = b.localScale,
                localRot = b.localRot, restRot = b.restRot, restMatrix = b.restMatrix,
                calibrated = b.calibrated
            });
            return dst;
        }
    }

    // ---------------- per-frame retarget ----------------
    public class MmdSampledPose
    {
        public Quaternion[] localRot, worldRot;
        public Vector3[] worldPos;
        public bool[] write;
        public Vector3 rootOffset;
        public bool[] legIkActive = new bool[2];
    }

    public class MmdRetargeter
    {
        MmdRigDefinition _source;
        VmdMotionClip _clip;
        MmdRetargetProfile _target;
        MmdRigEvaluator _eval = new MmdRigEvaluator();
        int[] _sourceRole = new int[55];
        Quaternion[] _alignedRest = new Quaternion[55];
        bool[] _affected = new bool[55];
        Quaternion[] _neutralLocal;
        Quaternion _basis = Quaternion.identity;
        public MmdSampledPose output = new MmdSampledPose();
        public float suggestedScale = .08f;
        public List<string> unmapped => _eval.unmapped;

        static readonly int[] Child = { 7, 3, 4, 5, 6, 19, 20, 8, 54, 10, -1,
            13, 14, 15, 16, 17, 18, 30, 45, -1, -1, -1,
            -1, -1, 25, 26, -1, 28, 29, -1, 31, 32, -1,
            34, 35, -1, 37, 38, -1, 40, 41, -1, 43, 44,
            -1, 46, 47, -1, 49, 50, -1, 52, 53, -1, 9 };

        static Vector3 MPos(Matrix4x4 m) => m.GetColumn(3);

        void World()
        {
            for (int i = 0; i < _target.bones.Count; i++)
            {
                var b = _target.bones[i];
                if (b.parent < 0)
                {
                    output.worldRot[i] = output.localRot[i];
                    output.worldPos[i] = output.localRot[i] * b.localPos;
                }
                else
                {
                    output.worldRot[i] = MmdQ.Normalize(output.worldRot[b.parent] * output.localRot[i]);
                    output.worldPos[i] = output.worldPos[b.parent]
                        + output.worldRot[b.parent] * b.localPos;
                }
            }
        }

        void SetWorld(int i, Quaternion q)
        {
            int p = _target.bones[i].parent;
            output.localRot[i] = MmdQ.Normalize(
                (p >= 0 ? Quaternion.Inverse(output.worldRot[p]) : Quaternion.identity) * q);
            output.write[i] = true;
            World();
        }

        public void Bind(MmdRigDefinition source, VmdMotionClip clip, MmdRetargetProfile target)
        {
            _source = source; _clip = clip; _target = target;
            Array.Fill(_sourceRole, -1);
            Array.Clear(_affected, 0, _affected.Length);
            bool bodyMotion = false;
            foreach (var track in clip.bones.Keys)
                bodyMotion = bodyMotion || !Vmd.EyeBone(track);
            for (int r = 0; r < 55; r++) _sourceRole[r] = source.Find(MmdRigDefinition.RoleNames[r]);
            if (_sourceRole[0] < 0) _sourceRole[0] = source.Find("センター");
            if (_sourceRole[8] < 0) _sourceRole[8] = _sourceRole[7];
            if (_sourceRole[54] < 0) _sourceRole[54] = _sourceRole[8];
            for (int side = 0; side < 2; side++)
            {
                int role = side != 0 ? 39 : 24;
                string s = side != 0 ? "右" : "左";
                if (_sourceRole[role] < 0)
                {
                    _sourceRole[role] = source.Find(s + "親指1");
                    _sourceRole[role + 1] = source.Find(s + "親指2");
                    _sourceRole[role + 2] = -1;
                }
            }
            _eval.Bind(source, clip);

            Vector3 Sp(int r) => _sourceRole[r] >= 0 ? source.bones[_sourceRole[r]].rest : Vector3.zero;
            Vector3 Tp(int r) => target.roles[r] >= 0 ? target.bones[target.roles[r]].restPos : Vector3.zero;

            Quaternion BodyBasisQ(Vector3 l, Vector3 r2, Vector3 hip, Vector3 head)
            {
                Vector3 x = MmdV.Norm(l - r2), y = MmdV.Norm(head - hip);
                Vector3 z = MmdV.Norm(Vector3.Cross(x, y));
                y = MmdV.Norm(Vector3.Cross(z, x));
                var m = Matrix4x4.identity;
                m.SetColumn(0, x); m.SetColumn(1, y); m.SetColumn(2, z);
                return MmdQ.Normalize(m.rotation);
            }

            _basis = MmdQ.Normalize(
                BodyBasisQ(Tp(13), Tp(14), Tp(0), Tp(10)) *
                Quaternion.Inverse(BodyBasisQ(Sp(13), Sp(14), Sp(0), Sp(10))));
            float sl = (Sp(1) - Sp(3)).magnitude + (Sp(3) - Sp(5)).magnitude;
            float tl = (Tp(1) - Tp(3)).magnitude + (Tp(3) - Tp(5)).magnitude;
            suggestedScale = source.builtin ? .08f : (sl > 1e-5f ? tl / sl : .08f);

            for (int r = 0; r < 55; r++)
            {
                int si = _sourceRole[r], ti = target.roles[r];
                if (si < 0 || ti < 0) continue;
                Quaternion rest = target.bones[ti].restRot;
                int cr = Child[r];
                bool foot = r == 5 || r == 6;
                if (!foot && cr >= 0 && _sourceRole[cr] >= 0 && target.roles[cr] >= 0)
                {
                    Vector3 a = Tp(cr) - Tp(r), b = _basis * (Sp(cr) - Sp(r));
                    if (a.magnitude > 1e-5f && b.magnitude > 1e-5f)
                        rest = MmdQ.Normalize(Quaternion.FromToRotation(a, b) * rest);
                }
                bool terminalFinger = r >= 24 && r <= 53 && (r - 24) % 3 != 0 &&
                    (cr < 0 || _sourceRole[cr] < 0 || target.roles[cr] < 0);
                if (terminalFinger && _sourceRole[r - 1] >= 0 && target.roles[r - 1] >= 0)
                {
                    // Carry previous phalanx's rest correction through the real chain.
                    int sp2 = source.bones[si].parent;
                    while (sp2 >= 0 && sp2 != _sourceRole[r - 1]) sp2 = source.bones[sp2].parent;
                    int tp2 = target.bones[ti].parent;
                    while (tp2 >= 0 && tp2 != target.roles[r - 1]) tp2 = target.bones[tp2].parent;
                    if (sp2 >= 0 && tp2 >= 0)
                        rest = MmdQ.Normalize(_alignedRest[r - 1] *
                            Quaternion.Inverse(target.bones[tp2].restRot) * rest);
                }
                _alignedRest[r] = rest;

                var seen = new HashSet<int>();
                bool Affects(int i)
                {
                    if (i < 0 || !seen.Add(i)) return false;
                    var b = source.bones[i];
                    return _eval.HasTrack(i) || Affects(b.parent) || Affects(b.grant);
                }
                _affected[r] = Affects(si) || (bodyMotion && r != 21 && r != 22 && r != 23);
            }

            int nb = target.bones.Count;
            output.localRot = new Quaternion[nb];
            output.worldRot = new Quaternion[nb];
            output.worldPos = new Vector3[nb];
            output.write = new bool[nb];
            _neutralLocal = new Quaternion[nb];
            for (int i = 0; i < nb; ++i)
            {
                var b = target.bones[i];
                Quaternion parent = b.parent >= 0 ? output.worldRot[b.parent] : Quaternion.identity;
                bool mapped = b.role >= 0 && b.role < 55 &&
                    _sourceRole[b.role] >= 0 && _affected[b.role];
                Quaternion rest = mapped ? _alignedRest[b.role] : MmdQ.Normalize(parent * b.localRot);
                _neutralLocal[i] = mapped ? MmdQ.Normalize(Quaternion.Inverse(parent) * rest) : b.localRot;
                output.worldRot[i] = rest;
            }
        }

        public void Sample(double frame, float scale, bool inPlace, float height,
            VmdIkMode mode = VmdIkMode.FollowMotion)
        {
            _eval.Sample(frame, mode);
            output.legIkActive = new bool[2];
            output.rootOffset = Vector3.zero;
            int hip = _sourceRole[0];
            if (hip >= 0 && _affected[0])
                output.rootOffset = _basis * (_eval.pose.positions[hip] - _source.bones[hip].rest) * scale;
            if (inPlace) { output.rootOffset.x = 0; output.rootOffset.z = 0; }
            output.rootOffset.y += height;

            int nb = _target.bones.Count;
            for (int i = 0; i < nb; i++)
            {
                var b = _target.bones[i];
                output.localRot[i] = b.localRot;
                output.write[i] = false;
                int r = b.role;
                if (r >= 0 && _sourceRole[r] >= 0 && _affected[r])
                {
                    Quaternion desired = MmdQ.Normalize(_basis * _eval.pose.rotations[_sourceRole[r]]
                        * Quaternion.Inverse(_basis) * _alignedRest[r]);
                    Quaternion parent = b.parent >= 0 ? output.worldRot[b.parent] : Quaternion.identity;
                    output.localRot[i] = MmdQ.Normalize(Quaternion.Inverse(parent) * desired);
                    output.write[i] = true;
                }
                output.worldRot[i] = b.parent >= 0
                    ? MmdQ.Normalize(output.worldRot[b.parent] * output.localRot[i])
                    : output.localRot[i];
                output.worldPos[i] = output.worldRot[i] * b.localPos
                    + (b.parent >= 0 ? output.worldPos[b.parent] : Vector3.zero);
            }
            if (hip < 0) return;

            // Leg two-bone IK: transfer the source knee bend onto target leg lengths.
            for (int side = 0; side < 2; side++)
            {
                int ar = side != 0 ? 2 : 1, br = side != 0 ? 4 : 3, cr = side != 0 ? 6 : 5;
                int a = _target.roles[ar], b = _target.roles[br], c = _target.roles[cr];
                int sc = _sourceRole[cr], sb = _sourceRole[br], saI = _sourceRole[ar];
                string controller = side != 0 ? "右足IK" : "左足IK";
                if (a < 0 || b < 0 || c < 0 || sc < 0 || sb < 0 || saI < 0 || !_affected[ar] ||
                    !_eval.IkEnabled(_source.Find(controller), frame, mode))
                    continue;
                Vector3 pa = output.worldPos[a], pb = output.worldPos[b], pc = output.worldPos[c];
                Vector3 sourceUpper = _eval.pose.positions[sb] - _eval.pose.positions[saI];
                Vector3 sourceLower = _eval.pose.positions[sc] - _eval.pose.positions[sb];
                Vector3 sourceReach = sourceUpper + sourceLower;
                float upperLength = (pb - pa).magnitude, lowerLength = (pc - pb).magnitude;
                if (upperLength < 1e-5f || lowerLength < 1e-5f ||
                    sourceUpper.magnitude < 1e-5f || sourceLower.magnitude < 1e-5f || sourceReach.magnitude < 1e-5f)
                    continue;
                // Transfer the source knee angle and hip-to-ankle direction onto the
                // target's actual thigh/shin lengths (Poser note: scaling the whole
                // pelvis-to-foot vector erased bends).
                float bendCos = Mathf.Clamp(Vector3.Dot(MmdV.Norm(sourceUpper), MmdV.Norm(sourceLower)), -1f, 1f);
                float reach = Mathf.Sqrt(Mathf.Max(0f, upperLength * upperLength +
                    lowerLength * lowerLength + 2f * upperLength * lowerLength * bendCos));
                Vector3 goal = pa + (_basis * MmdV.Norm(sourceReach)) * reach;
                Vector3 pole = pa + (_basis * MmdV.Norm(sourceUpper)) * (upperLength + lowerLength);
                output.legIkActive[side] = true;
                Quaternion foot = output.worldRot[c];
                Vector3 sa = pa, sb = pb, sc = pc;
                MmdIk.SolveTwoBone(ref sa, ref sb, ref sc, goal, pole, true);
                SetWorld(a, MmdQ.Normalize(Quaternion.FromToRotation(pb - pa, sb - sa) * output.worldRot[a]));
                SetWorld(b, MmdQ.Normalize(Quaternion.FromToRotation(
                    output.worldPos[c] - output.worldPos[b], sc - sb) * output.worldRot[b]));
                SetWorld(c, foot);
            }
        }
    }
}
