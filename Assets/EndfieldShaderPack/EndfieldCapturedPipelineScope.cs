using UnityEngine;
using UnityEngine.Rendering;

namespace Endfield
{
    // The isolated showcase owns its pipeline only while active. No project
    // settings or original pipeline asset is written by this component.
    [ExecuteAlways]
    public sealed class EndfieldCapturedPipelineScope : MonoBehaviour
    {
        public RenderPipelineAsset pipeline;
        RenderPipelineAsset previous;
        RenderPipelineAsset applied;
        int qualityLevel;
        bool ownsOverride;
        void OnEnable()
        {
            if (pipeline == null) return;
            qualityLevel = QualitySettings.GetQualityLevel();
            previous = QualitySettings.renderPipeline;
            applied = pipeline;
            QualitySettings.renderPipeline = applied;
            ownsOverride = true;
        }
        void OnDisable()
        {
            // The override belongs to the tier active when enabled, not whichever
            // tier is current now. Also use the applied reference, since Inspector
            // edits to `pipeline` must not prevent restoring the original value.
            if (ownsOverride && QualitySettings.GetRenderPipelineAssetAt(qualityLevel) == applied)
            {
                int currentLevel = QualitySettings.GetQualityLevel();
                try
                {
                    if(currentLevel != qualityLevel) QualitySettings.SetQualityLevel(qualityLevel,false);
                    QualitySettings.renderPipeline = previous;
                }
                finally
                {
                    if(currentLevel != qualityLevel) QualitySettings.SetQualityLevel(currentLevel,false);
                }
            }
            ownsOverride = false;
        }
    }
}
