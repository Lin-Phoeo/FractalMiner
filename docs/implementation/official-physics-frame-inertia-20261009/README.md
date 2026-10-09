# 官方物理：已解析输入上的帧级惯性修正

2026-10-09。新增 `Tools/official_physics_frame_inertia.py`，把帧级全局惯性、移动/旋转限速、步数补偿、历史姿态回拉与[帧移动归约](../official-physics-frame-motion-20261008/README.md)接通。返回的 `step_state` 直接消费于[子步中心](../official-physics-center-step-20261003/README.md)，`motion` 消费于移动风。

**交付是离线有限值参考，仍不是完整帧中心或 Unity 官方物理后端。** 当前组件采样、working-old、anchor/smoothing 临时值、pivot 与历史状态必须由调用方完成前序解析，不能拿舞台 root 或全零默认值冒充原输入。当前 Unity 预览保持未改。

## 来源与新核实的事实

只静态读取固定版本文件，不执行、加载、注入或附加游戏 DLL/进程。GameAssembly SHA `c24495e51b406f03b03890c4788ee618ae022c991405be5d5b8b787cb775ae89`，metadata SHA `0076743397acadf03d3b0064343a963c7c88863b8160526d397e4b3efb96f02e`。

- 所在函数仍为 method369644，`0x5a34900..0x5a36de4`。本轮主要片段 `0x5a36313..0x5a36ab1`（尾不含），1950 字节、402 条指令，SHA `8ba48a69caebd08a48cce6bcc999c3f048c0020e9f9aad05ffc7407914a71dc2`；另核查分片外 reset 的清零分支。不是独立函数 ABI，也不是完整 kernel 已移植。
- final motion 位移已确认是 **当前采样组件位置 − 惯性修正后的 working-old 位置**。当前位置来自 `transformPositionArray`；syncTeam 非零且 flag `0x40` 时使用 syncCenterTransformIndex，否则使用中心 transform index。无 sign-remap 路径的 working-old 最初来自旧组件位置；其他前序路径仍未完整移植。
- `frameComponentShiftVector` 是另一条输出：初始位移乘累计平移 fraction，加 anchor 偏移，再加 smoothing 偏移。它不是移动风残差的通用替代物。某些无修正路径两者可以相等，不能把此前“不作等同宣称”误解成“证明永不相等”。
- 局部 `scale_length_ratio` 是 `lengthF(currentComponentScale)/lengthF(Team.initScale)`，不是 Team.scaleRatio；旋转限速先乘 `57.295780181884766f`，再除 frameDeltaTime。
- Team unboxed 字段：frameDeltaTime@16、nowTimeScale@48、updateCount@52、initScale@84、velocityWeight@252。补偿不使用 blendWeight@260。
- 历史变换 pivot 是同一次前序解析后的 `CenterData.oldComponentWorldPosition@152`。只回拉 oldFrame position/rotation@312/@336 与 now position/rotation@368/@392；不改 frameWorld 目标和历史 scale。

完整本地指令/字段证明在 `D:/EndfieldTechLib/notes/official-physics-frame-inertia-20261009-01/`；公开仅保存自有参考、测试、摘要及 SHA，不上传原资产或完整原生报告。

## 顺序与输入契约

1. 初始位移保留 Double 减法，需作为 float3 的地方再逐 lane 窄化。初始差旋转是 `currentRotation * inverse(workingOldRotation)`。
2. 全局跟随 fraction 为 `Single(1-worldInertia)`；flag `0x200/0x800/0x80000` 强制为 1。门限为 `1e-8f`，不是 `1e-6f`。
3. 移动/旋转速度限制消费全局跟随后剩余的位移与角度。fraction 按 `Single(Single(Single(1-prev)*weight)+prev)` 累积；Double lerp 是 `a+(b-a)*Double(singleWeight)`。
4. count 补偿按 `Single(Single(Single(count)*simulationDeltaTime)/Single(nowTimeScale*frameDeltaTime))` 再 clamp01；随后依次混合 velocityWeight、nowTimeScale。不能重关联乘除。末次旋转 slerp 被调用但结果未保存到工作旋转，参考保留这一源行为。
5. 最终平移必须是 **`Single3(Single3(Single3(initialDeltaF*fraction) + anchorShiftF) + smoothingShiftF)`**。乘法和两次加法分别舍入，不得合成 FMA；smoothing offset 与 smoothingVelocity 不是同一个东西，也不能提前合并两个 offset。最终旋转为 `anchorShiftRotation * slerp(identity, initialDeltaRotation, rotationFraction)`。
6. 世界历史位置按 Double 的 `(shift + rotate(q, oldPosition-pivot)) + pivot` 回拉，旋转按 shiftRotation 左乘；不能改写成另一个代数相等但舍入不同的次序。
7. final residual 进入 `reduce_frame_motion`，再显式交接移动风；子步中心使用返回的 flag 与 `step_state`。reset 分片只清 shift、shiftRotation、smoothingVelocity；完整 reset 生命周期由前序负责，不能因此宣称已完成。

finite、非负 count/timeScale/ratio、[0,1] inertia/velocityWeight、非零 count 补偿分母都是适配层限制，不是假定官方新增 clamp/异常规则。Python sin/acos/sqrt 是数学参考，不是原生 CRT/Burst 逐位 oracle。TRS 与完整逆矩阵的运算顺序尚未移植，不能将“逆四元数旋转再除 scale”标成其等价实现。

## 验证、交接与下一步

53 项针对性测试覆盖多阶段共存、非二进制补偿黄金值、Single 两次加法取消、巨大 Double 坐标、不同 pivot、非共轴工作旋转、两组历史左乘、reset 清零、frame→wind，以及 frame→center→Start→End 两子步反馈。后一条是合成已解析输入链，约束迭代、pending tail 与 native publication 均不假装完成。

完整 `Tools/tests`：2457 passed、114 subtests、3 历史 skip、2 Pillow 弃用告警。31 个 `official_physics*` 参考模块的 2682 statements / 628 branches 覆盖 100%；Ruff、format、Pyright、compile、pip-audit 通过。完整来源摘要、输入限制与验证 SHA 见 `verification.json`。覆盖率说明参考代码被测试到，不代表整个官方 solver 或真实角色已验收。

下一主线是把本片段**前序 working-old / anchor / smoothing 偏移的生成**补齐，连同 sign-remap、teleport/reset 和帧中心目标形成真实生产链；随后补风区/碰撞/约束完整顺序和状态发布，再做可回退 C# 后端及 MMD 实测。不要跳过前序输入生产直接套到当前舞台，也不要继续重复本片段调参。
