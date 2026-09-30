"""Reviewed frame-6411 fragment basis and skin texture exports; offline only.

The actual face SPIR-V uses bit16 of instance flags to load three root rows
at base*16 from buffer245. This is NOT the vertex palette starting at base+3.
Run with ENDFIELD_CAPTURE_PATH/OUTPUT/TOOLS_PATH in official qrenderdoc.
"""
import hashlib
import json
import math
import os
from pathlib import Path
import struct
import sys
import traceback


def decode_basis_record(record, root_bytes, origin):
    if len(record) != 256 or len(origin) != 3 or not all(math.isfinite(x) for x in origin):
        raise ValueError('Invalid instance record/origin')
    flags, base = struct.unpack_from('<I', record, 76)[0], struct.unpack_from('<I', record, 80)[0]
    if flags & 16:
        if root_bytes is None or len(root_bytes) != 48:
            raise ValueError('Missing skin root rows')
        values = struct.unpack('<12f', root_bytes)
        rows = [list(values[i:i+4]) for i in range(0, 12, 4)]
        source = 'skin-root-buffer'
    else:
        values = struct.unpack_from('<16f', record, 0)
        rows = [[values[column*4+row] for column in range(4)] for row in range(3)]
        source = 'instance-matrix'
    if not all(math.isfinite(x) for row in rows for x in row):
        raise ValueError('Non-finite source basis')
    local = [row[:3] + [row[3] - origin[i]] for i, row in enumerate(rows)]
    return {'flags': flags, 'base_float4': base, 'source': source,
            'scene_origin': list(origin), 'rows_absolute': rows, 'rows_local_origin': local}


def run():
    import renderdoc as rd
    from capture_replay_inventory import open_controller, validate_paths, write_new_json
    tools = Path(os.environ['ENDFIELD_TOOLS_PATH'])
    project = tools.parent
    capture, output = Path(os.environ['ENDFIELD_CAPTURE_PATH']), Path(os.environ['ENDFIELD_CAPTURE_OUTPUT'])
    validate_paths(capture, output)
    cap = controller = None
    try:
        cap, controller = open_controller(rd, capture)
        if controller.GetFrameInfo().frameNumber != 6411:
            raise ValueError('This extraction is reviewed only for front frame6411')
        pose = json.loads((project/'Validation/Captures/tifuluosi-front-20260917/pose-full-01/manifest.json').read_text())
        buffers = {str(b.resourceId): b.resourceId for b in controller.GetBuffers()}
        textures = {str(t.resourceId): t for t in controller.GetTextures()}
        report = {'frame': 6411, 'capture': str(capture), 'parts': {},
                  'basis_contract': 'actual fragment-37671.hlsl:407-418,457; per-draw bit16/base'}
        for event, metadata in pose['events'].items():
            controller.SetFrameEvent(int(event), True)
            state = controller.GetPipelineState()
            reflection = state.GetShaderReflection(rd.ShaderStage.Pixel)
            blocks = [(i,b) for i,b in enumerate(reflection.constantBlocks)
                      if b.fixedBindNumber == 0 and b.fixedBindSetOrSpace == 2]
            if len(blocks) != 1:
                raise ValueError('Missing/ambiguous instance block')
            descriptor = state.GetConstantBlock(rd.ShaderStage.Pixel, blocks[0][0], 0).descriptor
            raw = bytes(controller.GetBufferData(descriptor.resource, descriptor.byteOffset, 256))
            if len(raw) != 256:
                raise ValueError('Truncated instance record')
            base = struct.unpack_from('<I', raw, 80)[0]
            if base + 3 != metadata['ssbo_base1']:
                raise ValueError('Capture no longer matches reviewed pose manifest')
            flags = struct.unpack_from('<I', raw, 76)[0]
            root = bytes(controller.GetBufferData(buffers['ResourceId::245'], base*16, 48)) if flags & 16 else None
            child = struct.unpack_from('<16f', raw, 0)
            basis = decode_basis_record(raw, root, child[12:15])
            basis.update(event=int(event), part=metadata['part'], instance_offset=descriptor.byteOffset,
                         root_sha256=hashlib.sha256(root).hexdigest() if root is not None else None)
            report['parts'][metadata['part']] = basis
            if metadata['part'] != 'face':
                continue
            expected = (project/'Validation/Captures/tifuluosi-front-20260917/replay-details-01/shader-37671.spv').read_bytes()
            if hashlib.sha256(bytes(reflection.rawBytes)).digest() != hashlib.sha256(expected).digest():
                raise ValueError('Unexpected face fragment shader')
            names = {1:'ShadowLutTex',2:'SDFMask',3:'SDFLightmap',4:'HighlightMap',
                     5:'EmotionMap',6:'DiffRampMap',7:'BumpMap',8:'BaseMap'}
            exports = {}
            for used in state.GetReadOnlyResources(rd.ShaderStage.Pixel):
                binding = reflection.readOnlyResources[used.access.index]
                if binding.fixedBindSetOrSpace != 1:
                    continue
                name = names.get(binding.fixedBindNumber)
                if name is None or name in exports:
                    raise ValueError('Unexpected/duplicate face texture binding')
                texture = textures[str(used.descriptor.resource)]
                save = rd.TextureSave()
                save.resourceId = texture.resourceId
                save.mip = 0
                save.slice.sliceIndex = 0
                save.destType = rd.FileType.PNG
                path = output/(name+'.png')
                result = controller.SaveTexture(save, str(path))
                if result != rd.ResultCode.Succeeded:
                    raise RuntimeError('SaveTexture '+name+': '+str(result))
                exports[name] = {'binding': binding.fixedBindNumber, 'resource': str(texture.resourceId),
                                 'format': texture.format.Name(), 'width': texture.width,'height':texture.height,
                                 'file':path.name,'sha256':hashlib.sha256(path.read_bytes()).hexdigest(),
                                 'note':'RenderDoc mip0 PNG preview; verify channel/row encoding before input replacement'}
            if set(exports) != set(names.values()):
                raise ValueError('Incomplete face texture export')
            basis['textures'] = exports
        write_new_json(output/'basis.json', report)
        write_new_json(output/'complete.json', {'status':'ok','frame':6411,'parts':list(report['parts'])})
    except BaseException:
        write_new_json(output/'error.json', {'traceback':traceback.format_exc()})
        raise
    finally:
        if controller is not None: controller.Shutdown()
        if cap is not None: cap.Shutdown()


if __name__ == '__main__':
    sys.path.insert(0, os.environ['ENDFIELD_TOOLS_PATH'])
    try: run()
    finally: sys.exit()
