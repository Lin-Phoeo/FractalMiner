# 04｜从材质正确到官方画面：管线与验收

本章说明后续完整还原所需的技术路径，并把已经有数值证据的部分和仍在研究的部分分开。完成几何与单个 Shader 后，最大的误区是靠调色把缺失的光照、阴影和相机问题一起“调像”。这样在正面可能接近，转动角色就暴露错误。

## 1. 最终颜色经过什么

```text
材质主颜色（linear HDR）
  + 正确的环境反射/阴影/覆盖层
  → 当帧HDR颜色19394
  ├─ 13-tap prefilter → 8次downsample → 8次upsample → Bloom58923
  └─ sharpen → exposure → Bloom合成 → vignette
       → LogC编码 → LUT19397 → sRGB编码 → dither → RGBA8输出19599
```

这不是对所有游戏/场景的普遍声明，而是本帧 event1205 的实际路径。原始片元程序是 PS36235，参考 HLSL 是 `postprocessing/uberpost/Sub0_Pass0_Fragment_b354.hlsl`。不要用名称相似但关键字不同的 post pass 代替。

## 2. 导出时就可能丢掉信息

PNG适合看最终画面，不适合保存大于1的HDR光照、BC6H预滤波反射或16-bit LUT。压缩块和全部 mip 保留在 DDS；EXR用于浮点分析与Unity线性导入。把 EXR 当 sRGB 导入、自动缩小2560×1600、或者重新生成环境 mip，都可能让正确 Shader 输出错误。

当前已有可复现的离线导出器：

```powershell
$repo = 'A:\Hypergryph Launcher\games\Arknights Endfield\FractalMiner'
$env:ENDFIELD_CAPTURE_PATH = 'C:\Users\Administrator\Downloads\正面.rdc'
$env:ENDFIELD_CAPTURE_OUTPUT = Join-Path $repo 'Validation\Captures\manual-learning-pipeline-01'
$env:ENDFIELD_TOOLS_PATH = Join-Path $repo 'Tools'
& 'C:\Program Files\RenderDoc\qrenderdoc.exe' --python (Join-Path $repo 'Tools\capture_pipeline_export.py')
Get-Content (Join-Path $env:ENDFIELD_CAPTURE_OUTPUT 'complete.json')
$env:ENDFIELD_PIPELINE_EXPORT = $env:ENDFIELD_CAPTURE_OUTPUT
```

最后一行把本次导出目录交给Unity导入器；它与导出器的变量名不同。随后从同一终端启动Unity验证。已经打开的Unity不会继承新终端的环境变量，需保存后关闭并从此终端重开；不设置时导入器读取本工程默认的 `pipeline-textures-01`，不是上面新建的学习目录。

新目录、完成标志、资源ID/尺寸/格式检查、每文件SHA-256，四项都要保留。本导出计划明确限定 frame6411，不应拿它盲扫其他捕获。

| 数据 | 捕获属性 | 使用原则 |
|---|---|---|
| 14188 环境cube | 128²、6面、8mip、BC6_UFLOAT | 全面/全mip保存，不能当普通2D图 |
| 58932 屏幕阴影 | 2560×1600、R8G8 | 数据图，不做sRGB解码 |
| 19397 调色LUT | 1024×32、RGBA16F | linear、Clamp、bilinear、无mip |
| 19394 HDR输入 | 2560×1600、RGBA16F | 原始尺寸，不压成8-bit |
| 58923 Bloom | 1280×800、R11G11B10F | 仅作为生成算法对照，不贴进实时场景 |
| 19599 post输出 | 2560×1600、RGBA8_UNORM | Shader已编码sRGB，数值比较时不再解码 |

RenderDoc 的 DDS 保存可选所有切片与 mip；EXR只取指定面和级别。[TextureSave 官方定义](https://github.com/baldurk/renderdoc/blob/v1.46/renderdoc/api/replay/control_types.h)。

Unity 导入入口 `EndfieldCaptureAssets.ImportAll` 会验证校验和。生成资产在 `Assets/EndfieldShaderPack/GeneratedCapture`，默认不上传 GitHub。BC6H cube 直接读 DDS 子资源，不重新压缩或重新生成预滤波 mip。Unity 每面/每级写入 API 见 [Cubemap.SetPixelData](https://docs.unity3d.com/2022.3/Documentation/ScriptReference/Cubemap.SetPixelData.html)。

## 3. 环境反射不是“随便挂个天空盒”

反射向量通常形如 `reflect(-V,N)`；roughness决定LOD。当前cloth源码是 `lod=1.2*log2(max(roughness,.001))+5`。mip不是单纯模糊贴图的缓存，而是不同粗糙度下预处理后的环境能量。

自主练习：

1. 自制六个纯色面，验证 +X/-X/+Y/-Y/+Z/-Z 的面序。
2. 每个面画不同方向的渐变，再验证面内上下/左右方向；纯色面无法发现翻转。
3. 用已知法线与视向手算反射方向，GPU采样验证。
4. 使用捕获cube时，把每面GPU采样与独立EXR面导出比较，避免仅凭“看起来不黑”判定正确。
5. 逐级查询mip数据，不用 `Apply(true)` 重算；检查roughness变化没有异常跳变。

未绑定 cube 的默认值不保证是黑色。上一阶段数值测试已经发现它会额外贡献布料亮度，所以用显式 `capturedEnvironment`/available标记管理；不要依赖隐式默认。

## 4. 先还原后处理，再接实时画面

把官方19394、19397、58923作为已知输入，向Unity的linear浮点RenderTexture输出**原始sRGB编码值**，与19599对应像素比较。这隔离了模型、灯光、姿态等不确定因素，是最有力的排错顺序。

本轮已经验证：在正确的导出坐标约定下，2560×1600整帧全部RGB通道误差不超过1个8-bit色阶，平均约0.12色阶。这个结果证明选定post pass在该输入上的数值对应，**不证明Unity新模型已经与官方画面相同**。

LogC 本帧明确采用：

```text
logC(C) = saturate(0.2441609949 * log10(max(5.55555582*C + 0.04799599946,0))
                    + 0.3860360086)
```

它不是直接套一个名字相同的现成函数。先验标量：C=0→约.0640377；.18→.3910070；1→.5687816；4→.7150978。然后将 logC 的 RGB 当作32³ LUT 的三维坐标：R/G定位片内，B选相邻两个蓝色切片并插值。

### 避免两次Gamma

参考测试写到 linear float RT，保存的是源Shader算出的sRGB数值；实时Unity相机最终还可能由硬件做linear→sRGB。因此实时Pass先把源sRGB+dither解码回linear交给Unity最终输出，不能直接让同一编码执行两次。

相关入口：

- `EndfieldCapturedPost.shader`：两个Pass共用公式，Pass1供Graphics.Blit参考测试，Pass0供URP实时。
- `EndfieldCapturedPostProfile`：相机级显式开关、LUT、采样方向、捕获常量。
- `EndfieldCapturedPostFeature`：URP14 RTHandle/Blitter执行；不使用Built-in管线的OnRenderImage。
- `EndfieldCapturePipelineValidation`：输入、坐标、量化与全帧差分实验。

URP版本适配先读本机PackageCache，不能只看manifest。当前manifest/lock请求14.0.12，实际缓存package.json为14.0.11；本轮使用二者兼容的14系列API，未升级引擎。[URP全屏Blit官方示例](https://docs.unity3d.com/Packages/com.unity.render-pipelines.universal@14.0/manual/renderer-features/how-to-fullscreen-blit.html)。

## 5. 动态 Bloom 必须自己生成

原捕获Compute三类kernel：20453 Prefilter、20455 Downsample、20463 Upsample。单纯“开URP Bloom”不保证相同算法或参数。

尺寸为：1280×800 → 640×400 → 320×200 → 160×100 → 80×50 → 40×25 → 20×13 → 10×6 → 5×3，然后8次上采样回1280×800。25→13→6并非每一步都向上取整，也不是递归向下取整，必须按捕获的实际尺寸查证。

你要掌握：

- prefilter 的13个采样、软阈值、Karis亮度加权。
- downsample 的9-tap卷积与groupshared，为什么barrier不能被部分线程提前return绕开。
- half打包/解包和R11G11B10存储量化为何导致不同GPU有细小差异。
- upsample 的bicubic重建与 `lerp(high,low,.77)`；不是直接相加。
- 中间RT的创建、尺寸变化、释放和相机生命周期。

验证顺序：黑色 → 纯色HDR → 单像素脉冲 → 水平/竖直梯度 → 棋盘 → 官方HDR输入。先对第一层59945，再逐层比，最后对58923。最终调色很容易掩盖Bloom误差，不能只看最后PNG。

动态实现入口是 `EndfieldCapturedBloom.compute/.cs`，每帧读取当前camera颜色。原版58923只用于reference测试，实时模式禁止把它当作当前角色Bloom。

### 本轮实际排错：不是权重错，而是写入量化错

在本机D3D11上，R11G11B10报告支持LoadStore，却不支持Sample/Linear。本实现改用RGBAFloat保存值，但每次写入仍显式量化到R11/G11/B10的可表示数，不能简单“提高精度”后就当成原版。

第一版采用round-to-nearest-even，17层误差全部偏亮，最终相对L1为0.05620586。把算法、阈值、采样位置保持不动，只把存储转换改为round-toward-zero：第一层误差降为0，最终相对L1为0.00027051（约0.0271%），MAE为0.00001651。这是本捕获的实测支持，不是“所有Vulkan设备都截断”的普遍规律。两种模式都保留用于实验，测试阈值没有为通过而放宽。

如何自己复现：先用 `Tools/capture_bloom_evidence.py` 按第2节同样的环境变量方式导出到一个新的目录；脚本限定frame6411，保存17个事件的资源与校验和。设置 `$env:ENDFIELD_BLOOM_EXPORT` 为该目录，从同一终端启动Unity，运行 `EndfieldShaderPack.EndfieldCaptureAssets.ImportAll` 后运行 `EndfieldShaderPack.EndfieldCapturePipelineValidation.RunAssetDiagnostics`。逐层日志在 `Logs/capture-asset-diagnostics.txt`。这一诊断必须读取完整17层导出，不是只导sampler的轻量模式。

观察signedMean和正/负误差数非常重要：如果从第一层开始只向一侧累积，先怀疑量化/颜色转换；如果集中在上下边界，先查UV原点和尺寸。原prefilter最后一个tap重复`(-1,+1)`，并不Y对称；不能随意翻转输入，再翻转结果，就当成完全相同的实验。

### 接入实时场景的具体入口

**2026-09-23最新门禁：实验场景尚未整体通过。** 它能执行真实HDR/Bloom并保存重开，但 `BuildAndValidate` 最后发现QualitySettings被Unity持久化改写。暂停前已恢复原设置。下面是待修复后使用的流程，现在不要在唯一原工程上直接执行Build或打开实验场景后保存。先读仓库根目录 `RESUME-2026-09-23-captured-pipeline.md` 第5节，在隔离副本修复设置保存生命周期。

先完成模型基线及捕获导出，再依次运行：

1. `EndfieldShaderPack.EndfieldCapturePipelineValidation.RunAll`：完整捕获后处理、cube和Bloom数值回归。
2. `EndfieldShaderPack.EndfieldCapturedSceneBuilder.BuildAndValidate`：构建两次、检查GUID稳定、保存重开后实际渲染，检查退出后原管线设置恢复。
3. 在Unity打开 `Assets/Scenes/Typhoeus_CapturedPipeline.unity`，看Game视图。Scene视图不执行这套相机专属后处理。

日常重新生成可以使用菜单 `Endfield > Build Captured Pipeline Showcase`。新场景从 `Typhoeus_OfficialFrame_Recovered.unity` 派生，原场景和原pipeline asset保留。它加载真正的环境cube和官方LUT，并从当前相机HDR实时生成Bloom；没有绑定固定截图的Bloom或阴影。

专用pipeline/renderer放在 `Assets/EndfieldShaderPack/GeneratedCapture/Settings`，由场景中的 `Captured Pipeline Scope` 接管当前质量档位。它意图在关闭场景时恢复，但当前只验证了内存恢复，磁盘设置恢复仍有上述阻塞。当前实现限定单场景、单个Base Game相机、Linear/HDR、非XR、无MSAA/动态分辨率；不要把这个小范围实现当成支持所有URP相机栈的通用插件。原URP后处理必须关掉，否则会重复调色。

本地预览为 `Validation/official-captured-pipeline.png`；生成图、场景和捕获贴图默认不提交GitHub，需自己保留本地数据。不要把“重放官方HDR通过”和“新模型的最终整帧与官方相同”混为一谈。

## 6. 阴影是目前仍需深入完成的一关

本帧阴影图实测 R恒为1，G范围0到1，约116890个像素的G<.99。R代表方向阴影，G代表独立角色自阴影。因本帧常量使方向分支直接返回1，优先级是G，而不是先重做完整场景CSM。

生产事件744/748；角色atlas资源32538，4096×2048 D16。resolve读取GBuffer角色索引、camera depth、每角色world-to-shadow矩阵/atlas rect，16次旋转Poisson GatherRed，累计64次比较并做非线性软化。普通URP主灯的单一shadowAttenuation不能未经测试就声称等价。

独立实现路线：

1. 导出并核对 camera depth、GBuffer中的角色索引、atlas与其常量矩阵；记录每个矩阵的空间。
2. 先选一个角色的一块atlas rect，手算3个已知点的投影、深度和比较结果。
3. 在Unity实现只含一个角色的shadow depth pass，验证剔除、bias、骨骼变形和alpha test。
4. 先做1-tap比较输出灰度，再加原Poisson偏移、旋转噪声、Gather顺序与软化函数。
5. 把生成结果与官方G通道做差分，分开统计轮廓边缘、内部、未覆盖区域。
6. 接回四族Shader的 `selfShadow`，同时验证face、hair、cloth的不同遮挡混合。
7. 转动相机/灯光/角色验证；固定截图阴影只能做离线实验，不能拿来当动态完成品。

这部分是明确待完成的研发内容。教程给出路径和证据，不提供一个未经验证的“万能阴影参数”。

## 7. 最终官方效果的验收矩阵

| 维度 | 锁定条件 | 不能做的补偿 |
|---|---|---|
| 几何 | 同模型、LOD、骨骼、动画时间、表情 | 用FOV去遮掩身材比例/姿态错误 |
| 镜头 | 投影矩阵、位置/旋转、viewport、分辨率、裁剪 | 仅按包围盒填满屏幕就声称相机1:1 |
| 材质 | 原始采样数据、每槽ST、颜色空间、mip/sampler | 用曝光修错贴图或错误gamma |
| 光照 | 捕获常量、环境cube、角色阴影、覆盖层 | 用补光抬平真正缺失的阴影 |
| 后处理 | 同HDR输入、Bloom、LUT、锐化、暗角、输出编码 | 一边用ACES一边用官方LUT比较相似度 |
| 输出 | 同像素位置、同颜色域、量化策略 | 把经过缩放/截图压缩的图片当位级基准 |

推荐分区：脸、头发、衣服、角、眼睛、背景。保存绝对差分、平均误差、最大误差、分位数/阈值内比例；同时看轮廓错位与颜色误差。先对齐几何和相机，再解释逐像素误差。指标必须写明只覆盖哪个Pass/场景/视角。
