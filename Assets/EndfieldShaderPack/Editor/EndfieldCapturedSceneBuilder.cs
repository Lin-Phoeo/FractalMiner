using System;
using System.Globalization;
using System.IO;
using System.Linq;
using System.Text;
using UnityEditor;
using UnityEditor.SceneManagement;
using UnityEngine;
using UnityEngine.Rendering;
using UnityEngine.Rendering.Universal;
using Object = UnityEngine.Object;

namespace EndfieldShaderPack
{
    public static class EndfieldCapturedSceneBuilder
    {
        public const string ScenePath="Assets/Scenes/Typhoeus_CapturedPipeline.unity";
        public const string RecoveredScenePath="Assets/Scenes/Typhoeus_OfficialFrame_Recovered.unity";
        const string ReportPath="Logs/captured-scene-validation.txt";
        const string RestartReportPath="Logs/captured-scene-restart-validation.txt";
        const string RestartCheckPath="Library/EndfieldCapturedRestartCheck.json";

        [Serializable]
        sealed class RestartCheck
        {
            public int tier;
            public string activatedPipelineGuid="";
            public string originalPipelineGuid="";
            public string qualitySha256BeforeActivation="";
            public string activatedUtc="";
            public string armedUtc="";
        }

        // Pure generation: assets plus scene only. Project settings are a
        // project/quality-tier concern and are never written from here, so no
        // SaveScene/OpenScene/Refresh downstream can flush a pipeline override.
        [MenuItem("Endfield/Build Captured Pipeline Showcase",false,65)]
        public static void Build()
        {
            if(!Application.isBatchMode && !EditorSceneManager.SaveCurrentModifiedScenesIfUserWantsTo())return;
            if(EndfieldCapturedPipelineActivation.IsActivated)
                throw new InvalidOperationException("Restore the original pipeline before rebuilding; while activated, GraphicsSettings.currentRenderPipeline is the generated asset and Build would clone it instead of the project's own pipeline.");
            if(EndfieldCaptureAssets.EnvironmentCube==null || EndfieldCaptureAssets.Texture("grading-lut")==null)
                EndfieldCaptureAssets.ImportAll();
            EditorSceneManager.OpenScene(RecoveredScenePath,OpenSceneMode.Single);
            var originalPipeline=GraphicsSettings.currentRenderPipeline as UniversalRenderPipelineAsset;
            if(originalPipeline==null)throw new InvalidOperationException("An active URP pipeline is required.");
            var pipelineData=new SerializedObject(originalPipeline);
            int rendererIndex=pipelineData.FindProperty("m_DefaultRendererIndex").intValue;
            var originalRenderer=pipelineData.FindProperty("m_RendererDataList").GetArrayElementAtIndex(rendererIndex).objectReferenceValue as UniversalRendererData;
            if(originalRenderer==null)throw new InvalidOperationException("Expected UniversalRendererData.");

            string folder=EndfieldCaptureAssets.Root+"/Settings";Directory.CreateDirectory(folder);AssetDatabase.Refresh();
            var renderer=Upsert(Object.Instantiate(originalRenderer),folder+"/CapturedRenderer.asset");
            renderer.name="Endfield Captured Renderer";
            renderer.rendererFeatures.Clear();
            string rendererPath=AssetDatabase.GetAssetPath(renderer);
            var feature=AssetDatabase.LoadAllAssetsAtPath(rendererPath).OfType<EndfieldCapturedPostFeature>().FirstOrDefault();
            if(feature==null){feature=ScriptableObject.CreateInstance<EndfieldCapturedPostFeature>();AssetDatabase.AddObjectToAsset(feature,renderer);}
            feature.name="Captured LogC LUT and Dynamic Bloom";
            var settings=new SerializedObject(feature);
            settings.FindProperty("shader").objectReferenceValue=Shader.Find("Hidden/Endfield/CapturedPost");
            settings.FindProperty("bloomShader").objectReferenceValue=AssetDatabase.LoadAssetAtPath<ComputeShader>("Assets/EndfieldShaderPack/EndfieldCapturedBloom.compute");
            settings.ApplyModifiedPropertiesWithoutUndo();
            feature.SetActive(true);feature.Create();renderer.rendererFeatures.Add(feature);
            renderer.SetDirty();EditorUtility.SetDirty(feature);EditorUtility.SetDirty(renderer);
            if(renderer.rendererFeatures.Count!=1 || AssetDatabase.LoadAllAssetsAtPath(rendererPath).OfType<EndfieldCapturedPostFeature>().Count()!=1)
                throw new InvalidOperationException("Duplicate or missing generated renderer feature.");

            var pipeline=Upsert(Object.Instantiate(originalPipeline),folder+"/CapturedPipeline.asset");
            pipeline.name="Endfield Captured Pipeline";pipeline.supportsHDR=true;pipeline.msaaSampleCount=1;pipeline.renderScale=1;
            var pipelineSerialized=new SerializedObject(pipeline);
            var renderers=pipelineSerialized.FindProperty("m_RendererDataList");renderers.arraySize=1;renderers.GetArrayElementAtIndex(0).objectReferenceValue=renderer;
            pipelineSerialized.FindProperty("m_DefaultRendererIndex").intValue=0;
            pipelineSerialized.ApplyModifiedPropertiesWithoutUndo();EditorUtility.SetDirty(pipeline);AssetDatabase.SaveAssets();

            var camera=Camera.main;
            if(camera==null)throw new InvalidOperationException("No main camera in recovered scene.");
            camera.allowHDR=true;camera.allowMSAA=false;camera.allowDynamicResolution=false;
            var additional=camera.GetUniversalAdditionalCameraData();additional.renderPostProcessing=false;
            additional.antialiasing=AntialiasingMode.None;additional.dithering=false;additional.SetRenderer(0);
            var profile=camera.GetComponent<EndfieldCapturedPostProfile>() ?? camera.gameObject.AddComponent<EndfieldCapturedPostProfile>();
            profile.logLut=EndfieldCaptureAssets.Texture("grading-lut");
            profile.lutUV=new Vector4(1,-1,0,1); // Proven against full captured event1205, EXR rows are inverted.
            profile.generateBloom=true;profile.applyCapturedPost=true;
            profile.referenceBloomTexture=null;profile.liveBloomTexture=null;
            var globals=Object.FindObjectOfType<Endfield.EndfieldOfficialFrameGlobals>();
            if(globals==null)throw new InvalidOperationException("Missing captured character globals.");
            globals.useSourceShading=true;globals.capturedEnvironment=EndfieldCaptureAssets.EnvironmentCube;
            Endfield.EndfieldOfficialFrameGlobals.ApplyGlobals(true,globals.capturedEnvironment);
            EditorSceneManager.SaveScene(EditorSceneManager.GetActiveScene(),ScenePath);
            var errors=ShaderUtil.GetShaderMessages(Shader.Find("Hidden/Endfield/CapturedPost"))
                .Where(m=>m.severity==UnityEditor.Rendering.ShaderCompilerMessageSeverity.Error).ToArray();
            if(errors.Length!=0)throw new InvalidOperationException(string.Join("; ",errors.Select(m=>m.message)));
            Debug.Log("[CapturedScene] Generated the isolated pipeline, renderer feature and showcase scene. ProjectSettings untouched; the captured renderer is only reachable after Endfield/Captured Pipeline/Activate generated pipeline.");
        }

        // The showcase camera only executes the captured post/dynamic bloom while the
        // generated pipeline is the project's active one, so the live render is an
        // explicitly activated step rather than a side effect of building.
        public static void RenderShowcasePreview()
        {
            if(!EndfieldCapturedPipelineActivation.IsActivated)
                throw new InvalidOperationException("Activate the generated pipeline first; the showcase renderer feature is not reachable from the project's own pipeline.");
            EditorSceneManager.OpenScene(ScenePath,OpenSceneMode.Single);
            var camera=Camera.main;
            if(camera==null)throw new InvalidOperationException("No main camera in the generated scene.");
            var profile=camera.GetComponent<EndfieldCapturedPostProfile>();
            if(profile==null)throw new InvalidOperationException("Generated scene has no captured post profile.");
            SaveHDRPreview(camera,profile,"official-captured-pipeline.png",1600,1000);
        }

        public static void BuildAndValidate()
        {
            if(!Application.isBatchMode && !EditorSceneManager.SaveCurrentModifiedScenesIfUserWantsTo())return;
            if(EndfieldCapturedPipelineActivation.IsActivated)
                throw new InvalidOperationException("An activation is already in progress ("+EndfieldCapturedPipelineActivation.StatePath+"); restore it before running the gate.");

            var report=new StringBuilder();
            int failures=0;
            report.AppendLine("Endfield captured pipeline showcase gate");
            report.AppendLine("utc: "+DateTime.UtcNow.ToString("o",CultureInfo.InvariantCulture));
            report.AppendLine();

            report.AppendLine("--- activation isolation (sandbox copy, real project untouched) ---");
            failures+=EndfieldCapturedPipelineIsolationValidation.RunAll(report);
            report.AppendLine();

            // Let Unity normalise its own serialisation once first, so a one-time
            // format upgrade is never attributed to Build.
            AssetDatabase.Refresh();
            AssetDatabase.SaveAssets();
            string[] settingsFiles={EndfieldCapturedPipelineActivation.QualitySettingsPath,EndfieldCapturedPipelineActivation.GraphicsSettingsPath};
            var baseline=settingsFiles.Select(File.ReadAllBytes).ToArray();
            string recoveredBefore=Sha256(RecoveredScenePath);
            int tier=QualitySettings.GetQualityLevel();
            var tierGuidsBefore=EndfieldCapturedPipelineActivation.AllTierGuids();
            report.AppendLine("--- baseline after one normalisation pass ---");
            report.AppendLine("tier: "+tier+" ("+QualitySettings.names[tier]+")");
            for(int i=0;i<settingsFiles.Length;i++)report.AppendLine(settingsFiles[i]+": "+Sha256(settingsFiles[i]));
            report.AppendLine(RecoveredScenePath+": "+recoveredBefore);
            report.AppendLine();

            Check(report,ref failures,"Build twice keeps generated asset GUIDs stable",()=>
            {
                EditorSceneManager.OpenScene(RecoveredScenePath,OpenSceneMode.Single);
                Build();
                string[] assets={ScenePath,EndfieldCapturedPipelineActivation.PipelinePath,EndfieldCapturedPipelineActivation.RendererPath};
                var guids=assets.Select(AssetDatabase.AssetPathToGUID).ToArray();
                for(int i=0;i<guids.Length;i++)Require(!string.IsNullOrEmpty(guids[i]),"Missing GUID for "+assets[i]);
                Build();
                var rebuilt=assets.Select(AssetDatabase.AssetPathToGUID).ToArray();
                Require(guids.SequenceEqual(rebuilt),"Rebuilding changed generated asset GUIDs.");
                var rendererPath=EndfieldCapturedPipelineActivation.RendererPath;
                int features=AssetDatabase.LoadAllAssetsAtPath(rendererPath).OfType<EndfieldCapturedPostFeature>().Count();
                Require(features==1,"Expected exactly one generated renderer feature, found "+features+".");
            });

            Check(report,ref failures,"Build alone leaves ProjectSettings bytes unchanged",()=>
                RequireSettingsBytes(settingsFiles,baseline,"Build"));

            Check(report,ref failures,"Build alone leaves every quality tier pipeline unchanged",()=>
                RequireTierGuids(tierGuidsBefore,"Build"));

            Check(report,ref failures,"Build alone leaves the recovered baseline scene untouched",()=>
            {
                string now=Sha256(RecoveredScenePath);
                Require(now==recoveredBefore,RecoveredScenePath+" was overwritten: "+recoveredBefore+" -> "+now);
            });

            Check(report,ref failures,"explicit Activate runs the live captured post and dynamic bloom",()=>
            {
                var state=EndfieldCapturedPipelineActivation.Activate();
                try
                {
                    Require(EndfieldCapturedPipelineActivation.PipelineGuidAt(state.tier)==state.activatedPipelineGuid,
                        "Activation did not install the generated pipeline on tier "+state.tier+".");
                    RenderShowcasePreview();
                }
                finally
                {
                    // Leave the generated scene before restoring, so no scene save can
                    // flush the settings while they still hold the activated value.
                    EditorSceneManager.NewScene(NewSceneSetup.EmptyScene,NewSceneMode.Single);
                    EndfieldCapturedPipelineActivation.Restore();
                }
            });

            Check(report,ref failures,"Restore after the live render returns the original settings bytes",()=>
                RequireSettingsBytes(settingsFiles,baseline,"Activate+render+Restore"));

            Check(report,ref failures,"Restore after the live render returns every quality tier pipeline",()=>
                RequireTierGuids(tierGuidsBefore,"Activate+render+Restore"));

            Check(report,ref failures,"an exception while activated still restores the settings",()=>
            {
                EndfieldCapturedPipelineActivation.Activate();
                try
                {
                    EditorSceneManager.OpenScene(ScenePath,OpenSceneMode.Single);
                    throw new InvalidOperationException("injected failure while the generated pipeline was active");
                }
                catch(InvalidOperationException e) when(e.Message.StartsWith("injected",StringComparison.Ordinal)){}
                finally
                {
                    EditorSceneManager.NewScene(NewSceneSetup.EmptyScene,NewSceneMode.Single);
                    EndfieldCapturedPipelineActivation.Restore();
                }
                RequireSettingsBytes(settingsFiles,baseline,"exception path");
                RequireTierGuids(tierGuidsBefore,"exception path");
                Require(!EndfieldCapturedPipelineActivation.IsActivated,"Activation state survived the exception path.");
            });

            Check(report,ref failures,"the recovered baseline scene is still untouched at the end",()=>
            {
                string now=Sha256(RecoveredScenePath);
                Require(now==recoveredBefore,RecoveredScenePath+" was overwritten: "+recoveredBefore+" -> "+now);
            });

            EditorSceneManager.NewScene(NewSceneSetup.EmptyScene,NewSceneMode.Single);
            report.AppendLine();
            report.AppendLine(failures==0
                ? "PASS: pure generation, stable GUIDs, single renderer feature, explicit activation really executed dynamic bloom, and both the normal and exception paths restored the project settings."
                : "FAIL: "+failures+" gate check(s) failed.");
            Directory.CreateDirectory("Logs");File.WriteAllText(ReportPath,report.ToString());
            Debug.Log(report.ToString());
            if(failures!=0)throw new InvalidOperationException(failures+" captured scene gate check(s) failed; see "+ReportPath);
        }

        // Arms a real cross-process check: activation is left on disk, this Unity
        // process exits, and VerifyAfterRestartAndRestore re-reads it from a fresh one.
        public static void ActivateForRestartCheck()
        {
            if(EndfieldCapturedPipelineActivation.IsActivated)
                EndfieldCapturedPipelineActivation.Restore();
            Build();
            AssetDatabase.Refresh();
            AssetDatabase.SaveAssets();
            var state=EndfieldCapturedPipelineActivation.Activate();
            var check=new RestartCheck
            {
                tier=state.tier,
                activatedPipelineGuid=state.activatedPipelineGuid,
                originalPipelineGuid=state.originalPipelineGuid,
                qualitySha256BeforeActivation=state.qualitySha256,
                activatedUtc=state.activatedUtc,
                armedUtc=DateTime.UtcNow.ToString("o",CultureInfo.InvariantCulture)
            };
            File.WriteAllText(RestartCheckPath,JsonUtility.ToJson(check,true));
            Debug.Log("[CapturedScene] Restart check armed on tier "+check.tier+". Exit Unity now, then run VerifyAfterRestartAndRestore in a NEW process.");
        }

        public static void VerifyAfterRestartAndRestore()
        {
            Require(File.Exists(RestartCheckPath),"No armed restart check at "+RestartCheckPath+"; run ActivateForRestartCheck in a previous Unity process first.");
            var check=JsonUtility.FromJson<RestartCheck>(File.ReadAllText(RestartCheckPath));
            var report=new StringBuilder();
            int failures=0;
            report.AppendLine("Endfield captured pipeline restart gate");
            report.AppendLine("armedUtc: "+check.armedUtc);
            report.AppendLine("verifiedUtc: "+DateTime.UtcNow.ToString("o",CultureInfo.InvariantCulture));
            report.AppendLine("qualitySha256OnLoad: "+Sha256(EndfieldCapturedPipelineActivation.QualitySettingsPath));
            report.AppendLine("qualitySha256BeforeActivation: "+check.qualitySha256BeforeActivation);
            report.AppendLine();

            // A fresh process can only know this from disk, which is exactly the
            // distinction the old in-memory-only restore test could not make.
            Check(report,ref failures,"activation survived a full Unity restart",()=>
            {
                Require(EndfieldCapturedPipelineActivation.IsActivated,"Activation state did not survive the restart.");
                var state=EndfieldCapturedPipelineActivation.ReadState(EndfieldCapturedPipelineActivation.StatePath);
                Require(state.tier==check.tier,"State tier changed across the restart: "+check.tier+" -> "+state.tier);
                Require(state.activatedPipelineGuid==check.activatedPipelineGuid,"Activated GUID changed across the restart.");
                Require(EndfieldCapturedPipelineActivation.PipelineGuidAt(check.tier)==check.activatedPipelineGuid,
                    "The reloaded project does not report the activated pipeline on tier "+check.tier+".");
            });

            Check(report,ref failures,"live captured post and dynamic bloom still execute after the restart",()=>
                RenderShowcasePreview());

            try
            {
                Check(report,ref failures,"Restore after the restart returns the original pipeline semantics",()=>
                {
                    EndfieldCapturedPipelineActivation.Restore();
                    Require(EndfieldCapturedPipelineActivation.PipelineGuidAt(check.tier)==check.originalPipelineGuid,
                        "Tier "+check.tier+" points at "+EndfieldCapturedPipelineActivation.PipelineGuidAt(check.tier)+
                        " instead of "+check.originalPipelineGuid+" after restore.");
                    Require(!EndfieldCapturedPipelineActivation.IsActivated,"Activation state survived Restore.");
                });
            }
            finally
            {
                EditorSceneManager.NewScene(NewSceneSetup.EmptyScene,NewSceneMode.Single);
                if(EndfieldCapturedPipelineActivation.IsActivated)EndfieldCapturedPipelineActivation.Restore();
            }

            Check(report,ref failures,"Restore after the restart returns the pre-activation bytes",()=>
            {
                string now=Sha256(EndfieldCapturedPipelineActivation.QualitySettingsPath);
                Require(now==check.qualitySha256BeforeActivation,
                    "QualitySettings.asset did not return to its pre-activation bytes: "+
                    check.qualitySha256BeforeActivation+" -> "+now);
            });

            File.Delete(RestartCheckPath);
            report.AppendLine();
            report.AppendLine(failures==0
                ? "PASS: activation persisted across a real Unity restart, executed dynamic bloom, and Restore returned both the semantics and the bytes."
                : "FAIL: "+failures+" restart gate check(s) failed.");
            Directory.CreateDirectory("Logs");File.WriteAllText(RestartReportPath,report.ToString());
            Debug.Log(report.ToString());
            if(failures!=0)throw new InvalidOperationException(failures+" restart gate check(s) failed; see "+RestartReportPath);
        }

        static void Check(StringBuilder report,ref int failures,string name,Action body)
        {
            try
            {
                body();
                report.AppendLine("PASS  "+name);
            }
            catch(Exception e)
            {
                failures++;
                report.AppendLine("FAIL  "+name+" :: "+e.GetType().Name+": "+e.Message);
            }
        }

        static void Require(bool condition,string message)
        {
            if(!condition)throw new InvalidOperationException(message);
        }

        static void RequireSettingsBytes(string[] files,byte[][] baseline,string phase)
        {
            for(int i=0;i<files.Length;i++)
            {
                var now=File.ReadAllBytes(files[i]);
                if(!now.SequenceEqual(baseline[i]))
                    throw new InvalidOperationException(phase+" modified project settings: "+files[i]+
                        " ("+Sha256(files[i])+"), expected "+ToHex(baseline[i]));
            }
        }

        static void RequireTierGuids(System.Collections.Generic.IReadOnlyList<string> expected,string phase)
        {
            var now=EndfieldCapturedPipelineActivation.AllTierGuids();
            Require(now.Count==expected.Count,phase+" changed the quality tier count.");
            for(int i=0;i<expected.Count;i++)
                Require(now[i]==expected[i],phase+" changed tier "+i+" pipeline from "+
                    EndfieldCapturedPipelineActivation.Describe(expected[i])+" to "+
                    EndfieldCapturedPipelineActivation.Describe(now[i]));
        }

        static string ToHex(byte[] bytes)
        {
            var text=new StringBuilder(bytes.Length*2);
            foreach(byte b in bytes)text.Append(b.ToString("x2",CultureInfo.InvariantCulture));
            return text.ToString();
        }

        static string Sha256(string path)=>EndfieldCapturedPipelineActivation.Sha256(path);

        static void SaveHDRPreview(Camera camera,EndfieldCapturedPostProfile profile,string name,int width,int height)
        {
            var target=new RenderTexture(width,height,24,RenderTextureFormat.ARGBHalf,RenderTextureReadWrite.Linear);
            var readback=new Texture2D(width,height,TextureFormat.RGBAFloat,false,true);
            var png=new Texture2D(width,height,TextureFormat.RGBA32,false,true);
            var previousTarget=camera.targetTexture;var previousActive=RenderTexture.active;
            int before=profile.executedFrames;
            try
            {
                camera.targetTexture=target;camera.Render();
                if(profile.executedFrames<=before || !profile.lastFrameUsedDynamicBloom)
                    throw new InvalidOperationException("Live post/dynamic bloom did not execute on the showcase camera.");
                RenderTexture.active=target;readback.ReadPixels(new Rect(0,0,width,height),0,0);readback.Apply();
                var pixels=readback.GetPixels();
                for(int i=0;i<pixels.Length;i++)
                {
                    Color p=pixels[i];
                    if(float.IsNaN(p.r+p.g+p.b) || float.IsInfinity(p.r+p.g+p.b))throw new InvalidOperationException("Nonfinite HDR scene output.");
                    pixels[i]=p.gamma; // Linear target -> encoded PNG, exactly once.
                }
                png.SetPixels(pixels);png.Apply();Directory.CreateDirectory("Validation");
                File.WriteAllBytes("Validation/"+name,png.EncodeToPNG());
                Debug.Log($"[CapturedScene] HDR camera post executions={profile.executedFrames-before}; dynamicBloom={profile.lastFrameUsedDynamicBloom}; linear readback encoded once to PNG.");
            }
            finally
            {
                camera.targetTexture=previousTarget;RenderTexture.active=previousActive;
                target.Release();Object.DestroyImmediate(target);Object.DestroyImmediate(readback);Object.DestroyImmediate(png);
            }
        }

        static T Upsert<T>(T generated,string path) where T:Object
        {
            var existing=AssetDatabase.LoadAssetAtPath<T>(path);
            if(existing==null){AssetDatabase.CreateAsset(generated,path);return generated;}
            EditorUtility.CopySerialized(generated,existing);Object.DestroyImmediate(generated);EditorUtility.SetDirty(existing);return existing;
        }
    }
}
