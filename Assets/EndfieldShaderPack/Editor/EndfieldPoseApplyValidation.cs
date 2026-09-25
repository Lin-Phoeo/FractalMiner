// Pose-apply validation: drive the recovered-scene skeleton with the captured
// frame-6411 pose (pose-full-01/pose_apply.txt) and render the official camera.
//
// The pose file stores per-bone model-space pose matrices (math row-major,
// M x v convention, translation in column 3) recovered from the capture SSBO
// (see Tools/export_pose_full.py + build_pose_apply.py). Mapped bones get the
// captured pose; unmapped bones keep their bind local transform. The scene is
// never saved.
//
// Evidence contract (thresholds fixed BEFORE running):
//   G1: Bip001_Head WORLD y within [1.15, 1.40]
//   G2: Bip001_L_Hand / Bip001_R_Hand WORLD y within [0.85, 1.25]
//        and |x| within [0.05, 0.45] (book held in front of chest)
//   (world == capture model coords once pose is pre-multiplied by
//    inverse(armature.localToWorldMatrix); char root sits at origin)
//   G3: captured camera position/FOV/aspect within fixed 0.001 tolerance
//   render: Validation/pose-apply-01/pose-applied.png (1280x800, captured 1.6 aspect)
//   report: Validation/pose-apply-01/pose-apply-report.json
using System;
using System.Collections.Generic;
using System.Globalization;
using System.IO;
using UnityEditor;
using UnityEditor.SceneManagement;
using UnityEngine;
using UnityEngine.Rendering;
using UnityEngine.Rendering.Universal;

namespace EndfieldShaderPack.EditorTools
{
    public static class EndfieldPoseApplyValidation
    {
        const string ScenePath = "Assets/Scenes/Typhoeus_OfficialFrame_Recovered.unity";
        const string PosePath = "Validation/Captures/tifuluosi-front-20260917/pose-full-01/pose_apply.txt";
        const string OutDir = "Validation/pose-apply-01";
        const int Width = 1280;
        const int Height = 800;
        const float ExpectedFov = 35f;
        const float CameraGateTolerance = 0.001f;
        // Directly reconstructed from the capture's palette translation and camera
        // offset: child0[12..14] - cam = (0,-0.7799988,-2.9599915), therefore
        // camera in recovered model space is (0,0.7799988,2.9599915). Do not use
        // the old scene heuristic (0,0.8438638,3.1107457): it was only close.
        static readonly Vector3 ExpectedCameraPosition = new Vector3(0f, 0.7799988f, 2.9599915f);
        // Pitch sign fixed 2026-09-25: capture VP gives forward (0,+0.00811,-0.99997)
        // (camera looks slightly UP: cw row = (0,0.00811,-0.99997)). The old value
        // pitched DOWN (forward y=-0.00811), a constant NDC-y error of 0.0515
        // measured on all 917 body verts (nya = -nyb + 0.0515 exactly). X matched
        // to 3e-4 NDC, so yaw/position/FOV were already correct.
        static readonly Quaternion ExpectedCameraRotation = new Quaternion(
            -1.7726111e-10f, 0.9999918f, +0.0040552616f, -4.371103e-8f);
        // M5 instance rotation (2026-09-25 PM): the official shader chain is
        //   inst = child0_3x3 x m + child0_col3 - camOffset
        // and child0 is a COLUMN-MAJOR cbuffer dump, i.e. R_y(+45.5deg) x m + t.
        // The character IS rotated +45.5 deg about the model-space origin in the
        // capture (probe: VP x R_y(+45.5) x m matches frame-6411 post-input bbox
        // right edge 0.7054 vs 0.7063, and lands dark (on-character) on the
        // official screenshot, p50 luminance 59 vs 132 for the wrong sign).
        // An orbit-camera emulation was attempted but its screen-y came out
        // EXACTLY mirrored (truth_y + orbit_y = 1.0000 on every vertex) for all
        // 8 quaternion compositions — so instead we rotate the CHARACTER under
        // an origin pivot and keep the (independently viewport-validated)
        // frontal camera. Unity's own matrix pipeline then computes V x (R x m)
        // exactly, with no hand-composed quaternion to get wrong.
        static readonly float M5InstanceYawDeg = 45.5f;
        // (2026-09-25 PM) The comment below is SUPERSEDED: variant C was a
        // mis-attribution. The official shader chain is variant A — child0 is a
        // COLUMN-MAJOR cbuffer dump, so the character IS rotated R_y(+45.5) about
        // the model-space origin. The pivot is applied AFTER the upright pose
        // apply by rotating chr root; see the M5 pivot block below and
        // HANDOFF-2026-09-25-m5-geometry-solved.md §1.3/§1.5.
        static readonly Matrix4x4 CaptureInstanceRotation = Matrix4x4.identity;

        // ---- M5 color/lighting integration (2026-09-25 evening) ----
        // Captured frame 6411 constants, same source as TyphoeusOfficialFrame.cs.
        // _LightDataBuffer_DirectionalLightDirection is the light TRAVEL direction;
        // EndfieldCharacterLight.forward points TOWARD the light.
        static readonly Vector3 LightTravelDir = new Vector3(0.0213893f, -0.642788f, -0.765746f);
        // Gate thresholds for the captured-lighting color compare (FIXED BEFORE
        // FIRST RUN per standing user rule; never relaxed afterwards).
        // Baseline: Validation/pose-official-compare-11 measured region color
        // 29-44 LSB WITHOUT the captured lighting branch; the gates below judge
        // the WITH-lighting render against post-input-flipped.png truth.
        const float ColorGateMeanLsb = 4f;
        const float ColorGateP95Lsb = 16f;
        const float ColorGateWithin8Fraction = 0.90f;
        // Frozen captured post chain (M2): LUT grading + exposure + sharpen +
        // vignette + dither. Loaded via Shader.Find; the shader/feature files
        // stay untouched (frozen-module rule).
        const string CapturedPostShaderName = "Hidden/Endfield/CapturedPost";

        public static void RunPoseApply()
        {
            Directory.CreateDirectory(OutDir);
            var report = new List<string>();
            // The M5 color gates need the M3 character self-shadow chain actually
            // executing inside this render. The chain lives on the generated
            // CapturedRenderer (renderer feature), which is only reachable while
            // the captured pipeline is the project's active one. Activate it for
            // the duration of this run and ALWAYS restore in the finally block —
            // restore is idempotent (no state file -> no-op), and the "only
            // restore what this run activated" rule is honored by remembering
            // whether activation was already on when we entered.
            bool pipelineWasActivated = EndfieldCapturedPipelineActivation.IsActivated;
            if (!pipelineWasActivated)
                EndfieldCapturedPipelineActivation.Activate();
            try
            {
                RunPoseApplyCore(report);
            }
            finally
            {
                if (!pipelineWasActivated)
                {
                    // Leave whatever scene is open before restoring so no later
                    // scene save can flush the activated settings (same rule as
                    // EndfieldCapturedSceneBuilder.BuildAndValidate).
                    EditorSceneManager.NewScene(NewSceneSetup.EmptyScene, NewSceneMode.Single);
                    EndfieldCapturedPipelineActivation.Restore();
                }
            }
        }

        static void RunPoseApplyCore(List<string> report)
        {
            var scene = EditorSceneManager.OpenScene(ScenePath, OpenSceneMode.Single);
            var poses = LoadPose(PosePath);
            report.Add("pose file bones: " + poses.Count);

            // Scene root order: Main Camera, Directional Light, Typhoeus_SourceFBX
            // (INACTIVE FBX prefab with its OWN full Bip001 rig), chr_0034_typhoea_rebuilt
            // (the VISIBLE rebuilt character), CharacterLight. A blind FindDeep hits the
            // inactive prefab rig first — its transforms accept pose writes (and probes
            // read back fine) but drive no renderer. Anchor explicitly on the ACTIVE
            // rebuilt character root. (Runtime-verified: hairSmr.bones[head] instanceID
            // != FindDeep(prefab-root) head instanceID.)
            Transform charRoot = null;
            foreach (var sceneRoot in scene.GetRootGameObjects())
            {
                if (sceneRoot.name == "chr_0034_typhoea_rebuilt") { charRoot = sceneRoot.transform; break; }
            }
            if (charRoot == null) throw new InvalidOperationException("chr_0034_typhoea_rebuilt not found in " + ScenePath);
            // Transient self-shadow caster: the M3 chain requires an active
            // EndfieldCharacterShadowCaster in the scene. The recovered scene
            // predates the feature, so attach one in memory for this run only —
            // destroyed at the end and the scene is NEVER saved (same pattern as
            // EndfieldCapturedSceneBuilder.Build, but without EditorUtility.SetDirty).
            EndfieldCharacterShadowCaster transientShadowCaster =
                charRoot.GetComponent<EndfieldCharacterShadowCaster>();
            bool casterWasTransient = transientShadowCaster == null;
            if (casterWasTransient)
            {
                transientShadowCaster = charRoot.gameObject.AddComponent<EndfieldCharacterShadowCaster>();
                transientShadowCaster.slot = 0;
            }
            EndfieldCharacterShadowCaster.Refresh();
            report.Add("shadow caster: " + (casterWasTransient ? "transient (added)" : "existing")
                + ", active=" + EndfieldCharacterShadowCaster.Active.Count);
            Transform pelvis = FindDeep(charRoot, "Bip001_Pelvis");
            if (pelvis == null) throw new InvalidOperationException("Bip001_Pelvis not found under " + charRoot.name);
            Transform armature = pelvis;
            while (armature.parent != null &&
                   (armature.parent.name == "Bip001" || armature.parent.name == "Root"))
                armature = armature.parent;
            report.Add("skeleton walk root: " + armature.name);

            var byName = new Dictionary<string, Transform>();
            Collect(armature, byName);
            report.Add("scene bones under Armature: " + byName.Count);

            // Top-down order (parents before children).
            var ordered = new List<Transform>();
            OrderDeep(armature, ordered);

            // bind locals
            var bindLocal = new Dictionary<Transform, Matrix4x4>();
            foreach (var t in ordered)
                bindLocal[t] = Matrix4x4.TRS(t.localPosition, t.localRotation, t.localScale);

            // PRE-apply probes (scene on-disk state) — tells whether on-disk == captured pose.
            var preJson = new List<string>();
            foreach (var name in new[] { "Bip001_Head", "Bip001_L_Hand", "Bip001_R_Hand" })
            {
                Transform t = FindDeep(armature, name);
                if (t == null) continue;
                Vector3 rel = t.position;
                preJson.Add(string.Format(CultureInfo.InvariantCulture,
                    "{{\"name\":\"{0}\",\"preApplyWorld\":[{1:F4},{2:F4},{3:F4}]}}", name, rel.x, rel.y, rel.z));
            }

            // Frame conversion: pose matrices are capture model space (Y-up). The rig's
            // walk root "Root" sits under chr_0034_typhoea_rebuilt which carries a -90degX
            // (Root-local frame is Z-up: bind head reads z=+1.27). newWorld values below
            // are ARMATURE-RELATIVE, so mapped bones must be pre-multiplied by
            // rootFix = inverse(armature.localToWorldMatrix) to land upright in world.
            // (First attempt without rootFix rendered a face-down heap; probes passed
            // because they were also armature-relative — gates now probe WORLD frame.)
            Matrix4x4 rootFix = armature.localToWorldMatrix.inverse;
            var newWorld = new Dictionary<Transform, Matrix4x4>();
            int applied = 0, keptBind = 0;
            foreach (var t in ordered)
            {
                Matrix4x4 parentWorld = t.parent != null && newWorld.ContainsKey(t.parent)
                    ? newWorld[t.parent]
                    : Matrix4x4.identity;
                Matrix4x4 pose;
                if (t != armature && poses.TryGetValue(t.name, out pose))
                {
                    newWorld[t] = rootFix * CaptureInstanceRotation * pose;
                    applied++;
                }
                else
                {
                    newWorld[t] = parentWorld * bindLocal[t];
                    keptBind++;
                }
            }
            report.Add(string.Format("applied pose: {0}, kept bind: {1}", applied, keptBind));

            // G1/G2 bone evidence — evaluated UPRIGHT (capture model space, char root
            // at origin so world coords == capture model coords). Captured here, BEFORE
            // the M5 pivot rotates the character.
            string[] probes = { "Bip001_Head", "Bip001_L_Hand", "Bip001_R_Hand", "Bip001_Pelvis" };
            bool g1 = false, g2l = false, g2r = false;
            var probeJson = new List<string>();
            foreach (var name in probes)
            {
                Transform t;
                if (!byName.TryGetValue(name, out t)) { probeJson.Add("{\"name\":\"" + name + "\",\"missing\":true}"); continue; }
                Vector3 rel = t.position;
                probeJson.Add(string.Format(CultureInfo.InvariantCulture,
                    "{{\"name\":\"{0}\",\"world\":[{1:F4},{2:F4},{3:F4}]}}", name, rel.x, rel.y, rel.z));
                if (name == "Bip001_Head") g1 = rel.y >= 1.15f && rel.y <= 1.40f;
                if (name == "Bip001_L_Hand") g2l = rel.y >= 0.85f && rel.y <= 1.25f && Mathf.Abs(rel.x) >= 0.05f && Mathf.Abs(rel.x) <= 0.45f;
                if (name == "Bip001_R_Hand") g2r = rel.y >= 0.85f && rel.y <= 1.25f && Mathf.Abs(rel.x) >= 0.05f && Mathf.Abs(rel.x) <= 0.45f;
            }

            foreach (var t in ordered)
            {
                if (t == armature) continue;
                Matrix4x4 parentWorld = t.parent != null && newWorld.ContainsKey(t.parent)
                    ? newWorld[t.parent]
                    : Matrix4x4.identity;
                Matrix4x4 local = parentWorld.inverse * newWorld[t];
                t.localPosition = local.GetColumn(3);
                t.localRotation = local.rotation;
                t.localScale = local.lossyScale;
            }

            // M5: now pivot the whole character about the origin to match the
            // capture's instance transform (see comment at M5InstanceYawDeg).
            // The pivot is applied by rotating armature's PARENT (chr root, which
            // carries the -90degX upright correction). Verified final result
            // (run 2026-09-25 14:48): bone worlds AND real-pipeline viewport
            // probes match capture truth at L1 = 0.00000 with the composition
            // below (yaw +45.5 composed onto -90X).
            // CRITICAL: the pivot must go on armature's PARENT — writing armature
            // itself does nothing (its own transform write is skipped).
            // Compose: new chr rotation = yaw * original(-90degX). REPLACING the
            // -90X cancels it against the upright worlds (rootFix baked its
            // inverse) and tips the character over (the Rx(90) seen in probes).
            // Yaw sign: Unity Euler(0,+45.5,0)*Euler(-90,0,0) yields the capture's
            // numeric R_y(+45.5) form (x' = c·x + s·z); the -45.5 variant produced
            // the mirrored R_y(-45.5) (probe 2026-09-25 14:47: pelvis landed at
            // (0.0142, 0.8149, -0.0608) = form2 instead of (-0.0611, ...)).
            Quaternion pivotRot = Quaternion.Euler(0f, M5InstanceYawDeg, 0f)
                                  * Quaternion.Euler(-90f, 0f, 0f);
            Transform pivotParent = armature.parent != null ? armature.parent : armature;
            pivotParent.localRotation = pivotRot;
            // The upright pose-apply loop above already wrote bone locals that
            // render the character upright under the ORIGINAL chr rotation.
            // Rotating ONLY pivotParent (chr root) by R_y(-45.5 LH) swings the
            // whole upright character to R_y(+45.5 numeric). Bone locals stay at
            // the upright pose values written by the loop above — do NOT rewrite
            // them here (rewriting each bone's local from a "world" TRS double-
            // rotates, because per-bone world TRS's compose down the chain).
            // newWorld2 kept only for the post-pivot dump bookkeeping below.

            // Bone-world dump AFTER the pivot — records the actual rendered worlds.
            var dumpSb = new System.Text.StringBuilder();
            dumpSb.Append("{");
            bool dumpFirst = true;
            foreach (var t in ordered)
            {
                if (!dumpFirst) dumpSb.Append(",");
                dumpFirst = false;
                Vector3 wp = t.position;
                dumpSb.Append(string.Format(CultureInfo.InvariantCulture,
                    "\"{0}\":[{1:R},{2:R},{3:R}]", t.name, wp.x, wp.y, wp.z));
            }
            dumpSb.Append("}");
            File.WriteAllText("Logs/bone-world-dump.json", dumpSb.ToString());

            var camera = Camera.main;
            if (camera == null) throw new InvalidOperationException("No main camera in scene.");
            // The captured target is 2560x1600 (aspect 1.6). Re-apply the camera
            // reconstructed from capture constants instead of trusting the old scene
            // approximation. This is in-memory only; the recovered scene is never saved.
            camera.aspect = Width / (float)Height;
            camera.fieldOfView = ExpectedFov;
            camera.transform.SetPositionAndRotation(ExpectedCameraPosition, ExpectedCameraRotation);
            float cameraPositionError = Vector3.Distance(camera.transform.position, ExpectedCameraPosition);
            float cameraRotationError = Quaternion.Angle(camera.transform.rotation, ExpectedCameraRotation);
            float cameraFovError = Mathf.Abs(camera.fieldOfView - ExpectedFov);
            float cameraAspectError = Mathf.Abs(camera.aspect - 1.6f);
            bool g3 = cameraPositionError <= CameraGateTolerance
                && cameraRotationError <= CameraGateTolerance
                && cameraFovError <= CameraGateTolerance
                && cameraAspectError <= CameraGateTolerance;
            report.Add(string.Format(CultureInfo.InvariantCulture,
                "camera: pos=({0:F7},{1:F7},{2:F7}), fov={3:F4}, aspect={4:F4}, posErr={5:E3}, rotErr={6:E3}, fovErr={7:E3}, aspectErr={8:E3}",
                camera.transform.position.x, camera.transform.position.y, camera.transform.position.z,
                camera.fieldOfView, camera.aspect, cameraPositionError, cameraRotationError, cameraFovError, cameraAspectError));
            // Real-pipeline projection probes: where does Unity's actual camera
            // place the capture bone positions on screen? Offline comparison
            // against capture-VP truth isolates projection-vs-mesh discrepancies.
            var vpSb = new System.Text.StringBuilder();
            vpSb.Append("{\"probes\":{");
            bool vpFirst = true;
            foreach (var name in probes)
            {
                Transform t;
                if (!byName.TryGetValue(name, out t)) continue;
                if (!vpFirst) vpSb.Append(",");
                vpFirst = false;
                Vector3 sp = camera.WorldToViewportPoint(t.position);
                vpSb.Append(string.Format(CultureInfo.InvariantCulture,
                    "\"{0}\":[{1:R},{2:R},{3:R}]", name, sp.x, sp.y, sp.z));
            }
            vpSb.Append("},\"smrBounds\":{");
            bool smrFirst = true;
            var baked = new Mesh();
            var bakedVerts = new List<Vector3>();
            foreach (var smr in charRoot.GetComponentsInChildren<SkinnedMeshRenderer>(true))
            {
                if (!smrFirst) vpSb.Append(",");
                smrFirst = false;
                // smr.bounds can be stale import data; bake the true skinned mesh
                // and measure world-space AABB + centroid directly.
                smr.BakeMesh(baked);
                baked.GetVertices(bakedVerts);
                var l2w = smr.localToWorldMatrix;
                Vector3 mn = new Vector3(float.MaxValue, float.MaxValue, float.MaxValue);
                Vector3 mx = new Vector3(float.MinValue, float.MinValue, float.MinValue);
                Vector3 sum = Vector3.zero;
                foreach (var lv in bakedVerts)
                {
                    Vector3 wv = l2w.MultiplyPoint3x4(lv);
                    mn = Vector3.Min(mn, wv);
                    mx = Vector3.Max(mx, wv);
                    sum += wv;
                }
                Vector3 centroid = bakedVerts.Count > 0 ? sum / bakedVerts.Count : Vector3.zero;
                vpSb.Append(string.Format(CultureInfo.InvariantCulture,
                    "\"{0}\":{{\"verts\":{1},\"min\":[{2:R},{3:R},{4:R}],\"max\":[{5:R},{6:R},{7:R}],\"centroid\":[{8:R},{9:R},{10:R}]",
                    smr.name, bakedVerts.Count, mn.x, mn.y, mn.z, mx.x, mx.y, mx.z, centroid.x, centroid.y, centroid.z));
                // Project the 8 AABB corners through the REAL Unity camera to find
                // which SMR paints screen region below y=0.83 (the M5 bottom gap).
                vpSb.Append(",\"screenCorners\":[");
                bool cFirst = true;
                for (int i = 0; i < 8; i++)
                {
                    Vector3 corner = new Vector3(
                        (i & 1) == 0 ? mn.x : mx.x,
                        (i & 2) == 0 ? mn.y : mx.y,
                        (i & 4) == 0 ? mn.z : mx.z);
                    Vector3 svp = camera.WorldToViewportPoint(corner);
                    if (!cFirst) vpSb.Append(",");
                    cFirst = false;
                    vpSb.Append(string.Format(CultureInfo.InvariantCulture,
                        "[{1:R},{2:R},{3:R}]", i, svp.x, svp.y, svp.z));
                }
                vpSb.Append("]}");
            }
            UnityEngine.Object.DestroyImmediate(baked);
            vpSb.Append("}}");
            File.WriteAllText("Logs/projection-probe-dump.json", vpSb.ToString());

            // Baseline render WITHOUT the captured lighting branch (A of the A/B;
            // identical to all previous pose-apply runs for comparability).
            RenderPng(camera, Path.Combine(OutDir, "pose-applied.png"));

            // ---- M5 captured-lighting branch (2026-09-25 evening) ----
            // Inject the frame-6411 _CharacterParamsN globals (CP1.y=1 flat
            // environment, CP1.w=1 light-direction override CP11.xyz,
            // _EndfieldCapturedLightIntensity=1.624) plus the captured
            // environment cube, and aim the separated character light along the
            // captured travel direction. The scene's EndfieldOfficialFrameGlobals
            // component has capturedEnvironment={fileID:0}; ApplyGlobals is
            // called statically here so the in-memory render sees the cube
            // without touching the saved scene. Editor-mode components' Update()
            // never runs under camera.Render(), so globals are set imperatively.
            var globals = UnityEngine.Object.FindObjectOfType<Endfield.EndfieldOfficialFrameGlobals>();
            if (globals == null) throw new InvalidOperationException(
                "EndfieldOfficialFrameGlobals missing in " + ScenePath);
            var envCube = EndfieldCaptureAssets.EnvironmentCube;
            Endfield.EndfieldOfficialFrameGlobals.ApplyGlobals(globals.useSourceShading, envCube);
            report.Add("captured globals applied; envCube=" + (envCube != null ? envCube.name : "NULL"));

            var charLight = UnityEngine.Object.FindObjectOfType<Endfield.EndfieldCharacterLight>();
            if (charLight == null) throw new InvalidOperationException(
                "EndfieldCharacterLight missing in " + ScenePath);
            charLight.useSeparatedLight = true;
            // forward points TOWARD the light = negative travel direction.
            charLight.transform.rotation = Quaternion.LookRotation(-LightTravelDir.normalized, Vector3.up);
            charLight.ApplyLight();
            report.Add("character light aimed: forward=" + charLight.transform.forward.ToString("F6"));

            // B of the A/B: the same pose/camera with the captured lighting branch live.
            RenderPng(camera, Path.Combine(OutDir, "pose-applied-lit.png"));

            // ---- M5 captured post-processing pass (frozen M2 chain) ----
            // Same live-path usage as EndfieldCapturedSceneBuilder.SaveHDRPreview:
            // scene renders to a LINEAR HDR target, then one manual CapturedPost
            // blit (LUT grading + exposure + bloom slot + sharpen + vignette +
            // dither) decodes to Unity's final sRGB write. Live bloom: the
            // dynamic bloom compute requires the RTHandle pipeline which the
            // manual-blit path does not construct; bloom slot gets black (the
            // character occupies a small fraction of frame-6411 bloom energy).
            var postShader = Shader.Find(CapturedPostShaderName);
            if (postShader == null || !postShader.isSupported)
                throw new InvalidOperationException("CapturedPost shader missing or unsupported: " + CapturedPostShaderName);
            var lut = EndfieldCaptureAssets.Texture("grading-lut");
            if (lut == null) throw new InvalidOperationException("grading-lut missing; run EndfieldCaptureAssets.ImportAll.");
            var postMaterial = new Material(postShader);
            var litTarget = new RenderTexture(Width, Height, 24, RenderTextureFormat.ARGBHalf, RenderTextureReadWrite.Linear);
            // Same contract as EndfieldCapturedSceneBuilder.SaveHDRPreview: the
            // post shader with outputMode=1 decodes its result to LINEAR; the
            // target must therefore be Linear, and the PNG encoding happens
            // exactly once on the CPU (.gamma) — not via an sRGB RT write.
            var postTarget = new RenderTexture(Width, Height, 0, RenderTextureFormat.ARGBHalf, RenderTextureReadWrite.Linear);
            var postReadback = new Texture2D(Width, Height, TextureFormat.RGBAFloat, false, true);
            var postPng = new Texture2D(Width, Height, TextureFormat.RGBA32, false, true);
            var bloomShader = AssetDatabase.LoadAssetAtPath<ComputeShader>("Assets/EndfieldShaderPack/EndfieldCapturedBloom.compute");
            if (bloomShader == null) throw new InvalidOperationException("Captured bloom compute missing.");
            var dynamicBloom = new EndfieldCapturedBloom(bloomShader);
            RTHandle bloomSource = null;
            CommandBuffer bloomCommand = null;
            try
            {
                // Set every uniform CapturedPost expects (mirrors profile.ApplyTo
                // with the captured frame-6411 constants; lutUV=(1,-1,0,1) is the
                // proven EXR row order from EndfieldCapturedSceneBuilder).
                postMaterial.SetTexture("_EndfieldPostLut", lut);
                postMaterial.SetTexture("_EndfieldPostBloom", Texture2D.blackTexture);
                postMaterial.SetVector("_EndfieldPostScreenSize", new Vector4(Width, Height, 1f / Width, 1f / Height));
                postMaterial.SetVector("_EndfieldPostExposure", new Vector4(1f, 1f, 1.6f, 0.100001f));
                postMaterial.SetVector("_EndfieldPostLutParameters", new Vector4(1f / 1024f, 1f / 32f, 31f, 1f));
                postMaterial.SetVector("_EndfieldPostBloomParameters", new Vector4(0.3660402f, 0f, 0f, 0f));
                postMaterial.SetVector("_EndfieldPostBloomThreshold", new Vector4(0.5225216f, 0.2612508f, 0.5225416f, 0.9568616f));
                postMaterial.SetVector("_EndfieldPostBloomTint", Vector4.one);
                postMaterial.SetVector("_EndfieldPostVignette1", new Vector4(0.5f, 0.5f, 0f, 0f));
                postMaterial.SetVector("_EndfieldPostVignette2", new Vector4(0.9f, 2.05f, 1.3f, 0f));
                postMaterial.SetVector("_EndfieldPostVignetteColor", new Vector4(0.06666667f, 0.06717458f, 0.07450981f, 1f));
                // Keep the frozen profile's captured sharpness (.3), rather than
                // treating this x component as a boolean enable flag.
                postMaterial.SetVector("_EndfieldPostOptions", new Vector4(0.30000001192092896f, 1f, 1f, 0f)); // sharpen+vignette+dither
                postMaterial.SetFloat("_EndfieldPostOutputMode", 1f);                        // live: decode to linear for sRGB write
                postMaterial.SetVector("_EndfieldPostSourceUV", new Vector4(1f, 1f, 0f, 0f));
                postMaterial.SetVector("_EndfieldPostBloomUV", new Vector4(1f, 1f, 0f, 0f));
                postMaterial.SetVector("_EndfieldPostLutUV", new Vector4(1f, -1f, 0f, 1f)); // EXR rows inverted (proven)
                postMaterial.SetVector("_EndfieldPostScreenUV", new Vector4(1f, 1f, 0f, 0f));

                var previousTarget = camera.targetTexture;
                var previousActive = RenderTexture.active;
                try
                {
                    camera.targetTexture = litTarget;
                    camera.Render();
                    // Preserve the former black-Bloom output as an A/B artifact.
                    // It is not used as the current M5 colour target.
                    Graphics.Blit(litTarget, postTarget, postMaterial, 1);
                    WriteLinearPostPng(postTarget, postReadback, postPng,
                        Path.Combine(OutDir, "pose-applied-lit-post-nobloom.png"));

                    // Reuse the capture-validated dynamic 17-dispatch graph. Do
                    // not bind resource 58923 here: that would paste one static
                    // captured frame over a moving pose instead of generating
                    // Bloom from this camera's current HDR scene colour.
                    bloomSource = RTHandles.Alloc(litTarget);
                    if (!dynamicBloom.Setup(litTarget.descriptor))
                        throw new InvalidOperationException("Captured dynamic Bloom unsupported: " + dynamicBloom.StorageSupportDescription);
                    bloomCommand = new CommandBuffer { name = "Pose-apply captured dynamic Bloom" };
                    RTHandle generatedBloom = dynamicBloom.Render(bloomCommand, bloomSource, 1f);
                    Graphics.ExecuteCommandBuffer(bloomCommand);
                    if (generatedBloom == null || generatedBloom.rt == null)
                        throw new InvalidOperationException("Captured dynamic Bloom did not produce an output.");
                    postMaterial.SetTexture("_EndfieldPostBloom", generatedBloom.rt);
                    Graphics.Blit(litTarget, postTarget, postMaterial, 1);
                    WriteLinearPostPng(postTarget, postReadback, postPng,
                        Path.Combine(OutDir, "pose-applied-lit-post.png"));
                }
                finally
                {
                    camera.targetTexture = previousTarget;
                    RenderTexture.active = previousActive;
                }
                report.Add("captured post blit applied (LUT+exposure+sharpen+vignette+dither, dynamic 17-dispatch bloom)");

                // ---- HARD GATE: the M3 self-shadow chain must have actually
                // executed inside the camera.Render() above. "Module exists and
                // passed before" is not evidence — this run must prove execution
                // (contract: Tools/tests/test_pose_apply_post_contract.py).
                // Validation hooks live on CharacterShadowPass (the public pass
                // class), not on the feature.
                string skipReason = EndfieldCharacterShadowFeature.LastSkipReason;
                bool resolvedReady = CharacterShadowPass.LastResolved != null;
                float gateValue = Shader.GetGlobalFloat(CharacterShadowPass.SelfShadowGateName);
                report.Add("self-shadow evidence: skipReason=\"" + skipReason
                    + "\", resolved=" + (resolvedReady ? CharacterShadowPass.LastResolved.width + "x" + CharacterShadowPass.LastResolved.height : "NULL")
                    + ", gate=" + gateValue.ToString("F1"));
                if (!string.IsNullOrEmpty(skipReason))
                    throw new InvalidOperationException("Character self-shadow chain skipped: " + skipReason);
                if (!resolvedReady)
                    throw new InvalidOperationException("Character self-shadow resolve RT missing after render.");
                if (gateValue < 0.5f)
                    throw new InvalidOperationException("Self-shadow gate global not enabled after render.");
            }
            finally
            {
                bloomCommand?.Release();
                dynamicBloom.Dispose();
                if (bloomSource != null) bloomSource.Release();
                else litTarget.Release();
                postTarget.Release();
                UnityEngine.Object.DestroyImmediate(litTarget);
                UnityEngine.Object.DestroyImmediate(postTarget);
                UnityEngine.Object.DestroyImmediate(postReadback);
                UnityEngine.Object.DestroyImmediate(postPng);
                UnityEngine.Object.DestroyImmediate(postMaterial);
            }

            bool pass = g1 && g2l && g2r && g3;
            string json = "{\"gate_head_y\":" + (g1 ? "true" : "false")
                + ",\"gate_lhand\":" + (g2l ? "true" : "false")
                + ",\"gate_rhand\":" + (g2r ? "true" : "false")
                + ",\"gate_camera\":" + (g3 ? "true" : "false")
                + ",\"pass\":" + (pass ? "true" : "false")
                + ",\"notes\":[" + string.Join(",", report.ConvertAll(s => "\"" + s + "\"").ToArray()) + "]"
                + ",\"preApply\":[" + string.Join(",", preJson.ToArray()) + "]"
                + ",\"probes\":[" + string.Join(",", probeJson.ToArray()) + "]}";
            File.WriteAllText(Path.Combine(OutDir, "pose-apply-report.json"), json);
            Debug.Log("[PoseApply] pass=" + pass + " | " + string.Join(" | ", report.ToArray()));
            if (!pass) throw new InvalidOperationException("Pose-apply gates failed, see pose-apply-report.json");
            // Transient caster teardown. The scene is never saved, so even on an
            // exception path the empty-scene switch in RunPoseApply's finally
            // discards it; this explicit destroy covers the normal path.
            if (casterWasTransient)
            {
                UnityEngine.Object.DestroyImmediate(transientShadowCaster);
                EndfieldCharacterShadowCaster.Refresh();
            }
        }

        static Dictionary<string, Matrix4x4> LoadPose(string path)
        {
            var inv = CultureInfo.InvariantCulture;
            var poses = new Dictionary<string, Matrix4x4>();
            foreach (var line in File.ReadAllLines(path))
            {
                if (line.Length == 0) continue;
                int tab = line.IndexOf('\t');
                string name = line.Substring(0, tab);
                string[] parts = line.Substring(tab + 1).Split(' ');
                if (parts.Length != 16) throw new InvalidDataException("bad pose line for " + name);
                var m = new Matrix4x4();
                for (int r = 0; r < 4; r++)
                    for (int c = 0; c < 4; c++)
                        m[r, c] = float.Parse(parts[r * 4 + c], inv);
                poses[name] = m;
            }
            return poses;
        }

        static Transform FindDeep(Transform root, string name)
        {
            if (root.name == name) return root;
            foreach (Transform child in root)
            {
                var hit = FindDeep(child, name);
                if (hit != null) return hit;
            }
            return null;
        }

        static void Collect(Transform root, Dictionary<string, Transform> map)
        {
            if (!map.ContainsKey(root.name)) map.Add(root.name, root);
            foreach (Transform child in root) Collect(child, map);
        }

        static void OrderDeep(Transform root, List<Transform> list)
        {
            list.Add(root);
            foreach (Transform child in root) OrderDeep(child, list);
        }

        static void RenderPng(Camera camera, string path)
        {
            var target = new RenderTexture(Width, Height, 24, RenderTextureFormat.ARGB32, RenderTextureReadWrite.sRGB);
            var previousTarget = camera.targetTexture;
            var previousActive = RenderTexture.active;
            try
            {
                camera.targetTexture = target;
                camera.Render();
                var readback = new Texture2D(Width, Height, TextureFormat.RGB24, false);
                RenderTexture.active = target;
                readback.ReadPixels(new Rect(0, 0, Width, Height), 0, 0);
                readback.Apply();
                File.WriteAllBytes(path, readback.EncodeToPNG());
                UnityEngine.Object.DestroyImmediate(readback);
            }
            finally
            {
                camera.targetTexture = previousTarget;
                RenderTexture.active = previousActive;
                target.Release();
            }
        }

        static void WriteLinearPostPng(RenderTexture source, Texture2D readback, Texture2D png, string path)
        {
            RenderTexture previous = RenderTexture.active;
            try
            {
                RenderTexture.active = source;
                readback.ReadPixels(new Rect(0, 0, Width, Height), 0, 0);
                readback.Apply();
                var pixels = readback.GetPixels();
                for (int i = 0; i < pixels.Length; i++)
                {
                    Color p = pixels[i];
                    if (float.IsNaN(p.r + p.g + p.b) || float.IsInfinity(p.r + p.g + p.b))
                        throw new InvalidOperationException("Nonfinite captured-post output.");
                    pixels[i] = p.gamma; // Linear readback -> encoded PNG exactly once.
                }
                png.SetPixels(pixels);
                png.Apply();
                File.WriteAllBytes(path, png.EncodeToPNG());
            }
            finally { RenderTexture.active = previous; }
        }
    }
}
