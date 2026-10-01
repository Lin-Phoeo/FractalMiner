using System;
using System.Collections.Generic;
using System.IO;
using System.Reflection;
using UnityEditor;
using UnityEditor.SceneManagement;
using UnityEngine;
using UnityEngine.Rendering;
using UnityEngine.Rendering.Universal;
using EndfieldShaderPack.EditorTools.Mmd;
using Object=UnityEngine.Object;

namespace EndfieldShaderPack
{
    public static class EndfieldShadowTemporalValidation
    {
        static readonly List<string> lines=new List<string>();
        static int checks, failures;
        static void Check(bool value,string reason)
        {checks++;if(!value)failures++;lines.Add((value?"PASS ":"FAIL ")+reason);}
        static float MatrixError(Matrix4x4 a,Matrix4x4 b)
        {float result=0;for(int i=0;i<16;i++)result=Mathf.Max(result,Mathf.Abs(a[i]-b[i]));return result;}
        static Color[] Pixels(RenderTexture rt)
        {
            var request=AsyncGPUReadback.Request(rt);request.WaitForCompletion();
            if(request.hasError)throw new InvalidOperationException("GPU readback failed: "+rt.name);
            var result=new Color[rt.width*rt.height];
            if(rt.graphicsFormat==UnityEngine.Experimental.Rendering.GraphicsFormat.A2B10G10R10_UNormPack32)
            {
                var values=request.GetData<uint>();
                for(int i=0;i<result.Length;i++){uint p=values[i];result[i]=new Color((p&1023)/1023f,((p>>10)&1023)/1023f,((p>>20)&1023)/1023f,(p>>30)/3f);}return result;
            }
            if(rt.graphicsFormat==UnityEngine.Experimental.Rendering.GraphicsFormat.R32G32B32A32_SFloat)return request.GetData<Color>().ToArray();
            if(rt.graphicsFormat==UnityEngine.Experimental.Rendering.GraphicsFormat.R32_SFloat||rt.graphicsFormat==UnityEngine.Experimental.Rendering.GraphicsFormat.R32G32_SFloat)
            {var values=request.GetData<float>();int channels=values.Length/result.Length;for(int i=0;i<result.Length;i++)result[i]=new Color(values[i*channels],channels==2?values[i*channels+1]:0,0,1);return result;}
            var previous=RenderTexture.active;var image=new Texture2D(rt.width,rt.height,TextureFormat.RGBAFloat,false,true);
            try {RenderTexture.active=rt;image.ReadPixels(new Rect(0,0,rt.width,rt.height),0,0);image.Apply();return image.GetPixels();}
            finally {RenderTexture.active=previous;Object.DestroyImmediate(image);}
        }
        public static void RunBatch()
        {
            if(!Application.isBatchMode)
                throw new InvalidOperationException("Isolated batch only; do not replace a user's open scene.");
            string output=Environment.GetEnvironmentVariable("ENDFIELD_SHADOW_TEMPORAL_OUTPUT");
            if(string.IsNullOrEmpty(output)||Directory.Exists(output))throw new IOException("Fresh output directory required");
            Directory.CreateDirectory(output);lines.Clear();checks=failures=0;
            try
            {
                VerifyProjectionTargets();
                VerifyFrozenPose(output);
                lines.Add("RESULT "+(failures==0?"PASS":"FAIL")+" checks="+checks+" failures="+failures);
                File.WriteAllLines(Path.Combine(output,"report.txt"),lines);
                if(failures!=0)throw new InvalidOperationException("Shadow temporal failures="+failures);
            }
            catch(Exception e){lines.Add("ERROR "+e);File.WriteAllLines(Path.Combine(output,"report.txt"),lines);throw;}
            finally {EditorSceneManager.NewScene(NewSceneSetup.EmptyScene,NewSceneMode.Single);}
        }
        static void VerifyProjectionTargets()
        {
            var previousQuality=QualitySettings.renderPipeline;var previousDefault=GraphicsSettings.defaultRenderPipeline;
            var owned=new List<Object>();
            try
            {
                var scene=EditorSceneManager.NewScene(NewSceneSetup.EmptyScene,NewSceneMode.Single);
                var original=AssetDatabase.LoadAssetAtPath<UniversalRenderPipelineAsset>(EndfieldCapturedPipelineActivation.PipelinePath);
                var originalData=new SerializedObject(original);
                int index=originalData.FindProperty("m_DefaultRendererIndex").intValue;
                var renderer=Object.Instantiate(originalData.FindProperty("m_RendererDataList").GetArrayElementAtIndex(index).objectReferenceValue as UniversalRendererData);owned.Add(renderer);
                renderer.rendererFeatures.Clear();
                var rendererSettings=new SerializedObject(renderer);
                rendererSettings.FindProperty("m_IntermediateTextureMode").intValue=0;rendererSettings.ApplyModifiedPropertiesWithoutUndo();
                var feature=ScriptableObject.CreateInstance<EndfieldCharacterShadowFeature>();owned.Add(feature);
                var settings=new SerializedObject(feature);settings.FindProperty("resolveShader").objectReferenceValue=AssetDatabase.LoadAssetAtPath<ComputeShader>("Assets/EndfieldShaderPack/EndfieldCharacterShadowResolve.compute");
                settings.FindProperty("atlasResolution").intValue=128;settings.ApplyModifiedPropertiesWithoutUndo();feature.Create();renderer.rendererFeatures.Add(feature);
                var probe=ScriptableObject.CreateInstance<EndfieldShadowProjectionObserver>();owned.Add(probe);probe.Create();renderer.rendererFeatures.Add(probe);renderer.SetDirty();
                var pipeline=Object.Instantiate(original);owned.Add(pipeline);pipeline.supportsHDR=false;pipeline.msaaSampleCount=1;pipeline.renderScale=1;
                var pipelineData=new SerializedObject(pipeline);var data=pipelineData.FindProperty("m_RendererDataList");data.arraySize=1;data.GetArrayElementAtIndex(0).objectReferenceValue=renderer;
                pipelineData.FindProperty("m_DefaultRendererIndex").intValue=0;pipelineData.ApplyModifiedPropertiesWithoutUndo();
                QualitySettings.renderPipeline=pipeline;GraphicsSettings.defaultRenderPipeline=pipeline;
                typeof(RenderPipelineManager).GetMethod("PrepareRenderPipeline",BindingFlags.NonPublic|BindingFlags.Static).Invoke(null,new object[]{pipeline});
                var root=new GameObject("Temporal shadow fixture");owned.Add(root);
                var cube=GameObject.CreatePrimitive(PrimitiveType.Cube);cube.transform.SetParent(root.transform);cube.transform.position=new Vector3(.2f,.3f,0);
                var material=new Material(Shader.Find("Endfield/CharacterLit"));owned.Add(material);material.SetFloat("_EnableAlphaTest",0);material.SetFloat("_Cull",0);cube.GetComponent<Renderer>().sharedMaterial=material;
                root.AddComponent<EndfieldCharacterShadowCaster>();
                var light=root.AddComponent<Endfield.EndfieldCharacterLight>();light.transform.rotation=Quaternion.LookRotation(new Vector3(-.3f,.4f,-1));light.ApplyLight();EndfieldCharacterShadowCaster.Refresh();
                var go=new GameObject("Temporal camera");owned.Add(go);var camera=go.AddComponent<Camera>();camera.enabled=false;camera.allowHDR=false;camera.allowMSAA=false;camera.transform.position=new Vector3(0,0,-3);
                camera.pixelRect=new Rect(0,0,160,120);camera.scene=scene;camera.GetUniversalAdditionalCameraData().renderPostProcessing=false;
                var target=new RenderTexture(160,120,24,RenderTextureFormat.ARGB32);owned.Add(target);target.Create();
                foreach(bool toTexture in new[]{true,false,true,false})
                {
                    camera.targetTexture=toTexture?target:null;camera.Render();
                    float error=MatrixError(probe.expected,CharacterShadowPass.LastViewProj);
                    Check(probe.camera==camera&&CharacterShadowPass.LastRenderedCamera==camera,"fresh projection observer camera / target="+toTexture);
                    Check(error<1e-6f,"resolve VP matches actual URP raster VP; target="+toTexture+" actualFlip="+probe.flipped+" error="+error.ToString("R"));
                    Check(Shader.GetGlobalFloat(CharacterShadowPass.SelfShadowGateName)==0,"G ownership cleared after target="+toTexture);
                }
                VerifyAtlasDepth(camera,material,target,owned);
            }
            finally
            {
                QualitySettings.renderPipeline=previousQuality;GraphicsSettings.defaultRenderPipeline=previousDefault;
                typeof(RenderPipelineManager).GetMethod("PrepareRenderPipeline",BindingFlags.NonPublic|BindingFlags.Static)?.Invoke(null,new object[]{GraphicsSettings.currentRenderPipeline});
                for(int i=owned.Count-1;i>=0;i--)
                {if(owned[i] is ScriptableRendererFeature f)f.Dispose();if(owned[i] is RenderTexture r)r.Release();if(owned[i]!=null)Object.DestroyImmediate(owned[i]);}
                EndfieldCharacterShadowCaster.Refresh();
            }
        }
        static void VerifyAtlasDepth(Camera camera,Material material,RenderTexture target,List<Object> owned)
        {
            camera.targetTexture=target;camera.Render();
            int pass=material.FindPass(CharacterShadowPass.AtlasPassName);
            Check(pass>=0,"production atlas metadata warm");if(pass<0)return;
            var rt=new RenderTexture(16,16,16,RenderTextureFormat.R16,RenderTextureReadWrite.Linear);owned.Add(rt);rt.Create();
            var mesh=new Mesh();owned.Add(mesh);
            mesh.vertices=new[]{new Vector3(-1,-1,0),new Vector3(1,-1,0),new Vector3(1,1,0),new Vector3(-1,1,0)};
            mesh.normals=new[]{Vector3.forward,Vector3.forward,Vector3.forward,Vector3.forward};mesh.uv=new[]{Vector2.zero,Vector2.right,Vector2.one,Vector2.up};mesh.triangles=new[]{0,1,2,0,2,3};
            foreach(bool nearFirst in new[]{true,false})
            {
                var command=new CommandBuffer();
                try
                {
                    command.SetRenderTarget(rt);command.SetViewport(new Rect(0,0,16,16));command.ClearRenderTarget(RTClearFlags.All,Color.clear,1,0);
                    foreach(float z in nearFirst?new[]{.8f,.2f}:new[]{.2f,.8f})
                    {var block=new MaterialPropertyBlock();block.SetMatrix(CharacterShadowPass.AtlasClipMatrixName,Matrix4x4.Translate(new Vector3(0,0,z)));command.DrawMesh(mesh,Matrix4x4.identity,material,0,pass,block);}
                    Graphics.ExecuteCommandBuffer(command);float actual=Pixels(rt)[8*16+8].r;
                    Check(Mathf.Abs(actual-.8f)<2e-4f,"production atlas selects nearest light depth independent of submission order; nearFirst="+nearFirst+" actual="+actual.ToString("R"));
                }
                finally{command.Release();}
            }
        }
        static void VerifyFrozenPose(string output)
        {
            using(var session=new EndfieldWetnessSession(true))
            {
                var pipeline=GraphicsSettings.currentRenderPipeline as UniversalRenderPipelineAsset;
                var data=new SerializedObject(pipeline);int rendererIndex=data.FindProperty("m_DefaultRendererIndex").intValue;
                var renderer=data.FindProperty("m_RendererDataList").GetArrayElementAtIndex(rendererIndex).objectReferenceValue as UniversalRendererData;
                var observer=ScriptableObject.CreateInstance<EndfieldShadowProjectionObserver>();
                observer.probeMaterial=new Material(Shader.Find("Hidden/Endfield/ShadowWorldProbe"));observer.Create();renderer.rendererFeatures.Add(observer);renderer.SetDirty();
                try
                {
                session.InitializeMmdPose();session.FrameFront();session.Weather.freezeTime=true;
                string motion=Environment.GetEnvironmentVariable("ENDFIELD_MMD_TEST_MOTION");
                var player=MmdPlayer.Load(Vmd.ReadFile(motion),session.Root);
                using(var physics=new EndfieldSecondaryMotion(session.Root))
                {
                    Action<float> pose=t=>{player.Reset();player.ApplyFrame(t,player.suggestedScale,true,0);};
                    physics.Evaluate(1.0,pose);Endfield.EndfieldSkinBasisDriver.ApplyForTyphoeus(session.Root);
                    Shader.SetGlobalFloat("_EndfieldDebugValueMode",211);
                    Color[] reference=null;Matrix4x4 baseline=default;
                    for(int k=0;k<5;k++)
                    {
                        session.SavePreview(Path.Combine(output,"frozen-self-"+k+".png"),640,400);
                        var actual=Pixels(CharacterShadowPass.LastResolved);
                        VerifyWorldPositions(observer,k);
                        if(k==0){reference=actual;baseline=CharacterShadowPass.LastWorldToShadow;continue;}
                        int changed=0,invalid=0;float max=0;
                        for(int i=0;i<actual.Length;i++){float delta=Mathf.Abs(actual[i].g-reference[i].g);max=Mathf.Max(max,delta);if(delta>1f/255f)changed++;if(!float.IsFinite(actual[i].g))invalid++;}
                        Check(changed==0&&invalid==0,"identical frozen pose re-render mask k="+k+" changed="+changed+" max="+max.ToString("R"));
                        Check(MatrixError(baseline,CharacterShadowPass.LastWorldToShadow)<1e-6f,"frozen light-box matrix k="+k);
                    }
                    Shader.SetGlobalFloat("_EndfieldDebugValueMode",0);
                    foreach(float time in new[]{2f,.5f,1.5f})
                    {
                        physics.Evaluate(time,pose);Endfield.EndfieldSkinBasisDriver.ApplyForTyphoeus(session.Root);
                        session.SavePreview(Path.Combine(output,"move-"+time.ToString("F1")+"-a.png"),640,400);
                        var first=Pixels(CharacterShadowPass.LastResolved);
                        var firstMatrix=CharacterShadowPass.LastWorldToShadow;
                        var firstAtlas=Pixels(CharacterShadowPass.LastAtlas);var firstDepth=Pixels(CharacterShadowPass.LastDepth);var firstIndex=Pixels(CharacterShadowPass.LastIndex);
                        session.SavePreview(Path.Combine(output,"move-"+time.ToString("F1")+"-b.png"),640,400);
                        var second=Pixels(CharacterShadowPass.LastResolved);int changed=0;
                        for(int i=0;i<first.Length;i++)if(Mathf.Abs(first[i].g-second[i].g)>1f/255f)changed++;
                        Check(changed==0,"pose transition first/repeat same mask t="+time+" changed="+changed+" matrixDelta="+MatrixError(firstMatrix,CharacterShadowPass.LastWorldToShadow).ToString("R"));
                        lines.Add("TRANSITION "+time+" atlas="+Changed(firstAtlas,Pixels(CharacterShadowPass.LastAtlas))+" depth="+Changed(firstDepth,Pixels(CharacterShadowPass.LastDepth))+" index="+Changed(firstIndex,Pixels(CharacterShadowPass.LastIndex)));
                        VerifyWorldPositions(observer,10+(int)(time*2));
                    }
                    var light=Object.FindObjectOfType<Endfield.EndfieldCharacterLight>();
                    Quaternion capturedLight=light.transform.rotation;
                    try
                    {
                        Directory.CreateDirectory(Path.Combine(output,"frames"));
                        for(int k=0;k<30;k++)
                        {
                            physics.Evaluate(k/30.0,pose);Endfield.EndfieldSkinBasisDriver.ApplyForTyphoeus(session.Root);
                            // Actual pose/light/camera transitions, never a shadow-only
                            // warmup or a second draw before the exported first frame.
                            if(k==10)light.transform.rotation=Quaternion.Euler(0,35,0)*capturedLight;
                            if(k==20)light.transform.rotation=capturedLight;
                            light.ApplyLight();
                            string frame=Path.Combine(output,"frames",k.ToString("D4")+".png");
                            session.SavePreview(frame,640,400,k%2==0);
                            var first=Pixels(CharacterShadowPass.LastResolved);var atlas=Pixels(CharacterShadowPass.LastAtlas);
                            session.SavePreview(Path.Combine(output,"repeat.png"),640,400,k%2==0);
                            Check(Changed(first,Pixels(CharacterShadowPass.LastResolved))==0&&Changed(atlas,Pixels(CharacterShadowPass.LastAtlas))==0,"continuous motion first draw equals repeat; frame="+k+" standardRequest="+(k%2==0));
                            File.Delete(Path.Combine(output,"repeat.png")); // Only this test's scratch preview.
                        }
                    }
                    finally {light.transform.rotation=capturedLight;light.ApplyLight();}
                }
                }
                finally {renderer.rendererFeatures.Remove(observer);renderer.SetDirty();observer.Dispose();Object.DestroyImmediate(observer.probeMaterial);Object.DestroyImmediate(observer);Shader.SetGlobalFloat("_EndfieldDebugValueMode",0);}
            }
        }
        static int Changed(Color[] a,Color[] b){int count=0;for(int i=0;i<a.Length;i++)if(a[i]!=b[i])count++;return count;}
        static void VerifyWorldPositions(EndfieldShadowProjectionObserver observer,int frame)
        {
            var depth=Pixels(CharacterShadowPass.LastDepth);var world=Pixels(observer.reference);
            var index=Pixels(CharacterShadowPass.LastIndex);var errors=new List<float>();var inverted=new List<float>();
            int w=observer.reference.width,h=observer.reference.height;
            Matrix4x4 inverse=CharacterShadowPass.LastViewProj.inverse;
            if(frame==0)foreach(var point in new[]{new Vector2Int(w/2,h/2),new Vector2Int(w/2,h/3),new Vector2Int(w/3,h/2)})
            {int i=point.y*w+point.x;var a=inverse*new Vector4((point.x+.5f)/w*2-1,1-(point.y+.5f)/h*2,depth[i].r,1);lines.Add("RAW "+point+" index="+index[i].ToString("F6")+" depth="+depth[i].ToString("F6")+" world="+world[i].ToString("F6")+" reconstructed="+(a/a.w).ToString("F6"));}
            for(int y=2;y<h-2;y+=3)for(int x=2;x<w-2;x+=3)
            {
                int i=y*w+x;if(index[i].r==0||depth[i].r<=0||world[i].a<.9f)continue;
                Vector3 p=new Vector3(world[i].r,world[i].g,world[i].b);
                float nx=(x+.5f)/w*2-1,ny=1-(y+.5f)/h*2;
                Vector4 a=inverse*new Vector4(nx,ny,depth[i].r,1),b=inverse*new Vector4(nx,-ny,depth[i].r,1);
                errors.Add(Vector3.Distance(p,new Vector3(a.x,a.y,a.z)/a.w));inverted.Add(Vector3.Distance(p,new Vector3(b.x,b.y,b.z)/b.w));
            }
            errors.Sort();inverted.Sort();float p50=errors.Count>0?errors[errors.Count/2]:float.PositiveInfinity;
            float other=inverted.Count>0?inverted[inverted.Count/2]:float.PositiveInfinity;
            Check(errors.Count>100&&p50<.002f,"independent raster world position vs depth unprojection frame="+frame+" samples="+errors.Count+" median="+p50.ToString("R")+" oppositeY="+other.ToString("R"));
        }
    }
    public sealed class EndfieldShadowProjectionObserver : ScriptableRendererFeature
    {
        public Matrix4x4 expected;public bool flipped;public Camera camera;
        public Material probeMaterial;public RenderTexture reference;
        Pass pass;
        public override void Create(){pass=new Pass(this){renderPassEvent=RenderPassEvent.AfterRenderingOpaques};}
        public override void AddRenderPasses(ScriptableRenderer renderer,ref RenderingData data){renderer.EnqueuePass(pass);}
        protected override void Dispose(bool disposing){if(reference!=null){reference.Release();Object.DestroyImmediate(reference);reference=null;}}
        sealed class Pass:ScriptableRenderPass
        {
            readonly EndfieldShadowProjectionObserver owner;
            public Pass(EndfieldShadowProjectionObserver owner){this.owner=owner;}
            public override void Execute(ScriptableRenderContext context,ref RenderingData data)
            {
                owner.camera=data.cameraData.camera;owner.flipped=data.cameraData.IsCameraProjectionMatrixFlipped();owner.expected=data.cameraData.GetGPUProjectionMatrix()*data.cameraData.GetViewMatrix();
                if(owner.probeMaterial==null)return;
                int w=data.cameraData.cameraTargetDescriptor.width,h=data.cameraData.cameraTargetDescriptor.height;
                if(owner.reference==null||owner.reference.width!=w||owner.reference.height!=h)
                {if(owner.reference!=null){owner.reference.Release();Object.DestroyImmediate(owner.reference);}owner.reference=new RenderTexture(w,h,24,RenderTextureFormat.ARGBFloat,RenderTextureReadWrite.Linear);owner.reference.Create();}
                var cmd=new CommandBuffer();
                try
                {
                    cmd.SetRenderTarget(owner.reference);cmd.SetViewport(new Rect(0,0,w,h));cmd.ClearRenderTarget(RTClearFlags.All,Color.clear,1,0);context.ExecuteCommandBuffer(cmd);cmd.Clear();
                    var draw=new DrawingSettings(new ShaderTagId("UniversalForward"),new SortingSettings(data.cameraData.camera)){overrideMaterial=owner.probeMaterial,overrideMaterialPassIndex=0};
                    var filter=new FilteringSettings(RenderQueueRange.opaque);context.DrawRenderers(data.cullResults,ref draw,ref filter);
                    cmd.SetRenderTarget(data.cameraData.renderer.cameraColorTargetHandle.nameID,data.cameraData.renderer.cameraDepthTargetHandle.nameID);cmd.SetViewport(data.cameraData.camera.pixelRect);context.ExecuteCommandBuffer(cmd);
                }
                finally{cmd.Release();}
            }
        }
    }
}
