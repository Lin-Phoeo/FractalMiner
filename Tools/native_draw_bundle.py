"""Byte-exact native draw handoff, not a Unity Mesh or rendering certificate.

Build only into a NEW sibling/outside directory. Preserve every logical input,
native format, source address and original index value. No mesh operations,
normalization, float JSON conversion, coordinate conversion or game dependency.
An incomplete write has no completion marker and is rejected by readers.
"""
import argparse
import hashlib
import importlib.util
import json
from pathlib import Path
from typing import Any

AUDIT_PATH = Path(__file__).resolve().parents[1] / 'docs/render-baseline/v2/tools/raw_draw_inputs.py'
SPEC = importlib.util.spec_from_file_location('sealed_native_input_audit_v2', AUDIT_PATH)
if SPEC is None or SPEC.loader is None:
    raise ImportError('Frozen v2 native checker unavailable')
audit = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(audit)

SCHEMA = 'endfield-native-draw-bundle-v1'
COMPLETE_SCHEMA = 'endfield-native-draw-complete-v1'
RESERVED = {'manifest.json', 'complete.json', 'source-manifest.json', 'source-contract.json'}


def sha(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


def parse(raw: bytes) -> dict[str, Any]:
    def unique(pairs):
        result = {}
        for key, value in pairs:
            if key in result:
                raise ValueError('Duplicate JSON key: ' + key)
            result[key] = value
        return result
    return json.loads(raw.decode('utf-8-sig'), object_pairs_hook=unique)


def encode(value: dict[str, Any]) -> bytes:
    return (json.dumps(value, ensure_ascii=False, indent=2, allow_nan=False) + '\n').encode('utf-8')


def capture_files(root: Path, source: dict[str, Any]) -> dict[str, bytes]:
    blobs = {}
    for event, record in source['events'].items():
        names = [entry['file'] for entry in record['inputs'].values()] + [record['ib_file']]
        for name in names:
            if name.lower() in RESERVED:
                raise ValueError('Reserved payload filename: ' + name)
            blobs[name] = audit.local_file(root, name).read_bytes()
        for entry in record['inputs'].values():
            if any(entry[key] < 0 for key in ('buffer_offset', 'buffer_stride', 'offset', 'first_byte')):
                raise ValueError('Negative native input address/stride')
            if sha(blobs[entry['file']]) != entry['sha256']:
                raise ValueError('Input hash changed while reading')
        binding, draw = record['index_binding'], record['draw']
        if (draw['event'] != int(event)
                or draw['index_count'] != record['indices'] or draw['instances'] <= 0):
            raise ValueError('Index draw identity/count mismatch')
        if (draw['index_offset'] < 0 or binding['buffer_offset'] < 0
                or binding['first_byte'] != binding['buffer_offset']
                + draw['index_offset'] * binding['index_stride']):
            raise ValueError('Index address mismatch')
    return blobs


def describe(source_raw: bytes, contract_raw: bytes, blobs: dict[str, bytes], report: dict[str, Any]) -> dict[str, Any]:
    source = parse(source_raw)
    files = dict(blobs, **{'source-manifest.json': source_raw, 'source-contract.json': contract_raw})
    events = {}
    for event, record in source['events'].items():
        draw = {key: value for key, value in record.items() if key != 'inputs'}
        draw['attributes'] = {str(loc): record['inputs'][name]
                              for loc, name in sorted(audit.locations(record).items())}
        events[event] = draw
    return {'schema': SCHEMA, 'byte_order': 'little', 'frame': source['frame'], 'api': source['api'],
            'source_manifest_sha256': sha(source_raw), 'contract_sha256': sha(contract_raw),
            'rendering_certified': False, 'mesh_mapping_ready': False,
            'scope': 'lossless native storage and location-address handoff only; no palette, Unity semantic or pass adaptation',
            'events': events, 'input_check': report,
            'files': {name: {'bytes': len(raw), 'sha256': sha(raw)} for name, raw in sorted(files.items())}}


def build(manifest_path: Path, contract_path: Path, output: Path) -> dict[str, Any]:
    manifest_path, contract_path = manifest_path.resolve(), contract_path.resolve()
    output = output.resolve()
    if output.exists():
        raise FileExistsError(output)
    if output.is_relative_to(manifest_path.parent):
        raise ValueError('Output must be outside the immutable source export')
    source_raw, contract_raw = manifest_path.read_bytes(), contract_path.read_bytes()
    source, contract = parse(source_raw), parse(contract_raw)
    if contract.get('raw_manifest_sha256') != sha(source_raw):
        raise ValueError('Transfer requires matching source manifest pin')
    report = audit.inspect(manifest_path, contract)
    blobs = capture_files(manifest_path.parent, source)
    if manifest_path.read_bytes() != source_raw or contract_path.read_bytes() != contract_raw:
        raise ValueError('Source metadata changed while reading')
    metadata = describe(source_raw, contract_raw, blobs, report)
    manifest_raw = encode(metadata)
    # All validation above precedes the first write. Never reuse/delete a partial directory.
    output.mkdir()
    for name, raw in dict(blobs, **{'source-manifest.json': source_raw, 'source-contract.json': contract_raw}).items():
        with (output / name).open('xb') as stream:
            stream.write(raw)
    with (output / 'manifest.json').open('xb') as stream:
        stream.write(manifest_raw)
    # Publish only after revalidating the actual bytes written, including indices.
    validate(output, manifest_raw, metadata)
    with (output / 'complete.json').open('xb') as stream:
        stream.write(encode({'schema': COMPLETE_SCHEMA, 'manifest_sha256': sha(manifest_raw)}))
    return dict(summary(metadata), manifest_sha256=sha(manifest_raw))


def bundle_file(root: Path, name: str) -> Path:
    path = root / name
    if path.is_symlink() or path.is_junction():
        raise ValueError('Bundle links are not allowed')
    return audit.local_file(root, name)


def validate(root: Path, raw: bytes, metadata: dict[str, Any], expected_contract_sha256: str | None = None) -> None:
    if (metadata.get('schema') != SCHEMA or metadata.get('byte_order') != 'little'
            or metadata.get('rendering_certified') is not False or metadata.get('mesh_mapping_ready') is not False):
        raise ValueError('Unknown/certified bundle schema or byte order')
    if expected_contract_sha256 is not None and metadata['contract_sha256'] != expected_contract_sha256:
        raise ValueError('External contract identity mismatch')
    expected_names = set(metadata['files']) | {'manifest.json'}
    if (root / 'complete.json').exists():
        expected_names.add('complete.json')
    if {p.name for p in root.iterdir()} != expected_names:
        raise ValueError('Unexpected/missing bundle entries')
    for name, entry in metadata['files'].items():
        path = bundle_file(root, name)
        if not path.is_file():
            raise ValueError('Non-regular bundle file')
        payload = path.read_bytes()
        if len(payload) != entry['bytes'] or sha(payload) != entry['sha256']:
            raise ValueError('Bundle byte/hash mismatch: ' + name)
    if (root / 'manifest.json').read_bytes() != raw:
        raise ValueError('Bundle metadata changed while reading')
    source_raw = (root / 'source-manifest.json').read_bytes()
    contract_raw = (root / 'source-contract.json').read_bytes()
    if parse(contract_raw).get('raw_manifest_sha256') != sha(source_raw):
        raise ValueError('Transfer requires matching source manifest pin')
    report = audit.inspect(root / 'source-manifest.json', parse(contract_raw))
    blobs = capture_files(root, parse(source_raw))
    if metadata != describe(source_raw, contract_raw, blobs, report):
        raise ValueError('Bundle metadata disagrees with original source records')


def load(root: Path, expected_contract_sha256: str | None = None,
         expected_manifest_sha256: str | None = None) -> dict[str, Any]:
    root = root.resolve()
    completion_path = bundle_file(root, 'complete.json')
    manifest_path = bundle_file(root, 'manifest.json')
    marker = parse(completion_path.read_bytes())
    raw = manifest_path.read_bytes()
    if expected_manifest_sha256 is not None and sha(raw) != expected_manifest_sha256:
        raise ValueError('External manifest identity mismatch')
    if marker != {'schema': COMPLETE_SCHEMA, 'manifest_sha256': sha(raw)}:
        raise ValueError('Incomplete or changed bundle manifest')
    metadata = parse(raw)
    validate(root, raw, metadata, expected_contract_sha256)
    return metadata


def read_stream(root: Path, event: int, location: int) -> bytes:
    metadata = load(root)
    entry = metadata['events'][str(event)]['attributes'][str(location)]
    raw = bundle_file(root.resolve(), entry['file']).read_bytes()
    identity = metadata['files'][entry['file']]
    if len(raw) != identity['bytes'] or sha(raw) != identity['sha256']:
        raise ValueError('Stream changed after loading')
    return raw


def summary(metadata: dict[str, Any]) -> dict[str, Any]:
    return {'ok': True, 'rendering_certified': False, 'mesh_mapping_ready': False,
            'frame': metadata['frame'], 'draws': len(metadata['events']),
            'vertices': sum(draw['vertices'] for draw in metadata['events'].values()),
            'payload_files': len(metadata['files']) - 2,
            'source_manifest_sha256': metadata['source_manifest_sha256'],
            'contract_sha256': metadata['contract_sha256']}


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest='command', required=True)
    make = sub.add_parser('build')
    make.add_argument('manifest', type=Path)
    make.add_argument('contract', type=Path)
    make.add_argument('output', type=Path)
    check = sub.add_parser('verify')
    check.add_argument('bundle', type=Path)
    check.add_argument('--contract-sha256')
    check.add_argument('--manifest-sha256')
    args = parser.parse_args(argv)
    result = (build(args.manifest, args.contract, args.output) if args.command == 'build'
              else summary(load(args.bundle, args.contract_sha256, args.manifest_sha256)))
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
