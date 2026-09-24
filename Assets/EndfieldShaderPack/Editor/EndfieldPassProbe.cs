using System;
using System.IO;
using System.Reflection;
using System.Text;
using UnityEditor;
using UnityEditor.Build;
using UnityEngine;

namespace EndfieldShaderPack
{
    /// Read-only diagnostic: determines why Material.passCount reports 1 and
    /// Material.FindPass returns -1 for every pass of every shader in batchmode
    /// Editor runs (see Logs/character-shadow-live.txt, pass probe section),
    /// including a stock URP/Lit control. The live gate cannot tell whether the
    /// EndfieldCharacterShadowAtlas/GBuffer passes actually exist in the imported
    /// shader; this probe enumerates the pass names the runtime can see, cold and
    /// after one real camera render, and dumps the ShaderUtil API surface so the
    /// next round can use an editor-only pass query if the runtime one is broken.
    /// Nothing is saved; the generated scene is opened without modification.
    public static class EndfieldPassProbe
    {
        const string ReportPath = "Logs/passprobe.txt";
        const string GeneratedScenePath = "Assets/Scenes/Typhoeus_CapturedPipeline.unity";

        [MenuItem("Endfield/Pass Probe", false, 99)]
        public static void Run()
        {
            var report = new StringBuilder();
            report.AppendLine("Endfield pass visibility probe");
            report.AppendLine("utc: " + DateTime.UtcNow.ToString("o"));
            report.AppendLine("graphicsDevice=" + SystemInfo.graphicsDeviceName +
                              " type=" + SystemInfo.graphicsDeviceType +
                              " version=" + SystemInfo.graphicsDeviceVersion +
                              " shaderLevel=" + SystemInfo.graphicsShaderLevel +
                              " reversedZ=" + SystemInfo.usesReversedZBuffer +
                              " batchmode=" + Application.isBatchMode +
                              " colorSpace=" + QualitySettings.activeColorSpace);
            report.AppendLine("currentRenderPipeline=" +
                              (GraphicsSettings.currentRenderPipeline != null
                                  ? GraphicsSettings.currentRenderPipeline.name : "none"));

            report.AppendLine();
            report.AppendLine("=== phase A: cold (no render yet) ===");
            ProbeShaders(report, "cold");

            report.AppendLine();
            report.AppendLine("=== ShaderUtil API surface ===");
            foreach (var method in typeof(ShaderUtil).GetMethods(BindingFlags.Public |
                                                                 BindingFlags.NonPublic |
                                                                 BindingFlags.Static |
                                                                 BindingFlags.Instance |
                                                                 BindingFlags.DeclaredOnly))
                report.AppendLine("  " + method);

            report.AppendLine();
            report.AppendLine("=== IPreprocessShaders / IPreprocessBuildWithReport implementations ===");
            bool foundStripper = false;
            foreach (var assembly in AppDomain.CurrentDomain.GetAssemblies())
            {
                Type[] types;
                try { types = assembly.GetTypes(); }
                catch { continue; }
                foreach (var type in types)
                {
                    if (type.IsInterface || type.IsAbstract) continue;
                    if (typeof(IPreprocessShaders).IsAssignableFrom(type) ||
                        typeof(IPreprocessBuildWithReport).IsAssignableFrom(type))
                    {
                        foundStripper = true;
                        report.AppendLine("  " + type.FullName + "  [" + assembly.GetName().Name + "]");
                    }
                }
            }
            if (!foundStripper) report.AppendLine("  (none)");

            report.AppendLine();
            report.AppendLine("=== phase B: render one frame from the generated scene ===");
            try
            {
                if (!File.Exists(GeneratedScenePath))
                {
                    report.AppendLine("no generated scene at " + GeneratedScenePath);
                }
                else
                {
                    UnityEditor.SceneManagement.EditorSceneManager.OpenScene(GeneratedScenePath,
                        UnityEditor.SceneManagement.OpenSceneMode.Single);
                    var camera = Camera.main;
                    if (camera == null)
                    {
                        report.AppendLine("scene has no main camera");
                    }
                    else
                    {
                        var target = new RenderTexture(256, 256, 24);
                        camera.targetTexture = target;
                        camera.Render();
                        camera.targetTexture = null;
                        target.Release();
                        UnityEngine.Object.DestroyImmediate(target);
                        report.AppendLine("rendered one 256x256 frame with camera '" + camera.name + "'");
                    }
                }
            }
            catch (Exception exception)
            {
                report.AppendLine("phase B aborted: " + exception);
            }

            report.AppendLine();
            report.AppendLine("=== phase C: warm (after one render) ===");
            ProbeShaders(report, "warm");
            ProbeSceneMaterials(report);

            report.AppendLine();
            report.AppendLine("probe complete");
            Directory.CreateDirectory("Logs");
            File.WriteAllText(ReportPath, report.ToString());
            Debug.Log(report.ToString());
        }

        static void ProbeShaders(StringBuilder report, string phase)
        {
            foreach (var shaderName in new[]
                     {
                         "Endfield/CharacterLit",
                         "Universal Render Pipeline/Lit"
                     })
            {
                var shader = Shader.Find(shaderName);
                if (shader == null)
                {
                    report.AppendLine(phase + " " + shaderName + ": Shader.Find -> null");
                    continue;
                }
                var loaded = AssetDatabase.LoadAssetAtPath<Shader>(
                    AssetDatabase.GetAssetPath(shader));
                var material = new Material(shader);
                report.AppendLine(phase + " " + shaderName +
                                  ": passCount(shader)=" + shader.passCount +
                                  " passCount(material)=" + material.passCount +
                                  " isSupported=" + shader.isSupported +
                                  " instanceID=" + shader.GetInstanceID() +
                                  " loadEq=" + ReferenceEquals(loaded, shader));
                int count = Mathf.Max(shader.passCount, material.passCount, 1);
                for (int i = 0; i < count && i < 16; i++)
                    report.AppendLine("  pass[" + i + "] name='" + SafeGetPassName(material, i) + "'");
                foreach (var pass in new[]
                         {
                             "UniversalForward", "ForwardLit", "ShadowCaster", "DepthOnly",
                             "Outline", "SRPDefaultUnlit",
                             "EndfieldCharacterShadowAtlas", "EndfieldCharacterShadowGBuffer"
                         })
                    report.AppendLine("  FindPass('" + pass + "')=" + material.FindPass(pass));
                var messages = ShaderUtil.GetShaderMessages(shader);
                report.AppendLine("  shaderMessages=" + messages.Length);
                foreach (var message in messages)
                    report.AppendLine("    [" + message.severity + "] " + message.message +
                                      " @" + message.file + ":" + message.line);
                UnityEngine.Object.DestroyImmediate(material);
            }
        }

        static void ProbeSceneMaterials(StringBuilder report)
        {
            report.AppendLine("scene materials using Endfield/CharacterLit (warm):");
            int dumped = 0;
            foreach (var renderer in UnityEngine.Object.FindObjectsOfType<Renderer>())
            {
                foreach (var material in renderer.sharedMaterials)
                {
                    if (material == null || material.shader == null) continue;
                    if (material.shader.name != "Endfield/CharacterLit") continue;
                    report.AppendLine("  " + renderer.name + " -> " + material.name +
                                      " passCount=" + material.passCount +
                                      " atlas=" + material.FindPass("EndfieldCharacterShadowAtlas") +
                                      " gbuf=" + material.FindPass("EndfieldCharacterShadowGBuffer") +
                                      " fwd=" + material.FindPass("UniversalForward") +
                                      " outline=" + material.FindPass("Outline"));
                    for (int i = 0; i < material.passCount && i < 16; i++)
                        report.AppendLine("    pass[" + i + "]='" + SafeGetPassName(material, i) + "'");
                    dumped++;
                    break;
                }
                if (dumped >= 3) break;
            }
            if (dumped == 0) report.AppendLine("  (no scene material uses Endfield/CharacterLit)");
        }

        static string SafeGetPassName(Material material, int index)
        {
            try { return material.GetPassName(index); }
            catch (Exception exception) { return "<error: " + exception.Message + ">"; }
        }
    }
}
