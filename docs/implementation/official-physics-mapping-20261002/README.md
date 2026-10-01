# 官方物理身份与骨架空间：核查检查点

日期：2026-10-02。接续 [原始绑定恢复](../official-physics-bindings-20261002/README.md)。

本轮只增加离线工具、测试和证据文档。没有修改 Unity 模型、场景、渲染、湿身、自阴影、MMD 或运行中的预览物理；没有逐像素调参。

## 官方是否使用 MagicaCloth 2？

**证据支持 MagicaCloth 2 系的官方定制 `BeyondDynamicBone` 骨骼布料方案，不支持直接认定为未经修改的商店插件。** 精确版本、授权来源、完整求解器等价性均未核实。

证据分层，不能相互冒充：

1. 原 Characters prefab/AvatarMesh：11 组配置，Magica 命名的碰撞节点、selection/ignore、参数曲线和骨骼引用。上一轮已恢复原字段与局部 TRS。
2. 游戏 `Endfield_Data/globalgamemanagers.assets` 的 typed MonoScript 声明：

| PathID（仅属于此 serialized file） | Namespace.ClassName | Assembly |
| --- | --- | --- |
| 10752 | BeyondDynamicBone.BeyondBoneCapsuleCollider | BeyondDynamicBone.dll |
| 13665 | BeyondDynamicBone.BeyondBoneCloth | BeyondDynamicBone.dll |
| 17457 | BeyondDynamicBone.BeyondBoneSphereCollider | BeyondDynamicBone.dll |

   清单读取原始对象表中的 18,472 个 MonoScript，成功生成 typed 对象同样为 18,472；失败读取被省略时，数量门禁会停止输出。PathID 保存为十进制字符串，防止 64-bit ID 被 JavaScript 数字舍入。
3. 本地 IL2CPP 类型清单：`BeyondDynamicBone.ClothUpdateMode` 包含 `Normal/UnityPhysics/Unscaled/AnimatorLinkage`；`BeyondBoneCloth` 还包含 RWBuffer、协变处理等定制接口。此清单没有给出枚举数值或方法实现，不能用字段名证明运行时行为。
4. 上游作者 API 可作为语义对照，但不是官方定制实现的真值：
   - [ClothSerializeData](https://magicasoft.jp/en/mc2_api_clothserializedata/)：上游 `updateMode=10` 是 `AnimatorLinkage`，不是固定 120Hz。官方配置也为 10、枚举名称也匹配，但本地数值和调用时序还需核实。
   - [MagicaCapsuleCollider](https://magicasoft.jp/en/mc2_api_magicacapsulecollider/)：上游 size 为起点半径、终点半径、长度；direction 为轴向，其他标志参与构型。
   - [MagicaSphereCollider](https://magicasoft.jp/en/mc2_api_spherecollider/)：上游球体使用 size.x 表示半径。

### 仍未闭合：prefab 的外部 MonoScript 精确身份

prefab external fileID=1 指向 `CAB-5f527d7b7706baccdad9f794cf46420c`。三类字段形状的脚本 PathID 分别为：

- cloth：`-4499696877219864329`
- capsule fields：`-8854559673020325403`
- size-only fields：`-7738307689003339598`

这些 ID 与上表 global asset 中的正 ID **不是同一个序列化身份**。当前不能把“游戏含该类”升级成“这一 prefab 的 PPtr 已精确指向该类”。上一轮 `class_resolved=false` 保持有效；不能悄悄改成 true。

初次普通 Dump/AssetMap 未读出 stripped type-tree 的 MonoScript，不代表游戏没有这些类。新增 `ScriptInventory.cs` 复用现有 AnimeStudio typed reader，避免该误判。读取器也加载了 Unity 内置资源；结果的 `Source` 字段保留实际文件名。

## 骨架身份映射：PASS

新增 `Tools/map_official_physics_skeleton.py`，只读以下三份输入并生成新报告：

- 上一轮 `official-physics-bindings-03.json`：原节点 ID、父链、局部 TRS。
- 当前 `_typhoea_model_data.json`：模型骨骼与各网格的 bindpose。
- 本目录 `bone-aliases.json`：显式、可审查的锚点和别名契约。

结果：481 个模型节点中，480 个唯一对应原 Transform；1 个 `Armature` 是额外辅助根节点。映射根据父节点身份和节点名递归建立，不用全局名字查找。

左链原文件错误同名节点 `skirt_base_R_c_03_jnt` 明确映射到模型的 `skirt_base_L_c_03_jnt`，source ID 为 `CAB-f859e4fe0ae8ddbe9e3aac716c534e11:-5985668592349786321`。契约同时核对原名和父节点，不能误用右链。辅助根不能有待映射子节点，不能进入加权骨骼 palette；重复 source ID、未使用别名、歧义和循环均拒绝。

## 空间兼容性：不能直接整套注入原始 TRS

这是独立于身份映射的门禁，不是截图误差标准。矩阵读取遵循现有 C# `ReadMatrix` 的实际列填充行为：NumPy `reshape(order="F")`，不能跟随其旧注释误读成行主序。

令 `S_i` 为原 prefab 祖先链累计后的世界矩阵，`Q_i` 为模型存储的 bindpose。检查是否存在统一左乘矩阵 `B`，使 `S_i = B * inverse(Q_i)`；候选矩阵是 `B_i = S_i * Q_i`。这只是静态兼容性诊断，**并不假定 prefab authored pose 必须等于 mesh bind pose**。

| 检查 | 实测 | 结果 |
| --- | --- | --- |
| 17 个网格的 palette 观察数 / 唯一加权骨骼 | 486 / 305 | 输入完整 |
| 跨 palette 重复的骨骼 | 130 | 同 ID 单独核对 |
| 重复 bindpose 最大单元素差 | 1.4000000003733248e-7 | PASS，≤1e-4 |
| 统一左乘基准的最大平移偏差 | 0.042031018650988045（源单位） | FAIL，>1e-4 |
| 统一左乘基准的最大线性矩阵元素偏差 | 0.03838716643125951 | FAIL，>1e-4 |

第一个候选接近绕 X 轴 -90°，但不能因此宣布全骨架都适用同一换轴。最大偏差来自 `cloth_R_UpperArm_c_01_jnt`，两份衣服网格均出现；左右袖链也出现类似偏差。报告保存最差 20 项的完整父链。

重复 palette 一致性排除了“重复骨骼的 bindpose 在不同网格明显不一致”这一解释。尚未区分 authored 初始姿态、每骨局部坐标约定、导入路径等原因；身份映射通过也不证明每骨空间约定正确。**不要重写已验证捕获姿态、MMD 初始姿态，或把所有原始局部 TRS 整套覆盖进去。**

## 复现与证据

本地数据不发布 Git；其长度和 SHA256 在 `verification.json`。最终输出：

```text
D:/EndfieldTechLib/notes/official-physics-mapping-20261002-01/
  global-script-inventory-02.json       # 原声明数与 typed 读取数门禁
  skeleton-map-02.json                 # 身份映射、重复 palette、统一空间门禁
  mapping-coverage.json
  script-probe-bin/                    # ScriptInventory 入口
  default-probe-bin/                   # 原 SceneProbe 默认入口仍可编译
  original-main-index.bin
```

```powershell
cd 'A:/Hypergryph Launcher/games/Arknights Endfield'
dotnet build 'FractalMiner/Tools/EndfieldPhysicsProbe/EndfieldPhysicsProbe.csproj' `
  '-p:SceneProbeRoot=D:/EndfieldTechLib/04-engine-data/Endfield-map-extractor/dotnet/EndfieldSceneProbe' `
  '-p:AnimeStudioBin=A:/Hypergryph Launcher/games/Arknights Endfield/EndfieldUnpacker/AnimeStudio-net10/bin' `
  '-p:StartupObject=ScriptInventory' --output '<新的 probe-bin 绝对路径>'
# 按上一轮说明，将本地 AnimeStudio bin 的运行依赖 DLL 复制到新输出目录。
dotnet '<新的 probe-bin 绝对路径>/EndfieldPhysicsProbe.dll' `
  'Endfield_Data/globalgamemanagers.assets' '<新的 inventory.json 绝对路径>'
python 'FractalMiner/Tools/map_official_physics_skeleton.py' `
  --bindings 'D:/EndfieldTechLib/notes/official-physics-bindings-20261002-01/official-physics-bindings-03.json' `
  --model 'FractalMiner/Assets/Typhoeus/_typhoea_model_data.json' `
  --contract 'FractalMiner/docs/implementation/official-physics-mapping-20261002/bone-aliases.json' `
  --output '<新的 skeleton-map.json 绝对路径>'
```

两种输出均拒绝覆盖。不启动/注入游戏；不需要绕过保护。

## 下一步顺序与禁止误判

1. 解开 prefab 外部脚本 CAB 的身份，核实定制 collider 数学语义、selection/ignore 属性与索引顺序。上游语义只能当候选。
2. 定位上述每骨 authored/bind 差异，验证坐标适配后的根骨、忽略骨、碰撞挂点和局部轴。加权 palette 只覆盖 305 骨，不能用它宣布其余辅助/物理骨空间已通过。
3. 查证官方枚举值、动画求值/物理/骨写回顺序、初始化、复位与 teleport、步长/子步和约束。当前预览的固定 120Hz 与官方更新模式是两件事。
4. 实现独立可切回的适配与求解链，先做静止、转身、下蹲、跳跃、seek 和固定步录制结构测试，再接 MMD。不要把当前简化 Verlet 调参数后叫做完整官方求解器。
5. 若选 MagicaCloth 2 作为可用替代，先确认项目授权与集成兼容性；本轮未购买、未导入该插件，也未承诺替换插件即可等价还原。其他官方 GPU Cloth 的存在不证明本角色就走那条链。

验收：18 个新增测试；全部 Python 测试 526 passed、3 项历史 skip、114 subtests passed、2 项历史 Pillow 弃用告警。新增映射工具含分支覆盖率 89.95%。Ruff/Pyright/pip-audit 通过；两个 C# 入口分别编译 0 错误、0 警告。Unity 未重跑，Unity 文件与主索引保持不变。

后续检查点：[源模型一致性、局部姿态区间与碰撞挂接计划](../official-physics-local-pose-20261002/README.md)。现有模型 palette/bindpose 与已有原始导出精确一致；局部空间差异集中于旋转，18 个额外碰撞挂点已生成离线恢复计划。未修改本页历史门禁结果，也未升级为已接入官方物理。
