"""Frame-6411 full pose export (VERIFIED skinning chain, pose-screentruth-03).

Chain (from shader-22249/37670 disassembly, 100% NDC-inside + silhouette overlay):
  palette cbuffer (set2/binding0, per-event ring offset) = per-INSTANCE records
  (struct28, 256B): child0 instance transform (placement at m[12..14]),
  child1.w @76 flags (bit5 + count bits -> SSBO path), child2.x @80 u32 = SSBO
  float4 base (+3) of this draw's bone block.
  SSBO = ResourceId::245 (set0/binding18): bone b matrix = 3 float4 rows at
  (base1 + 3*b) * 16.  v = sum_i w_i * rows(b_i) x pos4      (model space)
  inst = v + child0[12..14] - cam(@704 of set0/binding12)    (camera-relative)
  clip = (inst,1) x ViewProj(@512, row-vector).

Skin streams (exact VB bindings, no content scan):
  iris(776): slot2 stride 4  = u32 bone slot (1 influence)
  body(786)/cloth_02(850)/face(860)/hair(875): stride 12 = 4x u16unorm w + 4x u8 slot
  cloth_01(835): stride 32 = 4x f32 w + 4x u32 slot

Exports per event: positions.bin (3xf32 bind), skin.bin (canonical 4x u16 w +
4x u8 slot per vertex), ib.bin (u16), bones.json (per used slot: 3x4 matrix),
plus manifest.json (cam, viewProj, instance transform, bases, layouts).
Only complete.json indicates success.
"""
import json
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
PERFRAME_OFF = 549184
SSBO_NAME = 'ResourceId::245'


def run():
    capture = Path(os.environ['ENDFIELD_CAPTURE_PATH']).resolve()
    output = Path(os.environ['ENDFIELD_CAPTURE_OUTPUT']).resolve()
    validate_paths(capture, output)
    write_new_json(output / 'started.json', dict(capture=str(capture)))
    cap = controller = None
    try:
        cap, controller = open_controller(rd, capture)
        if controller.GetFrameInfo().frameNumber != 6411:
            raise ValueError('pose export only reviewed for front frame 6411')
        rid864 = next(b.resourceId for b in controller.GetBuffers()
                      if str(b.resourceId) == 'ResourceId::864')
        rid245 = next(b.resourceId for b in controller.GetBuffers()
                      if str(b.resourceId) == SSBO_NAME)
        ssbo = as_bytes(controller.GetBufferData(rid245, 0, 8413184))
        manifest = {'frame': 6411, 'events': {}}
        for event_id, part in EVENTS:
            controller.SetFrameEvent(event_id, True)
            state = controller.GetPipelineState()
            perframe = as_bytes(controller.GetBufferData(rid864, PERFRAME_OFF, 1312))
            cam = struct.unpack_from('<3f', perframe, 704)
            vp = struct.unpack_from('<16f', perframe, 512)
            rec = as_bytes(controller.GetBufferData(rid864, PAL_OFF[event_id], 256))
            child0 = list(struct.unpack_from('<16f', rec, 0))
            flags = struct.unpack_from('<I', rec, 76)[0]
            base1 = struct.unpack_from('<I', rec, 80)[0] + 3
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
            positions = bytearray(count * 12)
            skin_out = bytearray(count * 12)
            used = set()
            for v in range(count):
                positions[v * 12:(v + 1) * 12] = \
                    pos_raw[v * vb0.byteStride:v * vb0.byteStride + 12]
                if stride == 12:
                    vals = struct.unpack_from('<4H4B', skin_raw, v * 12)
                    ws, ss = vals[:4], vals[4:]
                elif stride == 32:
                    vals = struct.unpack_from('<4f4I', skin_raw, v * 32)
                    ws = tuple(int(round(w * 65535.0)) for w in vals[:4])
                    ss = tuple(min(s, 255) for s in vals[4:])
                else:
                    (s,) = struct.unpack_from('<I', skin_raw, v * 4)
                    ws, ss = (65535, 0, 0, 0), (min(s, 255), 0, 0, 0)
                struct.pack_into('<4H4B', skin_out, v * 12, *(list(ws) + list(ss)))
                for w, s in zip(ws, ss):
                    if w > 0:
                        used.add(s)
            bones = {}
            for s in sorted(used):
                b = (base1 + 3 * s) * 16
                rows = [list(struct.unpack_from('<4f', ssbo, b + k * 16)) for k in range(3)]
                bones[str(s)] = rows
            prefix = '{}-{}'.format(event_id, part)
            with (output / (prefix + '-positions.bin')).open('xb') as f:
                f.write(bytes(positions))
            with (output / (prefix + '-skin.bin')).open('xb') as f:
                f.write(bytes(skin_out))
            with (output / (prefix + '-ib.bin')).open('xb') as f:
                f.write(ib_raw)
            write_new_json(output / (prefix + '-bones.json'), {
                'base1': base1, 'slots': bones})
            manifest['events'][str(event_id)] = {
                'part': part, 'vertices': count, 'indices': mesh.numIndices,
                'ib_min': ib_min, 'skin_stride_src': stride,
                'palette_offset': PAL_OFF[event_id],
                'flags': flags, 'ssbo_base1': base1,
                'instance_child0': child0,
                'cam_offset': list(cam), 'view_proj': list(vp),
                'used_slots': sorted(used),
                'files': {'positions': prefix + '-positions.bin',
                          'skin': prefix + '-skin.bin',
                          'ib': prefix + '-ib.bin',
                          'bones': prefix + '-bones.json'},
            }
        write_new_json(output / 'manifest.json', manifest)
        write_new_json(output / 'complete.json', dict(status='ok', phase='full-export',
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
