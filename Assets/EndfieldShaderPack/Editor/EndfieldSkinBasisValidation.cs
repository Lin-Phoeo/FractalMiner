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
            RunAnimationInputsCore(false);
        }

        // Live pass/input integration, not an image-matching or MMD fidelity gate.
        public static void RunRenderedAnimationInputs()
        {
            if (!Application.isBatchMode) throw new InvalidOperationException("Run rendered input validation in batch mode.");
            RunAnimationInputsCore(true);
        }

        static void RunAnimationInputsCore(bool render)
        {
            string motionPath = Environment.GetEnvironmentVariable("ENDFIELD_BASIS_TEST_VMD");
            string output = Environment.GetEnvironmentVariable("ENDFIELD_BASIS_TEST_REPORT");
            if (!File.Exists(motionPath) || string.IsNullOrEmpty(output) || File.Exists(output))
                throw new InvalidOperationException("Provide an existing VMD and a fresh report path.");
            string renderDirectory = null;
            if (render)
            {
                renderDirectory = Path.Combine(Path.GetDirectoryName(Path.GetFullPath(output)),
                    Path.GetFileNameWithoutExtension(output) + "-frames");
                if (Directory.Exists(renderDirectory)) throw new IOException("Use a fresh frame directory: " + renderDirectory);
                Directory.CreateDirectory(renderDirectory);
            }
            var samples = new List<object>();
            bool pipelineWasActivated = EndfieldCapturedPipelineActivation.IsActivated;
            int renderedFrames = 0;
            try
            {
                if (render && !pipelineWasActivated) EndfieldCapturedPipelineActivation.Activate();
                Transform root = OpenDanceRoot();
                if (render) ConfigureRender(root);
                var clip = AssetDatabase.LoadAssetAtPath<AnimationClip>(
                    "Assets/Typhoeus/AnimationsDecoded/A_actor_typhoea_battle_attack_01.anim");
                if (clip == null || clip.length <= 0 || AnimationUtility.GetCurveBindings(clip).Length == 0)
                    throw new InvalidOperationException("Decoded native animation is missing/empty.");
                foreach (float fraction in new[] { 0f, .25f, .5f })
                {
                    clip.SampleAnimation(root.gameObject, clip.length * fraction);
                    Endfield.EndfieldSkinBasisDriver.ApplyForTyphoeus(root);
                    CheckRealBindings(root);
                    if (render) RenderAndCheck(root, renderDirectory, "native-" + renderedFrames++);
                    samples.Add(new { source = "decoded-native-clip", fraction, basis = "live" });
                }
                root = OpenDanceRoot(); // Calibration must not inherit native animated pose.
                if (render) ConfigureRender(root);
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
                    if (render) RenderAndCheck(root, renderDirectory, "vmd-" + renderedFrames++);
                    samples.Add(new { source = "VMD-MmdPlayer", fraction, basis = "live" });
                }
                File.WriteAllText(output, Newtonsoft.Json.JsonConvert.SerializeObject(new {
                    status = "pass", scope = "loader -> pose -> dynamic skin basis, NOT MMD fidelity/complete video",
                    nativeClip = AssetDatabase.GetAssetPath(clip), nativeCurves = AnimationUtility.GetCurveBindings(clip).Length,
                    motionPath, sourceRig = player.sourceRig.name, renderedFrames, renderDirectory,
                    dynamicBloomAndShadowChecked = render, samples
                }, Newtonsoft.Json.Formatting.Indented));
                Debug.Log("[SkinBasisAnimationInputs] PASS: decoded native clip + VMD, six post-pose shader binding checks; " + output);
            }
            finally
            {
                EditorSceneManager.NewScene(NewSceneSetup.EmptyScene, NewSceneMode.Single);
                EndfieldCharacterShadowCaster.Refresh();
                if (render && !pipelineWasActivated && EndfieldCapturedPipelineActivation.IsActivated)
                    EndfieldCapturedPipelineActivation.Restore();
            }
        }

        static void ConfigureRender(Transform root)
        {
            var caster = root.GetComponent<EndfieldCharacterShadowCaster>();
            if (caster == null) caster = root.gameObject.AddComponent<EndfieldCharacterShadowCaster>();
            caster.slot = 0;
            EndfieldCharacterShadowCaster.Refresh();
            Endfield.EndfieldOfficialFrameGlobals.ApplyGlobals(true, EndfieldCaptureAssets.EnvironmentCube);
            var light = UnityEngine.Object.FindObjectOfType<Endfield.EndfieldCharacterLight>();
            if (light == null) throw new InvalidOperationException("Dance character light missing.");
            light.useSeparatedLight = true;
            light.transform.rotation = Quaternion.LookRotation(
                -new Vector3(.0213893f, -.642788f, -.765746f).normalized, Vector3.up);
            light.ApplyLight();
        }

        static void RenderAndCheck(Transform root, string frameDirectory, string frameName)
        {
            var camera = Camera.main;
            var profile = camera != null ? camera.GetComponent<EndfieldCapturedPostProfile>() : null;
            if (profile == null || !profile.IsConfigured) throw new InvalidOperationException("Dance post profile missing/unconfigured.");
            int previousFrames = profile.executedFrames;
            long previousShadowSequence = CharacterShadowPass.LastRenderSequence;
            string framePath = Path.Combine(frameDirectory, frameName + ".png");
            EndfieldVmdBatchRender.SaveFrame(camera, framePath, 640, 400, false);
            if (profile.executedFrames <= previousFrames || !profile.lastFrameUsedDynamicBloom)
                throw new InvalidOperationException("Captured post/dynamic Bloom did not execute for " + frameName);
            if (!string.IsNullOrEmpty(EndfieldCharacterShadowFeature.LastSkipReason)
                || CharacterShadowPass.LastResolved == null || CharacterShadowPass.LastAtlas == null
                || CharacterShadowPass.LastRenderSequence <= previousShadowSequence || CharacterShadowPass.LastRenderedCamera != camera)
                throw new InvalidOperationException("Live self-shadow did not execute: " + EndfieldCharacterShadowFeature.LastSkipReason);
            if (Shader.GetGlobalFloat(CharacterShadowPass.SelfShadowGateName) != 0f)
                throw new InvalidOperationException("Self-shadow gate leaked past camera cleanup.");
            CheckRealBindings(root); // Rendering must not erase the post-pose root data.
            foreach (var renderer in root.GetComponentsInChildren<SkinnedMeshRenderer>())
            for (int slot = 0; slot < renderer.sharedMaterials.Length; slot++)
            {
                var block = new MaterialPropertyBlock();
                renderer.GetPropertyBlock(block, slot);
                if (block.GetFloat("_EndfieldSkinBasisEnabled") != 1) continue;
                if ((block.GetVector(CharacterShadowPass.IndexEncodeName) - CharacterShadowPass.IndexEncode(0)).sqrMagnitude > 1e-10f
                    || block.GetMatrix(CharacterShadowPass.AtlasClipMatrixName) == Matrix4x4.zero)
                    throw new InvalidOperationException("Root slot masks live shadow data: " + renderer.name);
            }
            Debug.Log("[RenderedAnimationInputs] PASS " + frameName + ": live roots + shadow + dynamic Bloom + captured post");
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
                    && !renderer.name.EndsWith("_typhoea_body_01_lod0", StringComparison.Ordinal)
                    && !renderer.name.EndsWith("_typhoea_iris_01_lod0", StringComparison.Ordinal)
                    && !renderer.name.EndsWith("_typhoea_hair_01_lod0", StringComparison.Ordinal)) continue;
                for (int slot = 0; slot < renderer.sharedMaterials.Length; slot++)
                {
                    var block = new MaterialPropertyBlock();
                    renderer.GetPropertyBlock(block, slot);
                    if (block.GetFloat("_EndfieldSkinBasisEnabled") != 1) throw new Exception("Real shader slot not bound.");
                    checkedSlots++;
                }
            }
            if (checkedSlots != 4) throw new Exception("Expected face/body/iris/hair root slots, got " + checkedSlots);
        }

        public static void Run()
        {
            var root = new GameObject("SkinBasisValidation");
            var material = new Material(Shader.Find("Endfield/CharacterLit"));
            var irisMaterial = new Material(material);
            var hairMaterial = new Material(material);
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
                irisMaterial.SetFloat("_MaterialFamily", 3);
                hairMaterial.SetFloat("_MaterialFamily", 2);
                var iris = new GameObject("S_actor_typhoea_iris_01_lod0").AddComponent<SkinnedMeshRenderer>();
                var hair = new GameObject("S_actor_typhoea_hair_01_lod0").AddComponent<SkinnedMeshRenderer>();
                iris.transform.SetParent(root.transform, false);
                hair.transform.SetParent(root.transform, false);
                iris.sharedMaterial = irisMaterial;
                hair.sharedMaterial = hairMaterial;
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
                    foreach (var renderer in new[] { face, body, iris, hair })
                    {
                        renderer.GetPropertyBlock(block, 0);
                        if (block.GetFloat("_EndfieldSkinBasisEnabled") != 1) throw new Exception("Basis not enabled");
                        var source = (renderer != body ? head : spine).localToWorldMatrix;
                        for (int row = 0; row < 3; row++)
                        {
                            Vector4 expected = renderer != body
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
                Debug.Log("[SkinBasisValidation] PASS: three dynamic poses x four parts, head axis permutation, spine basis, translation, MPB preservation, missing-bone rejection");
            }
            finally
            {
                UnityEngine.Object.DestroyImmediate(root);
                UnityEngine.Object.DestroyImmediate(material);
                UnityEngine.Object.DestroyImmediate(irisMaterial);
                UnityEngine.Object.DestroyImmediate(hairMaterial);
            }
        }
    }
}
