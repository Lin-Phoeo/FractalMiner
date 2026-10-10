# 普通 Point Job：独立形状数学与 Spring 速度纠错

2026-10-10。接续 [ColliderManager 生产](../official-physics-collider-production-20261010/README.md)，本批恢复独立普通 `PointColliderCollisionConstraintJob.Execute(index)` 的有限值参考。**不是完整官方后端已接入 Unity**；当前舞台、渲染、动作播放器及预览物理未变。

## 实际交付

- `Tools/official_physics_point_job.py`：独立 Job 形状消费、已选粒子求值、list ordinal → particle → signed Team → proxy 的单槽解析。
- `Tools/official_physics_point_collision.py`：保留 managed 形状路径，只复用已独立核对相同的门禁与累加；修复两条源路径共同存在的 Spring 速度参考偏差。
- 测试使用轴向和非轴向手算、独立 `struct` Single 舍入，以及已实现的 Double Collider WorkData 生产组合。不会把 managed 实现当作唯一数值真值。

输入仍须显式提供，未由 prefab 或角色 root 猜造原缓冲。不提供普通 Job 的“串行 range 等价”接口：实际 worker 分配、重复 list 引发的并发读写和 Burst 目标未观测。单槽返回私有逻辑写入，并不发布 Unity NativeArray。

## 关键发现：不能直接复用 managed 形状函数

版本锚点保持原始 `GameAssembly.dll` SHA256 `c24495e51b406f03b03890c4788ee618ae022c991405be5d5b8b787cb775ae89`，metadata SHA256 `0076743397acadf03d3b0064343a963c7c88863b8160526d397e4b3efb96f02e`。只读静态解析，没有加载或执行原 DLL。

| 项目 | managed kernel | 普通 Job |
| --- | --- | --- |
| 主体 | method368740，`0x59f47cc..0x59f5471` | method368824，`0x59f5ae0..0x59f679a` |
| Sphere 实际 helper | `0x59f5774` | method368825，`0x59f6b34..0x59f6dfe` |
| Capsule 实际 helper | `0x59f4494` | method368827，`0x59f679c..0x59f6a61` |
| Plane 实际 helper | `0x59f5670` | method368826，`0x59f6a64..0x59f6b34` |
| 粒子 radius / limit 生产 | Single 曲线、floor、scale 乘法 | 同样 Single，传 helper 时拓宽 Double |
| 球体合并半径 | Single 加法再拓宽 | collider Single 半径拓宽后与 Double 粒子半径相加 |
| 胶囊方向 | radial 窄化 Single，两次 Single 旋转 | radial 保持 Double，调用 `rotate_double@0x59d732c` 两次 |
| 胶囊半径 | taper Single，再 Single 加粒子半径 | taper Single，再拓宽与 Double 粒子半径相加 |
| 实际平面投影法线 | 输出法线 Single 后再拓宽 | 保留原始 Double 法线；Single 只用于输出 |
| 无 AABB 重叠时距离 | Sphere Double.Max；Capsule Single.Max 拓宽 | Sphere / Capsule 均 Single.Max 拓宽 |

Job 的 `isSpring` 参数存在于 Sphere 签名和调用处，**实际 helper 不读取它**。Sphere limit/0.85 回拉/distance×3 的门禁仍只是 `maxLength > 0`，而普通粒子调用方提供 -1；不能按参数名字自行增加 Boolean 门禁。0.85 常量是 Single 拓宽。

胶囊段投影 fraction 的求除是 Double，但会**先窄化 Single，再严格比较 clamp**，边界相等时保留原值，包括负零与负小数下溢后的负零，再拓宽给 Double lerp。旧参考先对 Double 限幅，会抹掉这个符号；两条路径已改用按源码顺序的共享 helper，保留实际失败及边界回归。超过 Single 范围的比例选相同限幅端点，不把 transient infinity 当成有限最终输出。没有把整段求值都提升为 Double。Quaternion 输入也仍 Single，不归一化输入以隐藏差异。

两条原路径均调用 `AABB.Overlaps@0x59e4490` 下的 `0x59ea6b4/0x59ea630`，因此保留已记录的非对称 z 比较，不擅自修成常规 AABB。未知 shape 的原默认 distance 为 100；Python 有限参考继续明确拒绝未支持的 enabled shape，不冒充该原默认分支或原日志行为。

## 修正此前遗漏的 Spring 反馈

碰撞对象均读取同一原粒子位置。穿透修正以 Double 累加，输出法线以 Single 累加；命中后先按次数求平均并计算 Single 法线长度。

- `next_position += average_correction * min(1, normal_length)`。
- Spring 有命中时，`velocity_position += average_correction`，**不乘上面的增益**。
- 法线长度低于原 Single `1e-8` 时，原平均修正寄存器清零，两种写回均加零；不是强行保留原始未门禁平均。

原 managed 和 Job 的寄存器数据流分别独立核对。旧参考把速度也加了缩放后的 position correction；已有单方向测试未暴露，因为增益恰为 1。两正交平面的独立测试先复现失败：速度 x 为 `7.265165038406849`，真应为 `7.375`；修复后通过。此前的覆盖率或绿灯不能替代这次语义核查。

## 索引、门禁与输出边界

Execute 的 index 是 list ordinal，读取列表获得 global particle，再读 signed Int16 Team。Team.colliderCount **等于零**先返回；collision mode 非 1 再返回。proxy = Int32 wrap(proxyStart − particleStart + particle)，attributes/depth 读 proxy，位置/摩擦/法线读 particle。valid、NoCollision、ordinary-fixed / Spring 的规则保持原顺序，无 Team0 或 IsProcess 附加过滤。

共享累加保持 Double correction / minDistance / friction 比例，与 Single normal 累加、平均、dot、sqrt、归一化及最终 friction 写入边界。三种形状的投影不额外除 normal squared。finite/representable/索引边界、未知 shape 和 mode 拒绝是适配器契约，不是原程序异常或非有限数行为。

## 可复核证据

私有目录：`D:/EndfieldTechLib/notes/official-physics-point-job-20261010-01/`。原字节与 DLL 不公开入库；本目录 `verification.json` 记录报告、脚本及所审公共代码 SHA。

- `body-audit.py` / `body-certificate-02.json`：主 Job、managed 主体、共享运算及写回路径，完整 span、65 个关键指令、9 个常量和实际 method signatures。
- `helpers-audit.py` / `helpers-audit-05.json`、`helpers-certificate.py`：形状 helper 及依赖闭包、精度边界、完整 PE span 与明确标注的无 pdata leaf CFG；未恢复 metadata 名称的 compiler clone 仍保留未知。
- `verify_frozen_source.py` / source replay：重新读取原字节，校验 span 哈希、原 PE 边界、指令与常量，不执行原程序。
- `checks-red.json`、`ratio-order-red.json` 与 `tests-red-01.txt`：修正前失败留存；`helpers-signed-zero-review.md` 为后续精度纠错的独立补充。最终测试/覆盖率/类型/格式/依赖与独立复审结果见 verification。

Python 数学库、显式值输入和离线测试都不能证明原 CRT/Burst 逐 bit 一致、真实数组发布或角色动态验收。

最终专项为165 passed（新Job95、managed及共享helper70），完整Tools/tests为3453 passed、114 subtests passed、3历史skip和2历史Pillow弃用warning。48个参考模块4448语句/1034分支均覆盖，Ruff/格式/Pyright/compileall及临时Python依赖审计通过。再次强调：这些数字是回归与覆盖范围，不是官方物理完成百分比。11组配置/164 saved点、7个runtime文件与9557条main index内容及flags保持。

## 下一步

普通 Point Job 的有限值消费已恢复，下一主线是 Tether / Angle / TriangleBending / Motion / SelfCollision 的实际约束消费与真实 list/proxy/Team 生产，之后接入可回退 C# 候选后端并测 MMD/解包动作、reset、暂停/seek及骨骼输出。各未实现算子不默认填零或 no-op。完整门禁见 [当前缺口](../official-physics-animator-buffer-20261003/PROGRESS.md)。
