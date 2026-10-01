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
    // Synthetic source-algebra tests. Batch only: no project scene load/save,
    // original material mutation, screenshot fitting or existing report overwrite.
    public static class EndfieldClothEmissionValidation
    {
        static readonly double[] Luma = { .2126729041337967, .7151522040367126, .07217500358819962 };
        static Texture2D Texture(Color[] pixels, int width, List<Object> owned)
        {
            var result = new Texture2D(width,1,TextureFormat.RGBAFloat,false,true);
            result.SetPixels(pixels); result.Apply(); owned.Add(result); return result;
        }
        static Texture2D Constant(Color color, List<Object> owned) => Texture(new[] {color,color},2,owned);

        static void CheckCompiled(Shader shader)
        {
            if (shader == null || !shader.isSupported) throw new Exception("Missing/unsupported shader");
            var errors = ShaderUtil.GetShaderMessages(shader).Where(m=>m.severity==UnityEditor.Rendering.ShaderCompilerMessageSeverity.Error).ToArray();
            if (errors.Length != 0) throw new Exception(string.Join("\n",errors.Select(m=>m.message)));
        }

        static Color Read(RenderTexture rt, Texture2D readback)
        {
            RenderTexture.active=rt;
            readback.ReadPixels(new Rect(0,0,4,4),0,0); readback.Apply();
            var color = readback.GetPixel(2,2);
            if (!float.IsFinite(color.r) || !float.IsFinite(color.g) || !float.IsFinite(color.b) || !float.IsFinite(color.a))
                throw new Exception("Nonfinite GPU output");
            return color;
        }

        static Color Draw(Material material, Mesh mesh, RenderTexture rt, Texture2D readback)
        {
            var cmd = new CommandBuffer { name="Cloth emission source probe" };
            try
            {
                cmd.SetRenderTarget(rt); cmd.ClearRenderTarget(true,true,Color.clear);
                cmd.SetViewProjectionMatrices(Matrix4x4.Translate(new Vector3(0,0,-2)),
                    GL.GetGPUProjectionMatrix(Matrix4x4.Ortho(-.5f,.5f,-.5f,.5f,.1f,10),true));
                cmd.DrawMesh(mesh,Matrix4x4.identity,material,0,0); Graphics.ExecuteCommandBuffer(cmd);
                Color result = Read(rt,readback);
                // Production output alpha is deliberately not used as the source factor.
                if (result.a <= 0) throw new Exception("No production fragment");
                return result;
            }
            finally { cmd.Release(); }
        }

        static double Error(Color actual, double[] expected) => Math.Max(Math.Abs(actual.r-expected[0]),Math.Max(Math.Abs(actual.g-expected[1]),Math.Abs(actual.b-expected[2])));
        static float Difference(Color a, Color b) => Mathf.Max(Mathf.Abs(a.r-b.r),Mathf.Abs(a.g-b.g),Mathf.Abs(a.b-b.b));
        static string Number(double value) => value.ToString("R",CultureInfo.InvariantCulture);
        static double[] ExpectedEmission(Color sample, Color color, float brightness, float baseAlpha, float selector)
        {
            double factor = (1.0-(double)selector)+(double)baseAlpha*selector;
            return new[] {((double)sample.r*color.r)*brightness*factor,
                          ((double)sample.g*color.g)*brightness*factor,
                          ((double)sample.b*color.b)*brightness*factor};
        }

        static int ProbeProduction(Material mat, RenderTexture rt, Texture2D readback, List<string> lines)
        {
            var owned = new List<Object>();
            string[] vectors = Enumerable.Range(0,16).Select(i=>"_CharacterParams"+i).Concat(new[] {
                "_EnvironmentGlobalParams0","_ExposureWithMiscParams","_CharacterLightDir","_CharacterLightColor","_WorldSpaceCameraPos" }).ToArray();
            string[] floats = {"_EndfieldOfficialFrameEnabled","_EndfieldOfficialShadingEnabled","_EndfieldCapturedLightIntensity",
                "_EndfieldCapturedCubemapAvailable","_EndfieldCapturedGlobalMipBias","_EndfieldLabelMode","_EndfieldDebugValueMode","_EndfieldCharacterSelfShadow"};
            var savedVectors = vectors.Select(Shader.GetGlobalVector).ToArray();
            var savedFloats = floats.Select(Shader.GetGlobalFloat).ToArray();
            var savedCube = Shader.GetGlobalTexture("_CharMaxCubemap");
            try
            {
                Endfield.EndfieldOfficialFrameGlobals.ApplyGlobals();
                Shader.SetGlobalFloat("_EndfieldLabelMode",0); Shader.SetGlobalFloat("_EndfieldDebugValueMode",0);
                Shader.SetGlobalFloat("_EndfieldCharacterSelfShadow",0);
                Shader.SetGlobalVector("_CharacterLightDir",new Vector4(0,0,1,1));
                Shader.SetGlobalVector("_CharacterLightColor",Vector4.one);
                Shader.SetGlobalVector("_WorldSpaceCameraPos",new Vector4(0,0,2,1));
                Shader.SetGlobalVector("_CharacterParams11",new Vector4(0,0,1,0));
                Shader.SetGlobalVector("_CharacterParams12",new Vector4(1,1,1,0));
                Shader.SetGlobalVector("_CharacterParams13",Vector4.zero);
                mat.SetFloat("_MaterialFamily",0); mat.SetFloat("_Cull",0);
                mat.SetFloat("_UseBumpMap",0); mat.SetFloat("_UseMetallicGlossMap",1);
                mat.SetFloat("_UseDiffRampMap",1); mat.SetFloat("_UseSpecRampMap",0);
                mat.SetFloat("_UseShadowLutTex",0); mat.SetFloat("_ClearCoat",0);
                mat.SetFloat("_UseEmission",1); mat.SetFloat("_EmissionBrightness",8);
                mat.SetColor("_BaseColor",new Color(0,0,0,1));
                var emissionColor = new Color(1.2f,.8f,.4f,1);
                var emissionSample = new Color(.125f,.25f,.5f,.9f);
                // Color-property upload converts sRGB even with SetVector. Supply
                // the encoded authoring value so the GPU sees the linear fixture.
                mat.SetColor("_EmissionColor",emissionColor.gamma);
                mat.SetTexture("_MetallicGlossMap",Constant(new Color(0,0,1,.4f),owned));
                mat.SetTexture("_DiffRampMap",Constant(Color.white,owned));
                mat.SetTexture("_EmissionMap",Constant(emissionSample,owned));
                var mesh = new Mesh { name="SyntheticClothQuad" }; owned.Add(mesh);
                mesh.vertices = new[] {new Vector3(-.5f,-.5f,0),new Vector3(.5f,-.5f,0),new Vector3(.5f,.5f,0),new Vector3(-.5f,.5f,0)};
                mesh.normals=Enumerable.Repeat(Vector3.forward,4).ToArray();
                mesh.tangents=Enumerable.Repeat(new Vector4(1,0,0,1),4).ToArray();
                mesh.uv=Enumerable.Repeat(new Vector2(.125f,.5f),4).ToArray(); mesh.triangles=new[] {0,1,2,0,2,3};
                int cases=0;
                foreach (float baseAlpha in new[] {0f,.25f,1f})
                foreach (float selector in new[] {0f,.25f,1f})
                {
                    mat.SetTexture("_BaseMap",Constant(new Color(.4f,.5f,.6f,baseAlpha),owned));
                    mat.SetFloat("_AlphaPremultiply",selector);
                    var actual=Draw(mat,mesh,rt,readback);
                    double error=Error(actual,ExpectedEmission(emissionSample,emissionColor,8,baseAlpha,selector));
                    if (error>2e-5) throw new Exception("Production alpha selection mismatch "+Number(error)+" actual="+actual);
                    lines.Add("Production factor baseAlpha="+baseAlpha+" selector="+selector+" PASS error="+Number(error)); cases++;
                }
                mat.SetFloat("_AlphaPremultiply",1);
                mat.SetColor("_BaseColor",new Color(0,0,0,.5f));
                mat.SetTexture("_BaseMap",Texture(new[] {new Color(0,0,0,.2f),new Color(0,0,0,.8f)},2,owned));
                mat.SetTexture("_EmissionMap",Texture(new[] {new Color(.8f,0,0,1),new Color(0,0,.5f,0)},2,owned));
                mat.SetTextureScale("_BaseMap",new Vector2(2,1)); mat.SetTextureOffset("_BaseMap",new Vector2(.5f,0));
                mat.SetTextureOffset("_EmissionMap",new Vector2(-.125f,0)); // must be ignored by source
                var uvSample = new Color(0,0,.5f,0);
                double uvError=Error(Draw(mat,mesh,rt,readback),ExpectedEmission(uvSample,emissionColor,8,.8f*.5f,1));
                if (uvError>2e-5) throw new Exception("Shared BaseUV or BaseColor alpha mismatch "+Number(uvError));
                lines.Add("Production shared BaseST UV / no EmissionST / baseMap alpha * BaseColor alpha PASS error="+Number(uvError)); cases++;

                mat.SetTextureScale("_BaseMap",Vector2.one); mat.SetTextureOffset("_BaseMap",Vector2.zero);
                mat.SetTextureOffset("_EmissionMap",Vector2.zero);
                mat.SetColor("_BaseColor",new Color(0,0,0,1)); mat.SetFloat("_AlphaPremultiply",0);
                mat.SetTexture("_BaseMap",Constant(Color.clear,owned));
                mat.SetTexture("_EmissionMap",Constant(emissionSample,owned));
                mat.SetFloat("_EnableVFXColorAdjustment",1); mat.SetFloat("_ColorAdjustmentSaturation",.4f);
                mat.SetFloat("_ColorAdjustmentContrast",.75f); mat.SetFloat("_ColorAdjustmentBrightness",1.3f);
                mat.SetFloat("_ColorAdjustmentRimIntensity",0);
                var blend = new Color(.6f,.8f,.2f,.2f); mat.SetColor("_ColorAdjustmentColorBlend",blend.gamma);
                Shader.SetGlobalVector("_ExposureWithMiscParams",new Vector4(1,.8f,1.6f,.1f));
                var e=ExpectedEmission(emissionSample,emissionColor,8,0,0);
                double lum=e.Select((v,i)=>v*Luma[i]).Sum();
                double[] b={blend.r,blend.g,blend.b};
                for (int i=0;i<3;i++) e[i]=(((.5*(1-.75)+(lum*(1-(double).4f)+e[i]*(double).4f)*.75)*(double)1.3f)*(1-(double)blend.a)+b[i]*blend.a)*(double).8f;
                double vfxError=Error(Draw(mat,mesh,rt,readback),e);
                if (vfxError>3e-5) throw new Exception("Emission/VFX/output exposure order mismatch "+Number(vfxError));
                lines.Add("Production emission before VFX and one output exposure PASS error="+Number(vfxError)); cases++;

                mat.SetFloat("_EnableVFXColorAdjustment",0);
                Shader.SetGlobalVector("_ExposureWithMiscParams",new Vector4(1,1,1.6f,.1f));
                mat.SetFloat("_UseEmission",0);
                mat.SetColor("_BaseColor",Color.white);
                mat.SetTexture("_BaseMap",Constant(new Color(.02f,.03f,.04f,.25f),owned));
                mat.SetFloat("_AlphaPremultiply",0); var diffuseUnselected=Draw(mat,mesh,rt,readback);
                mat.SetFloat("_AlphaPremultiply",1); var diffuseSelected=Draw(mat,mesh,rt,readback);
                double diffuseLuma=diffuseUnselected.r*Luma[0]+diffuseUnselected.g*Luma[1]+diffuseUnselected.b*Luma[2];
                if(diffuseLuma<=.001 || diffuseLuma>=.49) throw new Exception("Diffuse isolation must be nonzero below saturation boost");
                double diffuseError=Error(diffuseSelected,new[] {(double)diffuseUnselected.r*.25,diffuseUnselected.g*.25,diffuseUnselected.b*.25});
                if(diffuseError>2e-5) throw new Exception("Diffuse factor mismatch "+Number(diffuseError));
                lines.Add("Production direct diffuse factor .25 PASS error="+Number(diffuseError)); cases++;

                mat.SetColor("_BaseColor",new Color(0,0,0,1));
                mat.SetTexture("_BaseMap",Constant(Color.clear,owned));
                mat.SetTexture("_MetallicGlossMap",Constant(new Color(0,1,1,.4f),owned));
                Shader.SetGlobalVector("_CharacterParams13",new Vector4(0,0,0,1));
                mat.SetFloat("_AlphaPremultiply",0); var specUnselected=Draw(mat,mesh,rt,readback);
                mat.SetFloat("_AlphaPremultiply",1); var specSelected=Draw(mat,mesh,rt,readback);
                float specError=Difference(specUnselected,specSelected);
                if(specUnselected.r<=1e-4 || specError>2e-5) throw new Exception("Direct specular factor isolation failed "+specError);
                lines.Add("Production direct specular NOT selected PASS difference="+Number(specError)); cases++;

                Shader.SetGlobalVector("_CharacterParams13",Vector4.zero);
                var cube=new Cubemap(2,TextureFormat.RGBAFloat,false); owned.Add(cube);
                for(int face=0;face<6;face++) cube.SetPixels(Enumerable.Repeat(new Color(.2f,.3f,.4f,1),4).ToArray(),(CubemapFace)face);
                cube.Apply(); Shader.SetGlobalTexture("_CharMaxCubemap",cube);
                Shader.SetGlobalFloat("_EndfieldCapturedCubemapAvailable",1);
                mat.SetFloat("_AlphaPremultiply",0); var iblUnselected=Draw(mat,mesh,rt,readback);
                mat.SetFloat("_AlphaPremultiply",1); var iblSelected=Draw(mat,mesh,rt,readback);
                float iblError=Difference(iblUnselected,iblSelected);
                if(iblUnselected.r<=1e-4 || iblError>2e-5) throw new Exception("IBL factor isolation failed "+iblError);
                lines.Add("Production IBL NOT selected PASS difference="+Number(iblError)+"; synthetic constant cube only"); cases++;
                Shader.SetGlobalFloat("_EndfieldCapturedCubemapAvailable",0);

                mat.SetFloat("_MaterialFamily",1); mat.SetFloat("_UseEmission",0);
                var off=Draw(mat,mesh,rt,readback); mat.SetFloat("_UseEmission",1); var on=Draw(mat,mesh,rt,readback);
                if (Difference(off,on)>2e-5) throw new Exception("Cloth emission leaked into skin family");
                lines.Add("Production skin family emission isolation PASS"); cases++;
                mat.SetFloat("_MaterialFamily",0); Shader.SetGlobalFloat("_EndfieldOfficialShadingEnabled",0);
                mat.SetFloat("_AlphaPremultiply",0); off=Draw(mat,mesh,rt,readback);
                mat.SetFloat("_AlphaPremultiply",1); on=Draw(mat,mesh,rt,readback);
                if (Difference(off,on)>2e-5) throw new Exception("New factor changed legacy source-off path");
                lines.Add("Production source-off legacy alpha-selector isolation PASS"); cases++;
                return cases;
            }
            finally
            {
                for(int i=0;i<vectors.Length;i++) Shader.SetGlobalVector(vectors[i],savedVectors[i]);
                for(int i=0;i<floats.Length;i++) Shader.SetGlobalFloat(floats[i],savedFloats[i]);
                Shader.SetGlobalTexture("_CharMaxCubemap",savedCube);
                foreach(var obj in owned) Object.DestroyImmediate(obj);
            }
        }

        public static void RunBatch()
        {
            if (!Application.isBatchMode) throw new Exception("Use a separate batch editor");
            string output=Environment.GetEnvironmentVariable("ENDFIELD_CLOTH_PROBE_REPORT");
            if(string.IsNullOrEmpty(output)||File.Exists(output)) throw new Exception("Report path must be fresh");
            var lines=new List<string> {"Synthetic source-algebra probes, not official-image equality.","GPU="+SystemInfo.graphicsDeviceType+" / "+SystemInfo.graphicsDeviceName};
            Material probe=null,production=null; RenderTexture rt=null; Texture2D readback=null;
            GameObject cameraObject=null; Scene previewScene=default; var prior=RenderTexture.active;
            try
            {
                if(SystemInfo.graphicsDeviceType==GraphicsDeviceType.Null) throw new Exception("GPU required");
                rt=new RenderTexture(4,4,0,RenderTextureFormat.ARGBFloat,RenderTextureReadWrite.Linear); rt.Create();
                readback=new Texture2D(4,4,TextureFormat.RGBAFloat,false,true);
                previewScene=EditorSceneManager.NewPreviewScene(); cameraObject=new GameObject("ClothProbePipelineInit");
                SceneManager.MoveGameObjectToScene(cameraObject,previewScene);
                var camera=cameraObject.AddComponent<Camera>(); camera.targetTexture=rt; camera.enabled=false; camera.Render();
                if(RenderPipelineManager.currentPipeline==null) throw new Exception("URP did not initialize");
                lines.Add("Pipeline="+RenderPipelineManager.currentPipeline.GetType().FullName);
                var probeShader=AssetDatabase.LoadAssetAtPath<Shader>("Assets/EndfieldShaderPack/Editor/EndfieldClothEmissionProbe.shader");
                CheckCompiled(probeShader); probe=new Material(probeShader);
                var sample=new Color(.125f,.25f,.5f,.9f); var color=new Color(1.2f,.8f,.4f,1);
                probe.SetVector("_ProbeSample",sample); probe.SetVector("_ProbeColor",color);
                int kernelCases=0; double maxError=0;
                foreach(float alpha in new[] {0f,.25f,1f,1.5f})
                foreach(float selector in new[] {0f,.25f,1f,-.5f})
                foreach(float brightness in new[] {0f,8f})
                {
                    probe.SetVector("_ProbeParams",new Vector4(alpha,selector,brightness,0));
                    Graphics.Blit(Texture2D.blackTexture,rt,probe,0); var actual=Read(rt,readback);
                    double factor=(1.0-selector)+(double)alpha*selector;
                    double error=Math.Max(Error(actual,ExpectedEmission(sample,color,brightness,alpha,selector)),Math.Abs(actual.a-factor));
                    if(error>3e-6) throw new Exception("Kernel mismatch "+Number(error));
                    maxError=Math.Max(maxError,error); kernelCases++;
                }
                CheckCompiled(probeShader);
                var productionShader=Shader.Find("Endfield/CharacterLit"); CheckCompiled(productionShader); production=new Material(productionShader);
                for(int pass=0;pass<production.passCount;pass++) if(!production.SetPass(pass)) throw new Exception("SetPass failed "+pass);
                int productionCases=ProbeProduction(production,rt,readback,lines); CheckCompiled(productionShader);
                lines.Add("Kernel PASS cases="+kernelCases+" maxError="+Number(maxError));
                lines.Add("CharacterLit default-keyword passes="+production.passCount);
                lines.Add("RESULT PASS kernel="+kernelCases+" production="+productionCases+"; no real mip/view/sampler certification");
                using(var stream=new FileStream(output,FileMode.CreateNew,FileAccess.Write))
                using(var writer=new StreamWriter(stream)) foreach(var line in lines) writer.WriteLine(line);
                Debug.Log("Cloth emission probe PASS: "+output);
            }
            finally
            {
                RenderTexture.active=prior;
                if(probe!=null) Object.DestroyImmediate(probe); if(production!=null) Object.DestroyImmediate(production);
                if(cameraObject!=null) Object.DestroyImmediate(cameraObject);
                if(previewScene.IsValid()) EditorSceneManager.ClosePreviewScene(previewScene);
                if(rt!=null) {rt.Release(); Object.DestroyImmediate(rt);} if(readback!=null) Object.DestroyImmediate(readback);
            }
        }
    }
}
