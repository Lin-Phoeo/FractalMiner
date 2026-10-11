# 官方物理：Line邻接、Distance缓存与步进工作列表生产

日期：2026-10-11。接续[baseline/局部姿态/root-depth生产](../official-physics-baseline-production-20261011/README.md)，本轮恢复普通BoneCloth零三角形Line路线的双向邻接、Distance约束缓存，以及由**给定Team数据**生成粒子/baseline步进列表的有限参考。**这关闭的是输入生产算法和11组局部缓存，不代表真实Team已分配，也不代表官方实时物理已接入Unity。** 原舞台、渲染、湿身、阴影和当前预览物理均未修改。

## 本轮真正完成的内容

新增：

- `Tools/official_physics_distance_inputs.py`：按原Line Job生成双向去重邻接，按原Distance `CreateData`生成high12数量/low20起点、UInt16邻点及带符号静止长度。
- `Tools/export_official_physics_distance_inputs.py`：严格复算并比对上游完整baseline文档，以三份SHA256封印输入独占导出11组实际局部缓存。
- `Tools/official_physics_work_lists.py`：对**调用者提供的稀疏Team槽、flag和全局chunk**生成粒子列表及packed baseline列表。两种列表的跨Team块顺序分别显式给出，不假装原子并行顺序相同。

本地最终实际输出：`D:/EndfieldTechLib/notes/official-physics-distance-production-20261011-01/eleven-distance-02.json`，SHA256 `939bc3d178a7cfa07f86cb757989e99f7b9149cf01e2920441d47e4c7abf2d3f`。每个参考状态11组、140顶点、109条Line；双向graph共218项，属性门禁剔除40项，长度门禁前178项，长度门禁再剔除2项，最终176项。两个状态合计352项；全部是父子正静止长度，没有横向负长度。Skirt的12↔13为零长边，每状态双向两项在严格`distance < Single(1e-6)`门禁被剔除。旧`eleven-distance-01.json`保留为历史，不覆盖；最终统计字段为`pre_length_entry_count`，明确表示长度过滤前数量。

| 11组每状态 | Line | Distance项 |
| --- | ---: | ---: |
| 短刘海 | 10 | 10 |
| 前侧长发 | 8 | 12 |
| 后长马尾 | 12 | 24 |
| 马尾结 | 22 | 24 |
| 外套 | 6 | 12 |
| 裙摆 | 30 | 58 |
| 裙绳 | 4 | 8 |
| 裙包 | 4 | 8 |
| 左后包 | 3 | 2 |
| 右后灯笼 | 3 | 4 |
| 尾巴 | 7 | 14 |

## 原结构与顺序规则

1. **Line图不是“直接把parents抄成约束”。** 原`Proxy_CalcVertexToVertexFromLineJob.Execute`按Line原序对两个方向分别做`UniqueAdd`；重复项丢弃，新项插链首。当前普通BoneCloth由child升序生成`min(parent,child),max(...)`的109条Line。fresh builder容量`4*n`，当前森林双向项严格小于容量，不触发rehash。
2. **两次链首插入恢复原发布行序。** `MultiDataBuilder<UInt16>.ToNativeArray`直接按链枚举行；实际泛型`ConvertArrayToMapJob<UInt16>.Execute`已由IL2CPP methodSpec/genericMethodTable定位到method 370956、RVA `0x40da1d0`，按row升序、row内packed数据升序再次Add到链首，反转一次。Distance临时正/负表再链首插入一次，因此最终每个相位的输出顺序回到已发布graph行序。正父子相位整体先于负横向相位，不能排序、按索引重建或改成无序集合。
3. **Distance门禁和精度单独保留。** 一条有向邻接仅在至少一端`Move(bit2)`且两端都不是`Invalid((attr&3)==0)`时进入临时表；第一阶段不按pair集合去重。父子关系（任一端是另一端parent）进正表，其余进负表。长度使用float3 Single减法、`(y²+x²)+z²`逐步Single及Single平方根；严格小于`Single(1e-6)`才剔除。这个阈值不是求解器的Double长度`< Single(1e-8)`门禁。
4. **null与allocated-empty不同。** 属性门禁后临时项总数为0时三份输出保留默认null；只要临时项非0，即使全部短边被长度门禁剔除，也发布长度为顶点数的packed index及空data/distance数组。零三角形路线仍创建空`edgeToTriangles`容器；查询返回count0，`count<2`使附加shear阶段不产生邻接，不能把它描述成“未创建容器”。

上述顺序结论限定fresh、串行、无删除、无扩容的当前参考路线。通用重复邻接会保留到Distance第一阶段；适配器在超过已静态证明的容量时拒绝，而不是猜测rehash后的顺序。

## 工作列表的正确边界

`CreateUpdateParticleList`的当前恢复范围不是11组真实Team发布器。原逻辑：Team 0先跳过；随后要求`IsProcess`、`IsRunning(0x20)`、`IsStepRunning(0x80)`，合并为必须位`0xa2`，并排除`0x2000000000080810`。符合条件的Team把**整个particleChunk**按全局槽升序加入粒子列表，不按Move/Fixed/root/Invalid预过滤；消费者自行门禁。baseline也加入整个全局chunk，编码为`high16 Team | low16 GLOBAL baseline`，保留low16截断和signed Int32位模式。

原两个列表各有独立原子计数器，同一Team内块连续升序，但不同Team在两份列表中的并行块顺序可不同。有限API因此要求分别给`particle_team_order`与`baseline_team_order`；相同非零Team多重集、非负Int32 chunk等是明确的安全适配器策略，不冒充native畸形输入行为。当前11组还没有经证据闭合的Team ID、global chunk起点、运行flag和TeamStep时钟，所以实际导出仍写明`real_constraint_work_lists_generated=false`。

`build_step_work_lists`还要求调用者显式传入`particle_output_capacity`和`baseline_output_capacity`。两份输出总长度先检查容量，再生成任何prefix；不足时拒绝，不擅自扩容，也不根据最大Int32合法chunk自动物化巨型Python元组。容量策略是本地安全边界，不是对原allocator或实际数组容量的观测。

## 原始证据、测试与未完成项

静态读取固定SHA256的原GameAssembly与metadata，未加载/执行DLL、未启动游戏、未附加进程。关键身份包括：Line Job method 371599/RVA `0x4310a70`；Distance `CreateData` method 368867/RVA `0x37e7bb0`（6592字节，6536代码+56字节两个跳表）；转换泛型method 370956/RVA `0x40da1d0`（完整CHAININFO家族36+147+10=193字节）；work-list ordinary单槽method 370620/RVA `0x5a6f838`与实际managed fallback method 370422/RVA `0x5a58a28`。另复验Distance实际caller的`IJobExtensions.Run` spec514571及51个helper/8655字节。Run内部仍有运行时解析的间接调用，不把静态闭合体认证冒充原Job实际执行。完整证书、指令锚点和原数据只保存在本地证据目录，不提交原二进制或完整反汇编。

TDD保留两个缺模块RED、中间lint/type失败，以及审查后容量/统计命名修复的RED。最终`checks-07.json`专项96项通过；完整4169项通过、114项subtest通过，3项历史skip、2项历史Pillow告警。三个新增模块205语句/78分支均为100%覆盖；Ruff、Black、Pyright、compileall通过，实际工具环境依赖审计为0个已知漏洞。独立校验器不导入生产模块，从三份封印输入复算22组实例/218条Line/436 graph项/356长度门禁前项/352最终Distance项，与实际输出的完整结构、类型、顺序和浮点位模式一致。证据索引、实现SHA256和边界声明见本目录`verification.json`。

尚未完成：真实Team/particle/global chunk分配与原生命周期、10个step计数器/数组容量和尾部语义、所有当前启用兄弟列表、NativeArray发布、Job/Burst实际调度、骨骼唯一writer，以及Unity候选后端。当前工作列表模块是给定Team表的算法参考，不得被包装成“11组真实work-list已生成”。

下一单元应从真实参数转换与Team创建/注册入口恢复11组TeamData和global chunk布局，随后将已闭合的local proxy/baseline/Distance输入接进统一粒子初始化。只有在所有启用分支能生成或显式拒绝后，才进入可回退Unity后端并用MMD/解包动作做可见动态测试。
