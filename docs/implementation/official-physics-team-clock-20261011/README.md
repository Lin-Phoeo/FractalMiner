# 官方物理：Team 每帧时钟、步数与连续子步连接

日期：2026-10-11。接续[世界 proxy 到首次 reset](../official-physics-world-proxy-20261011/README.md)，恢复 `AlwaysTeamUpdatePostJob.Execute` 的有限时钟片段，并把它与既有子步中心及粒子/baseline 工作列表做两帧组合验证。本轮没有修改 Unity 舞台、角色、渲染、湿身、阴影或当前预览物理后端。

## 本轮闭合内容

新增 `Tools/official_physics_team_clock.py`。输入是调用点已经解析好的 update mode、三种 Unity 帧 delta、全局/Team 时间倍率、模拟步长/最大步数及现有 Team 时钟字段；输出是不可变的有限字段片段，不负责 NativeArray 发布或 Job 调度。

已恢复原顺序：mode 0/1/2 分别选择普通/fixed/unscaled delta；unscaled 路径绕过全局倍率但仍乘 Team 倍率；flag8 先清五个时钟字段；计算 `time += nowTimeScale * frameDelta`；`cvttss2si((time-nowUpdateTime)/simulationDeltaTime)` 向零截断；最大步数只限制上界，超额步对应的时间从 `time` 扣除；动画姿态 reset 请求将 `nowUpdateTime` 对齐到当前 time、步数/skip 清零并置 flag4；零倍率且存在正 backlog 时用 `time-step+1e-4f` 重定位并取消本帧步进；仅正步数推进 frame/oldUpdate 窗口；bit60 控制 LOD fade 方向；最后按正步数写 Running bit20。

关键语义边界：负商不会被擅自钳到0；flag4 本身不等价于 flag8 的时钟清零；零步进帧仍可推进 time 与 LOD fade，但不覆盖 frame history；动画姿态 reset 请求的产生、首次粒子 reset、暂停/seek 上游标志、距离剔除与 update mode 解析仍由尚未闭合的上游负责。

## 原证据与独立复核

绑定原文件：GameAssembly SHA256 `c24495e51b406f03b03890c4788ee618ae022c991405be5d5b8b787cb775ae89`；metadata SHA256 `0076743397acadf03d3b0064343a963c7c88863b8160526d397e4b3efb96f02e`。

源方法为 `BeyondDynamicBone.TeamManager+AlwaysTeamUpdatePostJob.Execute`，method index 369639，RVA `0x5a2f048`，exact unwind 主范围2282字节，SHA256 `193884b57623d53197f56c228f9e8c031d7e646ed87ff928aa1da65ab4f53595`。本轮实现片段为 `0x5a2f63e..0x5a2f7ee`；字段偏移从 metadata 独立核验。

私有 `check_source_clock.py` 不导入生产舍入/时钟函数做预期值，直接从原 DLL 静态读取并受限解释该标量指令片段；未知地址、操作码或唯一 Clamp 调用以外的 call 全部拒绝。固定随机种子生成1000组状态，12个写回字段逐位一致。这个解释器仍不是执行原 DLL/Burst，也不是完整 PostJob 或 Unity 生命周期证明。

## 组合结果与边界

两帧组合验证为：时钟片段产生 Team updateCount/Running → 已有 `advance_center_step` 逐子步推进 nowUpdateTime/中心 → 已有 `build_step_work_lists` 只在 Step 位生效时发布整个粒子和 baseline chunk → 显式合并有限 Team 字段进入下一帧。额外调用一次 `updateIndex == updateCount`，确认 Step 位清除且列表为空，防止最后一步状态残留。

这只是串行、显式的离线组合。尚未闭合：完整 AlwaysTeamUpdate Pre/Post 的字典/sync/anchor/culling 分支，真实 Team ID/chunk/参数发布，暂停/seek 请求生成，跨帧 native scheduler，唯一 Transform writer，以及 Unity C# 候选后端。现有可见物理没有因此改变，不能称官方物理已在 Unity 运行。

## 验证

按 TDD 先得到缺模块的 collection RED，再实现。专项49项；新增模块90语句/24分支100%覆盖。完整 Python 回归、Ruff、Black、Pyright、compileall 和隔离依赖审计结果封存在同目录 `verification.json`，私有详细报告位于 `D:/EndfieldTechLib/notes/official-physics-team-clock-20261011-01/`。

下一步沿同一链补完整 Team 参数/Running/Reset 请求与真实11组 Team/chunk 统一发布，再接 Transform read/relative 分支和唯一 writer；完成离线候选链后才进入可回退 C# 后端与动作验收。
