# 官方物理：粒子受力片段与步末状态更新

2026-10-03，接续[动画读取](../official-physics-animator-buffer-20261003/README.md)。本轮新增可执行代码 `Tools/official_physics_particle_step.py`，不是只增加入口清单。完成 **EndSimulationStep 的有限单粒子值参考**，另补 StartSimulationStep 中已经完成惯性变换之后的阻尼/重力/外力积分片段。

**完整官方后端仍未接入 Unity，没有新可见物理效果或实际动作验收。** 当前舞台、渲染、湿身、自阴影、MMD和替代物理均未改动。整体剩余项见[三类、八门禁](../official-physics-animator-buffer-20261003/PROGRESS.md)。

## 源绑定与执行路径边界

本地 GameAssembly 和 metadata SHA 分别为 `c24495e51b406f03b03890c4788ee618ae022c991405be5d5b8b787cb775ae89`、`0076743397acadf03d3b0064343a963c7c88863b8160526d397e4b3efb96f02e`。只作离线文件读取，未执行、加载或注入游戏 DLL。

| 身份 | RVA / 字节数 | 本轮用途 |
| --- | --- | --- |
| StartSimulationStepKernel$BurstManaged，370473 | 0x5a64a78 / 3746 | 完整范围审读；仅实现其惯性后的受力片段 |
| EndSimulationStepKernel$BurstManaged，370554 | 0x5a6ff88 / 3512 | 有限单粒子末步计算及逻辑写入顺序 |
| End direct-call Invoke，370565 | 0x5a7210c / 545 | 区分动态 Burst 指针与明确的 fallback |
| Invoke 的 End fallback | 0x5a68cc8 / 3512 | 从 +0x95 初始化后开始，与上行 managed body 的规范化指令完全一致 |
| End job UnsafeDo，370636 | 0x5a71dd0 / 481 | 核对字段向 range 参数的搬运；不当成单粒子主体 |
| End range managed，370555 | 0x5a69a80 / 304 | 有符号正计数循环，逐项调用单粒子 wrapper；未移植原生调度 |

不按相邻函数地址猜边界：主体使用 AMD64 exact RUNTIME_FUNCTION 范围。若干标量 helper 没有 exact unwind，另以固定尺寸、限定指令、内部直接分支/返回路径证明，未声称整个方法边界。Single clamp 最大值分支有回跳，不能扫到第一个 RET 就截掉。

**Burst 指针实际指向哪个运行体仍未认证。** 上述是源端 managed/fallback 规则；Python sqrt、Single 舍入参考不是官方 CRT/Burst 的逐位运行 oracle。

## 三个位置与两种速度：不能合并

End job unboxed 字段：dt@0，stepIndices@8，Team@24，parameters@40，center@56，attributes@72，depth@88，teamIds@104，nextPos@120，oldPos@136，velocityPos@152，velocity@168，realVelocity@184，friction@200，staticFriction@216，normal@232。

Team stride=464，参数 stride=808，Center stride=696。Team 参数身份：scaleRatio@96、velocityWeight@252；参数身份：惯性参数@180，其中 centrifugal@36、particleSpeedLimit@40；碰撞参数@612，其中 dynamicFriction@4、staticFriction@8。Center nowPosition@368、angularVelocity@528、rotationAxis@532。不可混淆这三个结构的局部偏移。

| 输入/输出 | 实际角色 |
| --- | --- |
| nextPos | 本子步约束后的位置；End **不回写这个数组** |
| oldPos | 上一步位置；End 用于计算 realVelocity，最后更新为局部修正后的 next |
| velocityPos | 模拟速度的独立基准；约束可另行修改它，End **不回写这个数组** |
| velocity | 后续积分使用的模拟速度；可受动态摩擦、限速、离心补偿与权重影响 |
| realVelocity | 局部修正后的 `(next − old)/dt`，不附加限速/离心/velocityWeight |

普通非 movable 粒子跳过摩擦和 velocity 回写，但仍更新 realVelocity、oldPos。Team flag0x2000（spring）会让非 movable 粒子也进入前者分支；没有增加额外 root 跳过规则。

## 已落地的步末规则

1. normal 的 Single squared length > Single(1e−8) 且 friction>0、Single(staticParameter×scaleRatio)>0 时进入静摩擦。`Project(v,n)` 是 `n×dot(v,n)`，**不除以 dot(n,n)**；传入非单位 normal 时也保留源规则。
2. tangent = `(next−old) − Project(next−old,n)`。低于静摩擦速度门限时 saved stick 的 Double 中间量增加 Single(.04)；否则减少 **max**(Single(.05), (speed−threshold)/Single(.2))，不是 min。无有效静摩擦时减少 Single(.05)。clamp01 后，saved 数组写回 Single。
3. 使用未窄化的 Double stick 同时从**局部 next、局部 velocityPos**减去 tangent×stick。因此不能擅自把模拟速度清零，也不能把局部 next 修正立即写到 nextPosArray。
4. 计算 Double `(next−velocityPos)/dt`。动态摩擦方向来自其**窄化再 Single normalize**的方向；因子按 source dot、.5 映射、平方、clamp 顺序计算。friction memory 每步乘 Single(.6)。
5. particleSpeedLimit≥0 才限速，门限为 Single(limit×scaleRatio)。ClampVectorLength 的长度 epsilon 是 **Single(1e−9) 宽化 Double**，不同于方向/squared-speed 使用的 Single(1e−8)；不能统一替换。
6. 离心项使用 Center 原始轴和当前位置。径向 delta 必须先窄化 Single 再宽化，ProjectOnPlane 同样不除 normal 的模长。方向对齐使用摩擦/限速**之前**归一化得到的方向；增量按 `((1−depth)+1)×ω×ω` 的 Single 边界、半径、centrifugal、Single(.02) 的原 Double 次序计算。
7. 离心补偿在限速**之后**，再乘 velocityWeight 并窄化写 velocity。所以最终 velocity 可以超过前面的 limit，不能自作主张末尾再限一次。
8. 正常参与者的逻辑写入顺序是 staticFriction → friction → velocity → realVelocity → oldPos。返回值记录此顺序；Python 没有执行实际 NativeArray 写入或异常时部分写入。

## 受力积分片段：实施范围严格限定

`integrate_force_fragment` 的 velocity 已经过原始惯性旋转；damping 已经是曲线求值结果，wind 已经是 Wind 的输出。返回 Single velocity 与 Single displacement，供后续宽化后加入 Double 位置。该返回 velocity 是局部中间量，**不代表 Start 写了 velocityArray**。

依次执行：velocity×Team.velocityWeight；damping clamp01，再 `clamp01(1−damping×simulationPower.z)`；gravityDirection×Single(gravity×Team.gravityRatio)；加入 impact、wind；force×scaleRatio×dt；加入旧 velocity；最终×dt 得 displacement。模式1/2把 impact除以 `1 + 5×(1−depth)²`，2/11清掉旧 velocity，10/11不除质量，其余 Int32 mode 的 impact为零。

**没有把已审读的整个 Start 标成实现完成。** pose/旋转插值、中心更新和惯性变换、Wind/Spring 生成、Team 时间累积、粒子名单、实际迭代顺序、reset、最终显示/发布仍需接通。曲线/风不能默认填零充当完整官方算法。

## 测试与下一步

57项新增测试覆盖自由粒子、fixed/spring分流、静摩擦stick/slip及非单位normal、动态摩擦方向、记忆衰减、distinct epsilon、速度权重、离心同向/反向/轴上及退化输入、六类force mode、尺度/风/重力、两步反馈。是**合成数学/状态测试**，不是独立执行官方 DLL 对照。

TDD缺失模块 RED 已观察；57项 GREEN；全套 **2122 passed /114 subtests /3历史skip /2历史Pillow warnings**。23个离线参考模块1943statements/514branches，含分支覆盖100%；新模块150statements/32branches 100%。Ruff、格式、Pyright通过，临时工具环境pip-audit无已知漏洞。覆盖率不代表 Unity 或全 solver 覆盖。finite、正 dt、边界和退化轴拒绝是适配保护，不等同官方异常契约。

下一步优先闭合中心/惯性与 Start 前段、Wind/Spring 和跨子步状态，然后碰撞/reset，并与现有约束参考组合。完整候选链具备后，才做可回退 C# 后端、舞台切换与 MMD/解包动作动态验收。没有重新分叉到无关工具或逐像素调参。

私有审查文件和复核脚本留在 `D:/EndfieldTechLib/notes/official-physics-integration-20261003-01/`；摘要 SHA 见 verification.json。review-01是发现阶段快照；当前 review.py 的扩展 owners 用于复现 review-02/03/04。所有输出须用新目录/文件，不能覆盖原证据。未发布原始资产、DLL/metadata、完整反汇编、native manifests或第三方源。

11组164 saved点克隆保护通过，7个运行态文件、用户修改的舞台、主HEAD及9557项原暂存索引保留。阶段提交仍使用独立索引与记录分支，不纳入用户暂存内容。
