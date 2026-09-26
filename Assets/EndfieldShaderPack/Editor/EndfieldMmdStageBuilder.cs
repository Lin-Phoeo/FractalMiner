using System;
using UnityEditor;
using UnityEditor.SceneManagement;
using UnityEngine;
using UnityEngine.Rendering.Universal;

namespace EndfieldShaderPack
{
    /// <summary>
    /// Creates a separate dance venue from the recovered Typhoeus scene. The
    /// floor, ring and gradient sky use the already imported Laevatain sample
    /// scene assets. Character materials remain on the capture-derived shader.
    /// </summary>
    public static class EndfieldMmdStageBuilder
    {
        public const string BaselineScenePath = "Assets/Scenes/Typhoeus_OfficialFrame_Recovered.unity";
        public const string DanceScenePath = "Assets/Scenes/Typhoeus_MMD_Stage.unity";
        const string VenueAssets = "Assets/EndfieldShowcaseRef/Arts/Materials/Scene/";

        [MenuItem("Endfield/MMD/Build Typhoeus Dance Stage")]
        public static void BuildDanceScene()
        {
            if (!Application.isBatchMode &&
                !EditorSceneManager.SaveCurrentModifiedScenesIfUserWantsTo())
                return;

            var floor = RequireMaterial("Floor.mat");
            var ring = RequireMaterial("Ring.mat");
            var sky = RequireMaterial("Skybox.mat");
            var lut = EndfieldCaptureAssets.Texture("grading-lut");
            if (lut == null || lut.width != 1024 || lut.height != 32)
                throw new InvalidOperationException("Captured grading LUT is unavailable or has wrong dimensions.");

            var scene = EditorSceneManager.OpenScene(BaselineScenePath, OpenSceneMode.Single);
            if (!scene.IsValid())
                throw new InvalidOperationException("Could not open the recovered Typhoeus baseline.");

            var venue = new GameObject("Typhoeus Dance Venue (Laevatain SampleScene)");
            venue.transform.SetPositionAndRotation(Vector3.zero, Quaternion.identity);

            // The source SampleScene uses a large cylinder for the floor and a
            // small textured plane for the luminous ring. Scale the ring to give
            // the dancer several metres of travel without changing its material.
            var floorObject = GameObject.CreatePrimitive(PrimitiveType.Cylinder);
            floorObject.name = "Laevatain Floor";
            floorObject.transform.SetParent(venue.transform, false);
            floorObject.transform.localPosition = new Vector3(0f, -0.11f, 0f);
            floorObject.transform.localScale = new Vector3(30f, 0.1f, 30f);
            floorObject.GetComponent<MeshRenderer>().sharedMaterial = floor;

            var ringObject = GameObject.CreatePrimitive(PrimitiveType.Plane);
            ringObject.name = "Laevatain Ring";
            ringObject.transform.SetParent(venue.transform, false);
            ringObject.transform.localPosition = new Vector3(0f, 0.002f, 0f);
            ringObject.transform.localScale = new Vector3(0.56f, 1f, 0.56f);
            ringObject.GetComponent<MeshRenderer>().sharedMaterial = ring;
            ringObject.GetComponent<MeshRenderer>().shadowCastingMode = UnityEngine.Rendering.ShadowCastingMode.Off;
            // The lower floor supplies collision. Removing the ring collider
            // prevents two coplanar surfaces from confusing motion tools.
            UnityEngine.Object.DestroyImmediate(ringObject.GetComponent<Collider>());

            RenderSettings.skybox = sky;
            var camera = Camera.main;
            if (camera == null) throw new InvalidOperationException("Recovered scene has no Main Camera.");
            camera.clearFlags = CameraClearFlags.Skybox;
            camera.allowHDR = true;
            camera.allowMSAA = false;
            camera.fieldOfView = 39f;
            camera.transform.SetPositionAndRotation(
                new Vector3(3.8f, 1.0f, 0f),
                Quaternion.LookRotation(new Vector3(0f, 0.86f, 0f) - new Vector3(3.8f, 1.0f, 0f), Vector3.up));
            var additional = camera.GetUniversalAdditionalCameraData();
            additional.renderPostProcessing = false;
            additional.antialiasing = AntialiasingMode.None;
            additional.SetRenderer(0);

            var post = camera.GetComponent<EndfieldCapturedPostProfile>();
            if (post == null) post = camera.gameObject.AddComponent<EndfieldCapturedPostProfile>();
            post.logLut = lut;
            post.lutUV = new Vector4(1f, -1f, 0f, 1f);
            post.generateBloom = true;
            post.applyCapturedPost = true;

            if (!EditorSceneManager.SaveScene(scene, DanceScenePath))
                throw new InvalidOperationException("Could not save dance scene: " + DanceScenePath);
            AssetDatabase.Refresh();
            Debug.Log("[MmdStage] Built " + DanceScenePath +
                " with Laevatain floor/ring/sky and captured Typhoeus post profile.");
        }

        static Material RequireMaterial(string file)
        {
            string path = VenueAssets + file;
            var material = AssetDatabase.LoadAssetAtPath<Material>(path);
            if (material == null || material.shader == null || !material.shader.isSupported)
                throw new InvalidOperationException("Laevatain stage material missing or unsupported: " + path);
            return material;
        }
    }
}
