# 官方物理：距离内核数学与角度参数阶段

日期：2026-10-02。接续 [时钟阶段](../official-physics-clock-20261002/README.md)。本阶段以原始 metadata / GameAssembly 的身份、字段与数据流为依据，不靠逐像素调参。新增的是**离线数学参考**，没有替换 Unity 舞台物理，没有宣称完整官方后端可用。

后续进展：[角度恢复与限幅离线数学阶段](../official-physics-angles-20261002/README.md)。下文保留本阶段历史状态；新阶段已补单边角度公式，完整旋转缓存与实时求解器仍未闭合。

## 本阶段实际完成与边界

- 原生布局工具支持值类型，区分 registration/boxed offset 和 unboxed struct offset；保留旧 `offset` 含义，新增 `unboxed_offset`，不破坏 class 查询。
- 距离/角度的 Job、range dispatcher、kernel、`$BurstManaged` 及 Burst direct-call 入口已登记；核查参数结构和 managed 距离内核核心计算、缓冲读写。
- 恢复 EvaluateCurve、一个 CalcInverseMass 重载及**通过资格判定后单粒子的距离修正**，实现于 `Tools/official_physics_constraints.py`，附合成数学测试。
- 角度结构字段和参数转换已核查；角度恢复/限幅全数学、旋转写回**未闭合**。不能把“定位5,762字节内核”记成“角度算法完成”。

没有执行DLL、附加游戏进程、注入或启动Unity。`$BurstManaged` 是文件中可认证的 managed fallback；**实际运行时Burst指针目标、优化内核等价性和Job调度顺序仍待核查**。离线输入验证是我们的适配策略，不是原生异常/NaN行为；Python参考及合成测试也不是执行官方DLL后的逐位对照。

## 来源与证据

binary SHA256：`c24495e51b406f03b03890c4788ee618ae022c991405be5d5b8b787cb775ae89`；metadata SHA256：`0076743397acadf03d3b0064343a963c7c88863b8160526d397e4b3efb96f02e`。所有地址只适用于这组文件。

权威本地报告：`D:/EndfieldTechLib/notes/official-physics-constraints-20261002-01/complete-03/`。父目录第一次native/calls输出保留，但辅助审查遇到无unwind的叶函数而中止，**第一次输出不作为完整证据**。区分明确的人工leaf路径后重跑到complete-02；最终将class的offset_base明确标作object（不是boxed value），完整重跑到complete-03，没有猜邻近方法之间的长度。

53 inventories /1,274 managed entries /16 layouts；82 selected：78 unwind families /192 ranges、3前阶段受限叶路径、1 pending ForceCompleteAllJob；共69,958字节有界解码。另有21项helper review，其中3个人工leaf路径，不冒充自动全CFG认证。完整native报告、原二进制和metadata不上传GitHub。

## 值类型、布局与精度

registration值类型实例字段包含boxed对象头。当前PE64上两指针合计16字节：unboxed offset=registration offset−16；static绝不减。metadata bit1和native kind/valuetype必须一致，byref/mod/pinned及不足16的实例偏移拒绝。布局参考已有Il2CppDumper MIT资料（`Tools/THIRD_PARTY_IL2CPP_NOTICE.txt`）；未复制商业物理库源码。

交叉核对：float3 registered x/y/z=16/20/24，unboxed=0/4/8；double3=16/24/32，unboxed=0/8/16。method368841的nextPos/basePos/velocityPos pointer记录都指向 **Unity.Mathematics.double3**（definition55820），与24字节步幅和Double算术一致，不能用float3替换。

DistanceParams unboxed：restorationStiffness(float4x4)=0、velocityAttenuation(Single)=64。ClothParameters.distanceConstraint=244、angleConstraint=320，stride808；TeamData stride464。DistanceJob：power=0，index list16、Team32、params48、attributes64、depth80、teamId96、nextPos112、basePos128、velocityPos144、friction160、indexArray176、dataArray192、distanceArray208。

上述NativeArray字段的**泛型实例布局未认证**；元素类型由kernel pointer参数及pointee记录确定，不把generic union数字当定义索引。

## 入口身份

| 项目 | method index | RVA | 核查范围 |
| --- | --- | --- | --- |
| DistanceJob.UnsafeDo | 368880 | 0x59ec828 | call0x59ec9a7→range0x59ebbc0 |
| DistanceRange `$BurstManaged` | 368842 | 0x59e6b64 | call0x59e6c46→dispatcher0x59ebab8 |
| DistanceKernel `$BurstManaged` | 368841 | 0x59eafdc | 2,778字节单unwind range |
| AngleJob.UnsafeDo | 368723 | 0x59dace4 | call0x59daed5→range0x59d9360 |
| AngleRange `$BurstManaged` | 368687 | 0x59d6eb8 | call0x59d6ffa→dispatcher0x59d91f8 |
| AngleKernel `$BurstManaged` | 368686 | 0x59d7b74 | 5,762字节，数学待闭合 |
| EvaluateCurve | 370882 | 0x59d702c | 265字节，公式人工追踪 |
| CalcInverseMass(4 params) | 371225 | 0x59e7d54 | 64字节两返回leaf路径人工审查 |

身份经image/module/token-RID认证，共享地址保留别名。CalcInverseMass有重载，不能按名字任取一个。部分向量helper尚无managed名称，只依据有界指令确认行为，不臆称某Unity.Mathematics方法。

## 曲线与逆质量公式

S(x)表示该算术边界舍入为Single。CurveSerializeData.ConvertFloatArray（0x34e0a60）useCurve=false时把value填入16样本；true时调用DataUtility.ConvertAnimationCurve（method370881 /0x3277ca0），经间接Unity evaluator在Single(i/15)、i=0..15采样，再乘value。evaluator运行时指针未认证，不能自写任意keyframe插值替代它。

EvaluateCurve使用float4x4内存中16个样本的线性顺序：

```text
n = trunc(S(clamp01(t)*15))
i0 = clamp(n,0,15); i1 = clamp(n+1,0,15)
u = S(S(t-S(n*S(1/15))) / S(1/15))
value = S(samples[i0]+S(S(samples[i1]-samples[i0])*u))
```

只有索引使用clamped t，u使用**原始t**，负t会在首两样本间外推。15来自site0x59d704e→data0xa8c2fcc，Single(1/15)=0.06666667014360428（0xa8c300c）；采样端0x3277d6d也除以15，不是16。

CalcInverseMass method371225参数表顺序 **friction, depth, fix, fixMass**；XMM0=friction、XMM1=depth，不能猜反：

```text
if fix: return S(1/fixMass)
gap = S(1-depth)
denominator = S(S(S(gap*gap)*5)+S(S(friction*3)+1))
return S(1/denominator)
```

leaf site0x59e7d6c读取3.0，0x59e7d83读取5.0。距离kernel在Team bit13为1时选fixMass10，否则50。metadata `TeamManager.Flag_Spring` Int32字面值=13（field234411/default data472926）。这不证明提弗洛斯每组都启用Spring；固定点资格/跳过分支不在离线距离API中。

## 距离计算：通过资格判断的单粒子快照

p=nextPos、b=basePos；邻点q/bq、signed rest d、逆质量wq；当前点逆质量w。按输入邻边顺序遍历。**不宣称原生调度是Jacobi快照**：nextPos读写共享，Job依赖及范围顺序必须另查。

```text
scale = S(team.initScale.x * team.scaleRatio)
k = S(clamp01(EvaluateCurve(params.restorationStiffness,depth))*power.y)
edgeK = clamp01(d<0 ? S(k*0.5) : k)
rest = Double(S(abs(d)*scale))
delta = q-p; length = sqrt((delta.y²+delta.x²)+delta.z²)
if length < 9.99999993922529e-9: skip edge
target = rest+(distance(b,bq)-rest)*Double(team.animationPoseRatio)
c = normalize(delta)*Double(edgeK)*(length-target)
c = componentwise(c/Double(S(w+wq)))*Double(w)
sum += c; validCount++
average = validCount>0 ? sum/validCount : 0
nextPos[p] = p+average
velocityPos[p] += average*Double(params.velocityAttenuation)
```

原生先逐分量除再乘w，不能合并为float质量比例。负d是半刚度编码，不是负目标长度；有效边即使刚度0也计数；短长度常数是Single(1e-8)转换后的Double。参考函数接收已算好的Single scale，不负责团队变换、资格判定或解包索引。

字段数据流：Team copy0x210+0x54→initScale.x（site0x59eb26b），copy0x40+0x60→scaleRatio（0x59eb29a）；params copy0x780+244→curve0x874（0x59eb59f），+244+64→attenuation0x8b4（0x59eb9e9）；Team copy0x5b0+232→animationPoseRatio0x698（0x59eb836）。nextPos写0x59eb9e3/9f1，velocityPos写0x59eba57/5c，不能漏更新后者。邻接index高12位count/低20位start，dataArray邻点UInt16；chunks关联已标记于trace，未放入可执行API。

DistanceParams.Convert（368874 /0x34dffd0）：MeshCloth0/BoneCloth1采用serialized stiffness；BoneSpring10填16个0.5；velocityAttenuation=0.3f。未知clothType路径不写curve，不能自创“默认全零”规则。

## 角度参数（全数学未闭合）

| unboxed offset | 字段 | Convert |
| --- | --- | --- |
| 0 | useAngleRestoration | serialized bool |
| 4 | restorationStiffness | converted stiffness ×0.2f |
| 68 | restorationVelocityAttenuation | serialized value |
| 72 | restorationGravityFalloff | serialized value |
| 76 | useAngleLimit | serialized bool |
| 80 | limitCurveData | converted limitAngle，不乘0.2 |
| 144 | limitstiffness | serialized value |

Convert method368719 /0x34e0850，273字节；0.2f来自site0x34e0894→data0xa8c2e80。matrix helper0x34e0ca0向四列调用0x34e0d60，后者是17字节广播mulps人工leaf路径。角度恢复、限幅是两个开关/曲线/刚度路径，不能简化成一个共用弹簧。

## 验证与下一接手点

新增48测试（布局9、参考39）；全套807 passed /3历史skip /114 subtests /2历史Pillow告警。三个工具含分支覆盖91.1573%，新参考100%；Ruff/format通过、Pyright零错误零告警、临时Python环境pip-audit无已知漏洞。这不是Unity/C#/HLSL覆盖或整套solver动态验收。

TDD先布局RED（4失败）再修复；约束参考先RED（模块不存在）再实现。静态检查发现不定长tuple/测试默认int类型，已修复且保留负例。辅助审查发现无unwind后保留输出并明确人工边界，没有跳过范围验证。

1. **下一主线**：沿0x59d7b74恢复角度恢复/限幅，包括power lanes、gravityFalloff、父链/局部旋转及length/rotation/restorationVector缓存读写；做独立数学用例。
2. 距离链补齐资格/固定点、邻接解码、range调度、Burst目标和实测遍历顺序，再接碰撞、惯性、复位、输出旋转；不能凭此阶段公式宣布官方后端完成。
3. 核查11组配置空间差异/碰撞挂点，接独立可切回后端；骨写回单所有者，等待Job结束再切换，保留预览和正确bindpose。
4. 静止、转身、下蹲、跳跃、强加速动态验收，再测MMD倒拖/循环/帧步进/固定出帧；缓存烘焙属于制作适配，不冒称官方算法。

主HEAD、主暂存index、六项历史保护文件及当前修改后的MMD舞台raw SHA均保持；舞台不入本阶段提交，sealed捕获/原资料不覆盖。机器摘要见verification.json。本地reproduce.py传入**全新目录**可复核完整输出。
