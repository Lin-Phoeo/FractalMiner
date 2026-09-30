# C6 交接:官方描边 / 阴影通道 shader 译读(2026-09-28)

> 2026-09-30 后续回源审查：本交接为历史工作记录，不是全项认证。原先接受/抽查通过未覆盖下列已发现问题：描边方向矩阵不是视图旋转而是NonJitteredVP的3×3；有符号半角不得取abs；切线标量0须取+1；蒙皮80.x组同时作用于N/T/当前P，80.y仅输出_406，MV条件<1时选_405。Overlay去斜不是正交，Ref4/20为互斥分类，PreDepth的CPU调度仍未知。ShadowReceiver LUT归一化必须×1/256，SH是4×4运算，0.95限混合量不保证保留5%RGB。三份分析和三份逐行层均已同步这些更正；请勿继续引用旧“全部命中”作为完整性门禁。

## 做了什么

纯静态阅读 `_dump_1.5.3` 反编译 HLSL 与 .shader 文本(未克隆 Ruri.ShaderDecompiler——现有 HLSL 可读性足够,按任务规则不折腾;未运行游戏、未截帧、未动任何工程文件),产出三份译读报告,每份末尾含"对我们实现的含义"。

## 产物

| 文件 | 内容 |
|---|---|
| `D:\EndfieldTechLib\reports\translations\official-outline-skin-b273.md` | characternpr_skin CharacterOutline(顶点+片元 995 行逐段)、`_44_Stripped_N`→属性名映射表(带证据)、b274/b283/b311 差异、cloth/hair/eye 差异 |
| `D:\EndfieldTechLib\reports\translations\official-shadowreceiver.md` | ShadowReceiver 全 pass:脚下投影接收器(自阴影 atlas + CSM/ASM/云影 + CapsuleAO + CircleFade) |
| `D:\EndfieldTechLib\reports\translations\official-overlayshadow-b5.md` | OverlayShadow 两 pass:刘海/头发投脸(PreDepth b5 抖动+光角偏移顶点、Pass1 乘法叠色、DISABLE_DRAW_UNDER_HAIR 落点) |
| `line-by-line\outline-skin-b273.md` | **逐行译读**:skin 描边顶点(497 行)+ 片元(995 行)全量,每行可执行代码一条目,声明区按段汇总;含 main() FragCoord.w 反演机制说明(_300 = 线性视深的依据) |
| `line-by-line\shadowreceiver-b2.md` | 逐行译读:ShadowReceiver 顶点+片元(222+590 行),PCF/atlas/CSM/ASM/云影/SH 解码逐行 |
| `line-by-line\overlayshadow-pass0-b5.md` | 逐行译读:OverlayShadow PreDepth 顶点+片元(304+49 行),去斜投影/光角偏移/IGN 抖动逐行 |
| `evidence\` 子目录 | 12 个 diff 文件(fc 原始 + 变量名归一化后),供复核 |

## 核心发现(给 Claude 的 TL;DR)

1. **官方描边片元是"缩水 ForwardLit 全打光"**,不是纯色壳:环境 IV、方向光、SS 阴影、点光分箱、雾、VFX 调色全在;albedo=BaseMap×_BaseColor×_OutlineColorBrightness→_OutlineColorSaturation→覆盖色,阴影侧 albedo 用 _ShadowColorBrightness/_ShadowColorSaturation(b138 cbuffer 具名借名);**无高光/SSS**。
2. **打光法线来自 GBuffer**:片元把未外扩 positionRWS 重投影回屏幕,`Load _GBufferTexture1` 八面体解码——描边像素借用"挤出源像素"的法线。写入方是各部件 **PreGBuffer** pass(eye 的 PreGBuffer 片元 = 5 路 MRT:0/MV/对象ID/八面体法线/albedo)。
3. **eye 没有 CharacterOutline pass**(pass 表:ForwardLit/PreGBuffer/RTR/ShadowCaster/TSF,已复核)。b64 是 PreGBuffer,不是描边。
4. b273 是 Pass1 catch-all;捕获帧材质 `_DIFF_RAMP_ON` 开着(同 key 在 Pass1 也声明)→ 运行时描边大概率走 **b274(ramp 贴图版:ramp.w 作明暗 + ramp.rgb 经 chroma 加权染色)**【推断】。
5. b283(_OUTLINE_MASK)顶点采样调试名 `_SDFMask`(b284 一致,命名可信):R 乘宽度、G 乘深度偏移;片元"albedo"槽恢复名跨变体漂移(b283 t2=_DiffRampMap、b284 t2=_EmissionMap/t3=_DiffRampMap),与属性表 `_OutlineMask` 对不上【未确认】。
6. b311(DITHER)在描边 pass 完全无操作;但 overlay shadow 的 DITHER 在 **Pass0 与 Pass1 都**插入 IGN discard。
7. hair 描边 CP8 边缘光门控 = **采样 _CameraDepthTexture(t46)算深度差**(smoothstep(0.10,0.20));skin/cloth 用视角门控。cloth/hair 另有逆光 SDF 项 + smoothstep(0.25,1.0) ramp、CP2/CP5、alpha 输出(_OutlineTransparent)、BaseMap.a×_BaseColor.a 调光。
8. ShadowReceiver ≠ 刘海投脸:它是**脚下投影接收器**(无蒙皮静态网、乘法混合、stencil NotEqual 32、receiver bias 在几何侧;`_167=0` 只是采样坐标填充,比较值是 SampleCmp 末参)。刘海投脸是 OverlayShadow(蒙皮网格、PreDepth 去斜投影+`_ShadowAngleRange` 光角平移+IGN 抖动、Pass1 `Blend Zero SrcColor` 乘法)。
9. 官方宽度模型按V453逐字保留VP3×3法线投影、_543有符号多项式近似半角、距离clamp及常量；V454–458是逐轴裁剪空间下限，换成实际像素还需目标尺寸及透视除法，不能直接叫min(dist,π/fovY)像素；V464/466另有深度偏移。
10. 八面体/切线解包系数 = **1/511**(非 2/1023);10bit 有符号化后 [-512,511],负端略超 [-1,1]。
11. Pass0 与 Pass1 的材质 cbuffer 是**两个独立结构**(共享 c0-c13 前缀:VFX 组/_BaseColor/_BaseMap_ST/_ShadowColorBrightness/Saturation;尾部各自定义),跨 pass 借名仅对共享前缀成立;各部件间 cbuffer 也不通用。

## 复现方式

全部结论可由以下只读操作复现(命令行,PowerShell 可用):
1. 读三个 .hlsl 与对应 .shader(路径见各报告头部);逐行层 `line-by-line\*.md` 的行号与 .hlsl 一一对应,可直接抽查。
2. 变体差异:`fc /n` 原始 diff;或 PowerShell 归一化(`-replace '_[0-9]{1,4}\b','_N'` 后 `Compare-Object`)消 SPIR-V-Cross 重编号噪声,evidence\ 里的 `_nf_*.txt` 即此产物。
3. 属性名证据:`characternpr_skin.shader:71-81`(属性)、b138 Pass0 具名 `type_UnityPerMaterial`(b138:263-319,共享前缀借名依据)、各部件 shader 的 `Name "..."` 与 dispatch `#elif` 行。

## 【未确认】清单(汇总)

- 受光侧亮度/饱和度的公式偏移c14.z/w可回源确认；与UI属性名对应主要来自Properties顺序借名，尚不能认证cbuffer ABI。阴影侧c4.z/w同样需跨pass实际上传契约，不能将数学同槽直接外推所有变体。
- c12.x(疑 `_SkinRimOffScale`)、c13.xyz(疑 `_SDFRimColor.rgb`):共享前缀借名,语义吻合但 Pass1 cbuffer 独立成结构。
- c15.w/c16(覆盖使能/覆盖色)、c6.w(`_BaseColor.a`,布料/头发描边用):无 UI 属性对应,疑 C# 驱动。
- b283/b284 顶点 `_SDFMask` 命名可信,但片元"albedo"槽恢复名漂移(b283=_DiffRampMap、b284=_EmissionMap)+ 与 `_OutlineMask` 属性的关系:运行时绑定需验证。
- 运行时描边变体 b273 vs b274(无捕获常量)。
- GBufferTexture1 与 PreGBuffer MRT 的精确对应(编码互逆是强推断)。
- ShadowReceiver 的 `_VisibilitySHRT`/CapsuleAO SH 解码语义、`_CharacterShadowBiases[i].w` bit 分配表。
- OverlayShadow 的 `PerDraw.Stripped_64.x/y/z` 抖动语义、Pass1 t37(匿名 `_29`)身份与 DISABLE_DRAW_UNDER_HAIR 的极性(现读法:关键字去掉"t37.w==1 不画"的测试,极性与属性名相反)。
- `_ShadowAngleRange` 的 C# 侧换算。

## 边界遵守

只写 `D:\EndfieldTechLib\`;FractalMiner/_EndfieldRefs 只读;未 git commit/push 任何仓库;未运行 Unity/游戏/截帧;未动 `_unity_bridge.bat`;未克隆大仓库(555me/EndfieldAssets 等未触碰)。
