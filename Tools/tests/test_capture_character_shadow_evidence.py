import json
import sys
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace as NS
from unittest.mock import Mock, patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import capture_character_shadow_evidence as evidence


# Real reflection layout of the frame-6411 shadow cbuffer (uniforms21, 11440 bytes),
# taken from Validation/Captures/.../replay-details-01/draw-details.json event 748.
# Names are stripped to _childN by SPIR-V reflection, so only this shape table and
# the byte offsets identify anything. (child count, element bytes)
CHILD_SHAPES = [
    (5, 64), (4, 16), (4, 16), (4, 16),
    (1, 16), (1, 16), (1, 16), (1, 16), (1, 16),
    (27, 16), (56, 64), (56, 16), (56, 16), (1, 16), (47, 16),
    (15, 64), (15, 16), (15, 16), (15, 16), (1, 16), (1, 16),
    (21, 16), (1, 64), (1, 64),
    (1, 16), (1, 16), (1, 16),
    (128, 16),
]
W2S_ROW0 = [0.825103, -0.053014, 0.088867, 0.0]
BIASES0 = [0.00347, 0.00695, 0.00116, 256.0]
LIGHT_DIR = [-0.17632, -0.52992, -0.82952, 0.0]
ATLAS0 = [0.75, 0.0, 0.25, 0.5]
TEXEL_SIZE = [0.000244140625, 0.00048828125, 4096.0, 2048.0]
SHADOW_PARAMS = [1.0, 1.0, 7.0, 0.0]

# The resolve also needs the view transform and the screen size, which live in two
# other cbuffers. Descriptor binding numbers drift between events (the same block is
# binding 13 at event 748 and 12 at 744), so only byte size can identify a block.
INV_VIEW_PROJ = [float(i + 1) / 16.0 for i in range(16)]
CAMERA_POS = [1.5, 2.5, 3.5, 1.0]
SCREEN_SIZE = [2560.0, 1600.0, 1.0 / 2560.0, 1.0 / 1600.0]

# (count, element bytes, value) tiling to the real block sizes. Runs we never read
# are collapsed into one oversized leaf so the fixture stays cheap; variable_bytes
# still accounts for every byte, which is what offset resolution depends on.
TRANSFORM_SPEC = [(1, 384, None), (1, 64, INV_VIEW_PROJ), (1, 256, None),
                  (1, 16, CAMERA_POS), (1, 592, None)]
GLOBAL_SPEC = [(1, 16, SCREEN_SIZE), (1, 3184, None)]
LIGHT_SPEC = [(1, 32864, None)]

# reflection_index -> (name, size), as observed at event 748. Binding numbers are
# deliberately not part of the contract because they drift between events.
BLOCKS = [('uniforms6', 1312), ('uniforms17', 32864), ('uniforms21', 11440), ('uniforms8', 3200)]


def variable(count, element, value=None):
    """Build one reflection child. `element` is bytes per array entry (16 or 64)."""
    rows = element // 16
    columns = 4
    leaf_value = NS(f32v=list(value) if value else [0.0] * (rows * columns))
    if count == 1:
        return NS(name='_childN', type='VarType.Float', rows=rows, columns=columns,
                  members=[], value=leaf_value)
    return NS(name='_childN', type='VarType.Float', rows=0, columns=0, value=None,
              members=[NS(name='[{}]'.format(i), type='VarType.Float', rows=rows,
                          columns=columns, members=[], value=NS(f32v=list(leaf_value.f32v)))
                       for i in range(count)])


def shadow_block(children=None, size=11440, name='uniforms21'):
    if children is None:
        children = []
        for index, (count, element) in enumerate(CHILD_SHAPES):
            value = None
            if index == 15:
                value = W2S_ROW0 * 4
            elif index == 16:
                value = BIASES0
            elif index == 17:
                value = LIGHT_DIR
            elif index == 18:
                value = ATLAS0
            elif index == 19:
                value = TEXEL_SIZE
            elif index == 20:
                value = SHADOW_PARAMS
            child = variable(count, element, value)
            child.name = '_child{}'.format(index)
            children.append(child)
    return dict(name=name, reflection_index=3, binding=13, set=3,
                resource='ResourceId::864', offset=610944, size=size,
                variables=children)


class ConstantLayoutTests(unittest.TestCase):
    def test_plan_offsets_are_the_documented_packoffsets(self):
        by_name = {row['name']: row for row in evidence.CONSTANT_PLAN}
        expected = {'characterWorldToShadow': (448, 15, 4),
                    'characterShadowBiases': (508, 15, 4),
                    'characterShadowLightDir': (523, 15, 4),
                    'characterShadowAtlasParams': (538, 15, 4),
                    'characterShadowTexelSize': (553, 1, 4),
                    'characterShadowParams': (554, 1, 4)}
        self.assertEqual(set(by_name), set(expected))
        for name, (register, count, columns) in expected.items():
            row = by_name[name]
            self.assertEqual(row['offset'], register * 16, name)
            self.assertEqual(row['count'], count, name)
            self.assertEqual(row['columns'], columns, name)

    def test_shapes_sum_to_the_real_cbuffer_size(self):
        total = sum(count * element for count, element in CHILD_SHAPES)
        self.assertEqual(total, evidence.SHADOW_CBUFFER_BYTES)
        self.assertEqual(total, 11440)

    def test_plan_is_tight_against_the_real_layout(self):
        """Offsets must tile the real reflection layout, proving they are enforced."""
        offsets = []
        cursor = 0
        for count, element in CHILD_SHAPES:
            offsets.append(cursor)
            cursor += count * element
        by_offset = {row['offset']: row for row in evidence.CONSTANT_PLAN}
        for index in (15, 16, 17, 18, 19, 20):
            self.assertIn(offsets[index], by_offset,
                          'child{} at byte {} is not in the plan'.format(index, offsets[index]))

    def test_selects_the_shadow_cbuffer_by_size_not_by_name(self):
        blocks = [dict(name='uniforms6', size=1312, variables=[]),
                  dict(name='uniforms17', size=32864, variables=[]),
                  shadow_block(name='someOtherName'),
                  dict(name='uniforms8', size=3200, variables=[])]
        self.assertEqual(evidence.shadow_block(blocks)['size'], 11440)
        self.assertEqual(evidence.shadow_block(blocks)['name'], 'someOtherName')

    def test_rejects_absent_shadow_cbuffer(self):
        with self.assertRaises(ValueError):
            evidence.shadow_block([dict(name='uniforms6', size=1312, variables=[])])

    def test_rejects_ambiguous_shadow_cbuffer(self):
        with self.assertRaises(ValueError):
            evidence.shadow_block([shadow_block(), shadow_block(name='uniforms22')])


class ConstantExtractionTests(unittest.TestCase):
    def test_extracts_the_real_frame_6411_character_values(self):
        rows = evidence.select_constants(shadow_block())
        self.assertEqual(rows['characterShadowParams'], [SHADOW_PARAMS])
        self.assertEqual(rows['characterShadowTexelSize'], [TEXEL_SIZE])
        self.assertEqual(len(rows['characterWorldToShadow']), 15)
        self.assertEqual(rows['characterWorldToShadow'][0], W2S_ROW0 * 4)
        self.assertEqual(rows['characterShadowBiases'][0], BIASES0)
        self.assertEqual(rows['characterShadowLightDir'][0], LIGHT_DIR)
        self.assertEqual(rows['characterShadowAtlasParams'][0], ATLAS0)
        self.assertEqual(len(rows['characterShadowParams'][0]), 4)

    def test_rejects_layout_drift_instead_of_returning_wrong_data(self):
        """A preceding child changing size shifts every offset; that must fail loudly."""
        shapes = list(CHILD_SHAPES)
        shapes[14] = (48, 16)  # was (47, 16): pushes child15 off c448
        drifted_children = []
        for index, (count, element) in enumerate(shapes):
            child = variable(count, element, SHADOW_PARAMS if index == 20 else None)
            child.name = '_child{}'.format(index)
            drifted_children.append(child)
        drifted = shadow_block(children=drifted_children, size=sum(c * e for c, e in shapes))
        with self.assertRaises(ValueError):
            evidence.select_constants(drifted)

    def test_rejects_wrong_shape_at_the_expected_offset(self):
        children = []
        for index, (count, element) in enumerate(CHILD_SHAPES):
            child = variable(14 if index == 15 else count, element)
            child.name = '_child{}'.format(index)
            children.append(child)
        with self.assertRaises(ValueError):
            evidence.select_constants(shadow_block(children=children))

    def test_rejects_non_numeric_constant(self):
        block = shadow_block()
        block['variables'][20].value = None
        block['variables'][20].members = []
        block['variables'][20].rows = 0
        block['variables'][20].columns = 0
        with self.assertRaises(ValueError):
            evidence.select_constants(block)


def spec_variables(spec):
    children = []
    for count, element, value in spec:
        child = variable(count, element, value)
        child.name = '_child{}'.format(len(children))
        children.append(child)
    return children


def all_block_variables():
    """Reflection variables per block index at event 748: transform, light, shadow, global."""
    return [spec_variables(TRANSFORM_SPEC), spec_variables(LIGHT_SPEC),
            shadow_block()['variables'], spec_variables(GLOBAL_SPEC)]


def runtime(bindings=None, output_target='ResourceId::58932', frame=6411):
    controller, capture, state = Mock(), Mock(), Mock()
    if bindings is None:
        bindings = [(4, 58994), (5, 58985), (6, 156), (7, 32538), (8, 59000), (9, 1463), (10, 1463)]
    state.GetReadOnlyResources.return_value = [
        NS(access=NS(index=index, arrayElement=0, descriptorStore='ResourceId::864', byteOffset=0,
                     byteSize=0, stage='Pixel', type='ReadOnlyResource', staticallyUnused=False),
           descriptor=NS(resource='ResourceId::{}'.format(resource), byteOffset=5, byteSize=0))
        for index, (_, resource) in enumerate(bindings)]
    state.GetOutputTargets.return_value = [NS(resource=output_target), NS(resource='ResourceId::0')]
    state.GetDepthTarget.return_value = NS(resource='ResourceId::58980')
    state.GetShaderReflection.return_value = NS(
        readOnlyResources=[NS(name='res{}'.format(binding), fixedBindNumber=binding, fixedBindSetOrSpace=3)
                           for binding, _ in bindings],
        constantBlocks=[NS(name=name, fixedBindNumber=11 + index, fixedBindSetOrSpace=3)
                        for index, (name, _) in enumerate(BLOCKS)],
        entryPoint='main', rawBytes=b'')
    state.GetConstantBlock.side_effect = lambda stage, index, array: NS(
        descriptor=NS(resource='ResourceId::864', byteOffset=500000 + index * 1000,
                      byteSize=BLOCKS[index][1]))
    controller.GetPipelineState.return_value = state
    controller.GetFrameInfo.return_value = NS(frameNumber=frame)
    controller.GetTextures.return_value = [
        NS(resourceId='ResourceId::{}'.format(row['id']), width=row['width'], height=row['height'],
           arraysize=row['slices'], mips=row['mips'], format=NS(Name=lambda row=row: row['format']))
        for row in evidence.TEXTURE_PLAN]
    blocks = all_block_variables()
    # Signature: (pipeline, shader, stage, entryPoint, blockIndex, resource, offset, size)
    controller.GetCBufferVariableContents.side_effect = lambda *args: blocks[args[4]]
    events = []
    controller.SetFrameEvent.side_effect = lambda event, force: events.append(event)
    rd = NS(ShaderStage=NS(Pixel='ShaderStage.Pixel', Vertex='ShaderStage.Vertex'),
            ResultCode=NS(Succeeded='Succeeded'), FileType=NS(DDS='DDS', EXR='EXR'),
            TextureSave=Mock, ActionFlags=NS(Drawcall=1))
    return rd, capture, controller, state, events


class BindingContractTests(unittest.TestCase):
    def test_registers_map_to_the_expected_capture_resources(self):
        rd, _, _, state, _ = runtime()
        rows = evidence.validate_bindings(rd, state)
        resolved = {row['binding']: row['resource'] for row in rows}
        self.assertEqual(resolved[7], 'ResourceId::32538')
        self.assertEqual(resolved[5], 'ResourceId::58985')
        self.assertEqual(resolved[4], 'ResourceId::58994')
        self.assertEqual(resolved[8], 'ResourceId::59000')

    def test_rejects_atlas_bound_to_the_wrong_register(self):
        rd, _, _, state, _ = runtime(bindings=[(4, 58994), (5, 58985), (6, 156),
                                               (7, 99999), (8, 59000)])
        with self.assertRaises(ValueError):
            evidence.validate_bindings(rd, state)

    def test_rejects_missing_required_binding(self):
        rd, _, _, state, _ = runtime(bindings=[(4, 58994), (5, 58985), (8, 59000)])
        with self.assertRaises(ValueError):
            evidence.validate_bindings(rd, state)

    def test_rejects_wrong_render_target(self):
        rd, _, _, state, _ = runtime(output_target='ResourceId::99999')
        with self.assertRaises(ValueError):
            evidence.validate_output_target(rd, state)

    def test_accepts_the_real_render_target(self):
        rd, _, _, state, _ = runtime()
        self.assertEqual(evidence.validate_output_target(rd, state), 'ResourceId::58932')


class RunTests(unittest.TestCase):
    def run_mock(self, constants_only=True, frame=6411, mutate=None):
        rd, cap, controller, state, events = runtime(frame=frame)
        if mutate:
            mutate(rd, cap, controller, state)
        with tempfile.TemporaryDirectory() as directory:
            capture = Path(directory) / 'frame.rdc'
            capture.touch()
            output = Path(directory) / 'output'
            env = {'ENDFIELD_CAPTURE_PATH': str(capture), 'ENDFIELD_CAPTURE_OUTPUT': str(output),
                   'ENDFIELD_SHADOW_CONSTANTS_ONLY': '1' if constants_only else '0'}
            with patch.dict('os.environ', env), patch.dict(sys.modules, {'renderdoc': rd}), \
                    patch.object(evidence, 'open_controller', return_value=(cap, controller)), \
                    patch.object(evidence, 'save_texture', return_value={'file': 'x'}) as save:
                error = None
                try:
                    evidence.run()
                except Exception as exc:
                    error = exc
                manifest = json.loads((output / 'complete.json').read_text()) if (output / 'complete.json').exists() else None
                record = json.loads((output / 'error.json').read_text()) if (output / 'error.json').exists() else None
            return cap, controller, save, manifest, record, error, events

    def test_constants_only_still_verifies_every_contract(self):
        cap, controller, save, manifest, _, error, events = self.run_mock()
        self.assertIsNone(error)
        self.assertEqual(manifest['status'], 'ok')
        self.assertEqual(manifest['frame'], 6411)
        self.assertEqual(manifest['event'], 748)
        self.assertEqual(manifest['constants']['characterShadowParams'], [SHADOW_PARAMS])
        self.assertEqual(len(manifest['textures']), len(evidence.TEXTURE_PLAN))
        save.assert_not_called()
        self.assertEqual(events, [748])
        cap.Shutdown.assert_called_once()
        controller.Shutdown.assert_called_once()

    def test_full_mode_saves_dds_and_exr_for_every_texture(self):
        _, _, save, manifest, _, error, _ = self.run_mock(constants_only=False)
        self.assertIsNone(error)
        self.assertEqual(save.call_count, 2 * len(evidence.TEXTURE_PLAN))
        self.assertTrue(all(row['files'] for row in manifest['textures']))

    def test_wrong_frame_fails_before_any_export(self):
        cap, controller, save, manifest, record, error, _ = self.run_mock(frame=12)
        self.assertIsInstance(error, ValueError)
        self.assertIsNone(manifest)
        self.assertIn('6411', record['traceback'])
        save.assert_not_called()
        cap.Shutdown.assert_called_once()
        controller.Shutdown.assert_called_once()

    def test_texture_contract_mismatch_never_reports_success(self):
        def mutate(rd, cap, controller, state):
            controller.GetTextures.return_value[0].width = 2048
        _, _, save, manifest, record, error, _ = self.run_mock(constants_only=False, mutate=mutate)
        self.assertIsInstance(error, ValueError)
        self.assertIsNone(manifest)
        self.assertIn('contract', record['traceback'])
        save.assert_not_called()

    def test_layout_drift_never_reports_success(self):
        def mutate(rd, cap, controller, state):
            shapes = list(CHILD_SHAPES)
            shapes[14] = (48, 16)
            drifted = all_block_variables()
            drifted[2] = [variable(count, element) for count, element in shapes]
            controller.GetCBufferVariableContents.side_effect = lambda *args: drifted[args[4]]
        _, _, save, manifest, record, error, _ = self.run_mock(mutate=mutate)
        self.assertIsInstance(error, ValueError)
        self.assertIsNone(manifest)
        save.assert_not_called()

    def test_capture_releases_even_if_controller_shutdown_raises(self):
        def mutate(rd, cap, controller, state):
            controller.Shutdown.side_effect = RuntimeError('shutdown failed')
        cap, controller, _, manifest, record, error, _ = self.run_mock(mutate=mutate)
        self.assertIsInstance(error, RuntimeError)
        self.assertIsNone(manifest)
        self.assertIn('shutdown failed', record['traceback'])
        cap.Shutdown.assert_called_once()

    def test_existing_output_is_refused_before_open(self):
        with tempfile.TemporaryDirectory() as directory:
            capture = Path(directory) / 'frame.rdc'
            capture.touch()
            output = Path(directory) / 'output'
            output.mkdir()
            (output / 'keep').touch()
            with patch.dict('os.environ', {'ENDFIELD_CAPTURE_PATH': str(capture),
                                           'ENDFIELD_CAPTURE_OUTPUT': str(output)}), \
                    patch.object(evidence, 'open_controller') as opening:
                with self.assertRaises(FileExistsError):
                    evidence.run()
                opening.assert_not_called()


class TransformCbufferTests(unittest.TestCase):
    def test_plans_use_the_declared_packoffsets(self):
        transform = {row['name']: row for row in evidence.TRANSFORM_PLAN}
        self.assertEqual(transform['invViewProjMatrix']['offset'], 24 * 16)
        self.assertEqual(transform['invViewProjMatrix']['rows'], 4)
        self.assertEqual(transform['invViewProjMatrix']['columns'], 4)
        self.assertEqual(transform['worldSpaceCameraPos']['offset'], 44 * 16)
        global_plan = {row['name']: row for row in evidence.GLOBAL_PLAN}
        self.assertEqual(global_plan['screenSize']['offset'], 0)

    def test_fixtures_tile_to_the_real_block_sizes(self):
        for spec, size in ((TRANSFORM_SPEC, evidence.TRANSFORM_CBUFFER_BYTES),
                           (GLOBAL_SPEC, evidence.GLOBAL_CBUFFER_BYTES),
                           (LIGHT_SPEC, 32864)):
            self.assertEqual(sum(count * element for count, element, _ in spec), size)

    def test_locates_each_cbuffer_by_size_among_the_four_real_blocks(self):
        blocks = [dict(name=name, size=size, variables=[]) for name, size in BLOCKS]
        self.assertEqual(evidence.shadow_block(blocks)['name'], 'uniforms21')
        self.assertEqual(evidence.block_by_size(blocks, evidence.TRANSFORM_CBUFFER_BYTES, 'transform')['name'], 'uniforms6')
        self.assertEqual(evidence.block_by_size(blocks, evidence.GLOBAL_CBUFFER_BYTES, 'global')['name'], 'uniforms8')

    def test_rejects_absent_transform_cbuffer(self):
        blocks = [dict(name='uniforms21', size=11440, variables=[])]
        with self.assertRaises(ValueError):
            evidence.block_by_size(blocks, evidence.TRANSFORM_CBUFFER_BYTES, 'transform')

    def test_extracts_inv_view_proj_and_camera_position_by_offset(self):
        block = dict(name='uniforms6', size=1312, variables=spec_variables(TRANSFORM_SPEC))
        rows = evidence.select_fields(block, evidence.TRANSFORM_PLAN, 'transform')
        self.assertEqual(rows['invViewProjMatrix'], [INV_VIEW_PROJ])
        self.assertEqual(rows['worldSpaceCameraPos'], [CAMERA_POS])

    def test_screen_size_contract_cross_validates_the_block_mapping(self):
        """ScreenSize must agree with the render target, proving the offsets are right."""
        evidence.validate_screen_size(SCREEN_SIZE, 2560, 1600)
        for bad in ([1600.0, 2560.0, 1.0 / 1600.0, 1.0 / 2560.0],
                    [1280.0, 800.0, 1.0 / 1280.0, 1.0 / 800.0],
                    [0.0, 0.0, 0.0, 0.0]):
            with self.assertRaises(ValueError):
                evidence.validate_screen_size(bad, 2560, 1600)

    def test_screen_size_reciprocals_must_match_its_dimensions(self):
        with self.assertRaises(ValueError):
            evidence.validate_screen_size([2560.0, 1600.0, 0.5, 0.5], 2560, 1600)


class TransformRunTests(unittest.TestCase):
    run_mock = RunTests.run_mock

    def test_manifest_carries_transform_and_global_constants(self):
        _, _, _, manifest, _, error, _ = self.run_mock()
        self.assertIsNone(error)
        self.assertEqual(manifest['transform']['invViewProjMatrix'], [INV_VIEW_PROJ])
        self.assertEqual(manifest['transform']['worldSpaceCameraPos'], [CAMERA_POS])
        self.assertEqual(manifest['global']['screenSize'], [SCREEN_SIZE])

    def test_screen_size_disagreeing_with_the_target_fails_the_export(self):
        def mutate(rd, cap, controller, state):
            blocks = all_block_variables()
            blocks[3] = spec_variables([(1, 16, [1280.0, 800.0, 1.0 / 1280.0, 1.0 / 800.0]),
                                        (1, 3184, None)])
            controller.GetCBufferVariableContents.side_effect = lambda *args: blocks[args[4]]
        _, _, save, manifest, record, error, _ = self.run_mock(mutate=mutate)
        self.assertIsInstance(error, ValueError)
        self.assertIsNone(manifest)
        self.assertIn('ScreenSize', record['traceback'])
        save.assert_not_called()

    def test_missing_transform_cbuffer_fails_the_export(self):
        def mutate(rd, cap, controller, state):
            original = state.GetConstantBlock.side_effect

            def patched(stage, index, array):
                block = original(stage, index, array)
                if index == 0:
                    block.descriptor.byteSize = 999999
                return block
            state.GetConstantBlock.side_effect = patched
        _, _, save, manifest, record, error, _ = self.run_mock(mutate=mutate)
        self.assertIsInstance(error, ValueError)
        self.assertIsNone(manifest)
        self.assertIn('transform', record['traceback'])
        save.assert_not_called()


if __name__ == '__main__':
    unittest.main()
