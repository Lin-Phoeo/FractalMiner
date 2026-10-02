# 官方物理：骨骼读取、恢复与有符号缩放

日期：2026-10-03。接续[Transform写入参考](../official-physics-setter-20261003/README.md)。新增 `Tools/official_physics_read_restore.py`，实现限定有限输入下的 **ReadTransformJob最终缓冲值、RestoreTransformJob操作序列及ReadComponentTransformJob位置读取**。不执行Unity getter/setter，不更新骨骼层级，不是完整官方物理或新的舞台效果。

## 三条路径不能共用门控

| 路径 | 槽flag条件 | Team条件 | 结果 |
| --- | --- | --- | --- |
| RestoreTransformJob | 先需mask0x08；随后enable mask0x10 **或** Team mask0x100000 | (mask0x800 **且** mask0x1000) 或mask0x80000时跳过 | 初始局部位置先写、初始局部旋转后写 |
| ReadTransformJob | enable mask0x10 **且** read mask0x01 | mask0x800、mask0x80000或(1<<61)任一置位跳过 | 读取当前Transform的姿态、矩阵并更新缓冲 |
| ReadComponentTransformJob | 不读槽flag或Team | 不读Team | 有效Transform的Single3世界位置 |

三者都先检查传入TransformAccess首qword是否非零。本参考要求调用者提供已确定的bool有效性，不重建原生hierarchy指针。`get_isValid`包装函数无exact unwind记录，未猜测完整函数范围；Job中的直接非零检查已核查。

Restore在仅0x800或仅0x1000时仍可恢复；不能套用Read/输出setter的剔除规则。这里没有新增team0跳过、恢复权重、相对坐标变换、四元数归一化或输出setter的`.01`范数筛选。有限的零四元数仍可作为恢复操作值返回。非法输入处理不作原生等价声明。

## 恢复取初始缓冲，不取上一帧

manager RestoreTransform369423将 `initLocalPositionArray@24`、`initLocalRotationArray@32` 传入Job的 localPositionArray/localRotationArray。**Job字段名虽叫local，实际输入是init数组**。不能将ReadTransform后不断变化的局部缓冲、current/last物理输出或当前VMD采样代替它。

本参考要求调用者显式提供原init数组，不自行推断它等于模型绑定姿态或当前动画首帧。原始注册时如何生成/更新init数组仍需接续核查。返回操作顺序为局部位置→局部旋转，不回写localScale。没有实际执行Transform层级、动画覆盖或多个写入者的时序试验。

## 读取的关键数学

源getter顺序：世界位置→世界旋转→localToWorldMatrix→局部位置→局部旋转。输入是getter的Single值，不能把普通世界getter位置假称为原生Double精度。

缩放不是localScale、lossyScale、列向量长度或绝对值。源先构造零平移的 `float4x4(inverse(worldQuaternion), float3.zero)`，左乘原getter的localToWorldMatrix，再取 **c0.x、c1.y、c2.z**。保留有符号结果和剪切矩阵下的原定义，不引入“修正负缩放”。本轮实现该矩阵构造和乘法的Single分组，不强制归一化四元数。

源写入顺序：localPosition→localRotation→scale→原matrix→worldPosition→worldRotation→最终matrix。普通模式最后再写一次同一matrix；本参考记录该顺序和最终值，**不是逐次执行的NativeArray写入，也不模拟部分异常副作用**。

相对读取开关仍为useRelativeTransform@156非零，非syncTeam字段。相对读取通过 WorldToLocalMatrix 辅助链取得 **TRS(relativePos,relativeRot,Vector3.one)的逆矩阵**；它与输出setter使用的正向TRS方向相反，不能共用同方向矩阵。

- 相对矩阵变换Single世界位置，然后才扩展成Double3写缓冲。
- 相对矩阵四元数左乘世界getter旋转；逆矩阵左乘getter matrix。
- localPosition/localRotation和已计算的scale保持原getter空间，不重复相对变换。
- 原生TRS、逆矩阵构造及Quaternion(matrix)尚未移植；`RelativeReadContext`要求真正解析出的逆矩阵及其四元数，不自动填identity。矩阵与四元数的一致性是调用方前提，合成测试不证明真实Team构造闭合。

## 源绑定、验证及私有证据

GameAssembly SHA256 `c24495e51b406f03b03890c4788ee618ae022c991405be5d5b8b787cb775ae89`，metadata SHA256 `0076743397acadf03d3b0064343a963c7c88863b8160526d397e4b3efb96f02e`。ReadTransformJob369465/0x5a1e6d8/1653字节，RestoreTransformJob369464/0x5a1ed50/433字节，ReadComponentTransformJob369495/0x5a1e668/112字节。manager传参、Team stride464、两组Job布局分别核查。

按exact unwind family读取主函数；少数短叶复制、位XOR、加减乘与扩展函数仅接受限定的无分支/无调用白名单并在RET结束，不从相邻方法猜长度。共享RVA可能有多个metadata别名，数学角色由调用点和指令确认，不擅自给未确定身份的helper指定唯一方法名。float3.zero的typeinfo usage及static offset0已核查，不声称观察到了运行时storage。

技能要求先写测试：缺模块RED，新增 **79项GREEN**。覆盖不同门控、停用恢复、init缓冲、team0、零四元数恢复、世界位置Single→Double、原始有符号缩放、矩阵乘法次序、相对读取和有限adapter拒绝。全套 **1933 passed /114 subtests /3历史skip /2历史Pillow告警**。20参考模块1638语句/442分支，branch-inclusive覆盖100%；本模块103语句/28分支全覆盖。Ruff/格式检查/Pyright通过，临时工具pip-audit无已知漏洞；覆盖率不代表官方物理完成比例。

独立C#程序调用未修改的本地Unity.Mathematics.dll，以1008组输入复核旋转平移矩阵、逆旋转矩阵、一般4×4矩阵乘法和读取scale，共51408个Single分量，**原始位模式差异0**。含非单位四元数、负零和任意四列矩阵；关闭硬件intrinsics，固定随机种子。该结果限定在此托管库/环境/样本，**不是游戏原生、Burst、真实11组Team或动态hierarchy oracle**，不证明原生相对TRS构造等价。

完整私有报告：`D:/EndfieldTechLib/notes/official-physics-read-restore-20261003-01/review-05/`；数学复核 `oracle/oracle-01.json`；覆盖 `coverage-full-01.json`。哈希和门禁见[verification.json](verification.json)。原资产、完整指令、第三方源码与DLL均不提交。7项runtime、主HEAD和9557项用户原index保持；没有运行Unity或游戏，没有修改现有舞台/湿身/阴影/预览物理。

## 下一步

1. 继续核查注册init数组、读缓冲和动画唯一writer的关系；Animator读取Job的31字节入口仅是转发到0x5a1dc98，**未移植后续主体**，不能以普通读取Job代替。
2. 补齐相对TRS/逆矩阵/矩阵四元数构造、真实11组proxy/Team发布、normalAxis下游，以及step/collision/惯性/reset，保留跨帧调度约束。
3. 完整候选链具备真实输入后，再在Unity接入可回退后端并验证MMD与解包动画、暂停恢复/跳帧和唯一回写。当前效果保持，不能把本轮数学测试称为新可见效果验收。
