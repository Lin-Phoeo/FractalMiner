# 03｜离线截帧、证据匹配与 Shader 实验室

先通过第 02 章，再开始本章。目标不是“抄完几千行 HLSL”，而是建立能自己证伪的推理链：实际绘制使用了哪些输入 → 对应哪个公式 → 每一步得到什么数 → 输出差异发生在哪一步。

## 1. 截图、解包、RDC 分别能回答什么

| 数据 | 能回答 | 不能单独回答 |
|---|---|---|
| 最终截图 | 最终观感、轮廓、构图 | 颜色从哪一层算来、纹理各通道语义 |
| 解包模型/材质/贴图 | 静态内容、部分配置 | 当帧覆盖常量、实际编译变体、实时阴影与后处理 |
| RDC | 本帧GPU资源、绘制顺序、状态、实际常量与着色程序 | 原始高层C++架构、源变量名、其他未捕获场景 |
| 反编译HLSL | 编译后的表达式和绑定布局 | 未被执行的原始功能、可靠的人类命名、引擎全部控制逻辑 |

研究已有离线 `C:\Users\Administrator\Downloads\正面.rdc` 即可开始；不要因为正常抓帧受到保护程序阻止，就去关闭或隐藏保护。已有捕获不要求运行游戏。更换游戏版本或相机后，ResourceId/Event ID 都可能改变，不能照抄本帧编号。

## 2. 一次完整的手工 RenderDoc 阅读

1. 用官方 RenderDoc 打开 `正面.rdc`，确认 Vulkan、frame 6411，而不是另一份 capture。
2. 在 Event Browser 找 875，查看 Pipeline State。记录 render target、深度、顶点/片元 shader ID、材质纹理集合与常量缓冲。
3. 对比 860、786、835、776。同一个角色的不同部位不会共用完全相同的纹理槽。
4. Texture Viewer 分别查看 BaseMap、法线、ramp、mask 的 R/G/B/A；不要把“看起来像灰图”当成压缩数据坏掉。
5. Mesh Viewer 检查 VS Input 与 VS Output。前者是输入属性，后者是该 draw 变换后的结果；不要混用其坐标空间。
6. 向前追某张 render target 的最后一次写入事件，再看消费者；依此画出 Pass 图。
7. 把观察写成表：事件、用途、输入ID/尺寸/格式、输出ID、状态、证据等级、未确定项。

本帧主颜色事件：776 iris，786 body，835 cloth_01，850 cloth_02，860 face，875 hair。仅凭“同一个 mesh 又画了一次”不能删除后面的 draw，它可能是眼影、轮廓、深度或特效覆盖。

## 3. 自动导出只是记录工具，不代替理解

在 PowerShell 先把目录变量设成自己的实际路径。本例只写新的本地输出目录：

```powershell
$repo = 'A:\Hypergryph Launcher\games\Arknights Endfield\FractalMiner'
$env:ENDFIELD_CAPTURE_PATH = 'C:\Users\Administrator\Downloads\正面.rdc'
$env:ENDFIELD_CAPTURE_OUTPUT = Join-Path $repo 'Validation\Captures\manual-learning-inventory-01'
$env:ENDFIELD_CAPTURE_DETAILS = '1'
$env:ENDFIELD_CAPTURE_PREVIEW = '1'
& 'C:\Program Files\RenderDoc\qrenderdoc.exe' --python (Join-Path $repo 'Tools\capture_replay_inventory.py')
Get-Content (Join-Path $env:ENDFIELD_CAPTURE_OUTPUT 'complete.json')
```

输出目录必须为空。只看到窗口退出不算成功：检查 `complete.json`、`error.json` 和实际文件。当前基准应为 246 draws、44 dispatches。脚本不注入进程；读原始 RDC，输出独立文件。

读代码顺序：`open_controller` → `collect_inventory` → `collect_draw_details` → `shader_variable` → `run`。理解 `try/finally` 为什么同时负责释放 controller 与 capture file。

**重要 API 陷阱：** Vulkan binding number 不是反射列表下标。例如 shader 只有一个常量缓冲，列表 index=0，但其 binding=17，读取时必须使用 index=0。参考 [RenderDoc 官方 descriptor 说明](https://github.com/baldurk/renderdoc/blob/v1.46/docs/python_api/in_depth/descriptors_bindings.rst)。

## 4. 没有变量名时怎样认常量

把每个 captured variable 的类型、偏移、长度与 HLSL `packoffset(cN.x)` 对齐。一个 c 寄存器是 16 字节；`c12.x` 的偏移是 192 字节。float3 的后面是否还能放一个 float，需要按缓冲布局规则计算，不能简单“第几个变量对第几个变量”。

建立如下证据链：

```text
UPM字节长度吻合
  → 每字段 offset/type/size 吻合
    → set/binding集合吻合
      → 纹理尺寸/格式/通道用途吻合
        → 源公式真的使用对应字段
          → 相同输入CPU/GPU数值吻合
```

任何一级出现矛盾，都要重新选候选，不要把后续参数调漂亮来遮盖。

真实反例：body786 的 UPM=368 字节，cloth b401 的长度也相同。旧工具又把 body 限定在 cloth 文件夹，于是误选。可实际 t1 是 1024×32 LUT，t2 是 256×1 diffuse ramp；b401 却把它们当 P 图与 clearcoat mask。正确候选族是 skin b114/b208。身体光照应与脸一样使用 CP3/CP4，不能再沿错误候选解释成 CP2/CP5。

当前工具 `Tools/extract_front_frame_constants.py` 已扩大到全族评分，并对本帧经过核验的 786/835 纹理语义添加约束。还有歧义的项目明确保留，不声称文件名已经唯一确定。读取新 `extracted-source-shading-reviewed-20260923`，不要继续信旧 `extracted` 里的 body 属性名。

自己提取时必须显式指定三个目录，避免使用默认输出覆盖旧报告：

```powershell
Set-Location $repo
$details = 'Validation/Captures/manual-learning-inventory-01'
$dump = '_dump_1.5.3/AllShader_1.5.3/Assets/packages/com.hg.render-pipelines/runtime/shaders/materials/characternpr'
$out = 'Validation/Captures/manual-learning-constants-01'
if (Test-Path -LiteralPath $out) { throw '请换一个新的输出目录' }
& '..\EndfieldUnpacker\.venv\Scripts\python.exe' Tools/extract_front_frame_constants.py $details $dump $out
Get-Content (Join-Path $out 'summary.md') -TotalCount 60
```

先确认 `$details` 有 `inventory.json` 和 `draw-details.json`，`$dump` 有相应HLSL目录。脚本输出的 MISMATCH 不能删掉；它们是未解决或无法唯一匹配的证据。

练习：暂时在**自己的副本**把 body 的 folder hint 改错，运行 `test_wrong_hint_cannot_exclude_better_global_match`，理解为什么正确实现仍必须选更强证据。

## 5. 学 HLSL 的最短有效路径

先掌握以下运算，每个都做一次手算和 Shader 输出：

| 运算 | 含义 | 易错点 |
|---|---|---|
| `dot` / `cross` | 投影/夹角；正交方向 | 非单位向量的 dot 不是角度余弦 |
| `normalize` | 只保留方向 | 零向量要有明确处理 |
| `lerp(a,b,t)` | a到b的线性插值 | a/b 颠倒会让 mask 方向相反 |
| `saturate` | 限制0到1 | 随手加 clamp 可能改变原函数，尤其SDF/ramp坐标 |
| `smoothstep` | 平滑过渡 | 参数次序、区间、反向区间必须按原式核对 |
| `mul(M,v)` 与 `mul(v,M)` | 矩阵/向量乘法 | 转置与坐标空间约定不能靠名字猜 |
| `Sample` / `SampleLevel` | 纹理采样 | sampler地址模式、LOD、sRGB解码会改变数据 |
| `asuint` | 重新解释位模式 | 不是普通数值转换，极小float不一定没用 |

顺序：纯色 → UV → 法线 → Lambert → ramp → 高光 → 专用材质。每步保存最小场景和一张调试输出。

## 6. 四个材质实验室

### 6.1 共用 diffuse/ramp 实验

固定 albedo=(.2,.3,.4)、P图=(0,0,1,.5)、ramp RGB=(1,1,1)，只改变 ramp alpha=0/.5/1，禁用高光。

旧版把 ramp 当 RGB 颜色相乘，三个结果相同。真实公式里 alpha 控制 litMask、环境染色、阴影混合，三个输出必须不同。独立 CPU 期望已经放在 `EndfieldOfficialShadingValidation.Expected`。先在纸上算它，再看 HLSL，不要两份代码互相照抄后宣称验证成功。

源码入口：`EndfieldOfficialHair.hlsl` 的 `EFHairDiffuseLighting`；`EndfieldOfficialCloth.hlsl` 的 `EFClothDiffuseLighting`。蓝色 P 通道进入遮挡混合，不是最终颜色统一乘 AO。

### 6.2 Skin / body

- g=0 选择 SDF，g=1 选择普通 N·L。用全0/全1两张 mask 单独验证方向。
- 阴影 LUT 用 rim 染色前的 albedo，先转换索引颜色到 sRGB，再找32个蓝色切片。
- 法线的 RGorAG 解码：`x=2*R*A-1`，`y=2*G-1`，z由单位长度补出；不要把 normal texture 当颜色图读。
- direct GGX 用原始贴图法线；SDF 重建法线不该替代它。
- body 没有 SDF/面部高光图，使用等价 mask=(1,1,1,0) 的皮肤分支。

练习：把 BaseMap alpha 从1改成.25，检查颜色变化但表面仍不透明；让 SDF ramp 坐标跨过1，确认 Repeat 行为。对应 21 项 `EndfieldSkinShadingValidation`。

### 6.3 Hair / cloth

头发先理解 T、B、N 各向异性方向，再实现主/副高光，最后接 LineMap。不要同时改变 flow、roughness、光向、曝光，否则无法定位差异。

布料的 specRamp 是二维查表：x 与 GGX 分布或 N·V² 有关，y 与粗糙度和金属度有关；不等价于 `(N·H,.5)`。clearcoat 若启用有独立法线/粗糙度；环境 IBL 与直接高光的缩放不同。

练习：P图四通道各做一个0/1棋盘，明确谁影响金属、镜面、遮挡、smoothness；再输出 specRampUV 调试颜色，不看最终漂亮与否。

### 6.4 Eye

raw UV 负责解析虹膜球面，ST 只负责具体贴图方向。模组 Y 翻转不应先作用在球面坐标上。b28 固定视差，与旧布料 `_UseParallax` 开关不是同一个功能。

matcap 合成不是简单相乘：`matcap.rgb*color.a + color.rgb*matcap.a`。练习固定两组RGBA手算；改变 alpha 时不能把虹膜挖透明。

## 7. 编译、单元实验、整体验证缺一不可

```powershell
$repo = 'A:\Hypergryph Launcher\games\Arknights Endfield\FractalMiner'
& 'A:\Unity\Editor\2022.3.30f1\Editor\Unity.exe' -batchmode `
  -projectPath $repo -executeMethod EndfieldShaderPack.EndfieldOfficialShadingValidation.RunAll `
  -logFile (Join-Path $repo 'Logs\manual-shading-validation.log') -quit
```

先关闭打开同一工程的其他 Unity 编辑器，别为了运行测试强杀正在编辑的实例。看最终退出码、日志异常、各报告的 PASS；检查生成的 scene/asset/PNG，不只看最后一行。

`RunAll` 不仅测试公式，还会调用珊瑚海岸修复和官方场景回归，因此需要原工程的mod目录、原版 `Typhoeus_Showcase.unity`、已导出的角色资产。若你只做最小数学练习，分别把入口改为 `EndfieldShaderPack.EndfieldOfficialShadingValidation.RunNumerical` 和 `EndfieldShaderPack.EndfieldSkinShadingValidation.RunNumerical`：它们创建合成纹理和平面，不需要游戏贴图或mod。不要为了让全量脚本通过而下载不相关资源。

验收层级：Shader 能编译 → 常量输入数值正确 → 实际材质纹理正确 → 整个人物可见 → 多视角/动态正确 → 官方画面对齐。32 项数值测试没有覆盖全游戏的雨雪、点光、所有材质变体；不能把通过率写成“官方还原率100%”。
