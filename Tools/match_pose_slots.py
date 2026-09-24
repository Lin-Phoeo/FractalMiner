# -*- coding: utf-8 -*-
"""Vote capture skin-slot -> Unity bone mapping by direct vertex-order match.

The pose-full-01 export (verified chain) and _typhoea_model_data.json have
identical per-part vertex counts; if the vertex ORDER also matches (checked
by position distance under axis-convention candidates), each capture vertex
pairs 1:1 with a Unity vertex, and slot<->bone votes come from pairing the
two weight vectors per vertex.

Outputs slot_vote.json: per part, per slot -> {bone_index, bone_name, share,
paired_vertices}.
"""
import json
import struct
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
EXPORT = ROOT / 'Validation' / 'Captures' / 'tifuluosi-front-20260917' / 'pose-full-01'
MODEL = ROOT / 'Assets' / 'Typhoeus' / '_typhoea_model_data.json'

PARTS = [(776, 'iris', 'S_actor_typhoea_iris_01_lod0'),
         (786, 'body', 'S_actor_typhoea_body_01_lod0'),
         (835, 'cloth_01', 'S_actor_typhoea_cloth_01_lod0'),
         (850, 'cloth_02', 'S_actor_typhoea_cloth_02_lod0'),
         (860, 'face', 'S_actor_typhoea_face_01_lod0'),
         (875, 'hair', 'S_actor_typhoea_hair_01_lod0')]

# axis candidates mapping capture raw (x,y,z) -> unity (x,y,z)
CANDIDATES = {
    'identity': lambda x, y, z: (x, y, z),
    'swapYZ': lambda x, y, z: (x, z, y),
    'swapYZ_negZ': lambda x, y, z: (x, z, -y),
    'swapYZ_negY': lambda x, y, z: (x, -z, y),
    'negX': lambda x, y, z: (-x, y, z),
    'negX_swapYZ': lambda x, y, z: (-x, z, y),
}


def load_positions(path, count):
    data = path.read_bytes()
    return [struct.unpack_from('<3f', data, i * 12) for i in range(count)]


def main():
    model = json.load(open(str(MODEL), encoding='utf-8'))
    bone_names = [b['name'] for b in model['bones']]
    meshes = {m['name']: m for m in model['meshes']}
    result = {}
    for event_id, part, mesh_name in PARTS:
        mesh = meshes[mesh_name]
        uv = mesh['vertices']
        n = len(uv) // 3
        upos = [(uv[3 * i], uv[3 * i + 1], uv[3 * i + 2]) for i in range(n)]
        cpos = load_positions(EXPORT / '{}-{}-positions.bin'.format(event_id, part), n)
        # pick axis convention on the first 200 verts
        best = None
        for name, f in CANDIDATES.items():
            tot = 0.0
            for i in range(min(200, n)):
                cx, cy, cz = f(*cpos[i])
                ux, uy, uz = upos[i]
                tot += (cx - ux) ** 2 + (cy - uy) ** 2 + (cz - uz) ** 2
            if best is None or tot < best[1]:
                best = (name, tot)
        conv_name = best[0]
        f = CANDIDATES[conv_name]
        max_d2 = 0.0
        for i in range(n):
            cx, cy, cz = f(*cpos[i])
            ux, uy, uz = upos[i]
            d2 = (cx - ux) ** 2 + (cy - uy) ** 2 + (cz - uz) ** 2
            max_d2 = max(max_d2, d2)
        entry = {'mesh': mesh_name, 'verts': n, 'axis': conv_name,
                 'max_pos_err': max_d2 ** 0.5}
        # votes
        skin = (EXPORT / '{}-{}-skin.bin'.format(event_id, part)).read_bytes()
        bwi = mesh['boneWeightIndices']
        bwv = mesh['boneWeightValues']
        mesh_bones = mesh['bones']  # local slot -> global bone index
        per_vertex = len(bwi) // n
        votes = {}   # slot -> {bone_idx: weight_sum}
        paired = {}
        for i in range(n):
            cw, cs = [], []
            vals = struct.unpack_from('<4H4B', skin, i * 12)
            for w, s in zip(vals[:4], vals[4:]):
                if w > 0:
                    cw.append((w / 65535.0, s))
            uw, ub = [], []
            for k in range(per_vertex):
                w = bwv[i * per_vertex + k]
                if w > 0:
                    uw.append(w)
                    ub.append(mesh_bones[bwi[i * per_vertex + k]])
            # pair by rank order of weights (both sorted desc)
            cw.sort(key=lambda t: -t[0])
            order = sorted(range(len(uw)), key=lambda k: -uw[k])
            for rank, (w, s) in enumerate(cw):
                if rank >= len(order):
                    break
                b = ub[order[rank]]
                votes.setdefault(s, {}).setdefault(b, 0.0)
                votes[s][b] += min(w, uw[order[rank]])
                paired.setdefault(s, 0)
                paired[s] += 1
        slot_map = {}
        for s, bv in sorted(votes.items()):
            total = sum(bv.values())
            b, w = max(bv.items(), key=lambda t: t[1])
            slot_map[str(s)] = {
                'bone_index': b, 'bone_name': bone_names[b],
                'share': round(w / total, 4),
                'runner_up': sorted(((bone_names[k2], round(v2 / total, 4))
                                     for k2, v2 in bv.items() if k2 != b),
                                    key=lambda t: -t[1])[:2],
                'paired_vertices': paired[s],
            }
        entry['slots'] = slot_map
        result[str(event_id)] = entry
        print('{} {}: axis={} max_err={:.5f} slots={}'.format(
            event_id, part, conv_name, entry['max_pos_err'], len(slot_map)))
    out = EXPORT / 'slot_vote.json'
    json.dump(result, open(str(out), 'w', encoding='utf-8'), ensure_ascii=False, indent=1)
    print('wrote', out)


if __name__ == '__main__':
    sys.exit(main())
