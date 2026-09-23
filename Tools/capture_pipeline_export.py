"""Offline frame-6411 pipeline texture export. No process injection or live game access.

Run with official qrenderdoc --python; set ENDFIELD_CAPTURE_PATH,
ENDFIELD_CAPTURE_OUTPUT (fresh directory), ENDFIELD_TOOLS_PATH (this folder).
DDS preserves compressed format/mips. Linear EXR is for Unity/reference analysis.
Only complete.json indicates success, never qrenderdoc's native exit code.
"""
import hashlib
import os
from pathlib import Path
import sys
import traceback

tool_root = os.environ.get('ENDFIELD_TOOLS_PATH') or str(Path(__file__).resolve().parent)
sys.path.insert(0, tool_root)
from capture_replay_inventory import open_controller, validate_paths, write_new_json


PLAN = [
    dict(id=14188, event=835, name='character-environment', width=128, height=128, slices=6, mips=8, format='BC6_UFLOAT'),
    dict(id=58932, event=835, name='screen-shadow', width=2560, height=1600, slices=1, mips=1, format='R8G8_UNORM'),
    dict(id=19397, event=1205, name='grading-lut', width=1024, height=32, slices=1, mips=1, format='R16G16B16A16_FLOAT'),
    dict(id=19394, event=1205, name='post-input', width=2560, height=1600, slices=1, mips=1, format='R16G16B16A16_FLOAT'),
    dict(id=58923, event=1205, name='bloom', width=1280, height=800, slices=1, mips=1, format='R11G11B10_FLOAT'),
    dict(id=19599, event=1205, name='post-output', width=2560, height=1600, slices=1, mips=1, format='R8G8B8A8_UNORM'),
]


def validate_texture(texture, plan):
    actual=(texture.width, texture.height, texture.arraysize, texture.mips, texture.format.Name())
    expected=tuple(plan[k] for k in ('width','height','slices','mips','format'))
    if actual != expected:
        raise ValueError('Capture texture contract mismatch for {}: {} != {}'.format(plan['name'],actual,expected))


def save_texture(rd, controller, resource, path, file_type, all_subresources, face=None):
    if path.exists():
        raise FileExistsError(path)
    settings=rd.TextureSave()
    settings.resourceId=resource
    settings.destType=getattr(rd.FileType,file_type)
    settings.mip=-1 if all_subresources else 0
    settings.slice.sliceIndex=-1 if all_subresources else (face if face is not None else 0)
    status=controller.SaveTexture(settings,str(path))
    if status != rd.ResultCode.Succeeded:
        raise RuntimeError('SaveTexture {}: {}'.format(path.name,status))
    if not path.is_file() or path.stat().st_size == 0:
        raise RuntimeError('Missing/empty export: '+path.name)
    return dict(file=path.name, bytes=path.stat().st_size, sha256=hashlib.sha256(path.read_bytes()).hexdigest())


def run():
    capture=Path(os.environ['ENDFIELD_CAPTURE_PATH']).resolve()
    output=Path(os.environ['ENDFIELD_CAPTURE_OUTPUT']).resolve()
    validate_paths(capture,output)
    write_new_json(output/'started.json',dict(capture=str(capture),size=capture.stat().st_size))
    cap=controller=None
    try:
        import renderdoc as rd
        cap,controller=open_controller(rd,capture)
        if controller.GetFrameInfo().frameNumber != 6411:
            raise ValueError('This reviewed resource plan is only for front frame 6411')
        textures={str(t.resourceId):t for t in controller.GetTextures()}
        manifest=[]
        for plan in PLAN:
            key='ResourceId::'+str(plan['id'])
            if key not in textures: raise ValueError('Missing '+key)
            texture=textures[key]
            validate_texture(texture,plan)
            controller.SetFrameEvent(plan['event'],True)
            files=[save_texture(rd,controller,texture.resourceId,output/(plan['name']+'.dds'),'DDS',True)]
            if plan['slices']==6:
                for face in range(6):
                    files.append(save_texture(rd,controller,texture.resourceId,
                        output/('{}-face{}.exr'.format(plan['name'],face)),'EXR',False,face))
            else:
                files.append(save_texture(rd,controller,texture.resourceId,output/(plan['name']+'.exr'),'EXR',False))
            record=dict(plan,files=files)
            manifest.append(record)
            write_new_json(output/(plan['name']+'-manifest.json'),record)
        write_new_json(output/'complete.json',dict(status='ok',frame=6411,textures=manifest,
            note='EXR contains numeric channel values; post-output is shader-encoded sRGB, others linear/data.'))
    except BaseException:
        write_new_json(output/'error.json',dict(traceback=traceback.format_exc()))
        raise
    finally:
        if controller is not None:controller.Shutdown()
        if cap is not None:cap.Shutdown()


if __name__=='__main__':
    try:run()
    finally:sys.exit()
