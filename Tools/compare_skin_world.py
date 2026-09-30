"""Offline per-vertex contract: raw capture skinning THEN column-major instance.

No camera, silhouette, image alignment or gain fitting. Origin-shifted world
coordinates are compared in metres; threshold defaults to 50 micrometres.
Requires the previously verified identical vertex order/topology.
"""
import argparse
import hashlib
import json
from pathlib import Path
import numpy as np


def evaluate_world(positions, weights, slots, palette, instance_column_major):
    positions, weights, palette = [np.asarray(x, dtype=np.float64) for x in (positions, weights, palette)]
    slots = np.asarray(slots, dtype=np.int64)
    instance = np.asarray(instance_column_major, dtype=np.float64).reshape(4, 4).T
    if positions.ndim != 2 or positions.shape[1] != 3 or weights.shape != (len(positions), 4) or slots.shape != weights.shape:
        raise ValueError('Invalid vertex/weight/slot dimensions')
    if palette.ndim != 3 or palette.shape[1:] != (3, 4) or np.any(slots < 0) or np.any(slots >= len(palette)):
        raise ValueError('Invalid palette/slots')
    if not all(np.isfinite(x).all() for x in (positions, weights, palette, instance)):
        raise ValueError('Non-finite input')
    skin = (palette[slots] * weights[:, :, None, None]).sum(axis=1)
    model = (skin @ np.c_[positions, np.ones(len(positions))][:, :, None])[:, :, 0]
    # Translation is the capture scene origin; subtract it rather than fitting.
    return model @ instance[:3, :3].T


def compare_vertices(actual, expected, tolerance):
    actual, expected = np.asarray(actual, dtype=float), np.asarray(expected, dtype=float)
    if tolerance <= 0 or not np.isfinite(tolerance) or actual.shape != expected.shape or actual.ndim != 2 or actual.shape[1] != 3 or not len(actual):
        raise ValueError('Invalid comparison shape/tolerance')
    if not np.isfinite(actual).all() or not np.isfinite(expected).all():
        raise ValueError('Non-finite vertices')
    error = np.linalg.norm(actual - expected, axis=1)
    return dict(vertices=len(actual), mean_m=float(error.mean()), p95_m=float(np.percentile(error, 95)),
                max_m=float(error.max()), threshold_m=tolerance, **{'pass': bool(error.max() <= tolerance)})


def run():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--pose', type=Path, required=True)
    parser.add_argument('--current', type=Path, required=True)
    parser.add_argument('--out', type=Path, required=True)
    args = parser.parse_args()
    if args.out.exists():
        raise FileExistsError(args.out)
    manifest = json.loads((args.pose/'manifest.json').read_text())
    current = json.loads(args.current.read_text())
    report = {'contract': 'weighted 3x4 skinning -> column-major instance rotation; scene origin removed',
              'scope': 'body+face positions only, not lighting/color/other parts', 'parts': {},
              'current_sha256': hashlib.sha256(args.current.read_bytes()).hexdigest()}
    for event, metadata in manifest['events'].items():
        part = metadata['part']
        if part not in ('body', 'face'):
            continue
        selected = [r for r in current if r['name'].endswith('_'+part+'_01_lod0')]
        if len(selected) != 1:
            raise ValueError('Missing/ambiguous current part: '+part)
        files = metadata['files']
        positions = np.fromfile(args.pose/files['positions'], dtype='<f4').reshape(-1, 3)
        raw = np.fromfile(args.pose/files['skin'], dtype=np.uint8).reshape(-1, 12)
        weights = raw[:, :8].copy().view('<u2').reshape(-1, 4) / 65535.
        slots = raw[:, 8:]
        bones = json.loads((args.pose/files['bones']).read_text())['slots']
        palette = np.zeros((256, 3, 4))
        if not set(np.unique(slots)).issubset({int(s) for s in bones}):
            raise ValueError('Palette missing skin slots')
        for slot, rows in bones.items():
            palette[int(slot)] = rows
        expected = evaluate_world(positions, weights, slots, palette, metadata['instance_child0'])
        result = compare_vertices(selected[0]['vertices'], expected, 5e-5)
        result['event'] = int(event)
        result['input_sha256'] = {name: hashlib.sha256((args.pose/files[name]).read_bytes()).hexdigest()
                                  for name in ('positions', 'skin', 'bones')}
        report['parts'][part] = result
    report['pass'] = set(report['parts']) == {'body', 'face'} and all(p['pass'] for p in report['parts'].values())
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(report, indent=2), encoding='utf-8')
    print(json.dumps(report, indent=2))
    return 0 if report['pass'] else 1


if __name__ == '__main__':
    raise SystemExit(run())
