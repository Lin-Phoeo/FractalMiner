# 官方后处理栈补充抽取(TAAU / SMAA / DOF / 体积光 / 镜头光晕 / 变形光条 / 锐化 / 磨砂玻璃 / UI 模糊)

来源:`_dump_1.5.3/AllShader_1.5.3/Assets/packages/com.hg.render-pipelines/runtime/shaders/postprocessing/` 下 `taau\`、`smaa\`、`dof\`、`lightshaft\`、`anamorphicstreaks\`、`sharpen\`、`frostedglassblur.shader`、`lensflaredatadriven\`、`uiimageblur.shader`。**注意:taaudilation/taaumaskdilation/smaa/anamorphicstreaks 的代码全部内联在 .shader wrapper 里(无外部 .hlsl 变体);dof/lightshaft/lensflare 部分内联部分外置**。

**本文是家族/代表变体的源码导读，不是实际运行时pass图**；不含参考实现。下列模块是否启用、顺序、资源生产/历史更新必须另行有捕获或生产代码证据，不能因为wrapper均存在就全部串入角色展示链。顶点形态与Y翻转也以每个对应源码为准，不把全屏三角形概括扩到lensflare quad等其他模块。

---

## 1. TAAU(时域上采样/抗锯齿,HGRP/TAAU*)

### 1.1 TAAUDilation(taau/taaudilation.shader,单 Pass 全内联)

- 状态:ZWrite Off/Cull Off(:11-12),无 Blend。双 MRT 输出:SV_Target0=深度,SV_Target1=float4(修正后 MV,.z=打包标志)。
- 资源:`type_TransformVariables` b5(唯一被读:`_ReprojectionMatrix` c69,taaudilation.shader:82)、`type_TAAUConstants` b6(`_TAAUParams1` c1、`_TAAUParams6` c6,:91/:96);纹理 `_SceneDepth` t1、`_PrevDilatedMV` t2、`_PrevDilatedDepth` t3、`_MotionVector` t4(:103-106)。顶点**无 UV 输出**(输入仅 gl_FragCoord,:30-43)。
- **深度膨胀(4×GatherRed，9点取最大device-depth)**(taaudilation.shader:128–176)：从0开始串行max并记录偏移。不能称“最远”：reversed-Z下最大值表示最近表面；具体正反Z必须绑定对应投影/附件契约。`TAAUParams6.zw`只能确认坐标步长，不能仅凭变量推断半分辨率。
- **MV 二次膨胀(taaudilation.shader:177-199)**:`mv = _MotionVector.Load(选中像素)`(:177);**速度放大曲线** `e(mv) = ((|mv|×2-1)²)² × sign(mv-0.5)`(:181-183,四阶曲线,输出像素级位移);`_192 = e(mv) × TAAUParams6.xy`(:184);异常标志 `_177 = |mv.w - 0.300000011920928955078125| < 0.100000001490116119384765625`(:179)。
- **重投影深度差**(taaudilation.shader:186-199):`clip = (ndc×2-1, 深度, 1)` 经 `_ReprojectionMatrix`(:187-189),`disoccl = (PrevDilatedDepth.Load(膨胀点).x - clip.z/clip.w) > TAAUParams1.y`(:199 内);**打包标志**写回 `_170.z`(= MV .z)(:199):`bit1 = clamp( clamp(disoccl + |异常标志对(当前,历史)|×smoothstep(1e-4, 0.0005000000237487256526947021484375, |e_now - e_prev|) + |(mv.w>0.89999997615814208984375)-(prev.w>0.89999997615814208984375)|, 0,1) × (1-_177) )`;`bit2 = ((mv.z - (prev.z×1023+0.5 截断到 u32 再 &1)) < 0)`(:199,即**历史帧奇偶校验位**);打包 `z = (bitflags + 0.5) × 0.000977517105638980865478515625`(:199,≈1/1023 编码)。

### 1.2 TAAUMaskDilation(taau/taaumaskdilation.shader,单 Pass 全内联)

单输出 float:`mask = max(5 点采样 _CurrDilatedMV(t1).z) > 0`(taaumaskdilation.shader:97,5 点 = 中心 + TAAUParams6.zw 的 ±(1,1)/(-1,1)/(1,-1) 对角)。TAAUParams6 c6(:73)。

### 1.3 TAAUResolve(taau/taauresolve.shader + taauresolve\Sub0_Pass0_Fragment_b{3,4,5}.hlsl)

- keyword(:19-20):`HG_TAAU_NEXTGEN_MODE`→b4、`HG_TAAU_PERFORMANCE_MODE`→b5、catch-all→b3(**已全文**,426 行)。状态:ZWrite Off/Cull Off(:11-12),无 Blend。
- 资源(b3):`type_TAAUConstants` b7(c0-c8 = TAAUParams0-8 + `Kernel3x3Weight[3]` c9,taauresolve\Sub0_Pass0_Fragment_b3.hlsl:153-165);ShaderVariablesGlobal b8 中 `_TaaFrameInfo` c18、`_TaaJitterStrength` c19(:20-21);纹理 `_SceneColorTexture` t3、`_SceneDepth` t2、`_CurrDilatedMV` t6、`_CurrDilatedMask` t5、`_HistorySceneColor` t4(:169-173)。
- **抖动/像素映射**(:190-196):`uvLow = fragCoord.xy × TAAUParams7.zw`(低分辨率 UV);`uvFull = fragCoord.xy × TAAUParams8.xy`;`采样点 = floor(clamp(uvFull - _TaaJitterStrength.xy, 0.5, TAAUParams6.xy - 0.5))`(:194);深度双线性采样(:196)。
- **速度位移曲线**(:199-202):同 dilation 的四阶曲线 `e(mv) = ((|mv|×2-1)²)² × sign(mv-0.5)`,`_208 = uvLow - e(mv)`(:202,历史 UV)。
- **3×3 邻域矩(YCoCg 形)**(:209-264):9 点 `clamp(采样点±1, 0, TAAUParams6.xy)` Load `_SceneColorTexture`;每点 `m0 = dot(c,(1,2,1))`、`m1 = dot(c,(2,0,-2))`、`m2 = dot(c,(-1,2,-1))`,权重 `1/(m0×TAAUParams4.w + 4)`(:214 等);**加权平均核 `Kernel3x3Weight[3]`**(cbuffer c9,3×float4=9 权重,:263)。
- **Catmull-Rom 5-tap 历史滤波**(:267-301):对 `_208×TAAUParams7.xy` 做标准 Catmull-Rom 系数(`_488 = t²-t³/2-t/2` 型四段多项式,:271-276,逐字: `_488 = t² - ((t³+t)×0.5)`、`_492 = t³×1.5 - t²×2.5 + 1`、`_494 = (t³-t²)×0.5`、`_497 = 1 - _488 - _492 - _494`);5 点(`_504/_505/_506` 偏移)采样 `_HistorySceneColor`(**sampler_LinearRepeat**),每点先**亮度归一** `c/(1+luma709(c))`(luma 权重 0.2125999927520751953125/0.715200006961822509765625/0.072200000286102294921875,:297)再加权,最后 `/(Σw)` 并**反归一** `c/(1-luma)` 夹到 `center×0.20000000298023223876953125 ~ center×1.7999999523162841796875`(:301-304,即 **0.2/1.8 历史夹取**)。
- **邻域一致性位掩码检验**(:315-390):9 邻域中与中心比 `max/min ∈ (0,1.89999997615814208984375)` 者置 bit(i)(:335-344);若中心在其余点的 [min,max] 内 → 一致(:355);查表 `_139[4] = {27u, 54u, 216u, 432u}`(:8,= 二进制 11011/110110/11011000/110110000 的"单侧连线"掩码)判定是否为孤立结构(:367)。
- **混合因子级联**(:391-410):`histWeight = max(一致性, history.a×0.89999997615814208984375) × max(0, 1 - mask命中 - (动标志+TAAUParams5.x+奇偶位 clamp) - 越界(边缘 TAAUParams7.zw 内缩判界 :310-311) - TAAUParams1.w - (|位移|>0.300000011920928955078125) - 速度异常 - TAAUParams2.w)`(:391);`_720 = step(0.100000001490116119384765625, histWeight)`(:392)。
- **方差裁剪**(:394-408):9 点均值/方差(`0.111111111938953399658203125`),`σ' = σ × (1.25 - smoothstep(20, 40, σ)×0.699999988079071044921875)`(:407),矩空间夹取 `clamp(_574, min(μ-σ', prev), max(μ+σ', prev))`(:408)。
- **最终混合 + YCoCg 反变换**(:409-414):混合因子 = 5 层 lerp 级联(`TAAUParams0.z → TAAUParams0.w(by depth×速度×256×depthA) → 0.819999992847442626953125(by 边缘距离) → TAAUParams4.x(by 越界+异常) → TAAUParams2.z(by 动) → 0.89999997615814208984375(by histWeight)`,:409);矩空间混合后 `_768 = c/max(1-c.x, 0.001000000047497451305389404296875)`,RGB = `((y0+y1-y2), (y0+y2), (y0-y1-y2))×0.25`(:410-414);alpha = histWeight(:414)。
- b4/b5(NEXTGEN/PERFORMANCE)未逐行 ⚠待核(尺寸 21.3KB/17.4KB vs b3 24KB,疑为简化核/免 Catmull-Rom 档)。

---

## 2. SMAA(smaa/smaa.shader,10 Pass 全内联,无 keyword、无变体——CPU 按 Pass 号选)

所有 Pass:ZTest Always/ZWrite Off/Cull Off。**Pass 表**(:3/:76/:212/:348/:484/:620/:857/:1348/:1839/:2330):

| Pass | 内容 | 函数体行 |
|---|---|---|
| 0 | **清屏**(edges RT 初始化)`float4(0,0,0,1)` | :59-62 |
| 1 | **颜色边缘检测 阈值 0.1500000059604644775390625** | :166-196 |
| 2 | 同式,阈值 **0.100000001490116119384765625** | :302-332 |
| 3 | 同式,阈值 **0.100000001490116119384765625**(与 Pass2 相同 ⚠待核差异) | :438-468 |
| 4 | 同式,阈值 **0.0500000007450580596923828125** | :574-604 |
| 5 | **权重计算(正交,简版)**,函数体 :724-840(已全文) | :724-840 |
| 6 | 权重计算(**+对角线+圆角**) | :965-1347(增量段 :1018-1247 已抽) |
| 7 | 同 Pass6(结构逐行同构 ⚠待核用途) | :1456-1838 |
| 8 | 同 Pass6(结构逐行同构 ⚠待核用途) | :1947-2329 |
| 9 | **SMAA Neighborhood Blending** | :2426-2535 |

- **边缘检测公式**(以 Pass1 :166-196 为准,4 Pass 仅阈值不同):取 4 个 TEXCOORD1 偏移(顶点提供的 SMAA 标准邻域偏移),`L = max3(|c - c_left|), max3(|c - c_right|)`(:172-181);`edge = step(threshold.xx, L.xy)`(:181);**双边缘局部对比修正**:再采 4 邻域差(:186-193),`edge ×= step(max(L.LR, L.TB).xx, L.xy × 2.0f)`(:195,即 SMAA 经典 ×2 规则);无边缘则 `discard`(:184)。
- **权重计算 Pass5 正交段**(:724-840,全文):读 `_EdgeTex` t3;**横向搜索循环**(:736-749):从 `TEXCOORD2` 偏移起步,步长 `±2×MainTex_TexelSize`(:742),终止条件 `_125.y > 0.828100025653839111328125f 且 _125.x == 0`(边缘值交叉采样,:739)且未越 `TEXCOORD2[2]` 搜索界;**SearchTex 距离补偿**(:750):`d = TexelSize.x × mad(-2.007874011993408203125, SearchTex.Sample(mad((0.5,-2), e, (0.0078125, 2.03125))).w, 3.25) + 搜索位移`;**AreaTex 坐标**(:774):`uv = (0.0062500000931322574615478515625, 0.001785714295692741870880126953125) × (16 × round(边缘×4) + sqrt(|round(TexelSize.zz×d - 相对偏移)|)) + (0.00312500004656612873077392578125, 0.0008928571478463709354400634765625)`,再加 `_27.y = mad(0.14285714924335479736328125, 0, _27.y)`(:775);`w_left = _AreaTex(uv).rg`(:776);右侧/上/下同式(:754-837,右侧 SearchTex 偏移 (0.5234375, 2.03125)、系数 -TexelSize);输出 float4(左.rg, 上.rg)(:833)。
- **Pass6 对角线/圆角增量**(:1018-1247):**对角搜索**步长 `±(1,-1)×TexelSize`(:1024),上限 **7.0f 步**(:1022),交叉值 `dot(edge,0.5)`(:1027);对角面积 `if (左长+对角位移 > 2.0f)`(:1039):**圆角测试** `_262 = e × |e×5.0f - 3.75f|` + round(:1046-1048),`step(0.89999997615814208984375, ...)` 端点判定(:1049);对角 AreaTex 坐标用 **20.0f** 缩放(:1075,正交是 16),采样偏移 `+0.5f`(:1076,`_AreaTex(uv+0.5).xy`);同向双对角累加(:1179 `.yx`);**边侧长度衰减**(:1238-1245):`_509 = step(len, len.yx)`,`_515 = (_509×0.75)/(sum)`,4 点边缘采样(int2(0,-2)/(0,1)/(1,1)/(1,-2))后 `AreaTex × clamp(_538, 0, 1)`(:1245)。
- **Neighborhood Blending Pass9**(:2426-2535,全文):`_BlendTex` t3 四向采样(:2431-2439,取 .w/.y/.z/.x);四向和 < 1e-6 → 直通(:2441);否则 `bool = max(N,S) > max(E,W)` 选主方向(:2450),**权重归一 2-tap**:`offset = ±MainTex_TexelSize×方向权重`(`_11_Stripped_0` cbuffer,:2528),`out = 采样(±offset) × (w/(w0+w1))`(:2527-2529)。
- AreaTex/SearchTex 尺寸与 CPU 侧生成不在 dump 内 ⚠待核。

---

## 3. DOF(dof\,三套)

### 3.1 hgdepthoffield.shader(主版本,9 Pass)

| Pass | Name | 行号 | 变体 |
|---|---|---|---|
| 0 | CoC and Split | :8 | b2(catch-all,已全文)/b3(PHYSICAL_CAMERA ⚠待核) |
| 1 | Horizontal Tiled CoC | :45 | 内联直通(见下) |
| 2 | Vertical Tiled CoC | :294 | 内联(与 Horizontal 同构 ⚠待核未逐行) |
| 3 | One Component Horizontal Filter | :543 | b8(catch-all,已全文)+b9-b13(radius 4/6/8/12/16 ⚠待核仅核半径) |
| 4 | One Component Vertical Filter | :600 | b15-b20 |
| 5 | Two Component Horizontal Filter | :657 | b22-b27 |
| 6 | Two Component Vertical Filter | :714 | b29-b34 |
| 7 | Depth of Field Composite | :771 | 内联(已全文) |
| 8 | Depth of Field Apply | :1022 | b39(catch-all,已全文)/b40(PHYSICAL_CAMERA ⚠待核) |

- **CoC 公式**(Pass0 b2,dof\hgdepthoffield\Sub0_Pass0_Fragment_b2.hlsl:176-191):
```
eye = 1/(z×_ZBufferParams.z + _ZBufferParams.w)                                       // :178(线性眼深)
cocNear = (Params1.z == 0) ? 0 : clamp((eye - Params0.y)/(Params0.x - Params0.y), 0, 1)   // :179
cocFar  = (Params1.w == 0) ? 0 : clamp((eye - Params0.z)/(Params0.w - Params0.z), 0, 1)   // :180
c' = c/(1 + dot(c, (0.21267290413379669189453125, 0.715152204036712646484375, 0.072175003588199615478515625)))  // :182(亮度归一)
MRT0 = float4(c'.xyz, cocNear)
MRT1 = cocFar>0 ? float4(c'.xyz,cocFar) : float4(0,0,0,0)                            // :183-190；Far未命中时RGB也清零
```
cbuffer `_Params0/_Params1/_Params2/_RTSize`(b2,:150–154)。按GPU消费者分别确认：MRT0使用Params0.x/y与Params1.z，MRT1使用Params0.w/z与Params1.w；不要沿用原稿把两组near/far窗口互换的CPU命名猜测。正负分母与实际焦距参数须由生产端确认。
- **Horizontal Tiled CoC**(内联 :263-279):直通采样 `_DoFNearRT0`,alpha(=CoC) `max(coc, 重采样 coc)`(:275)——平铺 CoC 修正。
- **17-tap 核滤波**(Pass3 b8,dof\hgdepthoffield\Sub0_Pass3_Fragment_b8.hlsl:176-199,已全文):
```
半径 r = _RTSize.zw × _Params1.x × 采样.w(CoC)                                        // :179
for i in [-8, 8]: s = _DoFNearRT0(uv + r×(i,0))(clamp 9.9999997473787516355514526367188e-05 ~ 0.99989998340606689453125)
  accNear += s × w[i].y; accFar += s × w[i].x                                          // :188-194
out1 = accFar×17/(n+9.9999997473787516355514526367188e-05); out2 = accNear×17/(n+9.9999997473787516355514526367188e-05) // :195-198
```
**权重表 `_86[17]`**(:5,对称 disc):.x(far) = (-0.00144200003705918788909912109375, 0.0104879997670650482177734375, 0.0237709991633892059326171875, 0.0363559983670711517333984375, 0.0468220002949237823486328125, 0.054554998874664306640625, 0.05960600078105926513671875, 0.062366001307964324951171875, 0.063231997191905975341796875, 0.062366001307964324951171875, …对称),.y(near) = (0.02665599994361400604248046875, 0.0309449993073940277099609375, 0.0308299995958805084228515625, 0.0267699994146823883056640625, 0.020139999687671661376953125, 0.012687000446021556854248046875, 0.0060740001499652862548828125, 0.001583999954164028167724609375, 0.0, …对称)。b9-b13 = 同式换核(半径 4/6/8/12/16)⚠待核(未逐行,核表未抄)。
- **Composite**(内联 :992-1007,已全文):`scene` → 若 far.CoC>0 用 far 模糊反归一 `c/(1-luma709(c))`(:1000) → 若 near.CoC>0 用 near 模糊反归一(:1003);alpha 沿用 scene(:1006)。
- **Apply**(Pass8 b39,dof\hgdepthoffield\Sub0_Pass8_Fragment_b39.hlsl:176-184,已全文):重算该像素 CoC(near>0 或 far>0,:179),命中则输出 `_CompositeRT`(LinearMirror)否则原场景色(:180-182)。

### 3.2 hgdepthoffieldhexagonal.shader(六边形版,7 Pass)

| Pass | Name | 行号 | 说明 |
|---|---|---|---|
| 0 | CoC and Split | :8 | 外部 b2/b3,**与主版 Pass0 文件同尺寸同内容** ⚠待核(11500/11851 B 完全一致) |
| 1/2 | One Component H/V Filter | :45/:314 | 内联 |
| 3 | Hexagonal Blur Pass One | :599 | 内联,已全文(:827-876) |
| 4 | Hexagonal Blur Pass Two | :892 | 内联(:1132-1144 已抽关键行) |
| 5 | Hexagonal Composite | :1172 | 内联 ⚠待核(未逐行) |
| 6 | Hexagonal Apply | :1423 | 外部 b16/b17,与主版 Apply 同尺寸 ⚠待核 |

- **Hex Blur Pass One**(hgdepthoffieldhexagonal.shader:827-876,已全文):输入 `_DoFFarRT0`;CoC=alpha,**16 步 × 两方向**:`dir1 = (0, -i)`、`dir2 = (i, 0.5×i)`(:853-854,即六边形的垂直与 60° 方向),步长 `RTSize.zw × CoC × _Params1.y`(:841/:853);每步 `clamp(uv, 9.9999997473787516355514526367188e-05, 0.99989998340606689453125)`;**有效样本均值**(w≠0 才累计,:855-861),双 MRT 分别输出两方向和(:864-871,alpha 恒写 CoC)。
- **Pass Two**(:1132-1144):从 RT2/RT3(= Pass One 两方向输出)再采样,方向 `(-i, …)` 与 `(i, …)`,步长同式 — 与 Pass One 合成第三/第四方向 ⚠待核(合成权重段未逐行)。
- Composite/Apply:与主版概念同 ⚠待核。

### 3.3 hgdepthoffieldmobile.shader(移动版,6 Pass)

| Pass | Name | 行号 | 变体 |
|---|---|---|---|
| 0 | Mobile CoC | :8 | b2(catch-all,11.5KB)/b3(DOF_PHYSICAL_MODE,1.8KB ⚠待核) |
| 1 | Mobile Temporal Low | :45 | b5/b6(14KB ⚠待核,时域滤波) |
| 2 | Mobile Downsample | :82 | 内联 ⚠待核 |
| 3/4 | Mobile H/V Filter | :321/:358 | b11/b12、b13/b14(4.2KB,⚠待核) |
| 5 | Mobile Apply | :395 | b17(1.7KB)/b18(1.1KB)⚠待核 |

keyword:`DOF_PHYSICAL_MODE`(:21)。移动版整体未逐行 ⚠待核——仅确认 Pass 结构与 keyword。

---

## 4. 体积光 lightshaft/hglightshaft.shader(5 Pass)

| Pass | Name | Blend | 行号 |
|---|---|---|---|
| 0 | LightShaftDownsample | 无 | :8(外部 b2/b3,b2 已全文) |
| 1 | LightShaftOcclusionTermDownsample | 无 | :45(内联) |
| 2 | LightShaftRadialBlur | 无 | :293(内联) |
| 3 | LightShaftOcclusionTerm | 无 | :416(内联) |
| 4 | ApplyLightShaft | **Blend One One, One One + ColorMask RGB** | :664(:667-668) |

- **Pass0 Downsample**(hglightshaft\Sub0_Pass0_Fragment_b2.hlsl:176-184,已全文;`_Globals_LightShaftParams0-3` b5 c0-c3、`_LightShaftCloudMaskParams` c4、`_LightShaftBlurPassIndex` c5,:148-156):
```
c = max(场景色(uv, LinearRepeat), 0)                                                  // :178
vig = 1 - ((uv.x(1-uv.x) × uv.y(1-uv.y)) × 8)                                          // :179
lum = max(dot(c, Rec709权重), 6.103515625e-05)                                         // :181
r = 1 - clamp(length(LightShaftParams2.xy - uv) × 2, 0, 1)                             // :182(径向衰减)
out = c × Params0.y / lum × clamp(lum - Params1.w, 0, Params0.w) × 2 × Params1.xyz
      × clamp((1/(ZBufferParams.z×depth + ZBufferParams.w) - 0.5/Params0.x) × Params0.x, 0, 1)   // 深度窗(:183)
      × (1 - vig⁴) × r²                                                                // :183
```
keyword `LIGHT_SHAFT_CLOUD_MASK`(:21)→ b3 ⚠待核(云掩码分支未读)。
- **Pass1 OcclusionTermDownsample**(内联 :273-278):`occ = max(clamp(线性深度 × _12_Stripped_0.x, 0, 1), vig⁴)`,输出 float4(occ, 0, 0, 1)——遮挡项与暗角平方取 max。
- **Pass2 RadialBlur**(内联 :378-401,已全文):
```
off = (中心(_10_Stripped_32.xy) - uv) × min(( _10_Stripped_32.w × 0.100000001490116119384765625 ) × pow(0.4000000059604644775390625 × _10_Stripped_32.z, _10_Stripped_80), 1.0)   // :380
for i in [0, _10_Stripped_32.z): sum += 采样(uv + off×i/z)                              // :386-399
out = sum / _10_Stripped_32.z                                                          // :400
```
即**采样数 = _10_Stripped_32.z(整数)、步进 = off×i/N、总位移 = off**;`_10_Stripped_80` = 强度指数。
- **Pass3 OcclusionTerm**(内联 :644-649):`occ = lerp(lerp(_12_Stripped_0.z, 1, occ²), 1, clamp(length((光源屏幕位(_12_Stripped_32.xy + _6_Stripped_0.zw×0.5)) - uv) × 0.20000000298023223876953125, 0, 1))`——离光源越远遮挡影响越弱。
- **Pass4 Apply**(内联 :740-743):直通采样 `_LightShaftBlurResult`,**加法混合**。

## 5. 镜头光晕 lensflaredatadriven.shader(4 Pass × 12 变体,ghost 元素 = CPU 每元素一次绘制)

| Pass | Name | Blend/Op | 行号 |
|---|---|---|---|
| 0 | LensFlareAdditive | **Blend One One, One One** | :3(:6) |
| 1 | LensFlareScreen | **Blend One OneMinusSrcColor×2 + BlendOp Max, Max** | :90(:93-94) |
| 2 | LensFlarePremultiply | **Blend One OneMinusSrcAlpha×2** | :178(:181) |
| 3 | LensFlareLerp | **Blend SrcAlpha OneMinusSrcAlpha×2** | :265(:268) |

keyword(每 Pass 相同,:23-26):`FLARE_INVERSE_SDF / FLARE_CIRCLE / FLARE_POLYGON / FLARE_OCCLUSION`;12 变体 b6-b17(b6=catch-all 贴图模式)。
- **cbuffer type_LensFlareData**(b0/b1,space3,Vertex_b6:150-159):`_FlareData0`(旋转/偏移)、`_FlareData1`(遮挡: .x 采样半径 .y 采样数 .z 深度阈)、`_FlareData2`(屏幕位置 .xy / 尺寸 .zw)、`_FlareData3`(.x 离屏开关 .y 圆环起始 .z 圆环幂)、`_FlareData4`、`_FlareColorValue`(c6)。
- **Quad 生成**(Vertex_b6:177-197,已全文):角点索引 → `本地角点 × FlareData2.zw`(尺寸)→ **旋转**(FlareData0.xy = cos/sin: `_82 = x×c - y×s`、`y' = x×s + y×c`,:187-188)→ `_86.x ×= ScreenSize.y/ScreenSize.x`(宽高比校正,:189)→ `+ FlareData2.xy + FlareData0.zw`(:190)。
- **贴图模式**(Fragment_b6:175-178):`out = _FlareTex(uv) × FlareColorValue`。
- **圆环模式**(FLARE_CIRCLE,Fragment_b8:30-32,已全文):
```
shape = pow(clamp((length((uv-0.5)×2) - 1) / (FlareData3.y - 1), 0, 1), FlareData3.z)
out = shape.xxxx × FlareColorValue
```
- **遮挡模式**(FLARE_OCCLUSION,Vertex_b12:197-253,已全文):**屏幕空间哈希螺旋采样投票**——
```
if FlareData1.y == 0: occ = 1
else: N = FlareData1.y; for i in [0,N):
  哈希:(2i / 2i+1)各经(h^2747636419u)*2654435769u，再两次(h^(h>>16))*2654435769u；uint32环绕必须保留(:212–217)
  角度=float(h2)*1.4629181199765639576071407645941e-09；半径=sqrt(float(h1)*2.3283064365386962890625e-10) // 归一因子在sqrt内，不能移出
  采样位 = FlareData2.xy + (cos,sin)(角) × 半径 × FlareData1.x,转 uv(:217-218)
  界内: occ += (1/(ZBufferParams.z×_CameraDepthTexture.Load(px).x + ZBufferParams.w) > FlareData1.z) ? 1/N : 0   (:221-231)
  界外: FlareData3.x>0也累计1/N(:235–244)，使可见性权重增加，即界外样本视为可见，**不是遮挡**
离屏裁剪: FlareData3.x < 0 且元素中心出屏 → occ = 0(:253)
```
输出 occ 走 TEXCOORD1 给 fragment 乘(:b12 Fragment:177-180 `× _3`)。FLARE_POLYGON / FLARE_INVERSE_SDF 变体未逐行 ⚠待核(b13/b9/b14-b17;Vertex 里疑含多边形 SDF 距离场)。

## 6. 变形光条 anamorphicstreaks/anamorphicstreaks.shader(4 Pass 全内联)

| Pass | Name | 行号 | 函数体 |
|---|---|---|---|
| 0 | Prefilter | :8 | :96-124(已全文) |
| 1 | Downsample | :139 | :218-248(已全文) |
| 2 | Upsample | :263 | :356-367(已全文) |
| 3 | Composition | :382 | :475-499(已全文) |

- **Prefilter**(:96–124)：先`p=(uv-.5)*AStreaksAngleTextureScale.xy`，再`uv'=.5+RotateParams.xy*p.x+RotateParams.zw*p.y`；scale不可省。界内Gather四色，选最亮色，除以`max(minLuma,6.103515625e-05)`再乘阈值窗。这里是标量归一、保留色彩方向，不是“去色”。Stencil &4命中剔除，UV越界输出0；这些条件不能在摘要移植时丢掉。
- **Downsample 9-tap 横向**(:218-248):步长 `_AStreaksScreenParams.z`,9 点固定权重 `(0.062970198690891265869140625, 0.09290249645709991455078125, 0.12264899909496307373046875, 0.14489300549030303955078125, 0.15317000448703765869140625)`(对称 5 系数 ×2 ± 中心,:247)。
- **Upsample**(:356-367):3-tap `_42 = 步长×1.5`,权重 `(0.3271040022373199462890625, 0.3457910120487213134765625, 0.3271040022373199462890625)`,与 `_BlurSrc_Other` 按 `_AStreaksParams1.w` lerp(:366)。
- **Composition**(:475-499):逆旋转映射(:477-478);5-tap(步长 ×0.75,权重 `(0.17820300161838531494140625, 0.210521996021270751953125, 0.22254900634288787841796875)` 对称,:480-498);**与场景合成**:`out = lerp(场景提取(同 Prefilter 阈值式 :498), 光条, _AStreaksParams1.w) × _AStreaksParams1.xyz × _AStreaksParams0.z + 场景色`(:498);保留场景 alpha(:498)。

## 7. 锐化 sharpen.shader(单 Pass 3 变体)

keyword(:21-23):`_SHAPEN_FILTER_1`(catch-all b1,已全文)/`_SHAPEN_FILTER_2`(b2)/`_SHAPEN_FILTER_4`(b3)。ZTest Always/ZWrite Off/Cull Off(:12-14)。
- **FILTER_1**(sharpen\Sub0_Pass0_Fragment_b1.hlsl:171-180,已全文;cbuffer `_SharpenParams` c0(.x 强度 .y 半径 .z 死区)、`_InputTexture_TexelSize` c2,:148-153):
```
diag = 采样(uv + 0.7070000171661376953125 × TexelSize.xy × SharpenParams.y)            // :175(对角单 tap)
d    = center - (center + diag) × 0.5                                                  // :175
out  = center + (max(|d| - SharpenParams.z, 0) × sign(d)) × SharpenParams.x            // :176(死区阈值锐化)
```
b2/b3(FILTER_2/4,疑 2/4 tap 方向扩展)未逐行 ⚠待核。

## 8. 磨砂玻璃模糊 frostedglassblur.shader(2 Pass,Pass0 4 变体 + Pass1 内联单变体)

keyword(:20-21):`USER_LUT / APPLY_LUT`。Pass0 Horizontal 变体:b3(catch-all,已全文)、b4/b5(单 LUT keyword)、b6(APPLY_LUT+USER_LUT,37KB)。
- **Horizontal b3**(frostedglassblur\Sub0_Pass0_Fragment_b3.hlsl:172–189)：9tap，偏移±4/±3/±2/±1 texel及中心；**单位步长为1 texel，不是×4 texel**。权重同上述高斯。每tap先做`c/(max(max3(c),ColorThreshold.x)/ColorThreshold.x)`再累计，sampler名称为`sampler_LinearClamp_LogLut2D`，具体过滤/寻址仍需绑定证据。
- **Vertical 内联**(frostedglassblur.shader:278-289,已全文):**5-tap 高斯**(0.0702702701091766357421875/0.3162162303924560546875/0.2270270287990570068359375,步长 `TexelSize.w × 3.23076915740966796875 / 1.384615421295166015625`,:280-287),同软阈值。
- **b6(APPLY_LUT+USER_LUT)**:每个 blur tap 单独过 `_LogLut2D` 调色(log 编码 + 条带行混合 + clamp [0,1],与 uberpost §4.2-4.3 同构,b6:187 等 9 处)+ `_UserLut` t3 ⚠待核(460 行未逐行)。

## 9. UI 模糊 uiimageblur.shader(2 Pass 全内联,单变体)

- **Horizontal**(:89-95,已全文;cbuffer `_Param0` c0、`_Param1` c1、`_paramAtlas` c2,:66-71):**7-tap 高斯** `0.03125/0.109375/0.21875/0.28125/0.21875/0.109375/0.03125`(sum=1),步长 `_Param0.zw × _Param1.x × _paramAtlas.zw`,全部采样 **clamp 到图集范围** `[_paramAtlas.xy, _paramAtlas.xy + _paramAtlas.zw]`(:91-94,UI 图集安全采样)。
- **Vertical**(:193-205,已全文):同权重静态表 `_41[7]`(:168),循环 ±3,无图集 clamp(:200)。

## 10. ⚠待核汇总

1. TAAU resolve b4/b5(NEXTGEN/PERFORMANCE)差异。
2. SMAA Pass3 与 Pass2 阈值相同(0.10)的真实差异;Pass6/7/8 为何三份同构;AreaTex/SearchTex 的 CPU 生成规格。
3. DOF b9-b13 各半径核表、Pass4/5/6(one/two component)与 Pass3 的差异、Vertical Tiled CoC 与 Horizontal 的逐行比对、b3/b40(PHYSICAL_CAMERA)分支。
4. 六边形版 Pass Two 合成权重、Composite、Pass0 是否与主版逐字相同。
5. 移动版 DOF 全部细节(Temporal Low/Downsample/Filter/Apply、DOF_PHYSICAL_MODE)。
6. lightshaft b3(LIGHT_SHAFT_CLOUD_MASK 云掩码分支)。
7. lensflare FLARE_POLYGON / FLARE_INVERSE_SDF 的 SDF 数学(b13/b9 等变体、其 Vertex)。
8. sharpen FILTER_2/4、frostedglass b4/b5/b6 全文。

---
*仅静态转写;行号指各 .shader wrapper 与子目录 .hlsl;无测试/参考实现。*

## 11. 本轮审核范围与缺口（2026-09-30）

全文审阅资料并回源抽查TAAUDilation、DOF主版Pass3、lensflare遮挡b12、anamorphic Prefilter、sharpen b1、frostedglass b3、UI blur Horizontal，更正上文确定错误。其他长链摘要仍未逐指令认证；特别TAAU:199的打包包含当前`uint(mv.z)`按位OR、bit1和bit2，不能改成“历史帧奇偶位”叙述来重新设计。DOF Pass3输出精确归一分母为`n+9.9999997473787516355514526367188e-05`(:195)，摘要17/n省略了epsilon，不能用于逐字实现。Temporal历史初始化/重置、jitter、MV编码/类别、深度正反Z、分辨率、SMAA资源、物理DOF/简化变体及所有模块启用顺序仍有缺口，必须列未闭合而非冻结为已完整规格。
