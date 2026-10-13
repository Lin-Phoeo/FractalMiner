# 官方物理候选的实时 world proxy / reset14 阴影门禁

2026-10-12，承接记录分支 `6138bcbe`。本单元在上一轮151个实时 Transform 与140个 Team ID 的 Unity shadow publisher 上，接入封存的一热骨权重、局部位置/法线/切线和 bindpose；每次从当前舞台骨骼重新计算140个 world proxy 位置/旋转，并向本单元自有的持久 `NativeArray` 写入140粒子的14项首次 reset 状态。Unity 2022.3.30f1 在真实 `Typhoeus_MMD_Stage` 和真实 `动作.vmd` frame0/frame2 下运行通过。

这仍是**只读阴影候选**：`SolverExecuted=false`、`SolverOutputsWritten=false`，没有积分、约束、碰撞、显示预测或骨骼回写。预览图只证明真实舞台、动作和输入链能同时运行，不是“官方物理效果完成”的截图。

## 坐标证据纠错

初版门禁错误地把 `eleven-global-world-reset-02.json` 当成恢复角色的 root-local 真值，得到约1.97米和178.44度误差。该文件及其 getter 源明确标注为“隔离重建的序列化参考树，不是游戏姿态或恢复角色”，因此直接跨层级比较没有语义依据，不能靠放宽阈值处理。

最终门禁拆为两层：

1. **封存资料层**：global-state 的140个 rest world position/rotation 与同一 SHA 封存 imports 的140个 snapshot 逐项核对。最大位置误差 `3.588675e-7` 米、旋转误差0度，证明全局重定位没有改变来源值。
2. **当前Unity层**：封存数据为一热权重，且每个 proxy 顶点位于其骨骼原点，因此 `currentBone.localToWorld × bindpose × vertex` 必须等于当前 live Transform 的 world position/rotation。canonical、MMD frame0、MMD frame2 三态的最大位置误差 `4.109977e-7` 米、旋转误差0度。

这两个门禁分别证明资料继承和实时适配；不再把合成参考树的世界坐标误称为舞台角色坐标。

## 当前真实数组与写入

`EndfieldOfficialPhysicsShadowWorldInputs` 自有并释放：

- 140个 proxy `double3` world positions；
- 140个 proxy `quaternion` world rotations；
- 6组 `double3` reset位置：next、old、base、oldAnimation、velocity、display；
- 3组 reset旋转：old、base、oldAnimation；
- velocity、realVelocity、friction、staticFriction、collisionNormal 五组缓存。

每个粒子严格写14项，因此每态是 `140 × 14 = 1960` 次字段写入。canonical、MMD frame0、MMD frame2 都写140个 world proxy 和1960项 reset；reset误差0。发布前后逐个检查151个解析 Transform 的局部旋转，最大变化0，确认此阶段没有向角色写物理输出。

动态证明使用真正的 MMD frame0 作为基线，再应用 frame2；140个 proxy 槽都发生变化。早期从 canonical 直接比较 frame2 的结果已作废，因为其中混有T-pose校准变化，不能单独证明VMD动态。

## Unity实际结果

最终 D3D11 可见运行在 `D:/EndfieldTechLib/notes/official-physics-shadow-world-20261012-01-green-08-visible/`：

| 门禁 | 结果 |
| --- | --- |
| Unity / 场景 / 动作 | 2022.3.30f1 / `Typhoeus_MMD_Stage` / `动作.vmd` |
| 容量 | 140 world proxy / 140 particle |
| canonical写入 | 140 world + 1960 reset字段 |
| MMD frame0写入 | 140 world + 1960 reset字段 |
| MMD frame2写入 | 140 world + 1960 reset字段 |
| 真正frame0→frame2动态 | 140槽变化 |
| 封存来源最大误差 | position `3.588675e-7`；rotation `0°` |
| live Transform最大误差 | position `4.109977e-7`；rotation `0°` |
| reset / 角色旋转写入 | `0` / `0°` |
| solver / 输出写回 | false / false |

正向25项检查通过。错误 imports SHA 在发布前以 Unity exit 1 和 seal mismatch 拒绝；已有输出目录同样以 exit 1 在覆盖前拒绝。上一层151/140输入发布门禁21项继续通过。现有 alternate 可见物理链692项、61帧继续通过，并仍明确标记不是官方solver。Python全套为4754 passed、3 skipped、114 subtests，只有2条既有Pillow弃用警告。

## 下一步与未完成边界

下一单元应建立一个可释放的完整 arena owner，把已封存的 baseline、baseline data、distance start/data、attributes/flags、particle Team与当前 world/reset 数组装入同一连续布局，并加入严格容量、生命周期、reset/seek 门禁。其后才允许接 step/constraint/collision/display 求解顺序；最终必须以显式开关和唯一writer写回角色，禁止 alternate 与候选后端同时驱动同一骨骼。

目前尚未接入官方solver、碰撞体动态输入、完整work-list、Team时钟、暂停/seek reset、显示预测或角色回写，因此不能宣称官方可见物理已经完成。全局状态以 [PROGRESS.md](../official-physics-animator-buffer-20261003/PROGRESS.md) 为准。
