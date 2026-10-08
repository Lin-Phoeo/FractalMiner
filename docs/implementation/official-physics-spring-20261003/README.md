# 官方物理：固定粒子 Spring

2026-10-03，接续[粒子 Wind/WindForceBlend](../official-physics-particle-wind-20261003/README.md)。本阶段新增 `Tools/official_physics_spring.py`，静态恢复 `StartSimulationStepJobKernels.Spring` 的有限数值路径，并把它接回 [StartStep](../official-physics-start-step-20261003/README.md) 中 `Team flag 0x2000 && IsFixed bit1` 的源位置：先完成惯性与受力，再以动画 base 作为 Spring 基准回拉。

**这是离线有限值参考，不是 Unity 已接入的官方后端，也没有产生新的可见物理效果。** 它不选择粒子、不生成参数、不管理 NativeArray、不调度 Job、不处理碰撞/reset，也不写 Transform。调用者必须提供已经解析好的 Spring 参数、法向轴、noiseTime、base pose 与 Team scaleRatio。

## 固定来源与调用链

只静态读取本地固定版本文件，不执行、加载、注入或附加游戏 DLL/进程。GameAssembly SHA 为 `c24495e51b406f03b03890c4788ee618ae022c991405be5d5b8b787cb775ae89`，metadata SHA 为 `0076743397acadf03d3b0064343a963c7c88863b8160526d397e4b3efb96f02e`。

- 公共包装器 Spring：method370470，RVA `0x5a649e0`，151字节；它调用 Spring DirectCall.Invoke method370507 / `0x5a7456c`。
- Burst managed body：method370475，RVA `0x5a644dc`，1282字节，SHA `7632dc117d33b61d5226eab071fbf1eda9e7f0b513e055c968de12c09e446c07`。
- DirectCall 的非 Burst fallback：RVA `0x5a69c6c`，1282字节，SHA `47a4db3022aa72cab4d32cea34cbdfd0b736453c9d71a0d3e0d5d305e5dc6997`。
- 两个1282字节 body 各294条指令；规范化地址后，指令、相对分支、外部调用和 RIP 目标全部一致。唯一差异是两个独立方法在零填充虚拟区中的初始化 guard 地址。动态 Burst 函数指针的实际运行体仍未认证，不能把静态等价写成运行时 oracle。
- Spring 的元数据签名依次是 `SpringConstraintParams&`、`ClothNormalAxis`、`double3& nextPos`、`in double3 basePos`、`in quaternion baseRot`、`double noiseTime`、`double scaleRatio`。noiseTime 与 scaleRatio **不是 Single**。
- `SpringConstraintParams` 四个 Single 字段的 unboxed 偏移依次为 springPower@0、limitDistance@4、normalLimitRatio@8、springNoise@12。
- `ClothNormalAxis` 的官方枚举和值为 Right=0、Up=1、Forward=2、InverseRight=3、InverseUp=4、InverseForward=5；公开 Python 枚举保留这些原名和序号。

完整指令、元数据布局、参数类型和等价性复核脚本只保存在 `D:/EndfieldTechLib/notes/official-physics-spring-20261003-01/`。公开仓库只放自己的有限值参考、测试、摘要与 SHA，不发布完整原生报告、游戏资产或第三方源码。

## 不能改写的数值顺序

1. 先以 Double 计算 `delta = nextPos - basePos`。按六值枚举选择单位轴，再用 baseRot 旋转为世界法向；四元数通道来自源端 Single quaternion。
2. `limit = Double(Single(limitDistance)) * Double(scaleRatio)`。limit≤0 时源分支直接选择零 delta，最终位置因此回到 base；不能把非正 limit 解释成“不限距离”。
3. limit>0 时先做球形限制：若 `length(delta)>limit`，按 `limit/length` 缩放 delta。
4. 仅 normalLimitRatio<1 时执行法向椭圆限制。先求 `normalComponent=dot(normal,delta)` 与切向长度，再按 `cos(asin(tangentLength/limit))*normalLimitRatio*limit` 得到允许法向长度。超界时只沿旋转后的法向减去超量，并保留源 sign 规则；不能改成逐轴 clamp 或圆柱限制。
5. springNoise>0 时才计算噪声：先以 Single 得到 `amplitude=Single(springNoise*Single(0.6))`，再以 Double noiseTime 求 `springPower + sin(noiseTime)*amplitude*springPower`。该分支中结果≤0才归零；**没有噪声时负 springPower 保留**，不能全局 clamp。
6. 末尾严格执行两次向量操作：`delta = delta - delta*power`，随后 `next = base + delta`。不能代数化为 `delta*(1-power)`，否则大/小数值下的舍入顺序改变。

sqrt/asin/cos/sin 的调用路径已静态定位；其中调用目标 `0x1b39a0` 进入 asin 路径，exact-bounded 实现记录从 `0x1b39c0` 起。Python `math` 只作为有限数学参考，不声称与 CRT/Burst 超越函数逐位一致。适配层的 finite、真实枚举实例、四元数长度和类型拒绝也不是官方异常契约。

## StartStep 接入边界

`ResolvedStartSpring` 只承载参数、normalAxis 与 noiseTime。`start_particle_step(...)` 的固定 Spring 分支仅在 Team flag0x2000 且 attribute bit1 同时成立时读取它；attribute3同样进入。普通固定粒子、仅spring Team但没有fixed位的粒子不会读取 Spring 输入。

进入该分支前，Start 已完成动画 base/baseRotation 写入以及移动/Team 路径的惯性和 force integration；Spring 消费该 nextPosition，却以**单独保存的动画 base/baseRotation**为约束基准。测试专门用不同的模拟位置与动画 base 证明调用顺序，避免把 moved position 误当 base。该接入仍只返回逻辑结果，不执行原生数组写入或部分写故障语义。

## 验证和剩余边界

89项 Spring+Start 目标测试通过，其中六个官方normalAxis枚举方向逐一验收。全套 **2385 passed /114 subtests /3历史skip /2历史Pillow warnings**；29个 `official_physics*` 参考模块共2509 statements/600 branches，分支覆盖100%；Spring模块62 statements/16 branches为100%。Ruff check/format、Pyright和compile通过。这里的测试是合成有限值与静态证据门禁，不是官方 DLL 运行、真实11组角色动态验收或 Unity 完成率。

Spring 这一局部不再是第4门禁的未移植项；但上游帧级中心/anchor/world惯性、风区选择，以及下游完整碰撞/约束/reset/发布仍未闭合。下一步应继续真实动力学依赖，形成可回退 C# 候选后端后再进入 Unity、MMD与解包动作下的动态验收；不能只把本模块导入就宣称官方物理已完成。
