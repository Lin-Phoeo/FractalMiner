using System;
using System.Collections.Generic;
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
    // Production call-site probes, not another shader's copied lighting algebra.
    public static class EndfieldCharacterLightingValidation
    {
        const float Tolerance = 2e-6f;
        const string Source = "Validation/Captures/character-light-selection-20261001-01";
        const string ManifestHash = "c3d7df8934814579f009f6d67844eee8541a584d17b123346678212b8b591d74";
        static void Require(bool ok, string why) { if (!ok) throw new InvalidDataException(why); }
        static Vector3 Rgb(Color c) => new Vector3(c.r,c.g,c.b);
        static Color Draw(Material material, Mesh mesh, RenderTexture target, Texture2D readback, int mode)
        {
            Shader.SetGlobalFloat("_EndfieldDebugValueMode",mode);
            var cb = new CommandBuffer { name = "Source light selection production probe" };
            try
            {
                cb.SetRenderTarget(target); cb.ClearRenderTarget(true,true,Color.clear);
                cb.SetViewProjectionMatrices(Matrix4x4.Translate(new Vector3(0,0,-2)),GL.GetGPUProjectionMatrix(Matrix4x4.Ortho(-.5f,.5f,-.5f,.5f,.1f,10),true));
                cb.DrawMesh(mesh,Matrix4x4.identity,material,0,0); Graphics.ExecuteCommandBuffer(cb);
                RenderTexture.active=target; readback.ReadPixels(new Rect(0,0,4,4),0,0); readback.Apply(); return readback.GetPixel(2,2);
            }
            finally { cb.Release(); }
        }
        static Texture2D Constant(Color value)
        {
            var t = new Texture2D(2,2,TextureFormat.RGBAFloat,false,true);
            t.SetPixels(new[]{value,value,value,value}); t.Apply(); return t;
        }
        public static void RunBatch()
        {
            Require(Application.isBatchMode,"Isolated batch only");
            string output=Environment.GetEnvironmentVariable("ENDFIELD_CHARACTER_LIGHTING_REPORT");
            Require(!string.IsNullOrEmpty(output)&&!File.Exists(output),"Fresh report required");
            Require(SystemInfo.graphicsDeviceType==GraphicsDeviceType.Direct3D11&&QualitySettings.activeColorSpace==ColorSpace.Linear,"Reviewed D3D11 / Linear required");
            var lines=new List<string>{"Source character light selection; no image fitting. tolerance="+Tolerance};
            var owned=new List<Object>(); Scene preview=default; var prior=RenderTexture.active;
            string[] vectors=Enumerable.Range(0,16).Select(i=>"_CharacterParams"+i).Concat(new[]{"_EndfieldCapturedDirectionalTravel","_EndfieldCapturedDirectionalColor","_EnvironmentGlobalParams0","_ExposureWithMiscParams","_CharacterLightDir","_CharacterLightColor","_WorldSpaceCameraPos"}).ToArray();
            string[] floats={"_EndfieldDebugValueMode","_EndfieldLabelMode","_EndfieldOfficialFrameEnabled","_EndfieldOfficialShadingEnabled","_EndfieldCapturedLightIntensity","_EndfieldCapturedCubemapAvailable","_EndfieldCapturedGlobalMipBias","_EndfieldCharacterSelfShadow"};
            var savedV=vectors.Select(Shader.GetGlobalVector).ToArray(); var savedF=floats.Select(Shader.GetGlobalFloat).ToArray();
            int failures=0,cases=0;
            try
            {
                preview=EditorSceneManager.NewPreviewScene(); var go=new GameObject("LightSelectionPipelineInit"); owned.Add(go); SceneManager.MoveGameObjectToScene(go,preview);
                var target=new RenderTexture(4,4,0,RenderTextureFormat.ARGBFloat,RenderTextureReadWrite.Linear); owned.Add(target); target.Create();
                var readback=new Texture2D(4,4,TextureFormat.RGBAFloat,false,true); owned.Add(readback);
                var camera=go.AddComponent<Camera>(); camera.enabled=false; camera.targetTexture=target; camera.Render(); Require(RenderPipelineManager.currentPipeline!=null,"URP not initialized");
                var mesh=new Mesh(); owned.Add(mesh);
                mesh.vertices=new[]{new Vector3(-.5f,-.5f,0),new Vector3(.5f,-.5f,0),new Vector3(.5f,.5f,0),new Vector3(-.5f,.5f,0)};
                mesh.normals=Enumerable.Repeat(Vector3.forward,4).ToArray(); mesh.tangents=Enumerable.Repeat(new Vector4(1,0,0,1),4).ToArray(); mesh.uv=Enumerable.Repeat(new Vector2(.5f,.5f),4).ToArray(); mesh.triangles=new[]{0,1,2,0,2,3};
                var mat=new Material(Shader.Find("Endfield/CharacterLit")); owned.Add(mat); mat.SetFloat("_Cull",0); mat.SetFloat("_BackFaceNormalFlip",1);
                mat.SetFloat("_UseBumpMap",0); mat.SetFloat("_UseSpecBumpMap",0); mat.SetFloat("_UseParallax",0); mat.SetFloat("_UseSDFLightmap",0);
                var baseMap=Constant(new Color(.2f,.3f,.4f,1)); var packed=Constant(new Color(0,0,1,.5f)); var white=Constant(Color.white); var black=Constant(Color.clear);
                owned.AddRange(new Object[]{baseMap,packed,white,black});
                mat.SetTexture("_BaseMap",baseMap); mat.SetTexture("_MetallicGlossMap",packed); mat.SetTexture("_DiffRampMap",white); mat.SetTexture("_ShadowLutTex",baseMap); mat.SetTexture("_MatcapTex",black);
                mat.SetFloat("_UseMetallicGlossMap",1); mat.SetFloat("_UseDiffRampMap",1); mat.SetFloat("_Metallic",0); mat.SetFloat("_Specular",0); mat.SetColor("_MatcapColor",Color.clear);
                mat.SetColor("_BaseColor",Color.white); mat.SetColor("_EyeHighLightColor",Color.white); mat.SetColor("_EyeScatteringColor",Color.white);
                Endfield.EndfieldOfficialFrameGlobals.ApplyGlobals();
                Shader.SetGlobalFloat("_EndfieldLabelMode",0); Shader.SetGlobalVector("_CharacterLightDir",new Vector4(0,0,1,1)); Shader.SetGlobalVector("_CharacterLightColor",new Vector4(3,2,4,1));
                byte[] manifest=File.ReadAllBytes(Path.Combine(Source,"complete.json")); Require(EndfieldCapturedClothNormals.Hash(manifest)==ManifestHash,"Captured light manifest changed");
                var root=(Dictionary<string,object>)MiniJson.Parse(System.Text.Encoding.UTF8.GetString(manifest));
                Require((string)root["status"]=="ok"&&Convert.ToInt32(root["frame"])==6411&&(string)root["schema"]=="endfield-character-light-selection-v1","Incomplete captured light manifest");
                var records=(List<object>)root["records"]; Require(records.Count==6,"Six actual light records required");
                int capturedChannels=0;
                foreach(Dictionary<string,object> record in records)
                {
                    int draw=Convert.ToInt32(record["event"]); mat.SetFloat("_MaterialFamily",draw==786||draw==860?1:draw==776?3:draw==875?2:0);
                    foreach(Dictionary<string,object> block in (List<object>)record["blocks"])
                    {
                        byte[] raw=File.ReadAllBytes(Path.Combine(Source,(string)block["file"])); Require(raw.Length==Convert.ToInt32(block["bytes"])&&EndfieldCapturedClothNormals.Hash(raw)==(string)block["sha256"],"Raw captured global bytes changed");
                        foreach(Dictionary<string,object> field in (List<object>)block["uniforms"])
                        {
                            string name=(string)field["name"]; Require((bool)field["active"]&&(bool)field["named"],"Unused/unapproved light input");
                            var expected=((List<object>)field["value"]).Select(Convert.ToSingle).ToArray(); Require(expected.Length==4,"Reviewed float4 required");
                            int offset=Convert.ToInt32(field["offset"]); for(int i=0;i<4;i++)Require(BitConverter.ToSingle(raw,offset+i*4)==expected[i]&&float.IsFinite(expected[i]),"Raw light decode differs");
                            int mode=name=="_LightDataBuffer_DirectionalLightDirection"?203:name=="_LightDataBuffer_DirectionalLightCustomData1"?204:name=="_CharacterParams1"?205:name=="_CharacterParams4"||name=="_CharacterParams5"?206:name=="_CharacterParams11"?207:name=="_CharacterParams12"?208:-1;
                            Require(mode!=-1,"Uncovered captured input "+name); Color gpu=Draw(mat,mesh,target,readback,mode); cases++;
                            for(int i=0;i<4;i++){capturedChannels++;float error=Mathf.Abs(gpu[i]-expected[i]);bool ok=float.IsFinite(error)&&error<=Tolerance;if(!ok){failures++;lines.Add($"FAIL draw={draw} input={name}[{i}] gpu={gpu[i]:R} capture={expected[i]:R} error={error:R}");}}
                        }
                    }
                }
                lines.Add($"Actual captured input upload: six PS / 36 float4 / {capturedChannels} channels; direct descriptor bytes and production GPU readback.");
                var incoming=new Vector3(-.2f,.5f,.3f); var character=new Vector3(.8f,-.4f,.1f); var incomingRgb=new Vector3(.25f,.7f,1.2f);
                var skinRgb=new Vector3(.9f,.25f,.4f); var otherRgb=new Vector3(.1f,1.1f,.6f);
                Shader.SetGlobalVector("_EndfieldCapturedDirectionalTravel",-incoming); Shader.SetGlobalVector("_EndfieldCapturedDirectionalColor",incomingRgb);
                Shader.SetGlobalVector("_CharacterParams4",skinRgb); Shader.SetGlobalVector("_CharacterParams5",otherRgb); Shader.SetGlobalVector("_CharacterParams11",character);
                int selectionStart=cases;
                foreach(int family in new[]{0,1,2,3})
                foreach(float directionWeight in new[]{0f,.35f,1f})
                foreach(float colorWeight in new[]{0f,.4f,1f})
                foreach(float show in new[]{0f,.25f,1f})
                foreach(float intensity in new[]{0f,1.6243867874f})
                {
                    mat.SetFloat("_MaterialFamily",family); Shader.SetGlobalVector("_CharacterParams1",new Vector4(0,1,0,directionWeight)); Shader.SetGlobalVector("_CharacterParams12",new Vector4(1,colorWeight,1,show)); Shader.SetGlobalFloat("_EndfieldCapturedLightIntensity",intensity);
                    // Independent CPU straight-line equations from actual PS expressions.
                    Vector3 direction=incoming*(1-directionWeight)+character*directionWeight;
                    Vector3 rgb=incomingRgb*(1-colorWeight)+(family==1?skinRgb:otherRgb)*colorWeight;
                    Vector3 scaled=rgb*(intensity*(1-show)+show);
                    foreach(int mode in new[]{200,201,202})
                    {
                        Color p=Draw(mat,mesh,target,readback,mode); Vector3 expected=mode==200?direction:mode==201?rgb:scaled;
                        float error=new[]{Mathf.Abs(p.r-expected.x),Mathf.Abs(p.g-expected.y),Mathf.Abs(p.b-expected.z)}.Max(); bool ok=float.IsFinite(error)&&error<=Tolerance&&p.a>.99f; cases++; if(!ok)failures++;
                        if(!ok)lines.Add($"FAIL family={family} dw={directionWeight} cw={colorWeight} show={show} intensity={intensity} mode={mode} GPU={Rgb(p).ToString("F7")} expected={expected.ToString("F7")} error={error:R}");
                    }
                }
                lines.Add($"Selection probes: cases={cases-selectionStart} failures={failures}; endpoint/partial weights, non-unit directions, CP4 body (no SDF) vs CP5, zero intensity, show-mode interpolation.");
                // Full production family consumption must remain continuous at I=0:
                // the unscaled RGB still tints ambient even with no direct light.
                Shader.SetGlobalVector("_CharacterParams11",new Vector4(0,0,1,0)); Shader.SetGlobalVector("_CharacterParams1",new Vector4(0,1,0,1)); Shader.SetGlobalVector("_CharacterParams12",new Vector4(1,1,1,0)); Shader.SetGlobalVector("_CharacterParams13",Vector4.zero); Shader.SetGlobalFloat("_EndfieldCapturedCubemapAvailable",0); Shader.SetGlobalVector("_CharacterParams6",Vector4.zero);
                foreach(int family in new[]{0,1,2,3})
                {
                    mat.SetFloat("_MaterialFamily",family); Shader.SetGlobalFloat("_EndfieldCapturedLightIntensity",0); Color zero=Draw(mat,mesh,target,readback,0);
                    Shader.SetGlobalFloat("_EndfieldCapturedLightIntensity",.0001f); Color near=Draw(mat,mesh,target,readback,0);
                    float error=(Rgb(zero)-Rgb(near)).magnitude; bool ok=float.IsFinite(error)&&error<.0002f&&Rgb(zero).magnitude>.001f; cases++; if(!ok)failures++;
                    lines.Add($"{(ok?"PASS":"FAIL")} full-family zero-intensity continuity family={family} zero={Rgb(zero).ToString("F7")} near={Rgb(near).ToString("F7")} delta={error:R}");
                }
                Require(!ShaderUtil.GetShaderMessages(mat.shader).Any(m=>m.severity==UnityEditor.Rendering.ShaderCompilerMessageSeverity.Error),"Shader compile error");
                lines.Add($"RESULT {(failures==0?"PASS":"FAIL")} cases={cases} failures={failures}; globals restored; no material/scene/settings save; bounded dry light selection only.");
                using(var stream=new FileStream(output,FileMode.CreateNew,FileAccess.Write))using(var writer=new StreamWriter(stream))foreach(string line in lines)writer.WriteLine(line);
                Require(failures==0,"Character light selection failed: "+failures); Debug.Log("Character light selection PASS: "+output);
            }
            finally
            {
                for(int i=0;i<vectors.Length;i++)Shader.SetGlobalVector(vectors[i],savedV[i]); for(int i=0;i<floats.Length;i++)Shader.SetGlobalFloat(floats[i],savedF[i]); RenderTexture.active=prior;
                for(int i=owned.Count-1;i>=0;i--)if(owned[i]!=null){if(owned[i] is RenderTexture rt)rt.Release();Object.DestroyImmediate(owned[i]);}
                if(preview.IsValid())EditorSceneManager.ClosePreviewScene(preview);
            }
        }
    }
}
