# 官方物理：Animator 写缓冲主体有限语义

日期：2026-10-12。接续[动画缓冲读取主体](../official-physics-animator-buffer-20261003/README.md)，新增 `Tools/official_physics_animator_write.py`，把此前只完成静态读取、明确标记为未移植的 `WriteAnimatorBufferDataJob._Do` 369460/0x5a2655c 推进为**有限、不可变、可回归的写缓冲参考**。

这不是 Unity Animator job，不生成原生 map/record，不执行 NativeArray、Burst、调度器或游戏代码，也没有产生新的可见物理效果。

## 静态证据边界

- 原始 `GameAssembly.dll` 与 metadata 只按字节读取，哈希仍为 `c24495...ae89` 与 `007674...f02e`。
- `_Do` 使用 AMD64 `RUNTIME_FUNCTION` 精确范围：2358 字节，SHA-256 `7238f1...c621`。
- 另封存两种位置非法检查、float3 插值、四元数插值、正向 `LocalToWorldMatrix`、矩阵四元数、四元数乘法、矩阵点变换及 Double3→Single3 helper。
- 独立 verifier 锁定 31 个关键指令点与 8 个 helper 哈希，不导入本轮 Python 端口来证明自身。

证据位于 `D:/EndfieldTechLib/notes/official-physics-animator-write-20261012-01/`。其中 `source-audit-02` 是成功的有界导出；早期 `source-audit-01` 是依赖/边界修正前的未完成尝试，不作为结论来源。

## 已恢复的控制流

每个全局 transform slot 的原顺序如下：

1. 先用 `teamIdArray[slot]` 取得 TeamData；`IsCullingInvisible` 命中低 32 位 `0x800/0x80000` 时直接结束**整个 job**。
2. 在第一张 map 前读取 `clothSimulateWeight`、`clothLodFadeWeight` 并按 Single 做乘法；此时只计算，还未按结果跳转。
3. 依次查 `transformID2RWHandlerID[global slot]`、`teamId2AnimatorInstanceId[teamId]`、`animatorID2RWHandler[animatorId]`。任一缺失仅推进到下一 slot；不会把非法 handler 伪装成 map miss。
4. 三张 map 成功后才读 transform flag。缺 `0x10`、Team bit61 命中或有效权重不大于零，均结束**整个 job**。
5. bit2 世界写优先于 bit4 局部写；两者都无则只推进下一 slot。

有限 API 通过 `AnimatorWriteStep.control` 显式区分 `continue`、`written` 与 `return_job`，并保留每槽查询轨迹、写入顺序、handler、Animator ID 和最终 status，防止后续调度接线把 job 退出误写成单槽跳过。

## 已恢复的写入语义

### 局部分支

- 先检查 solver localPosition 的 NaN；非法则当前槽无任何写入。
- 权重小于 1 时从 Animator record 已有 localPosition/localRotation 向 solver 值插值；权重大于等于 1 时直接采用 solver 值。
- 写 localPosition、localRotation，最后写 status=1。

### 世界分支

- 无论 Team `0x2000` 是否允许位置写入，都先检查 solver Double3 世界位置；非法则连世界旋转也不写。
- 世界旋转按相同权重规则从 record 旧值向 solver 值插值，写入后先标记 status=2。
- Team flag `0x2000` 命中时才将 Double3 转 Single3、插值、写世界位置，并把 status 覆盖为 3。
- `useRelativeTransform!=0` 时要求调用者提供官方 helper 已解析的**正向**相对矩阵：旋转为 `matrixRotation * q`，位置在插值后执行 `matrix * p`。不使用读路径的逆矩阵。

输入记录采用不可变 tuple，返回新 mapping/record；这是离线安全模型，不声称等价于原生指针别名、异常或部分写故障。

## 测试与验收

- 按 TDD 先观察缺模块 collection RED，再实现。
- 新增 22 项专项测试；模块 173 statements / 62 branches，branch-inclusive 91%。
- 覆盖三层 map 短路、负 Animator ID、handler 与 global slot 分离、whole-job/continue 差异、权重读取时序、世界优先、status 1/2/3、位置门控、NaN 无部分写、相对矩阵方向、分数权重和输入不可变。
- 全套：`4491 passed / 3 skipped / 114 subtests / 2` 条既有 Pillow 弃用告警。
- Ruff、Black、Pyright 通过；完整原始数字与哈希见[verification.json](verification.json)。

## 尚未闭合，下一步不得绕过

1. `Team.UpdateTeamAnimatorData` 369500/0x5a2283c 的 map/record 创建、更新、释放及 handler 索引生命周期仍需按分支恢复。
2. 11 组 `updateMode=10` 的跨帧 Animator 调度仍未接入；不能退回普通 Transform getter/setter 路径冒充官方链。
3. 当前接口消费 caller-resolved 相对矩阵；从 Team relativePos/relativeRot 构造该矩阵的有限函数可复用既有证据，但还未并入 Animator record 生命周期。
4. 尚未用 11 组真实 runtime map/record 输入运行，也未执行 Unity、游戏或 Burst oracle；无可见物理效果验收。

因此本单元的准确状态是：**WriteAnimatorBufferDataJob 的有限控制流与数值写入语义已恢复并回归；Animator map/record 生命周期与正式调度尚未闭合。**
