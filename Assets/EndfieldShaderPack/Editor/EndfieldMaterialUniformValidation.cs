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
    // Actual production UPM upload, not inspector values or screenshot fitting.
    public static class EndfieldMaterialUniformValidation
    {
        const string Source="Validation/Captures/material-uniforms-20261001-01";
        const string ManifestHash="943267aebf73d76b1aa0b8755c66bc5ba62af2f76085dba58c23bd6caee7909d";
        const float Tolerance=2e-6f;
        static readonly string[][] Fields={
            new[]{"_BaseColor"},new[]{"_EmissionColor"},new[]{"_ColorAdjustmentColorBlend"},new[]{"_ColorAdjustmentRimColor"},
            new[]{"_BaseMap_ST"},new[]{"_SDFRimColor"},new[]{"_EyeScatteringColor"},new[]{"_EyeHighLightColor"},new[]{"_MatcapColor"},
            new[]{"_AnisotropyColor2"},new[]{"_HighlightMapVector"},new[]{"_LineMap_ST"},
            new[]{"_Smoothness","_Specular","_Metallic","_BumpScale"},
            new[]{"_BackFaceNormalFlip","_AlphaPremultiply","_EmissionBrightness","_SurfaceType"},
            new[]{"_EnableVFXColorAdjustment","_ColorAdjustmentBrightness","_ColorAdjustmentSaturation","_ColorAdjustmentContrast"},
            new[]{"_ColorAdjustmentRimWidth","_ColorAdjustmentRimIntensity","_ShadowColorBrightness","_ShadowColorSaturation"},
            new[]{"_SkinRimOffScale","_FaceRimOffScale","_EmotionIndex","_EmotionBlend"},
            new[]{"_SpecBumpScale","_AnisotropyValue","_AnisotropyValue2","_AnisotropyIntensity"},
            new[]{"_AnisotropyEdgeFade","_AnisotropyRange2","_AnisotropyDirX","_SpecRampIridescentMode"},
            new[]{"_LineAmount","_LineValue","_LineRange","_LineIntensity"},
            new[]{"_LineSaturation","_UseLineMap","_ParallaxScale","_MatcapNormalScale"}
        };
        static void Require(bool ok,string why){if(!ok)throw new InvalidDataException(why);}
        static float DecodeSrgb(float value)=>(float)(value<=.04045f?value/12.92:Math.Pow((value+.055)/1.055,2.4));
        static Color Draw(Material material,Mesh mesh,RenderTexture target,Texture2D readback,int mode)
        {
            Shader.SetGlobalFloat("_EndfieldDebugValueMode",100+mode);
            var cb=new CommandBuffer{name="Actual production material uniform upload"};
            try
            {
                cb.SetRenderTarget(target);cb.ClearRenderTarget(true,true,Color.clear);
                cb.SetViewProjectionMatrices(Matrix4x4.Translate(new Vector3(0,0,-2)),GL.GetGPUProjectionMatrix(Matrix4x4.Ortho(-.5f,.5f,-.5f,.5f,.1f,10),true));
                cb.DrawMesh(mesh,Matrix4x4.identity,material,0,0);Graphics.ExecuteCommandBuffer(cb);
                RenderTexture.active=target;readback.ReadPixels(new Rect(0,0,4,4),0,0);readback.Apply();return readback.GetPixel(2,2);
            }
            finally{cb.Release();}
        }
        public static void RunBatch()
        {
            Require(Application.isBatchMode,"Isolated batch only");
            string report=Environment.GetEnvironmentVariable("ENDFIELD_MATERIAL_UNIFORM_REPORT");
            Require(!string.IsNullOrEmpty(report)&&!File.Exists(report),"Fresh report required");
            Require(SystemInfo.graphicsDeviceType==GraphicsDeviceType.Direct3D11&&QualitySettings.activeColorSpace==ColorSpace.Linear,"Reviewed D3D11/Linear required");
            byte[] manifest=File.ReadAllBytes(Path.Combine(Source,"complete.json"));Require(EndfieldCapturedClothNormals.Hash(manifest)==ManifestHash,"Uniform manifest identity changed");
            var root=(Dictionary<string,object>)MiniJson.Parse(System.Text.Encoding.UTF8.GetString(manifest));
            Require((string)root["status"]=="ok"&&Convert.ToInt32(root["frame"])==6411&&(string)root["schema"]=="endfield-upm-audit-v1","Incomplete uniform export");
            var records=(List<object>)root["records"];Require(records.Count==6,"Six reviewed draws required");
            var lines=new List<string>{"Actual frame6411 production material uniform audit; raw CB bytes, no image fitting.","GPU="+SystemInfo.graphicsDeviceType+" / "+SystemInfo.graphicsDeviceName,"ColorSpace=Linear; tolerance="+Tolerance};
            var owned=new List<Object>();Scene preview=default;var prior=RenderTexture.active;float oldMode=Shader.GetGlobalFloat("_EndfieldDebugValueMode");int failures=0,fields=0,channels=0,excluded=0;
            var hashes=new Dictionary<string,string>();
            try
            {
                preview=EditorSceneManager.NewPreviewScene();var cameraObject=new GameObject("UniformAuditPipelineInit");owned.Add(cameraObject);SceneManager.MoveGameObjectToScene(cameraObject,preview);
                var target=new RenderTexture(4,4,0,RenderTextureFormat.ARGBFloat,RenderTextureReadWrite.Linear);owned.Add(target);target.Create();
                var readback=new Texture2D(4,4,TextureFormat.RGBAFloat,false,true);owned.Add(readback);
                var camera=cameraObject.AddComponent<Camera>();camera.enabled=false;camera.targetTexture=target;camera.Render();Require(RenderPipelineManager.currentPipeline!=null,"URP not initialized");
                var mesh=new Mesh();owned.Add(mesh);mesh.vertices=new[]{new Vector3(-.5f,-.5f,0),new Vector3(.5f,-.5f,0),new Vector3(.5f,.5f,0),new Vector3(-.5f,.5f,0)};
                mesh.normals=Enumerable.Repeat(Vector3.forward,4).ToArray();mesh.tangents=Enumerable.Repeat(new Vector4(1,0,0,1),4).ToArray();mesh.uv=new[]{Vector2.zero,Vector2.right,Vector2.one,Vector2.up};mesh.triangles=new[]{0,1,2,0,2,3};
                foreach(Dictionary<string,object> record in records)
                {
                    int draw=Convert.ToInt32(record["event"]);string path="Assets/Typhoeus/Materials/"+(string)record["material"]+".mat";
                    hashes.Add(path,EndfieldCapturedClothNormals.Hash(File.ReadAllBytes(path)));
                    var asset=AssetDatabase.LoadAssetAtPath<Material>(path);Require(asset!=null&&asset.shader.name=="Endfield/CharacterLit","Missing production material "+path);
                    var mat=new Material(asset);owned.Add(mat);mat.SetFloat("_Cull",0); // diagnostic quad only, never change the asset
                    var raw=File.ReadAllBytes(Path.Combine(Source,(string)record["file"]));Require(raw.Length==Convert.ToInt32(record["bytes"])&&EndfieldCapturedClothNormals.Hash(raw)==(string)record["sha256"],"Raw UPM changed");
                    var uniforms=new Dictionary<string,float[]>();
                    foreach(Dictionary<string,object> item in (List<object>)record["uniforms"])
                    {
                        if(!(bool)item["active"]&&(string)item["name"]!="_BaseMap_ST")continue;
                        Require((bool)item["named"],"Unresolved active anonymous uniform");
                        string name=(string)item["name"];var values=((List<object>)item["value"]).Select(Convert.ToSingle).ToArray();
                        int offset=Convert.ToInt32(item["offset"]);for(int i=0;i<values.Length;i++)Require(BitConverter.ToSingle(raw,offset+4*i)==values[i]&&float.IsFinite(values[i]),"Uniform value not raw byte decode");
                        if(name=="_DisableRainEffectOnMaterial"){Require(values.Length==1&&values[0]==0,"Weather exclusion no longer dry captured case");excluded++;continue;}
                        Require(Fields.Any(row=>row.Contains(name)),"Uncovered active field "+name);Require(!uniforms.ContainsKey(name),"Duplicate semantic label "+name);uniforms.Add(name,values);
                    }
                    for(int mode=0;mode<Fields.Length;mode++)
                    {
                        var names=Fields[mode];if(!names.Any(uniforms.ContainsKey))continue;Color gpu=Draw(mat,mesh,target,readback,mode);
                        for(int channel=0;channel<names.Length;channel++)
                        {
                            if(!uniforms.TryGetValue(names[channel],out var expected))continue;fields++;
                            for(int component=0;component<expected.Length;component++)
                            {
                                int index=names.Length==1?component:channel;float error=Mathf.Abs(gpu[index]-expected[component]);channels++;
                                bool ok=float.IsFinite(gpu[index])&&error<=Tolerance;if(!ok)failures++;
                                lines.Add($"{(ok?"PASS":"FAIL")} draw={draw} field={names[channel]} component={component} GPU={gpu[index]:R} capture={expected[component]:R} error={error:R}");
                            }
                        }
                    }
                    Require(!ShaderUtil.GetShaderMessages(mat.shader).Any(m=>m.severity==UnityEditor.Rendering.ShaderCompilerMessageSeverity.Error),"Shader compile error");
                }
                foreach(var p in hashes)Require(EndfieldCapturedClothNormals.Hash(File.ReadAllBytes(p.Key))==p.Value,"Production material asset changed "+p.Key);
                // Independent known input, not the captured material's inverse
                // conversion: ordinary Color decodes RGB, HDR remains linear,
                // and neither representation changes alpha. No asset edits.
                var probeMaterial=new Material(Shader.Find("Endfield/CharacterLit"));owned.Add(probeMaterial);probeMaterial.SetFloat("_Cull",0);
                var ordinary=new Color(.002f,.25f,.73f,.37f);probeMaterial.SetColor("_AnisotropyColor2",ordinary);
                Color ordinaryGpu=Draw(probeMaterial,mesh,target,readback,9);
                for(int i=0;i<4;i++){float expected=i==3?ordinary.a:DecodeSrgb(ordinary[i]);Require(float.IsFinite(ordinaryGpu[i])&&Mathf.Abs(ordinaryGpu[i]-expected)<=Tolerance,"Ordinary Color RGB/alpha fixture");}
                var hdr=new Color(.002f,.25f,4.3f,.37f);probeMaterial.SetColor("_EyeHighLightColor",hdr);
                Color hdrGpu=Draw(probeMaterial,mesh,target,readback,7);
                for(int i=0;i<4;i++)Require(float.IsFinite(hdrGpu[i])&&Mathf.Abs(hdrGpu[i]-hdr[i])<=Tolerance,"HDR linear RGB/alpha fixture");
                lines.Add("Independent ordinary Color / HDR fixtures PASS: low/high RGB transfer and alpha=.37 unchanged; production UPM readback, eight channels.");
                lines.Add($"RESULT {(failures==0?"PASS":"FAIL")} draws=6 fields={fields} channels={channels} failures={failures}; excluded dry weather fields={excluded}; no scene/settings/material save, no whole-render certificate.");
                using(var stream=new FileStream(report,FileMode.CreateNew,FileAccess.Write))using(var writer=new StreamWriter(stream))foreach(var line in lines)writer.WriteLine(line);
                Require(failures==0,"Material uniform audit failed: "+failures);Debug.Log("Material uniform audit PASS: "+report);
            }
            finally
            {
                Shader.SetGlobalFloat("_EndfieldDebugValueMode",oldMode);RenderTexture.active=prior;
                for(int i=owned.Count-1;i>=0;i--)if(owned[i]!=null){if(owned[i] is RenderTexture rt)rt.Release();Object.DestroyImmediate(owned[i]);}
                if(preview.IsValid())EditorSceneManager.ClosePreviewScene(preview);
            }
        }
    }
}
