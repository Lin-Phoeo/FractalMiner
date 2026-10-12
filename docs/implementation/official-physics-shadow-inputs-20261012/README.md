# 官方物理候选的Unity阴影输入门禁

2026-10-12，承接记录分支 `d2592b95`。本单元第一次把此前封存的11组身份与候选全局布局接到真实 `Typhoeus_MMD_Stage`：Unity 2022.3.30f1 在真实 `动作.vmd` 第0帧和第2帧读取角色当前 Transform，并写入本单元自有的 `NativeArray`。这是**实际Unity输入发布**，不是Python快照；但它仍是只读shadow gate，**没有执行官方求解器，也没有向角色写回物理结果**。当前可见二级运动仍由明确标注为alternate的 `EndfieldSecondaryMotion` 提供。

## 输入边界与解析规则

加载器只接受三份SHA256封印输入：原始556 Transform绑定、11组140 skin+11 render身份、11 Team候选连续布局。输入文件中“尚未生成runtime ID/getter/native数组、未观测游戏运行路线、未集成官方solver”的false边界也必须保持；不能通过修改说明字段把候选冒充原运行状态。

恢复舞台与原 `postmodel` 层级存在三类已实测差异：

1. 恢复模型在 `Root` 外有额外包装层。骨骼只允许从叶节点向上连续匹配，并且命中 `Root`、`Bip001`、`Mesh_all` 或 `lod0` 稳定锚点；不做全树任意同名回退。
2. 恢复舞台缺少11个原 MBC 组件 Transform。它们在封存绑定中均为角色根的单位局部TRS，因此会在测试会话内建立11个 `HideAndDontSave` 代理，保留独立Unity instance ID和父ID。
3. 恢复舞台缺少9个裙摆碰撞挂点。只允许名称明确含 `collider`、父身份已按官方索引解析、局部TRS来自封存绑定的节点建立临时代理。普通缺骨仍硬失败。原 `postmodel` 左侧裙链中有一个名称写作 `skirt_base_R_c_03_jnt`，恢复模型为 `skirt_base_L_c_03_jnt`；仅这一处以“已解析父节点 + 唯一封存局部TRS”绑定，不按近似名称猜测。

全部20个代理在publisher释放时销毁，场景文件不保存。140个模拟槽中92个当前模型有正顶点权重，另外48个包括未加权末端、辅助节点及碰撞挂点；`skin_bone_count` 是原组件收集的模拟Transform数量，不能误写成“每个槽都有非零网格权重”。

## 实际发布内容

`EndfieldOfficialPhysicsShadowInputs` 持有并释放：

- 151个 `float4x4` 当前 `localToWorldMatrix`；
- 151个实时Unity `GetInstanceID()`；
- 151个实时父 `GetInstanceID()`，无父为0；
- 140个候选Team ID，按封存连续particle窗口写入1到11。

每次发布前重新读取当前Transform，因此真实VMD改变会进入数组。publisher不持有求解状态，`ShadowOnly=true`、`SolverExecuted=false`、`SolverOutputsWritten=false` 是固定API边界；验证同时保存发布前局部旋转，确认发布没有改写角色。

## Unity动态结果

最终成功报告位于 `D:/EndfieldTechLib/notes/official-physics-shadow-20261012-01-green-09/`：

| 门禁 | 结果 |
| --- | --- |
| Unity版本 / 真实场景 / 真实动作 | 2022.3.30f1 / `Typhoeus_MMD_Stage` / `动作.vmd` |
| 组与槽 | 11组，140 simulation slots，151 transform capacity |
| 恢复差异 | 11 render代理，9 collider代理，1 sealed-TRS名称别名 |
| 第0帧发布 | 151 Transform + 140 Team，全量一次写入 |
| 第2帧发布 | 151 Transform + 140 Team，全量一次写入 |
| VMD动态性 | 140个transform槽相对第0帧发生变化 |
| 发布精度与副作用 | matrix最大误差0；localRotation写入0 |
| 求解/回写 | 均为false；本单元没有伪造可见官方物理 |
| 清理 | 20个临时代理全部销毁 |

正向共21项检查通过。错误bindings SHA以Unity退出码1和明确seal mismatch拒绝；复用已有输出目录也以退出码1在覆盖前拒绝。随后原可见MMD/湿身/alternate physics整套回归重跑，692项、61帧全部通过。Python全套为4754 passed、3 skipped、114 subtests，只有2条既有Pillow弃用警告。

## 仍未完成与下一步

本单元只关闭“真实角色getter进入候选NativeArray”这一窄门禁。尚未发布完整proxy common/mesh/skin、particle 14状态、baseline/distance/work-list、saved attribute/flags、碰撞体数据、Team clock/reset与依赖；更没有执行积分、约束、碰撞、显示预测、Animator唯一writer或正式骨骼写回。因此截图只证明真实MMD姿态下输入桥正常，不证明官方物理效果。

下一单元应在同一shadow backend内建立完整的可释放arena owner，并把已封存的global layout、live getter world-proxy、particle reset14、baseline/distance/work-list按151/140/37/126/176容量装入真实Unity `NativeArray`。先做初始化与每帧刷新门禁，保持solver/output关闭；等输入、reset和生命周期都在Unity动态通过，再用显式开关接求解与唯一writer。不能把静态参考状态直接当连续VMD状态，也不能让alternate solver和官方候选同时写同一骨骼。

全局状态与最终交付门禁以 [PROGRESS.md](../official-physics-animator-buffer-20261003/PROGRESS.md) 为准。
