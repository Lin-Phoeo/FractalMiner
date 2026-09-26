// VmdCamera.cs — VMD camera track sampling and Unity camera driving.
// Derived from OedoSoldier/Endfield-Poser (AGPL-3.0) src/math/mmd_camera.h.
// Ported to C# for the Endfield offline Unity pipeline. No game dependencies.
//
// Coordinate notes (kept identical to Poser, which runs inside a Unity game):
//   * MMD camera keys: distance (mmd units, usually NEGATIVE for perspective),
//     target + Euler rotation (degrees, as stored in the file).
//   * Unity cameras look along their local +Z, so
//     position = target + rotation * (0, 0, distance) aims the camera at target.
//   * world basis maps MMD world axes onto the Unity scene (see Studio panel).
using System.Collections.Generic;
using UnityEngine;

namespace EndfieldShaderPack.EditorTools.Mmd
{
    public struct VmdCameraPose
    {
        public Vector3 position;
        public Quaternion rotation;
        public float fov;        // vertical FOV in degrees (perspective only)
        public bool perspective;
        public float orthoSize;  // half-height (orthographic only)
    }

    public struct VmdCameraSettings
    {
        public Vector3 origin;     // world-space follow origin (usually char root)
        public Quaternion basis;   // MMD world -> Unity world
        public Vector3 offset;     // extra target offset, Unity units
        public float scale;        // MMD unit -> Unity unit (same as retarget scale)
        public float distanceScale;
        public float fovOffset;
    }

    public static class VmdCameraTrack
    {
        /// <summary>
        /// Poser SampleCamera: per-channel Bezier mixing with hard-cut detection
        /// (adjacent keys = authored cut). Euler rotation is mixed LINEARLY, never
        /// slerped, so authored turns stay exact. Projection is a step track.
        /// </summary>
        public static VmdCameraKey SampleKey(List<VmdCameraKey> keys, double frame, bool cuts = true)
        {
            if (keys == null || keys.Count == 0)
                return new VmdCameraKey { distance = -45f, fov = 30f };
            int n = UpperC(keys, frame);
            if (n == 0) return keys[0];
            if (n == keys.Count) return keys[keys.Count - 1];
            var a = keys[n - 1];
            var b = keys[n];
            if (cuts && b.frame - a.frame == 1) return a;
            float t = (float)((frame - a.frame) / (double)(b.frame - a.frame));
            return new VmdCameraKey
            {
                frame = a.frame,
                distance = Mix(a.distance, b.distance, b.curves[4], t),
                fov = Mix(a.fov, b.fov, b.curves[5], t),
                target = new VVec3
                {
                    x = Mix(a.target.x, b.target.x, b.curves[0], t),
                    y = Mix(a.target.y, b.target.y, b.curves[1], t),
                    z = Mix(a.target.z, b.target.z, b.curves[2], t)
                },
                rotation = new VVec3
                {
                    x = Mix(a.rotation.x, b.rotation.x, b.curves[3], t),
                    y = Mix(a.rotation.y, b.rotation.y, b.curves[3], t),
                    z = Mix(a.rotation.z, b.rotation.z, b.curves[3], t)
                },
                curves = (VCurve[])a.curves.Clone(),
                perspective = a.perspective
            };
        }

        public static VmdCameraPose Sample(List<VmdCameraKey> keys, double frame,
            VmdCameraSettings settings, bool cuts = true)
        {
            return Place(SampleKey(keys, frame, cuts), settings);
        }

        /// <summary>Poser CameraOrbit: Q(Y,-ry) * Q(X,-rx) * Q(Z,-rz), degrees in.</summary>
        public static Quaternion OrbitDeg(Vector3 eulerDeg) =>
            Quaternion.Euler(0f, -eulerDeg.y, 0f)
            * Quaternion.Euler(-eulerDeg.x, 0f, 0f)
            * Quaternion.Euler(0f, 0f, -eulerDeg.z);

        /// <summary>Poser PlaceCamera: full key -> Unity camera pose.</summary>
        public static VmdCameraPose Place(VmdCameraKey key, VmdCameraSettings s)
        {
            float distance = key.distance * s.scale * Mathf.Clamp(s.distanceScale, 0.05f, 10f);
            Vector3 target = s.origin + s.basis *
                (new Vector3(key.target.x, key.target.y, key.target.z) * s.scale + s.offset);
            var pose = new VmdCameraPose
            {
                rotation = s.basis * OrbitDeg(new Vector3(key.rotation.x, key.rotation.y, key.rotation.z)),
                perspective = key.perspective,
                fov = Mathf.Clamp(key.fov + s.fovOffset, 1f, 179f)
            };
            pose.position = target + pose.rotation * new Vector3(0f, 0f, distance);
            if (!pose.perspective && distance > 1e-5f)
                pose.rotation = pose.rotation * Quaternion.Euler(0f, 180f, 0f);
            // MMD's orthographic vertical span is 25 units at distance 45.
            pose.orthoSize = Mathf.Max(0.001f, 25f * Mathf.Abs(distance) / 90f);
            return pose;
        }

        public static void Apply(Camera cam, VmdCameraPose pose)
        {
            if (cam == null) return;
            cam.transform.position = pose.position;
            cam.transform.rotation = pose.rotation;
            cam.orthographic = !pose.perspective;
            if (pose.perspective) cam.fieldOfView = pose.fov;
            else cam.orthographicSize = pose.orthoSize;
        }

        static float Mix(float a, float b, VCurve c, float t) => a + (b - a) * VmdBezier.Evaluate(c, t);

        static int UpperC(List<VmdCameraKey> keys, double frame)
        {
            int lo = 0, hi = keys.Count;
            while (lo < hi)
            {
                int mid = (lo + hi) / 2;
                if (frame < keys[mid].frame) hi = mid; else lo = mid + 1;
            }
            return lo;
        }
    }
}
