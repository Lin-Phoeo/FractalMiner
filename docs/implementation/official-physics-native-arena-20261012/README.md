# ExNativeArray空闲区账本：合并、尾部回缩与切分复用

2026-10-12，承接 `1885ebb`。生产参考 `Tools/official_physics_native_arena.py`。本单元实际实现有序free-list和useCount的有限逻辑，并将上一单元的十四Transform arena移除描述连接到各自独立账本；**不是原生内存分配/释放、数组扩容、NativeArray发布或Unity接入**，现有舞台效果保持。

## 原逻辑，不换成通用分配策略

| 方法 | 已恢复成功路径 |
| --- | --- |
| AddEmptyChunk / method371330 | 非正length早退；当前序找第一个end==新start的前块，RemoveAtSwapBack并合并；再按交换后的序找第一个start==新end的后块，RemoveAtSwapBack并合并；追加新块到列表末尾。不排序、不递归重扫，不合并重叠区 |
| GetEmptyChunk / method371329 | 非正request或无fit返回packed零chunk(0,0)；从当前序第一个fit取槽，exact用RemoveAtSwapBack移除，大块从前端切出request并在同一索引写回剩余块。不先找后面的exact、不做best-fit，不更新useCount |
| Remove / method371317 | 正length先AddEmptyChunk；仅在**传入原chunk的start+length**等于当前useCount时，先置0再取所有free chunk的最大**start**。不是最大end、活动元素总数，也不是用合并后的chunk.end判断。保留尾部空闲span供之后复用 |

private source里List<DataChunk>.Enumerator的Current位于+0x10，Remove局部enum从rsp+0x40开始，所以rsp+0x50读的是current.start。已独立核查MoveNext的原写入；不能凭字段名或高层猜测将其改成end。GetEmptyChunk只是内层选槽，外层AddRange的count增长/物理capacity处理尚未移植。

API使用显式 `ArenaState(use_count, empty_chunks)` 和 `ArenaChunk(start,length)`，没有空闲列表或计数默认值。输入正窗口要求非负、不溢出Int32；free capture完整验证、私有copy与原子错误拒绝是适配器策略，不声称原生非法输入、overflow、异常部分写入或并发等价。无效length/request路线不读取未选state/start。遵循原free列表顺序及交换删除导致的顺序变化，不增加未经证实的active-allocation字典；free span可延伸到已回缩useCount之外。

`apply_transform_arena_removals` 按上一单元十四操作原序更新十四份显式账本，缺一份输入报错，不借用其他数组的count或默认为0。它不执行RemoveAndFill中的内存fill或TransformAccess调用，不把旧 `native_allocator_applied=false` 改成true，不证明移除后的pose物理字节保留。

## 源身份与独立参照

从当前generic method table/MethodSpecs/pointer slots解析四份已选classInst的16个方法实例，认证原12个exact family3147字节，加上交换删除family258字节，共13个family3405字节、22个指令点和5个回调方法身份。合并包含冷分支的CHAININFO，不从邻近函数猜范围；具体地址/片段SHA保持私有证据。

关键根：AddEmptyChunk `0x359fb40`（311字节family，含`0x4b4256a`冷段）；GetEmptyChunk `0x35a0a80`（210字节）；matrix实例对应 `0x35a1190`（403）与`0x35a0830`（291）；共享Remove `0x7592e3c`（276），matrix Remove `0x75a3d0c`（347）。开放泛型definition中的零offset不当具体实例布局证据。

删除方法身份为MethodSpec515872 / method434698 `Unity.Collections.ListExtensions.RemoveAtSwapBack`，根`0x35a0730`，完整family258字节。原指令先get最后一项、set到选中索引，再对最后索引调用标准RemoveAt；不是稳定删除。

独立 `verify_source.py` 不导入生产reference，直接复读封印DLL/metadata并建立受限原指令解释器，执行AddEmptyChunk/GetEmptyChunk的有限控制路径。List get/set/Add/RemoveAtSwapBack是显式合成回调，初始化/异常/GC/runtime未模拟；五个回调身份及交换删除原指令另行认证。以固定seed生成1000组有序列表与请求的V2 oracle；Remove尾部count用独立认证的Current.start布局复算，**不是整份Remove指令或native runtime执行**。

另由 `check_oracle.py` 导入生产参考，仅做比较，V2的1000组合并列表、选槽/切分列表、原useCount保持和尾部count全部相同。oracle生成端与比较端分开，不能以生产代码自己生成expected。fixture包含有界非canonical列表/计数，不代表观测到的游戏运行状态。完整原资产、指令及fixtures在 `D:/EndfieldTechLib/notes/official-physics-native-arena-20261012-01/`，SHA见本目录verification.json。本轮没有独立代理语义审阅。

## 提交前纠错与旧证据作废

初稿生产代码和独立解释器的外部回调都误用了稳定删除，所以初版1000组通过是共同错误造成的假阳性，不能证明官方语义。方法身份复核发现交换删除后，先新增两项暴露顺序差异的测试并观察RED，再修生产代码和回调、认证原删除方法、重新生成V2并比较通过。旧`source-verification-01.json`、`source-oracle-01.json`、`reference-comparison-01.json`保留以记录纠错，但其语义结论已作废；当前有效参照仅为对应`-02.json`。`source-audit-01.json`的原身份/字节审计仍有效。本次纠错发生于该单元首次提交之前。

## 验证与下一步

先观察缺模块collection RED，随后观察两项交换删除语义RED；最终39项新测试及新模块84语句/34分支100%覆盖通过。全套4729项和114 subtests通过，3项历史skip、2项历史Pillow警告；生产/测试文件Ruff、Black、Pyright、compileall和测试环境pip-audit通过。

11组/164保存点、7个runtime文件、9557项主index与主HEAD保持。本轮无Unity新可见效果，不能据账本数学或测试数量称“官方物理完成”。

下一步沿AddEmpty wrapper指向的实际AddRange producer补count增长、capacity/Expand与typed Fill；之后连接十四数组真实注册/复用、component arena和完整Team teardown。native Job/GCHandle、真实Animator record/TRS和可回退C#候选仍未闭合；整体以 [PROGRESS.md](../official-physics-animator-buffer-20261003/PROGRESS.md) 为准。
