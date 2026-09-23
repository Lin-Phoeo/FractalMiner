using System;
using System.Collections.Generic;
using System.Globalization;
using System.IO;
using System.Text;
using UnityEditor;
using UnityEngine;

namespace EndfieldShaderPack
{
    // Proves the activate/restore state machine returns the settings files it owns
    // to byte-identical content, including on the exception, tier-switch and
    // third-party paths. Everything runs against a sandbox copy under Library/, so
    // the test can never pollute the only real project, and the real
    // ProjectSettings hashes are asserted unchanged across the whole run.
    //
    // Boundary: this validates the snapshot/ownership/rollback algorithm and its
    // byte exactness. It does not model Unity's own serializer; that half is covered
    // by EndfieldCapturedSceneBuilder.BuildAndValidate, which snapshots the real
    // files after a normalisation pass and then proves Build() introduces no diff.
    public static class EndfieldCapturedPipelineIsolationValidation
    {
        const string SandboxRoot = "Library/EndfieldIsolationSandbox";
        const string ReportPath = "Logs/captured-pipeline-isolation.txt";
        const string ThirdPartyGuid = "0000000000000000000000000000dead";
        static int sequence;

        [MenuItem("Endfield/Captured Pipeline/Validate activation isolation (sandbox)", false, 69)]
        public static void RunAll()
        {
            var report = new StringBuilder();
            int failures = RunAll(report);
            Directory.CreateDirectory("Logs");
            File.WriteAllText(ReportPath, report.ToString());
            Debug.Log(report.ToString());
            if (failures != 0)
                throw new InvalidOperationException(failures + " captured pipeline isolation check(s) failed; see " + ReportPath);
        }

        public static int RunAll(StringBuilder report)
        {
            string activatedGuid = AssetDatabase.AssetPathToGUID(EndfieldCapturedPipelineActivation.PipelinePath);
            if (string.IsNullOrEmpty(activatedGuid))
                throw new InvalidOperationException(
                    "Generated capture pipeline has no GUID at " + EndfieldCapturedPipelineActivation.PipelinePath +
                    "; run Endfield/Build Captured Pipeline Showcase before the isolation gate.");

            string realQualityBefore = EndfieldCapturedPipelineActivation.Sha256(EndfieldCapturedPipelineActivation.QualitySettingsPath);
            string realGraphicsBefore = EndfieldCapturedPipelineActivation.Sha256(EndfieldCapturedPipelineActivation.GraphicsSettingsPath);

            // Previous run's sandboxes are removed so this one stays inspectable
            // afterwards without accumulating under Library/.
            sequence = 0;
            if (Directory.Exists(SandboxRoot)) Directory.Delete(SandboxRoot, true);

            int failures = 0;
            report.AppendLine("Endfield captured pipeline activation isolation (sandbox)");
            report.AppendLine("sandbox: " + SandboxRoot);
            report.AppendLine("activatedPipelineGuid: " + activatedGuid);
            report.AppendLine("realTierCount: " + QualitySettings.names.Length);
            report.AppendLine();

            Check(report, ref failures, "sandbox copy is byte-identical to the real settings", () =>
            {
                var sandbox = new Sandbox(activatedGuid);
                return sandbox.CopyError;
            });

            for (int tier = 0; tier < QualitySettings.names.Length; tier++)
            {
                int captured = tier;
                Check(report, ref failures, $"tier {captured} ({QualitySettings.names[captured]}): activate mutates, restore is byte-exact", () =>
                {
                    var sandbox = new Sandbox(activatedGuid) { tier = captured };
                    string qualityBefore = sandbox.QualityHash, graphicsBefore = sandbox.GraphicsHash;

                    var state = EndfieldCapturedPipelineActivation.ActivateCore(sandbox.Target);
                    if (state.tier != captured) return "state recorded tier " + state.tier + ", expected " + captured;
                    if (sandbox.QualityHash == qualityBefore)
                        return "activation did not change the sandbox file; the gate would pass vacuously";
                    if (sandbox.ReadGuidAt(captured) != activatedGuid)
                        return "tier still points at " + sandbox.ReadGuidAt(captured);
                    if (!sandbox.StateExists) return "no state file was written";

                    var restored = EndfieldCapturedPipelineActivation.RestoreCore(sandbox.Target);
                    if (restored == null) return "restore reported nothing owned";
                    if (sandbox.QualityHash != qualityBefore) return "QualitySettings was not restored byte-exactly";
                    if (sandbox.GraphicsHash != graphicsBefore) return "GraphicsSettings was not restored byte-exactly";
                    if (sandbox.StateExists) return "state file survived a successful restore";
                    return null;
                });
            }

            Check(report, ref failures, "persistence failure during activate rolls back byte-exactly", () =>
            {
                var sandbox = new Sandbox(activatedGuid);
                string before = sandbox.QualityHash;
                sandbox.FailPersist = true;
                try
                {
                    EndfieldCapturedPipelineActivation.ActivateCore(sandbox.Target);
                    return "activate did not surface the injected persistence failure";
                }
                catch (InvalidOperationException) { }
                if (sandbox.QualityHash != before) return "rollback left the sandbox file modified";
                if (sandbox.StateExists) return "rollback left a state file behind";
                return null;
            });

            Check(report, ref failures, "activation that does not take effect rolls back", () =>
            {
                var sandbox = new Sandbox(activatedGuid) { SwallowWrites = true };
                string before = sandbox.QualityHash;
                try
                {
                    EndfieldCapturedPipelineActivation.ActivateCore(sandbox.Target);
                    return "activate accepted a write that never landed";
                }
                catch (InvalidOperationException) { }
                if (sandbox.QualityHash != before) return "file changed even though writes were swallowed";
                if (sandbox.StateExists) return "state file survived the rollback";
                return null;
            });

            Check(report, ref failures, "tier switch during activation restores the owning tier and keeps the user's tier", () =>
            {
                int owningTier = QualitySettings.GetQualityLevel();
                int otherTier = (owningTier + 1) % QualitySettings.names.Length;
                var sandbox = new Sandbox(activatedGuid) { tier = owningTier };
                var baseline = sandbox.AllTierGuids();

                var state = EndfieldCapturedPipelineActivation.ActivateCore(sandbox.Target);
                sandbox.Target.writeTier(otherTier);
                EndfieldCapturedPipelineActivation.RestoreCore(sandbox.Target);

                var after = sandbox.AllTierGuids();
                for (int i = 0; i < baseline.Count; i++)
                    if (baseline[i] != after[i])
                        return "tier " + i + " pipeline changed from " + baseline[i] + " to " + after[i];
                if (state.tier != owningTier) return "state owned tier " + state.tier;
                if (sandbox.tier != otherTier)
                    return "restore hijacked the user's tier selection: expected " + otherTier + ", got " + sandbox.tier;
                if (sandbox.StateExists) return "state file survived a successful restore";
                return null;
            });

            Check(report, ref failures, "third-party change to the owning tier is refused, not overwritten", () =>
            {
                var sandbox = new Sandbox(activatedGuid);
                int tier = sandbox.tier;
                EndfieldCapturedPipelineActivation.ActivateCore(sandbox.Target);
                sandbox.WriteGuidAt(tier, ThirdPartyGuid);

                try
                {
                    EndfieldCapturedPipelineActivation.RestoreCore(sandbox.Target);
                    return "restore clobbered a third-party project settings change";
                }
                catch (InvalidOperationException e)
                {
                    if (!e.Message.Contains("refusing to overwrite")) return "unexpected refusal reason: " + e.Message;
                }
                if (sandbox.ReadGuidAt(tier) != ThirdPartyGuid) return "third-party value was modified";
                if (!sandbox.StateExists) return "state file was deleted despite the refusal, losing the retry path";
                return null;
            });

            Check(report, ref failures, "third-party clearing the tier pipeline is refused", () =>
            {
                var sandbox = new Sandbox(activatedGuid);
                int tier = sandbox.tier;
                string original = sandbox.ReadGuidAt(tier);
                if (string.IsNullOrEmpty(original)) return null; // tier had no pipeline; nothing to distinguish
                EndfieldCapturedPipelineActivation.ActivateCore(sandbox.Target);
                sandbox.WriteGuidAt(tier, "");
                try
                {
                    EndfieldCapturedPipelineActivation.RestoreCore(sandbox.Target);
                    return "restore accepted a tier somebody else had cleared";
                }
                catch (InvalidOperationException e)
                {
                    if (!e.Message.Contains("refusing to overwrite")) return "unexpected refusal reason: " + e.Message;
                }
                if (sandbox.ReadGuidAt(tier) != "") return "cleared value was rewritten";
                return null;
            });

            Check(report, ref failures, "activate is idempotent while it still owns the tier", () =>
            {
                var sandbox = new Sandbox(activatedGuid);
                var first = EndfieldCapturedPipelineActivation.ActivateCore(sandbox.Target);
                string afterFirst = sandbox.QualityHash;
                var second = EndfieldCapturedPipelineActivation.ActivateCore(sandbox.Target);
                if (second.tier != first.tier || second.activatedPipelineGuid != first.activatedPipelineGuid)
                    return "second activate returned a different ownership record";
                if (sandbox.QualityHash != afterFirst) return "second activate rewrote the settings file";
                EndfieldCapturedPipelineActivation.RestoreCore(sandbox.Target);
                return sandbox.StateExists ? "state file survived restore" : null;
            });

            Check(report, ref failures, "activate refuses stale state it no longer owns", () =>
            {
                var sandbox = new Sandbox(activatedGuid);
                int tier = sandbox.tier;
                EndfieldCapturedPipelineActivation.ActivateCore(sandbox.Target);
                sandbox.WriteGuidAt(tier, ThirdPartyGuid);
                try
                {
                    EndfieldCapturedPipelineActivation.ActivateCore(sandbox.Target);
                    return "activate took ownership away from a third-party value";
                }
                catch (InvalidOperationException e)
                {
                    if (!e.Message.Contains("Stale activation state")) return "unexpected refusal reason: " + e.Message;
                }
                return sandbox.ReadGuidAt(tier) != ThirdPartyGuid ? "third-party value was modified" : null;
            });

            Check(report, ref failures, "restore with no state file is a no-op", () =>
            {
                var sandbox = new Sandbox(activatedGuid);
                string before = sandbox.QualityHash;
                if (EndfieldCapturedPipelineActivation.RestoreCore(sandbox.Target) != null)
                    return "restore claimed ownership it never had";
                return sandbox.QualityHash != before ? "restore modified the file without owning anything" : null;
            });

            Check(report, ref failures, "restore clears stale state when the value is already original", () =>
            {
                var sandbox = new Sandbox(activatedGuid);
                int tier = sandbox.tier;
                string before = sandbox.QualityHash;
                var state = EndfieldCapturedPipelineActivation.ActivateCore(sandbox.Target);
                sandbox.WriteGuidAt(tier, state.originalPipelineGuid);
                if (EndfieldCapturedPipelineActivation.RestoreCore(sandbox.Target) == null)
                    return "restore did not report the state it cleared";
                if (sandbox.StateExists) return "stale state file was not cleared";
                return sandbox.QualityHash != before ? "file is not back to its original bytes" : null;
            });

            Check(report, ref failures, "restore refuses when the original pipeline GUID cannot be resolved", () =>
            {
                var sandbox = new Sandbox(activatedGuid);
                int tier = sandbox.tier;
                var state = EndfieldCapturedPipelineActivation.ActivateCore(sandbox.Target);
                state.originalPipelineGuid = ThirdPartyGuid; // registered nowhere in the sandbox
                File.WriteAllText(sandbox.StatePath, JsonUtility.ToJson(state, true));
                try
                {
                    EndfieldCapturedPipelineActivation.RestoreCore(sandbox.Target);
                    return "restore proceeded with an unresolvable original pipeline";
                }
                catch (InvalidOperationException e)
                {
                    if (!e.Message.Contains("Cannot resolve the original pipeline GUID"))
                        return "unexpected refusal reason: " + e.Message;
                }
                if (!sandbox.StateExists) return "state file was deleted, losing the retry path";
                if (sandbox.ReadGuidAt(tier) != sandbox.ActivatedGuid) return "activated value was disturbed";
                return null;
            });

            Check(report, ref failures, "real ProjectSettings untouched by the whole sandbox run", () =>
            {
                string quality = EndfieldCapturedPipelineActivation.Sha256(EndfieldCapturedPipelineActivation.QualitySettingsPath);
                string graphics = EndfieldCapturedPipelineActivation.Sha256(EndfieldCapturedPipelineActivation.GraphicsSettingsPath);
                if (quality != realQualityBefore) return "QualitySettings.asset changed: " + realQualityBefore + " -> " + quality;
                if (graphics != realGraphicsBefore) return "GraphicsSettings.asset changed: " + realGraphicsBefore + " -> " + graphics;
                return null;
            });

            report.AppendLine();
            report.AppendLine(failures == 0
                ? "PASS: activation isolation holds on the sandbox copy; the real ProjectSettings bytes never changed."
                : "FAIL: " + failures + " isolation check(s) failed.");
            return failures;
        }

        static void Check(StringBuilder report, ref int failures, string name, Func<string> body)
        {
            string error;
            try
            {
                error = body();
            }
            catch (Exception e)
            {
                error = "unexpected " + e.GetType().Name + ": " + e.Message;
            }
            if (error == null) report.AppendLine("PASS  " + name);
            else
            {
                failures++;
                report.AppendLine("FAIL  " + name + " :: " + error);
            }
        }

        // File-backed stand-in for the Unity QualitySettings API, so the production
        // state machine in EndfieldCapturedPipelineActivation runs unchanged here.
        sealed class Sandbox
        {
            public readonly string QualityPath;
            public readonly string GraphicsPath;
            public readonly string StatePath;
            public readonly string ActivatedGuid;
            public readonly string CopyError;
            public int tier;
            public bool FailPersist;
            public bool SwallowWrites;

            readonly HashSet<string> resolvable = new HashSet<string>(StringComparer.Ordinal);

            public Sandbox(string activatedGuid)
            {
                ActivatedGuid = activatedGuid;
                string root = SandboxRoot + "/" + (++sequence).ToString("D2", CultureInfo.InvariantCulture);
                QualityPath = root + "/ProjectSettings/QualitySettings.asset";
                GraphicsPath = root + "/ProjectSettings/GraphicsSettings.asset";
                StatePath = root + "/activation.json";
                tier = QualitySettings.GetQualityLevel();
                try
                {
                    Directory.CreateDirectory(root + "/ProjectSettings");
                    File.Copy(EndfieldCapturedPipelineActivation.QualitySettingsPath, QualityPath, true);
                    File.Copy(EndfieldCapturedPipelineActivation.GraphicsSettingsPath, GraphicsPath, true);
                    foreach (string guid in ScanGuids(QualityPath)) resolvable.Add(guid);
                    foreach (string guid in ScanGuids(GraphicsPath)) resolvable.Add(guid);
                }
                catch (Exception e)
                {
                    CopyError = "could not build the sandbox: " + e.Message;
                }
            }

            public string QualityHash => EndfieldCapturedPipelineActivation.Sha256(QualityPath);
            public string GraphicsHash => EndfieldCapturedPipelineActivation.Sha256(GraphicsPath);
            public bool StateExists => File.Exists(StatePath);

            public EndfieldCapturedPipelineActivation.Target Target => new EndfieldCapturedPipelineActivation.Target
            {
                qualityPath = QualityPath,
                graphicsPath = GraphicsPath,
                statePath = StatePath,
                activatedPipelineGuid = ActivatedGuid,
                originalGuidResolvable = guid => string.IsNullOrEmpty(guid) || resolvable.Contains(guid),
                readTier = () => tier,
                writeTier = value => { tier = value; WriteCurrentQuality(value); },
                readPipelineGuidAt = ReadGuidAt,
                writePipelineGuidAt = (target, guid) => WriteGuidAt(target, guid),
                persist = () =>
                {
                    if (FailPersist) throw new InvalidOperationException("Injected persistence failure.");
                }
            };

            public List<string> AllTierGuids()
            {
                var guids = new List<string>();
                for (int i = 0; i < TierCount(); i++) guids.Add(ReadGuidAt(i));
                return guids;
            }

            public string ReadGuidAt(int tierIndex)
            {
                string[] lines = ReadLines();
                int line = PipelineLine(lines, TierStart(lines, tierIndex), TierEnd(lines, tierIndex));
                int at = lines[line].IndexOf("guid: ", StringComparison.Ordinal);
                if (at < 0) return "";
                int from = at + "guid: ".Length;
                int to = lines[line].IndexOf(',', from);
                return (to < 0 ? lines[line].Substring(from) : lines[line].Substring(from, to - from)).Trim();
            }

            public void WriteGuidAt(int tierIndex, string guid)
            {
                if (SwallowWrites) return;
                string[] lines = ReadLines();
                int line = PipelineLine(lines, TierStart(lines, tierIndex), TierEnd(lines, tierIndex));
                lines[line] = string.IsNullOrEmpty(guid)
                    ? "    customRenderPipeline: {fileID: 0}"
                    : "    customRenderPipeline: {fileID: 11400000, guid: " + guid + ", type: 2}";
                WriteLines(lines);
            }

            void WriteCurrentQuality(int value)
            {
                if (SwallowWrites) return;
                string[] lines = ReadLines();
                for (int i = 0; i < lines.Length; i++)
                    if (lines[i].StartsWith("  m_CurrentQuality:", StringComparison.Ordinal))
                    {
                        lines[i] = "  m_CurrentQuality: " + value.ToString(CultureInfo.InvariantCulture);
                        WriteLines(lines);
                        return;
                    }
                throw new InvalidOperationException("Sandbox QualitySettings has no m_CurrentQuality key.");
            }

            int TierCount()
            {
                string[] lines = ReadLines();
                int count = 0;
                Range(lines, out int start, out int end);
                for (int i = start; i < end; i++)
                    if (lines[i].StartsWith("  - ", StringComparison.Ordinal)) count++;
                return count;
            }

            int TierStart(string[] lines, int tierIndex)
            {
                Range(lines, out int start, out int end);
                int seen = -1;
                for (int i = start; i < end; i++)
                    if (lines[i].StartsWith("  - ", StringComparison.Ordinal) && ++seen == tierIndex) return i;
                throw new InvalidOperationException("Quality tier " + tierIndex + " is not in the sandbox file.");
            }

            int TierEnd(string[] lines, int tierIndex)
            {
                int from = TierStart(lines, tierIndex) + 1;
                Range(lines, out _, out int end);
                for (int i = from; i < end; i++)
                    if (lines[i].StartsWith("  - ", StringComparison.Ordinal)) return i;
                return end;
            }

            static int PipelineLine(string[] lines, int start, int end)
            {
                for (int i = start; i < end; i++)
                    if (lines[i].StartsWith("    customRenderPipeline:", StringComparison.Ordinal)) return i;
                throw new InvalidOperationException("Quality tier block has no customRenderPipeline key.");
            }

            static void Range(string[] lines, out int start, out int end)
            {
                start = -1;
                for (int i = 0; i < lines.Length; i++)
                    if (lines[i] == "  m_QualitySettings:") { start = i + 1; break; }
                if (start < 0) throw new InvalidOperationException("Sandbox QualitySettings has no m_QualitySettings list.");
                end = lines.Length;
                for (int i = start; i < lines.Length; i++)
                    if (lines[i].StartsWith("  m_", StringComparison.Ordinal)) { end = i; break; }
            }

            string[] ReadLines() => File.ReadAllText(QualityPath).Split('\n');
            void WriteLines(string[] lines) => File.WriteAllText(QualityPath, string.Join("\n", lines));

            static IEnumerable<string> ScanGuids(string path)
            {
                string text = File.ReadAllText(path);
                for (int at = text.IndexOf("guid: ", StringComparison.Ordinal); at >= 0; at = text.IndexOf("guid: ", at + 1, StringComparison.Ordinal))
                {
                    int from = at + "guid: ".Length;
                    int to = from;
                    while (to < text.Length && Uri.IsHexDigit(text[to])) to++;
                    if (to - from == 32) yield return text.Substring(from, 32);
                }
            }
        }
    }
}
