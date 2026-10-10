# Tether：原数学、根索引与串行消费的有限值参考

2026-10-10。本轮只补齐离线参考，不改当前舞台、预览物理或Unity后端。源码为 `Tools/official_physics_tether.py`，专项测试为 `Tools/tests/test_official_physics_tether.py`；完整进度仍以[主线门禁](../official-physics-animator-buffer-20261003/PROGRESS.md)为准。

## 原始证据与路由

固定原文件SHA256：GameAssembly `c24495e51b406f03b03890c4788ee618ae022c991405be5d5b8b787cb775ae89`；metadata `0076743397acadf03d3b0064343a963c7c88863b8160526d397e4b3efb96f02e`。只静态读取，不加载或执行原DLL。

| 原入口 | 身份与范围 | 本轮确认范围 |
| --- | --- | --- |
| 注册managed单槽 | method369163，`0x5a109f0..0x5a10e57` | Double数学与读写门禁 |
| 实际非Burst fallback | Invoke `0x5a11958` → `0x5a05d50..0x5a061b7` | 与注册body完整规范化对照，仅两处初始化flag地址不同 |
| managed range | method369164，`0x5a061b8..0x5a0629b` | signed count只读一次，按slot升序；UnsafeDo经range wrapper进入Invoke |
| 普通Job单槽 | method369194，`0x5a1108c..0x5a1152e` | 独立复核全body，不以managed函数名推定一致 |
| 普通Job循环 | method369193，`0x5a1102c..0x5a1108b` | count≤0跳过，否则升序调用单槽；不等于已验证实际并发调度 |
| 参数转换 | method369191，`0x34e1a90`及CHAININFO `0x4db76a2` | cloth0/1拷贝compression；cloth10用0.8f；其余不写compression；均写stretch=0.03f |

原名含拼写 `Tethre`。完整证据共27段（26段PE函数边界、1段有界leaf CFG），1599条指令；重新读取原字节复放52个关键位置、11个常量读取点与metadata布局。SHA/指令复放不是自动算法等价证明，也不是已观察到Burst执行。

## 计算与消费规则

- `slot → stepParticleIndices[slot] → signed Int16 teamId → proxy → signed Int32 localRoot`。proxy=`wrap32(proxyStart-particleStart+particle)`，rootParticle=`wrap32(particleStart+localRoot)`；所有负localRoot跳过。
- 只检查attribute的Move bit2。未添加Valid、NoCollision、Spring、team0或IsProcess过滤；这些额外过滤会改变原行为。
- 当前距离取root与粒子的Double `nextPosition`；参考距离取当前子步两者的 `stepBasicPosition`，不是bind距离或根链总长。
- 当前距离严格小于 `Double(Single(1e-8))` 跳过，等于仍继续；参考距离只在精确0时跳过。当前短边不读取后续basic buffer；未违反界限不读取velocity buffer。
- 下界为 `Double(Single(1-Single(compression)))`，上界为 `Double(Single(Single(stretch)+1))`；ratio=current/reference。先判断压缩，再判断拉伸，闭区间不写；界限交叉也不交换或钳正参数。
- 越界量除以 `Double(Single(0.3))`，按原Double strict比较钳到[0,1]得到gain。gap=`current-boundary*reference`；每轴先做delta/current，再乘gain*gap，顺序不替换为倒数乘法。
- next加correction，velocity reference加 `correction*Double(Single(0.7))`。没有中心、depth、friction、power或Team flag系数混入。
- 原0.3/0.7分别为 `0.30000001192092896` / `0.699999988079071`，不能直接换成Double字面量；距离平方求和保留 `(dy²+dx²)+dz²`。

API提供参数转换、selected particle、单slot及managed串行range。range私有发布next/velocity，并让重复slot、先前改过的root读取已完成写入；它不是native并发、原数组发布或Job调度的替代证明。未知cloth type必须显式传previous compression，不捏造未写字段的初值。未实现DataValidate。

## 可复核测试

71项专项通过；3524项全量通过，114个subtest通过，3项历史skip、2项历史Pillow警告。49个物理参考模块共4580个可执行语句、1070条分支，行/分支覆盖率100%；Tether自身132个语句、36条分支均覆盖。Ruff、format、Pyright、compileall通过；临时工具环境41项依赖pip-audit无已知漏洞，不代表Unity或整个项目无漏洞。

测试包括非轴向Double修正、Single界限误差、epsilon等号、精确零参考长度、稀疏proxy/root映射、signed Team、Move-only门禁、重复slot、已更新root及 `Start→Tether→End→下一Start`。初始RED为缺少新模块；初次运行两处错误测试预期已更正，其中ratio=0.6落在Single下界外的案例另保留为精度回归，不把夹具错误藏成实现修复。

私有证据目录：`D:/EndfieldTechLib/notes/official-physics-tether-20261010-01/`。重点为 `root-source-final-01.json`、`source-certificate-01.json`、`manual-review.md`、`checks-red.json`、`checks-02.json`与JUnit/coverage。公开[verification.json](verification.json)记录来源SHA、测试与限制。本轮由主代理人工复核；并行审阅因额度不可用，**没有独立代理语义审阅结果**。

## 交付边界与下一步

适配器仅接受有限、可表示值及有效索引；拒绝策略不是原游戏异常或NaN行为。Python sqrt与CRT/Burst逐位一致未验证。真实proxy/Team/list生产、allocator、原wrapper/runtime分流与依赖尚未闭合；不以默认零值补这些输入。

下一硬缺口是Angle完整消费、Bending/Motion/SelfCollision等剩余算子及真实输入/依赖链；已有角度cache/数学不等于Angle完整solver。候选链齐备后再做可回退C#后端、角色实例与MMD/解包动作下reset、暂停、seek动态验收。本轮没有新可见效果，也不宣称全部官方物理完成。
