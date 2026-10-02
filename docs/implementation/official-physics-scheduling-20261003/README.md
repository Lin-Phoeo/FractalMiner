# 官方物理：帧钩子与跨帧缓冲消费顺序

日期：2026-10-03。接续[当前/last缓冲复制](../official-physics-publication-20261002/README.md)。新增 `Tools/official_physics_scheduling.py`：**静态源调用顺序、符号依赖与条件完成点参考**，不是已接入Unity的调度器或完整求解器。现有舞台/湿身/阴影/预览物理未改动。

## 本轮确定的主线

| 稳定模式 | 本帧读取与消费 | 本帧求解后的发布 | 帧末状态 |
| --- | --- | --- | --- |
| 非跨帧 | ReadTransform → 求解链 | WriteTransform，输入当前四数组 | 普通完成master，再清零 |
| 跨帧、非Animator | 完成旧master → ReadTransform → WriteDoubleBufferTransform，输入last → **普通完成临时写入任务** → ValidPosition → 新求解链 | CopyDoubleBuffer：当前→last | 新master保留待完成；不在此处等待新求解完成 |
| 跨帧、Animator | ReadAnimatorBufferData → 六个托管对象句柄 → 委托任务 → 提前返回 | 另一路委托Job，未闭合 | **明确未移植，不套用上面两行** |

跨帧的last消费发生在下一条求解链之前。普通模式在求解/显示位置/后proxy之后写当前缓冲。**不要把当前→last复制放到每次渲染之前，也不要用交换current/last指针代替复制。**

这里的“完成”是源函数的条件完成调用点，不表示静态审计执行了任何Job。跨帧旧master使用 `Unity.Jobs.JobHandle::ScheduleBatchedCrossFrameJobsAndComplete(Unity.Jobs.JobHandle&)`；普通路径与临时last写入使用 `Unity.Jobs.JobHandle::ScheduleBatchedJobsAndComplete(Unity.Jobs.JobHandle&)`。字符串与源调用site已分别核查，**不是两个相同的普通Complete别名**。定制Unity的内部调度实现、JobHandle原地变化尚未恢复，不能直接声称stock Unity普通Complete等价。

## ClothUpdate的稳定、mapping为空分支

1. IsPlaying为false立即返回，没有pre/post回调与完成操作。
2. 可选OnPreSimulation；Time.FrameUpdate；若跨帧，条件完成旧master并清零16字节。
3. AlwaysTeamUpdate，然后读取enableTeamSet.Count；为0立即返回，**不触发OnPostSimulation**。
4. 读取Team.maxUpdateCount；AlwaysWindUpdate、WorkBufferUpdate。清零master，进入表格中的读取路径。
5. PreProxyMeshUpdate → CalcCenterAndInertiaAndWind → Simulation.PreSimulationUpdate → Collider.PreSimulationUpdate。
6. `SimulationStepUpdate(maxUpdateCount,stepIndex,master)`，stepIndex从0至count−1，返回句柄逐次成为下一次的依赖。原signed判断`jle`使0及负数均不执行step循环，但仍继续显示位置/发布。
7. **CalcDisplayPosition** → PostProxyMeshUpdate；它不是泛称的“PostSimulationUpdate”。mapping非空还有额外mesh/render工作，本参考明确拒绝该未移植分支。
8. 按稳定模式调度WriteTransform或CopyDoubleBuffer → Collider.PostSimulationUpdate → Team.PostTeamUpdate → CameraCullingPreProcess。
9. 普通模式完成master并清零。跨帧非Animator模式只再次检查临时last写入句柄的首qword、非零才普通完成；新master仍保留。可选OnPostSimulation最后调用。

第9步的临时句柄检查是第二个**条件检查site**，不是证明native Complete执行两次：第一次Complete接收句柄引用，可能改变它。参考保留两个 `complete-if-nonzero` 事件，不猜测内部首qword、liveness或回写行为。符号句柄只表达返回依赖，不是native Job ID。

## 帧钩子

- OnEarlyClothUpdate先读clothProcessDict.Count。没有process，或UseAnimatorTransform为true则退出。其余路径：跨帧先完成旧master并清零；enabled Count>0才CameraCullingPostProcess；**即便enabled为0，只要process存在仍RestoreTransform并普通完成其返回任务**。Restore自身算术未移植。
- OnAfterUpdate仅cross+Animator执行：active Count>0才CameraCullingPostProcess；然后完成master并清零，最后UpdateTeamAnimatorData。该host顺序已恢复，不能据此声称Animator委托求解链完成。
- metadata枚举验证：AfterLateUpdate=0、BeforeLateUpdate=1。对应两个hook只在精确匹配时调用ClothUpdate；其他Int32值不匹配，不擅自fallback。

process Count、enabled Count、active Count不是一个数。`plan_cloth_update` 的enabled与maxUpdateCount由调用者提供**AlwaysTeamUpdate之后、对应源读取site**的值；mapping Count也需对应后面的读取site。本参考不从deltaTime推导步数、不把输入静态值假称为Team计算结果。

## 证据与适用边界

源版本绑定：GameAssembly SHA256 `c24495e51b406f03b03890c4788ee618ae022c991405be5d5b8b787cb775ae89`；metadata `0076743397acadf03d3b0064343a963c7c88863b8160526d397e4b3efb96f02e`。

源入口：ClothUpdate369369/0x32ad500（4388字节）、OnEarly369364/0x30c4db0（703字节family）、OnAfterUpdate369365/0x3e2caa0（274）、OnBeforeLate369367/0x3e58db0（82）、OnAfterLate369368/0x32ad4b0（77）、CompleteMaster369360/0x3167490（146）、普通完成wrapper0x30c3e00（65）。均按exact unwind family审计；ForceCompleteAllJob/OnApplicationQuit共享0x507eca8没有exact unwind entry，**不猜长度、不宣称恢复**。MagicaManager static typeinfo usage与UseCrossFrameJob@9、UseAnimatorTransform@10、pre@176/post@184，Time.updateLocation@24，Team.maxUpdateCount@48/enableSet@80/processDict@88已核查。

有限adapter要求mode两项均为真正bool；整型/最多65536项的容量限制是adapter政策，非游戏上限。仅成功调用、稳定mode、稳定集合、无回调重入的骨骼Transform/mapping空路径。源码会多次重读static模式；若回调修改模式或销毁对象，本计划不能代表该运行。source方法名保留为**opaque事件**，没有借事件名实现求解、恢复、culling、setter或native scheduler。

没有确认游戏实际选中哪种mode/UpdateLocation，不能按静态分支推断当前游戏默认。无独立native/Burst运动oracle；两帧current→last→消费组合仅串行合成fixture，不是异步执行证明。

## 验证与留存

技能要求先写测试：缺模块RED，新增67项GREEN。覆盖了两种主要模式的完整事件序列、逐步返回依赖、host完成屏障、两处临时句柄条件检查、零/负step、早退/回调、三种不同Count、枚举hook、未移植路径显式拒绝，以及两帧合成缓冲组合。

全套 **1787 passed /114 subtests /3历史skip /2历史Pillow告警**。18个参考模块1418语句/368分支，branch-inclusive覆盖100%；本模块127语句/36分支全覆盖。Ruff/format/Pyright通过，临时工具pip-audit无已知漏洞。覆盖率只衡量这些有限参考代码，不是官方物理完成比例。

7项runtime文件、主HEAD与9557项用户原index保持。未运行Unity、未改舞台效果、未启动游戏或执行DLL。原资产、完整native指令与第三方源码保持私有。私有报告：`D:/EndfieldTechLib/notes/official-physics-scheduling-20261003-01/review-05/`；哈希/门禁见[verification.json](verification.json)。

## 后续正确接入路线

1. 完成实际setter的blend/culling/world-local/relative-sync分支、RestoreTransform/ReadTransform与动画唯一writer；用本轮顺序约束防止last提前覆盖。保留定制cross-frame完成与stock兼容方案的差异，不能伪称替换等价。
2. 补全11组proxy/list/Team发布，step、collision、惯性/reset、normalAxis消费。委托Animator Job与mesh mapping分别核查，不降级套用当前分支。
3. 完整成功调用链与原输入闭合后，才在Unity接入候选物理后端，验证MMD/解包动画、暂停/恢复/跳帧及回写唯一性。当前预览后端继续保留可回退。

**本轮闭合的是已限定路径的调用顺序，不是完整官方物理效果。**

后续记录：[Transform写入值与顺序](../official-physics-setter-20261003/README.md)已恢复有限输入下的权重、剔除、世界/局部分支及操作顺序。相对开关核实为useRelativeTransform，并使用正向TRS、不是逆矩阵；原生矩阵构造和实际setter/层级执行仍未移植。上面的“relative-sync”只是一项旧路线泛称，不是源字段开关结论。
