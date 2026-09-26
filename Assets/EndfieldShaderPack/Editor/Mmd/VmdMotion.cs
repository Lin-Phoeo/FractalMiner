// VmdMotion.cs — VMD (Vocaloid Motion Data) reader and time-domain sampling.
// Derived from OedoSoldier/Endfield-Poser (AGPL-3.0) src/math/mmd_motion.h.
// Ported to C# for the Endfield offline Unity pipeline. No game dependencies.
using System;
using System.Collections.Generic;
using System.Globalization;
using System.IO;
using System.Text;

namespace EndfieldShaderPack.EditorTools.Mmd
{
    // ---------- math ----------
    public struct VVec3 { public float x, y, z; }

    public struct VQuat
    {
        public float x, y, z, w;
        public static VQuat Identity => new VQuat { x = 0, y = 0, z = 0, w = 1 };

        public static VQuat Slerp(VQuat a, VQuat b, float t)
        {
            float dot = a.x * b.x + a.y * b.y + a.z * b.z + a.w * b.w;
            float bx = b.x, by = b.y, bz = b.z, bw = b.w;
            if (dot < 0f) { bx = -bx; by = -by; bz = -bz; bw = -bw; dot = -dot; }
            if (dot > 0.9995f)
            {
                return Normalize(new VQuat {
                    x = a.x + (bx - a.x) * t, y = a.y + (by - a.y) * t,
                    z = a.z + (bz - a.z) * t, w = a.w + (bw - a.w) * t });
            }
            float theta0 = (float)Math.Acos(Math.Min(1.0, Math.Max(-1.0, dot)));
            float sinT = (float)Math.Sin(t * theta0);
            float s0 = (float)Math.Sin((1 - t) * theta0) / (float)Math.Sin(theta0);
            float s1 = sinT / (float)Math.Sin(theta0);
            return Normalize(new VQuat {
                x = a.x * s0 + bx * s1, y = a.y * s0 + by * s1,
                z = a.z * s0 + bz * s1, w = a.w * s0 + bw * s1 });
        }

        public static VQuat Normalize(VQuat q)
        {
            float l = (float)Math.Sqrt(q.x * q.x + q.y * q.y + q.z * q.z + q.w * q.w);
            if (l < 1e-12f) return Identity;
            return new VQuat { x = q.x / l, y = q.y / l, z = q.z / l, w = q.w / l };
        }
    }

    // ---------- interpolation ----------
    public struct VCurve { public float x1, y1, x2, y2; }

    public static class VmdBezier
    {
        public static float Evaluate(VCurve c, float x)
        {
            x = Math.Max(0f, Math.Min(1f, x));
            if (x == 0f || x == 1f) return x;
            float B(float t, float a, float z)
            {
                float u = 1 - t;
                return 3 * u * u * t * a + 3 * u * t * t * z + t * t * t;
            }
            float lo = 0, hi = 1, t = x;
            for (int i = 0; i < 22; i++)
            {
                float bx = B(t, c.x1, c.x2);
                if (Math.Abs(bx - x) < 1e-6f) break;
                if (bx < x) lo = t; else hi = t;
                t = (lo + hi) * 0.5f;
            }
            return B(t, c.y1, c.y2);
        }
    }

    // ---------- keys ----------
    public struct VmdBoneKey
    {
        public uint frame;
        public VVec3 position;
        public VQuat rotation;
        public VCurve[] curves; // 4: posX, posY, posZ, rot
    }

    public struct VmdMorphKey { public uint frame; public float weight; }

    public struct VmdIkKey { public uint frame; public bool enabled; }

    public struct VmdCameraKey
    {
        public uint frame;
        public float distance, fov;
        public VVec3 target, rotation; // VMD Euler radians, NOT a bone quaternion
        public VCurve[] curves;        // 6: target XYZ, rotation, distance, FOV
        public bool perspective;
    }

    public struct VmdLocalPose { public VVec3 position; public VQuat rotation; }

    public enum VmdIkMode { FollowMotion, ForceOn, ForceOff }

    // ---------- clip ----------
    public class VmdMotionClip
    {
        public string model;
        public Dictionary<string, List<VmdBoneKey>> bones = new Dictionary<string, List<VmdBoneKey>>();
        public Dictionary<string, List<VmdMorphKey>> morphs = new Dictionary<string, List<VmdMorphKey>>();
        public Dictionary<string, List<VmdIkKey>> ik = new Dictionary<string, List<VmdIkKey>>();
        public List<VmdCameraKey> cameras = new List<VmdCameraKey>();
        public uint lastFrame;
        public long boneKeys, morphKeys;
        public List<string> warnings = new List<string>();

        public double Duration => lastFrame / 30.0;
        public bool Empty => bones.Count == 0 && morphs.Count == 0 && cameras.Count == 0;
    }

    // ---------- reader ----------
    public class VmdReader
    {
        readonly byte[] _bytes; int _offset;
        public VmdReader(byte[] bytes) { _bytes = bytes; }
        int Remaining => _bytes.Length - _offset;
        void Require(int n)
        {
            if (n > Remaining) throw new InvalidDataException("Truncated MMD file");
        }
        void Skip(int n) { Require(n); _offset += n; }
        public byte U8() { Require(1); return _bytes[_offset++]; }
        public uint U32() { Require(4); uint v = BitConverter.ToUInt32(_bytes, _offset); _offset += 4; return v; }
        public int I32() { Require(4); int v = BitConverter.ToInt32(_bytes, _offset); _offset += 4; return v; }
        public float F32()
        {
            Require(4);
            float f = BitConverter.ToSingle(_bytes, _offset); _offset += 4;
            if (!float.IsFinite(f)) throw new InvalidDataException("Non-finite MMD value");
            return f;
        }
        public VVec3 Vec()
        {
            float x = F32(), y = F32(), z = F32();
            if (Math.Abs(x) > 1e6f || Math.Abs(y) > 1e6f || Math.Abs(z) > 1e6f)
                throw new InvalidDataException("MMD vector exceeds supported range");
            return new VVec3 { x = x, y = y, z = z };
        }
        public VQuat Quat()
        {
            float x = F32(), y = F32(), z = F32(), w = F32();
            double len = Math.Sqrt((double)x * x + (double)y * y + (double)z * z + (double)w * w);
            if (len < 1e-12) return VQuat.Identity;
            return new VQuat { x = x / (float)len, y = y / (float)len, z = z / (float)len, w = w / (float)len };
        }
        public byte[] Raw(int n) { Require(n); var s = new byte[n]; Array.Copy(_bytes, _offset, s, 0, n); _offset += n; return s; }
        public string Fixed(int n, Encoding enc)
        {
            var s = Raw(n);
            int z = Array.IndexOf(s, (byte)0);
            if (z >= 0) { var t = new byte[z]; Array.Copy(s, t, z); s = t; }
            return enc.GetString(s);
        }
        public uint Count(int minSize, uint limit = 2000000)
        {
            uint n = U32();
            if (n > limit || (minSize > 0 && n > (uint)(Remaining / minSize)))
                throw new InvalidDataException("Invalid MMD record count");
            return n;
        }
    }

    public static class VmdName
    {
        /// <summary>Normalize full-width digits/I/K to ASCII, keep Japanese names.</summary>
        public static string Normalize(string s)
        {
            var from = "０１２３４５６７８９ＩＫ";
            var to = "0123456789IK";
            var sb = new StringBuilder(s);
            for (int i = 0; i < from.Length; i++)
                sb.Replace(from[i], to[i]);
            return sb.ToString();
        }
    }

    public static class Vmd
    {
        /// <summary>Parse a VMD file. decode: Shift-JIS (932) for old files, UTF-8/16 for newer.</summary>
        public static VmdMotionClip Read(byte[] bytes, Func<string, int, string> decode)
        {
            var r = new VmdReader(bytes);
            var c = new VmdMotionClip();
            var signature = Encoding.ASCII.GetString(r.Raw(30));
            bool old = signature.StartsWith("Vocaloid Motion Data file", StringComparison.Ordinal);
            if (!signature.StartsWith("Vocaloid Motion Data 0002", StringComparison.Ordinal) && !old)
                throw new InvalidDataException("Not a VMD 0002/file motion");
            c.model = r.Fixed(old ? 10 : 20, enc => decode(enc, 932));

            var n = r.Count(111);
            for (uint i = 0; i < n; i++)
            {
                var name = VmdName.Normalize(r.Fixed(15, enc => decode(enc, 932)));
                var k = new VmdBoneKey { frame = r.U32(), position = r.Vec(), rotation = r.Quat() };
                var curve = r.Raw(64);
                k.curves = new VCurve[4];
                for (int j = 0; j < 4; j++)
                    k.curves[j] = new VCurve {
                        x1 = Math.Min(1f, curve[j] / 127f),
                        y1 = Math.Min(1f, curve[j + 4] / 127f),
                        x2 = Math.Min(1f, curve[j + 8] / 127f),
                        y2 = Math.Min(1f, curve[j + 12] / 127f) };
                if (!string.IsNullOrEmpty(name))
                {
                    if (!c.bones.TryGetValue(name, out var list)) { list = new List<VmdBoneKey>(); c.bones[name] = list; }
                    list.Add(k);
                }
            }

            if (r.Remaining() > 0)
            {
                n = r.Count(23);
                for (uint i = 0; i < n; i++)
                {
                    var name = VmdName.Normalize(r.Fixed(15, enc => decode(enc, 932)));
                    var k = new VmdMorphKey { frame = r.U32(), weight = Math.Max(0f, Math.Min(1f, r.F32())) };
                    if (!string.IsNullOrEmpty(name))
                    {
                        if (!c.morphs.TryGetValue(name, out var list)) { list = new List<VmdMorphKey>(); c.morphs[name] = list; }
                        list.Add(k);
                    }
                }
            }

            if (r.Remaining() > 0)
            {
                n = r.Count(61);
                c.cameras = new List<VmdCameraKey>((int)n);
                for (uint i = 0; i < n; ++i)
                {
                    var k = new VmdCameraKey { frame = r.U32() };
                    k.distance = r.F32();
                    if (Math.Abs(k.distance) > 1e6f) throw new InvalidDataException("Camera distance exceeds supported range");
                    k.target = r.Vec();
                    k.rotation = r.Vec();
                    var curve = r.Raw(24);
                    k.curves = new VCurve[6];
                    for (int j = 0; j < 6; ++j)
                    {
                        // Camera bytes are x1,x2,y1,y2, unlike bone interpolation.
                        float U(int at) => Math.Min(1f, curve[j * 4 + at] / 127f);
                        k.curves[j] = new VCurve { x1 = U(0), x2 = U(2), y1 = U(1), y2 = U(3) };
                    }
                    uint angle = r.U32();
                    uint projection = r.U8();
                    if (angle < 1 || angle >= 180 || projection > 1)
                        throw new InvalidDataException("Invalid VMD camera projection/FOV");
                    k.fov = angle;
                    k.perspective = projection == 0;
                    c.cameras.Add(k);
                }
            }

            foreach (var section in new[] { (28, "Light tracks ignored"), (9, "Shadow tracks ignored") })
            {
                if (r.Remaining() <= 0) break;
                n = r.Count(section.Item1);
                if (n > 0) c.warnings.Add(section.Item2);
                r.Skip((int)(n * section.Item1));
            }

            if (r.Remaining() > 0)
            {
                n = r.Count(9, 1000000);
                for (uint i = 0; i < n; i++)
                {
                    uint f = r.U32();
                    r.U8();
                    var m = r.Count(21, 10000);
                    for (uint j = 0; j < m; j++)
                    {
                        var name = VmdName.Normalize(r.Fixed(20, enc => decode(enc, 932)));
                        bool on = r.U8() != 0;
                        if (!c.ik.TryGetValue(name, out var list)) { list = new List<VmdIkKey>(); c.ik[name] = list; }
                        list.Add(new VmdIkKey { frame = f, enabled = on });
                    }
                }
            }

            if (r.Remaining() > 0) c.warnings.Add("Trailing VMD extension ignored");
            Recount(c);
            return c;
        }

        static void SortKeys<T>(List<T> v, Func<T, uint> frame, Action<List<T>> dedup)
        {
            v.Sort((a, b) => frame(a).CompareTo(frame(b)));
            dedup(v);
        }

        static void Recount(VmdMotionClip c)
        {
            c.lastFrame = 0; c.boneKeys = 0; c.morphKeys = 0;
            var boneNames = new List<string>(c.bones.Keys);
            foreach (var name in boneNames)
            {
                var list = c.bones[name];
                SortKeys(list, k => k.frame, v => {
                    int n = 0;
                    for (int i = 0; i < v.Count; i++)
                    {
                        if (n > 0 && v[n - 1].frame == v[i].frame) v[n - 1] = v[i];
                        else v[n++] = v[i];
                    }
                    v.RemoveRange(n, v.Count - n);
                });
                if (list.Count > 0) c.lastFrame = Math.Max(c.lastFrame, list[list.Count - 1].frame);
                c.boneKeys += list.Count;
            }
            var morphNames = new List<string>(c.morphs.Keys);
            foreach (var name in morphNames)
            {
                var list = c.morphs[name];
                list.Sort((a, b) => a.frame.CompareTo(b.frame));
                if (list.Count > 0) c.lastFrame = Math.Max(c.lastFrame, list[list.Count - 1].frame);
                c.morphKeys += list.Count;
            }
            foreach (var kv in c.ik) kv.Value.Sort((a, b) => a.frame.CompareTo(b.frame));
            c.cameras.Sort((a, b) => a.frame.CompareTo(b.frame));
            if (c.cameras.Count > 0) c.lastFrame = Math.Max(c.lastFrame, c.cameras[c.cameras.Count - 1].frame);
        }

        static int Upper(List<VmdBoneKey> keys, double frame)
        {
            int lo = 0, hi = keys.Count;
            while (lo < hi) { int mid = (lo + hi) / 2; if (frame < keys[mid].frame) hi = mid; else lo = mid + 1; }
            return lo;
        }
        static int UpperM(List<VmdMorphKey> keys, double frame)
        {
            int lo = 0, hi = keys.Count;
            while (lo < hi) { int mid = (lo + hi) / 2; if (frame < keys[mid].frame) hi = mid; else lo = mid + 1; }
            return lo;
        }
        static int UpperI(List<VmdIkKey> keys, double frame)
        {
            int lo = 0, hi = keys.Count;
            while (lo < hi) { int mid = (lo + hi) / 2; if (frame < keys[mid].frame) hi = mid; else lo = mid + 1; }
            return lo;
        }

        public static VmdLocalPose SampleBone(List<VmdBoneKey> keys, double frame)
        {
            if (keys == null || keys.Count == 0)
                return new VmdLocalPose { position = new VVec3(), rotation = VQuat.Identity };
            int n = Upper(keys, frame);
            if (n == 0)
                return new VmdLocalPose { position = keys[0].position, rotation = keys[0].rotation };
            if (n == keys.Count)
                return new VmdLocalPose { position = keys[keys.Count - 1].position, rotation = keys[keys.Count - 1].rotation };
            var a = keys[n - 1]; var b = keys[n];
            float t = (float)((frame - a.frame) / (double)(b.frame - a.frame));
            return new VmdLocalPose {
                position = new VVec3 {
                    x = a.position.x + (b.position.x - a.position.x) * VmdBezier.Evaluate(b.curves[0], t),
                    y = a.position.y + (b.position.y - a.position.y) * VmdBezier.Evaluate(b.curves[1], t),
                    z = a.position.z + (b.position.z - a.position.z) * VmdBezier.Evaluate(b.curves[2], t) },
                rotation = VQuat.Slerp(a.rotation, b.rotation, VmdBezier.Evaluate(b.curves[3], t)) };
        }

        public static float SampleMorph(List<VmdMorphKey> keys, double frame)
        {
            if (keys == null || keys.Count == 0) return 0;
            int n = UpperM(keys, frame);
            if (n == 0) return keys[0].weight;
            if (n == keys.Count) return keys[keys.Count - 1].weight;
            var a = keys[n - 1]; var b = keys[n];
            return a.weight + (b.weight - a.weight) * (float)((frame - a.frame) / (double)(b.frame - a.frame));
        }

        public static bool SampleIk(VmdMotionClip clip, string name, double frame, VmdIkMode mode = VmdIkMode.FollowMotion)
        {
            if (mode != VmdIkMode.FollowMotion) return mode == VmdIkMode.ForceOn;
            if (!clip.ik.TryGetValue(name, out var list) || list.Count == 0) return true;
            int n = UpperI(list, frame);
            return n > 0 ? list[n - 1].enabled : true;
        }

        public static bool EyeBone(string n) => n == "両目" || n == "左目" || n == "右目";

        public static void AppendFace(VmdMotionClip to, VmdMotionClip from)
        {
            foreach (var kv in from.morphs) to.morphs[kv.Key] = kv.Value;
            foreach (var kv in from.bones)
                if (EyeBone(kv.Key)) to.bones[kv.Key] = kv.Value;
            Recount(to);
        }

        /// <summary>Read a VMD from disk with Shift-JIS decode fallback (standard MMD files).</summary>
        public static VmdMotionClip ReadFile(string path)
        {
            var bytes = File.ReadAllBytes(path);
            return Read(bytes, (s, cp) => Decode(s, cp));
        }

        static Encoding GetEncoding(int cp)
        {
            if (cp == 932) return Encoding.GetEncoding(932);
            if (cp == 65001) return Encoding.UTF8;
            return Encoding.GetEncoding(cp);
        }

        static string Decode(string s, int cp)
        {
            var enc = GetEncoding(cp);
            // Bytes were decoded by Fixed() already with wrong encoding; re-interpret.
            // Fixed() used enc.GetString, so here we only pass through for 932.
            return s;
        }
    }
}
