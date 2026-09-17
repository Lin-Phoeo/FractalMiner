using UnityEditor;
using UnityEditor.SceneManagement;
using UnityEngine;

namespace EndfieldShaderPack
{
    public static class EndfieldRenderCapture
    {
        [MenuItem("Endfield/Capture Showcase Screenshot", false, 50)]
        public static void Capture()
        {
            TyphoeusSceneSetup.SetupShowcaseScene();
            var model = GameObject.Find("chr_0034_typhoea_rebuilt");
            if (model == null) throw new System.InvalidOperationException("Rebuilt model missing");
            TyphoeusGeometryValidation.Inspect(model, true);
            var light = Object.FindObjectOfType<Endfield.EndfieldCharacterLight>();
            if (light != null) light.ApplyLight();
            var cam = Camera.main;
            cam.aspect = 1920f / 1080f;
            TyphoeusSceneSetup.FrameCamera(model);
            EditorSceneManager.SaveScene(EditorSceneManager.GetActiveScene());
            TyphoeusGeometryValidation.SaveImage(cam, "typhoeus-fixed.png", 1920, 1080);
            Debug.Log("[Capture] Saved Validation/typhoeus-fixed.png");
        }
    }
}
