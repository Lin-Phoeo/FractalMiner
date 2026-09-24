"""True-skinning-model verification for the frame-6411 character draws.

Model recovered from the vertex shaders (shader-22249.txt body / 37670 face):
  palette record = per-INSTANCE (index = InstanceIndex, struct28 256B)
    child0  @0   float4x4 instance world transform (col3 = translation)
    child1.w@76  u32 flags (bit5 set + other bits -> SSBO skinning path)
    child2.x@80  u32 base1 = SSBO float4 offset (+3) of bone matrices
    child2.y@84  u32 base2 (prev frame)
  SSBO (set0/binding18, float4 array): bone b rows at base1 + 3*b .. +2,
  blended by vertex weights; world = child0 * skinned - camOffset(@704 set0
  binding12); clip = viewProj(@512) * world.

Run with qrenderdoc --python; ENDFIELD_CAPTURE_PATH / ENDFIELD_CAPTURE_OUTPUT /
ENDFIELD_TOOLS_PATH. Only complete.json indicates success.
"""
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
PERFRAME_OFF = 549184  # set0 binding12 uniforms26 in ResourceId::864


def run():
    capture = Path(os.environ['ENDFIELD_CAPTURE_PATH']).resolve()
    output = Path(os.environ['ENDFIELD_CAPTURE_OUTPUT']).resolve()
    validate_paths(capture, output)
    write_new_json(output / 'started.json', dict(capture=str(capture)))
    cap = controller = None
    try:
        cap, controller = open_controller(rd, capture)
        rid864 = next(b.resourceId for b in controller.GetBuffers()
                      if str(b.resourceId) == 'ResourceId::864')
        report = {}
        for event_id, part in EVENTS:
            controller.SetFrameEvent(event_id, True)
            state = controller.GetPipelineState()
            entry = {'part': part}
            ssbo_info = None
            for r in state.GetReadOnlyResources(rd.ShaderStage.Vertex):
                if r.bind == 18 and r.descriptorSet == 0:
                    ssbo_info = r
            if ssbo_info is not None:
                ssbo_rid = ssbo_info.resourceId
            else:
                # API does not enumerate the SSBO here; the only buffer large
                # enough for base1 ~272k float4s is the 63MB arena.
                ssbo_rid = next(b.resourceId for b in controller.GetBuffers()
                                if str(b.resourceId) == 'ResourceId::13774')
            entry['ssbo'] = {'resource': str(ssbo_rid)}
            perframe = as_bytes(controller.GetBufferData(rid864, PERFRAME_OFF, 1312))
            cam = struct.unpack_from('<3f', perframe, 704)
            entry['cam_offset'] = [round(x, 3) for x in cam]
            rec = as_bytes(controller.GetBufferData(rid864, PAL_OFF[event_id], 256))
            child0 = list(struct.unpack_from('<16f', rec, 0))
            flags = struct.unpack_from('<I', rec, 76)[0]
            base1 = struct.unpack_from('<I', rec, 80)[0] + 3
            entry['flags'] = flags
            entry['ssbo_base1'] = base1
            entry['child0_row3'] = [round(x, 3) for x in child0[12:16]]
            entry['child0_col3'] = [round(child0[3], 3), round(child0[7], 3),
                                    round(child0[11], 3)]
            mesh = controller.GetPostVSData(rd.MeshDataStage.VSIn, 0, 0)
            ib_raw = as_bytes(controller.GetBufferData(
                mesh.indexResourceId, mesh.indexByteOffset,
                mesh.numIndices * mesh.indexByteStride))
            indices = struct.unpack('<{}H'.format(mesh.numIndices), ib_raw)
            ib_min = min(indices)
            count = max(indices) + 1 - ib_min
            vbs = state.GetVBuffers()
            vb0, vb2 = vbs[0], vbs[2]
            pos_raw = as_bytes(controller.GetBufferData(
                vb0.resourceId, vb0.byteOffset + ib_min * vb0.byteStride,
                count * vb0.byteStride))
            stride = vb2.byteStride
            skin_raw = as_bytes(controller.GetBufferData(
                vb2.resourceId, vb2.byteOffset + ib_min * stride, count * stride))
            verts = []
            max_slot = 0
            for v in range(count):
                if stride == 12:
                    vals = struct.unpack_from('<4H4B', skin_raw, v * 12)
                    pairs = [(w / 65535.0, s) for w, s in zip(vals[:4], vals[4:]) if w > 0]
                elif stride == 32:
                    vals = struct.unpack_from('<4f4I', skin_raw, v * 32)
                    pairs = [(w, s) for w, s in zip(vals[:4], vals[4:]) if w > 0 and s < 4096]
                else:
                    (s,) = struct.unpack_from('<I', skin_raw, v * 4)
                    pairs = [(1.0, s)]
                max_slot = max(max_slot, max(s for _, s in pairs))
                px, py, pz = struct.unpack_from('<3f', pos_raw, v * vb0.byteStride)
                verts.append(((px, py, pz), pairs))
            need = (base1 + 3 * (max_slot + 1) + 2) * 16
            ssbo = as_bytes(controller.GetBufferData(ssbo_rid, 0, need + 64))
            entry['max_bone_slot'] = max_slot
            entry['ssbo_float4s_read'] = need // 16
            use_ssbo = (flags & 32) != 0 and (flags & 0xFFFFFFCF) != 0
            entry['use_ssbo'] = use_ssbo
            lo = [1e30] * 3
            hi = [-1e30] * 3
            slo = [1e30] * 3
            shi = [-1e30] * 3
            bad = 0
            for (px, py, pz), pairs in verts:
                if use_ssbo:
                    r = [[0.0] * 4 for _ in range(3)]
                    for w, s in pairs:
                        b = (base1 + 3 * s) * 16
                        for k in range(3):
                            row = struct.unpack_from('<4f', ssbo, b + k * 16)
                            for c in range(4):
                                r[k][c] += w * row[c]
                    mx = r[0][0] * px + r[0][1] * py + r[0][2] * pz + r[0][3]
                    my = r[1][0] * px + r[1][1] * py + r[1][2] * pz + r[1][3]
                    mz = r[2][0] * px + r[2][1] * py + r[2][2] * pz + r[2][3]
                else:
                    mx, my, mz = px, py, pz
                for k, val in enumerate((mx, my, mz)):
                    slo[k] = min(slo[k], val)
                    shi[k] = max(shi[k], val)
                wx = child0[0] * mx + child0[1] * my + child0[2] * mz + child0[3] - cam[0]
                wy = child0[4] * mx + child0[5] * my + child0[6] * mz + child0[7] - cam[1]
                wz = child0[8] * mx + child0[9] * my + child0[10] * mz + child0[11] - cam[2]
                if any(a != a or abs(a) > 1e5 for a in (wx, wy, wz)):
                    bad += 1
                    continue
                for k, val in enumerate((wx, wy, wz)):
                    lo[k] = min(lo[k], val)
                    hi[k] = max(hi[k], val)
            entry['model_box'] = (None if slo[0] > shi[0] else {
                'size': [round(shi[k] - slo[k], 3) for k in range(3)],
                'lo': [round(x, 2) for x in slo], 'hi': [round(x, 2) for x in shi]})
            entry['world_box'] = (None if lo[0] > hi[0] else {
                'size': [round(hi[k] - lo[k], 3) for k in range(3)],
                'lo': [round(x, 2) for x in lo], 'hi': [round(x, 2) for x in hi]})
            entry['bad'] = bad
            report[str(event_id)] = entry
        write_new_json(output / 'trueskin.json', report)
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
