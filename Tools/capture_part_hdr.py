"""Offline HDR evidence for character draws, identified by reviewed SPIR-V hashes.

Run in qrenderdoc --python with ENDFIELD_TOOLS_PATH, ENDFIELD_CAPTURE_PATH,
ENDFIELD_CAPTURE_OUTPUT and optionally ENDFIELD_HDR_EVENT (default 1081).
Masks mark pixels changed by a forward draw, not its full geometric coverage.
These exports are diagnostic evidence, not a pose-independent fidelity gate.
"""
import array
import hashlib
import json
import os
from pathlib import Path
import sys
import traceback


def decode_unsigned_float(bits, mantissa_bits):
    exponent = bits >> mantissa_bits
    mantissa = bits & ((1 << mantissa_bits) - 1)
    if exponent == 0:
        return mantissa * 2.0 ** (-14 - mantissa_bits)
    if exponent == 31:
        return float("inf") if mantissa == 0 else float("nan")
    return (1.0 + mantissa / float(1 << mantissa_bits)) * 2.0 ** (exponent - 15)


def changed_mask(before, after, width, height):
    expected = width * height * 4
    if len(before) != expected or len(after) != expected:
        raise ValueError("R11G11B10 snapshot byte length mismatch")
    first, second = array.array("I"), array.array("I")
    first.frombytes(before)
    second.frombytes(after)
    return bytes(1 if a != b else 0 for a, b in zip(first, second))


def select_part_draws(draws, signatures, target):
    selected = {}
    for part, signature in signatures.items():
        matches = [d for d in draws if target in d["outputs"]
                   and d["indices"] == signature["indices"]
                   and d["sha256"] == signature["sha256"]]
        if len(matches) != 1:
            raise ValueError("%s has %d matching forward draws; expected exactly one" % (part, len(matches)))
        selected[part] = matches[0]
    return selected


def save_new(path, data):
    with path.open("xb") as stream:
        stream.write(data)


def run():
    import renderdoc as rd
    from capture_replay_inventory import (
        flatten_actions, open_controller, shader_variable, validate_paths, write_new_json,
    )
    tools = Path(os.environ["ENDFIELD_TOOLS_PATH"])
    project = tools.parent
    capture = Path(os.environ["ENDFIELD_CAPTURE_PATH"])
    output = Path(os.environ["ENDFIELD_CAPTURE_OUTPUT"])
    validate_paths(capture, output)
    scene_id = os.environ.get("ENDFIELD_HDR_RESOURCE", "ResourceId::55208")
    final_event = int(os.environ.get("ENDFIELD_HDR_EVENT", "1081"))
    reference = project / "Validation/Captures/tifuluosi-front-20260917/replay-details-01"
    signatures = {}
    for part, count, shader in (("body_01", 4248, 22250), ("face_01", 10686, 37671),
                                ("hair_01", 54816, 22257)):
        path = reference / ("shader-%d.spv" % shader)
        signatures[part] = {"indices": count, "sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
                            "reference": str(path)}
    write_new_json(output / "started.json", {"capture": str(capture), "signatures": signatures})
    cap = controller = None
    try:
        cap, controller = open_controller(rd, capture)
        textures = {str(t.resourceId): t for t in controller.GetTextures()}
        scene = textures[scene_id]
        if scene.format.Name() != "R11G11B10_FLOAT":
            raise ValueError("Expected R11G11B10_FLOAT, found " + scene.format.Name())
        actions = sorted(flatten_actions(controller.GetRootActions()), key=lambda a: a.eventId)
        if not any(a.eventId == final_event for a in actions):
            raise ValueError("Final HDR event is absent from capture")
        draws, previous = [], 0
        for action in actions:
            if action.flags & rd.ActionFlags.Drawcall:
                controller.SetFrameEvent(action.eventId, True)
                state = controller.GetPipelineState()
                outputs = [str(d.resource) for d in state.GetOutputTargets()]
                if scene_id in outputs:
                    reflection = state.GetShaderReflection(rd.ShaderStage.Pixel)
                    if reflection is None:
                        raise ValueError("Missing pixel shader reflection at %d" % action.eventId)
                    draws.append({"event": action.eventId, "previous_event": previous,
                                  "indices": action.numIndices, "outputs": outputs,
                                  "shader": str(state.GetShader(rd.ShaderStage.Pixel)),
                                  "sha256": hashlib.sha256(bytes(reflection.rawBytes)).hexdigest()})
            previous = action.eventId
        selected = select_part_draws(draws, signatures, scene_id)
        evidence = {"capture": str(capture), "frame": controller.GetFrameInfo().frameNumber,
                    "target": {"resource": scene_id, "width": scene.width, "height": scene.height,
                               "format": scene.format.Name(), "rowOrder": "RenderDoc raw texture rows",
                               "encoding": "linear", "storage": "little-endian packed R11G11B10"},
                    "parts": {}, "mask_semantics": "pixels changed by forward draw, not full coverage",
                    "acceptance": "diagnostic only; same-surface registration required for colour gates"}
        for part, draw in selected.items():
            controller.SetFrameEvent(draw["previous_event"], True)
            before = bytes(controller.GetTextureData(scene.resourceId, rd.Subresource(0, 0, 0)))
            controller.SetFrameEvent(draw["event"], True)
            after = bytes(controller.GetTextureData(scene.resourceId, rd.Subresource(0, 0, 0)))
            mask = changed_mask(before, after, scene.width, scene.height)
            if not any(mask):
                raise ValueError(part + " changed no HDR pixels")
            save_new(output / (part + "-forward.r11g11b10"), after)
            save_new(output / (part + "-changed.u8"), mask)
            state = controller.GetPipelineState()
            reflection = state.GetShaderReflection(rd.ShaderStage.Pixel)
            pipeline = state.GetGraphicsPipelineObject()
            shader = state.GetShader(rd.ShaderStage.Pixel)
            constants = []
            for index, block in enumerate(reflection.constantBlocks):
                used = state.GetConstantBlock(rd.ShaderStage.Pixel, index, 0).descriptor
                if used.byteSize > 13000:
                    continue
                values = controller.GetCBufferVariableContents(pipeline, shader, rd.ShaderStage.Pixel,
                    reflection.entryPoint, index, used.resource, used.byteOffset, used.byteSize)
                constants.append({"binding": block.fixedBindNumber, "set": block.fixedBindSetOrSpace,
                                  "size": used.byteSize, "variables": [shader_variable(v) for v in values]})
            bindings = []
            for used in state.GetReadOnlyResources(rd.ShaderStage.Pixel):
                descriptor = used.descriptor
                texture = textures.get(str(descriptor.resource))
                if texture is None:
                    continue
                binding = reflection.readOnlyResources[used.access.index]
                bindings.append({"binding": binding.fixedBindNumber, "set": binding.fixedBindSetOrSpace,
                                 "resource": str(descriptor.resource), "width": texture.width,
                                 "height": texture.height, "format": texture.format.Name()})
            evidence["parts"][part] = dict(draw, changed_pixels=sum(mask), constants=constants,
                                           textures=bindings)
        if final_event < max(d["event"] for d in selected.values()):
            raise ValueError("Final HDR sample predates a selected part")
        controller.SetFrameEvent(final_event, True)
        final = bytes(controller.GetTextureData(scene.resourceId, rd.Subresource(0, 0, 0)))
        if len(final) != scene.width * scene.height * 4:
            raise ValueError("Final HDR snapshot byte length mismatch")
        save_new(output / "scene-final.r11g11b10", final)
        evidence["final_event"] = final_event
        write_new_json(output / "evidence.json", evidence)
        write_new_json(output / "complete.json", {"status": "ok", "frame": evidence["frame"],
            "parts": {p: {"event": d["event"], "changed_pixels": d["changed_pixels"]}
                      for p, d in evidence["parts"].items()}})
    except BaseException:
        write_new_json(output / "error.json", {"traceback": traceback.format_exc()})
        raise
    finally:
        try:
            if controller is not None:
                controller.Shutdown()
        finally:
            if cap is not None:
                cap.Shutdown()


if __name__ == "__main__":
    sys.path.insert(0, os.environ["ENDFIELD_TOOLS_PATH"])
    try:
        run()
    finally:
        sys.exit()
