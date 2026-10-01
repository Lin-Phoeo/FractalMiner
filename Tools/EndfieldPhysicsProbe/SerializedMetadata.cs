using System.Text;
using System.Text.Json;
using AnimeStudio;
using Object = AnimeStudio.Object;

// Reuse the existing SceneProbe loader. Only widen its raw metadata selection.
// Identity is (serialized file, PathID), never the potentially duplicate name.
internal static partial class Program
{
    private static List<ExportRecord> ExportSerializedMetadata(IEnumerable<Object> objects, string output)
    {
        var directory = Path.Combine(output, "metadata");
        Directory.CreateDirectory(directory);
        var result = new List<ExportRecord>();
        var sources = new Dictionary<string, int>(StringComparer.Ordinal);
        var identities = new HashSet<(string, long)>();
        var warnings = new List<object>();
        foreach (var obj in objects.Where(value => value.type is ClassIDType.GameObject or
                     ClassIDType.Transform or ClassIDType.RectTransform or ClassIDType.MonoBehaviour or
                     ClassIDType.MonoScript)
                     .OrderBy(value => value.assetsFile.fileName, StringComparer.Ordinal)
                     .ThenBy(value => value.m_PathID))
        {
            var source = obj.assetsFile.fileName;
            if (!identities.Add((source, obj.m_PathID)))
                throw new InvalidDataException($"Duplicate object identity: {source}/{obj.m_PathID}");
            if (!sources.TryGetValue(source, out var sourceIndex))
                sources.Add(source, sourceIndex = sources.Count);
            var previousLogger = Logger.Default;
            var capture = new MetadataLogger(previousLogger);
            string text;
            AssetRef asset;
            try
            {
                Logger.Default = capture;
                text = obj.Dump();
                asset = ToRef(obj);
            }
            finally { Logger.Default = previousLogger; }
            if (capture.Messages.Count > 0)
                warnings.Add(new { Source = source, PathId = obj.m_PathID, Type = obj.type.ToString(), Messages = capture.Messages });
            if (string.IsNullOrWhiteSpace(text))
                throw new InvalidDataException($"Missing raw Dump: {source}/{obj.m_PathID}");
            var path = Path.Combine(directory, $"{sourceIndex}_{obj.m_PathID}_{obj.type}.txt");
            using (var stream = new FileStream(path, FileMode.CreateNew))
            using (var writer = new StreamWriter(stream, new UTF8Encoding(false)))
                writer.Write(text);
            result.Add(new ExportRecord(asset, Path.GetRelativePath(output, path), null));
        }
        var warningPath = Path.Combine(output, "metadata-read-warnings.json");
        using (var stream = new FileStream(warningPath, FileMode.CreateNew))
            JsonSerializer.Serialize(stream, warnings, JsonOptions);
        return result;
    }

    private sealed class MetadataLogger(ILogger previous) : ILogger
    {
        public List<string> Messages { get; } = [];
        public void Log(LoggerEvent loggerEvent, string message)
        {
            // AnimeStudio reports some type-tree size mismatches at Info level.
            if (loggerEvent is LoggerEvent.Error or LoggerEvent.Warning ||
                message.Contains("Error while read type", StringComparison.OrdinalIgnoreCase))
                Messages.Add(message);
            previous.Log(loggerEvent, message);
        }
    }
}
