using System;
using System.IO;
using System.Text;
using UnityEditor;
using UnityEditor.SceneManagement;
using UnityEngine;

namespace EndfieldShaderPack
{
    public static class TyphoeusGeometryValidation
    {
        static readonly StringBuilder Report = new StringBuilder();

        [MenuItem("Endfield/Validate Saved Showcase", false, 51)]
        public static void VerifySavedShowcase()
        {
            Report.Clear();
            EditorSceneManager.OpenScene("Assets/Scenes/Typhoeus_Showcase.unity");
            var root = GameObject.Find("chr_0034_typhoea_rebuilt");
            if (root == null) throw new InvalidOperationException("Reopened scene has no rebuilt model");
            var renderers = root.GetComponentsInChildren<SkinnedMeshRenderer>();
            if (renderers.Length != 17) throw new InvalidOperationException("Expected all 17 source meshes");
            foreach (var smr in renderers)
            {
                if (!AssetDatabase.Contains(smr.sharedMesh)) throw new InvalidOperationException("Mesh not saved: " + smr.name);
                if (smr.sharedMesh.tangents.Length != smr.sharedMesh.vertexCount)
                    throw new InvalidOperationException("Missing tangents: " + smr.name);
                foreach (var material in smr.sharedMaterials)
                {
                    if (material == null || material.GetFloat("_ZTest") != 4)
                        throw new InvalidOperationException("Missing material or incompatible depth state: " + smr.name);
                    foreach (var message in ShaderUtil.GetShaderMessages(material.shader))
                        if (message.severity == UnityEditor.Rendering.ShaderCompilerMessageSeverity.Error)
                            throw new InvalidOperationException(message.message);
                }
            }
            Inspect(root, true);
            ValidateMovingBone(root);
            var cam = Camera.main;
            Vector3 originalPosition = cam.transform.position;
            Quaternion originalRotation = cam.transform.rotation;
            Bounds bounds = TyphoeusSceneSetup.ComputeWorldBounds(root);
            float distance = Vector3.Distance(cam.transform.position, bounds.center);
            var light = UnityEngine.Object.FindObjectOfType<Endfield.EndfieldCharacterLight>();
            if (light != null) light.ApplyLight();
            SaveImage(cam, "verified-front.png", 1920, 1080);
            cam.transform.position = bounds.center + new Vector3(distance, 0, 0);
            cam.transform.LookAt(bounds.center);
            SaveImage(cam, "verified-side.png", 1920, 1080);
            cam.transform.position = bounds.center + new Vector3(0, 0, -distance);
            cam.transform.LookAt(bounds.center);
            SaveImage(cam, "verified-back.png", 1920, 1080);
            cam.transform.SetPositionAndRotation(originalPosition, originalRotation);
            Log("PASS: reloaded scene; 17 persistent meshes; complete tangents; depth states; shader compilation; rest and posed skinning.");
            File.WriteAllText(Path.Combine(Application.dataPath, "../Validation/geometry-report.txt"), Report.ToString());
        }

        static void ValidateMovingBone(GameObject root)
        {
            Transform target = null;
            foreach (var t in root.GetComponentsInChildren<Transform>())
                if (t.name == "Bip001_Head") { target = t; break; }
            if (target == null) throw new InvalidOperationException("Head bone missing");
            Quaternion rest = target.localRotation;
            float error = 0;
            int moved = 0;
            try
            {
                target.localRotation = rest * Quaternion.Euler(0, 15, 0);
                foreach (var smr in root.GetComponentsInChildren<SkinnedMeshRenderer>())
                {
                    var mesh = smr.sharedMesh;
                    var matrices = new Matrix4x4[smr.bones.Length];
                    for (int b = 0; b < matrices.Length; b++)
                        matrices[b] = smr.transform.worldToLocalMatrix * smr.bones[b].localToWorldMatrix * mesh.bindposes[b];
                    var baked = new Mesh();
                    smr.BakeMesh(baked);
                    var src = mesh.vertices;
                    var dst = baked.vertices;
                    var weights = mesh.boneWeights;
                    for (int v = 0; v < src.Length; v++)
                    {
                        var w = weights[v];
                        Vector3 expected = matrices[w.boneIndex0].MultiplyPoint3x4(src[v]) * w.weight0
                            + matrices[w.boneIndex1].MultiplyPoint3x4(src[v]) * w.weight1
                            + matrices[w.boneIndex2].MultiplyPoint3x4(src[v]) * w.weight2
                            + matrices[w.boneIndex3].MultiplyPoint3x4(src[v]) * w.weight3;
                        float delta = Vector3.Distance(expected, dst[v]);
                        if (float.IsNaN(delta) || float.IsInfinity(delta)) throw new InvalidOperationException("Non-finite posed vertex");
                        error = Mathf.Max(error, delta);
                        if (Vector3.Distance(src[v], dst[v]) > 0.001f) moved++;
                    }
                    UnityEngine.Object.DestroyImmediate(baked);
                }
            }
            finally { target.localRotation = rest; }
            Log($"[Geometry] posedSkinError={error:G6} movedVertices={moved}");
            if (error > 0.0001f || moved == 0) throw new InvalidOperationException("Posed skinning failed");
        }

        static void Log(string message) { Debug.Log(message); Report.AppendLine(message); }

        public static void Baseline()
        {
            TyphoeusSceneSetup.SetupShowcaseScene();
            var root = GameObject.Find("chr_0034_typhoea_rebuilt");
            Inspect(root, false);
            Capture(root, "baseline-skinned.png", false);
            Capture(root, "baseline-static.png", true);
        }

        public static void Inspect(GameObject root, bool failOnError)
        {
            float worst = 0;
            foreach (var smr in root.GetComponentsInChildren<SkinnedMeshRenderer>())
            {
                var mesh = smr.sharedMesh;
                if (mesh == null) throw new InvalidOperationException("Missing persistent mesh: " + smr.name);
                float matrixError = 0;
                for (int b = 0; b < smr.bones.Length; b++)
                {
                    Matrix4x4 skin = smr.transform.worldToLocalMatrix * smr.bones[b].localToWorldMatrix * mesh.bindposes[b];
                    for (int i = 0; i < 16; i++) matrixError = Mathf.Max(matrixError, Mathf.Abs(skin[i] - Matrix4x4.identity[i]));
                }
                var baked = new Mesh();
                smr.BakeMesh(baked);
                var src = mesh.vertices;
                var dst = baked.vertices;
                float maxError = 0;
                for (int i = 0; i < src.Length; i++)
                {
                    float delta = Vector3.Distance(src[i], dst[i]);
                    if (float.IsNaN(delta) || float.IsInfinity(delta)) throw new InvalidOperationException("Non-finite rest vertex");
                    maxError = Mathf.Max(maxError, delta);
                }
                worst = Mathf.Max(worst, maxError);
                Log($"[Geometry] {smr.name}: vertices={src.Length} matrixError={matrixError:G6} vertexError={maxError:G6}");
                if (failOnError && matrixError > 0.0001f) throw new InvalidOperationException("Bind matrix mismatch: " + smr.name);
                UnityEngine.Object.DestroyImmediate(baked);
            }
            Log($"[Geometry] maxRestVertexError={worst:G6}");
            if (failOnError && worst > 0.0001f) throw new InvalidOperationException("Rest skinning displaces vertices: " + worst);
        }

        public static void Capture(GameObject root, string name, bool staticMesh)
        {
            var preview = new GameObject("GeometryPreview");
            preview.transform.SetPositionAndRotation(root.transform.position, root.transform.rotation);
            preview.transform.localScale = root.transform.localScale;
            var material = new Material(Shader.Find("Universal Render Pipeline/Lit"));
            material.SetColor("_BaseColor", new Color(0.7f, 0.7f, 0.7f));
            Bounds bounds = new Bounds();
            bool first = true;
            foreach (var smr in root.GetComponentsInChildren<SkinnedMeshRenderer>())
            {
                // These are special shadow/VFX shells, not opaque body surfaces.
                if (smr.name.Contains("shadow") || smr.name.Contains("vfxpart")) continue;
                var go = new GameObject(smr.name);
                go.transform.SetParent(preview.transform, false);
                Mesh mesh;
                if (staticMesh) mesh = smr.sharedMesh;
                else { mesh = new Mesh(); smr.BakeMesh(mesh); }
                go.AddComponent<MeshFilter>().sharedMesh = mesh;
                var r = go.AddComponent<MeshRenderer>();
                var mats = new Material[mesh.subMeshCount];
                for (int i = 0; i < mats.Length; i++) mats[i] = material;
                r.sharedMaterials = mats;
                if (first) { bounds = r.bounds; first = false; } else bounds.Encapsulate(r.bounds);
            }
            root.SetActive(false);
            var cam = Camera.main;
            cam.orthographic = true;
            cam.orthographicSize = bounds.extents.y * 1.15f;
            cam.transform.position = bounds.center + new Vector3(0, 0, 4);
            cam.transform.LookAt(bounds.center);
            cam.nearClipPlane = 0.01f;
            cam.farClipPlane = 100;
            cam.clearFlags = CameraClearFlags.SolidColor;
            cam.backgroundColor = new Color(0.12f, 0.14f, 0.18f);
            var light = UnityEngine.Object.FindObjectOfType<Light>();
            light.transform.rotation = Quaternion.Euler(35, 160, 0);
            light.intensity = 1.5f;
            SaveImage(cam, name);
            root.SetActive(true);
            foreach (var filter in preview.GetComponentsInChildren<MeshFilter>())
                if (!staticMesh) UnityEngine.Object.DestroyImmediate(filter.sharedMesh);
            UnityEngine.Object.DestroyImmediate(preview);
            UnityEngine.Object.DestroyImmediate(material);
        }

        public static void SaveImage(Camera cam, string name, int width = 1200, int height = 1200)
        {
            string dir = Path.GetFullPath(Path.Combine(Application.dataPath, "../Validation"));
            Directory.CreateDirectory(dir);
            var rt = new RenderTexture(width, height, 24);
            var previous = RenderTexture.active;
            cam.targetTexture = rt;
            cam.Render();
            RenderTexture.active = rt;
            var tex = new Texture2D(width, height, TextureFormat.RGBA32, false);
            tex.ReadPixels(new Rect(0, 0, width, height), 0, 0);
            tex.Apply();
            File.WriteAllBytes(Path.Combine(dir, name), tex.EncodeToPNG());
            cam.targetTexture = null;
            RenderTexture.active = previous;
            UnityEngine.Object.DestroyImmediate(tex);
            UnityEngine.Object.DestroyImmediate(rt);
        }
    }
}
