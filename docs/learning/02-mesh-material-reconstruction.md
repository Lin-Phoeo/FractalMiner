# 02｜网格、骨骼、材质重建与防炸验证

目标：自己解释并重现“官方默认提弗洛斯模型为什么能正确站立、蒙皮、绑定材质”，而不是只会按生成按钮。再把珊瑚海岸静态 mod 当作独立的二进制/UV 排错练习，不混进官方还原验收。

本章依据 2026-09-23 的源码与验收记录；源码光照基线提交为 `1b25951`。当前工作树仍在 `main`，恢复记录在 `fix/typhoeus-render-explosion-20260917`，不允许为了学习直接重置/清理这个目录。先阅读 [01 的环境与资产清单](</A:/Hypergryph Launcher/games/Arknights Endfield/FractalMiner/docs/learning/01-foundations-and-extraction.md>)。本章带生成动作的 Unity 菜单会修改资产或场景，先另存当前场景、在学习副本练习。

## 1. 一条数据链，不是“把 FBX 扔进 Unity”

```text
Avatar 模板 bonePathsStr + bonePaths
          │ 完整路径 CRC32 → 全局骨骼序号
          ▼
源 Mesh JSON ─→ 统一模型 JSON ─→ TyphoeusModelBuilder
 顶点/法线/UV     bones[]            ├─ 481 个 Transform
 索引/子网格      meshes[]           ├─ 17 个持久化 Mesh
 局部骨索引/权重                     └─ 17 个 SkinnedMeshRenderer
 bindpose                                     │
                                              ▼
Material JSON + Texture2D ─→ 材质导入器 ─→ 展示场景
                                              │
                      保存/重开 + 静止/运动蒙皮测试 + 通道检查
```

主入口：[TyphoeusModelBuilder.cs](</A:/Hypergryph Launcher/games/Arknights Endfield/FractalMiner/Assets/EndfieldShaderPack/Editor/TyphoeusModelBuilder.cs>)、[TyphoeusSceneSetup.cs](</A:/Hypergryph Launcher/games/Arknights Endfield/FractalMiner/Assets/EndfieldShaderPack/Editor/TyphoeusSceneSetup.cs>)。

已有 `chr_0034_typhoea_uimodel.fbx` 的优化骨架与源 bindpose 不一致，直接使用曾导致顶点飞散。当前 Setup 保留它为禁用的 `Typhoeus_SourceFBX` 参考对象，真正显示的是 `chr_0034_typhoea_rebuilt`。不要把禁用原 FBX 误认为“丢了模型”，也不要为了恢复显示同时启用两套人物。

## 2. 先给 JSON 建立数据契约

打开 `_typhoea_model_data.json` 时用可折叠 JSON 编辑器，或用小程序只输出统计，不要把几十万浮点数直接刷满终端。以下是 `TyphoeaModelData` 的契约：

| 字段 | 含义 | 长度/范围约束 |
|---|---|---|
| `bones[].name,parent` | 全局骨骼名、父序号 | parent 为 -1 或有效序号；无环；当前构建器要求父先于子 |
| `vertices` | 扁平 xyz | 长度 `3V`，所有值有限 |
| `normals` | 每顶点法线 xyz | 长度 `3V`；使用到的向量不能近零 |
| `uvs` | 原始 uv0 | 长度 `2V`；有限；不强行截断为 [0,1] |
| `indices` | 三角形顶点序号 | 每个索引在 `[0,V)`；总长为 3 的倍数 |
| `subMeshIndexCounts` | 每个子网格索引数量 | 每项为 3 的倍数；和等于索引总数 |
| `boneWeightIndices` | 每顶点 4 个**局部**骨序号 | 长度 `4V`；非零权重项必须有有效局部索引 |
| `boneWeightValues` | 每顶点 4 个权重 | 长度 `4V`；有限、非负、和接近 1 |
| `bones`（Mesh 内） | 局部骨序号 → 全局骨序号 | 每项有效；不应有未解析的 -1 |
| `bindPoses` | 每局部骨骼一组 16 个 float | 长度 `16B`；矩阵有限、可逆 |

**练习**：自己写一个检查器，对每个 Mesh 输出 V、三角形数、最大索引、UV min/max、权重和的最大偏差、未解析骨骼数。再复制一份小数据，把一个索引改成 V，确认程序能指出具体 Mesh 和索引位置。

**为什么不能只看数量**：481 根骨骼顺序错了一项仍然是 481；两个贴图名字对调仍然有两张；一张 Mesh 对应另一个身体部件也可能顶点数恰好相同。数量通过后还要检查对应关系。

### 源 JSON 转统一 JSON 的潜在限制

`_build_typhoea_model_data.py` 直接取源 `m_Indices`，子网格只保留 `indexCount`。当前数据已由后续测试验证，但把脚本移植到另一批资源时必须核对 `firstByte/baseVertex/topology`，确认它们已经在导出结果中展开或不需额外处理。不能对任何 Unity Mesh 都假设所有 submesh 恰好连续、baseVertex 为零。

## 3. 坐标变换：让整条链说同一种语言

本批官方数据的模型是 Z-up。当前做法把根对象旋转 `Quaternion.Euler(-90,0,0)`；顶点、骨架和 bindpose 保持在同一个源空间。对这个纯旋转，它的点坐标效果是：

```text
(x, y, z) → (x, z, -y)
```

**不是**“所有游戏都这样转”，也不是“Unity 和 DirectX 必然要翻某一轴”。先拿已知头顶、脚底、面朝方向的点验证；坐标轴方向、矩阵存储顺序、UV 方向是三件不同的事。

为什么只转顶点会炸：蒙皮矩阵仍以原坐标解释这些已旋转点，等价于对不同数据施加了不同基变换。若确实要烘焙坐标转换，所有相关变换都需要一致变换；这是一个完整推导任务，不是再补一个负 scale。

**手算练习**：取源点 `(0,0,1)`、`(0,1,0)`，分别经过上述旋转；在 Unity 用三个小方块表示它们。取一个点先应用旋转再应用逆旋转，核对误差。

**验收**：整体站立；源部件相对位置不变；不靠每个部件单独居中拼脸；没有不明负缩放；骨架和静态网格一起转。

## 4. bindpose：用恒等式而不是凭眼睛修骨骼

本节通用接口可查 [Unity 2022.3 Mesh.bindposes](https://docs.unity3d.com/2022.3/Documentation/ScriptReference/Mesh-bindposes.html)，实际数组读取规则必须按本地 `ReadMatrix` 验证。

令：

- `R`：SkinnedMeshRenderer 对象的世界矩阵。
- `Wj`：第 j 根骨骼的当前世界矩阵。
- `Bj`：第 j 根骨骼对应的 bindpose。
- `wj`：顶点对该骨骼的权重。

在 Renderer 的局部空间里，线性混合蒙皮为：

```text
Sj = inverse(R) * Wj * Bj
p_skinned = Σj wj * Sj * p_source
```

绑定姿态下应有 `Sj ≈ I`，因而 `p_skinned ≈ p_source`。这条式子就是“为什么没有炸”的可测解释。不能拿拍脑袋平移或关掉蒙皮作为修复完成的依据。

### 4.1 局部索引与全局索引

源 Mesh 的 `boneIndex` 是该 Mesh 的局部骨索引。`mesh.bindposes[j]` 与 `renderer.bones[j]` 必须同序。统一 JSON 的 Mesh `bones[j]` 再把 j 映射到全局 Transform 数组。

例：某顶点 `boneIndex0=3`，该 Mesh 的 `bones[3]=120`，其 weight0 应作用于全局第 120 根骨骼和局部第 3 个 bindpose。把权重中的 3 直接改成 120，会让 Renderer 去查它自己数组的第 120 项，含义已经变了。

完整路径通过 CRC32 匹配 `m_BoneNameHashes`，不是只 hash 最后一段骨骼名。检查两个同名骨骼的父路径，解释为什么只按短名不能唯一对应；遇到 CRC 碰撞或未知哈希要停下来解析，不要用第一项顶替。

### 4.2 矩阵扁平数组的读取

本地构建器实际使用 `M[row,column] = flat[column*4 + row]`，因此源数组的 12、13、14 三项进入 Unity 的 m03、m13、m23（平移列）。判断依据是这个实际映射及恒等式检查，不是“行主序/列主序”几个字。

从 bindpose 取逆得到理论绑定世界矩阵；子骨局部矩阵由 `inverse(parentWorld) * childWorld` 得到。当前代码把局部 scale 设置为 1，适用于这批已验收数据；如果未来输入含非均匀缩放、镜像或剪切，直接取 rotation 加 scale=1 不保证等价。应先量化矩阵分解误差，再设计支持方式，不要套历史推测就宣布现有骨骼坏了。

### 4.3 两道验收门

阅读 [TyphoeusGeometryValidation.cs](</A:/Hypergryph Launcher/games/Arknights Endfield/FractalMiner/Assets/EndfieldShaderPack/Editor/TyphoeusGeometryValidation.cs>)：

1. `Inspect(root,true)`：计算每个 `inverse(R)*Wj*Bj` 与单位矩阵的最大元素误差；再 `BakeMesh`，比较静止顶点。当前门限均为 `1e-4`。
2. `ValidateMovingBone`：把 `Bip001_Head` 临时旋转 15 度，自己按公式算顶点，和 Unity 的 BakeMesh 比较；要求误差 ≤ `1e-4`，且确有顶点运动；`finally` 恢复原旋转。

此前本批静止顶点最大误差约 `2.16243e-5`。它是该数据/编辑器组合的回归参考，不是所有游戏都应使用的统一精度标准。应记录最大值和最差部件，不只保存“PASS”。

**失败排查顺序**：源数组是否有限 → 索引/权重是否有效 → 本地/全局骨映射 → bindpose 读取顺序 → 根/Renderer 矩阵 → 父子顺序 → scale/镜像 → 动画。几何没过时不要动材质亮度。

## 5. 法线与切线：几何位置对了仍可能光照不对

一个三角形正常显示不代表法线正确。N 是表面法线，T 是切线，B 是副切线；常见构造为 `B = cross(N,T) * tangent.w`，还需正确处理对象变换中的手性。法线贴图的切线空间方向通过 TBN 转到光照计算空间。

原版重建保留导出法线、保留 UV，再 `RecalculateTangents()`；不要无条件 `RecalculateNormals()` 抹掉美术特调的平滑法线。静态 mod 的未改动部件能逐点匹配源几何时也继承源法线；重建法线只是无可靠源数据时的有标注替代。

**手工检查与练习**：

1. 调试输出 `N*0.5+0.5`，旋转物体，确认它随正确空间变化。
2. 用平坦法线贴图检查 TBN，不叠加 anisotropy 或 SDF。
3. 检查所有被绘制顶点：`|N|²` 和 `|T.xyz|²` 接近 1，`abs(T.w)` 接近 1；进一步检查 N·T 接近 0。
4. 故意把 T.xyz 清零但保留 w=1，观察为什么检查 `length(float4 tangent)` 会假通过。

当前回归检查会分别验证 tangent.xyz 和 w，不能用 `(0,0,0,1)` 冒充有效切线。完整验收仍需结合 UV 镜像边界与高光走向。

## 6. 材质是有类型的参数表，不是随便套 PBR 贴图

入口：[EndfieldMaterialImporter.cs](</A:/Hypergryph Launcher/games/Arknights Endfield/FractalMiner/Assets/EndfieldShaderPack/Editor/EndfieldMaterialImporter.cs>)、[EndfieldMaterialValidation.cs](</A:/Hypergryph Launcher/games/Arknights Endfield/FractalMiner/Assets/EndfieldShaderPack/Editor/EndfieldMaterialValidation.cs>)。

按顺序阅读 `BuildMaterialsFromJson → ApplyJsonToMaterial → PropertyIs → ConfigureUrpRenderState`：

- `m_TexEnvs` 给纹理及每个槽的 scale/offset。
- `m_Floats` 给标量；`m_Colors` 可能给 ShaderLab Color，也可能给 Vector，不能全用同一种设置方法。
- 先查 Shader 声明的属性类型，再写入。源材料可能同时残留同名 float/texture 旧条目，例如 `_ClearCoatMask`；“读出所有键并写入”会制造错误。
- `MaterialFamily` 是本地路由标签，不是官方 Shader 变体身份。body 在本轮已纠正为 skin b114/b208，不再用错误的 cloth b401 推断其参数。
- 未支持的源属性要记录。没有在本地 Shader 声明的某项即使存在 JSON 里，也不意味着它已经生效。

### 6.1 各类纹理与数据空间

| 槽/用途 | 应按什么理解 | 常见误区 |
|---|---|---|
| `_BaseMap` | 通常是颜色，依实际源格式使用 sRGB；alpha 的意义随 Shader 分支 | 不透明 skin 的 alpha 参与遮挡，不等于把皮肤变透明 |
| `_BumpMap` | 自定义法线数据；当前保持 Default + Linear 让 Shader 解码 | 用 Unity Normal map 导入可能重打包通道，造成双重解码 |
| `_MetallicGlossMap`，cloth | R 金属、G 高光 mask、B 阴影 mask、A 光滑度的当前分支语义 | 不能把 B 当全局最终 AO 乘数，也不能把通道说明泛化给所有材质族 |
| `_MetallicGlossMap`，hair | R 各向异性方向选择、G 主高光 mask、B 阴影 mask、A 副高光 mask | 头发 R 不等于金属度，A 不等于普通光滑度 |
| `_SDFLightmap/_SDFMask` | 数据场与选择权重，线性导入，采样/寻址按源码 | SDFMask.g=0 是 SDF，g=1 是普通 N·L；旧实现曾用反 |
| `_DiffRampMap` | 带 RGB 染色及 alpha 控制的查找表 | alpha 变化即使 RGB 不变也应影响光照 |
| `_ShadowLutTex` | 皮肤阴影颜色查找；根据捕获格式与源码解释 | 不因名字叫 LUT 就统一关闭 sRGB；本帧有 BC7-sRGB LUT |
| `_SpecRampMap` | 布料二维高光查表等，需按实际 uv/LOD | 不是一律用 N·L 取横坐标 |

本地 `RepairPackedTextureImports` 把 Bump/SplitNormal/P/SDF/Mask 等数据槽设为 Default、关闭 sRGB/alphaIsTransparency、使用未压缩导入。这样保留原始通道，再由 Shader 决定解码。颜色图、数据图为何应区别处理，参见 [Unity 2022.3 的线性纹理说明](https://docs.unity3d.com/2022.3/Documentation/Manual/LinearRendering-LinearTextures.html)。

目前 RGorAG 法线解码：`x=2*(R*A)-1`，`y=2*G-1`，从 xy 恢复 z。它是当前已核对分支的约定，不是所有名为 N/HN 的文件通用公式。Shader 中的历史开头注释和 debug 名称可能比源码新分支更旧，判断以实际函数体为准。

### 6.2 每张纹理都有自己的 ST

```text
uv_sample = rawUV * textureScale + textureOffset
```

本批 DDS 转 PNG 的 mod 图像通过相应纹理槽设置 `scale=(1,-1), offset=(0,1)`。保留网格 rawUV，原版 SDF/辅助贴图仍按自己的 ST 取样。

**练习**：在副本里仅翻 BaseMap，比较脸图与 SDF；再恢复。解释为什么把网格 UV 全部翻一次会同时破坏没有经过 DDS 转换的辅助贴图。不要以“图形 API 不同”为借口统一翻所有 UV。

### 6.3 深度/混合状态也是材质

官方 HGRP 的 `Equal` 深度测试可能依赖先前 depth prepass；独立 URP forward 没有对应前置深度时会使人物消失。当前适配设 `LessEqual`，不透明开启 ZWrite、One/Zero 混合，透明分支独立处理，队列随透明/alpha-test 调整。

这属于必要的管线适配，不应描述成“所有官方状态原样照抄”。专用眼影、发影、VFX 壳层保留几何但默认不作为普通不透明身体渲染；后续应恢复对应 stencil/pass，不能给它们套 body Shader 后宣布完成。

## 7. 亲手重建默认角色：菜单路径与检查点

在已经具备本地合法资产的 Unity 学习副本中操作：

1. 用 2022.3.30f1 打开工程。先看 Console 的**第一条**编译错误；有错误时不要继续连点菜单。
2. 核对 `Assets/Typhoeus/Materials/*.json`、所需纹理、统一模型 JSON、参考 FBX 均在。干净 Git 副本缺资源很正常，不能把源数据缺失当代码问题。
3. `Endfield / Repair Packed Texture Imports`：修复数据图导入约定。
4. `Endfield / Build Typhoeus Materials From JSON`：生成/更新 `.mat`。逐项检查缺纹理警告。
5. `Endfield / Setup Typhoeus Showcase Scene`：生成标准展示，保存到 `Assets/Scenes/Typhoeus_Showcase.unity`。先保存自己当前场景；此方法会新建场景。
6. Hierarchy 验证一个启用的重建根、一个禁用的参考 FBX；17 个 SkinnedMeshRenderer 包含禁用的特殊壳层，不能要求 17 个全部可见。
7. `Endfield / Validate Saved Showcase`：会重新打开保存场景，检查持久化 Mesh、切线、材质深度、Shader 编译与静止/运动蒙皮，报告 `Validation/geometry-report.txt`。
8. 在展示场景运行 `Endfield / Validate Material Data and Capture Channels`：核对声明属性的源数值、类型和绑定；生成 `Validation/material-report.txt` 及分通道预览。

单独 `Endfield / Rebuild Typhoeus Model` 不会替你管理旧根对象；反复执行会重复创建。需要可重复场景时用标准 Setup，或在练习场景中先明确移除自己上次生成的那个根，不能删除整个工程目录来“重来”。Humanoid/MMD 菜单不是此阶段必需品，打开它不等于原版动画恢复完成。

无编辑器界面时可用已核对入口；同一工程只能有一个 Editor 实例，先退出已有编辑器且保存工作：

```powershell
$projectRoot = 'A:\Hypergryph Launcher\games\Arknights Endfield\FractalMiner'
$unityExe = 'A:\Unity\Editor\2022.3.30f1\Editor\Unity.exe'

# 前提：Showcase 已按上面步骤生成。会打开该场景并写验证产物。
& $unityExe -batchmode -projectPath $projectRoot `
    -executeMethod EndfieldShaderPack.TyphoeusGeometryValidation.VerifySavedShowcase `
    -logFile "$projectRoot\Logs\learning-geometry.log" -quit
if ($LASTEXITCODE -ne 0) { throw '几何验收未通过：检查 learning-geometry.log' }
```

需要 GPU 像素输出的检查不要加 `-nographics`。进程退出码、日志中的 PASS 和报告时间都要确认；上次残留报告不是本次通过证据。

### 7.1 资产持久化是一个单独知识点

`new Mesh()` 只创建内存对象，场景当前能显示不代表重开能用。构建器把网格保存在 `Assets/Typhoeus/GeneratedMeshes/*.asset`；已有资产用 `CopySerialized` 更新内容，维持引用和 GUID。

**练习**：先在小测试工程创建但不保存 Mesh，观察重开差异；再 `AssetDatabase.CreateAsset` 保存；第三次更新同一路径资产而不是删除重建，检查 `.meta` GUID 是否稳定。不要在实际角色上用“删除重建一切”来做这个实验。

## 8. 珊瑚海岸：把历史错误变成可复现的排错题

这条支线不是官方默认服装。当前是一个静态预设，不是完整 runtime mod，也没有完成 C13/C14 的精确运行时蒙皮。

入口：[CoralCoastMeshImporter.cs](</A:/Hypergryph Launcher/games/Arknights Endfield/FractalMiner/Assets/EndfieldShaderPack/Editor/CoralCoastMeshImporter.cs>)、[TyphoeusRecoveryValidation.cs](</A:/Hypergryph Launcher/games/Arknights Endfield/FractalMiner/Assets/EndfieldShaderPack/Editor/TyphoeusRecoveryValidation.cs>)。

### 8.1 从 INI 确定布局，不从图像猜部位

对每个组件先读 VB0/VB1 的 stride、IB 的 DXGI 格式、draw 的 firstIndex/indexCount。索引个数不是三角形个数；triangle count = index count / 3。字节偏移 = index * stride + attributeOffset。

| 组件 | 逐点核验后的身份 | 当前事实 |
|---|---|---|
| C0 | 角，对应 cloth_05 | 1060 顶点；以前误当脸删除 |
| C1 | 头发 hair_01 | 15306 顶点；继承对应源法线 |
| C3 | face_01 | 2109 顶点；正确脸图集 `6b12e27e` |
| C6 | iris_01 | 162 顶点；瞳孔在正确脸部范围内 |
| C7 | eyeshadow_01 | 特殊覆盖层，不是多出来一对瞳孔 |
| C13/C14 | 眉部的另一布局/空间 | VB0 为 **40** 字节、VB1 为 8；不能按 16 字节解码 |

部件身份验证用原 JSON 顶点数、逐顶点位置与 UV。C0/C1/C3/C6 的位置/UV 最大误差约 `6e-8` 以内，远小于导入器 `1e-5` 的匹配门限。这个证据否定了“脸 UV 被重排，所以必须额外烘焙脸”的旧推测。

### 8.2 画哪些索引也是模型的一部分

当前 `DrawLists` 固定 INI 默认 `Main=0, Socks=1`，不把互斥服装同时画出来。C8 排除了 firstIndex 为 10404、54396、117732 的互斥片段。若自己更换预设，需要重新沿 INI 条件推导完整 draw list，不能随意加几个范围。

C13/C14 使用 `gpu_posed=0` 的不同坐标空间，目前用源模型组合的 638 顶点 brow 替代。把这一点写进状态表：**静态替代已通过，不是原运行时蒙皮已复原**。

### 8.3 不靠截图的验收

菜单 `Endfield / 珊瑚海岸 / ⑧ 构建并验证修复展示场景` 会先提示保存未保存场景，再导入两次、验证 GUID、保存/重开、清空再恢复全局参数并运行 GPU 探针。预期为 9 个部件、394445 个三角形。

检查内容包括：无额外重复脸；虹膜中心在真正脸的包围盒内；FaceAtlas 正确；SDF 未误翻 UV；法线/切线有限且有效；组装人物中打开/关闭虹膜确实改变可见像素。最近基线有 1389 个可见变化像素，该数量仅是此诊断相机下的回归参照，不是“还原度 99%”。

`⑤ 导入 mod 静态模型` 用于已有场景；`⑦ 校验脸部与眼部（无需烘焙）` 已停用旧额外烘焙逻辑。旧 `analyze_coral_mesh.py`、`probe_coral_buffers.py` 中有固定/猜测步长，不能继续用它们对合法 buffer 下“损坏”结论。历史探索文件是需要审查的草稿，不是不可推翻的工具权威。

## 9. 症状 → 第一项检查 → 不能乱改什么

| 症状 | 先检查 | 不要先做 |
|---|---|---|
| 四肢、角、脸飞散 | 静止 skin matrix 与顶点误差、局部/全局 bone index | 逐部件平移拼回去 |
| 静止正常，转头炸开 | posed 测试、权重映射、bindpose 顺序 | 删除骨骼、固定成静态并声称修复蒙皮 |
| 整个人看不见 | 相机/启用状态、深度测试、包围盒、材质 Shader 编译 | 重做全部贴图 |
| 模型发粉 | 第一条 Shader 编译错误、Shader 引用 | 调光颜色 |
| 脸黑但 UV 正常 | BaseMap 身份、色彩空间、ramp alpha、SDF/阴影公式 | 把所有阴影强度调成 0 |
| 瞳孔单独可见，组装不可见 | 深度/剔除/遮挡；开关虹膜贡献测试 | 随机把眼睛向外移动 |
| 某些部位花屏/细长尖刺 | stride、索引位宽、draw range、顶点有限性 | 判定导出器全坏 |
| 法线接缝/头发高光错方向 | TBN、w、法线通道解码、UV 镜像 | 用更强 Bloom 掩盖 |
| 衣服局部闪烁 | 互斥 draw 是否同时绘制、重复对象、Z-fighting | 修改所有部件 ZTest=Always |
| 当前好，重开坏 | 持久化 Mesh、GUID、场景全局参数恢复 | 认为 Unity 缓存必然损坏并清空 Library |
| 远看颜色相近，细节仍不像 | 同姿态/相机/光照、Shader 分支、后处理 | 宣称模型已完美等于渲染已完美 |

## 10. 无助手时的日常训练与升级门槛

每次只做一个可反驳的假设，留一条失败到通过的证据。例如：“我认为脸黑由错误图集造成”，应先确认当前图集哈希与 INI 不同，再仅换图集、运行同相机检查；不能同时动曝光、灯光、SDF、相机后说原因找到了。

自己的工作记录建议每次写 8 行：输入版本/哈希、源码提交、现象、假设、最小改动、测试命令、实际结果、剩余限制。失败记录同样保留，它能防止下次重走已证伪的路线。

进入后续 Shader/管线章节前，你应能不看答案回答：

1. 为什么权重索引必须保持 Mesh 局部索引？
2. 静止时 `inverse(R)*W*B` 为何应接近 I？
3. 为什么不能同时改顶点坐标而不改 bindpose？
4. 为什么 `(0,0,0,1)` 不能作为有效 tangent？
5. 为什么一张叫 P 的纹理在头发和布料上语义不同？
6. 为什么原模型 UV 不应为某张 mod PNG 被全局翻转？
7. 为什么 HGRP 的 Equal depth 不能直接视作独立 URP forward 的正确状态？
8. 为什么当前 32 项 Shader 数值测试、35 项脚本测试通过，仍不能宣称官方全帧完全一致？

回答时打开相应源码指出证据位置，并在小测试上演示。做到这一步，你已具备独立维护当前“模型还原通过”阶段的能力；下一步才是按捕获逐项对齐光照、环境反射、屏幕阴影和官方后处理。
