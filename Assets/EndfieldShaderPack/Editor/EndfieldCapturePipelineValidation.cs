using System;
using System.IO;
using System.Linq;
using System.Text;
using UnityEditor;
using UnityEditor.SceneManagement;
using UnityEngine;
using UnityEngine.Rendering;
using Object = UnityEngine.Object;

namespace EndfieldShaderPack
{
    public static class EndfieldCapturePipelineValidation
    {
        public static void RunAssetDiagnostics()
        {
            EndfieldCaptureAssets.ImportBloomEvidence();
            var report=new StringBuilder();int failed=0;
            foreach(Action action in new Action[]{
                ()=>ValidateDynamicBloom(EndfieldCaptureAssets.Texture("post-input"),report),
                ()=>ValidateCube(EndfieldCaptureAssets.EnvironmentCube,report)})
            {
                try{action();}catch(Exception e){failed++;report.AppendLine(e.ToString());}
            }
            File.WriteAllText("Logs/capture-asset-diagnostics.txt",report.ToString());
            Debug.Log(report.ToString());
            if(failed!=0)throw new InvalidOperationException($"{failed} asset diagnostics failed.");
        }
        public static void RunAll()
        {
            if (!Application.isBatchMode && !EditorSceneManager.SaveCurrentModifiedScenesIfUserWantsTo()) return;
            var shader = Shader.Find("Hidden/Endfield/CapturedPost");
            if (shader == null) throw new InvalidOperationException("Captured post shader has not been implemented.");
            if (!shader.isSupported) throw new InvalidOperationException("Captured post shader is not supported.");
            EndfieldCaptureAssets.ImportAll();
            EditorSceneManager.NewScene(NewSceneSetup.EmptyScene, NewSceneMode.Single);
            var report = new StringBuilder("Frame6411 captured-pipeline validation\n");
            var cameraObject = new GameObject("CapturedReferenceCamera");
            cameraObject.AddComponent<Camera>();
            var profile = cameraObject.AddComponent<EndfieldCapturedPostProfile>();
            profile.applyCapturedPost = true;
            profile.logLut = EndfieldCaptureAssets.Texture("grading-lut");
            profile.referenceBloomTexture = EndfieldCaptureAssets.Texture("bloom");
            var input = EndfieldCaptureAssets.Texture("post-input");
            var reference = EndfieldCaptureAssets.Texture("post-output");
            var material = new Material(shader);
            var target = new RenderTexture(input.width,input.height,0,RenderTextureFormat.ARGBFloat,RenderTextureReadWrite.Linear);
            var readback = new Texture2D(input.width,input.height,TextureFormat.RGBAFloat,false,true);
            var previous = RenderTexture.active;
            double bestError = double.PositiveInfinity, bestWithinOne=0;
            string bestOrientation = "";
            try
            {
                Color[] expected = reference.GetPixels();
                foreach (bool flipLut in new[] {false,true})
                foreach (bool flipInput in new[] {false,true})
                {
                    var transform = flipInput ? new Vector4(1,-1,0,1) : new Vector4(1,1,0,0);
                    profile.referenceSourceUV = transform;
                    profile.referenceBloomUV = transform;
                    profile.referenceScreenUV = transform;
                    profile.lutUV = flipLut ? new Vector4(1,-1,0,1) : new Vector4(1,1,0,0);
                    if(!profile.ApplyTo(material,input.width,input.height,true,true)) throw new InvalidOperationException("Invalid linear LUT import.");
                    Graphics.Blit(input,target,material,1);
                    RenderTexture.active=target;
                    readback.ReadPixels(new Rect(0,0,input.width,input.height),0,0); readback.Apply();
                    Color[] actual = readback.GetPixels();
                    foreach(bool flipReference in new[]{false,true})
                    {
                        double error=0; int within=0; float max=0;
                        for(int y=0;y<input.height;y++)
                        for(int x=0;x<input.width;x++)
                        {
                            Color a=actual[y*input.width+x];
                            Color b=expected[(flipReference?input.height-1-y:y)*input.width+x];
                            for(int c=0;c<3;c++)
                            {
                                if(float.IsNaN(a[c]) || float.IsInfinity(a[c])) throw new InvalidOperationException("Nonfinite GPU post output.");
                                // Capture attachment is RGBA8_UNORM: compare quantized encoded channels.
                                float delta=Mathf.Abs(Mathf.Round(Mathf.Clamp01(a[c])*255)-Mathf.Round(Mathf.Clamp01(b[c])*255));
                                error+=delta; max=Mathf.Max(max,delta); if(delta<=1)within++;
                            }
                        }
                        double count=(double)input.width*input.height*3;
                        string label=$"lutFlip={flipLut} inputFlip={flipInput} referenceFlip={flipReference}";
                        report.AppendLine($"{label}: meanByteError={error/count:F6} withinOneLSB={within/count:F8} maxByteError={max}");
                        if(error/count<bestError){bestError=error/count;bestWithinOne=within/count;bestOrientation=label;}
                    }
                }
                var shadow=EndfieldCaptureAssets.Texture("screen-shadow").GetPixels();
                float rMin=1,rMax=0,gMin=1,gMax=0;long shaded=0;
                foreach(var p in shadow){rMin=Mathf.Min(rMin,p.r);rMax=Mathf.Max(rMax,p.r);gMin=Mathf.Min(gMin,p.g);gMax=Mathf.Max(gMax,p.g);if(p.g<.99f)shaded++;}
                report.AppendLine($"Shadow R=[{rMin},{rMax}] G=[{gMin},{gMax}] G<.99 pixels={shaded}/{shadow.Length}");
                var cube=EndfieldCaptureAssets.EnvironmentCube;
                if(cube==null || cube.width!=128 || cube.mipmapCount!=8)throw new InvalidOperationException("Captured cube/mips lost.");
                report.AppendLine($"Cube: {cube.format}, {cube.width}x{cube.height}, mips={cube.mipmapCount}");
                ValidateCube(cube,report);
                ValidateDynamicBloom(input,report);
                ValidateFlatPost(shader,profile,report);
                report.AppendLine($"Best: {bestOrientation}; meanByteError={bestError:F6}; withinOneLSB={bestWithinOne:F8}");
                var errors=ShaderUtil.GetShaderMessages(shader).Where(m=>m.severity==UnityEditor.Rendering.ShaderCompilerMessageSeverity.Error).ToArray();
                if(errors.Length!=0)throw new InvalidOperationException(string.Join("; ",errors.Select(e=>e.message)));
                if(bestError>.3 || bestWithinOne<.995)throw new InvalidOperationException("Post chain does not yet meet captured-frame numeric tolerance.");
                report.AppendLine("PASS: captured post input + LUT + bloom reproduces event1205 within numerical tolerance.");
                Debug.Log(report.ToString());
            }
            finally
            {
                Directory.CreateDirectory("Logs"); File.WriteAllText("Logs/capture-pipeline-validation.txt",report.ToString());
                RenderTexture.active=previous;target.Release();
                Object.DestroyImmediate(target);Object.DestroyImmediate(readback);Object.DestroyImmediate(material);Object.DestroyImmediate(cameraObject);
            }
        }

        static void ValidateFlatPost(Shader shader,EndfieldCapturedPostProfile profile,StringBuilder report)
        {
            var input=new Texture2D(4,4,TextureFormat.RGBAFloat,false,true);
            var target=new RenderTexture(4,4,0,RenderTextureFormat.ARGBFloat,RenderTextureReadWrite.Linear);
            var readback=new Texture2D(4,4,TextureFormat.RGBAFloat,false,true);
            var material=new Material(shader);var previous=RenderTexture.active;
            try
            {
                profile.sharpen=true;profile.dither=false;profile.vignette=false;
                foreach(float level in new[]{0f,.18f,1f,4f})
                {
                    input.SetPixels(Enumerable.Repeat(new Color(level,level,level,1),16).ToArray());input.Apply();
                    profile.ApplyTo(material,4,4,true,false);Graphics.Blit(input,target,material,1);
                    RenderTexture.active=target;readback.ReadPixels(new Rect(0,0,4,4),0,0);readback.Apply();
                    var raw=readback.GetPixels();
                    profile.ApplyTo(material,4,4,false,false);Graphics.Blit(input,target,material,1);
                    readback.ReadPixels(new Rect(0,0,4,4),0,0);readback.Apply();
                    var linear=readback.GetPixels();
                    for(int i=0;i<16;i++)for(int c=0;c<3;c++)
                    {
                        float expected=Mathf.GammaToLinearSpace(Mathf.Clamp01(raw[i][c]));
                        if(float.IsNaN(raw[i][c]) || float.IsInfinity(raw[i][c])
                            || float.IsNaN(linear[i][c]) || Mathf.Abs(linear[i][c]-expected)>.0005f)
                            throw new InvalidOperationException("Flat post finite/transfer check failed: "+level);
                    }
                    report.AppendLine($"Flat post input={level}: finite, raw-to-live sRGB transfer PASS");
                }
                if(material.GetTexture("_EndfieldPostBloom")!=Texture2D.blackTexture)
                    throw new InvalidOperationException("Captured reference bloom leaked into live profile.");
            }
            finally
            {
                RenderTexture.active=previous;target.Release();Object.DestroyImmediate(target);
                Object.DestroyImmediate(input);Object.DestroyImmediate(readback);Object.DestroyImmediate(material);
            }
        }

        static void ValidateDynamicBloom(Texture2D input, StringBuilder report)
        {
            // RenderingUtils uses URP's RTHandle pool. Graphics.Blit alone does
            // not construct a render pipeline in a fresh batch-mode editor.
            if(RenderPipelineManager.currentPipeline==null)
            {
                var warmObject=new GameObject("PipelineTestWarmup");
                var warmTarget=new RenderTexture(8,8,24,RenderTextureFormat.ARGBHalf,RenderTextureReadWrite.Linear);
                try
                {
                    var warm=warmObject.AddComponent<Camera>();warm.cullingMask=0;warm.targetTexture=warmTarget;warm.Render();warm.targetTexture=null;
                }
                finally{warmTarget.Release();Object.DestroyImmediate(warmTarget);Object.DestroyImmediate(warmObject);}
            }
            var shader=AssetDatabase.LoadAssetAtPath<ComputeShader>("Assets/EndfieldShaderPack/EndfieldCapturedBloom.compute");
            if(shader==null)throw new InvalidOperationException("Bloom compute missing.");
            var source=new RenderTexture(input.width,input.height,0,RenderTextureFormat.ARGBHalf,RenderTextureReadWrite.Linear);
            source.Create();
            var handle=RTHandles.Alloc(source);
            var bloom=new EndfieldCapturedBloom(shader);
            var command=new CommandBuffer { name="Captured bloom reference validation" };
            var previous=RenderTexture.active;
            var expected=EndfieldCaptureAssets.Texture("bloom");
            var colors=expected.GetPixels();
            var readback=new Texture2D(expected.width,expected.height,TextureFormat.RGBAFloat,false,true);
            double best=double.PositiveInfinity;
            try
            {
                report.AppendLine($"Bloom support: compute={SystemInfo.supportsComputeShaders}, available={bloom.IsSupported}, source={source.descriptor.graphicsFormat}/{source.descriptor.dimension}/{source.descriptor.volumeDepth}/{source.descriptor.msaaSamples}");
                var fmt=UnityEngine.Experimental.Rendering.GraphicsFormat.B10G11R11_UFloatPack32;
                report.AppendLine($"R11 usage: loadStore={SystemInfo.IsFormatSupported(fmt,UnityEngine.Experimental.Rendering.FormatUsage.LoadStore)}, sample={SystemInfo.IsFormatSupported(fmt,UnityEngine.Experimental.Rendering.FormatUsage.Sample)}, linear={SystemInfo.IsFormatSupported(fmt,UnityEngine.Experimental.Rendering.FormatUsage.Linear)}");
                if(!bloom.Setup(source.descriptor))throw new InvalidOperationException("Captured bloom UAV format unsupported.");
                foreach(bool flip in new[]{false,true})
                {
                    Graphics.Blit(input,source,flip?new Vector2(1,-1):Vector2.one,flip?new Vector2(0,1):Vector2.zero);
                    command.Clear();var result=bloom.Render(command,handle,1);
                    Graphics.ExecuteCommandBuffer(command);
                    if(flip)
                    {
                        int[] downIds={59945,58920,58914,58908,58902,58896,58890,58884,58878};
                        int[] upIds={58923,58917,58911,58905,58899,58893,58887,58881};
                        for(int i=0;i<9;i++)CompareBloomLevel(bloom.GetDownsample(i).rt,1121+i*4,downIds[i],report);
                        for(int i=7;i>=0;i--)CompareBloomLevel(bloom.GetUpsample(i).rt,1185-i*4,upIds[i],report);
                    }
                    RenderTexture.active=result.rt;
                    readback.ReadPixels(new Rect(0,0,expected.width,expected.height),0,0);readback.Apply();
                    var actual=readback.GetPixels();
                    foreach(bool referenceFlip in new[]{false,true})
                    {
                        double sum=0,energy=0;float maximum=0;
                        for(int y=0;y<expected.height;y++)
                        for(int x=0;x<expected.width;x++)
                        {
                            Color a=actual[y*expected.width+x],b=colors[(referenceFlip?expected.height-1-y:y)*expected.width+x];
                            for(int c=0;c<3;c++)
                            {
                                if(float.IsNaN(a[c]) || float.IsInfinity(a[c]))throw new InvalidOperationException("Nonfinite bloom.");
                                float difference=Mathf.Abs(a[c]-b[c]);sum+=difference;energy+=Mathf.Abs(b[c]);maximum=Mathf.Max(maximum,difference);
                            }
                        }
                        double relative=sum/Math.Max(energy,1e-12);
                        report.AppendLine($"Dynamic bloom inputFlip={flip} referenceFlip={referenceFlip}: MAE={sum/actual.Length/3:F8} relativeL1={relative:F8} max={maximum:F6}");
                        best=Math.Min(best,relative);
                    }
                }
                // This tests the generator, independently of post grading. A
                // failure must not be hidden by a visually forgiving LUT.
                if(best>.025)throw new InvalidOperationException("Dynamic bloom does not yet match the captured generator.");
                report.AppendLine($"PASS: dynamic 17-dispatch bloom relative L1={best:F8}");
            }
            finally
            {
                RenderTexture.active=previous;command.Release();bloom.Dispose();handle.Release();
                // RTHandle owns and destroys this RenderTexture when released.
                Object.DestroyImmediate(readback);
            }
        }

        static void CompareBloomLevel(RenderTexture actual,int eventId,int resource,StringBuilder report)
        {
            var reference=EndfieldCaptureAssets.Texture($"bloom-{eventId}-{resource}");
            if(reference==null)return;
            if(reference.width!=actual.width || reference.height!=actual.height)throw new InvalidOperationException("Bloom level dimensions mismatch.");
            var pixels=new Texture2D(actual.width,actual.height,TextureFormat.RGBAFloat,false,true);
            var previous=RenderTexture.active;
            try
            {
                RenderTexture.active=actual;pixels.ReadPixels(new Rect(0,0,actual.width,actual.height),0,0);pixels.Apply();
                var a=pixels.GetPixels();var b=reference.GetPixels();
                double diff=0,signed=0,energy=0;int positive=0,negative=0;
                for(int y=0;y<actual.height;y++)for(int x=0;x<actual.width;x++)
                    for(int c=0;c<3;c++)
                    {
                        float delta=a[y*actual.width+x][c]-b[(actual.height-1-y)*actual.width+x][c];
                        diff+=Math.Abs(delta);signed+=delta;energy+=b[(actual.height-1-y)*actual.width+x][c];
                        if(delta>1e-7)positive++;else if(delta< -1e-7)negative++;
                    }
                report.AppendLine($"Bloom event={eventId} {actual.width}x{actual.height} relativeL1={diff/Math.Max(energy,1e-12):F8} signedMean={signed/a.Length/3:F8} positive={positive} negative={negative}");
            }
            finally{RenderTexture.active=previous;Object.DestroyImmediate(pixels);}
        }

        static void ValidateCube(Cubemap cube, StringBuilder report)
        {
            var shader=Shader.Find("Hidden/Endfield/CaptureCubeProbe");
            if(shader==null || !shader.isSupported)throw new InvalidOperationException("Cube probe unavailable.");
            var material=new Material(shader);material.SetTexture("_Cube",cube);
            var target=new RenderTexture(16,16,0,RenderTextureFormat.ARGBFloat,RenderTextureReadWrite.Linear);
            var readback=new Texture2D(16,16,TextureFormat.RGBAFloat,false,true);
            var previous=RenderTexture.active;
            try
            {
                int failures=0;
                report.AppendLine($"Cube graphics format={cube.graphicsFormat}, EXR={EndfieldCaptureAssets.Texture("character-environment-face0").graphicsFormat}");
                for(int face=0;face<6;face++)
                {
                    material.SetFloat("_Mode",0);material.SetFloat("_Face",face);Graphics.Blit(Texture2D.blackTexture,target,material);
                    RenderTexture.active=target;readback.ReadPixels(new Rect(0,0,16,16),0,0);readback.Apply();
                    var reference=EndfieldCaptureAssets.Texture("character-environment-face"+face);
                    var actual=readback.GetPixels();
                    material.SetTexture("_Reference2D",reference);material.SetFloat("_Mode",1);
                    float[] error=new float[2];
                    for(int flip=0;flip<2;flip++)
                    {
                        material.SetFloat("_ReferenceFlip",flip);Graphics.Blit(Texture2D.blackTexture,target,material);
                        RenderTexture.active=target;readback.ReadPixels(new Rect(0,0,16,16),0,0);readback.Apply();
                        var expected=readback.GetPixels();
                        for(int i=0;i<actual.Length;i++)
                        {
                            error[flip]+=Mathf.Abs(actual[i].r-expected[i].r)+Mathf.Abs(actual[i].g-expected[i].g)+Mathf.Abs(actual[i].b-expected[i].b);
                        }
                    }
                    float best=Mathf.Min(error[0],error[1])/(16*16*3);
                    report.AppendLine($"Cube face={face} compareEXR MAE={best:G7} referenceFlipY={error[1]<error[0]}");
                    report.AppendLine($"  center CubeGPU={actual[136].ToString("F6")} EXRGPU={readback.GetPixel(8,8).ToString("F6")}");
                    if(float.IsNaN(best) || best>.005f)failures++;
                }
                if(failures!=0)throw new InvalidOperationException($"Cube face/order/sample mismatch: {failures}/6.");
                report.AppendLine("PASS: all six BC6H cube faces reproduce captured face samples.");
            }
            finally
            {
                RenderTexture.active=previous;target.Release();Object.DestroyImmediate(target);
                Object.DestroyImmediate(readback);Object.DestroyImmediate(material);
            }
        }
    }
}
