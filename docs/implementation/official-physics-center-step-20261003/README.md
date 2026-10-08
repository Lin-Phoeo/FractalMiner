# 官方物理：子步中心生成与局部惯性

2026-10-03，接续[Start惯性消费](../official-physics-start-step-20261003/README.md)。新增 `Tools/official_physics_center_step.py`，不再只能由测试手填stepVector/inertiaVector：现在从**已解析的帧中心与上一子步状态**，按官方子步时间计算中心位置/旋转、平移/旋转增量、局部惯性比例、角速度和轴，供Start/End消费。连续两子步的中心→Start→End合成反馈已通过。

后续已补[Team子步缩放/重力/权重与风状态更新](../official-physics-team-tail-20261003/README.md)、[粒子风力](../official-physics-particle-wind-20261003/README.md)与[固定粒子Spring](../official-physics-spring-20261003/README.md)。新增模块消费本阶段返回值，不改本阶段历史范围；帧级上游/完整求解/Unity接入仍未完成。

**完整官方后端仍未接入Unity，没有新可见效果。** 帧级中心/anchor/world惯性/teleport/reset准备不是本模块；子步Job剩余的scale/gravity/weight/fade、UpdateWind和真实发布也未移植。模块明确返回 `pending_tail`，不能把这些默认填零后称为原版闭环。当前舞台、渲染、湿身、自阴影、MMD和预览物理未改动。

## 两层中心算法不能混为一谈

| 官方入口 | 本轮处理范围 |
| --- | --- |
| CalcCenterAndInertiaAndWindKernel$BurstManaged，369644 /0x5a34900 | 帧级上游：anchor、component、frame中心、world/local运动处理与teleport/reset等。已定位私有完整范围，**没有在本轮移植完整算法** |
| SimulationStepTeamUpdateKernel$BurstManaged，369542 /0x5a39fa0 | 子步时间与中心生成、局部惯性、angular state：本轮有限值参考；整个kernel的后半tail仍未移植 |
| StartSimulationStep，370473 | 消费本轮生成的 `ResolvedStartCenter`，按depth混合与旋转/平移粒子，再受力 |
| EndSimulationStep，370554 | 消费本轮生成的 `ResolvedCenter` 的nowPosition/omega/axis，用于已有离心项 |

输入的old/current frame中心必须由真实上游生成；不能拿场景root transform或上一模拟粒子位置冒充。上一子步的 `nowWorldPosition/Rotation` 在推进时保存到oldWorld，然后生成新的nowWorld。

## 源绑定与运算次序

GameAssembly SHA `c24495e51b406f03b03890c4788ee618ae022c991405be5d5b8b787cb775ae89`，metadata SHA `0076743397acadf03d3b0064343a963c7c88863b8160526d397e4b3efb96f02e`。只读本地文件，不执行/加载/注入游戏DLL。

主kernel method369542 /RVA0x5a39fa0 /3548字节 /SHA `6f7fd7d6c2b8b4657c8a565d9a118fbdfd60c07a4ce2e71e8cd9554f5c540f00`。完整exact AMD64 unwind范围已审读，**仅移植源片段**。Process helper0x5a3b644 /47字节、FromToRotation0x5a2b85c /91字节、Angle0x5a2b72c /130字节、ToAngleAxis0x5a2bccc /201字节另作exact范围审读。无unwind的enable/culling短入口以固定26/23字节、全部操作数、内部直接跳转和全部RET路径证明，不猜完整方法边界。

1. Team0跳过。IsProcess要求flag掩码0x2置位且第61位未置位，再排除0x10、0x800、0x80000。没有额外要求valid掩码0x1，也不能把Reset0x4、TimeReset0x8或KeepTeleport0x200当成统一停止条件；这些上游准备仍须由调用方正确处理。
2. 清stepRunning0x80；updateIndex<updateCount时设回该位并推进。超出count只改该flag，不读取中心、不累加时间。保持其他flags，不擅自重写reset位。
3. `nowUpdateTime = Single(nowUpdateTime + dt)`。分母是 Single(**Team.time − Team.frameOldTime**)，不是oldTime/oldUpdateTime。若分母>0，t=clamp01(Single((nowUpdateTime−frameOldTime)/span))；否则t=1。
4. 保存原nowWorld至oldWorld。位置在Double中按oldFrame→frame插值，t先Single再宽化；旋转slerp后normalize；scale在Single插值。interpolated scale是本地临时量，**不是凭空新增一个CenterData.nowWorldScale字段**。
5. stepVector = Single(newNowPosition−oldNowPosition)，先Double减再窄化。stepRotation = **newNowRotation × inverse(oldNowRotation)**，不是局部空间的inverse(old)×new。保存原始Single旧rotation，不提前强制归一化。
6. 初始平移与旋转比例均为Single(1−localInertia)。限速测量的是stepVector×Single(1−ratio)的Single长度/dt，旋转则是Single((Single(1−ratio)×angle)/dt)×Single(57.295780181884766)。不能代数化简 `1−(1−local)`；需保留原舍入。
7. 对应limit≥0且受惯性运动speed>limit时，ratio变为Single(**1 + (ratio−1)×(limit/speed)**)。这是让更多中心运动被跟随，**不是截断stepVector或nowWorld位置**。平移limit单位为世界单位/秒；旋转limit是度/秒。
8. inertiaVector = Single lerp(zero,stepVector,moveRatio)，inertiaRotation = slerp(identity,stepRotation,rotationRatio)。不能把参数localInertia直接当粒子跟随比例。
9. Angle先看abs(dot)≥Single(.9999)则返回0，否则对**signed dot**clamp后acos、乘2，超过Singleπ时用Single2π减去。angularVelocity=Single(angle/dt)，单位弧度/秒，不是上述度/秒limit。omega≤Single(1e−8)时axis为0。
10. ToAngleAxis使用signed w求acos，xyz除Single sin(halfAngle)，小于Single(1e−6)时轴为0。**不额外把stepQuaternion翻到最短弧半球**；Angle的shortest折叠和ToAngleAxis的符号规则不同，不能套同一个修正器。

Team unboxed关键偏移：time@20、nowUpdateTime@28、frameOldTime@40、updateCount@52、frameInterpolation@60。参数inertia@180；localInertia@20、localMovementSpeedLimit@24、localRotationSpeedLimit@28。Center framePos/Rot/Scale@248/272/288、oldFrame@312/336/352、nowWorld@368/392、oldWorld@408/432、stepRatio@448/452、stepVector/Rot@456/468、inertiaVector/Rot@484/496、omega/axis@528/532。Team/Params/Center stride分别464/808/696。

## 边界与真实状态

返回 `next_state` 与Team时钟fragment供下一子步继续；`for_start()`、`for_end()`只是明确类型的数据交接。`writes`记录改变的**值片段**，不是实际NativeArray写序、完整Team结构写入或骨骼发布。

`pending_tail = (scale_gravity_weight_fades, UpdateWind, native_publication)` 必须补齐后才能做实际发布。风/力本身仍由Start显式要求已解析输入；合成连续两步测试用零风只是该夹具的前提，不是官方风算法。

finite、正dt、非负Int32 index/count、localInertia[0,1]拒绝属于适配保护；源没有增加本参考的clamp。Python trig/sqrt不是native CRT/Burst逐位oracle，动态Burst指针未认证。没有运行官方DLL、没有真实11组动态验收，也没有完整teleport/reset链通过声明。

## 验证与下一步

先写测试观察缺失模块RED，再实现。新增53项覆盖Team0/process/culling/suspend/bit61、reset位保持、count耗尽、时钟比率、Double/Single边界、local惯性补数、限速与中心不截断、非交换world旋转、度/弧度、带符号AngleAxis、两子步中心→Start→End反馈及非法输入。

全套 **2232 passed /114 subtests /3历史skip /2历史Pillow warnings**。25个离线参考模块2160statements/540branches，含分支覆盖100%；新模块125statements/12branches 100%。Ruff/format、Python compile、Pyright通过，临时工具环境pip-audit无已知漏洞。不是Unity或原版solver完成率。

本页上方的pending tail和2232项结果是该阶段历史快照；后续Team tail、粒子Wind与固定Spring页面覆盖其中相应待办。当前下一步集中补帧级中心准备、风区选择、碰撞/reset与实际发布。完整候选链形成后才进入可回退C#接入、MMD/解包动作测试，不将本片段直接挂到现有舞台声称已等价。

私有源码证据/脚本/回归报告位于 `D:/EndfieldTechLib/notes/official-physics-center-step-20261003-01/`，SHA见verification.json。原游戏文件/资产、完整native报告和第三方源未发布。11组164 saved点、7个运行文件、主HEAD、9557项原索引和9555项原暂存改动保留；仍用独立索引提交记录分支。
