// Read-only getter producer for an ISOLATED Unity project. Not a game hook,
// recovered-model mapper, cloth solver, TransformAccess Job or stage backend.
// Reconstructs only reviewed serialized Transform local TRS and child order.
// Actual Unity getters are sampled in rest and rigidly moved reference states.
using System;
using System.Collections.Generic;
using System.Globalization;
using System.IO;
using System.Security.Cryptography;
using UnityEditor;
using UnityEngine;

public static class OfficialPhysicsGetterProbe
{
    [Serializable] public class Node
    {
        public string id;
        public long path_id, parent_path_id;
        public string name;
        public long[] children_path_ids;
        public float[] local_position, local_rotation_xyzw, local_scale;
    }
    [Serializable] public class BindingDocument
    {
        public int schema_version, transform_count;
        public Node[] transforms;
    }
    [Serializable] public class Columns { public float[] c0, c1, c2, c3; }
    [Serializable] public class Sample
    {
        public string identity;
        public int instance_id, parent_instance_id;
        public float[] position, rotation, local_position, local_rotation;
        public Columns local_to_world, world_to_local;
    }
    [Serializable] public class State { public string name; public Sample[] samples; }
    [Serializable] public class Output
    {
        public int schema_version = 1;
        public string unity_version, bindings_sha256;
        public string scope = "Unity getters on reconstructed serialized reference hierarchy; not game pose or recovered character";
        public bool synthetic_getter_checks_passed;
        public bool original_runtime_executed = false;
        public bool stage_modified = false;
        public State[] states;
    }

    static void Require(bool condition, string message)
    {
        if (!condition) throw new InvalidOperationException(message);
    }
    static string Env(string name)
    {
        string value = Environment.GetEnvironmentVariable(name);
        Require(!string.IsNullOrWhiteSpace(value), "Missing environment: " + name);
        return value;
    }
    static string Hash(byte[] bytes)
    {
        using (var sha = SHA256.Create())
            return BitConverter.ToString(sha.ComputeHash(bytes)).Replace("-", "").ToLowerInvariant();
    }
    static string FileOf(string identity)
    {
        int split = identity.LastIndexOf(':');
        Require(split > 0, "Unqualified identity");
        return identity.Substring(0, split);
    }
    static string Id(string file, long path)
    {
        return file + ":" + path.ToString(CultureInfo.InvariantCulture);
    }
    static Vector3 V(float[] value)
    {
        Require(value != null && value.Length == 3, "Invalid float3");
        foreach (float f in value) Require(!float.IsNaN(f) && !float.IsInfinity(f), "Nonfinite float3");
        return new Vector3(value[0], value[1], value[2]);
    }
    static Quaternion Q(float[] value)
    {
        Require(value != null && value.Length == 4, "Invalid quaternion");
        foreach (float f in value) Require(!float.IsNaN(f) && !float.IsInfinity(f), "Nonfinite quaternion");
        return new Quaternion(value[0], value[1], value[2], value[3]);
    }
    static float[] A(Vector3 v) { return new[] { v.x, v.y, v.z }; }
    static float[] A(Quaternion q) { return new[] { q.x, q.y, q.z, q.w }; }
    static float[] A(Vector4 v) { return new[] { v.x, v.y, v.z, v.w }; }
    static Columns M(Matrix4x4 m)
    {
        return new Columns { c0 = A(m.GetColumn(0)), c1 = A(m.GetColumn(1)), c2 = A(m.GetColumn(2)), c3 = A(m.GetColumn(3)) };
    }
    static Sample Read(string identity, Transform t)
    {
        return new Sample {
            identity = identity, instance_id = t.GetInstanceID(),
            parent_instance_id = t.parent ? t.parent.GetInstanceID() : 0,
            position = A(t.position), rotation = A(t.rotation),
            local_position = A(t.localPosition), local_rotation = A(t.localRotation),
            local_to_world = M(t.localToWorldMatrix), world_to_local = M(t.worldToLocalMatrix)
        };
    }
    static State Capture(string name, Node[] nodes, Dictionary<string, Transform> objects)
    {
        var samples = new Sample[nodes.Length];
        for (int i = 0; i < nodes.Length; ++i) samples[i] = Read(nodes[i].id, objects[nodes[i].id]);
        return new State { name = name, samples = samples };
    }
    static void CheckSyntheticGetters()
    {
        var parent = new GameObject("probe-synthetic-parent");
        var child = new GameObject("probe-synthetic-child");
        try {
            child.transform.SetParent(parent.transform, false);
            parent.transform.position = new Vector3(3, 4, 5);
            parent.transform.rotation = Quaternion.Euler(17, -31, 12);
            parent.transform.localScale = new Vector3(2, 0.5f, -3);
            child.transform.localPosition = new Vector3(1, 2, 3);
            child.transform.localRotation = Quaternion.Euler(25, 11, -8);
            child.transform.localScale = new Vector3(0.7f, 1.2f, 2);
            Sample value = Read("fixture:1", child.transform);
            Require(value.instance_id == child.transform.GetInstanceID(), "Wrong instance ID");
            Require(value.parent_instance_id == parent.transform.GetInstanceID(), "Wrong parent ID");
            Require(Vector3.Distance(child.transform.position, parent.transform.TransformPoint(child.transform.localPosition)) < 1e-5f, "World/local getter mismatch");
            Require(Vector3.Distance(child.transform.worldToLocalMatrix.MultiplyPoint3x4(child.transform.position), Vector3.zero) < 1e-5f, "WtoL getter mismatch");
            Require(value.local_to_world.c3[0] == child.transform.position.x && value.local_to_world.c3[3] == 1, "Matrix columns transposed");
            Require(value.local_position[0] == 1 && value.local_position[1] == 2 && value.local_position[2] == 3, "Local getter lost");
        } finally {
            UnityEngine.Object.DestroyImmediate(parent);
        }
    }
    public static void Run()
    {
        GameObject wrapper = null;
        try {
            string output = Path.GetFullPath(Env("ENDFIELD_GETTER_OUTPUT"));
            Require(!File.Exists(output), "Output exists; use a fresh path");
            byte[] raw = File.ReadAllBytes(Env("ENDFIELD_GETTER_BINDINGS"));
            string digest = Hash(raw);
            Require(digest == Env("ENDFIELD_GETTER_BINDINGS_SHA256"), "Bindings seal mismatch");
            var source = JsonUtility.FromJson<BindingDocument>(System.Text.Encoding.UTF8.GetString(raw));
            Require(source.schema_version == 1 && source.transforms != null && source.transform_count == source.transforms.Length, "Binding schema mismatch");
            CheckSyntheticGetters();
            wrapper = new GameObject("isolated-reference-frame-not-official-object");
            var objects = new Dictionary<string, Transform>();
            foreach (Node n in source.transforms) {
                Require(n.path_id != 0 && Id(FileOf(n.id), n.path_id) == n.id, "Identity mismatch");
                var go = new GameObject(n.name);
                go.transform.SetParent(wrapper.transform, false);
                objects.Add(n.id, go.transform);
            }
            foreach (Node n in source.transforms) {
                Transform t = objects[n.id];
                t.SetParent(n.parent_path_id == 0 ? wrapper.transform : objects[Id(FileOf(n.id), n.parent_path_id)], false);
                t.localPosition = V(n.local_position);
                t.localRotation = Q(n.local_rotation_xyzw);
                t.localScale = V(n.local_scale);
            }
            foreach (Node n in source.transforms) {
                Transform parent = objects[n.id];
                Require(parent.childCount == n.children_path_ids.Length, "Child count mismatch");
                for (int i = 0; i < n.children_path_ids.Length; ++i) {
                    Transform child = objects[Id(FileOf(n.id), n.children_path_ids[i])];
                    Require(child.parent == parent, "Nonreciprocal child edge");
                    child.SetSiblingIndex(i);
                }
                for (int i = 0; i < n.children_path_ids.Length; ++i)
                    Require(parent.GetChild(i) == objects[Id(FileOf(n.id), n.children_path_ids[i])], "Child order mismatch");
            }
            var rest = Capture("serialized-rest", source.transforms, objects);
            wrapper.transform.position = new Vector3(1.25f, -2, 0.75f);
            wrapper.transform.rotation = Quaternion.Euler(12, 35, -7);
            var moved = Capture("rigid-reference-frame", source.transforms, objects);
            var result = new Output { unity_version = Application.unityVersion, bindings_sha256 = digest,
                synthetic_getter_checks_passed = true, states = new[] { rest, moved } };
            using (var stream = new FileStream(output, FileMode.CreateNew, FileAccess.Write))
            using (var writer = new StreamWriter(stream, new System.Text.UTF8Encoding(false)))
                writer.WriteLine(JsonUtility.ToJson(result, true));
            Debug.Log("GETTER_PROBE_PASS " + source.transform_count + " transforms x 2 states");
            EditorApplication.Exit(0);
        } catch (Exception error) {
            Debug.LogException(error);
            EditorApplication.Exit(1);
        } finally {
            if (wrapper) UnityEngine.Object.DestroyImmediate(wrapper);
        }
    }
}
