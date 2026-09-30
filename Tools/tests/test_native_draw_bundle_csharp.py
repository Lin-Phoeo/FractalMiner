"""Compile and execute the actual C# reader; no string-matching certification."""
import hashlib
import json
import os
import struct
import subprocess
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import native_draw_bundle as bundle
import test_native_draw_bundle as fixture_support

PROJECT = Path(__file__).resolve().parents[2]


@pytest.fixture
def native_source(tmp_path):
    return fixture_support.make_native_source(tmp_path)


@pytest.fixture(scope='session')
def reader(tmp_path_factory):
    build = tmp_path_factory.mktemp('native-reader-build')
    env = dict(os.environ, DOTNET_CLI_TELEMETRY_OPTOUT='1')
    args = ['dotnet', 'build', str(PROJECT / 'Tools/NativeDrawBundleTests/NativeDrawBundleTests.csproj'),
            '--ignore-failed-sources', '--nologo', '-p:BaseIntermediateOutputPath=' + str(build / 'obj') + '/',
            '-p:OutputPath=' + str(build / 'bin') + '/']
    result = subprocess.run(args, capture_output=True, text=True, encoding='utf-8', timeout=60, env=env, check=False)
    assert result.returncode == 0, result.stdout + result.stderr
    return build / 'bin/NativeDrawBundleTests.dll'


def execute(reader, root, digest, mode='inspect'):
    return subprocess.run(['dotnet', str(reader), mode, str(root), digest],
                          capture_output=True, text=True, encoding='utf-8', timeout=30, check=False)


def test_actual_csharp_byte_preservation_and_typed_reads(reader, native_source, tmp_path):
    _, source, contract, _, _ = native_source
    output = tmp_path / 'bundle'
    report = bundle.build(source, contract, output)
    result = execute(reader, output, report['manifest_sha256'], 'fixture')
    assert result.returncode == 0, result.stderr
    data = json.loads(result.stdout)
    assert data['ok'] and data['vertices'] == 2 and data['streams'] == 6
    assert not data['rendering_certified'] and not data['mesh_mapping_ready']


@pytest.mark.parametrize('fault', ['pin', 'bytes', 'path', 'location', 'format', 'address', 'index',
                                  'duplicate', 'incomplete', 'extra', 'schema', 'zero_stride'])
def test_actual_csharp_rejects_bad_bundle(reader, native_source, tmp_path, fault):
    _, source, contract, _, _ = native_source
    output = tmp_path / 'bundle'
    digest = bundle.build(source, contract, output)['manifest_sha256']
    metadata_path = output / 'manifest.json'
    metadata = json.loads(metadata_path.read_text())
    if fault == 'pin':
        digest = '0' * 64
    elif fault in ('bytes', 'index'):
        name = 'anonymous_8.bin' if fault == 'bytes' else 'ib.bin'
        (output / name).write_bytes(b'x')
    elif fault == 'incomplete':
        (output / 'complete.json').unlink()
    elif fault == 'extra':
        (output / 'extra.bin').write_bytes(b'x')
    elif fault == 'duplicate':
        metadata_path.write_bytes(b'{"schema":1,"schema":2}')
        digest = hashlib.sha256(metadata_path.read_bytes()).hexdigest()
    else:
        draw = metadata['events']['835']
        if fault == 'path':
            draw['attributes']['8']['file'] = '../outside.bin'
        elif fault == 'location':
            draw['attributes']['7'] = draw['attributes'].pop('6')
        elif fault == 'format':
            draw['attributes']['8']['format']['name'] = 'R16G16B16A16_UNORM'
        elif fault == 'address':
            draw['attributes']['8']['first_byte'] += 1
        elif fault == 'zero_stride':
            draw['attributes']['8']['buffer_stride'] = 0
        else:
            metadata['rendering_certified'] = True
        metadata_path.write_bytes(bundle.encode(metadata))
        digest = hashlib.sha256(metadata_path.read_bytes()).hexdigest()
    if fault != 'incomplete':
        (output / 'complete.json').write_bytes(bundle.encode({'schema': bundle.COMPLETE_SCHEMA,
                                                             'manifest_sha256': digest}))
    result = execute(reader, output, digest)
    assert result.returncode != 0


@pytest.mark.parametrize('fault', ['nan_weight', 'slot_format', 'zero_stride', 'negative_address',
                                  'index_span', 'index_count', 'component_width', 'duplicate_signature', 'index_address'])
def test_reader_checks_native_payload_not_only_normalized_metadata(reader, native_source, tmp_path, fault):
    _, source_path, contract_path, _, _ = native_source
    output = tmp_path / 'bundle'
    bundle.build(source_path, contract_path, output)
    source = json.loads((output / 'source-manifest.json').read_text())
    contract = json.loads((output / 'source-contract.json').read_text())
    record = source['events']['835']
    if fault == 'nan_weight':
        raw = struct.pack('<8f', float('nan'), 0, 0, 1, 1, 0, 0, 0)
        (output / 'anonymous_8.bin').write_bytes(raw)
        record['inputs']['anonymous_8']['sha256'] = bundle.sha(raw)
    elif fault == 'slot_format':
        record['inputs']['anonymous_9']['format']['name'] = 'R32G32B32A32_SNORM'
        contract['events']['835']['formats']['9'] = 'R32G32B32A32_SNORM'
    elif fault == 'zero_stride':
        record['inputs']['anonymous_8'].update(buffer_stride=0, first_byte=128)
    elif fault == 'negative_address':
        record['inputs']['anonymous_8']['buffer_offset'] = -1
        record['inputs']['anonymous_8']['first_byte'] = -1 + 4 * 16
    elif fault == 'index_span':
        (output / 'ib.bin').write_bytes(bytes([5, 0, 9, 0, 5, 0]))
    elif fault == 'index_count':
        record['draw']['index_count'] += 1
    elif fault == 'component_width':
        record['inputs']['anonymous_8']['format']['compByteWidth'] = 2
    elif fault == 'duplicate_signature':
        record['signature'].append(dict(record['signature'][1]))
    else:
        record['index_binding']['first_byte'] += 1
    source_raw = bundle.encode(source)
    (output / 'source-manifest.json').write_bytes(source_raw)
    contract['raw_manifest_sha256'] = bundle.sha(source_raw)
    (output / 'source-contract.json').write_bytes(bundle.encode(contract))
    metadata = json.loads((output / 'manifest.json').read_text())
    metadata['source_manifest_sha256'] = bundle.sha(source_raw)
    metadata['contract_sha256'] = bundle.sha((output / 'source-contract.json').read_bytes())
    metadata['events']['835'] = {key: value for key, value in record.items() if key != 'inputs'}
    metadata['events']['835']['attributes'] = {
        str(sig['location']): record['inputs'][sig['name']] for sig in record['signature']
        if sig['system_value'] == 'ShaderBuiltin.Undefined'}
    for name in metadata['files']:
        raw = (output / name).read_bytes()
        metadata['files'][name] = {'bytes': len(raw), 'sha256': bundle.sha(raw)}
    raw = bundle.encode(metadata)
    (output / 'manifest.json').write_bytes(raw)
    digest = bundle.sha(raw)
    (output / 'complete.json').write_bytes(bundle.encode({'schema': bundle.COMPLETE_SCHEMA, 'manifest_sha256': digest}))
    result = execute(reader, output, digest)
    assert result.returncode != 0


@pytest.mark.parametrize('weight_width,index_width', [(1, 1), (2, 4)])
def test_csharp_native_unorm_constants_and_index_widths(reader, native_source, tmp_path, weight_width, index_width):
    root, source_path, contract_path, source, _ = native_source
    record = source['events']['835']
    data = struct.pack('<8' + ('B' if weight_width == 1 else 'H'),
                       (1 << (weight_width * 8)) - 1, 0, 0, 0, (1 << (weight_width * 8)) - 1, 0, 0, 0)
    for location, width, fmt, raw in [
        (8, weight_width, f'R{weight_width * 8}G{weight_width * 8}B{weight_width * 8}A{weight_width * 8}_UNORM', data),
        (9, 1, 'R8G8B8A8_UINT', bytes([17, 0, 0, 0] * 2)),
    ]:
        entry = record['inputs']['anonymous_' + str(location)]
        (root / entry['file']).write_bytes(raw)
        entry.update(sha256=bundle.sha(raw), buffer_stride=0, first_byte=128)
        entry['format'].update(name=fmt, compByteWidth=width, stride=4 * width)
    record['index_binding'].update(index_stride=index_width, first_byte=128 + 6 * index_width)
    (root / 'ib.bin').write_bytes(struct.pack('<3' + ('B' if index_width == 1 else 'I'), 5, 6, 5))
    source_path.write_bytes(bundle.encode(source))
    contract = json.loads(contract_path.read_text())
    contract['raw_manifest_sha256'] = bundle.sha(source_path.read_bytes())
    for location in (8, 9):
        contract['events']['835']['formats'][str(location)] = record['inputs']['anonymous_' + str(location)]['format']['name']
    contract_path.write_bytes(bundle.encode(contract))
    output = tmp_path / 'bundle'
    digest = bundle.build(source_path, contract_path, output)['manifest_sha256']
    result = execute(reader, output, digest, 'unorm')
    assert result.returncode == 0, result.stderr
