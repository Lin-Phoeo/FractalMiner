# 官方物理：热冷块连接、更新门控与时钟初始值

日期：2026-10-02。接续 [原生字段与调用点](../official-physics-native-20261002/README.md)。这一轮集中检查实施所需的更新条件；没有改 Unity 运行代码、角色、渲染、湿身、阴影或 MMD 基线。

## 先更正函数边界的解释

前轮的 30 个“有界函数体”实际是 **方法入口对应的 30 个 RUNTIME_FUNCTION 范围**。这些范围均已完整线性解码，但不能解释为 30 个完整托管方法的全部机器码：编译器可能把同一方法拆成多个热/冷范围。

本轮按 [Microsoft CHAININFO 文档](https://learn.microsoft.com/en-us/cpp/build/exception-handling-x64?view=msvc-170) 读取 padded unwind-code array 后的 RUNTIME_FUNCTION triple，校验它与真实 exception-table entry 精确相等，再递归连接；循环、错误三元组、handler/chain 非法组合和不支持的 chained version 都拒绝。**多个函数复用同一个 unwindInfo 地址不构成归属关系。** 不解读无关 v2 unwind operations，也不按相邻方法地址猜长度。

原 30 个入口现在关联 90 个明确同属 unwind 链的代码范围，共 36,436 字节。例如 OnEarlyClothUpdate 从原来的 39 字节入口范围扩展到 5 个范围、703 字节；OnAfterUpdate 从 98 字节扩展到 5 个范围、274 字节。遗漏的冷块里确实存在 Job completion 和动画数据更新。

这仍不是完整控制流证明：family 归属准确，不代表每个块都可达，也不证明间接调用、exception funclet、叶函数、外部 tail target 和 Job 依赖全部恢复。前轮报告原封不动保留；之后不要只据其 primary range 推断整段逻辑。

## 已认证的字段、模式和静态拥有者

新增 `NativeAudit.field_layout`：沿已认证 native class owner 与 fieldOffsets 注册表取真正偏移；type attributes 的 static 位决定偏移是相对静态存储还是实例，不能混用。仅 CLASS/VALUETYPE union 的 data 会标记为 definition index；primitive/generic union 不再被错误标注为定义身份。

本轮取出 MagicaManager、TimeManager、ClothManager 共 57 个字段的偏移/静态属性。关键项：

| owner / field | offset | 存储 |
| --- | --- | --- |
| MagicaManager.UseCrossFrameJob | 0x09 | static |
| MagicaManager.UseAnimatorTransform | 0x0a | static |
| MagicaManager.s_Time | 0x10 | static |
| TimeManager.simulationFrequency | 0x10 | instance |
| TimeManager.maxSimulationCountPerFrame | 0x14 | instance |
| TimeManager.updateLocation | 0x18 | instance |
| TimeManager.GlobalTimeScale | 0x24 | instance |
| ClothManager.masterJob | 0x38 | instance |

TimeManager.updateLocation 的 native type variant=180373，canonical=180372，均指向 definition=46104：**BeyondDynamicBone.TimeManager+UpdateLocation**。枚举默认数据独立解码为 AfterLateUpdate=0、BeforeLateUpdate=1。这与之前的 ClothUpdateMode.AnimatorLinkage=10 是不同字段/枚举。

上述 callbacks 和 SetUseCrossFrameJob 引用的 MagicaManager type-info cell 为 preferred VA `0x18d050868`，文件偏移 218424936，原 tagged value `0x2003fa53`：usage-kind=1、tag=1、type-index=130345；canonical native class 精确指向 MagicaManager definition=45989。解码依据是本地 Il2CppDumper Metadata.GetDecodedMethodIndex v29 规则；**没有**把这个初始 tagged value 当运行时 class pointer 或已读取的静态值。runtime static storage 本轮未读。

## 更新条件：已经可用于设计，但实际开关仍未知

以下是结合原生字段偏移、枚举、热冷块和人工逐指令复核得到的结构性门控，不是文件调用点排列推测。

| callback / setter | 已核实的门控或动作 | 原生证据 |
| --- | --- | --- |
| OnAfterLateUpdate | updateLocation=AfterLateUpdate(0) 才进入 ClothUpdate 跳转分支；非 0 返回 | cmp site 0x32ad4d5；jne 0x32ad4d9；tail jmp 0x32ad4e5 |
| OnBeforeLateUpdate | updateLocation=BeforeLateUpdate(1) 才进入 ClothUpdate 调用冷块；非 1 返回 | cmp 0x3e58dd5；je 0x3e58dd9；cold call 0x4f2abcd |
| OnAfterUpdate | UseCrossFrameJob 与 UseAnimatorTransform 都为 true 才继续进入相应冷块；任一 false 返回 | byte compares 0x3e2cac0 / 0x3e2cad6；cold entry 0x4f26142 |
| 同一冷块 | 包含 CompleteMasterJob，再到 UpdateTeamAnimatorData；还有额外 team/null 判断 | calls 0x4f261b8 / 0x4f261d8 |
| SetUseCrossFrameJob | 正常非空路径先 CompleteMasterJob，再写 static UseCrossFrameJob；不能边跑未完成 Job 边直接切开关 | call 0x5a4f8cf；write 0x5a4f8e2 |

`get_Time` 已由所属镜像/方法表定位，callback 的返回值使用 instance offset=0x18，与 native TimeManager.updateLocation 的身份一致。仍保留 class initialization、null/异常路径的边界，不把上述入口理解成所有游戏状态下必然执行。

OnEarlyClothUpdate 也确认存在 UseAnimatorTransform、UseCrossFrameJob、team 数据和 masterJob 判断，且调用 RestoreTransform 的 site=0x30c4f30；这段还不列成已完整重建的决策表，避免跳过前置 team/Job 条件。

**本角色运行时两个开关值、updateLocation 的最终配置、scheduler 如何注册 callback，以及 Job 依赖仍未核实。** 仅将目前预览放进 LateUpdate、不区分两个开关或不等待 Job 就切换模式，都不能由这些证据证明等价。

## 时钟：初始 90 / 3，不是已确认的实际运行设置

TimeManager..ctor 没有 exact exception entry，但其入口是短直线：三条 MOV32 immediate 写实例字段，然后 RET。新受限读取器只接受 RCX 接收者、已认证 instance offset、32 位 primitive immediate 写与无操作数 RET；任何分支、call、其他指令、未知 field/receiver/width、重复写或缺失 terminal 都拒绝。最多检查 128 字节；这不是通用的“扫到 ret 就算函数”的边界猜测。

22 字节终止路径直接证明：

- 0x4a475d0 写 simulationFrequency=90（原数据 `5a000000`）。
- 0x4a475d7 写 maxSimulationCountPerFrame=3（`03000000`）。
- 0x4a475de 写 GlobalTimeScale=1.0（`0000803f`）。
- 0x4a475e5 RET。

另在 FrameUpdate 中核实 simulationFrequency 的 30/150 边界比较及写回，maxSimulationCountPerFrame 的 1/5 边界比较及写回。**这些初始值/边界不证明运行时一定为 90Hz/3 步**，setter、初始化与其他配置仍可能覆盖。updateLocation 等未被该构造路径显式写入的字段，不能靠此读取器擅自补默认值；尚未完整恢复的 timestep/GlobalTimeScale/SimulationPower 公式也不补成猜测代码。

目前 34 个选中入口：30 个 unwind families + 1 个受限直线初始化入口已查；3 个仍 pending（ForceCompleteAllJob、AfterFixedUpdate、AfterRenderring）。合计解码 36,458 字节。现有预览时钟没有被改成 90，当前官方求解器仍未接入。

## 工具与复现

复用已有两个工具，没有另造反编译器。新 native/calls 报告均为 schema=2。capstone=5.0.9；完整证据、hash 与门禁见本目录 verification.json。

```powershell
cd 'A:/Hypergryph Launcher/games/Arknights Endfield/FractalMiner'
uv run --no-project --python 3.12 python Tools/export_official_physics_native.py `
  --binary ../GameAssembly.dll --metadata ../Endfield_Data/il2cpp_data/Metadata/global-metadata.dat `
  --type-info-cell BeyondDynamicBone.MagicaManager=0x18d050868 --output '<新 native 报告>'
uv run --no-project --python 3.12 --with capstone==5.0.9 python Tools/audit_official_physics_calls.py `
  --binary ../GameAssembly.dll --native-manifest '<上一条 native 报告>' --output '<新 calls 报告>'
```

本地最终证据：`D:/EndfieldTechLib/notes/official-physics-conditions-20261002-01/physics-native-layout-03.json`、`physics-call-families-03.json`、`conditions-coverage.json`。来源地址仅适用于当前已记录 SHA256 的游戏文件；binary、metadata、原始 bytecode 和 manifests 不入 Git。

本轮增加 24 项测试，两个工具合计 77 项：补热冷链、奇数 slot padding、多级/循环/错误 chain、shared-unwind 不能混合不同函数、字段静态/实例区别、tagged usage 拒绝错误 owner、受限直线入口拒绝未知执行路径。全套 661 passed、3 项历史 skip、114 subtests、2 项历史 Pillow 告警；新增/修改工具含分支覆盖率 native=86.26%、calls=93.52%、合计 89.30%；Ruff、Pyright、pip-audit 通过。7 项受保护运行文件 hash 保持原样。

## 直接接续点

下一步只沿已证链推进：先查 callback 注册与最终 mode/flag/频率写入者，补 ClothUpdate 内跨帧读写与 Job 依赖，然后将这些规则作为可切回适配层的约束。沿用原 11 组 BoneCloth/AnimatorLinkage/Line 参数及挂点计划；不重新改捕获姿态、加权 bindpose、材质、湿身或 MMD，不做逐像素拟合。

在约束数学和原始脚本 PPtr 尚未闭合前，新的近似物理也必须标为近似，不能标“官方 solver 已完成”。

接续进展：[PlayerLoop 挂接、订阅与跨帧完成入口](../official-physics-scheduler-20261002/README.md)。七个挂接请求、布料/时钟订阅及静态初始开关已补证，发现游戏引擎专用跨帧 Job 完成入口；实际角色最终配置与求解数学仍待查，未替换预览。
