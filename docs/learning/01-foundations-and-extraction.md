# 01｜从零建立能力与可信资产清单

本章不是提示词或自动代做流程。目标是让你不用任何模型服务，也能自己读代码、运行工具、判断输出是否正确，并在几天后靠记录继续工作。学习对象限定为你有权研究的本地资源与已有离线截帧；不包含关闭、隐藏或绕过游戏保护的方法。

核验日期：2026-09-23。本章命令以当前 Windows 目录为例。CLI 参数已用本机 `--help` 核对，但本次编写没有重新执行全量解包；游戏更新后的格式兼容性不能由这些命令保证。

## 1. 先理解终点与证据层级

下面各层解决不同问题，后一层不能用来掩盖前一层错误：

```text
原始资源文件
  └─ 容器读取与导出：找到了什么对象？源包和版本是什么？
      └─ 网格、骨骼、材质重建：坐标、索引、绑定和纹理是否对应？
          └─ Shader 数学：同样输入是否得到相同线性颜色？
              └─ 渲染管线：阴影、反射、遮挡、绘制顺序是否一致？
                  └─ 最终画面：同姿态、同镜头、同曝光、同后处理吗？
```

“解包成功”只说明某层数据被读出来；“模型没有炸开”只说明一部分几何问题被排除；“数值测试通过”也只覆盖测试中的输入与分支。最终目标是官方提弗洛斯角色详情页，但当前已验收的是阶段性模型、材质绑定以及选定源码光照分支，不是全游戏管线复制完成。

证据优先顺序：原始文件及其哈希 → 捕获中的实际绑定/数值 → 导出器与导入器的可运行测试 → 研究笔记 → 旧会话中的判断。若笔记和原始数据矛盾，先停下来核验数据，不用另一套“看起来正常”的参数补偿。

## 2. 必要知识：每项都配一个能独立完成的小作品

零编程基础时，不必先学完全部 C++、引擎源码和微积分。按下表做小练习，做完再进入真实角色；时间按掌握程度安排，不能把看完视频算作通过。

| 先修模块 | 必须理解的内容 | 不靠现成答案完成的练习 | 通过条件 |
|---|---|---|---|
| 文件与 PowerShell | 绝对/相对路径、引号、工作目录、程序退出码、标准输出/错误、只读与写入 | 找到指定 `.json`；读取前 20 行；把两个文件的 SHA-256 对比 | 路径带空格仍正确；知道命令是否会写文件 |
| Git | 工作树、暂存区、提交、分支、远端、忽略文件、差异 | 在自己的小练习库新增一个脚本、提交，再写出两次提交的差别 | 能解释“文件在硬盘上”与“文件在提交中”不是同一回事 |
| Python 基础 | 变量、条件、循环、函数、异常、字典/列表、`json`、`pathlib`、`struct` | 读取一个网格 JSON，输出顶点数、三角形数、包围盒、最大索引 | 对一个故意越界的索引明确报错，不静默跳过 |
| 二进制数据 | 字节、位、大小端、uint16/uint32、float32、stride、offset | 自己编码并解码 3 个 float 和一个 uint32；改变 stride 看错误 | 算出 `count = bufferBytes / stride`；说明余数非零为何有问题 |
| C# 基础 | 类/结构体、数组、泛型、`static`、命名空间、引用、异常、生命周期 | 在独立 Unity 练习项目写一个菜单，生成三角形并保存 Mesh 资产 | 保存/关闭/重开后仍能显示；没有丢失引用 |
| 向量 | 长度、归一化、点积、叉积、投影 | 计算两个方向夹角；用 `cross` 给三角形求法线 | 知道点积为 0、1、-1 各代表什么；零向量不能直接当方向 |
| 矩阵与坐标 | 4×4 仿射变换、逆矩阵、乘法顺序、局部/世界空间、法线逆转置 | 平移后旋转与旋转后平移各算一次；对点做变换再逆变换 | 明确两结果通常不同；恢复误差在给定容差内 |
| 四元数与骨骼 | 父子 Transform、局部旋转、绑定姿态、权重混合 | 两根骨骼带动一条 4 顶点长条 | 静止时不变形；旋转父骨骼时子骨骼跟随；权重之和为 1 |
| GPU 管线 | 顶点着色、光栅化、片元着色、深度、剔除、混合、RenderTexture | 输出 UV、法线、纯红色三种调试视图 | 能分清缺几何、被深度挡住和 Shader 输出黑色 |
| 纹理与颜色 | UV、ST、采样器、mip、线性/sRGB、HDR、数据图和颜色图 | 生成线性 0.5 灰与 sRGB 0.5 灰的对照 | 不把两种 0.5 当成相同物理亮度 |
| 材质与光照 | 漫反射/高光、N·L、N·V、粗糙度、金属度、ramp、SDF、TBN | 用常量纹理和单个平面复现一个光照公式 | 能手算预期值，再读回 GPU 像素验证 |

学习资料只负责解释通用概念，项目事实仍要回到本地源码：

- 编程零基础先用 [Microsoft C# 入门入口](https://learn.microsoft.com/en-us/dotnet/csharp/tour-of-csharp/) 中的 beginner tutorials，不要直接学习网页默认展示的新语言特性；Unity 的可用语法由本项目编辑器决定。
- 掌握基本编程后，按 [Python 3.13 官方教程](https://docs.python.org/3.13/tutorial/) 的控制流、数据结构、文件、异常、模块与浮点误差章节做练习。该教程本身并不以完全没有编程经验的人为前提。
- 网格属性的定义查 [Unity 2022.3 Mesh data](https://docs.unity3d.com/2022.3/Documentation/Manual/AnatomyofaMesh.html)。不要把“顶点”只理解成一个坐标；它还可对应法线、UV、切线和蒙皮等数据。

### 一页数学备忘

```text
dot(a,b) = ax*bx + ay*by + az*bz
normalize(v) = v / length(v)                 # length 太小时必须另行处理
lerp(a,b,t) = a + (b-a)*t                     # 不自带 t 的 [0,1] 截断
saturate(x) = min(max(x,0),1)
p_world = M_objectToWorld * float4(p_local,1)
n_world ∝ transpose(inverse(M_objectToWorld)) * float4(n_local,0)
```

本项目多次错误来自“看懂了式子的形状，却改了式子的含义”：把 `lerp` 当成自动截断、把矩阵存储顺序当成坐标手性、把 alpha 永远当透明度。每次移植都要写出输入范围、输出空间和使用分支。

## 3. 本机工作区地图与版本冻结

```text
A:\Hypergryph Launcher\games\Arknights Endfield\
├─ Endfield_Data\StreamingAssets\VFS\         原始容器，保持只读
├─ EndfieldUnpacker\                         解包与中间产物，独立于 Unity
│  ├─ .venv\Scripts\python.exe               本项目 Python
│  ├─ AnimeStudio-net10\AnimeStudio.CLI.exe   资产导出入口
│  ├─ DecryptOutput\Bundles\Windows\         已解出的 AssetBundle
│  ├─ _fullmap\assets_map.json               全量资产索引
│  ├─ _typhoea_assets_map.json               角色资产清单
│  └─ _typhoea_material_binding.json         材质/纹理来源线索
└─ FractalMiner\                             Unity 工程及源码记录库
   ├─ Assets\Typhoeus\                       本地官方导出数据
   ├─ Assets\EndfieldShaderPack\             重建与渲染代码
   ├─ Tools\                                离线检查和截帧分析
   ├─ Validation\                           可再生报告/预览/本地捕获
   └─ docs\learning\                        本学习手册
```

核验过的版本：Unity **2022.3.30f1 (70558241b701)**；URP 的 manifest/lock 请求 **14.0.12**，本机实际 PackageCache 内 package.json 是 **14.0.11**（不要混为已加载同一版本）；Python **3.13.2**；AnimeStudio CLI **1.1.0+7cfb26b9c158f6150c887f9157de97a3fa7672e1**。Python 当前包含 `pycryptodome=3.23.0`、`UnityPy=1.25.3`、`Pillow=12.3.0`。这三项不是整个环境的依赖锁定清单。当前环境没有 `pip` 模块，也没有 `numpy`；不要把“pip 不存在”当成解包程序损坏，更不要因为历史探索脚本引用 numpy 就给核心流程强行增加依赖。

版本依据：[ProjectVersion.txt](</A:/Hypergryph Launcher/games/Arknights Endfield/FractalMiner/ProjectSettings/ProjectVersion.txt>)、[manifest.json](</A:/Hypergryph Launcher/games/Arknights Endfield/FractalMiner/Packages/manifest.json>) 和本机程序输出。工程有历史工具包，但手动学习与 Unity 菜单/命令行验收不依赖聊天助手或 MCP 服务。

先只运行下面的身份检查：

```powershell
$gameRoot = 'A:\Hypergryph Launcher\games\Arknights Endfield'
$projectRoot = Join-Path $gameRoot 'FractalMiner'
$unpackRoot = Join-Path $gameRoot 'EndfieldUnpacker'
$pythonExe = Join-Path $unpackRoot '.venv\Scripts\python.exe'
$assetCli = Join-Path $unpackRoot 'AnimeStudio-net10\AnimeStudio.CLI.exe'

Get-Content -LiteralPath (Join-Path $projectRoot 'ProjectSettings\ProjectVersion.txt')
& $pythonExe --version
& $assetCli --version
& $assetCli --help
& $pythonExe -c "from importlib.metadata import distributions; print('\n'.join(sorted(d.metadata['Name']+'=='+d.version for d in distributions())))"
git -C $projectRoot status --short --branch
git -C $projectRoot log -1 --oneline fix/typhoeus-render-explosion-20260917
```

把输出复制到自己的学习日志。全新机器先根据它建立隔离 Python 环境和相同 Unity 版本，不在已验收 `.venv` 内直接全量升级；不要把不同电脑间直接复制 `.venv` 当成可靠安装方法。

### 特别注意：当前 main 不是恢复记录分支

编写时当前 checkout 是上游 `main`，其工作树有大量现存改动、删除和未跟踪资产；阶段性恢复代码的记录在 `fix/typhoeus-render-explosion-20260917`，上一阶段提交为 `1b2595116e020371d29dbc9742d7a8fe07fb2a90`。后续提交会继续前进。

不能在此直接 `git add .`、清理未跟踪文件、强制切分支或硬重置。“相对 main 未跟踪”并不表示可以删除。学习实验最好放到另外的目录/工作树；干净代码副本通常**不含**原游戏资源、mod、`.rdc`、生成场景和大部分预览，需要按清单单独准备本地数据。当前主目录的特殊隔离索引提交办法见总路线中的保存与恢复章节；新手不要自行用普通提交把整个游戏目录纳入 Git。

## 4. 解包：先查层次，再决定是否重做

入口依据：[EndfieldUnpacker README](</A:/Hypergryph Launcher/games/Arknights Endfield/EndfieldUnpacker/README.md>)、[config.py](</A:/Hypergryph Launcher/games/Arknights Endfield/EndfieldUnpacker/config.py>)、[decrypt_vfs.py](</A:/Hypergryph Launcher/games/Arknights Endfield/EndfieldUnpacker/decrypt_vfs.py>)。阅读时不要把 README 中描述的所有工具都当成必须执行项。

本任务的最短资产链是：

```text
VFS 下 BLC 索引 / CHK 容器
  → 已授权的现有本地导出流程
  → DecryptOutput/Bundles/Windows 中的 .ab
  → AnimeStudio 的资源索引与 JSON/纹理导出
  → 角色网格、Avatar 模板、材质、共享贴图
  → Unity 重建
```

Lua、语音 WEM、地形等是其他分支，不是“角色图形还原必须全做”的前置。也不要为了读已经导出的 JSON 再启动游戏。

### 4.1 只读预检

1. 关闭正在修改这批资源的其他导出任务；保留原文件与已经通过检查的导出结果。
2. 检查 `EndfieldUnpacker/.game_dir`，它应指向含 `Endfield_Data` 的游戏目录，不是 `EndfieldUnpacker` 本身。`config.py` 读取缓存；无缓存时才会提示输入并写缓存。
3. 查看原始 VFS 目录结构、可用磁盘空间和目标输出目录。程序默认把结果写到自身目录的 `DecryptOutput`，并非当前终端目录。
4. 先读 `decrypt_vfs.py` 的 `if __name__ == '__main__'`；此脚本用的是位置参数，不是标准 `--help` CLI。

README 确实提供以下命令；`dry` 不导出资源，但首次选择路径仍可能创建 `.game_dir`：

```powershell
Push-Location $unpackRoot
try {
    & $pythonExe '.\decrypt_vfs.py' dry
    if ($LASTEXITCODE -ne 0) { throw 'VFS 预检失败：保留完整错误输出' }
}
finally { Pop-Location }
```

**验收**：能枚举预期 BLC/CHK，文件计数不是意外的 0，路径正确；出现 CRC、范围或读入错误时先分析原因，不能把退出码为 0 当成所有条目完整。

**失败排查**：路径缓存是否过期？文件是否属于同一游戏版本？容器是否下载完整？脚本依赖是否在指定解释器？`decrypt_blc` 的 CRC 检查目前只打印警告，而且读取有符号 i32 与 `crc32()` 的无符号结果可能产生符号差异；必须核对数值和后续结构，既不能忽略所有警告，也不能仅凭一条警告断言文件损坏。

### 4.2 全量导出不是日常操作

现有资源能支持后续工作时跳过。确实需要重建且权限/数据完整性已确认时，在单独备份或新的工作副本中使用 README 已有命令：

```powershell
# 注意：会向该脚本目录下的 DecryptOutput 写入，已有同名文件可能被覆盖。
# 先保留旧输出；本手册编写时没有执行此命令。
Push-Location $unpackRoot
try {
    & $pythonExe '.\decrypt_vfs.py' extract
    if ($LASTEXITCODE -ne 0) { throw '导出未成功完成，请检查日志' }
}
finally { Pop-Location }
```

不要运行密钥搜寻/保护绕过工具来补救不兼容版本；可以继续用已有离线导出学习网格和 Shader。导出程序能读取的范围、是否包括所有 DLC/版本资源，要由清单证明，不能从“目标是提取全部资源”的 README 描述推导成“目前都已完整”。

### 4.3 AssetBundle → 索引 → 定向导出

本机 CLI 帮助确认支持以下参数：`--game ArknightsEndfield`、`--map_op Both`、`--map_type JSON`、`--map_name`、`--types`、`--names`、`--containers`、`--group_assets ByContainer`、`--export_type JSON/Convert/Dump/Raw`。不要照搬其他版本的 `--output`、`--export-json` 等参数。

先复用已经存在的 `_fullmap/assets_map.json`；它关联 Name、Container、Source、PathID、Type、Hash、Offset。若原始版本更换才建立新索引，输出必须另起目录，例如：

```powershell
$bundleRoot = Join-Path $unpackRoot 'DecryptOutput\Bundles\Windows'
$mapOutput = Join-Path $unpackRoot '_learning_map_new'

# 大操作示例：扫描整个输入，可能连带导出大量所选对象；不是瞬间完成的只读命令。
# 先在一个已知 .ab 上练习，再决定是否运行全量。
& $assetCli $bundleRoot $mapOutput --game ArknightsEndfield `
    --map_op Both --map_type JSON --map_name assets_map `
    --types Mesh --export_type JSON --group_assets ByContainer
```

不要因为输出文件有了就认为成功。核对 CLI 日志、`$LASTEXITCODE`、索引中的来源路径和目标 Mesh 数量。`--map_op Both` 表示 CAB/Asset map 组合，不等于“只建索引、不导出任何东西”；帮助没有提供足够依据支持这种假设。

定向练习用本地已存在的原始包，不覆盖现在的工作产物：

```powershell
$oneBundle = Join-Path $bundleRoot 'main\9d16a8bf44730d81348ac3e2.ab'
$oneOutput = Join-Path $unpackRoot '_learning_one_mesh'
if (!(Test-Path -LiteralPath $oneBundle)) { throw '当前版本样例包不存在：从自己的索引重新选取' }
& $assetCli $oneBundle $oneOutput --game ArknightsEndfield `
    --types Mesh --export_type JSON --group_assets ByContainer
```

包名来自本地 `_probe_typhoea_bundles.py` 的样例，不能假设下一版本也叫这个名字。批量导出材料、Avatar 模板、纹理时，先从索引确认 Source，再分别选择正确类型与导出形式：网格/材质/MonoBehaviour 需要结构化 JSON，Texture2D 的 Convert 用于可用纹理。共享 ramp/LUT 的名字未必含 `typhoea`，单用 `--names typhoea` 会漏依赖。

**练习**：取一个 face Material，沿它的 Shader 与每个 `m_TexEnvs` 引用，逐条找到 Texture2D 所在源包，做一张“材质槽 → Name → PathID → Source → 本地输出”表。先练一张材质，再扩大到全部。

**验收**：材质引用的每项要么能解析到正确对象，要么明确标注缺失/内置/运行时绑定。没有“凭名字看着像”的默认替代。

## 5. 从索引走到角色统一 JSON

按此顺序读已有脚本，不需要一次读完所有历史探索文件：

| 阅读入口 | 学会什么 | 必须警惕 |
|---|---|---|
| [_build_typhoea_manifest.py](</A:/Hypergryph Launcher/games/Arknights Endfield/EndfieldUnpacker/_build_typhoea_manifest.py>) | 从全量索引提取角色条目，按类型/名称去重 | 脚本按行和字段顺序解析 JSON，格式变了会失效；名称筛选不会覆盖所有共享资源 |
| [_resolve_materials.py](</A:/Hypergryph Launcher/games/Arknights Endfield/EndfieldUnpacker/_resolve_materials.py>) | 从材料引用沿 PathID 找纹理与 Shader | 当前历史脚本把 PathID 当全局键，有跨源碰撞风险；`unresolved` 统计也不能证明全部 needed 已解析 |
| [_build_typhoea_model_data.py](</A:/Hypergryph Launcher/games/Arknights Endfield/EndfieldUnpacker/_build_typhoea_model_data.py>) | 合并骨架层级、网格、四权重、bindpose；以完整骨路径 CRC32 做局部→全局映射 | BASE/AV/MESH_DIR/OUT 硬编码；未知哈希变成 -1，应先拦截而非自动继续 |

物件身份最好保留 `(版本、源 serialized file/bundle、PathID、引用 FileID)`，不要依赖整数 PathID 全库唯一；保存 64 位 PathID 时使用精确整数或十进制字符串，不经过浮点数转存。历史 `MiniJson` 把数值读成 double 是材质浮点参数使用上的便利，不是精确通用 Unity 引用解析器。

统一模型构建脚本目前读取：

- `AnimeStudio-net10/_avatar_test/assets/beyond/dynamicassets/gameplay/npc/avatartemplet/actor/data_npc_avatartemplet_typhoea.json`
- `AnimeStudio-net10/_all_meshes/assets/beyond/arts/entity/actor/loli/typhoea/models/*.json`
- 输出到 `FractalMiner/Assets/Typhoeus/_typhoea_model_data.json`

这些中间文件本机存在，但名称像 `_test` 并不表示没用。不要清理它们。如果从零重新导出，先把新产物放在新的练习目录并核对结构，修改**练习副本**中的这四个路径，再运行构建脚本；不要先覆盖已经验收的统一 JSON。

运行前手工检查：`bonePathsStr`、`bonePaths[].boneIdxs`、每个 Mesh 的 `m_Vertices/m_Normals/m_UV0/m_Indices/m_SubMeshes/m_Skin/m_BoneNameHashes/m_BindPose` 是否齐全。运行后检查 481 根骨骼、17 个 Mesh 是否仍与**本批**数据相符；未来版本不同不能靠硬编码补齐到这两个数字。

## 6. 离开本章前必须留下的四样东西

1. **环境表**：Unity、URP、Python、导出器版本及完整依赖列表；游戏原始目录、捕获文件、数据批次哈希。
2. **资产表**：每个部件/材质/纹理的来源和绑定，不确定项单独列出。
3. **执行日志**：命令、工作目录、起止时间、退出码、警告、输出目录。记录“没有执行”的步骤，避免未来误当作已验收。
4. **练习结果**：自己写出的网格计数/范围检查程序，以及一个故意错误输入会失败的例子。

无助手时的恢复顺序是：打开自己的环境表 → 检查目录仍存在 → `git status` 和记录分支最新提交 → 运行只读资产检查 → 找第一个失败阶段 → 只重做该阶段。错误在 Mesh 层时不要开始调曝光；没有找到共享纹理时不要靠刷基础颜色填空。

下一章：[02｜网格、骨骼、材质重建与防炸验证](</A:/Hypergryph Launcher/games/Arknights Endfield/FractalMiner/docs/learning/02-mesh-material-reconstruction.md>)。
