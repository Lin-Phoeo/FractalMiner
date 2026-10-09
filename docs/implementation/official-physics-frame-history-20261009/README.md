# 帧重置补全与独立 PostTeam 历史推进

2026-10-09，`Tools/official_physics_frame_history.py`。本轮补的是有限值离线参考：已有 prelude 遗漏的持久字段、帧末权重初始化以及真正的 PostTeamUpdate。**不是完整粒子 reset、NativeArray 发布、Unity 后端或真实动作验收。** 当前舞台与现有物理未改动。

## 原顺序，不能提前推进历史

scale/sign → fixed-point frame target → frame inverse/remap → anchor → **prepare_frame_history** → frame inertia → frameLocalPosition → **initialize_frame_weights** → zones/帧字段发布 → 全部子步/求解 → 显示与transform回写/Collider post → **finish_frame_history**。

粗体函数是本轮参考接口；其他节点有现存参考或仍有未闭合输入/算子。此顺序不是可执行完整调度器，也不意味着各节点都已实现。

帧中心核末尾不是 oldComponent/oldAnchor/oldFrame 的统一历史推进。真正推进在独立 `PostTeamUpdateKernel$BurstManaged`（方法369588，`5a2c1f0..5a2c9d1`）。尤其不能在 target 生成后就把 oldFrame 复制成 frame，否则首子步会直接跳到新目标。

## 重置与权重

`prepare_frame_history` 调用已有 prelude，并补齐其未表示的字段；不修改冻结的既有数学模块。

| 条件/阶段 | 原字段来源与处理 |
| --- | --- |
| flag4，`5a3626d..5a362b8` | oldComponent pose/scale ← 当前组件样本；已有 prelude 处理工作变换/位置，本模块补 oldComponent rotation/scale 缓存 |
| flag4 或40000，`5a362c0..5a36313` | oldFrame/now/oldWorld pose ← 本帧已生成 frame target，oldFrameScale ← frameScale；本模块补 oldWorld 持久姿态 |
| 仅40000 | 不把旧组件旋转/缩放改成当前组件；不是 flag4 的同义分支 |
| anchor 与 teleport | anchor 在 teleport 之前；新触发 flag4 不追溯重跑 anchor，入口已有4/10000才由 anchor 模块初始化 |
| flag4 或8，`5a36c13..5a36c42` | stabilizationTime > Single(1e-6) 时 velocityWeight、blendWeight 同写0，否则同写1；必须在帧惯性之后，不覆盖该核已消费的旧权重快照 |

重置仍按原顺序先算 smoothing，再由 frame-inertia reset 清零；不能把清零前的速度反馈到下一帧。初始化权重也不同于子步 tail 中逐步增长的稳定化权重。

## 独立帧末规则

`finish_frame_history` 使用 IsProcess：flag2且非bit61、非10、非800/80000。无独立 team-index-zero gate；输入槽位/range 由真实调用方负责。

- 无条件 oldComponent pose/scale ← 当前组件，不取 corrected working-old，也不归一化原四元数。
- 仅 flag20：oldFrame pose/scale ← 当前 frame；同时清 forceMode、impactForce、skipCount。不是依据子步flag80或自行假设 updateCount。
- 无条件 oldAnchor pose ← 当前 anchor；以单位尺度的完整 Double TRS inverse 重新计算组件在 anchor 下的 local position，最后窄化成 Single3。不是 quaternion inverse/转置矩阵快捷替代。
- 普通帧末不改 nowWorld、oldWorld，也不把 transient working-old 改成下帧种子。下一次 scale 阶段重新从已推进的 component cache 生产工作变换。
- 清瞬态掩码 `0x406ac`：4、8、20、80、200、400、40000；**不清10000 AnchorReset**。
- 仅 Single time >7200时，time/oldTime/nowUpdateTime/oldUpdateTime/frameUpdateTime/frameOldTime各减 Single3600一次；严格大于，不循环、不用 wind-time 的阈值。

原 PostTeam 的 Team 数组发布从 `5a2c8b8`开始，Center 发布从`5a2c933`开始。本模块只返回所表示字段的值；`writes`是选中片段标签，不是实际 buffer 写入或 Job 完成。所有 Team/Center 未表示字段仍需真实发布与生命周期接入。

## 验证及边界

62项新测试包括两子步保持旧帧、帧末后下一帧继续、重置两步零移动后恢复、两阶段权重时序、跨帧 anchor 反馈、非单位四元数/完整逆矩阵、Double 巨世界小位移、瞬态位与时钟边界、未选分支不读非法输入及适配器拒绝。

最终全套2691项通过、114 subtests通过；3个历史skip和2个历史Pillow警告原样保留。37个official_physics模块3140条语句/688分支均覆盖。Ruff、Pyright（显式实际Python环境）、编译和工具环境依赖审计通过。静态证明校验原DLL/metadata SHA、75条关键指令、字段布局、函数/手验leaf边界与常数；两路独立只读审查。不是自动全CFG证明、原运行时逐位oracle或Unity动态验证。

有限值/奇异矩阵拒绝是适配器安全政策，不将其说成原程序的异常行为。没有执行原 DLL、注入或进程操作。原输入/证据/保护状态见`verification.json`。

下一主线：frameLocalPosition 原矩阵计算、wind-zone 真实选择和跨步输入/发布依赖；再补粒子 reset、碰撞/约束与完整生命周期，形成可切换 C# 候选后端后才做解包动作/MMD动态验收。[缺口账本](../official-physics-animator-buffer-20261003/PROGRESS.md)仍是当前状态依据。
