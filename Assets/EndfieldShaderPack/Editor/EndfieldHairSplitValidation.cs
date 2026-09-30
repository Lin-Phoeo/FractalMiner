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
    // Isolated synthetic GPU probes. No scene load/save, material asset edits,
    // screenshot fitting, or write to earlier validation reports.
    public static class EndfieldHairSplitValidation
    {
        struct Case
        {
            public string name;
            public Vector4 packed, tangent;
            public Vector3 geometry;
            public float diffuseScale, specularScale, backface;
            public Case(string n, Vector4 p, Vector3 g, Vector4 t, float d = 1, float s = 1, float b = 1)
            { name = n; packed = p; geometry = g; tangent = t; diffuseScale = d; specularScale = s; backface = b; }
        }

        // Independently evaluated double algebra from PS22257. This does not
        // call the HLSL helper and deliberately retains raw raster N/T lengths.
        static double[] Expected(Case c, bool specular)
        {
            double x = (specular ? c.packed.z : c.packed.x) * 2.0 - 1.0;
            double y = (specular ? c.packed.w : c.packed.y) * 2.0 - 1.0;
            double z = Math.Max(1e-16, Math.Sqrt(1.0 - Math.Min(1.0, Math.Max(0.0, x*x+y*y))));
            double scale = specular ? c.specularScale : c.diffuseScale;
            double[] n = { c.geometry.x, c.geometry.y, c.geometry.z };
            double[] t = { c.tangent.x, c.tangent.y, c.tangent.z };
            double[] b = { (n[1]*t[2]-n[2]*t[1])*c.tangent.w,
                           (n[2]*t[0]-n[0]*t[2])*c.tangent.w,
                           (n[0]*t[1]-n[1]*t[0])*c.tangent.w };
            double[] v = new double[3];
            for (int i=0; i<3; i++) v[i] = x*scale*t[i]+y*scale*b[i]+z*n[i];
            double length2 = v.Sum(a => a*a);
            double inverse = 1.0/Math.Sqrt(specular ? length2 : Math.Max(length2, 1.175494351e-38));
            for (int i=0; i<3; i++) v[i] *= inverse * (specular ? 1 : c.backface);
            return v;
        }

        static void CheckCompiled(Shader shader)
        {
            if (shader == null || !shader.isSupported) throw new Exception("Missing/unsupported shader");
            var errors = ShaderUtil.GetShaderMessages(shader).Where(m => m.severity == UnityEditor.Rendering.ShaderCompilerMessageSeverity.Error).ToArray();
            if (errors.Length != 0) throw new Exception(string.Join("\n", errors.Select(e=>e.message)));
        }

        static Texture2D Constant(Color value, List<Object> owned)
        {
            var tex = new Texture2D(2,2,TextureFormat.RGBAFloat,false,true);
            tex.SetPixels(new[] {value,value,value,value}); tex.Apply(); owned.Add(tex); return tex;
        }

        static Color DrawProduction(Material material, Mesh mesh, RenderTexture rt, Texture2D readback)
        {
            var command = new CommandBuffer { name = "Hair source branch synthetic probe" };
            try
            {
                command.SetRenderTarget(rt);
                command.ClearRenderTarget(true,true,Color.clear);
                command.SetViewProjectionMatrices(Matrix4x4.Translate(new Vector3(0,0,-2)),
                    GL.GetGPUProjectionMatrix(Matrix4x4.Ortho(-.5f,.5f,-.5f,.5f,.1f,10),true));
                command.DrawMesh(mesh,Matrix4x4.identity,material,0,0);
                Graphics.ExecuteCommandBuffer(command);
                RenderTexture.active=rt;
                readback.ReadPixels(new Rect(0,0,4,4),0,0); readback.Apply();
                Color value = readback.GetPixel(2,2);
                if (value.a < .9f || !float.IsFinite(value.r) || !float.IsFinite(value.g) || !float.IsFinite(value.b))
                    throw new Exception("Production draw did not produce a finite opaque fragment: "+value);
                return value;
            }
            finally { command.Release(); }
        }

        static float Difference(Color a, Color b) => Mathf.Max(Mathf.Abs(a.r-b.r),Mathf.Abs(a.g-b.g),Mathf.Abs(a.b-b.b));

        static void ProbeProduction(Material material, RenderTexture rt, Texture2D readback, List<string> lines)
        {
            var owned = new List<Object>();
            string[] vectors = Enumerable.Range(0,16).Select(i=>"_CharacterParams"+i).Concat(new[] {
                "_EnvironmentGlobalParams0", "_ExposureWithMiscParams", "_CharacterLightDir", "_CharacterLightColor", "_WorldSpaceCameraPos" }).ToArray();
            string[] floats = { "_EndfieldOfficialFrameEnabled", "_EndfieldOfficialShadingEnabled", "_EndfieldCapturedLightIntensity",
                "_EndfieldCapturedCubemapAvailable", "_EndfieldCapturedGlobalMipBias", "_EndfieldLabelMode", "_EndfieldDebugValueMode" };
            var savedVectors = vectors.Select(Shader.GetGlobalVector).ToArray();
            var savedFloats = floats.Select(Shader.GetGlobalFloat).ToArray();
            try
            {
                Endfield.EndfieldOfficialFrameGlobals.ApplyGlobals();
                Shader.SetGlobalFloat("_EndfieldLabelMode",0);
                Shader.SetGlobalFloat("_EndfieldDebugValueMode",0);
                if (Shader.GetGlobalFloat("_EndfieldCapturedGlobalMipBias") != -1) throw new Exception("Capture bias binding failed");
                Shader.SetGlobalVector("_CharacterLightDir",new Vector4(0,0,1,1));
                Shader.SetGlobalVector("_CharacterLightColor",Vector4.one);
                Shader.SetGlobalVector("_WorldSpaceCameraPos",new Vector4(0,0,2,1));
                Shader.SetGlobalVector("_CharacterParams11",new Vector4(0,0,1,0));
                Shader.SetGlobalVector("_CharacterParams12",new Vector4(1,1,1,0)); // no backlight rim
                material.SetFloat("_MaterialFamily",2);
                material.SetFloat("_UseSpecBumpMap",1); material.SetFloat("_UseBumpMap",1);
                material.SetFloat("_BumpScale",1); material.SetFloat("_SpecBumpScale",1);
                material.SetFloat("_Cull",0); material.SetFloat("_LineIntensity",0);
                material.SetFloat("_AnisotropyValue",.5f); material.SetFloat("_AnisotropyDirX",0);
                material.SetFloat("_AnisotropyIntensity",1); material.SetFloat("_AnisotropyEdgeFade",2);
                material.SetColor("_BaseColor",Color.white);
                material.SetTexture("_BaseMap",Constant(new Color(.2f,.3f,.4f,1),owned));
                material.SetTexture("_MetallicGlossMap",Constant(new Color(0,1,1,0),owned));
                material.SetTexture("_DiffRampMap",Constant(Color.white,owned));
                material.SetTexture("_SpecRampMap",Constant(Color.white,owned));
                var hnA = Constant(new Color(.5f,.75f,.5f,.5f),owned);
                var hnB = Constant(new Color(.5f,.75f,.95f,.5f),owned); // only BA changes
                var hnC = Constant(new Color(.5f,.25f,.5f,.5f),owned); // only RG changes
                var mesh = new Mesh { name = "SyntheticHairQuad" }; owned.Add(mesh);
                mesh.vertices = new[] {new Vector3(-.5f,-.5f,0),new Vector3(.5f,-.5f,0),new Vector3(.5f,.5f,0),new Vector3(-.5f,.5f,0)};
                mesh.normals = Enumerable.Repeat(Vector3.forward,4).ToArray();
                mesh.tangents = Enumerable.Repeat(new Vector4(1,0,0,1),4).ToArray();
                mesh.uv = new[] {Vector2.zero,Vector2.right,Vector2.one,Vector2.up};
                mesh.triangles = new[] {0,1,2,0,2,3};
                Shader.SetGlobalVector("_CharacterParams13",Vector4.zero);
                material.SetTexture("_SplitNormalMap",hnA); Color a = DrawProduction(material,mesh,rt,readback);
                material.SetTexture("_SplitNormalMap",hnB); Color b = DrawProduction(material,mesh,rt,readback);
                float baDiffuse = Difference(a,b);
                if (baDiffuse > 2e-5f) throw new Exception("BA contaminated diffuse-only output "+baDiffuse);
                material.SetTexture("_SplitNormalMap",hnC); Color c = DrawProduction(material,mesh,rt,readback);
                float rgDiffuse = Difference(a,c);
                if (rgDiffuse < 1e-3f) throw new Exception("RG not used by production diffuse "+rgDiffuse+" A="+a+" C="+c);
                Shader.SetGlobalVector("_CharacterParams13",new Vector4(0,0,0,1));
                material.SetTexture("_SplitNormalMap",hnA); a = DrawProduction(material,mesh,rt,readback);
                material.SetTexture("_SplitNormalMap",hnB); b = DrawProduction(material,mesh,rt,readback);
                float baSpecular = Difference(a,b);
                if (baSpecular < 1e-3f) throw new Exception("BA not used by production specular "+baSpecular);
                lines.Add("Production PASS BA-no-diffuse="+baDiffuse+" RG-diffuse-response="+rgDiffuse+" BA-specular-response="+baSpecular);
                lines.Add("Captured bias binding PASS -1; synthetic textures have no mip chain (LOD state NOT tested)");
            }
            finally
            {
                for (int i=0;i<vectors.Length;i++) Shader.SetGlobalVector(vectors[i],savedVectors[i]);
                for (int i=0;i<floats.Length;i++) Shader.SetGlobalFloat(floats[i],savedFloats[i]);
                foreach (var obj in owned) Object.DestroyImmediate(obj);
            }
        }

        public static void RunBatch()
        {
            if (!Application.isBatchMode) throw new Exception("Use a separate batch editor; do not alter an interactive GPU context");
            string output = Environment.GetEnvironmentVariable("ENDFIELD_HAIR_PROBE_REPORT");
            if (string.IsNullOrEmpty(output) || File.Exists(output))
                throw new Exception("ENDFIELD_HAIR_PROBE_REPORT must name a fresh output file");
            var lines = new List<string> { "Synthetic source-algebra probes; not official-image equality.",
                "GPU="+SystemInfo.graphicsDeviceType+" / "+SystemInfo.graphicsDeviceName };
            var cases = new[] {
                new Case("flat", new Vector4(.5f,.5f,.5f,.5f), Vector3.forward, new Vector4(1,0,0,1)),
                new Case("RG-vs-BA", new Vector4(.8f,.3f,.2f,.7f), Vector3.forward, new Vector4(1,0,0,1)),
                new Case("backface", new Vector4(.8f,.3f,.2f,.7f), Vector3.forward, new Vector4(1,0,0,1), b:-1),
                new Case("raw-interpolation", new Vector4(.7f,.8f,.3f,.6f), new Vector3(.1f,.2f,.7f), new Vector4(.8f,.15f,.2f,-1), .4f,1.7f),
                new Case("XY-outside-disk", new Vector4(1,1,0,1), Vector3.forward, new Vector4(1,0,0,1), .8f,.3f),
                new Case("scale-after-Z", new Vector4(.9f,.6f,.6f,.9f), Vector3.forward, new Vector4(1,0,0,-1), .15f,2.3f),
                new Case("zero-XY-scale", new Vector4(.7f,.6f,.3f,.4f), Vector3.forward, new Vector4(1,0,0,1), 0,0),
                new Case("negative-scale", new Vector4(.7f,.6f,.3f,.4f), Vector3.forward, new Vector4(1,0,0,1), -1,-.5f),
                new Case("diffuse-zero-vector", new Vector4(.5f,.5f,.8f,.5f), Vector3.zero, new Vector4(1,0,0,1))
            };
            Material probe = null, character = null;
            RenderTexture rt = null;
            Texture2D readback = null;
            Scene previewScene = default;
            GameObject cameraObject = null;
            var prior = RenderTexture.active;
            try
            {
                if (SystemInfo.graphicsDeviceType == GraphicsDeviceType.Null) throw new Exception("Real GPU required");
                Shader probeShader = AssetDatabase.LoadAssetAtPath<Shader>("Assets/EndfieldShaderPack/Editor/EndfieldHairNormalProbe.shader");
                CheckCompiled(probeShader);
                probe = new Material(probeShader);
                rt = new RenderTexture(4,4,0,RenderTextureFormat.ARGBFloat,RenderTextureReadWrite.Linear);
                rt.Create();
                readback = new Texture2D(4,4,TextureFormat.RGBAFloat,false,true);
                // Batch startup has not yet rendered a camera: initialize the
                // configured URP before DrawMesh selects its pipeline-tagged subshader.
                previewScene = EditorSceneManager.NewPreviewScene();
                cameraObject = new GameObject("HairProbePipelineInit");
                SceneManager.MoveGameObjectToScene(cameraObject,previewScene);
                var initCamera = cameraObject.AddComponent<Camera>();
                initCamera.targetTexture=rt; initCamera.enabled=false; initCamera.Render();
                lines.Add("Pipeline="+(RenderPipelineManager.currentPipeline?.GetType().FullName ?? "null"));
                if (RenderPipelineManager.currentPipeline == null) throw new Exception("Configured URP did not initialize");
                double maxError = 0;
                foreach (var c in cases)
                {
                    probe.SetVector("_ProbePacked",c.packed);
                    probe.SetVector("_ProbeGeometry",c.geometry);
                    probe.SetVector("_ProbeTangent",c.tangent);
                    for (int mode=0; mode<2; mode++)
                    {
                        probe.SetVector("_ProbeScales",new Vector4(c.diffuseScale,c.specularScale,c.backface,mode));
                        Graphics.Blit(Texture2D.blackTexture,rt,probe,0);
                        RenderTexture.active=rt;
                        readback.ReadPixels(new Rect(0,0,4,4),0,0); readback.Apply();
                        var actual = readback.GetPixel(2,2);
                        var expected = Expected(c,mode==1);
                        double error = Math.Max(Math.Abs(actual.r-expected[0]),Math.Max(Math.Abs(actual.g-expected[1]),Math.Abs(actual.b-expected[2])));
                        if (double.IsNaN(error) || double.IsInfinity(error) || error > 2e-5)
                            throw new Exception(c.name+" mode="+mode+" error="+error+" actual="+actual);
                        maxError = Math.Max(maxError,error);
                        lines.Add(c.name+" "+(mode==0?"diffuse":"specular")+" PASS error="+error.ToString("R",System.Globalization.CultureInfo.InvariantCulture));
                    }
                }
                CheckCompiled(probeShader);
                // Compile actual production passes, not just the probe kernel.
                Shader characterShader = Shader.Find("Endfield/CharacterLit");
                CheckCompiled(characterShader);
                character = new Material(characterShader);
                for (int pass=0; pass<character.passCount; pass++)
                    if (!character.SetPass(pass)) throw new Exception("CharacterLit SetPass failed "+pass);
                ProbeProduction(character,rt,readback,lines);
                CheckCompiled(characterShader);
                lines.Add("CharacterLit PASS passes="+character.passCount);
                lines.Add("RESULT PASS probes="+(cases.Length*2)+" maxError="+maxError.ToString("R",System.Globalization.CultureInfo.InvariantCulture));
                using (var stream = new FileStream(output,FileMode.CreateNew,FileAccess.Write))
                using (var writer = new StreamWriter(stream)) foreach (var line in lines) writer.WriteLine(line);
                Debug.Log("Hair split normal probe PASS: "+output);
            }
            finally
            {
                RenderTexture.active=prior;
                if (probe != null) Object.DestroyImmediate(probe);
                if (character != null) Object.DestroyImmediate(character);
                if (rt != null) { rt.Release(); Object.DestroyImmediate(rt); }
                if (readback != null) Object.DestroyImmediate(readback);
                if (cameraObject != null) Object.DestroyImmediate(cameraObject);
                if (previewScene.IsValid()) EditorSceneManager.ClosePreviewScene(previewScene);
            }
        }
    }
}
