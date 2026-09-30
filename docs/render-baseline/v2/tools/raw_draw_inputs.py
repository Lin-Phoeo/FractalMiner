"""Read-only checks of native frame-6411 inputs, never a rendering certificate.

Use input locations, not anonymous names. Never normalize normals, weights or
slots; report the damage a hypothetical f32-to-u16 conversion would introduce.
Only an explicitly requested NEW report is written. No Unity/game dependency.
"""
import argparse
import hashlib
import json
import math
import re
import struct
from pathlib import Path
from typing import Any


def local_file(root: Path, relative: str) -> Path:
    # Exported files are direct children; disallow paths, drives and symlinks out.
    if not re.fullmatch(r'[A-Za-z0-9_.-]+', relative) or relative in ('.', '..'):
        raise ValueError('Invalid exported filename: ' + relative)
    path = (root / relative).resolve()
    if path.parent != root.resolve():
        raise ValueError('Exported file escapes root: ' + relative)
    return path


def locations(record: dict[str, Any]) -> dict[int, str]:
    result = {}
    names = set()
    for signature in record['signature']:
        if signature['system_value'] != 'ShaderBuiltin.Undefined':
            continue
        name = signature['name']
        if name not in record['inputs']:
            continue  # Declared but unused inputs are not raw used-attribute exports.
        location = signature['location']
        if location in result or name in names:
            raise ValueError('Duplicate input location/name')
        result[location] = name
        names.add(name)
    if names != set(record['inputs']):
        raise ValueError('Export has inputs absent from the vertex signature')
    return result


def skin_stats(payloads: dict[int, bytes], formats: dict[int, str]) -> dict[str, Any]:
    weight_format = formats[8]
    if weight_format == 'R32G32B32A32_FLOAT':
        weights = list(struct.iter_unpack('<4f', payloads[8]))
    elif weight_format in ('R16G16B16A16_UNORM', 'R8G8B8A8_UNORM'):
        width = 2 if weight_format.startswith('R16') else 1
        divisor = 65535 if width == 2 else 255
        weights = [tuple(x / divisor for x in row)
                   for row in struct.iter_unpack('<4' + ('H' if width == 2 else 'B'), payloads[8])]
    else:
        raise ValueError('Unsupported weight storage: ' + weight_format)
    slot_code = {'R8G8B8A8_UINT': 'B', 'R32G32B32A32_UINT': 'I'}.get(formats[9])
    if slot_code is None:
        raise ValueError('Unsupported slot storage: ' + formats[9])
    slots = list(struct.iter_unpack('<4' + slot_code, payloads[9]))
    changed = 0
    max_error = 0.0
    for row in weights:
        for weight in row:
            if not math.isfinite(weight) or not 0 <= weight <= 1:
                raise ValueError('Invalid native weight')
            restored = round(weight * 65535) / 65535
            error = abs(restored - weight)
            changed += error != 0
            max_error = max(max_error, error)
    return {'weight_storage': weight_format, 'slot_storage': formats[9],
            'maximum_slot': max(max(row) for row in slots),
            'active_maximum_slot': max((slot for ws, ss in zip(weights, slots)
                                        for w, slot in zip(ws, ss) if w > 0), default=0),
            'weight_sum_min': min(map(sum, weights)), 'weight_sum_max': max(map(sum, weights)),
            'u16_quantization_changed_components': changed,
            'u16_quantization_max_added_error': max_error}


def inspect(manifest_path: Path, contract: dict[str, Any]) -> dict[str, Any]:
    raw_manifest = manifest_path.read_bytes()
    expected_hash = contract.get('raw_manifest_sha256')
    if expected_hash is not None and hashlib.sha256(raw_manifest).hexdigest() != expected_hash:
        raise ValueError('Raw manifest identity mismatch')
    data = json.loads(raw_manifest.decode('utf-8-sig'))
    if contract.get('schema') != 1 or data.get('schema') != 'renderdoc-vsin-raw-v1':
        raise ValueError('Unsupported contract/raw-export schema')
    if any(data[key] != contract[key] for key in ('frame', 'api')):
        raise ValueError('Different capture frame/API')
    if set(data['events']) != set(contract['events']) or not data['events']:
        raise ValueError('Missing/unexpected event')
    root = manifest_path.resolve().parent
    report: dict[str, Any] = {'ok': True, 'rendering_certified': False,
                              'scope': 'native bytes, input locations, index span and storage statistics only',
                              'frame': data['frame'], 'files_checked': 0, 'events': {}}
    for event, record in data['events'].items():
        expected = contract['events'][event]
        if any(record[key] != expected[key] for key in ('part', 'shader', 'vertices', 'indices')):
            raise ValueError('Draw identity/count changed: ' + event)
        count = record['vertices']
        if count <= 0 or record['indices'] <= 0:
            raise ValueError('Empty draw: ' + event)
        inputs = locations(record)
        if {str(k) for k in inputs} != set(expected['formats']):
            raise ValueError('Input locations changed: ' + event)
        payloads, formats = {}, {}
        for location, name in inputs.items():
            entry = record['inputs'][name]
            fmt = entry['format']
            formats[location] = fmt['name']
            components = re.findall(r'[RGBA](\d+)', fmt['name'])
            width = fmt['compByteWidth']
            stride = fmt['stride']
            if (fmt['name'] != expected['formats'][str(location)] or len(components) != fmt['compCount']
                    or any(int(bits) != width * 8 for bits in components)
                    or stride != fmt['compCount'] * width):
                raise ValueError('Input format changed: ' + event + ':' + str(location))
            blob = local_file(root, entry['file']).read_bytes()
            if len(blob) != count * stride or hashlib.sha256(blob).hexdigest() != entry['sha256']:
                raise ValueError('Input byte/hash mismatch: ' + entry['file'])
            first_vertex = record['ib_min'] + record['base_vertex'] + record['vertex_offset']
            first_byte = entry['buffer_offset'] + first_vertex * entry['buffer_stride'] + entry['offset']
            if first_vertex < 0 or first_byte != entry['first_byte']:
                raise ValueError('Input address mismatch: ' + entry['file'])
            if entry['buffer_stride'] == 0 and blob != blob[:stride] * count:
                raise ValueError('Zero-stride constant stream was not replicated')
            payloads[location] = blob
            report['files_checked'] += 1
        stride = record['index_binding']['index_stride']
        if stride not in (1, 2, 4):
            raise ValueError('Unsupported index width')
        index_data = local_file(root, record['ib_file']).read_bytes()
        if len(index_data) != record['indices'] * stride:
            raise ValueError('Index size mismatch')
        indices = [value[0] for value in struct.iter_unpack('<' + {1: 'B', 2: 'H', 4: 'I'}[stride], index_data)]
        if min(indices) != record['ib_min'] or max(indices) - min(indices) + 1 != count:
            raise ValueError('Index span mismatch')
        report['events'][event] = {'part': record['part'], 'vertices': count,
                                  'position_rest_same_bytes': payloads[0] == payloads[5],
                                  'skin': skin_stats(payloads, formats)}
    return report


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('manifest', type=Path)
    parser.add_argument('contract', type=Path)
    parser.add_argument('--output', type=Path)
    args = parser.parse_args(argv)
    report = inspect(args.manifest, json.loads(args.contract.read_text('utf-8-sig')))
    text = json.dumps(report, ensure_ascii=False, indent=2) + '\n'
    if args.output:
        with args.output.open('x', encoding='utf-8', newline='\n') as stream:
            stream.write(text)
    print(text, end='')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
