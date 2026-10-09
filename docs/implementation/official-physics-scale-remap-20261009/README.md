# 负缩放切换与帧矩阵：有限值参考

2026-10-09。实现为 `Tools/official_physics_scale_remap.py`，对应当前版本帧核369644的两个片段：`5a34dd7..5a35365`、`5a357a1..5a35a8d`。证据只读来自已校验SHA的原文件；没有加载、执行或注入游戏DLL。完整反汇编只保存在本地，公开版本保留范围、SHA、核查规则和自有参考实现。

**这不是完整官方物理后端，也未接入Unity。** 两片段之间的fixed-point帧中心归约尚待实现；不能拿舞台root当作已还原的中心输入。当前Unity舞台与现有物理保持不变。

## 关键规则

| 状态 | 实际行为 |
| --- | --- |
| Team.sign / flag20000 | 当前Single缩放任一轴小于0即为负分支；不是行列式奇偶。无负轴清20000，其余flag保留 |
| Team.direction / change | direction为逐轴sign，±0均得到+0；change是旧direction乘新direction，不是相减 |
| Team.quaternionValue | 无负轴为(1,1,1,1)；负分支为(-signX,-signY,-signZ,1)，零符号也翻转。这是逐分量乘数，不能当旋转四元数归一化 |
| Team.triangleSign | 第一项在X或Z负时为-1；第二项仅X负时为-1 |
| 符号变化检测 | 三轴Single数值相等比较，±0相等；变化才新增40000。已有40000不在本片段清除 |
| 组件映射矩阵 | currentComponentTRS × fullInverse(oldComponentTRS)，不是fastinverse；不是Center.negativeScaleMatrix |
| 组件映射修改项 | oldComponentPosition、oldAnchorPosition；smoothingVelocity先Single→Double方向变换(w=0)→Single；oldComponentScale改当前缩放 |
| 保持项 | 该片段不改oldComponentRotation/oldAnchorRotation，不直接重映射或重置frame历史，不新增400 |
| 帧局部矩阵 | 无条件生成fullInverse(frameTargetTRS)；当前scale取组件样本，不取未发布/陈旧frame-scale |
| Center.negativeScaleMatrix | 仅flag40000时生成frameTargetTRS × fullInverse(**oldFrame**TRS)，否则保留原矩阵。不是oldWorldTRS，也不等于帧逆矩阵 |

CenterData的oldFrame字段未装箱偏移为312/336/352，对应帧核栈408/420/430；oldWorldPosition偏移408对应栈468，不能因同一个“408”混淆二者。组件pivot在152，旧anchor在40，平滑速度在556，负缩放矩阵在568。

Double矩阵乘法每lane按四次乘法、三次左到右加法计算。方向变换仍执行translation×0的第四列加法，不用点变换替代。TRS引用已有Single旋转→Double列缩放/平移，inverse引用已有完整shuffle/minor路径。有限值、奇异矩阵拒绝属于适配器约束；原生无效输入可能传播NaN/Inf，Python结果不宣称CRT/Burst逐位真值。

## 两阶段接口与接续顺序

1. `prepare_component_scale_remap(state, team, anchor, currentScale, cache)`：消费同一快照的当前组件样本、Center旧组件位置/旋转/缩放和Team旧符号缓存。返回工作旧姿态、选定字段变化、符号缓存和flag。reset帧也先执行这一段。
2. **待实现的帧中心归约与发布**：fixed-point位置均值与姿态基向量归约；无fixed-point分支使用组件姿态。必须将同一帧的position/rotation及当前component scale发布到后续step输入。测试中的手工resolved输入仅验证接口，不能算这个生产阶段已经完成。
3. `prepare_frame_scale_matrices(step, currentScale, flag, previousMatrix)`：在oldFrame被重置之前消费它，返回局部frame inverse及条件更新的negativeScaleMatrix。
4. 已有 `advance_frame_anchor` → `prepare_frame_inertia` → `advance_frame_inertia` →帧运动/子步中心→Start/End。prelude才在40000/reset条件下更新其所表示的frame历史。

接口目前是不可变Python参考，不发布Team/Center NativeArray，不处理完整帧末oldComponent/oldAnchor生命周期。不能把cache.oldComponentScale保持规则推广为整帧尾规则；本片段外仍有发布。

## 验证与交付边界

41项新测试覆盖正/负/零轴、±0相等、已有flag、reset不跳过、非单位旋转、非均匀缩放、大世界Double坐标、方向与点区分、矩阵顺序及独立NumPy逆矩阵对照。另验证component-remap→caller-resolved frame目标→anchor→prelude时，在正确边界重置旧frame缩放/姿态。source proof逐条检查73条关键指令、29/7条矩阵/向量调用序列、常量及metadata字段位置；这是静态证据核查，不是自动完整CFG/数据流证明或原生执行oracle。

最终全套回归、覆盖率、输入/舞台保护、依赖扫描及文件SHA见 `verification.json`。合成测试通过不等同整个角色真实11组输入/约束链动态验收。

下一主线是补两片段之间的fixed-point帧目标生产，再核查wind-zone选择、完整reset/tail及跨步发布，形成候选链后才接C#和MMD/解包动作。剩余门禁继续按 [PROGRESS](../official-physics-animator-buffer-20261003/PROGRESS.md)；不以测试数量报完工百分比。
