# 固定点帧中心目标：有限值参考

2026-10-09。实现为 `Tools/official_physics_frame_target.py`，对应当前版本帧核369644的 `5a35365..5a357a1`。补齐上一轮组件符号映射与帧矩阵之间的位置、朝向目标生产。依据为校验SHA后的原DLL与metadata静态读取；不加载或执行游戏代码。

**已实现的是Python有限值参考，不是Unity后端或整帧动态验收。** 原固定点列表/全局proxy数组仍需真实发布；本模块消费这些原输入，不推测舞台root或凭当前FBX姿态重建它们。当前Unity舞台和现有物理未改动。

## 已核对的流程

| 阶段 | 原规则 |
| --- | --- |
| 组件种子 | 先取当前组件Double位置、原Single旋转、Single缩放；count≤0保留这些值，不默认identity、不归一化组件旋转 |
| 索引 | 按fixedDataChunk.startIndex递增读原UInt16列表，每项加proxyCommonChunk.startIndex得到全局slot；不排序、不去重、不按Int16读取 |
| 位置 | 顺序Double累加proxy positions，每轴以Double除原count。不是Single均值，也不是补偿求和 |
| 每点负缩放 | negativeScaleSign<0时，取点旋转后的+Y、+Z，分别取负，经39d4200重建。不是根据行列式判断，也不先归一化原点四元数 |
| 组合姿态 | 修正后的点四元数 **左乘** vertexBindPoseRotations[slot]；不反过来、不再inverse/conjugate |
| 朝向归约 | 分别按原顺序Single累加组合姿态的+Y、+Z轴；不是平均四元数 |
| 归约后符号 | Y和乘-1 iff direction.x<0 OR direction.z<0；Z和乘-1 iff direction.x<0 OR direction.y<0；不是轴符号相乘/奇偶判断 |
| 最终姿态 | 两条和分别按Single dot(y²+x²+z²)→sqrt→reciprocal→乘法归一化，first=Y、second=Z交给39d4200；包装函数交换为内部ABI的forward=Z、up=Y。Python接口是up/forward顺序，调用应为 `rotation_from_normal_tangent(Y,Z)` |

**2026-10-09接续纠错：初版把内部native ABI参数当成Python接口参数，结论与测试均错误。** 39d4250的第一ABI参数是forward，第二是up；现有Python函数则第一是normal/up，第二是tangent/forward。原包装函数39d4200交换的是ABI参数，不是中心的Y/Z轴。合成identity点+identity bind在正符号下必须产生identity中心旋转；初版“不能按直觉修正”的说法撤回。负缩放重建应调用 `rotation_from_normal_tangent(-Y,-Z)`，不是反过来。此次从cross输入、三列矩阵及上游调用重新双路核查，详见[粒子重置与参数纠错](../official-physics-particle-reset-20261009/README.md)。

5a2bd98/39d4430/39d4490均使用已有 `rotate_single` 的逐运算Single舍入。39d4200应由已有 `rotation_from_normal_tangent(first, second)`复用，保留cross/matrix-quaternion/sign-bit次序。既有数学实现没有改动，helper docstring已明确API与native ABI的顺序区别。最终normalize复用Single归一化尺度；不能换成Double `_normalized` 或LookRotationSafe。

## 接续与状态边界

`produce_frame_target(ComponentFrameSample, FrameTargetTeam, FrameTargetBuffers)`返回位置/旋转/缩放，以及仅用于审计的全局slot序列。

`resolve_frame_target(step, result)`只把目标交给后续离线片段，保持oldFrame/now历史不变；不是实际NativeArray发布。原流程在 `5a36214..5a36250`写局部CenterData的frame字段，稍后才有数组复制。适配器提前把局部目标表示为step字段，仅为了其他参考模块消费；不能误称原来的发布/调度生命周期已完成。

正确链路为：组件符号映射 → **本模块目标生产** → 帧inverse/负缩放矩阵（消费未重置oldFrame）→ anchor → teleport/smoothing/reset片段 → 帧惯性 → 帧运动/子步中心 → Start/End。接续测试实际调用目标生产，不再用手填frame目标替代该阶段。

Team字段未装箱偏移：fixedDataChunk@364（start0/count4）、proxyCommonChunk@292、negativeScaleSign@100、direction@104；Center frame字段@248/272/288。符号缓存应来自同一帧前置scale阶段。

## 验证与限制

47项新测试覆盖fallback、UInt16最大值、切片/全局偏移、重复与未使用slot、Double大世界/累加顺序、Single朝向抵消次序、非单位旋转、非交换乘法、负缩放两阶段、历史不提前重置和scale→target→matrix→anchor→prelude组合。另有独立NumPy旋转矩阵数学对照，不等同原生Single逐位oracle。

边界/平行数组/有限值/退化拒绝是适配器政策。原unsafe normalize没有零长度fallback；真实原输入若轴和为零或平行，原计算可传播NaN/Inf，不能悄悄用组件朝向补救。没有观测原运行时MXCSR/FTZ/DAZ，Python数学不宣称原生逐位相等。

静态证明脚本、原输入/舞台保护与历史回归见 `verification.json`及其本地报告路径；其中初版报告与旧文件SHA仅为纠错前的历史快照，不是当前源码验收。初版源字节检查正确不等于语义解释正确。当前测试已撤销错误的轴交换预期，随机矩阵参照的负缩放与最终basis也已纠正；最新全套结果与新文件SHA见粒子重置阶段的verification。两路只读审查不替代真实动作测试。

下一主线继续补完整reset/帧末component与anchor历史发布、wind-zone选择及真实跨步依赖，再形成可切换的C#候选后端。全部缺口仍见 [PROGRESS](../official-physics-animator-buffer-20261003/PROGRESS.md)；不以测试数量宣称物理完成或估算百分比。
