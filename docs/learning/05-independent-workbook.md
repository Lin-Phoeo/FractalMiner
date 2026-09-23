# 05｜独立续作手册：练习、排错、验收与回退

这章是没有外部助手时的工作台。每次只解决一个可观察的问题；保留能复现它的最小输入；修完后再回到完整角色。

## 1. 每次开始先做五分钟登记

```text
日期 / Unity版本 / 实际URP包版本：
当前场景 / 当前Git分支与提交：
输入资产 / RDC frame / Event / ResourceId：
昨天通过的测试及日志路径：
今天只改哪个变量：
预期变化 / 如何测量：
如果不符，先查哪一层：
```

然后执行只读检查：

```powershell
$repo = 'A:\Hypergryph Launcher\games\Arknights Endfield\FractalMiner'
git -C $repo status --short
git -C $repo branch --show-current
git -C $repo log -5 --oneline fix/typhoeus-render-explosion-20260917
Get-Content (Join-Path $repo 'ProjectSettings\ProjectVersion.txt')
```

当前目录有很多其他项目改动和未跟踪资源，不能 `git add .`，不能强制清理。记录分支是恢复历史，main是当前checkout，两者不是同一个视图。

## 2. 从安全副本开始练习

不要在唯一工作目录里练习危险回退。可先对记录分支做只含受控源码的归档：

```powershell
$backup = 'A:\TyphoeusLearning-source.zip'
if (Test-Path -LiteralPath $backup) { throw '备份已存在，请改用新文件名' }
git -C $repo archive --format=zip --output=$backup fix/typhoeus-render-explosion-20260917
```

这是源码快照，不含被ignore的游戏资源、Library、captured textures或完整生成场景。要真正运行，按第01章资产清单另外备份你自己的必要本地资源；不能以“GitHub有提交”代替完整数据备份。

ZIP也不含 `.git` 历史，不能直接执行后文的旧提交切换。需要练习分支与回退时，另建一个独立 `git clone` 的学习库，或在理解worktree后建立隔离工作树；不要在唯一原工程上试验。

开始写脚本前，把它的输入、输出和是否覆盖已有文件列出来。优先新目录、拒绝覆盖、保留原始包。遇到输入文件字段缺失，要报错并定位版本，不要用默认0偷偷补齐。

## 3. 错误图谱：先查什么

| 症状 | 优先检查 | 最小实验 | 不要先做 |
|---|---|---|---|
| 顶点炸开/长刺 | stride、索引宽度、骨映射、bindpose、坐标转换 | 无材质静止模型；CPU蒙皮恒等式 | 降曝光、换shader |
| 部件相互错位 | 是否分别重居中、局部/世界空间混用、预变形buffer | 对应顶点坐标与官方JSON比较 | 逐个凭眼睛移动部件 |
| 黑脸/缺眼 | 材质身份、图集、深度、alpha用途、UV | 独立部件纯色与BaseMap调试 | 把脸删掉重烘焙 |
| 一半纹理颠倒 | 每槽ST、DDS/EXR导出方向 | UV棋盘和单独R/G输出 | 翻整个网格全部UV |
| 高光乱跑 | TBN、RGorAG解码、specRamp坐标、光向空间 | 固定平面、固定V/L、常量P图 | 把roughness和光色同时调 |
| 颜色整体偏灰/过亮 | sRGB、LUT方向、曝光、双重Gamma、默认cube | .18/1/4线性输入与GPU读回 | 加补光或套ACES |
| 转动后露馅 | 固定截图投影、世界/切线方向错误、阴影缺失 | 转90度、只显示法线/阴影 | 只交付正面截图 |
| Unity重开后坏了 | 生成Mesh是否持久化、GUID是否变化、globals是否恢复 | 保存→清空globals→重开→读数 | 只在当前内存Scene里验收 |
| 自动匹配“唯一”却很怪 | 候选搜索域、buffer/sampler误当texture、语义约束 | 故意改hint看正确候选是否仍保留 | 相信alphabetical first |
| Bloom条纹/边缘错位 | group索引、barrier、尺寸取整、mip/UV原点 | 脉冲/梯度和每层误差 | 只看最终LUT图是否好看 |
| Bloom逐层偏亮 | R11/G11/B10舍入、half中转、隐式颜色转换 | 每层signedMean与正负误差计数 | 改强度压低亮度掩盖错误 |

## 4. 十个独立结业作品

1. 文件清单工具：输出源包/对象ID/类型/名称/大小，重复名字不会互相覆盖。
2. 模型验证器：对合法/越界/NaN/权重和错误各有一个测试。
3. 双骨骼小长条：手算一个顶点的线性混合蒙皮，并与Unity一致。
4. 法线诊断材质：输出世界法线与切线方向，解释镜像UV和w符号。
5. 材质契约表：用代码行证明P图/SDF/ramp每通道用途。
6. 候选匹配器：错误hint、相同长度不同语义、缺字段都能正确报警。
7. Skin平面：SDF权重0/1、alpha0/1四组合，CPU/GPU对照。
8. Cube实验：六个方向渐变面、8级mip采样和面序验证。
9. Post实验：相同HDR输入经LUT，量化后与已知参考比较，解释翻转与Gamma。
10. 角色回归：固定相机与转身两套，保存日志、差分、版本和回退点。

做完一个再打开项目里的参考实现对照。能解释失败原因比抄出同样代码更重要。

## 5. 用测试工作，而不是凭记忆工作

脚本测试：

```powershell
Set-Location 'A:\Hypergryph Launcher\games\Arknights Endfield\FractalMiner'
& '..\EndfieldUnpacker\.venv\Scripts\python.exe' -m unittest discover -s Tools/tests -v
```

Unity主颜色回归：`EndfieldShaderPack.EndfieldOfficialShadingValidation.RunAll`。
该全量入口依赖原版展示场景与珊瑚海岸mod；纯数学学习用第03章列出的两个 `RunNumerical` 入口即可，不依赖角色资源。
捕获资源/后处理回归：`EndfieldShaderPack.EndfieldCapturePipelineValidation.RunAll`。
该回归需要第04章成功导出的资源。若使用自建导出目录，先设置 `$env:ENDFIELD_PIPELINE_EXPORT` 并从同一终端启动Unity；默认目录是 `Validation/Captures/tifuluosi-front-20260917/pipeline-textures-01`。
启动格式见第03章，替换 `-executeMethod` 和独立日志文件名即可。

实时场景回归：`EndfieldShaderPack.EndfieldCapturedSceneBuilder.BuildAndValidate`。目前最后的设置持久化门禁失败，先按最新RESUME文档在隔离副本修复，再使用此入口。检查 `Logs/captured-scene-validation.txt`；完整通过后才能把 `Assets/Scenes/Typhoeus_CapturedPipeline.unity` 当作集成通过版本。生成资源依赖你本地的解包/截帧，不会随Git源码自动出现。

判断成功要同时满足：脚本/Unity正常完成、报告存在、没有遗漏分支、预期的资源尺寸和像素数量正确。警告需区分类型：授权客户端网络消息不等同Shader失败；真正的CS编译错误和GPU非有限输出必须处理。一次导入中的旧程序集错误可能随后重新编译成功，最终再开干净批次验证，不能只挑PASS行。

## 6. 自己进行一次完整修复

以“ramp alpha不生效”为例：

1. 写假设：当前实现只使用RGB，忽略alpha。
2. 写最小输入：RGB全白，alpha分别0/.5/1，关闭高光和额外后处理。
3. 写CPU期望：三个输出不相同，且每个值能逐步算出。
4. 跑旧实现，保存失败记录；如果测试原本就通过，假设可能错了。
5. 只改相关光照公式，不动摄像机/材质贴图/曝光。
6. 数值测试通过后，跑整模和场景重载回归。
7. 查看本次diff，提交只包含相关文件的改动，记录剩余限制。

模型重建、UV翻转、cubemap默认亮度、body候选误配，都可以用同一流程，不需要聊天模型替你判断。

## 7. 提交与回退的实际规则

你自己的干净学习库可正常 `git add 指定文件` → `git diff --cached` → `git commit` → `git push`。本机已有复杂工作树时，先向独立副本迁移学习改动，不要为了模仿历史提交方式立刻使用底层commit-tree命令。

如果要恢复旧代码，先保存当前改动和需要的资源，再在学习副本上用 `git switch -c study-old <提交号>`。这样会新建学习分支，不改动原工作区。需要撤销公开提交时优先理解 `git revert`；不要未经确认强推或hard reset。

每个检查点至少记录：提交号、Unity/URP版本、输入哈希、测试命令与结果、场景路径、生成资源是否被Git忽略、未完成项。旧研究笔记保持历史原貌，在新记录中明确“哪条结论被什么证据推翻”。

## 8. 没网络、没额度、没助手时怎么查

- C#报错：先看第一条编译错误所在文件/行和实际方法签名，再查本地Unity API/PackageCache；别追后续连锁错误。
- Python报错：看traceback最下面的具体异常，再逐层找你的代码；用print输出类型、长度、路径，避免一次输出数十万行。
- Shader报错：简化到最小Pass，检查变量声明、纹理采样类型、目标平台、关键词。
- 数学不确定：用纸笔或10行Python构造3个输入，不用真实角色复杂纹理起步。
- 数据不确定：查源文件哈希/结构/格式，做一个最小取样，拒绝“猜字段补零”。
- 思路乱了：写下“已知事实 / 假设 / 下一项可证伪实验”三栏，回到最近通过的关卡。

本地教材HTML、源代码、日志、已有官方软件帮助、PackageCache与RDC都能在离线时阅读。网页链接是补充来源，不是执行每一步的在线依赖。
