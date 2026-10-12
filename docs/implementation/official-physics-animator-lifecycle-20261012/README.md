# 官方物理：Animator 绑定重建有限生命周期

日期：2026-10-12。接续[Animator 写缓冲主体](../official-physics-animator-write-20261012/README.md)，新增 `Tools/official_physics_animator_lifecycle.py`，恢复 `TeamManager.UpdateTeamAnimatorData` 369500 / RVA `0x5a2283c` 的正常完成路径、绑定操作顺序与索引映射规则。

本单元提供离线有限参考。实际 `Animator.CreateClothBindings` 返回记录、Transform 对象身份、Animator 对象身份及原生 HashSet 遍历顺序由调用者提供；原生 map/record 创建、容器释放、Unity Animator API 与跨帧 job 调度仍未实现。因此没有新增可见物理效果，也不能据此宣布官方物理完成。

## 静态证据

- GameAssembly 与 metadata 只作为静态字节读取，原始 SHA-256 为 `c24495...ae89` 与 `007674...f02e`。
- 主体按 AMD64 unwind 表精确限定为 3241 字节，SHA-256 `8c7b76...25ee`。
- 参数从 metadata 与 Il2CppType 解码确认：`ExNativeArray<Int16> teamIdArray`、`TransformAccessArray transformArray`。
- 六个持久字段的闭合类型已确认：两张 `NativeParallelHashMap<int,int>`、`NativeParallelHashMap<int,AnimationTransformRWBufferHandle>`、`Dictionary<int,Animator>` 与两个 `HashSet<int>`。
- 四个分配点确认临时 `HashSet<int>`、`HashSet<Transform>`、`List<Transform>`、`Dictionary<int,List<int>>`。
- 独立 verifier 重算原始文件与方法哈希，检查 38 个调用点、30 个主函数指令点，以及 240 字节的引用列表 append 方法体。它不导入本次端口。
- IL2CPP 引用类型泛型共享明确留痕：分配点证明 `Transform` / `List<int>` 等闭合类型，调用目标可能解析为 `System.Object` 共享体，不能虚构独立特化。`0x2d10e70` 的泛型别名未解析，已通过接收对象与读写指令证明其 append 数据流；不冒充已解析的方法定义身份。

本机证据目录：`D:/EndfieldTechLib/notes/official-physics-animator-lifecycle-20261012-01/`。`source-audit-06` 与 `source-verification-02.json` 是最终证据；`source-audit-01..05` 和 `source-verification-01.json` 属于初稿，不作为本结论来源。第一次 verifier 的“全部重复槽位归组”声明已由后续静态复核纠正。

## 恢复的正常完成路径

1. dirty 集合为空立即返回，原有 temp 集合保持不变。
2. dirty 非空先清 temp；dirty Team ID 通过 `teamId2AnimatorInstnceId` 查到的 Animator ID 去重进入 temp。缺映射跳过。
3. 按调用者观测到的 temp HashSet 顺序处理每个 Animator ID；遍历整张 Team→Animator ID map，选择全部共享该 ID 的团队，不限于 dirty 团队。
4. 按全局 Transform slot 升序扫描，跳过未选团队与 null Transform，按对象身份建立唯一 Transform 列表和反向索引字典。
5. 当前 Animator 为 null 时读取匹配团队的 `teamId2Animator`；若读到 null，后续匹配 Transform 会继续尝试。成功后保留首次非 null Animator。
6. 以实际 `Animator.GetInstanceID` 查旧 RW record。存在旧记录才 Disable；随后 Create(unique Transform array)、以实际 Instance ID 替换 record、Enable。
7. 按返回 record 低 UInt16 数量遍历其 UInt16 Transform 索引数组，将 handler 写到该字典键保留的全局 slot。缺键记录错误并继续；重复返回索引由后一次 handler 覆盖。
8. 不全局清理旧 slot→handler map；正常结束时清 dirty 和 temp。

返回值保留 `plans`、`operations` 和 `errors`，使接线时可以核验真实操作顺序与映射结果。范围、记录数组形状和 caller-order 检查属于适配器策略，不声称复制原生异常或部分写入状态。

## 复核中修正的重复 Transform 分支

官方主体的重复分支先 `List.IndexOf`（`0x5a22f98`），但 `ContainsKey`（`0x5a22faf`）的键来自当前列表 Count（`0x5a22fa8`）；新建列表后的 `set_Item`（`0x5a23007`）又使用 IndexOf 结果（`0x5a23000`）。

字典从空开始，已有键严格小于 Count，因此这个 ContainsKey 始终失败，重复分支会把原组替换为 `[当前 slot]`。每个唯一 Transform 最终只保留最后一个出现的 slot，丢出的旧 slot 不被清理。端口保留该行为。

例如 Transform 序列 `[A,B,A]` 的最终组为 `[[2],[1]]`，不是 `[[0,2],[1]]`。初稿采用合并组；静态逐指令复核及独立审查发现后，先用回归测试观察 5 项 RED，再修正至 GREEN。另补了 UInt16 count 上限、首个 Animator 为 null 后重试、全部 null 与多 Animator 顺序等用例。

## 验证

- TDD：缺模块 collection RED；重复槽位纠正的 5 项断言 RED 已观测。
- 专项 26 项通过；模块 131 statements / 52 branches，分支计入覆盖率 90.71%。
- 测试覆盖空 dirty、共享团队、重复 Transform 覆盖、返回重排、Disable/Create/Enable 顺序、null 路径、返回索引缺失、多 Animator 顺序、旧键保留、不可变输入及 count 0 / 65535 / 65536 边界。
- 完整回归、静态检查与输入保护的最终数字及文件哈希见 [verification.json](verification.json)。

## 后续接入顺序

1. 将重建后的 slot→handler map、现有 Team→Animator map 与 caller-resolved RW record 接到已恢复的 Animator read/write 主体，验证重建后 handler 顺序确实被两端使用。
2. 完成 Team 相对变换输入及 `updateMode=10` 跨帧 Animator 调度，逐分支恢复启用、变更、移除和释放路径。
3. 获取并验证 11 组真实运行 map/record 与 binding index 输入，再执行正式 Unity 接入与连续动作验证。

调用者提供的静态 capture 不能代替 `CreateClothBindings` 本身，也不能证明原生容器生命周期、指针别名、异常时部分写或 Unity 执行时序正确。此前写缓冲文档里的生命周期缺口由本单元恢复其有限正常路径；上述正式运行缺口仍在。
