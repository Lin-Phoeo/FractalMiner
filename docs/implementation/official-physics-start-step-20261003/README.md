# 官方物理：普通粒子的姿态、惯性与受力链

2026-10-03，接续[粒子步末与受力片段](../official-physics-particle-step-20261003/README.md)。新增 `Tools/official_physics_start_step.py`：将普通粒子的动画姿态插值、已解析中心的惯性消费、阻尼曲线求值与受力积分连起来，并测试与 EndStep 的连续两步反馈。

后续已补[子步中心生成、局部惯性比例与angular state](../official-physics-center-step-20261003/README.md)，能向本模块提供解析后的step/inertia数据；又补了[粒子风力](../official-physics-particle-wind-20261003/README.md)和[固定粒子Spring](../official-physics-spring-20261003/README.md)。本页保留最初阶段的证据，同时以文末“同日增量”覆盖已经失效的待办描述。

**这是离线有限值参考，不是 Unity 已接入的完整官方后端。** 当前舞台、渲染、湿身、自阴影、MMD及预览物理未改动，没有新可见效果。帧级中心/anchor/world惯性、风区选择、碰撞、reset和完整状态发布仍未闭合；总体状态见[八个交付门禁](../official-physics-animator-buffer-20261003/PROGRESS.md)。

## 源证据及实施边界

只读取本地文件，不执行、加载、注入游戏 DLL。GameAssembly SHA：`c24495e51b406f03b03890c4788ee618ae022c991405be5d5b8b787cb775ae89`；metadata SHA：`0076743397acadf03d3b0064343a963c7c88863b8160526d397e4b3efb96f02e`。

- 主体：StartSimulationStepKernel$BurstManaged，method370473，RVA `0x5a64a78`，3746字节，SHA `8adcbd6287c41363fe524a74b99b7d6f543351031bb25bcdbd13bddc269fee5f`。完整 exact unwind 范围审读，移植限定的单粒子有限值路径，不移植原始名单/指针/调度。
- 姿态 slerp 后的 quaternion normalize：`0x59d7b18` /90字节，SHA `83b0fbd4b33b6db1e2653de08c74f14d7bc97674c733a6c080f4066e55c17a8f`。dot 使用 `(y²+x²)+z²+w²` 的 Single 次序，Single sqrt、倒数、逐通道乘。sqrt 有 exact unwind `0x2dd410` /155字节。
- float4 dot 和 multiply 没有 exact unwind；另外固定读取51字节/18字节，验证每条指令、寄存器操作数、无跳转/调用和末尾 RET。**不猜整个函数边界**。证明及完整指令留在私有目录，不发布。
- 沿用已核查的 Single float3 lerp `0x59fb7fc`、quaternion slerp `0x5a19748`、Single quaternion-vector rotation `0x2cd4520`、Double加减/lerp、窄化/宽化及 damping curve helper。没有用始终归一化输入的通用 Quaternion 替代源规则。
- 本轮也导出了中心生成 kernel `0x5a34900` /9444字节（method369644）的 exact unwind 范围。这只是**定位/留证，尚未完整解释、移植或验证该 kernel**，不能以此宣布中心算法完成。

动态 Burst 指针实际运行体仍未认证。Python trig/sqrt 与显式 Single 舍入不是官方 CRT/Burst 的逐位 oracle。源端没有本参考的 finite、正dt、插值权重[0,1]拒绝策略；这些是适配保护，不是新发现的官方 clamp 或异常契约。

## 不能合并的输入

`ParticleStartState.old_position` 对应 **oldPosArray（模拟历史）**；`old_animation_position/rotation` 对应 **oldPositionArray/oldRotationArray（上一动画proxy姿态）**。当前 proxy position/rotation 又是另一组输入。动画基准不得拿模拟位置代替，否则跟随动画和惯性链会串台。

Start Job 的 unboxed 字段：simulationPower@0、dt@16、stepIndices@24、attributes@40、depth@56、positions@72、rotations@88、Team@120、parameters@136、Center@152、oldPos@216、nextPos@232、basePos@248、velocity@264、baseRot@280、oldPosition@296、oldRotation@312、velocityPos@328、stepBasicPosition@360、stepBasicRotation@376。

| 所属结构 | 字段 / unboxed偏移 | 本轮用途 |
| --- | --- | --- |
| TeamData（stride464） | frameInterpolation@60 | 先窄化Single，再宽化用于Double位置插值；旋转插值仍Single |
| TeamData | velocityWeight@252、scaleRatio@96、gravityRatio@64、forceMode@264、impactForce@268 | 对接上一轮受力片段，不重复施加权重 |
| 参数（stride808） | damping曲线@28、inertia@180，其中depthInertia@32 | 按depth求曲线；惯性权重来自平方深度差 |
| CenterData（stride696） | oldWorldPosition@408 | 惯性旋转枢轴；不是nowWorldPosition |
| CenterData | inertiaVector@484、stepVector@456 | Single线性混合；先inertia再step |
| CenterData | inertiaRotation@496、stepRotation@468 | 同一权重的shortest-arc slerp |

## 本轮可执行规则

1. basePosition = Double `oldAnimationPosition + (proxyPosition − oldAnimationPosition) × Single(frameInterpolation)`。baseRotation 为 slerp 后再 normalize。逻辑写入 basePosition、baseRotation、stepBasicPosition、stepBasicRotation，然后才判断 movable。
2. attribute bit2 或 Team flag0x2000 进入惯性/受力。普通非moving粒子的 nextPosition、velocityPosition 均跟随动画basePosition，不求值无用的风、中心或受力参数。
3. 进入受力分支必须明确提供 `ResolvedStartCenter` 和 **Wind输出**。即使当前参数使作用为零，也不擅自默认中心、identity、风为零。中心/风数据由调用方负责按官方上游解析；本模块不是它们的生成器。
4. 权重 `t = Single(Single(1 − Single(depth × depth)) × depthInertia)`。translation = Single lerp(inertiaVector,stepVector,t)，rotation = slerp(inertiaRotation,stepRotation,t)。源片段未clamp；适配域外会拒绝而不是偷偷clamp。
5. `oldPosition − oldWorldPosition` 在 Double 算完后**窄化Single**，再 Single quaternion rotate；将结果和Single translation宽化Double相加，最后加旧中心。保留该精度边界和运算顺序。
6. velocityPosition 按 **oldPosition + (movedPosition − oldPosition)** 重建，不能直接代换成 movedPosition。大坐标的消去误差探针可区分两者，本轮专门保留了这个测试。
7. 同一混合rotation旋转旧velocity，按depth求damping曲线，再进入已有 force fragment；Single displacement宽化后加到Double movedPosition。中心平移**不额外乘scaleRatio**，scaleRatio只在后续受力处使用。
8. 最后逻辑写 velocityPosition、nextPosition。Start 不回写 velocityArray 或 oldPosArray；返回的 integratedVelocity 仅是局部诊断值。End才回写速度与旧位置。
9. flag0x2000 且 IsFixed bit1 在受力积分后调用 Spring；现在必须显式提供 `ResolvedStartSpring(parameters, normal_axis, noise_time)`，再把本步next、动画base/baseRotation和Team scaleRatio交给已核查的Spring参考。缺输入仍明确拒绝，包括同时有bit1/bit2的attribute3。spring标记但没有fixed位时仍走普通受力路径且不读取Spring输入。

返回写序不执行 NativeArray 写入、Transform setter 或发生异常时的部分写入；完整原生异常/并发契约没有移植。

## 验证与接续

先新增测试并观察缺失模块RED，再实现。57项合成测试覆盖动画/模拟历史分离、fixed路径、Double位置插值、slerp与后归一化、depth/曲线、旧中心枢轴、Single窄化、速度基准重建、尺度边界、风、六类force mode、fixed Spring拒绝和连续两步Start→End反馈。它们不是执行官方DLL或真实11组角色的动态验收。

全套 **2179 passed /114 subtests /3历史skip /2历史Pillow warnings**；24个离线参考模块2035statements/528branches，含分支覆盖100%；新模块92statements/14branches 100%。Ruff/format、Python compile、Pyright通过，临时工具环境pip-audit无已知漏洞。测试数量和覆盖率不代表Unity后端完成率。

同日增量：固定Spring已接入本模块的正确调用位置，新增测试证明“受力先算、Spring后拉回动画base”；详细精度边界、DirectCall fallback证明与新全套结果见Spring页面。本页上方2179项结果是历史快照，不应覆盖Spring阶段的更新结果。

下一步继续第4–6门禁的帧级中心/跨子步真实状态、风区选择、碰撞/reset；不是继续增加无关入口包装器。必须解析真实上游状态，而不是把这些必需输入用调参近似填完。随后组合约束与发布链，形成可回退C#候选，再在MMD/解包动作下实际验证。

私有证据与复核脚本：`D:/EndfieldTechLib/notes/official-physics-inertia-20261003-01/`。SHA摘要见本目录 verification.json。原生完整报告、游戏文件、资产与第三方源未发布。11组164 saved点、7个运行态文件、主HEAD和9557项原索引均保持；阶段提交使用独立索引与记录分支。
