"""Lossless transfer and read-only consumer tests, not a skinning oracle."""
import hashlib
import json
import struct
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import native_draw_bundle as bundle


def make_native_source(tmp_path):
    root = tmp_path / 'source'
    root.mkdir()
    formats = {0: ('R32G32B32_FLOAT', 3, 4), 2: ('R32_FLOAT', 1, 4),
               5: ('R32G32B32_FLOAT', 3, 4), 6: ('R32_FLOAT', 1, 4),
               8: ('R32G32B32A32_FLOAT', 4, 4), 9: ('R32G32B32A32_UINT', 4, 4)}
    payloads = {0: struct.pack('<6f', 0, 0, 0, 1, 0, 0),
                2: struct.pack('<2I', 0xFFC00001, 0x40000000),
                5: struct.pack('<6f', 0, 0, 0, 1, 0, 0),
                6: struct.pack('<2I', 0x400001FF, 0x40000000),
                8: struct.pack('<8f', .2, .3, .4, .1, 1, -0.0, 0, 0),
                9: struct.pack('<8I', 300, 1, 2, 3, 7, 0, 0, 0)}
    inputs = {}
    signature = [{'name': 'instance', 'location': 0, 'system_value': 'ShaderBuiltin.InstanceIndex'}]
    for loc, (fmt, count, width) in formats.items():
        name = 'anonymous_' + str(loc)
        raw = payloads[loc]
        filename = name + '.bin'
        (root / filename).write_bytes(raw)
        stride = count * width
        inputs[name] = {'file': filename, 'sha256': hashlib.sha256(raw).hexdigest(),
                        'format': {'name': fmt, 'compCount': count, 'compByteWidth': width, 'stride': stride},
                        'slot': loc, 'offset': 0, 'buffer_stride': stride,
                        'buffer_offset': 128, 'first_byte': 128 + 4 * stride}
        signature.append({'name': name, 'location': loc, 'system_value': 'ShaderBuiltin.Undefined'})
    (root / 'ib.bin').write_bytes(struct.pack('<3H', 5, 6, 5))
    record = {'part': 'fixture', 'shader': 'ResourceId::123', 'vertices': 2, 'indices': 3,
              'ib_min': 5, 'base_vertex': -2, 'vertex_offset': 1,
              'inputs': inputs, 'signature': signature, 'ib_file': 'ib.bin',
              'index_binding': {'index_stride': 2, 'first_byte': 140,
                                'buffer_offset': 128, 'resource': 'ResourceId::42'},
              'draw': {'event': 835, 'index_offset': 6, 'index_count': 3, 'instances': 1}}
    source = {'schema': 'renderdoc-vsin-raw-v1', 'frame': 6411, 'import_ready': False,
              'api': 'GraphicsAPI.Vulkan', 'events': {'835': record}}
    path = root / 'manifest.json'
    path.write_text(json.dumps(source), encoding='utf-8')
    contract = {'schema': 1, 'frame': 6411, 'api': source['api'],
                'raw_manifest_sha256': hashlib.sha256(path.read_bytes()).hexdigest(),
                'events': {'835': {'part': 'fixture', 'shader': record['shader'],
                                   'vertices': 2, 'indices': 3,
                                   'formats': {str(k): v[0] for k, v in formats.items()}}}}
    contract_path = tmp_path / 'contract.json'
    contract_path.write_text(json.dumps(contract), encoding='utf-8')
    return root, path, contract_path, source, payloads


@pytest.fixture
def native_source(tmp_path):
    return make_native_source(tmp_path)


def test_byte_exact_roundtrip_and_location_reader(native_source, tmp_path):
    root, manifest, contract, _, payloads = native_source
    before = {p.name: p.read_bytes() for p in root.iterdir()}
    output = tmp_path / 'bundle'
    report = bundle.build(manifest, contract, output)
    assert report['ok'] and not report['rendering_certified'] and not report['mesh_mapping_ready']
    draw = bundle.load(output)['events']['835']
    assert draw['base_vertex'] == -2 and draw['ib_min'] == 5
    for location, raw in payloads.items():
        assert bundle.read_stream(output, 835, location) == raw
    assert bundle.read_stream(output, 835, 0) == bundle.read_stream(output, 835, 5)
    assert draw['attributes']['0']['file'] != draw['attributes']['5']['file']
    assert draw['attributes']['8']['format']['name'] == 'R32G32B32A32_FLOAT'
    assert struct.unpack_from('<I', bundle.read_stream(output, 835, 9))[0] == 300
    assert (output / 'ib.bin').read_bytes() == struct.pack('<3H', 5, 6, 5)
    assert {p.name: p.read_bytes() for p in root.iterdir()} == before
    assert (output / 'source-manifest.json').read_bytes() == manifest.read_bytes()
    assert (output / 'source-contract.json').read_bytes() == contract.read_bytes()


def test_existing_or_nested_output_refused_without_source_mutation(native_source, tmp_path):
    root, manifest, contract, _, _ = native_source
    for output in (root, root / 'nested'):
        with pytest.raises((ValueError, FileExistsError)):
            bundle.build(manifest, contract, output)
    target = tmp_path / 'exists'
    target.mkdir()
    (target / 'sentinel').write_text('keep', encoding='utf-8')
    with pytest.raises(FileExistsError):
        bundle.build(manifest, contract, target)
    assert (target / 'sentinel').read_text() == 'keep'


def test_source_hash_failure_creates_no_bundle(native_source, tmp_path):
    root, manifest, contract, _, _ = native_source
    (root / 'anonymous_8.bin').write_bytes(b'x' * 32)
    target = tmp_path / 'bundle'
    with pytest.raises(ValueError, match='hash'):
        bundle.build(manifest, contract, target)
    assert not target.exists()


@pytest.mark.parametrize('fault', ['attribute', 'index', 'manifest', 'contract', 'incomplete', 'extra', 'directory'])
def test_changed_or_incomplete_bundle_refused(native_source, tmp_path, fault):
    _, manifest, contract, _, _ = native_source
    output = tmp_path / 'bundle'
    bundle.build(manifest, contract, output)
    filename = {'attribute': 'anonymous_8.bin', 'index': 'ib.bin',
                'manifest': 'manifest.json', 'contract': 'source-contract.json'}.get(fault)
    if filename:
        with (output / filename).open('ab') as stream:
            stream.write(b'x')
    elif fault == 'incomplete':
        (output / 'complete.json').unlink()
    elif fault == 'extra':
        (output / 'extra.bin').write_bytes(b'x')
    else:
        (output / 'unlisted-folder').mkdir()
    with pytest.raises((ValueError, FileNotFoundError)):
        bundle.load(output)


def test_missing_location_does_not_fall_back_or_alias(native_source, tmp_path):
    _, manifest, contract, _, _ = native_source
    output = tmp_path / 'bundle'
    bundle.build(manifest, contract, output)
    with pytest.raises(KeyError):
        bundle.read_stream(output, 835, 7)
    with pytest.raises(KeyError):
        bundle.read_stream(output, 999, 0)


def test_index_address_and_draw_count_checked(native_source, tmp_path):
    _, manifest, contract_path, source, _ = native_source
    source['events']['835']['index_binding']['first_byte'] = 141
    manifest.write_text(json.dumps(source), encoding='utf-8')
    contract = json.loads(contract_path.read_text())
    contract['raw_manifest_sha256'] = hashlib.sha256(manifest.read_bytes()).hexdigest()
    contract_path.write_text(json.dumps(contract), encoding='utf-8')
    with pytest.raises(ValueError, match='Index address'):
        bundle.build(manifest, contract_path, tmp_path / 'bad')
    source['events']['835']['index_binding']['first_byte'] = 140
    source['events']['835']['draw']['index_count'] = 99
    manifest.write_text(json.dumps(source), encoding='utf-8')
    contract['raw_manifest_sha256'] = hashlib.sha256(manifest.read_bytes()).hexdigest()
    contract_path.write_text(json.dumps(contract), encoding='utf-8')
    with pytest.raises(ValueError, match='draw'):
        bundle.build(manifest, contract_path, tmp_path / 'bad-count')


def test_cli_build_verify(native_source, tmp_path, capsys):
    _, manifest, contract, _, _ = native_source
    output = tmp_path / 'bundle'
    assert bundle.main(['build', str(manifest), str(contract), str(output)]) == 0
    assert bundle.main(['verify', str(output)]) == 0
    assert 'mesh_mapping_ready' in capsys.readouterr().out


def test_no_unorm_or_slot_conversion(native_source, tmp_path):
    root, manifest, contract_path, source, _ = native_source
    for location, fmt, width, raw in [
        (8, 'R8G8B8A8_UNORM', 1, bytes([255, 0, 0, 0] * 2)),
        (9, 'R8G8B8A8_UINT', 1, bytes([17, 1, 2, 3] * 2)),
    ]:
        entry = source['events']['835']['inputs']['anonymous_' + str(location)]
        (root / entry['file']).write_bytes(raw)
        entry['sha256'] = hashlib.sha256(raw).hexdigest()
        entry['format'].update(name=fmt, compByteWidth=width, stride=4 * width)
        entry['buffer_stride'] = 4 * width
        entry['first_byte'] = 128 + 4 * 4 * width
    manifest.write_text(json.dumps(source), encoding='utf-8')
    contract = json.loads(contract_path.read_text())
    contract['raw_manifest_sha256'] = hashlib.sha256(manifest.read_bytes()).hexdigest()
    contract['events']['835']['formats'].update({'8': 'R8G8B8A8_UNORM', '9': 'R8G8B8A8_UINT'})
    contract_path.write_text(json.dumps(contract), encoding='utf-8')
    output = tmp_path / 'bundle'
    bundle.build(manifest, contract_path, output)
    assert bundle.read_stream(output, 835, 8) == bytes([255, 0, 0, 0] * 2)
    assert bundle.read_stream(output, 835, 9) == bytes([17, 1, 2, 3] * 2)


def test_external_pins_and_duplicate_json_keys_fail_closed(native_source, tmp_path):
    _, manifest, contract, _, _ = native_source
    output = tmp_path / 'bundle'
    result = bundle.build(manifest, contract, output)
    assert bundle.load(output, result['contract_sha256'], result['manifest_sha256'])
    with pytest.raises(ValueError, match='contract identity'):
        bundle.load(output, '0' * 64)
    with pytest.raises(ValueError, match='manifest identity'):
        bundle.load(output, expected_manifest_sha256='0' * 64)
    with pytest.raises(ValueError, match='Duplicate JSON'):
        bundle.parse(b'{"schema":1,"schema":2}')


@pytest.mark.parametrize('field', ['buffer_offset', 'buffer_stride', 'offset'])
def test_negative_native_addresses_fail_before_any_write(native_source, tmp_path, field):
    _, manifest, contract_path, source, _ = native_source
    entry = source['events']['835']['inputs']['anonymous_8']
    entry[field] = -1
    entry['first_byte'] = entry['buffer_offset'] + 4 * entry['buffer_stride'] + entry['offset']
    manifest.write_bytes(bundle.encode(source))
    contract = json.loads(contract_path.read_text())
    contract['raw_manifest_sha256'] = bundle.sha(manifest.read_bytes())
    contract_path.write_bytes(bundle.encode(contract))
    output = tmp_path / 'bundle'
    with pytest.raises(ValueError, match='Negative native'):
        bundle.build(manifest, contract_path, output)
    assert not output.exists()


def test_transfer_requires_source_manifest_pin(native_source, tmp_path):
    _, manifest, contract_path, _, _ = native_source
    contract = json.loads(contract_path.read_text())
    contract.pop('raw_manifest_sha256')
    contract_path.write_bytes(bundle.encode(contract))
    with pytest.raises(ValueError, match='manifest pin'):
        bundle.build(manifest, contract_path, tmp_path / 'bundle')


def test_read_stream_rechecks_bytes_after_loading(native_source, tmp_path, monkeypatch):
    _, manifest, contract, _, _ = native_source
    output = tmp_path / 'bundle'
    bundle.build(manifest, contract, output)
    original_load = bundle.load
    def load_then_change(root):
        metadata = original_load(root)
        (root / 'anonymous_8.bin').write_bytes(b'x' * 32)
        return metadata
    monkeypatch.setattr(bundle, 'load', load_then_change)
    with pytest.raises(ValueError, match='Stream changed'):
        bundle.read_stream(output, 835, 8)
