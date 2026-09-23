# 2026-09-23 角色自阴影证据导出与坐标约定验证

接续 `official-source-shading-20260923.md`。本文记录阶段2-1/2-2 的产物、以及**在写任何 GPU resolve 代码之前就已解析确认的坐标约定**。这些约定是交接文档要求 1-tap 实验优先验证的项，提前确认可以避免把"深度符号搞反"误诊成"矩阵方向搞反"。

## 1. 产物

```text
Tools/capture_character_shadow_evidence.py            导出器
Tools/tests/test_capture_character_shadow_evidence.py 32 项单测（全套 90/90 通过）
Validation/Captures/tifuluosi-front-20260917/
  character-shadow-constants-02/   常量模式（含 transform/global cbuffer）
  character-shadow-01/             完整模式，5 纹理各 DDS+EXR，292MB
```

两个目录均 gitignore，不进 GitHub。

## 2. 事件与绑定契约（实测，非推断）

事件 **748** = `ScreenSpaceShadowResolve_Character`，输出目标 `ResourceId::58932`（R8G8_UNORM 2560×1600），深度目标 `58980`（D32S8）。事件 744 是方向阴影 pass，**两者写同一个 58932**：R = 方向项（本帧恒 1），G = 角色自阴影。

绑定契约由反射 index → `fixedBindNumber` 解析后与反编译声明逐一核对：

| register | 资源 | 语义 | 格式 |
|---|---|---|---|
| t4 | `58994` | GBuffer1 法线 | R10G10B10A2_UNORM 2560×1600 |
| t5 | `58985` | GBuffer0 角色索引 | R10G10B10A2_UNORM 2560×1600 |
| t7 | `32538` | 角色 shadow atlas | D16 4096×2048 |
| t8 | `59000` | camera depth | R32_FLOAT 2560×1600 |

GBuffer 是 R10G10B10A2 正好解释官方索引解码里的 `*1023`（10 位）与 `*3`（2 位）。

**绑定号不可用作契约**：同一 cbuffer 在 748 是 binding 13、在 744 是 binding 12。这与上游作者所述"Bindings 魔改成 Vulkan 风格 DescriptorSetParams（PackedBinding/PackedInfo）、可能绕过 hlslcc 直接用 Vulkan 工具链编译"一致，也是反射把常量名全剥成 `_childN` 的原因。因此定位方式只有两种可靠：**块按字节大小、字段按 packoffset×16**。

## 3. cbuffer 定位与字段偏移

| cbuffer | 声明 | 大小(B) | 取用字段 |
|---|---|---|---|
| `type_ShadowData` | register(b13, space3) | 11440 | 见下 |
| `type_TransformVariables` | register(b11, space3) | 1312 | `InvViewProjMatrix`@c24、`WorldSpaceCameraPos_Internal`@c44 |
| `type_ShaderVariablesGlobal` | register(b14, space3) | 3200 | `_ScreenSize`@c0 |

ShadowData 字段（数组均 15 槽，本帧 `Params.z=7` 表示前 7 槽有效）：

```text
CharacterWorldToShadow[15]      c448  byte 7168   15 × 4x4
CharacterShadowBiases[15]       c508  byte 8128   15 × float4
CharacterShadowLightDir[15]     c523  byte 8368   15 × float4
CharacterShadowAtlasParams[15]  c538  byte 8608   15 × float4
CharacterShadowTexelSize        c553  byte 8848   float4
CharacterShadowParams           c554  byte 8864   float4
```

28 个 child 的尺寸累加恰好等于 11440，无余量、无重叠。导出器带**布局漂移测试**：把 child14 从 47 项改成 48 项使后续偏移错位，必须硬失败而不是静默返回错数据。

### 自证契约

`_ScreenSize` 提供了不依赖任何外部假设的映射校验：官方 pass 用 `pixel * _ScreenSize.zw` 算 UV，所以 zw 必须是 xy 的倒数，且 xy 必须等于输出目标真实尺寸。实测：

```text
screen_size = [2560.0, 1600.0, 0.0003906250058207661, 0.0006249999860301614]
              = [2560, 1600, 1/2560, 1/1600]   与 58932 的 2560×1600 一致
```

该检查失败即中止导出，因此"块定位/字段偏移正确"不是假设而是每次运行都被验证的前提。

## 4. 坐标约定：column-major 存储 + reversed-Z（已解析确认）

实测值：

```text
worldSpaceCameraPos = (-300.0, 300.779999, -297.040009, 0)
invViewProjMatrix 连续 16 float：
  f[0..3]   = (-0.5044781,  0.0,          0.0,          0.0)
  f[4..7]   = ( 0.0,       -0.31528845,  -0.00255703,   0.0)
  f[8..11]  = (-2999.97045898, 3007.77050781, -2970.37084961, 9.99990177)
  f[12..15] = (-0.0298306, 0.03789175, -1.02935684, 0.00009894)
```

声明是 `column_major float4x4`，即**每 4 个连续 float 是一列**，`col_j = f[4j..4j+3]`。官方 pass 做 `mul(InvViewProj, float4(ndc.x, -ndc.y, depth, 1))` 后再除 w。

验证一（depth=1）：

```text
M·(0,0,1,1) = col2 + col3 = (-3000.0, 3007.81, -2971.40, 10.00000)
xyz / w     = (-300.00, 300.78, -297.14)
cameraPos   = (-300.00, 300.78, -297.04)      差 0.10 / 约 300，即 0.03%
```

验证二（depth=0）：

```text
M·(0,0,0,1) = col3 = (-0.0298, 0.0379, -1.0294, 0.00009894)
xyz / w     = (-301.4, 383.0, -10403)         远离相机
```

两条合起来的结论：

1. **列优先解释正确**（若按行优先解释，验证一不会落在相机位置上）。
2. **depth=1 → 近平面（≈相机位置），depth=0 → 远平面**，即 **reversed-Z**。
3. 矩阵含 10× 的整体尺度（`col3.w = 9.9999e-5`、`col2.w = 9.9999`），除 w 时被消掉，实现时**不要预先归一化**，必须保留 w 除法。
4. 官方在乘之前把 ndc.y 取负（`_284.y = -_281.y`，其中 `_281 = uv*2-1`）。这是 Vulkan/D3D 的 Y 方向约定差异，与本项目已记录的"EXR 与 GPU 坐标有 Y 方向约定、LUT 也需 Y 翻转"同源，实现时按原样保留，不要"顺手修正"。

## 5. 其余实测常量

```text
CharacterShadowParams     = (1, 1, 7, 0)                  .z=7 -> 7 个有效角色槽
CharacterShadowTexelSize  = (1/4096, 1/2048, 4096, 2048)  与 atlas 4096×2048 自洽
CharacterShadowLightDir   = 7 槽全部相同 (-0.176319, -0.529919, -0.829516, 0)，模长 1.0
AtlasParams[0..6]         = 每槽 zw=(0.25,0.5)，xy 取 (0,0.5),(0.25,0),(0.25,0.5),(0.5,0),(0.75,0),(0.75,0.5),(0,0)
                            即 4×2 网格用 7 格，每格 1024×1024
Biases[0]                 = (0.003473, 0.006946, 0.001158, 256.0)
                            .w 逐槽为 256,512,1024,2048,4096,8192,16384（2 的幂，语义待查）
```

7 槽光向完全相同，说明本帧只有一个方向光参与角色阴影。这给阶段3 一个可判定检验：把该光向与 frame6411 的相机 forward 求夹角，即可判定第三方赏析文所说的"局内把光照方向摆正到相机方向"是否成立。

## 6. 导出后独立复核（不经 Unity）

`screen-shadow-resolved.dds` = 8192128 B = 128 头 + 2560×1600×2，未压缩 R8G8，可直接解析：

```text
R 通道 distinct=1 且全为 255         -> 证实"R 恒 1"，本帧方向项被常量短路为全亮
G 通道 distinct=238，min=0，max=255  -> 证实"G 范围 0~1"
G/255 < 0.99 的像素 = 116890 / 4096000
```

**阈值陷阱**：116890 对应 `byte/255.0 < 0.99`（即 `byte < 253`）。若误用 `byte < round(0.99*255) = 252`，得到 115618，差的正好是 `count(252)=1272`（1.1%）。做 GPU 逐像素对照时这会被误判成 resolve 实现错误，务必按浮点阈值比较。

## 7. 尚未做

- GPU resolve 实验（1-tap → 16-tap Poisson/GatherRed + 软化）未开始。
- 动态 shadow depth/atlas 未开始。
- `EndfieldCharacterLit.shader:576-578` 仍是 `float selfShadow = 1.0;`，**未改**。
- Unity 侧实现要点已确认可用：本地 URP core 14.0.11 的 `ShaderLibrary/API/D3D11.hlsl:158` 定义 `GATHER_RED_TEXTURE2D(tex,samp,coord2) -> tex.GatherRed(samp,coord2)`，D3D11 分支支持（GLES2 不支持）。官方角色路径用的是**普通 GatherRed + 手动减法 + step**，不是 `SampleCmp`/`GatherCmp`，所以需要 Mirror 寻址的普通采样器而非比较采样器；这与同文件里 CSM 路径用 `SampleCmpLevelZero(sampler_LinearMirrorOnce, ...)` 不同，不要混用。

## 8. 外部参考（本地留存，不入库）

`Validation/LocalReference/` 下两份第三方摘要，均标注来源与"冲突时以捕获证据为准"：

- `zhihu-endfield-urp-toon-digest.md`：URP 复刻教程摘要。最有价值的一条是它给出的角色着色消费屏幕空间阴影的方式 `min(_ScreenSpaceShadowmapTexture, PerObjectScreenSpaceShadowmap)`，与本项目"统一屏幕空间 shadow 纹理 + 逐角色 atlas 槽"的方向一致；另指出刘海阴影可能是**独立错位网格 + 模板渲染**，这是阶段4 排查 draw call 的具体假设。
- `zhihu-endfield-rendering-appreciation-digest.md`：TA 观感赏析（作者自称"纯顶针，不保真"，无截帧）。其中"角色甚至可能没有采样间接光"与本项目已验证的 `ResourceId::14188` 环境 cube 绑定**直接冲突，该论断为错**；但"角色在不同曝光下几乎没变"这一观察值得在阶段5 单独验证。

原始网页正文抽取件在 `Validation/LocalReference/raw/`，抽取脚本 `extract_html.py`（仅标准库，venv 无 bs4/lxml）。整个 `Validation/LocalReference/` 已 gitignore，第三方版权内容不入库。

## 9. 由外部资料确认的实现约束（阶段2-3 直接适用）

### 9.1 用普通 GatherRed，不要用 SampleCmp

官方角色路径是 `GatherRed(sampler_LinearMirror, uv) - refDepth` 后接 `step(0, ·)` 手动比较，**不是** `SampleCmp`/`GatherCmp`；同文件的 CSM 路径才用 `SampleCmpLevelZero(sampler_LinearMirrorOnce, ·)`。两条路径不能混用。

这不只是风格问题。第三方踩坑记录（GuardHei《用 TextureArray 实现 Shadowmap 的一个坑》）指出：`SampleCmp` 作用于 `Texture2DArray`/`TextureCubeArray` **需要 Shader Model 4.1+**，Unity `#pragma target 4.0` 下会报 `cannot map expression to ps_4_0 instruction set`，而微软 SM4.0 文档并未标注这一限制。该作者给出的降级方案正是"Gather 邻近 4 个深度值、单独比较、手动 lerp"——**与官方角色路径的做法一致**。因此官方的手动比较是可移植性选择，实现时应原样保留。

本地可用性已核实：`Library/PackageCache/com.unity.render-pipelines.core@14.0.11/ShaderLibrary/API/D3D11.hlsl:158` 定义 `GATHER_RED_TEXTURE2D(tex,samp,coord2) -> tex.GatherRed(samp,coord2)`（GLES2 分支为 `ERROR_ON_UNSUPPORTED_FUNCTION`）。新 resolve shader 应声明 `#pragma target 4.5` 或以上——现有 `EndfieldCapturedPost.shader` 用 4.5、`EndfieldCharacterLit.shader` 用 5.0，`EndfieldCaptureCubeProbe.shader` 的 3.0 不可作为参照。

### 9.2 atlas 跨格泄漏：复现，不要修正

用实测常量算 Poisson 采样的实际触及范围：

```text
max |TBL247[k]|          = 1.233932
offset scale 4*TexelSize.x = 4 * (1/4096) = 1/1024  (atlas UV)
最大 UV 触及             = 1.233932 / 1024 = 0.00120501 atlas UV
                         = 4.94 个 atlas texel
加上 GatherRed 自身 2×2 footprint ≈ 6 个 atlas texel
每个角色格 = 0.25 × 0.5 atlas UV = 1024 × 1024 atlas texel
```

即距格边约 6 texel（格宽的 0.6%）以内的像素，其 Poisson 采样会跨格取到**相邻角色**的深度。官方代码在此处没有任何 clamp/inset，`_863.xy` 的 `<=0 || >=1` 检查只保证中心点落在格内，不约束 16 个偏移采样点。

=> 实现时**不要**加 clamp、不要加 padding、不要"修好"它。逐像素对照官方 G 通道时，格边 6 texel 内的差异属于官方行为的一部分。若对照不上，先怀疑自己的寻址模式（必须 Mirror）与偏移旋转，而不是先怀疑泄漏。

### 9.3 八面体法线解码的折叠轴是 Y，不是 Z

第三方（次次先生《使用八面体映射传递球形法线》）解包鸣潮与终末地后，发现模型存在一个**菱形分布的 UV 通道**，并用 RenderDoc 逆向出八面体编码，推测该通道是**头发高光用的平滑法线**。其给出的 encode（Blender/Python，Z 为折叠轴）：

```python
l1 = abs(x)+abs(y)+abs(z); x/=l1; y/=l1; z/=l1
if z < 0:
    x, y = (1-abs(y))*sign_nz(x), (1-abs(x))*sign_nz(y)
u, v = x*0.5+0.5, y*0.5+0.5
```

与官方 `screenspaceshadowresolve.shader:878-893` 的 decode 对照，二者互为精确逆运算，但**折叠轴不同**：

```hlsl
float2 e = GBuffer1.Load(px).xy * 2.0 - 1.0;
float  z = 1.0 - dot(1.0.xx, abs(e));          // 重建分量
float3 n = float3(e.x, z, e.y);                // 重建分量落在中间的 Y
if (z < 0.0) {                                 // 折叠判据作用在 Y 上
    float2 xz = n.xz;                          // = e
    bool2  sg = (xz.x >= 0.0, xz.y >= 0.0);
    float2 f  = (1.0 - abs(n.zx)) * float2(sg.x ? 1:-1, sg.y ? 1:-1);
    n = float3(f.x, n.y, f.y);
}
n = normalize(n);
```

关键点：官方把重建分量放在 **Y（中间）**，折叠判据是 `z_var = 1-(|e.x|+|e.y|) < 0`，即**折叠轴是 Y（Y-up 约定）**；通用/Blender 公式以 Z 为折叠轴（Z-up）。照抄通用八面体公式会得到轴序错误的法线。符号判据是 `>= 0 ? 1 : -1`，与 encode 的 `sign_not_zero`（0 视为正）一致。

该 decode 是本文所有结论中**唯一直接来自官方 dump** 的一条，阶段2-3 必须原样使用。

### 9.4 阶段4 新线索：模型 UV 里的八面体平滑法线尚未接入

本地现状核查：

| 位置 | 现有做法 | 是否八面体 |
|---|---|---|
| `EndfieldCharacterLit.shader:765` | `snTS.z = sqrt(saturate(1.0 - dot(snXY, snXY)))` | 否，切线空间二分量重建 |
| `EndfieldCharacterLit.shader:831` | `sphereN.z = sqrt(saturate(1.0 - dot(ndc, ndc)))` | 否，球面法向 |
| `Assets/Scripts/SmoothNormals.cs` | CPU 算平滑法线，经 TBN 转切线空间后写 `mesh.SetUVs(7, ...)` 三分量 | 否 |
| `EndfieldNormalDecompress.cs` | 解压 Endfield 打包的**法线贴图**格式 | 与八面体无关 |

即：9.3 的八面体解码目前只用于屏幕空间 GBuffer1（阶段2-3 会用到），而**模型网格上那个菱形 UV 通道（八面体编码的平滑法线，疑似头发高光用）在本项目里完全没有接入**。这与上游作者"我没有实现法线解码函数，需要在 shader 加上法线解码"的说法吻合。

=> 阶段4 待办：确认导入的提弗洛斯网格是否存在菱形分布的 UV 通道，若有，用 9.3 的 Y 折叠 decode 解出平滑法线，与现有头发高光路径（已定案的 b125 RGorAG 法线 + LineMap）对照，判断二者是同一套数据的两种用法还是两套独立数据。**在数值对照之前不要替换已通过的头发高光实现。**

### 9.5 两条对后续阶段有约束力的观察

- **"日光直射强度"双状态**（秋大叔）：主光强度随时间/天气变化，且人物在墙角时应去除与主光相关的边缘光等效果，因此几乎所有着色环节都按"直射/非直射"走不同分支。=> 阶段5 做官方帧差分时必须同时锁定该状态；frame6411 只是单一状态的一张图，不能外推。候选对应字段：`_DirectionalShadowParams.x`、`_DirectionalShadowParams2.zw`。
- **刘海阴影可能是独立错位网格 + 模板渲染**（秋大叔）："截帧时应该能拿到一个特殊的刘海模型，还帮你错位好了，直接做一个模板渲染即可"。=> 阶段4 应先在捕获 draw call 中找"与头部同源、顶点已错位、带 stencil 状态"的 draw，而不是假设它是屏幕空间效果。这与 Tiansing 的"overlay pass 做内偏移当 shadowproxy"互相印证，也对应本地已有的 `characternpr_overlayshadow` dump。

