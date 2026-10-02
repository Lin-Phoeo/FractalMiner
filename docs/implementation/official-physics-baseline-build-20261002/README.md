# 官方物理：Transform baseline生成控制流

日期：2026-10-02。接续[单baseline角度调用层](../official-physics-angle-baseline-20261002/README.md)。新增 `Tools/official_physics_baseline_build.py`：输入**已经正确映射的原始有序根列表、原始子表枚举结果**，离线生成四个baseline数组。不是完整proxy生成器、Mesh baseline生成器、实时Job调度器或Unity物理后端。当前舞台、渲染、湿身、自阴影及预览物理保持不变。

后续：[proxy分组输入与局部姿态链](../official-physics-proxy-chain-20261002/README.md)已复核转换入口的骨/网格分支、实现ID映射、限定fresh/no-resize子表顺序及局部pose；没有据此宣称全部真实proxy输入或实时后端成立。

## 已确认的生成规则

这次从原始 `VirtualMesh.CreateTransformBaseLine` 控制流确认，而不是根据骨名或骨架外观猜测：

1. 按 `TransformData.rootIdList` 的枚举顺序逐根处理，每根有独立候选栈。候选栈和组内栈均是末项pop的 **LIFO**；子表枚举顺序不能排序。
2. 候选节点只按 `attribute & 2` 判断Move。Move候选直接跳过其整棵子树；非Move不等同于必须有Fixed标志，值0也能成为候选。
3. 非Move候选有直接Move子节点时，生成**一个**baseline，以该候选自身为首项，然后仅沿Move子节点深度遍历。
4. 候选没有直接Move子节点时，才把它的非Move子节点按子表枚举顺序压入候选栈，向下继续找组首；叶节点不凭空生成一项baseline。
5. baseline开始后，不跨非Move节点，也不另外搜索非Move兄弟/后代。相关节点如另有显式root输入，才可能独立生成组。不能“固定节点拆分整棵树”来替代这条规则。
6. 任一实际纳入节点（包括首项）不含attribute mask128时，组flags置最低位（数值1，IncludeLine）；被排除节点不贡献该flag。
7. 原始根列表顺序、重复根都保留。控制流未见跨根全局去重；本参考也不添加这种去重。**这不证明真实角色有重复根、共享可动点或并行写入安全。**

因此，对于这一生成路径的有效输入，生成首项确实非Move，其余项都是Move。这解释了角度kernel预处理只按首slot跳过父边缓存、求解只按Move过滤的配合；不是给kernel补一个不存在的“首项永不求解”规则。此结论不推广到Mesh生成路径或任意外部baseline数组。

## 证据边界

GameAssembly SHA256 `c24495e51b406f03b03890c4788ee618ae022c991405be5d5b8b787cb775ae89`；metadata SHA256 `0076743397acadf03d3b0064343a963c7c88863b8160526d397e4b3efb96f02e`。原始文件和完整指令仅留本地，不上传GitHub。

入口认证：`BeyondDynamicBone.VirtualMesh` / method371533 / `CreateTransformBaseLine` / RVA0x37e9610。PE unwind精确范围 `[0x37e9610,0x37ec254)` 共11332字节，body SHA256 `988c8e83ae7e8e05f49548b976c41075502fc06fd2141516f006746602fea2e6`。

此前complete-01/02把尾部数据当指令，完整解码门禁拒绝了**同一个Transform方法**，并非两个生成函数都失败。complete-03将前11192字节完整代码与末140字节分开认证：末尾是五张各7项、28字节的image-RVA表。每张对应cmp eax,6 / ja保护、表加载及jmp rdx；35项全部落在已解码代码的指令边界内。它们是编译器metadata usage初始化分派，不是物理规则。该分段是针对当前hash的人工复核，**不是通用自动CFG算法、每个分支可达性或实际运行证明**。

主要语义锚点（RVA，仅导航，不发布完整指令）：

| 原始位置 | 已复核用途 |
| --- | --- |
| 0x37ea6ba–0x37ea79c | transformData.rootIdList枚举，随后将该root ID映射成局部vertex索引 |
| 0x37ea7a3、0x37ea8ac–0x37ea8e6 | 每根清候选列表、从末项pop |
| 0x37ea9d6、0x37eae5f | Move候选跳过；直接子Move检测 |
| 0x37eb392–0x37eb414 | 没有直接Move时，只压入非Move子节点继续候选搜索 |
| 0x37eb4b7–0x37eb52e | 清组内列表、压入非Move候选首项、记录UInt16 start |
| 0x37eb569–0x37eb626 | 组内末项pop、追加UInt16 vertex、UInt16 count递增 |
| 0x37eb667–0x37eb670 | 任一纳入节点缺mask128则flags OR1 |
| 0x37ebc18–0x37ebc9a | 组内仅压入Move子节点，非Move直接继续枚举 |
| 0x37ebd0b–0x37ebe93 | 发布flags/start/count/data到VirtualMesh四个字段 |

另认证并完整有界解码三个入口：CreateMeshBaseLine method371532/RVA0x5a93958/3607字节；DoBaseLine_Bone_CreateBoneChildInfo method371534/RVA0x40da320/125字节；CreateBaseLinePose method371535/RVA0x3ddadd0/440字节。**完整解码不等于这三者的全部语义已恢复。**

ChildInfo循环按vertex索引递增处理，只对非负parent传入 `(parent, UInt16 vertex)` 给child-map插入调用；没有属性过滤。但**插入顺序不自动等于哈希表枚举顺序**，泛型容器插入/枚举全部行为尚未证明。因此本API明确要求有序子表作为输入，拒绝自行按骨架/parent升序补表。

新认证 `TransformData` 对象字段：idArray@96、parentIdArray@104、rootIdList@112；`VirtualMesh` 的attributes@56、transformData@320、vertexParentIndices@576、vertexLocalPositions@624、vertexLocalRotations@640，四个baseline字段@672/@688/@704/@720。父表由transform ID映射产生；这些字段是**对象偏移**，不能当unboxed值类型偏移。ID映射及属性生成没有包含在本模块内。

CreateBaseLinePose按baseLineData长度启动另一任务，并分配vertexLocalPositions/Rotations；这轮未恢复它的局部pose算术。补充审查ConvertProxyMesh method371526/RVA0x3ddaf90时，整范围指令解码门禁仍拒绝；已保存失败结论，**未据部分指令宣布Mesh/Transform自动选择规则成立**。

## API与适配器约束

```python
built = build_transform_baselines(
    parents, attributes,
    ordered_local_roots,      # 已从原始rootIdList映射，保留原顺序/重复
    ordered_children,         # 每vertex的原child-map枚举结果，非按id重排
)
# built.flags / built.starts / built.counts / built.data 均为immutable tuple
```

返回可供 `resolve_baseline` 使用的局部数据；调用者仍需真实Team数据窗口和全局baseline ID。集成测试覆盖非零team、proxy/particle/data起点，组首不是vertex0的情况。parents只用来验证子表与原父表对应；本模块不会拿parents偷偷生成另一套枚举顺序。

适配器预先检查等长buffer、Int32 parent、Byte attribute、UInt16 vertex、子表完整且无重复/错父及全图无环。允许任意负Int32 parent作为无父节点、显式根不必parent=-1。图验证用迭代而非递归，65k长链不受Python递归深度限制。

原生start/count/vertex会截为UInt16；本参考拒绝无法表示的vertex/start/count，不模拟危险的回绕。最大vertex65535允许；count65535允许、65536拒绝；start65534且count2允许，**不能误把end或总data长度也强制≤65535**。检查全图包括不可达节点、拒绝坏输入及失败不发布部分输出，是适配器安全策略，不冒充官方异常/上游验证。

## 验证与后续

先新增测试取得缺模块RED，再实现。307个新合成用例包含全部256种attribute、两种LIFO、原子表顺序、Move候选跳过、固定子树不跨越、重复根、IncludeLine、索引错误、无环/完整性、UInt16边界和现有角度adapter集成。全套 **1217 passed /114 subtests /3历史skip /2历史Pillow告警**；五个参考模块508语句、138分支，覆盖100%。Ruff/format通过、Pyright零错误零告警；临时Python工具环境pip-audit无已知漏洞，新增代码/测试未发现密钥模式。

测试是合成控制流和模块接线验证，**不是官方DLL/Burst执行oracle、逐位运行等价或实时效果验收**。没有改Unity代码/资产，没有启动Unity/游戏、执行原DLL、附加/注入进程。基于测试驱动与验证技能完成并复核，未引入新运行时依赖。

下一阶段按证据顺序推进：

1. 核清ConvertProxyMesh精确代码/数据边界及生成路径；恢复ID映射、属性来源与真实child-map枚举，验证实际11组输入，而非用升序/骨名猜顺序。
2. 恢复局部pose/root-depth生成、Team缓冲及baseline step发布，再检查shared root、Job依赖和真实Burst目标。不能因为单组控制流正确就默认多组并发安全。
3. 继续积分/惯性、碰撞、reset、最终骨骼写回；完整后才做可切回Unity后端及静止、转身、下蹲、跳跃、MMD倒拖/循环/固定出帧验证。

本轮主HEAD/主index及七项runtime保护值保持，用户修改的舞台按新hash保护，不恢复历史场景。新参考不含提弗洛斯骨名，供后续其他角色共用；真实绑定/坐标系仍须单独适配。机器摘要、私有证据路径/hash及未完成声明见verification.json。
