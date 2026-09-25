import re
import unittest
from pathlib import Path


class PoseApplyPostContractTests(unittest.TestCase):
    def test_manual_post_uses_the_frozen_profile_sharpen_strength(self):
        root = Path(__file__).resolve().parents[2]
        profile = (root / "Assets/EndfieldShaderPack/EndfieldCapturedPostProfile.cs").read_text("utf-8")
        pose = (root / "Assets/EndfieldShaderPack/Editor/EndfieldPoseApplyValidation.cs").read_text("utf-8")
        expected = re.search(r"sharpenStrength\s*=\s*([0-9.]+)f", profile)
        self.assertIsNotNone(expected)
        self.assertIn(
            "new Vector4(" + expected.group(1) + "f, 1f, 1f, 0f)", pose,
            "Manual pose post must not amplify sharpness beyond the frozen captured profile.",
        )

    def test_manual_post_preserves_an_explicit_black_bloom_ab_artifact(self):
        root = Path(__file__).resolve().parents[2]
        pose = (root / "Assets/EndfieldShaderPack/Editor/EndfieldPoseApplyValidation.cs").read_text("utf-8")
        self.assertIn('postMaterial.SetTexture("_EndfieldPostBloom", Texture2D.blackTexture)', pose)
        self.assertIn("pose-applied-lit-post-nobloom.png", pose)

    def test_manual_post_uses_the_captured_dynamic_bloom_not_a_static_capture(self):
        root = Path(__file__).resolve().parents[2]
        pose = (root / "Assets/EndfieldShaderPack/Editor/EndfieldPoseApplyValidation.cs").read_text("utf-8")
        self.assertIn("new EndfieldCapturedBloom", pose)
        self.assertIn("dynamicBloom.Render", pose)
        self.assertIn('postMaterial.SetTexture("_EndfieldPostBloom", generatedBloom.rt)', pose)
        self.assertNotIn('EndfieldCaptureAssets.Texture("bloom")', pose)

    def test_pose_apply_activates_the_captured_pipeline_for_the_shadow_render(self):
        root = Path(__file__).resolve().parents[2]
        pose = (root / "Assets/EndfieldShaderPack/Editor/EndfieldPoseApplyValidation.cs").read_text("utf-8")
        self.assertIn("EndfieldCapturedPipelineActivation.Activate()", pose)
        self.assertIn("EndfieldCapturedPipelineActivation.Restore()", pose)
        # LastSkipReason lives on the feature; LastResolved/SelfShadowGateName on
        # the public CharacterShadowPass class (verified against source 2026-09-25).
        self.assertIn("EndfieldCharacterShadowFeature.LastSkipReason", pose)
        self.assertIn("CharacterShadowPass.LastResolved", pose)
        self.assertIn("CharacterShadowPass.SelfShadowGateName", pose)

    def test_pose_apply_supplies_a_transient_shadow_caster_without_saving_the_scene(self):
        root = Path(__file__).resolve().parents[2]
        pose = (root / "Assets/EndfieldShaderPack/Editor/EndfieldPoseApplyValidation.cs").read_text("utf-8")
        self.assertIn("charRoot.gameObject.AddComponent<EndfieldCharacterShadowCaster>()", pose)
        self.assertIn("EndfieldCharacterShadowCaster.Refresh()", pose)
        self.assertIn("DestroyImmediate(transientShadowCaster)", pose)


if __name__ == "__main__":
    unittest.main()
