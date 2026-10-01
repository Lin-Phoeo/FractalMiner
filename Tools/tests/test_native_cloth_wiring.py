"""Native input safety/consumption guards, not screenshot matching."""
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
PACK = ROOT / 'Assets/EndfieldShaderPack'


class NativeClothWiring(unittest.TestCase):
    def test_native_upload_without_transcoding_or_regenerating_mips(self):
        code = (PACK / 'EndfieldCapturedClothNormals.cs').read_text('utf-8-sig')
        for expected in ('TextureFormat.BC5, 12, true', 'LoadRawTextureData(data)',
                         'Apply(false, false)', 'FilterMode.Bilinear', 'TextureWrapMode.Repeat',
                         'SHA256.Create()', '5592432'):
            self.assertIn(expected, code)
        self.assertNotIn('Compress(', code)
        self.assertNotIn('SetPixels(', code)

    def test_slot_binding_restores_and_preserves_overrides(self):
        code = (PACK / 'EndfieldCapturedClothNormals.cs').read_text('utf-8-sig')
        for expected in ('GetPropertyBlock', 'SetPropertyBlock', 'previous.isEmpty', 'IDisposable',
                         'M_actor_typhoea_cloth_01', 'M_actor_typhoea_cloth_02'):
            self.assertIn(expected, code)
        self.assertNotIn('sharedMaterial.SetTexture', code)
        self.assertNotIn('SaveAssets', code)

    def test_source_bias_reads_share_texture_bound_sampler(self):
        shader = (PACK / 'EndfieldCharacterLit.shader').read_text('utf-8-sig')
        cloth = (PACK / 'EndfieldOfficialCloth.hlsl').read_text('utf-8-sig')
        for name in ('_BaseMap', '_BumpMap', '_EmissionMap'):
            self.assertIn('SAMPLE_TEXTURE2D_BIAS(' + name + ', sampler_BumpMap,', shader)
        self.assertIn('SAMPLE_TEXTURE2D_BIAS(_MetallicGlossMap, sampler_BumpMap,', cloth)
        for name in ('_DiffRampMap', '_SpecRampMap'):
            self.assertIn('SAMPLE_TEXTURE2D_LOD(' + name + ', sampler_Endfield_LinearClamp,', cloth)

    def test_pinned_evidence_no_scene_or_asset_writes(self):
        code = (PACK / 'Editor/EndfieldCapturedClothInputs.cs').read_text('utf-8-sig')
        for expected in ('ManifestSha256', 'ENDFIELD_CLOTH_NATIVE_EXPORT', 'complete.json', 'CreateTexture'):
            self.assertIn(expected, code)
        for forbidden in ('SaveScene(', 'SaveAssets(', 'CreateAsset(', 'SaveAndReimport('):
            self.assertNotIn(forbidden, code)

    def test_pose_entry_restores_slot_overrides_after_labels(self):
        code = (PACK / 'Editor/EndfieldPoseApplyValidation.cs').read_text('utf-8-sig')
        self.assertIn('EndfieldCapturedClothInputs.BindIfRequested(charRoot, report)', code)
        self.assertIn('originalBlocks', code)
        self.assertIn('originalBlocks[r][s]', code)


if __name__ == '__main__':
    unittest.main()
