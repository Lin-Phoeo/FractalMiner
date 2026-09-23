using System;
using System.IO;
using System.Linq;
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

        public static void BuildAndValidate()
        {
            if(!Application.isBatchMode && !EditorSceneManager.SaveCurrentModifiedScenesIfUserWantsTo())return;
            EditorSceneManager.OpenScene("Assets/Scenes/Typhoeus_OfficialFrame_Recovered.unity",OpenSceneMode.Single);
            string[] settingsFiles={"ProjectSettings/QualitySettings.asset","ProjectSettings/GraphicsSettings.asset"};
            var settingsBytes=settingsFiles.Select(File.ReadAllBytes).ToArray();
            var original=QualitySettings.renderPipeline;
            int tier=QualitySettings.GetQualityLevel();
            Build();
            string[] assets={ScenePath,EndfieldCaptureAssets.Root+"/Settings/CapturedPipeline.asset",EndfieldCaptureAssets.Root+"/Settings/CapturedRenderer.asset"};
            var guids=assets.Select(AssetDatabase.AssetPathToGUID).ToArray();
            Build();
            if(!guids.SequenceEqual(assets.Select(AssetDatabase.AssetPathToGUID)))
                throw new InvalidOperationException("Rebuilding changed generated asset GUIDs.");
            EditorSceneManager.OpenScene(ScenePath,OpenSceneMode.Single);
            var profile=Camera.main.GetComponent<EndfieldCapturedPostProfile>();
            SaveHDRPreview(Camera.main,profile,"official-captured-pipeline.png",1600,1000);
            // Reproduce a quality-tier switch plus an Inspector edit while active.
            var scope=Object.FindObjectOfType<Endfield.EndfieldCapturedPipelineScope>();
            int other=(tier+1)%QualitySettings.names.Length;
            var otherOriginal=QualitySettings.GetRenderPipelineAssetAt(other);
            QualitySettings.SetQualityLevel(other,false);scope.pipeline=null;scope.enabled=false;
            if(QualitySettings.GetRenderPipelineAssetAt(tier)!=original
                || QualitySettings.GetQualityLevel()!=other
                || QualitySettings.GetRenderPipelineAssetAt(other)!=otherOriginal)
                throw new InvalidOperationException("Pipeline scope did not restore the original quality tier.");
            QualitySettings.SetQualityLevel(tier,false);
            EditorSceneManager.NewScene(NewSceneSetup.EmptyScene,NewSceneMode.Single);
            for(int i=0;i<settingsFiles.Length;i++)
                if(!settingsBytes[i].SequenceEqual(File.ReadAllBytes(settingsFiles[i])))
                    throw new InvalidOperationException("Generated scene modified project settings: "+settingsFiles[i]);
            string result="PASS: build twice, stable GUIDs, reload and real HDR render; dynamic bloom executed; quality-tier/Inspector restoration; project settings bytes unchanged.";
            Directory.CreateDirectory("Logs");File.WriteAllText("Logs/captured-scene-validation.txt",result);Debug.Log(result);
        }

        [MenuItem("Endfield/Build Captured Pipeline Showcase",false,65)]
        public static void Build()
        {
            if(!Application.isBatchMode && !EditorSceneManager.SaveCurrentModifiedScenesIfUserWantsTo())return;
            if(EndfieldCaptureAssets.EnvironmentCube==null || EndfieldCaptureAssets.Texture("grading-lut")==null)
                EndfieldCaptureAssets.ImportAll();
            EditorSceneManager.OpenScene("Assets/Scenes/Typhoeus_OfficialFrame_Recovered.unity",OpenSceneMode.Single);
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
            var scope=new GameObject("Captured Pipeline Scope").AddComponent<Endfield.EndfieldCapturedPipelineScope>();
            scope.enabled=false;scope.pipeline=pipeline;scope.enabled=true;
            EditorSceneManager.SaveScene(EditorSceneManager.GetActiveScene(),ScenePath);
            SaveHDRPreview(camera,profile,"official-captured-pipeline.png",1600,1000);
            var errors=ShaderUtil.GetShaderMessages(Shader.Find("Hidden/Endfield/CapturedPost"))
                .Where(m=>m.severity==UnityEditor.Rendering.ShaderCompilerMessageSeverity.Error).ToArray();
            if(errors.Length!=0)throw new InvalidOperationException(string.Join("; ",errors.Select(m=>m.message)));
            Debug.Log("[CapturedScene] Saved isolated pipeline, real captured cube/LUT, dynamic bloom; no static shadow/bloom pasted into the model.");
        }

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
