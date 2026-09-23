using System;
using System.IO;
using System.Linq;
using System.Text;
using UnityEditor;
using UnityEditor.SceneManagement;
using UnityEngine;
using Object = UnityEngine.Object;

namespace EndfieldShaderPack
{
    // Numerical GPU tests with constant textures, independent CPU reference algebra.
    public static class EndfieldOfficialShadingValidation
    {
        public static void RunAll()
        {
            RunNumerical();
            EndfieldSkinShadingValidation.RunNumerical();
            TyphoeusRecoveryValidation.RunAll();
        }

        static readonly Vector3 Luma = new Vector3(.2126729f, .7151522f, .0721750f);
        static Vector3 Sat(Vector3 c, float s) => Vector3.LerpUnclamped(Vector3.one * Vector3.Dot(c, Luma), c, s);
        static Vector3 Mul(Vector3 a, Vector3 b) => Vector3.Scale(a, b);
        static Texture2D Constant(Color color)
        {
            var t = new Texture2D(2, 2, TextureFormat.RGBAFloat, false, true);
            t.SetPixels(new[] {color,color,color,color}); t.Apply(); return t;
        }

        // b125: _2174.._2296, b471: _2063.._2179. N=(0,0,1), no spec,
        // white RGB ramp with variable alpha, selfShadow=directionalShadow=1.
        static Vector3 Expected(float rampAlpha, Vector3 matcap = default)
        {
            var albedo = new Vector3(.2f,.3f,.4f);
            Vector3 diffuse = albedo * .96f;
            Vector3 deep = Sat(albedo * .55f, 1.1f) * (.96f * .65f);
            Vector3 baseSel = Vector3.Lerp(Vector3.Lerp(Sat(deep*.65f,1.2f), deep, Mathf.Clamp01(2*rampAlpha)), diffuse, rampAlpha);
            Vector3 ambient = .725f * Vector3.Lerp(new Vector3(.8490771055f,.8957685828f,1.1509230137f), Vector3.one, rampAlpha);
            Vector3 lightTerm = Vector3.one * 1.6243867874f + ambient * .287722f;
            Vector3 color = Mul(baseSel, lightTerm) + Mul(matcap, lightTerm)
                * ((rampAlpha * .5f + .5f) * Mathf.Lerp(.65f, 1, rampAlpha));
            float boost = Mathf.Clamp(Vector3.Dot(color,Luma)-.5f,0,.5f);
            return Sat(color,1+boost*boost);
        }

        public static void RunNumerical()
        {
            if (!Application.isBatchMode && !EditorSceneManager.SaveCurrentModifiedScenesIfUserWantsTo()) return;
            EditorSceneManager.NewScene(NewSceneSetup.EmptyScene, NewSceneMode.Single);
            Endfield.EndfieldOfficialFrameGlobals.ApplyGlobals();
            Shader.SetGlobalFloat("_EndfieldOfficialShadingEnabled", 1);
            Shader.SetGlobalVector("_CharacterParams13", Vector4.zero);
            Shader.SetGlobalVector("_CharacterParams6", Vector4.zero);
            Shader.SetGlobalVector("_CharacterLightDir", new Vector4(0,0,1,1));
            Shader.SetGlobalVector("_CharacterLightColor", Vector4.one);
            Shader.SetGlobalVector("_CharacterAmbient", new Vector4(.45f,.5f,.6f,1));
            var camera = new GameObject("NumericalCamera").AddComponent<Camera>();
            camera.transform.SetPositionAndRotation(new Vector3(0,0,2), Quaternion.Euler(0,180,0));
            camera.orthographic = true; camera.orthographicSize = .5f; camera.nearClipPlane=.01f; camera.farClipPlane=4;
            camera.clearFlags=CameraClearFlags.SolidColor; camera.backgroundColor=Color.clear;
            var quad = GameObject.CreatePrimitive(PrimitiveType.Quad);
            var mat = new Material(Shader.Find("Endfield/CharacterLit"));
            quad.GetComponent<Renderer>().sharedMaterial=mat;
            mat.SetFloat("_EnableOutline",0); mat.SetFloat("_BackFaceNormalFlip",1); mat.SetFloat("_Cull",0);
            mat.SetFloat("_UseBumpMap",0); mat.SetFloat("_UseSpecBumpMap",0);
            mat.SetFloat("_UseMetallicGlossMap",1); mat.SetFloat("_UseDiffRampMap",1);
            mat.SetFloat("_UseShadowLutTex",0); mat.SetFloat("_ShadowColorBrightness",.55f); mat.SetFloat("_ShadowColorSaturation",1.1f);
            mat.SetFloat("_LineIntensity",0); mat.SetFloat("_Anisotropy",1);
            mat.SetColor("_BaseColor",Color.white);
            mat.SetColor("_EyeScatteringColor",Color.white); mat.SetColor("_EyeHighLightColor",Color.white);
            mat.SetColor("_MatcapColor",Color.clear);
            var baseMap=Constant(new Color(.2f,.3f,.4f,1));
            var packed=Constant(new Color(0,0,1,.5f));
            mat.SetTexture("_BaseMap",baseMap); mat.SetTexture("_MetallicGlossMap",packed);
            var rt = new RenderTexture(16,16,24,RenderTextureFormat.ARGBFloat,RenderTextureReadWrite.Linear);
            var readback = new Texture2D(16,16,TextureFormat.RGBAFloat,false,true);
            var prior=RenderTexture.active;
            var report=new StringBuilder(); int failures=0, cases=0;
            try
            {
                foreach (int family in new[] {2,0,3})
                foreach (float alpha in new[] {0f,.5f,1f})
                {
                    var ramp=Constant(new Color(1,1,1,alpha));
                    try
                    {
                        mat.SetFloat("_MaterialFamily",family); mat.SetTexture("_DiffRampMap",ramp);
                        cases++;
                        camera.targetTexture=rt; camera.Render(); RenderTexture.active=rt;
                        readback.ReadPixels(new Rect(0,0,16,16),0,0); readback.Apply();
                        Color p=readback.GetPixel(8,8);
                        Vector3 gpu=new Vector3(p.r,p.g,p.b), expected=Expected(alpha);
                        float error=(gpu-expected).magnitude;
                        report.AppendLine($"family={family} rampAlpha={alpha} gpu={gpu.ToString("F6")} expected={expected.ToString("F6")} error={error:G6}");
                        if (float.IsNaN(error) || error>.004f || p.a<.9f) failures++;
                    }
                    finally { Object.DestroyImmediate(ramp); }
                }
                // Nonzero alpha cross-blend: matcap.rgb*color.a + color.rgb*matcap.a.
                var eyeRamp=Constant(Color.white);
                var eyeMatcap=Constant(new Color(.02f,.03f,.04f,.4f));
                try
                {
                    mat.SetTexture("_DiffRampMap",eyeRamp); mat.SetTexture("_MatcapTex",eyeMatcap);
                    mat.SetColor("_MatcapColor",new Color(.1f,.2f,.3f,.5f));
                    camera.Render(); RenderTexture.active=rt;
                    readback.ReadPixels(new Rect(0,0,16,16),0,0); readback.Apply();
                    Color p=readback.GetPixel(8,8);
                    Vector3 gpu=new Vector3(p.r,p.g,p.b), expected=Expected(1,new Vector3(.05f,.095f,.14f));
                    float error=(gpu-expected).magnitude;
                    cases++;
                    report.AppendLine($"eye matcap cross-blend gpu={gpu.ToString("F6")} expected={expected.ToString("F6")} error={error:G6}");
                    if(float.IsNaN(error) || error>.004f || p.a<.9f) failures++;
                }
                finally { Object.DestroyImmediate(eyeRamp); Object.DestroyImmediate(eyeMatcap); }
                var emissionRamp=Constant(Color.white);
                var emission=Constant(new Color(.1f,.2f,.3f,1));
                try
                {
                    mat.SetFloat("_MaterialFamily",0); mat.SetFloat("_UseEmission",1);
                    mat.SetTexture("_DiffRampMap",emissionRamp); mat.SetTexture("_EmissionMap",emission);
                    mat.SetColor("_EmissionColor",new Color(.5f,.6f,.7f,1)); mat.SetFloat("_EmissionBrightness",2);
                    camera.Render(); RenderTexture.active=rt;
                    readback.ReadPixels(new Rect(0,0,16,16),0,0); readback.Apply();
                    Color p=readback.GetPixel(8,8);
                    // _EmissionColor is a ShaderLab Color property: Unity uploads
                    // its sRGB-authored value as linear RGB in this linear project.
                    Color linearEmission=new Color(.5f,.6f,.7f,1).linear;
                    Vector3 gpu=new Vector3(p.r,p.g,p.b), expected=Expected(1)
                        + Mul(new Vector3(.1f,.2f,.3f),new Vector3(linearEmission.r,linearEmission.g,linearEmission.b))*2;
                    float error=(gpu-expected).magnitude;
                    cases++;
                    report.AppendLine($"cloth emission gpu={gpu.ToString("F6")} expected={expected.ToString("F6")} error={error:G6}");
                    if(float.IsNaN(error) || error>.004f || p.a<.9f) failures++;
                }
                finally { Object.DestroyImmediate(emissionRamp); Object.DestroyImmediate(emission); }
                var shaderErrors=ShaderUtil.GetShaderMessages(mat.shader)
                    .Where(m=>m.severity==UnityEditor.Rendering.ShaderCompilerMessageSeverity.Error).ToArray();
                if(shaderErrors.Length!=0) throw new InvalidOperationException(string.Join("; ",shaderErrors.Select(m=>m.message)));
                Directory.CreateDirectory("Logs"); File.WriteAllText("Logs/official-shading-numerical.txt",report.ToString());
                Debug.Log(report.ToString());
                if(failures!=0) throw new InvalidOperationException($"Official lighting GPU reference: {failures}/{cases} failed");
                Debug.Log($"[OfficialShading] PASS: {cases} GPU/CPU reference cases");
            }
            finally
            {
                camera.targetTexture=null; RenderTexture.active=prior;
                rt.Release(); Object.DestroyImmediate(rt); Object.DestroyImmediate(readback);
                Object.DestroyImmediate(baseMap); Object.DestroyImmediate(packed); Object.DestroyImmediate(mat);
                Object.DestroyImmediate(quad); Object.DestroyImmediate(camera.gameObject);
            }
        }
    }
}
