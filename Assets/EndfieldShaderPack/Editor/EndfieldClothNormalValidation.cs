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
    // Batch-only synthetic CPU/GPU algebra and real CharacterLit consumption.
    // No original scene/material/import mutation; no official-image comparison.
    public static class EndfieldClothNormalValidation
    {
        struct Case
        {
            public string name;
            public Vector4 packed,tangent;
            public Vector3 geometry;
            public float scale,backface;
            public Case(string n,Vector4 p,Vector3 g,Vector4 t,float s=1,float b=1)
            {name=n;packed=p;geometry=g;tangent=t;scale=s;backface=b;}
        }
        static string Number(double x)=>x.ToString("R",CultureInfo.InvariantCulture);
        static double[] Expected(Case c,bool geometric)
        {
            double[] n={c.geometry.x,c.geometry.y,c.geometry.z};
            double[] t={c.tangent.x,c.tangent.y,c.tangent.z};
            double x=(double)c.packed.x*c.packed.w*2-1, y=(double)c.packed.y*2-1;
            // The source literal is float; retain its binary value in the double
            // oracle, especially where a degenerate world vector cancels exactly.
            double z=Math.Max((double)1e-16f,Math.Sqrt(1-Math.Min(1,Math.Max(0,x*x+y*y))));
            double[] b={(n[1]*t[2]-n[2]*t[1])*c.tangent.w,(n[2]*t[0]-n[0]*t[2])*c.tangent.w,(n[0]*t[1]-n[1]*t[0])*c.tangent.w};
            double[] v=geometric?n.ToArray():Enumerable.Range(0,3).Select(i=>x*c.scale*t[i]+y*c.scale*b[i]+z*n[i]).ToArray();
            double len2=v.Sum(a=>a*a);
            double inv=1/Math.Sqrt(geometric?len2:Math.Max(len2,1.175494351e-38));
            return v.Select(a=>a*inv*c.backface).ToArray();
        }
        static double Error(Color a,double[] b)=>Math.Max(Math.Abs(a.r-b[0]),Math.Max(Math.Abs(a.g-b[1]),Math.Abs(a.b-b[2])));
        static float Difference(Color a,Color b)=>Mathf.Max(Mathf.Abs(a.r-b.r),Mathf.Abs(a.g-b.g),Mathf.Abs(a.b-b.b));
        static void Compiled(Shader shader)
        {
            if(shader==null||!shader.isSupported) throw new Exception("Missing/unsupported shader");
            var errors=ShaderUtil.GetShaderMessages(shader).Where(m=>m.severity==UnityEditor.Rendering.ShaderCompilerMessageSeverity.Error).ToArray();
            if(errors.Length!=0) throw new Exception(string.Join("\n",errors.Select(e=>e.message)));
        }
        static Color Read(RenderTexture rt,Texture2D readback)
        {
            RenderTexture.active=rt; readback.ReadPixels(new Rect(0,0,4,4),0,0); readback.Apply();
            var c=readback.GetPixel(2,2);
            if(!float.IsFinite(c.r)||!float.IsFinite(c.g)||!float.IsFinite(c.b)||c.a<=0) throw new Exception("No finite GPU fragment");
            return c;
        }
        static Texture2D Constant(Color c,List<Object> owned)
        {
            var tex=new Texture2D(2,2,TextureFormat.RGBAFloat,false,true);
            tex.SetPixels(new[]{c,c,c,c}); tex.Apply(); owned.Add(tex); return tex;
        }
        static Color Draw(Material mat,Mesh mesh,RenderTexture rt,Texture2D readback)
        {
            var cmd=new CommandBuffer{name="Captured cloth normal probe"};
            try {
                cmd.SetRenderTarget(rt);cmd.ClearRenderTarget(true,true,Color.clear);
                cmd.SetViewProjectionMatrices(Matrix4x4.Translate(new Vector3(0,0,-2)),GL.GetGPUProjectionMatrix(Matrix4x4.Ortho(-.5f,.5f,-.5f,.5f,.1f,10),true));
                cmd.DrawMesh(mesh,Matrix4x4.identity,mat,0,0);Graphics.ExecuteCommandBuffer(cmd);
                return Read(rt,readback);
            } finally {cmd.Release();}
        }
        static int Production(Material mat,RenderTexture rt,Texture2D readback,List<string> lines)
        {
            var owned=new List<Object>();
            string[] vectors=Enumerable.Range(0,16).Select(i=>"_CharacterParams"+i).Concat(new[]{"_EnvironmentGlobalParams0","_ExposureWithMiscParams","_CharacterLightDir","_CharacterLightColor","_WorldSpaceCameraPos"}).ToArray();
            string[] floats={"_EndfieldOfficialFrameEnabled","_EndfieldOfficialShadingEnabled","_EndfieldCapturedLightIntensity","_EndfieldCapturedCubemapAvailable","_EndfieldCapturedGlobalMipBias","_EndfieldLabelMode","_EndfieldDebugValueMode","_EndfieldCharacterSelfShadow"};
            var savedVectors=vectors.Select(Shader.GetGlobalVector).ToArray();var savedFloats=floats.Select(Shader.GetGlobalFloat).ToArray();
            try {
                Endfield.EndfieldOfficialFrameGlobals.ApplyGlobals();
                Shader.SetGlobalFloat("_EndfieldLabelMode",0);Shader.SetGlobalFloat("_EndfieldCharacterSelfShadow",0);
                Shader.SetGlobalVector("_WorldSpaceCameraPos",new Vector4(0,0,2,1));
                Shader.SetGlobalVector("_CharacterLightDir",new Vector4(0,0,1,1));Shader.SetGlobalVector("_CharacterLightColor",Vector4.one);
                Shader.SetGlobalVector("_CharacterParams11",new Vector4(0,0,1,0));Shader.SetGlobalVector("_CharacterParams12",new Vector4(1,1,1,0));Shader.SetGlobalVector("_CharacterParams13",Vector4.zero);
                mat.SetFloat("_MaterialFamily",0);mat.SetFloat("_Cull",0);mat.SetFloat("_UseBumpMap",1);mat.SetFloat("_BumpScale",.6f);
                mat.SetFloat("_UseMetallicGlossMap",1);mat.SetFloat("_UseDiffRampMap",1);mat.SetFloat("_UseSpecRampMap",0);
                mat.SetFloat("_UseEmission",0);mat.SetFloat("_ClearCoat",0);mat.SetFloat("_UseShadowLutTex",0);
                mat.SetColor("_BaseColor",new Color(0,0,0,1));
                mat.SetTexture("_BaseMap",Constant(Color.black,owned));mat.SetTexture("_MetallicGlossMap",Constant(new Color(0,0,1,.4f),owned));mat.SetTexture("_DiffRampMap",Constant(Color.white,owned));
                var packed=new Vector4(.8f,.35f,.1f,.75f);mat.SetTexture("_BumpMap",Constant(packed,owned));
                var mesh=new Mesh{name="VaryingClothNormalQuad"};owned.Add(mesh);
                mesh.vertices=new[]{new Vector3(-.5f,-.5f,0),new Vector3(.5f,-.5f,0),new Vector3(.5f,.5f,0),new Vector3(-.5f,.5f,0)};
                // All values vary only across x, so RT y-orientation does not change
                // barycentric expected N/T at pixel (2,2): right weight = .625.
                mesh.normals=new[]{Vector3.forward,new Vector3(.6f,0,.8f),new Vector3(.6f,0,.8f),Vector3.forward};
                mesh.tangents=new[]{new Vector4(1,0,0,1),new Vector4(.8f,0,-.6f,1),new Vector4(.8f,0,-.6f,1),new Vector4(1,0,0,1)};
                mesh.uv=Enumerable.Repeat(new Vector2(.5f,.5f),4).ToArray();
                var fixture=new Case("production-interpolation",packed,new Vector3(.375f,0,.875f),new Vector4(.875f,0,-.375f,1),.6f);
                var signs=new List<int>();int count=0;
                foreach(int flip in new[]{1,0}) foreach(int winding in new[]{0,1}) {
                    mat.SetFloat("_BackFaceNormalFlip",flip);
                    mesh.triangles=winding==0?new[]{0,1,2,0,2,3}:new[]{0,2,1,0,3,2};
                    Shader.SetGlobalFloat("_EndfieldDebugValueMode",10);Color geometry=Draw(mat,mesh,rt,readback);
                    int sign=flip==1?1:(geometry.b>=0?1:-1);if(flip==0) signs.Add(sign);
                    fixture.backface=sign;
                    double geometryError=Error(geometry,Expected(fixture,true));
                    Shader.SetGlobalFloat("_EndfieldDebugValueMode",9);double mappedError=Error(Draw(mat,mesh,rt,readback),Expected(fixture,false));
                    if(Math.Max(geometryError,mappedError)>2e-5) throw new Exception("Production interpolation/face mismatch "+Number(geometryError)+" / "+Number(mappedError));
                    lines.Add("Production raw interpolation flip="+flip+" winding="+winding+" PASS geometry="+Number(geometryError)+" mapped="+Number(mappedError));count+=2;
                }
                if(signs.Count!=2||signs[0]!=-signs[1]) throw new Exception("Winding did not produce complementary backface signs");
                mat.SetFloat("_BackFaceNormalFlip",1);mesh.triangles=new[]{0,1,2,0,2,3};Shader.SetGlobalFloat("_EndfieldDebugValueMode",9);
                var blueA=Draw(mat,mesh,rt,readback);mat.SetTexture("_BumpMap",Constant(new Color(.8f,.35f,.9f,.75f),owned));var blueB=Draw(mat,mesh,rt,readback);
                if(Difference(blueA,blueB)>2e-5) throw new Exception("B channel changed production normal");
                lines.Add("Production unused B-channel isolation PASS difference="+Number(Difference(blueA,blueB)));count++;

                // Independent consumer reference: feed the CPU-decoded direction
                // as geometry to the unmapped path. No copied lighting formula.
                Shader.SetGlobalFloat("_EndfieldDebugValueMode",0);
                Shader.SetGlobalVector("_CharacterParams7",new Vector4(.5f,1,0,0));
                mat.SetColor("_BaseColor",Color.white);mat.SetTexture("_BaseMap",Constant(new Color(.1f,.2f,.3f,1),owned));
                fixture.backface=1;
                var litMapped=Draw(mat,mesh,rt,readback);
                var originalNormals=mesh.normals;double[] cpuMapped=Expected(fixture,false);
                mesh.normals=Enumerable.Repeat(new Vector3((float)cpuMapped[0],(float)cpuMapped[1],(float)cpuMapped[2]),4).ToArray();
                mat.SetFloat("_UseBumpMap",0);var litReference=Draw(mat,mesh,rt,readback);
                float diffuseError=Difference(litMapped,litReference);
                if(litMapped.g<=.001 || diffuseError>2e-5)throw new Exception("Mapped N direct diffuse reference mismatch "+diffuseError);
                lines.Add("Production mapped N direct diffuse CPU-direction reference PASS difference="+Number(diffuseError));count++;
                mesh.normals=originalNormals;mat.SetFloat("_UseBumpMap",1);
                mat.SetTexture("_BumpMap",Constant(new Color(.5f,.5f,0,1),owned));var litFlat=Draw(mat,mesh,rt,readback);
                float diffuseResponse=Difference(litMapped,litFlat);
                if(diffuseResponse<1e-3)throw new Exception("Mapped N not consumed by direct diffuse "+diffuseResponse);
                lines.Add("Production mapped N direct diffuse response PASS difference="+Number(diffuseResponse));count++;
                mat.SetColor("_BaseColor",new Color(0,0,0,1));

                // Independent normal-sensitive VFX consumer; N.y=0 so either RT
                // y orientation gives the same dot(V,N). No image reference used.
                Shader.SetGlobalFloat("_EndfieldDebugValueMode",0);mat.SetFloat("_BumpScale",1);
                mesh.tangents=Enumerable.Repeat(new Vector4(1,0,0,1),4).ToArray();
                var rimPacked=new Vector4(.8f,.5f,0,1);mat.SetTexture("_BumpMap",Constant(rimPacked,owned));
                mat.SetFloat("_EnableVFXColorAdjustment",1);mat.SetFloat("_ColorAdjustmentRimWidth",1);mat.SetFloat("_ColorAdjustmentRimIntensity",1);mat.SetColor("_ColorAdjustmentRimColor",Color.white);
                var rimFixture=new Case("VFX",rimPacked,new Vector3(.375f,0,.875f),new Vector4(1,0,0,1));
                double[] n=Expected(rimFixture,false);double len=Math.Sqrt(4+2*.125*.125);
                double dot=(-.125*n[0]+2*n[2])/len;double k=1-Math.Max(0,Math.Min(1,dot));double expected=k*k*(3-2*k);
                double rimError=Error(Draw(mat,mesh,rt,readback),new[]{expected,expected,expected});
                if(rimError>2e-5) throw new Exception("Production VFX normal/view mismatch "+Number(rimError));
                lines.Add("Production mapped float N / view consumed by VFX PASS error="+Number(rimError));count++;

                mat.SetFloat("_EnableVFXColorAdjustment",0);mat.SetFloat("_MaterialFamily",1);
                Shader.SetGlobalFloat("_EndfieldDebugValueMode",0);var skin=Draw(mat,mesh,rt,readback);Shader.SetGlobalFloat("_EndfieldDebugValueMode",9);var skinDiagnostic=Draw(mat,mesh,rt,readback);
                if(Difference(skin,skinDiagnostic)>2e-5) throw new Exception("Cloth diagnostic leaked into skin");
                lines.Add("Production skin diagnostic isolation PASS");count++;
                mat.SetFloat("_MaterialFamily",0);Shader.SetGlobalFloat("_EndfieldOfficialShadingEnabled",0);
                Shader.SetGlobalFloat("_EndfieldDebugValueMode",0);var legacy=Draw(mat,mesh,rt,readback);Shader.SetGlobalFloat("_EndfieldDebugValueMode",9);var legacyDiagnostic=Draw(mat,mesh,rt,readback);
                if(Difference(legacy,legacyDiagnostic)>2e-5) throw new Exception("Cloth diagnostic changed source-off path");
                lines.Add("Production source-off diagnostic isolation PASS");count++;
                return count;
            } finally {
                for(int i=0;i<vectors.Length;i++) Shader.SetGlobalVector(vectors[i],savedVectors[i]);for(int i=0;i<floats.Length;i++) Shader.SetGlobalFloat(floats[i],savedFloats[i]);
                foreach(var o in owned)Object.DestroyImmediate(o);
            }
        }
        public static void RunBatch()
        {
            if(!Application.isBatchMode)throw new Exception("Use an isolated batch editor");
            string output=Environment.GetEnvironmentVariable("ENDFIELD_CLOTH_NORMAL_REPORT");
            if(string.IsNullOrEmpty(output)||File.Exists(output))throw new Exception("Report path must be fresh");
            var cases=new[]{
                new Case("flat",new Vector4(.5f,.5f,.9f,1),Vector3.forward,new Vector4(1,0,0,1)),
                new Case("RA",new Vector4(.8f,.35f,.1f,.75f),Vector3.forward,new Vector4(1,0,0,1)),
                new Case("unused-B",new Vector4(.8f,.35f,.9f,.75f),Vector3.forward,new Vector4(1,0,0,1)),
                new Case("RA-equivalent",new Vector4(.6f,.35f,.1f,1),Vector3.forward,new Vector4(1,0,0,1)),
                new Case("raw-interpolation",new Vector4(.7f,.8f,.3f,.6f),new Vector3(.1f,.2f,.7f),new Vector4(.8f,.15f,.2f,-1)),
                new Case("nonorthogonal-fractional-w",new Vector4(.7f,.8f,.3f,.6f),new Vector3(.4f,.1f,.8f),new Vector4(.9f,.2f,.1f,.3f)),
                new Case("outside-disk",new Vector4(1,1,0,1),Vector3.forward,new Vector4(1,0,0,1)),
                new Case("boundary",new Vector4(1,.5f,0,1),Vector3.forward,new Vector4(1,0,0,1)),
                new Case("scale-after-Z",new Vector4(.75f,.75f,0,1),Vector3.forward,new Vector4(1,0,0,1),.25f),
                new Case("scale-zero-boundary",new Vector4(1,.5f,0,1),Vector3.forward,new Vector4(1,0,0,1),0),
                new Case("zero-world-guard",new Vector4(1,.5f,0,1),Vector3.forward,new Vector4(0,0,-1e-16f,1)),
                new Case("negative-scale",new Vector4(.7f,.6f,0,1),Vector3.forward,new Vector4(1,0,0,1),-1),
                new Case("backface",new Vector4(.8f,.35f,.1f,.75f),Vector3.forward,new Vector4(1,0,0,1),1,-1),
                new Case("fractional-backfactor",new Vector4(.8f,.35f,.1f,.75f),Vector3.forward,new Vector4(1,0,0,1),1,.4f),
                new Case("zero-backfactor",new Vector4(.8f,.35f,.1f,.75f),Vector3.forward,new Vector4(1,0,0,1),1,0)
            };
            var lines=new List<string>{"Synthetic source algebra / production probes; not official-image equality.","GPU="+SystemInfo.graphicsDeviceType+" / "+SystemInfo.graphicsDeviceName};
            Material probe=null,production=null;RenderTexture rt=null;Texture2D readback=null;GameObject cameraObject=null;Scene scene=default;var prior=RenderTexture.active;
            try {
                if(SystemInfo.graphicsDeviceType==GraphicsDeviceType.Null)throw new Exception("GPU required");
                rt=new RenderTexture(4,4,0,RenderTextureFormat.ARGBFloat,RenderTextureReadWrite.Linear);rt.Create();readback=new Texture2D(4,4,TextureFormat.RGBAFloat,false,true);
                scene=EditorSceneManager.NewPreviewScene();cameraObject=new GameObject("ClothNormalPipelineInit");SceneManager.MoveGameObjectToScene(cameraObject,scene);
                var camera=cameraObject.AddComponent<Camera>();camera.targetTexture=rt;camera.enabled=false;camera.Render();if(RenderPipelineManager.currentPipeline==null)throw new Exception("URP did not initialize");
                lines.Add("Pipeline="+RenderPipelineManager.currentPipeline.GetType().FullName);
                foreach(string part in new[]{"01","02"}) {
                    string path="Assets/Typhoeus/T_actor_typhoea_cloth_"+part+"_N.png";
                    var texture=AssetDatabase.LoadAssetAtPath<Texture2D>(path);
                    var importer=AssetImporter.GetAtPath(path) as TextureImporter;
                    if(texture==null||importer==null)throw new Exception("Missing imported normal "+path);
                    lines.Add("Imported normal observation cloth"+part+" format="+texture.graphicsFormat+" textureFormat="+texture.format+" size="+texture.width+"x"+texture.height+" type="+importer.textureType+" sRGB="+importer.sRGBTexture+"; bytes/mips NOT certified");
                }
                var shader=AssetDatabase.LoadAssetAtPath<Shader>("Assets/EndfieldShaderPack/Editor/EndfieldClothNormalProbe.shader");Compiled(shader);probe=new Material(shader);
                double maxError=0;int kernel=0;
                foreach(var c in cases)foreach(bool geometric in new[]{false,true}) {
                    probe.SetVector("_ProbePacked",c.packed);probe.SetVector("_ProbeGeometry",c.geometry);probe.SetVector("_ProbeTangent",c.tangent);probe.SetVector("_ProbeParams",new Vector4(c.scale,c.backface,geometric?1:0,0));
                    Graphics.Blit(Texture2D.blackTexture,rt,probe,0);double error=Error(Read(rt,readback),Expected(c,geometric));
                    if(error>2e-5)throw new Exception("Kernel mismatch "+c.name+" "+Number(error));maxError=Math.Max(maxError,error);kernel++;
                    lines.Add(c.name+(geometric?" geometry":" mapped")+" PASS error="+Number(error));
                }
                probe.SetVector("_ProbePacked",new Vector4(1,.5f,0,1));probe.SetVector("_ProbeParams",new Vector4(0,1,2,0));Graphics.Blit(Texture2D.blackTexture,rt,probe,0);
                double floor=Read(rt,readback).b;double floorRelative=Math.Abs(floor/1e-16-1);
                if(floorRelative>1e-5)throw new Exception("Z floor / sqrt ordering mismatch "+Number(floor));kernel++;
                lines.Add("Z-after-sqrt floor PASS value="+Number(floor)+" relativeError="+Number(floorRelative));Compiled(shader);
                var productionShader=Shader.Find("Endfield/CharacterLit");Compiled(productionShader);production=new Material(productionShader);
                for(int p=0;p<production.passCount;p++)if(!production.SetPass(p))throw new Exception("SetPass failed "+p);
                int count=Production(production,rt,readback,lines);Compiled(productionShader);
                lines.Add("RESULT PASS kernel="+kernel+" maxError="+Number(maxError)+" production="+count+" passes="+production.passCount+"; native fetch/mip/import equivalence NOT certified");
                using(var stream=new FileStream(output,FileMode.CreateNew,FileAccess.Write))using(var writer=new StreamWriter(stream))foreach(var line in lines)writer.WriteLine(line);
                Debug.Log("Cloth normal probe PASS: "+output);
            } finally {
                RenderTexture.active=prior;if(probe!=null)Object.DestroyImmediate(probe);if(production!=null)Object.DestroyImmediate(production);
                if(cameraObject!=null)Object.DestroyImmediate(cameraObject);if(scene.IsValid())EditorSceneManager.ClosePreviewScene(scene);
                if(rt!=null){rt.Release();Object.DestroyImmediate(rt);}if(readback!=null)Object.DestroyImmediate(readback);
            }
        }
    }
}
