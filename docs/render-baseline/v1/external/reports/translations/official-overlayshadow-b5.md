# 官方 CharacterNPR_OverlayShadow 译读(Sub0_Pass0_Fragment_b5 + 配套顶点)

来源:`FractalMiner\_dump_1.5.3\AllShader_1.5.3\Assets\packages\com.hg.render-pipelines\runtime\shaders\materials\characternpr\`
- `characternpr_overlayshadow.shader`(134 行,两个 pass)
- 顶点 `characternpr_overlayshadow\Sub0_Pass0_Vertex_b5.hlsl`(317 行，含 main)
- 片元 `characternpr_overlayshadow\Sub0_Pass0_Fragment_b5.hlsl`(57 行，含 main)

## 0. 结论速览

> 2026-09-30 回源更正：本文为静态译读，不代表工程已正确接入。投影去斜不等于改成正交投影；模板 Ref=4/20 是两个分类，不是一个“覆盖脸+虹膜”的包容开关；已有官方蒙皮叠影网格应直接复用，禁止为了配合本文建议重新造替代网格。完整边界见仓库 `docs/research/source-contract-audit-20260930.md`。

OverlayShadow = **刘海/头发在脸上的投影**(任务背景里的"刘海阴影")本体,分两个 pass:
- **Pass0 "OverlayShadowPreDepth"**:把投影网格的深度(带逐对象抖动 discard、随光角度偏移)写进深度缓冲,供 Pass1 做遮挡。b5 = `DISABLE_DRAW_UNDER_HAIR + DITHER + SRP_INSTANCING_ON` 变体。
- **Pass1 "OverlayShadow"**:乘法混合(`Blend Zero SrcColor`)把 BaseMap 定义的阴影图案叠到脸上,含点光源与雾,`_ShadowOverIris` 用 stencil 控制是否盖住虹膜。

两个 pass 都挂在角色网格渲染流程内(网格 = 脸上的投影板,顶点走角色骨骼蒙皮),区别于无蒙皮的 ShadowReceiver(地面)。

## 1. Pass 状态与属性

`characternpr_overlayshadow.shader:2-13` 属性:`_BaseColor`、`_BaseMap`(阴影图案,默认 white)、`_UseGrayAsAlpha`、`_ShadowAngleRange`(Range(-0.01,0.01),阴影随光角偏移幅度)、`_EnablePreDepthPass`、`_ShadowOverIris`(Enum(Off=4, On=20))、`_DisableDrawUnderHair [Toggle(DISABLE_DRAW_UNDER_HAIR)]`、`_EnableVFXColorAdjustment`、`_ColorAdjustmentColorBlend`、`_EnableDither [Toggle(DITHER)]`。

SubShader Tags:`QUEUE="Transparent-100"`(排在 Transparent 队列极早处)、`RenderType="HGCharacterLitShader"`。

| | Pass0 "OverlayShadowPreDepth" | Pass1 "OverlayShadow" |
|---|---|---|
| LIGHTMODE | `ForwardOnly`(20-35 行) | `ForwardCharacterOnly`(76-92 行) |
| Blend | `Zero One, Zero One`(丢弃颜色,只写深度) | **`Zero SrcColor, One One`**(rgb 乘法、alpha 加法) |
| ZWrite | 默认 On(未覆盖) | Off |
| ZClip | On | On |
| Stencil | `Ref [_ShadowOverIris] / ReadMask 20 / Comp Equal`(24-31 行) | 同左(81-88 行) |
| 关键字 | `SRP_INSTANCING_ON / DISABLE_DRAW_UNDER_HAIR / DITHER` | 同左 |

变体:Pass0 = b2(catch-all)/b3(+DISABLE)/b4(+DITHER)/b5(+both);Pass1 = b10/b11/b12/b13。ReadMask20在捕获帧将skin36选择成4、eye52选择成20；Ref4与Ref20是互斥分类选择，不是Ref20包含脸与虹膜。wrapper默认ZTest/未覆盖ZWrite只描述ShaderLab文本，具体API最终深度状态应另以捕获为准。

**PreDepth调度缺口**：`_EnablePreDepthPass`仅出现在Properties（wrapper:7），没有shader表达式消费，实际CPU/管线是否启用及绘制次数未闭合。捕获眼部叠影968/971与头发PreDepth993/叠影997表明不能要求每种叠影固定“两个pass都画”；保留开关生产端与调度证据缺口。

## 2. Pass0 顶点着色器(b5,238-303 行)

```hlsl
// 1) 蒙皮:槽位布局又不同 —— 权重 TEXCOORD? 不,本 pass:权重=TANGENT0(float4)、索引=COLOR0(uint4)
posOS = 蒙皮(POSITION0, TANGENT0 权重, COLOR0 索引, _VertexSkinMatrices)      // 240-290 行
posWS = mul(O2W, posOS) - camPos(相机相对)                                    // 291 行
posVS = mul(ViewMatrix 3x3, posWS)                                            // 292 行
// 2) 投影去斜:清零 ProjMatrix 的 4 个非对角项
P2 = ProjMatrix; P2[1].x = P2[3].x = P2[0].y = P2[3].y = 0                    // 293-297 行
// 3) 视图空间 x 按"光方向 x 分量"平移(刘海阴影随光角度偏移)
shadowShift = -DirectionalLightDirection.x × _ShadowAngleRange                // 298 行
clip = mul(P2, float4(posVS.x + shadowShift, posVS.yz, 1))                      // 只加一次，不先修改posVS.x又加偏移
clip.xy += _TaaJitterStrength.zw × (2,-2) × clip.w                            // 299 行,加回抖动与主深度一致
gl_Position = (clip.x, -clip.y, clip.z, clip.w)                               // 300-302 行
```

要点:
- **投影去斜**(293-297 行)清零指定矩阵项，但仍保留透视深度及齐次除法；不是改成正交相机，也不能仅凭这四项清零保证任意视角的图案稳定。
- 蒙皮槽位与描边 pass(TEXCOORD2/3)不同(权重 TANGENT0、索引 COLOR0),逐 pass 自定义 layout,做资产导入时按 pass 分配。
- b2↔b5 顶点**完全一致**(除头注释):DISABLE_DRAW_UNDER_HAIR 与 DITHER 都不改动顶点。

## 3. Pass0 片元 b5(全文 38-47 行)

```hlsl
noise = frac(52.9829178 × frac(dot(fragCoord.xy, (0.06711056, 0.00583715))))   // Jimenez 交错梯度噪声
if ( min( PerDraw.Stripped_64.x - (PerDraw.Stripped_64.x >= 0 ? |noise| : -|noise|),   // 逐对象抖动阈值(保符号减噪声幅度)
          (1 - max(PerDraw.Stripped_64.y, PerDraw.Stripped_64.z)) - noise ) < 0 )
    discard;
SV_Target0 = 1;                                                                // 纯深度写
```
- `Stripped_64.x` = 逐对象抖动阈值(对象整体淡出/淡入的 dither alpha;第一项是 `x - sign(x)·|noise|`,保持减法方向与阈值符号一致);`Stripped_64.y/z` 与 skin 描边里按 MV scale 解释的字段同 offset,此处复用为第二重抖动条件,精确语义【未确认】(若 y=z=1,第二项恒 ≤0 会导致全 discard,故 DITHER 变体应只在 y/z<1 的对象上启用)。
- **同一个 IGN discard 块也出现在 Pass1 的 DITHER 变体(b12/b13)片元开头**(b10↔b12 归一化 diff 的唯一新增)——淡出同时作用于深度与颜色两个 pass。
- 无 DITHER 的 b2/b3 片元仅 18/≤30 行(无 discard 直写 1);DISABLE_DRAW_UNDER_HAIR 在 Pass0 无任何代码差异(b2↔b3↔b5 顶点一致、片元除 DITHER 块外一致)——该关键字的真实效果在 **Pass1**(见 §5)。
- 与 `Blend Zero One` 配合:Pass0 只留深度,配合默认 ZWrite On 完成"抖动镂空 + 带光角偏移的深度预写"。

## 4. Pass1 "OverlayShadow" 概述(b10 catch-all,478 行;本文按任务范围只做功能概述)

- 输入:投影板 UV(`_BaseMap_ST`,c3)、蒙皮位置同 Pass0(顶点 b10)。
- 主体(f_b10):`_BaseMap.SampleBias(LinearClamp, uv, mipBias)`(252 行)→ `_200 = lerp(map, (1,1,1,map.x 灰度), _UseGrayAsAlpha) × _BaseColor`(278 行,即 alpha 源 = UseGrayAsAlpha ? BaseMap 灰度 : BaseMap.a,再乘 _BaseColor.a)→ 进入与角色 ForwardLit 同构的**点光源衰减/阴影循环**(286-419 行,阴影贴图采样同 shadowreceiver)与**体积雾**(427 行起)。
- 输出478行必须保留完整双层lerp：`rgb=lerp(1,lerp(_921.rgb,_ColorAdjustmentColorBlend.rgb,_EnableVFXColorAdjustment*_ColorAdjustmentColorBlend.a),(_921.a*_BaseColor.a)*((1-_EnableVFXColorAdjustment)+(1-_ColorAdjustmentColorBlend.a)*_EnableVFXColorAdjustment))`，输出alpha为`_921.a`（479行）。`_921.a`已包含第一次`_BaseColor.a`，外层再乘一次不能合并丢失。雾路径471行单独修改alpha，其完整衰减表达式是本概述未逐项转写的保留缺口。

## 5. DISABLE_DRAW_UNDER_HAIR 的真实位置(Pass1 b12 vs b13)

归一化 diff(唯一差异,f_b12:422 行 vs b13 对应行):
```
b12(无关键字): tex  = _29.Load(int3(pixel, 0))            // t37,space0,匿名纹理(引擎侧 RT,无属性名)
               alpha = (tex.w == 1.0) ? 0 : (baseColor后alpha × (1 - 点光累加.r))
b13(有关键字): alpha = baseColor后alpha × (1 - 点光累加.r)   // 不再 Load t37,无 w==1 判零
```
其中"baseColor后alpha"即 §4 的 `_200.w`,`点光累加.r` 是该片元点光源循环的累加色 R 分量(f_b12:286-290 行初始化、循环内累加)。即:
- **关键字打开 = 去掉一次屏幕像素掩码测试**("t37.w==1 的像素不画阴影");
- t37 是匿名全局纹理(`_29`,t37,space0),不是材质属性,身份未知(疑为头发覆盖/描边类 RT)【未确认】;
- 按属性名 `_DisableDrawUnderHair`("关闭在头发下绘制")推断 t37.w==1 标记"头发下"区域,但这样默认行为反而是"不在头发下画"、打开关键字变成"照画",**极性与名字相反**【未确认,需运行时验证 t37 内容与开关方向】。

## 6. 未能解析的点

1. `PerDraw.Stripped_64.x/y/z` 在本 pass 的确切含义(x=抖动阈值是强推断;y/z 复用 MV scale 槽位)【未确认】。
2. Pass1 的 t37(匿名 `_29`)纹理身份与 DISABLE_DRAW_UNDER_HAIR 的极性(§5)【未确认】。
3. 投影板网格(蒙皮权重/索引绑在 TANGENT0/COLOR0)的具体资产形态不在 dump 内【未确认】。
4. `_ShadowAngleRange` 只有 view-x 平移一项,Range ±0.01 极小,推测还有 C# 侧把光方向角换算进该值【未确认】。

## 7. 对我们实现的含义(对照 `FractalMiner\Assets\EndfieldShaderPack\EndfieldCharacterLit.shader`)

我们工程当前没有等价 pass(刘海阴影/脸上叠影缺失;描边 pass 1004-1087 行、atlas cast pass 1098 行起)。建议的还原顺序:

1. **数据**：优先复用现有解包的眼白/头发叠影蒙皮网格、贴图、原材质属性；本工程已有这类 draw 的捕获证据，不能自行造一张近似投影板替代。捕获输入布局与 Unity SMR 导入布局是不同契约，必须确认解码、权重和骨索引，不是直接换语义名。
2. **两个pass算法结构**分别保留：启用并调度PreDepth时去斜投影/光角平移/可选IGN discard，再以正确状态绘制乘法叠色。不要将CPU未知的`_EnablePreDepthPass`调度推定为全部叠影必走；先依据每个实际draw/材质明确是否预写。
3. **stencil 方案**：保持 ReadMask=20、Comp Equal。捕获帧6411 中 skin 写36、eye写52，分别 `&20` 得4、20；叠影事件968/971分别用Ref4/20。这是两个分类选择，Ref20不会同时覆盖普通皮肤。把 ReadMask 改0是禁用模板测试的替代方案，不是官方还原，不能作为已验收实现。
4. **抖动分支**：公式和逐对象槽位保留，`Stripped_64.x/y/z`的精确生产语义仍未确认，不能直接认证为Unity现成PerObject淡出接口。只在实际不启用DITHER的变体可略过；缺输入不能当作官方完整实现。
5. 与 ShadowReceiver 的分工要记牢:**脸上投影视=OverlayShadow(蒙皮网格、Transparent-100 队列、乘法),脚下投影=ShadowReceiver(静态网格、Transparent 队列、乘法+stencil 反遮)**,两者不要合并。

---
*生成说明:仅静态阅读,未运行游戏/未截帧。行号指 `...\materials\characternpr\characternpr_overlayshadow\` 下文件与 `characternpr_overlayshadow.shader`。*
