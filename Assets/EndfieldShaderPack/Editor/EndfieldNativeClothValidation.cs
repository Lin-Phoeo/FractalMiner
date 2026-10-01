using System;
using System.Collections.Generic;
using System.Globalization;
using System.IO;
using System.Linq;
using UnityEditor;
using UnityEditor.SceneManagement;
using UnityEngine;
using UnityEngine.Rendering;
using UnityEngine.SceneManagement;
using Object = UnityEngine.Object;

namespace EndfieldShaderPack
{
    // Input-channel sampling, source algebra and MPB ownership, not image fitting.
    public static class EndfieldNativeClothValidation
    {
        static string Number(double x) => x.ToString("R", CultureInfo.InvariantCulture);
        static void Require(bool condition, string why) { if (!condition) throw new Exception(why); }
        static double Difference(Color a, Color b) => new[] { Math.Abs(a.r-b.r), Math.Abs(a.g-b.g), Math.Abs(a.b-b.b), Math.Abs(a.a-b.a) }.Max();
        static void Reject(Action action, string why)
        {
            try { action(); } catch (InvalidDataException) { return; }
            throw new Exception("Did not reject " + why);
        }
        static int Size(int width) => ((width+3)/4)*((width+3)/4)*16;
        static int Offset(int mip) => Enumerable.Range(0, mip).Sum(m => Size(Math.Max(1, 2048>>m)));
        static Color Read(RenderTexture rt, Texture2D readback)
        {
            RenderTexture.active=rt; readback.ReadPixels(new Rect(0,0,4,4),0,0); readback.Apply();
            var c=readback.GetPixel(2,2);
            Require(float.IsFinite(c.r)&&float.IsFinite(c.g)&&float.IsFinite(c.b)&&float.IsFinite(c.a),"Non-finite GPU sample");
            return c;
        }
        static Color Sample(Material probe, Texture texture, Vector2 uv, float lod, RenderTexture rt, Texture2D readback, bool load=false)
        {
            probe.SetTexture("_BumpMap",texture);probe.SetVector("_ProbeUVLOD",new Vector4(uv.x,uv.y,lod,load?1:0));
            Graphics.Blit(Texture2D.blackTexture,rt,probe,0);return Read(rt,readback);
        }
        static Color Production(Material material, Mesh mesh, MaterialPropertyBlock block, RenderTexture rt, Texture2D readback)
        {
            var command=new CommandBuffer{name="Native cloth production consumer"};
            try
            {
                command.SetRenderTarget(rt);command.ClearRenderTarget(true,true,Color.clear);
                command.SetViewProjectionMatrices(Matrix4x4.Translate(new Vector3(0,0,-2)),GL.GetGPUProjectionMatrix(Matrix4x4.Ortho(-.5f,.5f,-.5f,.5f,.1f,10),true));
                command.DrawMesh(mesh,Matrix4x4.identity,material,0,0,block);Graphics.ExecuteCommandBuffer(command);
                return Read(rt,readback);
            }
            finally {command.Release();}
        }
        public static void RunBatch()
        {
            Require(Application.isBatchMode,"Use an isolated batch Editor");
            string output=Environment.GetEnvironmentVariable("ENDFIELD_NATIVE_CLOTH_REPORT");
            Require(!string.IsNullOrEmpty(output)&&!File.Exists(output),"Fresh report required");
            var owned=new List<Object>();var lines=new List<string>{"Native captured input channels/algebra/ownership; no official-image fitting.","GPU="+SystemInfo.graphicsDeviceType+" / "+SystemInfo.graphicsDeviceName};
            var previous=RenderTexture.active;Scene scene=default;
            var savedDebug=Shader.GetGlobalFloat("_EndfieldDebugValueMode");
            var savedEnabled=Shader.GetGlobalFloat("_EndfieldOfficialShadingEnabled");
            var savedBias=Shader.GetGlobalFloat("_EndfieldCapturedGlobalMipBias");
            var savedLabel=Shader.GetGlobalFloat("_EndfieldLabelMode");
            var savedFrame=Shader.GetGlobalFloat("_EndfieldOfficialFrameEnabled");
            var savedCP1=Shader.GetGlobalVector("_CharacterParams1");
            try
            {
                Require(SystemInfo.graphicsDeviceType==GraphicsDeviceType.Direct3D11,"This probe certifies D3D11 only");
                scene=EditorSceneManager.NewPreviewScene();var cameraObject=new GameObject("NativeClothPipelineInit");owned.Add(cameraObject);SceneManager.MoveGameObjectToScene(cameraObject,scene);
                var rt=new RenderTexture(4,4,0,RenderTextureFormat.ARGBFloat,RenderTextureReadWrite.Linear);owned.Add(rt);rt.Create();
                var readback=new Texture2D(4,4,TextureFormat.RGBAFloat,false,true);owned.Add(readback);
                var camera=cameraObject.AddComponent<Camera>();camera.targetTexture=rt;camera.enabled=false;camera.Render();Require(RenderPipelineManager.currentPipeline!=null,"URP did not initialize");
                var probeShader=Shader.Find("Hidden/Endfield/NativeClothProbe");Require(probeShader!=null&&probeShader.isSupported,"Missing sampler probe");
                var probe=new Material(probeShader);owned.Add(probe);
                using(var bundle=EndfieldCapturedClothInputs.Load())
                {
                    double maxError=0;int sampleCount=0;
                    var textures=new[]{bundle.Cloth01,bundle.Cloth02};
                    string[] hashes={EndfieldCapturedClothNormals.Cloth01Hash,EndfieldCapturedClothNormals.Cloth02Hash};
                    for(int t=0;t<textures.Length;t++)
                    {
                        var texture=textures[t];byte[] bytes=texture.GetRawTextureData<byte>().ToArray();
                        Require(EndfieldCapturedClothNormals.Hash(bytes)==hashes[t],"Uploaded raw mip bytes changed");
                        for(int mip=0;mip<12;mip++)
                        {
                            int width=Math.Max(1,2048>>mip);
                            Require(texture.GetPixelData<byte>(mip).Length==Size(width),"Raw mip extent changed");
                            Require(EndfieldCapturedClothNormals.Hash(texture.GetPixelData<byte>(mip).ToArray())==EndfieldCapturedClothNormals.Hash(bytes.Skip(Offset(mip)).Take(Size(width)).ToArray()),"Per-mip CPU upload partition changed");
                            foreach(var sample in bundle.NativeSamples(t).Where(s=>s.mip==mip))
                            {
                                var uv=new Vector2((sample.x+.5f)/width,(sample.y+.5f)/width);
                                // Independently captured native BC5 GPU channels,
                                // not a copied software decoder or our shader.
                                var gpu=Sample(probe,texture,uv,mip,rt,readback);double error=Difference(gpu,sample.rgba);
                                Require(error<2e-6,"Native capture/upload sample mismatch t="+t+" mip="+mip+" xy="+sample.x+","+sample.y+" error="+Number(error));
                                Require(Difference(Sample(probe,texture,uv,mip,rt,readback,true),sample.rgba)<2e-6,"Native integer Load mismatch");
                                Require(Math.Abs(gpu.b)<1e-6&&Math.Abs(gpu.a-1)<1e-6,"BC5 default B/A mismatch");
                                maxError=Math.Max(maxError,error);sampleCount++;
                            }
                        }
                        var sampleUV=new Vector2(19.5f/2048,31.5f/2048);
                        Require(Difference(Sample(probe,texture,sampleUV,0,rt,readback),Sample(probe,texture,sampleUV+new Vector2(1,-1),0,rt,readback))<1e-6,"Repeat address mismatch");
                    }
                    lines.Add("Native payload/mip bytes PASS textures=2 mips=24 bytesEach=5592432");
                    lines.Add("GPU BC5 channel/row/mip sampling PASS cases="+sampleCount+" maxError="+Number(maxError)+"; no UV flip; B=0 A=1; Repeat wrap=2 checks");
                    byte[] good=File.ReadAllBytes(Path.Combine(EndfieldCapturedClothInputs.Source,"cloth01.bc5"));
                    Reject(()=>EndfieldCapturedClothNormals.CreateTexture(null,hashes[0],"bad"),"null");
                    Reject(()=>EndfieldCapturedClothNormals.CreateTexture(new byte[1],hashes[0],"bad"),"size");
                    good[0]^=1;Reject(()=>EndfieldCapturedClothNormals.CreateTexture(good,hashes[0],"bad"),"corruption");
                    Reject(()=>EndfieldCapturedClothNormals.CreateTexture(new byte[EndfieldCapturedClothNormals.PayloadBytes],"unknown","bad"),"unknown identity");
                    lines.Add("Fail-closed payload validation PASS cases=4");

                    // Independent synthetic fixture differentiates mip-point vs
                    // trilinear interpolation without judging official render pixels.
                    var levels=new Texture2D(8,8,TextureFormat.RGBAFloat,4,true){filterMode=FilterMode.Bilinear,wrapMode=TextureWrapMode.Repeat,anisoLevel=0};owned.Add(levels);
                    float[] values={.2f,.6f,.9f,.4f};
                    for(int m=0;m<4;m++)levels.SetPixels(Enumerable.Repeat(new Color(values[m],.5f,0,1),Math.Max(1,8>>m)*Math.Max(1,8>>m)).ToArray(),m);
                    levels.Apply(false,false);
                    foreach(float lod in new[]{.1f,.49f,.51f,.9f,1.49f,1.51f,2.49f,2.51f})
                        Require(Math.Abs(Sample(probe,levels,new Vector2(.5f,.5f),lod,rt,readback).r-values[(int)Math.Floor(lod+.5f)])<1e-5,"Mip-point sampler mismatch lod="+lod);
                    lines.Add("Sampler fractional LOD PASS cases=8; bilinear texels / nearest mip");

                    var shader=Shader.Find("Endfield/CharacterLit");Require(shader!=null&&shader.isSupported,"Missing CharacterLit");
                    var first=new Material(shader){name="M_actor_typhoea_cloth_01"};var second=new Material(shader){name="M_actor_typhoea_cloth_02"};owned.Add(first);owned.Add(second);
                    foreach(var material in new[]{first,second}) {material.SetFloat("_MaterialFamily",0);material.SetFloat("_UseBumpMap",1);material.SetFloat("_BumpScale",1);material.SetFloat("_BackFaceNormalFlip",1);material.SetFloat("_Cull",0);}
                    var mesh=new Mesh();owned.Add(mesh);mesh.vertices=new[]{new Vector3(-.5f,-.5f,0),new Vector3(.5f,-.5f,0),new Vector3(.5f,.5f,0),new Vector3(-.5f,.5f,0)};
                    mesh.normals=Enumerable.Repeat(Vector3.forward,4).ToArray();mesh.tangents=Enumerable.Repeat(new Vector4(1,0,0,1),4).ToArray();mesh.triangles=new[]{0,1,2,0,2,3};
                    var root=new GameObject("NativeClothOwnershipProbe");owned.Add(root);SceneManager.MoveGameObjectToScene(root,scene);
                    var renderer=root.AddComponent<MeshRenderer>();root.AddComponent<MeshFilter>().sharedMesh=mesh;renderer.sharedMaterials=new[]{first,second};
                    var rootBlock=new MaterialPropertyBlock();rootBlock.SetFloat("_UserRootSentinel",.37f);renderer.SetPropertyBlock(rootBlock);
                    var original=new MaterialPropertyBlock();original.SetFloat("_UserSlotSentinel",.83f);original.SetTexture("_BumpMap",Texture2D.whiteTexture);renderer.SetPropertyBlock(original,1);
                    var block=new MaterialPropertyBlock();
                    using(var binding=EndfieldCapturedClothNormals.Bind(root.transform,bundle.Cloth01,bundle.Cloth02))
                    {
                        Require(binding.SlotCount==2,"Incorrect slot count");renderer.GetPropertyBlock(block,0);Require(block.GetTexture("_BumpMap")==bundle.Cloth01&&block.GetFloat("_UserRootSentinel")==.37f,"Root inheritance lost");
                        renderer.GetPropertyBlock(block,1);Require(block.GetTexture("_BumpMap")==bundle.Cloth02&&block.GetFloat("_UserSlotSentinel")==.83f,"Slot property lost");
                        Shader.SetGlobalFloat("_EndfieldOfficialShadingEnabled",1);Shader.SetGlobalFloat("_EndfieldDebugValueMode",9);Shader.SetGlobalFloat("_EndfieldLabelMode",0);Shader.SetGlobalFloat("_EndfieldCapturedGlobalMipBias",-1);
                        Shader.SetGlobalFloat("_EndfieldOfficialFrameEnabled",1);Shader.SetGlobalVector("_CharacterParams1",new Vector4(0,1,0,1));
                        for(int t=0;t<2;t++)
                        {
                            var sample=bundle.NativeSamples(t)[0];
                            var uv=new Vector2((sample.x+.5f)/2048,(sample.y+.5f)/2048);mesh.uv=Enumerable.Repeat(uv,4).ToArray();renderer.GetPropertyBlock(block,t);
                            var raw=sample.rgba;
                            double x=raw.r*2-1,y=raw.g*2-1,z=Math.Max(1e-16,Math.Sqrt(1-Math.Min(1,x*x+y*y))), length=Math.Sqrt(x*x+y*y+z*z);
                            var expected=new Color((float)(x/length),(float)(y/length),(float)(z/length),1);
                            Require(Difference(Production(t==0?first:second,mesh,block,rt,readback),expected)<2e-5,"Native map did not reach production decode");
                        }
                    }
                    renderer.GetPropertyBlock(block,0);Require(block.isEmpty,"Empty slot not restored");renderer.GetPropertyBlock(block,1);Require(block.GetTexture("_BumpMap")==Texture2D.whiteTexture&&block.GetFloat("_UserSlotSentinel")==.83f,"Previous slot not restored");
                    renderer.GetPropertyBlock(block);Require(block.GetFloat("_UserRootSentinel")==.37f,"Root block changed");
                    Require(first.GetTexture("_BumpMap")!=bundle.Cloth01&&second.GetTexture("_BumpMap")!=bundle.Cloth02,"Material asset mutated");
                    lines.Add("Scoped MPB binding/restore PASS root inheritance, slot merge, empty-slot restore, root/material untouched; production native decode=2");
                    first.SetTexture("_BumpMap",Texture2D.blackTexture);
                    using(var liveBinding=EndfieldCapturedClothNormals.Bind(root.transform,bundle.Cloth01,bundle.Cloth02,preserveLaterChanges:true))
                    {
                        renderer.GetPropertyBlock(block,0);block.SetFloat("_UserLaterSentinel",.91f);renderer.SetPropertyBlock(block,0);
                        renderer.GetPropertyBlock(block,1);block.SetTexture("_BumpMap",Texture2D.grayTexture);block.SetFloat("_UserLaterSentinel",.63f);renderer.SetPropertyBlock(block,1);
                    }
                    renderer.GetPropertyBlock(block,0);Require(block.GetTexture("_BumpMap")==Texture2D.blackTexture&&block.GetFloat("_UserLaterSentinel")==.91f,"Live restore lost later MPB updates");
                    renderer.GetPropertyBlock(block,1);Require(block.GetTexture("_BumpMap")==Texture2D.grayTexture&&block.GetFloat("_UserLaterSentinel")==.63f,"Live restore clobbered foreign texture owner");
                    // Return to the scoped fixture baseline for rejection cases.
                    renderer.SetPropertyBlock(null,0);renderer.SetPropertyBlock(original,1);
                    lines.Add("Long-lived MPB ownership PASS later fields preserved / foreign normal replacement not overwritten");
                    Reject(()=>EndfieldCapturedClothNormals.Bind(cameraObject.transform,bundle.Cloth01,bundle.Cloth02),"missing target slots");
                    first.SetFloat("_MaterialFamily",1);Reject(()=>EndfieldCapturedClothNormals.Bind(root.transform,bundle.Cloth01,bundle.Cloth02),"wrong family");renderer.GetPropertyBlock(block,0);Require(block.isEmpty,"Rejected binding partially mutated slots");first.SetFloat("_MaterialFamily",0);
                    var altered=EndfieldCapturedClothNormals.CreateTexture(File.ReadAllBytes(Path.Combine(EndfieldCapturedClothInputs.Source,"cloth01.bc5")),hashes[0],"TamperProbe");owned.Add(altered);
                    altered.LoadRawTextureData(good);altered.Apply(false,false);
                    Reject(()=>EndfieldCapturedClothNormals.Bind(root.transform,altered,bundle.Cloth02),"modified texture after creation");
                    renderer.GetPropertyBlock(block,0);Require(block.isEmpty,"Tampered map partially bound");
                    lines.Add("Fail-closed target validation PASS missing slots / wrong family / mutated texture, no partial binding");
                    // Production sampler must select an original mip after shared
                    // bias -1, not blend levels. ddxUV=.25, size8 => lambda1-1=0.
                    Shader.SetGlobalFloat("_EndfieldCapturedGlobalMipBias",-.6f);
                    mesh.uv=new[]{new Vector2(0,0),new Vector2(1,0),new Vector2(1,1),new Vector2(0,1)};block.Clear();block.SetTexture("_BumpMap",levels);
                    var biased=Production(first,mesh,block,rt,readback);double px=values[0]*2-1,pz=Math.Sqrt(1-px*px);
                    Require(Difference(biased,new Color((float)px,0,(float)pz,1))<2e-5,"Production shared sampler/bias mip-point mismatch");
                    lines.Add("Production SampleBias mip-point PASS lambda1 + bias(-0.6) => mip0, not trilinear");
                    foreach(var checkedShader in new[]{shader,probeShader})Require(!ShaderUtil.GetShaderMessages(checkedShader).Any(m=>m.severity==UnityEditor.Rendering.ShaderCompilerMessageSeverity.Error),"Shader compiler error");
                    for(int p=0;p<first.passCount;p++)Require(first.SetPass(p),"Default pass failed "+p);
                    var actualScene=EditorSceneManager.OpenScene("Assets/Scenes/Typhoeus_OfficialFrame_Recovered.unity",OpenSceneMode.Additive);
                    try
                    {
                        var actualRoot=actualScene.GetRootGameObjects().Single(g=>g.name=="chr_0034_typhoea_rebuilt");
                        bool wasDirty=actualScene.isDirty;
                        using(var actualBinding=EndfieldCapturedClothNormals.Bind(actualRoot.transform,bundle.Cloth01,bundle.Cloth02))
                        {
                            Require(actualBinding.SlotCount==2,"Unexpected production character slots: "+actualBinding.SlotCount);
                            Require(actualScene.isDirty==wasDirty,"Memory-only binding changed production scene dirty state");
                            lines.Add("Actual recovered-scene read-only load PASS native cloth slots="+actualBinding.SlotCount+" dirtyStateUnchanged=true; no scene save/render or quality-setting changes");
                        }
                    }
                    finally {EditorSceneManager.CloseScene(actualScene,true);}
                    lines.Add("RESULT PASS defaultPasses="+first.passCount+"; certification limited to reviewed native Cloth01/02 input/sampler/consumer, not final render or all texture maps.");
                }
                using(var stream=new FileStream(output,FileMode.CreateNew,FileAccess.Write))using(var writer=new StreamWriter(stream))foreach(var line in lines)writer.WriteLine(line);
                Debug.Log("Native cloth input probe PASS: "+output);
            }
            finally
            {
                Shader.SetGlobalFloat("_EndfieldDebugValueMode",savedDebug);Shader.SetGlobalFloat("_EndfieldOfficialShadingEnabled",savedEnabled);Shader.SetGlobalFloat("_EndfieldCapturedGlobalMipBias",savedBias);Shader.SetGlobalFloat("_EndfieldLabelMode",savedLabel);
                Shader.SetGlobalFloat("_EndfieldOfficialFrameEnabled",savedFrame);Shader.SetGlobalVector("_CharacterParams1",savedCP1);
                RenderTexture.active=previous;
                for(int i=owned.Count-1;i>=0;i--)if(owned[i]!=null){if(owned[i] is RenderTexture rt)rt.Release();Object.DestroyImmediate(owned[i]);}
                if(scene.IsValid())EditorSceneManager.ClosePreviewScene(scene);
            }
        }
    }
}
