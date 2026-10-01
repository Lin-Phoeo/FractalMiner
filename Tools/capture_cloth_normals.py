"""Verify native BC5 draw inputs in an existing frame-6411 capture, offline only.

Run with official qrenderdoc --python. ENDFIELD_CAPTURE_PATH, ENDFIELD_CAPTURE_OUTPUT
(fresh directory), ENDFIELD_TOOLS_PATH and ENDFIELD_CAPTURE_ZIP are required.
No image conversion, recompression, process injection or live game access.
complete.json is written only after replay shutdown; native exit code is not proof.
"""
import hashlib
import os
import sys
import traceback
import zipfile
from pathlib import Path

sys.path.insert(0, os.environ.get('ENDFIELD_TOOLS_PATH') or str(Path(__file__).resolve().parent))
from capture_bloom_evidence import access_record, sampler_record
from capture_replay_inventory import open_controller, validate_paths, write_new_json

PLAN = [
    {'event': 835, 'id': 37987, 'shader': 22255, 'zip_entry': '002959', 'name': 'cloth01', 'normal_binding': 4,
         'sha256': 'e96d6fd9c9a1850ab0655f8fe42fd156beb992d19008fea1a5ac45e5c6c62841'},
    {'event': 850, 'id': 37828, 'shader': 37669, 'zip_entry': '004532', 'name': 'cloth02', 'normal_binding': 5,
         'sha256': '9c7ab3cb6d4c7e85284f4caee838c5dd8978495ed147b38856808758b7db35d8'},
]
NORMAL_SAMPLER = (0, 4)


def bc5_layout(width, height, mips):
    if any(type(v) is not int or v <= 0 for v in (width, height, mips)):
        raise ValueError('Positive integer dimensions/mip count required')
    if mips > max(width, height).bit_length():
        raise ValueError('Mip count exceeds the full chain')
    rows, offset = [], 0
    for mip in range(mips):
        w, h = max(1, width >> mip), max(1, height >> mip)
        size = ((w + 3) // 4) * ((h + 3) // 4) * 16
        rows.append({'mip': mip, 'width': w, 'height': h, 'offset': offset, 'bytes': size})
        offset += size
    return rows


def verify_mips(levels, initial, width, height, mips):
    rows = bc5_layout(width, height, mips)
    if len(levels) != mips or len(initial) != sum(r['bytes'] for r in rows):
        raise ValueError('Wrong mip count/initial payload size')
    for data, row in zip(levels, rows):
        offset, size = row['offset'], row['bytes']
        if len(data) != size or data != initial[offset:offset + size]:
            raise ValueError('Draw-time BC5 differs from initial contents at mip ' + str(row['mip']))
        row.update(sha256=hashlib.sha256(data).hexdigest(), initial_contents_equal=True)
    return rows


def validate_view(view):
    expected = {'format': 'BC5_UNORM', 'textureType': 'TextureType.Texture2D', 'firstMip': 0,
                    'numMips': 12, 'firstSlice': 0, 'numSlices': 1, 'minLODClamp': 0,
                    'swizzle': ['TextureSwizzle.' + c for c in ('Red', 'Green', 'Blue', 'Alpha')]}
    if any(view.get(key) != value for key, value in expected.items()):
        raise ValueError('Native normal image view contract mismatch: ' + str(view))


def binding(used, reflected):
    index = used.access.index
    if not 0 <= index < len(reflected):
        raise ValueError('Descriptor has no reflection association')
    item = reflected[index]
    return {'set': item.fixedBindSetOrSpace, 'binding': item.fixedBindNumber, 'name': item.name,
                'access': access_record(used.access)}


def collect(rd, controller, source_zip, output):
    if controller.GetFrameInfo().frameNumber != 6411:
        raise ValueError('This resource plan requires frame 6411')
    textures = {str(t.resourceId): t for t in controller.GetTextures()}
    results = []
    with zipfile.ZipFile(source_zip) as archive:
        for plan in PLAN:
            controller.SetFrameEvent(plan['event'], True)
            state = controller.GetPipelineState()
            stage = rd.ShaderStage.Pixel
            if str(state.GetShader(stage)) != 'ResourceId::' + str(plan['shader']):
                raise ValueError('Pixel shader identity mismatch')
            reflection = state.GetShaderReflection(stage)
            matches = []
            for used in state.GetReadOnlyResources(stage):
                record = binding(used, reflection.readOnlyResources)
                if (record['set'], record['binding']) == (1, plan['normal_binding']):
                    if str(used.descriptor.resource) != 'ResourceId::' + str(plan['id']):
                        raise ValueError('Normal binding resource mismatch at event {}: {} actual={} expected={}'.format(
                            plan['event'], record, used.descriptor.resource, plan['id']))
                    # Explicit descriptor view fields, not SWIG pointer serialization.
                    descriptor = used.descriptor
                    view: dict = {name: str(getattr(descriptor, name)) for name in
                                      ('resource', 'view', 'type', 'textureType')}
                    record['view'] = view
                    record['view']['format'] = descriptor.format.Name()
                    for name in ('firstMip', 'numMips', 'firstSlice', 'numSlices', 'minLODClamp'):
                        record['view'][name] = getattr(descriptor, name)
                    record['view']['swizzle'] = [str(getattr(descriptor.swizzle, c))
                                                  for c in ('red', 'green', 'blue', 'alpha')]
                    validate_view(record['view'])
                    matches.append(record)
            if len(matches) != 1:
                raise ValueError('Expected one variant-specific normal descriptor')
            texture = textures['ResourceId::' + str(plan['id'])]
            actual = (texture.width, texture.height, texture.depth, texture.arraysize,
                      texture.mips, texture.format.Name())
            if actual != (2048, 2048, 1, 1, 12, 'BC5_UNORM'):
                raise ValueError('Unexpected native normal image: ' + str(actual))
            initial = archive.read(plan['zip_entry'])
            if hashlib.sha256(initial).hexdigest() != plan['sha256']:
                raise ValueError('Initial contents ZIP hash mismatch')
            levels = [bytes(controller.GetTextureData(texture.resourceId, rd.Subresource(mip, 0, 0)))
                      for mip in range(texture.mips)]
            rows = verify_mips(levels, initial, texture.width, texture.height, texture.mips)
            native_samples = []
            for row in rows:
                w, h, mip = row['width'], row['height'], row['mip']
                for x, y in ((0, 0), (w-1, 0), (0, h-1), (w-1, h-1), (w//2, h//2)):
                    sample = controller.PickPixel(texture.resourceId, x, y, rd.Subresource(mip, 0, 0), rd.CompType.UNorm)
                    native_samples.append({'mip': mip, 'x': x, 'y': y, 'rgba': list(sample.floatValue)})
            samplers = []
            for used in state.GetSamplers(stage):
                record = binding(used, reflection.samplers)
                resolved = controller.GetSamplerDescriptors(used.access.descriptorStore,
                                                            [rd.DescriptorRange(used.access)])
                if len(resolved) != 1 or resolved[0].type not in (rd.DescriptorType.Sampler, rd.DescriptorType.ImageSampler):
                    raise ValueError('Unresolved Pixel sampler descriptor')
                record['sampler'] = sampler_record(resolved[0])
                samplers.append(record)
            if len([s for s in samplers if (s['set'], s['binding']) == NORMAL_SAMPLER]) != 1:
                raise ValueError('Expected normal sampler at set0/binding4')
            filename = plan['name'] + '.bc5'
            with (output / filename).open('xb') as stream:
                stream.write(b''.join(levels))
            result = dict(plan, file=filename, bytes=len(initial), width=2048, height=2048,
                          mips=12, format='BC5_UNORM', levels=rows, normal=matches[0], samplers=samplers,
                          shader_sha256=hashlib.sha256(bytes(reflection.rawBytes)).hexdigest(),
                          native_samples=native_samples)
            results.append(result)
            write_new_json(output / (plan['name'] + '-evidence.json'), result)
    return results


def run():
    capture = Path(os.environ['ENDFIELD_CAPTURE_PATH']).resolve()
    output = Path(os.environ['ENDFIELD_CAPTURE_OUTPUT']).resolve()
    source_zip = Path(os.environ['ENDFIELD_CAPTURE_ZIP']).resolve()
    validate_paths(capture, output)
    write_new_json(output / 'started.json', {'capture': str(capture), 'source_zip': str(source_zip), 'frame': 6411})
    cap = controller = None
    try:
        try:
            import renderdoc as rd  # pyright: ignore[reportMissingImports]
            cap, controller = open_controller(rd, capture)
            results = collect(rd, controller, source_zip, output)
        finally:
            try:
                if controller is not None:
                    controller.Shutdown()
            finally:
                if cap is not None:
                    cap.Shutdown()
        write_new_json(output / 'complete.json', {'status': 'ok', 'frame': 6411, 'textures': results,
                       'contract': 'raw BC5 blocks; draw-time mip bytes equal reviewed ZIP initial contents'})
    except BaseException:
        write_new_json(output / 'error.json', {'traceback': traceback.format_exc()})
        raise


if __name__ == '__main__':
    try:
        run()
    finally:
        sys.exit()
