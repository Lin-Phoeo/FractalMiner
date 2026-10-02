# 官方物理：代理绑定方向与写入标志

日期：2026-10-02。接续[骨骼权重和绑定矩阵](../official-physics-bindpose-20261002/README.md)，新增 `Tools/official_physics_proxy_frames.py`：三项原始Job的有限输入参考、None模式的默认方向修正契约、已有快照→骨骼导入的数据接线。**没有更换Unity舞台物理，不是完整ConvertProxyMesh或原版实时物理。**

## 可复用的实现

- `vertex_bindpose_frames`：位置为proxy位置的逐分量负值；旋转为normal/tangent构成frame的逆。两者分开存储，**位置没有先被逆旋转**，不能替换成通用inverse(TRS)的translation。它和上游skinBoneBindPoses矩阵是不同输出。
- `vertex_to_transform_rotations`：`inverse(frame) * (initInverseRotation * originalWorldRotation)`，保持乘法次序、原四元数大小和Single分组。不拿FBX localRotation、子骨方向或单位旋转冒充输入。
- `apply_bone_transform_flags`：Move位(2)优先OR4；否则Fixed位(1)OR2；任一有效再OR8。已有flags全部保留；两个attribute位同时设置不同时OR2和OR4。这些flag本身不证明Unity唯一写入者已成立。
- `default_normal_adjustments`：alignment None(0)时，每顶点identity。尚未移植模式1/2，显式拒绝，不静默退化为None。
- `prepare_bone_proxy_frames`：消费`BoundBoneInputs`、显式原始initInverseRotation和初始transformFlags，返回上述四类输出及原bound。

合成API的前提是**未重排的一对一skin/proxy索引、新生成selection、骨骼proxy、None模式**。不是实际保存selection分支、selection减点、mesh合并或三角法线重建的替代路径；不自动决定原游戏导入分支，不覆盖已有编辑过的selection。

frame仍是normal=UP、tangent=FORWARD，不额外归一化输入。逆旋转为`1/dot(q,q)`后乘`q*(-1,-1,-1,+1)`，**不是归一化共轭**；frame虽通常接近单位，额外normalize仍会改Single位。位置取负保留signed-zero翻转和subnormal。非有限/Single溢出/buffer不平行/退化frame/范围错误拒绝是adapter政策，不冒充原生异常；65536顶点是离线安全上限，不是Job的Int32上限。

## 原始身份与顺序

仅静态读取封存GameAssembly/metadata，SHA见verification.json。未执行游戏DLL、启动/注入/附加游戏。完整指令、原资产、第三方库及商业源码仅私有保存，不提交GitHub。

| 对象 | method / RVA | 有界字节数 |
| --- | --- | --- |
| ProxyNormalAdjustment | 371527 / 0x43f6b10 | 六段unwind family共888 |
| Proxy_CalcVertexToTransformJob.Execute | 371595 / 0x39d3c00 | 301 |
| Proxy_CalcVertexBindPoseJob2.Execute | 371597 / 0x39d3d30 | 315 |
| Proxy_BoneClothApplayTransformFlagJob.Execute | 371603 / 0x343c570 | 378 |

frame Job复用已认证的rotation0x39d4250、multiply0x305d080与inverse算术。新增受限直线到RET认证：position符号翻转0x39d3f50/49字节、float4 dot0x39d3f10/51、scalar*float4 0x39d3ef0/18、逐分量float4乘0x305d2c0/65。dot是`((y*y+x*x)+z*z)+w*w`，没有sqrt；调用侧倒数再乘(-1,-1,-1,+1)，与既有quaternion_inverse相同。

ConvertProxyMesh旧线性解码失败是末尾两张RVA跳表被当成指令。本轮按**精确unwind范围**0x3ddaf90–0x3ddc4bc分区认证：5362字节完整代码、2字节6690对齐、两张各7项/28字节跳表。两处table加载site、所有target指令边界均验证；**不是整函数已经移植**。

原Convert片段：骨骼CreateTransformBaseLine → ProxyNormalAdjustment(0x3ddbffa) → 骨骼vertexToTransform调度(0x3ddc0e4) → vertexBindPose调度(0x3ddc1b4) → 后续CreateBaseLinePose/CreateVertexRootAndDepth。没有把末尾table误读为FPU操作或猜边界跳过错误。

## 默认调整和normalAxis必须分开

配置SHA `ce377a025cc16e68a0382e92d73b0b47c82641550f79f58846dcc68af4ad9b3d`：11组均`normalAxis=1`、`alignmentMode=0`；metadata枚举分别确认为Up、None。**二者不是同一开关。**

ProxyNormalAdjustment先分配normalAdjustmentRotations@0x290，读取quaternion.identity静态首槽，构造value+NativeArray输入并调度helper0x37c1d20；再检查ClothSerializeData.normalAlignmentSetting@0x80的alignmentMode@0x10，0直接返回。模式1/2走BoundingBoxCenter/Transform辐射调整，不凭函数名套用AxisQuaternion。

RIP0x43f6bc4为IJobParallelForExtensions.Run MethodSpec（定义355187、method generic index17498）；NativeArray ctor、辐射Run身份亦认证。但泛型FillJob.Execute最终写入和游戏实际buffer仍未动态证明。本模块实现**调用侧None模式填充契约**，不宣称泛型调度后端恢复。normalAxis完整下游消费也未闭合，因此没给proxy frame凭空追加轴旋转。

## 验证和下一步

TDD先缺模块RED，后38项测试通过；包括负位置而非逆TRS平移、signed zero/subnormal、乘法次序、原四元数大小、旗标优先级/保留旧位、退化拒绝、快照合成、独立原库raw-bit固定fixture。

私有独立.NET harness只引用**未修改的本地Unity.Mathematics.dll**（SHA见verification），不引用Python实现、不运行GameAssembly、不改库。seed20261002，1201组非单位/非正交方向及原四元数，frame/inverse(frame)/vertexToTransform共14412个Single分量，原始位比较0不一致。首次build日志读取有GBK解码线程告警，修为UTF-8后oracle-02干净重跑。此验证仅认证算术，不证明原游戏浮点环境/Burst/Job布局/物理轨迹。

全套1571 passed /114 subtests /3历史skip /2历史Pillow告警；14参考模块1069语句/276分支100%覆盖；Ruff/format、Pyright、临时工具pip-audit通过。七项runtime保护文件、主HEAD/index保留。Unity未重跑，本轮没有新视觉效果。

后续：实际快照和保存selection分支/空间转换 → 11组完整proxy及碰撞/Team/step输入 → 完整求解/inertia/reset → Unity唯一骨骼写入与解包动作/MMD固定时步验证。不要用离线合成或覆盖计数宣称原版实时物理完成。
