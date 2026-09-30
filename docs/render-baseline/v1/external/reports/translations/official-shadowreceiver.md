# 官方 CharacterNPR_ShadowReceiver 全 pass 译读

来源:`FractalMiner\_dump_1.5.3\AllShader_1.5.3\Assets\packages\com.hg.render-pipelines\runtime\shaders\materials\characternpr\`
- `characternpr_shadowreceiver.shader`(65 行,单 SubShader 单 Pass)
- 顶点 `characternpr_shadowreceiver\Sub0_Pass0_Vertex_b2.hlsl`(231 行含 main,b3=+SRP_INSTANCING_ON)
- 片元 `characternpr_shadowreceiver\Sub0_Pass0_Fragment_b2.hlsl`(606 行含 main,b3=+SRP_INSTANCING_ON)

## 0. 结论速览(先纠一个预期)

> 2026-09-30 回源更正：接收 bias 的 clamp 上界为0.89999997615814208984375，不是 saturate；SH 信号检测是 any，不是四分量全部非零；0.95 是阴影混合量上限，不是最终RGB保证保留5%。完整验收边界见仓库 `docs/research/source-contract-audit-20260930.md`，其它未核项目仍保留。

这个 pass **不是"刘海/头发投影到脸"**——那是 `characternpr_overlayshadow`(见同目录 official-overlayshadow-b5.md)。ShadowReceiver 是**脚下/地面投影接收器**:一块静态(无蒙皮)接收网,把 ①角色高精度自阴影 atlas、②场景 CSM/ASM/云影、③Capsule AO 三路结果乘法压暗到地面;角色自阴影是"角色投到自己脚下地面"的部分,而非头发投脸。证据:接收网顶点无蒙皮、`_CircleFade` 以物体原点为中心(shader:6 注释"投影片的中心点移至角色脚下")、云影/CSM/ASM 全是场景级阴影、stencil NotEqual 32 把角色本体区域排除。

## 1. Pass 状态与变体

`characternpr_shadowreceiver.shader`:
- SubShader Tags:`QUEUE="Transparent"`(透明队列,不透明之后画)、`RenderType="HGCharacterLitShader"`(2-19 行)。
- Pass "ShadowReceiver"(`LIGHTMODE="ForwardOnly"`):
  - **`Blend Zero SrcColor, Zero SrcColor`**(19 行)→ 输出 = dst × src.rgb:纯乘法压暗,输出白色=不变。
  - `ZClip On`、`ZWrite Off`(20-21 行);无 ZTest 覆盖(默认 LEqual)。
  - `Stencil { Ref 32 / ReadMask 32 / Comp NotEqual }`(22-29 行):stencil bit5 置位的像素(角色本体,由角色各 pass 写入,如描边写 36=32|4)不接收地面阴影。
- 变体仅 2 个:`b2`(catch-all,无关键字)与 `b3`(`SRP_INSTANCING_ON`,dispatch 44-48 行)。归一化 diff 确认差异仅在实例化:b3 把 O2W/法线变换与 `_CircleFade` 圆心都改从 `UnityPerDrawArray[instance]` 读取,算法本体一致。

属性(2-10 行):`_ShadowColor`(默认 0.5 灰)、`_DisableCharacterSelfShadow`、`_DisableSceneShadow`、`_CircleFade`、`_CircleFadeDistance`(0.01-3,默认 0.5)、`_CircleFadeSmoothness`(0-3)、`_CapsuleAoColor`(默认 0.25 灰)。片元 UnityPerMaterial 布局(f_b2:245-257 行):c0=`_CircleFade/_CircleFadeDistance/_CircleFadeSmoothness/_DisableCharacterSelfShadow`,c1=`_DisableSceneShadow/...`,c2=`_ShadowColor`,c3=`_CapsuleAoColor`。

## 2. 顶点着色器(b2)

极简(208-219 行):
- 输入仅 POSITION0(裁剪前的物体空间,w 忽略)+ NORMAL0;**无蒙皮、无 UV、无切线**。
- 法线:`mul(O2W 3x3, N × (1/‖O2W 行向量‖²))` 归一化(210 行,处理非均匀缩放);位置:O2W 全变换(211 行)。
- 输出:TEXCOORD0=世界坐标、TEXCOORD1=世界法线;裁剪位置去 TAA 抖动、y 翻转(212-218 行)。
- 结论:网格本体是一块**跟随角色的静态投影板**(大概率角色脚下地面网格,由引擎随角色摆放;`_CircleFade` 的圆心即 `unity_ObjectToWorld` 平移,550 行)。

## 3. 片元着色器整洁重构(b2)

纹理:`_CharacterShadowmapTex`(t39,角色自阴影 atlas)、`_CSMShadowmapTex`(t9)、`_ASMShadowmapTex`(t11)、`_CloudShadowTex`(t8)、`_VisibilitySHRT`(t21)、`_ABLutTex`(t46)。`_167 = 0.0`(文件 5 行)只是被拼进采样坐标 float3 后又取 `.xy` 的**填充值,不是比较偏置**;真正的比较值是 `SampleCmpLevelZero` 的末参(`_225`/`_515`/`_737`,即各自空间下的深度)。接收端 bias 在几何侧做,见下。

### 3.1 角色自阴影 atlas(303-364 行)

```hlsl
charShadow = 1;
for (i = 0; i < min(_CharacterShadowParams.z, 15); i++) {        // 最多 15 张 atlas tile
    if ((asuint(_unity_WorldTransformParams.z) & asuint(_CharacterShadowBiases[i].w)) == 0)
        continue;                                                // 位掩码决定本物体受哪张 tile 影响
    fade = 1 - clamp(dot(N, _CharacterShadowLightDir[i].xyz), 0, 0.9);
    p   = pos - LightDir_i × (fade × _CharacterShadowBiases[i].x)   // 沿光方向推
        + N      × (fade × _CharacterShadowBiases[i].y);            // 沿法线抬(receiver bias,几何侧)
    uv  = (atlasOffset_i.xy + shadowUV.xy × atlasScale_i.zw) × texel;
    charShadow = min(charShadow, PCF3x3Tent9(_CharacterShadowmapTex, uv, depth));
}
```
- 9 tap tent 权重与 skin 描边片元 780-833 行、b138 点光 PCF 完全同一套实现(常数 0.16/0.08)。
- `_CharacterShadowLightDir[i]`/`_CharacterWorldToShadow[15]`/`_CharacterShadowAtlasParams[15]`/`_CharacterShadowBiases[15]` 在 ShadowData c448-c554(与 cloth 描边片元 f1088:218-223 行的同名声明互证)——这是**按角色划分的 shadow atlas 体系**,我们的 EndfieldCharacterShadowAtlas pass 已在还原 cast 侧。

### 3.2 场景阴影:CSM + ASM(间接)+ 云影(365-545 行)

- `if (_DirectionalShadowParams2.w >= 0.99)` 直接用 `_DirectionalShadowParams2.z` 作为阴影值(368-372 行,DEBUG/覆盖通道)。
- CSM:4 球分层(`_CSMShadowSplitSpheres`,计算式与 Unity `ComputeCascadeIndex` 相同)+ 分层平滑 `_DirectionalShadowParams.z/w` + `_CSMRhodesParams.x`(fade 下限);4 tap bilinear PCF on `_CSMShadowmapTex`(394-432 行)。范围外 `_647=1`。
- ASM(Ambient/间接阴影,`_458 < 1` 或 `_CSMRhodesParams.x > 0.5` 时算):indirect tile 表 `_ASMIndirectParams[128]`(half2 打包 tile 偏移)+ `_ASMWorldToShadowBaseMat` 平移替换 + 4 tap PCF on `_ASMShadowmapTex`(448-524 行)。
- 组合:`_852 = lerp(lerp(ASM, CSM, _458), min(ASM, CSM), _CSMRhodesParams.x)`(530 行)。
- 云影:`_852 > 0.001` 时两层 `_CloudShadowTex` 采样按 `smoothstep(_CloudShadowParams1.x/y, distance(pos.xz, 云中心))` 插值,再 `lerp(1, 云影, _CloudShadowParams2.z)`(532-542 行)。
- 输出 `sceneShadow`(543 行)。

### 3.3 合成与输出(546-594 行)

```hlsl
self   = lerp(lerp(1, charShadow, _DirectionalShadowParams.x), 1, _DisableCharacterSelfShadow)
scene  = lerp(lerp(1, sceneShadow, _DirectionalShadowParams.x), 1, _DisableSceneShadow)
amount = clamp(0.95 - min(self, scene), 0, 1) × _ShadowColor.a          // 546 行
if (_CircleFade > 0.5)                                                  // 548-555 行
    amount ×= smoothstep(_CircleFadeDistance + _CircleFadeSmoothness,
                         _CircleFadeDistance, distance(pos, 物体原点))
visSH = _VisibilitySHRT.SampleLevel(screenUV)                            // 556 行,屏幕空间可见性 SH
if (any(abs(visSH) > 9.9999997473787516355514526367188e-05f)) // 任一分量命中即解码；4×4矩阵迭代，558-587 行→ _1055
else _1055 = (0,0,0,1)
color = lerp( lerp(1, _ShadowColor.rgb, amount),
              _CapsuleAoColor.rgb,
              1 - clamp(luma(max(0, dot(_1055, (0,1,0,1)))), 0, 1) )     // 592 行
SV_Target0 = float4(color, 1)
```
- Capsule AO 项:`_VisibilitySHRT` 解码出的 4 维量与 `(0,1,0,1)` 点积取亮度,近似"上方环境可见度";可见度越高 lerp 权重越低。SH 体系细节(AI 全景遮蔽/可见性 SH)未在本文展开【未确认:精确语义】;当屏幕处无 SH 信号(_1055=(0,0,0,1),dot=1,权重 0)时纯走 ShadowColor 路径。
- `_ABLutTex`采样UV必须保留归一化：`u=((((length(_982)*_FHatParams.x)+_FHatParams.y)*255)+0.5)*0.00390625`，v=0.5（F576）；逐行层原漏掉×1/256，已同步修正。此处并非2×2旋转，两次结构均构造float4x4（F581/F585）。
- `0.95 - min(...)` 限制阴影混合量（之后还乘 ShadowColor.a）；最终乘色值由 ShadowColor.rgb 和 Capsule AO 共同决定，不能说必定压暗到或保留5%。

### 3.4 帧内作用

透明队列乘法压暗 → 地面/背景接收"角色投影 + 场景阴影",形成角色脚下的接触阴影与自阴影落地;`_CircleFade` 让阴影以角色脚底为圆心淡出;stencil 防止叠到角色身上。与 character shadow atlas(角色身上的高精度自阴影)分工:atlas 管角色表面,本 pass 管环境。

## 4. 未能解析的点

1. `_unity_WorldTransformParams.z` 位掩码与 `_CharacterShadowBiases[i].w` 的对应(每角色/每部件分配 atlas tile 的约定)未展开;但结构上与 15-tile atlas 一致【未确认:bit 分配表】。
2. `_VisibilitySHRT` 的来源 pass(哪一 pass 写、分辨率)不在本 shader 范围内;Capsule AO 的 SH 解码只给出结构【未确认】。
3. `_DirectionalShadowParams2.z/w` 的 DEBUG 覆盖通道由谁设置【未确认】。
4. 接收网网格的实际形状/尺寸在资产侧(本工程未持有)【未确认】。

## 5. 对我们实现的含义(对照 `FractalMiner\Assets\EndfieldShaderPack\EndfieldCharacterLit.shader`)

1. 官方该shader的接收路径是独立接收网+乘法pass；不能据此排除整个引擎还有其它地面阴影路径。接收侧应采样cast生产的深度atlas（`_CharacterShadowmapTex`），不是屏幕空间resolve产生的阴影因子纹理；PCF depth/atlas布局/逐对象mask依该shader独立契约。
2. **Receiver bias 在几何侧**：fade=`1-clamp(dot(N,L),0,0.89999997615814208984375f)`，沿光方向推/沿法线抬(306-309行)。变换后比较深度还做 `max(z,0.00999999977648258209228515625f)` 与范围/NaN检查，不能用 `1-saturate(N·L)` 替换，也不能因匿名填充值为0就省略这些步骤。
3. `_CircleFade`(距离 smoothstep + 半径/柔度两个属性)是角色影子淡出的官方做法,实现成本极低,建议补。
4. `0.95-min(self,scene)`、`_ShadowColor.a`及SH→CapsuleAO共同决定最终乘色。只有确认输入无SH信号或该能力不在当前作用域时，才可使用源码无信号分支；“尚未实现所以填零”是有标记的缺省近似，不是官方完整还原。
5. 刘海/头发投脸用 overlayshadow,不要用本 pass 实现(见另一份报告)。

---
*生成说明:仅静态阅读,未运行游戏/未截帧。行号指 `...\materials\characternpr\characternpr_shadowreceiver\` 下文件与 `characternpr_shadowreceiver.shader`。*
