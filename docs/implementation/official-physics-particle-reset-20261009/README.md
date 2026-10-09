# 粒子帧重置与历史变换；修正帧中心参数适配

2026-10-09。实现 `Tools/official_physics_particle_reset.py`，对应 PreSimulationUpdateKernel$BurstManaged370446/`0x5a6035c` 的有限值路径：完整14缓冲重置、非重置时的负缩放与惯性历史变换、原全局粒子索引遍历。

**这是离线Python值参考，不是已经接入Unity的官方物理。** 当前舞台、渲染、湿身、自阴影与MMD没有改动。完整原输入发布、碰撞/约束生命周期、真实任务调度和C#候选仍待完成，不以测试数量表示完成率。

## 核实与纠错

原DLL/metadata只静态读取，SHA沿用已固定版本。managed kernel完整范围 `5a6035c..5a60d5a` /2558字节，DirectCall实际非Burst fallback `5a597d8..5a5a1df` /2567字节，均550条指令。两者reset片段318字节完全相同，SHA `3a7cd7a55ed3be99de0cc8c21f877ce6bfcf93a5eedb98ca6739cea4e7c1272c`。间接Burst分支仍未执行或认证，不能将fallback静态解释视为实际运行体证明。

此次沿旋转辅助函数复核，发现并修正前一阶段frame_target的两处真实错误：把native39d4250的 `(forward,up)` ABI套到Python `(normal/up,tangent/forward)` API，重复交换了Y/Z。原39d4200 `(Y,Z)`包装后得到native `(Z,Y)`，应映射为Python `(Y,Z)`。修复了最终中心与每点负缩放重建两处调用，撤回旧文档的“identity点产生轴交换中心”说法，纠正旧测试与随机矩阵参照。先观察identity回归RED，再修改实现。原helper数学未调参或替换。proxy Jobs371595/371597/371608另行检查，现有接口适配正确；没有泛改其他调用方。

## 原规则与输出

1. 从原Int16 teamId读取归属；team0跳过。IsProcess要求flag2，且没有bit61、0x10、0x800或0x80000。非处理Team不读proxy输入，不重置任何缓存。
2. flag4优先于0x40000/0x400，且**不按Fixed/Move属性过滤**。proxy slot = proxyCommonChunk.start − particleChunk.start + 原全局particleIndex；不是粒子index直读proxy，也不是局部bone序号。
3. 重置按原顺序写下表14个逻辑目标。Double位置保留；四元数只按Single复制，不额外normalize。旧模拟历史和旧动画proxy历史同时初始化，但它们仍是两个独立缓冲。

| 逻辑写序 | 原目标 | 来源 |
| --- | --- | --- |
| 1–3 | nextPos、oldPos、oldRot | proxy位置、位置、旋转 |
| 4–7 | basePos、baseRot、oldPosition、oldRotation | proxy位置、旋转、位置、旋转 |
| 8–9 | velocityPos、dispPos | proxy位置 |
| 10–14 | velocity、realVelocity、friction、staticFriction、collisionNormal | 全部零 |

4. 非reset且有0x40000时，先用同帧Center.negativeScaleMatrix变换oldPos、oldPosition、dispPos三组Double历史。两个历史旋转先以Single旋转+Y/+Z，再宽化→完整Double矩阵方向乘法→乘原caller的1.0→收窄→重建。不是inverse-transpose、polar decomposition或直接乘某个“矩阵旋转四元数”。两个Single速度也先宽化进行矩阵方向变换，再收窄。
5. 若还有0x400，随后使用**oldComponentWorldPosition@152**枢轴，按 `(shift + rotateDouble(q,old−pivot)) + pivot`处理三组位置；shift来自Single @204，q来自@216。历史旋转是 `shiftQ * historyQ`，速度只作Single旋转。0x400是InertiaShift；KeepReset是0x200，不混用。
6. 此历史分支只回写oldPos、oldRot、oldPosition、oldRotation、dispPos、velocity、realVelocity七项。其余七项保持；不要顺便清摩擦、normal或更新next/base。若没有reset/历史标志，整个输入值保持。
7. range按照原indexCount遍历 `0..count-1`，count≤0不消费数组。参考返回不可变结果及逻辑write顺序；不执行NativeArray写入或并发Job，不模拟原异常后部分写入。

`ParticleFrameState`区分上述全部14项；`ParticleResetTeam`保留原chunk start。`prepare_particle_frame`消费单个全局槽，`prepare_particle_frames`消费声明的全局范围。非reset变换必须提供同快照的 `ResolvedParticleFrameCenter`，没有默认identity/零位移补输入。Start的stepBasic缓冲不在原Pre Job中，它们由Start写入，不在reset函数中额外添加。

## 连续链与验证

77项新增测试覆盖门控/优先级、14/7目标与写序、global chunk映射、Double大坐标、非单位旋转、未消费脏值、负缩放/惯性组合次序、range/缺失输入拒绝。组合测试执行修正后的fixed-point目标生产→帧历史重置→粒子重置→子步中心→选区风力→Start→End两子步→再次从新proxy重置；确认无旧速度/摩擦残留，且End不冒充动画历史发布。这是合成值链，不是原生调度或实际MMD seek验收。

全套2852 passed /114 subtests /3历史skip /2历史Pillow warnings；39个official_physics模块3358 statements、754 branches含分支覆盖100%；新模块112 statements、26 branches100%。compile、Ruff/format、显式Python路径Pyright通过；依赖安全审计与源/运行态保护结果见verification。测试覆盖率不证明native/Burst逐位相等或真实角色物理完成。

本轮源证明固定71条关键指令、15个exact unwind函数、两个手工门控范围、Job/Team/Center布局和参数顺序。完整静态快照/复核报告保存在 `D:/EndfieldTechLib/notes/official-physics-particle-reset-20261009-01/`，仅公开摘要与SHA，不发布原生完整报告或游戏资产。Double/Single有限性、非负Int16归属/Int32无溢出范围、退化cross拒绝均是适配安全域限制；原始unsafe代码没有这些边界检查。

下一步集中补碰撞/约束链的真实输入、顺序与依赖发布；随后建立可切换C#候选和真实动作验收。暂停恢复/跳帧请求如何产生reset标志、真实proxy数组如何发布、显示/帧末动画历史推进仍不能由这个reset参考替代。整体缺口见[PROGRESS](../official-physics-animator-buffer-20261003/PROGRESS.md)。
