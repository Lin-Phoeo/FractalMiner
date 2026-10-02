# 官方骨骼物理：收集顺序与忽略分支

日期：2026-10-02。接续[骨骼导入的位置与方向](../official-physics-bone-import-20261002/README.md)。本轮实现 `Tools/official_physics_collection.py`：恢复**有效、存活的骨骼引用域**内的上游收集规则，用原始11组root/ignore和原始556个Transform的孩子顺序进行离线回放。不是完整proxy生成器或官方实时物理。舞台、模型、湿身、阴影、渲染和当前预览物理均未改动。

## 关键纠正：导入Job不是收集器

方法签名、字段身份和直接调用点共同确认：

- `VirtualMesh.ImportBoneType(rsetup, transformIndices)` method371507/RVA0x3471d40的第一个参数是 **RenderSetupData**，不是TransformData。传入的是已收集好的世界快照、变换矩阵及列表。
- `VirtualMesh.ImportFrom` method371504/RVA0x39d2f80先调用TransformData.AddTransformRange，再把返回的映射数组交给ImportBoneType；不能把runtime Int32 ID、原始PPtr Int64和列表索引混为一谈。
- 真正的root/ignore收集发生在 `RenderSetupData` 七参数构造器 method370195/RVA0x38d4a50。`ClothProcess.CreateBoneRenderSetupData` method368543有直接构造器调用。

## 原始收集控制流

| 步骤 | 已核实行为 |
| --- | --- |
| 输入 | 原始rootTransforms、ignoreFromRootBones、collisionBones和renderTransform；render空/无效或root为空时原构造器失败 |
| 栈初始化 | 按root列表原序Push，因此最后一个root先Pop；不排序、不改成BFS |
| 访问 | 已收集对象先跳过；随后命中ignore则跳过该节点，且不展开子树 |
| 保存 | 先记当前输出索引，再Add对象、Dictionary.Add；仅收集一次 |
| 子节点 | `get_childCount`、`GetChild(i)`从0递增，逐个Push；出栈时最后一个孩子先处理 |
| 根引用 | 另按原序保留root实例ID列表，包括重复root和被ignore的root，不从收集结果重建 |
| collisionBones | 收集完成后按输入序IndexOf；null项跳过，未收集对象记-1；此时还没追加render |
| render | skinBoneCount与renderTransformIndex都取收集数量，然后无条件Add render，即使它已经被收集；此后的世界快照读取尚未移植 |

11个泛型MethodSpec的tagged metadata usage已沿实际RIP引用解析到List.GetEnumerator/Enumerator.MoveNext、Stack.Push/Pop、Dictionary.ContainsKey/Add、List.Contains/Add/IndexOf的原定义。两个icall字符串直接指向UnityEngine.Transform孩子访问API。这些是**静态调用身份和控制流证据**，不是泛型运行时地址、Job执行或Burst一致性证明。

适配层采用 `(serialized file, signed Int64 PathID)` 代表已解析对象身份，不按名字去重，也不把PathID截成runtime instance ID。有效存活对象域之外的Unity destroyed/null比较语义尚未恢复。输入shape/引用校验及总65536槽容量上限属于适配层防御，不冒充官方异常或原始容量。

## 原始11组离线回放

保留原Transform孩子顺序、不加入恢复模型的Armature包装、不以骨名排序。仅公布数量；原始对象、列表、原生指令和完整回放输出仍留本地。

| 组（省略MBC_Typhoea_） | root/ignore收集骨数 | 保存的selection点数 |
| --- | ---: | ---: |
| Hair_Front_Bangs_Short | 15 | 15 |
| Hair_Front_Side_Long | 10 | 10 |
| Hair_Back_Ponytail_Long | **14** | **38** |
| Hair_Back_Ponytail_Knot | 24 | 24 |
| Cloth_Coat | 12 | 12 |
| Cloth_Skirt | 37 | 37 |
| Cloth_Skirt_Rope | 6 | 6 |
| Cloth_Skirt_Bag | 6 | 6 |
| Acc_Back_Left_Bag | 4 | 4 |
| Acc_Back_Right_Lantern | 4 | 4 |
| Tail | 8 | 8 |
| 合计（逐组相加，非跨组去重） | 140 | 164 |

因此**164个保存选择点不是164个实际收集骨骼**，更不是164个已验证可动物理粒子。长马尾的ignore分支会剪掉一部分骨链，不能按38直接构造proxy或逐槽照搬selection属性。这不证明保存selection错误/过期；其空间匹配、选择生成/复用路径仍需核查。

回放用component owner作为**未验证的center占位参数**，只验收之前的root/ignore骨序；没有把它冒充已捕获的TransformRecord。collisionParentBoneList也尚未与实际调用参数接通。因此 `actual_eleven_full_proxy_inputs_generated=false`，世界pose、runtime IDs、selection属性、normalAxis、bindpose与Team缓冲仍未生成。

## 验证与证据

30项新测试：两级LIFO、忽略子树、显式后代root、重叠/重复root、所有root被忽略、render重复追加、collision查找时机与null/missing处理、跨文件同PathID、caller数据不变、引用/容量拒绝。先执行得到缺少模块的失败，再实现通过。全套 **1403 passed / 114 subtests / 3历史skip**；9个参考模块743语句208分支全部覆盖。历史Pillow弃用告警2条；Ruff/format、Pyright和临时环境pip-audit通过。测试与离线回放不是官方引擎运行oracle；未做Unity动态验收。

私人证据目录：`D:/EndfieldTechLib/notes/official-physics-collection-20261002-01/`：

- `review-04/review.json`、`instructions.json`：认证类型、参数签名、精确unwind/CHAININFO函数边界及实际引用身份；校验值见verification.json。
- `review.py`：源DLL/metadata哈希保护的静态重跑脚本；只读源文件、不执行DLL。
- `original-order-01.json`、`collect_original.py`：原始绑定哈希保护的11组有序回放；center验证、snapshot/selection/full proxy各项明确false。
- `coverage-full-01.json`：完整回归覆盖报告。

`PreBuildDataConstruction`的本次原生检查因不完整指令解码而拒绝，没有拿相邻函数间距或部分body补成证明。该缺口与世界快照、泛型fill Job、实际step调用等继续保持pending。

## 剩余主线（不要把参考模块数量当完成百分比）

1. **真实输入闭合**：CreateBoneRenderSetupData的TransformRecord来源/调用参数，ReadTransformInformation世界快照，GenerateBoneClothSelection及selection复用/空间匹配，属性、法线轴、默认填充Job、scale/bindpose、Team/step发布。已有collector、ID映射、pose/depth/angle参考不重写。
2. **完整求解闭合**：积分、惯性、完整约束依赖、碰撞接入、reset/seek状态；目前不是差一项参数即可结束。
3. **实时输出闭合**：可切回的Unity后端、骨骼单写入者，与解包动作/MMD的更新次序，静止/旋转/下蹲/跳跃/seek/复位/固定步导出验证。现有预览效果保留作回退，不称其为原版求解器。
