"""Native BC5 input evidence tests; no rendered-image comparisons."""
import hashlib
import sys
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace as NS
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import capture_cloth_normals as export


class ClothNormalCaptureTests(unittest.TestCase):
    def test_reviewed_plan_identity(self):
        self.assertEqual([(p['event'], p['id'], p['shader'], p['zip_entry']) for p in export.PLAN],
                         [(835, 37987, 22255, '002959'), (850, 37828, 37669, '004532')])

    def test_layout_includes_small_mips_without_padding(self):
        sizes = export.bc5_layout(2048, 2048, 12)
        self.assertEqual(sum(s['bytes'] for s in sizes), 5592432)
        self.assertEqual([s['bytes'] for s in sizes[-3:]], [16, 16, 16])
        self.assertEqual(sizes[-1]['offset'] + sizes[-1]['bytes'], 5592432)

    def test_variant_specific_binding_and_shared_sampler(self):
        self.assertEqual([p['normal_binding'] for p in export.PLAN], [4, 5])
        self.assertEqual(export.NORMAL_SAMPLER, (0, 4))

    def test_view_domain_is_not_image_metadata(self):
        view = {'format': 'BC5_UNORM', 'textureType': 'TextureType.Texture2D', 'firstMip': 0,
                    'numMips': 12, 'firstSlice': 0, 'numSlices': 1, 'minLODClamp': 0,
                    'swizzle': ['TextureSwizzle.' + c for c in ('Red', 'Green', 'Blue', 'Alpha')]}
        export.validate_view(view)
        for key, bad in (('numMips', 1), ('firstMip', 1), ('minLODClamp', 1),
                         ('format', 'BC5_SNORM'), ('swizzle', ['TextureSwizzle.One'] * 4)):
            with self.subTest(key=key), self.assertRaises(ValueError):
                export.validate_view(dict(view, **{key: bad}))

    def test_bad_layout_is_rejected(self):
        for args in ((0, 4, 1), (4, 4, 0), (4, 4, 4), (True, 4, 1)):
            with self.subTest(args=args), self.assertRaises(ValueError):
                export.bc5_layout(*args)

    def test_per_mip_exact_raw_payload_and_hash(self):
        levels = [b'a' * 64, b'b' * 16, b'c' * 16, b'd' * 16]
        initial = b''.join(levels)
        rows = export.verify_mips(levels, initial, 8, 8, 4)
        self.assertEqual(rows[1]['offset'], 64)
        self.assertEqual(rows[2]['sha256'], hashlib.sha256(levels[2]).hexdigest())
        self.assertTrue(all(r['initial_contents_equal'] for r in rows))

    def test_reject_changed_or_reordered_mips(self):
        levels = [b'a' * 64, b'b' * 16, b'c' * 16, b'd' * 16]
        for initial in (b''.join(levels) + b'x', b''.join(levels)[::-1]):
            with self.assertRaises(ValueError):
                export.verify_mips(levels, initial, 8, 8, 4)

    def test_reject_truncated_readback_and_wrong_mip_count(self):
        for levels in ([b'a' * 64], [b'a' * 63, b'b' * 16, b'c' * 16, b'd' * 16]):
            with self.assertRaises(ValueError):
                export.verify_mips(levels, b'a' * 112, 8, 8, 4)


class OfflineReplayFixture:
    """Only API/IO contracts; real source/GPU fidelity is the separate RDC replay."""
    def __init__(self, fail=''):
        self.fail, self.event, self.shutdown = fail, 835, False
        self.rows = export.bc5_layout(2048, 2048, 12)
        self.payloads = {p['zip_entry']: bytes([i+3]) * 5592432 for i, p in enumerate(export.PLAN)}
        self.plans = [dict(p, sha256=hashlib.sha256(self.payloads[p['zip_entry']]).hexdigest()) for p in export.PLAN]
        self.rd = NS(ShaderStage=NS(Pixel='ShaderStage.Pixel'),
                     DescriptorType=NS(Sampler='sampler', ImageSampler='image-sampler'),
                     Subresource=lambda mip, layer, sample: NS(mip=mip, layer=layer, sample=sample),
                     DescriptorRange=lambda access: access, CompType=NS(UNorm='unorm'))

    def plan(self):
        return next(p for p in self.plans if p['event'] == self.event)

    def access(self):
        return NS(index=0, descriptorStore='store', byteOffset=17, byteSize=1, arrayElement=0,
                  stage='ShaderStage.Pixel', type='image', staticallyUnused=False)

    def GetFrameInfo(self):
        return NS(frameNumber=0 if self.fail == 'frame' else 6411)

    def GetTextures(self):
        return [NS(resourceId='ResourceId::'+str(p['id']), width=2048, height=2048, depth=1,
                   arraysize=1, mips=12, format=NS(Name=lambda: 'BC7_UNORM' if self.fail == 'format' else 'BC5_UNORM')) for p in self.plans]

    def SetFrameEvent(self, event, force):
        self.event = event

    def GetPipelineState(self):
        return self

    def GetShader(self, stage):
        return 'ResourceId::'+str(0 if self.fail == 'shader' else self.plan()['shader'])

    def GetShaderReflection(self, stage):
        return NS(rawBytes=b'fixture-program',
                  readOnlyResources=[NS(fixedBindNumber=self.plan()['normal_binding'], fixedBindSetOrSpace=1, name='normal')],
                  samplers=[NS(fixedBindNumber=4, fixedBindSetOrSpace=0, name='sampler')])

    def GetReadOnlyResources(self, stage):
        if self.fail == 'missing-binding':
            return []
        swizzle = NS(**{c: 'TextureSwizzle.'+c.title() for c in ('red', 'green', 'blue', 'alpha')})
        if self.fail == 'swizzle':
            swizzle.red = 'TextureSwizzle.One'
        descriptor = NS(resource='ResourceId::'+str(0 if self.fail == 'resource' else self.plan()['id']),
                        view='view', type='image', textureType='TextureType.Texture2D',
                        format=NS(Name=lambda: 'BC5_UNORM'), firstMip=0, numMips=12,
                        firstSlice=0, numSlices=1, minLODClamp=0, swizzle=swizzle)
        return [NS(access=self.access(), descriptor=descriptor)]

    def GetTextureData(self, resource, subresource):
        row = self.rows[subresource.mip]
        data = self.payloads[self.plan()['zip_entry']][row['offset']:row['offset']+row['bytes']]
        return data[:-1] if self.fail == 'truncated-mip' else data

    def GetSamplers(self, stage):
        return [] if self.fail == 'missing-sampler' else [NS(access=self.access())]

    def GetSamplerDescriptors(self, store, ranges):
        return [] if self.fail == 'unresolved-sampler' else [NS(type='sampler')]

    def PickPixel(self, resource, x, y, subresource, cast):
        return NS(floatValue=[.5, .5, 0., 1.])

    def Shutdown(self):
        self.shutdown = True
        if self.fail == 'shutdown':
            raise RuntimeError('fixture shutdown failure')

    def read(self, entry):
        data = self.payloads[entry]
        return data[:-1] if self.fail == 'initial' else data

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False


class OfflineReplayContractTests(unittest.TestCase):
    def collect(self, fixture, folder):
        with patch.object(export, 'PLAN', fixture.plans), patch.object(export.zipfile, 'ZipFile', return_value=fixture), \
                patch.object(export, 'sampler_record', return_value={'fixture': True}):
            return export.collect(fixture.rd, fixture, Path('fixture.zip'), folder)

    def test_collect_exact_mips_sampler_reflection_and_exclusive_outputs(self):
        fixture = OfflineReplayFixture()
        with tempfile.TemporaryDirectory() as folder:
            output = Path(folder)
            results = self.collect(fixture, output)
            self.assertEqual(len(results), 2)
            for record in results:
                self.assertEqual((output / record['file']).read_bytes(), fixture.payloads[record['zip_entry']])
                self.assertEqual(record['normal']['binding'], record['normal_binding'])
                self.assertEqual(record['samplers'][0]['access']['byteOffset'], 17)
                self.assertEqual(len(record['native_samples']), 60)
                self.assertEqual(record['shader_sha256'], hashlib.sha256(b'fixture-program').hexdigest())
            with self.assertRaises(FileExistsError):
                self.collect(fixture, output)

    def test_collect_rejects_foreign_or_incomplete_evidence(self):
        for fail in ('frame', 'shader', 'resource', 'swizzle', 'missing-binding', 'format',
                     'initial', 'truncated-mip', 'missing-sampler', 'unresolved-sampler'):
            with self.subTest(fail=fail), tempfile.TemporaryDirectory() as folder, self.assertRaises(ValueError):
                self.collect(OfflineReplayFixture(fail), Path(folder))

    def test_reflection_index_is_not_descriptor_byte_offset(self):
        used = NS(access=NS(index=65535))
        with self.assertRaises(ValueError):
            export.binding(used, [])

    def test_run_marks_complete_only_after_successful_shutdown(self):
        for fail in ('', 'shader', 'shutdown'):
            fixture = OfflineReplayFixture(fail)
            cap = NS(Shutdown=lambda: None)
            with self.subTest(fail=fail), tempfile.TemporaryDirectory() as folder:
                root = Path(folder)
                capture = root / 'fixture.rdc'
                capture.write_bytes(b'offline test fixture')
                output = root / 'export'
                env = {'ENDFIELD_CAPTURE_PATH': str(capture), 'ENDFIELD_CAPTURE_OUTPUT': str(output),
                       'ENDFIELD_CAPTURE_ZIP': str(root / 'fixture.zip')}
                with patch.dict(export.os.environ, env), patch.dict(sys.modules, {'renderdoc': fixture.rd}), \
                        patch.object(export, 'open_controller', return_value=(cap, fixture)), \
                        patch.object(export, 'PLAN', fixture.plans), patch.object(export.zipfile, 'ZipFile', return_value=fixture), \
                        patch.object(export, 'sampler_record', return_value={'fixture': True}):
                    if fail:
                        with self.assertRaises((ValueError, RuntimeError)):
                            export.run()
                        self.assertTrue((output / 'error.json').is_file())
                        self.assertFalse((output / 'complete.json').exists())
                    else:
                        export.run()
                        self.assertTrue(fixture.shutdown)
                        self.assertTrue((output / 'complete.json').is_file())


if __name__ == '__main__':
    unittest.main()
