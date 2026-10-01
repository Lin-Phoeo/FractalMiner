using System.Globalization;
using System.Security.Cryptography;
using System.Text.Json;
using AnimeStudio;

// Read typed MonoScripts even when the player stripped their type trees.
// This inventories declarations; it does not certify external CAB identity.
internal static class ScriptInventory
{
    private static int Main(string[] args)
    {
        try
        {
            if (args.Length != 2)
                throw new ArgumentException("Usage: <serialized file> <NEW inventory.json>");
            var input = Path.GetFullPath(args[0]);
            var output = Path.GetFullPath(args[1]);
            if (!File.Exists(input)) throw new FileNotFoundException("Input missing", input);
            if (File.Exists(output)) throw new IOException("Refusing to overwrite inventory");
            TypeFlags.SetTypes(new Dictionary<ClassIDType, (bool, bool)>());
            TypeFlags.SetType(ClassIDType.MonoScript, true, false);
            Logger.Default = new ConsoleLogger();
            Logger.Flags = LoggerEvent.Error | LoggerEvent.Warning | LoggerEvent.Info;
            var manager = new AssetsManager
            {
                Game = GameManager.GetGameByType(GameType.ArknightsEndfield),
                ResolveDependencies = false,
            };
            manager.LoadFiles(input);
            var objects = manager.assetsFileList.SelectMany(file => file.Objects).ToList();
            var scripts = objects.OfType<MonoScript>().ToList();
            // Failed typed reads may be omitted from Objects. Count the original
            // serialized object table as well, so omission cannot pass this gate.
            var declared = manager.assetsFileList.Sum(file => file.m_Objects.Count(
                info => info.classID == (int)ClassIDType.MonoScript));
            if (scripts.Count == 0 || scripts.Count != declared ||
                scripts.Count != objects.Count(obj => obj.type == ClassIDType.MonoScript))
                throw new InvalidDataException("Incomplete typed MonoScript inventory");
            var rows = scripts.Select(script => new
            {
                Source = script.assetsFile.fileName,
                PathIdDecimal = script.m_PathID.ToString(CultureInfo.InvariantCulture),
                Name = script.m_Name,
                ClassName = script.m_ClassName,
                Namespace = script.m_Namespace,
                Assembly = script.m_AssemblyName,
                RawSha256 = Convert.ToHexString(SHA256.HashData(script.GetRawData())).ToLowerInvariant(),
            }).OrderBy(row => row.Source).ThenBy(row => row.PathIdDecimal).ToArray();
            var report = new
            {
                Format = "EndfieldScriptInventory/1", Input = input,
                InputSha256 = Convert.ToHexString(SHA256.HashData(File.ReadAllBytes(input))).ToLowerInvariant(),
                DeclaredMonoScripts = declared,
                TypedMonoScripts = scripts.Count,
                DeclarationCountGatePassed = true,
                Scripts = rows,
            };
            using var stream = new FileStream(output, FileMode.CreateNew);
            JsonSerializer.Serialize(stream, report, new JsonSerializerOptions { WriteIndented = true });
            Console.WriteLine($"Typed MonoScripts: {rows.Length}; output: {output}");
            return 0;
        }
        catch (Exception error)
        {
            Console.Error.WriteLine(error.Message);
            return 1;
        }
    }
}
