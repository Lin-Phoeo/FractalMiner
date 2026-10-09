# 当前物理交付缺口：不以测试数量代替完成进度

初版 2026-10-03，当前状态更新至 2026-10-09。本表限定官方物理接入主线，不重新宣称渲染/MMD的历史验收状态。现有预览物理继续可用；**完整官方候选后端没有接入Unity，也没有动态通过验收**。因此不是只剩若干参数微调，无法给可靠的完工百分比或会话数量。

## 已有基础

原版本与参数证据、若干proxy/角度/骨骼输出数学、current/last发布、限定host调度、普通Read/Restore/Set字段规则已有离线参考。Animator读取主体的map分流与有限值参考已有；[EndSimulationStep步末有限值参考与Start受力片段](../official-physics-particle-step-20261003/README.md)后，又实现[Start姿态插值/已解析中心惯性消费/受力组合](../official-physics-start-step-20261003/README.md)，测试连续两步反馈。所有这些仍各有输入/分支前提；合成测试和代码覆盖率不能证明真实全链完成。

## 剩下三类工作、八个交付门禁

| 类别 | 必须完成的门禁 | 当前实际状态 |
| --- | --- | --- |
| 真实输入与生命周期 | 1. 11组proxy/Team/list/骨骼/碰撞体等完整原输入发布 | 164个saved点克隆已核查；完整proxy与Team发布未闭合 |
| 真实输入与生命周期 | 2. bulk init生成、分配/复用/释放、相对矩阵构造 | 单槽Set/Copy/Enable有参考；[Double TRS/full inverse数学](../official-physics-frame-anchor-20261009/README.md)已有有限值参考，但allocator、bulk构造及全部调用方接入未完成 |
| 真实输入与生命周期 | 3. 动画map/record、回写Job与唯一writer调度 | 动画读取有限值已实现；map生成、输出Job与cross+Animator委托链待补 |
| 动态求解 | 4. step积分、中心运动/惯性/风与各算子依赖 | 普通粒子Start→End、[子步中心](../official-physics-center-step-20261003/README.md)、[Team与风状态](../official-physics-team-tail-20261003/README.md)、[粒子风力](../official-physics-particle-wind-20261003/README.md)、[Spring](../official-physics-spring-20261003/README.md)、[帧移动归约](../official-physics-frame-motion-20261008/README.md)、[帧惯性](../official-physics-frame-inertia-20261009/README.md)、[瞬移/平滑](../official-physics-frame-prelude-20261009/README.md)、[锚点生产](../official-physics-frame-anchor-20261009/README.md)、[符号缩放映射/帧矩阵](../official-physics-scale-remap-20261009/README.md)、[fixed-point帧目标生产](../official-physics-frame-target-20261009/README.md)、[帧reset补全/权重/独立PostTeam历史推进](../official-physics-frame-history-20261009/README.md)、[frameLocalPosition/风区选择](../official-physics-wind-zones-20261009/README.md)、[粒子14缓冲reset/7历史变换](../official-physics-particle-reset-20261009/README.md)和[帧末显示预测/动画历史发布](../official-physics-display-20261009/README.md)已有离线参考。风区经swap-back替换后按原顺序接续子步时间与粒子风力；帧prelude保留旧历史，PostTeam在全部子步/回写后推进帧历史；显示链保持模拟、显示与动画proxy历史分离。真实WindData/proxy/Team输入发布、reset请求/暂停恢复及跨步依赖仍未闭合，不用舞台root或默认零值代替原输入 |
| 动态求解 | 5. 碰撞链、normalAxis下游及约束完整消费 | 尚未完成整个角色的原输入、迭代顺序与输出闭环 |
| 动态求解 | 6. reset、暂停恢复、跳帧及状态发布 | current/last复制与host顺序有参考；帧级component/frame/now/oldWorld reset、帧权重初始化、PostTeam历史/flags/clock/force片段、[粒子14缓冲reset/7历史负缩放与惯性变换](../official-physics-particle-reset-20261009/README.md)，以及[帧末显示位置、原动画proxy历史和负缩放rotation发布](../official-physics-display-20261009/README.md)已有有限值参考。暂停/seek请求产生reset标志、暂停恢复跨步、真实数组发布及定制完成机制仍待补；离线私有range结果不等于Unity已发布 |
| Unity交付 | 7. 可回退C#候选后端与角色实例接入 | 未开始替换当前舞台后端；不能将Python参考称为Unity已实现 |
| Unity交付 | 8. MMD/解包动作下的实际动态验收与可迁移接口 | 候选后端未具备，不能宣称已验收或可无误迁移其他角色 |

“三类”不是三次调用，“八门禁”不是八个小补丁。动态求解与真实输入仍有逆向工作，不能给“已经90%”或“再一两轮就完美”的保证。

## 推进优先级

2026-10-09接续审计纠正了fixed-point帧目标旋转的native ABI→Python API适配：旧代码/测试重复交换Y/Z，正符号identity fixture本应保持identity。修正实现、独立矩阵参照和旧说明；粒子reset与两子步组合采用修正后的目标。原字节SHA检查正确不等于旧语义结论正确。详情见粒子reset说明与frame-target纠错记录。

2026-10-09随后补齐CalcDisplayPosition的有限值参考：恢复realVelocity显示外推、未钳制clock比例、原1.3根半径、blendWeight、flag20原动画历史与flag20000负缩放rotation写回，并用reset→两次Start/End→显示→再reset组合测试确认三套历史没有串用。这仍不是原NativeArray/Job或Unity动态验收。

2026-10-09同批推进[约束调用链](../official-physics-constraint-chain-20261009/README.md)：Distance的work-list/稀疏chunk/packed邻居与顺序range消费、显式WorkData的mode1点碰撞，以及完整18段子步符号依赖已有参考。恢复碰撞前后两次Distance、Spring/普通碰撞velocity reference差异与摩擦→逆质量→End反馈，用Start→Distance→Collision→Distance→End→下一Start限定组合测试验证。其余算子没有暗中设为已实现no-op；SelfCollision四轮目前只有顺序描述，不是碰撞数学。ColliderManager生产、真实list/proxy/Team发布、wrapper空列表与实际调度仍未闭合。

后续集中推进第4–6项完整动力学主链，下一硬缺口是ColliderManager的帧前/子步/帧后WorkData生产、完整约束输入与依赖闭合；第1–3项只按该链需要补齐，不用增加无关工具或微型文档阶段。候选链形成后再进入第7–8项做可见效果与动作测试。若忠实原实现某分支仍无证据，明确保留待核查，不将调参近似或stock替代方案标成官方等价。

这轮没有新可见效果；当前效果保持。用户能看到的新物理必须以候选后端实际切换并运行过的结果为准，而不是测试数字。
