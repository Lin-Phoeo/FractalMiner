# 官方物理：11 组 world proxy / reset 全局重定位

日期：2026-10-11。接续[11 组候选 Team 核心布局](../official-physics-team-layout-20261011/README.md)，将[世界 proxy / 首次 reset](../official-physics-world-proxy-20261011/README.md)中每组独立的 Team1、零起点参考结果重定位到统一 Team1..11、全局 proxy/particle 窗口。

本轮只移动索引和 Team 身份，不重新计算任何浮点。两态各 11 组、140 个世界位置/旋转和 140 个粒子 reset14 状态逐值复制；每个局部结果必须是完整 Team1/flag15、proxy/mesh/skin/particle 起点0、升序 `0..count-1`、14字段写序固定且 result.state 与保存 state 完全相等。任一条件不成立即拒绝，不用猜测或 fallback。

## 全局发布结果

新增 `Tools/export_official_physics_global_state.py`。它同时校验 world/reset 与布局的 getter scope、imports SHA、两态名称、11 组名称和序列化 component identity，并重新验证九个候选 arena 对 Team 顺序连续覆盖。

输出两态各自包含：

- 140 槽 `proxy_world_positions` / `proxy_world_rotations`；
- 全局升序 `world_written_vertices = 0..139`；
- 140 槽 proxy Team ID 与 particle Team ID；
- 140 槽 particle reset 状态；
- 每项显式记录 global particle、global proxy、Team ID、原 14 字段状态/写序及 reset 标志。

Team1 覆盖最前15点，Team11覆盖全局132..139；所有 Team 边界按上一单元封存窗口映射。独立验证脚本不导入生产导出器，从局部 world/reset 与布局重新拼接两态，比较全部 280 个世界/粒子 payload 和 reset 结果结构，结果完全一致。

真实导出位于 `D:/EndfieldTechLib/notes/official-physics-global-state-20261011-01/eleven-global-world-reset-02.json`，SHA256 `f479050dbb6e9c63a5b5fe25510eea69a9e9256f039a75f590c1d41b7ee924aa`。

## 边界与下一步

两个保存状态各自用本态 bindpose/getter 建成，仍不是同一角色连续动画的两帧，因此 `changing_animation_verified=false`。候选 Team ID/窗口不是官方运行时 allocator 观测；本轮没有 NativeArray 写入、Job 调度、Unity/C# 后端、舞台或可见效果变化。

后续不再消费每组 Team1/零起点实验数据，而直接以本全局状态为首次 reset 输入。下一主线是恢复并接上 TransformRead 的 relative 分支、动画变换读取/状态发布和唯一 Transform writer；再进入可回退 C# 候选后端和解包动作/MMD 多帧实测。
