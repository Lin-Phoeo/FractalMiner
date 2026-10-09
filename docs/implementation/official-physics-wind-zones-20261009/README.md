# 帧风区选择与 frameLocalPosition

2026-10-09，实现位于 `Tools/official_physics_wind_zones.py`。本轮补齐帧风区选择、区域历史时间保留，以及 `frameLocalPosition` 的原矩阵计算，并接续已有子步风状态与粒子风力参考。测试驱动与完整验证流程用于约束边界行为和跨帧接续。

**当前交付是 Python 有限值参考。** 原 WindManager 的变换采样/数据发布、全局 proxy/Team 输入与实际数组/Job 依赖仍需接入；可见 Unity 物理后端保持原状态。本轮的测试不能用作解包动作/MMD 的实际动态验收。

## 静态证据

原 DLL SHA256：`c24495e51b406f03b03890c4788ee618ae022c991405be5d5b8b787cb775ae89`；metadata SHA256：`0076743397acadf03d3b0064343a963c7c88863b8160526d397e4b3efb96f02e`。仅读取文件字节，没有加载、执行或注入原 DLL。

- 帧风区入口 `Wind` method369643 / `5a3772c..5a377b0` 是包装器。Invoke `5a3e774..5a3e842` 的非 Burst 路径在 `5a3e828` 调用 `5a2a620..5a2ad5c`；另一条 `call rax` 路径的动态执行体没有认证。
- metadata `Wind$BurstManaged` method369646 / `5a36ff4..5a3772a` 为1846字节；实际非 Burst fallback为1852字节。两者各408条指令；归一化内部跳转目标、RIP常数地址，以及14处明确的临时记录/winner栈槽迁移后，408对指令全部匹配。这是静态结构核查，没有执行原程序。
- `frameLocalPosition` 区域 `5a36bb8..5a36c13`，随后 Wind 调用区域 `5a36c42..5a36c81`；Wind 的 R8 仍指向 `rbp+128` 的 Double 帧目标，不使用窄化后的 `frameLocalPosition`。
- `AddOrReplaceWindZone` `5a7782c..5a779ae`、`IndexOfWindZone` `5a779f0..5a77a78`、删除包装器 `5a77a78..5a77ad0`、`7669404→766a0b8` 的 swap-back、`7663150→76634e8` 的追加均已读到实际底层操作。

私有证据在 `D:/EndfieldTechLib/notes/official-physics-wind-zones-20261009-01/`；公开验证摘要及文件哈希在本目录 `verification.json`。原文件、完整指令转录和原资产未纳入记录提交。源码证明含106条关键指令、21个 exact unwind 函数范围、1个手验 leaf 范围、字段偏移与常数，以及408对 managed/fallback 指令匹配。主代理独立复核，并有一次完整只读源码/实现审查。

## 必须保留的规则

| 处理 | 原规则 |
| --- | --- |
| 帧门禁 | 新建空 zones；windCount≤0先跳过 influence。否则 influence≤Single(1e-8)跳过选择；两者都清旧 zones、原样保留 movingWind。子步 `advance_wind_state` 的相同 influence 门禁则保留整个传入状态，两阶段规则不同 |
| 扫描/标志 | 按原 WindData 数组槽位0起递增；flag掩码0x1（valid）和0x2（enabled）同时成立才处理。windId是数组槽位，不是组件ID/PPtr |
| 叠加限制 | addition掩码0x4成立且已接纳候选≥3，先跳过形状/主强度读取。仅满足区域/径向中心条件的候选进入计数；其 main太小未追加时，计数仍增加 |
| 区域点 | 原 Single4x4 的四列逐通道拓宽为 Double，再对 Double帧目标做完整点变换，最后窄化为 Single3；随后 Single dot→sqrt 求距离。不能先把世界坐标变为Single，也没有齐次除法 |
| sphere/radial | mode1或10：distance≤size.x，边界包含。mode10在 distance≤Single(1e-6)时跳过候选 |
| box | mode2：逐轴 `Single(abs(local)*2)≤size`，边界包含。其他 mode 数值没有区域边界门禁，但仍执行局部点/距离计算 |
| 非叠加优先级 | 初始体积阈值是float.MaxValue；仅 volume>当前阈值时跳过，等体积后扫描者可替换。没有按强度排序，也没有额外体积非负clamp |
| 径向方向 | 原Single worldPositin先拓宽为Double，从Double帧世界目标减去它，再窄化成Single3并unsafe normalize。局部点只决定区域/衰减；没有把局部方向乘worldRotation |
| 径向强度 | `t=clamp01(Single(distance/radius))`；复用原16样本曲线，结果clamp01后Single乘main。曲线索引按15段/Single(1/15)，保持原运算边界 |
| 弱风门禁 | Add helper只追加 main>Single(1e-6)。非叠加候选先删旧winner，再调用Add，并始终更新volume/winner；因此弱候选可以移除原强风并阻止后续更大体积候选 |
| 删除顺序 | 删除第一个匹配ID时，末尾元素搬到该槽，然后减少计数（swap-back）。例如 `[winner0,add1,add2]` 替换winner3得到 `[add2,add1,winner3]`；后续风力按这个顺序累加，不能排序 |
| 时间 | 新候选time=-10000f；强度门禁通过后，在上一帧zones中找第一个同ID，仅复制它的time。main/direction使用本帧值；本阶段不推进时间 |
| movingWind | 逐字段原样保留到后续子步；选择阶段不清main，不计算移动风力或修改其时间 |

原 `FixedList128Bytes<TeamWindInfo>` 元素stride24，payload偏移8，物理容量5；选择算法最多同时输出3个叠加风和1个非叠加风。Python列表表示这些值，不模拟原FixedList内存/allocator，也不擅自给native追加路径增加容量分支。

WindData stride212：flag@0、mode@4、size@8、main@20、turbulence@24、zoneVolume@28、worldWindDirection@32、worldPositin@44、worldRotation@56、worldScale@72、worldToLocalMatrix@84、attenuation@148。适配器省略选择过程没有读取的worldRotation/worldScale；调用者供应已生成的原矩阵，不以这两个字段重新推算矩阵。turbulence保留为后续粒子风力按windId读取的输入，选择不消费它。

## frameLocalPosition 与接续

`produce_frame_local_position(step, matrices)` 使用前置 `prepare_frame_scale_matrices` 产生的完整 Double frame_inverse，对同一帧目标 `step.frame_world_position` 做 Double 点乘，再窄化为 Single3，返回 CenterData@300 的值。该目标经过 scale/sign→固定点归约→resolve 生产；原矩阵在reset/惯性之前生成。不能把这个表达式直接简化为零，也不能在这里用新历史重建inverse。巨世界非单位旋转测试保留了实际非零舍入残差。

顺序：scale/sign→fixed-point target→frame inverse/remap→anchor→prelude/reset→frame inertia→**frameLocalPosition→帧权重初始化→select_wind_zones**→原帧字段发布→全部子步→独立PostTeam。加粗项的离线值参考已有；原数组发布和完整调度依赖仍需接入。

`select_wind_zones(previous, wind_data, wind_count=..., influence=..., frame_world_position=...)` 输出的 `state` 直接交给 `advance_wind_state`/`complete_team_step`，随后交给 `particle_wind`。粒子湍流表仍按原windId读取 `wind_data[id].turbulence`；没有按缺失ID补零。固定点生产接续测试验证Wind使用生成的world目标，而不是frameLocalPosition或舞台root。

两帧接续测试实际执行选择→子步时间/移动风更新→粒子风力：角色首帧在sphere内，第二帧出区；对应风力约为 `(3,-1,2)`→`(3,-1,0)`，保留叠加风时间并移除sphere贡献。Single旋转带来的小数舍入使用已有数值参考的合理容差，没有进行视觉调参或逐像素拟合。

## 验证与实际缺口

84项新增测试覆盖各门禁、全部模式/轴边界、Single/Double转换、无齐次除法、等体积/弱候选/3个叠加名额、swap-back次序、曲线clamp、时间匹配与未选输入、生成帧目标以及两帧风力接续。先观察缺失模块RED，再实现；初次接续测试的整数字面量预期已修正为Single旋转容差，原数学没有改动。

最终全套2775 passed、114 subtests passed；3个历史skip和2个历史Pillow警告保留。38个official_physics模块3246条语句/728分支全部覆盖；本模块106条语句/40分支全部覆盖。编译、Ruff/format、显式Python环境Pyright及工具环境依赖审计通过。原11组164点、7个运行文件与9557个用户暂存条目/flags保护通过。

有限值/范围/退化输入拒绝是适配器政策。没有认证原MXCSR/FTZ/DAZ、CRT或动态Burst逐位结果。`winner_id`/`addition_candidates` 是审计信息，不是新增官方字段。

下一主线是原WindData/Team/proxy等真实输入与跨步发布，完整粒子reset、碰撞与约束生命周期，随后形成可切换C#候选后端并运行解包动作/MMD。[PROGRESS](../official-physics-animator-buffer-20261003/PROGRESS.md)保留全部八项交付门禁。
