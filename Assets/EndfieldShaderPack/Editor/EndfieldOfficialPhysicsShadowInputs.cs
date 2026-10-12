using System;
using System.Collections.Generic;
using System.Globalization;
using System.IO;
using System.Security.Cryptography;
using System.Text;
using Unity.Collections;
using Unity.Mathematics;
using UnityEngine;

namespace EndfieldShaderPack
{
    /// <summary>
    /// Read-only bridge from sealed candidate identities/layout to live Unity getters.
    /// It publishes current transform inputs into owned NativeArrays but deliberately
    /// contains no solver and never writes a simulated pose back to the character.
    /// </summary>
    public sealed class EndfieldOfficialPhysicsShadowInputs : IDisposable
    {
        [Serializable]
        sealed class BindingNode
        {
            public string id;
            public long path_id;
            public string name;
            public long parent_path_id;
            public string[] hierarchy_names;
            public float[] local_position;
            public float[] local_rotation_xyzw;
            public float[] local_scale;
        }

        [Serializable]
        sealed class BindingDocument
        {
            public int schema_version;
            public int transform_count;
            public BindingNode[] transforms;
        }

        [Serializable]
        sealed class IdentityGroup
        {
            public string name;
            public string component_identity;
            public string ordinary_render_identity;
            public string[] ordered_transform_identities;
            public int skin_bone_count;
            public int render_transform_index;
            public int[] snapshot_parent_indices;
            public int[] skin_parent_indices;
            public int[] root_indices;
        }

        [Serializable]
        sealed class IdentityDocument
        {
            public int schema_version;
            public IdentityGroup[] groups;
            public bool runtime_instance_ids_generated;
            public bool world_getters_generated;
            public bool selection_attributes_generated;
            public bool full_proxy_inputs_generated;
            public bool native_arrays_published;
            public bool game_build_route_observed;
            public bool unity_backend_modified;
        }

        [Serializable]
        sealed class Chunk
        {
            public int start;
            public int count;
        }

        [Serializable]
        sealed class LayoutTeam
        {
            public int team_id;
            public string name;
            public string component_identity;
            public Chunk proxy_transform;
            public Chunk proxy_common;
            public Chunk proxy_mesh;
            public Chunk proxy_skin_bone;
            public Chunk baseline;
            public Chunk baseline_data;
            public Chunk particle;
            public Chunk distance_start;
            public Chunk distance_data;
        }

        [Serializable]
        sealed class CandidateFlags
        {
            public int add_team;
            public int enabled_reset;
            public int supplied_running_step;
        }

        [Serializable]
        sealed class LayoutDocument
        {
            public int schema_version;
            public int[] team_ids;
            public string team_id_policy;
            public string arena_policy;
            public string[] supported_core_arenas;
            public bool unsupported_team_chunks_omitted;
            public CandidateFlags candidate_flags;
            public LayoutTeam[] teams;
            public bool fresh_candidate_core_layout_generated;
            public bool state_topology_invariant;
            public bool original_runtime_team_ids_observed;
            public bool original_runtime_chunks_observed;
            public bool native_arrays_published;
            public bool official_solver_integrated;
            public bool original_runtime_executed;
            public bool stage_modified;
        }

        readonly struct ParticleWindow
        {
            public readonly short teamId;
            public readonly int start;
            public readonly int count;

            public ParticleWindow(short teamId, int start, int count)
            {
                this.teamId = teamId;
                this.start = start;
                this.count = count;
            }
        }

        readonly Transform[] transformSlots;
        readonly ParticleWindow[] particleWindows;
        readonly GameObject[] ownedShadowObjects;
        NativeArray<float4x4> transformMatrices;
        NativeArray<int> transformInstanceIds;
        NativeArray<int> transformParentInstanceIds;
        NativeArray<short> particleTeamIds;
        bool disposed;

        EndfieldOfficialPhysicsShadowInputs(
            Transform[] transformSlots,
            ParticleWindow[] particleWindows,
            int particleCapacity,
            int groupCount,
            int resolvedSkinSlotCount,
            int positiveWeightedSlotCount,
            int shadowRenderProxyCount,
            int shadowHelperProxyCount,
            int structuralAliasCount,
            GameObject[] ownedShadowObjects)
        {
            this.transformSlots = transformSlots;
            this.particleWindows = particleWindows;
            this.ownedShadowObjects = ownedShadowObjects;
            GroupCount = groupCount;
            ResolvedSkinSlotCount = resolvedSkinSlotCount;
            PositiveWeightedSlotCount = positiveWeightedSlotCount;
            ShadowRenderProxyCount = shadowRenderProxyCount;
            ShadowHelperProxyCount = shadowHelperProxyCount;
            StructuralAliasCount = structuralAliasCount;
            transformMatrices = new NativeArray<float4x4>(
                transformSlots.Length, Allocator.Persistent, NativeArrayOptions.UninitializedMemory);
            transformInstanceIds = new NativeArray<int>(
                transformSlots.Length, Allocator.Persistent, NativeArrayOptions.UninitializedMemory);
            transformParentInstanceIds = new NativeArray<int>(
                transformSlots.Length, Allocator.Persistent, NativeArrayOptions.UninitializedMemory);
            particleTeamIds = new NativeArray<short>(
                particleCapacity, Allocator.Persistent, NativeArrayOptions.UninitializedMemory);
        }

        public int GroupCount { get; }
        public int ResolvedSkinSlotCount { get; }
        public int PositiveWeightedSlotCount { get; }
        public int ShadowRenderProxyCount { get; }
        public int ShadowHelperProxyCount { get; }
        public int StructuralAliasCount { get; }
        public int ShadowProxyCount => ownedShadowObjects.Length;
        public int TransformCapacity => transformSlots.Length;
        public int ParticleCapacity => particleTeamIds.IsCreated ? particleTeamIds.Length : 0;
        public int LastTransformWrites { get; private set; }
        public int LastParticleTeamWrites { get; private set; }
        public bool ShadowOnly => true;
        public bool SolverExecuted => false;
        public bool SolverOutputsWritten => false;
        public Transform[] ResolvedTransforms => (Transform[])transformSlots.Clone();

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
            return Encoding.UTF8.GetString(bytes);
        }

        static Dictionary<string, BindingNode> IndexBindings(BindingDocument document)
        {
            Require(document != null && document.schema_version == 1 && document.transforms != null &&
                    document.transform_count == document.transforms.Length,
                "Invalid binding document");
            var result = new Dictionary<string, BindingNode>(StringComparer.Ordinal);
            foreach (BindingNode node in document.transforms)
            {
                Require(node != null && !string.IsNullOrEmpty(node.id) && node.path_id != 0 &&
                        !string.IsNullOrEmpty(node.name) && node.hierarchy_names != null &&
                        node.hierarchy_names.Length > 0 &&
                        node.hierarchy_names[node.hierarchy_names.Length - 1] == node.name,
                    "Invalid binding node");
                Require(result.TryAdd(node.id, node), "Duplicate binding identity: " + node.id);
            }
            return result;
        }

        static bool HasStableMatchedAnchor(BindingNode node, int matchedNames)
        {
            int firstMatched = node.hierarchy_names.Length - matchedNames;
            for (int index = firstMatched; index < node.hierarchy_names.Length; index++)
            {
                string name = node.hierarchy_names[index];
                if (name == "Root" || name == "Bip001" || name == "Mesh_all" || name == "lod0")
                    return true;
            }
            return false;
        }

        static bool Finite(float value) => !float.IsNaN(value) && !float.IsInfinity(value);

        static Transform CreateSealedShadowTransform(
            Transform parent, BindingNode node, List<GameObject> ownedShadowObjects)
        {
            Require(node.local_position != null && node.local_position.Length == 3 &&
                    node.local_rotation_xyzw != null && node.local_rotation_xyzw.Length == 4 &&
                    node.local_scale != null && node.local_scale.Length == 3,
                "Missing sealed render Transform values: " + node.id);
            foreach (float value in node.local_position) Require(Finite(value), "Nonfinite sealed render position");
            foreach (float value in node.local_rotation_xyzw) Require(Finite(value), "Nonfinite sealed render rotation");
            foreach (float value in node.local_scale) Require(Finite(value), "Nonfinite sealed render scale");
            var rotation = new Quaternion(
                node.local_rotation_xyzw[0], node.local_rotation_xyzw[1],
                node.local_rotation_xyzw[2], node.local_rotation_xyzw[3]);
            Require(Mathf.Abs(1f - Quaternion.Dot(rotation, rotation)) <= 1e-4f,
                "Non-unit sealed render rotation: " + node.id);
            Require(Mathf.Abs(node.local_scale[0]) > 1e-8f && Mathf.Abs(node.local_scale[1]) > 1e-8f &&
                    Mathf.Abs(node.local_scale[2]) > 1e-8f,
                "Degenerate sealed render scale: " + node.id);
            var gameObject = new GameObject(node.name) { hideFlags = HideFlags.HideAndDontSave };
            Transform transform = gameObject.transform;
            transform.SetParent(parent, false);
            transform.localPosition = new Vector3(
                node.local_position[0], node.local_position[1], node.local_position[2]);
            transform.localRotation = rotation;
            transform.localScale = new Vector3(node.local_scale[0], node.local_scale[1], node.local_scale[2]);
            ownedShadowObjects.Add(gameObject);
            return transform;
        }

        static bool MatchesSealedLocalTrs(Transform candidate, BindingNode node)
        {
            if (node.local_position == null || node.local_position.Length != 3 ||
                node.local_rotation_xyzw == null || node.local_rotation_xyzw.Length != 4 ||
                node.local_scale == null || node.local_scale.Length != 3) return false;
            var position = new Vector3(node.local_position[0], node.local_position[1], node.local_position[2]);
            var rotation = new Quaternion(
                node.local_rotation_xyzw[0], node.local_rotation_xyzw[1],
                node.local_rotation_xyzw[2], node.local_rotation_xyzw[3]);
            var scale = new Vector3(node.local_scale[0], node.local_scale[1], node.local_scale[2]);
            return Vector3.Distance(candidate.localPosition, position) <= 1e-5f &&
                   Quaternion.Angle(candidate.localRotation, rotation) <= 1e-3f &&
                   Vector3.Distance(candidate.localScale, scale) <= 1e-5f;
        }

        static Transform ResolveHierarchy(
            Transform[] live, BindingNode node, bool renderSlot, Transform missingParent,
            List<GameObject> ownedShadowObjects)
        {
            Transform match = null;
            foreach (Transform candidate in live)
            {
                if (candidate.name != node.name) continue;
                int index = node.hierarchy_names.Length - 1;
                Transform cursor = candidate;
                int matchedNames = 0;
                while (index >= 0 && cursor != null && cursor.name == node.hierarchy_names[index])
                {
                    matchedNames++;
                    index--;
                    cursor = cursor.parent;
                }
                bool exactHierarchy = index < 0;
                bool anchoredSuffix = matchedNames >= 2 && HasStableMatchedAnchor(node, matchedNames);
                bool directBoundParent = !renderSlot && missingParent != null && candidate.parent == missingParent;
                bool sealedRenderIdentity = renderSlot && node.hierarchy_names.Length == 2 &&
                                            node.hierarchy_names[1] == node.name &&
                                            node.name.StartsWith("MBC_Typhoea_", StringComparison.Ordinal) &&
                                            candidate.parent != null;
                if (!exactHierarchy && !anchoredSuffix && !directBoundParent && !sealedRenderIdentity) continue;
                Require(match == null, "Ambiguous live hierarchy: " + node.id);
                match = candidate;
            }
            if (match == null && !renderSlot && missingParent != null)
            {
                for (int childIndex = 0; childIndex < missingParent.childCount; childIndex++)
                {
                    Transform candidate = missingParent.GetChild(childIndex);
                    if (!MatchesSealedLocalTrs(candidate, node)) continue;
                    Require(match == null, "Ambiguous sealed-TRS hierarchy alias: " + node.id);
                    match = candidate;
                }
            }
            bool sealedColliderHelper = !renderSlot && missingParent != null &&
                                        node.name.IndexOf("collider", StringComparison.OrdinalIgnoreCase) >= 0;
            if (match == null && (renderSlot || sealedColliderHelper))
                match = CreateSealedShadowTransform(missingParent, node, ownedShadowObjects);
            Require(match != null, "Missing live hierarchy: " + node.id + " / " + node.name);
            return match;
        }

        static void DestroyShadowObjects(IEnumerable<GameObject> objects)
        {
            foreach (GameObject gameObject in objects)
                if (gameObject != null) UnityEngine.Object.DestroyImmediate(gameObject);
        }

        static HashSet<Transform> WeightedBones(Transform root)
        {
            var result = new HashSet<Transform>();
            foreach (SkinnedMeshRenderer renderer in root.GetComponentsInChildren<SkinnedMeshRenderer>(true))
            {
                Transform[] bones = renderer.bones;
                BoneWeight[] weights = renderer.sharedMesh.boneWeights;
                foreach (BoneWeight weight in weights)
                {
                    if (weight.weight0 > 0f) result.Add(bones[weight.boneIndex0]);
                    if (weight.weight1 > 0f) result.Add(bones[weight.boneIndex1]);
                    if (weight.weight2 > 0f) result.Add(bones[weight.boneIndex2]);
                    if (weight.weight3 > 0f) result.Add(bones[weight.boneIndex3]);
                }
            }
            return result;
        }

        static void RequireChunk(Chunk chunk, int expectedStart, int expectedCount, string label)
        {
            Require(chunk != null && chunk.start == expectedStart && chunk.count == expectedCount,
                "Non-contiguous or mismatched candidate chunk: " + label);
        }

        static int Advance(Chunk chunk, int cursor, string label)
        {
            Require(chunk != null && chunk.start == cursor && chunk.count >= 0 &&
                    chunk.start <= int.MaxValue - chunk.count,
                "Invalid candidate chunk: " + label);
            return chunk.start + chunk.count;
        }

        public static EndfieldOfficialPhysicsShadowInputs Load(
            Transform root,
            string bindingsPath,
            string bindingsSha256,
            string identityPath,
            string identitySha256,
            string layoutPath,
            string layoutSha256)
        {
            if (root == null) throw new ArgumentNullException(nameof(root));
            var bindings = JsonUtility.FromJson<BindingDocument>(
                ReadSealedText(bindingsPath, bindingsSha256));
            var identities = JsonUtility.FromJson<IdentityDocument>(
                ReadSealedText(identityPath, identitySha256));
            var layout = JsonUtility.FromJson<LayoutDocument>(
                ReadSealedText(layoutPath, layoutSha256));
            Require(identities != null && identities.schema_version == 1 && identities.groups != null &&
                    identities.groups.Length == 11 && !identities.runtime_instance_ids_generated &&
                    !identities.world_getters_generated && !identities.selection_attributes_generated &&
                    !identities.full_proxy_inputs_generated && !identities.native_arrays_published &&
                    !identities.game_build_route_observed && !identities.unity_backend_modified,
                "Identity document boundary flags changed");
            Require(layout != null && layout.schema_version == 1 && layout.teams != null &&
                    layout.team_ids != null && layout.teams.Length == 11 && layout.team_ids.Length == 11 &&
                    layout.fresh_candidate_core_layout_generated && layout.state_topology_invariant &&
                    layout.unsupported_team_chunks_omitted && !layout.original_runtime_team_ids_observed &&
                    !layout.original_runtime_chunks_observed && !layout.native_arrays_published &&
                    !layout.official_solver_integrated && !layout.original_runtime_executed && !layout.stage_modified,
                "Candidate layout boundary flags changed");
            Require(layout.candidate_flags != null && layout.candidate_flags.add_team == 0x0d &&
                    layout.candidate_flags.enabled_reset == 0x0f &&
                    layout.candidate_flags.supplied_running_step == 0xaf,
                "Candidate Team flags changed");
            Require(layout.supported_core_arenas != null && layout.supported_core_arenas.Length == 9,
                "Candidate core arena set changed");

            Dictionary<string, BindingNode> bindingById = IndexBindings(bindings);
            Transform[] live = root.GetComponentsInChildren<Transform>(true);
            HashSet<Transform> weighted = WeightedBones(root);
            int transformCapacity = 0;
            int particleCapacity = 0;
            int proxyCommonCursor = 0;
            int proxyMeshCursor = 0;
            int proxySkinBoneCursor = 0;
            int baselineCursor = 0;
            int baselineDataCursor = 0;
            int distanceStartCursor = 0;
            int distanceDataCursor = 0;
            int resolvedSkinCount = 0;
            int positiveWeightedCount = 0;
            for (int index = 0; index < layout.teams.Length; index++)
            {
                LayoutTeam team = layout.teams[index];
                IdentityGroup group = identities.groups[index];
                Require(team != null && group != null && team.team_id == index + 1 &&
                        layout.team_ids[index] == team.team_id && team.name == group.name &&
                        team.component_identity == group.component_identity,
                    "Team/identity order mismatch at " + index.ToString(CultureInfo.InvariantCulture));
                Require(group.skin_bone_count > 0 && group.ordered_transform_identities != null &&
                        group.ordered_transform_identities.Length == group.skin_bone_count + 1 &&
                        group.render_transform_index == group.skin_bone_count &&
                        group.ordinary_render_identity == group.ordered_transform_identities[group.render_transform_index] &&
                        group.snapshot_parent_indices != null &&
                        group.snapshot_parent_indices.Length == group.skin_bone_count + 1 &&
                        group.skin_parent_indices != null && group.skin_parent_indices.Length == group.skin_bone_count,
                    "Identity group shape mismatch: " + group.name);
                RequireChunk(team.proxy_transform, transformCapacity, group.skin_bone_count + 1,
                    group.name + ".proxy_transform");
                RequireChunk(team.proxy_common, proxyCommonCursor, group.skin_bone_count,
                    group.name + ".proxy_common");
                RequireChunk(team.proxy_mesh, proxyMeshCursor, group.skin_bone_count,
                    group.name + ".proxy_mesh");
                RequireChunk(team.proxy_skin_bone, proxySkinBoneCursor, group.skin_bone_count,
                    group.name + ".proxy_skin_bone");
                RequireChunk(team.particle, particleCapacity, group.skin_bone_count,
                    group.name + ".particle");
                RequireChunk(team.distance_start, distanceStartCursor, group.skin_bone_count,
                    group.name + ".distance_start");
                transformCapacity += team.proxy_transform.count;
                proxyCommonCursor += team.proxy_common.count;
                proxyMeshCursor += team.proxy_mesh.count;
                proxySkinBoneCursor += team.proxy_skin_bone.count;
                particleCapacity += team.particle.count;
                distanceStartCursor += team.distance_start.count;
                baselineCursor = Advance(team.baseline, baselineCursor, group.name + ".baseline");
                baselineDataCursor = Advance(team.baseline_data, baselineDataCursor, group.name + ".baseline_data");
                distanceDataCursor = Advance(team.distance_data, distanceDataCursor, group.name + ".distance_data");
                resolvedSkinCount += group.skin_bone_count;
            }
            Require(transformCapacity == 151 && particleCapacity == 140 && proxyCommonCursor == 140 &&
                    proxyMeshCursor == 140 && proxySkinBoneCursor == 140 && distanceStartCursor == 140 &&
                    baselineCursor == 37 && baselineDataCursor == 126 && distanceDataCursor == 176,
                "Candidate global capacities changed");

            var transformSlots = new Transform[transformCapacity];
            var particleWindows = new ParticleWindow[layout.teams.Length];
            var ownedShadowObjects = new List<GameObject>();
            int shadowRenderProxyCount = 0;
            int shadowHelperProxyCount = 0;
            int structuralAliasCount = 0;
            try
            {
                for (int groupIndex = 0; groupIndex < layout.teams.Length; groupIndex++)
                {
                    IdentityGroup group = identities.groups[groupIndex];
                    LayoutTeam team = layout.teams[groupIndex];
                    var groupTransforms = new Transform[group.ordered_transform_identities.Length];
                    int groupPositiveWeightedCount = 0;
                    for (int local = 0; local < groupTransforms.Length; local++)
                    {
                        string identity = group.ordered_transform_identities[local];
                        Require(bindingById.TryGetValue(identity, out BindingNode node),
                            "Missing binding identity: " + identity);
                        bool renderSlot = local == group.render_transform_index;
                        Require(!renderSlot || node.name == group.name,
                            "Render identity/name mismatch: " + group.name);
                        int parentIndex = renderSlot ? -1 : group.skin_parent_indices[local];
                        Transform missingParent = renderSlot ? root :
                            parentIndex >= 0 ? groupTransforms[parentIndex] : null;
                        if (!renderSlot && parentIndex >= 0)
                        {
                            string parentIdentity = group.ordered_transform_identities[parentIndex];
                            Require(bindingById.TryGetValue(parentIdentity, out BindingNode parentNode) &&
                                    node.parent_path_id == parentNode.path_id,
                                "Sealed helper parent identity mismatch: " + identity);
                        }
                        int ownedBefore = ownedShadowObjects.Count;
                        Transform resolved = ResolveHierarchy(
                            live, node, renderSlot, missingParent, ownedShadowObjects);
                        if (ownedShadowObjects.Count != ownedBefore)
                        {
                            if (renderSlot) shadowRenderProxyCount++;
                            else shadowHelperProxyCount++;
                        }
                        else if (resolved.name != node.name)
                            structuralAliasCount++;
                        groupTransforms[local] = resolved;
                        transformSlots[team.proxy_transform.start + local] = resolved;
                        if (local < group.skin_bone_count && weighted.Contains(resolved))
                        {
                            groupPositiveWeightedCount++;
                            positiveWeightedCount++;
                        }
                    }
                    Require(groupPositiveWeightedCount > 0,
                        "Official group has no positively weighted live slot: " + group.name);
                    var roots = new HashSet<int>(group.root_indices ?? Array.Empty<int>());
                    for (int local = 0; local < group.skin_bone_count; local++)
                    {
                        int parent = group.skin_parent_indices[local];
                        Require(parent >= -1 && parent < group.skin_bone_count && parent != local,
                            "Invalid skin parent index: " + group.name);
                        if (parent >= 0)
                            Require(groupTransforms[local].parent == groupTransforms[parent],
                                "Live skin parent mismatch: " + group.name + "[" + local + "]");
                        Require(roots.Contains(local) == (parent < 0),
                            "Root index/parent mismatch: " + group.name + "[" + local + "]");
                    }
                    particleWindows[groupIndex] = new ParticleWindow(
                        checked((short)team.team_id), team.particle.start, team.particle.count);
                }
                foreach (Transform slot in transformSlots) Require(slot != null, "Unfilled transform slot");
                return new EndfieldOfficialPhysicsShadowInputs(
                    transformSlots, particleWindows, particleCapacity, layout.teams.Length, resolvedSkinCount,
                    positiveWeightedCount, shadowRenderProxyCount, shadowHelperProxyCount,
                    structuralAliasCount, ownedShadowObjects.ToArray());
            }
            catch
            {
                DestroyShadowObjects(ownedShadowObjects);
                throw;
            }
        }

        static float4 F(Vector4 value) => new float4(value.x, value.y, value.z, value.w);

        static float4x4 F(Matrix4x4 value) => new float4x4(
            F(value.GetColumn(0)), F(value.GetColumn(1)),
            F(value.GetColumn(2)), F(value.GetColumn(3)));

        static Matrix4x4 M(float4x4 value)
        {
            var result = new Matrix4x4();
            result.SetColumn(0, new Vector4(value.c0.x, value.c0.y, value.c0.z, value.c0.w));
            result.SetColumn(1, new Vector4(value.c1.x, value.c1.y, value.c1.z, value.c1.w));
            result.SetColumn(2, new Vector4(value.c2.x, value.c2.y, value.c2.z, value.c2.w));
            result.SetColumn(3, new Vector4(value.c3.x, value.c3.y, value.c3.z, value.c3.w));
            return result;
        }

        static bool Finite(Matrix4x4 value)
        {
            for (int row = 0; row < 4; row++)
                for (int column = 0; column < 4; column++)
                    if (float.IsNaN(value[row, column]) || float.IsInfinity(value[row, column])) return false;
            return true;
        }

        void ThrowIfDisposed()
        {
            if (disposed) throw new ObjectDisposedException(nameof(EndfieldOfficialPhysicsShadowInputs));
        }

        public void PublishCurrentTransformInputs()
        {
            ThrowIfDisposed();
            LastTransformWrites = 0;
            LastParticleTeamWrites = 0;
            for (int index = 0; index < transformSlots.Length; index++)
            {
                Transform transform = transformSlots[index];
                Require(transform != null, "Live transform was destroyed before publication");
                Matrix4x4 matrix = transform.localToWorldMatrix;
                Require(Finite(matrix), "Nonfinite live transform matrix: " + transform.name);
                transformMatrices[index] = F(matrix);
                transformInstanceIds[index] = transform.GetInstanceID();
                transformParentInstanceIds[index] = transform.parent ? transform.parent.GetInstanceID() : 0;
                LastTransformWrites++;
            }
            foreach (ParticleWindow window in particleWindows)
                for (int offset = 0; offset < window.count; offset++)
                {
                    particleTeamIds[window.start + offset] = window.teamId;
                    LastParticleTeamWrites++;
                }
        }

        public Matrix4x4[] CopyPublishedTransformMatrices()
        {
            ThrowIfDisposed();
            var result = new Matrix4x4[transformMatrices.Length];
            for (int index = 0; index < result.Length; index++) result[index] = M(transformMatrices[index]);
            return result;
        }

        public float MaxPublishedTransformMatrixError()
        {
            ThrowIfDisposed();
            float error = 0f;
            for (int index = 0; index < transformSlots.Length; index++)
            {
                Matrix4x4 actual = transformSlots[index].localToWorldMatrix;
                Matrix4x4 published = M(transformMatrices[index]);
                for (int row = 0; row < 4; row++)
                    for (int column = 0; column < 4; column++)
                        error = Mathf.Max(error, Mathf.Abs(actual[row, column] - published[row, column]));
            }
            return error;
        }

        public void Dispose()
        {
            if (disposed) return;
            if (transformMatrices.IsCreated) transformMatrices.Dispose();
            if (transformInstanceIds.IsCreated) transformInstanceIds.Dispose();
            if (transformParentInstanceIds.IsCreated) transformParentInstanceIds.Dispose();
            if (particleTeamIds.IsCreated) particleTeamIds.Dispose();
            DestroyShadowObjects(ownedShadowObjects);
            disposed = true;
        }
    }
}
