using System;
using System.IO;
using System.Text;
using EndfieldShaderPack.EditorTools.Mmd;
using UnityEditor.SceneManagement;
using UnityEngine;

namespace EndfieldShaderPack
{
    /// <summary>
    /// Real-Unity gate for live one-hot proxy skinning and the source reset14
    /// publication. The candidate remains shadow-only and writes no bone output.
    /// </summary>
    public static class EndfieldOfficialPhysicsShadowWorldValidation
    {
        [Serializable]
        sealed class Report
        {
            public bool ok;
            public string unityVersion;
            public int checks;
            public int proxyCapacity;
            public int particleCapacity;
            public int canonicalWorldWrites;
            public int canonicalResetFieldWrites;
            public int mmdFrame0WorldWrites;
            public int mmdFrame0ResetFieldWrites;
            public int frame2WorldWrites;
            public int frame2ResetFieldWrites;
            public int movedWorldSlots;
            public float maxSealedRestPositionProvenanceError;
            public float maxSealedRestRotationProvenanceError;
            public float maxLivePositionError;
            public float maxLiveRotationError;
            public float maxResetError;
            public float maxCharacterRotationWrite;
            public bool shadowOnly;
            public bool solverExecuted;
            public bool solverOutputsWritten;
            public string error;
        }

        static int checks;

        static void Check(bool condition, string message)
        {
            if (!condition) throw new InvalidOperationException(message);
            checks++;
        }

        static string Env(string name)
        {
            string value = Environment.GetEnvironmentVariable(name);
            if (string.IsNullOrWhiteSpace(value))
                throw new InvalidOperationException("Missing environment: " + name);
            return value;
        }

        static Quaternion[] LocalRotations(Transform[] transforms)
        {
            var result = new Quaternion[transforms.Length];
            for (int index = 0; index < result.Length; index++)
                result[index] = transforms[index].localRotation;
            return result;
        }

        static float RotationDifference(Transform[] transforms, Quaternion[] before)
        {
            float maximum = 0f;
            for (int index = 0; index < transforms.Length; index++)
                maximum = Mathf.Max(maximum, Quaternion.Angle(before[index], transforms[index].localRotation));
            return maximum;
        }

        static void WriteReport(string output, Report report)
        {
            using (var stream = new FileStream(
                       Path.Combine(output, "report.json"), FileMode.CreateNew, FileAccess.Write))
            using (var writer = new StreamWriter(stream, new UTF8Encoding(false)))
                writer.WriteLine(JsonUtility.ToJson(report, true));
        }

        public static void RunBatch()
        {
            string output = Path.GetFullPath(Env("ENDFIELD_OFFICIAL_WORLD_OUTPUT"));
            if (Directory.Exists(output)) throw new IOException("Fresh output required: " + output);
            Directory.CreateDirectory(output);
            checks = 0;
            var report = new Report { unityVersion = Application.unityVersion };
            try
            {
                using (var session = new EndfieldWetnessSession(true))
                {
                    session.FrameFront();
                    using (var transforms = EndfieldOfficialPhysicsShadowInputs.Load(
                               session.Root,
                               Env("ENDFIELD_OFFICIAL_BINDINGS"), Env("ENDFIELD_OFFICIAL_BINDINGS_SHA256"),
                               Env("ENDFIELD_OFFICIAL_IDENTITY"), Env("ENDFIELD_OFFICIAL_IDENTITY_SHA256"),
                               Env("ENDFIELD_OFFICIAL_LAYOUT"), Env("ENDFIELD_OFFICIAL_LAYOUT_SHA256")))
                    using (var world = EndfieldOfficialPhysicsShadowWorldInputs.Load(
                               transforms,
                               Env("ENDFIELD_OFFICIAL_IMPORTS"), Env("ENDFIELD_OFFICIAL_IMPORTS_SHA256")))
                    {
                        report.proxyCapacity = world.ProxyCapacity;
                        report.particleCapacity = world.ParticleCapacity;
                        report.shadowOnly = world.ShadowOnly;
                        report.solverExecuted = world.SolverExecuted;
                        report.solverOutputsWritten = world.SolverOutputsWritten;
                        Check(world.ShadowOnly && !world.SolverExecuted && !world.SolverOutputsWritten,
                            "world/reset publisher must remain shadow-only");
                        Check(world.ProxyCapacity == 140 && world.ParticleCapacity == 140,
                            "world/reset capacities must match the sealed eleven-Team layout");

                        Transform[] resolved = transforms.ResolvedTransforms;
                        Quaternion[] rotations = LocalRotations(resolved);
                        transforms.PublishCurrentTransformInputs();
                        world.PublishCurrentWorldProxyAndReset();
                        float referencePositionError = world.MaxSealedReferencePositionError(
                            Env("ENDFIELD_OFFICIAL_GLOBAL_STATE"),
                            Env("ENDFIELD_OFFICIAL_GLOBAL_STATE_SHA256"));
                        float referenceRotationError = world.MaxSealedReferenceRotationError(
                            Env("ENDFIELD_OFFICIAL_GLOBAL_STATE"),
                            Env("ENDFIELD_OFFICIAL_GLOBAL_STATE_SHA256"));
                        float livePositionError0 = world.MaxLiveTransformPositionError();
                        float liveRotationError0 = world.MaxLiveTransformRotationError();
                        float resetError0 = world.MaxResetError();
                        float rotationWrite0 = RotationDifference(resolved, rotations);
                        report.canonicalWorldWrites = world.LastWorldWrites;
                        report.canonicalResetFieldWrites = world.LastResetFieldWrites;
                        report.maxSealedRestPositionProvenanceError = referencePositionError;
                        report.maxSealedRestRotationProvenanceError = referenceRotationError;
                        report.maxLivePositionError = livePositionError0;
                        report.maxLiveRotationError = liveRotationError0;
                        report.maxResetError = resetError0;
                        report.maxCharacterRotationWrite = rotationWrite0;
                        Check(world.LastWorldWrites == 140, "canonical pose writes all world proxy slots once");
                        Check(world.LastResetFieldWrites == 1960, "canonical pose writes reset14 for all particles");
                        Check(referencePositionError <= 5e-5f,
                            "global rest positions retain sealed imports provenance");
                        Check(referenceRotationError <= 5e-4f,
                            "global rest rotations retain sealed imports provenance");
                        Check(livePositionError0 <= 5e-5f,
                            "canonical one-hot world positions match live Transform positions");
                        Check(liveRotationError0 <= 5e-4f,
                            "canonical one-hot world rotations match live Transform rotations");
                        Check(resetError0 <= 1e-6f, "canonical reset14 arrays match world pose and zero caches");
                        Check(rotationWrite0 <= 1e-6f, "canonical world/reset publication does not write bones");

                        // The sealed global state is validated only against its same-domain imports.
                        // Enter MMD calibration after the canonical live one-hot gate, then use
                        // current live Transform equality for the dynamic frame0/frame2 checks.
                        session.InitializeMmdPose();
                        var player = MmdPlayer.Load(
                            Vmd.ReadFile(Env("ENDFIELD_MMD_TEST_MOTION")), session.Root);
                        Check(player.calibrationOk, "actual VMD calibration must pass before live world publication");
                        player.Reset();
                        player.ApplyFrame(0f, player.suggestedScale, true, 0f);
                        rotations = LocalRotations(resolved);
                        transforms.PublishCurrentTransformInputs();
                        world.PublishCurrentWorldProxyAndReset();
                        Vector3[] frame0Positions = world.CopyWorldPositions();
                        Quaternion[] frame0Rotations = world.CopyWorldRotations();
                        float livePositionErrorMmd0 = world.MaxLiveTransformPositionError();
                        float liveRotationErrorMmd0 = world.MaxLiveTransformRotationError();
                        float resetErrorMmd0 = world.MaxResetError();
                        float rotationWriteMmd0 = RotationDifference(resolved, rotations);
                        report.mmdFrame0WorldWrites = world.LastWorldWrites;
                        report.mmdFrame0ResetFieldWrites = world.LastResetFieldWrites;
                        Check(world.LastWorldWrites == 140, "MMD frame0 writes all world proxy slots once");
                        Check(world.LastResetFieldWrites == 1960, "MMD frame0 writes reset14 for all particles");
                        Check(livePositionErrorMmd0 <= 5e-5f,
                            "MMD frame0 one-hot world positions match live Transform positions");
                        Check(liveRotationErrorMmd0 <= 5e-4f,
                            "MMD frame0 one-hot world rotations match live Transform rotations");
                        Check(resetErrorMmd0 <= 1e-6f,
                            "MMD frame0 reset14 arrays match world pose and zero caches");
                        Check(rotationWriteMmd0 <= 1e-6f,
                            "MMD frame0 world/reset publication does not write bones");

                        player.Reset();
                        player.ApplyFrame(2f, player.suggestedScale, true, 0f);
                        rotations = LocalRotations(resolved);
                        transforms.PublishCurrentTransformInputs();
                        world.PublishCurrentWorldProxyAndReset();
                        Vector3[] frame2Positions = world.CopyWorldPositions();
                        Quaternion[] frame2Rotations = world.CopyWorldRotations();
                        int moved = 0;
                        for (int index = 0; index < frame0Positions.Length; index++)
                            if (Vector3.Distance(frame0Positions[index], frame2Positions[index]) > 1e-5f ||
                                Quaternion.Angle(frame0Rotations[index], frame2Rotations[index]) > 1e-3f)
                                moved++;
                        float resetError2 = world.MaxResetError();
                        float rotationWrite2 = RotationDifference(resolved, rotations);
                        float livePositionError2 = world.MaxLiveTransformPositionError();
                        float liveRotationError2 = world.MaxLiveTransformRotationError();
                        report.frame2WorldWrites = world.LastWorldWrites;
                        report.frame2ResetFieldWrites = world.LastResetFieldWrites;
                        report.movedWorldSlots = moved;
                        report.maxResetError = Mathf.Max(resetError0, Mathf.Max(resetErrorMmd0, resetError2));
                        report.maxCharacterRotationWrite = Mathf.Max(
                            rotationWrite0, Mathf.Max(rotationWriteMmd0, rotationWrite2));
                        report.maxLivePositionError = Mathf.Max(
                            livePositionError0, Mathf.Max(livePositionErrorMmd0, livePositionError2));
                        report.maxLiveRotationError = Mathf.Max(
                            liveRotationError0, Mathf.Max(liveRotationErrorMmd0, liveRotationError2));
                        Check(world.LastWorldWrites == 140, "frame2 writes all world proxy slots once");
                        Check(world.LastResetFieldWrites == 1960, "frame2 writes reset14 for all particles");
                        Check(moved > 0, "real VMD frame0-to-frame2 changes at least one live world proxy slot");
                        Check(livePositionError2 <= 5e-5f,
                            "frame2 one-hot world positions match live Transform positions");
                        Check(liveRotationError2 <= 5e-4f,
                            "frame2 one-hot world rotations match live Transform rotations");
                        Check(resetError2 <= 1e-6f, "frame2 reset14 arrays match live world pose and zero caches");
                        Check(rotationWrite2 <= 1e-6f, "frame2 world/reset publication does not write bones");
                        Check(!world.SolverExecuted && !world.SolverOutputsWritten,
                            "two-frame world/reset publication still has no solver/output side effects");
                        session.SavePreview(Path.Combine(output, "shadow-world-frame2.png"), 960, 600);

                    }
                }
                report.ok = true;
                report.checks = checks;
                WriteReport(output, report);
                Debug.Log("OFFICIAL_PHYSICS_SHADOW_WORLD_PASS checks=" + checks);
            }
            catch (Exception error)
            {
                report.ok = false;
                report.checks = checks;
                report.error = error.ToString();
                WriteReport(output, report);
                Debug.LogException(error);
                throw;
            }
            finally
            {
                EditorSceneManager.NewScene(NewSceneSetup.EmptyScene, NewSceneMode.Single);
            }
        }
    }
}
