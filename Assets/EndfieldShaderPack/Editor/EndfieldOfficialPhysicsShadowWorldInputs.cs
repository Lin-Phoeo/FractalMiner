using System;
using System.IO;
using System.Security.Cryptography;
using System.Text;
using Newtonsoft.Json.Linq;
using Unity.Collections;
using Unity.Mathematics;
using UnityEngine;

namespace EndfieldShaderPack
{
    /// <summary>
    /// Shadow-only live world-proxy skinning and reset14 publication. This owns
    /// candidate NativeArrays but deliberately contains no solver or bone writer.
    /// </summary>
    public sealed class EndfieldOfficialPhysicsShadowWorldInputs : IDisposable
    {
        readonly EndfieldOfficialPhysicsShadowInputs transforms;
        NativeArray<float3> localPositions;
        NativeArray<float3> localNormals;
        NativeArray<float3> localTangents;
        NativeArray<float4x4> bindposes;
        NativeArray<float3> sealedRestPositions;
        NativeArray<quaternion> sealedRestRotations;
        NativeArray<double3> worldPositions;
        NativeArray<quaternion> worldRotations;
        NativeArray<double3> nextPositions;
        NativeArray<double3> oldPositions;
        NativeArray<quaternion> oldRotations;
        NativeArray<double3> basePositions;
        NativeArray<quaternion> baseRotations;
        NativeArray<double3> oldAnimationPositions;
        NativeArray<quaternion> oldAnimationRotations;
        NativeArray<double3> velocityPositions;
        NativeArray<double3> displayPositions;
        NativeArray<float3> velocities;
        NativeArray<float3> realVelocities;
        NativeArray<float> frictions;
        NativeArray<float> staticFrictions;
        NativeArray<float3> collisionNormals;
        bool disposed;

        EndfieldOfficialPhysicsShadowWorldInputs(
            EndfieldOfficialPhysicsShadowInputs transforms,
            float3[] localPositions,
            float3[] localNormals,
            float3[] localTangents,
            float4x4[] bindposes,
            float3[] sealedRestPositions,
            quaternion[] sealedRestRotations)
        {
            this.transforms = transforms;
            try
            {
                this.localPositions = CopyPersistent(localPositions);
                this.localNormals = CopyPersistent(localNormals);
                this.localTangents = CopyPersistent(localTangents);
                this.bindposes = CopyPersistent(bindposes);
                this.sealedRestPositions = CopyPersistent(sealedRestPositions);
                this.sealedRestRotations = CopyPersistent(sealedRestRotations);
                int count = localPositions.Length;
                worldPositions = New<double3>(count);
                worldRotations = New<quaternion>(count);
                nextPositions = New<double3>(count);
                oldPositions = New<double3>(count);
                oldRotations = New<quaternion>(count);
                basePositions = New<double3>(count);
                baseRotations = New<quaternion>(count);
                oldAnimationPositions = New<double3>(count);
                oldAnimationRotations = New<quaternion>(count);
                velocityPositions = New<double3>(count);
                displayPositions = New<double3>(count);
                velocities = New<float3>(count);
                realVelocities = New<float3>(count);
                frictions = New<float>(count);
                staticFrictions = New<float>(count);
                collisionNormals = New<float3>(count);
            }
            catch
            {
                DisposeArrays();
                throw;
            }
        }

        public int ProxyCapacity => worldPositions.IsCreated ? worldPositions.Length : 0;
        public int ParticleCapacity => nextPositions.IsCreated ? nextPositions.Length : 0;
        public int LastWorldWrites { get; private set; }
        public int LastResetFieldWrites { get; private set; }
        public bool ShadowOnly => true;
        public bool SolverExecuted => false;
        public bool SolverOutputsWritten => false;

        static NativeArray<T> New<T>(int count) where T : struct =>
            new NativeArray<T>(count, Allocator.Persistent, NativeArrayOptions.UninitializedMemory);

        static NativeArray<T> CopyPersistent<T>(T[] source) where T : struct
        {
            var result = New<T>(source.Length);
            result.CopyFrom(source);
            return result;
        }

        static void Require(bool condition, string message)
        {
            if (!condition) throw new InvalidOperationException(message);
        }

        static string ReadSealedText(string path, string expectedSha256)
        {
            Require(!string.IsNullOrWhiteSpace(path), "Missing sealed input path");
            Require(expectedSha256 != null && expectedSha256.Length == 64 &&
                    expectedSha256 == expectedSha256.ToLowerInvariant(),
                "Require lowercase SHA256 seal");
            byte[] bytes = File.ReadAllBytes(Path.GetFullPath(path));
            string actual;
            using (var sha = SHA256.Create())
                actual = BitConverter.ToString(sha.ComputeHash(bytes)).Replace("-", "").ToLowerInvariant();
            Require(actual == expectedSha256, "Sealed input SHA256 mismatch: " + path);
            return new UTF8Encoding(false, true).GetString(bytes).TrimStart('\ufeff');
        }

        static JArray Array(JToken token, int count, string label)
        {
            var value = token as JArray;
            Require(value != null && value.Count == count, "Invalid " + label);
            return value;
        }

        static int Integer(JToken token, string label)
        {
            Require(token != null && token.Type == JTokenType.Integer, "Invalid integer " + label);
            return token.Value<int>();
        }

        static float Single(JToken token, string label)
        {
            Require(token != null && (token.Type == JTokenType.Float || token.Type == JTokenType.Integer),
                "Invalid Single " + label);
            float value = token.Value<float>();
            Require(math.isfinite(value), "Nonfinite Single " + label);
            return value;
        }

        static float3 Float3(JToken token, string label)
        {
            JArray value = Array(token, 3, label);
            return new float3(Single(value[0], label), Single(value[1], label), Single(value[2], label));
        }

        static float4 Float4(JToken token, string label)
        {
            JArray value = Array(token, 4, label);
            return new float4(
                Single(value[0], label), Single(value[1], label),
                Single(value[2], label), Single(value[3], label));
        }

        static float4x4 Float4x4(JToken token, string label)
        {
            JArray columns = Array(token, 4, label);
            return new float4x4(
                Float4(columns[0], label + ".c0"), Float4(columns[1], label + ".c1"),
                Float4(columns[2], label + ".c2"), Float4(columns[3], label + ".c3"));
        }

        static float4x4 Float4x4(Matrix4x4 value) => new float4x4(
            Float4(value.GetColumn(0)), Float4(value.GetColumn(1)),
            Float4(value.GetColumn(2)), Float4(value.GetColumn(3)));

        static float4 Float4(Vector4 value) => new float4(value.x, value.y, value.z, value.w);

        public static EndfieldOfficialPhysicsShadowWorldInputs Load(
            EndfieldOfficialPhysicsShadowInputs transforms,
            string importsPath,
            string importsSha256)
        {
            if (transforms == null) throw new ArgumentNullException(nameof(transforms));
            JObject document = JObject.Parse(ReadSealedText(importsPath, importsSha256));
            Require(Integer(document["schema_version"], "schema_version") == 1 &&
                    document["selection_attributes_generated"]?.Value<bool>() == false &&
                    document["full_proxy_inputs_generated"]?.Value<bool>() == false &&
                    document["native_arrays_published"]?.Value<bool>() == false &&
                    document["official_solver_integrated"]?.Value<bool>() == false &&
                    document["original_runtime_executed"]?.Value<bool>() == false &&
                    document["stage_modified"]?.Value<bool>() == false,
                "Imports document boundary flags changed");
            JArray states = document["states"] as JArray;
            Require(states != null && states.Count == 2, "Imports document must contain two sealed reference states");
            JObject state = states[0] as JObject;
            Require(state != null && state["name"]?.Value<string>() == "serialized-rest",
                "First imports state must be serialized-rest");
            JArray groups = state["groups"] as JArray;
            Require(groups != null && groups.Count == transforms.GroupCount,
                "Imports group count differs from live layout");

            var positions = new float3[140];
            var normals = new float3[140];
            var tangents = new float3[140];
            var matrices = new float4x4[140];
            var restPositions = new float3[140];
            var restRotations = new quaternion[140];
            int written = 0;
            for (int groupIndex = 0; groupIndex < groups.Count; groupIndex++)
            {
                JObject group = groups[groupIndex] as JObject;
                Require(group != null && group["name"]?.Value<string>() == transforms.GroupName(groupIndex),
                    "Imports/live group order mismatch at " + groupIndex);
                int count = Integer(group["skin_bone_count"], "skin_bone_count");
                Require(count == transforms.GroupSkinCount(groupIndex),
                    "Imports/live skin count mismatch: " + transforms.GroupName(groupIndex));
                JObject vertices = group["vertices"] as JObject;
                JObject frames = vertices?["frames"] as JObject;
                Require(vertices != null && frames != null, "Missing imported vertex frames");
                JArray framePositions = Array(frames["positions"], count, "frame positions");
                JArray frameNormals = Array(frames["normals"], count, "frame normals");
                JArray frameTangents = Array(frames["tangents"], count, "frame tangents");
                JArray weights = Array(vertices["bone_weights"], count, "bone weights");
                JArray bindposeColumns = Array(vertices["skin_bone_bindposes"], count, "bindposes");
                JArray snapshots = Array(group["snapshots"], count + 1, "snapshots");
                for (int local = 0; local < count; local++)
                {
                    JObject weight = weights[local] as JObject;
                    JArray lanes = weight?["weights"] as JArray;
                    JArray indices = weight?["bone_indices"] as JArray;
                    Require(weight != null && lanes != null && indices != null &&
                            lanes.Count == 4 && indices.Count == 4 &&
                            Single(lanes[0], "weight0") == 1f && Single(lanes[1], "weight1") == 0f &&
                            Single(lanes[2], "weight2") == 0f && Single(lanes[3], "weight3") == 0f &&
                            Integer(indices[0], "bone index0") == local,
                        "Candidate live world path requires sealed one-hot bone weights");
                    int global = written + local;
                    positions[global] = Float3(framePositions[local], "frame position");
                    normals[global] = Float3(frameNormals[local], "frame normal");
                    tangents[global] = Float3(frameTangents[local], "frame tangent");
                    matrices[global] = Float4x4(bindposeColumns[local], "bindpose");
                    JObject snapshot = snapshots[local] as JObject;
                    Require(snapshot != null, "Invalid snapshot");
                    restPositions[global] = Float3(snapshot["position"], "snapshot position");
                    float4 restRotation = Float4(snapshot["rotation"], "snapshot rotation");
                    restRotations[global] = new quaternion(restRotation);
                }
                written += count;
            }
            Require(written == 140, "Imports must fill exactly 140 proxy vertices");
            return new EndfieldOfficialPhysicsShadowWorldInputs(
                transforms, positions, normals, tangents, matrices, restPositions, restRotations);
        }

        static float4 Multiply(float4x4 matrix, float4 vector)
        {
            float4 first = matrix.c0 * vector.x;
            float4 second = matrix.c1 * vector.y;
            float4 sum01 = first + second;
            float4 third = matrix.c2 * vector.z;
            float4 sum012 = sum01 + third;
            float4 fourth = matrix.c3 * vector.w;
            return sum012 + fourth;
        }

        static float3 Cross(float3 left, float3 right) => new float3(
            left.y * right.z - left.z * right.y,
            left.z * right.x - left.x * right.z,
            left.x * right.y - left.y * right.x);

        static float NormalizationScale(float3 value)
        {
            float yx = value.y * value.y + value.x * value.x;
            float norm = yx + value.z * value.z;
            Require(math.isfinite(norm) && norm > 0f, "Degenerate proxy frame vector");
            return 1f / math.sqrt(norm);
        }

        static float NormalizationScale(float4 value)
        {
            float yx = value.y * value.y + value.x * value.x;
            float z = yx + value.z * value.z;
            float norm = z + value.w * value.w;
            Require(math.isfinite(norm) && norm > 0f, "Degenerate proxy quaternion");
            return 1f / math.sqrt(norm);
        }

        static float Signed(float value, uint flip) => math.asfloat(math.asuint(value) ^ flip);

        static quaternion MatrixQuaternion(float3 u, float3 v, float3 w)
        {
            const uint sign = 0x80000000u;
            uint uSign = math.asuint(u.x) & sign;
            float t = v.y + Signed(w.z, uSign);
            uint tSign = math.asuint(t) & sign;
            uint uMask = uSign != 0 ? uint.MaxValue : 0u;
            uint tMask = tSign != 0 ? uint.MaxValue : 0u;
            var basis = new uint4(0u, sign, sign, sign);
            var uFlips = new uint4(0u, sign, 0u, sign);
            var tFlips = new uint4(sign, sign, sign, 0u);
            uint4 flips = basis ^ (uMask & uFlips) ^ (tMask & tFlips);
            var left = new float4(1f + math.abs(u.x), u.y, w.x, v.z);
            var right = new float4(t, v.x, u.z, w.y);
            var value = new float4(
                left.x + Signed(right.x, flips.x), left.y + Signed(right.y, flips.y),
                left.z + Signed(right.z, flips.z), left.w + Signed(right.w, flips.w));
            if (uSign != 0) value = new float4(value.z, value.w, value.x, value.y);
            if (tSign == 0) value = new float4(value.w, value.z, value.y, value.x);
            return new quaternion(value * NormalizationScale(value));
        }

        static quaternion RotationFromNormalTangent(float3 normal, float3 tangent)
        {
            float3 right = Cross(normal, tangent);
            right *= NormalizationScale(right);
            return MatrixQuaternion(right, Cross(tangent, right), tangent);
        }

        void ThrowIfDisposed()
        {
            if (disposed) throw new ObjectDisposedException(nameof(EndfieldOfficialPhysicsShadowWorldInputs));
        }

        public void PublishCurrentWorldProxyAndReset()
        {
            ThrowIfDisposed();
            LastWorldWrites = 0;
            LastResetFieldWrites = 0;
            int proxy = 0;
            for (int groupIndex = 0; groupIndex < transforms.GroupCount; groupIndex++)
            {
                int transformStart = transforms.GroupTransformStart(groupIndex);
                int count = transforms.GroupSkinCount(groupIndex);
                for (int local = 0; local < count; local++, proxy++)
                {
                    float4x4 bound = bindposes[proxy];
                    float4x4 current = Float4x4(transforms.TransformSlot(transformStart + local).localToWorldMatrix);
                    float4 boundPosition = Multiply(bound, new float4(localPositions[proxy], 1f));
                    float4 boundNormal = Multiply(bound, new float4(localNormals[proxy], 0f));
                    float4 boundTangent = Multiply(bound, new float4(localTangents[proxy], 0f));
                    float4 position = Multiply(current, boundPosition);
                    float4 normal4 = Multiply(current, boundNormal);
                    float4 tangent4 = Multiply(current, boundTangent);
                    float3 normal = normal4.xyz * NormalizationScale(normal4.xyz);
                    float3 tangent = tangent4.xyz * NormalizationScale(tangent4.xyz);
                    worldPositions[proxy] = new double3(position.x, position.y, position.z);
                    worldRotations[proxy] = RotationFromNormalTangent(normal, tangent);
                    LastWorldWrites++;
                }
            }
            Require(proxy == ProxyCapacity, "World proxy publication did not fill the candidate capacity");
            for (int index = 0; index < ParticleCapacity; index++)
            {
                double3 position = worldPositions[index];
                quaternion rotation = worldRotations[index];
                nextPositions[index] = position;
                oldPositions[index] = position;
                oldRotations[index] = rotation;
                basePositions[index] = position;
                baseRotations[index] = rotation;
                oldAnimationPositions[index] = position;
                oldAnimationRotations[index] = rotation;
                velocityPositions[index] = position;
                displayPositions[index] = position;
                velocities[index] = float3.zero;
                realVelocities[index] = float3.zero;
                frictions[index] = 0f;
                staticFrictions[index] = 0f;
                collisionNormals[index] = float3.zero;
                LastResetFieldWrites += 14;
            }
        }

        public Vector3[] CopyWorldPositions()
        {
            ThrowIfDisposed();
            var result = new Vector3[worldPositions.Length];
            for (int index = 0; index < result.Length; index++)
            {
                double3 value = worldPositions[index];
                result[index] = new Vector3((float)value.x, (float)value.y, (float)value.z);
            }
            return result;
        }

        public Quaternion[] CopyWorldRotations()
        {
            ThrowIfDisposed();
            var result = new Quaternion[worldRotations.Length];
            for (int index = 0; index < result.Length; index++)
            {
                float4 value = worldRotations[index].value;
                result[index] = new Quaternion(value.x, value.y, value.z, value.w);
            }
            return result;
        }

        public float MaxResetError()
        {
            ThrowIfDisposed();
            double maximum = 0.0;
            for (int index = 0; index < ParticleCapacity; index++)
            {
                double3 position = worldPositions[index];
                quaternion rotation = worldRotations[index];
                foreach (double3 value in new[]
                         {
                             nextPositions[index], oldPositions[index], basePositions[index],
                             oldAnimationPositions[index], velocityPositions[index], displayPositions[index]
                         })
                    maximum = math.max(maximum, math.cmax(math.abs(value - position)));
                foreach (quaternion value in new[]
                         { oldRotations[index], baseRotations[index], oldAnimationRotations[index] })
                    maximum = math.max(maximum, math.cmax(math.abs(value.value - rotation.value)));
                maximum = math.max(maximum, math.cmax(math.abs(velocities[index])));
                maximum = math.max(maximum, math.cmax(math.abs(realVelocities[index])));
                maximum = math.max(maximum, math.abs(frictions[index]));
                maximum = math.max(maximum, math.abs(staticFrictions[index]));
                maximum = math.max(maximum, math.cmax(math.abs(collisionNormals[index])));
            }
            return (float)maximum;
        }

        static JArray ReferenceState(string path, string sha256)
        {
            JObject document = JObject.Parse(ReadSealedText(path, sha256));
            Require(Integer(document["schema_version"], "reference schema_version") == 1 &&
                    document["candidate_global_world_reset_generated"]?.Value<bool>() == true &&
                    Integer(document["state_count"], "state_count") == 2 &&
                    Integer(document["team_count"], "team_count") == 11 &&
                    Integer(document["proxy_capacity"], "proxy_capacity") == 140 &&
                    Integer(document["particle_capacity"], "particle_capacity") == 140 &&
                    document["changing_animation_verified"]?.Value<bool>() == false &&
                    document["native_arrays_published"]?.Value<bool>() == false &&
                    document["official_solver_integrated"]?.Value<bool>() == false &&
                    document["original_runtime_executed"]?.Value<bool>() == false &&
                    document["stage_modified"]?.Value<bool>() == false,
                "Global reference boundary flags changed");
            JArray states = document["states"] as JArray;
            Require(states != null && states.Count == 2 &&
                    states[0]["name"]?.Value<string>() == "serialized-rest",
                "Global reference first state must be serialized-rest");
            return states;
        }

        public float MaxSealedReferencePositionError(string path, string sha256)
        {
            ThrowIfDisposed();
            JArray expected = Array(ReferenceState(path, sha256)[0]["proxy_world_positions"], 140,
                "reference positions");
            float maximum = 0f;
            for (int index = 0; index < ProxyCapacity; index++)
            {
                float3 reference = Float3(expected[index], "reference position");
                maximum = math.max(maximum, math.distance(sealedRestPositions[index], reference));
            }
            return maximum;
        }

        public float MaxSealedReferenceRotationError(string path, string sha256)
        {
            ThrowIfDisposed();
            JArray expected = Array(ReferenceState(path, sha256)[0]["proxy_world_rotations"], 140,
                "reference rotations");
            float maximum = 0f;
            for (int index = 0; index < ProxyCapacity; index++)
            {
                float4 reference = Float4(expected[index], "reference rotation");
                float4 value = sealedRestRotations[index].value;
                maximum = Mathf.Max(maximum, Quaternion.Angle(
                    new Quaternion(value.x, value.y, value.z, value.w),
                    new Quaternion(reference.x, reference.y, reference.z, reference.w)));
            }
            return maximum;
        }

        public float MaxLiveTransformPositionError()
        {
            ThrowIfDisposed();
            float maximum = 0f;
            int proxy = 0;
            for (int groupIndex = 0; groupIndex < transforms.GroupCount; groupIndex++)
            {
                int transformStart = transforms.GroupTransformStart(groupIndex);
                int count = transforms.GroupSkinCount(groupIndex);
                for (int local = 0; local < count; local++, proxy++)
                {
                    double3 value = worldPositions[proxy];
                    Vector3 expected = transforms.TransformSlot(transformStart + local).position;
                    maximum = Mathf.Max(maximum, Vector3.Distance(
                        new Vector3((float)value.x, (float)value.y, (float)value.z), expected));
                }
            }
            Require(proxy == ProxyCapacity, "Live position comparison did not cover all proxies");
            return maximum;
        }

        public float MaxLiveTransformRotationError()
        {
            ThrowIfDisposed();
            float maximum = 0f;
            int proxy = 0;
            for (int groupIndex = 0; groupIndex < transforms.GroupCount; groupIndex++)
            {
                int transformStart = transforms.GroupTransformStart(groupIndex);
                int count = transforms.GroupSkinCount(groupIndex);
                for (int local = 0; local < count; local++, proxy++)
                {
                    float4 value = worldRotations[proxy].value;
                    maximum = Mathf.Max(maximum, Quaternion.Angle(
                        new Quaternion(value.x, value.y, value.z, value.w),
                        transforms.TransformSlot(transformStart + local).rotation));
                }
            }
            Require(proxy == ProxyCapacity, "Live rotation comparison did not cover all proxies");
            return maximum;
        }

        void DisposeArrays()
        {
            if (localPositions.IsCreated) localPositions.Dispose();
            if (localNormals.IsCreated) localNormals.Dispose();
            if (localTangents.IsCreated) localTangents.Dispose();
            if (bindposes.IsCreated) bindposes.Dispose();
            if (sealedRestPositions.IsCreated) sealedRestPositions.Dispose();
            if (sealedRestRotations.IsCreated) sealedRestRotations.Dispose();
            if (worldPositions.IsCreated) worldPositions.Dispose();
            if (worldRotations.IsCreated) worldRotations.Dispose();
            if (nextPositions.IsCreated) nextPositions.Dispose();
            if (oldPositions.IsCreated) oldPositions.Dispose();
            if (oldRotations.IsCreated) oldRotations.Dispose();
            if (basePositions.IsCreated) basePositions.Dispose();
            if (baseRotations.IsCreated) baseRotations.Dispose();
            if (oldAnimationPositions.IsCreated) oldAnimationPositions.Dispose();
            if (oldAnimationRotations.IsCreated) oldAnimationRotations.Dispose();
            if (velocityPositions.IsCreated) velocityPositions.Dispose();
            if (displayPositions.IsCreated) displayPositions.Dispose();
            if (velocities.IsCreated) velocities.Dispose();
            if (realVelocities.IsCreated) realVelocities.Dispose();
            if (frictions.IsCreated) frictions.Dispose();
            if (staticFrictions.IsCreated) staticFrictions.Dispose();
            if (collisionNormals.IsCreated) collisionNormals.Dispose();
        }

        public void Dispose()
        {
            if (disposed) return;
            DisposeArrays();
            disposed = true;
        }
    }
}
