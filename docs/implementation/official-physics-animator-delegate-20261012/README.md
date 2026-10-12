# 官方物理：跨帧 Animator 宿主与委托顺序

日期：2026-10-12。接续[绑定重建](../official-physics-animator-lifecycle-20261012/README.md)和[已确定的委托入口](../official-physics-animator-lifecycle-20261012/NEXT.md)，扩展 `Tools/official_physics_scheduling.py`，恢复稳定、成功、无 mesh-mapping 路径的两阶段有限调用计划。它们描述源顺序和返回依赖；没有执行 native job、GCHandle、求解器或 Unity 角色物理。

## 宿主阶段

`plan_cloth_update(FrameMode(True, True), ...)` 现在返回跨帧 Animator 计划，不再将此分支整体拒绝。

在已有 Playing/enable 门禁和旧 master 完成之后，依次 AlwaysWindUpdate、WorkBufferUpdate、清 master、VirtualMesh.UpdateBuffer、ReadAnimatorBufferData、六次 GCHandle.Alloc、Schedule<DoAllInOneJob>、CameraCullingPreProcess、可选 OnPostSimulation，随后返回。DoAllInOneJob 依赖读取任务返回值，其调度返回值成为宿主 master。

此时宿主不运行 SimulationStep、CopyDoubleBuffer、普通 WriteTransform，也不完成刚调度的委托任务。mappingCount 属于后面的 Execute 读取点；宿主不能提前消费它。宿主曾读到的 maxUpdateCount 没有作为数值捕获进六字段 Job，不能用它冻结稍后的 Execute 步数。

## 委托阶段

新增 `plan_animator_delegate(max_update_count=..., mapping_count=...)`，输入对应 `DoAllInOneJob.Execute` 内两个读取点：maxUpdateCount 在 pre-simulation 后，mappingCount 在 PostProxyMeshUpdate 后。两值必须显式提供；缺 mapping 观测不能用默认0代替。这里的数值由调用者观测，不从宿主快照或 deltaTime 猜测。

正常无 mapping 顺序如下：

1. GetTarget 按 bm/tm/vm/sm/wm 顺序进行。wm 的返回对象在此主体中未被消费，也不能省略这次读取。
2. 新建局部 default 依赖，再依次 ValidPosition、PreProxyMeshUpdate、CalcCenterAndInertiaAndWind、PreSimulationUpdate、Collider.PreSimulationUpdate。
3. signed maxUpdateCount 大于零时以 index=0..count−1 进入 SimulationStepUpdate，逐次将返回值作为下一调用的依赖；零或负数跳过循环，仍继续尾部。
4. CalcDisplayPosition、PostProxyMeshUpdate、WriteAnimatorBufferData、Collider.PostSimulationUpdate、PostTeamUpdate。

mappingCount≤0 的跳转绕过第六个 GetTarget 与全部 mesh/render 分支；mappingCount>0 明确拒绝未实现路径。最后一次返回依赖只作为 `last_call_handle` 诊断标签保存：Execute 的返回类型经 metadata 确认为 **void**，没有将它写到宿主 master，也没有证明该标签对应实际存活的 native job。

两阶段计划与帧后 `plan_after_update` 保持分开：帧后才完成宿主 master、清零并 UpdateTeamAnimatorData。不能把串联的合成 fixture 当成异步执行证明。

## 独立静态验证与测试

独立脚本重读 DLL / metadata，不导入调度端口。Execute 的完整 unwind family 为 1662 字节，SHA-256 `86825b...3b0b`；ClothUpdate 完整 family 为 4388 字节，SHA-256 `4bcc1e...ea63`。验证 41 个委托指令点、16 个宿主指令点及四个 method table 身份；实际 Alloc、GetTarget、UpdateBuffer、CameraCullingPreProcess 的名称由当前 native 方法表确认。源版本哈希与之前封存版本相同。

TDD 缺新接口 RED 及缺mapping观测误用默认0的RED已观测；原宿主“明确拒绝 Animator”测试改为真实 deferred 分支断言。新增23项委托测试和一个额外宿主门禁用例；调度专项共91项通过，模块157 statements / 52 branches，分支计入覆盖率100%。全套最终数字见verification；三项历史skip及两项既有Pillow告警保留。类型、格式、静态检查和依赖审计通过，7项runtime文件与主index/HEAD保护通过。

本轮未请求独立代理审查；由主代理逐指令复核和独立原字节 verifier 支撑。完整数字和哈希见[verification.json](verification.json)，私有证据在 `D:/EndfieldTechLib/notes/official-physics-animator-delegate-20261012-01/`，最终 verifier 输出为 `source-verification-02.json`。

## 尚需完成

- 实际 Schedule/Schedule2 与 worker 同步分支、定制完成机制和 GCHandle 释放/失效生命周期；本计划没有擅自添加 Free 或 Complete。
- record→读取 capture 接口、原 native 单位尺度 TRS 和 relative 输入，以及真实11组 map/record 与数组发布。
- 三段绑定/读取/写入接线、可回退 C# 候选后端与连续角色动作测试。

因此本轮闭合的是**当前限定路径的宿主/委托顺序与依赖表达**。正式调度与 Unity 动态仍未通过，本轮没有新的可见物理效果。
