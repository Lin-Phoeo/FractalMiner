"""Offline inventory via official qrenderdoc --python (never injects a process).

Set ENDFIELD_CAPTURE_PATH and ENDFIELD_CAPTURE_OUTPUT before starting qrenderdoc.
Use a fresh output directory. Captures and generated reports stay local/ignored.
Python 3.8 compatible for RenderDoc 1.46's embedded runtime.
"""
import json
import hashlib
import os
import sys
import traceback
from pathlib import Path


def flatten_actions(actions):
    for action in actions:
        yield action
        yield from flatten_actions(action.children)


def resource_id(value):
    return str(value)


def write_new_json(path, value):
    # The embedded Python debugger traces Python-level encoder loops. Use the
    # C encoder in one shot: per-draw constant arrays can contain millions of values.
    encoded = json.dumps(value, ensure_ascii=False, separators=(',', ':'))
    with Path(path).open('x', encoding='utf-8') as stream:
        stream.write(encoded)
        stream.write('\n')


def validate_paths(capture, output):
    if not capture.is_file():
        raise FileNotFoundError(capture)
    if capture.suffix.lower() != '.rdc':
        raise ValueError('Expected an already converted .rdc capture')
    output.mkdir(parents=True, exist_ok=True)
    if any(output.iterdir()):
        raise FileExistsError('Use a fresh, empty output directory')


def action_record(action, structured):
    return {
        'event': action.eventId, 'action': action.actionId,
        'name': action.GetName(structured), 'flags': int(action.flags),
        'index_count': action.numIndices, 'instances': action.numInstances,
        'base_vertex': action.baseVertex, 'index_offset': action.indexOffset,
        'vertex_offset': action.vertexOffset, 'instance_offset': action.instanceOffset,
    }


def open_controller(rd, capture):
    cap = rd.OpenCaptureFile()
    try:
        status = cap.OpenFile(str(capture), '', None)
        if status != rd.ResultCode.Succeeded:
            raise RuntimeError('OpenFile: ' + str(status))
        status, controller = cap.OpenCapture(rd.ReplayOptions(), None)
        if status != rd.ResultCode.Succeeded:
            raise RuntimeError('OpenCapture: ' + str(status))
        return cap, controller
    except BaseException:
        cap.Shutdown()
        raise


def collect_inventory(rd, controller):
    actions = list(flatten_actions(controller.GetRootActions()))
    structured = controller.GetStructuredFile()
    resources = {resource_id(r.resourceId): r.name for r in controller.GetResources()}
    textures = [{
        'id': resource_id(t.resourceId), 'name': resources.get(resource_id(t.resourceId), ''),
        'width': t.width, 'height': t.height, 'depth': t.depth,
        'array_size': t.arraysize, 'mips': t.mips, 'format': t.format.Name(),
        'flags': int(t.creationFlags), 'bytes': t.byteSize,
    } for t in controller.GetTextures()]
    buffers = [{
        'id': resource_id(b.resourceId), 'name': resources.get(resource_id(b.resourceId), ''),
        'bytes': b.length, 'flags': int(b.creationFlags),
    } for b in controller.GetBuffers()]
    draws = [a for a in actions if a.flags & rd.ActionFlags.Drawcall]
    dispatches = [a for a in actions if a.flags & rd.ActionFlags.Dispatch]
    # Replay the complete frame, not just load metadata or trust the thumbnail.
    if actions:
        controller.SetFrameEvent(actions[-1].eventId, True)
    return {
        'api': str(controller.GetAPIProperties().pipelineType),
        'frame': controller.GetFrameInfo().frameNumber,
        'draw_count': len(draws), 'dispatch_count': len(dispatches),
        'actions': [action_record(a, structured) for a in actions],
        'textures': textures, 'buffers': buffers, 'resources': resources,
        'replayed_last_event': actions[-1].eventId if actions else None,
    }


def shader_variable(variable):
    result = {'name': variable.name, 'type': str(variable.type),
              'rows': variable.rows, 'columns': variable.columns}
    if variable.members:
        result['members'] = [shader_variable(member) for member in variable.members]
    else:
        kind = str(variable.type).lower().split('.')[-1]
        fields = {'float': 'f32v', 'half': 'f32v', 'double': 'f64v',
                  'uint': 'u32v', 'int': 's32v', 'sint': 's32v', 'bool': 'u32v',
                  'ulong': 'u64v', 'slong': 's64v'}
        if kind not in fields:
            raise ValueError('Unsupported constant scalar type: ' + kind)
        data = getattr(variable.value, fields[kind])
        result['value'] = list(data)[:variable.rows * variable.columns]
    return result


def descriptor_record(used, reflection):
    index = used.access.index
    binding = reflection[index] if 0 <= index < len(reflection) else None
    return {
        'reflection_index': index, 'array_element': used.access.arrayElement,
        'name': binding.name if binding else '',
        'binding': binding.fixedBindNumber if binding else None,
        'set': binding.fixedBindSetOrSpace if binding else None,
        'resource': resource_id(used.descriptor.resource),
        'offset': used.descriptor.byteOffset, 'size': used.descriptor.byteSize,
    }


def collect_draw_details(rd, controller, output):
    """Use reflection indices, never Vulkan binding numbers as list indices."""
    details, shaders = [], {}
    actions = flatten_actions(controller.GetRootActions())
    for action in actions:
        compute = bool(action.flags & rd.ActionFlags.Dispatch)
        if not compute and not action.flags & rd.ActionFlags.Drawcall:
            continue
        controller.SetFrameEvent(action.eventId, True)
        state = controller.GetPipelineState()
        pipeline = state.GetComputePipelineObject() if compute else state.GetGraphicsPipelineObject()
        record = {'event': action.eventId, 'index_count': action.numIndices,
                  'pipeline': resource_id(pipeline), 'stages': {},
                  'outputs': [resource_id(d.resource) for d in state.GetOutputTargets()],
                  'depth': resource_id(state.GetDepthTarget().resource)}
        stages = [rd.ShaderStage.Compute] if compute else [rd.ShaderStage.Vertex, rd.ShaderStage.Pixel]
        for stage in stages:
            reflection = state.GetShaderReflection(stage)
            if reflection is None:
                continue
            shader = state.GetShader(stage)
            key = resource_id(shader)
            if key not in shaders:
                raw = bytes(reflection.rawBytes)
                basename = 'shader-' + key.split('::')[-1]
                with (output / (basename + '.spv')).open('xb') as stream:
                    stream.write(raw)
                with (output / (basename + '.txt')).open('x', encoding='utf-8') as stream:
                    stream.write(controller.DisassembleShader(pipeline, reflection, ''))
                shaders[key] = {'stage': str(stage), 'sha256': hashlib.sha256(raw).hexdigest(),
                                'file': basename + '.spv', 'bytes': len(raw)}
            stage_record = {
                'shader': key, 'entry': state.GetShaderEntryPoint(stage),
                'resources': [descriptor_record(d, reflection.readOnlyResources)
                              for d in state.GetReadOnlyResources(stage)],
                'constants': [],
            }
            for index, block in enumerate(reflection.constantBlocks):
                used = state.GetConstantBlock(stage, index, 0)
                desc = used.descriptor
                values = controller.GetCBufferVariableContents(
                    pipeline, shader, stage, reflection.entryPoint, index,
                    desc.resource, desc.byteOffset, desc.byteSize)
                stage_record['constants'].append({
                    'name': block.name, 'reflection_index': index,
                    'binding': block.fixedBindNumber, 'set': block.fixedBindSetOrSpace,
                    'resource': resource_id(desc.resource), 'offset': desc.byteOffset,
                    'size': desc.byteSize, 'variables': [shader_variable(v) for v in values],
                })
            record['stages'][str(stage)] = stage_record
        details.append(record)
    return {'draws_and_dispatches': details, 'shaders': shaders}


def save_present_preview(rd, controller, output):
    presents = [a for a in flatten_actions(controller.GetRootActions()) if a.flags & rd.ActionFlags.Present]
    if not presents:
        return None
    present = presents[-1]
    controller.SetFrameEvent(present.eventId, True)
    save = rd.TextureSave()
    save.resourceId = present.copyDestination
    save.mip = 0
    save.slice.sliceIndex = 0
    save.destType = rd.FileType.PNG
    path = output / 'replayed-present.png'
    status = controller.SaveTexture(save, str(path))
    if status != rd.ResultCode.Succeeded:
        raise RuntimeError('SaveTexture: ' + str(status))
    return {'event': present.eventId, 'resource': resource_id(present.copyDestination), 'file': path.name}


def run():
    capture = Path(os.environ['ENDFIELD_CAPTURE_PATH']).resolve()
    output = Path(os.environ['ENDFIELD_CAPTURE_OUTPUT']).resolve()
    validate_paths(capture, output)
    write_new_json(output / 'started.json', {'phase': 'opening_capture'})
    cap = controller = None
    try:
        import renderdoc as rd
        cap, controller = open_controller(rd, capture)
        write_new_json(output / 'opened.json', {'phase': 'replay_controller_open'})
        inventory = collect_inventory(rd, controller)
        write_new_json(output / 'inventory.json', inventory)
        if os.environ.get('ENDFIELD_CAPTURE_PREVIEW') == '1':
            write_new_json(output / 'preview.json', save_present_preview(rd, controller, output))
        if os.environ.get('ENDFIELD_CAPTURE_DETAILS') == '1':
            write_new_json(output / 'draw-details.json', collect_draw_details(rd, controller, output))
        write_new_json(output / 'complete.json', {
            'status': 'ok', 'frame': inventory['frame'],
            'draws': inventory['draw_count'], 'dispatches': inventory['dispatch_count'],
            'textures': len(inventory['textures']), 'buffers': len(inventory['buffers']),
            'last_event': inventory['replayed_last_event'],
        })
    except BaseException:
        write_new_json(output / 'error.json', {'traceback': traceback.format_exc()})
        raise
    finally:
        if controller is not None:
            controller.Shutdown()
        if cap is not None:
            cap.Shutdown()


if __name__ == '__main__':
    try:
        run()
    finally:
        # In qrenderdoc's --python mode SystemExit suppresses the main UI.
        # Native process exit code is NOT our success signal: inspect complete.json.
        sys.exit()
