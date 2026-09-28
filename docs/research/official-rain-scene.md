# 官方场景雨系统源码抽取(4 shader)

来源:`_dump_1.5.3/AllShader_1.5.3/Assets/packages/com.hg.render-pipelines/runtime/shaders/materials/rain/`(4 wrapper 全读 + 各自代表变体)。
代表变体:各 shader 单 Pass,取编号最小 Fragment(catch-all 或首个分支)+ 同号 Vertex;其余变体只补 keyword 差异。

**本文不含任何单元测试或参考实现**(独立 oracle 由验收方另写),仅忠实转写源码。

## 0. 总览

| Shader | 用途 | Pass | LIGHTMODE | Blend | ZTest/ZWrite/Cull | 关键字 | 代表变体 |
|---|---|---|---|---|---|---|---|
| farrain.shader | 远景雨幕(包围盒内程序化雨柱) | FarRain | ForwardOnly | `SrcAlpha OneMinusSrcAlpha, One One`(alpha 加法) | 无 ZTest 行(默认 LEqual)/Off/**Cull Front** | HG_ENABLE_MV、RAIN_WAVE、RAIN_LIGHTING、SRP_INSTANCING_ON(farrain.shader:26-29) | b6 |
| rainsplash.shader | 地面溅射(三阶段粒子片) | RainSplash | ForwardOnly | 同上 | 默认/Off/Cull Off | RAIN_LIGHTING、SRP_INSTANCING_ON(rainsplash.shader:26-28) | b3 |
| sceneeffectrain.shader | 场景雨/雪效(屏幕重建+贴图调制) | SceneEffectRain | ForwardOnly | 同上 | 默认/Off/Cull Off | HG_ENABLE_MV、SNOW_COLLISION、SNOW_FLAKE、RAIN_LIGHTING、SRP_INSTANCING_ON(sceneeffectrain.shader:25-29) | b12 |
| screenraindropfx.shader | 镜头雨滴遮罩(供 Distortion 折射) | ScreenRainDropFX | **Distortion** | 同上 | 默认/Off/Cull Off | SRP_INSTANCING_ON(screenraindropfx.shader:26) | b1 |

四者共同点:输出 `SV_Target0 = (RGB 颜色, 强度)`;部分双 RT(SV_Target1 = 恒零 MV 编码 `(0.5,0.5,1,0)`);共用全局 `_RainWetnessGlobalParam4`(SVG c148,`.y > 0.5` 启用垂直遮挡比较)与 `VerticalOcclusionMapTransformCB`(b12/b13,space0)。

## 1. FarRain(远景雨幕)

属性(farrain.shader:2-8):`_RainTex0`(2D,white)、`_RainTex1_ST`(1,1,1,1)、`_RainParams`(1,1,1,1)、`_RainMaskParams`(-1,1,1,1)、`_RainColor`(1,1,1,1)。

纹理(f_b6):t23 `_VerticalOcclusionMap`(s5 比较 LinearRepeat)、t0,space3 `_DepthTextureWithWater`(深度+水面)、t37 `_IntegratedLightScattering`。cbuffer:b12 `VerticalOcclusionMapTransformCB`(WorldToVerticalOcclusionMap 4×4 + UVScrollingOffset)、b0,space1 UnityPerMaterial(`_RainTex0_ST/_RainTex1_ST/_RainColor/_RainParams/_RainMaskParams`,注意 cbuffer 顺序与 Properties 声明不同)(Sub0_Pass0_Fragment_b6.hlsl:176-189)。

**核心:雨柱完全程序化,不采样 _RainTex0**:

```
// 程序化雨柱(f_b6:242-255)
uv = _5 × _RainTex0_ST.xy                                     // :242
r  = frac(floor(uv.x) × 0.010999999940395355224609375f)        // :243 列随机
r2 = r × (r + 7.5f); r3 = frac(r2 × (r2 + r2)); s = 0.5f × r3  // :244-246
len = floor(_RainTex0_ST.y × (1.0f + s))                       // :247 条纹长度(受贴图 ST.y 调制)
u2.y = uv.y + ((_RainParams.x + 0.5f) + s) × len               // :250 下落偏移
rand = frac(sin(dot(fmod(floor(u2), 1024.0f.xx), (12.98980045318603515625f, 78.233001708984375f))) × 43758.546875f)   // :251 经典 hash
wob  = rand × ((sin(uv.y + (r3 × len)) × 0.5f) + 0.5f)         // :252 摆动相位
d    = clamp(abs(float2(0.5f + ((wob×2 - 1) × 0.300000011920928955078125f), 0.5f) - frac(u2)), 0, 1)   // :253 条带距离(半宽 0.3)
thick = min(_RainParams.y × 0.4000000059604644775390625f × (0.4000000059604644775390625f + r3 × 0.60000002384185791015625f), 1.0f)   // :254
stripe = (step(lerp(0.64999997615814208984375f, 1.0f, 1.0f - _RainParams.z), rand) × smoothstep(0.64999997615814208984375f, 1.0f, rand)   // 密度门(_RainParams.z)
        × (smoothstep(0.20000000298023223876953125f, 0.0f, clamp(d.x - (int(_RainMaskParams.w > 0) × clamp(0.25f / (_6.x × (1/max(_6.y, 0.01)))), 0, 1)), 0, 1)   // 竖直遮挡修正
        × (1 - smoothstep(clamp(thick - 0.2, 0, 1), max(thick, 0.00048828125f), d.y))))   // 条带宽度门
        × smoothstep(130.0f, 10.0f, max(WS.y - camY, 0))        // :255 高度衰减(130m→10m)
// 垂直遮挡比较(f_b6:261-274,同 screenraindropfx §4)
// 强度(f_b6:323):
intensity = clamp((stripe × vOcclusion × clamp(max(LinearEyeDepth(场景深度) - viewZ - (wob × 7.5f), 0) × 0.100000001490116119384765625f, 0, 1)) × _RainColor.w, 0, 1)
// LinearEyeDepth = 1/(z×_ZBufferParams.z + _ZBufferParams.w),场景深度用 _DepthTextureWithWater(水面感知)——雨条纹落到地面前被裁剪
// 颜色(f_b6:324):_RainColor.rgb × 雾透过 + 雾散射(大气雾/指数雾/体积雾全链,同家族)——无 RAIN_LIGHTING(catch-all)
out = (雾后色, intensity);SV_Target1 = (0.5, 0.5, 1, 0)(恒零 MV)   // :331-332
```
keyword 差异:`RAIN_LIGHTING`(变体 b8-b13)加光照复算 ⚠待核;`RAIN_WAVE` ⚠待核;`HG_ENABLE_MV` 打开 RT1 的真实 MV 计算(恒零版见 :332)。

## 2. RainSplash(地面溅射)

属性(rainsplash.shader:2-7):`_RainTex0`、`_RainTex1_ST`、`_RainParams`、`_RainColor`。

片元(Sub0_Pass0_Fragment_b3.hlsl:30-34)极简:
```
tex = _RainTex0.SampleLevel(LinearClamp, uv0, 0)
sel = _4.y × 3.0f                                    // 溅射阶段选择器(顶点给)
ch  = lerp(lerp(tex.x, tex.y, step(1.0f, sel)), tex.z, step(2.0f, sel))   // 三阶段:扩散/水花/消散 三张图打包在 RGB
out = (_RainColor.rgb, _RainColor.w × ch × _4.x)     // _4.x = 生命期 alpha
```
顶点(v_b3/b4-b6)负责 UV 动画与阶段推进 ⚠待核(未逐行);`RAIN_LIGHTING` 变体加光照 ⚠待核。

## 3. SceneEffectRain(场景雨/雪效)

属性(sceneeffectrain.shader:2-8):`_RainTex0`、`_RainParams`、`_RainColor`、`_RainDirectionParams`(0,0,0,0)、`_RainMaskParams`(0,0,0,0)。cbuffer 里另有 `_RainOffsetParams`(c5,f_b12:198-204,Properties 未列 ⚠待核)。

片元(Sub0_Pass0_Fragment_b12.hlsl:194-241,catch-all 无 SNOW/RAIN_LIGHTING):

> **验收修正(Claude 2026-09-28,已核实)**:本 §3 的 b12 行号整体偏低约 +14~20——`frag_main` 实际起于 `Sub0_Pass0_Fragment_b12.hlsl:214`,垂直遮挡 SampleCmp 在 `:228-230`(非下方标的 :206-215)。逻辑/结构/公式均正确,仅行号需按此偏移对照。farrain/rainsplash/screenraindropfx 三者行号经抽查准确。
```
ndc = fragCoord.xy×_ScreenSize.zw×2 - 1(y 翻转);world = InvViewProjMatrix × ndc(透视除)   // :194-198 屏幕重建世界坐标
tex  = _RainTex0.SampleBias(LinearClamp, _4.zw × _RainTex0_ST.xy, mipBias)                 // :199(动画 UV 由顶点给)
edge = clamp((0.5f.xx - abs(0.5f.xx - _4.xy)) × 2, 0, 1)                                    // :200 屏幕内边缘淡出
vOccl = _VerticalOcclusionMap.SampleCmpLevelZero(旋转 UV + ScrollOffset, max(z, 0.00048828125f))(if _RainWetnessGlobalParam4.y > 0.5f,否则 1)   // :206-215
alpha = clamp(((_RainTex0_ST.z + _RainTex0_ST.w × (tex.x×2 - 1)) × ((vOccl × edge.x × edge.y) × _5.x)) × (_RainColor.w × _5.y), 0, 1)   // :216
out = (_RainColor.rgb, alpha);SV_Target1 = 恒零 MV                                          // :216-217
```
SNOW_COLLISION/SNOW_FLAKE/RAIN_LIGHTING 分支(b13-b27,+行数递增 ⚠待核)。

## 4. ScreenRainDropFX(镜头雨滴遮罩)

属性(screenraindropfx.shader:2-7):`_ScreenDropFXNoiseTex`、`_ScreenDropFXNoiseTex_ST`、`_RainTex0_ST`、`_RainParams`、`_RainColor`。LIGHTMODE="Distortion"——输出被 Distortion 后处理消费(镜头水滴折射/叠色)⚠待核消费端。

片元(Sub0_Pass0_Fragment_b1.hlsl:210-238):
```
vOccl = _VerticalOcclusionMap.SampleCmpLevelZero(camPos 变换 UV + ScrollOffset, camDepth)(if _RainWetnessGlobalParam4.y > 0.5f)   // :212-225 镜头是否被淋到
if (vOccl > 0.00048828125f):
  noise = _ScreenDropFXNoiseTex.SampleBias(uv1 × ST.xy + ST.zw)                              // :230
  drop  = ( smoothstep(_RainParams.z, _RainParams.w, length(uv1 - 0.5f.xx))                  // 外环(水痕半径)
          × smoothstep(_RainParams.x × (1 + ((noise.x - 0.5) × 2) × _RainParams.y), 0, length(uv0 - 0.5f.xx)) )   // 内滴(噪声抖动半径)
          × _RainColor.w × clamp(_5.x, 0, 1) × noise.x × vOccl                               // :232
out = (_RainColor.rgb, drop);else alpha = 0                                                  // :233-238
```

## 5. _Property 默认值汇总(可调参数)

| Shader | 属性 | 默认值 |
|---|---|---|
| farrain | _RainTex0 / _RainTex1_ST / _RainParams / _RainMaskParams / _RainColor | white / (1,1,1,1) / (1,1,1,1) / (-1,1,1,1) / (1,1,1,1) |
| rainsplash | _RainTex0 / _RainTex1_ST / _RainParams / _RainColor | 同上(无 _RainMaskParams) |
| sceneeffectrain | _RainTex0 / _RainParams / _RainColor / _RainDirectionParams / _RainMaskParams | white / (1,1,1,1) / (1,1,1,1) / (0,0,0,0) / (0,0,0,0) |
| screenraindropfx | _ScreenDropFXNoiseTex / _ScreenDropFXNoiseTex_ST / _RainTex0_ST / _RainParams / _RainColor | white / (1,1,1,1) / (1,1,1,1) / (1,1,1,1) / (1,1,1,1) |

全部属性均暴露 inspector(无 HideOnly 标记);但 cbuffer 内顺序与 Properties 声明不一致(如 farrain cbuffer 为 `_RainTex0_ST/_RainTex1_ST/_RainColor/_RainParams/_RainMaskParams`,f_b6:184-188)——借名需按 cbuffer 核对。

## 6. ⚠待核汇总
1. RAIN_WAVE / RAIN_LIGHTING / SNOW_COLLISION / SNOW_FLAKE / HG_ENABLE_MV 各分支逐行(变体 b7-b13 / b13-b27 未读)。
2. farrain 顶点动画(UV 下落/wave)与 rainsplash 顶点(阶段推进)未逐行(242 行级)。
3. ScreenRainDropFX 的 Distortion 消费端(哪个 pass 读它的输出)不在 rain/ 目录内。
4. `_RainOffsetParams`(sceneeffectrain c5)在 Properties 中不存在,由脚本注入。
5. `_6.x/_6.y`(farrain 竖直遮挡修正的输入)来自顶点插值的具体语义。

---
*仅静态转写,行号指 rain\ 下各 .shader 与变体文件;无测试/参考实现。*
