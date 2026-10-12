# Transform移除的显式字段与Animator dirty调用接线

日期2026-10-12，承接记录提交 `2fae2fd`。生产文件 `Tools/official_physics_transform_release.py`。本单元是有限值/调用描述参考，不是native allocator、完整RemoveTeam、GCHandle释放或Unity资源销毁。现有舞台效果保持。

## 原始RemoveTransform顺序

method369419 / `0x5a1cc48`，完整exact family582字节。源门控是manager isValid及DataChunk signed length>0，不借用Enable位或Team0门禁。

1. flagArray调用 `ExNativeArray<Byte>.RemoveAndFill(chunk,0)`。
2. 初始local p/q、world p/q、last world p/q、scale、local p/q、last local p/q和matrix分别调用自己的Remove，共12份arena；矩阵使用独立泛型实例body，不能混成同一数组或省略。
3. teamIdArray调用 `ExNativeArray<Int16>.RemoveAndFill(chunk,0)`。
4. 从start开始递增length次，调用 `TransformAccessArray.SetTransform(...,index,null)`（method360368 / `0x40e7480`）。此方法没有额外Animator dirty、record/handler删除、component arena清理或GCHandle.Free。

API `release_registered_transform_range` 只更新detached RegisteredSlot capture中明确的flag=0、team_id=0、transform_handle=None，返回十四个arena操作描述和逐槽解除索引。它**不执行**上述ExNativeArray方法或TransformAccess原生调用，没有发布native数组。非正length/无效manager不读取未选输入；有效路线必须提供已拥有、非负且落在capture内的窗口，不默认空slot表。窗口验证/私有copy/原子结果是适配器策略，不是native非法索引或部分写入等价。

其他字段留作opaque inactive storage cells，不重算、不清零、不normalize、不伪造矩阵；它们不能继续当作有效pose输入，**也不宣称原生Remove后这些物理字节一定保留**。native allocation、emptyChunks/useCount、回收复用与容量/搬移规则仍需独立恢复，`native_allocator_applied` 明确为false。函数名中的release不表示这些未实现资源已经释放。

## 接通注册调用的dirty效果

AddAnimatorTransform method369503 / `0x34408a0`（160字节）和MarkAnimatorTransformDirty method369504 / `0x5a22398`（140字节）均只在caller已解析的Unity Transform有效时，将原Int32 Team ID加入当前manager dirty HashSet。Mark实际调用 `UnityEngine.Object.op_Inequality(transform,null)`（method359621），不是Python非None检查，也不是误标成op_Implicit。Add的Unity-null检查为inline。

`apply_animator_transform_dirty` 可消费已有注册参考的AnimatorCall描述。保留原Int32调用参数，不能拿已经存入teamIdArray的Int16代替。null/destroyed调用不自动生成dirty；`SetTransform`失败分支先描述Mark再清slot，不代表null的Mark会成功标记Team。dirty effect不创建bindings、不采样hierarchy、不改两张Team map或旧record。源有效性由caller提供，真实Unity-null采样尚未接入。

## 验证

先观察缺模块collection RED。31项新增测试覆盖十四arena顺序、两种Remove区别、窗口/skip、明确三字段写入、未选payload不验证、inactive cell不进行浮点再舍入、dirty两方法/Unity-null/Int32及失败Set组合。所有slot及有效性是合成capture，不是实时角色或native释放oracle。

专项31项通过，新模块34语句/10分支100%覆盖；全套4690项和114 subtests通过，3项历史skip、2项历史Pillow警告。生产/测试文件Ruff、Black、Pyright、compileall和测试环境pip-audit通过。

独立静态verifier不导入生产参考：复读当前封印DLL/metadata，认证三个主函数882字节、连同component解除入口和四个arena helper共八个exact family2014字节，24指令点、十四Remove/RemoveAndFill方法初始化格、两个dirty Add格、实际TransformAccess setter和Unity inequality身份。完整原始资产/指令保持私有；报告目录 `D:/EndfieldTechLib/notes/official-physics-transform-release-20261012-01/`，SHA见本目录verification.json。没有独立代理语义审阅。

11组/164保存点、7个runtime文件、9557条主index与主HEAD保持。真实Free列表、useCount、native缓冲发布、句柄生命周期和Unity候选均未完成；不能据测试数或解除描述称官方物理已完工。

## 下一步

沿ExNativeArray的emptyChunks/useCount及独立component arena入口补分配/复用/释放规则；不要将emptyChunks误当active allocations，也不使用开放泛型definition的零offset推测具体实例布局。再接完整Team移除与唯一writer/Job就绪、实际record/TRS及可回退C#候选，进行连续动作/暂停/seek验收。[整体门禁](../official-physics-animator-buffer-20261003/PROGRESS.md)仍有效。
