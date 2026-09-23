import json
import sys
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace as NS
from unittest.mock import Mock, patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import capture_bloom_evidence as evidence


class BloomEvidenceTests(unittest.TestCase):
    def runtime(self):
        controller, capture, state = Mock(), Mock(), Mock()
        access = NS(descriptorStore='ResourceId::69499', byteOffset=2, byteSize=1,
                    index=0, arrayElement=0, stage='Compute', type='Sampler',
                    staticallyUnused=False, this='SWIG POINTER', thisown=False)
        sampler = NS(object='ResourceId::42', type='Sampler', addressU='ClampEdge',
                     addressV='ClampEdge', addressW='ClampEdge', compareFunction='AlwaysTrue',
                     maxAnisotropy=1.0, minLOD=0.0, maxLOD=1000.0, mipBias=0.0,
                     unnormalized=False, creationTimeConstant=False, seamlessCubemaps=True,
                     srgbBorder=False, borderColorType='Float',
                     borderColorValue=NS(floatValue=[0.0, 0.0, 0.0, 0.0]),
                     filter=NS(minify='Linear', magnify='Linear', mip='Point', filter='Normal',
                               this='SWIG FILTER POINTER'), this='SWIG SAMPLER POINTER')
        state.GetSamplers.return_value = [NS(access=access, descriptor=NS(resource='WRONG GENERIC DESCRIPTOR'))]
        controller.GetSamplerDescriptors.return_value = [sampler]
        controller.GetPipelineState.return_value = state
        controller.GetFrameInfo.return_value = NS(frameNumber=6411)
        selected = [1121]
        controller.SetFrameEvent.side_effect = lambda event, force: selected.__setitem__(0, event)
        expected = dict(evidence.OUTPUTS)
        state.GetReadWriteResources.side_effect = lambda stage: [NS(descriptor=NS(resource='ResourceId::' + str(expected[selected[0]])))]
        dimensions = [(1280,800),(640,400),(320,200),(160,100),(80,50),(40,25),(20,13),(10,6),(5,3),
                      (10,6),(20,13),(40,25),(80,50),(160,100),(320,200),(640,400),(1280,800)]
        controller.GetTextures.return_value = [NS(resourceId='ResourceId::'+str(resource),
            width=size[0], height=size[1], arraysize=1, mips=1, format=NS(Name=lambda:'R11G11B10_FLOAT'))
            for (_,resource),size in zip(evidence.OUTPUTS,dimensions)]
        rd = NS(ShaderStage=NS(Compute='Compute'), DescriptorType=NS(Sampler='Sampler', ImageSampler='ImageSampler'),
                DescriptorRange=Mock(side_effect=lambda item:NS(byteOffset=item.byteOffset, descriptorSize=item.byteSize, count=1)))
        return rd, capture, controller, state, access

    def test_plan_is_fixed_17_events_with_captured_odd_dimensions(self):
        self.assertEqual(len(evidence.PLAN),17)
        self.assertEqual(len({p['event'] for p in evidence.PLAN}),17)
        self.assertEqual(evidence.PLAN[6]['height'],13)
        self.assertEqual(evidence.PLAN[-1]['id'],58923)
        self.assertEqual(evidence.PLAN[0]['event'],1121)

    def test_resolves_real_sampler_from_store_and_access_range(self):
        rd, _, controller, state, access = self.runtime()
        rows=evidence.collect_samplers(rd,controller,state)
        rd.DescriptorRange.assert_called_once_with(access)
        self.assertEqual(controller.GetSamplerDescriptors.call_args.args[0],access.descriptorStore)
        self.assertEqual(rows[0]['sampler']['filter']['minify'],'Linear')
        self.assertEqual(rows[0]['sampler']['addressU'],'ClampEdge')
        self.assertNotIn('SWIG',json.dumps(rows))
        self.assertNotIn('this',rows[0]['access'])

    def test_rejects_missing_sampler_payload(self):
        rd, _, controller, state, _ = self.runtime()
        controller.GetSamplerDescriptors.return_value=[]
        with self.assertRaises(ValueError):evidence.collect_samplers(rd,controller,state)

    def test_rejects_non_sampler_descriptor_type(self):
        rd, _, controller, state, _ = self.runtime()
        controller.GetSamplerDescriptors.return_value[0].type='Unknown'
        with self.assertRaises(ValueError):evidence.collect_samplers(rd,controller,state)

    def test_rejects_missing_sampler_access(self):
        rd, _, controller, state, _ = self.runtime()
        state.GetSamplers.return_value=[]
        with self.assertRaises(ValueError):evidence.collect_samplers(rd,controller,state)

    def run_mock(self, sampler_only=True, failure=None):
        rd, cap, controller, state, _ = self.runtime()
        if failure:failure(cap,controller,state)
        with tempfile.TemporaryDirectory() as directory:
            capture=Path(directory)/'frame.rdc';capture.touch()
            output=Path(directory)/'output'
            with patch.dict('os.environ',{'ENDFIELD_CAPTURE_PATH':str(capture),
                    'ENDFIELD_CAPTURE_OUTPUT':str(output),'ENDFIELD_BLOOM_SAMPLER_ONLY':'1' if sampler_only else '0'}), \
                    patch.dict(sys.modules,{'renderdoc':rd}), \
                    patch.object(evidence,'open_controller',return_value=(cap,controller)), \
                    patch.object(evidence,'save_texture',return_value={'file':'export'}) as save:
                error=None
                try:evidence.run()
                except Exception as exc:error=exc
                manifest=json.loads((output/'complete.json').read_text()) if (output/'complete.json').exists() else None
                failure_record=json.loads((output/'error.json').read_text()) if (output/'error.json').exists() else None
            return cap,controller,save,manifest,failure_record,error

    def test_sampler_only_visits_plan_without_saving_images(self):
        cap,controller,save,manifest,_,error=self.run_mock()
        self.assertIsNone(error)
        self.assertEqual(manifest['mode'],'sampler-only')
        self.assertEqual(len(manifest['events']),17)
        self.assertTrue(all(not row['files'] for row in manifest['events']))
        save.assert_not_called()
        cap.Shutdown.assert_called_once();controller.Shutdown.assert_called_once()

    def test_default_mode_preserves_dds_and_exr_exports(self):
        _,_,save,manifest,_,error=self.run_mock(False)
        self.assertIsNone(error)
        self.assertEqual(save.call_count,34)
        self.assertEqual(manifest['mode'],'textures-and-samplers')

    def test_wrong_frame_fails_before_sampling_and_shuts_down(self):
        def failure(cap,controller,state):controller.GetFrameInfo.return_value=NS(frameNumber=12)
        cap,controller,save,manifest,record,error=self.run_mock(failure=failure)
        self.assertIsInstance(error,ValueError);self.assertIsNone(manifest)
        self.assertIn('6411',record['traceback']);save.assert_not_called()
        cap.Shutdown.assert_called_once();controller.Shutdown.assert_called_once()

    def test_wrong_uav_never_reports_success_or_saves_texture(self):
        def failure(cap,controller,state):state.GetReadWriteResources.side_effect=lambda stage:[NS(descriptor=NS(resource='ResourceId::999'))]
        cap,controller,save,manifest,record,error=self.run_mock(failure=failure)
        self.assertIsInstance(error,ValueError);self.assertIsNone(manifest)
        self.assertIn('UAV',record['traceback']);save.assert_not_called()
        cap.Shutdown.assert_called_once();controller.Shutdown.assert_called_once()

    def test_unexpected_additional_uav_is_not_ignored(self):
        def failure(cap,controller,state):state.GetReadWriteResources.side_effect=lambda stage:[NS(descriptor=NS(resource='ResourceId::59945')),NS(descriptor=NS(resource='ResourceId::999'))]
        *_,error=self.run_mock(failure=failure)
        self.assertIsInstance(error,ValueError)

    def test_texture_format_and_dimensions_are_verified_even_sampler_only(self):
        def failure(cap,controller,state):controller.GetTextures.return_value[0].width=99
        _,_,save,manifest,_,error=self.run_mock(failure=failure)
        self.assertIsInstance(error,ValueError);self.assertIsNone(manifest);save.assert_not_called()

    def test_capture_releases_even_if_controller_shutdown_raises(self):
        def failure(cap,controller,state):controller.Shutdown.side_effect=RuntimeError('shutdown failed')
        cap,controller,_,manifest,record,error=self.run_mock(failure=failure)
        self.assertIsInstance(error,RuntimeError);self.assertIsNone(manifest)
        self.assertIn('shutdown failed',record['traceback'])
        cap.Shutdown.assert_called_once();controller.Shutdown.assert_called_once()

    def test_existing_output_is_refused_before_open(self):
        with tempfile.TemporaryDirectory() as directory:
            capture=Path(directory)/'frame.rdc';capture.touch()
            output=Path(directory)/'output';output.mkdir();(output/'keep').touch()
            with patch.dict('os.environ',{'ENDFIELD_CAPTURE_PATH':str(capture),'ENDFIELD_CAPTURE_OUTPUT':str(output)}), \
                    patch.object(evidence,'open_controller') as opening:
                with self.assertRaises(FileExistsError):evidence.run()
                opening.assert_not_called()


if __name__=='__main__':unittest.main()
