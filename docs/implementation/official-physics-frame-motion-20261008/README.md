# 官方物理：帧移动速度与方向归约

2026-10-09 增补：[帧级惯性修正参考](../official-physics-frame-inertia-20261009/README.md)已确认本归约输入为“当前采样组件位置 − 修正后的 working-old 位置”，并提供消费已解析前序输入的生产片段。完整 anchor/smoothing、sign-remap、teleport/reset 前序仍待移植；不能把 shiftVector 当通用残差。本页下方及 `verification.json` 保留 10-08 历史阶段边界，新的证据与门禁以增补文档为准，不重写旧快照。

2026-10-08，接续[帧中心的子步消费](../official-physics-center-step-20261003/README.md)与[Team 移动风状态](../official-physics-team-tail-20261003/README.md)。新增 `Tools/official_physics_frame_motion.py`，只恢复帧级大 kernel 中一个边界可证的数值片段：把调用方已经解析好的 Double 位移转换成 `CenterData.frameMovingSpeed` 与 `frameMovingDirection`，再通过 `FrameWindState.from_motion(...)` 送入现有 `UpdateWind` 参考。

**这是离线有限值参考，不是完整帧中心、Unity 物理后端或新可见效果。** 上游位移的 transform/anchor 来源仍未完全解码，因此接口故意命名为 `upstream_delta`；不得把场景 root 位移、`frameComponentShiftVector` 或粒子位移擅自代入。风区选择、teleport/reset、NativeArray 发布、Job 调度与 Transform 写回也不在本阶段。

## 固定来源与字段

仅静态读取固定版本本地文件，不执行、加载、注入或附加游戏 DLL/进程。GameAssembly SHA 为 `c24495e51b406f03b03890c4788ee618ae022c991405be5d5b8b787cb775ae89`，metadata SHA 为 `0076743397acadf03d3b0064343a963c7c88863b8160526d397e4b3efb96f02e`。

- 所在函数：`CalcCenterAndInertiaAndWindKernel$BurstManaged`，method369644，RVA `0x5a34900..0x5a36de4`，9444 字节，SHA `d5a34e2d385077c37a51c478d1eab92bb4ffd2e940655469ff362a515c1a4774`。
- 受限归约片段：`0x5a36ab1..0x5a36bd4`（尾地址不含），291 字节、62 条指令，SHA `b01c99e6ff406f1fe1d47df0407f7bc3edae1efbbb5f6e1e91d7dae09e958dfc`。这是大函数内部片段，不宣称独立 ABI 或函数边界。
- `0x5a36ab1` 调用 `MathUtility.AutoToFloat3`；随后依次调用 float3 dot 与 sqrt。`0x5a36a65` 载入的 Single 常量原始字节为 `bd378635`，即 `9.999999974752427e-07`（`1e-6f`）。
- TeamData：`frameDeltaTime@16`、`nowTimeScale@48`（unboxed）。CenterData：`frameMovingSpeed@232`、`frameMovingDirection@236`；`frameComponentShiftVector@204` 的字段身份已知，但该归约片段没有直接读取它。
- 私有完整指令与字段证明位于 `D:/EndfieldTechLib/notes/official-physics-frame-upstream-20261008-01/`。公开仓库只保存自己的参考、测试、摘要和 SHA，不发布完整原生报告或游戏资产。

## 不能改写的顺序

对调用方提供的 `double3 upstreamDelta`：

1. 先逐通道 `AutoToFloat3`，之后的 dot、长度、除法和乘法均按 Single 舍入；不能先在 Double 中求长度。
2. `length = Single(sqrt(dot(deltaF, deltaF)))`；dot 保留 helper 的通道相加次序。
3. `frameDeltaTime > 0` 时才做 `rate = Single(length / frameDeltaTime)`，否则 rate 为零。此门禁只影响 speed，不影响后面的 direction。
4. `nowTimeScale > 1e-6f` 时计算 `inverseTimeScale = Single(1 / nowTimeScale)`，否则为零。**这里不是 scaleRatio。**
5. `speed = Single(inverseTimeScale * rate)`。必须保留“先求 Single 倒数，再乘 Single rate”的次序，不能折叠为 `length / (dt * timeScale)` 或 `rate / timeScale`。
6. speed 无论长度是否小于 epsilon 都写入。direction 独立判断：仅 `length > 1e-6f` 时逐通道 `Single(deltaF / length)`；相等也走零向量分支。
7. `FrameWindState.from_motion` 只是同名字段的显式交接。后续 `UpdateWind` 仍按自己的源公式再计算 `frameMovingSpeed * movingWind / scaleRatio`；`nowTimeScale` 与 `scaleRatio` 是两次不同的缩放，不能合并。

Python `math.sqrt` 只作有限数学参考，不声称与游戏 CRT/Burst 超越函数逐位一致。finite 与三通道检查是适配层策略，不是官方异常契约。

## 验证和剩余边界

测试覆盖 3-4-5 向量、零位移、非正 frameDeltaTime、timeScale 在 epsilon 上下及负值、长度恰等于 epsilon、Double→Single 窄化、倒数乘法次序，以及移动风二次 scale 的实际交接。最终测试数、覆盖率和工具门禁见同目录 `verification.json`。

本阶段只清除了第 4 门禁里“帧移动速度/方向归约”这一小段。帧 anchor/component/world pose、teleport/reset、`upstreamDelta` 的确切生成、风区成员选择、完整碰撞/约束与发布仍未闭合；在这些完成并形成可回退 C# 候选以前，不能称为 Unity 已实现官方物理。
