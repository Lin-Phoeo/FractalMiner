import sys
import unittest
from pathlib import Path
import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from summarize_part_hdr import decode_r11g11b10, masked_stats


class PartHdrSummaryTests(unittest.TestCase):
    def test_decode_keeps_unclamped_hdr_and_distinct_rgb_channels(self):
        packed = (16 << 6) | ((15 << 6) << 11) | ((14 << 5) << 22)
        np.testing.assert_array_equal(decode_r11g11b10(np.array([packed], dtype="<u4")), [[2, 1, .5]])

    def test_mask_excludes_background_and_keeps_rgb_mean(self):
        rgb = np.array([[[2, 1, .5], [100, 100, 100]]], dtype=np.float32)
        stats = masked_stats(rgb, np.array([[True, False]]))
        self.assertEqual(stats["pixels"], 1)
        self.assertEqual(stats["mean_rgb"], [2, 1, .5])

    def test_invalid_empty_or_nonfinite_samples_are_rejected(self):
        for rgb, mask in ((np.zeros((1, 1, 3)), np.zeros((1, 1), dtype=bool)),
                          (np.full((1, 1, 3), np.nan), np.ones((1, 1), dtype=bool))):
            with self.assertRaises(ValueError):
                masked_stats(rgb, mask)
