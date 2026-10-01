using System;
using System.Collections.Generic;
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
    public static class EndfieldShadowSelectionValidation
    {
        const float Tolerance=2e-6f;
        const string Source="Validation/Captures/shadow-selection-20261001-01";
        const string ManifestHash="b74ed7d0c64485ad4f72979020d2566b547a73a977da3ae46396ae55e767f819";
        static void Require(bool ok,string why){if(!ok)throw new InvalidDataException(why);}
        static Color Draw(Material mat,Mesh mesh,RenderTexture target,Texture2D readback,int mode,int x,int y)
        {
            Shader.SetGlobalFloat("_EndfieldDebugValueMode",mode);
            var cb=new CommandBuffer{name="Production shadow selection probe"};
            try
            {
                cb.SetRenderTarget(target);cb.ClearRenderTarget(true,true,Color.clear);
                cb.SetViewProjectionMatrices(Matrix4x4.Translate(new Vector3(0,0,-2)),GL.GetGPUProjectionMatrix(Matrix4x4.Ortho(-.5f,.5f,-.5f,.5f,.1f,10),true));
                cb.DrawMesh(mesh,Matrix4x4.identity,mat,0,0);Graphics.ExecuteCommandBuffer(cb);RenderTexture.active=target;readback.ReadPixels(new Rect(0,0,4,4),0,0);readback.Apply();return readback.GetPixel(x,y);
            }
            finally{cb.Release();}
        }
        static Color DrawNativeAt(Material mat,Mesh mesh,RenderTexture target,Texture2D readback,int mode,int x,int y)
        {
            Shader.SetGlobalFloat("_EndfieldDebugValueMode",mode);var cb=new CommandBuffer{name="Actual screen mask production integer Load"};
            try
            {
                cb.SetRenderTarget(target);cb.ClearRenderTarget(true,true,Color.clear);cb.SetViewProjectionMatrices(Matrix4x4.Translate(new Vector3(0,0,-2)),GL.GetGPUProjectionMatrix(Matrix4x4.Ortho(-.5f,.5f,-.5f,.5f,.1f,10),true));
                cb.DrawMesh(mesh,Matrix4x4.identity,mat,0,0);Graphics.ExecuteCommandBuffer(cb);RenderTexture.active=target;readback.ReadPixels(new Rect(x,y,1,1),0,0);readback.Apply();return readback.GetPixel(0,0);
            }
            finally{cb.Release();}
        }
        public static void RunBatch()
        {
            Require(Application.isBatchMode,"Isolated batch required");string output=Environment.GetEnvironmentVariable("ENDFIELD_SHADOW_SELECTION_REPORT");Require(!string.IsNullOrEmpty(output)&&!File.Exists(output),"Fresh report required");
            Require(SystemInfo.graphicsDeviceType==GraphicsDeviceType.Direct3D11&&QualitySettings.activeColorSpace==ColorSpace.Linear,"D3D11/Linear required");
            var lines=new List<string>{"Official shadow consumer contract; synthetic known inputs, no image fitting. tolerance="+Tolerance};int cases=0,failures=0;var owned=new List<Object>();Scene preview=default;var prior=RenderTexture.active;
            string[] vectors=Enumerable.Range(0,16).Select(i=>"_CharacterParams"+i).Concat(new[]{"_EndfieldCapturedDirectionalShadowParams","_EnvironmentGlobalParams0","_ExposureWithMiscParams","_CharacterLightDir","_CharacterLightColor","_EndfieldCapturedDirectionalTravel","_EndfieldCapturedDirectionalColor","_EndfieldCharacterShadowScreenSize","_WorldSpaceCameraPos"}).ToArray();
            string[] floats={"_EndfieldOfficialFrameEnabled","_EndfieldOfficialShadingEnabled","_EndfieldCapturedLightIntensity","_EndfieldCapturedGlobalMipBias","_EndfieldCapturedCubemapAvailable","_EndfieldLabelMode","_EndfieldDebugValueMode","_EndfieldCharacterSelfShadow","_EndfieldDirectionalScreenShadow"};string[] textures={"_EndfieldCharacterShadowScreen","_EndfieldDirectionalShadowScreen"};
            var savedV=vectors.Select(Shader.GetGlobalVector).ToArray();var savedF=floats.Select(Shader.GetGlobalFloat).ToArray();var savedT=textures.Select(Shader.GetGlobalTexture).ToArray();
            try
            {
                preview=EditorSceneManager.NewPreviewScene();var go=new GameObject("ShadowSelectionPipelineInit");owned.Add(go);SceneManager.MoveGameObjectToScene(go,preview);
                var target=new RenderTexture(4,4,0,RenderTextureFormat.ARGBFloat,RenderTextureReadWrite.Linear);owned.Add(target);target.Create();var readback=new Texture2D(4,4,TextureFormat.RGBAFloat,false,true);owned.Add(readback);var camera=go.AddComponent<Camera>();camera.enabled=false;camera.targetTexture=target;camera.Render();Require(RenderPipelineManager.currentPipeline!=null,"URP not initialized");
                var mesh=new Mesh();owned.Add(mesh);mesh.vertices=new[]{new Vector3(-.5f,-.5f,0),new Vector3(.5f,-.5f,0),new Vector3(.5f,.5f,0),new Vector3(-.5f,.5f,0)};mesh.normals=Enumerable.Repeat(Vector3.forward,4).ToArray();mesh.tangents=Enumerable.Repeat(new Vector4(1,0,0,1),4).ToArray();mesh.uv=Enumerable.Repeat(new Vector2(.5f,.5f),4).ToArray();mesh.triangles=new[]{0,1,2,0,2,3};
                var mat=new Material(Shader.Find("Endfield/CharacterLit"));owned.Add(mat);mat.SetFloat("_Cull",0);mat.SetFloat("_UseParallax",0);mat.SetFloat("_UseBumpMap",0);mat.SetFloat("_UseSpecBumpMap",0);
                // Distinct maps expose accidental R/G/source aliasing. R8G8_UNorm
                // fixture values are uploaded as bytes; no image export/import flip.
                var r=new Texture2D(4,4,UnityEngine.Experimental.Rendering.GraphicsFormat.R8G8_UNorm,UnityEngine.Experimental.Rendering.TextureCreationFlags.None);var g=new Texture2D(4,4,UnityEngine.Experimental.Rendering.GraphicsFormat.R8G8_UNorm,UnityEngine.Experimental.Rendering.TextureCreationFlags.None);owned.Add(r);owned.Add(g);
                var rBytes=new byte[32];var gBytes=new byte[32];for(int i=0;i<16;i++){rBytes[i*2]=(byte)(13+i*11);rBytes[i*2+1]=239;gBytes[i*2]=251;gBytes[i*2+1]=(byte)(207-i*9);}r.LoadRawTextureData(rBytes);g.LoadRawTextureData(gBytes);r.Apply();g.Apply();r.filterMode=g.filterMode=FilterMode.Bilinear;r.wrapMode=g.wrapMode=TextureWrapMode.Repeat;
                Endfield.EndfieldOfficialFrameGlobals.ApplyGlobals();Shader.SetGlobalFloat("_EndfieldLabelMode",0);Shader.SetGlobalVector("_CharacterLightDir",new Vector4(0,0,1,1));Shader.SetGlobalVector("_CharacterLightColor",Vector4.one);
                Shader.SetGlobalTexture(textures[0],g);Shader.SetGlobalTexture(textures[1],r);
                byte[] manifest=File.ReadAllBytes(Path.Combine(Source,"complete.json"));Require(EndfieldCapturedClothNormals.Hash(manifest)==ManifestHash,"Captured shadow manifest changed");
                var root=(Dictionary<string,object>)MiniJson.Parse(System.Text.Encoding.UTF8.GetString(manifest));Require((string)root["status"]=="ok"&&Convert.ToInt32(root["frame"])==6411&&(string)root["schema"]=="endfield-shadow-selection-v1","Incomplete shadow export");var records=(List<object>)root["records"];Require(records.Count==6,"Six actual PS records required");int capturedChannels=0;
                foreach(Dictionary<string,object> record in records)
                {
                    foreach(Dictionary<string,object> block in (List<object>)record["blocks"])
                    {
                        byte[] raw=File.ReadAllBytes(Path.Combine(Source,(string)block["file"]));Require(raw.Length==Convert.ToInt32(block["bytes"])&&EndfieldCapturedClothNormals.Hash(raw)==(string)block["sha256"],"Raw shadow CB changed");
                        foreach(Dictionary<string,object> field in (List<object>)block["uniforms"])
                        {
                            string name=(string)field["name"];Require((bool)field["active"]&&(bool)field["named"],"Unapproved shadow field");var expected=((List<object>)field["value"]).Select(Convert.ToSingle).ToArray();Require(expected.Length==4,"Float4 required");int offset=Convert.ToInt32(field["offset"]);for(int i=0;i<4;i++)Require(BitConverter.ToSingle(raw,offset+i*4)==expected[i],"Raw shadow decode changed");
                            int mode=name=="_DirectionalShadowParams"?212:name=="_CharacterParams1"?205:-1;Require(mode!=-1,"Uncovered shadow field");Color gpu=Draw(mat,mesh,target,readback,mode,2,2);cases++;
                            for(int i=0;i<4;i++){capturedChannels++;if(!float.IsFinite(gpu[i])||Mathf.Abs(gpu[i]-expected[i])>Tolerance){failures++;lines.Add($"FAIL captured {name}[{i}] gpu={gpu[i]:R} expected={expected[i]:R}");}}
                        }
                    }
                }
                lines.Add("Captured parameter upload: six draws / 12 float4 / "+capturedChannels+" components from raw descriptors to production GPU.");int selectionStart=cases;
                foreach(int family in new[]{0,1,2,3})foreach(float strength in new[]{0f,.35f,1f})foreach(float ignore in new[]{0f,.4f,1f})foreach(int enabled in new[]{0,1})foreach(int point in new[]{0,6,15})
                {
                    mat.SetFloat("_MaterialFamily",family);Shader.SetGlobalVector("_CharacterParams1",new Vector4(0,1,ignore,1));Shader.SetGlobalVector("_EndfieldCapturedDirectionalShadowParams",new Vector4(strength,2,0,3600));Shader.SetGlobalFloat("_EndfieldDirectionalScreenShadow",enabled);Shader.SetGlobalFloat("_EndfieldCharacterSelfShadow",enabled);
                    // Poison the legacy normalized-size input. Official Load uses
                    // integer SV_POSITION and cannot depend on this value/filter.
                    Shader.SetGlobalVector("_EndfieldCharacterShadowScreenSize",new Vector4(999,999,1f/999,1f/999));
                    int x=point%4,y=point/4;float rawR=enabled==1?rBytes[point*2]/255f:1;float rawG=enabled==1?gBytes[point*2+1]/255f:1;
                    float expectedR=(1-strength+rawR*strength)*(1-ignore)+ignore;
                    Color p=Draw(mat,mesh,target,readback,210,x,y);Color q=Draw(mat,mesh,target,readback,211,x,y);
                    float error=Mathf.Max(Mathf.Abs(p.r-expectedR),Mathf.Abs(q.r-rawG));bool ok=float.IsFinite(error)&&error<=Tolerance&&p.a>.99f&&q.a>.99f;cases++;if(!ok){failures++;lines.Add($"FAIL family={family} strength={strength} ignore={ignore} gate={enabled} point={point} GPU=({p.r:R},{q.r:R}) expected=({expectedR:R},{rawG:R}) error={error:R}");}
                }
                lines.Add($"Synthetic selection: cases={cases-selectionStart} failures={failures}; distinct native R8G8 maps, integer pixel Load, no size/filter dependency, CP1.z once, strength before ignore; default fallback explicitly legacy.");
                // Every independent ownership gate combination must work; the
                // current live G producer's R=1 is never enabled as official R.
                mat.SetFloat("_MaterialFamily",2);Shader.SetGlobalVector("_CharacterParams1",new Vector4(0,1,0,1));Shader.SetGlobalVector("_EndfieldCapturedDirectionalShadowParams",Vector4.one);
                foreach(int rg in new[]{0,1})foreach(int gg in new[]{0,1})
                {
                    Shader.SetGlobalFloat("_EndfieldDirectionalScreenShadow",rg);Shader.SetGlobalFloat("_EndfieldCharacterSelfShadow",gg);
                    Color rp=Draw(mat,mesh,target,readback,210,2,1),gp=Draw(mat,mesh,target,readback,211,2,1);float expectedR=rg==1?rBytes[12]/255f:1,expectedG=gg==1?gBytes[13]/255f:1;bool ok=Mathf.Abs(rp.r-expectedR)<=Tolerance&&Mathf.Abs(gp.r-expectedG)<=Tolerance;cases++;if(!ok)failures++;lines.Add($"{(ok?"PASS":"FAIL")} independent ownership R={rg} G={gg}");
                }
                var mask=(Dictionary<string,object>)((Dictionary<string,object>)records[0])["screen_mask"];Require((string)mask["format"]=="R8G8_UNORM"&&Convert.ToInt32(mask["mips"])==1,"Native mask format changed");int width=Convert.ToInt32(mask["width"]),height=Convert.ToInt32(mask["height"]);byte[] payload=File.ReadAllBytes(Path.Combine(Source,(string)mask["file"]));Require(payload.Length==width*height*2&&EndfieldCapturedClothNormals.Hash(payload)==(string)mask["sha256"],"Native mask payload changed");
                var nativeMask=new Texture2D(width,height,UnityEngine.Experimental.Rendering.GraphicsFormat.R8G8_UNorm,UnityEngine.Experimental.Rendering.TextureCreationFlags.None);owned.Add(nativeMask);nativeMask.LoadRawTextureData(payload);nativeMask.Apply();
                var nativeTarget=new RenderTexture(width,height,0,RenderTextureFormat.ARGBFloat,RenderTextureReadWrite.Linear);owned.Add(nativeTarget);nativeTarget.Create();Shader.SetGlobalTexture(textures[0],nativeMask);Shader.SetGlobalTexture(textures[1],nativeMask);Shader.SetGlobalFloat("_EndfieldDirectionalScreenShadow",1);Shader.SetGlobalFloat("_EndfieldCharacterSelfShadow",1);
                var points=new List<int>{0,width-1,(height-1)*width,width*height-1,(height/2)*width+width/2};int firstR=-1,firstG=-1;for(int i=0;i<width*height;i++){if(firstR<0&&payload[i*2]<255)firstR=i;if(firstG<0&&payload[i*2+1]>0&&payload[i*2+1]<250)firstG=i;if(firstR>=0&&firstG>=0)break;}Require(firstG>=0,"Native mask has no fractional G sample");
                if(firstR>=0)points.Add(firstR);else lines.Add("Actual frame R is uniformly 255 (fully lit); nonuniform R/strength is tested by independent synthetic inputs, not invented captured shadows.");points.Add(firstG);
                foreach(int point in points)
                {
                    int x=point%width,y=point/width;Color rp=DrawNativeAt(mat,mesh,nativeTarget,readback,210,x,y),gp=DrawNativeAt(mat,mesh,nativeTarget,readback,211,x,y);float error=Mathf.Max(Mathf.Abs(rp.r-payload[point*2]/255f),Mathf.Abs(gp.r-payload[point*2+1]/255f));bool ok=float.IsFinite(error)&&error<=Tolerance;cases++;if(!ok)failures++;lines.Add($"{(ok?"PASS":"FAIL")} actual native mask integer pixel=({x},{y}) R={rp.r:R} G={gp.r:R} error={error:R}");
                }
                Require(!ShaderUtil.GetShaderMessages(mat.shader).Any(m=>m.severity==UnityEditor.Rendering.ShaderCompilerMessageSeverity.Error),"Shader compile error");lines.Add($"RESULT {(failures==0?"PASS":"FAIL")} cases={cases} failures={failures}; no full directional producer certificate; no scene/settings/material save.");
                using(var stream=new FileStream(output,FileMode.CreateNew,FileAccess.Write))using(var writer=new StreamWriter(stream))foreach(string line in lines)writer.WriteLine(line);Require(failures==0,"Shadow selection failed: "+failures);Debug.Log("Shadow selection PASS: "+output);
            }
            finally
            {
                for(int i=0;i<vectors.Length;i++)Shader.SetGlobalVector(vectors[i],savedV[i]);for(int i=0;i<floats.Length;i++)Shader.SetGlobalFloat(floats[i],savedF[i]);for(int i=0;i<textures.Length;i++)Shader.SetGlobalTexture(textures[i],savedT[i]);RenderTexture.active=prior;
                for(int i=owned.Count-1;i>=0;i--)if(owned[i]!=null){if(owned[i] is RenderTexture rt)rt.Release();Object.DestroyImmediate(owned[i]);}if(preview.IsValid())EditorSceneManager.ClosePreviewScene(preview);
            }
        }
    }
}
