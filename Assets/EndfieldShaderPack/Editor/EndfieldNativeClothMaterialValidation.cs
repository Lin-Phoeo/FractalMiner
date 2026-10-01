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
    // Native input/view/sampler and real production consumption, not screenshots.
    public static class EndfieldNativeClothMaterialValidation
    {
        static void Require(bool yes, string why) { if (!yes) throw new Exception(why); }
        static double Difference(Color a, Color b) => new[] { Math.Abs(a.r-b.r), Math.Abs(a.g-b.g), Math.Abs(a.b-b.b), Math.Abs(a.a-b.a) }.Max();
        static string Number(double value) => value.ToString("R", CultureInfo.InvariantCulture);
        static void Reject(Action action, string why)
        { try { action(); } catch (InvalidDataException) { return; } throw new Exception("Accepted " + why); }
        static Color Read(RenderTexture target, Texture2D readback)
        {
            RenderTexture.active=target; readback.ReadPixels(new Rect(0,0,4,4),0,0); readback.Apply();
            var value=readback.GetPixel(2,2);
            Require(float.IsFinite(value.r)&&float.IsFinite(value.g)&&float.IsFinite(value.b)&&float.IsFinite(value.a),"Nonfinite output"); return value;
        }
        static Color Sample(Material probe, Texture texture, Vector2 uv, float mip, RenderTexture target, Texture2D readback, bool load=false)
        {
            probe.SetTexture("_BumpMap",texture); probe.SetVector("_ProbeUVLOD",new Vector4(uv.x,uv.y,mip,load?1:0));
            Graphics.Blit(Texture2D.blackTexture,target,probe,0); return Read(target,readback);
        }
        static Color Draw(Material material, Mesh mesh, MaterialPropertyBlock block, RenderTexture target, Texture2D readback)
        {
            var command=new CommandBuffer{name="Native cloth material production consumer"};
            try
            {
                command.SetRenderTarget(target); command.ClearRenderTarget(true,true,Color.clear);
                command.SetViewProjectionMatrices(Matrix4x4.Translate(new Vector3(0,0,-2)),GL.GetGPUProjectionMatrix(Matrix4x4.Ortho(-.5f,.5f,-.5f,.5f,.1f,10),true));
                command.DrawMesh(mesh,Matrix4x4.identity,material,0,0,block); Graphics.ExecuteCommandBuffer(command); return Read(target,readback);
            }
            finally {command.Release();}
        }
        static Texture2D Constant(Color value, List<Object> owned)
        {
            var texture=new Texture2D(1,1,TextureFormat.RGBAFloat,false,true){filterMode=FilterMode.Bilinear,wrapMode=TextureWrapMode.Repeat};
            texture.SetPixel(0,0,value); texture.Apply(false,false); owned.Add(texture); return texture;
        }
        public static void RunBatch()
        {
            Require(Application.isBatchMode,"Isolated batch Editor required");
            string output=Environment.GetEnvironmentVariable("ENDFIELD_CLOTH_MATERIAL_REPORT");
            Require(!string.IsNullOrEmpty(output)&&!File.Exists(output),"Fresh report required");
            var lines=new List<string>{"Native captured material inputs; no official-image/per-pixel fitting.","GPU="+SystemInfo.graphicsDeviceType+" / "+SystemInfo.graphicsDeviceName};
            var owned=new List<Object>(); var prior=RenderTexture.active; Scene preview=default;
            string[] vectors=Enumerable.Range(0,16).Select(i=>"_CharacterParams"+i).Concat(new[]{"_EnvironmentGlobalParams0","_ExposureWithMiscParams","_CharacterLightDir","_CharacterLightColor","_WorldSpaceCameraPos"}).ToArray();
            string[] floats={"_EndfieldOfficialFrameEnabled","_EndfieldOfficialShadingEnabled","_EndfieldCapturedLightIntensity","_EndfieldCapturedCubemapAvailable","_EndfieldCapturedGlobalMipBias","_EndfieldLabelMode","_EndfieldDebugValueMode","_EndfieldCharacterSelfShadow"};
            var savedVectors=vectors.Select(Shader.GetGlobalVector).ToArray(); var savedFloats=floats.Select(Shader.GetGlobalFloat).ToArray();
            var savedCube=Shader.GetGlobalTexture("_CharMaxCubemap");
            try
            {
                Require(SystemInfo.graphicsDeviceType==GraphicsDeviceType.Direct3D11,"Only D3D11 certified here");
                preview=EditorSceneManager.NewPreviewScene(); var cameraObject=new GameObject("ClothMaterialPipelineInit"); owned.Add(cameraObject); SceneManager.MoveGameObjectToScene(cameraObject,preview);
                var target=new RenderTexture(4,4,0,RenderTextureFormat.ARGBFloat,RenderTextureReadWrite.Linear); owned.Add(target); target.Create();
                var readback=new Texture2D(4,4,TextureFormat.RGBAFloat,false,true); owned.Add(readback);
                var camera=cameraObject.AddComponent<Camera>(); camera.targetTexture=target; camera.enabled=false; camera.Render(); Require(RenderPipelineManager.currentPipeline!=null,"URP did not initialize");
                var probeShader=Shader.Find("Hidden/Endfield/NativeClothProbe"); Require(probeShader!=null&&probeShader.isSupported,"Missing raw sampling probe");
                var probe=new Material(probeShader); owned.Add(probe);
                using (var bundle=EndfieldCapturedClothMaterialInputs.Load())
                {
                    int samples=0, mips=0; double maxError=0;
                    for(int i=0;i<7;i++)
                    {
                        var spec=EndfieldCapturedClothMaterials.Specs[i]; var texture=bundle.Textures[i];
                        var bytes=texture.GetRawTextureData<byte>().ToArray(); Require(EndfieldCapturedClothNormals.Hash(bytes)==spec.Hash,"Uploaded bytes changed");
                        int offset=0;
                        for(int mip=0;mip<spec.Mips;mip++)
                        {
                            int size=EndfieldCapturedClothMaterials.LevelBytes(spec,mip);
                            Require(texture.GetPixelData<byte>(mip).SequenceEqual(bytes.Skip(offset).Take(size)),"Native mip partition changed"); offset+=size; mips++;
                        }
                        Require(offset==spec.Bytes,"Native payload length mismatch");
                        foreach(var captured in bundle.NativeSamples(i))
                        {
                            int w=Math.Max(1,spec.Width>>captured.Mip),h=Math.Max(1,spec.Height>>captured.Mip);
                            var uv=new Vector2((captured.X+.5f)/w,(captured.Y+.5f)/h);
                            double error=Difference(Sample(probe,texture,uv,captured.Mip,target,readback),captured.Rgba);
                            Require(error<2e-6,"Native view sample mismatch "+spec.File+" mip="+captured.Mip+" error="+Number(error));
                            Require(Difference(Sample(probe,texture,uv,captured.Mip,target,readback,true),captured.Rgba)<2e-6,"Integer Load/view mismatch "+spec.File);
                            maxError=Math.Max(maxError,error); samples++;
                        }
                        // Native RGBA8 ramp interpolation with exact quarter-texel
                        // weights. Negative address coordinates must clamp, not wrap.
                        if(spec.Ramp)
                        {
                            int x=127; float u=(x+.75f)/spec.Width,v=.5f/spec.Height;
                            var left=new Color(bytes[x*4]/255f,bytes[x*4+1]/255f,bytes[x*4+2]/255f,bytes[x*4+3]/255f);
                            var right=new Color(bytes[(x+1)*4]/255f,bytes[(x+1)*4+1]/255f,bytes[(x+1)*4+2]/255f,bytes[(x+1)*4+3]/255f);
                            var rampActual=Sample(probe,texture,new Vector2(u,v),0,target,readback);var expected=Color.LerpUnclamped(left,right,.25f);
                            // GPU normalized-format filtering need not equal ideal
                            // float arithmetic bit-for-bit. This is an explicitly
                            // bounded interpolation check, NOT a relaxed native
                            // PickPixel gate (which remains 2e-6 above).
                            Require(Difference(rampActual,expected)<=1.0/65535,"Ramp quarter interpolation mismatch "+spec.Role+" error="+Number(Difference(rampActual,expected)));
                            lines.Add("Ramp interpolation "+spec.Role+" error="+Number(Difference(rampActual,expected))+" ideal-float bound=1/65535; not claimed bit-exact GPU arithmetic");
                            Require(Difference(Sample(probe,texture,new Vector2(-.25f,v),0,target,readback),Sample(probe,texture,new Vector2(.5f/spec.Width,v),0,target,readback))<2e-6,"Ramp Clamp mismatch");
                        }
                        Reject(()=>EndfieldCapturedClothMaterials.CreateTexture(i,null),"null payload");
                        var corrupt=(byte[])bytes.Clone(); corrupt[0]^=1; Reject(()=>EndfieldCapturedClothMaterials.CreateTexture(i,corrupt),"tampered payload");
                    }
                    lines.Add("Native view GPU PASS images=7 mipLevels="+mips+" cases="+samples+" maxError="+Number(maxError)+"; SampleLevel + integer Load; RGB sRGB decode exactly once / alpha linear / no UV flip");
                    lines.Add("Native payload bytes/mip partitions PASS; fail-closed null/corruption=14; RGBA8 ramp bilinear/Clamp=4");
                    var shader=Shader.Find("Endfield/CharacterLit"); Require(shader!=null&&shader.isSupported,"CharacterLit unsupported");
                    var first=new Material(shader){name="M_actor_typhoea_cloth_01"}; var second=new Material(shader){name="M_actor_typhoea_cloth_02"}; owned.Add(first);owned.Add(second);
                    foreach(var material in new[]{first,second})
                    {
                        material.SetFloat("_MaterialFamily",0);material.SetFloat("_UseBumpMap",1);material.SetFloat("_BumpScale",1);material.SetFloat("_BackFaceNormalFlip",1);
                        material.SetFloat("_UseMetallicGlossMap",1);material.SetFloat("_UseDiffRampMap",1);material.SetFloat("_UseSpecRampMap",1);material.SetFloat("_UseShadowLutTex",0);
                        material.SetFloat("_Cull",0);material.SetFloat("_ClearCoat",0);material.SetFloat("_EmissionBrightness",8);material.SetColor("_BaseColor",Color.white);material.SetColor("_EmissionColor",Color.white);
                    }
                    first.SetFloat("_UseEmission",0);second.SetFloat("_UseEmission",1);
                    var mesh=new Mesh();owned.Add(mesh);mesh.vertices=new[]{new Vector3(-.5f,-.5f,0),new Vector3(.5f,-.5f,0),new Vector3(.5f,.5f,0),new Vector3(-.5f,.5f,0)};
                    mesh.normals=Enumerable.Repeat(Vector3.forward,4).ToArray();mesh.tangents=Enumerable.Repeat(new Vector4(1,0,0,1),4).ToArray();mesh.triangles=new[]{0,1,2,0,2,3};
                    var root=new GameObject("NativeClothMaterialOwnership");owned.Add(root);SceneManager.MoveGameObjectToScene(root,preview);
                    var renderer=root.AddComponent<MeshRenderer>();root.AddComponent<MeshFilter>().sharedMesh=mesh;renderer.sharedMaterials=new[]{first,second};
                    var rootBlock=new MaterialPropertyBlock();rootBlock.SetFloat("_RootSentinel",.37f);renderer.SetPropertyBlock(rootBlock);
                    var original=new MaterialPropertyBlock();original.SetFloat("_SlotSentinel",.83f);original.SetTexture("_BaseMap",Texture2D.whiteTexture);renderer.SetPropertyBlock(original,1);
                    var block=new MaterialPropertyBlock();
                    Endfield.EndfieldOfficialFrameGlobals.ApplyGlobals();Shader.SetGlobalFloat("_EndfieldLabelMode",0);Shader.SetGlobalFloat("_EndfieldCharacterSelfShadow",0);Shader.SetGlobalFloat("_EndfieldCapturedCubemapAvailable",0);
                    Shader.SetGlobalVector("_CharacterLightDir",new Vector4(0,0,1,1));Shader.SetGlobalVector("_CharacterLightColor",Vector4.one);Shader.SetGlobalVector("_WorldSpaceCameraPos",new Vector4(0,0,2,1));
                    Shader.SetGlobalVector("_CharacterParams11",new Vector4(.8f,0,.6f,0));Shader.SetGlobalVector("_CharacterParams12",new Vector4(1,1,1,0));
                    using(var normalEvidence=EndfieldCapturedClothInputs.Load())
                    {
                        using(var binding=EndfieldCapturedClothMaterials.Bind(root.transform,bundle.Textures,normalEvidence.Cloth01,normalEvidence.Cloth02))
                        {
                            Require(binding.SlotCount==2,"Unexpected slot count");renderer.GetPropertyBlock(block,0);Require(block.GetFloat("_RootSentinel")==.37f,"Root inheritance lost");
                            renderer.GetPropertyBlock(block,1);Require(block.GetFloat("_SlotSentinel")==.83f,"Slot merge lost");
                            for(int t=0;t<2;t++)
                            {
                                int baseIndex=t==0?0:2,pIndex=t==0?1:3;var sample=bundle.NativeSamples(baseIndex).First(s=>s.Mip==0&&s.X==1024&&s.Y==1024);
                                var uv=new Vector2((sample.X+.5f)/2048,(sample.Y+.5f)/2048);mesh.uv=Enumerable.Repeat(uv,4).ToArray();renderer.GetPropertyBlock(block,t);
                                Shader.SetGlobalFloat("_EndfieldDebugValueMode",4);
                                var baseResult=Draw(t==0?first:second,mesh,block,target,readback);
                                var fixtureBase=Constant(sample.Rgba,owned);block.SetTexture("_BaseMap",fixtureBase);
                                Require(Difference(baseResult,Draw(t==0?first:second,mesh,block,target,readback))<2e-5,"Production base view not consumed");
                                Shader.SetGlobalFloat("_EndfieldDebugValueMode",0);renderer.GetPropertyBlock(block,t);
                                var native=Draw(t==0?first:second,mesh,block,target,readback);
                                var packed=bundle.NativeSamples(pIndex).First(s=>s.Mip==0&&s.X==1024&&s.Y==1024);
                                block.SetTexture("_BaseMap",fixtureBase);block.SetTexture("_MetallicGlossMap",Constant(packed.Rgba,owned));
                                var rawNormal=Sample(probe,t==0?normalEvidence.Cloth01:normalEvidence.Cloth02,uv,0,target,readback);
                                block.SetTexture("_BumpMap",Constant(rawNormal,owned));
                                if(t==1)block.SetTexture("_EmissionMap",Constant(bundle.NativeSamples(4).First(s=>s.Mip==0&&s.X==1024&&s.Y==1024).Rgba,owned));
                                var fixture=Draw(t==0?first:second,mesh,block,target,readback);
                                Require(Difference(native,fixture)<2e-5,"Production D/P/N/E capture-domain fixture mismatch "+Number(Difference(native,fixture)));
                            }
                        }
                        renderer.GetPropertyBlock(block,0);Require(block.isEmpty,"Empty slot not restored");renderer.GetPropertyBlock(block,1);Require(block.GetTexture("_BaseMap")==Texture2D.whiteTexture&&block.GetFloat("_SlotSentinel")==.83f,"Slot not restored");
                        using(var binding=EndfieldCapturedClothMaterials.Bind(root.transform,bundle.Textures,normalEvidence.Cloth01,normalEvidence.Cloth02))
                        { renderer.GetPropertyBlock(block,0);block.SetTexture("_BaseMap",Texture2D.grayTexture);block.SetFloat("_LaterSentinel",.91f);renderer.SetPropertyBlock(block,0); }
                        renderer.GetPropertyBlock(block,0);Require(block.GetTexture("_BaseMap")==Texture2D.grayTexture&&block.GetFloat("_LaterSentinel")==.91f,"Foreign writer lost");
                        Require(block.GetTexture("_BumpMap")!=normalEvidence.Cloth01&&block.GetTexture("_SpecRampMap")!=bundle.Textures[6],"Foreign branch retained soon-to-be-released owned inputs");
                        renderer.SetPropertyBlock(null,0);
                        Reject(()=>EndfieldCapturedClothMaterials.Bind(cameraObject.transform,bundle.Textures,normalEvidence.Cloth01,normalEvidence.Cloth02),"missing slots");
                        first.SetFloat("_UseShadowLutTex",1);Reject(()=>EndfieldCapturedClothMaterials.Bind(root.transform,bundle.Textures,normalEvidence.Cloth01,normalEvidence.Cloth02),"invented ShadowLUT");first.SetFloat("_UseShadowLutTex",0);
                        renderer.GetPropertyBlock(block,0);Require(block.isEmpty,"Rejected binding partially mutated");
                        var texture=bundle.Textures[0];texture.filterMode=FilterMode.Trilinear;
                        Reject(()=>EndfieldCapturedClothMaterials.Bind(root.transform,bundle.Textures,normalEvidence.Cloth01,normalEvidence.Cloth02),"altered sampler");texture.filterMode=FilterMode.Bilinear;
                    }
                    lines.Add("Production native base + D/P/N/E vs decoded constant fixtures PASS cases=4; shared native ramps retained; source algebra certified by separate regressions, not this equivalence check");
                    lines.Add("Scoped ownership PASS root/slot merge, empty-slot restore, foreign texture+later fields preserved, no dangling owned inputs; reject missing slots/ShadowLUT/altered sampler without partial bind");
                    var actual=EditorSceneManager.OpenScene("Assets/Scenes/Typhoeus_OfficialFrame_Recovered.unity",OpenSceneMode.Additive);
                    try
                    {
                        var actualRoot=actual.GetRootGameObjects().Single(g=>g.name=="chr_0034_typhoea_rebuilt");bool dirty=actual.isDirty;
                        bundle.Bind(actualRoot.transform);Require(bundle.SlotCount==2&&actual.isDirty==dirty,"Actual scene input bind changed dirty state/slots");
                        lines.Add("Actual recovered character native material+normal bind PASS slots=2 dirtyStateUnchanged=true; no scene save/full frame render/settings changes");
                        bundle.Dispose();
                    }
                    finally {EditorSceneManager.CloseScene(actual,true);}
                    foreach(var s in new[]{shader,probeShader})Require(!ShaderUtil.GetShaderMessages(s).Any(m=>m.severity==UnityEditor.Rendering.ShaderCompilerMessageSeverity.Error),"Shader compiler error");
                    for(int p=0;p<first.passCount;p++)Require(first.SetPass(p),"Default pass failed "+p);
                    lines.Add("RESULT PASS defaultPasses="+first.passCount+"; only these two dry opaque cloth input variants, not all uniforms/weather/final scene/MMD.");
                }
                using(var stream=new FileStream(output,FileMode.CreateNew,FileAccess.Write))using(var writer=new StreamWriter(stream))foreach(var line in lines)writer.WriteLine(line);
                Debug.Log("Native cloth materials PASS: "+output);
            }
            finally
            {
                for(int i=0;i<vectors.Length;i++)Shader.SetGlobalVector(vectors[i],savedVectors[i]);for(int i=0;i<floats.Length;i++)Shader.SetGlobalFloat(floats[i],savedFloats[i]);Shader.SetGlobalTexture("_CharMaxCubemap",savedCube);
                RenderTexture.active=prior;for(int i=owned.Count-1;i>=0;i--)if(owned[i]!=null){if(owned[i] is RenderTexture rt)rt.Release();Object.DestroyImmediate(owned[i]);}
                if(preview.IsValid())EditorSceneManager.ClosePreviewScene(preview);
            }
        }
    }
}
