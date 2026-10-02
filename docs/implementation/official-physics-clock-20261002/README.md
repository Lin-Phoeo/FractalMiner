# 官方物理：时钟公式、计数器与下一阶段约束入口

后续阶段已推进到 [距离内核数学与角度参数](../official-physics-constraints-20261002/README.md)：新增值类型布局和离线数学参考，仍未替换Unity舞台物理。本文是此前时钟阶段的记录，不是最新整体完成状态。

日期：2026-10-02。接续 [更新调度与订阅](../official-physics-scheduler-20261002/README.md)。本轮增加一个可执行的**离线时钟参考**，并增强已有原生审查工具；没有改 Unity 角色、渲染、湿身、阴影、场景或现有 MMD/物理预览。

## 目前进度：可用、已核实与未完成分开

| 部分 | 当前可以说的结论 | 还不能说的结论 |
| --- | --- | --- |
| 角色渲染 | 已有可查看的提弗洛斯场景，多个材质/捕获输入/光照/后处理模块已有源码及测试证据 | 所有 variant、实时场景、特殊状态及完整管线全部官方等价 |
| 湿身、自阴影 | cloth01/02 湿身可预览；自阴影提交时序修复已有测试及用户反馈 | 全角色/所有天气与阴影 pass 都已认证 |
| MMD | 干净初始姿态、已有 VMD 的加载/播放/采样预览可用；有替代次级运动 | 任意动作/源骨架、脚接触、表情、相机和整段视频已经完美 |
| 官方物理 | 11 组原始配置/挂点已有离线恢复；更新枚举、字段、挂接、订阅和完成入口已有证据；本轮补时钟公式 | 原始 solver 已接入；最终运行参数已知；所有物理骨局部空间/PPtr 已闭合 |

现有 `EndfieldSecondaryMotion` 仍是 MIT UniVRM 核心的简化适配：30 条已审查加权边，固定 120Hz，有限碰撞代理和确定性重放。**这一轮没有悄悄把它切到 90Hz**。原始构造默认 90Hz 与角色运行时最终设置不同，改变频率还必须配合本页强度补偿和真正约束算法。

历史渲染/MMD门禁参见 [环境反射与完整剩余范围](../cloth-environment-20261001/README.md)、[湿身与 MMD 测试入口](../wetness-mmd-start-20261001/README.md)、[替代物理说明](../secondary-motion-20261001/README.md)。这些是各自有边界的结果，本轮没有重新全量运行 Unity，不能由 Python 测试推出整个成品已验收。

## 两个计数回调：由原字段身份补齐

TimeManager 的 `<FixedUpdateCount>k__BackingField` 是实例 Int32，offset=0x20。新增受限 `inspect_leaf_counter` 只接受两种两指令入口路径：已认证字段的 INC32/RET，或 MOV32 immediate-zero/RET。宽度、receiver、index/segment、字段种类/静态身份、重复字段、非零 reset、分支/call/额外写入/RET-immediate均拒绝；不按相邻方法地址、padding 或通用“扫到 ret”猜整函数长度。

| 回调 | 已验证的正常入口路径 | RET | 路径字节数 |
| --- | --- | --- | --- |
| AfterFixedUpdate，method370663 | RVA0x4a475c0：实例计数加一，32 位回绕 | 0x4a475c3 | 4 |
| AfterRenderring，method370664 | RVA0x4a45960：实例计数清零 | 0x4a45967 | 8 |

结合上一阶段订阅身份，这分别绑定到 afterFixedUpdateDelegate 和 afterRenderingDelegate。证明的是**回调被调用时**的写入，不证明运行时循环已安装、EnableTick 必定开启、每个渲染帧一定调用几次；更不等于模拟子步数。有效普通对象接收者、无外部并发写入是该离线解释的前提，异常/fault未认证。

## FrameUpdate 的实际数学

原生入口 RVA0x32c1f60，hot range [0x32c1f60,0x32c2080)，CHAININFO 关联 cold range [0x4d5a824,0x4d5a855)。公式来自对这些原始范围的人工逐指令追踪，不是从现有预览/商业组件抄出。

令 `F32` 表示每个 Single 运算边界的舍入，`P(a,b)` 表示源端 float power：

```text
frequency = clamp_int(frequency, 30, 150)
maxSteps = clamp_int(maxSteps, 1, 5)
globalTimeScale = clamp01(globalTimeScale)
simulationDeltaTime = F32(1 / frequency)
maxDeltaTime = F32(maxSteps * simulationDeltaTime)
r = F32(90 / frequency)
simulationPower = (
    r,
    r > 1 ? P(r, 0.5f) : r,
    r > 1 ? P(r, 0.3f) : r,
    P(r, 1.8f)
)
```

`GlobalTimeScale` 本方法只被限幅、写回，**不参与本方法中的上述步长/向量乘法**。这不能推出它在 Team/后续时间累计中没有用途。`MaxDeltaTime` 只是这个方法的字段输出，不能据此宣称实际每帧会执行 maxSteps 次或完整累计算法已恢复。

关键 trace：频率/次数的 signed clamp 分支返回各自写回点；0x32c1fb0 调用 clamp helper；0x32c1fd8 的 divss →0x32c1fdf 写0x28；0x32c1fe4 的 mulss →0x32c1fef 写0x2c；0x32c1ff4 计算90/frequency；两次 comiss/ja 只在 r>1 走不同指数冷块；最后按四次 SHUFPS 和三次 MOVSS 的 lane 流转写0x30。

| Single 常量 | 使用 site | RIP 数据 RVA | 文件原始值 |
| --- | --- | --- | --- |
| 1.0 | 0x32c1fb5 | 0xa8c2ce8 | 0000803f |
| 90.0 | 0x32c1fbd | 0xa8c2e34 | 0000b442 |
| 1.8f = 1.7999999523162842 | 0x32c2011 | 0xa8c2fe8 | 6666e63f |
| 0.5f | 0x4d5a824 | 0xa8c2cfc | 0000003f |
| 0.3f = 0.30000001192092896 | 0x4d5a83d | 0xa8c2e58 | 9a99993e |

lane 复核：对 xmm6 的低 lane 记 `r`，未定高 lane记 u/v/w：SHUFPS e1 后 MOVSS→(A,r,v,w)，SHUFPS c6 后 MOVSS→(B,r,A,w)，SHUFPS27 后 MOVSS→(C,r,A,B)，SHUFPS39→(r,A,B,C)。A/B分别是两个条件补偿，C是1.8次幂；不能把 float4 分量顺序凭习惯补成另一种排列。

clamp helper RVA0x2d5a5d0 到 RET0x2d5a5ed 的支持路径只有 XMM0/1 和 flags 操作，没有 GPR写入/call：有限输入的正常路径为小于0→0、大于1→1、否则原值返回（包含负零）。因此 FrameUpdate 在这次调用后继续使用 EAX/ECX 的频率/次数有依据，不只是相信普通 ABI 的 volatile 寄存器总会保持。

power 身份也另查：`System.MathF.Pow` 的 metadata method276480 / mscorlib token0x0600092b / RID2347 对应 RVA0x9837b60；其单条 JMP 到0x29b24c。该 wrapper 的有界范围包含正常 positive-finite 路径把原两参数送入0x2dbe90的 call（site0x29b38b）；这是 FrameUpdate 实际直接调用的同一 helper。公开 [MathF.Pow 文档](https://learn.microsoft.com/en-us/dotnet/api/system.mathf.pow?view=netstandard-2.1) 仅支持幂函数语义，具体地址身份与数据流来自本机文件。没有将现在的 .NET 实现误当游戏 CRT，也没有恢复/复制整段 CRT 数值算法。

## 可执行离线参考与适配边界

新增 `Tools/official_physics_clock.py`：不可变 FrameSettings，输出受限频率/次数/scale、Single 步长、最大时间量及补偿向量；`fixed_callback_count` 明确模拟 Int32 加一/清零语义，不拥有 Unity 时钟、Jobs 或骨架。

Python double `math.pow` 后舍入为 Single 只作数学参考，**不是原生 CRT/SIMD pow 的逐位等价证明**；测试也不是独立运行官方 DLL 后的对照。finite/Single可表示/Int32与严格bool输入检查是我们适配策略，不声称官方原生方法会以相同方式拒绝NaN/inf/坏类型。未改门限来掩盖这些边界。

## 已定位的约束入口：接下来查这里

把九个约束 owner 的原生方法身份加入本地审查报告，关联 SimulationStepUpdate 的直接调用点。以下只认证文件中的调用位置与目标身份，**不是所有角色/分支下的必经执行顺序或固定迭代次数**。

| 目标 | method index | 目标 RVA | SimulationStepUpdate call site |
| --- | --- | --- | --- |
| TetherConstraint.SolverConstraint | 369186 | 0x32b2040 | 0x32b421a |
| DistanceConstraint.SolverConstraint | 368870 | 0x32b50b0 | 0x32b4247、0x32b42fb |
| AngleConstraint.SolverConstraint | 368712 | 0x32be760 | 0x32b4274 |
| TriangleBendingConstraint.SolverConstraint | 369205 | 0x32b2d80 | 0x32b42a1 |
| ColliderCollisionConstraint.SolverConstraint | 368728 | 0x39788a0 | 0x32b42ce |
| MotionConstraint.SolverConstraint | 368918 | 0x32b1c00 | 0x32b4328 |
| SelfCollisionConstraint.SolverRuntimeSelfCollision | 368947 | 0x32b2f20 | 0x32b4361 |
| SelfCollisionConstraint.SolveIntersect | 368950 | 0x32b2ed0 | 0x32b437e |

这些八个入口各自通过 RUNTIME_FUNCTION/CHAININFO 关联热冷块，新增11,365字节有界解码。InertiaConstraint/SpringConstraint 在此已审查的 direct sites 没匹配，不等于没有这两项：内联/其他阶段/间接Job链仍待查。Burst kernel、缓冲索引、参数曲线、权重与完整约束数学尚未认证。

## 后续实施顺序

1. **约束数学**：沿上表从距离、角度入手，核查实际 kernel/参数与缓冲读写；再补碰撞、惯性、复位和输出旋转。调用入口找到了不等于算法恢复了。
2. **11组配置/空间适配**：闭合45个局部旋转/linear差异、辅助骨和18个额外碰撞挂点，并继续查外部MonoScript PPtr、最终频率/模式写入者。不覆盖当前正确加权bindpose来凑物理骨。
3. **独立可切回后端**：每条骨写回只有一个所有者，等待Job完成再切模式/重建；不照搬不可用的游戏跨帧icall。接时钟与原始参数，并保留替代预览作为回退。
4. **实际动态验证**：静止、转身、下蹲、跳跃、快速移动/复位，再测MMD倒拖、循环、帧步进和固定出帧的可重复性。需要烘焙/缓存优化时明确标为MMD适配，不称官方算法。
5. **完整成品**：已证材质/光照/后处理整合、特殊状态及实时场景检查，随后表情、相机/音轨、长片录制和打包。目标是逻辑可信、观感自然、适合你的制作需求，不报虚假的完成百分比或“再接一个模块就完美”。

## 验证、复现与保留

全套 Python：759 passed /3历史skip /114 subtests /2历史Pillow告警；本轮新增62项。Ruff/格式检查通过，Pyright零错误；临时工具环境pip-audit未发现已知漏洞。含分支的工具合计覆盖91.80%，新增clock模块100%；**不是Unity/C#/HLSL或整项目覆盖**。首次RED为缺少counter函数/clock模块；第一次GREEN后lint发现两处import顺序、typecheck发现负例传入int给bool的静态类型问题，已修复并重跑完整套件，没有删除负例。

本机新报告：`D:/EndfieldTechLib/notes/official-physics-clock-20261002-01/native-clock-02.json`、`calls-clock-02.json`、`clock-coverage-02.json`。旧01保留。总32 inventories /810 managed entries，59 selected：55 unwind families /165 ranges、3 restricted leaf paths（构造+两个counter）、1 pending ForceCompleteAllJob，选中方法共54,866字节。更多字段/字符串/地址仅适用于记录的原始文件SHA，不出版原binary/metadata/bytecode或完整native manifests。

复现复用 `Tools/export_official_physics_native.py.export_files`：在DEFAULT_SPEC的inventories追加 `System.MathF` 和上表涉及的九个约束owner（含InertiaConstraint/SpringConstraint）；type-info cell仍为MagicaManager=0x18d050868，metadata_usage_cells仍来自上一阶段verification的27值。然后用calls.export_files，selections=DEFAULT_METHODS +上表八个目标全名。输入路径和报告SHA见verification.json，输出必须用全新文件，不能覆盖证据。两个工具的默认CLI用途保持兼容。

主HEAD和用户暂存索引不动；六项历史保护文件匹配，现有修改后的MMD舞台raw SHA仍为5b4fd74ccbb85348e5855f1741fe32cb2754a13afca8327471c1e8573216d13a，原样保留且不纳入阶段提交。本轮没有启动游戏、注入、运行DLL或重跑Unity，也没有改捕获、sealed原始资料或质量/性能设置。
