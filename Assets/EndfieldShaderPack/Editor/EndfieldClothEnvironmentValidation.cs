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
    // Native input and controlled sampler tests, not official-image comparison.
    public static class EndfieldClothEnvironmentValidation
    {
        static void Require(bool ok, string message) { if (!ok) throw new Exception(message); }
        static double Error(Color a, Color b) => new[] { Math.Abs(a.r-b.r),Math.Abs(a.g-b.g),Math.Abs(a.b-b.b),Math.Abs(a.a-b.a) }.Max();
        static string Number(double x) => x.ToString("R",CultureInfo.InvariantCulture);
        static Color Read(RenderTexture rt, Texture2D readback)
        {
            RenderTexture.active=rt;readback.ReadPixels(new Rect(0,0,4,4),0,0);readback.Apply();
            Color value=readback.GetPixel(2,2);
            Require(float.IsFinite(value.r)&&float.IsFinite(value.g)&&float.IsFinite(value.b)&&float.IsFinite(value.a),"Non-finite sample");
            return value;
        }
        static Vector3 Direction(int face, float u, float v)
        {
            float x=u*2-1,y=v*2-1;
            switch(face)
            {
                case 0:return new Vector3(1,-y,-x);
                case 1:return new Vector3(-1,-y,x);
                case 2:return new Vector3(x,1,y);
                case 3:return new Vector3(x,-1,-y);
                case 4:return new Vector3(x,-y,1);
                case 5:return new Vector3(-x,-y,-1);
                default:throw new Exception("Invalid cube face");
            }
        }
        static Color Sample(Material probe,Cubemap cube,Vector3 direction,float lod,RenderTexture rt,Texture2D readback)
        {
            probe.SetTexture("_CharMaxCubemap",cube);
            probe.SetVector("_ProbeDirectionLOD",new Vector4(direction.x,direction.y,direction.z,lod));
            Graphics.Blit(Texture2D.blackTexture,rt,probe,0);return Read(rt,readback);
        }
        static Color Draw(Material mat,Mesh mesh,RenderTexture rt,Texture2D readback)
        {
            var command=new CommandBuffer{name="Cloth native environment consumer"};
            try
            {
                command.SetRenderTarget(rt);command.ClearRenderTarget(true,true,Color.clear);
                command.SetViewProjectionMatrices(Matrix4x4.Translate(new Vector3(0,0,-2)),GL.GetGPUProjectionMatrix(Matrix4x4.Ortho(-.5f,.5f,-.5f,.5f,.1f,10),true));
                command.DrawMesh(mesh,Matrix4x4.identity,mat,0,0);Graphics.ExecuteCommandBuffer(command);return Read(rt,readback);
            }
            finally {command.Release();}
        }
        static Cubemap Fixture(List<Object> owned,Func<int,int,Color> value)
        {
            var cube=new Cubemap(128,TextureFormat.RGBAFloat,true){filterMode=FilterMode.Bilinear,wrapMode=TextureWrapMode.Clamp,anisoLevel=0};owned.Add(cube);
            Fill(cube,value);return cube;
        }
        static void Fill(Cubemap cube,Func<int,int,Color> value)
        {
            for(int face=0;face<6;face++)for(int mip=0;mip<8;mip++)
                cube.SetPixels(Enumerable.Repeat(value(face,mip),Math.Max(1,128>>mip)*Math.Max(1,128>>mip)).ToArray(),(CubemapFace)face,mip);
            cube.Apply(false,false);
        }
        public static void RunBatch()
        {
            Require(Application.isBatchMode,"Isolated batch Editor required");
            string output=Environment.GetEnvironmentVariable("ENDFIELD_CLOTH_ENVIRONMENT_REPORT");
            Require(!string.IsNullOrEmpty(output)&&!File.Exists(output),"Fresh report required");
            Require(SystemInfo.graphicsDeviceType==GraphicsDeviceType.Direct3D11,"D3D11 certification only");
            var owned=new List<Object>();var previousRT=RenderTexture.active;Scene scene=default;
            string[] vectors=Enumerable.Range(0,16).Select(i=>"_CharacterParams"+i).Concat(new[]{"_EnvironmentGlobalParams0","_ExposureWithMiscParams","_CharacterLightDir","_CharacterLightColor","_WorldSpaceCameraPos"}).ToArray();
            string[] floats={"_EndfieldOfficialFrameEnabled","_EndfieldOfficialShadingEnabled","_EndfieldCapturedLightIntensity","_EndfieldCapturedCubemapAvailable","_EndfieldCapturedGlobalMipBias","_EndfieldLabelMode","_EndfieldDebugValueMode","_EndfieldCharacterSelfShadow"};
            var savedVectors=vectors.Select(Shader.GetGlobalVector).ToArray();var savedFloats=floats.Select(Shader.GetGlobalFloat).ToArray();
            var savedCube=Shader.GetGlobalTexture("_CharMaxCubemap");
            var lines=new List<string>{"Native cube input/sampler/production probes; no screenshot fitting.","GPU="+SystemInfo.graphicsDeviceName};
            try
            {
                var rt=new RenderTexture(4,4,0,RenderTextureFormat.ARGBFloat,RenderTextureReadWrite.Linear);owned.Add(rt);rt.Create();
                var readback=new Texture2D(4,4,TextureFormat.RGBAFloat,false,true);owned.Add(readback);
                scene=EditorSceneManager.NewPreviewScene();var init=new GameObject("CubeProbePipelineInit");owned.Add(init);SceneManager.MoveGameObjectToScene(init,scene);
                var camera=init.AddComponent<Camera>();camera.targetTexture=rt;camera.enabled=false;camera.Render();Require(RenderPipelineManager.currentPipeline!=null,"URP missing");
                var probeShader=Shader.Find("Hidden/Endfield/ClothEnvironmentProbe");Require(probeShader!=null&&probeShader.isSupported,"Missing cube probe");
                var probe=new Material(probeShader);owned.Add(probe);
                using(var bundle=EndfieldCapturedEnvironmentInputs.Load())
                {
                    var dds=File.ReadAllBytes(Path.Combine(EndfieldCapturedEnvironmentInputs.Source,"character-environment.dds"));int offset=148;
                    for(int face=0;face<6;face++)for(int mip=0;mip<8;mip++)
                    {
                        int w=Math.Max(1,128>>mip),size=((w+3)/4)*((w+3)/4)*16;
                        byte[] cpu=bundle.Cube.GetPixelData<byte>(mip,(CubemapFace)face).ToArray();
                        Require(cpu.Length==size&&cpu.SequenceEqual(dds.Skip(offset).Take(size)),"Cube CPU block upload mismatch");offset+=size;
                    }
                    Require(offset==dds.Length,"Cube upload partition mismatch");
                    double maxError=0;
                    foreach(var sample in bundle.Samples)
                    {
                        int w=Math.Max(1,128>>sample.mip);
                        var direction=Direction(sample.face,(sample.x+.5f)/w,(sample.y+.5f)/w);
                        double error=Error(Sample(probe,bundle.Cube,direction,sample.mip,rt,readback),sample.rgba);
                        Require(error<2e-5,"Native cube channel/face/mip mismatch face="+sample.face+" mip="+sample.mip+" error="+Number(error));maxError=Math.Max(maxError,error);
                    }
                    lines.Add("Native BC6H unsigned/linear PASS faces=6 mips=48 CPU bytes=131232; GPU samples="+bundle.Samples.Count+" maxError="+Number(maxError));
                    var foreign=Fixture(owned,(f,m)=>Color.gray);
                    Shader.SetGlobalTexture("_CharMaxCubemap",foreign);Shader.SetGlobalFloat("_EndfieldCapturedCubemapAvailable",.37f);
                    using(var scope=EndfieldCapturedEnvironmentInputs.Load()) {scope.Bind();Require(Shader.GetGlobalTexture("_CharMaxCubemap")==scope.Cube,"Native binding failed");}
                    Require(Shader.GetGlobalTexture("_CharMaxCubemap")==foreign&&Shader.GetGlobalFloat("_EndfieldCapturedCubemapAvailable")==.37f,"Global restore failed");
                    using(var scope=EndfieldCapturedEnvironmentInputs.Load()) {scope.Bind();Shader.SetGlobalTexture("_CharMaxCubemap",foreign);Shader.SetGlobalFloat("_EndfieldCapturedCubemapAvailable",.63f);}
                    Require(Shader.GetGlobalTexture("_CharMaxCubemap")==foreign&&Shader.GetGlobalFloat("_EndfieldCapturedCubemapAvailable")==.63f,"Foreign ownership overwritten");
                    lines.Add("Scoped global restore/foreign-owner preservation PASS cases=2");
                    using(var mutated=EndfieldCapturedEnvironmentInputs.Load())
                    {
                        byte[] changed=mutated.Cube.GetPixelData<byte>(0,CubemapFace.PositiveX).ToArray();changed[0]^=1;
                        mutated.Cube.SetPixelData(changed,0,CubemapFace.PositiveX);mutated.Cube.Apply(false,false);
                        bool rejected=false;try {mutated.Bind();}catch(InvalidDataException){rejected=true;}
                        Require(rejected,"Cube changed after creation was accepted");
                        Require(Shader.GetGlobalTexture("_CharMaxCubemap")==foreign,"Rejected cube partially bound");
                    }
                    lines.Add("Mutated-after-load cube rejection / no partial binding PASS");
                    foreach(byte[] bad in new[]{new byte[1],dds.Take(dds.Length-1).ToArray(),dds.Select((b,i)=>i==148?(byte)(b^1):b).ToArray()})
                    {
                        bool rejected=false;try {var unexpected=EndfieldCapturedEnvironment.CreateTexture(bad);owned.Add(unexpected);}catch(InvalidDataException){rejected=true;}
                        Require(rejected,"Damaged DDS accepted");
                    }
                    lines.Add("Native DDS fail-closed PASS truncation/length/hash cases=3");
                    Func<int,int,Color> palette=(face,mip)=>new Color(.1f+face*.03f+mip*.04f,.2f+face*.02f+mip*.03f,.3f+mip*.02f,1);
                    var levels=Fixture(owned,palette);int samplerCases=0;
                    foreach(int mode in new[]{0,1})foreach(int face in Enumerable.Range(0,6))foreach(float lod in new[]{-2f,0f,.49f,.51f,1.49f,1.51f,4.49f,4.51f,6.49f,6.51f,9f})
                    {
                        probe.SetFloat("_ProbeMode",mode);
                        int mip=Math.Clamp((int)Math.Floor(lod+.5),0,7);
                        Require(Error(Sample(probe,levels,Direction(face,.5f,.5f),lod,rt,readback),palette(face,mip))<2e-6,"Cube sampler not nearest-mip");samplerCases++;
                    }
                    levels.filterMode=FilterMode.Trilinear;probe.SetFloat("_ProbeMode",0);
                    Color interpolated=Sample(probe,levels,Direction(0,.5f,.5f),4.49f,rt,readback);
                    Require(Error(interpolated,palette(0,4))>1e-3,"Fixture did not distinguish trilinear from mip-point");
                    probe.SetFloat("_ProbeMode",1);
                    Require(Error(Sample(probe,levels,Direction(0,.5f,.5f),4.49f,rt,readback),palette(0,4))<2e-6,"Inline Clamp depended on cube trilinear state");
                    levels.filterMode=FilterMode.Bilinear;
                    lines.Add("Synthetic cube face/LOD/bounds PASS cases="+samplerCases+"; linked Bilinear and inline LinearClamp nearest mip; trilinear negative control PASS");
                    var spatial=Fixture(owned,(f,m)=>Color.clear);
                    for(int face=0;face<6;face++)
                    {
                        var pixels=new Color[128*128];for(int y=0;y<128;y++)for(int x=0;x<128;x++)pixels[y*128+x]=new Color(x/127f,y/127f,.3f,1);
                        spatial.SetPixels(pixels,(CubemapFace)face,0);
                    }
                    spatial.Apply(false,false);
                    foreach(int mode in new[]{0,1})foreach(int face in Enumerable.Range(0,6))
                    {
                        // Exactly representable quarter-texel fractions avoid
                        // treating ideal arbitrary-UV interpolation as a bit-exact
                        // hardware oracle. Keep the original 2e-6 gate unchanged.
                        probe.SetFloat("_ProbeMode",mode);float u=(52+.5f+.25f)/128,v=(79+.5f+.75f)/128;
                        var expected=new Color((u*128-.5f)/127,(v*128-.5f)/127,.3f,1);
                        var actual=Sample(probe,spatial,Direction(face,u,v),0,rt,readback);
                        Require(Error(actual,expected)<2e-6,"Within-face bilinear filtering mismatch mode="+mode+" face="+face+" actual="+actual.ToString("F9")+" expected="+expected.ToString("F9")+" error="+Number(Error(actual,expected)));
                    }
                    probe.SetFloat("_ProbeMode",2);
                    var pointSample=Sample(probe,spatial,Direction(0,(52+.5f+.25f)/128,(79+.5f+.75f)/128),0,rt,readback);
                    Require(Error(pointSample,new Color(52.25f/127,79.75f/127,.3f,1))>1e-3,"Bilinear fixture cannot reject point texel filtering");
                    lines.Add("Within-face bilinear exact quarter-texel interpolation PASS cases=12; point-filter negative control PASS");

                    var shader=Shader.Find("Endfield/CharacterLit");Require(shader!=null&&shader.isSupported,"CharacterLit missing");
                    var mat=new Material(shader);owned.Add(mat);
                    foreach(string toggle in new[]{"_UseBumpMap","_UseMetallicGlossMap","_UseDiffRampMap","_UseSpecRampMap","_UseShadowLutTex","_ClearCoat","_UseEmission","_EnableOutline"}) mat.SetFloat(toggle,0);
                    mat.SetFloat("_MaterialFamily",0);mat.SetFloat("_Cull",0);mat.SetFloat("_Metallic",0);mat.SetFloat("_Specular",1);mat.SetColor("_BaseColor",new Color(0,0,0,1));
                    var mesh=new Mesh{vertices=new[]{new Vector3(-.5f,-.5f,0),new Vector3(.5f,-.5f,0),new Vector3(.5f,.5f,0),new Vector3(-.5f,.5f,0)},triangles=new[]{0,1,2,0,2,3},normals=Enumerable.Repeat(Vector3.forward,4).ToArray(),uv=new[]{Vector2.zero,Vector2.right,Vector2.one,Vector2.up}};owned.Add(mesh);
                    Endfield.EndfieldOfficialFrameGlobals.ApplyGlobals();Shader.SetGlobalFloat("_EndfieldLabelMode",0);Shader.SetGlobalFloat("_EndfieldDebugValueMode",0);
                    Shader.SetGlobalVector("_CharacterParams13",Vector4.zero);Shader.SetGlobalFloat("_EndfieldCharacterSelfShadow",0);Shader.SetGlobalVector("_WorldSpaceCameraPos",new Vector4(0,0,2,1));
                    var reference=Fixture(owned,(f,m)=>Color.clear);Fill(levels,(f,m)=>palette(0,m));int productionCases=0;
                    foreach(float lod in new[]{-2f,.49f,.51f,1.49f,1.51f,3.49f,3.51f,4.49f,4.51f,5f})
                    {
                        float roughness=Mathf.Pow(2,(lod-5)/1.2f);mat.SetFloat("_Smoothness",1-roughness);
                        int mip=Math.Clamp((int)Math.Floor(lod+.5),0,7);Color value=palette(0,mip);
                        Fill(reference,(f,m)=>value);Shader.SetGlobalTexture("_CharMaxCubemap",reference);Shader.SetGlobalFloat("_EndfieldCapturedCubemapAvailable",1);
                        Color expected=Draw(mat,mesh,rt,readback);Shader.SetGlobalTexture("_CharMaxCubemap",levels);
                        Color actual=Draw(mat,mesh,rt,readback);
                        Require(expected.r>1e-4&&Error(actual,expected)<2e-5,"Production cube nearest-mip mismatch lod="+lod+" error="+Number(Error(actual,expected)));productionCases++;
                    }
                    lines.Add("CharacterLit source IBL original roughness-log2 LOD / captured inline Clamp sampler PASS cases="+productionCases);
                    using(var scope=EndfieldCapturedEnvironmentInputs.Load())
                    {
                        scope.Bind();Color native=Draw(mat,mesh,rt,readback);Shader.SetGlobalFloat("_EndfieldCapturedCubemapAvailable",0);Color absent=Draw(mat,mesh,rt,readback);
                        Require(native.r>1e-4&&Math.Abs(absent.r)<1e-6,"Native cube did not reach CharacterLit IBL / availability gate failed");
                    }
                    lines.Add("CharacterLit native BC6H consumption / missing-input gate PASS");
                    foreach(var checkedShader in new[]{shader,probeShader})Require(!ShaderUtil.GetShaderMessages(checkedShader).Any(m=>m.severity==UnityEditor.Rendering.ShaderCompilerMessageSeverity.Error),"Shader compiler error");
                    for(int pass=0;pass<mat.passCount;pass++)Require(mat.SetPass(pass),"Default pass failed");
                    lines.Add("RESULT PASS defaultPasses="+mat.passCount+"; bounded native environment path, not full scene/post/motion certification.");
                }
                using(var stream=new FileStream(output,FileMode.CreateNew,FileAccess.Write))using(var writer=new StreamWriter(stream))foreach(var line in lines)writer.WriteLine(line);
                Debug.Log("Cloth environment PASS: "+output);
            }
            finally
            {
                for(int i=0;i<vectors.Length;i++)Shader.SetGlobalVector(vectors[i],savedVectors[i]);for(int i=0;i<floats.Length;i++)Shader.SetGlobalFloat(floats[i],savedFloats[i]);Shader.SetGlobalTexture("_CharMaxCubemap",savedCube);
                RenderTexture.active=previousRT;
                for(int i=owned.Count-1;i>=0;i--)if(owned[i]!=null){if(owned[i] is RenderTexture rt)rt.Release();Object.DestroyImmediate(owned[i]);}
                if(scene.IsValid())EditorSceneManager.ClosePreviewScene(scene);
            }
        }
    }
}
