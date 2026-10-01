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
using Object=UnityEngine.Object;

namespace EndfieldShaderPack
{
    // Native views/mip partitions + production sampling tests; no screenshots.
    public static class EndfieldNativeSkinMaterialValidation
    {
        static void Require(bool yes,string why){if(!yes)throw new Exception(why);}
        static double Difference(Color a,Color b)=>new[]{Math.Abs(a.r-b.r),Math.Abs(a.g-b.g),Math.Abs(a.b-b.b),Math.Abs(a.a-b.a)}.Max();
        static string Number(double value)=>value.ToString("R",CultureInfo.InvariantCulture);
        static void Reject(Action action,string why)
        {try{action();}catch(InvalidDataException){return;}throw new Exception("Accepted "+why);}
        static Color Read(RenderTexture target,Texture2D readback)
        {
            RenderTexture.active=target;readback.ReadPixels(new Rect(0,0,4,4),0,0);readback.Apply();var c=readback.GetPixel(2,2);
            Require(float.IsFinite(c.r)&&float.IsFinite(c.g)&&float.IsFinite(c.b)&&float.IsFinite(c.a),"Nonfinite output");return c;
        }
        static Color Sample(Material probe,Texture texture,Vector2 uv,float mip,RenderTexture target,Texture2D readback,bool load=false)
        {
            probe.SetTexture("_BumpMap",texture);probe.SetVector("_ProbeUVLOD",new Vector4(uv.x,uv.y,mip,load?1:0));
            Graphics.Blit(Texture2D.blackTexture,target,probe,0);return Read(target,readback);
        }
        static Color Draw(Material material,Mesh mesh,MaterialPropertyBlock block,RenderTexture target,Texture2D readback)
        {
            var cb=new CommandBuffer{name="Native skin production consumer"};
            try
            {
                cb.SetRenderTarget(target);cb.ClearRenderTarget(true,true,Color.clear);
                cb.SetViewProjectionMatrices(Matrix4x4.Translate(new Vector3(0,0,-2)),GL.GetGPUProjectionMatrix(Matrix4x4.Ortho(-.5f,.5f,-.5f,.5f,.1f,10),true));
                cb.DrawMesh(mesh,Matrix4x4.identity,material,0,0,block);Graphics.ExecuteCommandBuffer(cb);return Read(target,readback);
            }
            finally{cb.Release();}
        }
        static Texture2D Constant(Color value,List<Object> owned)
        {
            var t=new Texture2D(1,1,TextureFormat.RGBAFloat,false,true){filterMode=FilterMode.Bilinear,wrapMode=TextureWrapMode.Repeat};
            t.SetPixel(0,0,value);t.Apply(false,false);owned.Add(t);return t;
        }
        public static void RunBatch()
        {
            Require(Application.isBatchMode,"Isolated batch Editor required");string output=Environment.GetEnvironmentVariable("ENDFIELD_SKIN_MATERIAL_REPORT");
            Require(!string.IsNullOrEmpty(output)&&!File.Exists(output),"Fresh report required");
            var lines=new List<string>{"Native captured body/face inputs; no official-image/per-pixel fitting.","GPU="+SystemInfo.graphicsDeviceType+" / "+SystemInfo.graphicsDeviceName};
            var owned=new List<Object>();var prior=RenderTexture.active;Scene preview=default;
            string[] vectors=Enumerable.Range(0,16).Select(i=>"_CharacterParams"+i).Concat(new[]{"_EnvironmentGlobalParams0","_ExposureWithMiscParams","_CharacterLightDir","_CharacterLightColor","_WorldSpaceCameraPos"}).ToArray();
            string[] floats={"_EndfieldOfficialFrameEnabled","_EndfieldOfficialShadingEnabled","_EndfieldCapturedLightIntensity","_EndfieldCapturedCubemapAvailable","_EndfieldCapturedGlobalMipBias","_EndfieldLabelMode","_EndfieldDebugValueMode","_EndfieldCharacterSelfShadow"};
            var sv=vectors.Select(Shader.GetGlobalVector).ToArray();var sf=floats.Select(Shader.GetGlobalFloat).ToArray();
            try
            {
                Require(SystemInfo.graphicsDeviceType==GraphicsDeviceType.Direct3D11,"Only D3D11 certified here");
                preview=EditorSceneManager.NewPreviewScene();var cameraObject=new GameObject("SkinMaterialPipelineInit");owned.Add(cameraObject);SceneManager.MoveGameObjectToScene(cameraObject,preview);
                var target=new RenderTexture(4,4,0,RenderTextureFormat.ARGBFloat,RenderTextureReadWrite.Linear);owned.Add(target);target.Create();
                var readback=new Texture2D(4,4,TextureFormat.RGBAFloat,false,true);owned.Add(readback);
                var camera=cameraObject.AddComponent<Camera>();camera.targetTexture=target;camera.enabled=false;camera.Render();Require(RenderPipelineManager.currentPipeline!=null,"URP not initialized");
                var probeShader=Shader.Find("Hidden/Endfield/NativeClothProbe");Require(probeShader!=null&&probeShader.isSupported,"Missing native sampling probe");var probe=new Material(probeShader);owned.Add(probe);
                using(var bundle=EndfieldCapturedSkinMaterialInputs.Load())
                {
                    int cases=0,mips=0;double maxError=0;
                    for(int i=0;i<10;i++)
                    {
                        var s=EndfieldCapturedSkinMaterials.Specs[i];var t=bundle.Textures[i];var bytes=t.GetRawTextureData<byte>().ToArray();int offset=0;
                        for(int mip=0;mip<s.Mips;mip++)
                        {
                            int size=EndfieldCapturedSkinMaterials.LevelBytes(s,mip);
                            Require(t.GetPixelData<byte>(mip).SequenceEqual(bytes.Skip(offset).Take(size)),"Native mip partition changed");offset+=size;mips++;
                        }
                        Require(offset==s.Bytes,"Payload length changed");
                        foreach(var sample in bundle.NativeSamples(i))
                        {
                            int w=Math.Max(1,s.Width>>sample.Mip),h=Math.Max(1,s.Height>>sample.Mip);var uv=new Vector2((sample.X+.5f)/w,(sample.Y+.5f)/h);
                            double error=Difference(Sample(probe,t,uv,sample.Mip,target,readback),sample.Rgba);
                            Require(error<2e-6,"Native view mismatch "+s.File+" mip="+sample.Mip+" error="+Number(error));
                            Require(Difference(Sample(probe,t,uv,sample.Mip,target,readback,true),sample.Rgba)<2e-6,"Native integer Load mismatch "+s.File);
                            maxError=Math.Max(maxError,error);cases++;
                        }
                        Reject(()=>EndfieldCapturedSkinMaterials.CreateTexture(i,null),"null payload");var corrupt=(byte[])bytes.Clone();corrupt[0]^=1;
                        Reject(()=>EndfieldCapturedSkinMaterials.CreateTexture(i,corrupt),"corrupt payload");
                    }
                    lines.Add("Native view PASS images=10 mipLevels="+mips+" cases="+cases+" maxError="+Number(maxError)+"; SampleLevel+Load; sRGB RGB exactly once / linear alpha / no UV flip");
                    lines.Add("Native payload/mip partition and fail-closed null/corruption=20 PASS");
                    var shader=Shader.Find("Endfield/CharacterLit");Require(shader!=null&&shader.isSupported,"Production shader unsupported");
                    var body=new Material(shader){name="M_actor_typhoea_body_01"};var face=new Material(shader){name="M_actor_typhoea_face_01"};owned.Add(body);owned.Add(face);
                    foreach(var material in new[]{body,face})
                    {
                        material.SetFloat("_MaterialFamily",1);material.SetFloat("_UseBumpMap",1);material.SetFloat("_BumpScale",1);material.SetFloat("_BackFaceNormalFlip",1);
                        material.SetFloat("_UseDiffRampMap",1);material.SetFloat("_UseShadowLutTex",1);material.SetFloat("_UseSDFLightmap",material==face?1:0);material.SetFloat("_UseEmotionMap",material==face?1:0);
                        material.SetFloat("_EmotionIndex",0);material.SetFloat("_EmotionBlend",.7f);material.SetFloat("_Cull",0);material.SetFloat("_SkinRimOffScale",0);material.SetFloat("_FaceRimOffScale",0);
                        material.SetColor("_BaseColor",Color.white);material.SetVector("_HighlightMapVector",Vector4.zero);
                    }
                    var mesh=new Mesh();owned.Add(mesh);mesh.vertices=new[]{new Vector3(-.5f,-.5f,0),new Vector3(.5f,-.5f,0),new Vector3(.5f,.5f,0),new Vector3(-.5f,.5f,0)};
                    mesh.normals=Enumerable.Repeat(Vector3.forward,4).ToArray();mesh.tangents=Enumerable.Repeat(new Vector4(1,0,0,1),4).ToArray();mesh.triangles=new[]{0,1,2,0,2,3};
                    var root=new GameObject("NativeSkinOwnership");owned.Add(root);SceneManager.MoveGameObjectToScene(root,preview);
                    var renderer=root.AddComponent<MeshRenderer>();root.AddComponent<MeshFilter>().sharedMesh=mesh;renderer.sharedMaterials=new[]{body,face};
                    var original=new MaterialPropertyBlock();original.SetFloat("_SlotSentinel",.83f);renderer.SetPropertyBlock(original,1);
                    var inherited=new MaterialPropertyBlock();inherited.SetFloat("_RootSentinel",.37f);renderer.SetPropertyBlock(inherited);
                    var block=new MaterialPropertyBlock();
                    Endfield.EndfieldOfficialFrameGlobals.ApplyGlobals();Shader.SetGlobalFloat("_EndfieldLabelMode",0);Shader.SetGlobalFloat("_EndfieldCharacterSelfShadow",0);Shader.SetGlobalFloat("_EndfieldCapturedCubemapAvailable",0);
                    Shader.SetGlobalVector("_CharacterParams11",new Vector4(.8f,0,.6f,0));Shader.SetGlobalVector("_WorldSpaceCameraPos",new Vector4(0,0,2,1));
                    Shader.SetGlobalVector("_CharacterLightDir",new Vector4(0,0,1,1));Shader.SetGlobalVector("_CharacterLightColor",Vector4.one);
                    int productionCases=0;
                    using(var binding=EndfieldCapturedSkinMaterials.Bind(root.transform,bundle.Textures))
                    {
                        Require(binding.SlotCount==2,"Wrong slots");renderer.GetPropertyBlock(block,0);Require(block.GetFloat("_RootSentinel")==.37f,"Root inheritance lost");renderer.GetPropertyBlock(block,1);Require(block.GetFloat("_SlotSentinel")==.83f,"Slot merge lost");
                        for(int slot=0;slot<2;slot++)for(int transformed=0;transformed<2;transformed++)
                        {
                            var material=slot==0?body:face;var uv=slot==0?new Vector2(256.5f/512,256.5f/512):new Vector2(512.5f/1024,512.5f/1024);
                            var st=transformed==0?new Vector4(1,1,0,0):new Vector4(.5f,.75f,.1f,.15f);
                            var meshUV=new Vector2((uv.x-st.z)/st.x,(uv.y-st.w)/st.y);mesh.uv=Enumerable.Repeat(meshUV,4).ToArray();renderer.GetPropertyBlock(block,slot);block.SetVector("_BaseMap_ST",st);
                            // Deliberately nonidentity legacy aux ST must NOT affect
                            // this source path, which shares the captured VS UV.
                            block.SetVector("_BumpMap_ST",new Vector4(.25f,.25f,.7f,.7f));
                            Shader.SetGlobalFloat("_EndfieldDebugValueMode",0);var native=Draw(material,mesh,block,target,readback);
                            for(int i=2;i<10;i++)
                            {
                                var spec=EndfieldCapturedSkinMaterials.Specs[i];if(spec.Event!=(slot==0?786:860))continue;
                                var sampleUV=spec.Role=="Emotion"?uv*.5f:uv;
                                block.SetTexture(spec.Property,Constant(Sample(probe,bundle.Textures[i],sampleUV,0,target,readback),owned));
                            }
                            double error=Difference(native,Draw(material,mesh,block,target,readback));Require(error<2e-5,"Production native vs decoded fixture "+slot+"/"+transformed+" error="+Number(error));productionCases++;
                        }
                    }
                    renderer.GetPropertyBlock(block,0);Require(block.isEmpty,"Empty slot not restored");renderer.GetPropertyBlock(block,1);Require(block.GetFloat("_SlotSentinel")==.83f&&block.GetTexture("_BaseMap")==null,"Previous slot not restored");
                    using(var binding=EndfieldCapturedSkinMaterials.Bind(root.transform,bundle.Textures))
                    {renderer.GetPropertyBlock(block,0);block.SetTexture("_BaseMap",Texture2D.grayTexture);block.SetFloat("_LaterSentinel",.91f);renderer.SetPropertyBlock(block,0);}
                    renderer.GetPropertyBlock(block,0);Require(block.GetTexture("_BaseMap")==Texture2D.grayTexture&&block.GetFloat("_LaterSentinel")==.91f,"Foreign writer lost");
                    Require(block.GetTexture("_BumpMap")!=bundle.Textures[2]&&block.GetTexture("_ShadowLutTex")!=bundle.Textures[0],"Dangling owned input");renderer.SetPropertyBlock(null,0);
                    Reject(()=>EndfieldCapturedSkinMaterials.Bind(cameraObject.transform,bundle.Textures),"missing slots");face.SetFloat("_UseSDFLightmap",0);Reject(()=>EndfieldCapturedSkinMaterials.Bind(root.transform,bundle.Textures),"wrong variant");face.SetFloat("_UseSDFLightmap",1);
                    renderer.GetPropertyBlock(block,0);Require(block.isEmpty,"Rejected bind partially mutated");bundle.Textures[0].wrapMode=TextureWrapMode.Repeat;
                    Reject(()=>EndfieldCapturedSkinMaterials.Bind(root.transform,bundle.Textures),"wrong LUT sampler");bundle.Textures[0].wrapMode=TextureWrapMode.Clamp;
                    lines.Add("Production decoded native Base/N/SDFMask/SDF/Highlight/Emotion fixtures PASS cases="+productionCases+"; actual native LUT/ramp retained; Base ST once, legacy aux ST ignored");
                    // Independently known per-mip constant colors: 32 texels over
                    // 4 pixels => implicit LOD3; source bias -1 must select mip2.
                    var mipTexture=new Texture2D(32,32,TextureFormat.RGBAFloat,6,true){filterMode=FilterMode.Bilinear,wrapMode=TextureWrapMode.Repeat};owned.Add(mipTexture);
                    for(int mip=0;mip<6;mip++){int side=Math.Max(1,32>>mip);mipTexture.SetPixels(Enumerable.Repeat(new Color((mip+1)/8f,.125f,.25f,1),side*side).ToArray(),mip);}mipTexture.Apply(false,false);
                    mesh.uv=new[]{Vector2.zero,Vector2.right,Vector2.one,Vector2.up};block.Clear();block.SetTexture("_BaseMap",mipTexture);block.SetVector("_BaseMap_ST",new Vector4(1,1,0,0));body.SetFloat("_UseBumpMap",0);
                    Shader.SetGlobalFloat("_EndfieldDebugValueMode",4);Shader.SetGlobalFloat("_EndfieldCapturedGlobalMipBias",-1);var biased=Draw(body,mesh,block,target,readback);
                    Require(Difference(biased,new Color(.375f,.125f,.25f,1))<2e-6,"Production bias -1 did not select mip2 "+biased);
                    Shader.SetGlobalFloat("_EndfieldCapturedGlobalMipBias",0);var unbiased=Draw(body,mesh,block,target,readback);Require(Difference(unbiased,new Color(.5f,.125f,.25f,1))<2e-6,"Bias negative control did not select mip3");
                    Require(Difference(biased,unbiased)>.1,"Bias test insensitive");Shader.SetGlobalFloat("_EndfieldDebugValueMode",0);body.SetFloat("_UseBumpMap",1);
                    lines.Add("Production implicit mip/bias PASS independent expected mip2 at bias=-1 and mip3 at bias=0; negative control effective");
                    lines.Add("Scoped ownership PASS inheritance/slot merge/restoration/foreign writer/no dangling textures/reject before mutation");
                    var actual=EditorSceneManager.OpenScene("Assets/Scenes/Typhoeus_OfficialFrame_Recovered.unity",OpenSceneMode.Additive);
                    try{var actualRoot=actual.GetRootGameObjects().Single(g=>g.name=="chr_0034_typhoea_rebuilt");bool dirty=actual.isDirty;bundle.Bind(actualRoot.transform);Require(bundle.SlotCount==2&&actual.isDirty==dirty,"Actual bind slots/dirty changed");bundle.Dispose();}
                    finally{EditorSceneManager.CloseScene(actual,true);}
                    foreach(var s in new[]{shader,probeShader})Require(!ShaderUtil.GetShaderMessages(s).Any(m=>m.severity==UnityEditor.Rendering.ShaderCompilerMessageSeverity.Error),"Shader compiler error");
                    for(int pass=0;pass<body.passCount;pass++)Require(body.SetPass(pass),"Production pass failed "+pass);
                    lines.Add("Actual recovered body/face bind PASS slots=2 dirty unchanged; no scene save/full frame render/settings change");
                    lines.Add("RESULT PASS defaultPasses="+body.passCount+"; bounded dry body/face inputs, not all uniforms/weather/final scene/MMD.");
                }
                using(var stream=new FileStream(output,FileMode.CreateNew,FileAccess.Write))using(var writer=new StreamWriter(stream))foreach(var line in lines)writer.WriteLine(line);
                Debug.Log("Native skin materials PASS: "+output);
            }
            finally
            {
                for(int i=0;i<vectors.Length;i++)Shader.SetGlobalVector(vectors[i],sv[i]);for(int i=0;i<floats.Length;i++)Shader.SetGlobalFloat(floats[i],sf[i]);
                RenderTexture.active=prior;for(int i=owned.Count-1;i>=0;i--)if(owned[i]!=null){if(owned[i] is RenderTexture rt)rt.Release();Object.DestroyImmediate(owned[i]);}
                if(preview.IsValid())EditorSceneManager.ClosePreviewScene(preview);
            }
        }
    }
}
