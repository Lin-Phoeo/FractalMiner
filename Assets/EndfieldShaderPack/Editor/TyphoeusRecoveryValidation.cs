using System;
using System.Collections;
using System.Collections.Generic;
using System.IO;
using System.Reflection;
using System.Linq;
using System.Text;
using UnityEditor;
using UnityEditor.SceneManagement;
using UnityEngine;
using Object = UnityEngine.Object;

namespace EndfieldShaderPack
{
    // Regression checks derived from the capture and the mod's actual draw commands.
    public static class TyphoeusRecoveryValidation
    {
        const string ScenePath = "Assets/Scenes/CoralCoast_Repaired.unity";
        public static void RunAll()
        {
            BuildAndValidateScene();
            RenderOfficialBaseline();
            RenderSourceComparisons();
        }

        static void Require(bool condition, string message)
        {
            if (!condition) throw new InvalidOperationException(message);
        }

        // Same geometry, camera and post stack. Only the source-shading profile
        // switch changes, making regression previews reproducible across runs.
        public static void RenderSourceComparisons()
        {
            if (!Application.isBatchMode && !EditorSceneManager.SaveCurrentModifiedScenesIfUserWantsTo()) return;
            foreach (var item in new[] {
                ("Assets/Scenes/CoralCoast_Repaired.unity", "coral"),
                ("Assets/Scenes/Typhoeus_OfficialFrame_Recovered.unity", "official") })
            {
                EditorSceneManager.OpenScene(item.Item1, OpenSceneMode.Single);
                var profile = Object.FindObjectOfType<Endfield.EndfieldOfficialFrameGlobals>();
                Require(profile != null, "Missing frame profile: " + item.Item1);
                bool previous = profile.useSourceShading;
                try
                {
                    foreach (bool source in new[] { false, true })
                    {
                        profile.useSourceShading = source;
                        Endfield.EndfieldOfficialFrameGlobals.ApplyGlobals(source, profile.capturedEnvironment);
                        TyphoeusGeometryValidation.SaveImage(Camera.main,
                            item.Item2 + (source ? "-source-shading.png" : "-legacy-shading.png"), 1600, 1000);
                    }
                }
                finally
                {
                    profile.useSourceShading = previous;
                    Endfield.EndfieldOfficialFrameGlobals.ApplyGlobals(previous, profile.capturedEnvironment);
                }
            }
            Debug.Log("[Recovery] PASS: fixed-camera legacy/source comparison previews");
        }

        public static void ValidateContract()
        {
            var failures = new List<string>();
            var importer = typeof(CoralCoastMeshImporter);
            var draws = (IEnumerable)importer.GetField("DrawLists", BindingFlags.NonPublic | BindingFlags.Static).GetValue(null);
            var plans = new Dictionary<int, string>();
            foreach (var draw in draws)
            {
                int component = (int)draw.GetType().GetField("Item1").GetValue(draw);
                var subs = (Array)draw.GetType().GetField("Item2").GetValue(draw);
                object sub = subs.GetValue(0);
                plans[component] = (string)sub.GetType().GetField("tex").GetValue(sub);
                if (component == 8)
                {
                    var firstIndices = new HashSet<int>();
                    foreach (var item in subs) firstIndices.Add((int)item.GetType().GetField("first").GetValue(item));
                    if (new[] {10404, 54396, 117732}.Any(firstIndices.Contains) || !firstIndices.Contains(374718))
                        failures.Add("C8: mutually exclusive Main/Socks branches mixed; expected INI defaults Main=0, Socks=1");
                }
            }
            foreach (var item in new[] { (0, "horns"), (3, "face"), (6, "iris") })
                if (!plans.TryGetValue(item.Item1, out string actual) || actual != item.Item2)
                    failures.Add($"C{item.Item1}: expected {item.Item2}, got {actual ?? "missing"}");

            typeof(TyphoeusOfficialFrame).GetMethod("ApplyCharacterParams", BindingFlags.Static | BindingFlags.Public | BindingFlags.NonPublic).Invoke(null, null);
            var expected = new Dictionary<string, Vector4>
            {
                {"_CharacterParams0", new Vector4(1, 1, .65f, .9f)},
                {"_CharacterParams2", new Vector4(.849077f, .895769f, 1.150923f, 1)},
                {"_CharacterParams3", new Vector4(1.260404f, .739596f, .739596f, 1)},
                {"_CharacterParams4", new Vector4(1, .913683f, .911321f, 1)},
                {"_CharacterParams5", Vector4.one},
                {"_CharacterParams14", new Vector4(0, 0, 0, 1)},
                {"_CharacterParams15", new Vector4(0, .001f, -1, 0)},
                {"_EnvironmentGlobalParams0", new Vector4(.287722f, .287722f, 1, 0)}
            };
            foreach (var kv in expected)
            {
                Vector4 actual = Shader.GetGlobalVector(kv.Key);
                if ((actual - kv.Value).magnitude > 1e-5f)
                    failures.Add($"{kv.Key}: expected {kv.Value.ToString("G9")}, got {actual.ToString("G9")}");
            }
            Directory.CreateDirectory("Logs");
            File.WriteAllLines("Logs/recovery-contract.txt", failures.Count == 0 ? new[] {"PASS: component roles and captured globals"} : failures);
            if (failures.Count != 0) throw new InvalidOperationException(string.Join("\n", failures));
            Debug.Log("[Recovery] PASS: component roles and captured globals");
        }

        [MenuItem("Endfield/珊瑚海岸/⑧ 构建并验证修复展示场景", false, 207)]
        public static void BuildAndValidateScene()
        {
            if (!Application.isBatchMode && !EditorSceneManager.SaveCurrentModifiedScenesIfUserWantsTo()) return;
            ValidateContract();
            var report = new StringBuilder("Coral Coast recovery validation\n");
            var scene = EditorSceneManager.NewScene(NewSceneSetup.DefaultGameObjects, NewSceneMode.Single);
            var light = new GameObject("CharacterLight").AddComponent<Endfield.EndfieldCharacterLight>();
            light.transform.rotation = Quaternion.LookRotation(new Vector3(.1763192f, .5299193f, .8295162f));
            light.ApplyLight();
            light.gameObject.AddComponent<Endfield.EndfieldOfficialFrameGlobals>();
            CoralCoastMeshImporter.Import();
            var root = GameObject.Find(CoralCoastMeshImporter.RootName);
            var originalIds = root.GetComponentsInChildren<MeshFilter>().ToDictionary(f => f.name, f => AssetDatabase.AssetPathToGUID(AssetDatabase.GetAssetPath(f.sharedMesh)));
            CoralCoastMeshImporter.Import();
            root = GameObject.Find(CoralCoastMeshImporter.RootName);
            Require(root.transform.childCount == 9, "Expected 8 buffer components and original brow");
            Require(root.transform.Find("BakedFromOriginal") == null, "Duplicate face bake still exists");
            foreach (var f in root.GetComponentsInChildren<MeshFilter>())
            {
                var mesh = f.sharedMesh;
                Require(EditorUtility.IsPersistent(mesh), "Nonpersistent mesh: " + f.name);
                Require(originalIds[f.name] == AssetDatabase.AssetPathToGUID(AssetDatabase.GetAssetPath(mesh)), "Reimport changed GUID: " + f.name);
                var vertices = mesh.vertices; var normals = mesh.normals; var tangents = mesh.tangents;
                Require(normals.Length == vertices.Length && tangents.Length == vertices.Length, "Missing TBN: " + f.name);
                var used = new HashSet<int>(mesh.triangles);
                foreach (int i in used)
                {
                    Require(i >= 0 && i < vertices.Length, "Index out of bounds");
                    Require(!float.IsNaN(vertices[i].sqrMagnitude) && !float.IsInfinity(vertices[i].sqrMagnitude), "Nonfinite vertex");
                    float normalLength = normals[i].sqrMagnitude;
                    Vector3 tangent = new Vector3(tangents[i].x, tangents[i].y, tangents[i].z);
                    Require(Mathf.Abs(normalLength - 1) < .02f, "Bad normal: " + f.name);
                    Require(Mathf.Abs(tangent.sqrMagnitude - 1) < .02f && Mathf.Abs(Mathf.Abs(tangents[i].w) - 1) < .001f,
                        "Bad tangent xyz/w: " + f.name);
                }
                report.AppendLine($"{f.name}: vertices={mesh.vertexCount} triangles={mesh.triangles.Length / 3} bounds={mesh.bounds} guidStable=true");
            }
            var face = root.transform.Find("C3").GetComponent<MeshRenderer>();
            var iris = root.transform.Find("C6").GetComponent<MeshRenderer>();
            Require(face.bounds.Contains(iris.bounds.center), "Iris center is outside actual face bounds");
            Require(face.sharedMaterial.GetTexture("_BaseMap").name.Contains("6b12e27e"), "Face atlas mismatch");
            Require(face.sharedMaterial.GetFloat("_UseSDFLightmap") == 1, "SDF disabled");
            Require(face.sharedMaterial.GetTextureScale("_BaseMap") == new Vector2(1, -1), "Mod texture orientation missing");
            Require(face.sharedMaterial.GetTextureScale("_SDFLightmap") == Vector2.one, "Official SDF orientation changed");
            Camera.main.aspect = 1.6f;
            TyphoeusSceneSetup.FrameCamera(root);
            Camera.main.backgroundColor = new Color(.60f, .60f, .59f);
            EditorSceneManager.SaveScene(scene, ScenePath);
            EditorSceneManager.NewScene(NewSceneSetup.EmptyScene, NewSceneMode.Single);
            for (int i = 0; i < 16; i++) Shader.SetGlobalVector("_CharacterParams" + i, Vector4.zero);
            Shader.SetGlobalFloat("_EndfieldOfficialFrameEnabled", 0);
            EditorSceneManager.OpenScene(ScenePath, OpenSceneMode.Single);
            root = GameObject.Find(CoralCoastMeshImporter.RootName);
            Require(root.GetComponentsInChildren<MeshFilter>().Length == 9, "Scene round trip lost meshes");
            var profile = Object.FindObjectOfType<Endfield.EndfieldOfficialFrameGlobals>();
            Require(profile != null && profile.isActiveAndEnabled, "Scene lost active global profile");
            Require(Shader.GetGlobalFloat("_EndfieldOfficialFrameEnabled") == 1 && Shader.GetGlobalVector("_CharacterParams3").x > 1.26f,
                "Scene reload did not restore cleared globals");
            TyphoeusGeometryValidation.SaveImage(Camera.main, "coral-repaired-front.png", 1600, 1000);
            // Isolate each suspect surface and measure pixels rendered by Unity itself.
            var renderers = root.GetComponentsInChildren<MeshRenderer>();
            var camera = Camera.main;
            Vector3 cameraPosition = camera.transform.position;
            Quaternion cameraRotation = camera.transform.rotation;
            try
            {
                Bounds head = root.transform.Find("C3").GetComponent<Renderer>().bounds;
                camera.transform.position = head.center + new Vector3(0, 0, .6f);
                camera.transform.LookAt(head.center);
                Color[] eyesOn = ReadPixels(camera);
                var pupil = root.transform.Find("C6").GetComponent<Renderer>();
                pupil.enabled = false;
                Color[] eyesOff;
                try { eyesOff = ReadPixels(camera); } finally { pupil.enabled = true; }
                int eyePixels = 0;
                for (int i = 0; i < eyesOn.Length; i++)
                    if (Mathf.Abs(eyesOn[i].r - eyesOff[i].r) + Mathf.Abs(eyesOn[i].g - eyesOff[i].g) + Mathf.Abs(eyesOn[i].b - eyesOff[i].b) > .01f)
                        eyePixels++;
                report.AppendLine($"GPU integrated iris visible pixels={eyePixels}");
                Require(eyePixels > 20, "Iris has no visible contribution in assembled character");
                foreach (string part in new[] { "C3", "C6", "C0" })
                {
                    foreach (var r in renderers) r.enabled = r.name == part;
                    var renderer = renderers.Single(r => r.name == part);
                    Bounds b = renderer.bounds;
                    camera.transform.position = b.center + new Vector3(0, 0, b.size.y * 2.5f + .1f);
                    camera.transform.LookAt(b.center);
                    PixelProbe(camera, part, report);
                }
            }
            finally
            {
                foreach (var r in renderers) r.enabled = true;
                camera.transform.SetPositionAndRotation(cameraPosition, cameraRotation);
            }
            var errors = ShaderUtil.GetShaderMessages(Shader.Find("Endfield/CharacterLit")).Where(m => m.severity == UnityEditor.Rendering.ShaderCompilerMessageSeverity.Error).ToArray();
            Require(errors.Length == 0, "Shader errors: " + string.Join("; ", errors.Select(m => m.message)));
            report.AppendLine("PASS: geometry, material roles, independent UV transforms, import idempotence, scene persistence, GPU probes and shader compilation");
            File.WriteAllText("Logs/recovery-validation.txt", report.ToString());
            Debug.Log(report.ToString());
        }

        static Color[] ReadPixels(Camera camera)
        {
            var target = camera.targetTexture;
            var active = RenderTexture.active;
            var rt = new RenderTexture(512, 512, 24, RenderTextureFormat.ARGBFloat, RenderTextureReadWrite.Linear);
            var tex = new Texture2D(512, 512, TextureFormat.RGBAFloat, false, true);
            try
            {
                camera.targetTexture = rt; camera.Render(); RenderTexture.active = rt;
                tex.ReadPixels(new Rect(0, 0, 512, 512), 0, 0); tex.Apply();
                return tex.GetPixels();
            }
            finally
            {
                camera.targetTexture = target; RenderTexture.active = active;
                Object.DestroyImmediate(tex); rt.Release(); Object.DestroyImmediate(rt);
            }
        }

        public static void RenderOfficialBaseline()
        {
            EditorSceneManager.OpenScene("Assets/Scenes/Typhoeus_Showcase.unity", OpenSceneMode.Single);
            var root = GameObject.Find("chr_0034_typhoea_rebuilt");
            Require(root != null, "Official rebuilt model missing");
            foreach (var r in Object.FindObjectsOfType<Renderer>())
                if (!r.transform.IsChildOf(root.transform)) r.enabled = false;
            TyphoeusGeometryValidation.Inspect(root, true);
            TyphoeusOfficialFrame.Apply();
            TyphoeusGeometryValidation.SaveImage(Camera.main, "official-default-recovered.png", 1600, 1000);
            foreach (var m in ShaderUtil.GetShaderMessages(Shader.Find("Endfield/CharacterLit")))
                Require(m.severity != UnityEditor.Rendering.ShaderCompilerMessageSeverity.Error, m.message);
            EditorSceneManager.SaveScene(EditorSceneManager.GetActiveScene(), "Assets/Scenes/Typhoeus_OfficialFrame_Recovered.unity");
            Debug.Log("[Recovery] PASS: official default model geometry and shared shader render");
        }

        static void PixelProbe(Camera camera, string name, StringBuilder report)
        {
            var previousTarget = camera.targetTexture;
            var previousActive = RenderTexture.active;
            Color previousBackground = camera.backgroundColor;
            var rt = new RenderTexture(512, 512, 24, RenderTextureFormat.ARGBFloat, RenderTextureReadWrite.Linear);
            var texture = new Texture2D(512, 512, TextureFormat.RGBAFloat, false, true);
            try
            {
                camera.backgroundColor = Color.clear;
                camera.targetTexture = rt;
                camera.Render();
                RenderTexture.active = rt;
                texture.ReadPixels(new Rect(0, 0, 512, 512), 0, 0); texture.Apply();
                int visible = 0, black = 0; double sum = 0;
                foreach (Color c in texture.GetPixels())
                {
                    Require(!float.IsNaN(c.r + c.g + c.b) && !float.IsInfinity(c.r + c.g + c.b), "Nonfinite GPU output: " + name);
                    if (c.a < .5f) continue;
                    visible++;
                    float luminance = .2126f*c.r + .7152f*c.g + .0722f*c.b;
                    sum += luminance;
                    if (luminance < .005f) black++;
                }
                string metrics = $"GPU {name}: pixels={visible} meanLinearLuminance={sum / Math.Max(1,visible):F6} nearBlackFraction={(double)black / Math.Max(1,visible):F6}";
                report.AppendLine(metrics);
                Debug.Log(metrics);
                File.WriteAllText("Logs/recovery-validation.txt", report.ToString());
                Require(visible > 500, "Surface not visible: " + name);
                // Horns are deliberately dark; use a near-zero-output check there.
                Require(sum / visible > (name == "C0" ? .001 : .02), "Surface still black: " + name);
            }
            finally
            {
                camera.targetTexture = previousTarget; camera.backgroundColor = previousBackground;
                RenderTexture.active = previousActive;
                Object.DestroyImmediate(texture); rt.Release(); Object.DestroyImmediate(rt);
            }
        }
    }
}
