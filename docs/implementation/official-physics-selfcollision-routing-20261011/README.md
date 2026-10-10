# SelfCollision：先按官方启用条件缩小当前角色范围

2026-10-11。**交付是离线路由与缓冲更新计划，不是碰撞求解器或 Unity 新效果。**

## 对提弗洛斯的结论

固定 SHA 的 11 组保存配置全部为 BoneCloth=1、selfMode=0、syncMode=0、空 syncPartner。若这些参数仍有效、角色独立运行且没有启用同步碰撞的外部父组，官方 UpdateTeam 会清除所有自碰撞／同步碰撞需求位。这个结论不依赖尚未生成的真实边／三角形数量。

因此当前独立角色候选链不必先补整套 SelfCollision 碰撞数学。但**不能**据保存模式为零宣布全局计数为零：外部父组可激活 PSync，其他角色可占用全局缓冲，旧有效 chunk 必须释放。这里没有观测游戏运行时的父组表或动态参数覆盖。新建独立 roster 的零计数是明确场景前提，不是伪造捕获值。

## 代码与已恢复规则

- `Tools/official_physics_selfcollision_routes.py`：参数转换、一次已解析 UpdateTeam 的 flags、三类 chunk 操作计划、成功操作后的全局计数预测和同步目标刷新请求。
- `Tools/tests/test_official_physics_selfcollision_routes.py`：68 项专项，包含 mode0 收到外部父组、Valid+Exit 父组仍参与、旧缓冲释放、计数溢出／下溢和现有子步计划接续。
- 参数 Convert 仅对 BoneSpring=10 将两模式清零；厚度与质量照样复制。16 项曲线样本必须由调用方预先转换，未插入钳制或替代 Unity 曲线采样。
- 原 UInt64 flag 位 32–49 重写，其他位保留；Exit=bit8，父组 Valid=bit0。FullMesh=2 不等于必须是 MeshCloth 类型。
- chunk 有效仅取 signed dataLength>0；需求开启且旧 chunk 有效时保留，不按新拓扑计数重建。需求关闭才释放有效旧 chunk。
- 全局 Point/Edge/Triangle 计数按原 Int32 增减；IntersectCount 按 44–49 任意位旧／新状态变迁增减一次，不按接触数或父组数量增加。
- 尾部对非零 syncMode 且存在的目标继续 UpdateTeam；这里仅报告请求，不执行尾循环、不加入原实现没有的 visited 防环策略。

| 判定 | Self | Sync | PSync（每个有效父组 OR） |
| --- | --- | --- | --- |
| 路由门禁 | 本组 mode=2 且未 Exit | 本组 syncMode=2、目标存在且未 Exit | 本组未 Exit、父组 Valid 且父 syncMode=2 |
| EdgeEdge | 本组 E>0 | 本组 E>0 且目标 E>0 | 本组 E>0 且父 E>0 |
| PointTriangle | 本组 T>0 | 目标 T>0 | 父 T>0 |
| TrianglePoint | 本组 T>0 | 本组 T>0 | 本组 T>0 |
| EdgeTriangleIntersect | 本组 E>0 且 T>0 | 本组 E>0 且目标 T>0 | 本组 E>0 且父 T>0 |
| TriangleEdgeIntersect | 本组 E>0 且 T>0 | 本组 T>0 且目标 E>0 | 本组 T>0 且父 E>0 |

E/T 指对应 Team 的真实 chunk.dataLength。全局 host 仍按显式计数决定是否调度，不使用本组 flags 代替全局计数。

## 证据与验证边界

当前版本 GameAssembly 与 metadata 只做文件字节静态检查，未加载或执行。参数 Convert=369050/0x34dff30，UpdateTeam=368942/0x343d8b0，Register=368940/0x39d2b10，RuntimeSelfCollision=368947/0x32b2f20，SolveIntersect=368950/0x32b2ed0。

私有原始证据目录：`D:/EndfieldTechLib/notes/official-physics-selfcollision-routing-20261011-01/`。input-review 和 dispatch-review 独立提取布局、枚举、原指令与调用关系；final-review 独立审查实现。公开 [verification.json](verification.json) 记录来源、测试、哈希与保护门禁。stock MagicaCloth2 仅辅助定位，不作为当前游戏等价证明。

完整回归：3806 passed、114 subtests、3 项历史 skipped、2 项历史 Pillow warnings。68 项专项，当前模块语句／分支覆盖率 100%；Ruff、Black、Pyright、compileall 通过。临时测试工具环境 48 个包的 pip-audit 无已知漏洞；不代表整个项目安全审查完成。

未实现：实际 Team／父组图生成、native allocator／InitPrimitive、故障中断和并发发布、active SelfCollision 碰撞数学、真实 Burst、Unity 候选后端和动作动态验收。计数输出仅在计划中的缓冲操作全部成功后成立。

## 接续主线

按独立 11 组原配置推进真实 proxy/topology/work-list、Team 与骨骼数据生产；不为当前关闭的功能继续扩张碰撞数学。接入时必须显式检查动态参数和外部父组前提：若失效，active SelfCollision 尚未实现应明确阻止候选运行，不能把它静默当作 no-op。随后整合可回退 C# 候选后端，再进行 MMD／解包动作、暂停与 seek 的动态验收。当前舞台、原参数和现有运行后端保持不变。
