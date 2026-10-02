# 官方物理：原生字段身份与有界函数调用点

日期：2026-10-02。接续 [官方更新模式枚举核查](../official-physics-update-mode-20261002/README.md)。本轮仅离线读取本地游戏文件，没有执行 DLL、启动/注入游戏或改变任何 Unity 运行代码、资产、场景。

## 结论与边界

四个此前未认证的 consuming field type variants 现在已通过 **native types registration → Il2CppType.data → metadata type definition** 严格认证，不再依赖索引差值或字段名字。14 个类型共 502 个方法声明中，491 个有非空、位于文件支持可执行区的入口；11 个为 null，明确保留未知。502 是库存数量，不是全部有函数体或全部完成审查。

34 个关键入口中，30 个通过 AMD64 exception directory 的精确 `RUNTIME_FUNCTION` 边界完成线性解码，合计 18,681 字节；4 个缺少精确边界，保持 pending。观察到 607 个直接 call/jmp 点、9 个间接 call/jmp 点及 421 个条件跳转。**调用点存在不等于可达性、分支条件或每帧执行顺序已经证明。** 不发布原始游戏字节码，不把反汇编结果当完整求解器源码。

现有 UniVRM/Verlet 预览没有被替换。官方 frequency、custom-loop 生效路径、跨帧交换条件、约束数学及 teleport/reset 策略仍待证；旧固定 120Hz 仍只是预览的确定性策略。

## 四个字段：原生 identity 闭合

每个 field variant 和 canonical enum 都验证 kind=VALUETYPE(0x11)、valuetype 位、无 byref/pinned/modifier，并直接指向同一 metadata definition index。field variant 的 attrs=0x0006，canonical attrs=0；不能把属性位当另一类型或靠相邻索引猜测身份。

| consuming field | field index | native variant / canonical index | definition index | 完整枚举身份 |
| --- | --- | --- | --- | --- |
| ClothSerializeData.updateMode | 233416 | 111633 / 111631 | 45695 | BeyondDynamicBone.ClothUpdateMode |
| ClothSerializeData.clothType | 233406 | 160122 / 160120 | 45681 | BeyondDynamicBone.ClothProcess+ClothType |
| ClothSerializeData.connectionMode | 233413 | 174475 / 174473 | 46014 | BeyondDynamicBone.RenderSetupData+BoneConnectionMode |
| BeyondBoneCapsuleCollider.direction | 233498 | 152583 / 152582 | 45696 | BeyondDynamicBone.BeyondBoneCapsuleCollider+Direction |

至此上述字段的 enum mapping 可使用前轮已从 metadata 原字节恢复的数值。提弗洛斯 11 组原配置 `1/10/0` 对应 BoneCloth/AnimatorLinkage/Line 的类型环节已经补证。

这**不**自动解开 prefab 的 external MonoScript CAB PPtr，也不证明 25 个物理组件的源码身份全部完成，更不证明 stock MagicaCloth 2 与 BeyondDynamicBone 分支求解等价。

## 注册结构与方法定位

当前 PE 为 AMD64、PE32+，preferred image base `0x180000000`。地址仅属于下述 SHA256 的文件，不可套用其他版本。

- metadata registration：VA `0x18a88e860`，文件偏移 `0x0a88ca60`。
- native types count=225789；types pointer table VA `0x18c472bb0`。
- fieldOffsetsCount / typeDefinitionsSizesCount 均为 58110；整组 pointer arrays 有界，全部 type-size 指针可读。
- metadata 共 170 个 image；类型范围无重复、无漏覆盖。
- BeyondDynamicBone.dll module VA `0x18ac33e10`，method pointer count=3221。
- Gameplay.Beyond.dll module VA `0x18acd4360`，method pointer count=102186。

方法按 **type 所属 image + method token 的 RID−1** 查该 image 的 method pointer table，不用全局 method index 直接索引，也不把 token 当 RVA。两个 module 都核查完整 metadata RID 清单、exact count、唯一 module name pointer 和所有非空 pointer 的可执行文件支持范围。共享入口保留所有别名，null 不造地址。

`global_code_registration_verified=false`：本轮结构定位的是上述 modules，不冒充已经沿全局 code-registration 注册函数证明它们的初始化调用链。

## 真正读到的调用点

以下是函数体中的直接调用/跳转证据，而非由名字拼出来的流程。所有调用点仍须配合分支控制流、Job 依赖和 NPC/角色配置确认实际执行路径。

| 源函数 | site RVA | 指令 | 目标 |
| --- | --- | --- | --- |
| ClothManager.OnAfterLateUpdate | 0x32ad4e5 | jmp | ClothManager.ClothUpdate |
| ClothManager.ClothUpdate | 0x32ad610 | call | TimeManager.FrameUpdate |
| 同上 | 0x32ad88c | call | DynamicBoneTransformManager.ReadAnimatorBufferData |
| 同上 | 0x32ada94 | call | SimulationManager.PreSimulationUpdate |
| 同上 | 0x32adb31 | call | SimulationManager.SimulationStepUpdate |
| 同上 | 0x32adb68 | call | SimulationManager.CalcDisplayPosition |
| 同上 | 0x32ade18 | call | DynamicBoneTransformManager.WriteTransform |
| 同上 | 0x32ade74 | call | DynamicBoneTransformManager.CopyDoubleBuffer |
| 同上 | 0x32aded2 | call | DynamicBoneTransformManager.WriteAnimatorBufferData |
| 同上 | 0x32adf7a | call | ClothManager.CompleteMasterJob |
| NPCCPUAnimator._UpdateBeyondBoneCloth | 0x42ee51d | call | ClothCalculator.UpdateDynamicBone |
| 同上 | 0x42ee538 | call | ClothCalculator.UpdateBeyondClothEnabled |

`ClothUpdate` 入口 RVA `0x32ad500`，精确 range `[0x32ad500, 0x32ae624)`，4388 字节。另有两个 ReadTransform 调用点、一个 WriteDoubleBufferTransform 调用点；有多处分支和不同位置的状态读写，不能解释成上表行顺序在同一帧必然串行执行。Job schedule、依赖与 completion 也不能只据函数名字认定。

4 个未检查函数体：ClothManager.ForceCompleteAllJob、TimeManager.AfterFixedUpdate、TimeManager.AfterRenderring、TimeManager..ctor。可能为叶函数/其他布局，但尚未证明原因；不拿相邻方法地址减法猜长度，不强行扫描到 ret，也不根据名字填实现。

## 复现、依据与验收

两个新只读工具复用现有 metadata parser，未复制完整 dumper 或自造解码器。registration/type/module 布局与 image-qualified method lookup 参考 [Perfare Il2CppDumper](https://github.com/Perfare/Il2CppDumper/blob/master/Il2CppDumper/Il2Cpp/Il2CppClass.cs)；函数边界依 [Microsoft AMD64 exception handling](https://learn.microsoft.com/en-us/cpp/build/exception-handling-x64?view=msvc-170)；指令解码复用 [Capstone Python API](https://www.capstone-engine.org/lang_python.html)，本次版本 5.0.9。许可说明见 `Tools/THIRD_PARTY_IL2CPP_NOTICE.txt`。

```powershell
cd 'A:/Hypergryph Launcher/games/Arknights Endfield/FractalMiner'
uv run --no-project --python 3.12 python Tools/export_official_physics_native.py `
  --binary ../GameAssembly.dll `
  --metadata ../Endfield_Data/il2cpp_data/Metadata/global-metadata.dat `
  --output '<新的 native 报告绝对路径>'
uv run --no-project --python 3.12 --with capstone==5.0.9 python Tools/audit_official_physics_calls.py `
  --binary ../GameAssembly.dll --native-manifest '<上一条 native 报告路径>' `
  --output '<新的 calls 报告绝对路径>'
```

输出 exclusive-create，拒绝覆盖。calls 工具重新核对 binary SHA256 与入口 VA/RVA/file offset；清单是前轮定位依据，不冒充 independent oracle。所有文件边界检查排除 BSS、区段重叠、空长度、越界；函数只能用精确 exception entry，有效入口无 entry 时明确 pending，解码截断时拒绝结果。

证据保留在 `D:/EndfieldTechLib/notes/official-physics-native-20261002-01/`：`physics-native-01.json`、`physics-calls-01.json`、`combined-coverage-final.json`，SHA256 及测试记录见本目录 `verification.json`。游戏文件与 native manifests 不入 Git；只入工具、测试、摘要和指纹。

53 项新增合成测试（33 native、20 calls），覆盖非相邻类型 variant、错误种类/flags、注册歧义、模块 count/不可执行 pointer、image token、null、截断 PE、BSS/区段重叠、精确函数边界、共享入口别名、间接调用、分支、部分解码拒绝、hash/address 错配和覆盖保护。新工具含分支覆盖率分别 87.89% / 94.00%，合计 89.98%。全套 Python 637 passed、3 项历史 skip、114 subtests passed、2 项历史 Pillow 告警；Ruff、Pyright、pip-audit 通过。未改 C#/Unity，未宣称经过新的 Unity 视觉或物理验收。

## 下一阶段：从调用点推进到条件和状态

1. 先读 OnAfterLateUpdate/ClothUpdate 分支谓词：updateLocation、UseCrossFrameJob、UseAnimatorTransform、Job completion 和读写 buffer 哪些组合生效。补字段 offsets 和 mode identity；要证明条件，不能仅看调用点文件顺序。
2. 追 TimeManager.Initialize/FrameUpdate 与 simulationFrequency 的写入者/配置者；四个无精确边界入口用独立、安全的离线边界依据继续核查。setter 存在、枚举值 10 或 clamp 常量都不证明本角色运行频率。
3. 确認 NPCCPUAnimator/ClothCalculator 的 weight、teleport、reset 与 AnimatorLinkage 选择路径；前置分支、间接 dispatch/hotfix 等仍需核实。
4. 补各约束/惯性/碰撞/显示插值数学及 scheduler，再做独立可切回适配。继续保留既有加权 bindpose、18 个额外挂点计划、捕获姿态、MMD 和湿身/阴影基线，不覆盖为猜测值。

目标是忠实且可追溯的官方逻辑；本轮没有逐像素拟合，也没有宣布官方物理完成。

后续重要更正与进展：[热冷块连接、更新门控与时钟初始值](../official-physics-conditions-20261002/README.md)。本页的 30 个有界函数体指入口的 RUNTIME_FUNCTION 范围，不保证完整方法代码；新版通过 CHAININFO 扩展到 90 个相关范围，并补证 TimeManager 直线构造入口写入 90/3/1.0。实际角色的最终频率、开关和求解逻辑仍待查。
