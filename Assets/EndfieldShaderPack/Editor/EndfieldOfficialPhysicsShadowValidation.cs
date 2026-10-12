using System;
using System.IO;
using System.Text;
using EndfieldShaderPack.EditorTools.Mmd;
using UnityEditor;
using UnityEditor.SceneManagement;
using UnityEngine;

namespace EndfieldShaderPack
{
    /// <summary>
    /// Actual Unity/MMD input-publication gate for the official-physics candidate.
    /// It never runs a solver or writes simulation output to the character.
    /// </summary>
    public static class EndfieldOfficialPhysicsShadowValidation
    {
        [Serializable]
        sealed class Report
        {
            public bool ok;
            public string unityVersion;
            public int checks;
            public int groups;
            public int resolvedSkinSlots;
            public int positiveWeightedSlots;
            public int shadowProxyCount;
            public int shadowRenderProxyCount;
            public int shadowHelperProxyCount;
            public int structuralAliasCount;
            public int transformCapacity;
            public int particleCapacity;
            public int frame0TransformWrites;
            public int frame0ParticleTeamWrites;
            public int frame2TransformWrites;
            public int frame2ParticleTeamWrites;
            public int movedTransformSlots;
            public float maxPublishMatrixError;
            public float maxPublishRotationWrite;
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

        static float MatrixDifference(Matrix4x4 a, Matrix4x4 b)
        {
            float error = 0f;
            for (int row = 0; row < 4; row++)
                for (int column = 0; column < 4; column++)
                    error = Mathf.Max(error, Mathf.Abs(a[row, column] - b[row, column]));
            return error;
        }

        static Quaternion[] LocalRotations(Transform[] transforms)
        {
            var result = new Quaternion[transforms.Length];
            for (int i = 0; i < result.Length; i++) result[i] = transforms[i].localRotation;
            return result;
        }

        static float RotationDifference(Transform[] transforms, Quaternion[] before)
        {
            float error = 0f;
            for (int i = 0; i < transforms.Length; i++)
                error = Mathf.Max(error, Quaternion.Angle(transforms[i].localRotation, before[i]));
            return error;
        }

        static int CountOfficialShadowProxies(Transform root)
        {
            int count = 0;
            foreach (Transform transform in root.GetComponentsInChildren<Transform>(true))
                if (transform.name.StartsWith("MBC_Typhoea_", StringComparison.Ordinal) ||
                    transform.name.IndexOf("collider", StringComparison.OrdinalIgnoreCase) >= 0) count++;
            return count;
        }

        static void WriteReport(string output, Report report)
        {
            string path = Path.Combine(output, "report.json");
            using (var stream = new FileStream(path, FileMode.CreateNew, FileAccess.Write))
            using (var writer = new StreamWriter(stream, new UTF8Encoding(false)))
                writer.WriteLine(JsonUtility.ToJson(report, true));
        }

        public static void RunBatch()
        {
            string output = Path.GetFullPath(Env("ENDFIELD_OFFICIAL_SHADOW_OUTPUT"));
            if (Directory.Exists(output)) throw new IOException("Fresh output required: " + output);
            Directory.CreateDirectory(output);
            checks = 0;
            var report = new Report { unityVersion = Application.unityVersion };
            try
            {
                using (var session = new EndfieldWetnessSession(true))
                {
                    session.InitializeMmdPose();
                    session.FrameFront();
                    int shadowProxyCountBefore = CountOfficialShadowProxies(session.Root);
                    using (var inputs = EndfieldOfficialPhysicsShadowInputs.Load(
                        session.Root,
                        Env("ENDFIELD_OFFICIAL_BINDINGS"), Env("ENDFIELD_OFFICIAL_BINDINGS_SHA256"),
                        Env("ENDFIELD_OFFICIAL_IDENTITY"), Env("ENDFIELD_OFFICIAL_IDENTITY_SHA256"),
                        Env("ENDFIELD_OFFICIAL_LAYOUT"), Env("ENDFIELD_OFFICIAL_LAYOUT_SHA256")))
                    {
                        Check(inputs.ShadowOnly, "candidate input publisher must be shadow-only");
                        Check(!inputs.SolverExecuted && !inputs.SolverOutputsWritten,
                            "shadow gate must not execute solver or write outputs");
                        Check(inputs.GroupCount == 11, "all eleven saved groups must bind");
                        Check(inputs.ResolvedSkinSlotCount == 140, "all 140 skin slots must bind");
                        Check(inputs.PositiveWeightedSlotCount > 0 && inputs.PositiveWeightedSlotCount < 140,
                            "official slots must include real weighted bones and recovered unweighted helpers");
                        Check(inputs.ShadowRenderProxyCount == 11 && inputs.ShadowHelperProxyCount == 9 &&
                              inputs.ShadowProxyCount == 20 &&
                              CountOfficialShadowProxies(session.Root) == shadowProxyCountBefore + 20,
                            "missing official component/collider Transforms must use 20 temporary sealed-TRS proxies");
                        Check(inputs.StructuralAliasCount == 1,
                            "the single recovered left-skirt source-name mismatch must bind by parent plus sealed local TRS");
                        Check(inputs.TransformCapacity == 151, "candidate transform capacity must be 151");
                        Check(inputs.ParticleCapacity == 140, "candidate particle capacity must be 140");

                        Transform[] resolved = inputs.ResolvedTransforms;
                        Quaternion[] rotations = LocalRotations(resolved);
                        inputs.PublishCurrentTransformInputs();
                        Matrix4x4[] frame0 = inputs.CopyPublishedTransformMatrices();
                        float matrixError0 = inputs.MaxPublishedTransformMatrixError();
                        float rotationWrite0 = RotationDifference(resolved, rotations);
                        Check(inputs.LastTransformWrites == 151, "frame0 writes every transform slot once");
                        Check(inputs.LastParticleTeamWrites == 140, "frame0 writes every particle Team slot once");
                        Check(matrixError0 <= 1e-6f, "frame0 NativeArray matrices match live Transform getters");
                        Check(rotationWrite0 <= 1e-6f, "frame0 publication does not write character rotations");

                        var player = MmdPlayer.Load(Vmd.ReadFile(Env("ENDFIELD_MMD_TEST_MOTION")), session.Root);
                        Check(player.calibrationOk, "actual VMD calibration must pass before shadow publication");
                        player.Reset();
                        player.ApplyFrame(2f, player.suggestedScale, true, 0f);
                        rotations = LocalRotations(resolved);
                        inputs.PublishCurrentTransformInputs();
                        Matrix4x4[] frame2 = inputs.CopyPublishedTransformMatrices();
                        float matrixError2 = inputs.MaxPublishedTransformMatrixError();
                        float rotationWrite2 = RotationDifference(resolved, rotations);
                        int moved = 0;
                        for (int i = 0; i < frame0.Length; i++)
                            if (MatrixDifference(frame0[i], frame2[i]) > 1e-5f) moved++;
                        Check(inputs.LastTransformWrites == 151, "frame2 writes every transform slot once");
                        Check(inputs.LastParticleTeamWrites == 140, "frame2 writes every particle Team slot once");
                        Check(matrixError2 <= 1e-6f, "frame2 NativeArray matrices match live Transform getters");
                        Check(rotationWrite2 <= 1e-6f, "frame2 publication does not write character rotations");
                        Check(moved > 0, "real VMD changes at least one published transform slot");
                        Check(!inputs.SolverExecuted && !inputs.SolverOutputsWritten,
                            "two-frame shadow publication still has no solver/output side effects");
                        session.SavePreview(Path.Combine(output, "shadow-input-frame2.png"), 960, 600);

                        report.groups = inputs.GroupCount;
                        report.resolvedSkinSlots = inputs.ResolvedSkinSlotCount;
                        report.positiveWeightedSlots = inputs.PositiveWeightedSlotCount;
                        report.shadowProxyCount = inputs.ShadowProxyCount;
                        report.shadowRenderProxyCount = inputs.ShadowRenderProxyCount;
                        report.shadowHelperProxyCount = inputs.ShadowHelperProxyCount;
                        report.structuralAliasCount = inputs.StructuralAliasCount;
                        report.transformCapacity = inputs.TransformCapacity;
                        report.particleCapacity = inputs.ParticleCapacity;
                        report.frame0TransformWrites = frame0.Length;
                        report.frame0ParticleTeamWrites = inputs.ParticleCapacity;
                        report.frame2TransformWrites = inputs.LastTransformWrites;
                        report.frame2ParticleTeamWrites = inputs.LastParticleTeamWrites;
                        report.movedTransformSlots = moved;
                        report.maxPublishMatrixError = Mathf.Max(matrixError0, matrixError2);
                        report.maxPublishRotationWrite = Mathf.Max(rotationWrite0, rotationWrite2);
                        report.shadowOnly = inputs.ShadowOnly;
                        report.solverExecuted = inputs.SolverExecuted;
                        report.solverOutputsWritten = inputs.SolverOutputsWritten;
                    }
                    Check(CountOfficialShadowProxies(session.Root) == shadowProxyCountBefore,
                        "disposing shadow inputs removes all temporary component Transform proxies");
                }
                report.ok = true;
                report.checks = checks;
                WriteReport(output, report);
                Debug.Log("OFFICIAL_PHYSICS_SHADOW_PASS checks=" + checks);
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
