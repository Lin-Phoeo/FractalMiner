"""Frame-6411 per-pixel draw labels for the post-input colour buffer.

WP1.1 task 1: for every pixel of the scene HDR input read by post-processing at
event 1205 (post-input, ResourceId::19394), record which draw last changed the
content that ends up there.

Post-input is fed by a reviewed chain of full-screen copies (verified byte for
byte at runtime):

  55208 scene colour (GBuffer MRT out0, deferred blits, character forward)
    -> copy draws 953 / 962 -> 19414 (transparent / overlay draws)
    -> composite dispatch 1075 (screen-space blend, NOT a draw: labels carry,
       modified pixel count reported)
    -> 59948
    -> copy draw 1083 -> 59966 (overlay draw 1089)
    -> convert draw 1116 (R11G11B10 -> R16G16B16A16, decode-compared) -> 19394

Only geometry draws become label values; value 0 means no geometry draw
changed the pixel. Full-screen screen-space operations CARRY the per-pixel
provenance instead of claiming it, because they only transform whatever the
geometry produced at that pixel:

  - 757 / 761 / 765: deferred-lighting blits over the GBuffer pass output
  - 953 / 962: byte-verified copies 55208 -> 19414
  - 1075: screen-space composite dispatch (same-uv blend, shader 36231)
  - 1083: byte-verified copy 59948 -> 59966
  - 1116: convert/composite draw 59966 -> 19394 (16-tap neighbourhood loop in
    shader 8248; provenance still follows the pixel's own geometry)

Label rows follow GetTextureData's raw texture row order (no flip).

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

TARGET = 'ResourceId::19394'      # post-input, read at event 1205
SCENE = 'ResourceId::55208'       # forward scene colour, R11G11B10
OVERLAY = 'ResourceId::19414'     # scene copy + transparent/overlay draws
COMP = 'ResourceId::59948'        # output of composite dispatch 1075
PRE = 'ResourceId::59966'         # copy of COMP + draw 1089, input of 1116
POST_EVENT = 1205

SCENE_BASE_EVENT = 488            # BeginRenderPass of the GBuffer pass
OVERLAY_BASE_EVENT = 947          # BeginRenderPass before copy draw 953
PRE_BASE_EVENT = 1077             # BeginRenderPass before copy draw 1083
COPY_EVENTS = (953, 962, 1083)    # verified pixel-faithful copies, labels carry
DEFERRED_EVENTS = (757, 761, 765)  # deferred-lighting blits, labels carry
COMPOSITE_EVENT = 1075            # dispatch; labels carry, modifications counted
FINAL_EVENT = 1116                # draw writing post-input; labels carry

BPP = 4                           # every chain buffer except TARGET is R11G11B10
TARGET_BPP = 8                    # R16G16B16A16_FLOAT


def as_bytes(data):
    if isinstance(data, (bytes, bytearray)):
        return bytes(data)
    return bytes(bytearray(data))


def build_fp16_luts():
    """Exact R11G11B10 channel -> fp16 bit-pattern conversion (no sign bit;
    fp16 has 10 mantissa bits and subnormals down to 2^-24, so every R11/R10
    value is exactly representable)."""
    lut11 = [0] * 2048
    for i in range(2048):
        e = (i >> 6) & 0x1F
        m = i & 0x3F
        lut11[i] = (m << 4) if e == 0 else ((e << 10) | (m << 4))
    lut10 = [0] * 1024
    for i in range(1024):
        e = (i >> 5) & 0x1F
        m = i & 0x1F
        lut10[i] = (m << 5) if e == 0 else ((e << 10) | (m << 5))
    return lut11, lut10


def diff_update(labels, prev, cur, event, width, height):
    """Set labels[p]=event for every pixel whose bytes differ between prev and
    cur (4 bytes per pixel). Row compare first, then 64-pixel blocks, then
    per-pixel: the embedded runtime has no NumPy."""
    if prev == cur:
        return 0
    changed = 0
    row_bytes = width * BPP
    block_bytes = 64 * BPP
    mv_prev = memoryview(prev)
    mv_cur = memoryview(cur)
    for y in range(height):
        r0 = y * row_bytes
        r1 = r0 + row_bytes
        if prev[r0:r1] == cur[r0:r1]:
            continue
        row_base = y * width
        for x0 in range(0, width, 64):
            c0 = r0 + x0 * BPP
            c1 = min(c0 + block_bytes, r1)
            if prev[c0:c1] == cur[c0:c1]:
                continue
            npx = (c1 - c0) // BPP
            px = row_base + x0
            for i in range(npx):
                o = c0 + i * BPP
                if mv_prev[o:o + BPP] != mv_cur[o:o + BPP]:
                    struct.pack_into('<H', labels, (px + i) * 2, event)
                    changed += 1
    return changed


def decode_diff_update(labels, pre_r11, post_h16, event, width, height, luts):
    """Compare an R11G11B10 buffer against an R16G16B16A16 buffer pixelwise
    (RGB only; the source format has no alpha). Exact via fp16 LUTs."""
    lut11, lut10 = luts
    pre = memoryview(pre_r11).cast('I')
    post = memoryview(post_h16).cast('H')
    changed = 0
    for i in range(width * height):
        v = pre[i]
        j = i * 4
        if (lut11[v & 0x7FF] != post[j]
                or lut11[(v >> 11) & 0x7FF] != post[j + 1]
                or lut10[v >> 22] != post[j + 2]):
            struct.pack_into('<H', labels, i * 2, event)
            changed += 1
    return changed


def collect_markers(controller):
    """This capture is a FLAT action list (RenderDoc models render passes as
    Begin/End markers, not a nested tree), so reconstruct each draw's owning
    render pass by scanning forward: the nearest preceding vkCmdBeginRenderPass
    name becomes its 'marker'."""
    structured = controller.GetStructuredFile()
    actions = sorted(flatten_actions(controller.GetRootActions()), key=lambda a: a.eventId)
    names = {}
    markers = {}
    current_pass = ''
    for action in actions:
        name = action.GetName(structured)
        names[action.eventId] = name
        if name.startswith('vkCmdBeginRenderPass'):
            current_pass = name
        markers[action.eventId] = [current_pass] if current_pass else []
    return names, markers


def state_diagnostics(state):
    """Best-effort rasterizer/depth/stencil evidence for pass classification."""
    diag = {}
    try:
        ras = state.GetRasterState()
        diag['cull'] = str(ras.cullMode).split('.')[-1]
        diag['front_ccw'] = bool(ras.frontCCW)
        diag['depth_clip'] = bool(ras.depthClip)
    except BaseException as exc:
        diag['cull_error'] = str(exc)
    try:
        diag['depth_func'] = str(state.GetDepthTestState()).split('.')[-1]
        diag['depth_writes'] = bool(state.GetDepthWriteState()) \
            if hasattr(state, 'GetDepthWriteState') else None
    except BaseException as exc:
        diag['depth_error'] = str(exc)
    try:
        diag['stencil_enable'] = bool(state.IsStencilTestEnabled())
        front, _back = state.GetStencilFaces()
        diag['stencil_front_pass'] = str(front.passOp).split('.')[-1]
        diag['stencil_front_func'] = str(front.compareFunc).split('.')[-1]
        diag['stencil_front_ref'] = int(front.reference)
    except BaseException as exc:
        diag['stencil_error'] = str(exc)
    return diag


def shader_id(state, stage):
    try:
        return str(state.GetShader(stage))
    except BaseException:
        return ''


def pixel_textures(rd, state, texmap):
    reflection = state.GetShaderReflection(rd.ShaderStage.Pixel)
    out = []
    if reflection is None:
        return out
    used = state.GetReadOnlyResources(rd.ShaderStage.Pixel)
    for desc in used:
        index = desc.access.index
        binding = reflection.readOnlyResources[index] if 0 <= index < len(reflection.readOnlyResources) else None
        res = str(desc.descriptor.resource)
        tex = texmap.get(res)
        if tex is None:
            continue
        out.append({
            'slot': binding.fixedBindNumber if binding else -1,
            'resource': res,
            'width': tex.width, 'height': tex.height,
            'format': tex.format.Name(),
        })
    return out


def run():
    capture = Path(os.environ['ENDFIELD_CAPTURE_PATH']).resolve()
    output = Path(os.environ['ENDFIELD_CAPTURE_OUTPUT']).resolve()
    validate_paths(capture, output)
    write_new_json(output / 'started.json', dict(capture=str(capture), target=TARGET))
    cap = controller = None
    try:
        import renderdoc as rd
        cap, controller = open_controller(rd, capture)
        if controller.GetFrameInfo().frameNumber != 6411:
            raise ValueError('This reviewed chain is only for front frame 6411')

        texmap = {str(t.resourceId): t for t in controller.GetTextures()}
        expected = {TARGET: (2560, 1600, 'R16G16B16A16_FLOAT'),
                    SCENE: (2560, 1600, 'R11G11B10_FLOAT'),
                    OVERLAY: (2560, 1600, 'R11G11B10_FLOAT'),
                    COMP: (2560, 1600, 'R11G11B10_FLOAT'),
                    PRE: (2560, 1600, 'R11G11B10_FLOAT')}
        for res, (w, h, fmt) in expected.items():
            tex = texmap.get(res)
            if tex is None:
                raise ValueError('Missing ' + res)
            actual = (tex.width, tex.height, tex.format.Name())
            if actual != (w, h, fmt):
                raise ValueError('{} contract mismatch: {} != {}'.format(res, actual, (w, h, fmt)))
        width, height = 2560, 1600

        names, markers = collect_markers(controller)
        actions = {a.eventId: a for a in flatten_actions(controller.GetRootActions())}

        # GetTextureData wants the typed ResourceId, not the string form.
        res_ids = {res: texmap[res].resourceId for res in expected}

        def grab(res):
            data = as_bytes(controller.GetTextureData(res_ids[res], rd.Subresource(0, 0, 0)))
            bpp = TARGET_BPP if res == TARGET else BPP
            if len(data) != width * height * bpp:
                raise RuntimeError('{} readback {} bytes, expected {}'.format(
                    res, len(data), width * height * bpp))
            return data

        labels = bytearray(width * height * 2)
        entries = {}        # event -> draws.json record
        diagnostics = {}    # event -> extra rasterizer/depth/stencil evidence
        hops = []           # copy/composite verification records

        def register(event, compute=False):
            action = actions.get(event)
            state = controller.GetPipelineState()
            if compute:
                textures = []
                reflection = state.GetShaderReflection(rd.ShaderStage.Compute)
                if reflection is not None:
                    for desc in state.GetReadOnlyResources(rd.ShaderStage.Compute):
                        index = desc.access.index
                        binding = (reflection.readOnlyResources[index]
                                   if 0 <= index < len(reflection.readOnlyResources) else None)
                        res = str(desc.descriptor.resource)
                        tex = texmap.get(res)
                        if tex is None:
                            continue
                        textures.append({'slot': binding.fixedBindNumber if binding else -1,
                                         'resource': res, 'width': tex.width,
                                         'height': tex.height, 'format': tex.format.Name()})
                entries[event] = {
                    'event': event,
                    'name': names.get(event, ''),
                    'markers': markers.get(event, []),
                    'indices': 0, 'instances': 0,
                    'vs': '', 'ps': shader_id(state, rd.ShaderStage.Compute),
                    'textures': textures,
                    'pixels_changed': 0, 'pixels_final': 0,
                }
                diagnostics[event] = {'kind': 'dispatch'}
                return
            entries[event] = {
                'event': event,
                'name': names.get(event, ''),
                'markers': markers.get(event, []),
                'indices': action.numIndices if action else 0,
                'instances': action.numInstances if action else 0,
                'vs': shader_id(state, rd.ShaderStage.Vertex),
                'ps': shader_id(state, rd.ShaderStage.Pixel),
                'textures': pixel_textures(rd, state, texmap),
                'pixels_changed': 0, 'pixels_final': 0,
            }
            diagnostics[event] = state_diagnostics(state)

        # Phase 1: scene colour 55208 (base at the GBuffer render-pass begin).
        controller.SetFrameEvent(SCENE_BASE_EVENT, True)
        scene = grab(SCENE)
        scene_writers = []
        for event in sorted(e for e, a in actions.items()
                            if a.flags & rd.ActionFlags.Drawcall
                            and SCENE_BASE_EVENT < e < 936):
            controller.SetFrameEvent(event, True)
            state = controller.GetPipelineState()
            if SCENE not in [str(d.resource) for d in state.GetOutputTargets()]:
                continue
            register(event)
            cur = grab(SCENE)
            changed = diff_update(labels, scene, cur, event, width, height) \
                if event not in DEFERRED_EVENTS else \
                sum(1 for a, b in zip(memoryview(scene).cast('I'), memoryview(cur).cast('I')) if a != b) \
                if cur != scene else 0
            entries[event]['pixels_changed'] = changed
            if event in DEFERRED_EVENTS:
                hops.append({'event': event, 'kind': 'deferred-lighting-blit',
                             'src': SCENE, 'dst': SCENE,
                             'pixels_modified': changed,
                             'note': 'labels carry: lighting of the GBuffer content at the same pixel'})
            scene = cur
            scene_writers.append(event)

        # Phase 2: copies 953 / 962 into 19414, then overlay draws.
        controller.SetFrameEvent(OVERLAY_BASE_EVENT, True)
        overlay_base = grab(OVERLAY)
        overlay = overlay_base
        for event in (953, 962):
            controller.SetFrameEvent(event, True)
            register(event)
            cur = grab(OVERLAY)
            entries[event]['pixels_changed'] = sum(
                1 for a, b in zip(memoryview(overlay).cast('I'), memoryview(cur).cast('I')) if a != b) \
                if cur != overlay else 0
            faithful = (cur == scene)
            hops.append({'event': event, 'kind': 'copy', 'src': SCENE, 'dst': OVERLAY,
                         'byte_equal_to_source': faithful,
                         'pixels_changed_vs_previous_dst': entries[event]['pixels_changed']})
            if not faithful:
                raise RuntimeError(
                    'copy event {} is not pixel-faithful ({} != {}); chain review needed'.format(
                        event, OVERLAY, SCENE))
            overlay = cur
        for event in sorted(e for e, a in actions.items()
                            if a.flags & rd.ActionFlags.Drawcall
                            and 962 < e < 1032):
            controller.SetFrameEvent(event, True)
            state = controller.GetPipelineState()
            if OVERLAY not in [str(d.resource) for d in state.GetOutputTargets()]:
                continue
            register(event)
            cur = grab(OVERLAY)
            entries[event]['pixels_changed'] = diff_update(labels, overlay, cur, event, width, height)
            overlay = cur

        # Phase 3: composite dispatch 1075 -> 59948 (labels carry; count changes).
        controller.SetFrameEvent(COMPOSITE_EVENT, True)
        register(COMPOSITE_EVENT, compute=True)
        comp = grab(COMP)
        composite_changed = sum(
            1 for a, b in zip(memoryview(overlay).cast('I'), memoryview(comp).cast('I')) if a != b) \
            if comp != overlay else 0
        hops.append({'event': COMPOSITE_EVENT, 'kind': 'composite-dispatch',
                     'src': OVERLAY, 'dst': COMP,
                     'pixels_modified': composite_changed,
                     'note': 'labels carry through (not a draw); see shader 36231 blend'})
        entries[COMPOSITE_EVENT]['pixels_changed'] = composite_changed

        # Phase 4: copy 1083 into 59966, then draw 1089.
        controller.SetFrameEvent(PRE_BASE_EVENT, True)
        pre_base = grab(PRE)
        controller.SetFrameEvent(1083, True)
        register(1083)
        pre = grab(PRE)
        entries[1083]['pixels_changed'] = sum(
            1 for a, b in zip(memoryview(pre_base).cast('I'), memoryview(pre).cast('I')) if a != b) \
            if pre != pre_base else 0
        faithful = (pre == comp)
        hops.append({'event': 1083, 'kind': 'copy', 'src': COMP, 'dst': PRE,
                     'byte_equal_to_source': faithful,
                     'pixels_changed_vs_previous_dst': entries[1083]['pixels_changed']})
        if not faithful:
            raise RuntimeError('copy event 1083 is not pixel-faithful; chain review needed')
        controller.SetFrameEvent(1089, True)
        register(1089)
        cur = grab(PRE)
        entries[1089]['pixels_changed'] = diff_update(labels, pre, cur, 1089, width, height)
        pre = cur

        # Phase 5: draw 1116 converts/composites 59966 -> post-input 19394.
        # It samples a neighbourhood (16-tap loop in shader 8248), so its value
        # changes do NOT re-assign provenance: count them, carry the labels.
        controller.SetFrameEvent(FINAL_EVENT, True)
        register(FINAL_EVENT)
        post = grab(TARGET)
        luts = build_fp16_luts()
        probe = bytearray(width * height * 2)
        entries[FINAL_EVENT]['pixels_changed'] = decode_diff_update(
            probe, pre, post, FINAL_EVENT, width, height, luts)
        hops.append({'event': FINAL_EVENT, 'kind': 'convert-composite-draw',
                     'src': PRE, 'dst': TARGET,
                     'pixels_modified': entries[FINAL_EVENT]['pixels_changed'],
                     'note': 'labels carry: R11G11B10 -> R16G16B16A16 RGB compared exactly '
                             'via fp16 LUTs; shader 8248 has a 16-tap neighbourhood loop'})

        # Final per-event pixel counts.
        counts = {}
        for i in range(0, len(labels), 2):
            value = labels[i] | (labels[i + 1] << 8)
            if value:
                counts[value] = counts.get(value, 0) + 1
        for event, n in counts.items():
            if event in entries:
                entries[event]['pixels_final'] = n
        unknown = sorted(set(counts) - set(entries))
        if unknown:
            raise RuntimeError('labels reference unregistered events: {}'.format(unknown))

        with (output / 'labels-u16.bin').open('xb') as stream:
            stream.write(bytes(labels))

        draws = {'capture': str(capture),
                 'target': {'resource': TARGET, 'width': width, 'height': height,
                            'format': expected[TARGET][2]},
                 'orientation': 'raw-texture-rows',
                 'draws': [entries[e] for e in sorted(entries)]}
        write_new_json(output / 'draws.json', draws)
        write_new_json(output / 'debug-state.json', diagnostics)
        write_new_json(output / 'complete.json', {
            'status': 'ok', 'frame': 6411,
            'target': draws['target'],
            'draws': len(entries),
            'scene_writers': len(scene_writers),
            'distinct_labels': len(counts),
            'nonzero_pixels': sum(counts.values()),
            'hops': hops,
        })
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
