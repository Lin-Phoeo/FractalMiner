# 官方物理：锚点生产与 Double TRS / full inverse 参考

2026-10-09。新增 `Tools/official_physics_frame_anchor.py` 与 `Tools/official_physics_matrix.py`，补上锚点 local position 的重建、锚点运动对 working-old 的贡献，再接入[瞬移/平滑](../official-physics-frame-prelude-20261009/README.md)和[帧惯性](../official-physics-frame-inertia-20261009/README.md)。交付仍是离线有限值参考，**没有替换当前 Unity 后端，没有新增可见物理效果**。

## 实际来源

固定 GameAssembly SHA `c24495e51b406f03b03890c4788ee618ae022c991405be5d5b8b787cb775ae89` 与 metadata SHA `0076743397acadf03d3b0064343a963c7c88863b8160526d397e4b3efb96f02e`，只静态读文件，不执行/加载/注入/附加。

kernel369644 内部区域 `0x5a35a8d..0x5a35eba`（尾不含），1069字节/223指令/SHA `eff1c9f06ba0c19487349e43fb7b132d87d8a7dc04965462175b794058f0e54d`，不是独立函数。67 条关键指令、17 个精确 unwind helper 记录与具名 `Unity.Mathematics.math.inverse` 路径已核对；inverse 的58次 helper调用顺序与 Double 分母归约、四lane reciprocal、乘/减及shuffle八lane选择分别核查。不是自动全CFG/完整寄存器数据流证明或原生逐位数值验收。

矩阵代数亦参照项目已有 Unity.Mathematics 1.3.3 `matrix.cs` / `double4x4.gen.cs`；该来源不是“游戏源码”。先用游戏二进制确认实际调用路径，再据矩阵代数和静态次序写参考。参考模块保留 Unity copyright 与 Unity Companion License 的说明；不发布包缓存原文件或游戏资产。

## 必须保留的顺序

1. `build_double_trs`：quaternion 先窄化 Single，构造 Single 3×3矩阵，不强制归一化；每列转Double，再乘拓宽后的Single scale，最后放入Double translation。列缩放不得提前到Single。锚点调用scale固定 `(1,1,1)`，generic helper支持源传入的其他scale。
2. `inverse_double_matrix`：完整4×4 lane-packed minors及 signed denominator 归约。不是 fastinverse、inverse quaternion+scale 或numpy求逆替代。numpy只在测试中作为独立数学参照，不能证明原生逐位一致。
3. `transform_double_point`：`((c0*x+c1*y)+c2*z)+c3`，返回xyz，不做w除法或提早转Single。
4. `0x10000`（AnchorReset）或既有reset `0x4`：复制当前anchor位置/旋转到oldAnchor，再用**完整inverse TRS**把当前component世界位置变为anchor local，最后窄化Single。此初始化独立于Anchor `0x8000`，不是拿working-old当输入。
5. Anchor `0x8000` 才生产运动贡献：拓宽已保存Single local，用当前anchor TRS重建目标；目标减已有working-old先Double后Single。旋转差是 `currentAnchor * inverse(oldAnchor)`，不是倒过来。
6. `weight=Single(1-anchorInertia)`；位移 `lerp(0,delta,weight)`，旋转 `slerp(identity,deltaRotation,weight)`。Single shift拓宽后加到working-old；shiftRotation**左乘**working-oldRotation。即使weight为0也置 `0x400`。
7. 未启用Anchor时只清本轮anchor临时shift/rotation，不动working-old、不读取anchorInertia。初始化与贡献都不是旧anchor的每帧tail发布，调用方不能误把不变oldAnchor直接反馈到下一帧。

Center unboxed字段：anchorPosition@0 / anchorRotation@24 / oldAnchorPosition@40 / oldAnchorRotation@64 / anchorComponentLocalPosition@80。anchorInertia来自Cloth的InertiaConstraintParams第0字段。位置保留Double，local及旋转保留Single。

## 使用与边界

`anchored = advance_frame_anchor(sign_resolved_state, frame_team, sampled_anchor, anchor_inertia)` → `prepare_frame_inertia(anchored.state, anchored.team, prelude_settings)` → `advance_frame_inertia(...)`。全部输入来自**同一帧**，frameWorld目标和component/pivot/history已先完成前序解析；本函数不选择采样anchor索引、不构造frameWorld、不进行signed-scale remap、不写NativeArray/Unity骨骼。

39项测试覆盖general/projective inverse、非单位quaternion、负scale、Double大坐标、Single缩放边界、左右乘、两个reset标志、未选中输入、权重端点，以及anchor→smoothing→inertia交接。完整回归和覆盖率见 `verification.json`。finite/[0,1]权重/拒绝奇异inverse是适配策略，不冒充官方NaN/异常规则；Python数学函数和Double算术参考不冒充CRT/Burst bit oracle。

本地完整证据：`D:/EndfieldTechLib/notes/official-physics-frame-anchor-20261009-01/`。下一主线是**signed-scale remap、实际帧中心目标生成及完整reset/tail发布**；新的矩阵helper可复用，但这些调用方还没有因此自动完成。随后仍须真实proxy/Team发布、风区/碰撞/约束完整消费、C#候选后端和MMD动态验收。
