# 官方物理：PlayerLoop 挂接、订阅与跨帧完成入口

日期：2026-10-02。接续 [更新门控与时钟初始值](../official-physics-conditions-20261002/README.md)。本轮只增强离线解析工具、测试和证据文档；没有替换 Unity 预览求解器，没有改渲染、湿身、自阴影或 MMD。现有替代物理仍可使用，不标成官方算法。

## 本轮闭合的范围

- `InitCustomGameLoop` 对当前 PlayerLoop 做 CheckRegist；其 true 分支跳过新挂接，false 分支调用 SetCustomGameLoop，再调用 SetPlayerLoop。不是无条件每帧重复注册。
- 七个挂接请求的 category/system、last/before、callback 身份及 callback 使用的静态 delegate 字段已交叉核查。
- ClothManager.Initialize 的四个更新订阅及退出订阅、TimeManager.Initialize 的两个时钟订阅已定位。
- 默认静态开关和正常 Job 完成入口已经确认；实际运行最终开关、安装后的整棵循环树和求解数学仍未确认。

Unity 的 [PlayerLoop API](https://docs.unity3d.com/2022.3/Documentation/ScriptReference/LowLevel.PlayerLoop.html) 支持插入自定义更新入口。下面的具体挂接关系来自本机原始 binary/metadata，不是把通用 Unity 文档当作游戏证据。

## 七个挂接请求

`BeyondDynamicBone.PlayerLoopUtils.AddPlayerLoop` 的 method definition=371450，入口 RVA=0x39371c0。参数表六项为 `method / playerLoop / categoryName / systemName / last / before`，原始参数项文件位置从 37862368 到 37862428、步长 12。人工沿已界定的热冷块检查参数装载、缓存 delegate 对应字段及 helper 的插入分支：last=true 使用追加分支；last=false 按 systemName 查索引，before=true 用该索引插入，false 用索引+1。

| callback（`b__50_N`） | category / system | last / before | 挂接请求 | 读取的 MagicaManager 静态字段 | AddPlayerLoop call site |
| --- | --- | --- | --- | --- | --- |
| 0，RVA 0x30c4ad0 | EarlyUpdate / null | 1 / 0 | EarlyUpdate 子列表末尾 | afterEarlyUpdateDelegate，0x60 | 0x3935a39 |
| 1，0x30c4b60 | FixedUpdate / ScriptRunBehaviourFixedUpdate | 0 / 0 | 指定系统之后 | afterFixedUpdateDelegate，0x68 | 0x3935b73 |
| 2，0x30c4570 | Update / ScriptRunDelayedTasks | 0 / 0 | 指定系统之后 | afterUpdateDelegate，0x70 | 0x3935cad |
| 3，0x30c4650 | PreLateUpdate / ScriptRunBehaviourLateUpdate | 0 / 1 | 指定系统之前 | beforeLateUpdateDelegate，0x78 | 0x3935de7 |
| 4，0x30c46e0 | PreLateUpdate / ScriptRunBehaviourLateUpdate | 0 / 0 | 指定系统之后 | afterLateUpdateDelegate，0x80 | 0x3935f21 |
| 5，0x30c4770 | PostLateUpdate / ScriptRunDelayedDynamicFrameRate | 0 / 0 | 指定系统之后 | afterDelayedDelegate，0x88 | 0x393605b |
| 6，0x30c4800 | PostLateUpdate / FinishFrameRendering | 0 / 0 | 指定系统之后 | afterRenderingDelegate，0x90 | 0x3936195 |

这些 callbacks 都检查 EnableTick，再检查相应 delegate 是否非空。callback 2 在主 delegate 路径后还检查 `UnityEngine.Application.get_isPlaying`（method=355502、RVA=0x2e6ce90），条件成立才进入 defaultUpdateDelegate(0x98) 的额外路径；不能把 defaultUpdateDelegate 当无条件的第二个物理更新。

**表格证明注册代码所请求的位置，不证明当前运行实例已经成功安装、每个系统名称在所有循环树里都存在、订阅者总数固定或回调实际必定执行。** InitCustomGameLoop 中 CheckRegist call=0x393aaeb、true 分支=0x393aaf2；SetCustomGameLoop call=0x393ab1c；SetPlayerLoop call=0x393ab48。仍保留 null、class-init、已有注册和异常分支的边界。

## 订阅与两个时钟回调

新的 tagged metadata usage 解析区分 TypeInfo(1)、Il2CppType(2)、MethodDef(3)、StringLiteral(5)。低位 tag、索引、所属类型/方法、canonical native 身份、字符串 table/length/dataIndex 都需验证；不支持的 primitive/generic/field usages 不猜。字符串按 metadata 的 length 读取，不能用邻接 C string 替代。初始 tagged value **不是运行时 MethodInfo、class pointer 或 native 函数指针**。

ClothManager.Initialize（RVA=0x37a8140）中构造绑定当前实例的 UpdateMethod，调用 `System.Delegate.Combine`（method=278511、RVA=0x3659650）后写回：

| 方法 identity cell（preferred VA） | 方法 | delegate 字段 | 正常写回 site |
| --- | --- | --- | --- |
| 0x18d068748 | OnEarlyClothUpdate，369364 | afterEarlyUpdateDelegate，0x60 | 0x37a82ac |
| 0x18d068758 | OnAfterUpdate，369365 | afterUpdateDelegate，0x70 | 0x37a8361 |
| 0x18d068780 | OnAfterLateUpdate，369368 | afterLateUpdateDelegate，0x80 | 0x37a8419 |
| 0x18d068738 | OnBeforeLateUpdate，369367 | beforeLateUpdateDelegate，0x78 | 0x37a84d4 |
| 0x18d068768 | OnApplicationQuit，369366 | onApplicationQuitDelegate，0xa0 | 0x37a85b3 |

TimeManager.Initialize（RVA=0x37a7f10）把 AfterFixedUpdate（identity cell=0x18d0767a0）合并到 0x68，正常写回=0x37a8009；把 AfterRenderring（拼写照原 metadata，cell=0x18d0767c0）合并到 0x90，写回=0x37a80bd。因此时钟不只有 FrameUpdate 这一个入口。两个 leaf 回调本体仍 pending，不能仅凭名字补公式。

## 初始开关与跨帧 Job

MagicaManager..cctor（RVA=0x476df60）可核实初始写入：EnableTick=true（0x476dfb5）、UseCrossFrameJob=true（0x476dfc7）、UseAnimatorTransform=false（0x476dfd9）。这不是最终运行配置。

最后一项不能仅凭“前面 xor r10d，所以这里 r10b=0”推断：R10 是跨调用需要审查的寄存器。本轮给 cctor 引用的 helper RVA=0x26b40 增加了受限局部控制流证明，跟踪其所有 JE/JNE/JMP 分支，在 96 字节 file-backed 窗口内只接受已支持的普通指令；拒绝 call、间接/系统控制、R10 任一宽度写入、RET 之外的 RSP 写入、指令重叠及缺失正常返回。实际到达 17 条指令、66 字节、RET=0x26b81；支持路径均保持 R10。CAS 重试循环的终止性、fault/exception、并发自修改等不在证明内，不能把它泛化为完整原生 CFG 还原。

CompleteMasterJob 的已核实正常完成分支：

- UseCrossFrameJob=false：cold site 0x4b1e312 调用 Unity.Jobs.JobHandle.Complete（RVA=0x30c3e00），解析的 icall 名称为 `Unity.Jobs.JobHandle::ScheduleBatchedJobsAndComplete(Unity.Jobs.JobHandle&)`。
- UseCrossFrameJob=true：检查 masterJob(0x38)，经 cached function slot 调用；其解析名称为 `Unity.Jobs.JobHandle::ScheduleBatchedCrossFrameJobsAndComplete(Unity.Jobs.JobHandle&)`（C string RVA=0xa869510，解析 site=0x31674fc）。
- 支持的正常路径回到 0x31674c5，将 masterJob 的 16 字节存储清零。这里没有将 engine 的 icall 实现、依赖图或整套异常行为视为已恢复。

本机 Unity.Jobs.JobHandle 还存在 CrossFrameComplete、ScheduleBatchedCrossFrameJobsAndComplete 方法。**这是所检查游戏引擎的实际扩展证据，不等于标准 Unity 的公开 API，也不证明官方 stock MagicaCloth 版本、授权或求解完全相同。** 普通项目不能直接假定这个 native hook 可用。

## 对 MMD 适配的直接约束

1. 不重复注册；关闭/重建先完成正在运行的任务，再解绑和清历史。动画、物理和蒙皮写回必须有明确的所有者。
2. 保留官方路径的参数/模式证据；实际最终频率、两个开关与 updateLocation 未取得前，不把初始 90/3 和目前预览 120Hz 混为一谈。
3. MMD 编辑器拖动、倒拖、循环和离线出片需要确定性求值。可设计同步 Complete 的独立适配后端，但要标明这是使用需求适配，不冒充游戏跨帧 icall；不需要照搬原引擎的并发调度来得到可复现出帧。
4. 下一步优先恢复 ClothUpdate 内参数/缓冲读写及约束数学，并查配置写入者；将原始 11 组参数和挂点数据接到独立可切回后端。45 个 local orientation/linear 差异与外部 MonoScript PPtr 仍未闭合，不覆盖现有正确蒙皮来强行适配。

## 工具、证据与状态保留

复用两个原工具：native/calls 报告 schema=3，新增可选 `--usage-cell VA`；RIP references 区分 LEA 地址、内存读写和间接调用槽，槽地址不当作最终 callee。保留所有同地址 alias；没有遍历游戏进程或执行 DLL。

最终本地证据目录：`D:/EndfieldTechLib/notes/official-physics-scheduler-20261002-01/`：native-scheduler-04.json、calls-scheduler-05.json、scheduler-coverage-formatted.json（最终格式化后工具测试覆盖；全套报告 scheduler-coverage-sealed.json 同样保留）。重跑用相同 binary/metadata、前轮 type-info 参数，加上 verification.json 记录的 27 个 `--usage-cell` 值，输出到**全新文件**；calls 工具引用该新 native 报告。旧 01–04 报告保留。

本轮新增 36 项测试，native=59、calls=54；全套 697 passed、3 历史 skip、114 subtests、2 历史 Pillow 告警。Ruff、Pyright 和临时环境 pip-audit 通过，工具含分支覆盖门槛 80% 通过。没有 C#/shader 修改，未重跑 Unity。

检查中发现 `Assets/Scenes/Typhoeus_MMD_Stage.unity` 是已有工作区修改：当前 raw hash=5b4fd74ccbb85348e5855f1741fe32cb2754a13afca8327471c1e8573216d13a、mtime=2026-10-02 09:14:26，与历史基线不同。这不是本轮工具造成的改写；原样保留、不恢复、不纳入提交。其余六项历史保护文件匹配。主 HEAD、用户原始暂存索引继续保留；阶段提交只含两工具、两测试和文档。
