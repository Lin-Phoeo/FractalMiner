import hashlib
import struct
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from capture_part_hdr import changed_mask, decode_unsigned_float, select_part_draws


class CapturePartHdrTests(unittest.TestCase):
    def test_signature_selection_uses_bytecode_not_cross_capture_ids(self):
        digest = hashlib.sha256(b"face shader").hexdigest()
        signatures = {"face": {"indices": 10686, "sha256": digest}}
        draws = [
            {"event": 1006, "indices": 10686, "sha256": digest, "outputs": ["scene"]},
            {"event": 1058, "indices": 10686, "sha256": "outline", "outputs": ["scene"]},
            {"event": 622, "indices": 10686, "sha256": digest, "outputs": ["gbuffer"]},
        ]
        self.assertEqual(select_part_draws(draws, signatures, "scene")["face"]["event"], 1006)

    def test_signature_selection_refuses_missing_or_ambiguous_part(self):
        signature = {"face": {"indices": 3, "sha256": "digest"}}
        draw = {"event": 1, "indices": 3, "sha256": "digest", "outputs": ["scene"]}
        for draws in ([], [draw, dict(draw, event=2)], [dict(draw, indices=6)]):
            with self.subTest(draws=draws), self.assertRaises(ValueError):
                select_part_draws(draws, signature, "scene")

    def test_diff_mask_is_per_pixel_and_rejects_truncated_data(self):
        before = struct.pack("<4I", 0, 1, 2, 3)
        after = struct.pack("<4I", 0, 7, 2, 9)
        self.assertEqual(changed_mask(before, after, 2, 2), bytes([0, 1, 0, 1]))
        with self.assertRaises(ValueError):
            changed_mask(before, after[:-1], 2, 2)

    def test_unsigned_hdr_decoding_preserves_values_above_one_and_subnormal(self):
        self.assertEqual(decode_unsigned_float(15 << 6, 6), 1.0)
        self.assertEqual(decode_unsigned_float(16 << 6, 6), 2.0)
        self.assertEqual(decode_unsigned_float(1, 6), 2.0 ** -20)
        self.assertEqual(decode_unsigned_float(15 << 5, 5), 1.0)


if __name__ == "__main__":
    unittest.main()
