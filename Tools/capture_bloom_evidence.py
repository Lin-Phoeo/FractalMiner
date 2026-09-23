"""Offline UAV/sampler evidence and optional per-level frame-6411 exports.

Use official RenderDoc 1.46 qrenderdoc --python and a fresh output directory.
ENDFIELD_CAPTURE_PATH / ENDFIELD_CAPTURE_OUTPUT / ENDFIELD_TOOLS_PATH have the
same meaning as capture_pipeline_export.py. ENDFIELD_BLOOM_SAMPLER_ONLY=1 skips
all texture saves, but still verifies the complete event/UAV/texture plan.
No injection or live game access. complete.json, not native exit status, is the
success signal; it is written only after replay resources shut down successfully.
"""
import os
from pathlib import Path
import sys
import traceback

sys.path.insert(0,os.environ.get('ENDFIELD_TOOLS_PATH') or str(Path(__file__).resolve().parent))
from capture_replay_inventory import open_controller,validate_paths,write_new_json
from capture_pipeline_export import save_texture, validate_texture

OUTPUTS=[(1121,59945)]+list(zip(range(1125,1154,4),[58920,58914,58908,58902,58896,58890,58884,58878]))+list(zip(range(1157,1186,4),[58881,58887,58893,58899,58905,58911,58917,58923]))
SIZES=[(1280,800),(640,400),(320,200),(160,100),(80,50),(40,25),(20,13),(10,6),(5,3),
       (10,6),(20,13),(40,25),(80,50),(160,100),(320,200),(640,400),(1280,800)]
PLAN=[dict(event=event,id=resource,name='bloom-{}-{}'.format(event,resource),
           width=size[0],height=size[1],slices=1,mips=1,format='R11G11B10_FLOAT')
      for (event,resource),size in zip(OUTPUTS,SIZES)]


def access_record(access):
    # Explicit fields: never serialize this/thisown or opaque SWIG addresses.
    return dict(descriptorStore=str(access.descriptorStore),byteOffset=access.byteOffset,
                byteSize=access.byteSize,index=access.index,arrayElement=access.arrayElement,
                stage=str(access.stage),type=str(access.type),staticallyUnused=access.staticallyUnused)


def sampler_record(sampler):
    record={name:str(getattr(sampler,name)) for name in
            ('object','type','addressU','addressV','addressW','compareFunction','borderColorType')}
    record['filter']={name:str(getattr(sampler.filter,name)) for name in
                      ('minify','magnify','mip','filter')}
    for name in ('maxAnisotropy','minLOD','maxLOD','mipBias','unnormalized',
                 'creationTimeConstant','seamlessCubemaps','srgbBorder'):
        record[name]=getattr(sampler,name)
    record['borderColorFloat']=list(sampler.borderColorValue.floatValue)
    return record


def collect_samplers(rd,controller,state):
    """Resolve sampler descriptors, not the generic descriptor in UsedDescriptor.

    API: RenderDoc v1.46 renderdoc_replay.h/GetSamplerDescriptors and
    common_pipestate.h/SamplerDescriptor. DescriptorRange(access) preserves its
    descriptor store byte offset/size; reflection index is NOT a byte offset.
    """
    records=[]
    for used in state.GetSamplers(rd.ShaderStage.Compute):
        access=used.access
        descriptors=controller.GetSamplerDescriptors(access.descriptorStore,[rd.DescriptorRange(access)])
        if len(descriptors)!=1:
            raise ValueError('Expected one sampler descriptor for '+str(access.descriptorStore))
        sampler=descriptors[0]
        if sampler.type not in (rd.DescriptorType.Sampler,rd.DescriptorType.ImageSampler):
            raise ValueError('Resolved descriptor is not a sampler: '+str(sampler.type))
        records.append(dict(access=access_record(access),sampler=sampler_record(sampler)))
    if not records:
        raise ValueError('Bloom compute event has no sampler access evidence')
    return records


def collect(rd,controller,output,sampler_only):
    if controller.GetFrameInfo().frameNumber!=6411:
        raise ValueError('This bloom plan requires frame 6411')
    textures={str(t.resourceId):t for t in controller.GetTextures()}
    result=[]
    for plan in PLAN:
        event=plan['event']
        controller.SetFrameEvent(event,True)
        state=controller.GetPipelineState()
        write_ids=[str(w.descriptor.resource) for w in state.GetReadWriteResources(rd.ShaderStage.Compute)]
        resource='ResourceId::'+str(plan['id'])
        if write_ids != [resource]:
            raise ValueError('UAV evidence mismatch: {} {}'.format(event,write_ids))
        if resource not in textures:
            raise ValueError('Missing bloom texture: '+resource)
        texture=textures[resource]
        validate_texture(texture,plan)
        samplers=collect_samplers(rd,controller,state)
        files=[]
        if not sampler_only:
            for kind in ('DDS','EXR'):
                files.append(save_texture(rd,controller,texture.resourceId,
                    output/(plan['name']+'.'+kind.lower()),kind,kind=='DDS'))
        record=dict(event=event,uav=write_ids,samplers=samplers,files=files,
                    width=texture.width,height=texture.height,format=texture.format.Name())
        result.append(record)
        write_new_json(output/('event-{}.json'.format(event)),record)
    return result


def run():
    output=Path(os.environ['ENDFIELD_CAPTURE_OUTPUT']).resolve()
    capture=Path(os.environ['ENDFIELD_CAPTURE_PATH']).resolve()
    validate_paths(capture,output)
    sampler_only=os.environ.get('ENDFIELD_BLOOM_SAMPLER_ONLY')=='1'
    mode='sampler-only' if sampler_only else 'textures-and-samplers'
    write_new_json(output/'started.json',dict(capture=str(capture),frame=6411,mode=mode))
    cap=controller=None
    try:
        try:
            import renderdoc as rd
            cap,controller=open_controller(rd,capture)
            result=collect(rd,controller,output,sampler_only)
        finally:
            try:
                if controller is not None:controller.Shutdown()
            finally:
                if cap is not None:cap.Shutdown()
        write_new_json(output/'complete.json',dict(status='ok',frame=6411,mode=mode,events=result))
    except BaseException:
        write_new_json(output/'error.json',dict(traceback=traceback.format_exc()));raise


if __name__=='__main__':
    try:run()
    finally:sys.exit()
