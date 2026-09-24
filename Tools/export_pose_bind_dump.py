"""Frame-6411 structured-file probe: find the vkCmdBindVertexBuffers state for
one character draw, so the skinning stream (arena buffer + offset) can be read.

GetBuffers() only lists 39 arena buffers while GetPostVSData reports replay-side
pseudo ids, so the vertex-buffer slot binding must come from the structured
file: locate the draw chunk by its exact index parameters, then walk back to
the most recent vkCmdBindVertexBuffers chunk and dump its full structure.

Run with official qrenderdoc --python; set ENDFIELD_CAPTURE_PATH,
ENDFIELD_CAPTURE_OUTPUT (fresh directory), ENDFIELD_TOOLS_PATH (this folder),
ENDFIELD_POSE_VB_EVENT (default 786). Only complete.json indicates success.
Python 3.8 compatible for RenderDoc 1.46's embedded runtime.
"""
import os
import sys
import traceback
from pathlib import Path

tool_root = os.environ.get('ENDFIELD_TOOLS_PATH') or str(Path(__file__).resolve().parent)
sys.path.insert(0, tool_root)
from capture_replay_inventory import open_controller, validate_paths, write_new_json, flatten_actions

# event -> (numIndices, indexOffset, vertexOffset, numInstances) from the actions
EXPECTED = {776: None, 786: None, 835: None, 850: None, 860: None, 875: None}


def brief(value, limit=200):
    try:
        text = repr(value)
    except BaseException as exc:
        return '<repr failed: {}>'.format(exc)
    return text if len(text) <= limit else text[:limit] + '...'


def sd_brief(obj, depth=0, max_depth=5):
    if depth > max_depth:
        return '...'
    record = {'name': getattr(obj, 'name', '') or '',
              'type': str(getattr(obj, 'type', '<none>'))}
    try:
        record['basic'] = str(obj.type.basic)
    except BaseException:
        pass
    for conv in ('AsResourceId', 'AsUInt', 'AsInt', 'AsULong', 'AsFloat'):
        fn = getattr(obj, conv, None)
        if fn is None:
            continue
        try:
            record[conv] = str(fn())
        except BaseException as exc:
            record[conv] = '<{}>'.format(exc)
    children = getattr(obj, 'children', None)
    if children:
        record['children'] = [sd_brief(c, depth + 1, max_depth) for c in
                              list(children)[:16]]
        if len(children) > 16:
            record['children_truncated'] = len(children)
    return record


def chunk_draw_params(chunk):
    """indexCount/firstIndex/vertexOffset/instanceCount out of a draw chunk,
    tolerating the SDObject layout differences between chunk versions."""
    params = {}
    def visit(obj):
        name = getattr(obj, 'name', '') or ''
        name = name.lstrip(' \t')
        if name in ('indexCount', 'firstIndex', 'vertexOffset', 'instanceCount',
                    'firstInstance', 'drawCount'):
            for conv in ('AsUInt', 'AsULong', 'AsInt'):
                fn = getattr(obj, conv, None)
                if fn is None:
                    continue
                try:
                    params[name] = fn()
                    return
                except BaseException:
                    pass
        for child in getattr(obj, 'children', []) or []:
            visit(child)
    visit(chunk.data)
    return params


def run():
    capture = Path(os.environ['ENDFIELD_CAPTURE_PATH']).resolve()
    output = Path(os.environ['ENDFIELD_CAPTURE_OUTPUT']).resolve()
    event_id = int(os.environ.get('ENDFIELD_POSE_VB_EVENT', '786'))
    validate_paths(capture, output)
    write_new_json(output / 'started.json', dict(capture=str(capture), event=event_id))
    cap = controller = None
    try:
        import renderdoc as rd
        cap, controller = open_controller(rd, capture)
        actions = list(flatten_actions(controller.GetRootActions()))
        action = next((a for a in actions if a.eventId == event_id), None)
        if action is None:
            raise ValueError('event {} not found'.format(event_id))
        want = {'indexCount': action.numIndices, 'firstIndex': action.indexOffset,
                'vertexOffset': action.vertexOffset, 'instanceCount': action.numInstances}

        sdfile = controller.GetStructuredFile()
        chunks = list(sdfile.chunks)
        record = {'event': event_id, 'want': want, 'chunk_count': len(chunks)}

        only_chunk = os.environ.get('ENDFIELD_POSE_VB_CHUNK')
        if only_chunk:
            idx = int(only_chunk)
            chunk = chunks[idx]
            data = chunk.data
            record['chunk_dump'] = {
                'index': idx, 'name': chunk.name,
                'chunk_attrs': {n: brief(getattr(chunk, n)) for n in dir(chunk)
                                if not n.startswith('_') and not callable(getattr(chunk, n))},
                'data_attrs': {n: brief(getattr(data, n)) for n in dir(data)
                               if not n.startswith('_') and not callable(getattr(data, n))},
                'data': sd_brief(data),
            }
            write_new_json(output / 'binds.json', record)
            write_new_json(output / 'complete.json', dict(status='ok', chunk=idx))
            return

        # Collect bind state per draw chunk whose params match the action, in
        # file order; the nth match corresponds to the nth equally-parametrised
        # action in event order.
        last_bind = None
        matches = []
        for idx, chunk in enumerate(chunks):
            name = chunk.name
            if 'BindVertexBuffers' in name:
                last_bind = (idx, chunk)
            elif 'DrawIndexed' in name and 'Indirect' not in name:
                params = chunk_draw_params(chunk)
                if all(params.get(k) == v for k, v in want.items()):
                    matches.append({'chunk_index': idx, 'params': params,
                                    'bind_chunk': last_bind[0] if last_bind else None})
        record['matching_draws'] = matches
        if not matches:
            # fall back to dumping a sample of draw chunks for diagnosis
            sample = []
            for idx, chunk in enumerate(chunks):
                if 'Draw' in chunk.name:
                    sample.append({'chunk_index': idx, 'name': chunk.name,
                                   'params': chunk_draw_params(chunk)})
                if len(sample) >= 40:
                    break
            record['draw_sample'] = sample
        else:
            bind_idx = matches[-1]['bind_chunk']
            if bind_idx is not None:
                record['bind_chunk_dump'] = sd_brief(chunks[bind_idx].data)
                record['bind_chunk_name'] = chunks[bind_idx].name
        write_new_json(output / 'binds.json', record)
        write_new_json(output / 'complete.json', dict(status='ok', event=event_id,
                                                      matches=len(matches)))
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
