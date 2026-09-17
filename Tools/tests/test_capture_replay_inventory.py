import sys
import json
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace as NS
from unittest.mock import Mock, patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import capture_replay_inventory as inventory


class InventoryTests(unittest.TestCase):
    def fake_runtime(self):
        def action(eid, flags):
            return NS(eventId=eid, actionId=eid, flags=flags, numIndices=42,
                      numInstances=1, baseVertex=0, indexOffset=0, vertexOffset=0,
                      instanceOffset=0, children=[], GetName=lambda _: 'action')
        controller, cap, state = Mock(), Mock(), Mock()
        controller.GetRootActions.return_value = [action(1, 0), action(2, 1), action(3, 1), action(4, 2)]
        controller.GetStructuredFile.return_value = None
        controller.GetResources.return_value = [NS(resourceId='ResourceId::99', name='texture')]
        controller.GetTextures.return_value = [NS(resourceId='ResourceId::99', width=4, height=4,
            depth=1, arraysize=1, mips=1, format=NS(Name=lambda: 'RGBA8'), creationFlags=1, byteSize=64)]
        controller.GetBuffers.return_value = [NS(resourceId='ResourceId::8', length=64, creationFlags=1)]
        controller.GetAPIProperties.return_value = NS(pipelineType='Vulkan')
        controller.GetFrameInfo.return_value = NS(frameNumber=7)
        controller.GetPipelineState.return_value = state
        state.GetGraphicsPipelineObject.return_value = 'ResourceId::2'
        state.GetComputePipelineObject.return_value = 'ResourceId::3'
        state.GetOutputTargets.return_value = [NS(resource='ResourceId::99')]
        state.GetDepthTarget.return_value = NS(resource='ResourceId::10')
        binding = NS(name='Globals', fixedBindNumber=17, fixedBindSetOrSpace=3)
        reflection = NS(rawBytes=b'spirv', entryPoint='main', constantBlocks=[binding], readOnlyResources=[binding])
        state.GetShaderReflection.side_effect = lambda stage: None if stage == 'Vertex' else reflection
        state.GetShader.return_value = 'ResourceId::22'
        state.GetShaderEntryPoint.return_value = 'main'
        used = NS(access=NS(index=0, arrayElement=0),
                  descriptor=NS(resource='ResourceId::8', byteOffset=128, byteSize=64))
        state.GetReadOnlyResources.return_value = [used]
        state.GetConstantBlock.return_value = used
        controller.GetCBufferVariableContents.return_value = [NS(name='Light', type='Float', rows=1,
            columns=2, members=[], value=NS(f32v=[0.1, 0.2]))]
        controller.DisassembleShader.return_value = 'shader disassembly'
        cap.OpenFile.return_value = 'ok'
        cap.OpenCapture.return_value = ('ok', controller)
        rd = NS(OpenCaptureFile=lambda: cap, ResultCode=NS(Succeeded='ok'), ReplayOptions=lambda: None,
                ActionFlags=NS(Drawcall=1, Dispatch=2), ShaderStage=NS(Vertex='Vertex', Pixel='Pixel', Compute='Compute'))
        return rd, cap, controller

    def test_inventory_counts_actions_and_replays_last_event(self):
        rd, _, controller = self.fake_runtime()
        result = inventory.collect_inventory(rd, controller)
        self.assertEqual((result['draw_count'], result['dispatch_count']), (2, 1))
        self.assertEqual(result['textures'][0]['name'], 'texture')
        controller.SetFrameEvent.assert_called_once_with(4, True)

    def test_empty_frame_has_no_replay_event(self):
        rd, _, controller = self.fake_runtime()
        controller.GetRootActions.return_value = []
        self.assertIsNone(inventory.collect_inventory(rd, controller)['replayed_last_event'])
        controller.SetFrameEvent.assert_not_called()

    def test_present_preview_replays_and_checks_save_result(self):
        rd, _, controller = self.fake_runtime()
        rd.ActionFlags.Present = 4
        rd.TextureSave = lambda: NS(slice=NS(sliceIndex=0))
        rd.FileType = NS(PNG='PNG')
        controller.GetRootActions.return_value = [NS(eventId=9, flags=4, copyDestination='ResourceId::99', children=[])]
        controller.SaveTexture.return_value = 'ok'
        with tempfile.TemporaryDirectory() as directory:
            result = inventory.save_present_preview(rd, controller, Path(directory))
        self.assertEqual(result['resource'], 'ResourceId::99')
        controller.SetFrameEvent.assert_called_once_with(9, True)
        self.assertEqual(controller.SaveTexture.call_args.args[0].resourceId, 'ResourceId::99')

    def test_present_preview_failure_is_not_reported_as_success(self):
        rd, _, controller = self.fake_runtime()
        rd.ActionFlags.Present = 4
        rd.TextureSave = lambda: NS(slice=NS(sliceIndex=0))
        rd.FileType = NS(PNG='PNG')
        controller.GetRootActions.return_value = [NS(eventId=9, flags=4, copyDestination='ResourceId::99', children=[])]
        controller.SaveTexture.return_value = 'failure'
        with tempfile.TemporaryDirectory() as directory:
            with self.assertRaises(RuntimeError):
                inventory.save_present_preview(rd, controller, Path(directory))

    def test_no_present_event_is_explicit(self):
        rd, _, controller = self.fake_runtime()
        rd.ActionFlags.Present = 4
        with tempfile.TemporaryDirectory() as directory:
            self.assertIsNone(inventory.save_present_preview(rd, controller, Path(directory)))

    def test_draw_details_deduplicate_shaders_and_use_constant_block_index(self):
        rd, _, controller = self.fake_runtime()
        with tempfile.TemporaryDirectory() as directory:
            result = inventory.collect_draw_details(rd, controller, Path(directory))
            self.assertEqual(len(result['shaders']), 1)
            self.assertEqual(len(result['draws_and_dispatches']), 3)
            self.assertTrue((Path(directory) / 'shader-22.spv').is_file())
        # fixedBindNumber=17 must NOT be passed as the reflection index.
        self.assertTrue(all(call.args[4] == 0 for call in controller.GetCBufferVariableContents.call_args_list))

    def test_full_run_writes_completion_and_releases_resources(self):
        rd, cap, controller = self.fake_runtime()
        with tempfile.TemporaryDirectory() as directory:
            capture = Path(directory) / 'frame.rdc'
            capture.touch()
            output = Path(directory) / 'output'
            with patch.dict('os.environ', {'ENDFIELD_CAPTURE_PATH': str(capture),
                    'ENDFIELD_CAPTURE_OUTPUT': str(output), 'ENDFIELD_CAPTURE_DETAILS': '1'}), \
                    patch.dict(sys.modules, {'renderdoc': rd}):
                inventory.run()
            self.assertEqual(json.loads((output / 'complete.json').read_text())['status'], 'ok')
            self.assertTrue((output / 'draw-details.json').is_file())
        cap.Shutdown.assert_called_once()
        controller.Shutdown.assert_called_once()

    def test_full_run_failure_records_error_without_false_completion(self):
        rd, cap, controller = self.fake_runtime()
        controller.GetRootActions.side_effect = RuntimeError('bad capture')
        with tempfile.TemporaryDirectory() as directory:
            capture = Path(directory) / 'frame.rdc'
            capture.touch()
            output = Path(directory) / 'output'
            with patch.dict('os.environ', {'ENDFIELD_CAPTURE_PATH': str(capture),
                    'ENDFIELD_CAPTURE_OUTPUT': str(output)}), patch.dict(sys.modules, {'renderdoc': rd}):
                with self.assertRaises(RuntimeError):
                    inventory.run()
            self.assertFalse((output / 'complete.json').exists())
            self.assertIn('bad capture', (output / 'error.json').read_text())
        cap.Shutdown.assert_called_once()
        controller.Shutdown.assert_called_once()

    def test_flatten_keeps_parent_before_children(self):
        leaf = NS(eventId=2, children=[])
        root = NS(eventId=1, children=[leaf])
        self.assertEqual(list(inventory.flatten_actions([root])), [root, leaf])

    def test_empty_actions(self):
        self.assertEqual(list(inventory.flatten_actions([])), [])

    def test_resource_ids_remain_strings(self):
        self.assertEqual(inventory.resource_id('ResourceId::710'), 'ResourceId::710')

    def test_existing_output_is_not_overwritten(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'report.json'
            inventory.write_new_json(path, {'ok': True})
            with self.assertRaises(FileExistsError):
                inventory.write_new_json(path, {})

    def test_json_export_uses_compact_round_trippable_encoding(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'report.json'
            value = {'values': [1.25, -2, '材质']}
            inventory.write_new_json(path, value)
            text = path.read_text(encoding='utf-8')
            self.assertEqual(json.loads(text), value)
            self.assertEqual(len(text.splitlines()), 1)

    def test_configuration_requires_existing_capture(self):
        with tempfile.TemporaryDirectory() as directory:
            with self.assertRaises(FileNotFoundError):
                inventory.validate_paths(Path(directory) / 'missing.rdc', Path(directory) / 'out')

    def test_configuration_rejects_non_rdc(self):
        with tempfile.TemporaryDirectory() as directory:
            capture = Path(directory) / 'capture.zip'
            capture.touch()
            with self.assertRaises(ValueError):
                inventory.validate_paths(capture, Path(directory) / 'out')

    def test_configuration_accepts_new_output(self):
        with tempfile.TemporaryDirectory() as directory:
            capture = Path(directory) / 'capture.rdc'
            capture.touch()
            output = Path(directory) / 'out'
            inventory.validate_paths(capture, output)
            self.assertTrue(output.is_dir())

    def test_action_record_contains_flags_and_count_not_callstack(self):
        action = NS(eventId=12, actionId=3, flags=5, numIndices=42,
                    numInstances=1, baseVertex=-2, indexOffset=7, vertexOffset=0,
                    instanceOffset=0, children=[], GetName=lambda _: 'draw')
        result = inventory.action_record(action, None)
        self.assertEqual(result['index_count'], 42)
        self.assertEqual(result['base_vertex'], -2)
        self.assertNotIn('callstack', result)

    def test_open_failure_shutdowns_capture(self):
        cap = Mock()
        cap.OpenFile.return_value = 'failed'
        rd = NS(OpenCaptureFile=lambda: cap, ResultCode=NS(Succeeded='ok'))
        with self.assertRaises(RuntimeError):
            inventory.open_controller(rd, Path('capture.rdc'))
        cap.Shutdown.assert_called_once()

    def test_replay_failure_shutdowns_capture(self):
        cap = Mock()
        cap.OpenFile.return_value = 'ok'
        cap.OpenCapture.return_value = ('unsupported', None)
        rd = NS(OpenCaptureFile=lambda: cap, ResultCode=NS(Succeeded='ok'),
                ReplayOptions=lambda: None)
        with self.assertRaises(RuntimeError):
            inventory.open_controller(rd, Path('capture.rdc'))
        cap.Shutdown.assert_called_once()

    def test_success_returns_live_objects(self):
        cap, controller = Mock(), Mock()
        cap.OpenFile.return_value = 'ok'
        cap.OpenCapture.return_value = ('ok', controller)
        rd = NS(OpenCaptureFile=lambda: cap, ResultCode=NS(Succeeded='ok'),
                ReplayOptions=lambda: None)
        self.assertEqual(inventory.open_controller(rd, Path('capture.rdc')), (cap, controller))
        cap.Shutdown.assert_not_called()

    def test_shader_variable_preserves_float_precision(self):
        value = NS(name='light', type='Float', rows=1, columns=2, members=[],
                   value=NS(f32v=[0.123456789, -2.0]))
        self.assertEqual(inventory.shader_variable(value)['value'], [0.123456789, -2.0])

    def test_shader_variable_handles_unsigned_and_nested_data(self):
        value = NS(name='flags', type='UInt', rows=1, columns=1, members=[],
                   value=NS(u32v=[4294967295]))
        parent = NS(name='block', type='Struct', rows=0, columns=0, members=[value])
        self.assertEqual(inventory.shader_variable(parent)['members'][0]['value'], [4294967295])

    def test_shader_variable_rejects_unsupported_scalar_type(self):
        value = NS(name='unknown', type='Resource', rows=1, columns=1, members=[], value=NS())
        with self.assertRaises(ValueError):
            inventory.shader_variable(value)

    def test_renderdoc_sint_enum_uses_signed_values(self):
        value = NS(name='mode', type='SInt', rows=1, columns=1, members=[],
                   value=NS(s32v=[-1]))
        self.assertEqual(inventory.shader_variable(value)['value'], [-1])

    def test_descriptor_record_preserves_actual_reflection_index(self):
        binding = NS(access=NS(index=2, arrayElement=0),
                     descriptor=NS(resource='ResourceId::99', byteOffset=128, byteSize=64))
        reflection = [NS(name='a'), NS(name='b'), NS(name='wanted', fixedBindNumber=17, fixedBindSetOrSpace=3)]
        result = inventory.descriptor_record(binding, reflection)
        self.assertEqual(result['name'], 'wanted')
        self.assertEqual(result['reflection_index'], 2)
        self.assertEqual(result['binding'], 17)
        self.assertEqual(result['offset'], 128)

    def test_descriptor_unknown_binding_does_not_index_out_of_range(self):
        binding = NS(access=NS(index=4294967295, arrayElement=3),
                     descriptor=NS(resource='ResourceId::99', byteOffset=0, byteSize=4))
        self.assertEqual(inventory.descriptor_record(binding, [])['name'], '')


if __name__ == '__main__':
    unittest.main()
