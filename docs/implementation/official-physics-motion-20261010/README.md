# 当前版本 Motion：活动范围与 Backstop 有限值参考

始于 2026-10-10，完成复放于 2026-10-11。本单元恢复 Motion 参数转换、单粒子数学、work-list 单槽及串行 range。**这是离线参考，尚未接入 Unity 候选物理后端；没有新可见效果。** 不以本地测试证明实际 Burst、完整 native 生命周期或 MMD 动态已经验收。

实现：[official_physics_motion.py](../../../Tools/official_physics_motion.py)；测试：[test_official_physics_motion.py](../../../Tools/tests/test_official_physics_motion.py)；机器可查证据：[verification.json](verification.json)。

## 1. 来源身份与入口

原 GameAssembly 与 metadata 仅静态读字节，未加载/执行；SHA 与精确 PE span 记录在 verification。`root-audit.py` 从当前注册元数据解析类型、签名及布局，不把旧版 `MagicaCloth2` 源码冒充当前官方源码。当前 Kernel 是独立类 `BeyondDynamicBone.MotionConstraintJobKernels`，不是约束内的同名嵌套类。

| 当前入口 | RVA | 本单元范围 |
| --- | --- | --- |
| registered managed 单槽 | `0x59f2464` | 已恢复有限输入消费 |
| Invoke 实际非 Burst fallback | `0x59e8c0c` | 独立定位并复核 |
| ordinary Job `Execute(index)` | `0x59f2f54` | 单独交叉检查门禁、精度及 helper |
| managed range | `0x59e9528` | signed count 快照、升序串行消费 |
| ordinary serial / UnsafeDo | `0x59f385c` / `0x59f38bc` | 入口与参数传递证据；不是并发调度实现 |
| 参数 Convert | `0x34e0970`，cold tail `0x4db75fc` | BoneSpring 例外与字段转换边界 |

registered 与 fallback 均 2329 字节、523 指令，归一后只有两处一次性初始化 flag cell 地址不同。ordinary 与其 call/branch 签名相同，并人工交叉检查消费路径。**签名相同不是自动整算法等价证明；没有观察实际 Burst target。** range 会调用 runtime-selecting wrapper，本参考明确选用已审计的 managed/fallback 有限数学，不声称 wrapper 必定走该路线。

本地 `MagicaCloth2 2.17.1 MotionConstraint.cs` 仅交叉确认高层意图。旧版是 `DataChunk` 连续循环、float3 位置；当前是显式全局 work-list、signed Int16 Team、double3 的 base/next/velocity。位置精度以当前二进制为准。

## 2. 数据、门禁与参数

Job 的 work-list / Team / params / attributes / depth / teamId 偏移为 `0/16/32/48/64/80`；base / next / velocity / baseRot 为 `96/112/128/144`；friction / collisionNormal / count 为 `160/176/192`。Motion params 内 flags/曲线/半径/曲线/stiffness 为 `0/4/68/72/76/140`，位于 ClothParameters `@468`；radius curve `@92`、normalAxis `@156` 不属于 Motion 子结构。

逻辑顺序：

1. `slot -> global particle -> signed Int16 teamId -> params`。两开关均关闭即返回；Team 地址已计算，但其字段复制在 flag 门禁之后。
2. `proxy = wrapInt32(proxyStart - particleStart + globalParticle)`，Move 只测 `0x02`。
3. 读取 next/base/proxy depth，然后 IsMotion 排除 `0x08`；不是 `0x10`。不附加 Valid、team0、IsProcess、DisableCollision 或 Spring gate。
4. 合格且启用时写 next/velocity，即使 stiffness=0 或最终修正为零。friction/collisionNormal 参数存在，但当前 Motion body 没有消费或写回它们。

`convert_motion_parameters` 接收**已完成 ConvertFloatArray 的 16 个 Single 样本**，不冒充 Unity AnimationCurve 采样器。clothType10 只强制两个 flags 为 false，其它字段仍转换/复制；其它 Int32 类型照抄 flags。非 Spring 的 max=true 冷块写1后跳回 `0x34e09ad`，已纳入复放。Convert 不替代 DataValidate，不偷偷钳制 radius/stiffness 或 curve。

安全 adapter 明确拒绝负 native 数组索引、非有限/不可表示值及错误类型；这是 Python 输入政策，不是官方异常行为。Python 不模拟完整 native struct copy、alias、非法指针、partial-write 或非有限执行。

## 3. 数学和精度契约

| 步骤 | 恢复规则 |
| --- | --- |
| particle radius | 曲线采原始 Single depth，至少 `1e-4f`；之后才做 Single `depth*depth` |
| axis | Right/Up/Forward/三个反向，未知 Int32 默认 Up；Single quaternion 旋转，不归一化、不改 Double rotate；仅 max-distance 开启仍执行 |
| MaxDistance | 以 animation basePose 为中心；Double delta/length，curve 为平方 depth 的 Single 结果拓宽；只有 `length > widened(1e-9f)` 且 `length > limit` 才以 `limit/length` 缩放 |
| Backstop center | `base + widen(Single(-rotatedAxis * Single(distance+radius)))`；distance 用平方 depth；radius<=0 不求 backstop 曲线 |
| Backstop projection | Double delta/length；先 `length > widened(1e-8f)` 且 `length < widen(Single(radius+particleRadius))`，再真正球内 `length < radius` 才推到球面；normal 为三次直接除法，非倒数乘法 |
| final stiffness | Single stiffness 拓宽，`original + (candidate-original)*stiffness`，不 saturate，不把 stiffness=1 简化成直接赋值 |
| velocity reference | `velocityPos += (newPos-original)*widened(0.95f)`，不是十进制 Double `0.95` |

MaxDistance 先于 Backstop。没有插入 scaleRatio、initScale、simulationPower、质量、animation blend 或摩擦增益。Python sqrt 不作为官方 CRT/Burst 逐 bit oracle；这里验证的是有限输入的运算结构和显式精度边界。

## 4. 初稿纠错与测试

第一轮 66 项通过仍有两处共同错误：Clamp 与 Backstop 误共用 `1e-8f`、InvalidMotion 误用 bit16。独立字节审阅揭示问题后，先用修正后的断言跑出 **4 failed / 68 passed**，再修实现；不是只更改测试来迎合旧结果。

最终 74 项 Motion 测试通过，包括两个 epsilon 等号/下一 Double、bit8/bit16 分流、raw-depth 曲线调用顺序、Single 平方、六轴与未知值、独立180°旋转、Single 球心偏移、非轴向逐分量除法、Double 大世界坐标、未饱和 stiffness、widened .95、重复 slot 的顺序写入，以及 `Start -> Motion -> End -> 下一 Start` 速度反馈。串行参考使用私有外层 next/velocity copies，不修改输入、去重或伪造并行安全。

完整 canonical 回归及 Ruff、Black、Pyright、compileall、覆盖率、依赖检查见 verification。测试数和覆盖率不是物理完成百分比。此前代理额度中断的未完成审阅不冒记成最终实现审阅；已有数学、selection、fixture报告与最终审阅范围分别记录。

## 5. 提弗洛斯当前保存配置，不额外增强效果

封存配置有11组、164点，全部 BoneCloth、normalAxis=Up、maxDistance 关闭；backstop radius=10、distance=0、stiffness=1。**仅 `MBC_Typhoea_Hair_Front_Bangs_Short` 启用 Backstop**，其保存选择有5个 Move+Motion 候选；其余10组 Motion 两开关均关闭。不能为了“效果更明显”统一打开全部组。保存选择/配置不等于实际 runtime proxy、work-list 或帧内调用数量。

没有修改官方保存配置、当前渲染/湿身/阴影/MMD 或 Unity 场景。原11组/164点、7个运行时文件、main HEAD/index 与舞台 SHA 在提交前后独立检查。

后续硬缺口仍是 SelfCollision 路由/启用条件、真实 topology/work-list/proxy/Team 生命周期及实际 C#候选链发布，之后才是 Unity 下 MMD/解包动作、reset/pause/seek 动态门禁；不能将本单元直接称为完整官方物理已经运行。

## 6. 可复跑证据

私有目录 `D:/EndfieldTechLib/notes/official-physics-motion-20261010-01/` 保存 extraction、原字节 SHA、root/独立证书、RED/GREEN JUnit、coverage 和 checks。原 DLL/metadata 或大体积 disassembly 不上传 GitHub。

```powershell
uv run --no-project python -B "D:/EndfieldTechLib/notes/official-physics-motion-20261010-01/certify-source.py" "source-certificate-replay-new.json"
```

证书输出必须是目录内未存在的新名字，脚本拒绝覆盖证据。专项：从仓库运行 `uv run --no-project --with pytest python -B -m pytest Tools/tests/test_official_physics_motion.py -q -p no:cacheprovider`。完整入口限定 `Tools/tests` 与 `docs/render-baseline/v2/tools/tests`，带 pytest-subtests/Pillow/NumPy/Capstone，不用会触发 qrenderdoc-host 脚本退出的裸根目录 pytest。
