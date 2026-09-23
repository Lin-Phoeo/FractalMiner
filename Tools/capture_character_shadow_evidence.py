"""Offline frame-6411 character self-shadow evidence export.

Targets event 748 (ScreenSpaceShadowResolve_Character), the pass that writes the
G channel of the R8G8 screen-shadow target. R is the directional term and is
constant-shortcut in this frame; G is the character self-shadow still missing from
EndfieldCharacterLit.shader, which hardcodes selfShadow=1.

SPIR-V reflection strips every constant name to _childN, so the cbuffer is located
by its byte size and each field by its packoffset. Both were cross-checked against
the decompiled official shader:
  _dump_1.5.3/AllShader_1.5.3/Assets/packages/com.hg.render-pipelines/
  runtime/shaders/lighting/shadow/screenspaceshadowresolve.shader
The layout tiles to exactly 11440 bytes and reproduces _CharacterShadowParams
(1,1,7,0) and _CharacterShadowTexelSize (1/4096,1/2048,4096,2048).

Use official RenderDoc 1.46 qrenderdoc --python and a fresh output directory.
ENDFIELD_CAPTURE_PATH / ENDFIELD_CAPTURE_OUTPUT / ENDFIELD_TOOLS_PATH have the same
meaning as capture_pipeline_export.py. ENDFIELD_SHADOW_CONSTANTS_ONLY=1 skips all
texture saves but still verifies the frame, binding, target, texture and cbuffer
contracts. No injection or live game access. complete.json, not the native exit
status, is the success signal.
"""
import os
from pathlib import Path
import sys
import traceback

sys.path.insert(0, os.environ.get('ENDFIELD_TOOLS_PATH') or str(Path(__file__).resolve().parent))
from capture_replay_inventory import open_controller, resource_id, validate_paths, write_new_json
from capture_pipeline_export import save_texture, validate_texture

FRAME = 6411
RESOLVE_EVENT = 748
DIRECTIONAL_EVENT = 744
OUTPUT_TARGET_ID = 58932
SHADOW_CBUFFER_BYTES = 11440
TRANSFORM_CBUFFER_BYTES = 1312
GLOBAL_CBUFFER_BYTES = 3200

# packoffset register * 16 = byte offset. Counts and shapes come from the official
# declaration; a drift in any preceding field shifts these and must fail loudly.
CONSTANT_PLAN = (
    dict(name='characterWorldToShadow', register=448, offset=448 * 16, count=15, rows=4, columns=4),
    dict(name='characterShadowBiases', register=508, offset=508 * 16, count=15, rows=1, columns=4),
    dict(name='characterShadowLightDir', register=523, offset=523 * 16, count=15, rows=1, columns=4),
    dict(name='characterShadowAtlasParams', register=538, offset=538 * 16, count=15, rows=1, columns=4),
    dict(name='characterShadowTexelSize', register=553, offset=553 * 16, count=1, rows=1, columns=4),
    dict(name='characterShadowParams', register=554, offset=554 * 16, count=1, rows=1, columns=4),
)

# type_TransformVariables, declared as register(b11, space3). Needed to rebuild world
# positions from the depth buffer, which the resolve does before any shadow lookup.
TRANSFORM_PLAN = (
    dict(name='invViewProjMatrix', register=24, offset=24 * 16, count=1, rows=4, columns=4),
    dict(name='worldSpaceCameraPos', register=44, offset=44 * 16, count=1, rows=1, columns=4),
)

# type_ShaderVariablesGlobal, declared as register(b14, space3). The official pass
# multiplies pixel coordinates by _ScreenSize.zw, so zw must be the reciprocals of xy.
GLOBAL_PLAN = (
    dict(name='screenSize', register=0, offset=0, count=1, rows=1, columns=4),
)

# register(tN, space3) -> capture resource, per the decompiled pass declaration.
BINDING_PLAN = (
    dict(binding=4, id=58994, name='gbuffer1-normal'),
    dict(binding=5, id=58985, name='gbuffer0-character-index'),
    dict(binding=7, id=32538, name='character-shadow-atlas'),
    dict(binding=8, id=59000, name='camera-depth'),
)

TEXTURE_PLAN = [
    dict(id=32538, event=RESOLVE_EVENT, name='character-shadow-atlas',
         width=4096, height=2048, slices=1, mips=1, format='D16'),
    dict(id=58985, event=RESOLVE_EVENT, name='gbuffer0-character-index',
         width=2560, height=1600, slices=1, mips=1, format='R10G10B10A2_UNORM'),
    dict(id=58994, event=RESOLVE_EVENT, name='gbuffer1-normal',
         width=2560, height=1600, slices=1, mips=1, format='R10G10B10A2_UNORM'),
    dict(id=59000, event=RESOLVE_EVENT, name='camera-depth',
         width=2560, height=1600, slices=1, mips=1, format='R32_FLOAT'),
    dict(id=58932, event=RESOLVE_EVENT, name='screen-shadow-resolved',
         width=2560, height=1600, slices=1, mips=1, format='R8G8_UNORM'),
]


def variable_bytes(variable):
    if getattr(variable, 'members', None):
        return sum(variable_bytes(member) for member in variable.members)
    return variable.rows * variable.columns * 4


def child_offsets(variables):
    cursor = 0
    for variable in variables:
        yield cursor, variable
        cursor += variable_bytes(variable)


def block_by_size(blocks, size, label):
    """Identify a cbuffer by byte size only: descriptor binding numbers drift between
    events (the shadow block is binding 13 at event 748 and 12 at 744) and reflection
    names are stripped, so size is the only stable handle."""
    matches = [block for block in blocks if block['size'] == size]
    if not matches:
        raise ValueError('No {} constant block of {} bytes at the resolve event; found {}'.format(
            label, size, [(b['name'], b['size']) for b in blocks]))
    if len(matches) != 1:
        raise ValueError('Ambiguous {} cbuffer: {} blocks of {} bytes'.format(
            label, len(matches), size))
    return matches[0]


def shadow_block(blocks):
    return block_by_size(blocks, SHADOW_CBUFFER_BYTES, 'shadow')


def leaf_values(variable, plan):
    if variable.members:
        raise ValueError('{}: expected a scalar/float4 at c{}, got a nested aggregate'.format(
            plan['name'], plan['register']))
    if (variable.rows, variable.columns) != (plan['rows'], plan['columns']):
        raise ValueError('{}: expected {}x{} at c{}, got {}x{}'.format(
            plan['name'], plan['rows'], plan['columns'], plan['register'],
            variable.rows, variable.columns))
    value = getattr(variable, 'value', None)
    if value is None:
        raise ValueError('{}: reflection returned no value at c{}'.format(plan['name'], plan['register']))
    return list(value.f32v)[:plan['rows'] * plan['columns']]


def select_fields(block, plan_rows, label):
    """Read fields by byte offset, never by stripped name or drifting binding number."""
    at_offset = {}
    for offset, variable in child_offsets(block['variables']):
        at_offset.setdefault(offset, variable)
    result = {}
    for plan in plan_rows:
        variable = at_offset.get(plan['offset'])
        if variable is None:
            raise ValueError('{}: no reflection variable starts at byte {} (c{}) in the {} cbuffer;'
                             ' the layout drifted, refusing to guess'.format(
                                 plan['name'], plan['offset'], plan['register'], label))
        if plan['count'] == 1:
            if variable.members:
                raise ValueError('{}: expected one float{}x{} at c{} in the {} cbuffer, got an array of {}'.format(
                    plan['name'], plan['rows'], plan['columns'], plan['register'], label,
                    len(variable.members)))
            result[plan['name']] = [leaf_values(variable, plan)]
            continue
        if len(variable.members) != plan['count']:
            raise ValueError('{}: expected {} entries at c{} in the {} cbuffer, got {}'.format(
                plan['name'], plan['count'], plan['register'], label, len(variable.members)))
        result[plan['name']] = [leaf_values(member, plan) for member in variable.members]
    return result


def select_constants(block):
    return select_fields(block, CONSTANT_PLAN, 'shadow')


def validate_screen_size(value, width, height):
    """Cross-validate the block mapping against an independent fact: the official pass
    computes UVs as pixel * _ScreenSize.zw, so zw must be the reciprocals of xy, and xy
    must be the resolve render target's real dimensions."""
    if len(value) != 4:
        raise ValueError('ScreenSize must have 4 components, got {}'.format(len(value)))
    if int(value[0]) != width or int(value[1]) != height:
        raise ValueError('ScreenSize xy {} does not match the resolve render target {}x{}'.format(
            [value[0], value[1]], width, height))
    for actual, expected, axis in zip(value[2:], (1.0 / width, 1.0 / height), 'zw'):
        if abs(actual - expected) > 1e-9:
            raise ValueError('ScreenSize.{} = {} is not 1/{} as the official resolve assumes;'
                             ' the cbuffer mapping is wrong'.format(axis, actual, expected))
    return list(value)


def pipeline_constant_blocks(rd, controller, state):
    reflection = state.GetShaderReflection(rd.ShaderStage.Pixel)
    if reflection is None:
        raise ValueError('No pixel shader reflection at the character shadow resolve event')
    pipeline = state.GetGraphicsPipelineObject()
    shader = state.GetShader(rd.ShaderStage.Pixel)
    blocks = []
    for index, block in enumerate(reflection.constantBlocks):
        used = state.GetConstantBlock(rd.ShaderStage.Pixel, index, 0)
        descriptor = used.descriptor
        values = controller.GetCBufferVariableContents(
            pipeline, shader, rd.ShaderStage.Pixel, reflection.entryPoint, index,
            descriptor.resource, descriptor.byteOffset, descriptor.byteSize)
        blocks.append(dict(name=block.name, reflection_index=index,
                           binding=block.fixedBindNumber, set=block.fixedBindSetOrSpace,
                           resource=resource_id(descriptor.resource),
                           offset=descriptor.byteOffset, size=descriptor.byteSize,
                           variables=list(values)))
    return blocks


def bound_resources(rd, state):
    reflection = state.GetShaderReflection(rd.ShaderStage.Pixel)
    if reflection is None:
        raise ValueError('No pixel shader reflection at the character shadow resolve event')
    table = reflection.readOnlyResources
    found = {}
    for used in state.GetReadOnlyResources(rd.ShaderStage.Pixel):
        index = used.access.index
        if not 0 <= index < len(table):
            continue
        found[table[index].fixedBindNumber] = resource_id(used.descriptor.resource)
    return found


def validate_bindings(rd, state):
    found = bound_resources(rd, state)
    rows = []
    for plan in BINDING_PLAN:
        expected = 'ResourceId::' + str(plan['id'])
        if plan['binding'] not in found:
            raise ValueError('Resolve event has no texture binding t{} for {} ({})'.format(
                plan['binding'], plan['name'], expected))
        actual = found[plan['binding']]
        if actual != expected:
            raise ValueError('Binding t{} holds {} but the character shadow contract requires {} ({})'.format(
                plan['binding'], actual, expected, plan['name']))
        rows.append(dict(binding=plan['binding'], name=plan['name'], resource=actual))
    return rows


def validate_output_target(rd, state):
    targets = state.GetOutputTargets()
    if not targets:
        raise ValueError('Character shadow resolve event has no render target')
    actual = resource_id(targets[0].resource)
    expected = 'ResourceId::' + str(OUTPUT_TARGET_ID)
    if actual != expected:
        raise ValueError('Character shadow resolve writes {} but the contract requires {}'
                         ' (screen shadow R8G8, G is the character term)'.format(actual, expected))
    return actual


def collect(rd, controller, output, constants_only):
    if controller.GetFrameInfo().frameNumber != FRAME:
        raise ValueError('This character shadow plan requires frame {}'.format(FRAME))
    controller.SetFrameEvent(RESOLVE_EVENT, True)
    state = controller.GetPipelineState()
    target = validate_output_target(rd, state)
    bindings = validate_bindings(rd, state)
    blocks = pipeline_constant_blocks(rd, controller, state)
    block = shadow_block(blocks)
    constants = select_constants(block)
    transform = select_fields(block_by_size(blocks, TRANSFORM_CBUFFER_BYTES, 'transform'),
                              TRANSFORM_PLAN, 'transform')
    constants_global = select_fields(block_by_size(blocks, GLOBAL_CBUFFER_BYTES, 'global'),
                                     GLOBAL_PLAN, 'global')

    textures = {resource_id(t.resourceId): t for t in controller.GetTextures()}
    target_texture = textures.get('ResourceId::' + str(OUTPUT_TARGET_ID))
    if target_texture is None:
        raise ValueError('Resolve render target texture is missing: ResourceId::' + str(OUTPUT_TARGET_ID))
    screen_size = validate_screen_size(constants_global['screenSize'][0],
                                       target_texture.width, target_texture.height)
    records = []
    for plan in TEXTURE_PLAN:
        key = 'ResourceId::' + str(plan['id'])
        if key not in textures:
            raise ValueError('Missing character shadow texture: ' + key)
        texture = textures[key]
        validate_texture(texture, plan)
        files = []
        if not constants_only:
            for kind in ('DDS', 'EXR'):
                files.append(save_texture(rd, controller, texture.resourceId,
                    output / (plan['name'] + '.' + kind.lower()), kind, kind == 'DDS'))
        record = dict(plan, files=files)
        records.append(record)
        write_new_json(output / ('texture-{}.json'.format(plan['name'])), record)

    write_new_json(output / 'constants.json', dict(
        event=RESOLVE_EVENT,
        cbuffer=dict(name=block['name'], resource=block['resource'],
                     offset=block['offset'], size=block['size']),
        constants=constants, transform=transform, global_constants=constants_global,
        screen_size=screen_size))
    result = dict(event=RESOLVE_EVENT, directional_event=DIRECTIONAL_EVENT,
                  output_target=target, cbuffer_size=block['size'],
                  bindings=bindings, constants=constants, transform=transform,
                  screen_size=screen_size, textures=records)
    result['global'] = constants_global
    return result


def run():
    output = Path(os.environ['ENDFIELD_CAPTURE_OUTPUT']).resolve()
    capture = Path(os.environ['ENDFIELD_CAPTURE_PATH']).resolve()
    validate_paths(capture, output)
    constants_only = os.environ.get('ENDFIELD_SHADOW_CONSTANTS_ONLY') == '1'
    mode = 'constants-only' if constants_only else 'textures-and-constants'
    write_new_json(output / 'started.json', dict(capture=str(capture), size=capture.stat().st_size,
        frame=FRAME, event=RESOLVE_EVENT, mode=mode))
    cap = controller = None
    try:
        try:
            import renderdoc as rd
            cap, controller = open_controller(rd, capture)
            result = collect(rd, controller, output, constants_only)
        finally:
            try:
                if controller is not None:
                    controller.Shutdown()
            finally:
                if cap is not None:
                    cap.Shutdown()
        write_new_json(output / 'complete.json', dict(status='ok', frame=FRAME, mode=mode,
            note='G channel of screen-shadow-resolved is the character self-shadow;'
                 ' R is the directional term and is constant-shortcut in this frame.',
            **result))
    except BaseException:
        write_new_json(output / 'error.json', dict(traceback=traceback.format_exc()))
        raise


if __name__ == '__main__':
    try:
        run()
    finally:
        sys.exit()
