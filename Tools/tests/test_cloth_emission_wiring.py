"""Actual-program consumption guards; no official-image pixel fitting."""
import json
import re
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
PACK = ROOT / "Assets/EndfieldShaderPack"


def block(code, marker):
    start = code.index("{", code.index(marker))
    depth, end = 1, start + 1
    while depth:
        depth += (code[end] == "{") - (code[end] == "}")
        end += 1
    return code[start:end]


class ClothEmissionWiring(unittest.TestCase):
    def contains(self, code, expression):
        self.assertTrue(expression in code, f"Missing source contract: {expression}")

    def test_factor_is_float_selection_not_bool_or_clamped(self):
        code = (PACK / "EndfieldOfficialClothEmission.hlsl").read_text("utf-8-sig")
        self.contains(code, "(1.0 - premultiply) + sourceBaseAlpha * premultiply")
        self.contains(code, "((sampleRGB * emissionColor) * brightness) * alphaFactor")
        self.assertFalse(any(x in code for x in ("saturate(", "clamp(", " > 0.5", "LinearToSRGB", "SRGBToLinear")))

    def test_alpha_comes_from_captured_base_sample_not_output_alpha(self):
        code = (PACK / "EndfieldCharacterLit.shader").read_text("utf-8-sig")
        self.contains(code, '_AlphaPremultiply ("Source Alpha Premultiply Selector", Float) = 0')
        self.contains(code, "sourceBaseAlpha = clothBaseMap.a * _BaseColor.a")
        self.contains(code, "EFClothCapturedAlphaFactor(sourceBaseAlpha, _AlphaPremultiply)")
        source = block(code, "if (sourceShading)")
        self.contains(source, "sourceAlphaFactor, sourceEmission")
        self.assertNotIn("EFClothCapturedAlphaFactor(alpha", source)

    def test_base_emission_normal_share_uv_and_bias(self):
        code = (PACK / "EndfieldCharacterLit.shader").read_text("utf-8-sig")
        self.contains(code, "sourceCloth = sourceShading && _MaterialFamily < 0.5")
        self.contains(code, "float2 sourceUV = TRANSFORM_TEX(uv, _BaseMap)")
        self.contains(code, "clothBaseMap = SAMPLE_TEXTURE2D_BIAS(_BaseMap")
        self.contains(code, "SAMPLE_TEXTURE2D_BIAS(_EmissionMap, sampler_Endfield_LinearClamp,")
        source = block(code, "if (sourceShading)")
        self.assertNotIn("TRANSFORM_TEX(uv, _EmissionMap)", source)
        self.contains(code, "SAMPLE_TEXTURE2D_BIAS(_BumpMap, sampler_Endfield_LinearClamp,")
        self.contains(source, "EndfieldShadeOfficialCloth(sourceUV, clothBaseMap.rgb * _BaseColor.rgb")

    def test_emission_after_saturation_before_ibl_not_in_caller(self):
        shader = (PACK / "EndfieldCharacterLit.shader").read_text("utf-8-sig")
        source = block(shader, "if (sourceShading)")
        self.assertNotIn("sourceColor += SAMPLE_TEXTURE2D(_EmissionMap", source)
        helper = (PACK / "EndfieldOfficialCloth.hlsl").read_text("utf-8-sig")
        saturation = helper.index("color = lerp(luminance.xxx, color")
        emission = helper.index("color += emission;")
        ibl = helper.index("color += environment *")
        self.assertLess(saturation, emission)
        self.assertLess(emission, ibl)
        self.contains(helper, "diffuseAttenuation * alphaFactor")
        self.contains(helper, "specular * lighting.specLight * _CharacterParams13.w")

    def test_packed_and_ramp_sampling_uses_source_domain(self):
        code = (PACK / "EndfieldOfficialCloth.hlsl").read_text("utf-8-sig")
        self.contains(code, "SAMPLE_TEXTURE2D_BIAS(_MetallicGlossMap")
        self.contains(code, "uv, _EndfieldCapturedGlobalMipBias")
        self.assertNotIn("TRANSFORM_TEX(uv, _MetallicGlossMap)", code)
        for name in ("rampUV", "viewRampUV", "specRampUV"):
            self.assertNotIn(f"TRANSFORM_TEX({name},", code)

    def test_existing_emission_binding_and_import(self):
        mat = (ROOT / "Assets/Typhoeus/Materials/M_actor_typhoea_cloth_02.mat").read_text("utf-8-sig")
        self.contains(mat, "- _UseEmission: 1")
        self.contains(mat, "- _EmissionBrightness: 8")
        binding = re.search(r"_EmissionMap:\s*\n\s*m_Texture:.*guid: ([a-f0-9]+)", mat)
        if binding is None:
            self.fail("Missing emission binding")
        matches = [p for p in (ROOT / "Assets/Typhoeus").glob("*cloth_02_E*.meta")
                   if f"guid: {binding.group(1)}" in p.read_text("utf-8-sig")]
        self.assertEqual(len(matches), 1)
        meta = matches[0].read_text("utf-8-sig")
        self.contains(meta, "sRGBTexture: 1")
        self.contains(meta, "textureType: 0")
        saved = json.loads((ROOT / "Assets/Typhoeus/Materials/M_actor_typhoea_cloth_02.json").read_text("utf-8-sig"))
        self.assertEqual(saved["m_SavedProperties"]["m_Floats"]["_AlphaPremultiply"], 0)


if __name__ == "__main__":
    unittest.main()
