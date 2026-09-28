import struct
import sys
import tempfile
import unittest
from pathlib import Path

from PIL import Image

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import attribute_render_gap as gap
import compare_pose_official as compare


def solid(size, color):
    return Image.new("RGB", size, color)


def grid(rows):
    return [list(row) for row in rows]


class AttributeRenderGapTests(unittest.TestCase):
    def test_official_labels_load_and_flip(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "labels.bin"
            path.write_bytes(struct.pack("<6H", 1, 2, 3, 4, 5, 6))
            raw = gap.load_official_labels(path, (3, 2), flip=False)
            flipped = gap.load_official_labels(path, (3, 2), flip=True)
        self.assertEqual([raw.getpixel((x, 0)) for x in range(3)], [1, 2, 3])
        self.assertEqual([flipped.getpixel((x, 0)) for x in range(3)], [4, 5, 6])

    def test_official_labels_reject_wrong_size(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "labels.bin"
            path.write_bytes(b"\x00" * 10)
            with self.assertRaisesRegex(ValueError, "expected 12 bytes"):
                gap.load_official_labels(path, (3, 2), flip=False)

    def test_part_from_renderer_name(self):
        self.assertEqual(gap.part_from_renderer_name("S_actor_typhoea_cloth_01_lod0"), "cloth_01")
        self.assertEqual(gap.part_from_renderer_name("S_actor_Typhoea_vfxpart_02_lod0"), "vfxpart_02")

    def test_decode_unity_label(self):
        parts = {0: "body_01", 2: "hair_01"}
        self.assertEqual(gap.decode_unity_label((0, 0, 0), parts), "none")
        self.assertEqual(gap.decode_unity_label((3, 1, 128), parts), "hair_01")
        self.assertEqual(gap.decode_unity_label((1, 1, 255), parts), "body_01/outline")
        self.assertEqual(gap.decode_unity_label((9, 1, 128), parts), "undecodable")
        self.assertEqual(gap.decode_unity_label((3, 1, 77), parts), "undecodable")

    def test_official_part(self):
        parts = {"875": {"part": "hair_01", "pass": "forward"}, "900": {"part": "hair_01", "pass": "outline"}}
        self.assertEqual(gap.official_part(0, parts), "none")
        self.assertEqual(gap.official_part(875, parts), "hair_01")
        self.assertEqual(gap.official_part(900, parts), "hair_01/outline")
        self.assertEqual(gap.official_part(901, parts), "unmapped")

    def test_color_attribution_partitions_region_error(self):
        size = (2, 3)
        official = solid(size, (100, 100, 100))
        current = solid(size, (100, 100, 100))
        current.putpixel((0, 0), (110, 100, 100))   # head, err 10
        current.putpixel((1, 1), (100, 130, 100))   # torso, err 30
        mask = Image.new("1", size, 1)
        off_parts = grid([["hair_01", "hair_01"], ["cloth_01", "cloth_01"], ["cloth_01", "cloth_01"]])
        cur_parts = grid([["hair_01", "hair_01"], ["cloth_01", "body_01"], ["cloth_01", "cloth_01"]])
        result = gap.attribute(official, current, mask, mask, off_parts, cur_parts, None)
        head, torso = result["regions"]["head"], result["regions"]["torso"]
        self.assertEqual(head["err_sum"], 10)
        self.assertEqual(torso["err_sum"], 30)
        self.assertEqual(torso["sources"][0]["official"], "cloth_01")
        self.assertEqual(torso["sources"][0]["current"], "body_01")
        self.assertAlmostEqual(torso["sources"][0]["share"], 1.0)
        self.assertAlmostEqual(sum(s["share"] for s in head["sources"]), 1.0)

    def test_region_totals_match_compare_tool(self):
        size = (4, 6)
        official = Image.new("RGB", size)
        current = Image.new("RGB", size)
        for y in range(size[1]):
            for x in range(size[0]):
                official.putpixel((x, y), (x * 20, y * 10, 50))
                current.putpixel((x, y), (x * 25, y * 7, 60))
        mask = Image.new("1", size, 1)
        parts = grid([["body_01"] * size[0]] * size[1])
        result = gap.attribute(official, current, mask, mask, parts, parts, None)
        reference = compare.region_color_metrics(official, current, mask, mask.getbbox())
        for name in ("head", "torso", "legs"):
            expected = sum(reference[name]["mean_abs_rgb"]) / 3
            self.assertAlmostEqual(result["regions"][name]["mean_abs_rgb_avg"], expected, places=9)

    def test_silhouette_fix_gains(self):
        size = (4, 1)
        official_mask = Image.new("1", size, 0)
        current_mask = Image.new("1", size, 0)
        for x in (0, 1, 2):
            official_mask.putpixel((x, 0), 1)       # x=2 missing in current (book)
        for x in (0, 1, 3):
            current_mask.putpixel((x, 0), 1)        # x=3 extra in current (hair_01)
        off_parts = grid([["body_01", "body_01", "book", "none"]])
        cur_parts = grid([["body_01", "body_01", "none", "hair_01"]])
        img = solid(size, (0, 0, 0))
        result = gap.attribute(img, img, official_mask, current_mask, off_parts, cur_parts, None)
        sil = result["silhouette"]
        self.assertAlmostEqual(sil["iou"], 2 / 4)
        self.assertEqual(sil["missing"][0], {"part": "book", "pixels": 1, "unposed_pixels": 0, "iou_if_fixed": 3 / 4})
        self.assertEqual(sil["extra"][0], {"part": "hair_01", "pixels": 1, "unposed_pixels": 0, "iou_if_fixed": 2 / 3})

    def test_unattributed_share(self):
        size = (1, 3)
        official = solid(size, (0, 0, 0))
        current = solid(size, (30, 30, 30))
        mask = Image.new("1", size, 1)
        off_parts = grid([["unmapped"], ["hair_01"], ["hair_01"]])
        cur_parts = grid([["none"], ["hair_01"], ["hair_01"]])
        result = gap.attribute(official, current, mask, mask, off_parts, cur_parts, None)
        self.assertAlmostEqual(result["unattributed_share"], 1 / 3)


if __name__ == "__main__":
    unittest.main()
