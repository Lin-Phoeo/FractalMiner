import re
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
STUDIO = ROOT / "Assets/EndfieldShaderPack/Editor/EndfieldMmdStudio.cs"
BATCH = ROOT / "Assets/EndfieldShaderPack/Editor/EndfieldVmdBatchRender.cs"
RETARGET = ROOT / "Assets/EndfieldShaderPack/Editor/Mmd/MmdRetarget.cs"
RIG = ROOT / "Assets/EndfieldShaderPack/Editor/Mmd/MmdRig.cs"
PLAYER = ROOT / "Assets/EndfieldShaderPack/Editor/Mmd/MmdPlayer.cs"
ANIM = ROOT / "Assets/EndfieldShaderPack/Editor/EndfieldAnimStudio.cs"


class MmdRuntimeContractTests(unittest.TestCase):
    def test_loading_a_camera_does_not_reopen_and_invalidate_the_loaded_player(self):
        text = STUDIO.read_text("utf-8")
        method = re.search(r"void LoadCamera\(.*?\n        \}", text, re.S)
        self.assertIsNotNone(method)
        self.assertNotIn("EnsureScene(true)", method.group(0))
        self.assertIn("EnsureScene()", method.group(0))

    def test_amplitude_uses_consistent_world_space_and_supports_values_above_one(self):
        text = RETARGET.read_text("utf-8")
        self.assertIn("Quaternion.SlerpUnclamped(neutralWorld, desired", text)
        self.assertNotIn("Quaternion.Slerp(b.localRot, desired", text)
        self.assertNotIn("Mathf.Clamp01(amp)", text)

    def test_overall_amplitude_is_not_squared_for_torso_roles(self):
        text = RETARGET.read_text("utf-8")
        amp_for = re.search(r"float AmpFor\(int role\).*?;", text, re.S)
        self.assertIsNotNone(amp_for)
        self.assertRegex(amp_for.group(0), r":\s*1f\s*;")

    def test_studio_output_rate_controls_sampling_density_without_changing_speed(self):
        text = STUDIO.read_text("utf-8")
        self.assertIn("k / (float)outFps", text)
        self.assertIn("DurationFrameCount(player.clip, outFps)", text)
        self.assertNotIn("k / 30f", text)

    def test_batch_output_rate_controls_sampling_density_without_changing_speed(self):
        text = BATCH.read_text("utf-8")
        self.assertIn("outputFrame * 30.0 / fps", text)
        self.assertNotIn("for (int vf = frameStart; vf <= last; vf++", text)

    def test_tools_restore_only_the_pipeline_activation_they_own(self):
        studio = STUDIO.read_text("utf-8")
        batch = BATCH.read_text("utf-8")
        self.assertIn("ownsPipelineActivation", studio)
        self.assertIn("ReleasePipelineActivation", studio)
        self.assertIn("pipelineWasActivated", batch)
        self.assertIn("EndfieldCapturedPipelineActivation.Restore()", batch)

    def test_tpose_marks_the_bones_it_calibrates_and_clears_stale_errors(self):
        text = RETARGET.read_text("utf-8")
        self.assertIn("calibrated = true", text)
        self.assertIn('profile.calibrationError = ok ? "" : reason', text)

    def test_recalibration_rebuilds_from_the_clean_captured_bind_pose(self):
        text = PLAYER.read_text("utf-8")
        method = re.search(r"public bool Recalibrate\(\).*?\n        \}", text, re.S)
        self.assertIsNotNone(method)
        self.assertIn("Reset()", method.group(0))
        self.assertIn("MmdRetargetProfile.FromUnity(charRoot)", method.group(0))

    def test_fk_joint_position_uses_parent_rotation_not_the_joint_rotation(self):
        text = RETARGET.read_text("utf-8")
        self.assertIn("output.worldRot[b.parent] * b.localPos", text)
        self.assertNotIn("output.worldRot[i] * b.localPos", text)
        self.assertNotIn("output.localRot[i] * b.localPos", text)

    def test_iterative_ik_converts_radian_limits_to_unity_degrees(self):
        text = RIG.read_text("utf-8")
        self.assertIn("controller.angleLimit * Mathf.Rad2Deg", text)
        self.assertIn("Mathf.DeltaAngle(0f, eul.x) * Mathf.Deg2Rad", text)

    def test_calibration_uses_world_up_expressed_in_character_local_space(self):
        text = RETARGET.read_text("utf-8")
        self.assertIn("charRoot.InverseTransformDirection(Vector3.up)", text)
        self.assertIn("var up = MmdV.Norm(p.calibrationUp)", text)

    def test_each_render_uses_a_unique_run_directory(self):
        studio = STUDIO.read_text("utf-8")
        batch = BATCH.read_text("utf-8")
        self.assertIn("CreateRunDirectory", studio)
        self.assertIn("CreateRunDirectory", batch)

    def test_frame_capture_restores_camera_and_render_target_in_finally(self):
        text = BATCH.read_text("utf-8")
        method = re.search(r"public static void SaveFrame\(.*?\n        \}", text, re.S)
        self.assertIsNotNone(method)
        self.assertIn("finally", method.group(0))
        self.assertIn("cam.targetTexture = previousTarget", method.group(0))
        self.assertIn("RenderTexture.active = previousActive", method.group(0))

    def test_missing_mp4_is_null_not_an_empty_success_path(self):
        text = BATCH.read_text("utf-8")
        self.assertIn("string mp4 = null", text)
        self.assertNotIn('string mp4 = ""', text)

    def test_batch_exposes_a_real_scene_smoke_validation_entrypoint(self):
        text = BATCH.read_text("utf-8")
        self.assertIn("public static void RunSmokeValidation()", text)
        self.assertIn("MmdPlayer.Load", text)
        self.assertIn("player.calibrationOk", text)
        self.assertIn("Camera.vmd", text)
        self.assertIn("mmd-smoke-01", text)

    def test_current_windows_read_back_png_without_a_second_vertical_flip(self):
        studio = STUDIO.read_text("utf-8")
        batch = BATCH.read_text("utf-8")
        self.assertIn("bool flipY = false", batch)
        self.assertIn("SaveFrame(cam, Path.Combine(dir,", studio)
        self.assertIn("w, h, false", studio)
        self.assertIn("SaveFrame(camera, frame, 1280, 720, false)", batch)

    def test_smoke_gate_checks_head_is_above_pelvis(self):
        text = BATCH.read_text("utf-8")
        self.assertIn("headViewport.y <= pelvisViewport.y", text)
        self.assertIn("maxProbeAngle < 5f", text)

    def test_anim_studio_registers_and_unregisters_its_scene_overlay(self):
        text = ANIM.read_text("utf-8")
        self.assertIn("SceneView.duringSceneGui += OnSceneGUI", text)
        self.assertIn("SceneView.duringSceneGui -= OnSceneGUI", text)
        self.assertIn("void OnSceneGUI(SceneView sceneView)", text)

    def test_anim_studio_does_not_destroy_a_preexisting_shadow_caster(self):
        text = ANIM.read_text("utf-8")
        self.assertIn("ownsShadowCaster", text)
        self.assertIn("GetComponent<EndfieldCharacterShadowCaster>()", text)


if __name__ == "__main__":
    unittest.main()
