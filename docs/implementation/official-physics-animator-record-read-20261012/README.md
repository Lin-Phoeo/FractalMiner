# Animator共享record → 读取端：有限数据接线

日期：2026-10-12。承接记录分支 `4ae3ae1`，不修改用户主HEAD、主index或现有舞台效果。本单元只关闭离线参考接口断点，不宣称真实Animator容器、TRS数学、Job生命周期或Unity物理已经完成。

## 本次实际完成

`Tools/official_physics_animator_buffer.py` 新增 `read_animator_record_values`。绑定重建和写入端已有的 `AnimatorRecord` 可以直接由读取端按选定handler消费，不必另行制作一份可能过期的 `CapturedTransform` 数组。旧 `read_animator_buffer_values` API 保留，共用原门控、三张map、getter回退和relative运算。

- 只有三个映射都命中，才读取选定record的world position/rotation和local position/rotation；未选record、其他handler和writer statuses不读。
- 缺任一map沿原getter回退；命中的record缺数据、handler无效或TRS解析失败不能当作map缺失。
- world/local值保留Single收窄，四元数不擅自归一化。mapped路线先计算scale，再按原流程覆盖为单位尺度；getter回退保留符号尺度。
- 显式 `native_unit_trs(animator_id, handler, world_p, world_q)` 是调用方边界。已命中路线缺此输入报错，不填identity。接口只检查矩阵有限/shape及必要的齐次、平移一致性；这些检查**不能证明旋转基底为原生TRS或单位尺度**。
- read仍消费逆relative，write消费正向relative。两者不交换。

检查shape/finite/bounds和返回不可变结果是参考适配器策略，并非原生非法指针、异常或增量写入等价。回调与local数组读取的错误先后也不是本单元承诺的native fault语义。

## 原始证据

独立verifier不导入读取/写入参考，仅将DLL和metadata作为静态字节读取。原始SHA与前单元一致，完整unwind family及指令解码长度复验通过。

| 对象 | 已复核依据 |
| --- | --- |
| ReadAnimatorBufferDataJob._Do | method369459 / `0x5a1dc98..0x5a1e665`，2509字节；SHA `13fc5cba6396d081e58d767d61c5cdf3455aa04274041ca0f9a89cfcadfcba35` |
| RW handle原始结构 | definition54623；local p/q偏移 `0x18/0x20`，world p/q偏移 `0x30/0x38`，writeFlagPtr `0x50`；保留boxed/unboxed区别 |
| 单位尺度输入 | `0x5a1decc` 调 Vector3.get_one，method358754 / `0x4a749e0` |
| 正向TRS wrapper | `0x5a18560`，272字节；SHA `8f2896bba54fad84730566b859049c0e4b58b93bebf5ee206e49f3b784897c4e` |
| wrapper实际目标 | `0x5a1860a` 调 Matrix4x4.TRS，method358659 / `0x2cd43b0`；未在本单元移植native旋转数学 |

私有证据：`D:/EndfieldTechLib/notes/official-physics-animator-record-read-20261012-01/verify_source.py` 与 `source-verification-01.json`；14个reader指令点、两个native方法身份以及15字段原始偏移均复验。证据SHA见本目录 `verification.json`。

同时封存下一调度边界的三个精确span：`0x5a18270` 350字节、`0x5a1806c` 515字节、读schedule wrapper `0x3b5e68` 172字节。前两者存在worker同步Execute分支；不能因此推断所有调用方依赖已完成、句柄已释放或实际运行路由。读wrapper调用 `0x6985208`，其generic身份仍未闭合。GCHandle.Alloc `0x4545950` 无精确RUNTIME_FUNCTION项，不猜范围。

## 验证结果与边界

缺接口collection RED在实现前已观察。新增26项包含绑定顺序 `(1,0)` → read → write → read、重复Transform只保留末槽、rotation-only status2的旧world p+新q、三map短路、未选数据不读、错误不回退及relative顺序。矩阵输入均为显式合成fixture，**不是native TRS独立数值oracle或真实Animator采样**。

读取专项85项通过；生产模块94语句/28分支，分支含覆盖率100%。全套4567项和114 subtests通过，3项历史skip、2项历史Pillow警告。Ruff、Black、Pyright、compileall和pip-audit通过；无独立代理语义审阅。

保护检查确认11组/164保存点、7个runtime文件、9557条主index及主HEAD不变。现有Unity效果没有变；源码封存与测试通过不代表用户已能使用完整官方候选物理。

## 下一步

1. 明确实际Animator RW handle创建、真实record输入与native单位尺度TRS来源；当前共享record接线只使用有限capture。
2. 沿三个已封存schedule helper恢复读写依赖、worker同步分支和六GCHandle释放/异常生命周期，不能用符号计划冒充实际Job。
3. 接入统一11组真实状态、唯一writer及可回退C#候选后端，再做MMD/解包动作、暂停/seek和连续动态验收。完整门禁仍以 [PROGRESS.md](../official-physics-animator-buffer-20261003/PROGRESS.md) 为准。
