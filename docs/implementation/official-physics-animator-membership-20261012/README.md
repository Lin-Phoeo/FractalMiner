# Animator团队注册/清理：保留共享状态与原门控

日期：2026-10-12，承接 `ad53aba`。本单元实现两个有限成功路径，补入 `Tools/official_physics_animator_lifecycle.py`，可连接已有绑定重建参考。没有创建真实Animator bindings、执行原生Job或接入Unity；现有舞台效果保持。

## 核实并实现的规则

`AddTeamAnimatorData` method369502 / `0x38e2800` 的完整CHAININFO family为四段，共451字节。入口要求源process/component正常存在；组件父链取得Animator和Unity-null结果由caller显式提供，本接口不运行GetComponent或用Python对象非null冒充Unity有效性。

| 选中结果 | 原操作 |
| --- | --- |
| 有效Animator | 调get_InstanceID；更新**全局**MagicaManager.get_Team的NativeParallelHashMap<Int32,Int32>；更新**当前**manager的Dictionary<Int32,Animator>；随后当前manager dirty HashSet添加Team |
| Unity-null Animator（包括destroyed） | 不更新或删除两张旧映射；仍在当前manager dirty HashSet添加Team |

全局manager与当前manager不能凭感觉合并，API显式区分两份目标。有限返回为detached state copy，不模拟native写入、singleton观察、异常部分写入或hash容量。非null路线缺全局map报错；null路线可保留未提供的全局capture，不填默认空字典。输入Team ID按Int32处理，不从其他方法借来Team0/Int16门禁。

`ClearTeamAnimatorData` method369501 / `0x5a20b08`，118字节：依次Remove**当前manager**的instance-map key和Animator-object-map key；第一张map缺key不会跳过第二次Remove。它不清dirty set、RW record或handler map，不调用DisableClothBindings，不是GCHandle.Free。完整RemoveTeam另有isValid/Team0、同步父组、NativeArray/chunk和多容器清理，本单元**没有恢复完整RemoveTeam**，不能将这些门禁移到Clear方法，也不能把两张map Remove当作所有资源已释放。

注册→Clear→已有UpdateTeamAnimatorData组合验证保留共享Animator的其他Team、另一个Animator的旧record和未被该方法清理的旧handler key。未把合理化清理或自定缓存淘汰标成原逻辑。

## 真实源身份与句柄审计

六个MethodInfo初始化格由当前metadata registration解码并独立重读：GetComponentInParent<Animator> MethodSpec595463、全局instance setter298842、本地Animator setter544120、dirty Add168982、instance Remove298832、Animator Remove544118。TeamManager原字段offset分别为 `teamId2AnimatorInstnceId=0xb8`、`teamId2Animator=0xe8`、`dirtyAnimatorTransformTeams=0xf0`。

另核查GCHandle入口，避免错误补释放策略：

- `Alloc(object)` method283198 / `0x4545950` 没有exact RUNTIME_FUNCTION项。但可认证从入口到第一个无条件tail JMP的15字节stub：nop、EDX=0、R8D=2、JMP `0x1b7b0`；当前enum中2为Normal，不是Pinned。这里只认证stub指令，不以邻近函数推断整个Alloc边界或移植native allocator。
- `get_Target` method283195 / `0x31534e0` 的正常入口检查8字节handle非零，再传低32位给runtime lookup `0x2d7b0`。`Free` method283200 / `0x3151ac0` 则有原子清零与runtime release入口，两者不是同一操作。
- 已认证host/delegate两份完整family中未找到对上述Free或runtime release入口 `0x29110` 的**直接**call/jmp。这不证明下游callee、定制scheduler或runtime不会释放，也不证明游戏必有泄漏。完整GCHandle生命周期仍未闭合，不添加“Execute后自动Free”的假设。

私有 `D:/EndfieldTechLib/notes/official-physics-animator-membership-20261012-01/` 下的audit_source/verify_source只读取惯用封印DLL/metadata字节，不加载或执行它们，不导入生产生命周期参考。认证六个family共7084字节、24指令点、六个generic method reference及原字段/方法身份；原资产与反汇编保持私有。没有独立代理语义审阅。

## 验证与剩余边界

先观察缺API collection RED，再实现。新增27项覆盖valid/null/旧映射、全局与本地目标、signed Int32极值/Team0、两张map独立Remove、不可变输入、共享Animator以及注册/清理/重建组合。它们是合成对象/record，不是实时角色输入。

生命周期专项53项通过，生产模块162语句/56分支，分支含覆盖率92.20%；全量4659项和114 subtests通过，3项历史skip、2项历史Pillow警告。生产/测试文件Ruff、Black、Pyright、compileall与测试环境pip-audit通过。11组/164保存点、7个runtime文件、9557项主index与主HEAD保持。

下一步集中于完整Team/Transform释放与启用调用方、GCHandle/native调度的真实生命周期、实际CreateClothBindings与TRS/record输入；然后接统一11组状态和可回退C#候选。当前[整体门禁](../official-physics-animator-buffer-20261003/PROGRESS.md)仍未达到Unity动态验收，不能以本单元清理参考代替它。
