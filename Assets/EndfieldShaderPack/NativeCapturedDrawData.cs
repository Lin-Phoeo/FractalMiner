// Read-only native data handoff for editor/runtime adapters. No UnityEngine/Mesh operations.
// A caller pins the manifest SHA from a trusted publication, not from this folder.
using System;
using System.Collections.Generic;
using System.IO;
using System.Linq;
using System.Security.Cryptography;
using System.Text;
using System.Text.RegularExpressions;
using Newtonsoft.Json;
using Newtonsoft.Json.Linq;

namespace EndfieldShaderPack.CapturedData
{
    public sealed class NativeInput
    {
        readonly byte[] bytes;
        readonly JObject source;
        public int Location { get; }
        public int VertexCount { get; }
        public int Components { get; }
        public int ComponentBytes { get; }
        public string Format { get; }
        public JObject SourceBinding => (JObject)source.DeepClone();
        public byte[] CopyBytes() => (byte[])bytes.Clone();

        internal NativeInput(int location, int count, JObject entry, byte[] raw)
        {
            Location = location; VertexCount = count; source = (JObject)entry.DeepClone(); bytes = raw;
            var format = (JObject)entry["format"];
            Format = format.Value<string>("name"); Components = format.Value<int>("compCount");
            ComponentBytes = format.Value<int>("compByteWidth");
            var bits = Regex.Matches(Format, @"[RGBA](\d+)");
            NativeCapturedDrawData.Require(Regex.IsMatch(Format, @"^R\d+(G\d+)?(B\d+)?(A\d+)?_(FLOAT|UINT|UNORM|SNORM)$")
                && bits.Count == Components && new[] { 1, 2, 4 }.Contains(ComponentBytes)
                && bits.Cast<Match>().All(m => int.Parse(m.Groups[1].Value) == ComponentBytes * 8)
                && format.Value<int>("stride") == Components * ComponentBytes
                && raw.Length == checked(count * Components * ComponentBytes), "Native input format/size mismatch");
            NativeCapturedDrawData.Require(!(Format.EndsWith("_FLOAT", StringComparison.Ordinal) && ComponentBytes != 4),
                "Only native f32 carriers are supported here");
        }

        int Offset(int vertex, int component)
        {
            if (vertex < 0 || vertex >= VertexCount || component < 0 || component >= Components)
                throw new ArgumentOutOfRangeException(nameof(vertex));
            return checked((vertex * Components + component) * ComponentBytes);
        }

        public uint ReadUInt32Bits(int vertex, int component)
        {
            NativeCapturedDrawData.Require(ComponentBytes == 4, "Not a 32-bit carrier");
            int offset = Offset(vertex, component);
            return (uint)bytes[offset] | ((uint)bytes[offset + 1] << 8)
                | ((uint)bytes[offset + 2] << 16) | ((uint)bytes[offset + 3] << 24);
        }

        public float ReadFloat32(int vertex, int component)
        {
            NativeCapturedDrawData.Require(Format.EndsWith("_FLOAT", StringComparison.Ordinal) && ComponentBytes == 4,
                "Not a native f32 component");
            uint bits = ReadUInt32Bits(vertex, component);
            return BitConverter.ToSingle(BitConverter.GetBytes(bits), 0);
        }

        public uint ReadUnsignedComponent(int vertex, int component)
        {
            NativeCapturedDrawData.Require(Format.EndsWith("_UINT", StringComparison.Ordinal), "Not a native UINT component");
            return ReadInteger(vertex, component);
        }

        uint ReadInteger(int vertex, int component)
        {
            int offset = Offset(vertex, component);
            if (ComponentBytes == 1) return bytes[offset];
            if (ComponentBytes == 2) return (uint)bytes[offset] | ((uint)bytes[offset + 1] << 8);
            return ReadUInt32Bits(vertex, component);
        }

        public double ReadNormalizedComponent(int vertex, int component)
        {
            NativeCapturedDrawData.Require(Format.EndsWith("_UNORM", StringComparison.Ordinal)
                && ComponentBytes <= 2, "Not a native UNORM8/16 component");
            return ReadInteger(vertex, component) / (ComponentBytes == 1 ? 255.0 : 65535.0);
        }
    }

    public sealed class NativeDrawRecord
    {
        readonly Dictionary<int, NativeInput> inputs;
        readonly JObject source;
        readonly byte[] indices;
        public int EventId { get; }
        public int VertexCount { get; }
        public string Part { get; }
        public IReadOnlyList<int> Locations { get; }
        public JObject SourceRecord => (JObject)source.DeepClone();
        public NativeInput GetInput(int location) => inputs[location];
        public byte[] CopyIndexBytes() => (byte[])indices.Clone();

        internal NativeDrawRecord(int eventId, JObject original, JObject normalized, IDictionary<string, byte[]> files)
        {
            EventId = eventId; VertexCount = original.Value<int>("vertices"); Part = original.Value<string>("part");
            source = (JObject)original.DeepClone(); inputs = new Dictionary<int, NativeInput>();
            var rawInputs = (JObject)original["inputs"];
            var exported = (JObject)normalized["attributes"];
            var consumedNames = new HashSet<string>();
            foreach (JObject sig in (JArray)original["signature"])
            {
                if (sig.Value<string>("system_value") != "ShaderBuiltin.Undefined") continue;
                string name = sig.Value<string>("name");
                if (!(rawInputs[name] is JObject entry)) continue;
                int location = sig.Value<int>("location");
                NativeCapturedDrawData.Require(location >= 0 && !inputs.ContainsKey(location) && consumedNames.Add(name),
                    "Duplicate input signature");
                NativeCapturedDrawData.Require(JToken.DeepEquals(entry, exported[location.ToString()]),
                    "Location metadata disagrees with source signature");
                inputs.Add(location, new NativeInput(location, VertexCount, entry, files[entry.Value<string>("file")]));
            }
            NativeCapturedDrawData.Require(consumedNames.SetEquals(rawInputs.Properties().Select(p => p.Name))
                && exported.Count == inputs.Count, "Unmatched/missing inputs");
            Locations = Array.AsReadOnly(inputs.Keys.OrderBy(id => id).ToArray());
            indices = files[original.Value<string>("ib_file")];
        }
    }

    public sealed class NativeCapturedDrawData
    {
        readonly Dictionary<int, NativeDrawRecord> draws;
        public string ManifestSha256 { get; }
        public IReadOnlyList<int> EventIds { get; }
        public NativeDrawRecord GetDraw(int eventId) => draws[eventId];
        NativeCapturedDrawData(string digest, Dictionary<int, NativeDrawRecord> records)
        {
            ManifestSha256 = digest; draws = records; EventIds = Array.AsReadOnly(records.Keys.OrderBy(id => id).ToArray());
        }

        internal static void Require(bool value, string message)
        {
            if (!value) throw new InvalidDataException(message);
        }

        public static string Hash(byte[] raw)
        {
            using (var hash = SHA256.Create())
                return BitConverter.ToString(hash.ComputeHash(raw)).Replace("-", "").ToLowerInvariant();
        }

        static byte[] FileBytes(string root, string name)
        {
            Require(Regex.IsMatch(name, @"^[A-Za-z0-9_.-]+$") && name != "." && name != "..", "Invalid bundle filename");
            string path = Path.Combine(root, name);
            Require((File.GetAttributes(path) & (FileAttributes.ReparsePoint | FileAttributes.Directory)) == 0,
                "Bundle links/directories are not allowed");
            return File.ReadAllBytes(path);
        }

        static JObject Parse(byte[] raw) => JObject.Parse(new UTF8Encoding(false, true).GetString(raw).TrimStart('\ufeff'),
            new JsonLoadSettings { DuplicatePropertyNameHandling = DuplicatePropertyNameHandling.Error });

        public static NativeCapturedDrawData Load(string directory, string expectedManifestSha256)
        {
            Require(expectedManifestSha256 != null && Regex.IsMatch(expectedManifestSha256, @"^[a-f0-9]{64}$"),
                "An externally pinned manifest SHA256 is required");
            string root = Path.GetFullPath(directory);
            byte[] raw = FileBytes(root, "manifest.json");
            string digest = Hash(raw);
            Require(digest == expectedManifestSha256, "Pinned bundle identity mismatch");
            JObject metadata = Parse(raw), completion = Parse(FileBytes(root, "complete.json"));
            Require(completion.Count == 2 && completion.Value<string>("schema") == "endfield-native-draw-complete-v1"
                && completion.Value<string>("manifest_sha256") == digest, "Incomplete bundle");
            Require(metadata.Value<string>("schema") == "endfield-native-draw-bundle-v1"
                && metadata.Value<string>("byte_order") == "little"
                && metadata["rendering_certified"]?.Type == JTokenType.Boolean && !(bool)metadata["rendering_certified"]
                && metadata["mesh_mapping_ready"]?.Type == JTokenType.Boolean && !(bool)metadata["mesh_mapping_ready"],
                "Unsupported/certified bundle schema");
            var fileRecords = (JObject)metadata["files"];
            var required = new HashSet<string>(fileRecords.Properties().Select(p => p.Name), StringComparer.Ordinal);
            Require(required.Add("manifest.json") && required.Add("complete.json"), "Reserved payload file");
            Require(required.SetEquals(Directory.EnumerateFileSystemEntries(root).Select(Path.GetFileName)),
                "Unexpected/missing bundle entries");
            var files = new Dictionary<string, byte[]>(StringComparer.Ordinal);
            foreach (var property in fileRecords.Properties())
            {
                byte[] payload = FileBytes(root, property.Name);
                Require(payload.LongLength == property.Value.Value<long>("bytes")
                    && Hash(payload) == property.Value.Value<string>("sha256"), "Bundle byte/hash mismatch: " + property.Name);
                files.Add(property.Name, payload);
            }
            byte[] sourceRaw = files["source-manifest.json"], contractRaw = files["source-contract.json"];
            Require(Hash(sourceRaw) == metadata.Value<string>("source_manifest_sha256")
                && Hash(contractRaw) == metadata.Value<string>("contract_sha256"), "Source identity mismatch");
            JObject source = Parse(sourceRaw), contract = Parse(contractRaw);
            Require(source.Value<string>("schema") == "renderdoc-vsin-raw-v1" && contract.Value<int>("schema") == 1
                && contract.Value<string>("raw_manifest_sha256") == Hash(sourceRaw), "Unpinned original manifest");
            foreach (string key in new[] { "frame", "api" })
                Require(JToken.DeepEquals(metadata[key], source[key]) && JToken.DeepEquals(source[key], contract[key]),
                    "Capture frame/API mismatch");
            var sourceEvents = (JObject)source["events"];
            var targetEvents = (JObject)metadata["events"];
            var contractEvents = (JObject)contract["events"];
            var eventIds = new HashSet<string>(sourceEvents.Properties().Select(p => p.Name));
            Require(eventIds.Count > 0 && eventIds.SetEquals(targetEvents.Properties().Select(p => p.Name))
                && eventIds.SetEquals(contractEvents.Properties().Select(p => p.Name)), "Draw set changed");
            var records = new Dictionary<int, NativeDrawRecord>();
            var usedFiles = new HashSet<string> { "source-manifest.json", "source-contract.json" };
            foreach (var property in sourceEvents.Properties())
            {
                int eventId = int.Parse(property.Name);
                Require(eventId.ToString() == property.Name && eventId >= 0, "Invalid event identity");
                var original = (JObject)property.Value;
                var expected = (JObject)contractEvents[property.Name];
                var normalized = (JObject)targetEvents[property.Name];
                foreach (string key in new[] { "part", "shader", "vertices", "indices" })
                    Require(JToken.DeepEquals(original[key], expected[key]), "Draw contract mismatch: " + key);
                var baseRecord = (JObject)original.DeepClone(); baseRecord.Remove("inputs");
                var normalizedBase = (JObject)normalized.DeepClone(); normalizedBase.Remove("attributes");
                Require(JToken.DeepEquals(baseRecord, normalizedBase), "Source draw metadata changed");
                var record = new NativeDrawRecord(eventId, original, normalized, files);
                ValidateDraw(record, original, expected, files, usedFiles);
                records.Add(eventId, record);
            }
            Require(usedFiles.SetEquals(files.Keys), "Unreferenced payload file");
            return new NativeCapturedDrawData(digest, records);
        }

        static void ValidateDraw(NativeDrawRecord record, JObject original, JObject expected,
            IDictionary<string, byte[]> files, ISet<string> usedFiles)
        {
            int count = original.Value<int>("indices");
            Require(record.VertexCount > 0 && count > 0, "Empty draw");
            var formats = (JObject)expected["formats"];
            Require(new HashSet<string>(record.Locations.Select(id => id.ToString())).SetEquals(formats.Properties().Select(p => p.Name)),
                "Input locations changed");
            foreach (int location in record.Locations)
            {
                NativeInput input = record.GetInput(location);
                JObject entry = input.SourceBinding;
                byte[] payload = files[entry.Value<string>("file")];
                usedFiles.Add(entry.Value<string>("file"));
                Require(input.Format == formats.Value<string>(location.ToString()) && Hash(payload) == entry.Value<string>("sha256"),
                    "Native format/hash changed");
                long firstVertex = checked(original.Value<long>("ib_min") + original.Value<long>("base_vertex")
                    + original.Value<long>("vertex_offset"));
                long stride = entry.Value<long>("buffer_stride");
                Require(firstVertex >= 0 && stride >= 0 && entry.Value<long>("offset") >= 0 && entry.Value<long>("buffer_offset") >= 0
                    && entry.Value<long>("first_byte") == checked(entry.Value<long>("buffer_offset")
                        + firstVertex * stride + entry.Value<long>("offset")), "Native input address mismatch");
                if (stride == 0)
                {
                    int size = input.Components * input.ComponentBytes;
                    for (int i = size; i < payload.Length; i++)
                        Require(payload[i] == payload[i % size], "Zero-stride stream not replicated");
                }
            }
            var binding = (JObject)original["index_binding"];
            var draw = (JObject)original["draw"];
            int width = binding.Value<int>("index_stride");
            byte[] indices = record.CopyIndexBytes(); usedFiles.Add(original.Value<string>("ib_file"));
            Require(new[] { 1, 2, 4 }.Contains(width) && indices.Length == checked(count * width), "Index size/format mismatch");
            Require(draw.Value<int>("event") == record.EventId && draw.Value<int>("index_count") == count
                && draw.Value<long>("instances") > 0 && draw.Value<long>("index_offset") >= 0
                && binding.Value<long>("buffer_offset") >= 0 && binding.Value<long>("first_byte")
                    == checked(binding.Value<long>("buffer_offset") + draw.Value<long>("index_offset") * width), "Index draw/address mismatch");
            uint min = uint.MaxValue, max = 0;
            for (int i = 0; i < indices.Length; i += width)
            {
                uint value = 0;
                for (int b = 0; b < width; b++) value |= (uint)indices[i + b] << (b * 8);
                min = Math.Min(min, value); max = Math.Max(max, value);
            }
            Require(min == original.Value<long>("ib_min") && (long)max - min + 1 == record.VertexCount, "Index span mismatch");
            NativeInput weights = record.GetInput(8), slots = record.GetInput(9);
            Require(weights.Components == 4 && slots.Components == 4, "Not four native influences");
            for (int vertex = 0; vertex < record.VertexCount; vertex++)
                for (int component = 0; component < 4; component++)
                {
                    double w = weights.Format.EndsWith("_FLOAT", StringComparison.Ordinal)
                        ? weights.ReadFloat32(vertex, component) : weights.ReadNormalizedComponent(vertex, component);
                    Require(!double.IsNaN(w) && !double.IsInfinity(w) && w >= 0 && w <= 1, "Invalid native weight");
                    slots.ReadUnsignedComponent(vertex, component); // Validate type; never clip or reinterpret as a packed u32.
                }
        }
    }
}
