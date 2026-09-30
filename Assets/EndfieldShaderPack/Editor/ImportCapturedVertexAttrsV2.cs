using System;
using System.Collections.Generic;
using System.IO;
using System.Linq;
using System.Security.Cryptography;
using Newtonsoft.Json;
using Newtonsoft.Json.Linq;
using UnityEditor;
using UnityEngine;

namespace EndfieldShaderPack.EditorTools
{
    public static class ImportCapturedVertexAttrsV2
    {
        const string ValidationRoot = "Validation/vertex-input-export-20260929-183059";
        const string MeshRoot = "Assets/Typhoeus/GeneratedMeshes";
        static readonly string[] Parts = { "iris", "body", "cloth_01", "cloth_02", "face", "hair" };

        sealed class Prepared
        {
            public string Part, Path;
            public Mesh Mesh;
            public Vector3[] Normals;
            public Vector4[] Tangents;
            public float PositionError, UvError, NormalAngle, TangentAngle, Orthogonality;
        }

        static string MeshName(string part) => "S_actor_typhoea_" + (part.Contains("_") ? part : part + "_01") + "_lod0";

        // Skin b138 vertex: 306-343. The normal and tangent share one uint.
        public static void DecodePackedFrame(uint packed, out Vector3 normal, out Vector4 tangent)
        {
            if ((packed & 0x40000000u) == 0) throw new InvalidDataException("Packed frame compression flag is absent.");
            float Signed(uint value) => (value >= 512 ? (int)value - 1024 : (int)value) / 511f;
            float x = Signed(packed & 1023), y = Signed((packed >> 10) & 1023);
            float z = 1f - Mathf.Abs(x) - Mathf.Abs(y);
            if (z < 0)
            {
                float oldX = x;
                x = (1f - Mathf.Abs(y)) * (oldX >= 0 ? 1 : -1);
                y = (1f - Mathf.Abs(oldX)) * (y >= 0 ? 1 : -1);
            }
            normal = new Vector3(x, y, z).normalized;
            float parameter = Signed((packed >> 20) & 1023);
            Vector3 axis = new Vector3(normal.y - normal.z, normal.z - normal.x, normal.x - normal.y);
            Vector3 first = (axis - Vector3.one * Vector3.Dot(axis, normal)).normalized;
            Vector3 second = Vector3.Cross(normal, first).normalized;
            float sign = parameter < 0 ? -1f : 1f;
            float a = 1f - Mathf.Abs(parameter) * 2f;
            Vector2 weights = new Vector2(a, sign * (1f - Mathf.Abs(a))).normalized;
            Vector3 direction = first * weights.x + second * weights.y;
            tangent = new Vector4(direction.x, direction.y, direction.z, ((packed >> 31) & 1) * 2f - 1f);
            if (!Finite(normal) || !Finite(direction) || direction.sqrMagnitude < .99f)
                throw new InvalidDataException("Packed frame decoded to a degenerate direction.");
        }

        static bool Finite(Vector3 v) => !(float.IsNaN(v.x) || float.IsNaN(v.y) || float.IsNaN(v.z)
            || float.IsInfinity(v.x) || float.IsInfinity(v.y) || float.IsInfinity(v.z));

        static JObject InputAt(JObject eventData, int location)
        {
            var signature = eventData["signature"] as JArray
                ?? throw new InvalidDataException("Missing vertex shader input signature.");
            var inputs = eventData["inputs"] as JObject ?? throw new InvalidDataException("Missing raw vertex inputs.");
            var names = signature.OfType<JObject>().Where(s => (int?)s["location"] == location
                && (string)s["system_value"] == "ShaderBuiltin.Undefined").Select(s => (string)s["name"]).ToArray();
            if (names.Length != 1 || !(inputs[names[0]] is JObject input))
                throw new InvalidDataException("Missing or ambiguous input at location " + location);
            return input;
        }

        static byte[] ReadInput(JObject input, int count, string format)
        {
            if ((string)input["format"]?["name"] != format)
                throw new InvalidDataException("Expected " + format + ", got " + input["format"]?["name"]);
            string root = Path.GetFullPath(Path.Combine(Application.dataPath, "..", ValidationRoot));
            string path = Path.GetFullPath(Path.Combine(root, (string)input["file"]));
            if (!path.StartsWith(root + Path.DirectorySeparatorChar, StringComparison.OrdinalIgnoreCase))
                throw new InvalidDataException("Raw input path escapes the capture export.");
            byte[] bytes = File.ReadAllBytes(path);
            int expected = checked(count * (int)input["format"]["compCount"] * (int)input["format"]["compByteWidth"]);
            if (bytes.Length != expected) throw new InvalidDataException("Truncated raw input: " + path);
            using (var hash = SHA256.Create())
            {
                string actual = BitConverter.ToString(hash.ComputeHash(bytes)).Replace("-", "").ToLowerInvariant();
                if (actual != (string)input["sha256"]) throw new InvalidDataException("Raw input SHA256 mismatch: " + path);
            }
            return bytes;
        }

        static void ValidateCorrespondence(Prepared job, JObject eventData, int count)
        {
            if (job.Mesh.vertexCount != count) throw new InvalidDataException(job.Part + ": vertex count mismatch.");
            byte[] positions = ReadInput(InputAt(eventData, 0), count, "R32G32B32_FLOAT");
            byte[] uvs = ReadInput(InputAt(eventData, 1), count, "R32G32_FLOAT");
            var vertices = job.Mesh.vertices;
            var meshUvs = job.Mesh.uv;
            if (meshUvs.Length != count) throw new InvalidDataException(job.Part + ": UV count mismatch.");
            for (int i = 0; i < count; i++)
            {
                Vector3 p = new Vector3(BitConverter.ToSingle(positions, i * 12),
                    BitConverter.ToSingle(positions, i * 12 + 4), BitConverter.ToSingle(positions, i * 12 + 8));
                Vector2 uv = new Vector2(BitConverter.ToSingle(uvs, i * 8), BitConverter.ToSingle(uvs, i * 8 + 4));
                if (!Finite(p) || float.IsNaN(uv.x) || float.IsNaN(uv.y) || float.IsInfinity(uv.x) || float.IsInfinity(uv.y))
                    throw new InvalidDataException(job.Part + ": non-finite position/UV.");
                job.PositionError = Mathf.Max(job.PositionError, (vertices[i] - p).magnitude);
                job.UvError = Mathf.Max(job.UvError, (meshUvs[i] - uv).magnitude);
            }
            if (job.PositionError > 1e-5f || job.UvError > 1e-5f)
                throw new InvalidDataException(job.Part + ": vertex order/space does not match capture (position="
                    + job.PositionError + ", UV=" + job.UvError + "). Refusing guessed remapping.");
            int stride = (int)eventData["index_binding"]["index_stride"];
            if (stride != 2 && stride != 4) throw new InvalidDataException("Unsupported index stride.");
            string indexName = (string)eventData["ib_file"];
            if (indexName != Path.GetFileName(indexName)) throw new InvalidDataException("Index filename escapes export.");
            byte[] indices = File.ReadAllBytes(Path.Combine(Application.dataPath, "..", ValidationRoot, indexName));
            int[] triangles = job.Mesh.triangles;
            if (indices.Length != triangles.Length * stride) throw new InvalidDataException(job.Part + ": index count mismatch.");
            int minimum = (int)eventData["ib_min"];
            for (int i = 0; i < triangles.Length; i++)
            {
                uint captured = stride == 2 ? BitConverter.ToUInt16(indices, i * stride) : BitConverter.ToUInt32(indices, i * stride);
                if ((long)captured - minimum != triangles[i])
                    throw new InvalidDataException(job.Part + ": index topology differs at " + i);
            }
        }

        static List<Prepared> PrepareAll()
        {
            RunDecoderRegression();
            var manifest = JObject.Parse(File.ReadAllText(Path.Combine(Application.dataPath, "..", ValidationRoot, "manifest.json")));
            if ((string)manifest["schema"] != "renderdoc-vsin-raw-v1" || (int?)manifest["frame"] != 6411)
                throw new InvalidDataException("This semantic mapping is reviewed only for frame 6411 raw-v1.");
            var events = manifest["events"] as JObject ?? throw new InvalidDataException("No captured events.");
            var jobs = new List<Prepared>();
            foreach (string part in Parts)
            {
                var matches = events.Properties().Select(p => p.Value as JObject).Where(e => (string)e?["part"] == part).ToArray();
                if (matches.Length != 1) throw new InvalidDataException(part + ": expected exactly one captured draw.");
                JObject eventData = matches[0];
                string path = MeshRoot + "/" + MeshName(part) + ".asset";
                var mesh = AssetDatabase.LoadAssetAtPath<Mesh>(path) ?? throw new FileNotFoundException("Missing mesh", path);
                var job = new Prepared { Part = part, Path = path, Mesh = mesh };
                int count = (int)eventData["vertices"];
                ValidateCorrespondence(job, eventData, count);
                var normalInput = InputAt(eventData, 2);
                bool compressed = (string)normalInput["format"]?["name"] == "R32_FLOAT";
                byte[] packed = ReadInput(normalInput, count, compressed ? "R32_FLOAT" : "R32G32B32_FLOAT");
                byte[] tangentData = compressed ? null : ReadInput(InputAt(eventData, 3), count, "R32G32B32A32_FLOAT");
                job.Normals = new Vector3[count]; job.Tangents = new Vector4[count];
                var oldNormals = mesh.normals; var oldTangents = mesh.tangents;
                for (int i = 0; i < count; i++)
                {
                    if (compressed)
                        DecodePackedFrame(BitConverter.ToUInt32(packed, i * 4), out job.Normals[i], out job.Tangents[i]);
                    else
                    {
                        job.Normals[i] = new Vector3(BitConverter.ToSingle(packed, i * 12),
                            BitConverter.ToSingle(packed, i * 12 + 4), BitConverter.ToSingle(packed, i * 12 + 8));
                        job.Tangents[i] = new Vector4(BitConverter.ToSingle(tangentData, i * 16),
                            BitConverter.ToSingle(tangentData, i * 16 + 4), BitConverter.ToSingle(tangentData, i * 16 + 8),
                            BitConverter.ToSingle(tangentData, i * 16 + 12));
                        if (!Finite(job.Normals[i]) || !Finite(job.Tangents[i]) || job.Normals[i].sqrMagnitude < .99f
                            || ((Vector3)job.Tangents[i]).sqrMagnitude < .99f || Mathf.Abs(job.Tangents[i].w) != 1)
                            throw new InvalidDataException(part + ": invalid uncompressed vertex frame.");
                    }
                    if (oldNormals.Length == count) job.NormalAngle = Mathf.Max(job.NormalAngle, Vector3.Angle(oldNormals[i], job.Normals[i]));
                    if (oldTangents.Length == count) job.TangentAngle = Mathf.Max(job.TangentAngle, Vector3.Angle(oldTangents[i], job.Tangents[i]));
                    job.Orthogonality = Mathf.Max(job.Orthogonality, Mathf.Abs(Vector3.Dot(job.Normals[i], job.Tangents[i])));
                }
                // The uncompressed cloth capture contains authored non-orthogonal
                // frames (max |N.T| ~0.196). Preserve those bytes: orthogonalizing
                // them would change the official input, not repair the importer.
                if (compressed && job.Orthogonality > 1e-5f)
                    throw new InvalidDataException(part + ": decoded tangent frame is not orthogonal.");
                jobs.Add(job);
            }
            return jobs;
        }

        static void RunDecoderRegression()
        {
            float rootHalf = Mathf.Sqrt(.5f);
            foreach (uint sign in new[] { 0u, 0x80000000u })
            {
                DecodePackedFrame(0x40000000u | sign, out var n, out var t);
                if ((n - Vector3.forward).magnitude > 1e-6f
                    || ((Vector3)t - new Vector3(-rootHalf, rootHalf, 0)).magnitude > 1e-6f
                    || t.w != (sign == 0 ? -1f : 1f)) throw new InvalidOperationException("Packed frame canonical regression.");
            }
            DecodePackedFrame(0x400001ffu, out var nx, out var tx);
            if ((nx - Vector3.right).magnitude > 1e-6f
                || ((Vector3)tx - new Vector3(0, -rootHalf, rootHalf)).magnitude > 1e-6f)
                throw new InvalidOperationException("Packed frame axis regression.");
            bool rejected = false;
            try { DecodePackedFrame(0, out _, out _); }
            catch (InvalidDataException) { rejected = true; }
            if (!rejected) throw new InvalidOperationException("Missing compression flag was accepted.");
        }

        static void Report(List<Prepared> jobs, bool applied, string backup)
        {
            string path = Environment.GetEnvironmentVariable("ENDFIELD_VERTEX_IMPORT_REPORT") ?? "Logs/vertex-import-v2-report.json";
            Directory.CreateDirectory(Path.GetDirectoryName(Path.GetFullPath(path)));
            File.WriteAllText(path, JsonConvert.SerializeObject(new { applied, backup, frame = 6411,
                channels = "normal + tangent (packed or float); no inferred color/UV1", meshes = jobs.Select(j => new {
                    part = j.Part, path = j.Path, vertices = j.Normals.Length, maxPositionError = j.PositionError,
                    maxUvError = j.UvError, previousNormalAngleDegrees = j.NormalAngle,
                    previousTangentAngleDegrees = j.TangentAngle, maxOrthogonalityError = j.Orthogonality,
                }).ToArray() }, Formatting.Indented));
            Debug.Log("[VertexImportV2] " + (applied ? "APPLIED" : "VALIDATED (no mesh writes)") + ": " + jobs.Count + " meshes, "
                + jobs.Sum(j => j.Normals.Length) + " vertex frames; report=" + path);
        }

        public static void ValidateAll() => Report(PrepareAll(), false, null);

        [MenuItem("Endfield/Import Captured Vertex Attributes V2 (Octahedral)")]
        public static void ImportAll()
        {
            var jobs = PrepareAll();
            string backup = Path.GetFullPath("Logs/vertex-import-v2-backup-" + DateTime.UtcNow.ToString("yyyyMMdd-HHmmss-fffffff"));
            Directory.CreateDirectory(backup);
            foreach (var job in jobs)
            {
                File.Copy(job.Path, Path.Combine(backup, Path.GetFileName(job.Path)));
                File.Copy(job.Path + ".meta", Path.Combine(backup, Path.GetFileName(job.Path) + ".meta"));
            }
            foreach (var job in jobs)
            {
                Undo.RecordObject(job.Mesh, "Import captured normal/tangent frame");
                job.Mesh.normals = job.Normals; job.Mesh.tangents = job.Tangents;
                EditorUtility.SetDirty(job.Mesh);
            }
            AssetDatabase.SaveAssets();
            Report(jobs, true, backup);
        }
    }
}
