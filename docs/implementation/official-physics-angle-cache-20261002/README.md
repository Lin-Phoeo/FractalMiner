# 官方物理：非root父子边的角度缓存数学

日期：2026-10-02。接续[角度恢复/限幅阶段](../official-physics-angles-20261002/README.md)。实现位于 `Tools/official_physics_angle_cache.py`，是离线纯函数参考，**不是Unity物理后端或完整baseline求解器**。现有Unity舞台、材质、湿身、阴影和预览物理均未修改。

## 本轮完成

- 恢复Quaternion inverse、Quaternion×Quaternion、Quaternion×float3的Single运算边界及分组，没有转成通用Double Hamilton式再一次cast。
- 实现已解析、非root父子边的缓存初始化；四种limit/restoration组合只建立各自需要的缓存。
- 实现限幅后子点旋转缓存计算，使用**当前父缓存**和限幅更新后的父子位置。
- 合成用例覆盖两级父链传播、固定父点、非交换旋转顺序、三轮复用长度缓存、恢复在限幅后执行且不重写旋转缓存。

新增24用例。全套865 passed /114 subtests /3历史skip /2历史Pillow告警。三个参考模块（缓存、角度、距离）的语句与分支覆盖100%；Ruff/format通过，Pyright零错误零告警，工具环境pip-audit无已知漏洞。这不是Unity/C#动态覆盖，也不是执行原始DLL/Burst后的逐位oracle。

## 证据与来源

GameAssembly SHA256 `c24495e51b406f03b03890c4788ee618ae022c991405be5d5b8b787cb775ae89`；metadata SHA256 `0076743397acadf03d3b0064343a963c7c88863b8160526d397e4b3efb96f02e`。全部地址只对应这组文件。

权威本地目录 `D:/EndfieldTechLib/notes/official-physics-angle-cache-20261002-01/complete-02/`。新增Unity.Mathematics.math inventory共282方法入口；选定4方法身份/参数；审查7个unwind family与9个新人工leaf；inverse/multiply的符号float4常量已读取。原始报告与指令只保留本地，不上传GitHub。机器摘要、哈希见verification.json；本地reproduce.py传入**全新目录**可重现。complete-01因直线leaf白名单遗漏已观察到的movaps中止，未写完整报告；保留，不能当权威输出。

| 原始kernel使用的helper | RVA | 范围 |
| --- | --- | --- |
| Quaternion inverse | 0x39d3e70 | 123字节unwind |
| Quaternion product | 0x305d080 | 568字节unwind |
| Quaternion rotate float3 | 0x2cd4520 | 629字节unwind |
| dot(float4,float4) | 0x39d3f10 | 51字节人工leaf，认证method440514 |
| scalar×float4 | 0x39d3ef0 | 18字节人工leaf |
| float4 component product | 0x305d2c0 | 65字节人工leaf |
| float4 add / subtract | 0x305dd60 /0x305c750 | 各65字节人工leaf |
| float3 component product / subtract / add | 0x4a48fa0 /0x2ef3960 /0x305c6e0 | 各49字节人工leaf |
| scalar×float3 | 0x4a70140 | 41字节人工leaf |

新leaf均从已观察入口到RET，精确解码并检查直线指令白名单；不猜相邻方法间距，不把padding算进函数，也不冒称有unwind或通用自动全CFG认证。

managed数学入口另行认证：inverse(quaternion) method440652 /0xa1e8700；mul(quaternion,quaternion) 440658 /0xa1e9704；mul(quaternion,float3) 440659 /0xa1ea710。参数type definition55855=quaternion，55831=float3，dot的55836=float4，native kind/valuetype与metadata一致。**这些managed inverse/mul不是kernel helper相同地址**；共同低层操作及相符算术是人工数据流交叉核对，不是自动二进制等价证明。未证实际Burst目标。

本地官方Unity.Mathematics 1.2.6包quaternion.cs:502/630/640佐证inverse、swizzle乘法及旋转表达式；没有复制商业物理库源码。首轮测试曾误以为两级零限幅、identity local的子旋转必须不同于父旋转；实际应继承父旋转，已修正合成测试预期，没有改原始规则迁就错误预期。

## Single算术边界

S表示Single舍入，Quaternion分量顺序xyzw。

```text
norm = S(S(S(S(y*y)+S(x*x))+S(z*z))+S(w*w))
r = S(1/norm)
inverse = S(componentwise(S(r*q)*(-1,-1,-1,+1)))
```

inverse不是只有conjugate；非单位Quaternion不会先normalize。符号常量在0xa8c32e0。除法倒数和两次component乘法分开舍入。

```text
mul(a,b) = S( S(S(a.wwww*b)
                    + S(S(S(a.xyzx*b.wwwx)+S(a.yzxy*b.zxyy))*(1,1,1,-1)))
                - S(a.zxyz*b.yzxz))
```

符号在0xa8c2ed0；保留每个helper调用的乘、加、符号乘、加、减分组。不得改为四个Hamilton单分量连加再cast；测试用大/小混合分量区分舍入结果。输出不再normalize。

float3旋转使用各步Single cross：每个乘法、减法、×2、w乘法、两次加法各自舍入。不能调用Double旋转后只cast一次；缓存local方向float3→Double为精确扩大，不补normalize。

## 两个API的输入与输出契约

`initialize_edge_cache`只接受已定位的**非root父子边**，不查骨名、索引或资格，也不改变输入：

```text
basicDelta = childBasicWorld - parentBasicWorld       # Double3
if useLimit:
  inv = inverse(parentBasicQuaternion)               # Single4
  localDirection = float3(rotate_double(inv,normalize(basicDelta)))
  localRotation = mul(inv,childBasicQuaternion)
  cachedLength = S(distance(childNext,parentNext))    # 当前next位置，不是basic长度
if useRestoration:
  restorationWorldVector = float3(basicDelta)         # 保留长度，不转父局部
```

disabled缓存以None表示“此路径不建立/读取”，**不是宣称官方清空缓冲**。限幅关闭时不要求逆Quaternion、局部方向/旋转或length；两个开关关闭时不进行输入数学。root和所有节点的rotationBuffer=stepBasicRotation复制仍由未来调用层负责，这个edge API没有假造root缓存。

`limit_cached_edge`接收当前父rotationCache与上述immutable cache，返回位置/velocity修正和新子Quaternion：

```text
basis = rotate_single(currentParentRotationCache,childLocalDirection)
pair = original_limit_pair(currentPositions,currentVelocity,basis,cachedLength,...)
baseProduct = mul(currentParentRotationCache,childLocalRotation)
alignment = FromToRotation(Double(basis),pair.childPosition-pair.parentPosition,1)
newChildRotationCache = mul(alignment,baseProduct)
```

限幅调用后，即使角度原本已满足，仍有半长度修正和旋转缓存更新。limit_pair参数/摩擦/pivot/velocity规则沿用前阶段，没有改阈值或调参。固定父点不移动；不把其权重补给子点。

当恢复也开启，应使用pair更新的位置调用restoration_pair，但保留刚写出的旋转缓存；**恢复不会再用最终恢复后的方向重算Quaternion**。下游边应读取该父Quaternion以及当前更新位置。子边移动其父点时，没有凭空再补一个祖先递归旋转更新。

## 非官方声明与下一步

有限、非零方向、非正Quaternion norm/length拒绝是离线适配策略，不是原生NaN/异常行为。沿用原始有符号反向选轴及近同向阈值；未用“健壮通用旋转”悄悄替换原生规则。Python libm与原CRT逐位一致性仍未证明。

当前没有baseline/Team分配、root资格、attribute gate、共享buffer原位遍历、Job调度、积分/惯性、碰撞或骨骼写回。三轮用例为合成顺序接线检查，不能用来宣称实际跨baseline调度已证。

下一主线：

1. 补baseline/Team/root/attribute的解析、所有节点rotation copy与共享状态写回；核查同组/跨组Job依赖和实际Burst路径。不能把所有非root一律当可移动节点。
2. 沿原始积分/碰撞/复位/最终旋转链继续恢复；11组角色配置与碰撞挂点已有绑定证据，但原始字段值不等于全求解器完成。
3. 再接Unity可切回后端，保证骨写回单所有者；做静止、转身、下蹲、跳跃、急加速动态验证，随后验MMD倒拖、循环与固定出帧。

核心模块没有提弗洛斯专用骨名，利于后续角色共用；角色绑定和坐标空间仍需各自的适配层，不能直接替换当前Unity预览。主HEAD/主index/六项保护runtime与用户现有修改后的舞台hash均保持，舞台不提交。
