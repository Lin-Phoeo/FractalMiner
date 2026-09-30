"""Raw byte/location contracts are not rendering-equivalence certification."""
import hashlib
import json
import struct
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import raw_draw_inputs as audit


@pytest.fixture
def fixture(tmp_path):
    inputs = {}
    signature = [{'name': 'instance', 'location': 0, 'system_value': 'ShaderBuiltin.InstanceIndex'}]
    formats = {0: 'R32G32B32_FLOAT', 5: 'R32G32B32_FLOAT',
               8: 'R32G32B32A32_FLOAT', 9: 'R32G32B32A32_UINT'}
    payloads = {0: struct.pack('<6f', 0, 0, 0, 1, 0, 0),
                5: struct.pack('<6f', 0, 0, 0, 1, 0, 0),
                8: struct.pack('<8f', .2, .3, .4, .1, 1, 0, 0, 0),
                9: struct.pack('<8I', 300, 1, 2, 3, 7, 0, 0, 0)}
    for location, fmt in formats.items():
        name = 'anonymous_' + str(location)
        file = name + '.bin'
        data = payloads[location]
        (tmp_path / file).write_bytes(data)
        count = 3 if location in (0, 5) else 4
        inputs[name] = {'file': file, 'sha256': hashlib.sha256(data).hexdigest(),
                        'format': {'name': fmt, 'compCount': count,
                                   'compByteWidth': 4, 'stride': count * 4},
                        'slot': location, 'offset': 0, 'buffer_stride': count * 4,
                        'buffer_offset': 0, 'first_byte': 0}
        signature.append({'name': name, 'location': location,
                          'system_value': 'ShaderBuiltin.Undefined'})
    (tmp_path / 'ib.bin').write_bytes(struct.pack('<3H', 0, 1, 0))
    record = {'part': 'cloth', 'shader': 'ResourceId::123', 'vertices': 2, 'indices': 3,
              'ib_min': 0, 'base_vertex': 0, 'vertex_offset': 0,
              'inputs': inputs, 'signature': signature, 'ib_file': 'ib.bin',
              'index_binding': {'index_stride': 2}}
    manifest = {'schema': 'renderdoc-vsin-raw-v1', 'frame': 6411,
                'api': 'GraphicsAPI.Vulkan', 'events': {'835': record}}
    contract = {'schema': 1, 'frame': 6411, 'api': 'GraphicsAPI.Vulkan',
                'events': {'835': {'part': 'cloth', 'shader': 'ResourceId::123',
                                   'vertices': 2, 'indices': 3,
                                   'formats': {str(k): v for k, v in formats.items()}}}}
    path = tmp_path / 'manifest.json'
    path.write_text(json.dumps(manifest), encoding='utf-8')
    return tmp_path, path, manifest, contract


def save(fixture):
    fixture[1].write_text(json.dumps(fixture[2]), encoding='utf-8')


def test_location_not_name_and_builtin_zero_does_not_collide(fixture):
    _, path, _, contract = fixture
    report = audit.inspect(path, contract)
    assert report['ok'] and not report['rendering_certified']
    assert report['files_checked'] == 4
    assert report['events']['835']['position_rest_same_bytes']
    assert report['events']['835']['skin']['maximum_slot'] == 300
    assert report['events']['835']['skin']['u16_quantization_changed_components'] == 4


@pytest.mark.parametrize('failure', ['sha', 'size', 'path', 'location', 'extra', 'format', 'address', 'index'])
def test_bad_inputs_fail_closed(fixture, failure):
    root, path, manifest, contract = fixture
    record = manifest['events']['835']
    entry = record['inputs']['anonymous_8']
    if failure == 'sha':
        (root / entry['file']).write_bytes(b'x' * 32)
    elif failure == 'size':
        (root / entry['file']).write_bytes(b'x')
    elif failure == 'path':
        entry['file'] = '../outside.bin'
    elif failure == 'location':
        record['signature'][-1]['location'] = 8
    elif failure == 'extra':
        record['inputs']['undeclared'] = dict(entry)
    elif failure == 'format':
        entry['format']['name'] = 'R16G16B16A16_UNORM'
    elif failure == 'address':
        entry['first_byte'] = 1
    else:
        (root / 'ib.bin').write_bytes(struct.pack('<3H', 0, 9, 0))
    save(fixture)
    with pytest.raises(ValueError):
        audit.inspect(path, contract)


def test_constants_zero_stride_must_be_replicated(fixture):
    root, path, manifest, contract = fixture
    entry = manifest['events']['835']['inputs']['anonymous_9']
    entry['buffer_stride'] = 0
    save(fixture)
    with pytest.raises(ValueError, match='constant'):
        audit.inspect(path, contract)
    data = struct.pack('<8I', 7, 0, 0, 0, 7, 0, 0, 0)
    (root / entry['file']).write_bytes(data)
    entry['sha256'] = hashlib.sha256(data).hexdigest()
    save(fixture)
    assert audit.inspect(path, contract)['ok']


@pytest.mark.parametrize('field,value', [('frame', 99), ('schema', 'normalized-pose-v1')])
def test_unrelated_capture_or_normalized_pose_is_rejected(fixture, field, value):
    _, path, manifest, contract = fixture
    manifest[field] = value
    save(fixture)
    with pytest.raises(ValueError):
        audit.inspect(path, contract)


def test_unorm_weights_and_byte_slots_keep_native_storage(fixture):
    root, path, manifest, contract = fixture
    record = manifest['events']['835']
    for location, fmt, width, data in [
        (8, 'R16G16B16A16_UNORM', 2, struct.pack('<8H', 65535, 0, 0, 0, 65535, 0, 0, 0)),
        (9, 'R8G8B8A8_UINT', 1, bytes([17, 0, 0, 0, 19, 0, 0, 0])),
    ]:
        entry = record['inputs']['anonymous_' + str(location)]
        (root / entry['file']).write_bytes(data)
        entry['sha256'] = hashlib.sha256(data).hexdigest()
        entry['format'].update(name=fmt, compByteWidth=width, stride=4 * width)
        entry['buffer_stride'] = 4 * width
        contract['events']['835']['formats'][str(location)] = fmt
    save(fixture)
    skin = audit.inspect(path, contract)['events']['835']['skin']
    assert skin['maximum_slot'] == 19
    assert skin['u16_quantization_changed_components'] == 0


def test_nan_weights_not_confused_with_packed_float_payload(fixture):
    root, path, manifest, contract = fixture
    entry = manifest['events']['835']['inputs']['anonymous_8']
    data = struct.pack('<8f', float('nan'), 0, 0, 1, 1, 0, 0, 0)
    (root / entry['file']).write_bytes(data)
    entry['sha256'] = hashlib.sha256(data).hexdigest()
    save(fixture)
    with pytest.raises(ValueError, match='weight'):
        audit.inspect(path, contract)


def test_cli_refuses_existing_report(fixture):
    root, path, _, contract = fixture
    contract_path = root / 'contract.json'
    contract_path.write_text(json.dumps(contract), encoding='utf-8')
    output = root / 'report.json'
    assert audit.main([str(path), str(contract_path), '--output', str(output)]) == 0
    with pytest.raises(FileExistsError):
        audit.main([str(path), str(contract_path), '--output', str(output)])


def test_frozen_manifest_identity_is_checked_when_present(fixture):
    _, path, _, contract = fixture
    contract['raw_manifest_sha256'] = hashlib.sha256(path.read_bytes()).hexdigest()
    assert audit.inspect(path, contract)['ok']
    contract['raw_manifest_sha256'] = '0' * 64
    with pytest.raises(ValueError, match='identity'):
        audit.inspect(path, contract)
