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
    // Native-view, production-consumer and independently known sampling cases.
    // No official-image comparison or exposure/color compensation.
    public static class EndfieldNativeHairEyeMaterialValidation
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
            var cb=new CommandBuffer{name="Native Hair/Eye production consumer"};
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
        static Texture2D MipFixture(List<Object> owned)
        {
            var t=new Texture2D(32,32,TextureFormat.RGBAFloat,6,true){filterMode=FilterMode.Bilinear,wrapMode=TextureWrapMode.Repeat};owned.Add(t);
            for(int m=0;m<6;m++){int side=Math.Max(1,32>>m);t.SetPixels(Enumerable.Repeat(new Color((m+1)/8f,.125f,.25f,1),side*side).ToArray(),m);}t.Apply(false,false);return t;
        }
        static void FlatGlobals()
        {
            for(int i=0;i<16;i++)Shader.SetGlobalVector("_CharacterParams"+i,Vector4.zero);
            Shader.SetGlobalVector("_CharacterParams0",new Vector4(1,1,.65f,1));Shader.SetGlobalVector("_CharacterParams1",new Vector4(0,1,1,1));
            Shader.SetGlobalVector("_CharacterParams5",Vector4.one);Shader.SetGlobalVector("_CharacterParams11",new Vector4(0,0,1,0));Shader.SetGlobalVector("_CharacterParams12",new Vector4(1,1,1,0));
            Shader.SetGlobalVector("_EnvironmentGlobalParams0",Vector4.zero);Shader.SetGlobalVector("_ExposureWithMiscParams",Vector4.one);Shader.SetGlobalFloat("_EndfieldCapturedLightIntensity",1);
            Shader.SetGlobalFloat("_EndfieldDebugValueMode",0);Shader.SetGlobalFloat("_EndfieldCapturedGlobalMipBias",-1);
        }
        public static void RunBatch()
        {
            Require(Application.isBatchMode,"Isolated batch Editor required");string output=Environment.GetEnvironmentVariable("ENDFIELD_HAIR_EYE_MATERIAL_REPORT");
            Require(!string.IsNullOrEmpty(output)&&!File.Exists(output),"Fresh report required");
            var lines=new List<string>{"Native captured Hair/Eye inputs; no official-image/per-pixel fitting.","GPU="+SystemInfo.graphicsDeviceType+" / "+SystemInfo.graphicsDeviceName};
            var owned=new List<Object>();var prior=RenderTexture.active;Scene preview=default;
            string[] vectors=Enumerable.Range(0,16).Select(i=>"_CharacterParams"+i).Concat(new[]{"_EnvironmentGlobalParams0","_ExposureWithMiscParams","_CharacterLightDir","_CharacterLightColor","_WorldSpaceCameraPos"}).ToArray();
            string[] floats={"_EndfieldOfficialFrameEnabled","_EndfieldOfficialShadingEnabled","_EndfieldCapturedLightIntensity","_EndfieldCapturedCubemapAvailable","_EndfieldCapturedGlobalMipBias","_EndfieldLabelMode","_EndfieldDebugValueMode","_EndfieldCharacterSelfShadow"};
            var sv=vectors.Select(Shader.GetGlobalVector).ToArray();var sf=floats.Select(Shader.GetGlobalFloat).ToArray();
            try
            {
                Require(SystemInfo.graphicsDeviceType==GraphicsDeviceType.Direct3D11,"Only D3D11 certified here");
                preview=EditorSceneManager.NewPreviewScene();var cameraObject=new GameObject("HairEyePipelineInit");owned.Add(cameraObject);SceneManager.MoveGameObjectToScene(cameraObject,preview);
                var target=new RenderTexture(4,4,0,RenderTextureFormat.ARGBFloat,RenderTextureReadWrite.Linear);owned.Add(target);target.Create();var readback=new Texture2D(4,4,TextureFormat.RGBAFloat,false,true);owned.Add(readback);
                var camera=cameraObject.AddComponent<Camera>();camera.targetTexture=target;camera.enabled=false;camera.Render();Require(RenderPipelineManager.currentPipeline!=null,"URP not initialized");
                var probeShader=Shader.Find("Hidden/Endfield/NativeClothProbe");Require(probeShader!=null&&probeShader.isSupported,"Missing native sampling probe");var probe=new Material(probeShader);owned.Add(probe);
                using(var bundle=EndfieldCapturedHairEyeMaterialInputs.Load())
                {
                    int cases=0,mips=0;double maxError=0;
                    for(int i=0;i<9;i++)
                    {
                        var s=EndfieldCapturedHairEyeMaterials.Specs[i];var t=bundle.Textures[i];var bytes=t.GetRawTextureData<byte>().ToArray();int offset=0;
                        for(int mip=0;mip<s.Mips;mip++)
                        {int size=EndfieldCapturedHairEyeMaterials.LevelBytes(s,mip);Require(t.GetPixelData<byte>(mip).SequenceEqual(bytes.Skip(offset).Take(size)),"Native mip partition changed");offset+=size;mips++;}
                        Require(offset==s.Bytes,"Native length changed");
                        foreach(var sample in bundle.NativeSamples(i))
                        {
                            int w=Math.Max(1,s.Width>>sample.Mip),h=Math.Max(1,s.Height>>sample.Mip);var uv=new Vector2((sample.X+.5f)/w,(sample.Y+.5f)/h);
                            double error=Difference(Sample(probe,t,uv,sample.Mip,target,readback),sample.Rgba);Require(error<2e-6,"Native view mismatch "+s.File+" mip="+sample.Mip+" error="+Number(error));
                            Require(Difference(Sample(probe,t,uv,sample.Mip,target,readback,true),sample.Rgba)<2e-6,"Integer Load mismatch "+s.File);maxError=Math.Max(maxError,error);cases++;
                        }
                        Reject(()=>EndfieldCapturedHairEyeMaterials.CreateTexture(i,null),"null payload");var corrupt=(byte[])bytes.Clone();corrupt[0]^=1;Reject(()=>EndfieldCapturedHairEyeMaterials.CreateTexture(i,corrupt),"corrupt payload");
                    }
                    lines.Add("Native view PASS images=9 mipLevels="+mips+" cases="+cases+" maxError="+Number(maxError)+"; SampleLevel+Load; sRGB RGB once / alpha linear / no UV flip");
                    lines.Add("Native bytes/mip partition + fail-closed null/corruption=18 PASS");
                    var shader=Shader.Find("Endfield/CharacterLit");Require(shader!=null&&shader.isSupported,"Production shader unsupported");
                    var hair=new Material(shader){name="M_actor_typhoea_hair_01"};var eye=new Material(shader){name="M_actor_typhoea_iris_01"};owned.Add(hair);owned.Add(eye);
                    foreach(var material in new[]{hair,eye})
                    {
                        material.SetFloat("_MaterialFamily",material==hair?2:3);material.SetFloat("_UseDiffRampMap",1);material.SetFloat("_UseShadowLutTex",0);material.SetFloat("_BackFaceNormalFlip",1);material.SetFloat("_Cull",0);
                        material.SetFloat("_UseSpecBumpMap",material==hair?1:0);material.SetFloat("_UseMetallicGlossMap",material==hair?1:0);material.SetFloat("_UseSpecRampMap",material==hair?1:0);material.SetFloat("_UseLineMap",material==hair?1:0);material.SetFloat("_UseMatcap",material==eye?1:0);
                        material.SetFloat("_BumpScale",1);material.SetFloat("_SpecBumpScale",1);material.SetColor("_BaseColor",Color.white);material.SetFloat("_ParallaxScale",0);material.SetFloat("_MatcapNormalScale",0);
                    }
                    var mesh=new Mesh();owned.Add(mesh);mesh.vertices=new[]{new Vector3(-.5f,-.5f,0),new Vector3(.5f,-.5f,0),new Vector3(.5f,.5f,0),new Vector3(-.5f,.5f,0)};
                    mesh.normals=Enumerable.Repeat(Vector3.forward,4).ToArray();mesh.tangents=Enumerable.Repeat(new Vector4(1,0,0,1),4).ToArray();mesh.triangles=new[]{0,1,2,0,2,3};
                    var root=new GameObject("HairEyeOwnership");owned.Add(root);SceneManager.MoveGameObjectToScene(root,preview);var renderer=root.AddComponent<MeshRenderer>();root.AddComponent<MeshFilter>().sharedMesh=mesh;renderer.sharedMaterials=new[]{hair,eye};
                    var inherited=new MaterialPropertyBlock();inherited.SetFloat("_RootSentinel",.37f);renderer.SetPropertyBlock(inherited);var previous=new MaterialPropertyBlock();previous.SetFloat("_SlotSentinel",.83f);renderer.SetPropertyBlock(previous,1);var block=new MaterialPropertyBlock();
                    Endfield.EndfieldOfficialFrameGlobals.ApplyGlobals();Shader.SetGlobalFloat("_EndfieldLabelMode",0);Shader.SetGlobalFloat("_EndfieldCharacterSelfShadow",0);Shader.SetGlobalFloat("_EndfieldCapturedCubemapAvailable",0);
                    Shader.SetGlobalVector("_WorldSpaceCameraPos",new Vector4(0,0,2,1));Shader.SetGlobalVector("_CharacterLightDir",new Vector4(0,0,1,1));Shader.SetGlobalVector("_CharacterLightColor",Vector4.one);
                    int production=0;
                    using(var binding=EndfieldCapturedHairEyeMaterials.Bind(root.transform,bundle.Textures))
                    {
                        Require(binding.SlotCount==2,"Unexpected slots");renderer.GetPropertyBlock(block,0);Require(block.GetFloat("_RootSentinel")==.37f,"Root inheritance lost");renderer.GetPropertyBlock(block,1);Require(block.GetFloat("_SlotSentinel")==.83f,"Slot merge lost");
                        for(int slot=0;slot<2;slot++)for(int transform=0;transform<2;transform++)
                        {
                            var material=slot==0?hair:eye;int width=slot==0?2048:512;var uv=new Vector2((width/2+.5f)/width,(width/2+.5f)/width);var st=transform==0?new Vector4(1,1,0,0):new Vector4(.5f,.75f,.1f,.15f);
                            mesh.uv=Enumerable.Repeat(new Vector2((uv.x-st.z)/st.x,(uv.y-st.w)/st.y),4).ToArray();renderer.GetPropertyBlock(block,slot);block.SetVector("_BaseMap_ST",st);
                            var lineST=new Vector4(.8f,.6f,.1f,.2f);block.SetVector("_LineMap_ST",lineST);block.SetVector("_SplitNormalMap_ST",new Vector4(.25f,.25f,.7f,.7f));
                            var native=Draw(material,mesh,block,target,readback);
                            for(int i=0;i<9;i++)
                            {
                                var s=EndfieldCapturedHairEyeMaterials.Specs[i];if(s.Event!=(slot==0?875:776)||s.Rgba8)continue;
                                Vector2 sampleUV=s.Role=="Matcap"?new Vector2(.5f,.5f):s.Role=="Line"?new Vector2(uv.x*lineST.x+lineST.z,uv.y*lineST.y+lineST.w):uv;
                                block.SetTexture(s.Property,Constant(Sample(probe,bundle.Textures[i],sampleUV,0,target,readback),owned));
                            }
                            double error=Difference(native,Draw(material,mesh,block,target,readback));Require(error<2e-5,"Production decoded fixture "+slot+"/"+transform+" error="+Number(error));production++;
                        }
                    }
                    renderer.GetPropertyBlock(block,0);Require(block.isEmpty,"Empty slot not restored");renderer.GetPropertyBlock(block,1);Require(block.GetFloat("_SlotSentinel")==.83f&&block.GetTexture("_BaseMap")==null,"Previous slot not restored");
                    using(var binding=EndfieldCapturedHairEyeMaterials.Bind(root.transform,bundle.Textures))
                    {renderer.GetPropertyBlock(block,0);block.SetTexture("_BaseMap",Texture2D.grayTexture);block.SetFloat("_LaterSentinel",.91f);renderer.SetPropertyBlock(block,0);}
                    renderer.GetPropertyBlock(block,0);Require(block.GetTexture("_BaseMap")==Texture2D.grayTexture&&block.GetFloat("_LaterSentinel")==.91f,"Foreign writer lost");Require(block.GetTexture("_SplitNormalMap")!=bundle.Textures[0],"Dangling HN");renderer.SetPropertyBlock(null,0);
                    Reject(()=>EndfieldCapturedHairEyeMaterials.Bind(cameraObject.transform,bundle.Textures),"missing slots");hair.SetFloat("_UseSpecBumpMap",0);Reject(()=>EndfieldCapturedHairEyeMaterials.Bind(root.transform,bundle.Textures),"single-normal instead of split variant");hair.SetFloat("_UseSpecBumpMap",1);
                    renderer.GetPropertyBlock(block,0);Require(block.isEmpty,"Rejected binding mutated slots");bundle.Textures[6].wrapMode=TextureWrapMode.Repeat;Reject(()=>EndfieldCapturedHairEyeMaterials.Bind(root.transform,bundle.Textures),"Matcap sampler changed");bundle.Textures[6].wrapMode=TextureWrapMode.Clamp;
                    lines.Add("Production native HN/P/Line/Base and Matcap/Base decoded fixtures PASS cases="+production+"; native ramps retained; Base ST once / shared HN UV / separate Line ST");
                    lines.Add("Scoped ownership PASS root/slot inheritance/restoration/foreign writer/no dangling inputs/reject before mutation");
                    FlatGlobals();var mipTexture=MipFixture(owned);mesh.uv=new[]{Vector2.zero,Vector2.right,Vector2.one,Vector2.up};block.Clear();block.SetVector("_BaseMap_ST",new Vector4(1,1,0,0));block.SetTexture("_BaseMap",mipTexture);
                    Shader.SetGlobalVector("_CharacterParams0",Vector4.zero);Shader.SetGlobalVector("_CharacterParams13",new Vector4(1,0,0,0));eye.SetColor("_MatcapColor",Color.clear);eye.SetColor("_EyeScatteringColor",Color.black);eye.SetColor("_EyeHighLightColor",Color.black);
                    foreach(int bias in new[]{-1,0})
                    {Shader.SetGlobalFloat("_EndfieldCapturedGlobalMipBias",bias);var expected=new Color(bias==-1?.375f:.5f,.125f,.25f,1);var actual=Draw(eye,mesh,block,target,readback);Require(Difference(actual,expected)<2e-6,"Eye Base bias mismatch "+bias+" "+actual);}
                    lines.Add("Eye production Base SampleBias PASS bias=-1=>mip2, bias=0=>mip3; independent known per-mip colors");
                    var gradient=new Texture2D(4,4,TextureFormat.RGBAFloat,false,true){filterMode=FilterMode.Bilinear,wrapMode=TextureWrapMode.Repeat};owned.Add(gradient);
                    for(int y=0;y<4;y++)for(int x=0;x<4;x++)gradient.SetPixel(x,y,new Color(x/4f,y/4f,.25f,1));gradient.Apply(false,false);
                    mesh.uv=Enumerable.Repeat(new Vector2(-.125f,.5f),4).ToArray();block.SetTexture("_BaseMap",gradient);
                    Require(Difference(Draw(eye,mesh,block,target,readback),new Color(.75f,.375f,.25f,1))<2e-6,"Eye Base must Repeat negative UV, not Clamp");
                    lines.Add("Eye Base production addressing PASS negative UV repeats to last-column texel; independent RGBAFloat lattice");
                    // The inner 2x2 derivative quad has the unit spherical
                    // normal, so MatcapUV is 1-UV. 32/4 => LOD3, bias -1 => 2.
                    FlatGlobals();mesh.uv=new[]{Vector2.zero,Vector2.right,Vector2.one,Vector2.up};block.SetTexture("_BaseMap",Constant(Color.black,owned));block.SetTexture("_MatcapTex",mipTexture);
                    eye.SetFloat("_MatcapNormalScale",1);eye.SetColor("_MatcapColor",new Color(0,0,0,1));
                    foreach(int bias in new[]{-1,0})
                    {Shader.SetGlobalFloat("_EndfieldCapturedGlobalMipBias",bias);var expected=new Color(bias==-1?.375f:.5f,.125f,.25f,1);var actual=Draw(eye,mesh,block,target,readback);Require(Difference(actual,expected)<2e-6,"Eye Matcap bias mismatch "+bias+" "+actual);}
                    mesh.uv=Enumerable.Repeat(new Vector2(0,.5f),4).ToArray();block.SetTexture("_MatcapTex",gradient);
                    Require(Difference(Draw(eye,mesh,block,target,readback),new Color(.75f,.375f,.25f,1))<2e-6,"Eye Matcap seam must Clamp, not Repeat");
                    lines.Add("Eye Matcap production PASS bias=-1=>mip2 / 0=>mip3, spherical seam clamps to last-column texel; independent expected cases=3");
                    // Analytic iris mask uses the same VS-transformed UV, not raw
                    // mesh UV or a second Base ST. Lighting is zero; CP13.y=1.
                    Shader.SetGlobalVector("_CharacterParams0",Vector4.zero);eye.SetColor("_MatcapColor",Color.clear);eye.SetFloat("_MatcapNormalScale",0);
                    Shader.SetGlobalVector("_CharacterParams13",new Vector4(0,1,0,0));eye.SetColor("_EyeHighLightColor",Color.white);mesh.uv=Enumerable.Repeat(new Vector2(.25f,.25f),4).ToArray();
                    foreach(bool transformed in new[]{false,true})
                    {
                        block.SetVector("_BaseMap_ST",transformed?new Vector4(2,2,.49f,.49f):new Vector4(1,1,0,0));
                        var expected=transformed?Color.white:new Color(0,0,0,1);Require(Difference(Draw(eye,mesh,block,target,readback),expected)<2e-6,"Eye analytic source UV/ST contract");
                    }
                    lines.Add("Eye analytic UV production PASS raw mesh(.25,.25) inside / captured VS ST gives(.99,.99) outside; independent disk mask expected");
                    // Hair diffuse is .96 * .25 * (1-Line.r), with ambient,
                    // primary ramp, secondary mask and backlight all zero.
                    // Line is implicit Sample, so global bias must NOT change it.
                    FlatGlobals();mesh.uv=new[]{Vector2.zero,Vector2.right,Vector2.one,Vector2.up};block.Clear();block.SetVector("_BaseMap_ST",new Vector4(1,1,0,0));block.SetVector("_LineMap_ST",new Vector4(1,1,0,0));
                    block.SetTexture("_BaseMap",Constant(new Color(.25f,.25f,.25f,1),owned));block.SetTexture("_SplitNormalMap",Constant(new Color(.5f,.5f,.5f,.5f),owned));block.SetTexture("_MetallicGlossMap",Constant(new Color(0,1,1,0),owned));
                    block.SetTexture("_DiffRampMap",Constant(Color.white,owned));block.SetTexture("_SpecRampMap",Constant(Color.black,owned));block.SetTexture("_LineMap",mipTexture);
                    hair.SetFloat("_LineIntensity",1);hair.SetFloat("_LineRange",1);hair.SetFloat("_LineSaturation",1);
                    foreach(int bias in new[]{-1,0})
                    {Shader.SetGlobalFloat("_EndfieldCapturedGlobalMipBias",bias);var actual=Draw(hair,mesh,block,target,readback);Require(Difference(actual,new Color(.12f,.12f,.12f,1))<2e-5,"Hair Line incorrectly biased or sampler contract "+bias+" "+actual);}
                    block.SetVector("_LineMap_ST",new Vector4(2,2,0,0));Require(Difference(Draw(hair,mesh,block,target,readback),new Color(.09f,.09f,.09f,1))<2e-5,"Hair Line own ST/implicit mip4 contract");
                    lines.Add("Hair Line implicit Sample PASS bias=-1 and 0 both mip3, LineST x2 gives mip4; independent reduced-light CPU expected cases=3");
                    var actualScene=EditorSceneManager.OpenScene("Assets/Scenes/Typhoeus_OfficialFrame_Recovered.unity",OpenSceneMode.Additive);
                    try
                    {
                        var actualRoot=actualScene.GetRootGameObjects().Single(g=>g.name=="chr_0034_typhoea_rebuilt");bool dirty=actualScene.isDirty;
                        using(var cloth=EndfieldCapturedClothMaterialInputs.Load())using(var skin=EndfieldCapturedSkinMaterialInputs.Load())
                        {cloth.Bind(actualRoot.transform);skin.Bind(actualRoot.transform);bundle.Bind(actualRoot.transform);Require(cloth.SlotCount==2&&skin.SlotCount==2&&bundle.SlotCount==2&&actualScene.isDirty==dirty,"Four-family scope slots/dirty mismatch");bundle.Dispose();}
                    }
                    finally{EditorSceneManager.CloseScene(actualScene,true);}
                    foreach(var s in new[]{shader,probeShader})Require(!ShaderUtil.GetShaderMessages(s).Any(m=>m.severity==UnityEditor.Rendering.ShaderCompilerMessageSeverity.Error),"Shader compiler error");
                    for(int pass=0;pass<hair.passCount;pass++)Require(hair.SetPass(pass),"Default pass failed "+pass);
                    lines.Add("Actual recovered four-family simultaneous native binding PASS slots=2+2+2, dirty unchanged; no scene save/full frame/settings changes");
                    lines.Add("RESULT PASS defaultPasses="+hair.passCount+"; bounded dry inputs/sampling, not all uniforms/weather/final scene/MMD.");
                }
                using(var stream=new FileStream(output,FileMode.CreateNew,FileAccess.Write))using(var writer=new StreamWriter(stream))foreach(var line in lines)writer.WriteLine(line);Debug.Log("Native Hair/Eye PASS: "+output);
            }
            finally
            {
                for(int i=0;i<vectors.Length;i++)Shader.SetGlobalVector(vectors[i],sv[i]);for(int i=0;i<floats.Length;i++)Shader.SetGlobalFloat(floats[i],sf[i]);
                RenderTexture.active=prior;for(int i=owned.Count-1;i>=0;i--)if(owned[i]!=null){if(owned[i] is RenderTexture rt)rt.Release();Object.DestroyImmediate(owned[i]);}if(preview.IsValid())EditorSceneManager.ClosePreviewScene(preview);
            }
        }
    }
}
