# 官方物理：世界与局部骨骼缓冲回写

日期：2026-10-02。接续[保存选择与代理属性](../official-physics-saved-selection-20261002/README.md)。新增 `Tools/official_physics_writeback.py`，恢复两个已定位的世界/局部骨骼**缓冲计算内核**的有限输入参考。不是直接写Unity Transform，不是完整实时物理后端；现有舞台、渲染、湿身与预览物理均未更换。

## 已恢复的计算

`BoneWritebackTeam`显式提供原始common/transform/bone chunk起点、common顶点数量与negativeScaleQuaternionValue。必须使用原Job列表顺序、真实Team和同序缓冲，不能根据骨名补索引。

| 步骤 | 原规则 |
| --- | --- |
| 代理相对索引 | `relative = vertex - proxyCommonChunk.start` |
| transform目标 | `proxyTransformChunk.start + relative` |
| 世界旋转偏移 | `vertexToTransformRotations[proxyBoneChunk.start + relative]` |
| 世界位置 | 原Double3直接复制，不先窄化Single |
| 世界旋转 | `proxyWorldQ * (offsetQ componentwise negativeScaleQuaternionValue)` |
| 局部父索引 | 原proxy父索引是Team-relative；`parentTransform = transform.start + parent` |
| 局部位置 | Double世界差值，经原父四元数inverse旋转，除以提供的父transformScaleArray；最后一次窄化Single |
| 局部旋转 | `(inverseParentQ * childWorldQ) componentwise negativeScaleQuaternionValue` |

`write_world_bone_pose`仅按非零team进入此内核，没有再添加Fixed/Move或transform flag门禁。调用者仍须提供上游已经筛过的原列表。零team与未选输出保持原值。

`write_local_bone_pose`仅写非零team、parent>=0、Move位2启用的顶点。Fixed/Invalid/无父项保持；attribute=3仍满足Move。世界缓冲在整个局部计算中只读，不用刚写出的局部值计算后续骨骼。

父旋转inverse保留原非单位四元数的平方范数倒数，不替换成单位共轭、不强制normalize。父scale来自明确提供的transformScaleArray，不猜成localScale、lossyScale、initScale或scaleRatio，也不取绝对值。四元数sign是逐分量Single乘法，世界路径在乘积之前、局部路径在乘积之后应用，不能互换。

Double旋转helper为 `t = 2 * cross(q.xyz, v)`，输出 `(v + q.w*t) + cross(q.xyz,t)`。q先保持Single再提升为Double，向量运算全为Double，保持原分组，不使用先Single旋转再提升的捷径。测试包含`2**40 + 0.125`差值，防止大坐标下细微位移丢失。

有限、范围、并行数组、零scale、重复Job及别名写入拒绝属于adapter安全政策，不是原异常行为。当前adapter限定最多65536槽、非负Int16 team、有限数值及明确的一对一bone偏移；拒绝active零scale，不加未经证实的epsilon。唯一writer检查也不能证明原调度已无竞争。

## 原始证据与尚未闭合的链

只静态读取封存DLL/metadata，未启动、执行、注入或附加游戏。源与私有报告SHA见[verification.json](verification.json)，完整指令/资产/第三方库不发布。

| 对象 | method / RVA | 范围 |
| --- | --- | --- |
| WriteTransformDataKernel$BurstManaged | 369808 / 0x5a42b30 | 814字节，世界缓冲内核 |
| WriteTransformLocalDataKernel$BurstManaged | 369832 / 0x5a56ba0 | 942字节，局部缓冲内核 |
| Double旋转helper | 0x59d732c | 450字节及其Double算术helpers；原2.0常量已核查 |
| AutoToFloat3 | 371131 / 0x4a47950 | 无unwind的44字节叶函数，限定直线mov/cvtpd2ps至RET |
| GetClothParameters | 368630 / 0x34e05e0 | 625字节family：主段617+另8字节spring分支 |
| SyncParameters | 368597 / 0x34df500 | 305字节，全体0x328参数结构复制 |
| CalcLineNormalTangentKernel$BurstManaged | 369784 / 0x5a4452c | 2206字节已检查，未整体移植 |
| DynamicBoneTransformManager.WriteTransformJob.Execute | 369494 / 0x5a277d4 | 2173字节已检查，实际Unity setter链未整体恢复 |

TeamData原boxed→unboxed偏移：proxyTransformChunk 300→284、proxyCommonChunk 308→292、proxyBoneChunk 348→332、negativeScaleQuaternionValue 152→136；三个起点不能混用。源世界位置数组stride24，旋转stride16，scale stride12。

本轮方向轴只闭合了**参数传递**：ClothNormalAxis枚举Right/Up/Forward及inverse为0..5，11组序列化配置为Up=1、alignment=None=0；GetClothParameters从serialize @0x90读取normalAxis，原样复制至参数unboxed @0x9c，SyncParameters再复制参数整体。**没有闭合normalAxis全部消费，也没有证明其全局未使用。**不据此增加猜测的预旋转。

实际Unity setter还会读取last position/rotation/local buffers，并涉及TransformAccess有效性、flag0x10、culling/spring分支、blend、world/local分支及relative/sync转换。它不是`Transform.position = 本模块输出`。双缓冲发布、全部helper与列表构造尚未接齐；不能把此次缓冲公式恢复说成唯一Unity写入链完成。

## 验证与保存状态

TDD：先新增测试、观察缺模块RED，再实现；新增46项通过。覆盖Double保留/最终Single、三个chunk偏移、父relative索引、非单位四元数、sign顺序、负scale、Move优先、跳过保持和非法输入。frame offset→世界缓冲→局部缓冲的组合是**合成fixture**，不是11组真实proxy或游戏轨迹。

独立算术参照使用未修改的本地Unity.Mathematics.dll，经单独C#程序调用原math.cross/inverse/mul，与Python参考比原始float/double位。1501组输入、31521分量、0 mismatch；禁用HW intrinsic/FMA，未调用游戏DLL。这证明测试范围内的运算组合相符，**不是原生游戏/Burst运行、Team发布或物理轨迹oracle**。

全套：1672 passed /114 subtests /3历史skip /2历史Pillow告警；16参考模块1262语句/326分支，branch-inclusive覆盖100%。Ruff/format通过，Pyright 0 errors/0 warnings，临时工具pip-audit无已知漏洞。覆盖率不是项目完成百分比或官方行为证明。

主HEAD与用户原index保持，七项runtime文件保护通过；没有重跑Unity，也没有新舞台效果验收。实际11组/164保存点有限Single克隆复核仍通过，不施加未知字典覆盖或假造proxy。私有证据位于`D:/EndfieldTechLib/notes/official-physics-axis-flow-20261002-01/`：静态review-12、oracle/oracle-01.json、coverage-full-01.json。

## 接续顺序

1. 接齐实际世界快照、构建分支、normalAxis消费及11组完整proxy输入；不要用合成fixture替代。
2. 恢复Team/chunk与原Job列表发布、step/剩余求解、碰撞、惯性/reset，明确数据生命周期。
3. 接齐last双缓冲与实际Transform setter的blend/culling/relative链，再验证动画与物理唯一写入时序。
4. 满足上述条件后才引入可切换的Unity官方来源后端，保留现有预览模式并做运行回归。

本轮减少了回写算术的不确定性；完整官方物理仍未完成。接续时应优先闭合真实输入与运行链，不通过任意修改舞台参数制造“官方已还原”的结论。
