"""Decisive screen-space verification of the recovered skinning chain.

Chain (from shader-22249.txt):
  v      = sum_i w_i * SSBO245[base1 + 3*bone_i] (3x float4 rows) x pos4
  inst   = child0_3x3 * v + child0_col3 - camOffset(@704)
  clip   = (inst,1) x ViewProj(@512, row-vector conv)
  ndc    = clip.xy / clip.w

Renders a point-cloud overlay onto the official front screenshot per part;
also reports the fraction of vertices landing inside the NDC box.
Runs OUTSIDE qrenderdoc on the exported raw data (see pose-trueskin-03
for the capture-side export); this script expects:
  <output>/raw/<event>-pos.bin      3xf32 per vertex
  <output>/raw/<event>-skin.bin     parsed pairs json lines? no - raw
Actually simpler: this script runs INSIDE qrenderdoc and does everything.
"""
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
PERFRAME_OFF = 549184
SSBO_NAME = 'ResourceId::245'
IMG_W, IMG_H = 1280, 720

COLORS = {776: (255, 60, 60), 786: (255, 255, 255), 835: (80, 200, 255),
          850: (255, 200, 60), 860: (255, 80, 200), 875: (120, 255, 120)}


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
        rid245 = next(b.resourceId for b in controller.GetBuffers()
                      if str(b.resourceId) == SSBO_NAME)
        ssbo = as_bytes(controller.GetBufferData(rid245, 0, 8413184))
        pixels = {}   # event -> list of (x, y) screen points
        report = {}
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
            use_ssbo = (flags & 32) != 0 and (flags & 0xFFFFFFCF) != 0
            pts = []
            inside = 0
            variant_inside = {'A_model-cam': 0, 'B_model': 0,
                              'C_model+P-cam': 0, 'D_model+P': 0}
            wpos_sum = [0.0, 0.0, 0.0]
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
                px, py, pz = struct.unpack_from('<3f', pos_raw, v * vb0.byteStride)
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
                ix = (child0[0] * mx + child0[1] * my + child0[2] * mz
                      + child0[3] - cam[0])
                iy = (child0[4] * mx + child0[5] * my + child0[6] * mz
                      + child0[7] - cam[1])
                iz = (child0[8] * mx + child0[9] * my + child0[10] * mz
                      + child0[11] - cam[2])
                P = child0[12], child0[13], child0[14]
                for vn, (vx, vy, vz) in (
                        ('A_model-cam', (ix, iy, iz)),
                        ('B_model', (mx, my, mz)),
                        ('C_model+P-cam', (mx + P[0] - cam[0], my + P[1] - cam[1],
                                           mz + P[2] - cam[2])),
                        ('D_model+P', (mx + P[0], my + P[1], mz + P[2]))):
                    cx = vx * vp[0] + vy * vp[4] + vz * vp[8] + vp[12]
                    cy = vx * vp[1] + vy * vp[5] + vz * vp[9] + vp[13]
                    cw = vx * vp[3] + vy * vp[7] + vz * vp[11] + vp[15]
                    if cw > 1e-6 and abs(cx / cw) <= 1 and abs(cy / cw) <= 1:
                        variant_inside[vn] += 1
                wpos_sum[0] += ix + cam[0]
                wpos_sum[1] += iy + cam[1]
                wpos_sum[2] += iz + cam[2]
                # row-vector v x VP  (variant C: model + P - cam)
                ix = mx + child0[12] - cam[0]
                iy = my + child0[13] - cam[1]
                iz = mz + child0[14] - cam[2]
                cx = ix * vp[0] + iy * vp[4] + iz * vp[8] + vp[12]
                cy = ix * vp[1] + iy * vp[5] + iz * vp[9] + vp[13]
                cw = ix * vp[3] + iy * vp[7] + iz * vp[11] + vp[15]
                if cw <= 1e-6:
                    continue
                nx, ny = cx / cw, cy / cw
                if abs(nx) <= 1 and abs(ny) <= 1:
                    inside += 1
                sx = (nx + 1.0) * 0.5 * IMG_W
                sy = (1.0 - ny) * 0.5 * IMG_H
                if v % 7 == 0:  # subsample for the overlay
                    pts.append((sx, sy))
            pixels[event_id] = pts
            report[str(event_id)] = {
                'part': part, 'verts': count, 'inside_ndc': inside,
                'variant_inside': variant_inside,
                'world_center': [round(wpos_sum[k] / count, 2) for k in range(3)],
            }
            if event_id == 786:
                report['vp_matrix'] = [round(x, 4) for x in vp]
        # overlay via PIL if available, else raw ppm
        capimg = output.parent / 'official-front-1280.png'
        overlay_path = output / 'screen-overlay.png'
        try:
            from PIL import Image, ImageDraw
            img = Image.open(str(capimg)).convert('RGB')
            img = img.resize((IMG_W, IMG_H))
            dr = ImageDraw.Draw(img)
            for event_id, pts in pixels.items():
                col = COLORS[event_id]
                for sx, sy in pts:
                    if 0 <= sx < IMG_W and 0 <= sy < IMG_H:
                        dr.point((sx, sy), fill=col)
            img.save(str(overlay_path))
            report['overlay'] = str(overlay_path)
        except Exception as e:
            report['overlay_error'] = str(e)
        write_new_json(output / 'screen.json', report)
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
