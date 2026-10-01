# 提弗洛斯官方物理回源核查（2026-10-01）

状态（2026-10-02 续接）：**角色级配置与 prefab 交叉核查、离线完整导入均通过；尚未恢复官方求解、实例化/更新调用链。没有替换现有预览物理。**

用户要求优先查解包能否识别技术方案。本轮因此暂缓通用 XPBD 升级，先进行只读回源。此前检查 AvatarTemplet / 加权模型，不能推出 AvatarMesh 没有物理配置。本轮发现完整 AvatarMesh **Dump**，且从原始 bundle 重新导出，验证不是其他 agent 写入的推测。

## 1. 可复核的输入与结果

所有路径相对游戏根目录，除另有说明。原游戏文件、模型、场景、材质、渲染/湿身/阴影/MMD 代码均未修改。

| 输入 | SHA256 |
| --- | --- |
| `EndfieldUnpacker/DecryptOutput/Bundles/Windows/main/5edb0b7683b0a5e84f6602a3.ab`（AvatarMesh） | `0893832733d59a917ac20bc91eeb7da3f6a09aa8d206045eba7dbc914c7cb059` |
| `EndfieldUnpacker/_typhoea_avatar_dump/MonoBehaviour/data_npc_avatarmesh_typhoea.txt` | `71d802df5a73af0e15ad4eabc762b3544c58cadfdb58d98ea259891879d17be4` |
| `EndfieldUnpacker/DecryptOutput/Bundles/Windows/main/f96b038ea799224659a99f83.ab`（Characters prefab） | `094c05de7add093188e0a565c9a4b680a70e3cb396f9c466308365c4b6c611c4` |
| `GameAssembly.dll` | `c24495e51b406f03b03890c4788ee618ae022c991405be5d5b8b787cb775ae89` |
| `UnityPlayer.dll` | `bee7be52370adddd67ba61e4937ca51b7f272656841d187e95e505496da798d1` |
| `Endfield_Data/il2cpp_data/Metadata/global-metadata.dat` | `0076743397acadf03d3b0064343a963c7c88863b8160526d397e4b3efb96f02e` |

本机生成证据目录：`D:/EndfieldTechLib/notes/official-physics-fingerprint-20261001-01/`。原始游戏资产只在本机留存，不随这份报告发布。

结果：

- AvatarMesh 重新导出的 Dump 与历史 Dump **原始字节 SHA256 完全一致**（246704 bytes）。
- AvatarMesh 的 `boneClothItems`（源第 2023 行）数组为 11，全部 `clothType=1`。
- Characters prefab 导出 48 个 MonoBehaviour，含 11 个具有 `ClothSerializeData serializeData` 的物理组件；这些组件的 `m_Enabled=1`，对应的 11 个 `MBC_Typhoea_*` GameObject 也全部 `m_IsActive=True`。
- 11 组各自的 `rootBones` PathID 序列在 AvatarMesh 与 prefab 中唯一匹配；不能只凭名称猜对应关系。
- 11 组**完整 ClothSerializeData 子树**逐文本一致。比较只移除 3 层缩进差异和 `m_FileID` 行：AvatarMesh 外部引用为 fileID 2，而 prefab 内部引用为 fileID 0；PathID、数值、曲线和其他字段保留。不是只比较摘要或重力。
- 11 个 prefab 物理组件共用 MonoScript 引用 `fileID=1 / pathID=-4499696877219864329`；字段结构与现有 metadata 清单的 `BeyondDynamicBone.BeyondBoneCloth` 对应。**该 MonoScript 所在外部文件及类名仍需最终解析确认**。
- 同一 prefab 中另有 25 个共用脚本引用 `-8854559673020325403` 的胶囊形组件，带 center、size、direction、reverseDirection、radiusSeparation、alignedOnCenter。不能把它们误作 Unity CapsuleCollider 的 height/radius，不能假定 25 个全部被每组使用。

## 2. 角色级参数索引

名字省略 `MBC_Typhoea_`。节点数是 `selectionData.positions` 数组长度，**不是可动骨数/加权骨数**；其中可能含固定、忽略节点。表中的 damping/radius 是序列化基值，`useCurve=1` 时必须连同原曲线解释，不能当统一常数。重力是该系统参数，不直接等同于现有 UniVRM 风格的 `gravityPower`。

| 组 | Dump 起始行 | prefab MonoBehaviour 文件编号 | 节点数 | gravity | damping 基值/曲线 | radius 基值/曲线 |
| --- | --- | --- | --- | --- | --- | --- |
| Hair_Front_Bangs_Short | 2028 | 81 | 15 | 5 | 0.05 / 0 | 0.006 / 0 |
| Hair_Front_Side_Long | 2597 | 827 | 10 | 6 | 0.1 / 0 | 0.02 / 1 |
| Hair_Back_Ponytail_Long | 3171 | 712 | 38 | 0 | 0.3 / 1 | 0.125 / 1 |
| Hair_Back_Ponytail_Knot | 4092 | 572 | 24 | 0 | 0.2 / 0 | 0.02 / 0 |
| Cloth_Coat | 4721 | 520 | 12 | 5 | 0.05 / 0 | 0.02 / 0 |
| Cloth_Skirt | 5272 | 342 | 37 | 5 | 0.05 / 1 | 0.065 / 1 |
| Cloth_Skirt_Rope | 6089 | 847 | 6 | 8 | 0.01 / 0 | 0.045 / 1 |
| Cloth_Skirt_Bag | 6574 | 375 | 6 | 5 | 0.05 / 0 | 0.031 / 1 |
| Acc_Back_Left_Bag | 7065 | 309 | 4 | 10 | 0.05 / 0 | 0.038 / 1 |
| Acc_Back_Right_Lantern | 7528 | 739 | 4 | 2 | 0.2 / 0 | 0.055 / 1 |
| Tail | 8003 | 961 | 8 | 0 | 0.08 / 1 | 0.02 / 0 |

所有组的 `updateMode=10`、`connectionMode=0`。仅保留原值，**未将它们解释成当前插件枚举或 120Hz**。忽略列表：马尾长发 24、裙摆 6、右灯笼 3，其余 0。不能将前两组左右编号顺序或 `connectionMode=0` 自行解释为闭合裙摆三角网。

具体接触配置亦已找到：

- 刘海引用头部 Magica 胶囊；侧长发引用胸、锁骨、上臂、前臂等 10 个碰撞引用。
- 马尾长发包括前臂、尾链、包/灯笼、裙摆等 8 个引用，马尾结有左右长发第 02 骨的两个引用。不是单纯身体球碰撞。
- 裙摆有左右大腿、骨盆及左右小前臂共 5 个引用；尾链 colliderList 为空，**不应为了“官方一致”擅自添加身体接触**。
- 需要恢复完整角度、距离、三角弯曲、惯性、tether、motion、碰撞、selfCollision、wind、spring 参数，以及 selection 属性、root/ignore/骨骼绑定。存在字段不代表对应约束一定启用。

## 3. 技术方案能确定到哪一层

### 高置信：MagicaCloth 2 结构谱系的骨骼布料集成

原始 metadata 有 `BeyondDynamicBone.dll`、`MagicaCloth.dll`，以及 `BeyondDynamicBone.BeyondBoneCloth`、`ClothSerializeData`、`MagicaManager` 和多类约束/Jobs。角色的 11 组 `clothType=1`、根骨、selection、曲线与碰撞绑定，将证据从“游戏带有某库”推进到“此角色确有相应配置和已启用 prefab 组件”。

与作者公开的 [ClothSerializeData API](https://magicasoft.jp/en/mc2_api_clothserializedata/) 多字段结构高度对应；其 `BoneCloth=1`。这是**技术谱系推断**，不是鹰角正式披露，尚不能断言标准上游版插件、精确版本或数值求解器完全未修改。

作者在 [2023-03-30 的公开回复（193/195）](https://discussions.unity.com/t/released-magicacloth2-hybrid-cloth-simulation/908244?page=10) 描述上游为修改过的 PBD，并表示当时尚未采用 XPBD。这个带日期的陈述只能解释上游当时的算法家族，**不能证明本地鹰角分支具体公式**。因此现在不能把 XPBD 定为“官方物理”。

### 独立线索：鹰角 GPU Cloth 系统

`UnityPlayer.dll` / `GameAssembly.dll` 有 `UnityEngine.HyperGryph.HGGpuClothManagerV2`，包括 Setup、节点/骨架/MetaData buffer、风方向、ShouldStep、角色位置等入口。metadata 有 `HG.Rendering.Runtime.GpuClothSimulationPassConstructor` 及 dispatch/upload compute 句柄。

解包 shader：`EndfieldUnpacker/ShiyumeAssets/sm_153/AllShader_1.5.3/Assets/packages/com.hg.render-pipelines/runtime/shaders/cloth/clothtrishader.shader` 第 126、144–149 行：读取 `_TriIndexBuffer`，用节点 **stride 192 / offset 96** 的 xyz 进行 VP 投影，输出固定灰色。相邻 `clothlineshader.shader` 也读取这些数据。

这证明 GPU 布料数据/显示通路存在；这两段 vertex/fragment 是布料数据的可视化，**不是求解 compute 源码，也未证明提弗洛斯由它计算**。不要将它与 Magica 系统混为一条，也不要将 PhysX/NvCloth 通用符号当此角色的求解器证据。

## 4. 为什么此前导出容易漏掉

`--export_type JSON` 的 AvatarMesh 结果仅 331 bytes，只保留 MonoBehaviour 头、名字和 script 引用；没有 boneClothItems。历史同名 JSON 亦如此。**不完整 JSON 不是原资产没有这些字段**。`--export_type Dump` 则完整保留角色配置，已重新导出复核。

两个 prefab 不能混用：

- `3111ae7c1d13cce07475731f.ab`：`.../postmodels/npc/chr_0034_typhoea_postmodel.prefab`；本轮导出只见 5 个 MonoBehaviour，不带上述 11 组。
- `f96b038ea799224659a99f83.ab`：`.../postmodels/characters/chr_0034_typhoea_postmodel.prefab`；48 个 MonoBehaviour，带上述 11 组和物理碰撞组件。

NPC prefab 的 `HGCapsuleShadowContainer` 是**阴影胶囊**，不能当头发/衣服物理碰撞。AvatarTemplet 的 gameplay capsule 也不是这些布料接触组件。

## 5. 本机复核入口

使用现有 `EndfieldUnpacker/AnimeStudio-net10/AnimeStudio.CLI.exe`，不启动游戏，不注入。新建输出目录，不覆盖已保留证据：

```powershell
# 在游戏根目录运行；$out 设为新建的审计输出目录。
& './EndfieldUnpacker/AnimeStudio-net10/AnimeStudio.CLI.exe' `
  './EndfieldUnpacker/DecryptOutput/Bundles/Windows/main/5edb0b7683b0a5e84f6602a3.ab' `
  ($out + '/avatar-mesh-dump') --game ArknightsEndfield --map_op None `
  --types MonoBehaviour --names '^data_npc_avatarmesh_typhoea$' `
  --export_type Dump --group_assets ByContainer --silent

& './EndfieldUnpacker/AnimeStudio-net10/AnimeStudio.CLI.exe' `
  './EndfieldUnpacker/DecryptOutput/Bundles/Windows/main/f96b038ea799224659a99f83.ab' `
  ($out + '/character-postmodel-dump') --game ArknightsEndfield --map_op None `
  --types MonoBehaviour --types Transform --types GameObject `
  --export_type Dump --group_assets ByType --silent
```

本次 Characters 输出 555 GameObject、556 Transform、48 MonoBehaviour；导出器报告 1159 导出、1 skipped，**不是无缺失完整 prefab 认证**。48 项 MonoBehaviour AssetMap 单独导出于本机 `character-map/character_map.json`。完整原始配置在 AvatarMesh Dump 和上述 11 个 MonoBehaviour 文件里。

## 6. 升级方向与剩余门禁

1. 先建立**不损失原值**的配置导入：11 组、完整曲线及切线、selection 属性、忽略列表、原始 PPtr。64 位 PathID 用整数/字符串，禁止浮点转换。JSON exporter 已漏字段，不能继续依赖那份 331-byte JSON。
2. 解析 MonoScript 外部文件及角色 prefab 的真实 Transform、碰撞组件、父级空间。原 prefab 已含未加权末端等 GameObject/Transform；这提供恢复真实末端的入口，但未完成 PathID→名字→rest 对应前仍不猜。selection.positions 不直接作为 bone localPosition。
3. 追 `GetBoneClothItems`、`BeyondBoneClothPart`、`CharacterAnimationBlackboard._UpdateMagicaCloth`、`ScriptAnimationJobSyncManager.BeforeMagicaClothDelegate`、Reset/SoftReset、动画 `clothResetOption/dynamicLink`，确认构建、启用、时钟、动画叠加与写回顺序。静态 enabled 不等于捕获帧实际运行；不能声称官方频率已恢复。
4. 此后优先评估**合法授权的 MagicaCloth 2** 是否能按这些原始配置接入。商业资产源码不可提交公开仓库；不能因游戏包含库名而视为获得插件授权，也不会自动购买。需要兼容差异审计，而非把最新插件当官方同版本。
5. 若上游不可用或差异过大，独立实现已确认的约束和参数语义，明确“近似实现”。XPBD/SPCR/UniVRM 只能是候选工程方法，不再作为缺乏回源时默认的官方方案。保持当前替代预览作为可关的基线，不同时双重驱动骨骼。
6. 实装才做 TDD/Unity 回归：配置丢失拒绝、PPtr 精确解析、root/ignore/selection 对应、真实末端、胶囊非等半径/方向、动画→求解→写回、重置/倒拖/预览导出一致、关掉恢复。保留湿身和自阴影回归；不采用逐像素官方截图调参。

## 7. 已实现：严格离线导入与自动校验

`Tools/export_official_cloth_config.py` 与 `Tools/tests/test_export_official_cloth_config.py` 已实现。不是 Unity runtime preset，不自动改骨架、场景、插件或当前求解器。

- 按 Dump 的实际缩进/数组语法解析，拒绝重复字段、跳层、数组长度/索引错误、未知标量类型、NaN/Infinity 和整数越界；不补默认值。
- 保留每组完整 boneClothData、selectionData、名字/忽略/碰撞列表；还保留 prefab 完整组件（含 serializeData2 / prebuild）及原始标量类型、拼写、路径、源行号。
- `SInt64` PathID 用 Python 整数解析、JSON 整数输出，另保留原始十进制文本。后续 C#/JS 导入必须显式使用 Int64/BigInt/原始字符串，不能经过 double/JavaScript Number。数值相等不代表类型相同，已单独检查浮点伪装整数引用。
- 11 组 rootBones 序列分别唯一匹配到 prefab；完整参数和 selection 不仅比数值，还比较标量类型和原始拼写。只允许已核实的外部 fileID=2 与本地 fileID=0 差异。
- 输出采用 exclusive-create，不覆盖旧文件；所有输入带 SHA256。无新运行时依赖、联网调用或游戏进程操作。

本机最终产物：`D:/EndfieldTechLib/notes/official-physics-fingerprint-20261001-01/official-cloth-config-04.json`，26627663 bytes，SHA256 `ce377a025cc16e68a0382e92d73b0b47c82641550f79f58846dcc68af4ad9b3d`。11 组、164 个 selection positions、4074 个 AvatarMesh 标量记录；11 份完整 prefab 组件。它包含原始游戏配置，只留本机，不发布到 GitHub。03/04 两次独立导出 hash 相同。

```powershell
# 在 FractalMiner 根目录；输出名字必须尚不存在。
py -3.12 Tools/export_official_cloth_config.py `
  --avatar '../EndfieldUnpacker/_typhoea_avatar_dump/MonoBehaviour/data_npc_avatarmesh_typhoea.txt' `
  --prefab-dir 'D:/EndfieldTechLib/notes/official-physics-fingerprint-20261001-01/character-postmodel-dump/MonoBehaviour' `
  --output 'D:/EndfieldTechLib/notes/official-physics-fingerprint-20261001-01/official-cloth-config-next.json'
```

测试先行的失败已实际观察：实现前模块不存在；真实 prebuild 遇 UInt16 不支持后补越界测试；字段 float→int 同值及 m_FileID int→float 同值各先红后修。未以删字段或放宽比对来绕过。

最终验证：Python **483 passed / 3 历史 skipped / 114 subtests**，2 条已有 Pillow 弃用警告；新增工具 9 个测试函数/34 个子测试，覆盖率（含分支）**88.93%**；Ruff/Pyright 通过，临时测试工具环境 pip-audit 无已知漏洞。Unity/C#/shader 本轮未改，未重跑 Unity，不把历史 752 项物理门禁冒充新官方物理验收。

## 8. 新找到的真实末端与续接点

额外导出 GameObject AssetMap 到本机 `character-transform-map/transform_map.json`，将 Transform 的 m_GameObject PathID 与 GameObject 名对应，已看到以下此前加权模型里缺失的原始局部变换：

| 骨名 | Characters prefab Transform 文件编号 | 原始 localPosition.x |
| --- | --- | --- |
| tail_M_stone_a_08_jnt | 1185 | -0.1757781 |
| hair_L_base_a_07_jnt | 430 | -0.1447141 |
| hair_R_base_a_07_jnt | 702 | -0.1447144 |
| cloth_L_coat_a_02_jnt | 421 | -0.0585289 |
| skirt_base_M_a_04_jnt | 671 | -0.09322456 |
| cloth_L_cuff_b_03_jnt | 23 | -0.09812435 |

这六项 quaternion 都为 (0,0,0,1)，y/z 原始非零小值仍在对应文件，不在表中省略后拿去赋零。这里只确认数据存在且名字引用对应，**尚未完成全部父链、缩放、坐标系、当前 recovered skeleton 的兼容门禁**，没有把这些 x 当世界骨长，也没有覆盖当前模型。

接续优先级：完成 §6 的 Transform/碰撞引用与 MonoScript 解析 → 11 组完整拓扑/曲线语义 → 官方动画/物理更新顺序与时钟 → 合法上游或独立近似求解路线。保留当前预览作为基线，不能双重写入骨骼。

本轮只提交这个工具、合成测试、报告与上一轮文档导航。官方原文件、模型、场景、湿身、阴影、渲染/MMD代码、主 HEAD 和用户暂存索引保持不变。独立记录分支父提交为 `5e9f5a1`；不存在“官方物理已完美复现”的结论。
