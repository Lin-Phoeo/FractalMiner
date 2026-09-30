"""Guard the reviewed raw-export schema at the Unity import boundary.

Numerical decoding and actual mesh correspondence are checked by Unity's
ImportCapturedVertexAttrsV2.ValidateAll, not inferred from these source checks.
"""
import unittest
from pathlib import Path

SOURCE = Path(__file__).resolve().parents[2] / "Assets/EndfieldShaderPack/Editor/ImportCapturedVertexAttrsV2.cs"


class VertexImportContractTests(unittest.TestCase):
    def test_location_is_resolved_from_signature(self):
        source = SOURCE.read_text("utf-8")
        self.assertIn('eventData["signature"]', source)
        self.assertNotIn('inputMeta["location"]', source)

    def test_packed_normal_also_supplies_the_real_tangent(self):
        source = SOURCE.read_text("utf-8")
        self.assertIn("DecodePackedFrame", source)
        self.assertNotIn('fmt["compWidth"]', source)

    def test_import_verifies_correspondence_before_mutating_assets(self):
        source = SOURCE.read_text("utf-8")
        self.assertIn("ValidateCorrespondence", source)
        self.assertIn("public static void ValidateAll()", source)
        self.assertIn("SHA256", source)


if __name__ == "__main__":
    unittest.main()
