"""Cloth fragment-normal consumption guards, not full native-vertex certification."""
import re
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
PACK = ROOT / "Assets/EndfieldShaderPack"


class ClothNormalWiring(unittest.TestCase):
    def test_decode_order_and_channels(self):
        code = (PACK / "EndfieldOfficialClothNormals.hlsl").read_text("utf-8-sig")
        self.assertIn("float2(packed.r * packed.a, packed.g) * 2.0 - 1.0", code)
        self.assertIn("max(1e-16, sqrt(1.0 - clamp(dot(xy, xy), 0.0, 1.0)))", code)
        self.assertIn("float3(xy * scale, z)", code)
        self.assertNotIn("packed.b", code)
        self.assertNotIn("half", code)

    def test_raw_basis_and_normalization(self):
        code = (PACK / "EndfieldOfficialClothNormals.hlsl").read_text("utf-8-sig")
        self.assertIn("cross(geometryN, tangent.xyz) * tangent.w", code)
        self.assertIn("rsqrt(max(dot(world, world), 1.175494351e-38)) * backfaceFactor", code)
        self.assertIn("normalize(geometryN) * backfaceFactor", code)
        self.assertNotRegex(code, r"normalize\((tangent|cross)")
        self.assertNotIn("EndfieldCharacterRootToWorld", code)

    def test_source_branch_float_sampling(self):
        shader = (PACK / "EndfieldCharacterLit.shader").read_text("utf-8-sig")
        branch = shader[shader.index("EFClothNormals clothNormals;"):shader.index("// Source order:")]
        self.assertIn("float4 clothPackedNormal = SAMPLE_TEXTURE2D_BIAS(_BumpMap", branch)
        self.assertIn("sourceUV, _EndfieldCapturedGlobalMipBias", branch)
        self.assertIn("input.normalWS, input.tangentWS", branch)
        self.assertIn("EFClothDecodeNormals", branch)
        self.assertNotIn("CharTBN", branch)
        self.assertNotIn("UnpackEndfieldNormal", branch)

    def test_mapped_geometry_view_reach_shading_and_vfx(self):
        code = (PACK / "EndfieldCharacterLit.shader").read_text("utf-8-sig")
        branch = code[code.index("EFClothNormals clothNormals;"):code.index("// Source order:")]
        self.assertIn("clothNormals.mapped, clothNormals.geometry, sourceV", branch)
        self.assertIn("sourceVFXN = clothNormals.mapped", branch)
        self.assertIn("sourceVFXV = sourceV", branch)
        self.assertIn("float3 sourceV = normalize(input.viewDirWS)", branch)

    def test_legacy_decode_remains_outside_source_cloth(self):
        code = (PACK / "EndfieldCharacterLit.shader").read_text("utf-8-sig")
        self.assertIn("half3 UnpackEndfieldNormal(half4 packed, half scale)", code)
        self.assertIn("_UseBumpMap > 0.5 && !sourceCloth", code)
        self.assertIn("N = normalize(mul(normalTS, CharTBN(input, N)))", code)

    def test_existing_cloth_normal_assets_keep_current_import(self):
        for name in ("01", "02"):
            mat = (ROOT / f"Assets/Typhoeus/Materials/M_actor_typhoea_cloth_{name}.mat").read_text("utf-8-sig")
            self.assertIn("- _UseBumpMap: 1", mat)
            self.assertIn("- _BumpScale: 1", mat)
            binding = re.search(r"_BumpMap:\s*\n\s*m_Texture:.*guid: ([a-f0-9]+)", mat)
            if binding is None:
                self.fail("Missing normal binding")
            matches = [p for p in (ROOT / "Assets/Typhoeus").glob(f"*cloth_{name}_N*.meta")
                       if f"guid: {binding.group(1)}" in p.read_text("utf-8-sig")]
            self.assertEqual(len(matches), 1)
            meta = matches[0].read_text("utf-8-sig")
            self.assertIn("sRGBTexture: 0", meta)
            # Existing Unity NormalMap import; do not silently retype raw assets.
            # Real compression/swizzle/mip equivalence is a separate audit.
            self.assertIn("textureType: 1", meta)
            self.assertIn("convertToNormalMap: 0", meta)
            self.assertIn("flipGreenChannel: 0", meta)


if __name__ == "__main__":
    unittest.main()
