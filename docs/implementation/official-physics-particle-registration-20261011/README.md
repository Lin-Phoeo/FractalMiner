# 粒子注册、启用标志与首次 reset 桥接

2026-10-11。接续[Line/Distance 输入生产](../official-physics-distance-production-20261011/README.md)。本轮将原粒子注册和启用位片段接到已验证 reset14，关闭**给定分配结果、Team 状态和世界 proxy 输入**的有限参考。不是完整 allocator、Team 生命周期或已接入 Unity 的官方物理。舞台、渲染、湿身、阴影和现有预览物理未修改。

## 本轮实现

- `Tools/official_physics_particle_registration.py`：15 个数组原 Add 顺序、完整 VertexCount、首返回 chunk 到 Team.particleChunk 的计划；保留原 Int32 ID 与 low16 signed-short fill。其余14数组不自动清零，也不填绑定姿态。
- 同模块 `apply_team_enable_bits`：原 owner/Team0 门禁，启用置2/4，禁用清2/4并置0x100000；同值操作仍执行。CompleteMasterJob、集合、Collider/Transform Enable 仅是未执行调用描述。
- `Tools/official_physics_particle_init.py`：给定注册窗口与独立 proxy 起点，复用 `prepare_particle_frame`。窗口内所有粒子进门禁，不按 Move/Fixed/Invalid 过滤；返回私有状态与原14项写序，不改调用者缓冲。

注册接口返回紧凑 O(15) 计划，不物化调用者声明的大容量数组。15份分配结果的起点/数量一致、非负Int32、显式容量足够，均为**安全适配器策略**；原函数只保存首返回值，并不检查其余14个起点一致。原 Register 本体不限制 Team0/负数，它执行 signed Int32 的低16位截断。首次 reset 消费者另有限定的正Int16安全域，且必须同时匹配原 Int32 ID 和 short fill，禁止用65537→1的截断别名误接另一Team。

## 原顺序与精度边界

1. `SimulationManager.RegisterProxyMesh` method370396/RVA0x343f930，owner.isValid@364为false在读process/容器/Team之前返回。VertexCount来自 `VirtualMesh.localPositions` 容器count，不是render Transform数量。
2. 注册顺序：teamIdArray、nextPos、oldPos、oldRot、basePos、baseRot、oldPosition、oldRotation、velocityPos、dispPos、velocity、realVelocity、friction、staticFriction、collisionNormal。只有teamIdArray显式fill short Team；两套模拟/动画历史不是一个缓冲。
3. 原 Add 复用 free chunk 时不清旧pose；扩容才以ClearMemory=1创建新内存。注册不等于首次初始化，不能默认零四元数为identity。stepBasicPosition/Rotation不在这15个Add中，须由独立producer生成。
4. AddTeam初flag0x0d没有Enable2；SetEnable开启为0x0f，能过Process+Reset，但没有Running0x20/Step0x80，不能直接产出step work-list。禁用marker0x100000在后续启用时不擅自清掉。
5. 首次reset仍由原门禁决定：Process且Reset4时，从 `proxyCommonStart - particleStart + globalParticleIndex` 取世界姿态，保留Double位置、Single原四元数幅度，重置14缓冲。inactive/no-reset保留脏状态且不读缺失proxy；history-only请求由本FIRST-RESET桥明确拒绝，应走已有同帧中心的历史变换接口。空窗口不误报fully_reset。

独立审查发现初稿只比较short fill可能丢失注册原ID：先保留失败RED和独立复现，再添加original_team_id与三方一致检查。原short cast未改；这项是接口安全修复，不宣称改变官方算法。

## 世界姿态必须由原 producer 生产

不能把本轮已有render-local位置、baseline父frame局部姿态或原始bone world getter直接标成world proxy输出。刚性参考态world getter与render-local位置最大分量差2.0669280290603638；静止态偶合不能证明等价。

已定位真正生产器 `CalcProxyMeshSkinningKernel$BurstManaged` method369736/RVA0x5a3fab0（完整1693字节），与物理后的mapping `CalcProxySkinning` 不同。它消费原local位置/法线/切线、权重、bindpose、skin→transform映射和**每骨当前float4x4矩阵**，按原Single运算加权、归一化后生成frame quaternion；位置最后才拓宽Double。现有imports JSON没有每骨动态矩阵，不能以snapshot TRS代替可能的shear。

因此本轮只接受显式caller-confirmed global world输入，不输出伪造的11组官方world初始化缓存。`world_proxy_pose_confirmed=True`只是调用前提，不是认证证据。下一单元直接补已定位producer的三辅助运算、四Team窗口映射，并从已有上游getter原矩阵取得两态参考输入；不重新广泛调查整套物理。

## 验证及仍未完成的主线

133项专项、完整4302项+114 subtests通过；3项历史skip、2项历史Pillow告警。新增两模块111语句/38分支覆盖100%；Ruff、Black、Pyright、compileall、实际工具环境依赖审计通过。详细结果及SHA见`verification.json`。

原文件只静态读取，未加载/执行DLL、启动游戏或运行Unity。主代理重新复验78片段/16551字节、4签名、15字段类型、32锚点；独立源审查再核对9个完整家族/29锚点，并独立复核注册和reset接口。证书/完整反汇编及原资产仅保存在私有目录，不上传。

剩余工作按交付依赖合并为三段，不是三个小补丁，也不能据此给完工百分比：

| 阶段 | 必须闭合 | 当前边界 |
| --- | --- | --- |
| 输入与生命周期 | 世界proxy producer；Team/chunk/参数与clock/Running/Step；启用约束列表；唯一writer/状态发布 | 已有局部输入、注册计划与reset桥，尚非完整动态输入 |
| Unity候选后端 | 把已验证数学和上述输入接入可回退C#后端，统一采样/求解/回写顺序 | 未替换现有预览后端 |
| 动作动态验收 | MMD/解包动作、暂停/seek/reset、多帧碰撞/接触、迁移与导出 | 尚不能以离线测试宣称通过 |

不继续扩张当前独立11组关闭的active SelfCollision数学；对尚未实现而被动态启用的分支明确拒绝，不能静默no-op。此轮没有新可见物理效果；完整缺口持续以[PROGRESS](../official-physics-animator-buffer-20261003/PROGRESS.md)为准。
