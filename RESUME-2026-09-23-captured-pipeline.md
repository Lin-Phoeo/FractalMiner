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

## 6. 正确续作顺序

1. **工程隔离门禁**：先解决第5节；保持原主颜色场景不变。重跑BuildAndValidate，正常退出、稳定GUID、真实相机执行、设置字节不变都满足才标记新场景集成通过。然后重跑32项主颜色/整模回归。
2. **动态角色自阴影G**：当前selfShadow仍为1，不是完整官方。导出atlas/depth/GBuffer/矩阵，先复现单点投影/深度比较，再实现动态atlas和resolve，再接回各族Shader。不要把捕获G图投射回实时人物冒充动态阴影。
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
