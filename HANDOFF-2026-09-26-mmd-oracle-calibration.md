# HANDOFF 2026-09-26 晚 — MMD 独立播放基准与求解器校准（WorkBuddy → Claude）

> **2026-09-27 更新指针**：这是一份历史交接，其中“腿部 IK 是唯一剩余问题”“A 阶段 90%”及原 P1 数字均已过时。修正后的插值、相机、根位移与 1131 帧双参照结果，以 `HANDOFF-2026-09-27-mmd-research-closure.md` 为准；原文保留用于追溯错误形成过程。

> **更新（2026-09-26 19:10，Claude）：§4 腿部 IK 已闭合，根因不是 Decompose/LimitTotal，见 §8。**
> **更正（2026-09-26 20:50，Claude）：A 阶段未闭合。P1 补丁是错的：Motion.vmd 全部关键帧插值块 row0[2],[3] 都是物理标志 (0,0)，我方解析器与打过 P1 的 UMT 同样把 Z/旋转 x1 读成 0，所以"亚毫米一致"对插值无效。另有 2 处相机 bug（弧度当角度、贝塞尔字节序）。证据与修复方向见 `docs/research/mmd-integration-research-20260926.md` §1。**

> 目标（用户原话）：**提弗洛斯能接上 MMD 骨架、用上 MMD 动作**。不接别的模型、不追溯 VMD 原始源模型（该任务线用户已明确砍掉）。
> 上一环节：`HANDOFF-2026-09-26-mmd-source-rig-ab.md`（PMX A/B 接通，84f6fa5）。本文档接它之后。

## 0. 一句话状态

**A 阶段（建基准+校准）完成 90%**：独立 oracle 已建成并交叉验证；同一 PMX+同一 VMD 下，我们的 `MmdRigEvaluator` 与参考实现逐帧对比——**躯干/手臂/手指/头部/中心骨全部达到亚毫米级一致**（1131 帧全片 P50 位置误差 0.014mm、旋转 0°），**唯一未闭合项是腿部 IK 链在 C# 实现里不收敛**（算法已被 Python 复演器证明正确，差异定位到 C# 膝限位链接的更新被完全抵消，见 §4，证据齐全）。

## 1. 环境、路径、产物

| 项 | 位置 |
|---|---|
| Oracle 隔离工程 | `D:\MmdOracle\OracleProject`（UMT 以 `file:` 本地包引入，包体在 `D:\MmdOracle\UnityMMDTools`，**含 3 处本地补丁**，见 §3.1） |
| Oracle 导出器 | `D:\MmdOracle\OracleProject\Assets\Editor\UMTOracleExporter.cs`（baked/solved/camera 三件套） |
| 我方全帧导出器 | `Assets/EndfieldShaderPack/Editor/Mmd/MmdFullDump.cs`（FractalMiner 工程内，`MmdFullDump.Run`） |
| 对比脚本 | `D:\MmdOracle\compare_oracle.py`（纯标准库；`--same-space` 做 oracle 内部 A/B；跨空间自动转 (-x,y,-z)×0.08；NFKC 归一骨名；P50/P95/P99/max+逐帧最差） |
| 骨骼过滤名单生成 | `D:\MmdOracle\make_bone_filter.py`（354→63 骨、1182→75 骨） |
| **腿部 IK 离线复演器** | `D:\MmdOracle\trace_ik.py`（纯 Python 复刻 CCD，逐迭代打印；用法见 §4.4） |
| 数据产物 | `D:\MmdOracle\out\`：`pmx{354,1182}.{baked,solved,camera}.json`（oracle 1131 帧真值）、`ours-{pmx354,pmx1182,standard}.json`（我方同构导出）、`report-{354,1182}-vs-baked.json`（对比报告） |
| 输入 | VMD/相机：`D:\MmdOracle\OracleProject\Assets\Motion\{Motion,Camera}.vmd`（已复制为 ASCII 路径）；rig JSON：`C:\Users\Administrator\Documents\EndfieldMmdSourceRigs\`（354/1182 两份，**第三方 PMX 派生物，不得提交公开仓库**） |
| 桥接 | `_unity_bridge.bat` 改写载荷 → `schtasks //run //tn "EndfieldUnityBridge"` → 看 `FractalMiner\Logs\bridge-marker.txt` 的 exit=；**跑前确认无 Unity.exe 在跑**；用后已恢复为仅编译载荷 |

## 2. 已完成（按时间线）

1. **Oracle 建成**：UMT 播放两份 PMX + UNFORGIVEN VMD（1131 帧 @30fps），导出 baked（bakeIKToFK=true，内部求解器逐帧求解后烘 FK 曲线）与 solved（稀疏曲线+运行时求解）双路真值。
2. **Oracle 内部一致性验证**：baked vs solved 同空间对比，从 P95=1.39m 修到 **P95≈4.2-4.5cm**（残余全在指尖——欧拉曲线对高速自旋骨是有损的，已定性，不影响用作真值）。
3. **三处 UMT 本地补丁**（全部先实锤后修，见 §3.1）：插值字节布局、欧拉弧度/角度、PlayableGraph 启动。
4. **我方求解器修复**：
   - `MmdRig.FromJson` 校验上限 π→2π（354 骨つま先IK angleLimit=4.0rad=229° 是合法 PMX 数据，原校验误杀）；
   - `MmdFullDump` JSON 头重复引号修复；
   - **CCD 求解器按 UMT `MMDTransformManager.TransformIK`（nanoem 谱系）逐行对齐**（fix-axis 吸附、angleLimit×(linkIndex+1)、欧拉序限位+前半程反射、Fix 型链接跳过）。
5. **全帧对比基线（当前数值）**：两路 PMX 一致——
   - 非腿骨：**posP95 ≤ 0.0001m，rotP95 ≤ 0.1°**（手指/手臂/头/躯干/センター全中）；
   - 整体 P50 = 0.014mm / 0°；
   - **腿链（左右 足首/ひざ/つま先 6 根）：posP95 28-35cm、rotP95 53-65°** ← 唯一未闭合项。

## 3. 关键技术事实（勿重新推导）

### 3.1 UMT v0.5.1 的三处本地补丁（都在 `D:\MmdOracle\UnityMMDTools`，git diff 可查）

| # | 文件/位置 | 问题 | 修复 |
|---|---|---|---|
| P1 | `Runtime/VMD/VMDReader.cs` `GetBoneInterpolationChannelOffset` | **【已证伪，见顶部更正】** 上游骨骼插值通道偏移 {0,1,17,18} 与 saba/nanoem/mmd_tools 共识布局 {c,c+4,c+8,c+12} 不符；Z/旋转通道读到垃圾字节，中段帧旋转错 16-36°（实锤：右手首 f248 rotD 36°） | `return channel;`（**应还原**：上游读法正确） |
| P2 | `Runtime/VMD/VMDAnimationClipConverter.Math.cs` `BuildSparseBoneKeyframes` | `math.Euler` 返回**弧度**直接写进 `localEulerAnglesRaw` 曲线（需要**角度**），非烘焙路旋转全错 ~57 倍 | `math.degrees(math.Euler(...))`（其 `DeltaAngle` 按 360/180 写死，佐证作者意图是角度） |
| P3 | 我方 `UMTOracleExporter.cs` | `PlayableGraph.Evaluate()` 前必须先 `graph.Play()`，否则图不求值、solved 路整段静止 | solved 采样循环前 `graph.Play()` |

其他 UMT 使用注意：首刷包内 `UMTResources.asset` 引用未解析会报 `missing m_PMXRenameListsJson`（二次启动/强制 ImportAsset 即可）；.pmx 每根骨 GameObject 都是子资产，模型根必须 `LoadMainAssetAtPath`；编辑模式导出前 `manager.physicsManager = null` 防 NRE；`AnimationMode.SampleAnimationClip` **静默忽略 localEulerAnglesRaw 曲线**，欧拉曲线必须走 PlayableGraph。

### 3.2 坐标/命名约定（全链路统一，验证过）

- MMD→Unity：位置 `(-x, y, -z) × 0.08`；四元数 `(-qx, qy, -qz, qw)`（绕 Y 180° 相似变换）。
- 骨名全链路 **NFKC**（我方 rig JSON 导出时已归一；UMT 侧导出是 PMX 原名含全角ＩＫ/１２３，**对比脚本两侧都做 NFKC**，已兼容）。
- 双方导出 JSON 每骨 7 浮点（pos3+rot4）+ 独立 `ik[]` 开关数组；对比脚本步长=7（踩过 8 的坑）。

### 3.3 已排除的嫌疑（腿部 IK 排查，全部有数据）

- **VMD/采样层**：f0/f497 手臂链两侧逐位一致 → VMD 采样、贝塞尔、grant、FK 全对。
- **IK 目标骨**：左右 足IK/つま先IK 目标位置两侧逐帧一致（≤1e-4m）。
- **IK 开关**：VMD 该段 1131 帧四路 IK 全开，两侧 0 帧不一致。
- **链配置**：effector=足首、links=[ひざ(限位 X∈[-π,-0.5°]), 足(无限位)]，两侧相同；iterations=40、angleLimit=2.0/4.0 rad 相同。
- **收敛残差**：oracle 残差 0.07mm；我方 f248 残差 0.56m、f800 0.22m（卡死）。

### 3.4 UMT CCD 语义（`MMDTransformManager.cs` L996-1075，我们的 C# 已对齐）

冷启动（每帧 ikRotation=identity）；逐迭代 `reflect = iter < iterations/2`；无限位链接 `angle=min(acos(dot), angleLimit)`，限位链接 `angleLimit*(linkIndex+1)` 且轴经 `LimitIKAxis` 吸附到 ±X/Y/Z（按世界轴在父系对应轴投影定正负）；总局部旋转=base∘ik，限位=`LimitAngle`（派生欧拉序 ZXY/XYZ/YZX 分解→逐轴钳制/反射→重组）；fix=Fix 的链接整链跳过；每链接后查收敛 `≤ math.EPSILON`。

## 4. 唯一未闭合项：C# 腿部 IK 不收敛（证据与下一步）

### 4.1 现象

`ours` 导出里腿链 6 骨 P95 28-35cm；坏帧聚集 232-619（f248/f446/f497 等），f0 只差 3.7cm。**同一算法**（§3.4）C# 卡死、Python 复演器 2 次迭代收敛。

### 4.2 决定性证据：两侧逐迭代追踪（f497 右足IK）

**C#（IkTrace，`FractalMiner\Logs\mmd-ikprobe.log`）**：
```
it0 link0 右ひざ ang=114.592 err=8.0607 effP=(-1.32,2.27,-5.78)   ← 膝转满量程但踝纹丝不动
it0 link1 右足   ang= 44.347 err=7.6548 effP=(-7.04,3.74,-2.55)
it1..∞ link0 右ひざ ang=114.592 err=7.6548（几何冻结，无限循环）
```
**Python（`D:\MmdOracle\trace_ik.py`）**：
```
it0 link0 右ひざ ang=114.592 err=3.3919（踝被膝带动 5m）
it0 link1 右足 ang=12.884 / it1 link0 ang=46.5 / it1 link1 22.0 → it2 收敛 0.5mm
```

**结论**：C# 膝（限位）链接的每迭代更新被**完全抵消**（net≈identity）——膝角每迭代都是满量程 114.592° 但踝/几何从不变化。差异单点在 `MmdRig.cs` CCD 限位分支：`LimitTotal()`（或 `_ik` 写回路径）对该输入返回了≈恒等。Python `limit_total` 同输入工作正常。

### 4.3 下一步（建议顺序）

1. 在 IkTrace 里加打 `LimitTotal` 前后的 `next` 与分解欧拉（it0 link0 一条即可），与 Python `limit_total` 对同一四元数的输出对比——`D:\MmdOracle\trace_ik.py` 里的 `decompose/compose/limit_total` 就是参照实现。
2. 重点怀疑对象：`MmdIk.Decompose` 的 `Matrix4x4.Rotate(q)` 元素索引（m.mRC 行/列映射）或 `AsinClamp/InvCos` 在 gimbal 附近的行为；其次是 `_ik[i] = next * inv(baseLocal)` 的 baseLocal 语义（`_poseLocal` 是否含 grant/是否在 World() 后即时刷新）。
3. 修好后：恢复 `_unity_bridge.bat` 三跑载荷 → 重导 `ours-*.json` → `compare_oracle.py` 两路全帧对比 → 腿链 P95 应降到毫米级。
4. 然后才进 B/C 阶段（retarget 运动学、交付门禁、全片验收）。

### 4.4 复演器用法

```
python D:\MmdOracle\trace_ik.py <rig.json> <Motion.vmd> <控制器名> <帧号>
# 例：python D:\MmdOracle\trace_ik.py C:\Users\Administrator\Documents\EndfieldMmdSourceRigs\Typhoea-TeaSoap-1182.json D:\MmdOracle\OracleProject\Assets\Motion\Motion.vmd 右足IK 497
```
C# 侧追踪：`_unity_bridge.bat` 载荷改为 `MmdIkProbe.Run`（参数 `-mmdRigPath/-mmdMotionPath/-mmdFrame`），日志在 `FractalMiner\Logs\mmd-ikprobe.log`。`DebugIkTrace` 开关在 `MmdRig.cs`（静态字段，探针用，非出货路径）。

## 5. 并行编辑冲突警告（重要）

**9/26 17:28-17:46 期间 MmdRig.cs 被另一个会话（疑似你本机的 claude 窗口）并发编辑**：CCD 重写、`MmdIk.*` 限位工具集、`DeriveLimits`、`MmdIkProbe.cs` 都来自该会话；本会话（WorkBuddy）的并入内容：`DebugIkTrace` 静态字段 + IkTrace 日志行 + `angle` 变量提升 + `_unity_bridge.bat` 探针载荷 + `MmdIkProbe.cs` 初版（若两边版本不同以磁盘为准）。**继续开发前先 `stat`/diff 确认磁盘最新状态，避免互相覆盖**。遗留重复实现（`MmdIkLink.DeriveLimits` vs `MmdIk.NormalizeLimit`）功能等价，可任删一份。

## 6. Git/合规纪律（沿用）

- 第三方 PMX/贴图/rig JSON/逐骨轨迹/对比 JSON **不进公开仓库**；动作许可：署名/禁再配布/禁售卖/禁 MMD 以外用途（Kimagure, @kimagure_video）。
- 记录分支 `fix/typhoeus-render-explosion-20260917`；隔离临时 index 提交（`GIT_INDEX_FILE` Windows 路径、`hash-object -w`、`update-index --cacheinfo --add`）；勿动 main 工作区；push 大文件走 `env -u *_PROXY git -c http.proxy=http://127.0.0.1:7890 push`。
- `_unity_bridge.bat` 已恢复为仅编译载荷（跑完批任务必恢复）。
- 修改 `Editor/` 后**编译验证必须走桥接全量重编**（交互会话增量编译会复用旧缓存，漏报错误）。

## 7. 文件清单（本会话新增/修改）

**新增**：`D:\MmdOracle\{compare_oracle.py, make_bone_filter.py, trace_ik.py}`；`D:\MmdOracle\OracleProject\Assets\Editor\UMTOracleExporter.cs`；`FractalMiner\Assets\EndfieldShaderPack\Editor\Mmd\{MmdFullDump.cs, MmdIkProbe.cs}`；`D:\MmdOracle\out\*.json`（数据）。
**修改**：`D:\MmdOracle\UnityMMDTools`（P1/P2 补丁）；`FractalMiner\Assets\EndfieldShaderPack\Editor\Mmd\MmdRig.cs`（2π 校验上限 + IkTrace 探针行；**含并行会话的 CCD 重写**，见 §5）；`_unity_bridge.bat`（已恢复）。

## 8. 闭合记录（2026-09-26 19:10，Claude）

- **根因**：`MmdRigEvaluator.Sample` 对无轨骨写 `new VmdLocalPose()`，`VQuat` 是结构体、默认全零 → `World()` 里 `Normalize(_ik[i] * 0)` 恒为 identity，IK 对**无轨链接**完全失效。Motion.vmd 无 `左右ひざ/足首` 轨（有 `左右足` 轨），故膝冻结、つま先IK 也废。CCD/`Decompose`/`LimitTotal` 本身无误，§4.3 第 2 条嫌疑作废。Python 复演器缺轨返回 (0,0,0,1)，所以没复现。
- **证据**：`trace_ik.py` 仅把缺轨默认改成 (0,0,0,0)，逐位复现 §4.2 的 C# 日志（8.0607 → 7.6548 冻结）；修后 C# 探针（`Logs\mmd-ikprobe-postfix.log`）与 Python 原版逐行一致，it2 收敛 0.0005。
- **修复**：`MmdRig.cs` `_anim[i] = Vmd.SampleBone(_tracks[i], frame);`（`SampleBone` 空轨返回 identity）。
- **回归**：`MmdRigImportValidation.Run` 新增最小腿链自检（膝无轨、只有 足/足IK 有 key）：修前抛 `ankle error 2.199268`（`Logs\mmd-ik-regression-prefix.log`），修后 PASS。
- **全帧对比（修后）**：354/1182 整体 posP95 0.15/0.12mm；腿链 6 骨 posP95 ≤0.71mm、rotP95 ≤0.21°，max 2.1/3.2mm；frame-0 0.36/0.29mm。standard 内置 rig（解析两骨路径同样受此 bug）足首→足IK P95=0，残差帧全部是目标超出腿长。
- **产物**：`D:\MmdOracle\out\ours-*.json`、`report-{354,1182}-vs-baked.json` 已更新；修前版本备份在 `out\prefix-2026-09-26\`。`_unity_bridge.bat` 已恢复仅编译载荷。**未提交 git**。
- **下一步**：~~进入 B/C 阶段~~ 先修 `docs/research/mmd-integration-research-20260926.md` §1 的插值与相机缺陷、还原 UMT P1、引入独立第二 oracle 重新校准，再进 B/C 阶段（retarget 运动学 → 交付门禁 → 全片验收）。
