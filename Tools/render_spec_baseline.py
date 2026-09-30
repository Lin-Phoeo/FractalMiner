"""Versioned offline evidence seals. Hash integrity is NOT shader equivalence.

snapshot writes a new manifest only, never source/docs/game assets. verify is
read-only. Approval still requires a recorded human/source review; this tool
deliberately never labels a snapshot as an approved official specification.
"""
import argparse
import hashlib
import json
import re
from pathlib import Path, PurePosixPath, PureWindowsPath
from typing import Any


def resolve_path(roots, name, relative):
    if name not in roots:
        raise ValueError('Unknown root: ' + name)
    relative = relative.replace('\\', '/')
    posix = PurePosixPath(relative)
    windows = PureWindowsPath(relative)
    if posix.is_absolute() or windows.drive or '..' in posix.parts:
        raise ValueError('Path escapes root: ' + relative)
    root = Path(roots[name]).resolve()
    path = (root / relative).resolve()
    if not path.is_relative_to(root):
        raise ValueError('Resolved path escapes root: ' + relative)
    return path


def digest_payload(payload: dict[str, Any]) -> str:
    content = {key: value for key, value in payload.items() if key != 'digest'}
    raw = json.dumps(content, sort_keys=True, ensure_ascii=False, separators=(',', ':')).encode('utf-8')
    return hashlib.sha256(raw).hexdigest()


def file_record(path: Path, root_name: str, root: Path) -> dict[str, Any]:
    digest = hashlib.sha256()
    header = b''
    size = 0
    with path.open('rb') as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b''):
            if not header:
                header = chunk[:2048]
            digest.update(chunk)
            size += len(chunk)
    keywords = re.search(r'^// Keywords:\s*([^\r\n]*)', header.decode('utf-8', errors='replace'), re.MULTILINE)
    return {'root': root_name, 'path': path.relative_to(root.resolve()).as_posix(),
            'bytes': size, 'sha256': digest.hexdigest(),
            'keywords': keywords.group(1).split() if keywords else []}


def validate_plan(plan):
    if plan.get('schema') != 1 or not plan.get('baseline') or not plan.get('scope'):
        raise ValueError('Invalid baseline schema/identity/scope')
    for field in ('groups', 'contracts'):
        items = plan.get(field, [])
        ids = [item['id'] for item in items]
        if not ids or len(ids) != len(set(ids)):
            raise ValueError('Empty or duplicate ' + field)
    contracts = {item['id'] for item in plan['contracts']}
    for item in plan['contracts']:
        dimensions = item.get('dimensions', {})
        if not dimensions or any(value not in ('verified', 'pending', 'not-applicable')
                                 for value in dimensions.values()):
            raise ValueError('Invalid contract dimensions: ' + item['id'])
        if not isinstance(item.get('remaining'), list):
            raise TypeError('Missing remaining questions list: ' + item['id'])
    anchors = plan.get('anchors', [])
    if len({item['id'] for item in anchors}) != len(anchors):
        raise ValueError('Duplicate anchors')
    for item in anchors:
        if item['contract'] not in contracts or not item.get('literal'):
            raise ValueError('Invalid anchor: ' + item['id'])


def inventory(group, roots):
    root = resolve_path(roots, group['root'], '.')
    paths = set()
    for pattern in group['patterns']:
        resolve_path(roots, group['root'], pattern)  # Validate the glob before expanding it.
        for path in root.glob(pattern):
            if path.is_file():
                path = resolve_path(roots, group['root'], path.relative_to(root).as_posix())
                paths.add(path.relative_to(root).as_posix())
    return sorted(paths)


def anchor_matches(anchor, roots):
    path = resolve_path(roots, anchor['root'], anchor['path'])
    if not path.is_file():
        return False
    # Whitespace is formatting; operators, swizzles and literal values are not.
    return re.sub(r'\s+', '', anchor['literal']) in re.sub(r'\s+', '', path.read_text('utf-8-sig'))


def snapshot(plan: dict[str, Any], roots: dict[str, Path]) -> dict[str, Any]:
    validate_plan(plan)
    files = {}
    groups = []
    for group in plan['groups']:
        names = inventory(group, roots)
        if not names:
            raise ValueError('Empty inventory: ' + group['id'])
        groups.append(dict(group, files=names))
        for name in names:
            key = group['root'], name
            if key not in files:
                path = resolve_path(roots, *key)
                files[key] = file_record(path, key[0], Path(roots[key[0]]))
    for anchor in plan.get('anchors', []):
        if (anchor['root'], anchor['path']) not in files:
            raise ValueError('Unsealed anchor file: ' + anchor['id'])
        if not anchor_matches(anchor, roots):
            raise ValueError('Source anchor mismatch: ' + anchor['id'])
    manifest: dict[str, Any] = dict(plan, groups=groups, files=[files[key] for key in sorted(files)],
                                    approval='evidence-only')
    manifest['digest'] = digest_payload(manifest)
    return manifest


def verify(manifest: dict[str, Any], roots: dict[str, Path]) -> dict[str, Any]:
    validate_plan(manifest)
    errors = []
    if manifest.get('digest') != digest_payload(manifest):
        errors.append('manifest-digest')
    files = {(item['root'], item['path']): item for item in manifest['files']}
    if len(files) != len(manifest['files']):
        errors.append('duplicate-file-record')
    for key, record in files.items():
        path = resolve_path(roots, *key)
        if not path.is_file():
            errors.append('missing:' + ':'.join(key))
        elif file_record(path, key[0], Path(roots[key[0]])) != record:
            errors.append('changed:' + ':'.join(key))
    for group in manifest['groups']:
        if inventory(group, roots) != group['files']:
            errors.append('inventory:' + group['id'])
        for name in group['files']:
            if (group['root'], name) not in files:
                errors.append('unsealed:' + group['root'] + ':' + name)
    for anchor in manifest.get('anchors', []):
        if not anchor_matches(anchor, roots):
            errors.append('anchor:' + anchor['id'])
    pending = []
    for contract in manifest['contracts']:
        pending.extend(contract['id'] + ':' + name for name, status in contract['dimensions'].items()
                       if status == 'pending')
        if contract['remaining'] and not any(status == 'pending' for status in contract['dimensions'].values()):
            pending.append(contract['id'] + ':remaining-questions')
    return {'baseline': manifest['baseline'], 'files': len(files),
            'anchors': len(manifest.get('anchors', [])), 'integrity_ok': not errors,
            'complete': not errors and not pending, 'approval': manifest['approval'],
            'errors': errors, 'pending': pending,
            'note': 'Hash/anchor checks are provenance guards, not mathematical or runtime equivalence proofs.'}


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('command', choices=('snapshot', 'verify'))
    parser.add_argument('input', type=Path)
    parser.add_argument('output', type=Path, nargs='?')
    parser.add_argument('--project-root', type=Path, default=Path(__file__).resolve().parents[1])
    parser.add_argument('--techlib-root', type=Path, default=Path('D:/EndfieldTechLib'))
    parser.add_argument('--capture-root', type=Path, default=Path('C:/Users/Administrator/Downloads'))
    parser.add_argument('--require-complete', action='store_true')
    args = parser.parse_args(argv)
    roots = {'project': args.project_root, 'techlib': args.techlib_root, 'capture': args.capture_root}
    data = json.loads(args.input.read_text('utf-8-sig'))
    if args.command == 'snapshot':
        if args.output is None:
            parser.error('snapshot requires a NEW output file')
        manifest = snapshot(data, roots)
        with args.output.open('x', encoding='utf-8', newline='\n') as stream:
            json.dump(manifest, stream, ensure_ascii=False, indent=2)
            stream.write('\n')
        result = verify(manifest, roots)
    else:
        result = verify(data, roots)
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 1 if not result['integrity_ok'] else (2 if args.require_complete and not result['complete'] else 0)


if __name__ == '__main__':
    raise SystemExit(main())
