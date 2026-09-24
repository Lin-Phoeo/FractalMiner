"""Probe VSOut post-VS buffer layout for the character draws (frame 6411).

Dumps MeshFormat fields and the first few vertices as raw float4s so the
exporter can locate SV_Position inside the VSOut stream.

Run with qrenderdoc --python; ENDFIELD_CAPTURE_PATH / ENDFIELD_CAPTURE_OUTPUT /
ENDFIELD_TOOLS_PATH as usual. Only complete.json indicates success.
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

EVENTS = [776, 786, 835, 850, 860, 875]


def as_bytes(data):
    if isinstance(data, (bytes, bytearray)):
        return bytes(data)
    return bytes(bytearray(data))


def run():
    capture = Path(os.environ['ENDFIELD_CAPTURE_PATH']).resolve()
    output = Path(os.environ['ENDFIELD_CAPTURE_OUTPUT']).resolve()
    validate_paths(capture, output)
    write_new_json(output / 'started.json', dict(capture=str(capture)))
    cap = controller = None
    try:
        import renderdoc as rd
        cap, controller = open_controller(rd, capture)
        report = {}
        for event_id in EVENTS:
            controller.SetFrameEvent(event_id, True)
            entry = {}
            for stage_name, stage in (('VSIn', rd.MeshDataStage.VSIn),
                                      ('VSOut', rd.MeshDataStage.VSOut)):
                mesh = controller.GetPostVSData(stage, 0, 0)
                raw = as_bytes(controller.GetBufferData(
                    mesh.vertexResourceId, mesh.vertexByteOffset,
                    min(mesh.numIndices, 4) * mesh.vertexByteStride))
                verts = []
                for v in range(min(mesh.numIndices, 3)):
                    base = v * mesh.vertexByteStride
                    floats = struct.unpack_from(
                        '<{}f'.format(mesh.vertexByteStride // 4), raw, base)
                    verts.append([round(x, 4) for x in floats])
                entry[stage_name] = {
                    'numIndices': mesh.numIndices,
                    'vertexByteStride': mesh.vertexByteStride,
                    'vertexByteOffset': mesh.vertexByteOffset,
                    'indexByteStride': mesh.indexByteStride,
                    'first_vertices_f32': verts,
                }
            report[str(event_id)] = entry
        write_new_json(output / 'vsout-layout.json', report)
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
