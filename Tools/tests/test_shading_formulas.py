import math
import unittest


# Mirror of characternpr_skin/Sub0_Pass1_Vertex_b273.hlsl:531-543 (C6-verified).
# The official outline computes a FOV-half angle via this atan polynomial to keep
# screen-space outline width constant across FOV. Pins the poly-constant transcription.
def outline_fov_atan(proj_m11: float) -> float:
    f = -1.0 / proj_m11
    a = abs(f)
    small = a < 1.0
    r = a if small else 1.0 / a
    r2 = r * r
    poly = (1.0 + ((-0.3018949925899505615234375 + 0.087292902171611785888671875 * r2) * r2)) * r
    val = poly if small else (1.57079637050628662109375 - poly)
    return -val if f < 0 else val


class ShadingFormulaTests(unittest.TestCase):
    def test_outline_fov_atan_matches_atan(self):
        # URP ProjMatrix[1].y = 1/tan(fovY/2); f = -1/that = -tan(fovY/2) (<0 for fovY<180).
        # |got| should approximate atan(tan(fovY/2)) = fovY/2 for fovY < 90 (|f|<1).
        for fov_deg in (20, 35, 50, 70):
            half = math.radians(fov_deg) / 2
            m11 = 1.0 / math.tan(half)
            got = outline_fov_atan(m11)
            self.assertAlmostEqual(abs(got), half, places=2)


if __name__ == "__main__":
    unittest.main()
