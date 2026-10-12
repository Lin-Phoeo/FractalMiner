# Animator读/委托/写：独立调度路线与回调适配

日期：2026-10-12，承接记录提交 `329e0d0`。本轮恢复三个具体helper的有限成功路线，并提供调用显式后端回调的Python适配层。**未供应真实Unity调度后端，未运行原生Job，未闭合GCHandle生命周期，也没有改动当前舞台效果。**

## 新确认的读端身份

原读manager `0x5a1c92c` 在 `0x5a1cb94` 调 wrapper `0x3b5e68`。wrapper `0x3b5ef7` 的RIP-relative MethodInfo初始化格为 `0x18db91698`，原值 `0xc00fb88f`：kind6、MethodSpec515143；native metadata registration中的原记录为 `(method360316, classInst=-1, methodInst=28907)`。泛型参数为 `ReadAnimatorBufferDataJob`，typeIndex162243。

wrapper在 `0x3b5f03` 调 `0x6985208`，由generic method table/pointer slot486189确定为 `UnityEngine.Jobs.IJobParallelForTransformExtensions.ScheduleCrossFrameReadOnly<ReadAnimatorBufferDataJob>`，method360316。其181字节完整body在 `0x6985293` 调 `JobsUtility.ScheduleJobCrossFrameJobTransformReadOnly`（method355219 / `0xa3268c0`）。这关闭原先“读wrapper身份未解析”的子项；**不是写端Schedule2，也不能擅自改成stock Unity普通Transform ScheduleReadOnly**。

## 已实现的接口

生产文件 `Tools/official_physics_animator_dispatch.py`：

| 接口与源入口 | 已恢复成功路线 |
| --- | --- |
| `dispatch_animator_read` / manager `0x5a1c92c` | signed count≤0原样返回incoming dependency；count>0调用专用cross-frame read-only回调，传job、TransformAccess输入与dependency。源路线没有FrameMode/线程门控 |
| `dispatch_animator_delegate` / Schedule `0x5a18270` | 非cross调用ordinary；cross比较current/main signed thread ID，相等调用cross schedule，不等直接Execute后返回16字节零handle。此helper不检查Animator开关 |
| `dispatch_animator_write` / Schedule2 `0x5a1806c` | 非cross调用ordinary；cross但非Animator仍调用cross schedule且不查线程；cross+Animator main调用cross schedule，worker直接Execute后返回零handle |

调度分支传递并返回后端的实际**输入capture值**，不以planner字符串或incoming dependency替代回调返回。直接Execute没有隐藏Complete调用，忽略Execute回调返回值；异常传播，不返回假成功零handle。线程观察和回调仅在选中路线要求存在；普通路线不读取unused thread输入。

16字节不可变bytes只是有限handle capture，没有推断其中字段、liveness、实际完成或native身份。输入/返回验证、Python异常、稳定FrameMode与不变观察值是适配器策略，不声称native故障顺序、并发/race等价。native Job struct按值拷贝、reflection data、TransformAccessArray有效性、allocator/GCHandle/native JobHandle副作用由未接入的后端负责；当前直接把job对象传给回调并不模拟原生拷贝。

尤其不能把helper中的“同步分支不显式Complete”推广成任意实时依赖都能忽略。是否由caller建立了ready/同步前提，必须继续沿实际调用链验证。也不能将worker返回零解释成所有依赖原地清零或所有团队求解已完成。

## 原字节认证

五个exact unwind family，共1891字节；35个指令点、三个方法表身份、s_MainThreadId静态offset0与两个typeinfo初始化格复验通过。

| 函数 | 字节数 | SHA-256 |
| --- | --- | --- |
| delegate Schedule `0x5a18270` | 350 | `eba9a78591929a6f1f1cab993d051558ba87eeedca1a3448742be15b1d149ba3` |
| writer Schedule2 `0x5a1806c` | 515 | `4cee39caf53f61057c4bbd25fc20b64c6a717fa684133e03be1ddcdbae5876f5` |
| read wrapper `0x3b5e68` | 172 | `a2af7da5d40a1043bc50f80a804aa1c284ca6b1a0b8becfe5fa0a4129be67d24` |
| read generic ScheduleCrossFrameReadOnly `0x6985208` | 181 | `7d0aca5420730a96d6adc074be324101bc8e0b0c663fe4272b531a72f03b4a28` |
| read manager `0x5a1c92c` | 673 | `e765cc1b3d68e0feb70dc818f62a3bac2257d47823b60f5e3a4d49c893d33780` |

本机证据目录 `D:/EndfieldTechLib/notes/official-physics-animator-schedule-20261012-01/`；audit_source解析generic注册表，verify_source独立重读原字节、原MethodSpec/泛型参数和metadata/native身份，不导入调度适配器。完整反汇编与原资产保持私有。本轮没有独立代理语义审阅。

## 验收与下一步

缺模块collection RED先于实现。65项新增测试覆盖三条路线、非cross/非Animator未选线程、signed Int32边界、缺回调、无效16字节返回、异常与零handle。组合测试确认read返回handle被outer delegate接续，并让worker writer回调执行既有写缓冲参考，再由共享record读回local p。所有后端/句柄/姿态皆显式合成fixture，**不是原Job、真实CreateClothBindings或Unity实际Animator采样**。

四文件专项182项通过；新模块45语句/20分支100%覆盖。全量4632项和114 subtests通过，3项历史skip、2项历史Pillow警告。生产/测试文件的Ruff、Black、Pyright、compileall及测试环境pip-audit通过；11组/164保存点、7个runtime文件、9557条主index与主HEAD保持。

下一步沿后端与caller继续恢复：六个GCHandle的创建/释放/异常生命周期、read-only/cross普通包装层的实际完成机制与动态数据就绪前提、真实record/TRS来源。然后把统一11组状态和唯一writer接入可回退C#候选，完成连续动作/暂停/seek验收。不能据helper分流或测试数量称“官方物理完成”。完整门禁见 [PROGRESS.md](../official-physics-animator-buffer-20261003/PROGRESS.md)。
