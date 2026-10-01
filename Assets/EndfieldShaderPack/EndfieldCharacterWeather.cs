using System;
using System.Collections.Generic;
using UnityEngine;
using UnityEngine.Rendering;

namespace EndfieldShaderPack
{
    /// <summary>Manual input producer for the source rain/immersion preview.
    /// Not the original engine's weather/occlusion/drying simulation.</summary>
    [ExecuteAlways]
    [DisallowMultipleComponent]
    public sealed class EndfieldCharacterWeather : MonoBehaviour
    {
        public bool wetEnabled;
        [Range(0, 1)] public float rain = 1;
        [Range(0, 1)] public float immersion;
        [Range(0, 1)] public float waterlineAmount;
        public float waterlineHeight = -100;
        public float textureScale = 2.25f;
        public Texture2D rainEffect;
        public Texture2D rainStreak;
        [Tooltip("Manual time is seconds; source uses seconds/20, not seconds.")]
        public bool freezeTime;
        public float seconds = 12;

        sealed class MeshState { public SkinnedMeshRenderer renderer; public Mesh original, copy; }
        struct Globals
        {
            public Vector4 cp10, time;
            public float enabled, ready;
            public Texture effect, streak;
        }
        readonly List<MeshState> meshes = new List<MeshState>();
        readonly Stack<Globals> frames = new Stack<Globals>();
        readonly Stack<IDisposable> cameraScopes = new Stack<IDisposable>();
        static EndfieldCharacterWeather owner;
        public int PreparedMeshCount => meshes.Count;
        public string InputError { get; private set; } = "";

        public static uint PackBits(float rain, float waterline, float immersed, float snow = 0)
        {
            uint Byte(float value)
            {
                if (!float.IsFinite(value) || value < 0 || value > 1)
                    throw new ArgumentOutOfRangeException(nameof(value), "Weather channel must be finite within [0,1].");
                return (uint)Mathf.FloorToInt(value * 255f + 0.5f);
            }
            return Byte(rain) | (Byte(waterline) << 8) | (Byte(immersed) << 16) | (Byte(snow) << 24);
        }
        public static float Pack(float rain, float waterline, float immersed, float snow = 0)
            => BitConverter.ToSingle(BitConverter.GetBytes(PackBits(rain, waterline, immersed, snow)), 0);

        public void PrepareRestStreams()
        {
            if (meshes.Count != 0) return;
            try
            {
                foreach (var renderer in GetComponentsInChildren<SkinnedMeshRenderer>(true))
                {
                    // Only the two reviewed Typhoeus cloth draws have a source wet consumer.
                    bool cloth = renderer.name.Contains("_cloth_01") || renderer.name.Contains("_cloth_02");
                    bool sourceMaterial = false;
                    foreach (var material in renderer.sharedMaterials)
                        sourceMaterial |= material != null && material.shader.name == "Endfield/CharacterLit"
                            && material.GetFloat("_MaterialFamily") < 0.5;
                    if (!cloth || !sourceMaterial || renderer.sharedMesh == null) continue;
                    var original = renderer.sharedMesh;
                    if (!original.isReadable) throw new InvalidOperationException("Wet rest streams need readable mesh: " + original.name);
                    Vector3[] positions = original.vertices, normals = original.normals;
                    if (normals.Length != positions.Length) throw new InvalidOperationException("Missing rest normals: " + original.name);
                    var copy = Instantiate(original); copy.name = original.name + " (wet rest streams)";
                    copy.hideFlags = HideFlags.HideAndDontSave;
                    meshes.Add(new MeshState { renderer = renderer, original = original, copy = copy });
                    var p = new List<Vector4>(positions.Length); var n = new List<Vector4>(positions.Length);
                    for (int i = 0; i < positions.Length; i++)
                    {
                        // Preserve original model/rest coordinates. The source's skinned
                        // xzy*(1,1,-1) conversion happens in the fragment, exactly once.
                        p.Add(new Vector4(positions[i].x, positions[i].y, positions[i].z, 1));
                        n.Add(new Vector4(normals[i].x, normals[i].y, normals[i].z, 1));
                    }
                    copy.SetUVs(2, p); copy.SetUVs(3, n); renderer.sharedMesh = copy;
                }
            }
            catch { RestoreMeshes(); throw; }
        }
        void OnEnable()
        {
            if (owner != null && owner != this)
            { Debug.LogError("Only one manual character-weather owner may be active.", this); enabled = false; return; }
            owner = this;
            RenderPipelineManager.beginCameraRendering += BeginCamera;
            RenderPipelineManager.endCameraRendering += EndCamera;
        }
        void BeginCamera(ScriptableRenderContext context, Camera camera)
            => cameraScopes.Push(BeginRenderScope());

        sealed class Scope : IDisposable
        {
            EndfieldCharacterWeather weather;
            public Scope(EndfieldCharacterWeather value) { weather = value; }
            public void Dispose() { if (weather == null) return; weather.RestoreGlobals(); weather = null; }
        }
        // URP SingleCameraRequest does not emit begin/endCameraRendering. Both the
        // explicit request and normal Game/Scene cameras use this reversible scope.
        public IDisposable BeginRenderScope()
        {
            frames.Push(new Globals { cp10 = Shader.GetGlobalVector("_CharacterParams10"),
                time = Shader.GetGlobalVector("_EndfieldWeatherTime"),
                enabled = Shader.GetGlobalFloat("_EndfieldCharacterWetnessEnabled"), ready = Shader.GetGlobalFloat("_EndfieldWeatherTexturesReady"),
                effect = Shader.GetGlobalTexture("_CharacterRainEffectTex"), streak = Shader.GetGlobalTexture("_CharacterRainStreakTex") });
            bool Unit(float value) => float.IsFinite(value) && value >= 0 && value <= 1;
            bool valid = Unit(rain) && Unit(immersion) && Unit(waterlineAmount)
                && textureScale > 0 && float.IsFinite(textureScale) && float.IsFinite(waterlineHeight)
                && (!freezeTime || float.IsFinite(seconds));
            InputError = valid ? "" : "天气参数必须为有限数，R/G/B 在 [0,1] 内，纹理尺度 > 0。";
            bool ready = wetEnabled && rainEffect != null && rainStreak != null && valid;
            Shader.SetGlobalFloat("_EndfieldCharacterWetnessEnabled", ready ? 1 : 0);
            Shader.SetGlobalFloat("_EndfieldWeatherTexturesReady", ready ? 1 : 0);
            if (!ready) return new Scope(this);
            try
            {
                PrepareRestStreams();
                Shader.SetGlobalVector("_CharacterParams10", new Vector4(1, Pack(rain, waterlineAmount, immersion), textureScale, waterlineHeight));
                Shader.SetGlobalTexture("_CharacterRainEffectTex", rainEffect);
                Shader.SetGlobalTexture("_CharacterRainStreakTex", rainStreak);
                Shader.SetGlobalVector("_EndfieldWeatherTime", new Vector4(freezeTime ? 1 : 0, seconds / 20f, 0, 0));
                return new Scope(this);
            }
            catch { RestoreGlobals(); throw; }
        }
        void EndCamera(ScriptableRenderContext context, Camera camera)
        { if (cameraScopes.Count != 0) cameraScopes.Pop().Dispose(); }
        void RestoreGlobals()
        {
            if (frames.Count == 0) return;
            var g = frames.Pop();
            Shader.SetGlobalVector("_CharacterParams10", g.cp10); Shader.SetGlobalVector("_EndfieldWeatherTime", g.time);
            Shader.SetGlobalFloat("_EndfieldCharacterWetnessEnabled", g.enabled); Shader.SetGlobalFloat("_EndfieldWeatherTexturesReady", g.ready);
            Shader.SetGlobalTexture("_CharacterRainEffectTex", g.effect); Shader.SetGlobalTexture("_CharacterRainStreakTex", g.streak);
        }
        void RestoreMeshes()
        {
            foreach (var state in meshes)
            {
                if (state.renderer != null && state.renderer.sharedMesh == state.copy) state.renderer.sharedMesh = state.original;
                if (state.copy != null) { if (Application.isPlaying) Destroy(state.copy); else DestroyImmediate(state.copy); }
            }
            meshes.Clear();
        }
        void OnDisable()
        {
            RenderPipelineManager.beginCameraRendering -= BeginCamera; RenderPipelineManager.endCameraRendering -= EndCamera;
            while (cameraScopes.Count != 0) cameraScopes.Pop().Dispose();
            while (frames.Count != 0) RestoreGlobals(); RestoreMeshes();
            if (owner == this) owner = null;
        }
    }
}
