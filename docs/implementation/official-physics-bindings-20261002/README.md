# 提弗洛斯官方物理：原始 Transform 与碰撞引用核查

日期：2026-10-02。接续 `official-physics-fingerprint-20261001`。

本轮完成的是**离线绑定数据恢复**，不是官方物理求解器复现，也没有升级正在运行的预览物理。未修改角色模型、场景、光照、湿身、自阴影、MMD 或 Unity 运行代码；没有进行逐像素调参。

## 已通过的检查

- 原始 Characters prefab 的 556 个 GameObject、556 个 Transform、48 个 MonoBehaviour 均按 `(serialized file, signed 64-bit PathID)` 导出，共 1160 份原始 Dump。
- 每个 GameObject/Transform 的所属关系、父子双向引用、无环性、局部位置/四元数/缩放通过校验。保留原始标量类型和字符串，不做轴向转换。
- 11 组 cloth component 与 AvatarMesh 参数匹配；31 个根骨引用、33 个忽略骨骼引用、35 个碰撞引用全部解析。35 个引用去重后是 25 个组件：23 个 capsule 字段形状、2 个仅 `center + size` 形状。
- 每组原始根骨、忽略骨骼、碰撞挂点名称列表，均与相应 PPtr 按原始顺序吻合；组件启用，引用节点及其祖先均 active。
- AvatarMesh 的 external fileID=2 实际指向 `CAB-f859e4fe0ae8ddbe9e3aac716c534e11`，与该 Characters prefab 的 serialized-file 名称精确一致。不是仅凭碰巧相等的 PathID 跨文件拼接。
- 所有关键物理对象的原始类型树读取告警为 0。告警不能被普通解析成功掩盖。

| 官方组（省略 MBC_Typhoea_） | 根骨引用 | 忽略引用 | 碰撞引用 |
| --- | ---: | ---: | ---: |
| Hair_Front_Bangs_Short | 5 | 0 | 1 |
| Hair_Front_Side_Long | 2 | 0 | 10 |
| Hair_Back_Ponytail_Long | 2 | 24 | 8 |
| Hair_Back_Ponytail_Knot | 2 | 0 | 2 |
| Cloth_Coat | 6 | 0 | 1 |
| Cloth_Skirt | 7 | 6 | 5 |
| Cloth_Skirt_Rope | 2 | 0 | 2 |
| Cloth_Skirt_Bag | 2 | 0 | 3 |
| Acc_Back_Left_Bag | 1 | 0 | 2 |
| Acc_Back_Right_Lantern | 1 | 3 | 1 |
| Tail | 1 | 0 | 0 |

原 prefab 中 capsule 字段组件共有 25 个；上表只引用其中 23 个，另引用 2 个 `size` 字段组件。**“源文件有某组件”不等于“所有 cloth 都该使用它”**，不能把未引用的碰撞体强行加入。

## 两个必须记住的绑定陷阱

### 同名骨骼不能用名字作为主键

官方 prefab 有两个都叫 `skirt_base_R_c_03_jnt` 的 GameObject，实际分别处于左右父链：

| Transform PathID | 最后几级父链 |
| --- | --- |
| -1237160793539391697 | skirt_base_R_c_01_jnt / skirt_base_R_c_02_jnt / skirt_base_R_c_03_jnt |
| -5985668592349786321 | skirt_base_L_c_01_jnt / skirt_base_L_c_02_jnt / skirt_base_R_c_03_jnt |

原 CLI 按 GameObject 名称输出文件，两个对象覆盖同一文件名，实际只得到 555 个 GameObject Dump。新的 ID 限定输出保留全部 556 个。

当前已恢复模型却使用唯一的 `skirt_base_L_c_03_jnt` 和 `skirt_base_R_c_03_jnt`；前者在原 prefab 中没有同名节点。`Armature` 也不是原 prefab 节点。这不意味着立即重命名/重建模型：现有模型是另一套已验证恢复结构。下一阶段必须建立**有父链证据的别名映射**，不能用全局名字查找、自动把左链映射到右链，或破坏已通过的姿态。

### 原始 collider 不是普通 Unity CapsuleCollider 参数

一些 collider 挂在独立 Magica 命名节点，另一些直接挂在饰品骨骼上。

例如 `acc_L_beltBag_a_03_jnt` 上的组件 PathID=6771154128644165423，原始 `center=(-0.05,0,0.01)`、`size=(0.078,0,0)`；其脚本 PPtr 与 capsule 字段组件不同。这里保存的是 `size`，不是名为 `radius` 的标量。

输出只标记 `capsule_fields` / `size_only_fields`，所有 `class_resolved=false`。外部 MonoScript 尚未加载确认，不能把字段指纹冒充完整类名，更不能擅自规定 size 各分量的官方数学意义。

## 工具与本地真值位置

仓库新增：

- `Tools/EndfieldPhysicsProbe/EndfieldPhysicsProbe.csproj`、`SerializedMetadata.cs`：复用已有 SceneProbe loader，只扩展 ID 限定原始元数据输出和逐对象读取告警记录。
- `Tools/export_official_physics_bindings.py`：复用上一轮严格 Dump parser，校验关系、参数、启用状态和引用顺序；输出保留完整 raw objects、局部 TRS、祖先 ID、原始参数、外部文件表及 SHA256。
- `Tools/tests/test_export_official_physics_bindings.py`：同名节点、超过 JavaScript 安全整数范围的 ID、无环/双向关系、损坏引用、关键读取告警、文件路径越界、覆盖保护、实际文件流程等测试。

生成的原始游戏数据只保留本地，不推送 GitHub：

```text
D:/EndfieldTechLib/notes/official-physics-bindings-20261002-01/
  prefab-id-dump-02/scene_manifest.json
  prefab-id-dump-02/metadata/                  # 全部 1160 个对象
  prefab-id-dump-02/metadata-read-warnings.json
  avatar-id-dump/scene_manifest.json           # 原 external fileID=2 证据
  official-physics-bindings-03.json            # 本轮最终数据
  original-main-index.bin                     # 用户原主索引备份
```

最终数据：32,988,805 字节，SHA256=`8dad33d1dcbeee882233bb8803b7141b3d2c3817aeed23a619f5c0eeb8fbe3c8`。

读取告警只有一项：MonoBehaviour PathID=7923281468339408687，`read 336 bytes but expected 448 bytes`。其内容是动画事件 handlers/managed references，不属于上述 cloth/collider，也不属于 Transform/GameObject。它作为 `unvalidated_metadata_warnings` 保留，**没有宣布这个组件完整恢复或官方事件时序已核实**。任一关键物理对象出现同类告警，导出器直接停止验收。

## 复现命令

只针对已经解出的本地 AssetBundle；不启动游戏，不注入进程。

```powershell
cd 'A:/Hypergryph Launcher/games/Arknights Endfield'
dotnet build 'FractalMiner/Tools/EndfieldPhysicsProbe/EndfieldPhysicsProbe.csproj' `
  '-p:SceneProbeRoot=D:/EndfieldTechLib/04-engine-data/Endfield-map-extractor/dotnet/EndfieldSceneProbe' `
  '-p:AnimeStudioBin=A:/Hypergryph Launcher/games/Arknights Endfield/EndfieldUnpacker/AnimeStudio-net10/bin' `
  --output 'D:/EndfieldTechLib/notes/official-physics-bindings-20261002-01/probe-bin'
# 首次在新目录运行时，需将本地 AnimeStudio bin 的运行依赖 DLL 复制到 probe-bin。
dotnet 'D:/EndfieldTechLib/notes/official-physics-bindings-20261002-01/probe-bin/EndfieldPhysicsProbe.dll' `
  'EndfieldUnpacker/DecryptOutput/Bundles/Windows/main/f96b038ea799224659a99f83.ab' `
  'D:/EndfieldTechLib/notes/official-physics-bindings-20261002-01/prefab-id-dump-NEW' `
  --manifest-only --dump-metadata
python 'FractalMiner/Tools/export_official_physics_bindings.py' `
  --scene-manifest 'D:/EndfieldTechLib/notes/official-physics-bindings-20261002-01/prefab-id-dump-NEW/scene_manifest.json' `
  --cloth-manifest 'D:/EndfieldTechLib/notes/official-physics-fingerprint-20261001-01/official-cloth-config-04.json' `
  --output 'D:/EndfieldTechLib/notes/official-physics-bindings-20261002-01/official-physics-bindings-NEW.json'
```

输出文件/目录必须是新的；工具拒绝覆盖。复用的源代码与 DLL SHA256 见本目录 `verification.json`，这些外部依赖未复制进 Git。

## 验收与下一步

本轮 Python 全套：508 passed、3 项历史 skip、114 subtests passed、2 项已有 Pillow 弃用告警。新增 25 项测试，工具含分支覆盖率 87.73%；Ruff、Pyright、临时工具环境 pip-audit 通过。C# build 0 错误、0 警告。Unity 未重跑：本轮没有 Unity 代码或资产修改。

接下来按顺序做，不能跨过身份/坐标门禁直接把原始参数塞进当前 Verlet：

1. 以原 Transform ID + 父链为依据，建立原 prefab 到当前角色骨架的唯一映射，显式保留左裙链别名与额外根节点处理。核对现有加权 bindpose 与原始局部 TRS 的坐标关系；不要重写已验证的捕获姿态或 MMD 初始姿态。
2. 解析外部 MonoScript 真实类名、`size/direction/reverseDirection/radiusSeparation/alignedOnCenter` 的语义，以及原始 selection/ignore 的节点顺序与属性含义。
3. 核查官方更新顺序、更新模式、步长、约束结构和初始化流程。原 `updateMode=10` 仍是未经证实的数值；**不能据此声称官方物理固定 120Hz**。当前 120Hz 是现有预览的确定性设计。
4. 通过上述门禁后，独立、可切回地接入官方配置的物理实现/最接近实现。未解析约束或购买授权缺口要明确记录，不能把已有 MIT Verlet 换参数后称为官方完整求解器。
5. 在静止、转身、下蹲、跳跃、seek、固定步录制和 MMD 动作下验证骨长、碰撞、复位、更新顺序与渲染/阴影联动。按用户要求以结构、逻辑和方法正确性验收，不逐像素调参。
