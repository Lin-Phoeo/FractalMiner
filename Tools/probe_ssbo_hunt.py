"""Hunt the real bone-matrix SSBO: scan all big buffers at the shader-computed
base offsets (float4 units) and score matrix-likeness (orthonormal rows,
sane translation). Also dumps reflection read-only resource info."""
import math
import os
import struct
import sys
import traceback
from pathlib import Path

tool_root = os.environ.get('ENDFIELD_TOOLS_PATH') or str(Path(__file__).resolve().parent)
sys.path.insert(0, tool_root)
from capture_replay_inventory import open_controller, validate_paths, write_new_json
import renderdoc as rd
from export_pose_vertex_data import as_bytes, EVENTS

PAL_OFF = {776: 741952, 786: 742464, 835: 745280, 850: 746048, 860: 746560, 875: 747328}


def mat_score(buf, f4idx):
    """3 float4s at f4idx -> 1.0 if looks like a rigid 3x4, else 0."""
    b = f4idx * 16
    if b + 48 > len(buf):
        return 0.0, None
    rows = [struct.unpack_from('<4f', buf, b + k * 16) for k in range(3)]
    norms = [math.sqrt(sum(c * c for c in r[:3])) for r in rows]
    if any(n != n or n < 0.5 or n > 2.0 for n in norms):
        return 0.0, None
    if max(abs(r[3]) for r in rows) > 1000.0:
        return 0.0, None
    # orthogonality
    d01 = sum(rows[0][k] * rows[1][k] for k in range(3))
    d02 = sum(rows[0][k] * rows[2][k] for k in range(3))
    d12 = sum(rows[1][k] * rows[2][k] for k in range(3))
    if max(abs(d01), abs(d02), abs(d12)) > 0.1:
        return 0.0, None
    return 1.0, rows


def run():
    capture = Path(os.environ['ENDFIELD_CAPTURE_PATH']).resolve()
    output = Path(os.environ['ENDFIELD_CAPTURE_OUTPUT']).resolve()
    validate_paths(capture, output)
    write_new_json(output / 'started.json', dict(capture=str(capture)))
    cap = controller = None
    try:
        cap, controller = open_controller(rd, capture)
        buffers = [(str(b.resourceId), b.resourceId, b.length)
                   for b in controller.GetBuffers() if b.length >= (1 << 20)]
        report = {'buffers': {}, 'reflection': {}}
        # per-event bases from palette record child2.x
        rid864 = next(rid for name, rid, _ in buffers if name == 'ResourceId::864')
        bases = {}
        for event_id, part in EVENTS:
            controller.SetFrameEvent(event_id, True)
            rec = as_bytes(controller.GetBufferData(rid864, PAL_OFF[event_id], 256))
            bases[event_id] = struct.unpack_from('<I', rec, 80)[0] + 3
            # reflection info
            state = controller.GetPipelineState()
            refl = state.GetShaderReflection(rd.ShaderStage.Vertex)
            ro = []
            for r in refl.readOnlyResources:
                ro.append({'name': r.name,
                           'bindPoint': getattr(r, 'bindPoint', None),
                           'bindCount': getattr(r, 'bindCount', None),
                           'type': str(getattr(r, 'type', '')),
                           'resType': str(getattr(r, 'resType', ''))})
            report['reflection'][str(event_id)] = ro
        report['bases'] = bases
        for name, rid, length in buffers:
            data = as_bytes(controller.GetBufferData(rid, 0, min(length, 6 * 1024 * 1024)))
            scores = {}
            for event_id, base in bases.items():
                s, rows = mat_score(data, base)
                scores[str(event_id)] = s
                if s > 0 and str(event_id) not in report['buffers']:
                    report['buffers'].setdefault(name, {})[str(event_id)] = [
                        [round(x, 4) for x in r] for r in rows]
            if any(v > 0 for v in scores.values()):
                report['buffers'].setdefault(name, {})['scores'] = scores
                report['buffers'][name]['length'] = length
        write_new_json(output / 'hunt.json', report)
        write_new_json(output / 'complete.json', dict(status='ok'))
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
