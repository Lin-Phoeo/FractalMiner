# 官方物理：粒子风力、噪声与湍流

2026-10-03，接续[Team子步tail与风状态](../official-physics-team-tail-20261003/README.md)。新增 `Tools/official_physics_particle_wind.py`，将已经选好的风区列表与更新后的风状态求值为粒子受力，送入现有Start→End参考链。这里不使用零风占位，不用通用随机噪声、LookRotation或调参补偿替代观察到的算法。

**仍是离线有限值参考，没有接入Unity候选后端，也没有新增可见效果。** 帧级中心、风区选择、Spring、完整碰撞/约束/reset/发布，以及真实11组动态验收仍待完成。当前Unity舞台、渲染、湿身、自阴影、MMD和预览物理没有改动。

## 来源与边界

仅静态读取固定版本GameAssembly/metadata，不执行、加载、注入或附加游戏DLL/进程；文件SHA分别为 `c24495e51b406f03b03890c4788ee618ae022c991405be5d5b8b787cb775ae89`、`0076743397acadf03d3b0064343a963c7c88863b8160526d397e4b3efb96f02e`。

- Wind$BurstManaged method370476 /RVA0x5a66520 /992字节。另完整审读包装器370471 /0x5a66900 → DirectCall.Invoke370517 /0x5a7eb60，其实际非Burst fallback是 **0x5a6b018** /992字节，并非只凭managed标签认定运行入口。两处风力数值逻辑一致；动态函数指针执行体未认证。
- WindForceBlend$BurstManaged method370477 /0x5a66188 /790字节。包装器370472 /0x5a664a0 → DirectCall.Invoke370527 /0x5a7dfe8 的非Burst路径确实调用该body。
- 二维经典Perlin `Unity.Mathematics.noise.cnoise` /0xa1f5870 /1366字节，含mod289、permute、taylorInvSqrt、fade、frac/floor/abs与float向量操作链。不是simplex或随机方向。
- AxisToEuler /0x5a592d4 /209字节、AxisQuaternion /0x5a5928c /69字节；Euler的 **order4/ZXY** 具体实现 /0x2de4f00 /559字节。通用Euler dispatcher因完整decode未通过，不冒称整个函数已认证：只对已初始化、order=4的固定112字节hot入口做操作数证明，其他顺序与初始化cold路径明确排除。
- 无exact unwind的24个直线向量小helper使用固定字节范围、完整已审读操作数模式、终末RET且无中间控制转移的证明；不从首个RET猜整个方法边界。sqrt/sin/cos/atan2的Python实现不声称是CRT/Burst逐位oracle。

私有完整字段布局、指令、证明脚本与参照程序留在 `D:/EndfieldTechLib/notes/official-physics-particle-wind-20261003-01/`。公开只包含自己的有限值参考、测试、摘要与SHA；不发布原始游戏资产、完整原生报告或第三方源码。

## 输入：顶点与粒子索引不能混用

本轮静态读取参数表，核实原Wind的参数顺序：teamId、tdata、windParams、cdata、**vindex**、**pindex**、depth、teamWindArray、windDataArray、vertexRootIndices、frictionArray、result。tdata/cdata不在本段数值逻辑中读取，不凭空消费它们。

适配器接收调用者已解析的：

- `root_index = vertexRootIndices[vindex]`，是signed Int32；**不是**全局粒子索引pindex。
- `friction = frictionArray[pindex]`，是Start本次风力读取时的已有摩擦值；不能先用End本步衰减后的摩擦代替。
- `state.zones` 是上游已经选好、保持原顺序的TeamWindInfo列表。
- `zone_turbulence[info.wind_id] = windDataArray[windId].turbulence`。WindData stride212、turbulence unboxed@24；TeamWindData stride152；Info stride24，time@4/main@8/direction@12。
- `state.moving` 使用先前风状态模块生成的移动风，仍依赖真实**帧级**speed/direction，不能用stepVector/dt猜值。

列表选择、容量、windId有效性与原数组所有权仍由上游负责。这里的Mapping只是已解析槽值快照，不实现NativeArray/FixedList存储；缺失槽拒绝是适配安全规则，不是官方异常/越界契约。

## 固定算法契约

下列S表示每步Single舍入，不做代数重排或擅加clamp。

1. 种子标量：`root=S(S(Int32(rootIndex))*S(0.002396299969404936))`；`root=S(S(1−S(synchronization))*root)`；`root=S(root*100)`；`seed=S(root+S(S(Int32(teamId+1))*S(4.1923065185546875)))`，复制为float3的三个通道。teamId+1保留Int32边界回绕；不改成任意hash/random，不把synchronization限到[0,1]。
2. WindForceBlend只在 `main<S(.01)` 返回零。**等于阈值进入计算**；此低main分支不读取time、seed、方向、blend与湍流。Wind外层仍先解析该区的turbulence槽，不能把低main变成跳过数组查找。
3. 周期项是 `sin(seed.xy + S(time*10))`；噪声坐标是 `seed.xy + S(time*S(2.313199996948242))`，分别计算cnoise(x,y)与cnoise(y,x)，各乘S(2.3)。二者按 `periodic+S(S(noise−periodic)*blend)` 混合，blend不限范围。
4. `effectiveTurbulence=S(zoneRatio*parameter.turbulence)`。混合信号各乘45，再乘S(0.01745329238474369)换弧度；第二角度额外乘 `S(S(blend*S(.4))+S(.1))`，然后两个角度乘effectiveTurbulence。构造EulerZXY(firstAngle,secondAngle,0)。
5. 基方向通过 `yaw=atan2(dir.x,dir.z)`、`pitch=atan2(-dir.y,sqrt(dot(dir−(0,dir.y,0),同向量)))` 转EulerZXY(pitch,yaw,0)。**baseOrientation × perturbation** 后旋转(0,0,1)，不反乘、不先归一化方向或用Unity角度制Euler代替。
6. 强度衰减：`g=clamp01(S(1−S(main/S(7.5))))`；`g=S(g*effectiveTurbulence)`；`u=S(S(mixed.x−(-1))*.5)`；`amplitude=S(main−S(S(g*u)*main))`。保留可能负的amplitude，不强行修为零。最终返回S(direction*amplitude)。
7. Wind按原zone顺序**求和**，不平均、不额外按ID/IsValid/main筛选。movingWind>S(.01)才计算移动风，传入ratio=1，不读取zone table替代它；否则该分支不求值。
8. 最后：`depthFactor=S(S(S(S(depth*depth)−1)*depthWeight)+1)`；`mobility=S(S(1−friction)*influence)`；`factor=S(depthFactor*mobility)`；每通道乘factor。**没有influence提前返回或这些权重的额外clamp**。

`classic_noise2`保留浮点mod289/permute和fade运算边界，不把mod换成Python整数取模。`euler_zxy`保留三角函数后向量乘法/符号相加的分组。适配器拒绝非有限/溢出Single及不合法Int32，但这些拒绝不属于官方故障契约。

## 独立参照与回归

遵循测试驱动：新增测试先观察缺失模块RED，再实现。63项新测试覆盖门槛、未读取输入、signed根索引/team增量、噪声、ZXY弧度、非单位基方向、两种信号混合、湍流强度、负幅值、列表相加、移动风、深度/摩擦与影响权重，以及两子步 **Center→Team tail/风状态→粒子Wind→Start→End** 反馈。该反馈确实消费生成的非零区风与移动风，不手填零风；仍是合成场景，不是真实角色动态验收。

另外在独立.NET进程调用项目**未修改的Unity.Mathematics.dll**（SHA `5d575d3944c32c88d4b6b7516bedb1fc281a978738c5d1df0b246996cdebd9b7`）：1035个noise样本输出Single位模式零不一致；133个EulerZXY样本最大绝对差8.45e−8；5个用独立数学库求值的重建风力公式样本最大绝对差4.83e−8。这是**公共数学库参照**与**重建公式参照**，不是运行游戏/Burst取得的物理oracle，不能据此宣称全算法逐位等价。

算法来源可交叉查看[Unity官方经典二维噪声源码](https://github.com/Unity-Technologies/Unity.Mathematics/blob/master/src/Unity.Mathematics/Noise/classicnoise2D.cs)，实际实现依据仍是上述本地固定版本证据，而非直接套master版本。

全套 **2353 passed /114 subtests /3历史skip /2历史Pillow warnings**；27个参考模块2403statements/572branches，含分支覆盖100%。新增模块131statements/16branches覆盖100%；Ruff/format、Pyright、compile、工具环境pip-audit通过。7个runtime文件及主索引原始SHA复核一致。

## 接续与未完成

上一Team tail的返回值仍保留 `pending_pipeline=particle_wind_force`：它本身只产生Team状态，不替调用者逐粒子求力。现在调用者可显式调用 `particle_wind(...)` 并把 `.force` 交给 `start_particle_step(...)`；不能仅导入本模块就删除这个依赖声明或认定native发布已完成。

后续集中推进帧级中心/anchor/world惯性与风区选择、Spring，再闭合完整碰撞/约束/reset/发布；形成可回退C#候选后端后，才进入Unity、MMD与解包动作动态验收。完整剩余边界见[八个交付门禁](../official-physics-animator-buffer-20261003/PROGRESS.md)。不以单元测试数量代表完成百分比。
