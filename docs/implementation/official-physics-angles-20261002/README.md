# 官方物理：角度恢复与限幅的离线数学参考

日期：2026-10-02。接续[距离内核与角度参数阶段](../official-physics-constraints-20261002/README.md)。本阶段只依据已有原始文件与本地有界审查推进，没有改舞台、材质、渲染或实时物理组件。新增 `Tools/official_physics_angles.py`，不是完整求解器，也不是现有效果的新后端。

## 完成到哪里

- 认证 managed angle kernel、参数转换、Angle / ClampAngle / FromToRotation / AxisAngle 入口，按 method index 选方法，避免重载按名字误选。
- 核查三轮循环、恢复与限幅的不同公式、power.w、重力混合、父子点独立摩擦权重以及两个位置缓冲的修正。
- 实现已通过资格判定的**单条父子边**恢复/限幅数学和方向旋转，附独立合成几何用例；不实现 baseline 调度或旋转缓存系统。
- 将前置缓存及限幅后的旋转更新链记清，作为下一步实现依据；**全缓存链尚未实现和验收**。

全套 Python：841 passed、114 subtests、3历史skip、2历史Pillow告警；新增角度34测试。角度与距离两个参考模块的分支/语句覆盖100%，不代表Unity运行路径覆盖。Ruff/format通过、Pyright零错误零告警、临时工具环境pip-audit无已知漏洞。没有启动Unity或游戏、执行DLL、注入/附加进程。

## 原始依据与可复核证据

本阶段地址只适用于以下文件：

- GameAssembly SHA256：`c24495e51b406f03b03890c4788ee618ae022c991405be5d5b8b787cb775ae89`。
- metadata SHA256：`0076743397acadf03d3b0064343a963c7c88863b8160526d397e4b3efb96f02e`。

权威报告目录：`D:/EndfieldTechLib/notes/official-physics-angles-20261002-01/complete-04/`。55 inventories /1,369方法入口，10选定方法的身份及参数表，26 helper审查项（22 unwind families、4人工leaf），31浮点常量读取点。有界原始指令只保存本地，完整二进制、metadata和原生报告不上传GitHub。摘要与SHA见 `verification.json`。

本地 `reproduce.py` 传入全新目录可再生成报告；所有输出使用exclusive写入。complete-01止于零参数方法的parameterStart=-1检查；complete-02止于摘要键名错误；complete-03成功但缺少pivot加法常量/资格helper，保留，最终权威是complete-04。前两次中止不是原生公式失败，不能把不完整输出当完整审计。

| 身份 | method index | RVA | 范围 |
| --- | --- | --- | --- |
| AngleKernel `$BurstManaged` | 368686 | 0x59d7b74 | 5,762字节，单unwind range |
| AngleParams.Convert | 368719 | 0x34e0850 | 273字节 |
| MathUtility.Angle | 371135 | 0x59d7138 | 217字节 |
| MathUtility.ClampAngle | 371140 | 0x5a87660 | 809字节 |
| MathUtility.FromToRotation | 371141 | 0x5a88428 | 683字节 |
| quaternion.AxisAngle | 441273 | 0x53ad1a0 | 160字节 |
| MathUtility.AutoToFloat3 | 371131 | 0x4a47950 | 44字节人工leaf |
| double3.op_Implicit(float3) | 440713 | 0x40c6230 | 59字节，重载按index选 |
| VertexAttribute.IsMove | 371638 | 0x5a01f44 | 70字节 |
| System.Math.Acos | 276459 | 0x4a66a00 | 5字节JMP→0x1b36e0人工审查 |

资格helper0x37e95c0（74字节）读取attribute bit1 / mask2；它与认证的IsMove入口是分开的地址，不把行为相同当同一方法。没有managed名称的向量/四元数helper仅记录已核查行为。RUNTIME_FUNCTION / CHAININFO验证不等于自动全CFG证明；实际Burst指针和优化路径等价性仍未证实。

## 类型与缓存：下一步不能漏掉的状态

S(x)表示Single舍入；位置/距离/方向角的主运算为Double，quaternion与float3缓存为Single。AngleParams位于ClothParams unboxed320，恢复曲线4、恢复速度衰减68、重力falloff72、限幅开关76、限幅曲线80、限幅刚度144；ClothParams stride808、Team stride464，沿用前阶段认证。

kernel参数表有21项，已记录到本地报告；nextPos / velocityPos / stepBasicPosition 是double3，length是Single，localPos / restorationVector为float3，localRot / rotation为quaternion。packed step index低16位baseline ID、高16位team ID；baseline条目是UInt16索引。当前pair API**不解包这些数组**。

前置初始化的静态读写链：

```text
rotationBuffer[v] = stepBasicRotation[v]         # 两个开启路径均如此，含root
if v is non-root:
  if useLimit:
    localPos[v] = float3(rotate_double(inverse(basicRot[parent]),
                                      normalize(basicPos[v]-basicPos[parent])))
    localRot[v] = inverse(basicRot[parent]) * basicRot[v]
    length[v] = S(distance(nextPos[v],nextPos[parent]))
  if useRestoration:
    restorationVector[v] = float3(basicPos[v]-basicPos[parent])
```

限幅关闭而恢复开启时，不应自创localPos/localRot/length初始化需求。root没有父边缓存；两者关闭时退出。以上为有界数据流记录，inverse/mul/float旋转精度、退化边策略及整个缓存系统的可执行闭环仍待下一步，不宣称已实现。

## 共享方向数学

dotDouble的加法顺序为 `(a.y*b.y+a.x*b.x)+a.z*b.z`。helper0x59d7a98（127字节）归一化先 `Double(1)/sqrt(dot)`，再逐分量乘Double倒数，**不是逐分量除法**；0x59d7700执行乘法。新测试用(1,1,5)区分两种舍入结果。

Angle返回 `acos(clamp(dot(a,b)/(length(a)*length(b)),-1,1))`，单位弧度。FromToRotation先归一化，再算clamped dot、acos、cross轴；fraction是Double且不clamp。

- `abs(dot+1)<Double(S(1e-6))` 时，将theta替为Double(S(pi))。依据 **有符号** `from.x>from.y && from.x>from.z` 选Y轴，否则X轴，axis=cross(from,basis)。不能擅改为abs-max的健壮选轴。
- 否则若 `abs(1-dot)<Double(S(1e-6))`，返回identity；近乎同向不会因fraction放大而强行旋转。
- axis以Double归一化再转Single，角度为S(theta*fraction)。AxisAngle：half=S(angle*0.5f)，结果为float4(axis*sin(half),cos(half))，**不再次normalize quaternion**。

阈值Double实际值为9.999999974752427e-7，反向pi为3.1415927410125732。恢复/限幅共同使用此规则。ClampAngle首先检查maxAngle>=theta；需要旋转时先算r=(theta-maxAngle)/theta，再做上述反向theta替换（顺序不能颠倒），以S(r*theta)旋转原始dir，保留原长度；近同向直接返回false及原dir。

原生AxisAngle中两个数学调用目标为0x2dd0c0 /0x2daac0；本地官方Unity.Mathematics包quaternion.cs:99也佐证半角sin/cos结构。没有证明Python libm与原生CRT逐位一致，也没有假装两个CRT入口都通过metadata名称认证。

quaternion旋转Double方向helper0x59d732c：

```text
u = 2*cross(Double(q.xyz),v)
out = (v+Double(q.w)*u)+cross(Double(q.xyz),u)
```

(-X→+X)的原生有符号选轴会得到零轴。离线适配器拒绝这一退化情况，并拒绝零方向、非有限值、非法flag及非正分母；**这是适配器策略，不是宣称官方会抛异常，也没有悄悄替换官方选轴**。

## 每条可移动子边：限幅先于恢复

子点p、父点a，delta=p−a。父子摩擦权重各自计算 `S(1/S(S(friction*3)+1))`，没有距离链的depth²项；**不除以权重和**，父点固定也不把它的份额补给子点。

### 限幅

```text
L = length(delta)
desired = normalize(delta)*(L+(Double(cachedLength)-L)*0.5Double)
basis = Double(float3(parentRotationCache * childLocalPosCache))
theta = Angle(desired,basis)
limitRadians = Double(S(EvaluateCurve(limitCurve,depth)*0.01745329238474369f))
if theta > limitRadians:
  maximum = theta+(limitRadians-theta)*Double(limitStiffness)
  desired = ClampAngle(desired,basis,maximum).direction
mid = a+delta*Double(0.4f)
childCorrection = (mid+desired*Double(0.6f)-p)*Double(childWeight)
parentCorrection = (mid-desired*Double(0.4f)-a)*Double(parentWeight)
```

limit_pair接收**已由parentRotationCache变换过的float3 world basis**，不是原始localPos。长度半修正在角度已满足时仍执行；0.4f /0.6f分别来自原常量，不能归一化为Double和恰为1的权重。可移动点nextPos +=correction、velocityPos +=correction*Double(0.9f)，这一0.9不与恢复serialized衰减共用。

限幅写点后原生还写旋转缓存：

```text
rotationCache[child] = FromToRotation(basis,newChildPos-newParentPos,1)
                      * (rotationCache[parent]*localRot[child])
```

调用点0x59d8bad（parent×local）、0x59d8c16（FromTo）、0x59d8c35（左乘FromTo）、写0x59d8c4c。该状态影响后续子边及后续迭代，**当前pair参考不做此写回，不能直接串成官方求解器**。

### 恢复

使用限幅后更新的位置（若限幅开启）。恢复输入restorationVector缓存是**原始basic世界差值转float3**，此路径没有再乘rotationCache。

```text
curve = clamp01(EvaluateCurve(convertedRestCurve,depth))
strength = clamp01(S(curve*power.w))
gap = S(1-restorationGravityFalloff)
gravity = S(S(S(1-gap)*team.gravityDot)+gap)
fraction = S(strength*gravity)                   # 没有最终clamp
for original iteration i=0,1,2:
  p,a = current positions after this edge's limit # 每轮每边重新读取
  delta = p-a
  desired = rotate_double(FromToRotation(delta,Double(restorationVector),fraction),delta)
  pivot = S(S(S(i*0.5f)*0.4f)+0.1f)             # 约0.1、0.3、0.5
  mid = a+delta*Double(pivot)
  childCorrection = (mid+desired*Double(S(1-pivot))-p)*Double(childWeight)
  parentCorrection = (mid-desired*Double(pivot)-a)*Double(parentWeight)
```

上述for只说明原生外层三轮的pivot，每轮每边都重新读取更新后的位置和求desired；API执行一轮一边，**不提供伪造的整链三轮循环**。恢复曲线已经在Convert乘0.2f，API不能再乘一次。power从kernel copy0x158+12，即w读取（site0x59d8cc7），不是距离的y；falloff在Angle320+72（栈0x3b8），gravityDot来自Team offset68（栈0x774）。重力先算gap再算1-gap，不能代数替换为falloff，新测试用1e-8与大gravityDot捕捉Single消去差异。

所有带公差的角度用例显式rel=0，只接受写明的绝对公差；大Double原点的用例不会因默认相对容差放行百单位的位置错误。这些仍是合成几何检查，不是逐像素拟合或执行官方DLL的逐位oracle。

可移动点nextPos +=correction，velocityPos +=correction*Double(serialized restorationVelocityAttenuation)。恢复没有限幅路径的半长度修正；固定父点保持原位置/速度缓冲，子点份额不重分配。三轮比较/回跳在0x59d919a /0x59d919d，迭代数据指针按UInt16增2；跨baseline/Job的实际调度仍另查。

## 下一阶段与保护条件

1. 先实现并测限幅前缓存初始化、限幅后quaternion写回；认证inverse/mul/float旋转的精度次序，测试多级父链、两个开关组合、三轮状态传递。不能将pair输入basis当恒定basic世界方向。
2. 补齐资格/root/fixed、baseline和Team索引映射、同一buffer就地遍历与Job依赖，查实际Burst目标；继续碰撞、惯性/积分、复位和输出旋转。
3. 再建立可切回的Unity后端，11组配置/碰撞挂点逐项核查，骨骼单写入者。动态验收静止、转身、下蹲、跳跃、急加速之后，才验MMD倒拖、循环、帧步进和固定出帧。

主HEAD、主暂存index、六项保护runtime文件和用户现有修改后的MMD舞台hash保持原状；不会恢复旧舞台或把舞台加入本阶段提交。仍**不能宣布“官方物理已完整可用”**。
