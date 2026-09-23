# 提弗洛斯还原｜2026-09-23 安全暂停交接

## 0. 先读这个结论

用户要求先暂停研发、梳理未完成项并保存状态，避免额度中断丢失工作。不要把下面的实验场景当成整体通过；不要直接继续调光或曝光。

**模型与四族主颜色已有通过的基线；本轮离线后处理/Bloom/cube数值通过；新场景集成仍有项目质量设置持久化问题，整体验收未通过。**

当前未启动游戏、未注入进程；仅离线读取用户已有RDC。官方qrenderdoc与本轮Unity批处理均已退出。Unity Hub服务不是残留的测试Editor，不要杀它。

## 1. 首先打开的文档

- `QODER-HANDOFF-2026-09-23.md`：交给Qoder的完整架构、文件所有权、正确续作路线、测试与Git硬约束。
- `QODER-FIRST-PROMPT.md`：可直接复制给Qoder的第一条任务指令；本次只做管线激活隔离。
- `docs/learning/提弗洛斯渲染还原自学手册.html`：六章离线整本，无AI/账户/插件依赖，浏览器搜索、打印。
- `docs/learning/README.md`：总技术图谱、关卡、产物与阅读顺序。
- 本文件：最新真实进度和下一步优先级。
- `docs/research/official-source-shading-20260923.md`：上一阶段主颜色基线。

教材按真实文件、原理、最小实验、数值门禁与回退组织。覆盖从零到最终目标的路线，不声称尚未研发完的关卡已经完成。

## 2. 路径与版本

```text
工作目录 A:\Hypergryph Launcher\games\Arknights Endfield
源码库   工作目录\FractalMiner
Unity    A:\Unity\Editor\2022.3.30f1\Editor\Unity.exe
Python   工作目录\EndfieldUnpacker\.venv\Scripts\python.exe
RenderDoc C:\Program Files\RenderDoc\qrenderdoc.exe (1.46，内嵌Python3.8)
RDC      C:\Users\Administrator\Downloads\正面.rdc
```

RDC frame6411，大小1410912390字节。Unity URP manifest/lock请求14.0.12，但实际PackageCache的package.json为14.0.11；本轮不升级依赖。

Git checkout为main，存在大量既有删除、修改、未跟踪素材，必须保留。记录分支是 `fix/typhoeus-render-explosion-20260917`，remote `endfield-records`，地址 `https://github.com/LinXingjian365/FractalMiner.git`。上一个已通过主颜色检查点为 `1b2595116e020371d29dbc9742d7a8fe07fb2a90`。

本次交接提交是该分支随后新增的检查点（用 `git log -1 分支名` 获取）。采用独立临时index提交，不移动main、不修改用户暂存区。不执行 `git add .`、强制切分支、hard reset或clean。

## 3. 已通过和证据

| 项目 | 状态与边界 | 证据 |
|---|---|---|
| 模型/材质修复 | 上一阶段已通过，原版与珊瑚海岸基线保留 | `1b25951`、既有recovery报告 |
| 四族主颜色 | 上一阶段32项GPU/CPU基线通过；本轮未重新跑完整32项/整模 | `EndfieldOfficialShadingValidation.RunAll` |
| 捕获资源 | 六类资源，DDS保留原mip/压缩，EXR保存线性数值，校验和核验 | `pipeline-textures-01/complete.json` |
| 环境cube | 6面、128²、8mip原BC6H导入；6面mip0 GPU取样对独立EXR通过 | 六面MAE约0.0000763～0.0002143 |
| 指定post pass | 同官方HDR输入、LUT和参考Bloom，2560×1600全RGB量化误差≤1色阶；平均0.120543色阶 | `Logs/capture-pipeline-validation.txt` |
| 动态Bloom | 17-dispatch，第一层记录误差为0，最终相对L1=0.00027051、MAE=0.00001651、max=0.015625 | 同报告逐层1121～1185 |
| 黑/灰/白/HDR边界 | 输入0/.18/1/4均有限，raw输出到live sRGB解码对应通过 | 同报告末尾 |
| sampler | 实际descriptor为Linear/Linear/Point、U/V/W ClampEdge，全17事件一致 | `bloom-samplers-02/complete.json` |
| Python测试 | 本次58项全部通过 | `python -m unittest discover -s Tools/tests -q` |
| 依赖安全检查 | EndfieldUnpacker现有venv的pip-audit无已知漏洞；不是全系统安全审计 | 本轮命令结果 |
| 新实时场景 | 三次实际HDR相机渲染执行动态Bloom，保存重开有效、GUID检查通过，但最后设置文件检查失败 | `Logs/captured-scene-build01.log` |

后处理误差仅证明给定输入的post pass，不是“人物和官方全画面已经一致”。Bloom指标是HDR RGB能量归一化L1，不是感知相似度百分比。Cube逐面图像比较只覆盖mip0；全部mip通过DDS子资源布局/长度保留，没有宣称每级逐像素独立对照。

## 4. 本轮最大的排错收获

本机D3D11报告R11G11B10 LoadStore=True，但Sample=False、Linear=False。动态Bloom使用RGBAFloat作为兼容存储，在每次store显式量化为R11/G11/B10可表示值。

RNE版本最终relativeL1=0.05620586，17层单向偏亮。保持其他所有采样/权重/尺寸/阈值不变，换RTZ后降至0.00027051。两种模式保留；Python量化测试覆盖所有有限码值、中点、随机样本和特殊值。不能把某一捕获的证据推广成所有API/GPU都采用RTZ。

原prefilter最后重复(-1,+1)tap，不可擅自对称化；EXR与GPU坐标有Y方向约定。正确参考比较inputFlip=true/referenceFlip=true，LUT也需Y翻转。尺寸按原图独立取整得到25→13→6→3，不是递归向上取整。

## 5. 尚未通过的明确阻塞：质量设置持久化

失败入口：`EndfieldShaderPack.EndfieldCapturedSceneBuilder.BuildAndValidate`。

失败最后一项：`Generated scene modified project settings: ProjectSettings/QualitySettings.asset`。

运行中实际渲染、动态Bloom执行、重建GUID和场景重开均已到达通过路径；质量档位切换+Inspector改引用的内存恢复测试也经过。**但是磁盘QualitySettings仍被Unity保存/重新序列化为生成管线，内存恢复不等于磁盘恢复。** 日志显示构建过程中多次导入QualitySettings；需要继续精确定位SaveAssets/SaveScene/Refresh的写入点，不要用放宽hash检查掩盖它。

暂停前已撤销本次测试的设置变化，恢复到之前实际文件的精确SHA-256，未重置其他文件：

```text
QualitySettings.asset
2B7CB580B8FD042F92AEC91858DA36ACB9546F12A2DC5D432E9BAE9037821717
GraphicsSettings.asset
E2EAD59BEDD2AD92492703F6E907829744E51D0608FCADC4905D7E2840252E68
用户原index
C997CED59304D695D99B81CAB14B7E8BD6D411A63432CDD5216DDCCB958A6463
```

恢复依据：记录分支中的QualitySettings内容与运行前保存的哈希完全相等，因此只恢复该文件；没有从main盲目checkout。原全局pipeline GUID是13fa23817c5a2784ebcdc28788b04b05，生成pipeline GUID是f351291399134454680985801f0e93e8。

**修复前不要在唯一工作目录里重复运行Build/BuildAndValidate或打开实验场景继续保存。** 先用独立副本及设置快照做失败复现，再修正编辑器的管线生命周期/保存隔离。必须做到成功、异常、重载、切质量档位都恢复原设置。仅在finally改回QualitySettings.renderPipeline还不足以证明磁盘文件未变。

2026-09-23 20:24复核更新：用户重新打开Unity后，QualitySettings被Unity从serializedVersion 2规范化成3，当前哈希为 `E61ECBD3B831C8356DF6283D012E330AC34DDC4D552A993B7778A910C83C2163`；Ultra档位语义上仍引用原pipeline GUID `13fa23817c5a2784ebcdc28788b04b05`，并非生成pipeline GUID。不要在运行中的Editor外部强行覆盖。后续应把“Unity自身一次性格式升级”与“Build/场景引入的全局设置污染”分开验证，详见QODER-HANDOFF第4节。

2026-09-23 20:37 Qoder接续复核：Unity进程已全部退出，batchmode可运行。E61E哈希与Ultra→13fa…、GraphicsSettings E2EA…、用户index C997…、Python 58项通过均已在磁盘复验。**根因读码确认**：`Build()` 里 `scope.enabled=true` 触发 `OnEnable` 写 `QualitySettings.renderPipeline=生成管线` 并标脏，其后同函数的 `SaveScene`（及 `BuildAndValidate` 的 `OpenScene`）在污染状态下刷盘；`OnDisable` 只恢复内存且从不回刷。因此挂在scene生命周期上的管线激活**结构上不可能**通过字节门禁，必须改为显式、自行掌控 `SaveAssets` 时机的 Activate/Restore。

### 5.1 阶段1已完成：阻塞解除（2026-09-23 21:00 +08:00）

按上面的根因做了架构替换，不是放宽阈值：

| 变更 | 说明 |
|---|---|
| 删除 `EndfieldCapturedPipelineScope.cs`+`.meta` | 唯一职责就是那个缺陷写入；记录分支 `b35eda8` 可恢复。生成场景已重建，`6655d8225fbc503478905ac0e728b6ef` 引用数为 0，无 missing script |
| 新增 `Editor/EndfieldCapturedPipelineActivation.cs`（GUID `8e609c46a14e00383f530c5fd15a8181`） | Editor-only 显式 `Activate`/`Restore`+菜单+`ReportState`；状态存 `Library/EndfieldCapturedPipelineActivation.json`（已gitignore）；**先写状态文件再改设置**；`SaveAssets` 时机由本类独占；恢复前校验所有权，第三方改过就拒绝；回滚后按**重读值**决定是否删状态文件，而不是按哪个调用抛错 |
| 新增 `Editor/EndfieldCapturedPipelineIsolationValidation.cs`（GUID `66945ca21082726025ac16672a69bee8`） | 在 `Library/EndfieldIsolationSandbox/` 的 ProjectSettings 副本上跑**同一套** activate/restore 状态机（Target 依赖注入），沙箱每次运行前清空、编号有界 |
| `Build()` 改纯生成 | 去掉 scope 与实时预览；新增"已激活时拒绝 Build"守卫，否则会克隆生成管线而不是工程原管线 |
| 实时预览移到显式激活路径 | `RenderShowcasePreview()` 要求先 Activate，因为 showcase renderer feature 只能经生成管线到达 |
| 跨重启核对 | `ActivateForRestartCheck` / `VerifyAfterRestartAndRestore` 两个 executeMethod，由两个独立 Unity 进程完成 |

三层门禁结果：

```text
沙箱隔离   18/18 PASS  Logs/captured-pipeline-isolation.txt
真工程门禁  9/9  PASS  Logs/captured-scene-validation.txt      (qoder-scene-gate-01.log, EXIT=0)
跨重启门禁  4/4  PASS  Logs/captured-scene-restart-validation.txt (A/B 两进程均 EXIT=0)
```

关键证据（跨重启这一层才真正证明落盘）：A 进程激活后退出，磁盘 `QualitySettings.asset` = `BBAAD56816657EAA364F668F7D9BD92BF288EA158306F698566F733179442228`，`f351291399134454680985801f0e93e8` 出现 1 次；B 全新进程从磁盘读回并 Restore 后，精确回到 `E61ECBD3B831C8356DF6283D012E330AC34DDC4D552A993B7778A910C83C2163`。`GraphicsSettings.asset` 全程 `E2EAD59B…52E68`，`Typhoeus_OfficialFrame_Recovered.unity` 全程 `0185EB58…E7FB`。两个 ProjectSettings 里 `f351…` 残留计数为 0，状态文件与重启标记均已清除。

沙箱覆盖的路径：6 个质量档位逐个字节精确往返、persist 抛错回滚、写入未生效回滚、激活期间切档位（恢复归属档位且**不劫持用户当前档位选择**）、第三方改写拒绝、第三方清空拒绝、激活幂等、陈旧状态拒绝、无状态时 Restore 空操作、值已恢复时清理陈旧状态、原 GUID 不可解析时拒绝。每档还断言"激活后文件必须真的变了"，防止门禁空过。

回归未被扰动：Python 58/58 OK；`EndfieldCapturePipelineValidation.RunAll` EXIT=0、0 条 FAIL，动态 Bloom relativeL1=0.00027051 / MAE=0.00001651 / max=0.015625，post meanByteError=0.120543 / withinOneLSB=1.0，与上一轮记录逐位相同。**Bloom/Post 算法与阈值一行未改。**

边界（不要外推）：沙箱证明的是快照/所有权/回滚算法与其字节精确性，不模拟 Unity 自身序列化器；后者由真工程门禁"先规范化一次→快照→Build两次→无新 diff"覆盖。仍未做的是把官方还原交付拆成独立终末地 Unity 工程（QODER-HANDOFF §4 推荐项4），当前仍留在 FractalMiner 主工程内以显式激活方式隔离。

### 5.2 阶段2-1 已完成：角色自阴影证据导出器（2026-09-23 21:40 +08:00）

新增 `Tools/capture_character_shadow_evidence.py` 与 `Tools/tests/test_capture_character_shadow_evidence.py`。严格 TDD：先写测试并看到 RED（`ModuleNotFoundError`，全套 58→59 tests / 1 error），再写实现至 GREEN 22/22，全套 **80/80 OK**。

两个改变设计的实证发现：

1. **事件 748 = `ScreenSpaceShadowResolve_Character`**，由绑定表证实而非猜测：t4→`58994`(GBuffer1 法线)、t5→`58985`(GBuffer0 角色索引)、t7→`32538`(角色 shadow atlas)、t8→`59000`(camera depth)，与反编译 pass 里 `register(t4..t10, space3)` 的声明逐一对应。744 是方向阴影 pass，**两者都写 `58932`**（R8G8 2560×1600）：R=方向项（本帧被常量短路），G=角色自阴影。
2. **SPIR-V 反射把常量名全剥成 `_childN`，按名字取常量不可行。** 必须按字节定位：阴影 cbuffer 由唯一大小 `11440` 识别，各字段按 packoffset×16 定位。28 个 child 的尺寸累加恰好等于 11440，且复现出 `_CharacterShadowParams=(1,1,7,0)`、`_CharacterShadowTexelSize=(1/4096,1/2048,4096,2048)`（与 atlas 4096×2048 自洽）。字段偏移：W2S@7168(c448)、Biases@8128(c508)、LightDir@8368(c523)、AtlasParams@8608(c538)、TexelSize@8848(c553)、Params@8864(c554)。数组长度均为 15 槽，本帧 `.z=7` 表示前 7 槽有效；atlas 每槽 0.25×0.5，即 4×2 网格用 7 格。

因此导出器有专门的**布局漂移测试**：故意把 child14 从 47 项改成 48 项使后续偏移错位，导出器必须报错而不是静默返回错数据。GBuffer0/1 是 `R10G10B10A2_UNORM`，正好解释官方索引解码里的 `*1023`（10位）与 `*3`（2位）。

已从官方源码 `screenspaceshadowresolve.shader` 第1077-1127行完整解出 G 通道算法（下一步 GPU 实验的直接输入，不要重新推导）：

```text
index    = log2(pack10_10_10_2(GBuffer0.Load(px))) - 8        // 有效当 0 <= index < Params.z
若无效   -> G = 1
recv     = 1 - clamp(dot(N, LightDir[i].xyz), 0, 0.9)          // N = 解码后的 GBuffer1 法线
sp       = mul(W2S[i], float4((P - LightDir[i].xyz*(recv*Biases[i].x)) + N*(recv*Biases[i].y), 1))
refDepth = max(sp.z, 0.01)
若 sp.xyz 任一分量 <=0 或 >=1，或 refDepth 为 NaN/Inf -> G = 1
atlasUV  = AtlasParams[i].xy + sp.xy * AtlasParams[i].zw
m        = (px % 4) * 4 + (py % 4)                             // 逐像素 4x4 抖动
rot      = float2x2(TBL248[m], float2(-TBL248[m].y, TBL248[m].x))
sumPos = countLit = 0
for k in 0..15:
    g        = CharacterShadowmapTex.GatherRed(samplerLinearMirror,
                 atlasUV + mul(TBL247[k], rot) * (4 * TexelSize.x)) - refDepth
    lit      = step(0, g)                                      // 4 个 texel
    sumPos  += dot(g, lit);  countLit += dot(lit, 1)
f  = 2*clamp(countLit/64, 0, 1) - 1
s  = sign(f);  o = 1 - s*f
G  = min(1, 0.5 - 0.5*(1 - lerp(o^3, o, clamp((sumPos/countLit)/refDepth, 0, 1)))*s)
```

`TBL247`（16 个 Poisson 偏移）与 `TBL248`（16 个旋转基）是 shader 内 `static const`，在该文件第 616/617 行（角色 pass 内为相对第 64/65 行），不在 cbuffer 里。注意 `countLit==0` 时 `sumPos/countLit` 是 0/0，官方未做保护——GPU 实验必须按原样复现再用真实帧 G 通道对照，不要擅自"修正"这个除零。

常量模式（`ENDFIELD_SHADOW_CONSTANTS_ONLY=1`）已对真实 RDC 实跑成功：`Validation/Captures/tifuluosi-front-20260917/character-shadow-constants-01/` 有 `complete.json`、无 `error.json`，帧 6411 / 事件 748 / 输出目标 58932 / cbuffer 11440 / 四个绑定 / 五个纹理契约全部核验通过。这三个值是导出器**独立从 RDC 重新算出**的，不是从旧 `replay-details-01` 抄的，构成交叉验证。

RDC 有三个候选文件，必须按字节数 `1410912390` 精确选中 `正面.rdc`（`123.rdc`/`213.rdc` 是别的帧，用通配符取第一个会选错）。

完整模式也已对真实 RDC 实跑成功：`Validation/Captures/tifuluosi-front-20260917/character-shadow-01/`，有 `complete.json`、无 `error.json`，5 个纹理各 DDS+EXR 共 292MB，均带 sha256。导出后做了独立数值复核（不经 Unity）：

```text
screen-shadow-resolved.dds = 8192128 B = 128 头 + 2560*1600*2，未压缩 R8G8，可直接解析
R 通道 distinct=1 且全为 255            -> 证实"R 恒 1"（本帧方向项被常量短路为全亮）
G 通道 distinct=238，min=0，max=255     -> 证实"G 范围 0~1"
G/255 < 0.99 的像素 = 116890 / 4096000  -> 与交接记录逐位相同
```

**阈值陷阱（下一轮 GPU 对照会踩，务必按此比较）**：`116890` 对应 `byte/255.0 < 0.99`，即 `byte < 253`；若误用 `byte < round(0.99*255) = 252` 会得到 `115618`，差的正好是 `count(252)=1272`。两者相差 1.1%，足以让"阴影像素数对不上"被误判成 resolve 实现错误。

阶段2 剩余：GPU resolve 实验（先 1-tap 验证世界位置重建/索引解码/矩阵方向/atlas rect/深度符号，再加 16-tap Poisson 与软化，对固定帧 G 逐像素比较）→ 动态 shadow depth/atlas → 统一屏幕空间 shadow 纹理接回 `EndfieldCharacterLit.shader:576-578`。**`selfShadow` 目前仍是 1.0，未改。**

## 6. 正确续作顺序

1. **工程隔离门禁**：✅ 已完成，见 5.1 节。`BuildAndValidate` 正常退出、GUID 稳定、真实相机执行动态 Bloom、设置字节不变、跨重启还原全部满足；32 项主颜色/整模回归已重跑通过。**不要重做本项。**
2. **动态角色自阴影G（当前从这里开始）**：当前selfShadow仍为1，不是完整官方。导出atlas/depth/GBuffer/矩阵，先复现单点投影/深度比较，再实现动态atlas和resolve，再接回各族Shader。不要把捕获G图投射回实时人物冒充动态阴影。
3. **姿态与镜头**：核对同LOD、动画时间、面部表情、骨骼矩阵、投影矩阵、viewport和分辨率。轮廓不对齐时不以全帧色差推导材质错误。
4. **覆盖层/透明与细节Pass**：按真实draw定位，不按文件名猜。核对头发/角/布料局部覆盖与dither，不用“开透明”一概处理。
5. **最终多视角验收**：同输入条件分开脸/发/衣/角/眼睛，保存误差、轮廓与转动测试；只有这些通过才能谈整个人物达到官方效果。

阴影已有线索：events744/748；atlas32538，4096×2048 D16；GBuffer058985、GBuffer158994、cameraDepth59000；本帧R恒1，G范围0～1，G<.99共116890/4096000像素；7套角色shadow矩阵/rect、16次Poisson GatherRed共64比较及非线性软化。源码在本地 `_dump_1.5.3/.../runtime/shaders/lighting/shadow/screenspaceshadowresolve.shader`。普通URP主灯阴影不能未经对照当作等价实现。

## 7. 复现命令与输入依赖

```powershell
$repo = 'A:\Hypergryph Launcher\games\Arknights Endfield\FractalMiner'
Set-Location $repo
& '..\EndfieldUnpacker\.venv\Scripts\python.exe' -m unittest discover -s Tools/tests -q
# 离线数值通过入口，不是当前失败的实验场景构建入口：
& 'A:\Unity\Editor\2022.3.30f1\Editor\Unity.exe' -batchmode -projectPath $repo -executeMethod EndfieldShaderPack.EndfieldCapturePipelineValidation.RunAll -logFile "$repo\Logs\capture-pipeline-next.log" -quit
# 重新生成手册（仅构建需要Markdown，阅读HTML不需要）：
uvx --with Markdown==3.8.2 python Tools/build_learning_guide.py
```

不要同时运行两个同项目Unity Editor。新的日志名字避免覆盖上次证据；看最终退出结果，不能只找PASS子串。

默认本地证据根 `Validation/Captures/tifuluosi-front-20260917/`：

- `pipeline-textures-01`：6类纹理DDS/EXR与complete.json。
- `bloom-evidence-01`：17级纹理。旧manifest的samplers字段是假descriptor占位，**不要把它当采样状态证据**；纹理/UAV/哈希仍有效。
- `bloom-samplers-02`：修正API后的真sampler状态，sampler-only模式没有纹理文件。
- `bloom-source-01`：三个原始compute反编译参考。

导入器支持 `ENDFIELD_PIPELINE_EXPORT`、`ENDFIELD_BLOOM_EXPORT`。导出器用 `ENDFIELD_CAPTURE_PATH`、`ENDFIELD_CAPTURE_OUTPUT`（新目录）、`ENDFIELD_TOOLS_PATH`。变量从启动终端继承，不会自动传给已开Unity。

生成资产 `Assets/EndfieldShaderPack/GeneratedCapture`、实验场景 `Assets/Scenes/Typhoeus_CapturedPipeline.unity`、预览 `Validation/official-captured-pipeline.png` 均是本地未发布数据，默认gitignore。GitHub源码备份不能替代RDC、解包素材、mod和生成资源的本地备份。现有数据没有删除。

## 8. 本次需要纳入检查点的内容

新增离线自学六章+HTML+构建脚本；pipeline/bloom离线导出器与测试；captured cube/EXR importer；后处理shader/profile/URP feature；17-dispatch动态Bloom及量化测试；GPU数值验证器；实验场景builder/scope及本交接。

新场景builder/scope是**已编译、部分集成通过但最后门禁失败的WIP**，保存它是防止研究丢失，不是将其宣称生产完成。接手从第5节开始，不要重复已证实的post与Bloom推导，也不要重新解包全部资产。
