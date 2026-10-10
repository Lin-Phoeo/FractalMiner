# Angle：完整有限值消费与普通 Job 精度分流

2026-10-10。本轮补齐离线 Angle 单槽/串行 range，并纠正“普通 Job 可直接复用 managed 数学”的假设。没有改当前 Unity 舞台或预览后端。主线完成状态仍以[交付门禁](../official-physics-animator-buffer-20261003/PROGRESS.md)为准。

实现入口为 `Tools/official_physics_angle_pass.py`；保留已有 `official_physics_angles.py`、`official_physics_angle_cache.py`、`official_physics_angle_baseline.py` 的默认 managed 行为，以显式 `route="job"` / `ordinary_job=True` 选择独立复核的普通 Job 精度。这个选择是参考 API，不是推断出的官方序列化开关。

## 原始证据与身份

固定原文件 SHA256：GameAssembly `c24495e51b406f03b03890c4788ee618ae022c991405be5d5b8b787cb775ae89`；metadata `0076743397acadf03d3b0064343a963c7c88863b8160526d397e4b3efb96f02e`。只静态读取原字节，不加载或执行原 DLL。

| 原入口 | 身份与范围 | 已复核内容 |
| --- | --- | --- |
| 单槽 wrapper | method368684，`0x59d91f8..0x59d9360` | 调 Invoke `0x59db078` |
| 注册 managed 单槽 | method368686，`0x59d7b74..0x59d91f6` | 5762 字节、1211 指令；Double 几何链 |
| 实际非 Burst fallback | `0x59d5830..0x59d6eb8` | Invoke 在 `0x59db2fa` 调用；5768 字节、1211 指令 |
| managed range | method368687，`0x59d6eb8..0x59d702a` | signed count 一次读取，slot 升序，整条 baseline 完成后再进入下一条 |
| 普通 Job `Execute(index)` | method368722，`0x59d952c..0x59dace3` | 独立完整 body；6071 字节、1270 指令；两处重要 Single 边界 |
| 普通 Job `Execute()` | method368721，`0x59d94cc..0x59d952b` | 从 Job@320 读取 count，升序调用单槽；不证明实际并行调度顺序 |
| `UnsafeDo` / range wrapper | method368723 `0x59dace4` → method368685 `0x59d9360` | 经 range Invoke `0x59db794` 进入 managed range，另有未观测的间接 Burst 路由 |
| 参数转换 | method368719，`0x34e0850..0x34e0961` | 输入使用已 Convert 的曲线/参数；消费阶段不再乘一次0.2 |

实际 fallback 与注册 managed 完整规范化对照有24处 operand 差别：2处初始化 flag 地址、22处 scratch stack 放置。人工检查临时值生命周期后未发现运算 opcode、helper 调用或规范化 branch 目标差别；这不是自动二进制/算法等价证明。

主代理重新读取19段 PE 函数边界、4791条指令，复放24个精度调用点和20个 RIP 常量读取；另独立检查44字节 AutoToFloat3、38字节 float3 乘法两段直线 leaf 到 ret，明确不把它们当 PE 边界。索引审阅证据独立复放22段 PE 范围、4712条指令、44个控制/路由位置及6类布局。两份范围重叠，不相加当成唯一指令总量。完整指令仅留本地私有证据目录。

## 索引、缓存与消费顺序

- packed Int32 作为位模式拆分：unsigned high16 为 Team，low16 是**全局 baseline**。不添加 Team 的 baselineChunk.start；baseline start/count/data 均为 UInt16。
- `baselineDataStart+start` 解析 baseline 数据，粒子与 proxy 分别用各自 chunk 起点加 local index。Team 窗口不混用；稀疏 typed map 只改变参考存储表示，不改变全局 baseline/数组 offset。
- 两种约束都关闭时不解析 Team/baseline；enabled 空 baseline 无逻辑写入。managed 原 body 在早退前复制 full float4 power 和参数，普通 Job 的 power.w 读取不同；标量 API 不模拟这些原始内存读取时点。
- prepass 对所有列出的粒子复制 basic rotation，包括 root/fixed；非首槽按启用项初始化 edge cache，包括 fixed。跳过 parent/cache 的是**槽0**，不必是 local vertex0。
- 求解只以 Move bit2 过滤，不添加 Valid、NoCollision、Spring、Team0、IsProcess 等门禁；父粒子位置/速度反馈也只在父 Move 时写。
- baseline 保留原 UInt16 存储顺序；缓存每条 baseline 初始化一次，然后恰好三轮。每条边依次 limit → child rotation cache → restoration，写入立即被后续边读取。不是 Jacobi，也不是先所有 limit、再所有 restoration。
- restoration 不重写 rotation cache；子边移动父点不会凭空触发祖先 rotation 重算。
- range count 作为 signed Int32 只取一次；≤0 无逻辑写入；升序完成每条 baseline 后传递全部状态。重复 baseline 不去重，第二次从当前状态重新初始化启用缓存。

## 两条精度链不能合并

共享部分保留原 Single 曲线/摩擦/重力系数运算、Double limit 位置修正，以及各自拓宽的0.4f/0.6f/0.9f常量；不能把0.6f替换为 Double 的 `1-0.4f`。回拉 pivot 三轮为原 Single 计算；重力混合保留 `gap=S(1-falloff)` 后再用 `S(1-gap)`，不代数替换回 falloff。

| 环节 | managed / 非 Burst fallback | 普通 Job |
| --- | --- | --- |
| limit 后用于 FromTo 的更新 child-parent | Double difference 直接输入 | `0x59da560` 先 AutoToFloat3，`0x59da585` 拓宽再输入 |
| restoration 输入方向 | Double delta | `0x59da6b9` 收窄 delta，拓宽给 FromTo |
| restoration 旋转 desired | Double rotate | `0x59da7ce` 调 Single rotate `0x2cd4520` |
| pivot / desired 三次向量缩放 | Double | `0x59da7f6/0x59da87d/0x59da910` 分别 Single 乘法，拓宽后与 Double parent 组成目标 |
| 目标减当前值、摩擦修正、next / velocity reference 更新 | Double | 仍是 Double，不把最终修正一并收窄 |

`strength=0` 不添加早退：普通 Job 仍进行 Single 几何缩放，可能产生可见于精度测试的修正。固定父点不做权重重分配。绝对世界坐标不能先收窄；先以 Double 做 child-parent，再收窄局部 delta，保留 Double parent 原点。

## 验证及复核范围

专项164项通过（旧 Angle/cache/baseline103项＋新增61项）；全量3585项通过，114个 subtest、3项历史 skip、2项历史 Pillow 警告。50个物理参考模块共4678个可执行语句、1098条分支，行/分支覆盖率100%。Ruff、format、Pyright、compileall通过；临时工具环境41项依赖无已知 pip-audit 漏洞。覆盖率和合成数据不是官方动态正确率，也不是Unity安全审查。

测试含独立 `struct.pack/unpack` Single 期望、精确 dyadic 零强度案例、near-parallel 阈值跨分支、非平凡旋转、固定/可动父点、稀疏/高位 Team、全局 baseline、关闭/空/仅固定首槽、cache 保留、重复列表、原顺序、非法selector及 Int32 地址拒绝。`Start→Tether→Angle→End→下一Start` 两路组合检查使用更新后的 velocity reference，不读取陈旧积分值；这不是全部约束调度证明。

初始 RED 为新函数/selector/模块缺失；Int32 aggregate 地址保护另留修正前失败。连续步测试初稿是轴向已对齐边，却误要求普通 Job 必须产生改动；保留失败报告，改为非共线 `(1,2,0)` 夹具后通过，没有为满足错误测试去改原数学。

数学与选择/顺序由两个独立代理从原字节和当前代码复核；另一路提供独立精度夹具。主代理重放静态证据、人工检查 diff 并跑全量回归。最终代码 SHA、报告 SHA 和门禁见 [verification.json](verification.json)。私有证据：`D:/EndfieldTechLib/notes/official-physics-angle-pass-20261010-01/`；主要文件为 `source-final-02.json`、`source-certificate-01.json`、`selection-review/selection-certificate-02-root-replay.json`、最终两路 code review、RED/green JUnit、`checks-02.json` 和 coverage。

## 尚未证明的内容及下一步

有限适配器要求索引有效、数组一致、首槽非 Move、非零可表示方向；普通 Job 还拒绝 Single 收窄后归零的方向。checked Int32 aggregate 拒绝属于适配器策略，**不是原生 wrap 或异常行为模拟**。原 body 对 fixed/empty 条件的提前读取、非法内存、NaN、alias、并发或 partial write 不由私有不可变结果模拟。

没有观察实际 Burst 指针、native 并行 baseline 的独立性/顺序，没有验证 Python libm 与 CRT/Burst 逐位一致；也没有从这些测试证明真实提弗洛斯 list/Team/proxy 已生产齐全。

下一硬缺口为 Bending/Motion/SelfCollision 等剩余算子与真实输入/依赖链。候选链齐备后再做可回退 C# 后端、真实11组绑定、MMD/解包动作下的 reset/暂停/seek 验收。这轮 Angle 有限值参考完成，但完整官方物理与 Unity 可见效果仍未完成；当前舞台保持原样。
