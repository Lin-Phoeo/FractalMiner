# 官方物理：真实参考ID到baseline、局部姿态及根深度

日期：2026-10-11。接续[Line代理前处理](../official-physics-proxy-preprocess-20261011/README.md)，新增两个生产/导出模块，将已经封印的隔离Unity参考输入接到已恢复的数学模块。**本轮关闭这一条有限输入生产链，不代表完整官方实时物理已接入Unity。** 原舞台、渲染、湿身、阴影和预览物理均未修改。

## 实际产物与边界

输入为两个真实Unity getter参考状态：`serialized-rest`、`rigid-reference-frame`。它们来自原序列化556个Transform重建树，不是游戏运行时或主舞台恢复角色。每状态11组、140个skin槽，另有11个render-only快照槽。

`Tools/official_physics_baseline_inputs.py`复用已有参考，不重写四元数、遍历或深度算法；`Tools/export_official_physics_baseline_inputs.py`检查两份SHA256封印、getter嵌套来源、状态/组顺序与身份、源槽顺序及属性/Transform flags后，以独占方式导出：

`runtime Int32 IDs → skin父索引/有序根 → 有序子表 → baseline四数组 → 局部位置/旋转`，另以**原始代理位置**生成全顶点root/length/depth。

本地完整结果：`D:/EndfieldTechLib/notes/official-physics-baseline-production-20261011-01/eleven-baselines-01.json`，SHA256 `9ca9f1355ae6046ba55cc2f59f51bfc739a274c30037b1d124113e6602a50199`。原角色输入、原二进制、完整指令及参考骨数据仅保留本地，Git提交代码、说明与验证摘要。

| 每个状态 | 结果 |
| --- | --- |
| 物理顶点 / snapshot含render | 140 / 151 |
| 有父边 / 原序root列表项 | 109 / 31 |
| baseline / data槽 | 37 / 126 |
| 参与baseline的有父 / 无父槽 | 106 / 20 |
| 未参与baseline的局部输出槽 | 14，保持清零，旋转也是四个零 |
| root/depth求值域 | 全部140顶点，不按baseline筛选 |

37条baseline不等于31个输入root：非Move候选搜索可以在子树中产生多个baseline。不得按名称或根数量补齐、排序、合并。实际两态没有重复root或重复baseline槽；通用参考仍保留原根重复语义，未宣称并行重复写入安全。

## 三项接入规则：不以stock行为替代原代码

1. **只用skin前缀。** 导入IDs/parents/snapshots的最后一项是render Transform，不能加入proxy父子图。运行时有符号Int32 instance ID不是原PPtr的Int64 path ID。外部父ID映射为-1；缺失root拒绝；属性和Transform flags继续分别保留140/151槽域。
2. **子表顺序有条件地成立。** 原`CreateTransformBaseLine`创建空容器、传入容量`3*n`，清空bucket/next/free-list并将allocatedLength置0，再按顶点升序串行插入非负parent。至多n次Add，不触发扩容；同parent按链首插入逆序枚举。后续LIFO按原顺序消费。结论限成功fresh构造路径，不扩展到删除/复用/rehash；调用者仍须显式确认fresh参考前提。
3. **局部姿态与深度不能混用位置或初值。** `CreateBaseLinePose`的float3/quaternion构造都传`ClearMemory=1`；未访问槽保持zero quaternion，只有被访问且parent<0的槽写identity。原局部姿态Job没有attributes字段，不引入stock `ZeroDistance`修改。root/depth读取proxy `localPositions`，不是本Job输出`vertexLocalPositions`；由子向上Single累加，一个最大值归一化该组全部顶点，最大值不超过float32(1e-8)时保留初始零depth。

fresh空导入、空runtime覆盖、未减点/未改序、零三角形Line、None对齐仍为明确参考路线，**未观测游戏实时的这些前提**。None泛型Fill实际写入、generic构造TypeInfo和实时allocator/Job反射调度仍有独立证据缺口，不能因本轮通过而标成完整生命周期。

## 原始证据与独立验证

原GameAssembly/metadata SHA256沿用封印。两名独立审查者分别审查子表构造和pose/depth字段/初始化；主代理再次打开原文件认证六项方法身份、35个完整exact unwind/CHAININFO片段共5840字节，并复核baseline原11332字节的11192代码+140跳表字节分区。49个子表锚点、33个pose/depth锚点与MemSet名称契约保留私有证书。没有加载/执行原DLL、启动游戏或注入进程，也没有声称重新完成整个CFG证明。

子表审查用独立链桶结构，22组各检查9种collision mask，共198次匹配键顺序对照通过。第三名审查者不导入生产数学模块，以线性ID查找、链首插入、递归DFS和NumPy独立重算：

- 280个skin槽、74条baseline/252数据槽；父表、有序根、子表、baseline flags/starts/counts/data完全一致。
- 582个length/depth/global-max Float32数值槽逐位一致；这只表示两个有限参考实现一致，不是官方DLL/Burst运行oracle。
- 28个未访问输出为全零；40个访问且无父槽为零位置/identity；212个有父槽通过独立矩阵代数验证，最大位置差`7.28e-8`、旋转矩阵差`1.18e-6`，代数容差`1e-5`。这不是逐像素对照，也不是任意四元数原生逐位保证。
- 既有属性/flags/源槽顺序全部保留，render-only未混入；审查新模块未发现正确性问题。

TDD保留缺模块RED。新增44项专项通过；完整**4073 passed + 114 subtests**，3个历史skip、2个历史Pillow告警。新增两模块92语句/28分支覆盖100%。Ruff、Black、Pyright、compileall通过；实际工具环境48依赖、0已知漏洞。首轮lint及测试fixture类型检查失败记录保留，修复后重新全量验证。主HEAD、主index与七个受保护运行文件校验不变。

## 复现与下一步

在FractalMiner目录使用已有私有封印输入：

```powershell
uv run --python 3.13 --no-project python -B Tools/export_official_physics_baseline_inputs.py `
  --imports D:/EndfieldTechLib/notes/official-physics-getter-production-20261011-01/eleven-imports-01.json `
  --imports-sha256 3b9e2546c12fbe7b2c21e4cad6acf9faba8c1df8b258dad73ef92c12dcde9af7 `
  --frames D:/EndfieldTechLib/notes/official-physics-proxy-preprocess-20261011-01/eleven-frames-01.json `
  --frames-sha256 9d4e62062d3352264002c4ccdc20fe292a78515c6ed9fd18f1b1d0e0e623e1ec `
  --output D:/EndfieldTechLib/notes/official-physics-baseline-production-20261011-01/eleven-baselines-replay.json `
  --fresh-serial-no-resize --cleared-output-buffers
```

输出必须新路径，拒绝覆盖。参考脚本不会发布NativeArray、创建Team或启动Unity。

下一单元沿此真实槽位生成所需Line拓扑/约束cache与work-list，再接Team/particle初始化、原子步依赖和骨骼唯一writer，最后进入可回退Unity候选后端与MMD/解包动作动态测试。先补普通11组实际开启的分支；零三角形/关闭SelfCollision仅在明确前提下允许跳过，不把未知算子静默no-op。本轮没有新可见物理效果，不能给官方后端已完成的结论或可靠完工百分比。
