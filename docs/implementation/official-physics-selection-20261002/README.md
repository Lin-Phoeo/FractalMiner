# 官方骨骼物理：选择生成与有序位置匹配

日期：2026-10-02。接续[收集顺序与忽略分支](../official-physics-collection-20261002/README.md)。本轮新增 `Tools/official_physics_selection.py`，恢复生成新骨骼 selection 的标量规则，以及已保存 selection 的**有序候选匹配内核**。不是完整 ConvertFrom、空间网格或实时物理后端。舞台、模型、渲染、湿身、阴影和预览物理未改动。

## 两条路径必须区分

原始11组保存的 selection 中，`userEdit` 有7组为1、4组为0。不能把所有保存数据替换成“根骨固定、其余可动”，也不能把选择点数当作实际求解骨数。长马尾保存38点，上游 root/ignore 收集14骨，这仍然不证明原保存数据错误；需要位置匹配，而非逐槽复制。

| 组（省略 MBC_Typhoea_） | 保存点数 | 原始 userEdit |
| --- | ---: | ---: |
| Hair_Front_Bangs_Short | 15 | 1 |
| Hair_Front_Side_Long | 10 | 1 |
| Hair_Back_Ponytail_Long | 38 | 1 |
| Hair_Back_Ponytail_Knot | 24 | 1 |
| Cloth_Coat | 12 | 0 |
| Cloth_Skirt | 37 | 0 |
| Cloth_Skirt_Rope | 6 | 1 |
| Cloth_Skirt_Bag | 6 | 0 |
| Acc_Back_Left_Bag | 4 | 1 |
| Acc_Back_Right_Lantern | 4 | 1 |
| Tail | 8 | 0 |

上述 flag 是序列化事实，不等于已证明运行时每组必定走哪条分支。实际 async/prebuilt/普通构建分支及选择复用条件仍待接通；`userEdit=0` 不能单独作为强制重建依据。

## 新选择的生成规则

`ClothProcess.GenerateBoneClothSelection` method368604 / RVA0x59dff84，完整函数体1275字节，规则已实现为 `generate_bone_selection`：

1. 仅取 `RenderSetupData.skinBoneCount` 个骨骼，不包含最后追加的 renderTransform 槽。
2. 用其保存的 worldToLocal 对每个世界位置作点变换，写入 render-local 选择位置；初始属性都是 Move(2)。
3. 对每个有父骨的顶点计算**局部选择位置**的 Single 欧氏距离；所有父边的最大值写入 maxConnectionDistance。不是累计链长、世界距离、包围盒宽度，也不只统计 Move 边。
4. 从原始 rootBones 的有效对象身份查索引，把显式根改为 Fixed(1)。不是把所有 parent=-1 的顶点固定；原程序跳过 null/destroyed 根。
5. 新 selection 的 userEdit 无条件置 true。该函数只能生成新对象，不是“覆盖人工数据”的授权。

`GetParentTransformIndex(index, true)` method370206 / RVA0x346ff20 使用 parent 实例ID在 transform ID 列表中 IndexOf；若找到的是 render 槽则返回-1。`GetTransformIndexFromId` method370205 / RVA0x5a51ef0 也使用 runtime Int32 ID查找，不能把原始PPtr Int64直接代入。List.IndexOf 的重复值语义是第一次命中；现有独立ID适配层的重复ID拒绝策略不能冒充这里的原始行为。

两处 List 泛型调用和四处 VertexAttribute 静态引用已沿实际 RIP metadata usage 解析身份。VertexAttribute 静态构造器 method371648 / RVA0x49ef750 写入 Invalid=0、Fixed=1、Move=2、DisableCollision=0x10。本模块完整保留源 Byte，未把全部flag归约成固定/可动。

## 保存选择的匹配规则与边界

`SelectionData.ConvertSelectionJob.Execute` method369329 / RVA0x5a1a30c，完整944字节，内循环已实现为 `convert_selection_attributes`：

- 每个目标先置 Invalid(0)，最近距离初始化为 Single float.MaxValue，不沿用旧目标属性。
- 遍历调用者提供的**原始空间网格候选顺序**。计算 Single 距离；距离同时 ≤ radius、≤ 当前最近距离时，完整复制源属性 Byte。
- **等距时后遍历候选覆盖先遍历候选**。不能排序候选、优先固定点、按名字匹配或只看数组索引。
- 源 Invalid(0)也可赢得匹配；没匹配到保持0，而不是默认 Move。
- 距离辅助函数及两段无 unwind 条目的直线叶函数已检查：Single减法，点积顺序 `(y*y + x*x) + z*z`，随后 sqrt。叶函数只接受白名单直线指令并读到 ret，没有用相邻函数距离猜边界。

调用者必须先提供同一匹配空间中的位置、原始候选索引序列和半径。本模块**不创建网格、不猜 NativeMultiHashMap 枚举序、不扫描所有源点补候选、不执行坐标准备 Job，也不选择运行时分支**。因此目前不能声称11组真实属性缓冲已生成。

`SelectionData.ConvertFrom` method369326 / RVA0x5a1f270 的半径准备已静态核实：调用 AABB.get_MaxSideLength（method371097 / RVA0x5a812cc），取得 Single 返回值，乘 Single(0.2)，下限 Single(1e-5)；gridSize 是该 radius 乘 Single(0.5)。四个常数均按实际 RIP 引用读取，不是经验参数。**radius 与 selection.maxConnectionDistance 不是同一值。** AABB字段是 double3 Min/Max，不可未经核查改成另一种float包围盒算术。完整 AABB 构建和空间网格尚未移植，本内核仍要求上游传入原始 radius；这些证据不构成完整 ConvertFrom 一致性证明。

适配层额外拒绝非有限数、损坏矩阵/森林、越界索引和超容量输入，skin/source/target各设65535安全上限。None根表示上游已经判定需要跳过的无效根；没有恢复 Unity destroyed/null 运算本身。这些防御不是官方异常、容量或非有限数语义。

## 中心与世界快照的静态进展

普通构建路径的证据已连上：

- ClothProcess.Init 在 RVA0x343ac30 调用已认证的 Component.get_transform，交给 TransformRecord 构造器，再保存到 clothTransformRecord。
- CreateBoneRenderSetupData 从该 record.transform 读取并作为 renderTransform 传给 RenderSetupData 构造器。**普通路径中心源是布料组件自身的 Transform。**
- RenderSetupData.ReadTransformJob method370212 / RVA0x5a631e4 调用已认证的 TransformAccess.get_position、get_rotation、get_localToWorldMatrix、get_localPosition、get_localRotation。
- scale 缓冲由世界矩阵与逆世界旋转相关矩阵运算取出，不是简单照抄 get_localScale；这段矩阵算术尚未移植，不用近似的 lossyScale 代替。

以上仅证明静态身份与普通路径数据流。真实11组在游戏中实际走普通还是预建路径、对应时刻世界pose/矩阵、转换空间和最终proxy输入仍未恢复。[上一阶段的离线收集报告](../official-physics-collection-20261002/README.md)中 center 仍是占位参数；没有追溯修改那个报告，或把静态来源证明升级为已捕获的实际快照。

## 验证与复现

42项新测试覆盖局部矩阵/Single舍入、最大单边、显式根、父先后/重复根/null占位、无父节点、空域、最近点、半径边界、等距覆盖、Invalid/完整flag、缺候选、生成后匹配和适配层拒绝。先执行缺模块失败，再实现通过，补齐 Int32 防御分支。

全套 **1445 passed / 114 subtests / 3历史skip**，10个参考模块800语句、232分支覆盖100%。历史Pillow弃用告警2条。Ruff与格式检查通过，Pyright 0 errors / 0 warnings；本轮临时工具环境 pip-audit 无已知漏洞，不代表全Unity依赖审计。

私人证据目录：`D:/EndfieldTechLib/notes/official-physics-selection-20261002-01/`。

- `review.py`：校验源DLL/metadata SHA256后进行离线读取，不执行原始DLL。
- `review-08/review.json` 与 `instructions.json`：认证签名、字段、函数边界、引用身份、常数、辅助叶函数和拒绝项。哈希见 verification.json；完整指令仍只留本地。
- `coverage-full-02.json`：完整测试覆盖报告。

`VirtualMesh.ApplySelectionAttribute` 本次因指令解码不完整而拒绝；不使用部分body证明完整应用链。CalcAABBJob 包装体虽已完整读取，其计算辅助体/实际Job执行仍未闭合。未做 Unity 动态验收、独立 native/Burst oracle，未发布游戏原始资源或商业组件源代码。

## 下一步与完成边界

按依赖继续，不倒回已验证的收集/depth/angle规则：

1. **接完真实输入**：AABB计算、网格构建与枚举、空间变换和选择生成/复用分支；恢复世界快照/scale/bindpose、默认填充、normalAxis、collision参数、Team/step发布。完成后才生成11组真实完整proxy输入。
2. **接完求解**：积分/惯性、剩余约束与执行依赖、碰撞、reset/seek；不靠添加几个预览参数冒充原版求解器。
3. **接入Unity并验收**：保留可回退后端，确保动作/MMD/物理/骨写入顺序与单写入者；跑静止、旋转、下蹲、跳跃、seek、复位和固定步导出。

目前完成的是离线源规则与参考实现，不是官方完整实时物理。参考模块覆盖率不能转换成项目完成百分比；现有舞台效果继续保留。
