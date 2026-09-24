using System;
using System.Collections.Generic;
using UnityEngine;

namespace EndfieldShaderPack
{
    /// One slot of the official character shadow atlas. The slot index is what the
    /// resolve reads back out of GBuffer0 through log2(pack) - 8, so it has to stay
    /// below the active slot count and be unique per character.
    [DisallowMultipleComponent]
    public sealed class EndfieldCharacterShadowCaster : MonoBehaviour
    {
        public const int MaxSlots = 8;

        // Frame-6411 slot 0, captured verbatim. x scales the receiver's pull toward the
        // light and y its offset along the normal, both in normalised light-box units,
        // so they carry over to any world scale as long as the box stays a tight fit.
        // w is the cell resolution the official paired with them; the resolve never
        // reads it and neither does this project.
        public static readonly Vector4 CapturedBiases =
            new Vector4(0.0034731030464172363f, 0.006946206092834473f, 0.0011577010154724121f, 256f);

        [Range(0, MaxSlots - 1)] public int slot;

        // The captured box leaves the visible surface 12-17% of margin in plane, which
        // the character's own hidden back side consumes, so the official is a tight fit
        // and only needs enough padding to keep animated geometry inside the cell.
        [Range(0f, 0.25f)] public float paddingFraction = 0.02f;

        public Vector4 biases = CapturedBiases;

        static readonly List<EndfieldCharacterShadowCaster> registry = new List<EndfieldCharacterShadowCaster>();
        public static IReadOnlyList<EndfieldCharacterShadowCaster> Active => registry;

        // OnEnable/OnDisable keep the registry warm, but scene loads in batchmode have
        // shown the registry empty while the component is live, so the render path can
        // rebuild it from the scene instead of silently skipping the whole chain.
        // FindObjectsOfType returns disabled components on active GameObjects, so the
        // refresh has to re-apply the enabled filter: the live A/B gate relies on
        // caster.enabled = false actually disabling the whole chain.
        public static IReadOnlyList<EndfieldCharacterShadowCaster> Refresh()
        {
            registry.Clear();
            foreach (var caster in FindObjectsOfType<EndfieldCharacterShadowCaster>())
                if (caster.isActiveAndEnabled)
                    registry.Add(caster);
            return registry;
        }

        Renderer[] cached;

        void OnEnable()
        {
            if (!registry.Contains(this)) registry.Add(this);
        }

        void OnDisable()
        {
            registry.Remove(this);
        }

        public Renderer[] Casters => cached ?? (cached = GetComponentsInChildren<Renderer>());

        public void InvalidateCache()
        {
            cached = null;
        }

        public Bounds WorldBounds()
        {
            Renderer[] renderers = Casters;
            if (renderers.Length == 0)
                throw new InvalidOperationException(name + " has no renderers to fit a shadow box around.");
            Bounds bounds = renderers[0].bounds;
            for (int i = 1; i < renderers.Length; i++) bounds.Encapsulate(renderers[i].bounds);
            return bounds;
        }
    }
}
