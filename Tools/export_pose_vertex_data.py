"""Frame-6411 character draw vertex-data export (pose slot<->bone evidence).

Phase extract (default): for each character draw, export the per-vertex
position stream, the skinning stream (4x u16 weights + 4x u8 palette slot
indices) and the index buffer. The skinning stream is identified by content,
not by API binding names: 12-byte records whose four u16 weights sum to the
UNorm maximum 65535 on almost every record.

Layout evidence (pose-vb-discovery-01/02, body draw event 786):
  stream0: _input0 position 3xf32 @0 (MeshFormat stride 160), _input2 f32 @12
  stream1: _input1 uv 2xf32 @0, _input4 4xs8 @8
  stream2: _input8 weights 4xu16unorm @0, _input9 indices 4xu8 @8   <- target
  stream3: _input5 3xf32 @0, _input6 f32 @12, _input7 f32 @12
  stream4: _input3 4xu8unorm @12

Run with official qrenderdoc --python; set ENDFIELD_CAPTURE_PATH,
ENDFIELD_CAPTURE_OUTPUT (fresh directory), ENDFIELD_TOOLS_PATH (this folder).
Only complete.json indicates success, never qrenderdoc's native exit code.
Python 3.8 compatible for RenderDoc 1.46's embedded runtime.
"""
import json
import os
import struct
import sys
import traceback
from pathlib import Path

tool_root = os.environ.get('ENDFIELD_TOOLS_PATH') or str(Path(__file__).resolve().parent)
sys.path.insert(0, tool_root)
from capture_replay_inventory import open_controller, validate_paths, write_new_json, flatten_actions

EVENTS = [(776, 'iris'), (786, 'body'), (835, 'cloth_01'),
          (850, 'cloth_02'), (860, 'face'), (875, 'hair')]

SKIN_STRIDE = 12          # 4x u16 weights + 4x u8 indices
WEIGHT_SUM_MIN = 65000    # accept tiny float-quantisation slack around 65535
WEIGHT_SUM_MAX = 66000


def as_bytes(data):
    if isinstance(data, (bytes, bytearray)):
        return bytes(data)
    return bytes(bytearray(data))


def weight_sum_ok(buf, records):
    good = 0
    for i in range(records):
        w = struct.unpack_from('<4H', buf, i * SKIN_STRIDE)
        if WEIGHT_SUM_MIN <= sum(w) <= WEIGHT_SUM_MAX:
            good += 1
    return good


def skin_layout(state):
    """Locate the weight/index attribute pair on one vertex-buffer slot.
    Returns (slot, weight_offset, weight_width, index_offset, index_width) or
    None when the draw has no skinning inputs (rigid mesh)."""
    index_attr = None
    for entry in state.GetVertexInputs():
        fmt = entry.format
        if entry.used and fmt.compCount == 4 and fmt.compType == 4:  # CompType.UInt
            index_attr = entry
            break
    if index_attr is None:
        return None
    slot = index_attr.vertexBuffer
    weight_attr = None
    for entry in state.GetVertexInputs():
        fmt = entry.format
        # CompType.UNorm == 2; weights are 4-component UNorm on the same slot
        if entry.used and entry.vertexBuffer == slot and fmt.compCount == 4 and fmt.compType == 2:
            weight_attr = entry
            break
    if weight_attr is None:
        return None
    return (slot, weight_attr.byteOffset, weight_attr.format.compByteWidth,
            index_attr.byteOffset, index_attr.format.compByteWidth)


def load_palette():
    """Per-event (used-slot set, full 256-slot matrix list) from the reviewed
    palette extraction (pose-palette-01). __file__ is not defined in
    qrenderdoc's exec context, so anchor at the tools path."""
    palette_path = Path(tool_root).parent / \
        'Validation' / 'Captures' / 'tifuluosi-front-20260917' / \
        'pose-palette-01' / 'palette.json'
    data = json.load(open(str(palette_path), encoding='utf-8'))
    used = {}
    mats = {}
    for ev, entry in data.items():
        slots = set()
        for i, m in enumerate(entry['matrices']):
            if m is None:
                continue
            if all(abs(v) < 1e-30 for v in m):
                continue
            if max(abs(a - b) for a, b in zip(m, IDENT)) < 1e-6:
                continue
            slots.add(i)
        used[int(ev)] = slots
        mats[int(ev)] = entry['matrices']
    return used, mats


def build_skin_slice(arena, record_base, ib_min, vertex_count, layout):
    """Canonical 12-byte records for the draw's referenced slice."""
    _, weight_off, weight_w, index_off, index_w = layout
    weight_unpack = {1: '<4B', 2: '<4H', 4: '<4I'}[weight_w]
    index_unpack = {1: '<4B', 2: '<4H', 4: '<4I'}[index_w]
    out = bytearray(vertex_count * SKIN_STRIDE)
    for v in range(vertex_count):
        base = record_base + (ib_min + v) * SKIN_STRIDE
        weights = struct.unpack_from(weight_unpack, arena, base + weight_off)
        indices4 = struct.unpack_from(index_unpack, arena, base + index_off)
        struct.pack_into('<4H4B', out, v * SKIN_STRIDE,
                         *(list(weights) + list(indices4)))
    return out


IDENT = [1.0, 0.0, 0.0, 0.0,
         0.0, 1.0, 0.0, 0.0,
         0.0, 0.0, 1.0, 0.0,
         0.0, 0.0, 0.0, 1.0]


def run_used_slots(buf, record_base, start, count, layout):
    """Slot indices whose weight is non-zero, across records [start, start+count)
    of a candidate run (the draw's referenced slice, indices relative to the
    bound stream)."""
    _, weight_off, weight_w, index_off, index_w = layout
    weight_unpack = {1: '<4B', 2: '<4H', 4: '<4I'}[weight_w]
    index_unpack = {1: '<4B', 2: '<4H', 4: '<4I'}[index_w]
    slots = set()
    for v in range(start, start + count):
        base = record_base + v * SKIN_STRIDE
        weights = struct.unpack_from(weight_unpack, buf, base + weight_off)
        indices4 = struct.unpack_from(index_unpack, buf, base + index_off)
        for w, s in zip(weights, indices4):
            if w > 0:
                slots.add(s)
    return slots


def skinned_bbox(positions, skin, palette_mats, weight_max):
    """Skin the draw slice with the draw's palette (row-vector convention,
    translation in row 3) and return the world-space bounding box. The correct
    stream+palette pairing reproduces the character where it stood; a wrong
    pairing scatters vertices to garbage coordinates."""
    lo = [float('inf')] * 3
    hi = [float('-inf')] * 3
    n = len(positions) // 12
    for v in range(n):
        px, py, pz = struct.unpack_from('<3f', positions, v * 12)
        vals = struct.unpack_from('<4H4B', skin, v * SKIN_STRIDE)
        weights, slots = vals[:4], vals[4:]
        acc = [0.0, 0.0, 0.0]
        for w, s in zip(weights, slots):
            if w == 0:
                continue
            m = palette_mats[s]
            f = w / weight_max
            acc[0] += f * (px * m[0] + py * m[4] + pz * m[8] + m[12])
            acc[1] += f * (px * m[1] + py * m[5] + pz * m[9] + m[13])
            acc[2] += f * (px * m[2] + py * m[6] + pz * m[10] + m[14])
        for k in range(3):
            if not (acc[k] == acc[k]) or abs(acc[k]) > 1e6:
                return None
            lo[k] = min(lo[k], acc[k])
            hi[k] = max(hi[k], acc[k])
    return lo, hi


def bbox_plausible(box):
    """The captured full-body frame has the character standing within a few
    metres of the origin and roughly 2 m tall."""
    if box is None:
        return False
    lo, hi = box
    if not (-20.0 < lo[0] < hi[0] < 20.0 and -5.0 < lo[1] < hi[1] < 6.0
            and -20.0 < lo[2] < hi[2] < 20.0):
        return False
    height = hi[1] - lo[1]
    return 0.2 < height < 3.5


def select_skin_run(arenas, ib_min, vertex_count, layout, palette_slots, runs_cache,
                    max_runs=64):
    """All plausible runs, then the one whose referenced slice
    [ib_min, ib_min+vertex_count) best matches the palette's used slots (IoU).
    Runs are shared per-character streams, so their full length is expected to
    exceed the draw's slice."""
    key = tuple(layout)
    if key not in runs_cache:
        runs_cache[key] = find_skin_runs(arenas, 64, layout, max_runs=max_runs)
    runs = [r for r in runs_cache[key] if r[2] >= ib_min + vertex_count]
    scored = []
    for arena_id, record_base, run_records in runs:
        slots = run_used_slots(arenas[arena_id], record_base, ib_min, vertex_count,
                               layout)
        # Containment, not IoU: the palette cbuffer is shared with a dynamic
        # offset, so its non-trivial slots include stale entries the draw does
        # not reference. The correct stream must have (nearly) every referenced
        # slot inside the palette's used set.
        containment = len(slots & palette_slots) / max(1, len(slots))
        scored.append((containment, len(slots & palette_slots), arena_id,
                       record_base, run_records, len(slots)))
    scored.sort(key=lambda t: (-t[0], -t[1]))
    return scored


def read_arena_buffers(controller, buffers, min_bytes=65536):
    arenas = {}
    for desc in buffers:
        if desc.length < min_bytes:
            continue
        data = as_bytes(controller.GetBufferData(desc.resourceId, 0, desc.length))
        if len(data) == desc.length:
            arenas[str(desc.resourceId)] = data
    return arenas


def find_skin_runs(arenas, vertex_count, layout, max_runs=8):
    """Content-identified skinning stream inside the arena buffers. A run is a
    maximal span of 12-byte records whose 4 UNorm weights sum to the format
    maximum on at least 90% of records (degenerate all-zero vertices may break
    the sum, so short gaps are tolerated). The run must cover at least
    vertex_count records. Returns [(arena_id, record_base, run_records)]."""
    _, weight_off, weight_w, _, _ = layout
    weight_max = (1 << (8 * weight_w)) - 1
    lo, hi = int(weight_max * 0.98), weight_max + 1
    unpack = {1: '<4B', 2: '<4H', 4: '<4I'}[weight_w]
    found = []
    for arena_id, buf in arenas.items():
        n_rec = len(buf) // SKIN_STRIDE
        if n_rec < vertex_count:
            continue
        for base in range(SKIN_STRIDE):
            usable = (len(buf) - base) // SKIN_STRIDE
            if usable < vertex_count:
                continue
            # per-record scan with gap tolerance (fast enough offline)
            run_start = -1
            gap = 0
            total = 0
            good_count = 0
            for i in range(usable):
                w = struct.unpack_from(unpack, buf, base + i * SKIN_STRIDE + weight_off)
                ok = lo <= sum(w) <= hi
                if ok:
                    if run_start < 0:
                        run_start = i
                        total = 0
                        good_count = 0
                    gap = 0
                else:
                    if run_start < 0:
                        continue
                    gap += 1
                    if gap > 4:
                        if total >= vertex_count and good_count >= total * 9 // 10:
                            found.append((arena_id, base + run_start * SKIN_STRIDE, total))
                            if len(found) >= max_runs:
                                return found
                        run_start = -1
                        gap = 0
                        continue
                if run_start >= 0:
                    total += 1
                    if ok:
                        good_count += 1
            if run_start >= 0 and total >= vertex_count and good_count >= total * 9 // 10:
                found.append((arena_id, base + run_start * SKIN_STRIDE, total))
                if len(found) >= max_runs:
                    return found
    return found


def run():
    capture = Path(os.environ['ENDFIELD_CAPTURE_PATH']).resolve()
    output = Path(os.environ['ENDFIELD_CAPTURE_OUTPUT']).resolve()
    validate_paths(capture, output)
    write_new_json(output / 'started.json', dict(capture=str(capture), events=[e for e, _ in EVENTS]))
    cap = controller = None
    try:
        import renderdoc as rd
        cap, controller = open_controller(rd, capture)
        if controller.GetFrameInfo().frameNumber != 6411:
            raise ValueError('pose VB evidence is only reviewed for front frame 6411')

        actions = list(flatten_actions(controller.GetRootActions()))
        buffers = list(controller.GetBuffers())
        # Diagnostic: the content scan relies on GetBuffers() actually listing the
        # mesh streams; record what it offers and whether the MeshFormat ids are in it.
        listed = {str(b.resourceId) for b in buffers}
        write_new_json(output / 'buffers.json', {
            'count': len(buffers),
            'buffers': [{'id': str(b.resourceId), 'bytes': b.length} for b in buffers],
        })
        arenas = read_arena_buffers(controller, buffers)
        write_new_json(output / 'arenas.json', {
            'count': len(arenas),
            'bytes': {k: len(v) for k, v in arenas.items()},
        })
        palette_used, palette_matrices = load_palette()
        runs_cache = {}
        manifest = {'events': {}}
        for event_id, part in EVENTS:
            action = next((a for a in actions if a.eventId == event_id), None)
            if action is None:
                raise ValueError('event {} not found'.format(event_id))
            controller.SetFrameEvent(event_id, True)
            mesh = controller.GetPostVSData(rd.MeshDataStage.VSIn, 0, 0)
            if mesh.indexByteStride != 2:
                raise ValueError('event {}: expected u16 indices, stride={}'.format(
                    event_id, mesh.indexByteStride))

            ib_raw = as_bytes(controller.GetBufferData(
                mesh.indexResourceId, mesh.indexByteOffset,
                mesh.numIndices * mesh.indexByteStride))
            indices = struct.unpack('<{}H'.format(mesh.numIndices), ib_raw)
            ib_min = min(indices)
            vertex_count = max(indices) + 1 - ib_min

            pos_raw = as_bytes(controller.GetBufferData(
                mesh.vertexResourceId,
                mesh.vertexByteOffset + ib_min * mesh.vertexByteStride,
                vertex_count * mesh.vertexByteStride))
            if len(pos_raw) < vertex_count * mesh.vertexByteStride:
                raise RuntimeError('event {}: position stream too short'.format(event_id))
            positions = bytearray(vertex_count * 12)
            for v in range(vertex_count):
                positions[v * 12:(v + 1) * 12] = \
                    pos_raw[v * mesh.vertexByteStride:v * mesh.vertexByteStride + 12]

            state = controller.GetPipelineState()
            layout = skin_layout(state)
            skin_meta = {'skinned': layout is not None}
            if layout is not None:
                skin_meta['layout'] = dict(zip(
                    ('slot', 'weight_offset', 'weight_width', 'index_offset', 'index_width'),
                    layout))
            skin_raw = None
            if layout is not None:
                palette_slots = palette_used.get(event_id, set())
                palette_mats = palette_matrices.get(event_id)
                scored = select_skin_run(arenas, ib_min, vertex_count, layout,
                                         palette_slots, runs_cache)
                # Decisive verification: skin the slice with the draw's own
                # palette; only the correct stream lands on the character.
                chosen = None
                trials = []
                for cand in scored[:8]:
                    _, _, arena_id, record_base, run_records, _ = cand
                    skin_try = build_skin_slice(arenas[arena_id], record_base,
                                                ib_min, vertex_count, layout)
                    box = skinned_bbox(positions, skin_try, palette_mats, 65535.0)
                    trials.append((round(cand[0], 3), arena_id, record_base,
                                   box if box is None else
                                   ([round(x, 3) for x in box[0]],
                                    [round(x, 3) for x in box[1]])))
                    if bbox_plausible(box):
                        chosen = (cand, skin_try, box)
                        break
                if chosen is None:
                    raise RuntimeError('event {}: no skinning run skins onto the '
                                       'character (verts={}): {}'.format(
                                           event_id, vertex_count, trials))
                (cand, skin_raw, box) = chosen
                _, _, arena_id, record_base, run_records, _ = cand
                skin_meta['match'] = {'containment': round(cand[0], 4),
                                      'palette_slots': len(palette_slots),
                                      'skinned_bbox': [[round(x, 4) for x in box[0]],
                                                       [round(x, 4) for x in box[1]]]}
                skin_meta.update({'arena': arena_id, 'record_base': record_base,
                                  'run_records': run_records})

            prefix = '{}-{}'.format(event_id, part)
            with (output / (prefix + '-positions.bin')).open('xb') as f:
                f.write(bytes(positions))
            if skin_raw is not None:
                with (output / (prefix + '-skin.bin')).open('xb') as f:
                    f.write(bytes(skin_raw))
            with (output / (prefix + '-ib.bin')).open('xb') as f:
                f.write(ib_raw)
            manifest['events'][str(event_id)] = {
                'part': part, 'vertices': vertex_count, 'indices': mesh.numIndices,
                'ib_min': ib_min,
                'position_resource': str(mesh.vertexResourceId),
                'position_stride': mesh.vertexByteStride,
                'skin': skin_meta,
                'index_resource': str(mesh.indexResourceId),
                'files': {'positions': prefix + '-positions.bin',
                          'skin': prefix + '-skin.bin' if skin_raw is not None else None,
                          'ib': prefix + '-ib.bin'},
            }
            write_new_json(output / (prefix + '-meta.json'),
                           manifest['events'][str(event_id)])

        write_new_json(output / 'manifest.json', manifest)
        write_new_json(output / 'complete.json', dict(status='ok', phase='extract',
                                                      events=[e for e, _ in EVENTS]))
    except BaseException:
        write_new_json(output / 'error.json', dict(traceback=traceback.format_exc()))
        raise
    finally:
        if controller is not None:
            controller.Shutdown()
        if cap is not None:
            cap.Shutdown()


if __name__ == '__main__':
    try:
        run()
    finally:
        sys.exit()
