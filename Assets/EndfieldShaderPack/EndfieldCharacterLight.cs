// ============================================================
//  EndfieldCharacterLight.cs
//  分离式角色光照控制器
//
//  终末地角色使用独立光照系统，不受场景主光 / 探针影响。
//  本脚本把角色光的方向、颜色、强度通过全局 shader 变量注入：
//    _CharacterLightDir.xyz  = 世界空间光照方向（指向光源）
//    _CharacterLightDir.w    = 1 启用分离光 / 0 回退到场景光
//    _CharacterLightColor    = 光照颜色 * 强度
//
//  用法：把本脚本挂到任意场景管理器物体上，旋转该物体朝向即可
//  控制角色受光方向（沿用常见的"角色光朝向 = transform.forward"约定）。
// ============================================================
using UnityEngine;

namespace Endfield
{
    [ExecuteAlways]
    public class EndfieldCharacterLight : MonoBehaviour
    {
        [Header("角色光照")]
        [Tooltip("启用分离式角色光照；关闭则回退到场景主光")]
        public bool useSeparatedLight = true;

        [Tooltip("光照颜色")]
        [ColorUsage(false, true)] public Color lightColor = Color.white;

        [Tooltip("光照强度")]
        [Min(0f)] public float intensity = 1f;

        [Tooltip("环境/补光颜色，叠加到漫反射底部")]
        [ColorUsage(false, false)] public Color ambientColor = new Color(0.45f, 0.5f, 0.6f);

        static readonly int s_LightDir   = Shader.PropertyToID("_CharacterLightDir");
        static readonly int s_LightColor = Shader.PropertyToID("_CharacterLightColor");
        static readonly int s_Ambient    = Shader.PropertyToID("_CharacterAmbient");

        void Update()
        {
            ApplyLight();
        }

        void OnValidate()
        {
            // 编辑器里拖拽/改参数时实时刷新
            if (Application.isPlaying) return;
            ApplyLight();
        }

        public void ApplyLight()
        {
            if (useSeparatedLight)
            {
                // 角色光方向：默认用物体 forward 指向光源方向
                Vector3 dir = transform.forward;
                dir = dir.sqrMagnitude < 1e-6f ? Vector3.forward : dir.normalized;
                Shader.SetGlobalVector(s_LightDir, new Vector4(dir.x, dir.y, dir.z, 1f));
                Shader.SetGlobalVector(s_LightColor, lightColor.linear * intensity);
                Shader.SetGlobalVector(s_Ambient, new Vector4(ambientColor.r, ambientColor.g, ambientColor.b, 1f));
            }
            else
            {
                Shader.SetGlobalVector(s_LightDir, Vector4.zero); // w=0 触发 shader 回退
            }
        }

        void OnDisable()
        {
            // 关闭时让角色回到场景光，避免残留状态
            Shader.SetGlobalVector(s_LightDir, Vector4.zero);
        }
    }
}