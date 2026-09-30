# 官方描边着色器转写：characternpr_skin 描边 Pass（b273）

**Pass 定位**：《明日方舟：终末地》角色 NPR 的描边 Pass（Sub0 Pass1）。本篇只覆盖 skin 的 b273；characternpr 主体/布料 catch-all 是 b1088（wrapper:3272/3536），hair 是 b306（wrapper:1105/1303），不能共用编号、材质偏移或片元公式。b273 是「被裁剪过的 ForwardLit」——顶点在裁剪空间把外壳沿法线方向外扩，片元保留环境、主光、点光源、阴影、雾及 VFX 调色；材质调色不是始终开启的描边专属步骤。

> 2026-09-30 资料基线复核：这是指定变体的静态译读，不是全部角色/变体/运行期管线的完整认证。具体顶点布局、匿名字段生产端、实际选用变体和 GBuffer 生成/绑定仍须证据闭环。原文将半球平滑法线误称为八面体、将像素下限称最大宽度、将蒙皮矩阵组用途写错，本轮已回源修正。

**来源路径**（SPIR-V-Cross 反编译 HLSL，只读）：
- 顶点：`_dump_1.5.3/.../characternpr_skin/Sub0_Pass1_Vertex_b273.hlsl`（509 行，下称 `V:行号`）
- 片元：`_dump_1.5.3/.../characternpr_skin/Sub0_Pass1_Fragment_b273.hlsl`（1012 行，下称 `F:行号`）

**Keywords**（两文件头一致）：`HG_ENABLE_PER_OBJECT_MV`、`HG_ENABLE_SCREEN_SPACE_SHADOW_MASK`、`SRP_INSTANCING_ON`（`V:2` / `F:2`）。

**转写日期**：2026-09-30

> 命名约定：`_XXX` 是 SPIRV-Cross 生成的临时/寄存器名；`<Buffer>_Stripped_<byteOffset>` 是被剥离了 CPU 侧名字的 cbuffer 成员，仅按字节偏移命名（`V:3` / `F:3`）。凡是靠数学推断出的语义都标了置信度或 `⚠待核`。

---

## §1 顶点着色器：描边挤出逻辑

顶点输入语义（`SPIRV_Cross_Input`，`V:274-285`）——注意语义名疑似被反编译器打乱，用途以实际使用为准（见 §4）：

| 变量 | 语义 | 类型 | 实际用途（推断） |
|---|---|---|---|
| `_3` | POSITION0 | float3 | 物体空间位置 |
| `_4` | NORMAL0 | float2 | UV（`V:477` 用作 UV，非法线）|
| `_5` | TANGENT0 | float3 | `_5.x` 打包了法线+切线（见下），`_5` 本身也是回退法线 |
| `_6` | COLOR0 | float4 | 顶点色 / 回退切线 |
| `_7` | TEXCOORD0 | float2 | 描边用的切线空间平滑法线 xy（半球重建，不是八面体）|
| `_8` | TEXCOORD1 | float4 | 上一帧位置（motion vector 用）|
| `_10` | TEXCOORD2 | float4 | 蒙皮权重 |
| `_11` | TEXCOORD3 | uint4 | 骨骼索引 |

### 1.1 法线/切线解包（octahedral，可选）

`_5.x` 按 `asuint` 取整数位（`V:300`）。bit30（`1073741824u = 2^30`）为 1 时走解包分支（`V:301,304`）：

- 从 32-bit 里切出三个 10-bit 字段（`V:306-308`）：
  - `n0 = float((bits << 22) >> 22)`（低 10 位）
  - `n1 = float((bits << 12) >> 22)`（中 10 位）
  - `t  = float((bits <<  2) >> 22)`（高 10 位，用于切线角）
- 每个字段 `>= 512` 时减 `1024` 还原为有符号（`V:309,317`），再乘 **`0.001956947147846221923828125`（= 1/511）**（`V:309,317`）。
- octahedral 解法线（`V:310-316`）：
  - `oct.z = (1 - |oct.x|) - |oct.y|`（`V:310`）
  - `oct.z < 0` 时对 xy 做 `(1-|yx|) * (step(0,xy)*2-1)` 折叠（`V:313-315`）
  - `_185 = normalize(oct)` → 解出的世界前法线（`V:316`）
- 切线：第三字段恢复标量 `_186 = signed(t) * (1/511)`（`V:317`），不是角度直接乘 sin/cos。逐字保留 `_189 = N.yzx-N.zxy`、`_193 = normalize(_189-dot(_189,N).xxx)`（此处不是常见的 `v-dot(v,N)*N` 正交投影，不要“纠正”）；`_197 = (_186<0) ? -1 : 1`（0 必须取 +1，不能替换 `sign`）、`_200 = 1-(_186*_197)*2`，再按 `V:322` 的二维方向和两行基向量重构 `_207`。`_208.w` 由 bit31 符号位得到 `±1`（`V:324`，`(float((bits>>31)&1)*2)-1`）。

不解包分支（bit30=0）：法线 `_212 = _5`，切线 `_213 = 0`（`V:330-331`）。
最终切线 `_215` 在解包结果 `_213` 与顶点色 `_6` 之间按分支选（`V:334`）。

### 1.2 蒙皮

`V:339-422` 做 GPU skinning：从 `_SRP_UnityPerDraw_UnityPerDrawArray[instance].Stripped_64.w` 取标志位（`V:342-344`），按 `_226`（骨骼数 2/4 分支）从 `_VertexSkinMatrices`（ByteAddressBuffer，`t18`）加载矩阵行并用 `_10`（权重）加权（`V:367-414`）。注意 `Stripped_80.x/y` 是 `asuint` 位重解释，不是数值转换。80.x 组同时作用于法线 `_404`、切线 `_403`、当前位置 `_405`；80.y 组仅用于 `_406`（`V:415-420`）。它们此时仍在 object/骨架求值空间，`V:423-429` 才乘实例 object→world。上一帧投影 `V:430-431` 在 `Stripped_160.x<1` 时选择 `_405`，否则选择 `_406`，不能把条件写反。无蒙皮时 `_406=_8.xyz`；_8 的生产语义仍待资产/引擎证据确认。

### 1.3 世界变换

- `_415` = instance 的 object→world 3x3（`V:423`）。
- `_425` = 相机相对世界位置 = `mul(_415,_405) + (objWorldOrigin - WorldSpaceCameraPos)`（`V:424`），即 camera-relative world space（RWS）。
- `_432 = mul(NonJitteredViewNoTransProjMatrix, float4(_425,1))` → 裁剪空间位置（未抖动 VP）（`V:425`），`_437 = _432.w`（≈ 视深度）（`V:426`）。
- `_451` = 归一化世界法线（`V:427-428`）；`_453` = 世界切线（`V:429`）。

### 1.4 描边挤出方向 `_514`

由材质开关 `_30_Stripped_240 > 0.5` 决定（`V:433`，⚠语义推断=「用 UV 烘焙平滑法线」开关）：

- **开**（`V:435-439`）：从 UV0 `_7` 重建切线空间法线
  - `n.xy = _7`，`n.z = sqrt(1 - clamp(dot(_7,_7),0,1))`（`V:436-437`）
  - `_509` = 归一化世界切线（`V:438`）
  - `_514 = mul(n, float3x3(_509, cross(_451,_509)*_403.w, _451))`（`V:439`），即用 TBN 把切线空间平滑法线转到世界空间（`_403.w` 为切线手性符号）。
- **关**（`V:443`）：`_514 = _451`（直接用网格世界法线）。

> **这是描边外扩方向的来源**：优先用烘焙进 UV0 的「平滑法线」以避免硬边裂缝，否则退回网格法线。

### 1.5 FOV / 半视角计算 `_543`

`V:445-452` 用多项式近似 `atan` 求半垂直 FOV 角：
- `_528 = -1.0 / ProjMatrix[1].y`（`V:445`）；`ProjMatrix[1].y = 1/tan(fov/2)`，故 `|_528| = tan(fov/2)`。
- `_529 = |_528|`；`_532 = (_529<1) ? _529 : 1/_529`（`V:447-448`）。
- `_533 = _532*_532`（`V:449`）。
- `_538 = (1 + ((-0.3018949925899505615234375 + 0.087292902171611785888671875*_533) * _533)) * _532`（`V:450`）。
- `_540 = (_529<1) ? _538 : (1.57079637050628662109375 - _538)`（`V:451`，`1.5707963705 = π/2`）。
- `_543 = (_528<0) ? -_540 : _540`（`V:452`）→ **半 FOV 角（弧度，带符号）**。

### 1.6 屏幕空间描边偏移 `_577`（核心公式）

`V:453`（拆开 `mad`/嵌套后）：
```
dir      = normalize( mul( NonJitteredViewNoTransProjMatrix_3x3, _514 ).xy )   // 描边法线投到裁剪空间取 xy 并归一化
dir     *= float2( _BackBufferSize.y / _BackBufferSize.x, 1.0 )                // 宽高比校正
width    = _30_Stripped_224 * ( 0.3926990330219268798828125 / _543 )          // 宽度参数 × (π/8 / 半FOV)  → FOV 补偿
fade     = clamp( ( _437 * (_543 * 114.5915679931640625) ) * 0.039999999105930328369140625, 0.0, 1.0 )  // 距离淡入
_564     = dir * width * fade * 0.004999999888241291046142578125              // ×0.005 总缩放
```
常量：`0.3926990330219268798828125 = π/8`，`114.5915679931640625 = 360/π`（`_543*114.59 ≈ 全FOV(度)`），`0.04`、`0.005` 逐字保留（均 `V:453`）。

逐分量像素级下限钳制（`V:454-458`，不是最大宽度）：
```
_569 = _BackBufferSize.zw * clamp( _437, 0.0, 1.57079613208770751953125 / _543 )  // texelSize × clamp(w, 0, (π/2)/半FOV)   (V:454)
若 |_564| < _569 则取 _569*sign(_564) 否则取 _564                                    // 分量各自钳制 (V:455-458)
_577 = 上述结果 * 1.0                                                               // (V:458)
```
应用到裁剪空间 xy（`V:459-460`）：
```
_579 = ( _432.xy - (_TaaJitterStrength.zw * float2(2,-2)) * _437 ) + _577       // 去抖动后加描边偏移
_580 = float4(_579.x, _579.y, _432.z, _432.w)
```

### 1.7 深度偏移 `_606`

透视（`_unity_OrthoParams.w == 0`，`V:462-468`）：
```
_597 = -_437 + _30_Stripped_228 * (-0.100000001490116119384765625)             // 视深度上叠加 -0.1×深度偏移参数
_605.z = ( (_597 * ProjMatrix[2].z + ProjMatrix[2].w) * _437 ) / (-_597)       // 重投影出带偏移的裁剪 z
```
正交（`V:470-473`）：
```
_593.z = _432.z + ( (_30_Stripped_228 * (-0.1)) / _ProjectionParams.z )
```
常量 `-0.100000001490116119384765625 = -0.1`（`V:464,472`）。

### 1.8 顶点输出（`V:475-485`）

```
_12 = _4 * _30_Stripped_160.xy + _30_Stripped_160.zw   // UV，_30_Stripped_160 = ST(缩放.xy, 偏移.zw)  (V:477)
_13 = _425                                             // 世界位置(RWS) → 片元 TEXCOORD1
_14 = _514                                             // 描边/世界法线 → 片元 TEXCOORD2
_16 = float3(_432.xy + _577, _432.w)                   // 当前帧带偏移裁剪位 → TEXCOORD4  (V:480)
_17 = float3(_494.xy + _577, _494.w)                   // 上一帧带偏移裁剪位 → TEXCOORD5  (V:481, _494 由 Prev VP 算得 V:431)
gl_Position = _615;  _615.y = -_606.y                  // 最终裁剪位，Y 翻转  (V:482-484)
_19 = instanceIndex                                    // TEXCOORD6 (nointerpolation)  (V:485)
```
`_16`/`_17` 供片元算屏幕空间 motion vector（见 §2.4）。

---

## §2 片元着色器

片元几乎是完整 ForwardLit：base 采样 → 环境光（Irradiance Volume SH）→ 主平行光 + 分块 punctual 光循环 + 阴影 → 描边调色 → 大气/体积雾。输出两个 target。

### 2.1 base 颜色与 albedo

- `_347 = _BaseMap.SampleBias(sampler_LinearClamp, uv, _GlobalMipBias)`（`F:392`）——**与主体同一张 `_BaseMap`（t1, space1），描边 Pass 没有专用贴图**。
- `_367 = (_347.xyz * _44_Stripped_96.xyz) * _44_Stripped_232`（`F:395`，tint × 强度）。
- `_371 = lerp(luma(_367), _367, _44_Stripped_236)`（`F:396`，饱和度；luma 权重 `float3(0.21267290413379669189453125, 0.715152204036712646484375, 0.072175003588199615478515625)`，即 Rec.709，全文反复出现）。
- `_44_Stripped_252 != 0` 时用常量色 `_44_Stripped_256.xyz` 覆盖（`F:393-397`，⚠推断=纯色覆盖开关）。

### 2.2 光照（概述，非描边核心）

- **无 alpha clip / discard**：全文无 `clip()`，输出 alpha 恒为 1（`_1932.w = 1.0`，`F:933`）。描边写不透明。
- 世界法线由 `_GBufferTexture1`（t38）里 octahedral 解出的 `_464`（`F:416-431`），而**非**顶点法线——即片元重新从 GBuffer 取法线。⚠这点值得注意：描边片元的法线来自 GBuffer 采样（屏幕空间），见 §4。
- 环境光：`_CharacterParams1.y < 0.5` 时走 Irradiance Volume（三级 clipmap SH，`_IrradianceVolumeClipmapTexture{A,B}Lod{0,1,3}`，`F:435-568`）；否则用常量 `_CharacterParams3.xyz`（`F:572`）。
- 主光 + punctual 光：Z-bin / tile 分块循环（`_GlobalBinningBuffer` t51 + `_LightBinningConstants`，`F:608-921`），含 area light、shadow map PCF（`_PunctualLightShadowTexV2` t27）、屏幕空间阴影 `_ScreenSpaceShadowMask`（t22，`F:587`）。
- 累积得到最终着色色 `_1219`（`F:615` 起）。

### 2.3 共用 VFX 调色（`_44_Stripped_48 > 0.5`）

`F:924-931` 是与 ForwardLit 共用的 VFX 调色，不是描边专属改动；描边 albedo 专属的亮度/饱和度位于 F395–396。具名 ForwardLit cbuffer 可支持把共享前缀 c3.x 识别为 `_EnableVFXColorAdjustment`，但匿名尾部仍不能仅凭相邻属性顺序强认证。
```
若 _44_Stripped_48 > 0.5:
  base = lerp( lerp(0.5, lerp(luma(_1219), _1219, _44_Stripped_56), _44_Stripped_60) * _44_Stripped_52,
               _44_Stripped_128.xyz, _44_Stripped_128.w )                 // 去饱和/压暗 + 描边色混合
  rim  = _44_Stripped_144.xyz * smoothstep(1 - _44_Stripped_64, 1, 1 - clamp(_1169,0,1)) * _44_Stripped_68
  _1925 = base + rim
否则:
  _1925 = _1219                                                            // 不做描边调色
```
其中 `_1169 = dot(_318, _464)`（视线·法线，`F:606`），`1-clamp(_1169,0,1)` 是菲涅耳/边缘项。推断语义（⚠）：`_52` 亮度、`_56` 饱和度、`_60` 混合、`_128.xyz` 描边色 + `_128.w` 混合量、`_64` rim 宽度、`_68` rim 强度、`_144.xyz` rim 色。
之后 `_1932 = float4(_1925 * _ExposureWithMiscParams.y, 1.0)`（`F:932-933`，曝光缩放）。

### 2.4 两个输出

- `SV_Target0` `_10 = _2317`：`_1932` 经大气/体积雾（`_CharacterParams12.w < 0.5` 才做雾，`F:936-988`）后的最终颜色。
- `SV_Target1` `_11 = _1001`：屏幕空间 motion vector + 标志。`_983 = _6.xy/max(_6.z,9.99999993922529e-9) - _7.xy/max(_7.z,9.99999993922529e-9)`（F579），接着 `_983.y=-_983.y`（F580）；编码 `sqrt(sqrt(abs(_983*0.5)))*sign(_983)*0.5+0.5`，再由 `_970` 选择正常编码或常量 `(0.5,0.5)`（F581）。`_1001.z=1`，`_1001.w=_970?0.7:0.4`（F583–584）。`_970=(1-max(Stripped_64.y,Stripped_64.z))<0.9900000095367431640625`（F578）；字段语义和0.7/0.4用途待核，不能漏掉 epsilon、Y翻转或强制零运动分支。

---

## §3 用到的 cbuffer / 纹理 / keyword 清单

### 3.1 描边相关材质参数（per-material cbuffer，顶点 `_29_30` @ b0 space1 / 片元 `_43_44` @ b0 space1，同一 buffer）

顶点侧（`_30_Stripped_*`，`V:196-254`）：
| 偏移 | packoffset | 用途（推断） | 行 |
|---|---|---|---|
| 160 | c10 float4 | UV ST（xy 缩放, zw 偏移） | `V:477` |
| 224 | c14 | 描边宽度缩放 | `V:453` |
| 228 | c14.y | 描边深度偏移量（×-0.1） | `V:464,472` |
| 240 | c15 | 描边法线来源开关（>0.5 用 UV 烘焙平滑法线） | `V:433` |

片元侧（`_44_Stripped_*`，`F:258-316`）：
| 偏移 | packoffset | 用途（推断） | 行 |
|---|---|---|---|
| 48 | c3 | 描边调色总开关 | `F:924` |
| 52 | c3.y | 描边亮度 | `F:926` |
| 56 | c3.z | 描边饱和度 | `F:926` |
| 60 | c3.w | 描边混合 | `F:926` |
| 64 | c4 | rim 宽度（smoothstep） | `F:926` |
| 68 | c4.y | rim 强度 | `F:926` |
| 72 | c4.z | 颜色乘子（`_377`） | `F:398` |
| 76 | c4.w | 饱和度（`_963`） | `F:577` |
| 96 | c6 float4 | base tint (xyz) | `F:395` |
| 128 | c8 float4 | 描边色 (xyz) + 混合量 (w) | `F:926` |
| 144 | c9 float4 | rim 色 (xyz) | `F:926` |
| 192 | c12 | 阴影项缩放 | `F:575` |
| 208 | c13 float4 | 阴影 tint | `F:576` |
| 232 | c14.z | albedo 强度 | `F:395` |
| 236 | c14.w | 饱和度 | `F:396` |
| 252 | c15.w | 纯色覆盖开关 | `F:393` |
| 256 | c16 float4 | 覆盖色 | `F:394` |

> 其余 `_30_/_44_Stripped_*` 槽位在本 Pass 未被引用或仅参与光照，未逐一列出。

### 3.2 全局 cbuffer（两文件共用）

- `type_TransformVariables`（b12 space0）：`ProjMatrix`、`ViewMatrix`、`InvViewMatrix`、`NonJitteredViewNoTransProjMatrix`、`PrevNonJitteredViewNoTransProjMatrix`、`WorldSpaceCameraPos_Internal`、`PrevCamPosRWS_Internal`（`V:21-45` / `F:23-47`）。
- `type_ShaderVariablesGlobal`（b16 space0）：`_ScreenSize`、`_BackBufferSize`、`_ProjectionParams`、`_unity_OrthoParams`、`_TaaJitterStrength`、`_GlobalMipBias`、`_ExposureWithMiscParams`、`_CharacterParams0..15`、`_IVParam0..2`、`_IVDefaultSHA{r,g,b}`、各类 Fog 参数等（`V:47-188` / `F:49-190`）。
- `type_UnityInstancing_SRP_UnityPerDraw`（b0 space2）：`_SRP_UnityPerDraw_UnityPerDrawArray[256]`（object→world / prev matrices、标志位）（`V:190-193` / `F:192-195`）。
- 仅片元：`type_LightBinningConstants`（b48）、`type_LightDataBuffer`（b14）、`type_ShadowData`（b15）（`F:199-256`）。

### 3.3 纹理 / buffer / sampler

顶点：`_VertexSkinMatrices`（ByteAddressBuffer t18 space0，`V:195`）。
片元（`F:197-331`）：`_GlobalBinningBuffer`(t51)、`_VertexSkinMatrices`(t18)、`_PunctualLightShadowTexV2`(t27)、`_ScreenSpaceShadowMask`(t22)、`_IrradianceVolumeClipmapTexture{A,B}Lod{0,1,3}`(t35/32/34/31/33/30)、`_GBufferTexture1`(t38)、`_BaseMap`(t1 space1)、`_IntegratedLightScattering`(t36)；sampler：`sampler_LinearRepeat`(s6)、`sampler_LinearClamp`(s4)、`sampler_LinearMirror`(s7, comparison)。

### 3.4 keyword 分支
文件头 keyword 是固定编入的（`HG_ENABLE_PER_OBJECT_MV`、`HG_ENABLE_SCREEN_SPACE_SHADOW_MASK`、`SRP_INSTANCING_ON`），源码里无 `#if`，运行期分支全走 cbuffer 值（如 `_CharacterParams1.y`、`_unity_OrthoParams.w`、各 `_Stripped_*` 开关）。

---

## §4 已知不确定项（⚠待核）

1. **顶点输入语义疑似错位**：`_4` 标 `NORMAL0` 却当 UV 用（`V:477`），`_7` 标 `TEXCOORD0` 却当切线空间平滑法线用（`V:435`）。SPIRV-Cross 的语义名不可信，实际通道映射需对照真实 mesh 顶点布局核对。
2. **描边参数语义全部为推断**：§3.1 里 `_30_Stripped_224/228/240` 与 `_44_Stripped_48..68/128/144` 的「宽度/深度偏移/法线开关/描边色/rim」命名是从数学推断，CPU 侧原名已被剥离，未与材质 Inspector 对齐前不要写死。
3. **片元法线来自 GBuffer**：`_464` 由 `_GBufferTexture1`(t38) octahedral 解码得到（`F:416-431`），而非插值顶点法线 `_14`。这意味着描边片元打光依赖已存在的 GBuffer（延迟/pre-pass），在 URP14 缩水实现里如何提供该法线源需另行确认。
4. **`_1001.w = 0.7 / 0.4`（`F:584`）语义未知**：疑为 motion/material id 或 stencil 替代标志，待核。
5. **显式初始化 static**：`_290=0`（F20，用于 `_389.y` 后被2^-14覆写）、`_291=0u`（F21，雾随机数输入）和 `_288=0`（F19，采样坐标填充）不是未初始化。原始语义待核；尤其 `_291` 参与活跃雾分支，不能统一声称均无结果影响。移植时先保留常量与各使用点。
6. **`6.103515625e-05f`（`F:401`）** 强制写入 `_389.y`：该值 = 2^-14，用途（防零/高度锁定？）未确认。
7. 本 Pass **没有 alpha test**（无 `clip`/`discard`，输出 alpha 恒 1）。若主体 ForwardLit 有 alpha clip，描边这份 catch-all 变体不含，属实非猜测。

---

*转写者：Claude（Opus 4.8）；日期：2026-09-30。所有公式/常量/swizzle 逐字取自上述两只只读源文件，未做数值改写（仅将 `mad(a,b,c)` 等展开为 `a*b+c`）。*
