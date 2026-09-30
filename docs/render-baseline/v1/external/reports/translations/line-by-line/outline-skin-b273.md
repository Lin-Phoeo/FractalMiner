# 逐行译读:characternpr_skin CharacterOutline(变体 b273)

源文件(相对 `FractalMiner\_dump_1.5.3\AllShader_1.5.3\Assets\packages\com.hg.render-pipelines\runtime\shaders\materials\characternpr\`):
- `characternpr_skin\Sub0_Pass1_Vertex_b273.hlsl`(509 行，含 main)
- `characternpr_skin\Sub0_Pass1_Fragment_b273.hlsl`(1012 行，含 main)

配套分析见 `..\official-outline-skin-b273.md`(常量映射/变体差异/实现含义);本文是**逐行证据层**,每行可执行代码都有条目。声明区(cbuffer/struct)按段落汇总,不逐行展开(内容为声明,无逻辑)。

> 2026-09-30 复核：本层仍是人写译文，不是完整可执行源码。L319 广播减法、L320 的0符号、蒙皮80.x/y用途、MV位置选择、L453 VP矩阵/半角符号和片元双重倒数说明均已回源更正。以 hash 锁定原始源为最终公式证据，不因“每行有条目”认定整个管线闭合。

---

## A. 顶点 Sub0_Pass1_Vertex_b273.hlsl

### A.0 声明区(逐段)

- L1-3:头注释。Blob 273,ParamBlob 376;关键字 = HG_ENABLE_PER_OBJECT_MV + HG_ENABLE_SCREEN_SPACE_SHADOW_MASK + SRP_INSTANCING_ON(catch-all)。
- L5-17:`anon_UnityPerDrawArray` 结构 = HG 自定义 UnityPerDraw 数组元素:Stripped_0(O2W 4×4)、Stripped_64(float4,蒙皮/MV 标志)、Stripped_80(float4,蒙皮矩阵索引)、Stripped_96(4×4,上一帧 O2W)、Stripped_160..240(float4×5)。
- L19:`_117 = 0.0f.xxxx` 常量(仅在 L323 作 tangent.w 占位)。
- L21-45:`TransformVariables` b12,space0 —— ViewMatrix/InvViewMatrix/ProjMatrix(c0/c4/c8)、若干 Stripped 矩阵、NonJitteredViewNoTransProjMatrix(c32)、WorldSpaceCameraPos_Internal(c44)、PrevNonJitteredViewNoTransProjMatrix(c57)、PrevCamPosRWS_Internal(c81)。
- L47-188:`ShaderVariablesGlobal` b16,space0 —— 完整声明;体使用的成员见下文逐行(_ScreenSize 未用、_BackBufferSize、_TaaJitterStrength、_ProjectionParams、_unity_OrthoParams、_GlobalMipBias 未用、_ExposureWithMiscParams 未用、雾参数未用、_CharacterParams 未用 —— 顶点实际只读 _BackBufferSize/_TaaJitterStrength/_ProjectionParams/_unity_OrthoParams/各矩阵)。
- L190-193:`UnityInstancing_SRP_UnityPerDraw` b0,space2,数组 256。
- L195:`_VertexSkinMatrices` t18,space0(ByteAddressBuffer)。
- L196-254:材质 cbuffer `cbuffer _29_30 : register(b0, space1)` —— 全部成员为 `_30_Stripped_N`(工具未匹配到 CPU 属性);顶点读 c10(UV ST)/c14.x(宽)/c14.y(深度偏移)/c15.x(平滑法线开关),其余声明未读。与片元的 `_43_44`(b273 片元 L258-316)同布局。
- L257-272:静态输出变量声明(gl_Position、gl_InstanceIndex、_3.._19)。
- L274-296:输入/输出结构。输入:POSITION0=_3、NORMAL0=_4(float2=UV0)、TANGENT0=_5(打包)、COLOR0=_6(备用切线)、TEXCOORD0=_7(平滑法线 2 通道)、TEXCOORD1=_8(烘焙位置)、TEXCOORD2=_10(骨权重)、TEXCOORD3=_11(uint4 骨索引)、SV_InstanceID。输出:TEXCOORD0=_12(UV)、1=_13(positionRWS)、2=_14(输出法线)、4=_16(当前 clip xyw)、5=_17(上一帧 clip xyw)、6=_19(instanceID,nointerp)、SV_Position。

### A.1 vert_main(L298-486)逐行

- `L300-301` `uint _137 = asuint(_5.x); bool _139 = (_137 & 1073741824u) > 0u;` —— 取 TANGENT0.x 的 bit30 作"打包数据"标志。
- `L302-303` `_212/_213 = 0` —— 解包出的法线/切线占位。
- `L304` `if (_139)` —— 打包分支。
- `L305-308` `_145 = bit[0..9]`、`_148 = bit[10..19]`、`_151 = bit[20..29]`(各 `<<n >>22` 提取);`_165 = float3(有符号化(_145), 有符号化(_148), 0) × 0.001956947147846221923828125` —— 系数 = 1/511,前两个 10bit → [-1,1] 近似。
- `L310` `_171 = (1 - |x|) - |y|` —— 八面体 z 重建。
- `L311-313` `_172 = _165; _172.z = _171;` `bool2 _174 = (_171 < 0)` —— 负半球标志。
- `L314` `_182 = (1 - |y,x|) × (step(0,(x,y))×2-1)` —— 下半球折叠公式。
- `L315` `_183 = _174 ? _182 : _172.xy` —— 按象限选择折叠/原值。
- `L316` `_185 = normalize(float3(_183.x, _183.y, _172.z))` —— **解包法线**(10bit×2 八面体)。
- `L317` `_186 = 有符号化(_151) × 1/511` —— 第三个 10bit(切线参数)→ [-1,1]。
- `L318-319` `_189 = _185.yzx - _185.zxy; _193 = normalize(_189-dot(_189,_185).xxx)` —— 标量广播减法，不能补成乘法线的常规正交投影；“一定正交”未经公式支持。
- `L320-321` `_197=(_186<0)?-1:1; _200=1-((_186*_197)*2)` —— 0 取 +1，不能替换 sign(0)=0。
- `L322` `_207 = mul(normalize(float2(_200, _197×(1-|_200|))), float2x3(_193, normalize(cross(_185,_193))))` —— 2D 单位向量投回 (副切线, 切线×法线) 框架 → **重构切线**。
- `L323-324` `_208 = (T.xyz, w); _208.w = bit31 ? 1 : -1` —— 手性。
- `L325-326` `_212 = _185; _213 = _208` —— 打包模式:法线/切线取解包结果。
- `L327-331` else:未打包 → `_212 = _5`(TANGENT0 即法线),`_213 = 0`。
- `L333-334` `_214 = _139.xxxx; _215 = _214 ? _213 : _6` —— 未打包时切线回退到 COLOR0。
- `L335-338` `_403/_404/_405/_406 = 0` —— 切线(含 w)/法线/实时蒙皮位置/烘焙位置占位。
- `L339` `do {` —— 蒙皮单趟块。
- `L341` `_222 = float4(_3, 1)` —— 齐次物体空间位置。
- `L342` `_225 = asuint(PerDraw[inst].Stripped_64.w)` —— 逐实例蒙皮标志字。
- `L343` `_226 = _225 & 4294967247u`(= ~0x20)—— 去掉 bit5 后的"骨骼数"字段。
- `L344` `if (((_225 & 32u) == 0u) || (_226 == 0u))` —— 非 GPU 蒙皮或 0 骨。
- `L345-350` 非蒙皮路径:`_403=_215`(切线)、`_404=_212`(法线)、`_405=_3`(位置)、`_406=_8.xyz`(TEXCOORD1 烘焙位置)。
- `L351` `break`。
- `L352` `_242 = _11 × 3` —— 每骨占 3 个 float4(一行 3×4 矩阵)。
- `L353` `_243=(asuint(Stripped_80.x)+3)+_242` —— 法线/切线/当前位置矩阵组起始；Load 时×16，asuint不是数值转换。
- `L354` `_245=(asuint(Stripped_80.y)+3)+_242` —— _406位置组起始；不是切线组，生产端语义待核。
- `L355-360` 展开 `_243.x+{0,1,2}`、`_245.x+{0,1,2}` 为标量索引。
- `L361-366` `_305.._310 = 0` —— 2 骨累加占位。
- `L367` `if (_226 >= 2u)` —— ≥2 骨。
- `L368-376` 双骨混合：每组内部按骨索引×各骨权重求和；`_305.._307` 来自 `_245`（_406位置组），`_308.._310` 来自 `_243`（当前位置/法线/切线组）。两个矩阵组不是两个骨权重本身。
- `L377-386` else:单骨直读。
- `L387-392` `_376.._381 = 0` —— 4 骨累加占位。
- `L393` `if (_226 >= 4u)` —— ≥4 骨。
- `L394-404` 加第 3/4 骨(`_243.z/w`、`_245.z/w` × `_10.z/w`)。
- `L405-414` else:保持 2 骨结果。
- `L415-420` 汇总:`_403` = 混合后切线(保留 w)、`_404` = 混合法线、`_405` = 蒙皮位置(float4 dot)、`_406` = 蒙皮"上一帧源"位置(来自第二组矩阵)。
- `L421-422` `break; } while(false)`。
- `L423` `_415 = float3x3(PerDraw.Stripped_0[0..2].xyz)` —— O2W 旋转/缩放 3×3。
- `L424` `_425 = mul(_415, _405) + (Stripped_0[0..2].w - camPos)` —— **相机相对世界坐标**(RWS)。
- `L425-426` `_432 = mul(NonJitteredViewNoTransProjMatrix, _425)`;`_437 = _432.w` —— 当前帧无抖动裁剪坐标,`_437` = 裁剪 w(= 视深)。
- `L427-428` `_447 = mul(_415, _404); _451 = normalize(_447)` —— **世界法线**(几何)。
- `L429` `_453 = mul(_415, _403.xyz)` —— 世界切线(未归一化)。
- `L430` `bool3 _466 = (PerDraw.Stripped_160.x < 1.0f)` —— 逐对象 MV 参数 <1(疑 unity_MotionVectorsParams【推断】)。
- `L431` `_494 = mul(PrevNonJitteredViewNoTransProjMatrix, float4(mul(prev_O2W3x3(Stripped_96),_466?_405:_406)+prevTranslate-prevCamPos,1))` —— 上一帧裁剪坐标；MV字段<1时选_405，否则_406，不能写反。
- `L432` `_514 = 0` —— 输出法线占位。
- `L433` `if (_30_Stripped_240 > 0.5f)` —— `_OutlineAverageNormal` 开。
- `L434-436` `_502 = float3(_7, 0); _502.z = sqrt(1 - clamp(dot(_7.xy,_7.xy),0,1))` —— TEXCOORD0 2 通道半球编码 → 单位法线 z 重建。
- `L437-438` `_509 = normalize(_453)`(世界切线归一化,保留 `_403.w`)。
- `L439` `_514 = mul(_502, float3x3(_509, cross(_451,_509)×_403.w, _451))` —— **平滑法线 TS→WS**(TBN 列)。
- `L440-443` else:`_514 = _451`(几何世界法线)。
- `L445-452` `_528=-1/ProjMatrix[1].y`、_529=abs(_528)、_530=_529<1、_532=_530?_529:1/_529、_533=_532²、_538=(1+(-0.3018949925899505615234375+0.087292902171611785888671875*_533)*_533)*_532、_540=_530?_538:1.57079637050628662109375-_538、_543=_528<0?-_540:_540。这是带符号atan多项式近似，不是精确等于FOV/2，不用精确atan或舍入常量替换。
- `L453` `_564=normalize(mul(float3x3(NonJitteredViewNoTransProjMatrix[0].xyz,NonJitteredViewNoTransProjMatrix[1].xyz,NonJitteredViewNoTransProjMatrix[2].xyz),_514).xy)*float2(BackBufferSize.y/x,1)*(_30_Stripped_224*(0.3926990330219268798828125/_543))*clamp((_437*(_543*114.5915679931640625))*0.039999999105930328369140625,0,1)*0.004999999888241291046142578125` —— VP3×3不是仅视图旋转，_543保留符号，不取绝对值；常量、括号不改写。
- `L454` `_569 = BackBufferSize.zw × clamp(_437, 0, (π/2)/_543)` —— 像素下限 cap(`(π/2)/fovHalf = π/fovY`)。
- `L455-456` `_570 = |_564|; _571 = _570 < _569` —— 逐轴判断"偏移小于 cap"。
- `L457` `_575 = _569 × sign(_564)` —— cap 的带符号版本。
- `L458` `_577 = _571 ? _575 : _564` —— **小于 cap 抬到 cap(下限钳制,非上限)**。
- `L459` `_579 = (_432.xy - _TaaJitterStrength.zw×(2,-2)×_437).xy + _577` —— **去 TAA 抖动后加外扩**。
- `L460` `_580 = float4(_579, _432.z, _432.w)`。
- `L461-462` `if (_unity_OrthoParams.w == 0)` —— 透视分支。
- `L463-466` `_597 = -_437 + _30_Stripped_228×(-0.1)`(目标视深 = 往后推 `_OutlineOffsetZ×0.1`);`_605.z = ((_597×P[2].z + P[2].w) × _437) / (-_597)` —— 把 clip.z 重映射到目标视深。
- `L467-472` else 正交:`_593.z = _432.z + (_30_Stripped_228×(-0.1))/_ProjectionParams.z`(far 归一)。
- `L473` `}`。
- `L474`(空)。
- `L475` `_608 = _432.xy + _577` —— 当前帧 clip.xy **带抖动**加外扩(供 MV)。
- `L476` `_611 = _494.xy + _577` —— 上一帧 clip.xy 加同一外扩。
- `L477` `_12 = (_4 × c10.xy) + c10.zw` —— UV0 × `_BaseMap_ST`。
- `L478-479` `_13 = _425; _14 = _514` —— positionRWS(未外扩)/输出法线。
- `L480-481` `_16 = (_608, _432.w); _17 = (_611, _494.w)` —— MV 两帧 clip xyw。
- `L482-484` `_615 = _606; _615.y = -_606.y; gl_Position = _615` —— y 翻转(Vulkan 语义)。
- `L485` `_19 = gl_InstanceIndex`。
- `L488-509` `main()`:装载输入、调 vert_main、填输出。

---

## B. 片元 Sub0_Pass1_Fragment_b273.hlsl

### B.0 声明区(逐段)

- L1-3:头注释(Blob 273,ParamBlob 376,catch-all)。
- L5-17:UnityPerDraw 数组结构(同顶点 A.0)。
- L19-21:`_288/_290 = 0.0f`、`_291 = 0u` —— 静态占位(_288 用于 PCF 采样坐标填充、_290 用于根方向 y=0)。
- L23-47:TransformVariables b12。
- L49-190:ShaderVariablesGlobal b16(体使用:_ScreenSize、_BackBufferSize、_ProjectionParams、_unity_OrthoParams、_TaaJitterStrength、_GlobalMipBias、_FrameCount、_ExposureWithMiscParams、_BinningBufferOffsets、_EnvironmentGlobalParams0、雾参数组、_CloudShadowParams 未用、_IVParam0/1/2、_IVDefaultSHAr/Ag/Ab、_CharacterParams0/1/4/6/7/8/9/11/12/15)。
- L192-195:实例化 UnityPerDraw 数组。
- L197-198:`_GlobalBinningBuffer` t51、`_VertexSkinMatrices` t18(ByteAddressBuffer;片元只用前者读分箱,后者读 O2W 两行)。
- L199-213:LightBinningConstants b48(NumTilesX=c1.y、NumZBinSlice=c1.w、InvZBinSlice=c2.w)。
- L215-224:LightDataBuffer b14(DirectionalLightDirection、DirectionalLightCustomData1、PunctualLightData[2048])。
- L226-256:ShadowData b15(_CSM* 未用、_DirectionalShadowParams(c34)、_PunctualLightWorldToShadow[56]/ShadowParams/2/TexelSize)。
- L258-316:材质 cbuffer `_43_44` b0,space1 —— 映射见分析文档 §3(仅声明)。
- L318-320:采样器 sampler_LinearRepeat(s6)、sampler_LinearClamp(s4)、sampler_LinearMirror(s7,比较)。
- L321-332:纹理 —— t27 `_PunctualLightShadowTexV2`、t22 `_ScreenSpaceShadowMask`、t30-35 IV clipmap(A/B × Lod0/1/3)、t38 `_GBufferTexture1`、t1 `_BaseMap`、t36 `_IntegratedLightScattering`。
- L333-358:静态/IO(SV_Position → gl_FragCoord;输入 TEXCOORD0..6 = _3/_4/_5/_6/_7/_9;输出 SV_Target0=_10、SV_Target1=_11)。
- L360-369:`spvPackHalf2x16/spvUnpackHalf2x16` 辅助(点光源盒形衰减的 half 打包)。

### B.1 frag_main(L371-995)逐行

#### B.1.1 通用量与 albedo(L373-403)

- `L373` `_300=1.0f/gl_FragCoord.w`；main L1000先做`gl_FragCoord.w=1/stage_input.gl_FragCoord.w`，两次倒数在非零有限输入下返回入口w本身，不能声称“再倒数还原线性视深”。SPIR-V→HLSL入口适配与实际API的SV_Position.w约定须分开核实；未经原始SPIR-V或运行期入口证据，不以该译文移除/增加倒数。
- `L374` `_314 = lerp(-_4, ViewMatrix[2].xyz, _unity_OrthoParams.w)` —— 视向量(正交时取视轴)。
- `L375-378` `_315 = dot(_314,_314)`;`_317 = rsqrt(max(_315,1e-9))`;`_318 = _314×_317`(**V**);`_319 = _315×_317`(**viewDist**)。
- `L379-391` objectToWorld 两行:`_322 = Stripped_80.x`;若 `Stripped_64.w & 16`(蒙皮)则 `_340/_341 = _VertexSkinMatrices.Load((_322+2)/_322 ×16)`,否则取 Stripped_0[2]/[0] —— row2/row0(只需平移 w 分量)。
- `L392` `_347 = _BaseMap.SampleBias(sampler_LinearClamp, _3, _GlobalMipBias)` —— **BaseMap 采样(LinearClamp)**。
- `L393` `_356 = (_44_Stripped_252 != 0).xxx` —— 覆盖色逐通道使能。
- `L394` `_362 = _44_Stripped_256.xyz` —— 覆盖描边色。
- `L395` `_367 = _347.xyz × _44_Stripped_96.xyz × _44_Stripped_232` —— **BaseMap × _BaseColor.rgb × _OutlineColorBrightness**。
- `L396` `_371 = lerp(luma(_367), _367, _44_Stripped_236)` —— × `_OutlineColorSaturation`(灰度插值,>1 外插)。
- `L397` `_372 = _356 ? _362 : _371` —— 覆盖色替换。
- `L398` `_377 = _372 × _44_Stripped_72` —— **阴影侧 albedo × _ShadowColorBrightness**。
- `L399` `_385 = _4 + WorldSpaceCameraPos_Internal.xyz` —— 世界坐标(positionRWS→WS)。
- `L400-401` `_389 = _385 - float3(row0.w, 0, row2.w); _389.y = 6.1e-5` —— 根到像素水平向量(y 压平防零)。
- `L402-403` `_391 = normalize(_5)`(插值法线,后续点光阴影偏移用);`_392 = normalize(_389)`(**rootToPixelH**)。
- `L404` `_402 = mul(InvViewMatrix 3×3, (0,0,1))` —— **camAxisZ**。

#### B.1.2 GBuffer 法线重投影(L405-431)

- `L405-406` `_409 = mul(NonJitteredViewNoTransProjMatrix, _4); _414 = _409.w` —— 把**未外扩** RWS 位置投到当前帧裁剪空间。
- `L407` `_417 = _409.xy - _TaaJitterStrength.zw×(2,-2)×_414` —— 去抖动。
- `L408` `_421 = float4(_417, _409.z, _409.w).xyz / _414` —— NDC。
- `L409-411` `_424 = NDC×0.5+0.5; _425 = (u, 1-v, z)` —— 屏幕 UV(y 翻转)。
- `L412-415` `_434 = uint2(_425.xy × _ScreenSize.xy); _437/_438 = x/y; _440 = int2 像素`。
- `L416` `_445 = _GBufferTexture1.Load(int3(_440,0)).xy × 2 - 1` —— **读 GBuffer 法线(八面体 2 通道)**。
- `L417` `_449 = 1 - (|x|+|y|)` —— 八面体 z。
- `L418` `_451 = (x, _449, y)`。
- `L419-430` `_449 < 0` 时下半球折叠(`_463 = (折叠x, y, 折叠y)`),否则原值。
- `L431` `_464 = normalize(_463)` —— **GBuffer 法线(描边打光用的 N)**。

#### B.1.3 环境光:三层辐照度体 clipmap(L432-574)

- `L432` `_472 = lerp(_EnvironmentGlobalParams0.x, 1, _CharacterParams12.w) × _ExposureWithMiscParams.x` —— 环境缩放(展示模式 CP12.w=1 时不乘全局)。
- `L433-434` `if (_CharacterParams1.y < 0.5)` —— IV 路径(捕获帧 CP1.y=1 走 L571 else)。
- `L437-438` `_487 = _385 - (IVParam0.xyz + camAxisZ×(-IVParam2.w))`;`_501 = max(clamp((max|x|,|z| - 464)×0.03125,0,1), clamp((|y|-208)×0.03125,0,1))` —— **Lod3(最粗)层中心/淡出**(半宽 464/208,外扩余量 32)。
- `L439-443` `_803.._807 = 0` —— SH 累加占位。
- `L444` `if ((_IVParam0.w != 0) && (_501 < 1))` —— IV 启用且未出界。
- `L446-447` `_514/_528` —— **Lod1 层**(半宽 29/13,余量 0.5)中心与淡出。
- `L448-451` `_604.._607 = 0`。
- `L452` `if (_528 < 1)` —— Lod0(最细)层。
- `L454-455` `_537 = (_385×2 + 0.5) × IVParam1.xyz; _539 = frac(_537)` —— 体素 UV(×2 分辨率)。
- `L456` `_543 = ALod0.SampleLevel(LinearClamp, _539, 0)` —— A 纹理(SH 系数选择器 xyz)。
- `L457-458` `_544 = 1 - _528`(层内权重);`_548 = IVParam1.y × 0.5`(y 边缘 clamp 余量)。
- `L459-461` `_553/_554/_555`:B 纹理 UV(x、`clamp(y,_548,1-_548)×1/3`、z)。
- `L462` `_558 = BLod0.SampleLevel(LinearRepeat, _554 行, 0)` —— 第 1 行(SH 系数组)。
- `L463-465` `_574/_584/_594 = _543.x/y/z` —— A 的三个选择系数。
- `L466-469` `_604 += _558.w×_544`;`_605.._607 = (BLod0 第 2/3 行 xyz×4-2) × 选择系数 × _544` —— 三行 SH 系数加权(B 存 `(v×4-2)` 编码)。
- `L470-477` else:Lod0 出界清零。
- `L478-479` `_613/_627` —— **Lod1 层**重算(同构)。
- `L480-509` Lod1 采样与累加(完全同构:_636 UV、_642 ALod1、_644 权重、_658 BLod1 三行、_707-710 累加)。
- `L510-540` **Lod3 层**(`_627 > 0` 时补粗层:_719 UV(×0.125)、_722 边缘 clamp、_728 ALod3、_730 权重、_744 BLod3、_793-796 累加)。
- `L541` `_799 = clamp((_796×2)-1, 0, 1)` —— 总权重归一。
- `L542-546` `_803.._807 = 累加值 + 权重拆分`。
- `L547-555` else(IV 关闭):全零、`_807=1`。
- `L556-558` `_827/_847/_867 = _805/_804/_803 + IVDefaultSH{Ar,Ag,Ab} × _807/_806 组合` —— 缺失部分用默认 SH 补(0.5/0.375 为叉项系数)。
- `L559-560` `_871 = (_464,1); _877 = max(dot(SH行,_871),0) × _472` —— **SH(N) 环境色**。
- `L561-564` `_885 = SH 行 RGB 加权平均; _889 = 归一; _894 = (x,|y|,z,1); _899 = max(dot(SH行,_894),0)` —— **环境峰值**(y 取绝对值)。
- `L565-567` `_907 = luma(_877); _914 = lerp(_907, _877, clamp(_907×10-0.1,0,1)×0.5)`;`_927 = _914 / max(max3(_914), 0.001)` —— **环境色调归一化**(暗部保留最低亮度)。
- `L568` `_928 = max3(_899, 0) × _472` —— **环境峰值强度**。
- `L569-574` else(捕获帧路径):`_927 = _CharacterParams3.xyz`(平坦环境 CP3);`_928 = _472`。

#### B.1.4 albedo 汇总与运动矢量(L575-584)

- `L575` `_953 = clamp((1 - clamp((clamp(dot(_464,_318),0,1)×0.85)+0.15,0,1)) × _44_Stripped_192, 0, 1)` —— **rim 因子**(1-视角项,scale = c12.x,疑 _SkinRimOffScale)。
- `L576` `_962 = _372 × ((1-_953) + (_44_Stripped_208.xyz×_953)) × 0.96` —— **受光侧 albedo**(rim 处染 c13.xyz 色;0.96 = 1-0.04)。
- `L577` `_963 = lerp(luma(_377), _377, _44_Stripped_76) × 0.96` —— **阴影侧 albedo**(× _ShadowColorSaturation)。
- `L578` `_970 = (1 - max(Stripped_64.y, Stripped_64.z)) < 0.99` —— 逐对象 MV 缩放 ≠1 标志。
- `L579-580` `_983 = _6.xy/max(_6.z,ε) - _7.xy/max(_7.z,ε); _983.y = -_983.y` —— 当前/上一帧 clip → NDC 差(运动矢量)。
- `L581` `_999 = lerp(四重开方编码(_983), 0.5, _970)` —— MV 编码 `sqrt(sqrt(|mv×0.5|))·sign·0.5+0.5`;异常对象置 0.5。
- `L582-584` `_1001 = (enc.x, enc.y, 1, _970 ? 0.7 : 0.4)` —— **SV_Target1**(w 区分正常 0.4/异常 0.7)。

#### B.1.5 光照项(L585-604)

- `L585` `_1024 = lerp(DirectionalLightCustomData1.xyz, _CharacterParams4.xyz, CP12.y)` —— **光色**(CP4 覆盖)。
- `L586` `_1028 = _1024 × lerp(CustomData1.w, 1, CP12.w)` —— 光强(展示模式不乘)。
- `L587-588` `_1031 = _ScreenSpaceShadowMask.Load(_440); _1036 = _1031.y` —— ssmG(角色遮挡)。
- `L589` `_1039 = lerp(lerp(1, _1031.x, _DirectionalShadowParams.x), 1, CP1.z)` —— **shadowDir**(SS 阴影强度,可整体忽略)。
- `L590-591` `_1043 = _963 × CP0.z; _1044 = _1043 × 0.65` —— **阴影深色**(两级加深)。
- `L592` `_1058 = smoothstep(-0.5, 0.5, clamp(dot(_464, lerp(-DirLightDir, CP11.xyz, CP1.w)) + CP11.w×CP12.x, -1, 1))` —— **明暗 ramp**(硬 smoothstep;N=GBuffer 法线,光向=CP11,偏移=CP11.w×CP12.x)。
- `L593` `_1065 = max3(_1058)-min3(_1058)` —— 标量恒 0(染色占位,catch-all 无 ramp 贴图)。
- `L594` `_1071 = min(min(_1036, 1), _1058)` —— **litMask = min(ssmG, ramp)**。
- `L595` `_1075 = (clamp(dot(_464, CP6)+CP7.x,0,1)×CP7.y + CP7.z) × lerp(_927, 1, CP1.y×_1071)` —— **环境梯度**(受光侧趋白)。
- `L596-597` `_1077 = _1071.xxx; _1100 = _1039.xxx` —— 向量化。
- `L598` `_1102 = lerp(lerp(lerp(luma(_1044), _1044, 1.2), _1043, clamp(_1036+_1058,0,1)), _962, _1077)` —— **明暗底色选择**(深→中→受光)。
- `L599` `_1108 = _1102 × ((1-_1065) + (_1058×_1065))` —— 染色(此处 ≈×1)。
- `L600` `_1117 = lerp(lerp(_1043, lerp(luma(_962), _962, 1.2), _1036), _1108 × clamp(luma(_1102)/max(luma(_1108),0.001), 0, 1.5), _1039)` —— **diffuseTerm**(阴影侧按 ssmG 提亮,受光侧按亮度比钳制)。
- `L601` `_1121 = (_1117, _1039)` —— diffuseLit。
- `L602` `_1123 = lerp((_1075 × lerp(min(lerp(0.65,1,_928),1.5), clamp(_928,1.25,1.75), CP1.x)) × CP0.w, (lerp(luma(_1028), _1028, _1077) + (_1075×clamp(_928,0,1.5))×((1-CP12.y)+_1024×CP12.y)) × CP0.y, _1039) × _1117 × 1.0` —— **lightTerm × diffuseTerm**(受光/阴影两套环境×光色组合,CP0.y/w 为两侧总乘数;末尾 ×1.0 是高光项占位)。
- `L603-604` `_1124 = luma(_1123); _1127 = clamp(_1124-0.5, 0, 0.5)` —— 主体亮度与提饱和因子。

#### B.1.6 边缘光与分箱(L605-615)

- `L605` `_1163 = normalize(cross(_402, lerp((CP9.xy,0), ViewMatrix 行0/行1 × CP9.xy, CP15.w)))` —— **rimAxis**(世界轴或视图轴混合)。
- `L606-607` `_1169 = dot(_318, _464)`(NdotV,GBuffer 法线);`_1171 = 1 - |NdotV|` —— 视角门控量。
- `L608-610` `_1194 = _434; _1196 = floor(_1194×0.03125); _1204 = int((_1196.x + _1196.y×NumTilesX)×8)` —— 32px tile 的分箱字地址。
- `L611-613` `_1211 = floor(_300 - _ProjectionParams.y×InvZBinSlice); _1215 = clamp(_1211, 0, NumZBinSlice-1); _1217 = int(_1215×8)` —— z-bin(线性于视深)。
- `L614` `_1219 = 0`。
- `L615` `_1219 = lerp(_1124.xxx, _1123, (_1127²+1)) + CP8边缘光项` —— **基色 = 主体色 + 提饱和;边缘光** = `CP8.xyz × smoothstep(lerp(0.8,0.2,CP9.w), lerp(0.9,0.5,CP9.w), _1171) × CP8.w × min(min(sat(dot(_392,_1163)+1),1), _1036) × (lerp(0.25, _962, CP9.z) × sat(dot(_1163,_464)))`(捕获帧 CP8=0 → 0)。

#### B.1.7 点光源双重循环(L616-921)

- `L616-618` `_1220 = 0; [loop] for (_1222 = 0..7; _1219 = _1220)` —— 8 个 tile 字(word)循环。
- `L619-620` `_1240 = (_1211 <= _1215) ? (GlobalBinning.Load((_1204+i)×4) & GlobalBinning.Load((_BinningBufferOffsets.y + _1217 + i)×4)) : 0` —— **tile 掩码 AND z-bin 掩码**。
- `L621-626` 内层 `for (_1245 = _1240; _1245 != 0; _1245 = _1246)` —— 逐位遍历。
- `L627-629` `_1250 = firstbitlow(_1245); _1246 = 清位; _1256.._1274 = 灯数据 float4 索引((32×word+bit)×8)`。
- `L637` `_1281 = uint(PLD[_1271].w)` —— 标志字(k=5)。
- `L638-655` 盒形衰减:`(_1281 & 1)` 时按 half 打包的 3×3 矩阵变换相对位置、`_1348 = PLD[k+7].x×0.5`、`_1356 = (1 - clamp((max3(|p|) - (_1348+0.5))/(0.5-_1348)))²`,否则 1。
- `L656-660` `if (_1356 < 0.001) skip`。
- `L661-662` `if (PLD[_1256].w < 1.5)` —— 光类型 0/1/3/4(≥1.5 跳过)。
- `L663-672` `do {` 类型分发:`_1369 = PLD[_1265].w`(k=3.w 阴影/类型);`== 16` 或 `(PLD[_1265].z + CP12.z) < 0.5`(角色灯层)→ 跳过。
- `L673-676` `_1381 = 非盒形; _1385 = 盒形且 PLD[_1262].z>0(管状); _1386 = (_1369==4) 类型4; _1387 = float(_1381)`。
- `L677-680` `_1395.._1407` —— 八面体解码聚光方向(PLD[k=2])。
- `L681` `_1413 = lerp(PLD[k=4].w, max(2×PLD[k=4].y, 0.1), _1386)` —— 距离衰减指数。
- `L682-687` `_1418 = 灯位 - _385; _1419 = -_1407; _1424 = 管状投影; _1427 = normalize`。
- `L688-699` `_1385` 时做**管状灯/LTC 近似**(`_1460/_1461`:cos 权重线积分)。
- `L700-705` else `_1460 = _1427, _1461 = 1`。
- `L706-717` 距离衰减:`_1413<0` 走 `(1-(d²r²)²)²/(d²+1)` 平滑窗,否则 `pow(1-clamp(d²r²), _1413)`。
- `L718-719` `_1488 = sat((dot(_1460,_1419)-PLD[k=2].z)×PLD[k=2].w)`(聚光锥);`_1492 = _1483 × lerp(1, _1488², _1387) × _1356` —— **总衰减**。
- `L720-725` `if (_1492 > 1e-4)` 才算着色。
- `L726-732` `if (_1386)` **类型 4(体积/环境灯)**:`_1883 = lerp(_1220, PLD[k=0].xyz, _1492×PLD[k=4].x)` 直达、break。
- `L733-734` `_1505 = dot(_464, _1460)(NdotL); _1506 = sat`。
- `L735-743` `if (_1369 != 0)` 阴影:`_1512 = 非盒形 || (标志&2)`(全向/点光);`_1561 = _1512 ? PLD[k=3].x : 盒形六面索引`(按最大轴向选 face,<80 有效)。
- `L774-786` 阴影 UV:接收点 = `_385 - normalize(差)×ShadowParams.x + _391×(ShadowParams.y×5)`(沿插值法线偏移)经 `_PunctualLightWorldToShadow[_1561]`;atlas 区块重映射 ×TexelSize.zw。
- `L787-830` **3×3 tent PCF 权重**(0.16/0.08 常数,8 次显式 + 1 次条件 SampleCmpLevelZero(sampler_LinearMirror))。
- `L831` `_1778 = 8 tap 加权和`(长式)。
- `L832-833` `_1791 = min(uv, 1-uv)`(边界);`_1808 = 出界/NaN ? 1 : lerp(1, tent, _1512 ? min(Params.w, smoothstep(0,0.05,边界×0.25)) : Params.w)` —— 无阴影灯走 `sat(dot(_392,_1460)+1)`(L837)。
- `L836` `if (false || ...)` —— 恒 false 的占位(RC 保留)。
- `L845-849` `_1871.._1875 = 0`(类型分发寄存器)。
- `L850-859` **类型 0**(点光):`_1872 = 光色 × ((1-k4.y) + (1/max(1, max3(光色×衰减)×lerp(0.75,0.5,1-_1039)))×k4.y) × lerp(0.5×k4.x, 1, sat(_1505+0.5))`;`_1873 = _1506; _1874/_1875 = _1121(diffuseLit)`。
- `L860-899` 其他类型:`_1369==3` **类型 3(边缘灯)**:`_1867 = _1492 × smoothstep(同 CP8 公式,k4.x 换参数) × _1809`、`_1868 = sat(dot(_464, -normalize(cross(_402,cross(_402,_1460)))))`、`_1869 = lerp(0.5, _962, k4.y)`、`_1870 = 0`;`_1369==1` **类型 1**:`_1863 = sat(sat(_1505+k4.x))×_1809`、`_1864 = _963 × k4.y`;其余:`_1863 = _1506; _1864 = 0`。
- `L900-901` `_1882 = _1220 + (_1872×_1871×lerp(_1875,_1874,_1873)) × 1.0` —— **累加**(类型 1/3 用各自 diffuse 对)。
- `L902-918` 衰减过小/类型越界路径(直接保留)。
- `L919-921` `_1243 = _1885`;循环收尾。

#### B.1.8 VFX 调色与输出(L922-995)

- `L922-924` `if (_44_Stripped_48 > 0.5)`(_EnableVFXColorAdjustment)。
- `L925` `_1925 = lerp(lerp(0.5, lerp(luma(_1219), _1219, c3.z), c3.w)×c3.y, c8.xyz, c8.w) + (c9.xyz × smoothstep(1-c4.x, 1, 1-sat(_1169)) × c4.y)` —— **VFX 调色(对比/饱和/亮度/混色/rim)**;else `_1925 = _1219`。
- `L931-932` `_1932 = (_1925 × _ExposureWithMiscParams.y, 1); _1932.w = 1` —— 曝光,alpha 恒 1(皮肤 catch-all 无 _OutlineTransparent)。
- `L933-936` `if (_CharacterParams12.w < 0.5)` —— 非展示模式才算雾。
- `L937-943` 大气雾预备:`_1937 = -V; _1954 = _385.y×AtmFog3.w; _1959 = max(0.01, …); _1973 = exp(大气消光×距离积分); _1976 = dot(-V, AtmFog1.xyz); _1982/_1986 = 相函数分母`。
- `L944-945` `_2309/_2310 = 0`。
- `L946-972` 体积雾分支(`_VolumetricFogParams0.z > 0`):L947-955 白噪声哈希(帧抖动);`_2067.._2083` 视线插值;`_2097.._2132` 双层指数雾积分;`_2154/_2157` 高度雾因子;`_2197 = 体积雾纹理采样(抖动 UV、log 深度)`;`_2309/_2310` 合成。
- `L973-985` else:纯指数高度雾(`_2203.._2309` 同公式,无体积采样)。
- `L986` `_2315 = _1932.rgb × (_1973×_2310) + (大气 in-scatter × (1-_1973) × _2310) + _2309` —— **雾合成**。
- `L987-991` else:`_2317 = _1932`。
- `L993-994` `_10 = _2317; _11 = _1001` —— 输出。
- `L997-1012` `main()`：L1000`gl_FragCoord.w=1.0/gl_FragCoord.w`是入口适配；必须与L373联合解释，非零有限入口w经两次倒数回到自身，不据此声称线性视深。装载输入、调frag_main、填输出。

---

*说明:本文件为机械逐行层,变量语义词典与跨文件结论以 `..\official-outline-skin-b273.md` 为准;两文件行号一一对应,可直接对照验收。*
