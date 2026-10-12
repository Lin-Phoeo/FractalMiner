# 下一执行入口：跨帧 Animator 委托主体

更新时间：2026-10-12。代码记录提交 `4e3e4af9dc5aee1ad633997a46f33727e74e2e5b` 已推送并经远端复核；主 HEAD `fc9d4869803f439ffff83311986190e8a8b5ade3` 与主 index 的 9557 项保留。下一步接续本页，不重做已恢复的写缓冲或绑定重建。

后续进展：[宿主与无mapping委托顺序](../official-physics-animator-delegate-20261012/README.md)已补有限计划，下面的入口与证据仍有效；“恢复Execute”的正常顺序子项已推进，实际调度/句柄生命周期与读写数据接线仍未闭合。当前以新单元及PROGRESS的门禁为准。

## 已确认的连接

`ClothUpdate` 369369 / `0x32ad500` 的 cross+Animator 分支在 `0x32ad88c` 调读取 manager，再构造六个 GCHandle；`0x32ad954 → 0x5a18270` 已由当前泛型注册表确定为 `CrossFrameJobUtils.Schedule<DoAllInOneJob>`。开放方法 369400，MethodSpec 506099，pointer slot 478569。

实际委托主体为 `BeyondDynamicBone.DoAllInOneJob.Execute`，方法 369394，RVA `0x5a1b0a8`。完整 CHAININFO unwind family 只有一段：`0x5a1b0a8..0x5a1b726`，1662 字节，SHA-256 `86825b2332cac153c0128916853e1acd2e72d5d7ebac4d9cc8bfdf6444be3b0b`。已检查解码字节数相等；这不代表其完整控制流已移植。

六个字段均为 `System.Runtime.InteropServices.GCHandle`，unboxed offset 依次是：`bmHandle=0`、`tmHandle=8`、`vmHandle=16`、`smHandle=24`、`wmHandle=32`、`meshClothSetHandle=40`。与 caller 的六句柄打包对应，不能用一个 manager 或一个回调代替。

已解析的主干调用点如下。表中列举静态调用身份，不将表格本身当作完整分支/依赖证明。

| 调用点 | 已解析方法 |
| --- | --- |
| `0x5a1b248` | DynamicBoneTransformManager.ValidPosition |
| `0x5a1b26f` | VirtualMeshManager.PreProxyMeshUpdate |
| `0x5a1b296` | TeamManager.CalcCenterAndInertiaAndWind |
| `0x5a1b2bd` | SimulationManager.PreSimulationUpdate |
| `0x5a1b2f7` | ColliderManager.PreSimulationUpdate |
| `0x5a1b344` | SimulationManager.SimulationStepUpdate |
| `0x5a1b373` | SimulationManager.CalcDisplayPosition |
| `0x5a1b39a` | VirtualMeshManager.PostProxyMeshUpdate |
| `0x5a1b3dc` | VirtualMeshManager.PostMappingMeshUpdate（需核查条件分支） |
| `0x5a1b63b` | DynamicBoneTransformManager.WriteAnimatorBufferData |
| `0x5a1b671` | ColliderManager.PostSimulationUpdate |
| `0x5a1b68f` | TeamManager.PostTeamUpdate |

写 manager 的 `0x5a1d0ae → 0x5a1806c` 已确定为 `CrossFrameJobUtils.Schedule2<DynamicBoneTransformManager.WriteAnimatorBufferDataJob>`，开放方法 369399，MethodSpec 506112。读取 manager 的 `0x5a1cb94 → 0x3b5e68` 原先未解析；2026-10-12已沿wrapper的MethodInfo初始化格和目标 `0x6985208` 确认为 `ScheduleCrossFrameReadOnly<ReadAnimatorBufferDataJob>`，method360316 / MethodSpec515143，详见[读/委托/写调度](../official-physics-animator-schedule-20261012/README.md)。不是同一种Schedule2。

帧后 `OnAfterUpdate` 369365 / `0x3e2caa0` 的已封存完整 family 在 `0x4f261b8` 完成 master，之后 `0x4f261d8` 才更新 Team Animator bindings。`updateMode=10` 证明 AnimatorLinkage 模式；路由还受 `UseCrossFrameJob` 和 `UseAnimatorTransform` 两项开关门控，不能从保存的模式数值断言游戏当时选中的路由。

## 下一单元的工作边界

2026-10-12状态刷新：Execute的无mapping有限顺序已在 [delegate单元](../official-physics-animator-delegate-20261012/README.md) 实现；绑定→共享record→读→写→读合成接线已在 [record-read单元](../official-physics-animator-record-read-20261012/README.md) 验证。随后读wrapper身份与三个具体helper的worker/主线程门控已恢复为[显式回调适配](../official-physics-animator-schedule-20261012/README.md)。下列未完成项不据此标为已闭合：真实native record/TRS、positive mapping、native后端/依赖就绪、GCHandle生命周期及Unity动态。

1. 在已恢复的mapping-empty Execute有限顺序和三条具体helper门控基础上，核查native后端/调用方的依赖就绪、Job struct拷贝与实际完成机制；positive mapping仍未恢复。其余Schedule2泛型实例不能直接套用本writer的worker规则。
2. 核查六个句柄的 GetTarget 类型、创建及释放位置。当前只有入口/字段/静态调用身份，尚未证明生命周期；不推断 job 返回即自动释放。
3. 绑定重排后的handler在共享record读写合成fixture中已验证；继续接真实CreateClothBindings/record输入与原native单位尺度TRS来源，保留read逆relative与write正向relative。不能将合成矩阵视作native TRS oracle。
4. [Add/Clear Team Animator正常路径](../official-physics-animator-membership-20261012/README.md)已恢复有限参考：null Add仍dirty且不删旧映射，Clear仅删当前manager两张Team map；不是record/GCHandle释放。完整RemoveTeam（369510 / `0x5a22470`）的同步父组/chunk/多容器副作用仍待恢复。AddAnimatorTransform（369503 / `0x34408a0`）和 MarkAnimatorTransformDirty（369504 / `0x5a22398`）只在 Transform 非 Unity-null 时添加 dirty，不能无条件改写。
5. 完成输入/依赖后再接可回退 C# 候选，并在实际角色动作、暂停/恢复/跳帧中验证。当前已有舞台后端和可见效果保持，正式官方候选后端仍未接入 Unity。

## 本机证据与完整性

证据目录：`D:/EndfieldTechLib/notes/official-physics-animator-lifecycle-20261012-01/`。本次只读取静态原始文件，没有加载或执行原生游戏代码。

| 文件 | SHA-256 |
| --- | --- |
| `audit_delegate_source.py` | `34015adf9ec13313923bab63b9fcd61cc2637a635463815f1135ce3a88a14233` |
| `delegate-source-audit-01/animator-delegate-source-audit.json` | `38d231313c38e2e49d2d2c7065c52f4866b2a8974ee8009361f3b48e2739fb67` |
| `delegate-source-audit-01/do-all-in-one-job.txt` | `3de9b08e6b0371bcde5b133b288e02b121f40241ef0bf9d645f077d81c898e7c` |

原始 DLL / metadata SHA-256 仍为 `c24495e51b406f03b03890c4788ee618ae022c991405be5d5b8b787cb775ae89` / `0076743397acadf03d3b0064343a963c7c88863b8160526d397e4b3efb96f02e`。

既有 caller/帧后证据：`D:/EndfieldTechLib/notes/official-physics-scheduling-20261003-01/review-05/bounded-32ad500.txt`、`bounded-3e2caa0.txt`。既有 Read/Write manager：`D:/EndfieldTechLib/notes/official-physics-animator-buffer-20261003-01/review-04/`。全局最新门禁见[PROGRESS.md](../official-physics-animator-buffer-20261003/PROGRESS.md)。
