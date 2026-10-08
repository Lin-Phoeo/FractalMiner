# 官方物理：子步重力、权重与风状态

2026-10-03，接续[子步中心与局部惯性](../official-physics-center-step-20261003/README.md)。新增 `Tools/official_physics_team_tail.py`：子步中心生成后，计算Team缩放、重力dot/ratio、重置后速度权重、blendWeight，并推进已有风区与移动风的状态。连续两子步中，这些生成的缩放/重力/权重已实际送入Start→End有限值参考，不再由测试手填它们。

**仍是离线参考，没有替换Unity后端，没有新可见效果。** 风状态更新不等于粒子风力求值：上游风区选择、帧级中心/anchor/world惯性、碰撞/reset与实际发布仍未闭合。粒子WindForceBlend与固定Spring由下一段所列后续阶段补齐，但不改变本模块本身只更新Team状态的边界。当前舞台、渲染、湿身、自阴影、MMD和预览物理未改动。

同日后续：[粒子Wind/WindForceBlend、噪声与湍流](../official-physics-particle-wind-20261003/README.md)现已有独立离线参考并接入两子步合成测试；[固定粒子Spring](../official-physics-spring-20261003/README.md)也已接入Start的源调用位置。本页上述范围与verification保留本阶段历史状态；Team tail本身仍不逐粒子求力或Spring、不执行数组发布，不能仅因新模块存在就清除其pending依赖。

## 证据与范围

仅静态读取本地GameAssembly/metadata，不执行、加载、注入DLL。二者SHA分别为 `c24495e51b406f03b03890c4788ee618ae022c991405be5d5b8b787cb775ae89`、`0076743397acadf03d3b0064343a963c7c88863b8160526d397e4b3efb96f02e`。

- 子步主kernel method369542 /RVA0x5a39fa0 /3548字节：本轮移植中心片段后的 `0x5a3a7d8..0x5a3aa30` 数值tail，随后真实Team/Center数组发布未移植。
- UpdateWind$BurstManaged method369544 /0x5a3af10 /798字节。另审读实际DirectCall的非Burst fallback `0x5a2d8a8` /798字节：两处状态算法一致；动态函数指针执行体没有认证。不能只根据方法名把managed标签误当实际运行证明。
- UpdateWindTime method369541 /0x5a3aeac 是包装器；DirectCall.Invoke method369585 /0x5a3b898 的非Burst路径调用managed method369545 /0x5a2d84c。后者无exact unwind，使用固定89字节、完整操作数、全部内部跳转与RET路径证明，**不猜整个函数边界**。
- ZoneCount method370708 /0x5a77ad0 /51字节读取UInt16列表计数。适配器接受调用方解析好的活动列表，不自行生成区域成员、模拟FixedList存储或分配容量。
- float3 dot `0x4a4bd00` 固定37字节，向量负号 `0x39d3f50` 固定49字节，clamp `0x2cd23e0` 固定40字节另做完整入口路径证明。sqrt与quaternion-vector rotation沿用前阶段已审读的参考。Python sqrt不承诺CRT/Burst逐位一致。

私有完整指令/字段布局/复核脚本位于 `D:/EndfieldTechLib/notes/official-physics-team-tail-20261003-01/`；公开摘要与SHA见本目录 `verification.json`。完整原生报告、游戏文件/资产与第三方源不发布。

## 不能改写的公式

Single运算顺序逐项保留；下面的括号表示实际舍入边界，不使用代数化简或任意补偿。

1. `scaleRatio = max(Single(1e-6), Single(Single(sqrt(dot(scale,scale))) / Single(sqrt(dot(initScale,initScale)))))`。输入scale是上一模块生成的**子步插值scale临时量**，不是只取某一轴。适配器拒绝退化initScale，不给源增加容错clamp。
2. 若worldGravityDirection的Single平方长度>Single(1e-8)，只将initLocalGravityDirection的**Y**乘negativeScaleDirection.y，再按新的nowWorldRotation旋转。`gravityDot=clamp01(Single(Single(dot(rotated,worldGravityDirection)*.5)+.5))`。不额外归一化方向，不把X/Z也镜像。否则gravityDot=1，局部重力输入不读取。
3. gravity>Single(1e-6)且gravityFalloff>Single(1e-6)时，`fall=clamp01(Single(1−gravityFalloff))`，`gravityRatio=Single(Single(clamp01(Single(1−gravityDot))*Single(1−fall))+fall)`；否则ratio=1。
4. velocityWeight<1时，以dt/stablizationTimeAfterReset增加；该时间≤Single(1e-6)则增加1，再clamp01。已≥1时不修改，也不读取该时间。不是每次从零重置权重。
5. `blendWeight=clamp01(Single(Single(parameter.blendWeight*velocityWeight)*distanceWeight))`。**不是**clothSimulateWeight×clothLodFadeWeight。子步tail没有在此更新LOD fade；上一中心阶段pending名称带fades只是未完成tail标签，不构成fade算法证据。
6. WindParams.influence≤Single(1e-8)时，保持整个旧TeamWindData，**不清风区或移动风**。启用时对活动列表按原顺序逐个推进time，不额外按windId/零main过滤。
7. `rate=Single(Single(Single(Single(main/7.5)*.5)+Single(.2))*frequency)`；随后**min(rate,1.5)**，再 `time=Single(oldTime+Single(rate*dt))`。1.5是上限，不是最低速率；frequency/main不擅自加非负限制。
8. 更新time后，若time>10000，**减20000一次**。相等时不减，不对过大输入重复循环，不修复负time，不改成取模。
9. 启用风后移动风main先置零。movingWind>Single(.01)时，`main=Single(Single(frameMovingSpeed*movingWind)/scaleRatio)`，direction取frameMovingDirection逐通道负号，保持旧ID并用上述算法推进time。否则只清main，旧ID/time/direction保留。这里消费**帧级speed/direction**，不能用stepVector/dt猜值。

## 字段与接口

| 结构 | unboxed字段偏移 |
| --- | --- |
| TeamData，stride464 | initScale@84、scaleRatio@96、negativeScaleDirection@104、velocityWeight@252、distanceWeight@256、blendWeight@260、gravityRatio@64、gravityDot@68 |
| ClothParameters，stride808 | gravity@0、worldGravityDirection@4、gravityFalloff@16、stablizationTimeAfterReset@20、blendWeight@24、wind@764 |
| WindParams | influence@0、frequency@4、turbulence@8、blend@12、synchronization@16、depthWeight@20、movingWind@24；本轮状态算法只解释实际读取的influence/frequency/movingWind |
| CenterData，stride696 | frameMovingSpeed@232、frameMovingDirection@236、initLocalGravityDirection@544 |
| TeamWindData，stride152 | windZoneList@0、movingWind@128 |
| TeamWindInfo，stride24 | windId@0、time@4、main@8、direction@12 |

`complete_team_step(...)`消费前一模块的CenterStepResult；无active center时不读取tail输入。返回TeamDynamicsState与TeamWindState，不改原输入，不执行NativeArray操作。调用者必须传入与前一中心函数相同的source dt。

本函数active返回的 `pending_tail=(native_publication,)` 仅表示**本Team子步数值片段**补完了重力/权重/风状态；不是整个physics完成。另有 `pending_pipeline` 明确保留frame_center_and_zone_selection、particle_wind_force、constraints_reset_and_publication。前一模块历史返回值仍不可变，没有偷偷清它的pending信息。

finite、正dt、非零initScale/移动风scale的拒绝是适配保护，不是官方异常契约。未读取的输入不强制求值。风信息复制保留源ID/方向，不凭空加IsValid筛选。

## 测试与实际进度

按测试驱动流程，先新增测试观察缺失模块RED，再实现。58项新增测试覆盖缩放长度/floor、重力方向/镜像/旋转/退化输入、falloff分支、权重累计、blend公式、风门禁、零main/负ID列表推进、风速上限、正负time边界与一次减法、移动风清理/帧输入、非法适配输入，以及两子步中心→Team tail→Start→End反馈。

全套 **2290 passed /114 subtests /3历史skip /2历史Pillow warnings**。26个参考模块2272statements/556branches，含分支覆盖100%；新模块112statements/16branches 100%。Ruff/format、Pyright与Python compile通过。这些是合成数值测试，不是官方DLL运行、真实11组动态验收或Unity完成率。

后续[粒子风力](../official-physics-particle-wind-20261003/README.md)、[固定Spring](../official-physics-spring-20261003/README.md)与[帧移动速度/方向归约](../official-physics-frame-motion-20261008/README.md)均已形成独立离线参考；当前仍需补帧级anchor/component/world pose、归约前位移生成、风区选择，以及完整碰撞/reset/发布。形成可回退C#候选后才进入MMD/解包动作动态验收。总缺口见[八个交付门禁](../official-physics-animator-buffer-20261003/PROGRESS.md)。
