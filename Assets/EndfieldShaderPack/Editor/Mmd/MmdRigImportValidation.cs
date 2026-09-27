// Batch integration gate for local PMX-derived source-rig JSON. No PMX assets
// or generated rig data are checked into this project.
using System;
using System.Collections.Generic;
using System.IO;
using UnityEngine;

namespace EndfieldShaderPack.EditorTools.Mmd
{
    public static class MmdRigImportValidation
    {
        [Serializable]
        class SourceSample
        {
            public float seconds;
            public Vector3 hip, leftWrist, rightWrist, leftAnkle, rightAnkle;
        }

        [Serializable]
        class SourceReport
        {
            public string rigName;
            public int bones, unmapped;
            public List<SourceSample> samples = new List<SourceSample>();
        }

        public static void Run()
        {
            const string minimal = "{\"name\":\"test\",\"bones\":[" +
                "{\"name\":\"全ての親\",\"rest\":[0,0,0],\"parent\":-1,\"grant\":-1}," +
                "{\"name\":\"センター\",\"rest\":[0,1,0],\"parent\":0,\"grant\":-1}]}";
            var tiny = MmdRigDefinition.FromJson(minimal);
            if (tiny.bones.Count != 2 || tiny.Find("センター") != 1 ||
                Mathf.Abs(tiny.bones[1].rest.y - 1f) > 1e-5f)
                throw new InvalidOperationException("PMX source-rig JSON did not preserve names/rest positions.");
            const string invalid = "{\"name\":\"bad\",\"bones\":[" +
                "{\"name\":\"x\",\"rest\":[0,0,0],\"parent\":5,\"grant\":-1}]}";
            try
            {
                MmdRigDefinition.FromJson(invalid);
                throw new InvalidOperationException("Invalid parent was accepted.");
            }
            catch (InvalidDataException) { }

            // VMDs rarely key ひざ/足首, so IK must still bend links that have no track.
            const string leg = "{\"name\":\"leg\",\"bones\":[" +
                "{\"name\":\"全ての親\",\"rest\":[0,0,0],\"parent\":-1,\"grant\":-1}," +
                "{\"name\":\"右足\",\"rest\":[-1,10,0],\"parent\":0,\"grant\":-1}," +
                "{\"name\":\"右ひざ\",\"rest\":[-1,5,0],\"parent\":1,\"grant\":-1}," +
                "{\"name\":\"右足首\",\"rest\":[-1,1,0],\"parent\":2,\"grant\":-1}," +
                "{\"name\":\"右足IK\",\"rest\":[-1,1,0],\"parent\":0,\"grant\":-1,\"effector\":3," +
                "\"iterations\":40,\"angleLimit\":2,\"links\":[" +
                "{\"bone\":2,\"limited\":true,\"minimum\":[-3.1415927,0,0],\"maximum\":[-0.008726646,0,0]}," +
                "{\"bone\":1,\"limited\":false}]}]}";
            var legRig = MmdRigDefinition.FromJson(leg);
            var legClip = new VmdMotionClip();
            legClip.bones["右足"] = new List<VmdBoneKey> { new VmdBoneKey { rotation = VQuat.Identity } };
            legClip.bones["右足IK"] = new List<VmdBoneKey> {
                new VmdBoneKey { position = new VVec3 { y = 2.5f, z = -2f }, rotation = VQuat.Identity } };
            var legEvaluator = new MmdRigEvaluator();
            legEvaluator.Bind(legRig, legClip);
            legEvaluator.Sample(0);
            float legError = Vector3.Distance(legEvaluator.pose.positions[legRig.Find("右足首")],
                legEvaluator.pose.positions[legRig.Find("右足IK")]);
            if (legError > 0.01f)
                throw new InvalidOperationException("IK left the untracked knee unbent; ankle error " + legError);

            string[] args = Environment.GetCommandLineArgs();
            string Arg(string key)
            {
                for (int i = 0; i + 1 < args.Length; ++i)
                    if (args[i] == key) return args[i + 1];
                return null;
            }
            string path = Arg("-mmdRigPath");
            if (string.IsNullOrEmpty(path))
                throw new InvalidOperationException("Pass -mmdRigPath <local exported JSON|standard>.");
            var rig = path == "standard" ? MmdRigDefinition.StandardMmd() :
                MmdRigDefinition.FromFile(path);
            if (rig.bones.Count < 50 || rig.Find("左手首") < 0 || rig.Find("右足IK") < 0)
                throw new InvalidOperationException("MMD source rig is incomplete: " + path);
            Debug.Log("[MmdRigImport] PASS " + rig.name + " bones=" + rig.bones.Count +
                      " leftWrist=" + rig.bones[rig.Find("左手首")].rest);

            string motionPath = Arg("-mmdMotionPath");
            string reportPath = Arg("-mmdOutput");
            if (string.IsNullOrEmpty(motionPath) || string.IsNullOrEmpty(reportPath)) return;
            var motion = Vmd.ReadFile(motionPath);
            var evaluator = new MmdRigEvaluator();
            evaluator.Bind(rig, motion);
            var report = new SourceReport { rigName = rig.name, bones = rig.bones.Count,
                unmapped = evaluator.unmapped.Count };
            double[] times = { 0, motion.Duration * .25, motion.Duration * .5,
                motion.Duration * .75, motion.Duration };
            foreach (double time in times)
            {
                evaluator.Sample(time * 30.0);
                Vector3 Pos(string name)
                {
                    int index = rig.Find(name);
                    if (index < 0) throw new InvalidOperationException("Missing source role: " + name);
                    Vector3 value = evaluator.pose.positions[index];
                    if (float.IsNaN(value.sqrMagnitude) || float.IsInfinity(value.sqrMagnitude))
                        throw new InvalidOperationException("Non-finite source pose: " + name);
                    return value;
                }
                report.samples.Add(new SourceSample {
                    seconds = (float)time,
                    hip = Pos("下半身"), leftWrist = Pos("左手首"),
                    rightWrist = Pos("右手首"), leftAnkle = Pos("左足首"),
                    rightAnkle = Pos("右足首")
                });
            }
            Directory.CreateDirectory(Path.GetDirectoryName(reportPath));
            File.WriteAllText(reportPath, JsonUtility.ToJson(report, true));
            Debug.Log("[MmdRigImport] A/B PASS " + rig.name + " unmapped=" + report.unmapped +
                      " samples=" + report.samples.Count);
        }
    }
}
