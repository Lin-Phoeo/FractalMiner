# 提弗洛斯 MMD 动作源骨架 A/B：现状与下一位 Agent 的实施路线

更新：2026-09-26。目标是让**官方解包提弗洛斯网格/材质**可靠载入 VMD 跳舞；不是把第三方 PMX 网格替换进最终场景。本文件是进度交接，不是“已完美”的声明。

## 先读结论

1. 原播放器把每个 VMD 固定解释在手写 `StandardMmd()` 73 骨骨架上。用户提供的两份提弗洛斯 PMX 都有当前 UNFORGIVEN 的 **52/52 轨道**，但分别为 354/1,182 骨，静止姿态和层级不同。单看轨道覆盖不能证明动作正确。
2. 已实现**可选 PMX 源骨架**：本地 PMX → `Tools/export_pmx_motion_rig.py` 导出仅供本机的 JSON → Unity `MmdRigDefinition.FromFile()` → `MmdPlayer.Load(..., sourceRig)` → 官方网格。`Endfield/MMD Studio` 和 `Endfield/VMD Batch Render` 都有选 JSON 的入口；不选仍用原标准骨架。PMX 网格/纹理/骨架 JSON **未入 Git**。
3. 三路（标准、354 骨、1,182 骨）对同一 VMD 的源轨迹五时点求解均成功，未映射轨道 0；354 与 1,182 两路官方网投影五时点也都过现有烟测。明显差异：28.25s 源求解器左脚踝世界 Y：标准 2.51 MMD 单位、354 骨 0.36、1,182 骨 0.39；转成官方网格后，37.67s 最低可见顶点 Y：标准 -0.158m，两个 PMX 源均约 +0.001m。但这**不是 MMD 真值比较**；两份 PMX 均非 VMD 标注的动作原始模型，因此不擅自替换默认源骨架。
4. 3 套画面差异肉眼可见，354 骨在当前五帧的鞋底/身形较稳，可作为优先实验候选，不可称“完美”。全片 37.7s 和另外两条 VMD 尚未按 PMX 源跑完。

## 具体产物与位置

| 用途 | 路径 |
| --- | --- |
| PMX→本地源骨架 JSON 工具 | `Tools/export_pmx_motion_rig.py` |
| 工具单测 | `Tools/tests/test_export_pmx_motion_rig.py` |
| Unity JSON 读入、依赖拓扑/校验 | `Assets/EndfieldShaderPack/Editor/Mmd/MmdRig.cs` |
| Unity 源轨迹 A/B 批量验证 | `Assets/EndfieldShaderPack/Editor/Mmd/MmdRigImportValidation.cs` |
| 可选源骨架播放核心 | `Assets/EndfieldShaderPack/Editor/Mmd/MmdPlayer.cs` |
| 交互式切换 JSON | `Assets/EndfieldShaderPack/Editor/EndfieldMmdStudio.cs` |
| 离线出片和五时点烟测 | `Assets/EndfieldShaderPack/Editor/EndfieldVmdBatchRender.cs` |
| **只在用户电脑上**的 354/1,182 骨 JSON | `C:/Users/Administrator/Documents/EndfieldMmdSourceRigs/` |
| 本机源轨迹 A/B 证据（不提交骨位值） | `Validation/mmd-source-rig-ab/{standard,pmx354,pmx1182}.json` |
| 本机官方网投影 A/B 截图、报告 | `Validation/mmd-smoke-{01,pmx354,pmx1182}/` |

两份本机 JSON 是从第三方 PMX 生成的衍生数据，仅供个人核验。茶叶味香皂 PMX 的 ReadMe 禁止二次配布与拆件改造；**不要把 PMX、贴图、导出的 JSON 或逐骨架轨迹提交到公开 GitHub**。项目最终渲染网格仍是 `Assets/Typhoeus/chr_0034_typhoea_uimodel.fbx` 及捕获重建资源。源动作作者在 VMD 头部标注的是截断的 `1.トレモデル1.04(バ…`，用户提供的两个 PMX 都不是这个源模型。

## 最短复现

1. Unity 2022.3.30f1 打开 `FractalMiner`。先在 `Endfield/MMD Studio` 点击「① 初始化人物模型」，再点击「选择 JSON...」选本机 `C:/Users/Administrator/Documents/EndfieldMmdSourceRigs/Typhoeus-SheepyLord-354.json`，最后打开 VMD。窗口信息必须显示 `源骨架 Typhoeus`、`T-pose 校准成功`、`未映射轨道 0`。点击「标准骨架」可恢复旧路径。批渲染窗口有同名 JSON 路径栏。
2. 如需重生本地 JSON：安装只供脚本使用的 zlib 许可 `pymeshio`：`uv pip install --target <local-reader-dir> pymeshio`。运行 `py -3.12 Tools/export_pmx_motion_rig.py <input.pmx> <local-output.json> --reader-root <local-reader-dir>`；若目标已存在，需显式 `--force`。脚本不会复制网格和贴图。当前旧版 pymeshio 可读用户这两份 PMX，但**不能假定兼容所有 PMX 2.1 / 扩展 UV 文件**。
3. 源轨迹验证：Unity batchmode `-executeMethod EndfieldShaderPack.EditorTools.Mmd.MmdRigImportValidation.Run -mmdRigPath <JSON或standard> -mmdMotionPath <VMD> -mmdOutput <本地报告路径>`；五时点记录髋、双腕、双踝。`RunSmokeValidation` 接受 `-mmdRigPath <JSON>` 和 `-mmdOutputDir <目录>`，对官方网格跑五时点图像/姿态/蒙皮/后处理门禁。示例运行结果在上述 Validation 目录。
4. `uv run --with pytest --with pillow --python 3.12 -m pytest Tools/tests -q`：本轮 **133/133 通过**；PMX 导出脚本单测覆盖率 91%；`pip-audit` 对本轮 Python 工具环境报告无已知漏洞。Unity 三路源轨迹验证退出码 0；354/1,182 两路官方网格烟测退出码 0；这不是长片视觉验收。

## 下一位 Agent 必须按顺序完成

### A. 找到真正的 MMD 外部真值，才谈“无误”

- 首选取得与 VMD 匹配的原始 `トレモデル1.04` PMX（注意作者/下载许可）。若找不到，不允许把 354/1,182 骨中的任何一个称作原始源；可用它们作为**代理骨架**，但结论标签要写清。
- 在隔离工程或 MikuMikuDance / [UnityMMDTools](https://github.com/CandidumGames/UnityMMDTools) 中直接播放**同一 PMX + 同一 VMD**，导出 0..1130 每帧的源骨骼世界位置、局部旋转、IK 状态、镜头和关键帧截图。参考实现仅作离线判定，不接游戏进程、不绕保护。
- 对比当前 `MmdRigEvaluator` 对**同一源 PMX**的输出。先核对轴系/单位/静止姿态，再逐项修 VMD 贝塞尔插值、PMX grant、局部轴/fixed-axis、变形层顺序、腿/脚尖 IK 与开关。当前导入器**保存** fixed-axis 字段，但求解器尚未使用；PMX 刚体/布料物理也未复现。五时点 PASS 不能证明这些细节正确。

### B. 修 retarget 的运动学，而不是盲调幅度

- 保留 55 个主体/手指角色到游戏 481 骨骨架的绑定；源骨架可替换，目标网格保持官方。逐帧记录两肩、双腕、髋、双膝、双踝、脚尖的**根局部**坐标。用源模型肢长做无量纲化后比动作形状；不要比较不同 PMX 的原始绝对坐标就宣布优劣。
- 当前 `MmdRetargeter` 对腿是源膝角转目标两段 IK；检查根位移、骨盆转动、脚踝朝向与脚尖都保留。默认 `inPlace=true` 会锁掉水平根运动，仅适合原地预览；需要同时验收 `inPlace=false` 的舞台移动和相机跟随。
- `KeepFeetAboveBindFloor()` 只是整角色抬升的保底补丁。正式路径应建立**鞋底/脚尖蒙皮顶点**接触采样、左右脚接触相位、脚掌锁定和骨盆补偿；裙摆/武器与地面分开检查。禁止用全局高度增益掩盖错误 IK。
- 游戏原始头发/裙摆等次级骨、MMD 表情、手指细节、鞋/裙碰撞，必须独立处理。当前“骨与网格会动”只验证主角色骨链，不是全部 481 骨动画完成。

### C. 建立真正的交付门禁

- 至少 3 条来源清楚、许可允许的 VMD（含本例），每条逐帧跑完；源模型 oracle 的角色轨迹与 Unity 源求解器比较 P95/P99，并单独记录 IK 链、手指、头部。阈值从 oracle 浮点噪声和目标骨长定，不先拍脑袋设“完全一致”。
- 官方目标网格的无效/跳帧姿态数为 0、手脚关节无突跳；接地片段鞋底相对舞台误差和穿插逐帧有记录；跳跃片段不被全局抬升误判。至少对正、侧、俯三个镜头看完整舞步，检查镜头 VMD 轴、FOV、跟随及人物进出画。
- 再跑 37.7s 全片 PNG→MP4（帧数、音画同步、无丢帧），与来源视频关键帧逐项审阅；改动进入 MMD Studio 和 Batch Render 的同一播放核心。此前 3s 视频只证明编码链工作。
- **渲染风格是独立门禁**：现有 M5 对官方截帧的颜色/轮廓误差仍未达标；即便动作过关，也不能称“官方游戏一样”。继续按官方帧 6411 的材质/光照/后处理真值复核，不要把 MMD PMX 的材质混入官方渲染场景。

## 工程注意与 Git

- 工作区 `main` 极脏且含大量用户文件；记录分支 `fix/typhoeus-render-explosion-20260917`，远端 `endfield-records=https://github.com/Lin-Phoeo/FractalMiner.git`。基线提交 `0a5bcf3`（前一轮指骨/网格诊断）。本轮须用**独立临时 Git index** 从记录分支 `read-tree`，只 add 本轮文件，`commit-tree/update-ref/push`；切勿 `git add .`、reset、clean 或切换 main 工作区。
- `_unity_bridge.bat` 是本机未跟踪的调试桥，完成后应恢复为仅 Unity 编译命令，不提交。此文件当前曾用于跑 PMX 1182 烟测。
- 公开仓库不要提交第三方 PMX、纹理、本地转换 JSON；本机 `Validation/mmd-source-rig-ab/` 的逐骨样本也仅供内部研究。可以提交无版权载荷的代码、测试、聚合门禁表与本交接文档。
