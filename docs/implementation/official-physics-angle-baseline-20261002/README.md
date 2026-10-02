# 官方物理：单baseline角度调用层

日期：2026-10-02。接续[父子边角度缓存](../official-physics-angle-cache-20261002/README.md)。新增 `Tools/official_physics_angle_baseline.py`，只恢复 **一个已选baseline** 的索引解析、缓存预处理、三轮角度限幅/恢复和内部就地读写。**不是完整物理求解器，也没有接入Unity实时后端。** 舞台、材质、湿身、阴影和当前预览物理不变。

## 本轮实际完成

- 解包step的Int32位型：高16位team ID、低16位**全局baseline ID**；不错误地再加team.baseLineChunk.startIndex。
- 分开baseline数据、proxy属性、particle状态这三种索引空间，支持非零起点、非零team及乱序但合法的父引用。
- 保留原UInt16 baseline顺序、不排序、不去重；预处理一次，随后严格三轮，逐边限幅→旋转缓存→恢复。
- 首节点复制basic旋转、跳过父边缓存；fixed非首节点仍初始化边缓存。关闭的缓存字段保留旧值，不能用None清空官方未写的槽。
- 当前父点和父旋转立即参与后续边；父点被子边修正时不补祖先旋转，恢复不重算旋转缓存。支持位于baseline外但team内的父节点，不能将其缓存擅自重置成basic值。

45个新合成用例；全套 **910 passed /114 subtests /3历史skip /2历史Pillow告警**。四个参考模块436语句、96分支，覆盖100%；Ruff/format通过，Pyright零错误零告警，临时工具环境pip-audit无已知漏洞，新增代码/测试未发现密钥模式。这些是Python测试，不代表Unity动态覆盖、官方DLL执行oracle或实际Burst逐位等价。

## 原始证据与范围

只适用于GameAssembly SHA256 `c24495e51b406f03b03890c4788ee618ae022c991405be5d5b8b787cb775ae89` 和metadata SHA256 `0076743397acadf03d3b0064343a963c7c88863b8160526d397e4b3efb96f02e`。

新增本地权威证据：`D:/EndfieldTechLib/notes/official-physics-angle-baseline-20261002-01/complete-01/`。4个布局、21个kernel参数及其指针目标、6个unwind family的有界解码；机器摘要与哈希见verification.json。reproduce.py要求全新输出目录，原始文件/原生报告/完整指令只保留本地，不上传GitHub。没有启动游戏/Unity、执行DLL、附加或注入进程。

主要方法仍是认证的 method368686 / `AngleConstraintKernel$BurstManaged` / RVA0x59d7b74 /5762字节，body SHA256 `00e400a490c309da2aa5285cc6a5ed69766c4744ee4d730ce242a287132c99ce`。helper0x37e95c0和认证IsMove入口0x5a01f44分别审查，两者并不是同一个地址；两条路径最终均test byte mask2。

DataChunk实证 `startIndex: Int32 @0`、`dataLength: Int32 @4`（unboxed）。TeamData的proxyCommonChunk@292、baseLineChunk@348、baseLineDataChunk@356、particleChunk@372均为DataChunk；Team stride464、ClothParams stride808沿用原证据。本轮没有读取live Team实例、构建真实角色全部baseline或证明运行时缓冲分配。

新增参数指针目标审查避免把字节跨度误当类型：stepBaseLineIndexArray和vertexParentIndices指向Int32；baseLineStartDataIndices、baseLineDataCounts、baseLineData指向UInt16；attributes指向VertexAttribute（Value: Byte @0）；位置及velocityPos指向double3；旋转指向quaternion，depth/friction/length为Single，localPos/restorationVector为float3。

### 三种索引空间

```text
(team, baseline) = logical_split_u32(stepBaseLineIndexArray[index])
offset = baseLineStartDataIndices[baseline]          # UInt16，team baseline-data内相对起点
count  = baseLineDataCounts[baseline]                # UInt16
begin  = team.baseLineDataChunk.startIndex + offset
local  = baseLineData[begin + slot]                  # UInt16
particle = team.particleChunk.startIndex + local
proxy    = team.proxyCommonChunk.startIndex + local
parentLocal = vertexParentIndices[proxy]             # Int32
parentParticle = team.particleChunk.startIndex + parentLocal
parentProxy    = team.proxyCommonChunk.startIndex + parentLocal
```

step读取/逻辑右移在0x59d7c0f–0x59d7c1b；baseline起点/数量读取0x59d7ea3/0x59d7eb8；数据起点0x59d7f94–0x59d7fa6；proxy/particle父索引0x59d8015–0x59d8044及0x59d8466–0x59d8490。本参考接受Int32及等价UInt32位型；负数必须先按32位恢复，不以Python负数右移替换原mov ecx的零扩展。

### 首节点与可动资格：不能混为一个条件

预处理在0x59d800d–0x59d800f和0x59d82a8–0x59d82ab按**slot==0**跳过边缓存，不检查local是不是零，也不按attribute省掉fixed非首节点的缓存。

求解循环0x59d8447–0x59d844e只用IsMove（`attribute & 2 != 0`）决定是否进入子边；进入后读取parent，并分别按父IsMove决定父点/velocityPos写回。不能自创Fixed、InvalidMotion、DisableCollision或其他标志对Move的否决；矛盾值3在原IsMove也为true。本轮256个Byte值均验证mask语义。

**原kernel没有新增“首节点无论Move都跳过求解”的分支。** 有效首次slot应如何由上游生成/标记，仍待真实baseline构建链核查。本适配器明确拒绝首slot标Move，以免读取其未建立父边缓存；这是安全前提，不是证明官方必然报错或强制固定该节点。不要将“首slot”推广为所有parent=-1的自动root过滤。

## API和就地调用顺序

`resolve_baseline`建立immutable plan，保留输入顺序；TeamWindow是调用者已解析的3个DataChunk窗口，不是自称运行时原struct。`solve_baseline`消费该plan、完整particle数组状态以及已经Convert过的AngleSettings；恢复曲线不能再乘0.2。

```text
if neither enabled: return unchanged
for slot in stored baseline order:                 # 只预处理一次
  rotation[particle] = stepBasicRotation[particle]   # 包括首slot与fixed
  if slot != 0:
    initialize enabled edge cache fields only
for iteration in 0,1,2:
  for slot in SAME stored order:
    if not IsMove(child): continue
    if limit:
      read current points, velocityPos, parent rotation
      compute limit, write movable points and velocityPos immediately
      write child rotation cache
    if restoration:
      use points AFTER this edge's limit
      write movable points and velocityPos immediately
      keep rotation cache unchanged
```

缓存length从进入baseline时的nextPos读取，三轮中不重算、不重新初始化旋转。三轮及原始UInt16指针步进在0x59d9167–0x59d919d。当前边之后的兄弟/子边读更新状态，不是整轮冻结快照；也不是先所有边限幅，再所有边恢复。

位置/缓存内部使用独立工作数组并就地写入，成功后返回immutable BaselineState与AngleVisit轨迹。输入不改、失败不发布部分结果是适配器策略；**不是宣称官方也做整组copy或事务**。AngleVisit只记录合成参考的访问顺序，不能当官方运行trace。数组之间alias、竞态及外部同时修改不在此参考契约中。

关闭的缓存lane和首slot旧edge cache保留；disabled并不意味着清空。未列入当前baseline的父旋转保持caller提供的当前值；其点可因Move收到当前子边修正，但本kernel不为这个父点重算旋转。后续caller若运行其他baseline必须显式传承返回state，但这里**没有自动选择或证明跨baseline顺序**。

数值参考继续复用已验证的Single/Double算术，不改曲线、阈值或艺术参数。另附集成对照，能区分错误的Jacobi快照、每轮重建cache、两次整链扫描；这不是独立原生数学oracle。Index/UInt16/Byte/finite/正长度/root等拒绝条件均为适配器检查，不冒充native异常、NaN行为或原始上游验证。

## Job/Burst界限与后续

证据包也保存RangeKernel$BurstManaged0x59d6eb8、AngleConstraintJob.Execute()0x59d94cc和Execute(index)0x59d952c的有界指令。Range路径中0x59d6ffa调用**dispatch wrapper**0x59d91f8、随后递增index；无参数Execute在0x59d9510调用Execute(index)并递增。这只能描述观察到的静态范围，不证明实时Job拓扑、实际选用路径或跨baseline无竞态，也没有审查所有inlined算术与kernel逐位等价。

仍缺：

1. 真实proxy/baseline构建与首节点属性来源、shared root的组关系、Job依赖/实际Burst目标；不能直接按骨架拓扑重新生成baseline替代官方数据。
2. 原始积分/惯性、碰撞、reset和最终position/rotation输出完整链；离线角度子求解不是完整官方物理。
3. Unity可切回后端、骨骼单写入者，以及静止/转身/下蹲/跳跃/急加速和MMD倒拖/循环/固定出帧验证。

本轮没有换实时效果。主HEAD/主index保持，七项runtime保护值保持（包括用户已修改舞台的新hash，不恢复历史舞台）。代码仍无提弗洛斯骨名，便于后续角色共用；角色绑定、初始姿态和坐标空间仍需适配。
