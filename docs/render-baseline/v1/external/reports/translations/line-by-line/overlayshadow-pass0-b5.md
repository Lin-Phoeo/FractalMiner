# 逐行译读:HGRP/CharacterNPR_OverlayShadow Pass0"OverlayShadowPreDepth"(变体 b5)

源文件(相对 `...\materials\characternpr\`):`characternpr_overlayshadow\Sub0_Pass0_Vertex_b5.hlsl`(317 行)、`Sub0_Pass0_Fragment_b5.hlsl`(57 行，均含 main)。关键字 = DISABLE_DRAW_UNDER_HAIR + DITHER + SRP_INSTANCING_ON。Pass1"OverlayShadow"概述与实现含义见 `..\official-overlayshadow-b5.md`。

---

## A. 顶点 Sub0_Pass0_Vertex_b5.hlsl

### A.0 声明区

- L1-3:头注释(Blob 5,ParamBlob 1)。
- L5-17:`anon_UnityPerDrawArray`(同描边:Stripped_0/64/80/96/160..240)。
- L19-43:TransformVariables b12(体使用:ViewMatrix c0、ProjMatrix c8、WorldSpaceCameraPos_Internal c44)。
- L45-186:ShaderVariablesGlobal b16(体使用:_ProjectionParams、_unity_OrthoParams、_TaaJitterStrength、_GlobalMipBias(未用)、_FrameCount(未用)、**_CharacterParams12(c119,仅声明,片元用)**)。
- L188-191:实例化 UnityPerDraw 数组(b0,space2,256)。
- L193:`_VertexSkinMatrices` t18,space0。
- L194-203:LightDataBuffer b14(体使用:`_LightDataBuffer_DirectionalLightDirection`,L298)。
- L205-214:**UnityPerMaterial b0,space1(具名!)** —— c0 = `_UseGrayAsAlpha/_ShadowAngleRange/_EnableVFXColorAdjustment`/Stripped_12;c1 = `_BaseColor`;c2 = `_ColorAdjustmentColorBlend`;c3 = `_BaseMap_ST`。**顶点只用 `_ShadowAngleRange`**。
- L216-236:静态/IO —— 输入:POSITION0=_2(float4)、NORMAL0=_3(float2,未使用)、TANGENT0=_5(**float4 = 骨权重**)、COLOR0=_6(**uint4 = 骨索引**)、SV_InstanceID;输出:**仅 SV_Position**(PreDepth 不需要插值)。

### A.1 vert_main(L238-303)逐行

- `L240` `_193 = 0` —— 蒙皮位置占位。
- `L241-242` `do {`(蒙皮单趟块)。
- `L243` `_98 = (_2.xyz, 1)`。
- `L244-245` `_101 = asuint(PerDraw[inst].Stripped_64.w); _102 = _101 & 4294967247u`(= ~0x20)—— 蒙皮标志/骨骼数(与描边顶点同一套约定)。
- `L246-250` 非 GPU 蒙皮或 0 骨:`_193 = _2.xyz; break`。
- `L251` `_115 = (Stripped_80.x + 3) + _6×3` —— 骨矩阵地址(索引来自 **COLOR0**)。
- `L252-254` `_116/_119/_122 = _115.x+{0,1,2}`。
- `L255-257` `_148.._150 = 0`(2 骨累加占位)。
- `L258-263` `if (_102 >= 2u)`:双骨混合(权重 `_5.x/_5.y`,注意本 pass **没有第二组矩阵**,法线组与位置组共用 `_115`)。
- `L264-270` else:单骨直读。
- `L271-273` `_186.._188 = 0`(4 骨占位)。
- `L274-281` `if (_102 >= 4u)`:加第 3/4 骨(`_5.z/_5.w`)。
- `L282-287` else:保持。
- `L288` `_193=float3(dot(_188,_98),dot(_187,_98),dot(_186,_98))` —— 蒙皮后物体空间位置；_188来自矩阵起始行，_187来自+1，_186来自+2（L278–280），与描边当前组按起始/+1/+2取x/y/z的逻辑相同，不要因临时变量编号反序推断轴序相反。
- `L289-290` `break; } while(false)`。
- `L291` `_219 = mul(O2W 3×3, _193) + (Stripped_0[0..2].w - camPos)` —— 相机相对世界坐标(RWS)。
- `L292` `_230 = mul(ViewMatrix 3×3, _219)` —— **视角空间**。
- `L293` `_240 = _TransformVariables_ProjMatrix` —— 复制投影矩阵。
- `L294-297` `_240[1].x=0; _240[3].x=0; _240[0].y=0; _240[3].y=0` —— 清零这四个索引项，不是将投影改为正交。其余投影矩阵及透视齐次除法保留；矩阵存储方向与构造/乘法须分别核对，不凭列主序声明重排源码索引。图案稳定的视觉意图未证实。
- `L298` `_248 = mul(_240, (_230.x + (-_LightDataBuffer_DirectionalLightDirection.x)×_ShadowAngleRange, _230.yz, 1))` —— **视角空间 x 按光方向 x 分量平移**(`_ShadowAngleRange`,Range ±0.01)—— 刘海阴影随光角度偏移。
- `L299` `_256 = _248.xy + _TaaJitterStrength.zw×(2,-2)×_248.w` —— **加回 TAA 抖动**(与主深度对齐)。
- `L300-302` `_257 = (_256, _248.z, _248.w); _257.y = -_256.y; gl_Position = _257`(y 翻转)。
- L305-317:main() 装载与输出(只写 gl_Position)。

---

## B. 片元 Sub0_Pass0_Fragment_b5.hlsl(全文逐行)

- `L1-3` 头注释(Blob 5,ParamBlob 1)。
- `L5-17` UnityPerDraw 数组结构。
- `L19-22` `UnityInstancing_SRP_UnityPerDraw` b0,space2。
- `L25-36` 静态/IO:输入仅 SV_Position;输出仅 SV_Target0 = _4。
- `L38` `frag_main()` 开始。
- `L40` `_48 = frac(52.98291778564453125 × frac(dot(gl_FragCoord.xy, (0.067110560834407806396484375, 0.005837149918079376220703125))))` —— **Jimenez 交错梯度噪声(IGN)**。
- `L41` `_50 = abs(_48)`。
- `L42` `if (min( PerDraw[0u].Stripped_64.x - ((Stripped_64.x >= 0) ? _50 : (-_50)), (1 - max(Stripped_64.y, Stripped_64.z)) - _48 ) < 0) discard` —— **双重抖动裁剪**:第一项 = 逐对象抖动阈值(保符号减噪声幅度,即 `x - sign(x)·|n|`,对象淡出 alpha);第二项用 Stripped_64.y/z(与 skin 描边按 MV scale 解释的字段同 offset,此处复用为第二重条件,语义【未确认】;y=z=1 时恒 discard)。注意实例索引用**固定 0u**。
- `L44` `discard`。
- `L46` `_4 = 1.0f.xxxx` —— 通过则输出白(纯深度写,`Blend Zero One` 丢色)。
- `L49-57` main() 装载(**L52 `gl_FragCoord.w = 1.0 / gl_FragCoord.w`** 同描边)、输出。

---

*说明:机械逐行层;Pass0/Pass1 分工、stencil、DISABLE_DRAW_UNDER_HAIR 的真实位置(Pass1 b12/b13)以 `..\official-overlayshadow-b5.md` 为准。*
