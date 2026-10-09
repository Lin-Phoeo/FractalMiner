# 官方物理：瞬移检测、运动平滑与已表示历史重置

同日增补：[锚点与Double TRS/full inverse参考](../official-physics-frame-anchor-20261009/README.md)已生产这一段的working-old与anchor shift，接本模块。更早的signed-scale remap、frameWorld目标生成和完整reset/tail发布仍待完成；本页冻结说明与verification保留初始阶段边界，最新进展见增补与PROGRESS。

2026-10-09。`Tools/official_physics_frame_prelude.py` 现可在**已完成 anchor/sign-remap 且已有本帧 frameWorld 目标**的输入上，生产 working-old、smoothing velocity、独立 smoothing shift 与状态标志，再接入[帧惯性修正](../official-physics-frame-inertia-20261009/README.md)。不是对舞台 root 套一个滤波器，也没有修改 Unity 当前后端。

## 固定来源与边界

静态来源固定为 GameAssembly SHA `c24495e51b406f03b03890c4788ee618ae022c991405be5d5b8b787cb775ae89` 与 metadata SHA `0076743397acadf03d3b0064343a963c7c88863b8160526d397e4b3efb96f02e`，不加载/执行/注入/附加游戏 DLL 或进程。

主要片段为 method369644 大 kernel 内部 `0x5a35eba..0x5a36313`（尾不含），1113 字节、219 指令、SHA `cf94210c9b1d5072a5ae8edf958053744f7e2c82d284f534d4bc4fee93944807`。65 个关键指令断言核对了分流、参数、运算、缓存写入与历史分支。它不是独立函数边界或完整 kernel；数学 helper 另用精确 unwind 边界/经检查的叶函数/明确 forwarding thunk 认证，不按相邻方法猜长度。

`InertiaConstraintParams` unboxed 字段：movementInertiaSmoothing@8、movementSpeedLimit@12、teleportMode@44、teleportDistance@48、teleportRotation@52。Team flag@0 / frameDeltaTime@16，Center smoothingVelocity@556。局部 scale length ratio 与前一模块相同，仍不是 Team.scaleRatio。

## 恢复的源顺序

1. 当前组件位置减 anchor-resolved working-old，先 Double 减再窄化 float3；差角由已核查 quaternion-angle helper 产生。KeepTeleport `0x200`、既有 reset `0x4` 跳过自动瞬移检测；mode0 禁用。否则 distance 比 `Single(scaleLengthRatio*teleportDistance)`，angle 先乘 Single 度换算常量再比 teleportRotation。任一 **≥** 阈值触发：mode1 置 `0x4`，mode2 置 `0x200`。本分片没有把这两种行为混同。
2. 清零本轮 smoothing shift 临时量；smoothing **≥1e-6f** 才进入平滑，否则保留旧 smoothing velocity 与 working-old，不能把缓存速度清零。
3. 只有 flag `0x20` 才采样并更新 velocity；dt>0 时目标是逐 lane `Single(deltaF/dt)`，否则目标为零。非负限速先乘局部 ratio，再限幅；长度 **>1e-9f 且 >limit** 才缩放，边界相等不缩放。限幅在滤波之前，不在之后。
4. 更新权重是 `clamp01(Single(Single(powF(Single(1-smoothing),3f)*.99f)+.01f))`。PowF 路径先把两个 Single 输入拓宽为 Double，调用与具名 System.Math.Pow 相同的 CRT target，再窄化 Single。不能换成三次 Single 乘法；系数乘法与加法还要各自舍入，不得 FMA。本参考用 Python pow 作有限数学值，不声称原生超越函数逐位等价。
5. velocity 按 `old + Single((target-old)*gain)` 更新。未置 `0x20` 时不重新计算 gain/limit，也不覆盖缓存速度；但本轮平滑仍使用它。
6. displacement 是 `Single3(velocity*dt)`，再拓宽为 Double；`newWorkingOld = currentDouble - displacementDouble`。独立 shift 是 **`Single3(newWorkingOld - oldWorkingOld)`**，不能化简为 float3 的 delta 减 displacement。即使位移为零，激活平滑仍置 `0x400`。
7. 随后 reset `0x4` 将本适配结构中的 working-old、working rotation、旧 component pivot 改为当前组件；`0x4` 或外部 `0x40000` 将 oldFrame/now 历史改成本帧 frameWorld 目标并复制 oldFrame scale。`0x40000` 单独出现不会重置 working-old/pivot，`0x200` 也不等于这个历史重置标志。

reset 不提前跳过平滑：源先执行上面步骤，随后才由下一帧惯性分片清 shift/shiftRotation/smoothingVelocity。只复原 `FrameInertiaState` 表示的字段；原函数还写 oldComponent scale、oldWorld 等字段，完整 reset 生命周期和原数组发布仍待实现，不能称为整套 reset 已完成。

## 使用与验证

`prepared = prepare_frame_inertia(anchor_resolved_state, frame_team, settings)`；随后 `advance_frame_inertia(prepared.state, prepared.team, inertia_settings)`。两个 settings 的局部 ratio 和 movement speed limit 必须来自同一帧/同一组原参数，不能使用两套互相矛盾的值。当前接口没有合成丢失的 anchor、signed-scale、frameWorld 目标，也不进行 Unity bone 写回。

测试先写并观察缺模块失败，再实现参考。45 项针对性测试覆盖阈值相等、两种瞬移模式、原标志 bypass、缓存速度分支、非正 dt、限幅前后顺序、两帧反馈、Double 巨大坐标与窄化、Pow 与系数运算次序、reset 后继续惯性消费，以及独立 anchor/smoothing 与 motion 的不同输出。工具与全套回归数字见 `verification.json`；合成数值链不冒充真实角色动态验收。

finite、smoothing [0,1]、局部 ratio 非负、支持的 mode0..2 是适配层限制，不是新增官方 clamp/异常规则。完整本地证据保存在 `D:/EndfieldTechLib/notes/official-physics-frame-prelude-20261009-01/`；公开只发布自有参考、测试与 SHA 摘要，不发布完整原生记录或游戏资产。

下一主线剩下更早的 anchor production、sign-remap/TRS 逆矩阵与 frameWorld 目标生成；然后才能消除“已解析输入”前提。风区/碰撞/约束完整消费、状态发布、C#候选后端和实际 MMD 动态验收仍需完成，不能跳过这些直接宣称官方物理落地。
