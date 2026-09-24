using UnityEngine;

namespace EndfieldShaderPack
{
    /// Builds the light-space box the official character shadow atlas uses.
    ///
    /// The construction is measured from the frame-6411 capture, not assumed. Every
    /// valid _CharacterWorldToShadow slot decomposes into an orthogonal basis that
    /// equals, to 4.3e-8 (float32 round-off of the captured values),
    ///   towardLight = -_CharacterShadowLightDir[i]
    ///   right       = normalize(cross(worldUp, towardLight))
    ///   up          = cross(towardLight, right)
    /// with row k = basis_k / extent_k and translation_k = -min_k / extent_k.
    ///
    /// Depth is reversed: z = 1 on the light side, so the atlas keeps the caster
    /// nearest the light and the official resolve's step(0, atlas - receiver) reads
    /// as "occluded". Two matrices are handed out because the official constant maps
    /// the box to [0,1]^3 (the resolve consumes shadowClip.xy directly as the atlas
    /// UV) while a rasteriser needs [-1,1] in x and y; z is already the D3D [0,1]
    /// depth range and is left alone.
    public static class EndfieldCharacterShadowProjection
    {
        public struct LightBox
        {
            public Vector3 right;
            public Vector3 up;
            public Vector3 towardLight;
            public Vector3 min;
            public Vector3 max;

            public Vector3 Extent { get { return max - min; } }

            public Vector3 Scale
            {
                get
                {
                    Vector3 e = Extent;
                    return new Vector3(1f / e.x, 1f / e.y, 1f / e.z);
                }
            }

            /// The box as [0,1]^3 light-space coordinates of a world point.
            public Vector3 Project(Vector3 worldPosition)
            {
                return new Vector3(
                    (Vector3.Dot(right, worldPosition) - min.x) * Scale.x,
                    (Vector3.Dot(up, worldPosition) - min.y) * Scale.y,
                    (Vector3.Dot(towardLight, worldPosition) - min.z) * Scale.z);
            }
        }

        public static Vector3 TowardLight(Vector3 lightTravelDirection)
        {
            Vector3 toward = -lightTravelDirection;
            if (toward.sqrMagnitude < 1e-12f)
                throw new System.ArgumentException("Degenerate light direction: " + lightTravelDirection);
            return toward.normalized;
        }

        public static void Basis(Vector3 towardLight, out Vector3 right, out Vector3 up)
        {
            // The measured basis has right.y == 0 exactly, so the reference axis is
            // worldUp. A light shining straight up or down degenerates that cross
            // product; worldForward is the fallback the official also has to make.
            Vector3 reference = Mathf.Abs(towardLight.y) > 0.999f ? Vector3.forward : Vector3.up;
            right = Vector3.Cross(reference, towardLight);
            if (right.sqrMagnitude < 1e-12f)
                throw new System.ArgumentException("Cannot build a light basis from " + towardLight);
            right.Normalize();
            up = Vector3.Cross(towardLight, right);
        }

        /// Fits the box around a world-space AABB. paddingFraction expands every axis
        /// by that fraction of its own extent, which keeps texel density independent
        /// of the character's world scale.
        public static LightBox Fit(Vector3 towardLight, Bounds worldBounds, float paddingFraction)
        {
            Basis(towardLight, out Vector3 right, out Vector3 up);
            var box = new LightBox
            {
                right = right,
                up = up,
                towardLight = towardLight,
                min = new Vector3(float.MaxValue, float.MaxValue, float.MaxValue),
                max = new Vector3(float.MinValue, float.MinValue, float.MinValue)
            };
            Vector3 center = worldBounds.center, extents = worldBounds.extents;
            for (int i = 0; i < 8; i++)
            {
                Vector3 corner = center + Vector3.Scale(extents, new Vector3(
                    (i & 1) * 2 - 1, ((i >> 1) & 1) * 2 - 1, ((i >> 2) & 1) * 2 - 1));
                var projected = new Vector3(
                    Vector3.Dot(right, corner), Vector3.Dot(up, corner), Vector3.Dot(towardLight, corner));
                box.min = Vector3.Min(box.min, projected);
                box.max = Vector3.Max(box.max, projected);
            }
            Vector3 pad = (box.max - box.min) * Mathf.Max(0f, paddingFraction);
            box.min -= pad;
            box.max += pad;
            if (Mathf.Min(Mathf.Min(box.Extent.x, box.Extent.y), box.Extent.z) <= 0f)
                throw new System.ArgumentException("Empty light box for bounds " + worldBounds);
            return box;
        }

        /// The official constant: box -> [0,1]^3, xy consumed directly as atlas UV.
        public static Matrix4x4 WorldToShadow(LightBox box)
        {
            Vector3 s = box.Scale;
            var m = new Matrix4x4();
            m.SetRow(0, Scaled(box.right, s.x, -box.min.x * s.x));
            m.SetRow(1, Scaled(box.up, s.y, -box.min.y * s.y));
            m.SetRow(2, Scaled(box.towardLight, s.z, -box.min.z * s.z));
            m.SetRow(3, new Vector4(0f, 0f, 0f, 1f));
            return m;
        }

        /// The same box for the rasteriser: x to [-1,1], z left in [0,1], and y negated.
        /// The negation is not cosmetic. A rasteriser puts clip.y = +1 at memory row 0,
        /// while Unity's sampler addresses memory row v*(H-1), so without the negation
        /// the resolve's atlasUV.v would read the vertically mirrored depth. Captured
        /// atlases instead arrive already mirrored by the importer, which is what
        /// FlipAtlasV compensates on the sampling side; a runtime atlas has no import
        /// step, so the compensation belongs here. The live median-error gate fails by
        /// O(0.5) instead of O(1e-4) if this ever regresses.
        public static Matrix4x4 WorldToShadowClip(LightBox box)
        {
            Matrix4x4 unit = WorldToShadow(box);
            Vector4 r0 = unit.GetRow(0), r1 = unit.GetRow(1);
            var m = new Matrix4x4();
            m.SetRow(0, new Vector4(r0.x * 2f, r0.y * 2f, r0.z * 2f, r0.w * 2f - 1f));
            m.SetRow(1, new Vector4(-r1.x * 2f, -r1.y * 2f, -r1.z * 2f, 1f - r1.w * 2f));
            m.SetRow(2, unit.GetRow(2));
            m.SetRow(3, unit.GetRow(3));
            return m;
        }

        /// Reads a matrix back into its box. The gates use it on the captured
        /// constants; the runtime uses it to assert its own output round-trips.
        public static LightBox Decompose(Matrix4x4 worldToShadow)
        {
            Vector4 r0 = worldToShadow.GetRow(0), r1 = worldToShadow.GetRow(1), r2 = worldToShadow.GetRow(2);
            Vector3 d0 = new Vector3(r0.x, r0.y, r0.z);
            Vector3 d1 = new Vector3(r1.x, r1.y, r1.z);
            Vector3 d2 = new Vector3(r2.x, r2.y, r2.z);
            float s0 = d0.magnitude, s1 = d1.magnitude, s2 = d2.magnitude;
            if (Mathf.Min(Mathf.Min(s0, s1), s2) < 1e-9f)
                throw new System.ArgumentException("Degenerate world-to-shadow matrix: " + worldToShadow);
            var box = new LightBox
            {
                right = d0 / s0,
                up = d1 / s1,
                towardLight = d2 / s2
            };
            box.min = new Vector3(-r0.w / s0, -r1.w / s1, -r2.w / s2);
            box.max = box.min + new Vector3(1f / s0, 1f / s1, 1f / s2);
            return box;
        }

        static Vector4 Scaled(Vector3 direction, float scale, float translation)
        {
            return new Vector4(direction.x * scale, direction.y * scale, direction.z * scale, translation);
        }
    }
}
