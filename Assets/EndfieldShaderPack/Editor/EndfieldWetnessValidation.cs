using System;
using System.Collections.Generic;
using System.IO;
using UnityEditor;
using UnityEditor.SceneManagement;
using UnityEngine;
using UnityEngine.Rendering;
using EndfieldShaderPack.EditorTools.Mmd;
using Object = UnityEngine.Object;

namespace EndfieldShaderPack
{
    public static class EndfieldWetnessValidation
    {
        static void Require(bool valid, string reason) { if (!valid) throw new InvalidOperationException(reason); }
        static int checks;
        static List<string> lines;
        static void Check(bool valid, string reason) { Require(valid, reason); checks++; lines.Add("PASS " + reason); }
        public static void RunBatch()
        {
            string output = Environment.GetEnvironmentVariable("ENDFIELD_WET_OUTPUT") ?? "Validation/wetness-20261001-01";
            Require(!Directory.Exists(output), "Fresh output directory required."); Directory.CreateDirectory(output);
            lines = new List<string>(); checks = 0;
            try
            {
                VerifyGpu();
                var priorQuality=QualitySettings.renderPipeline;var priorDefault=GraphicsSettings.defaultRenderPipeline;
                Transform renderedRoot=null;
                using (var session = new EndfieldWetnessSession(true))
                {
                    renderedRoot=session.Root;
                    Check(session.Weather.PreparedMeshCount == 2, "only two reviewed cloth rest mesh streams prepared without saving assets");
                    EndfieldWetnessSession.RestoreCanonicalBindPose(session.Root);
                    session.FrameFront();
                    VerifyBindGeometry(session.Root);
                    session.Weather.freezeTime = true; session.Weather.seconds = 12;
                    VerifyWeatherScope(session.Weather);
                    session.Weather.wetEnabled = false;
                    Shader.SetGlobalFloat("_EndfieldDebugValueMode",231);
                    session.SavePreview(Path.Combine(output, "debug-dry-gates.png"));
                    Shader.SetGlobalFloat("_EndfieldDebugValueMode",0);
                    session.SavePreview(Path.Combine(output, "01-dry.png"));
                    session.Weather.wetEnabled = true; session.Weather.rain = 1; session.SavePreview(Path.Combine(output, "02-rain.png"));
                    Shader.SetGlobalFloat("_EndfieldDebugValueMode",231);
                    session.SavePreview(Path.Combine(output, "debug-wet-gates.png"));
                    session.SavePreview(Path.Combine(output, "debug-wet-camera-events.png"),1280,800,true);
                    Shader.SetGlobalFloat("_EndfieldDebugValueMode",0);
                    CheckRenderedWetGates(Path.Combine(output,"debug-dry-gates.png"),Path.Combine(output,"debug-wet-gates.png"));
                    CheckRenderedWetGates(Path.Combine(output,"debug-dry-gates.png"),Path.Combine(output,"debug-wet-camera-events.png"));
                    var skinRenderers=session.Root.GetComponentsInChildren<SkinnedMeshRenderer>(true);
                    foreach(var renderer in skinRenderers)
                    {
                        Check(renderer.forceMatrixRecalculationPerRender,"synchronous skin matrices refreshed: "+renderer.name);
                    }
                    Check(Shader.GetGlobalFloat("_EndfieldCharacterWetnessEnabled") == 0, "wet gate restored after camera");
                    session.Weather.wetEnabled = false;
                    session.SavePreview(Path.Combine(output, "02b-return-dry.png"));
                    VerifyDryRestoration(Path.Combine(output,"01-dry.png"),Path.Combine(output,"02b-return-dry.png"));
                    session.InitializeMmdPose();
                    foreach(var renderer in skinRenderers)
                    {
                        var baked=new Mesh();renderer.BakeMesh(baked);
                        lines.Add("CPU pose mesh="+renderer.name+" bounds="+baked.bounds+" allBoneCount="+renderer.bones.Length);
                        Object.DestroyImmediate(baked);
                    }
                    var p = MmdRetargetProfile.FromUnity(session.Root);
                    Vector3 World(int role) => p.ByRole(role).transform.position;
                    Check(Vector3.Dot((World(10)-World(0)).normalized, Vector3.up) > .94f, "visible calibrated trunk upright");
                    Check(Vector3.Dot((World(1)-World(2)).normalized,(World(13)-World(14)).normalized)>.95f,
                        "pelvis lateral axis agrees with shoulders (no reflected basis/twist)");
                    for (int side=0; side<2; side++)
                    {
                        var arm = (World(13+side)-World(14-side)).normalized;
                        Check(Vector3.Dot((World(15+side)-World(13+side)).normalized, arm) > .94f, "visible upper arm T-pose side " + side);
                        Check(Vector3.Dot((World(17+side)-World(15+side)).normalized, arm) > .94f, "visible forearm T-pose side " + side);
                        Check(Vector3.Dot((World(3+side)-World(1+side)).normalized, Vector3.down) > .94f, "visible thigh downward side " + side);
                    }
                    session.SavePreview(Path.Combine(output, "03-mmd-initial-tpose.png"));
                    // Independent repeat/reset test: no current dirty pose can become bind.
                    var clip = new VmdMotionClip(); var player = MmdPlayer.Load(clip, session.Root);
                    Check(player.calibrationOk, "MMD player calibrates from visible clean T-pose");
                    var hand = p.ByRole(17).transform; Quaternion original = hand.localRotation;
                    hand.localRotation = Quaternion.Euler(37, 51, 29); player.Reset();
                    Check(Quaternion.Angle(hand.localRotation, original) < .001f, "reset removes injected stale hand rotation");
                    string motion = Environment.GetEnvironmentVariable("ENDFIELD_MMD_TEST_MOTION");
                    if (!string.IsNullOrEmpty(motion))
                    {
                        player = MmdPlayer.Load(Vmd.ReadFile(motion), session.Root);
                        Check(player.calibrationOk, "provided VMD calibration");
                        Quaternion before = p.ByRole(13).transform.localRotation; float maxAngle = 0;
                        foreach(float time in new[]{0f, .3f, 1f, 2f, 4f})
                        {
                            player.Reset(); player.ApplyFrame(time, player.suggestedScale, true, 0);
                            Endfield.EndfieldSkinBasisDriver.ApplyForTyphoeus(session.Root);
                            foreach(var bone in player.profile.bones) if(bone.transform != null)
                                Require(float.IsFinite(bone.transform.localRotation.x + bone.transform.localRotation.y + bone.transform.localRotation.z + bone.transform.localRotation.w), "Nonfinite VMD bone");
                            maxAngle = Mathf.Max(maxAngle, Quaternion.Angle(before,p.ByRole(13).transform.localRotation));
                            session.SavePreview(Path.Combine(output,"04-mmd-"+time.ToString("F1", System.Globalization.CultureInfo.InvariantCulture)+".png"));
                        }
                        Check(maxAngle > 1, "actual VMD upper arm motion / all bones finite five times");
                        lines.Add("VMD="+motion+"; "+player.loadInfo);
                    }
                    foreach (var shader in new[]{Shader.Find("Endfield/CharacterLit"),Shader.Find("Hidden/Endfield/WetnessProbe")})
                        foreach(var message in ShaderUtil.GetShaderMessages(shader))
                            Require(message.severity != UnityEditor.Rendering.ShaderCompilerMessageSeverity.Error, message.message);
                    Check(true, "production/probe shaders compile after actual renders");
                }
                Check(QualitySettings.renderPipeline==priorQuality&&GraphicsSettings.defaultRenderPipeline==priorDefault,
                    "closing session restores prior pipeline assets in memory");
                Check(renderedRoot.GetComponent<EndfieldCharacterWeather>()==null,"closing session removes owned weather component");
                foreach(var renderer in renderedRoot.GetComponentsInChildren<SkinnedMeshRenderer>(true))
                    Check(!renderer.sharedMesh.name.Contains("wet rest streams"),"closing session restores original mesh: "+renderer.name);
                lines.Add("RESULT PASS checks="+checks+"; b471 manual cloth preview / MMD start only, not complete weather or arbitrary motion certification.");
                File.WriteAllLines(Path.Combine(output,"report.txt"),lines); Debug.Log("Wetness/MMD initial PASS: "+output);
            }
            catch(Exception error) { lines.Add("FAIL "+error); File.WriteAllLines(Path.Combine(output,"report.txt"),lines); throw; }
            finally { EditorSceneManager.NewScene(NewSceneSetup.EmptyScene,NewSceneMode.Single); }
        }
        static void VerifyWeatherScope(EndfieldCharacterWeather weather)
        {
            var cp = Shader.GetGlobalVector("_CharacterParams10");
            var texture = Shader.GetGlobalTexture("_CharacterRainEffectTex");
            float gate = Shader.GetGlobalFloat("_EndfieldCharacterWetnessEnabled");
            weather.wetEnabled=true;
            using(weather.BeginRenderScope())
            {
                Check(Shader.GetGlobalFloat("_EndfieldCharacterWetnessEnabled")==1,"outer explicit weather scope enabled");
                using(weather.BeginRenderScope()) Check(Shader.GetGlobalTexture("_CharacterRainEffectTex")==weather.rainEffect,"nested scope native texture");
                Check(Shader.GetGlobalFloat("_EndfieldCharacterWetnessEnabled")==1,"inner dispose preserves outer scope");
            }
            Check(Shader.GetGlobalFloat("_EndfieldCharacterWetnessEnabled")==gate && Shader.GetGlobalVector("_CharacterParams10")==cp
                && Shader.GetGlobalTexture("_CharacterRainEffectTex")==texture,"explicit scope restores prior globals/textures");
            weather.rain=float.NaN;
            using(weather.BeginRenderScope()) Check(Shader.GetGlobalFloat("_EndfieldCharacterWetnessEnabled")==0
                && weather.InputError.Length>0,"invalid input disables wet response without poisoning camera");
            weather.rain=1;
            try {using(weather.BeginRenderScope()) throw new OperationCanceledException("intentional scope test");}
            catch(OperationCanceledException) {}
            Check(Shader.GetGlobalFloat("_EndfieldCharacterWetnessEnabled")==gate,"exception restores explicit scope");
        }
        static void VerifyDryRestoration(string first, string restored)
        {
            var a=new Texture2D(2,2); var b=new Texture2D(2,2);
            try
            {
                a.LoadImage(File.ReadAllBytes(first)); b.LoadImage(File.ReadAllBytes(restored));
                var pa=a.GetPixels32();var pb=b.GetPixels32();int max=0;
                for(int i=0;i<pa.Length;i++) for(int c=0;c<3;c++)
                    max=Math.Max(max,Math.Abs((c==0?pa[i].r:c==1?pa[i].g:pa[i].b)-(c==0?pb[i].r:c==1?pb[i].g:pb[i].b)));
                Check(max<=1,"own dry/wet/dry switch restores output (not official-image fitting); max="+max);
            }
            finally {Object.DestroyImmediate(a);Object.DestroyImmediate(b);}
        }
        static void VerifyBindGeometry(Transform root)
        {
            foreach(var renderer in root.GetComponentsInChildren<SkinnedMeshRenderer>(true))
            {
                var mesh = renderer.sharedMesh; if(mesh == null) continue;
                var baked = new Mesh();
                try
                {
                    renderer.BakeMesh(baked); var a = mesh.vertices; var b = baked.vertices; float max=0;
                    Require(a.Length == b.Length,"Bind vertex count mismatch");
                    for(int i=0;i<a.Length;i++) max=Mathf.Max(max,Vector3.Distance(a[i],b[i]));
                    Check(max<2e-4f,"complete weighted bind geometry restored: "+renderer.name+" max="+max);
                }
                finally { Object.DestroyImmediate(baked); }
            }
        }
        static void CheckRenderedWetGates(string dryPath, string wetPath)
        {
            var dry = new Texture2D(2,2); var wet = new Texture2D(2,2);
            try
            {
                dry.LoadImage(File.ReadAllBytes(dryPath)); wet.LoadImage(File.ReadAllBytes(wetPath));
                var a = dry.GetPixels32(); var b = wet.GetPixels32(); int tested=0, active=0;
                for(int i=0;i<a.Length;i++)
                    if(a[i].r>180 && a[i].g<25 && a[i].b<25)
                    { tested++; if(b[i].g>160 && b[i].b>160) active++; }
                Check(tested>300 && active>.98f*tested,"production camera wet gates reach reviewed cloth fragments: "+active+"/"+tested);
            }
            finally {Object.DestroyImmediate(dry); Object.DestroyImmediate(wet);}
        }
        static void VerifyGpu()
        {
            var shader=Shader.Find("Hidden/Endfield/WetnessProbe"); Require(shader != null,"Probe missing");
            var material=new Material(shader); var rt=new RenderTexture(1,1,0,RenderTextureFormat.ARGBFloat,RenderTextureReadWrite.Linear);
            var read=new Texture2D(1,1,TextureFormat.RGBAFloat,false,true); var old=RenderTexture.active;
            Color Draw(int mode)
            {
                material.SetFloat("_ProbeMode",mode); Graphics.Blit(Texture2D.blackTexture,rt,material);
                RenderTexture.active=rt; read.ReadPixels(new Rect(0,0,1,1),0,0); read.Apply(); return read.GetPixel(0,0);
            }
            try
            {
                rt.Create();
                uint[] patterns={0u,1u,255u,0x12345678u,0x7fc12345u,0xffffffffu};
                foreach(uint bits in patterns)
                {
                    material.SetVector("_CharacterParams10",new Vector4(1,BitConverter.ToSingle(BitConverter.GetBytes(bits),0),2.25f,-100));
                    var color=Draw(0);
                    for(int c=0;c<4;c++) Check(Mathf.Abs(color[c]-((bits>>(8*c))&255)/255f)<2e-6f,"GPU packed float bits "+bits.ToString("x8")+" channel "+c);
                }
                material.SetVector("_CharacterParams10",new Vector4(.5f,EndfieldCharacterWeather.Pack(1,0,0),2.25f,2));
                material.SetVector("_EndfieldObjectWeather",new Vector4(EndfieldCharacterWeather.Pack(0,1,.25f),0,0,0));
                material.SetFloat("_ProbeY",1); var input=Draw(1);
                Check(input.r==0 && Mathf.Abs(input.g-.606414f)<3e-5f && Mathf.Abs(input.b-input.g)<2e-6f,"selector equal .5 uses object bytes but water height continuous lerp");
                using(var maps=EndfieldWeatherInputs.Load())
                {
                    material.SetTexture("_CharacterRainEffectTex",maps.Rain); material.SetTexture("_CharacterRainStreakTex",maps.Streak);
                    int textureIndex = 0;
                    foreach (Dictionary<string,object> entry in (List<object>)maps.Manifest["textures"])
                    {
                        foreach (Dictionary<string,object> sample in (List<object>)entry["native_samples"])
                        {
                            material.SetVector("_ProbeLoad", new Vector4(Convert.ToInt32(sample["mip"]),Convert.ToInt32(sample["x"]),Convert.ToInt32(sample["y"]),textureIndex));
                            var native=Draw(4); var rgba=(List<object>)sample["rgba"];
                            for(int c=0;c<4;c++) Check(Mathf.Abs(native[c]-Convert.ToSingle(rgba[c]))<2e-6f,"native weather mip/view "+entry["role"]+" mip="+sample["mip"]+" channel="+c);
                        }
                        textureIndex++;
                    }
                    material.SetFloat("_EndfieldCapturedGlobalMipBias",-1); material.SetVector("_EndfieldWeatherTime",new Vector4(1,.6f,0,0));
                    material.SetFloat("_DisableRainEffectOnMaterial",0);
                    foreach(float rain in new[]{0f,.25f,.6f,1f})
                    {
                        material.SetVector("_CharacterParams10",new Vector4(1,EndfieldCharacterWeather.Pack(rain,0,0),2.25f,-100));
                        var result=Draw(2); var normal=Draw(3);
                        Check(float.IsFinite(result.r+result.g+result.b+result.a) && result.r>=0 && result.r<=1 && result.g>=0 && result.g<=1,"wet surface finite/range rain="+rain);
                        Check(Mathf.Abs(new Vector3(normal.r,normal.g,normal.b).magnitude-1)<2e-5f,"wet spec normal unit rain="+rain);
                    }
                    material.SetFloat("_DisableRainEffectOnMaterial",1); var disabled=Draw(2);
                    Check(Mathf.Abs(disabled.r-.6f)<2e-6f&&disabled.g==0&&Mathf.Abs(disabled.b-.4f)<2e-6f,"material exclusion keeps dry surface");
                }
                Check(EndfieldCharacterWeather.PackBits(1,0,0)==255u && EndfieldCharacterWeather.PackBits(0,1,0)==65280u,"CPU channel bit locations");
                bool rejected=false; try{EndfieldCharacterWeather.Pack(float.NaN,0,0);}catch(ArgumentOutOfRangeException){rejected=true;}
                Check(rejected,"reject nonfinite user channel");
            }
            finally { RenderTexture.active=old; Object.DestroyImmediate(material);Object.DestroyImmediate(read);rt.Release();Object.DestroyImmediate(rt); }
        }
    }
}
