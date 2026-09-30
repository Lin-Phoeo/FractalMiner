using System;
using System.IO;
using System.Collections.Generic;
using UnityEditor;
using UnityEditor.SceneManagement;
using UnityEngine;
using EndfieldShaderPack.EditorTools.Mmd;

namespace EndfieldShaderPack.EditorTools
{
    public static class EndfieldSkinBasisValidation
    {
        // Loader/pose-to-shader smoke only. Not an oracle comparison, IK/physics
        // accuracy verdict, image comparison or completed dance-video gate.
        public static void RunAnimationInputs()
        {
            string motionPath = Environment.GetEnvironmentVariable("ENDFIELD_BASIS_TEST_VMD");
            string output = Environment.GetEnvironmentVariable("ENDFIELD_BASIS_TEST_REPORT");
            if (!File.Exists(motionPath) || string.IsNullOrEmpty(output) || File.Exists(output))
                throw new InvalidOperationException("Provide an existing VMD and a fresh report path.");
            var samples = new List<object>();
            try
            {
                Transform root = OpenDanceRoot();
                var clip = AssetDatabase.LoadAssetAtPath<AnimationClip>(
                    "Assets/Typhoeus/AnimationsDecoded/A_actor_typhoea_battle_attack_01.anim");
                if (clip == null || clip.length <= 0 || AnimationUtility.GetCurveBindings(clip).Length == 0)
                    throw new InvalidOperationException("Decoded native animation is missing/empty.");
                foreach (float fraction in new[] { 0f, .25f, .5f })
                {
                    clip.SampleAnimation(root.gameObject, clip.length * fraction);
                    Endfield.EndfieldSkinBasisDriver.ApplyForTyphoeus(root);
                    CheckRealBindings(root);
                    samples.Add(new { source = "decoded-native-clip", fraction, basis = "live" });
                }
                root = OpenDanceRoot(); // Calibration must not inherit native animated pose.
                var motion = Vmd.ReadFile(motionPath);
                string rigPath = Environment.GetEnvironmentVariable("ENDFIELD_BASIS_TEST_RIG");
                var rig = string.IsNullOrEmpty(rigPath) ? null : MmdRigDefinition.FromFile(rigPath);
                var player = MmdPlayer.Load(motion, root, rig);
                if (!player.calibrationOk) throw new InvalidOperationException("MMD calibration: " + player.profile.calibrationError);
                foreach (float fraction in new[] { 0f, .25f, .5f })
                {
                    player.Reset();
                    player.ApplyFrame((float)motion.Duration * fraction, player.suggestedScale, true, 0);
                    Endfield.EndfieldSkinBasisDriver.ApplyForTyphoeus(root);
                    CheckRealBindings(root);
                    samples.Add(new { source = "VMD-MmdPlayer", fraction, basis = "live" });
                }
                File.WriteAllText(output, Newtonsoft.Json.JsonConvert.SerializeObject(new {
                    status = "pass", scope = "loader -> pose -> dynamic skin basis, NOT MMD fidelity/complete video",
                    nativeClip = AssetDatabase.GetAssetPath(clip), nativeCurves = AnimationUtility.GetCurveBindings(clip).Length,
                    motionPath, sourceRig = player.sourceRig.name, samples
                }, Newtonsoft.Json.Formatting.Indented));
                Debug.Log("[SkinBasisAnimationInputs] PASS: decoded native clip + VMD, six post-pose shader binding checks; " + output);
            }
            finally { EditorSceneManager.NewScene(NewSceneSetup.EmptyScene, NewSceneMode.Single); }
        }

        static Transform OpenDanceRoot()
        {
            var scene = EditorSceneManager.OpenScene(EndfieldMmdStageBuilder.DanceScenePath, OpenSceneMode.Single);
            foreach (var go in scene.GetRootGameObjects())
                if (go.name == "chr_0034_typhoea_rebuilt") return go.transform;
            throw new InvalidOperationException("Dance character root missing.");
        }

        static void CheckRealBindings(Transform root)
        {
            int checkedSlots = 0;
            foreach (var renderer in root.GetComponentsInChildren<SkinnedMeshRenderer>())
            {
                if (!renderer.name.EndsWith("_typhoea_face_01_lod0", StringComparison.Ordinal)
                    && !renderer.name.EndsWith("_typhoea_body_01_lod0", StringComparison.Ordinal)) continue;
                for (int slot = 0; slot < renderer.sharedMaterials.Length; slot++)
                {
                    var block = new MaterialPropertyBlock();
                    renderer.GetPropertyBlock(block, slot);
                    if (block.GetFloat("_EndfieldSkinBasisEnabled") != 1) throw new Exception("Real shader slot not bound.");
                    checkedSlots++;
                }
            }
            if (checkedSlots != 2) throw new Exception("Expected face and body skin slots, got " + checkedSlots);
        }

        public static void Run()
        {
            var root = new GameObject("SkinBasisValidation");
            var material = new Material(Shader.Find("Endfield/CharacterLit"));
            try
            {
                material.SetFloat("_MaterialFamily", 1);
                var head = new GameObject("Bip001_Head").transform;
                var spine = new GameObject("Bip001_Spine2").transform;
                head.SetParent(root.transform, false);
                spine.SetParent(root.transform, false);
                var face = new GameObject("S_actor_typhoea_face_01_lod0").AddComponent<SkinnedMeshRenderer>();
                var body = new GameObject("S_actor_typhoea_body_01_lod0").AddComponent<SkinnedMeshRenderer>();
                face.transform.SetParent(root.transform, false);
                body.transform.SetParent(root.transform, false);
                face.sharedMaterial = body.sharedMaterial = material;
                var block = new MaterialPropertyBlock();
                block.SetFloat("_BasisValidationPreserved", 7);
                face.SetPropertyBlock(block, 0);
                for (int pose = 0; pose < 3; pose++)
                {
                    head.localPosition = new Vector3(pose, 1.2f, -pose);
                    head.localRotation = Quaternion.Euler(pose * 31, pose * -47, pose * 13);
                    spine.localPosition = new Vector3(-pose, .8f, pose * .5f);
                    spine.localRotation = Quaternion.Euler(pose * -17, pose * 19, pose * 29);
                    Endfield.EndfieldSkinBasisDriver.ApplyForTyphoeus(root.transform);
                    foreach (var renderer in new[] { face, body })
                    {
                        renderer.GetPropertyBlock(block, 0);
                        if (block.GetFloat("_EndfieldSkinBasisEnabled") != 1) throw new Exception("Basis not enabled");
                        var source = (renderer == face ? head : spine).localToWorldMatrix;
                        for (int row = 0; row < 3; row++)
                        {
                            Vector4 expected = renderer == face
                                ? new Vector4(-source[row, 2], -source[row, 0], source[row, 1], source[row, 3])
                                : source.GetRow(row);
                            if ((block.GetVector("_EndfieldSkinBasisRow" + row) - expected).sqrMagnitude > 1e-10f)
                                throw new Exception("Dynamic basis row mismatch");
                        }
                    }
                    face.GetPropertyBlock(block, 0);
                    if (block.GetFloat("_BasisValidationPreserved") != 7) throw new Exception("Existing MPB was discarded");
                }
                UnityEngine.Object.DestroyImmediate(spine.gameObject);
                bool rejected = false;
                try { Endfield.EndfieldSkinBasisDriver.ApplyForTyphoeus(root.transform); }
                catch (InvalidOperationException) { rejected = true; }
                if (!rejected) throw new Exception("Missing source bone was accepted");
                Debug.Log("[SkinBasisValidation] PASS: three dynamic poses, head axis permutation, spine basis, translation, MPB preservation, missing-bone rejection");
            }
            finally
            {
                UnityEngine.Object.DestroyImmediate(root);
                UnityEngine.Object.DestroyImmediate(material);
            }
        }
    }
}
