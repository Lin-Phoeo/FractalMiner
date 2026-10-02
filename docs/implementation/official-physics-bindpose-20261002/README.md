# 官方物理：补齐骨骼顶点的权重与绑定矩阵

日期：2026-10-02。接续[世界/局部快照及 scale](../official-physics-snapshot-20261002/README.md)。新增 `Tools/official_physics_bindpose.py`，复用已封存的 position/normal/tangent 和快照/scale 参考，补齐 **Import_BoneVertexJob 的五项有限数输出**：局部位置、normal、tangent、boneWeight、skinBoneBindPose。不是完整 ImportBoneType、实际11组 proxy 或 Unity 官方物理后端。

## 原始写入与运算顺序

沿用源 DLL/metadata hash；原 Job method371578/RVA0x34e00c0，837字节，SHA256 `3742e3d30b36271a0905ae65353c5452d8c6f523cc52e4eaa17e3f563543f2db`。原始资产、完整指令和商业源码没有发布。没有加载原 DLL、运行游戏、附加进程或修改舞台。

1. 位置/方向继续走上一轮已验证的 WtoL、世界 quaternion、长度补偿路径，不重写已封存代码。
2. index=i 的顶点权重写为 float4 `(1,0,0,0)`，索引写为 int4 `(i,0,0,0)`；**不是四骨插值，也不是复制角色原网格的蒙皮权重**。骨序是 collector 的 skin slot 序，不按名字/PathID排序，不附加 render slot。
3. helper0x305d310 生成 `TRS(worldPosition, rawWorldQuaternion, recoveredWorldScale)`：先构造 quaternion 矩阵，前三列各乘对应 scale，第四列写 xyz 世界平移与 w=1。没有额外 normalize；signed scale 不取绝对值。
4. math.inverse method440437/RVA0x34e0d80 对上述 TRS 做**通用4×4求逆**，不是 fastinverse、单纯 transpose、伪逆或逐轴倒数简写。
5. helper0x305d9c0 计算 `inverse(boneWorldTRS) * renderLtoW`，结果写 skinBoneBindPoses[i]。乘法右操作数来自 Job.LtoW@64，不是 WtoL，不交换两矩阵。

scale 输入必须使用上一轮恢复的世界矩阵去旋转对角提取规则，而非 prefab localScale。原 Job 以 TRS 重建骨世界矩阵，**不直接把带 shear 的 getter localToWorldMatrix 拿去求逆**；这是原流程的区别，不做“更准确”的自行替换。

例如：骨世界位置x=10、scale.x=2、renderLtoW平移x=4，绑定平移结果x=-3。交换乘法顺序会得出不同结果，测试用此区分。

## 静态身份与边界核查

- 权重常数实际 RIP 数据是 `0000803f000000000000000000000000`；Job index 写索引首槽，其余12字节清零，stride32。VirtualMeshBoneWeight 元数据字段布局 weights@0、boneIndices@16与此一致；**尚未验证 NativeArray 泛型运行时实例字段布局/实际指针**，不能把静态布局直接冒充泛型运行证明。
- TRS helper0x305d310完整368字节；另检查 math.float4x4.TRS method441165/RVA0xa1f2fb4 的438字节实现，使用相同 quaternion、逐列scale和float4拼接规则。不凭函数名替代实际 Job 的 helper。
- inverse0x34e0d80完整2622字节，恢复其原始 packed minor 运算。逐项Single乘/减/加；分母先成对相加，再成对相减；四项分别 `1/denom`，两项符号为正、两项为负。没有 Double determinant/FMA/数值库重排。
- shuffle helper0x34e17c0 的 unwind 区间包含四个 jump table，初次线性解码拒绝“不完整指令”。本轮另以四表×8项的有界可达CFG验证有效选择器0..7路径，跳表目标均在函数代码区；**非法选择器的throw分支显式排除**，没有抹掉原拒绝项或把表数据当指令。
- float4 componentwise乘/减、float3 scalar乘无 unwind 的叶函数按受限直线指令读取到RET；调用/跳转/越界不猜。复制、swizzle可以合并，浮点运算顺序不合并。

有限数、Single溢出、输入长度不齐、Single determinant=0/下溢拒绝，都是 adapter 策略；原 native 对奇异矩阵产生Inf/NaN的路径没有移植。支持负determinant；不使用“必须正数”的检查误杀镜像。固定65536项安全限额不是原生容量声明。离线API完整成功后才返回，不冒称原 native 逐个缓冲写入的失败时序。

## 可调用组合

- `bone_trs_single(position, rotation, scale)`：世界TRS参考。
- `inverse_matrix_single(matrix)`：完整4×4有限/非奇异参考，含非仿射矩阵，不限刚体。
- `import_bone_vertices(world_to_local, local_to_world, world_positions, world_rotations, world_scales)`：返回 `ImportedBoneVertices(frames, bone_weights, skin_bone_bindposes)`。
- `prepare_bound_bone_inputs(skin_getters, world_to_local, local_to_world, parents_excluding_render, fixed_root_indices, previous=None)`：getter输出→六项快照→显式新建selection→五项骨骼顶点输出；返回 `BoundBoneInputs(inputs, vertices)`。

WtoL、LtoW由调用者提供原始 render 矩阵，不擅自从一个求逆得到另一个、不默认identity。skin_getters仅skin槽，根/父索引已经正确解析；不覆盖保存的 userEdit selection。位置、normal、tangent与之前组合保持一致，新增的scale被真正消费生成bindpose，不再只是保存在快照中。

这仍不包含 normalAxis下游调整、代理拓扑/默认填充、selection复用/空间转换、collision/Team/step、完整求解和Unity骨写回。

## 独立数学库校验，避免循环论证

本轮额外建了独立C#进程，直接调用**未修改的现有 Unity.Mathematics.dll**，不引用Python实现、不替换库函数、不执行游戏DLL。

DLL本地raw SHA256：`5d575d3944c32c88d4b6b7516bedb1fc281a978738c5d1df0b246996cdebd9b7`。本地package源码标识1.2.6，用于交叉阅读 packed inverse/TRS；不同游戏函数以原DLL指令证据为准，不以包版本代替游戏验证。矩阵列存储的公开参考：[Unity.Mathematics float4x4定义](https://raw.githubusercontent.com/Unity-Technologies/Unity.Mathematics/master/src/Unity.Mathematics/float4x4.gen.cs)。依赖库没有复制进Git，仍受其原有许可约束。

固定随机种子20261002，1500组随机数据（含一般4×4、非单位quaternion、负/非均匀scale）+1组signed zero。C#直接计算TRS、matrix inverse、`mul(inverse(TRS), render)`、快照scale；Python按原指令参考计算。**72048个矩阵分量、4503个scale分量，以float32原始位比对，0不一致。**

C#运行时关闭HWIntrinsic/FMA，记录环境；这些是数学内核的独立实现核验，**不是官方 native/Burst、原浮点环境或真实角色动态轨迹的oracle**。普通测试另用NumPy Double inverse检查一般矩阵的代数性质；容差只用于数学测试，不做渲染逐像素拟合。

私人复现位置：`D:/EndfieldTechLib/notes/official-physics-bindpose-20261002-01/`。

```powershell
dotnet build D:/EndfieldTechLib/notes/official-physics-bindpose-20261002-01/oracle/Oracle.csproj -c Release
uv run --python 3.12 python D:/EndfieldTechLib/notes/official-physics-bindpose-20261002-01/check_oracle.py oracle-next.json
```

输出文件必须是新名字，脚本拒绝覆盖既有证据。`oracle-01.json`为本轮封存结果；`review.py`、`review-05/bindpose.json`与`bindpose-instructions.json`为只读源审计，精确hash见verification.json。

## 回归与剩余主线

先写26项测试，缺模块失败，再实现通过。全套 **1533 passed /114 subtests /3历史skip /2历史Pillow告警**；13个参考模块1010语句、262分支覆盖100%。Ruff/format、Pyright零错误告警、临时Python工具pip-audit无已知漏洞；独立C# harness build零错误/告警。已封存旧模块hash未改变，七项runtime保护文件未改变；主HEAD/index和其他工作不动。

下一步直接使用这条完整骨骼顶点输入链：核查实际构建/selection复用分支及normalAxis/默认填充，生成真实11组完整proxy输入；随后闭合collision、Team/step和求解/reset/唯一骨写入者，再在Unity动作/MMD路径做动态验收。**完整官方物理仍未接入舞台**；测试通过不是整体项目完成比例，不预先宣称“只剩最后一步”。
