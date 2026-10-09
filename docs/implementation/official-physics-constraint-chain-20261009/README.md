# 约束调用链：距离范围、点碰撞消费与子步依赖计划

日期：2026-10-09。此批把此前的单粒子算子向调用链推进；**不是官方物理后端已经接入 Unity，也不是完整动态求解闭合**。本轮不修改角色舞台、渲染管线、动作播放器或现有预览物理。

## 交付与输入边界

- `Tools/official_physics_distance_pass.py`：显式输入数组上的 Distance 单槽与顺序 range 参考。消费 work-list、Team/proxy/粒子各自的 chunk、UInt32 packed adjacency 与 UInt16 team-local 邻居；复用已核查的有限值距离数学。
- `Tools/official_physics_point_collision.py`：显式已生产 WorkData 的 mode1 点碰撞参考；恢复 Sphere、六种 Capsule type 与 Plane 的实际 helper 消费。**没有**由 prefab 字段猜造 WorkData，也没有写入 Unity 骨骼。
- `Tools/official_physics_substep_plan.py`：一轮成功正常 host 路径的18段符号依赖计划，保留八个 Schedule2 分流；SelfCollision 只描述原 gate 与四轮调用顺序，不执行其碰撞数学。
- 三份专项测试和 `Tools/tests/test_official_physics_constraint_chain.py`：验证手算、精度、读取门禁、稀疏索引、顺序反馈，以及 Start → Distance → PointCollision → Distance → End → 下一次 Start 的**限定片段**。未运行的 Tether/Angle/Bending/Motion/SelfCollision 不被暗中当作已经实现的 no-op。

所有输入必须由调用方明确提供。有限值/范围/unsupported mode 或 shape 拒绝、私有外层快照与 immutable result 是 Python 适配契约，不是原程序异常、NaN 或分配器契约。Python sqrt/trig、顺序 range 和符号 handle 不能证明实际 Burst、Job 并发或位级一致。

## 官方版本锚点

仅静态读取现有原文件，没有加载/执行 GameAssembly、启动游戏或重新注入捕获。

- `GameAssembly.dll` SHA256：`c24495e51b406f03b03890c4788ee618ae022c991405be5d5b8b787cb775ae89`
- `global-metadata.dat` SHA256：`0076743397acadf03d3b0064343a963c7c88863b8160526d397e4b3efb96f02e`
- Distance managed method368841：`0x59eafdc..0x59ebab6`，2778 bytes / 628 instructions。Range368842：`0x59e6b64..0x59e6c76`，274 bytes。
- Distance 实际 DirectCall 非 Burst fallback：`0x59e6080..0x59e6b63`，2787 bytes / 628 instructions；由 Invoke 的实际 call site `0x59ecd09` 确定。明确归一化42个栈槽和三处 frame 差异后，只剩两个函数各自的初始化标志地址；这不是 live Burst 等价证明。
- Point managed method368740：RVA `0x59f47cc`；实际 Sphere/Capsule/Plane helper 分别为 `0x59f5774`、`0x59f4494`、`0x59f5670`，不是只看同名公开声明地址。
- SimulationStepUpdate method370401：RVA `0x32b2f70`；五段 CHAININFO family 合计9757 bytes。两个 SelfCollision wrapper 的静态调用结构也单独认证。

完整原 trace、商业资源和 DLL 不入公开库；私有 proof/read-only review 的路径与 SHA 在 `verification.json`，最终测试及保护检查同样留存。

## 距离调用规则

work ordinal → global particle → Int16 team ID。Team 的 particle/proxy/adjacency/data 起点分别处理；不能误把 step list 当局部粒子号。kernel 没有额外 team0 或 IsProcess 判断，因此适配器不擅自新增。

空 team adjacency 先跳过；invalid 为 `(attr & 3)==0`，fixed 为 `(attr & 2)==0`。普通 fixed center 跳过，Spring bit `0x2000` 的 fixed center 保留；fixed 邻居始终参加，不能按 center 规则过滤。fixed mass 为 Spring10、普通50。普通逆质量由 depth 与 friction 共同求出，不是统一质量。

packed word：高12位 count、低20位 adjacency start；邻居是 UInt16 team-local ordinal。严格 Double `length < Single(1e-8)` 才丢弃边，等于阈值仍贡献。零有效边不写 next/velocity，也不读取最终 velocity；零 stiffness 但有效边仍计数并写回。

保留调用方原顺序、重复 work slot、邻居编码顺序。每个已完成槽的 next/velocity 写回立即被后续槽读到，不能排序、去重或替成 Jacobi。实际 Job 的 worker partition 与 work-list/adjacency 生产未由这个 range 证明。

## 点碰撞规则

实际11组序列化配置均 `colliderCollision.mode=1`。原绑定为35个组内引用、25个唯一 collider，且各组只能使用原组引用。此信息不意味着25个 WorkData 的运行时生产已恢复；本模块只消费明确给定的 WorkData。

WorkData stride184：AABB@0、float2 radii@48、double3x2 oldPos@56、nextPos@104、inverseOldRot@152、rot@168；valid/enabled/shape 来自独立 Byte flag。Team flag 保留64位。

- 粒子 AABB 先 `position ± radius` 再 expand radius，是两次 Double 运算，不能改成单次 `± 2r`。
- managed AABB helper `0x59ea6b4` 第一方向 z 比较实际为 `maxB.z >= maxB.z`；因此有限输入不检查 `minA.z <= maxB.z`，反方向仍检查 `maxA.z >= minB.z`。保留该原代码异常，**不推广成 Burst 路径已证实也相同**。
- Sphere 取 old center 的径向与 next center 的表面；Capsule 在 old segment 投影，Double fraction 窄化 Single 后用 inverseOldRot → rot 变换，按 Single fraction 插值两端半径。
- 三种 helper 的表面计算与最终投影法线精度不同：表面用恢复出的 Double 法线；投影用 Double → Single → Double 输出法线，不能全部统一为 Double。
- 每个 collider 都读同一原 next position；穿透修正与 Single 法线分别累加后平均，不逐 collider 更新粒子。
- Sphere 的 Spring-only limit、0.85回拉和 signed distance×3 不得搬到 Capsule。Spring 有穿透时修正 next 与 velocity reference；普通碰撞不改变 velocity reference。
- near friction、collision normal 和位置写回按各自原条件；End 再消费 normal/friction。dynamic/static 参数不是这个 point kernel 自行调入的系数。

## 完整子步顺序：两次 Distance 都必要

```text
TeamStep → ClearStepCounter → ParticleList → ColliderList → ColliderStart
→ ParticleStart → UpdateStepBasicPoture
→ Tether → Distance → Angle → TriangleBending → ColliderCollision
→ Distance → Motion → RuntimeSelfCollision → SolveIntersect
→ ParticleEnd → ColliderEnd
```

Distance 的原调用 site 为 `0x32b4247` 与 `0x32b42fb`。第二次在碰撞后，无条件存在，不是可删除的“额外收敛优化”。wrapper 的16B返回 handle 是下一调用的依赖；符号仅表示原调用返回，不保证 native handle 唯一。

八个 inline Schedule2 的普通、跨帧与 worker-thread 同步路线分别描述。cross + animator + 当前线程不同于 main 时同步执行并返回空 handle；七项先 Complete，但 ClearStepCounter 的同步分支没有 Complete，保留原例外。这里假定一轮内 flags/thread IDs 稳定，不声称恢复全部 fault/class-init/icall 行为。

`updateCount` 在此方法不参与重复调用，`updateIndex` 给 Team/collider-list 与 SelfCollision；SimulationStepCount 只加一次。SelfCollision 的 point+edge+triangle 用 Int32 wrap 后 signed sum>0 才进入；index0用 BroadPhase，其余 UpdateBroadPhase；固定四轮 EdgeEdge → PointTriangle → Aggregate。IntersectCount 仅等于0跳过。**四项 counts 必须显式传入，没有默认零值替代未恢复输入。**

## 串联验收与下一步

组合测试使用显式合成 collider/chunk/center/wind。两次距离之间的碰撞 friction 影响第二次的逆质量；Spring/普通 velocity reference 写回不同；End 的 solver velocity 与 realVelocity 分离；下一 Start 依然窄化 center-relative oldPos，即使中心运动和旋转为 identity。测试期待值由轴向公式独立计算，不调用被测距离函数当 oracle。

验证统计见 `verification.json`。主工作区 HEAD/index 与7个运行文件保护保持，采用隔离 index 做选择性记录，不打包其他 agent 或用户的改动。

下一主线仍是把 ColliderManager 的帧前/子步/帧后 WorkData 生产、真实 proxy/Team/list 发布、其余约束 wrapper 输入与依赖接齐，再迁移到可回退 C# 候选后端。之后才进行实际 MMD/解包动作、碰撞、reset、暂停/seek和骨骼回写验收。**当前没有新的 Unity 可见物理效果，不能据本批测试宣称官方最终效果完成。**
