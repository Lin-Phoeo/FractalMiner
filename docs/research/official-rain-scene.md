# 官方场景雨系统源码抽取(4 shader)

来源:`_dump_1.5.3/AllShader_1.5.3/Assets/packages/com.hg.render-pipelines/runtime/shaders/materials/rain/`(4 wrapper 全读 + 各自代表变体)。
代表变体:各 shader 单 Pass,取编号最小 Fragment(catch-all 或首个分支)+ 同号 Vertex;其余变体只补 keyword 差异。

**本文是代表变体导读，不是完整等价实现，也不证明 Unity 已接入雨系统。** 2026-09-30 对 wrapper 和下述关键片元回源修正；逐行未展开的光照/雪花分支仍未通过完整验收。见 [资料审计记录](source-contract-audit-20260930.md)。

## 0. 总览

| Shader | 用途 | Pass | LIGHTMODE | Blend | ZTest/ZWrite/Cull | 关键字 | 代表变体 |
|---|---|---|---|---|---|---|---|
| farrain.shader | 远景雨幕(包围盒内程序化雨柱) | FarRain | ForwardOnly | `SrcAlpha OneMinusSrcAlpha, One One`(alpha 加法) | 无 ZTest 行(默认 LEqual)/Off/**Cull Front** | HG_ENABLE_MV、RAIN_WAVE、RAIN_LIGHTING、SRP_INSTANCING_ON(farrain.shader:26-29) | b6 |
| rainsplash.shader | 地面溅射(三阶段粒子片) | RainSplash | ForwardOnly | 同上 | 默认/Off/Cull Off | RAIN_LIGHTING、SRP_INSTANCING_ON(rainsplash.shader:26-28) | b3 |
| sceneeffectrain.shader | 场景雨/雪效(屏幕重建+贴图调制) | SceneEffectRain | ForwardOnly | 同上 | 默认/Off/Cull Off | HG_ENABLE_MV、SNOW_COLLISION、SNOW_FLAKE、RAIN_LIGHTING、SRP_INSTANCING_ON(sceneeffectrain.shader:25-29) | b12 |
| screenraindropfx.shader | 镜头雨滴遮罩(供 Distortion 折射) | ScreenRainDropFX | **Distortion** | 同上 | 默认/Off/Cull Off | SRP_INSTANCING_ON(screenraindropfx.shader:26) | b1 |

四者的代表片元均输出 `SV_Target0 = (RGB 颜色, 强度)`。FarRain b6/b7 和 SceneEffectRain b12 的 Target1 是恒零 MV 编码 `(0.5,0.5,1,0)`；RainSplash b3 只有 Target0，不能说四者都写 MV。RainSplash 的遮挡图取样在顶点，不在极简 b3 片元；不要把其它三者的 `_RainWetnessGlobalParam4.y > 0.5` 片元门控直接套给它。常量缓冲寄存器和偏移须逐文件核对。

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
        × (smoothstep(0.20000000298023223876953125f, 0.0f, clamp(d.x - (int(_RainMaskParams.w > 0) × clamp(0.25f / (_6.x × (1/max(_6.y, 0.01))), 0, 1)), 0, 1))   // 像素尺寸/条纹横宽修正，不是 VerticalOcclusionMap 遮挡测试
        × (1 - smoothstep(clamp(thick - 0.2, 0, 1), max(thick, 0.00048828125f), d.y))))   // 条带宽度门
        × smoothstep(130.0f, 10.0f, max(WS.y - camY, 0))        // :255 高度衰减(130m→10m)
// 垂直遮挡比较(f_b6:261-274,同 screenraindropfx §4)
// 强度(f_b6:323):
intensity = clamp((stripe × vOcclusion × clamp(max(LinearEyeDepth(场景深度) - viewZ - (wob × 7.5f), 0) × 0.100000001490116119384765625f, 0, 1)) × _RainColor.w, 0, 1)
// LinearEyeDepth = 1/(z×_ZBufferParams.z + _ZBufferParams.w),场景深度用 _DepthTextureWithWater(水面感知)——雨条纹落到地面前被裁剪
// 颜色(f_b6:324):_RainColor.rgb × 雾透过 + 雾散射(大气雾/指数雾/体积雾全链,同家族)——无 RAIN_LIGHTING(catch-all)
out = (雾后色, intensity);SV_Target1 = (0.5, 0.5, 1, 0)(恒零 MV)   // :331-332
```
keyword 差异：`RAIN_LIGHTING` 加光照（b8/b9/b12/b13，逐行尚待核）；`RAIN_WAVE` 见 R2.2。**b6 自身已包含 HG_ENABLE_MV，Target1 仍恒零；不能由关键字名推断它输出真实运动向量。**

## 2. RainSplash(地面溅射)

属性(rainsplash.shader:2-7):`_RainTex0`、`_RainTex1_ST`、`_RainParams`、`_RainColor`。

片元(Sub0_Pass0_Fragment_b3.hlsl:30-34)极简:
```
tex = _RainTex0.SampleLevel(LinearClamp, uv0, 0)
sel = _4.y × 3.0f                                    // 溅射阶段选择器(顶点给)
ch  = lerp(lerp(tex.x, tex.y, step(1.0f, sel)), tex.z, step(2.0f, sel))   // 依次选择 RGB 通道；“扩散/水花/消散”具体图案语义须看资产，shader 不能证明
out = (_RainColor.rgb, _RainColor.w × ch × _4.x)     // _4.x = 生命期 alpha
```
顶点(v_b3/b4-b6)负责 UV 动画与阶段推进 ⚠待核(未逐行);`RAIN_LIGHTING` 变体加光照 ⚠待核。

## 3. SceneEffectRain(场景雨/雪效)

属性(sceneeffectrain.shader:2-8):`_RainTex0`、`_RainParams`、`_RainColor`、`_RainDirectionParams`(0,0,0,0)、`_RainMaskParams`(0,0,0,0)。cbuffer 里另有 `_RainOffsetParams`(c5，Properties 未列；写入端待核，不能仅凭声明断定由某个脚本注入)。

片元(Sub0_Pass0_Fragment_b12.hlsl:214-242，catch-all 无 SNOW/RAIN_LIGHTING)：

> 2026-09-30 已把下方行号直接改成当前解包文件的实际位置；不再要求读者按模糊偏移换算。
```
ndc = float4(fragCoord.xy×_ScreenSize.zw×2 - 1, fragCoord.z, 1);ndc.y = -ndc.y
hworld = mul(InvViewProjMatrix,ndc);world = hworld.xyz/hworld.w                            // :216-219，必须包含实际深度
tex  = _RainTex0.SampleBias(LinearClamp, _4.zw × _RainTex0_ST.xy, mipBias)                   // :220
edge = clamp((0.5f.xx - abs(0.5f.xx - _4.xy)) × 2, 0, 1)                                  // :221
occlPos = mul(WorldToVerticalOcclusionMap,float4(world,1))
occlUV = occlPos.xy*0.5+0.5;occlUV.y = 1-occlUV.y                                         // :222-226，不是任意“旋转 UV”
vOccl = _VerticalOcclusionMap.SampleCmpLevelZero(LinearRepeat,occlUV+ScrollOffset.xy,max(occlPos.z,0.00048828125f)) // :230；门控 .y>0.5，否则1
alpha = clamp(((_RainTex0_ST.z + _RainTex0_ST.w × (tex.x×2 - 1)) × ((vOccl × edge.x × edge.y) × _5.x)) × (_RainColor.w × _5.y), 0, 1) // :236
out = (_RainColor.rgb, alpha);SV_Target1 = 恒零 MV                                        // :236-237
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

wrapper 明列的属性没有 HideInInspector；自动生成或仅 cbuffer 出现的 `_RainTex0_ST/_RainOffsetParams` 不应据此声称都有 Inspector 属性。cbuffer 顺序与 Properties 不一致（如 FarRain cbuffer 为 `_RainTex0_ST/_RainTex1_ST/_RainColor/_RainParams/_RainMaskParams`），借名需按逐 pass 布局核对。

## 6. ⚠待核汇总
1. RAIN_WAVE / RAIN_LIGHTING / SNOW_COLLISION / SNOW_FLAKE / HG_ENABLE_MV 各分支逐行(变体 b7-b13 / b13-b27 未读)。
2. farrain 顶点动画(UV 下落/wave)与 rainsplash 顶点(阶段推进)未逐行(242 行级)。
3. ScreenRainDropFX 的 Distortion 消费端(哪个 pass 读它的输出)不在 rain/ 目录内。
4. `_RainOffsetParams`(sceneeffectrain c5)在 Properties 中不存在；生产端/写入方式未确认。
5. `_6.x/_6.y`(farrain 竖直遮挡修正的输入)来自顶点插值的具体语义。

---
*仅静态转写,行号指 rain\ 下各 .shader 与变体文件;无测试/参考实现。*

---

## 补充抽取(round 2,2026-09-28)

方法:各 keyword 首个单开变体与 catch-all(b6/b12/b3)归一化 diff;sceneeffectrain 派发表全量核对。

### R2.1 sceneeffectrain 派发表全量(wrapper :26-30 五 keyword)

`HG_ENABLE_MV / SNOW_COLLISION / SNOW_FLAKE / RAIN_LIGHTING / SRP_INSTANCING_ON`;fragment 变体:b12 = catch-all,b13 = MV+SNOW_COLLISION,b14 = MV+SNOW_FLAKE,b15 = MV+双雪,b16-b19 = +RAIN_LIGHTING,b20-b27 = 再 +SRP_INSTANCING_ON(:dispatch 段逐条核对)。RAIN_LIGHTING 变体(f_b16-b19、f_b24-b27)从 ~13.8KB 膨胀到 ~79KB——引入 `type_LightDataBuffer`(b15,space0:`_DirectionalLightDirection/_DirectionalLightColor/_DirectionalLightCustomData2/_PunctualLightData[2048]`,f_b8 类似结构)、`_PunctualLightWorldToShadow[56]`、`_CSMShadowmapTex` t9(farrain b8:210-290 同构)——**即雨/雪片元走完整前向光照库** ⚠待核(逐行未抽,体量 79KB)。

### R2.2 farrain RAIN_WAVE(f_b7 vs f_b6 diff)
```
层 0:u' = abs(frac(u + _RainParams.x) - 0.5) × 2;uv0 = (u' × _RainTex0_ST.xy) + _RainTex0_ST.zw;uv0.y += _RainParams.y   // f_b7:244-246
层 1:同式用 _RainParams.z / _RainTex1_ST / _RainParams.w                                        // f_b7:248-250
col = (_RainTex0(uv0).x × _RainTex0(uv1).y) × clamp(smoothstep(130,10, max(世界y-相机y,0)) × smoothstep(130, lerp(129.899993896484375,10,_RainMaskParams.y), max(相机y-世界y,0)), 0, 1)   // f_b7:251-253
```
即 **WAVE = 两层镜像回卷 UV(相位 _RainParams.x/.z、纵向滚动 _RainParams.y/.w)交叉采样(x×y 通道)**;高度衰减与竖直遮挡/深度裁剪同 round 1(f_b7:267/:322 与 f_b6 同式)。相机水平距离衰减沿用(f_b7:273)。
**顶点坐标/MV 边界**：v_b6/v_b7 都含相机相对位置、去 TAA 抖动与上一帧矩阵计算，但 b6/b7 片元最终 Target1 仍为恒零。存在上一帧相关中间量不等于这些量最终参与了 MV 输出；不能仅凭代码声明判定通路已生效。

### R2.3 farrain 顶点(逐行,v_b6:221-238)
```
_9.x = sin(3.1415927410125732421875 / _RainTex0_ST.x) × length(本地xz) × (_RainMaskParams.z × 0.5f)      // :237(柱体绕轴摆幅:半径越大摆幅越大)
_9.y = max(dot(-视方向, 世界位-物体位), 0) × ((-1.0f) / _TransformVariables_ProjMatrix[1].y) × (_ScreenParams.z - 1.0f)   // :237(屏幕高度比例系数,供 fragment 做像素级宽度/羽化)
```
(下落动画在 fragment 的 UV 滚动里,见 round 1;顶点只贡献摆幅与尺寸系数。)

### R2.4 rainsplash 顶点动画(逐行,v_b3:215-314)
```
过期剔除:_5.x(实例寿命相位) > _RainTex1_ST.x → gl_Position = NaN(asfloat(0x7fc00000))                    // :223-229
寿命随机:_122 = (_RainParams.y + frac(_5.x × 32.0f)) × (1 + ((frac(_5.y × 128.0f) × 2 - 1) × 0.300000011920928955078125))   // :231
实例哈希:_125 = frac(floor(_122) × 0.100000001490116119384765625)                                          // :232
生成位(相机网格):_144 = ((uv×2 + (v×2-1)×0.20000000298023223876953125) + ((frac(_125±_5.x)×2-1)×0.20000000298023223876953125)) × _RainParams.x   // :233
网格对齐:_153 = floor(相机 × (0.5/_RainParams.x)) × (_RainParams.x × 2.0f);xz 越界回卷 step(:236-237)
贴地高度:世界位 → _VerticalOcclusionMapTransformCB_WorldToVerticalOcclusionMap 投影(:238-244)→ **手动 4×4 求逆(余因子展开,:245-290)** → 遮挡图高度 _458.y
贴地偏移:_473 = 地面高 + _RainTex0_ST.w × lerp(_RainParams.z, _RainParams.w, _5.x)                        // :293-295(水花板离地高度,随机)
精灵图集帧:_482 = fmod(floor(frac(_122) × _RainTex0_ST.x²), _RainTex0_ST.x²)                              // :296-297
公告板:前向水平化 → cross(前向, (0,1,0)) / cross((0,1,0), 该轴) 构造基(:298-301)，cross 的次序不能反写；角点的第二分量走世界 Y，面板不是水平 XZ 面板
尺寸:_468 = lerp(_RainParams.z, _RainParams.w, _5.x)(:293,与贴地偏移同一随机量)
UV:_7 = clamp(角点,0,1) × _RainTex0_ST.y + float2(_RainTex0_ST.y × fmod(_482, _RainTex0_ST.x), _RainTex0_ST.y × ((_RainTex0_ST.x - 1) - floor(_482 × _RainTex0_ST.y)))   // :306(帧网格,Y 翻转)
衰减:_8 = (max(1 - clamp(距相机²/(_RainParams.x)², 0, 1), 0.5), frac(_5.x + _125))(距离淡出 + 寿命相位)     // :307
```

### R2.5 sceneeffectrain SNOW_FLAKE(v_b14 vs v_b12 diff)
```
生成域:pos = ((frac((clip×0.5+0.5) + _RainOffsetParams.xyz) × 2 - 1) × 域半径)(v_b14:254;域半径 y=20.0f,外圈 40.0f,:247/:253)
回卷:越界 step 加移位(y 向 40.0f / xz 向域半径,:256-259)
下落方向:_236 = (RainDirectionParams.xz × 摆动系数, _RainDirectionParams.y);摆动系数 = clamp(1 - ((sin(frac(_RainOffsetParams.y + 相位)×6.283185482025146484375)×0.20000000298023223876953125 + 0.60000002384185791015625)×0.5)×_RainDirectionParams.w, 0, 1)(:250-251)
双频摆动:_287 = 6.283185482025146484375 × frac(y × 0.01750000007450580596923828125 + 相位1);_294 = 6.283185482025146484375 × frac(y × 0.007000000216066837310791015625 + 相位2)(:267-269)
位移/朝向:_317 = 基位 + (轴1×(cos差) + 轴2×(sin差)) × _RainDirectionParams.w × |随机|;法向含固定系数 ±0.10995574295520782470703125 / 0.0439822971820831298828125(:274-275)
公告板:cross 构造正交基朝相机(:276-283);尺寸 = lerp(_RainParams.y, _RainParams.z, 随机) × (1 - |dot(视线,法向)|) 的透视膨胀 + normalize(向量)×_RainWetnessGlobalParam4.z(:279/:284)
淡出:_414 = smoothstep(0.5, 1.5, 距相机距离)(:288);fragment 增量:alpha = clamp((ST.z + ST.w×(随机×2-1)) × (中心距 smoothstep(0.4,0,…) × 随机) × _RainColor.w × 随机)(f_b14:235-237)
```
**_RainOffsetParams 用法**(c5，生产端待核)：在已分析的 SNOW_FLAKE 顶点分支，`.xyz` 参与生成域相位偏移(v_b14:254)，`.y` 参与摆动相位(:250)。未审计全部变体，不能断言只有该分支引用。

### R2.6 sceneeffectrain SNOW_COLLISION(v_b15 vs v_b14 diff;**单独开启无顶点差异**,只与 FLAKE 组合生效)
```
把雪片位投影进 _VerticalOcclusionMap 空间(手动 4×4 求逆,余因子展开 :285-325)→ 采样遮挡高度 _588(:282)
离地高:_591 = 下落参考高 - 遮挡高(:332)
命中行为:_609 = clamp(_591 × 2, 0, 1)(:334)——离遮挡面越近,方向越偏向上向量 lerp((0,1,0), 落速, _609)(:337)
停留:落速改写 _613 = _591 × (1 + 随机×0.20000000298023223876953125)(:336);贴面 _634 = max(遮挡高 + _RainParams.z×0.5, …)(:340);位置 fmod 回卷(:333)
尺寸/透明:尺寸 lerp(0, _RainMaskParams.w, _609)(:365,贴面后缩小);alpha = (1 - clamp(_591×(-0.20000000298023223876953125)×_RainMaskParams.z, 0, 1)) × clamp((|_613-1|×10 - 0.100000001490116119384765625), 0, 1)(:369);碰撞标记 _622 = 1 - step(_613, 1)(:338-339,静止片不再摆动)
```
