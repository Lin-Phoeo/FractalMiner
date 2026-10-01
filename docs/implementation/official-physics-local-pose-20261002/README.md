# 官方物理接入前：局部姿态与碰撞挂接计划

日期：2026-10-02。接续 [骨架身份与整体空间核查](../official-physics-mapping-20261002/README.md)。本轮只有离线工具、测试与文档修改，没有改动模型、场景、物理预览、MMD、湿身、自阴影或渲染。验收依据是原始数据与矩阵关系，不是逐像素比较。

## 新结论一：模型整合数据没有偏离已有原始导出

对照原 AvatarMesh JSON 和全部 17 份原 Mesh JSON，以下检查通过：

- 481 个模型节点的名字/父索引与 Avatar 的 `bonePathsStr/bonePaths` 一致；空名节点按既有约定命名为 `Armature`。
- 486 个 palette 索引按原 Avatar 完整路径的 CRC32 回查，逐项与原 `m_BoneNameHashes` 一致，没有用全局骨名近似匹配。
- 全部 486 份 bindpose 的 16 个标量，与原 `m_BindPose.Mij` 按既有整合脚本的行序展开结果逐值相等。不是仅比较若干小数或放宽阈值。

这里认证的是**当前模型与既有原始导出的整合一致性**，不是对最初 AnimeStudio 二进制读取器的独立认证，也不代表 prefab authored pose 与 mesh bind pose 必须相同。没有运行旧 `_build_typhoea_model_data.py`：它会覆盖当前模型。

矩阵层次必须分开：原 JSON 的 `Mij` 字段排列 → 整合脚本逐行 flatten → 现有 C# `ReadMatrix` 按列填充。新工具复核这个实际链条，没有“修正”成另一种矩阵排列。

## 新结论二：大部分局部空间一致，差异主要在旋转

上轮整体门禁失败，不能据此直接认定模型坏了。新增比较消除统一左乘基准：

```text
原区间矩阵 = inverse(S_ancestor) * S_bone
绑定区间矩阵 = inverse(W_ancestor) * W_bone
W_bone = inverse(存储的 bindpose)
```

祖先选最近有 bindpose 的模型祖先。两个世界矩阵同受任意统一左乘基准时，这个基准在区间计算中抵消。没有 bindpose 的中间辅助骨不会被假定为 identity；它们的索引明确留在报告中。

| 局部诊断 | 实测 |
| --- | ---: |
| 可比较区间 | 304 |
| 直接父子 / 跨未加权辅助节点 | 222 / 82 |
| 同时满足平移与线性矩阵 ≤1e-4 | 259 |
| 不满足门禁 | 45（直接 43，跨辅助节点 2） |
| 平移差 >1e-4 的区间 | 0 |
| 最大平移差 | 5.90421748797062e-5（源单位） |
| 最大线性矩阵元素差 | 0.04333195228805572 |
| 没有加权祖先的 palette 根 | 模型索引 3，Bip001_Pelvis |

较大的差异在左右锁骨、上臂、前臂及手腕旋转。最大线性差发生在右前臂，左前臂也有近似对应差异。上一轮袖链的较大世界位置偏差，并不等于袖子局部位置被挪动：父骨旋转差会传播成后代的世界位置差。

这已排除“仅补一个整体换轴即可闭合”和“模型整合时改坏 palette/bindpose”两个解释。**差异的具体生成机制仍未证实**：可能涉及 authored 初始姿态、局部轴约定或更早导入路径。跨辅助节点的两项只能定位到区间，不能冒称已锁定其中某一个辅助关节。

未修改验收容差；这些是物理接入的空间诊断，不是判定现有渲染观感的像素误差。

## 新结论三：18 个碰撞挂点需要保留额外节点

新增报告的 `physics_binding_plan` 已把原引用按唯一 ID 转成模型索引：

- 11 组、31 个根骨引用、33 个 ignore 引用全部对应当前模型。
- 31 个根骨均有当前 bindpose；没有靠 identity 猜测根骨初始空间。
- 25 个被引用碰撞组件全部找到现有模型上的最近祖先。
- 其中 7 个直接挂在已存在的模型节点，18 个挂在独立额外节点上；这 18 个各有一级原局部 TRS。

计划保存每个 collider 的组件 ID、原 Transform ID、目标祖先模型索引、额外节点的完整局部位置/四元数/缩放，以及相乘后的祖先局部矩阵。链有环、没有映射祖先、根/ignore 不可解析时停止。

例：头部 collider 的目标祖先是模型索引 8（Bip001_Head），但还必须保留原 `Magica Capsule Collider (Bip001_Head)` 节点的局部 TRS。不能看到名字含 Head 就直接把碰撞组件加到头骨并丢掉这层变换。

当前计划明确为 `runtime_ready=false`。它不是碰撞几何转换，仍保留原 `class_resolved=false`；没有把原 `size/direction/reverseDirection/radiusSeparation/alignedOnCenter` 凭名称替换成 Unity CapsuleCollider 参数。目标局部轴等价性还需验证，尤其要关注本轮已定位的手臂旋转差。

## 可复现产物与用法

唯一主工具仍为 `Tools/map_official_physics_skeleton.py`，没有新增平行解析器。新参数 `--avatar` 与 `--raw-mesh-dir` 必须成对给出；未给出时 `source_model_provenance=null`，不能宣称已做源模型验证。

```powershell
cd 'A:/Hypergryph Launcher/games/Arknights Endfield'
python 'FractalMiner/Tools/map_official_physics_skeleton.py' `
  --bindings 'D:/EndfieldTechLib/notes/official-physics-bindings-20261002-01/official-physics-bindings-03.json' `
  --model 'FractalMiner/Assets/Typhoeus/_typhoea_model_data.json' `
  --contract 'FractalMiner/docs/implementation/official-physics-mapping-20261002/bone-aliases.json' `
  --avatar 'EndfieldUnpacker/AnimeStudio-net10/_avatar_test/assets/beyond/dynamicassets/gameplay/npc/avatartemplet/actor/data_npc_avatartemplet_typhoea.json' `
  --raw-mesh-dir 'EndfieldUnpacker/AnimeStudio-net10/_all_meshes/assets/beyond/arts/entity/actor/loli/typhoea/models' `
  --output '<新的报告绝对路径>'
```

输出拒绝覆盖，所有输入与原 Mesh/Avatar 源文件的 SHA256 都保存在新报告。游戏数据仍只留本地：

```text
D:/EndfieldTechLib/notes/official-physics-local-pose-20261002-01/
  skeleton-local-pose-03.json           # 本轮最终；含挂接计划及全部区间矩阵
  skeleton-local-pose-01.json           # 中间诊断，仅供追溯
  skeleton-local-pose-02.json           # 中间诊断，仅供追溯
  mapping-coverage.json
  original-main-index.bin
```

最终报告 789,432 字节，SHA256=`2ac926d1e0bbfc5438d4fc7c97924c5694db1ce19ea099559f56e0a1606ec5cb`。

## 下一阶段：实现前还不能跳过什么

1. 在独立克隆/适配器中验证未加权辅助节点与碰撞挂点恢复，保持原 weighted bindpose 与当前几何不变。现有旧模型构建器对没有 bindpose 的节点用 identity；不能拿这个默认值证明原辅助骨已还原。不要直接重建用户当前场景。
2. 查清 45 段局部旋转差的来源与动画写回的坐标约定，验证挂点随动画的变换。静态源 mount plan 不等于动态行为已正确。
3. 继续解析 prefab 外部 MonoScript 精确身份、定制 collider 数学、selection 与约束数据。上一轮 global asset 声明仍不能代替外部 CAB 的实际 PPtr。
4. 官方更新模式枚举的数值、动画/物理/骨写回顺序、步长和复位仍未核实。已找到本地 `Il2CppDumper-end` 的厂商 29.2 变体及压缩默认整数读取实现，可优先复用；不能直接把 v29 默认值数据当固定 int32 读。该实现尚未在本轮执行验证。
5. 门禁通过后才接可切回的求解链。现有预览没有升级成官方求解器；也没有因上游 Magica API 相似而购买/导入插件或宣称完全等价。

测试策略增加了统一基准抵消、单关节差异定位、跨辅助节点区间、源 palette/bindpose 漂移拒绝、额外挂点与循环/无锚点拒绝、可选源文件完整流程和覆盖保护。使用先测试后实现的方式，不以两个同源错误实现互相吻合作为证明。

后续：[官方更新模式枚举与接口证据](../official-physics-update-mode-20261002/README.md)。本地 metadata 已确认 AnimatorLinkage=10，但原生执行时序、频率和 field type variants 仍待验证；没有改写本页历史门禁或接入官方求解器。
