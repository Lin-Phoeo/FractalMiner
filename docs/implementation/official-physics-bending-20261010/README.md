# TriangleBending：两阶段有限值参考

2026-10-10。本轮恢复当前版本 `BeyondDynamicBone.TriangleBendingConstraint` 的离线有限值参考：triangle-pair work 阶段把四个修正写入各顶点私有 `float3` 槽，aggregate 阶段再按粒子顺序以 Single 求和/平均，拓宽到 `double3` 后加到 `nextPos`。实现入口为 `Tools/official_physics_bending.py` 与 `Tools/official_physics_bending_pass.py`。

这不是 Unity 后端接入：没有改舞台、角色实例、预览物理或渲染，也没有产生新的可见效果。主线完成状态以[交付门禁](../official-physics-animator-buffer-20261003/PROGRESS.md)为准。

## 原始证据与身份

固定原文件 SHA256：GameAssembly `c24495e51b406f03b03890c4788ee618ae022c991405be5d5b8b787cb775ae89`；metadata `0076743397acadf03d3b0064343a963c7c88863b8160526d397e4b3efb96f02e`。全部证据来自只读静态解析，没有加载或执行原 DLL/游戏运行时。

| 路径 | method / RVA | 本轮用途 |
| --- | --- | --- |
| work wrapper / range wrapper | 369210 `0x5a13864`；369211 `0x5a1396c` | Invoke 入口与 range 身份 |
| work 注册 managed 单槽 / range | 369214 `0x5a13208`；369215 `0x5a068f8` | 当前有限值实现的主要静态参照 |
| work 实际 non-Burst fallback | `0x5a0629c` | 1628 字节、374 指令；与注册 managed 规范化对照 |
| managed helper | Volume 369212 `0x5a13a78`；Dihedral 369213 `0x5a127d0` | Double 几何、阈值与修正顺序 |
| ordinary work Job | serial 369267 `0x5a246ec`；index 369268 `0x5a24098` | 选择/调用签名交叉检查 |
| ordinary helper | Volume 369269 `0x5a24920`；Dihedral 369270 `0x5a23660` | 与 managed helper 的调用/分支签名交叉检查 |
| aggregate wrapper / range | 369236 `0x5a0c28c`；369237 `0x5a0c3d8` | 第二阶段入口身份 |
| aggregate 注册 managed 单槽 / range | 369238 `0x5a0bf0c`；369239 `0x5a0c334` | Single 累加、除法及 Double 写回 |
| aggregate 实际 non-Burst fallback | `0x5a047a4` | 896 字节、216 指令；与注册 managed 规范化对照 |
| ordinary aggregate Job | serial 369273 `0x5a205b8`；index 369274 `0x5a20614` | helper-call/branch 签名交叉检查 |
| 参数转换 | 369263 `0x34e1b30` | strict `stiffness > 1e-8f` 时 method 2，否则 method 0 |

来源证书重新读取17个方法跨度、9个常量位置与11组提弗洛斯保存配置。注册 managed work 与实际 fallback 均为374条指令，aggregate 均为216条；两组规范化对照各只剩2处不同的静态初始化 flag 地址。managed/ordinary 的 Volume、Dihedral、aggregate helper-call/branch 签名相同，单槽选择分支同形。它们支持本有限域参考，但不是自动 CFG 或整算法等价证明，也没有观察实际 Burst 函数指针。

本地 `_EndfieldRefs/ZMD/Assets/Plugin/MagicaCloth2/Scripts/Core/Cloth/Constraints/TriangleBendingConstraint.cs` 标识为 MagicaCloth2 2.17.1，SHA256 为 `87ba7a6898403581e6bf974fc021dd7710532c218325229da1d4cb41f9a3c701`。它只用于高层公式交叉参照；当前游戏已使用 `BeyondDynamicBone`、`double3` 和拆分的 work/aggregate 路径，不能把这份旧源码称为同版官方源码。游戏二进制才是本轮权威锚点。

## 布局、门禁与两阶段消费

- step triangle word：unsigned high12 是 Team，low20 是**全局 pair index**，不再加 Team pair chunk start。
- triangle pair `UInt64`：从高到低依次是四个 team-local `UInt16` 顶点；write data `UInt32` 从高到低是四个 `UInt8` 私有偏移。
- write index `UInt32`：high12 为 count，low20 为 base。work 写址为 `bendingBufferStart + base + privateOffset`。
- Team 字段锚点：`scaleRatio@96`、`negativeScaleSign@100`、`proxyCommonChunk@292`、`particleChunk@372`、`bendingPairChunk@416`、`bendingWriteIndexChunk@424`、`bendingBufferChunk@432`。
- work 门禁顺序是 method 0 → `stiffness < 1e-6f` → `Single(stiffness * simulationPower.y)` → saturate。等于 `1e-6f` 仍执行。
- `signOrVolume == 100` 在 method switch 之前选择 Volume。method 1 为无方向 Dihedral；method 2 使用 SByte 符号及 `negativeScaleSign`。
- 四个 Double 修正分别转换为 `float3`，写入生产器保证独占的私有槽。参考保留升序 managed range；不生成 topology，也不证明 worker partition 或 native 并发。
- aggregate 的 step particle 是全局索引；Team 来自该粒子的 signed Int16 team ID。先检查 `bendingPairChunk.dataLength`，再以 Move bit2 过滤 fixed 点，然后读取 count/base。
- aggregate 按槽序以 Single 累加并做 Single 除法，拓宽后加到 Double `nextPos`；不清空 write buffer。负 Team ID、越界、非有限值等由安全适配器明确拒绝，不模拟原生非法内存行为。

## 数学与精度边界

- Volume scale 为 Double `1000.0`；分母 epsilon 是从 `1e-6f` 拓宽的 `9.999999974752427e-7`；`1/6` 是从 Single 拓宽的 `0.1666666716337204`。
- Dihedral edge epsilon 是从 `1e-8f` 拓宽的 `9.99999993922529e-9`。两个法线除以各自 length-squared 使用逐分量 `divsd`；不能替换为一次 reciprocal 后向量乘法。
- fixed 点仍以拓宽的 `0.01f` 参与 work 数学；可动点逆质量为 `1 / (5 * (1-depth)^2 + 3 * friction + 1)`，保留 Single 运算边界。aggregate 才跳过 fixed 点。
- Volume rest 为 `Single(Single(rest * scaleRatio) * negativeScaleSign)`；directional rest 先乘 SByte 符号，再乘 `negativeScaleSign`；method 1 不乘这些方向符号。
- 官方保存的11组、164个点，其 TriangleBending stiffness 全为 `1.0`，因此参数转换候选均为 method 2；pair 上的 Volume marker 仍可优先覆盖。

Python 的 `math.acos/sqrt` 不证明与 CRT/Burst 逐位一致；aggregate 的 `divss` 以有限 Python 算术加最终 Single 收窄表示，理论上仍可能有极罕见 double-rounding 1 ULP 差异。因此本结果只称当前证据覆盖下的有限值/结构参考，不称 bitwise native clone。

## 验证与独立复核

- 专项：63项通过；新增测试覆盖非零私有 offset、有效刚度饱和、负 Team 安全拒绝，以及不对称 direct-`divsd` 精度夹具。
- 相邻约束：330项通过，覆盖 Distance/Angle/既有 constraint 组合。
- 正式全量入口：3664项通过、114个 subtest 通过、3项历史 skip、2项历史 Pillow deprecation warning。仓库根部裸 `pytest` 会收集仅供 qrenderdoc 运行的 `Tools/test_vb_access.py`，不是合法全量入口；本轮沿用已记录的 `Tools/tests + docs/render-baseline/v2/tools/tests` 入口并补齐 Pillow/NumPy/Capstone 依赖。
- Bending 两模块：367 statements、92 branches，综合行/分支覆盖率93%。
- Ruff、Black check、Pyright、compileall 全部通过。临时Python工具环境37项依赖，pip-audit未发现已知漏洞。

一位独立只读代码审阅者重新对照保存的 work/Volume/Dihedral/aggregate 反汇编，未发现阻断级语义错误；其提出的非零 offset、stiffness saturate 与负 Team 边界已转成测试并修正。另一位独立审阅者核对了文档证据边界，第三位核对了隔离提交/主索引保护流程。最终结论仍由主代理重放来源证书、跑专项和全量回归后给出；没有运行官方 DLL/游戏。

## 尚未证明及下一步

本轮没有证明实际 Burst 路由、native 并发/worker partition、真实 topology/work-list 生成、完整 Team/proxy/native array 发布、非法内存/NaN/alias/partial-write 行为、Unity C# 接入、11组动态结果、MMD或解包动作下的 reset/暂停/seek，也没有证明完整官方物理已经完成。

下一硬缺口是 Motion/SelfCollision，以及 TriangleBending 所依赖的真实 topology/work-list 与 list/proxy/Team 发布。候选链齐备后，才进入可回退 C# 后端、真实11组绑定和 Unity 动态验收。
