# 官方物理更新模式：枚举已确认，调用时序仍待核实

日期：2026-10-02。接续 [局部姿态与挂点计划](../official-physics-local-pose-20261002/README.md)。本轮只读现有游戏 metadata、原物理配置和本地解析器源代码；没有启动/注入游戏，没有改 Unity 运行代码、资产或场景。

## 本轮闭合的事实

从当前安装游戏的 `Endfield_Data/il2cpp_data/Metadata/global-metadata.dat` 直接读取：

| 完整类型身份 | 已核实的字面量 |
| --- | --- |
| BeyondDynamicBone.ClothUpdateMode | Normal=0、UnityPhysics=1、Unscaled=2、AnimatorLinkage=10 |
| BeyondDynamicBone.ClothProcess+ClothType | MeshCloth=0、BoneCloth=1、BoneSpring=10 |
| BeyondDynamicBone.BeyondBoneCapsuleCollider+Direction | X=0、Y=1、Z=2 |
| BeyondDynamicBone.RenderSetupData+BoneConnectionMode | Line=0、AutomaticMesh=1、SequentialLoopMesh=2、SequentialNonLoopMesh=3 |
| UnityEngine.AnimatorUpdateMode | Normal=0、AnimatePhysics=1、UnscaledTime=2 |

所有选中枚举都核对 `IsEnum` 位、`elementTypeIndex` 与 `System.Int32.byvalTypeIndex` 的身份相等，且每个字面量的 default record 同样指向该 Int32 类型。不是拿枚举成员名按顺序猜数值。

例如 AnimatorLinkage：

- field index：233497；default data index：472235。
- metadata 文件字节偏移：33071939；原字节：`14`（十六进制）。
- v29 的压缩 signed Int32 解码结果：10，消耗 1 字节。不能在这里直接 `ReadInt32`，否则会吞入后续字面量数据。

此前已恢复的提弗洛斯 11 组配置全部为 `clothType=1/updateMode=10/connectionMode=0`，与上述符号对应为 **BoneCloth / AnimatorLinkage / Line**。当前 metadata 与此前配置分别保留各自 SHA256；这不认证所有游戏版本或所有角色都相同。

这些值也与 [MagicaCloth 2 作者的 ClothSerializeData API](https://magicasoft.jp/en/mc2_api_clothserializedata/) 一致。但现在枚举数值结论依据的是本地官方 metadata，不再只依赖上游文档。

**updateMode=10 是模式，不是模拟频率。** 官方内部仍可能有固定步长/子步；本轮没有核实它是多少，也不否定它可能恰好是 120Hz。现有预览的固定 120Hz 仍属于本项目的确定性设计，不能被标为已确认的官方频率。

## 发现并避开的两个类型身份陷阱

### 嵌套类型不能拿 genericContainer 当 declaring owner

已有 `_parse_il2cpp_meta.py` 的旧库存脚本把 type-definition `+24` 当 declaring 字段；实际该位置属于另一字段。新工具按已观察厂商布局读取 `+12` 的 declaring type identity，并经 canonical byval identity 找到父类型，而不是把它当 type-definition 数组索引。

因此 `ClothType` 和 `Direction` 必须分别限定为上表的嵌套类型；全局还存在其他 Direction，不能依名字混用。新工具在当前文件检查 58,110 个 type definitions，canonical byval identity 唯一，嵌套父引用可解析；有循环/歧义/未知父时停止。旧类型库存没有被覆盖；之后不要拿它的嵌套显示路径作为权威身份。

### consuming field 的 native type index 不一定等于 canonical byval

当前 `ClothSerializeData.updateMode` 的 field type index 为 111633，而枚举定义的 canonical byval 为 111631；clothType、connectionMode、direction 也出现 attribute-bearing native type variant。

本轮**没有**用“加减 1/2”把它们强行对齐。字面量与嵌套所有权已核实，但这些 field variant 的严格身份仍需要 native type registration 验证。输出保持 `attribute_bearing_native_field_types_resolved=false`。`enum_for_field` 只有 exact canonical identity 匹配时才能返回；不匹配直接拒绝，默认导出不冒充已认证该 native 引用。

这不改变上轮 prefab 外部 MonoScript 尚未精确解析的状态。metadata 的类/枚举存在，不等于特定 prefab CAB PPtr 已闭合。

## 更新链的接口证据，不是已恢复的调用图

工具读取 14 个相关类型的字段/方法声明，并校验方法所属 type definition。报告保留全局 method index、parameter count 和 token；**token 不是全局唯一身份或 native RVA**，后续须连同所属镜像/注册信息定位。

| 已观察接口层 | 直接存在的声明（节选） | 尚不能由名称推出 |
| --- | --- | --- |
| MagicaManager | InitCustomGameLoop、SetCustomGameLoop、SetUpdateLocation、SetSimulationFrequency、UseCrossFrameJob、OnPreSimulation/OnPostSimulation | 启用哪种 loop、调用顺序、实际频率 |
| TimeManager | FrameUpdate、AfterFixedUpdate、simulationFrequency、maxSimulationCountPerFrame、DeltaTime/FixedDeltaTime/UnscaledDeltaTime | 本角色运行中的计时分支和子步数 |
| ClothManager | OnEarlyClothUpdate、OnBeforeLateUpdate、OnAfterLateUpdate、CompleteMasterJob/ForceCompleteAllJob | Job 何时开始、完成、等待 |
| TeamManager | UpdateTeamAnimatorData、animatorUpdateModeMap、ShouldResetSimulationToAnimationPose、SetSkipWriting | 本角色何时重置、是否跳过写回 |
| DynamicBoneTransformManager | ReadAnimatorBufferData、WriteAnimatorBufferData、CopyDoubleBuffer、WriteDoubleBufferTransform、initLocalPositionArray/initLocalRotationArray | 缓冲区具体交换和读写时点 |
| SimulationManager | basePosArray/baseRotArray、nextPosArray/oldPosArray、dispPosArray、PreSimulationUpdate、SimulationStepUpdate、CalcDisplayPosition | 数学公式和最终显示插值算法 |
| Beyond.NPC.Animation.ClothCalculator | CalcCloth、UpdateDynamicBone、TeleportClothUseRelativeTransform、ResetCloth | 控制权重和 teleport 的实际处理 |

`NPCCPUAnimator._UpdateBeyondBoneCloth` 已定位到 metadata 全局 method index 2490，parameter count=1，token=0x060009bb。相邻还存在 `_UpdateClothCurve` 和 teleport/reset 入口。这个位置可供下阶段 native 定位，**不是已找到其函数体或调用者**。

这些声明支持下一阶段分别检查动画基础姿态、模拟状态、显示状态、跨帧缓冲和骨写回。不能把声明顺序当执行顺序；也不能只把当前 Verlet 的 Update 放到 LateUpdate，就宣布官方管线等价。

## 工具、测试和复现

新增 `Tools/export_official_physics_metadata.py`：仅支持当前观察到的 header 0x108、typeDef 92、field 12、method 32 的 v29 厂商布局，其他布局拒绝；保留原字节与偏移；不写游戏文件、不执行旧库存脚本、不需要 native 注入。

复用/适配的格式依据是本地 `Il2CppDumper-end` 与 [Perfare Il2CppDumper 的整数读取实现](https://github.com/Perfare/Il2CppDumper/blob/master/Il2CppDumper/Extensions/BinaryReaderExtensions.cs)。第三方许可说明在 `Tools/THIRD_PARTY_IL2CPP_NOTICE.txt`；没有另行引入包、复制整套反编译器或发布原游戏 metadata。

```powershell
cd 'A:/Hypergryph Launcher/games/Arknights Endfield'
python 'FractalMiner/Tools/export_official_physics_metadata.py' `
  --metadata 'Endfield_Data/il2cpp_data/Metadata/global-metadata.dat' `
  --output '<新的报告绝对路径>'
```

输出必须新建，不覆盖已有报告。当前最终证据位于：

```text
D:/EndfieldTechLib/notes/official-physics-update-mode-20261002-01/
  physics-metadata-01.json       # 原字节、偏移、字面量与接口库存
  metadata-coverage.json
  original-main-index.bin
```

报告 165,161 字节，SHA256=`dfe930b337ccf31419b8432d506457b42d334b4bbe3e5295c19aa538ef431765`。

36 项新测试，包含独立 synthetic metadata tables、1/2/4/5 字节及 signed 极值、截断/保留前缀、错误底层类型/默认记录/表范围/嵌套父身份、方法所属类型、native field variant 禁止猜测及覆盖保护。测试不是向解析器喂预期的官方枚举结果再互相证明。全套 Python 584 passed、3 项历史 skip、114 subtests passed、2 项历史 Pillow 告警；新增工具含分支覆盖率 91.80%，Ruff/Pyright/pip-audit 通过。

## 下一阶段重点

1. 用 native metadata registration 精确解析 field type variants 和 method RVA/所属镜像，然后离线检查 custom loop 注册、ClothUpdate/FrameUpdate、动画 buffer 读写和 job completion 的真正调用关系。
2. 把调用链结论与本角色 prefab 配置及实际组件身份连接起来；仍需解开外部脚本 CAB。没有函数体证据时，调用时序和频率均保持 pending。
3. 在独立适配层验证上轮 18 个额外挂点及未加权辅助骨的动态空间；保持现有 weighted bindpose、捕获姿态和 MMD 不变。
4. 最后接可切回的官方配置/最接近求解链，检查静止、旋转、下蹲、跳跃、seek、复位与固定步导出。当前 `runtime_call_order_verified=false`、`simulation_frequency_verified=false`，官方求解器仍未接入。

后续进展见 [原生字段身份与有界函数调用点](../official-physics-native-20261002/README.md)：四个 consuming field variants 已通过 native registration 精确认证，491 个非空方法入口和 30 个有界函数体已查。上述 sealed 报告保留当时的 pending 状态；新结果不等于运行时序/频率或求解器已还原。
