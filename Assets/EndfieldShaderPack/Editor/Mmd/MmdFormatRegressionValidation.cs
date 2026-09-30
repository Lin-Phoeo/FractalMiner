using System;
using System.IO;
using System.Text;
using UnityEngine;

namespace EndfieldShaderPack.EditorTools.Mmd
{
    public static class MmdFormatRegressionValidation
    {
        static void Fixed(BinaryWriter writer, string value, int size)
        {
            byte[] result = new byte[size];
            byte[] source = Encoding.ASCII.GetBytes(value);
            Array.Copy(source, result, Math.Min(source.Length, result.Length));
            writer.Write(result);
        }

        static void Header(BinaryWriter writer)
        {
            Fixed(writer, "Vocaloid Motion Data 0002", 30);
            Fixed(writer, "test", 20);
        }

        static VmdMotionClip Read(Action<BinaryWriter> records)
        {
            using (var stream = new MemoryStream())
            using (var writer = new BinaryWriter(stream))
            {
                Header(writer);
                records(writer);
                writer.Flush();
                return Vmd.Read(stream.ToArray(), _ => Encoding.UTF8);
            }
        }

        static void Near(float actual, float expected, string label, float tolerance = 1e-6f)
        {
            if (Mathf.Abs(actual - expected) > tolerance)
                throw new InvalidOperationException(label + ": expected " + expected + ", got " + actual);
        }

        static void ValidateBoneInterpolation()
        {
            var clip = Read(writer =>
            {
                writer.Write((uint)1);
                Fixed(writer, "bone", 15);
                writer.Write((uint)0);
                for (int i = 0; i < 3; ++i) writer.Write(0f);
                writer.Write(0f); writer.Write(0f); writer.Write(0f); writer.Write(1f);
                byte[] interpolation = new byte[64];
                for (int channel = 0; channel < 4; ++channel)
                {
                    int offset = channel * 16;
                    interpolation[offset] = (byte)(11 + channel * 10);
                    interpolation[offset + 4] = (byte)(12 + channel * 10);
                    interpolation[offset + 8] = (byte)(13 + channel * 10);
                    interpolation[offset + 12] = (byte)(14 + channel * 10);
                }
                writer.Write(interpolation);
            });
            var curves = clip.bones["bone"][0].curves;
            for (int channel = 0; channel < 4; ++channel)
            {
                Near(curves[channel].x1, (11 + channel * 10) / 127f, "bone x1 " + channel);
                Near(curves[channel].y1, (12 + channel * 10) / 127f, "bone y1 " + channel);
                Near(curves[channel].x2, (13 + channel * 10) / 127f, "bone x2 " + channel);
                Near(curves[channel].y2, (14 + channel * 10) / 127f, "bone y2 " + channel);
            }
        }

        static void ValidateCameraInterpolation()
        {
            var clip = Read(writer =>
            {
                writer.Write((uint)0); // bones
                writer.Write((uint)0); // morphs
                writer.Write((uint)1); // cameras
                writer.Write((uint)0); writer.Write(-45f);
                for (int i = 0; i < 6; ++i) writer.Write(0f);
                byte[] interpolation = new byte[24];
                for (int channel = 0; channel < 6; ++channel)
                {
                    int offset = channel * 4;
                    interpolation[offset] = (byte)(11 + channel * 10);
                    interpolation[offset + 1] = (byte)(12 + channel * 10);
                    interpolation[offset + 2] = (byte)(13 + channel * 10);
                    interpolation[offset + 3] = (byte)(14 + channel * 10);
                }
                writer.Write(interpolation);
                writer.Write((uint)30); writer.Write((byte)0);
            });
            for (int channel = 0; channel < 6; ++channel)
            {
                VCurve curve = clip.cameras[0].curves[channel];
                Near(curve.x1, (11 + channel * 10) / 127f, "camera x1 " + channel);
                Near(curve.x2, (12 + channel * 10) / 127f, "camera x2 " + channel);
                Near(curve.y1, (13 + channel * 10) / 127f, "camera y1 " + channel);
                Near(curve.y2, (14 + channel * 10) / 127f, "camera y2 " + channel);
            }
        }

        static void ValidateCameraRadians()
        {
            var key = new VmdCameraKey
            {
                distance = -45f,
                fov = 30f,
                perspective = true,
                rotation = new VVec3 { x = Mathf.PI * .5f }
            };
            var settings = new VmdCameraSettings
            {
                basis = Quaternion.identity,
                scale = 1f,
                distanceScale = 1f
            };
            Quaternion actual = VmdCameraTrack.Place(key, settings).rotation;
            Quaternion expected = Quaternion.Euler(-90f, 0f, 0f);
            Near(Quaternion.Angle(actual, expected), 0f, "camera radians", 1e-3f);
        }

        static void WriteBone(BinaryWriter writer, string name, uint frame, float x)
        {
            Fixed(writer, name, 15);
            writer.Write(frame);
            writer.Write(x); writer.Write(0f); writer.Write(0f);
            writer.Write(0f); writer.Write(0f); writer.Write(0f); writer.Write(1f);
            byte[] interpolation = new byte[64];
            for (int channel = 0; channel < 4; ++channel)
            {
                int offset = channel * 16;
                interpolation[offset] = interpolation[offset + 4] = 20;
                interpolation[offset + 8] = interpolation[offset + 12] = 107;
            }
            writer.Write(interpolation);
        }

        static void WriteCamera(BinaryWriter writer, uint frame, float distance)
        {
            writer.Write(frame); writer.Write(distance);
            for (int i = 0; i < 6; ++i) writer.Write(0f);
            byte[] interpolation = new byte[24];
            for (int channel = 0; channel < 6; ++channel)
            {
                int offset = channel * 4;
                interpolation[offset] = interpolation[offset + 2] = 20;
                interpolation[offset + 1] = interpolation[offset + 3] = 107;
            }
            writer.Write(interpolation);
            writer.Write((uint)30); writer.Write((byte)0);
        }

        static void ValidateStableDuplicateKeys()
        {
            var bones = Read(writer =>
            {
                writer.Write((uint)2);
                WriteBone(writer, "bone", 10, 1f);
                WriteBone(writer, "bone", 10, 2f);
            });
            if (bones.boneKeys != 1 || bones.bones["bone"].Count != 1)
                throw new InvalidOperationException("duplicate bone keys were not collapsed");
            Near(bones.bones["bone"][0].position.x, 2f, "duplicate bone last-wins");

            var morphs = Read(writer =>
            {
                writer.Write((uint)0);
                writer.Write((uint)2);
                Fixed(writer, "morph", 15); writer.Write((uint)10); writer.Write(.1f);
                Fixed(writer, "morph", 15); writer.Write((uint)10); writer.Write(.9f);
            });
            if (morphs.morphKeys != 1 || morphs.morphs["morph"].Count != 1)
                throw new InvalidOperationException("duplicate morph keys were not collapsed");
            Near(morphs.morphs["morph"][0].weight, .9f, "duplicate morph last-wins");

            var cameras = Read(writer =>
            {
                writer.Write((uint)0); writer.Write((uint)0); writer.Write((uint)2);
                WriteCamera(writer, 10, -10f);
                WriteCamera(writer, 10, -20f);
            });
            if (cameras.cameras.Count != 1)
                throw new InvalidOperationException("duplicate camera keys were not collapsed");
            Near(cameras.cameras[0].distance, -20f, "duplicate camera last-wins");
        }

        static void ValidateRootOffsetSpace()
        {
            Quaternion root = Quaternion.Euler(0f, 45.5f, 0f) * Quaternion.Euler(-90f, 0f, 0f);
            Vector3 wantedWorld = new Vector3(3f, 2f, -4f);
            Vector3 profileLocal = Quaternion.Inverse(root) * wantedWorld;
            Vector3 free = MmdPlayer.ResolveRootOffsetWorld(root, profileLocal, false, .25f);
            Near((free - new Vector3(3f, 2.25f, -4f)).magnitude, 0f, "root offset world", 1e-4f);
            Vector3 locked = MmdPlayer.ResolveRootOffsetWorld(root, profileLocal, true, .25f);
            Near((locked - new Vector3(0f, 2.25f, 0f)).magnitude, 0f, "root offset in-place", 1e-4f);
        }

        static void ValidateIkAndCameraDefaults()
        {
            var rig = MmdRigDefinition.StandardMmd();
            var evaluator = new MmdRigEvaluator();
            evaluator.Bind(rig, new VmdMotionClip());
            int leftIk = rig.Find("左足IK");
            if (evaluator.IkEnabled(leftIk, 0, VmdIkMode.FollowMotion))
                throw new InvalidOperationException("builtin FK-only clip unexpectedly enables leg IK");
            if (!evaluator.IkEnabled(leftIk, 0, VmdIkMode.ForceOn))
                throw new InvalidOperationException("ForceOn did not enable leg IK");

            VmdCameraKey fallback = VmdCameraTrack.SampleKey(null, 0);
            if (!fallback.perspective || fallback.curves == null || fallback.curves.Length != 6)
                throw new InvalidOperationException("empty camera fallback is not a safe perspective key");
        }

        static void ValidateIkRadianLimits()
        {
            const float limit = .2f;
            foreach (int order in new[] { MmdIk.EulerZXY, MmdIk.EulerXYZ, MmdIk.EulerYZX })
            foreach (float sign in new[] { -1f, 1f })
            {
                var input = Quaternion.AngleAxis(sign * .6f * Mathf.Rad2Deg, Vector3.right);
                var actual = MmdIk.LimitTotal(input, new Vector3(-limit, 0, 0),
                    new Vector3(limit, 0, 0), order, false);
                var expected = Quaternion.AngleAxis(sign * limit * Mathf.Rad2Deg, Vector3.right);
                Near(Quaternion.Angle(actual, expected), 0f, "IK radian clamp/order " + order, .05f);
                Near(Quaternion.Angle(Quaternion.identity, actual), limit * Mathf.Rad2Deg,
                    "IK radian magnitude/order " + order, .001f);
            }
        }

        public static void Run()
        {
            ValidateBoneInterpolation();
            ValidateCameraInterpolation();
            ValidateCameraRadians();
            ValidateStableDuplicateKeys();
            ValidateRootOffsetSpace();
            ValidateIkAndCameraDefaults();
            ValidateIkRadianLimits();
            Debug.Log("[MmdFormatRegression] PASS format, duplicates, root space, IK/camera defaults, six radian-limit cases");
        }
    }
}
