# 官方物理：Transform 写入值与顺序

日期：2026-10-03。接续[跨帧调度参考](../official-physics-scheduling-20261003/README.md)。新增 `Tools/official_physics_setter.py`，恢复限定有限输入下的 **WriteTransformJob 单槽写入值、门控和顺序**。它返回写入操作，不执行 TransformAccess、不更新骨骼层级，也不是已接入 Unity 的官方求解器。现有舞台、渲染、湿身、自阴影及预览物理均未修改。

## 恢复的实际分支

1. 先检查 Transform 有效性，再检查槽 flag 的 `0x10`；随后读取 Team。这里**没有 teamId=0 自动跳过的源分支**，不能从其他 Job 搬来这个门控。
2. Team flag 的低 UInt32 中，`0x800` 或 `0x80000` 置位则剔除。
3. 有效权重为 `Single(Single(clothSimulateWeight) × Single(clothLodFadeWeight))`，字段偏移分别为 240、244，**不是偏移260的 blendWeight**。权重≤0不读取目标缓冲；权重≥1不读取当前 Transform 值、不插值，也不强制归一化。
4. 槽 flag 的世界分支 `2` 优先；只有世界分支未选中才检查局部分支 `4`，不能两个都执行。
5. 世界分支先读取并检查目标 Double3 位置，即便最终不写位置也如此。世界旋转先混合，再按相对分支变换，最后检查有效性。**世界旋转先写，世界位置后写**；位置写入另需 Team flag `0x2000`。
6. 世界 Double3 位置在插值和相对矩阵乘法**之前**转换为 Single3。局部分支不受 `0x2000` 控制，**局部位置先写、局部旋转后写**。
7. 最终有限四元数的平方范数低于 `Single(.01)` 时，只跳过该旋转 setter，不撤回其他位置写入，也不补单位四元数。

当前/last 的选择仍由 manager 决定，沿用[缓冲发布参考](../official-physics-publication-20261002/README.md)。Job 的数组字段名带 last，不能据此把普通模式也改为消费上一帧。模块不自行选择帧龄。

## 插值和相对坐标

旋转采用最短弧 slerp：dot<0翻转目标四元数，dot≥`Single(.9995)`使用 normalized-lerp；其余走 sqrt、acos、sin 权重路径。普通 slerp 不额外归一化输入/输出，满权重不进入插值。保留源 Single 分组，位置为 `a+(b-a)*t`。

相对变换的真实开关是 **useRelativeTransform@156 非零**，不是 syncTeamId@188 或 syncParentTeamId@192。旧路线文档的泛称“relative-sync”不能当作开关定义。

源 LocalToWorldMatrix 辅助链构造 **正向 `TRS(relativeTransformPos, relativeTransformRot, Vector3.one)`**，再通过四次 GetColumn 转为列矩阵；没有取逆。世界位置使用该矩阵乘已混合位置，旋转使用 `Quaternion(matrix) × 已混合旋转`。点乘顺序为 `((col0*x+col1*y)+col2*z)+col3`，取xyz、不做w除法。

**尚未移植原生 TRS 构造和 Quaternion(matrix) 构造。** 当前 `RelativeWriteContext` 要求调用者提供真正解析出的四列矩阵和矩阵四元数，缺失时明确拒绝，绝不填 identity。测试中的矩阵是合成夹具，不是11组真实 Team 输入。局部分支不读取这个上下文。

## 源证据与边界

绑定 GameAssembly SHA256 `c24495e51b406f03b03890c4788ee618ae022c991405be5d5b8b787cb775ae89`，metadata SHA256 `0076743397acadf03d3b0064343a963c7c88863b8160526d397e4b3efb96f02e`。主入口 WriteTransformJob.Execute369494，RVA `0x5a277d4`，2173字节。Team stride为464；源布局及辅助函数边界见 [verification.json](verification.json)。

有 exact unwind 的函数按真实边界读取。无该记录的短叶函数仅在限定白名单、无调用/间接跳转/外部跳转、所有可达路径抵达RET且解码连续的情况下恢复局部CFG；**不拿下一方法地址猜长度**。私有报告保留完整指令，仓库只记录结论、入口与哈希。

有限值、索引及类型验证属于本参考的 adapter 政策。源位置向量检查 NaN，并非同时拒绝 Infinity；源四元数额外检查有限分量和平方范数。本参考拒绝 NaN/Inf/溢出，**不声称原生非法输入异常或局部副作用相同**。返回操作序列只覆盖成功调用的值/顺序，不执行 getter/setter，也不模拟 setter 对后续层级或 getter 的反馈。

## 验证

- 先写测试，缺模块 RED；新增67项 GREEN，覆盖门控、权重乘积、世界/局部优先级与顺序、满权重不读 getter、旋转局部跳过、Double→Single时点、相对矩阵正向乘法、两帧缓冲组合及 adapter 拒绝边界。
- 全套 **1854 passed /114 subtests /3历史skip /2历史Pillow告警**。19个参考模块1535语句/414分支，branch-inclusive覆盖100%；本模块117语句/46分支全覆盖。Ruff、格式检查、Pyright通过；临时工具 pip-audit 无已知漏洞。覆盖率不是官方物理完成比例。
- 独立 C# 程序使用未修改的本地 Unity.Mathematics.dll，在1005组夹具中复核 `math.slerp`、`math.transform`、`math.mul`，合计11055个 Single 分量 **原始位模式差异0**。关闭硬件intrinsics；种子与库哈希固定。此结果只证明该托管库/该环境/该样本下的数学一致，不证明游戏原生CRT、Burst、完整setter、原始角色轨迹或动态层级一致。程序未加载游戏DLL。
- 主 HEAD、9557项用户原 index、7项runtime文件保持；保留用户现有舞台变更。没有运行 Unity，没有新增已验证的可见物理效果，没有启动/附加游戏。

私有留存：`D:/EndfieldTechLib/notes/official-physics-setter-20261003-01/`，最终静态报告 `review-08/`、独立数学复核 `oracle/oracle-03.json`、覆盖报告 `coverage-full-02.json`。原资产、完整指令、第三方源码和DLL不入库。

## 下一步

1. 补齐相对矩阵与矩阵四元数的源构造；恢复 ReadTransform/RestoreTransform，并确定动画与物理的唯一写入者。不能用本参考的返回列表宣称已跑实际setter。
2. 补全11组proxy、Team发布、normalAxis下游、step/collision/惯性/reset；Animator委托Job与非空mesh mapping继续单独恢复。
3. 成功调用链和真实输入闭合后，再接入可回退的Unity候选后端，验证MMD/解包动画、暂停恢复/跳帧、层级更新与唯一回写。保留定制跨帧调度与stock Unity兼容策略之间的差异。

**本轮完成的是有限输入的骨骼写入值与顺序参考；完整官方物理及Unity接入仍未完成。**

后续：[读取/恢复参考](../official-physics-read-restore-20261003/README.md)分别恢复了不同门控、init局部缓冲来源、有符号缩放与相对逆矩阵消费。该记录不代表实际Unity层级或Animator链已经接入；相对矩阵源构造仍需补齐。
