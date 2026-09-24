"""List all VS read-only resources for the character draws (find the SSBO)."""
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


def run():
    capture = Path(os.environ['ENDFIELD_CAPTURE_PATH']).resolve()
    output = Path(os.environ['ENDFIELD_CAPTURE_OUTPUT']).resolve()
    validate_paths(capture, output)
    write_new_json(output / 'started.json', dict(capture=str(capture)))
    cap = controller = None
    try:
        cap, controller = open_controller(rd, capture)
        report = {}
        for event_id, part in EVENTS:
            controller.SetFrameEvent(event_id, True)
            state = controller.GetPipelineState()
            res = []
            for r in state.GetReadOnlyResources(rd.ShaderStage.Vertex):
                item = {'name': r.name, 'resource': str(r.resourceId),
                        'resType': str(getattr(r, 'resType', '')),
                        'firstMip': getattr(r, 'firstMip', None),
                        'bind': str(getattr(r, 'bind', '')),
                        'descriptorSet': str(getattr(r, 'descriptorSet', '')),
                        'isBuffer': getattr(r, 'isBuffer', None),
                        'isTexture': getattr(r, 'isTexture', None)}
                try:
                    item['byteOffset'] = r.bufferView.byteOffset
                    item['byteSize'] = r.bufferView.byteSize
                except Exception:
                    pass
                res.append(item)
            report[str(event_id)] = {'part': part, 'vs_readonly': res}
        write_new_json(output / 'srvs.json', report)
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
