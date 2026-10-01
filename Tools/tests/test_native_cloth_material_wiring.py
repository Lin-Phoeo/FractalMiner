"""Wiring guards; GPU execution is certified separately, not by these strings."""

import unittest
from pathlib import Path

PACK = Path(__file__).resolve().parents[2] / "Assets/EndfieldShaderPack"


class Wiring(unittest.TestCase):
    def test_native_encoding_and_no_asset_mutation(self):
        code = (PACK / "EndfieldCapturedClothMaterials.cs").read_text("utf-8-sig")
        for value in (
            "TextureFormat.BC7",
            "TextureFormat.RGBA32",
            "Apply(false, false)",
            "LoadRawTextureData",
            "!spec.Srgb",
            "MaterialPropertyBlock",
            "ValidateTextures",
        ):
            self.assertIn(value, code)
        for forbidden in ("Compress(", "SaveAssets(", "SetPixels(", "SetTextureScale("):
            self.assertNotIn(forbidden, code)

    def test_loader_and_pose_scoped_entry(self):
        loader = (PACK / "Editor/EndfieldCapturedClothMaterialInputs.cs").read_text(
            "utf-8-sig"
        )
        for value in (
            "ManifestSha256",
            "EndfieldCapturedClothInputs.Load()",
            "ENDFIELD_CLOTH_NATIVE_MATERIALS",
            "IDisposable",
        ):
            self.assertIn(value, loader)
        pose = (PACK / "Editor/EndfieldPoseApplyValidation.cs").read_text("utf-8-sig")
        self.assertIn(
            "EndfieldCapturedClothMaterialInputs.BindIfRequested(charRoot, report)",
            pose,
        )
