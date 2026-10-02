# 官方选择网格：从位置到匹配属性的可调用链

日期：2026-10-02。接续[选择生成与有序匹配内核](../official-physics-selection-20261002/README.md)。新增 `Tools/official_physics_grid.py`：在**有限数、新建、单Job顺序插入、不扩容、不删除/复用**的域内，连接目标AABB → radius/gridSize → 源点入格 → 范围枚举 → 有序候选 → 上一轮匹配内核。不再要求调用者手工提供每个目标的候选序列。不是完整原生内存分配器、SelectionData.ConvertFrom对象状态变化或Unity实时物理。

后续：[世界/局部快照及 scale](../official-physics-snapshot-20261002/README.md)已实现 getter 输出参考、逆世界旋转后矩阵对角提取及新建 selection/frame 接线。真实 Unity getter、保存 selection 分支、bindpose、完整 proxy/运行后端仍未闭合。

## 本轮落地规则

| 环节 | 已核实并实现 |
| --- | --- |
| 目标包围盒 | CalcAABBInternal method370929/RVA0x40c6080：逐点读Single坐标，以 ±float.MaxValue初始化极值；极值转换为double3存入AABB |
| 最大边长 | double3 Max-Min，取最大分量后转换Single；不能提前把三个差值都改成Single计算 |
| 半径 | Single乘0.2，与Single(1e-5)取大；gridSize再Single乘0.5，不用源包围盒或maxConnectionDistance代替 |
| 源点入格 | AddGrid调用链RVA0x407d1c0：Single除gridSize，math.floor(float3)，再Int32；负数不得直接截断 |
| 查询范围 | GetArea链RVA0x3b3588 → 0x407d2e0：先Single计算position-radius / radius+position，再逐轴除法/向下取整 |
| 格子枚举 | 构造器0x40aae90、MoveNext0x4032d00：首项直接返回下界，范围包含上界，x最快，其次y，最后z |
| 同格值序 | 插入辅助0x3cd04f0先写next=旧head，再写head=新索引；0x31a2070从head沿next走并比较全部int3分量。因此在新建/顺序/无扩容域，同格源索引逆插入顺序；跨格按格子枚举顺序 |
| 匹配 | 复用上一轮内核：距离≤radius且≤当前最近距离时完整复制Byte；等距由后遍历候选覆盖 |

原始CreateGridMapJob从源索引0递增插入；本次ConvertFrom调用CreateGridMapRun的四个包含flag均为1，不能自行过滤Invalid源点。CreateGridMapRun从源NativeArray长度把容量传给构造链。本模块声明新建/不扩容域，**没有恢复分配器、rehash、free-list、并发写入或实际泛型运行时指针**，不把这套逆序规则推广到其他网格使用方式。hash碰撞不改变同key元素的相对顺序，因为插入是头插，读取只沿next并筛选全部key分量。

五个实际RIP MethodSpec引用分别认证为GridMap.AddGrid/GetArea、GridEnumerator.MoveNext、NativeParallelMultiHashMap.ContainsKey/Enumerator.MoveNext。Unity.Mathematics.math.floor(float3)为method440532/RVA0x4084980。这是静态调用身份与标量控制流证据，不是已运行官方泛型/Burst的证明。

三个没有RUNTIME_FUNCTION条目的叶函数（范围减/加和MoveNext）通过**可达控制流**读到所有ret：拒绝间接跳转、call、重叠指令和越界控制流，不以相邻函数间距猜边界。floor的下层CRT叶入口未按这个策略闭合；本模块使用已认证math.floor的有限数向下取整契约，不声称完整CRT异常数/浮点环境等价。泛型GridEnumerator字段注册偏移检查拒绝了不支持的boxed偏移，记录为未决，不把该偏移套作实例布局。

## API与边界

`selection_search_parameters(target_positions)`计算原始标量AABB、最大边、radius和gridSize；`grid_cell`及`grid_area_cells`恢复入格/枚举规则；`build_fresh_selection_grid`恢复限定域的同格逆序；`convert_fresh_selection_grid(target_positions, source_positions, source_attributes)`串接整条标量链。

所有位置必须已经处于**原始共同匹配空间**。本模块不把恢复Unity模型的位置当成原始快照，不自动决定保存selection是否复用，不替代TransformPositionJob或Proxy_ApplySelectionJob，不在舞台上写入骨骼。

原生ConvertFrom在空source/target时退出并保留此前对象状态；此无状态组合API直接拒绝空域，**不是返回全0来冒充原生行为**。单独建空网格允许返回空映射。非有限数、Single溢出、非正gridSize、Int32越界/递增溢出均拒绝；数组65535项、单次查询4096格的限额是适配层防御，不是官方容量或异常规则。

## 验证与证据

35项新测试包含目标/源范围区别、退化包围盒半径下限、输入Single舍入、signed zero极值覆盖、负坐标、先Single除法再floor的边界、含上界且x最快、同格逆序/跨格顺序的等距覆盖、Invalid、不命中、生成→网格→匹配集成及输入拒绝。先运行缺模块失败，再实现通过。

全套 **1480 passed / 114 subtests / 3历史skip / 2历史Pillow弃用告警**；11个参考模块865语句、248分支覆盖100%。Ruff/格式检查通过，Pyright零错误/告警；临时Python工具环境pip-audit无已知漏洞。测试不是独立游戏运行oracle，没有运行Unity或改动舞台/渲染/湿身/阴影/预览物理。

私人证据在 `D:/EndfieldTechLib/notes/official-physics-grid-20261002-01/`：

- `review.py`先校验上一轮审计脚本hash，再复用源DLL/metadata保护的只读加载。
- `review-08/grid.json`、`grid-instructions.json`保存本轮函数、引用、常数、可达叶CFG与拒绝项；完整报告仅本地。
- `coverage-full-01.json`保存完整覆盖结果。精确hash及门禁见verification.json。

## 接下来直接接输入，不再重写已通过规则

1. 恢复ReadTransformInformation/ReadTransformJob的世界位置、旋转、矩阵和scale算术；核查实际普通/预建构建分支、中心、selection生成/复用及空间转换。随后生成11组真实完整proxy输入，而非把测试数据算作真实角色输入。
2. 继续默认填充、normalAxis/bindpose、collision与Team/step发布，接全积分/惯性/约束/碰撞/reset。
3. 最后在可回退Unity后端里接动作/MMD与骨写入顺序，做静止/转身/下蹲/跳跃/seek/复位/固定步导出验收。

本轮确实减少了手工输入环节，但**完整官方物理仍未接入**。参考模块覆盖率不是整体完成百分比；现有效果保持可回退。
