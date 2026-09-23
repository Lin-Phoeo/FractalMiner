using System;
using System.Collections.Generic;
using System.Globalization;
using System.IO;
using System.Security.Cryptography;
using System.Text;
using UnityEditor;
using UnityEngine;
using UnityEngine.Rendering;

namespace EndfieldShaderPack
{
    // URP asset selection is a project/quality-tier setting, not scene state.
    // Activation therefore happens only here, on an explicit user or batch
    // invocation, and this class owns the timing of every AssetDatabase.SaveAssets
    // so a polluted value can never be flushed by an unrelated scene save.
    public static class EndfieldCapturedPipelineActivation
    {
        public const string PipelinePath = EndfieldCaptureAssets.Root + "/Settings/CapturedPipeline.asset";
        public const string RendererPath = EndfieldCaptureAssets.Root + "/Settings/CapturedRenderer.asset";
        public const string StatePath = "Library/EndfieldCapturedPipelineActivation.json";

        public const string QualitySettingsPath = "ProjectSettings/QualitySettings.asset";
        public const string GraphicsSettingsPath = "ProjectSettings/GraphicsSettings.asset";

        [Serializable]
        public sealed class State
        {
            public int tier;
            public string originalPipelineGuid = "";
            public string activatedPipelineGuid = "";
            public string qualitySha256 = "";
            public string graphicsSha256 = "";
            public string activatedUtc = "";
        }

        // Everything the activate/restore state machine touches, injectable so the
        // isolation gate can exercise the identical code path on a sandbox copy.
        public sealed class Target
        {
            public string qualityPath;
            public string graphicsPath;
            public string statePath;
            public string activatedPipelineGuid;
            public Func<string, bool> originalGuidResolvable;
            public Func<int> readTier;
            public Action<int> writeTier;
            public Func<int, string> readPipelineGuidAt;
            public Action<int, string> writePipelineGuidAt;
            public Action persist;
        }

        public static bool IsActivated => File.Exists(StatePath);

        public static string Sha256(string path)
        {
            using (var sha = SHA256.Create())
            using (var stream = File.OpenRead(path))
                return BitConverter.ToString(sha.ComputeHash(stream)).Replace("-", "").ToLowerInvariant();
        }

        public static State ReadState(string path) => JsonUtility.FromJson<State>(File.ReadAllText(path));

        public static string Describe(string guid) => string.IsNullOrEmpty(guid) ? "<none>" : guid;

        public static string PipelineGuidAt(int tier)
        {
            var asset = QualitySettings.GetRenderPipelineAssetAt(tier);
            if (asset == null) return "";
            string path = AssetDatabase.GetAssetPath(asset);
            return string.IsNullOrEmpty(path) ? "" : AssetDatabase.AssetPathToGUID(path);
        }

        public static RenderPipelineAsset ResolvePipeline(string guid)
        {
            if (string.IsNullOrEmpty(guid)) return null;
            string path = AssetDatabase.GUIDToAssetPath(guid);
            if (string.IsNullOrEmpty(path)) return null;
            return AssetDatabase.LoadAssetAtPath<RenderPipelineAsset>(path);
        }

        public static Target UnityTarget()
        {
            var pipeline = AssetDatabase.LoadAssetAtPath<RenderPipelineAsset>(PipelinePath);
            return new Target
            {
                qualityPath = QualitySettingsPath,
                graphicsPath = GraphicsSettingsPath,
                statePath = StatePath,
                activatedPipelineGuid = pipeline == null ? null : AssetDatabase.AssetPathToGUID(PipelinePath),
                originalGuidResolvable = guid => string.IsNullOrEmpty(guid) || ResolvePipeline(guid) != null,
                readTier = QualitySettings.GetQualityLevel,
                writeTier = tier => QualitySettings.SetQualityLevel(tier, false),
                readPipelineGuidAt = PipelineGuidAt,
                writePipelineGuidAt = WritePipelineGuidAt,
                persist = AssetDatabase.SaveAssets
            };
        }

        static void WritePipelineGuidAt(int tier, string guid)
        {
            int current = QualitySettings.GetQualityLevel();
            if (current != tier) QualitySettings.SetQualityLevel(tier, false);
            try
            {
                QualitySettings.renderPipeline = ResolvePipeline(guid);
            }
            finally
            {
                if (current != tier) QualitySettings.SetQualityLevel(current, false);
            }
        }

        public static State Activate()
        {
            var state = ActivateCore(UnityTarget());
            Debug.Log($"[CapturedPipeline] Activated on quality tier {state.tier}: {Describe(state.originalPipelineGuid)} -> {Describe(state.activatedPipelineGuid)}. State: {StatePath}");
            return state;
        }

        public static State Restore()
        {
            var state = RestoreCore(UnityTarget());
            if (state == null)
                Debug.Log("[CapturedPipeline] No activation state; nothing to restore.");
            else
                Debug.Log($"[CapturedPipeline] Restored quality tier {state.tier} to {Describe(state.originalPipelineGuid)}.");
            return state;
        }

        public static State ActivateCore(Target t)
        {
            if (string.IsNullOrEmpty(t.activatedPipelineGuid))
                throw new InvalidOperationException(
                    "Generated capture pipeline is missing at " + PipelinePath +
                    "; run Endfield/Build Captured Pipeline Showcase first.");

            if (File.Exists(t.statePath))
            {
                var existing = ReadState(t.statePath);
                if ((t.readPipelineGuidAt(existing.tier) ?? "") == existing.activatedPipelineGuid)
                    return existing;
                throw new InvalidOperationException(
                    "Stale activation state at " + t.statePath + ": tier " + existing.tier +
                    " no longer points at the pipeline this tool activated. Run Restore, or resolve the" +
                    " project settings manually and delete the state file, before activating again.");
            }

            int tier = t.readTier();
            var state = new State
            {
                tier = tier,
                originalPipelineGuid = t.readPipelineGuidAt(tier) ?? "",
                activatedPipelineGuid = t.activatedPipelineGuid,
                qualitySha256 = Sha256(t.qualityPath),
                graphicsSha256 = Sha256(t.graphicsPath),
                activatedUtc = DateTime.UtcNow.ToString("o", CultureInfo.InvariantCulture)
            };

            // Written before the mutation: a crash after this point still leaves a
            // restore path instead of an unattributable project settings change.
            WriteState(t.statePath, state);

            try
            {
                t.writePipelineGuidAt(tier, state.activatedPipelineGuid);
                t.persist();
            }
            catch
            {
                Rollback(t, state);
                throw;
            }

            if ((t.readPipelineGuidAt(tier) ?? "") != state.activatedPipelineGuid)
            {
                Rollback(t, state);
                throw new InvalidOperationException("Activation did not take effect on quality tier " + tier + ".");
            }
            return state;
        }

        public static State RestoreCore(Target t)
        {
            if (!File.Exists(t.statePath)) return null;
            var state = ReadState(t.statePath);

            string owning = t.readPipelineGuidAt(state.tier) ?? "";
            if (owning == state.originalPipelineGuid)
            {
                // Already back to the original value, e.g. a restore that crashed
                // before deleting its state file. Clearing it is safe and idempotent.
                File.Delete(t.statePath);
                return state;
            }
            if (owning != state.activatedPipelineGuid)
                throw new InvalidOperationException(
                    "Quality tier " + state.tier + " points at " + Describe(owning) +
                    ", not the pipeline this tool activated (" + Describe(state.activatedPipelineGuid) +
                    "). Someone else changed the project settings; refusing to overwrite their work." +
                    " Resolve manually, then delete " + t.statePath + ".");
            if (!t.originalGuidResolvable(state.originalPipelineGuid))
                throw new InvalidOperationException(
                    "Cannot resolve the original pipeline GUID " + Describe(state.originalPipelineGuid) +
                    "; refusing to leave quality tier " + state.tier + " without a render pipeline.");

            // Restore the tier we own, then hand the editor back to whichever tier
            // the user is actually on: their tier choice is not ours to rewrite.
            int currentTier = t.readTier();
            bool switched = currentTier != state.tier;
            try
            {
                if (switched) t.writeTier(state.tier);
                t.writePipelineGuidAt(state.tier, state.originalPipelineGuid);
                t.persist();
            }
            finally
            {
                if (switched) t.writeTier(currentTier);
            }

            if ((t.readPipelineGuidAt(state.tier) ?? "") != state.originalPipelineGuid)
                throw new InvalidOperationException(
                    "Restore did not return quality tier " + state.tier + " to its original pipeline;" +
                    " keeping " + t.statePath + " so the restore can be retried.");

            File.Delete(t.statePath);
            return state;
        }

        static void WriteState(string path, State state)
        {
            string directory = Path.GetDirectoryName(Path.GetFullPath(path));
            if (!string.IsNullOrEmpty(directory)) Directory.CreateDirectory(directory);
            File.WriteAllText(path, JsonUtility.ToJson(state, true));
        }

        static void Rollback(Target t, State state)
        {
            try
            {
                t.writePipelineGuidAt(state.tier, state.originalPipelineGuid);
                t.persist();
            }
            catch (Exception rollbackFailure)
            {
                Debug.LogWarning("[CapturedPipeline] Rollback reported: " + rollbackFailure.Message);
            }

            // Decide by re-reading, not by which call threw: a failed flush after a
            // successful write still leaves the original value in place.
            if ((t.readPipelineGuidAt(state.tier) ?? "") == state.originalPipelineGuid)
            {
                try { File.Delete(t.statePath); }
                catch (Exception deleteFailure) { Debug.LogError("[CapturedPipeline] Could not remove state file: " + deleteFailure.Message); }
                return;
            }
            Debug.LogError("[CapturedPipeline] Rollback could not return quality tier " + state.tier + " to " +
                           Describe(state.originalPipelineGuid) + "; " + t.statePath +
                           " is kept so Restore can be retried.");
        }

        [MenuItem("Endfield/Captured Pipeline/Activate generated pipeline (project-wide)", false, 66)]
        public static void ActivateFromMenu() => Activate();

        [MenuItem("Endfield/Captured Pipeline/Restore original pipeline (project-wide)", false, 67)]
        public static void RestoreFromMenu() => Restore();

        [MenuItem("Endfield/Captured Pipeline/Report activation state", false, 68)]
        public static void ReportState()
        {
            var report = new StringBuilder();
            report.AppendLine("Endfield captured pipeline activation state");
            report.AppendLine("activated: " + IsActivated);
            if (IsActivated)
            {
                var state = ReadState(StatePath);
                report.AppendLine("tier: " + state.tier);
                report.AppendLine("originalPipelineGuid: " + Describe(state.originalPipelineGuid));
                report.AppendLine("activatedPipelineGuid: " + Describe(state.activatedPipelineGuid));
                report.AppendLine("activatedUtc: " + state.activatedUtc);
                report.AppendLine("qualitySha256AtActivation: " + state.qualitySha256);
                report.AppendLine("graphicsSha256AtActivation: " + state.graphicsSha256);
                report.AppendLine("currentTierPipelineGuid: " + Describe(PipelineGuidAt(state.tier)));
            }
            for (int tier = 0; tier < QualitySettings.names.Length; tier++)
                report.AppendLine($"tier[{tier}] {QualitySettings.names[tier]} -> {Describe(PipelineGuidAt(tier))}");
            report.AppendLine("qualitySha256Now: " + Sha256(QualitySettingsPath));
            report.AppendLine("graphicsSha256Now: " + Sha256(GraphicsSettingsPath));
            Directory.CreateDirectory("Logs");
            File.WriteAllText("Logs/captured-pipeline-activation-state.txt", report.ToString());
            Debug.Log(report.ToString());
        }

        public static IReadOnlyList<string> AllTierGuids()
        {
            var guids = new List<string>();
            for (int tier = 0; tier < QualitySettings.names.Length; tier++) guids.Add(PipelineGuidAt(tier));
            return guids;
        }
    }
}
