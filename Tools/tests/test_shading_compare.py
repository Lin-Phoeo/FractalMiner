import sys, unittest
from pathlib import Path
from PIL import Image
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import shading_compare as sc
import compare_pose_official as cmp


def grid(rows): return [list(r) for r in rows]
def solid(size, color): return Image.new("RGB", size, color)


class ShadingCompareTests(unittest.TestCase):
    def test_part_base_strips_outline(self):
        self.assertEqual(sc.part_base("cloth_01/outline"), "cloth_01")
        self.assertEqual(sc.part_base("hair_01"), "hair_01")
        self.assertEqual(sc.part_base("none"), "none")

    def test_family_of_covers_vocabulary(self):
        for p in ("body_01", "face_01"): self.assertEqual(sc.family_of(p), "skin")
        for p in ("hair_01", "hairshadow_01"): self.assertEqual(sc.family_of(p), "hair")
        for p in ("cloth_01", "cloth_07", "cloth_03/outline"): self.assertEqual(sc.family_of(p), "cloth")
        for p in ("iris_01", "eyeshadow_01", "brow_01"): self.assertEqual(sc.family_of(p), "eye")
        for p in ("book", "background", "other", "none", "unmapped", "undecodable", "vfxpart_01"):
            self.assertEqual(sc.family_of(p), "other")

    def test_overlap_only_same_family_counted(self):
        size = (2, 2)
        official = solid(size, (100, 100, 100)); current = solid(size, (100, 100, 100))
        current.putpixel((0, 0), (110, 100, 100))   # skin∩skin, R err 10
        current.putpixel((1, 0), (200, 100, 100))   # official skin vs current cloth -> excluded
        mask = Image.new("1", size, 1)
        op = grid([["body_01", "body_01"], ["hair_01", "hair_01"]])
        cp = grid([["body_01", "cloth_01"], ["hair_01", "hair_01"]])
        fam = sc.compare_families(official, current, op, cp, mask)
        self.assertEqual(fam["skin"]["pixels"], 1)
        self.assertEqual(fam["skin"]["mean_abs_rgb_max"], 10)
        self.assertEqual(fam["hair"]["pixels"], 2)
        self.assertEqual(fam["hair"]["mean_abs_rgb_max"], 0)
        self.assertEqual(fam["cloth"]["pixels"], 0)   # no cloth∩cloth overlap

    def test_family_min_pixels_flag(self):
        size = (1, 1); img = solid(size, (0, 0, 0)); mask = Image.new("1", size, 1)
        fam = sc.compare_families(img, img, grid([["body_01"]]), grid([["body_01"]]), mask)
        self.assertTrue(fam["skin"]["low_sample"])   # 1 px < MIN_PIXELS
        self.assertFalse(fam["skin"]["pass"])         # low sample never passes

    def test_reuses_workspace_symbols(self):
        self.assertIs(sc.WORK_SIZE, cmp.WORK_SIZE)
        size = (4, 4)
        official = Image.new("RGB", size); current = Image.new("RGB", size)
        for y in range(4):
            for x in range(4):
                official.putpixel((x, y), (x * 10, y * 10, 20)); current.putpixel((x, y), (x * 13, y * 7, 25))
        mask = Image.new("1", size, 1)
        op = grid([["body_01"] * 4] * 4); cp = grid([["body_01"] * 4] * 4)
        fam = sc.compare_families(official, current, op, cp, mask)
        opx, cpx = official.load(), current.load()
        exp0 = sum(abs(opx[x, y][0] - cpx[x, y][0]) for y in range(4) for x in range(4)) / 16
        self.assertAlmostEqual(fam["skin"]["mean_abs_rgb"][0], exp0)


if __name__ == "__main__":
    unittest.main()
