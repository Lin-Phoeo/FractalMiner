# 帧末显示位置与动画历史发布

2026-10-09。实现 `Tools/official_physics_display.py`，对应 `CalcDisplayPositionKernel$BurstManaged` method370578 / `0x5a6da04` 及 DirectCall 实际非Burst fallback `0x5a6857c` 的有限值路径。它补上模拟子步之后、proxy后处理之前的显示位置预测、根部距离限制、显示混合、上一动画姿态保存和负缩放旋转重建。

**这是离线Python值参考，不是Unity里已经切换的官方物理。** 本轮没有改舞台、模型、渲染、湿身、自阴影、MMD导入或现有预览物理。真实NativeArray发布、并行Job划分、碰撞/约束全链、暂停/seek请求和C#候选后端仍待闭合。

## 静态来源与边界

原DLL与metadata仅静态读取，SHA-256分别为 `c24495e51b406f03b03890c4788ee618ae022c991405be5d5b8b787cb775ae89`、`0076743397acadf03d3b0064343a963c7c88863b8160526d397e4b3efb96f02e`。managed kernel与实际fallback均为1621字节、371条指令；本轮完整固定两个函数边界和SHA，并核对74个关键managed位置、对应54个fallback位置、21个exact-unwind函数、3个无unwind但逐分支人工定界的leaf、Job/Team布局、13个参数名及三个常量。

间接Burst函数指针没有执行或认证；完整函数被静态固定也不等于动态调度和Burst逐位等价。原DLL没有加载、执行、注入或改写。完整静态报告保存在 `D:/EndfieldTechLib/notes/official-physics-display-20261009-01/`，仓库只发布摘要和哈希，不发布原生函数体或游戏资产。

## 已恢复规则

1. 每个原全局particle slot先读Int16 teamId；team0跳过。处理门要求flag2，且没有bit61、`0x10`、`0x800`、`0x80000`。proxy slot为 `proxyCommonChunk.start - particleChunk.start + globalParticleIndex`。
2. 普通非移动点直接把原动画proxy位置写入`dispPos`，不写proxy position。attribute bit2（Move）或Team flag `0x2000`（Spring）才进入显示预测。
3. 预测先做Single `realVelocity * simulationDeltaTime`，再拓宽并加到Double `oldPos`。时间比例是Single `(time-oldTime)/(nowUpdateTime+dt-oldTime)`；分母不大于0时取0，正分母时**不钳制比例**。之后用该比例在上一`dispPos`与预测位置之间作Double lerp。
4. `vertexRootIndices[proxySlot] >= 0` 时，根slot是 `proxyCommonChunk.start + localRoot`。显示点到根的最大长度为“根当前proxy位置到本点原动画位置的Double距离 × 原 `1.2999999523162842`”。仅当显示偏移长度同时大于原约 `9.999999717180685e-10` 和该半径时缩短。range参考按原升序循环应用proxy写入，因此后项读取根时可看到前项已发布的根位置；这不是并行range划分证明。
5. 未混合的显示结果始终写`dispPos`。proxy position再按Team `blendWeight@260`混合：`<=0`保留原动画，`>=1`使用显示结果，中间为Double lerp；不是用`clothSimulateWeight@240`，也不把混合后的proxy写回模拟历史。
6. flag `0x20` 在位置混合之后，把**原动画proxy位置与原始Single旋转**复制到`oldPositionArray`/`oldRotationArray`。它们不是`oldPosArray`/`oldRotArray`，也不是混合后的显示输出。
7. flag `0x20000` 使用`negativeScaleDirection@104`构造原Single quaternion TRS，取缩放后的Y/Z列，经native `39d4200` wrapper进入 `39d4250(forward,up)`，适配到现有Python API为 `(up,forward)`。没有重复Y/Z交换，不改动画历史里的原旋转；只发布重建后的proxy rotation。
8. 返回对象不可变，`writes`只记录原逻辑写序；range在私有拷贝上模拟顺序写入，不修改调用者数组，也不冒充native失败后的部分写入或线程安全契约。

## 验证

87项本模块测试覆盖处理门、chunk映射、Move/Spring分支、未钳制时间比例、非正分母的未消费输入、Single→Double边界、根限制常量/epsilon及严格等号边界、blend端点、flag20/20000写序、非单位四元数固定bit-pattern、64组独立随机矩阵参照、大坐标、range前写后读/零count不读取/浅快照类型契约、未选择脏输入，以及reset→Start→End两子步→显示发布→下一帧非reset Start消费原动画历史→再次reset的组合值链。组合链的center/wind仍是手工resolved有限输入，不冒充碰撞约束或原生host帧序。

最终全套回归、覆盖率、静态源证明和依赖审计以同目录 `verification.json` 为准。有限值、非负Int16/Int32、无溢出、退化旋转拒绝是适配安全域，不是原unsafe代码的异常规则。Python Double/Single运算也不是CRT/Burst bit oracle。

## 下一步

显示位置和上一动画proxy历史的有限值发布已经从缺口中移除，但真正的角色物理还没有完成。下一主线仍是碰撞链与距离/角度等约束的真实输入、迭代顺序及依赖闭合；随后补host reset/暂停/seek与完整数组生命周期，才进入可回退C#后端和真实解包动作/MMD验收。整体门禁见[物理交付缺口](../official-physics-animator-buffer-20261003/PROGRESS.md)。
