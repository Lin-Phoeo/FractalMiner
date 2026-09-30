"""Source-contract guards, not screenshot fitting or a GPU-equivalence certificate."""
import re
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
PACK = ROOT / "Assets/EndfieldShaderPack"


def block(code, marker):
    start = code.index("{", code.index(marker))
    depth = 1
    end = start + 1
    while depth:
        depth += (code[end] == "{") - (code[end] == "}")
        end += 1
    return code[start:end]


class HairSplitWiring(unittest.TestCase):
    def test_split_kernel_preserves_captured_decode_order(self):
        code = (PACK / "EndfieldOfficialHairNormals.hlsl").read_text("utf-8-sig")
        self.assertIn("packed.rg", code)
        self.assertIn("packed.ba", code)
        self.assertIn("max(1e-16, sqrt(1.0 - clamp(dot(xy, xy), 0.0, 1.0)))", code)
        self.assertIn("float3(xy * scale, z)", code)
        self.assertIn("cross(geometryN, tangent.xyz) * tangent.w", code)
        self.assertIn("rsqrt(max(dot(diffuseWS, diffuseWS), 1.175494351e-38))", code)
        self.assertIn("normalize(specularWS)", code)
        self.assertNotRegex(code, r"normalize\((geometryN|tangent|cross)")

    def test_live_official_branch_decodes_before_early_return(self):
        code = (PACK / "EndfieldCharacterLit.shader").read_text("utf-8-sig")
        branch = block(code, "if (sourceShading)")
        self.assertIn("EFHairDecodeSplitNormals", branch)
        self.assertIn("sourceUV, _EndfieldCapturedGlobalMipBias", branch)
        self.assertIn("hairNormals.diffuse, hairNormals.specular", branch)
        self.assertIn("input.normalWS, input.tangentWS", branch)
        self.assertIn("float3 sourceV = normalize(input.viewDirWS)", branch)
        hair = block(branch, "else if (_MaterialFamily > 1.5)")
        split = block(hair, "if (_UseSpecBumpMap > 0.5)")
        self.assertIn("EFHairDecodeSplitNormals", split)
        self.assertIn("hairNormals.diffuse = N", hair)
        self.assertIn("hairNormals.specular = N", hair)
        self.assertLess(branch.index("EFHairDecodeSplitNormals"), branch.index("return half4(sourceColor"))
        self.assertNotIn("CharTBN", split)

    def test_sampling_domains(self):
        helper = (PACK / "EndfieldOfficialHair.hlsl").read_text("utf-8-sig")
        self.assertIn("SAMPLE_TEXTURE2D_BIAS(_MetallicGlossMap", helper)
        self.assertIn("uv, _EndfieldCapturedGlobalMipBias", helper)
        self.assertNotIn("TRANSFORM_TEX", helper.replace("TRANSFORM_TEX(uv, _LineMap)", ""))
        shader = (PACK / "EndfieldCharacterLit.shader").read_text("utf-8-sig")
        self.assertIn("SAMPLE_TEXTURE2D_BIAS(_BaseMap", shader)
        self.assertIn("float2 sourceUV = TRANSFORM_TEX(uv, _BaseMap)", shader)

    def test_diffuse_and_specular_consumers_are_separate(self):
        code = (PACK / "EndfieldOfficialHair.hlsl").read_text("utf-8-sig")
        shade = code[code.index("float3 EndfieldShadeOfficialHair"):]
        for expr in ("dot(diffuseN, L)", "dot(diffuseN, cameraAxisZ)",
                     "EFHairDiffuseLighting(albedo, diffuseN", "dot(horizontalLight, diffuseN)", "dot(V, diffuseN)"):
            self.assertIn(expr, shade)
        for expr in ("cross(specularN,", "cross(specularN, objectUp)",
                     "mul(specularN, objectToWorld)",
                     "specularN * (_AnisotropyValue *", "specularN * (_AnisotropyValue2 *",
                     "specularN * (2.0 * _LineValue"):
            self.assertIn(expr, shade)
        self.assertNotRegex(shade, r"\bN\b")

    def test_capture_bias_is_bound_without_urp_global_collision(self):
        code = (PACK / "EndfieldOfficialFrameGlobals.cs").read_text("utf-8-sig")
        self.assertRegex(code, r'SetGlobalFloat\("_EndfieldCapturedGlobalMipBias",\s*-1(?:\.0)?f\)')
        self.assertNotIn('SetGlobalFloat("_GlobalMipBias"', code)

    def test_existing_hn_binding_and_import_are_preserved(self):
        mat = (ROOT / "Assets/Typhoeus/Materials/M_actor_typhoea_hair_01.mat").read_text("utf-8-sig")
        self.assertIn("- _UseSpecBumpMap: 1", mat)
        self.assertIn("- _SpecBumpScale: 1", mat)
        binding = re.search(r"_SplitNormalMap:\s*\n\s*m_Texture:.*guid: ([a-f0-9]+)", mat)
        self.assertIsNotNone(binding)
        if binding is None:
            self.fail("Missing SplitNormalMap material binding")
        guid = binding.group(1)
        matches = [p for p in (ROOT / "Assets/Typhoeus").rglob("*HN*.meta") if f"guid: {guid}" in p.read_text("utf-8-sig")]
        self.assertEqual(len(matches), 1)
        meta = matches[0].read_text("utf-8-sig")
        self.assertIn("sRGBTexture: 0", meta)
        self.assertIn("textureType: 0", meta)


if __name__ == "__main__":
    unittest.main()
