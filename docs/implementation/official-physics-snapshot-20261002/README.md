# 官方物理：世界/局部快照及 scale 输入链

日期：2026-10-02。接续[选择网格](../official-physics-grid-20261002/README.md)。新增 `Tools/official_physics_snapshot.py`，按原始 `RenderSetupData.ReadTransformJob.Execute` 的规则恢复六个输出，并接到已有的新建选择和骨骼方向参考。**这是一条离线、有限数参考输入链，不是实际 Unity getter、完整官方物理或新的舞台效果。**

## 本轮实现

输入是原始坐标系、原始收集顺序下，调用者提供的 Unity getter 结果：世界 position、世界 quaternion、世界 localToWorldMatrix、localPosition、localRotation。不能把 prefab local TRS 当作世界输入，也不能用当前恢复 FBX 的骨骼姿态替代尚未采集的官方快照。

原 Job method370212 / RVA0x5a631e4，完整 unwind 范围775字节，SHA256 `c95b5a6ba761eac5197774b5a0e45562265a321f690f96e351c3ad60b0f17b10`。六个 NativeArray 字段 unboxed 偏移依次为 positions@0、rotations@16、scales@32、localPositions@48、localRotations@64、inverseRotations@80。

| 输出 | 已恢复规则 |
| --- | --- |
| position / localPosition | 分别来自世界/局部 getter；float3 原始复制，不把一个推导成另一个 |
| rotation / localRotation | 分别原样复制 float4，不自动 normalize |
| inverseRotation | 复用已认证的 Single reciprocal-dot inverse；不是单位四元数 conjugate 简写 |
| scale | `diag(float4x4(inverse(worldQuaternion), float3.zero) * worldLocalToWorld)`；保留负值和原矩阵 shear 的影响 |
| 无效 TransformAccess | 跳过该索引全部六项写入，保留之前槽位；不填零 |

**scale 不是 get_localScale、lossyScale、三个列向量长度或绝对值。** 原 Job 没有调用 get_localScale。非单位输入也不能额外归一化：测试输入 q=(0,0,1,1)，矩阵列(0,2,0)、(-3,0,0)、(0,0,4)，原顺序得到 scale=(1,1.5,4)，而非(2,3,4)。这是区分逻辑的合成数据测试，不是实测角色存在非单位 quaternion。

## 算术与静态身份核查

- Unity Matrix4x4 → math.float4x4：method441161 / 0xa1f3ae8 调 GetColumn(0..3)；GetColumn method358683 / 0x2d4dd60 分别复制四个16字节列，没有转置。
- float3 / quaternion 转换辅助 0x4a48e10、0x30e0ab0 只是复制分量，没有归一化或轴转换。
- 实际 0x5a633f9 RIP type usage 解到 **Unity.Mathematics.float3**，不是 UnityEngine.Vector3。static_storage@0 字段为 `zero`；该类型没有 .cctor 初始化方法。这认证默认零静态字段定义和读取身份，**未检查游戏运行时 static 指针内容或任意其他写入**。
- 0xa1f3910 是 math.float4x4 quaternion+translation 构造器，不是带 scale 参数的 TRS。rotation 部分继续调用0x305d480 → float3x3 constructor method441054 / 0x305d4c0；translation 来自 float3.zero，w 常数为1。
- quaternion 矩阵：先 q+q，按原 swizzle 与 sign-bit XOR 构造项，逐项 Single 乘、减，最后加三个 basis。不能换成预先合并的 Double 公式；没有 FMA 或额外 normalize。
- 矩阵乘 helper0x305d9c0：每列 `(((a.c0*b.x+a.c1*b.y)+a.c2*b.z)+a.c3*b.w)`；0x34e0d60 乘法、0x305dd60 加法逐项舍入。最后只取乘积的0、0x14、0x28三个对角元素。
- inverse 继续复用已封存的0x39d3e70参考，不重写已通过算术。

无 unwind 的复制/XOR/float3、float4 乘加叶函数，在私人审计里按有限直线指令到 RET 验证，拒绝 call、jump、int3，不按相邻函数间距猜边界。报告中同时保留初次无 unwind 拒绝项和随后单独叶认证，不能把初次 unresolved 当作完整恢复或静默抹掉。

## 可调用接线

`read_transform_snapshot(values, previous=None)` 实现一槽；`read_transform_snapshots(values, previous=None)` 保持传入顺序。`None` 明确代表无效 TransformAccess；缺少 previous 时 adapter 拒绝，而非猜测原 buffer 初值。空批次允许，尺寸不一致拒绝。有限数/尺寸/Single 溢出/零 quaternion 的拒绝是适配层安全规则，不冒称原生异常路径已实现。

`prepare_snapshot_bone_inputs(skin_getters, world_to_local, parents_excluding_render, fixed_root_indices, previous=None)` 连续调用：

1. 世界/局部 getter → 六项快照（包含 scale）。
2. 仅 skin 快照 → GenerateBoneClothSelection 参考；显式 Fixed root、Move 默认、局部位置和最大父边长。
3. 同一快照及 WtoL → Import_BoneVertexJob 的 position/normal/tangent 部分。

返回 `SnapshotBoneInputs(snapshots, selection, frames)`；选择和 frame position 可继续输入上一轮 `convert_fresh_selection_grid`。测试已覆盖这一组合。

这只是**显式新建 selection 分支**，不自动覆盖保存的 userEdit selection。skin_getters 不含追加 render 槽；parent/root 索引必须已经在正确收集空间，不能按名字猜。scale 现在保留在 snapshot 中，但 frame-only 模块尚未消费它来生成 skin bindpose/weight。不得据此声称完整 proxy 构建已完成。

## 验证与封存

先写27项测试，因模块缺失失败，再实现通过。覆盖世界/局部区别、Single 与 signed zero 复制、镜像/shear 对角提取、去世界旋转、非单位 quaternion、三个主轴/混合旋转、矩阵通用列与 Single 取消误差、无效槽保留、组合选择/方向/网格、空/错误输入与溢出拒绝。

全套 **1507 passed /114 subtests /3历史skip /2历史Pillow告警**；12个参考模块931语句、256分支覆盖100%。Ruff/format、Pyright零错误/告警，临时 Python 工具环境 pip-audit 无已知漏洞。原生 DLL 未加载执行、未启动游戏、未跑 Unity。测试是源流程夹具，**不是独立 native/Burst 动态 oracle**。

私人证据：`D:/EndfieldTechLib/notes/official-physics-snapshot-20261002-01/review.py`、`review-05/snapshot.json`、`snapshot-instructions.json`、`coverage-full-01.json`。源二进制、metadata、完整指令和模型清单保持本地；精确 hash、验收范围和未完成门禁见 verification.json。

## 下一步：补齐完整导入，再接运行时

1. 复用本轮 scale/rotation/matrix 算术，补 Import_BoneVertexJob 的 skin weight 和 skinBoneBindPose，核查 normalAxis、默认填充以及实际 selection 复用/空间转换；实际11组完整输入仍未生成。
2. 闭合 Team/step、积分/惯性、约束/碰撞/reset 的完整调用顺序。当前参考模块不能直接标为官方运行后端。
3. 在可回退 Unity 后端接唯一骨写入者，核查官方动作/MMD更新时序与静止、转身、下蹲、跳跃、seek、复位、固定步导出。

已认可的舞台、渲染、湿身、阴影和当前预览物理均保持原样。覆盖率不等于项目完成百分比；没有可证明的完成日期，不将下一块的工作预先宣称完成。
