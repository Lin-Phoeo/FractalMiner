# 官方物理：11 组候选 Team 核心全局布局

日期：2026-10-11。接续[粒子注册](../official-physics-particle-registration-20261011/README.md)、[世界 proxy / 首次 reset](../official-physics-world-proxy-20261011/README.md)和[Team 时钟](../official-physics-team-clock-20261011/README.md)，把原来“每组独立 Team1、每个数组从0开始”的实验布局替换为一份可供候选后端消费的 11 组统一核心布局。

这不是逐像素对照，也没有猜游戏某次运行的地址。布局输入来自已封印的两态 getter、baseline 和 distance 产物；Team ID `1..11` 与各 arena 前缀和是“全新空候选管理器、按保存组序串行创建”的明确策略。原生 `DynamicArray` 的真实 Team ID、free-list、复用结果仍未观测，输出不会将候选值标成官方运行时原值。

## 本轮闭合内容

新增 `Tools/official_physics_team_layout.py` 与封印导出器 `Tools/export_official_physics_team_layout.py`。每个 arena 有独立游标，绝不假设不同数组共享起点；只发布现有生产链能独立证明数量与用途的九个核心窗口：

| arena | 11 组总容量 | 数量来源 |
| --- | ---: | --- |
| proxyTransform | 151 | 每组 `skin + appended render Transform` |
| proxyCommon | 140 | 11 组 skin 顶点 |
| proxyMesh | 140 | world producer 的逐 proxy mesh 行 |
| proxySkinBone | 140 | 一对一候选 skin-bone 行 |
| baseline | 37 | 已生成 baseline flags/start/count 行 |
| baselineData | 126 | 已生成 baseline 数据 |
| particle | 140 | RegisterProxyMesh 完整 VertexCount |
| distanceStart | 140 | 每顶点 packed row/start word |
| distanceData | 176 | 已通过 1e-6 门禁的邻接/静止长度数据 |

两态 11 组的名称、序列化 component identity、skin 数量及九个计数必须完全相同；任一状态发生拓扑漂移就拒绝导出。最终布局中 Team1 的粒子窗口为 `0+15`，Team11 为 `132+8`；Transform 因每组多一个 render 槽，最后一组为 `142+9`。全部 arena 都从0连续覆盖到各自容量，不重叠、不留洞。

## 与已有生命周期片段的连接

导出器对每个 Team 用统一 particle 窗口调用既有 15 数组注册计划，确认 `teamIdArray` 到 `collisionNormalArray` 的安全候选窗口对齐，且 Team.particleChunk 与首个 Add 结果一致。它再用显式候选 stepping flag `0xaf` 调用既有工作列表生产器，得到全局粒子 `0..139` 和 37 个 `high16 Team | low16 GLOBAL baseline` 项。

`0xaf` 只是 `AddTeam 0x0d + Enable bit2 + caller supplied Running20/Step80` 的组合验收状态；它不声称完整原 PostJob 已经把这些位写入 NativeArray。AddTeam 初态仍是 `0x0d`，启用/reset 状态仍是 `0x0f`，时钟和 center step 各自已有的位生产规则没有被布局器替代。

真实两态导出封存在 `D:/EndfieldTechLib/notes/official-physics-team-layout-20261011-01/eleven-team-layout-02.json`，SHA256 为 `a783648e4a0881dcd1b53d8a4145c009bdba153e7556429edc3883f985ede3b4`。独立验证脚本不导入生产布局代码，重新读取三份封印输入、重算每个 arena 前缀、Team/baseline 打包及工作列表，结果 PASS。

## 明确保留的边界

本轮故意不发布尚未由当前输入闭合的 `proxyVertexChildData`、triangle/edge、proxyBone、fixedData、collider、bending/self-collision 等 Team chunk；它们不是零，也不是默认等于某个已知窗口。当前 11 组的零三角形、Self mode0 等前提只允许后续候选后端阻止未支持分支，不能借此伪造完整 TeamData。

还未完成：把已生成 world proxy/reset 两态从各组局部 Team1 重定位到这份全局布局；Team 参数完整转换与 constraint chunk 注册；暂停/seek reset 请求；TransformRead 相对分支、唯一 Transform writer 与实际 NativeArray/C# 发布；Unity 中解包动作/MMD 的多帧动态验收。本轮没有修改舞台或可见物理效果。

下一单元直接做“局部 world/reset → 统一 Team/chunk 的全局重定位及跨组连续帧验证”，随后补 Transform read/write 生命周期；不再回退到每组 Team1/零起点实验路径。
