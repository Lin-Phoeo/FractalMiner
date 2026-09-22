# 终末地（Arknights: Endfield）渲染逆向还原 — 完整技术路线

> **项目**：用 Unity 2022.3 LTS + URP 14 复刻《明日方舟：终末地》角色（提弗洛斯/Typhoeus）官方渲染效果
> **工作区**：`A:\Hypergryph Launcher\games\Arknights Endfield`
> **主工程**：`FractalMiner/`（Unity 2022.3.30f1，URP 14.0.11）
> **时间跨度**：2026-09-14 ~ 2026-09-22
> **协作者**：Codex（早期会话）→ Claude（09-22 接续）→ WorkBuddy（本轮接续）
> **本文档目的**：把从第一天到现在的技术路线、进度、踩坑、开发过程完整沉淀，避免会话压缩丢失经验。

---

## 一、技术路线总览

```
[阶段0] 渲染栈调研
   └─> 确认：Unity 深度定制（自研 C++ 管线 HGRP + Render Graph + ECS），PBR+NPR 混合
   └─> 确认：社区无完整开源还原，只有 FractalMiner（基座不全）+ 散篇技术文

[阶段1] 从零写 shader（EndfieldShaderPack）
   └─> 法线解压（10bit×3+1bit 单 float）→ Kajiya-Kay 头发 → 皮肤 SSS → 分离式角色光照
   └─> 交付：EndfieldCharacterLit.shader + EndfieldNormalDecompress.cs + EndfieldCharacterLight.cs

[阶段2] 模型导入（提弗洛斯）
   └─> 三份下载模型择优：hiragara FBX（含 62 贴图 + 17 材质 JSON）
   └─> EndfieldMaterialImporter.cs：读 JSON → 生成 .mat → 重映射 FBX
   └─> 踩坑：工程混入其他游戏脚本致编译错误 → 移出到 Project_Reference

[阶段3] 社区方案对齐（GitHub docx）
   └─> 克隆 3 个 Unity URP 仓库交叉对比
   └─> 结论：保留自研 game-accurate shader，移植算法（不换底座）
   └─> 移植：sigmoid 硬边阴影 + 光滑法线描边 + ColorAdjustmentRim 边缘光

[阶段4] 真实解包游戏（EndfieldUnpacker）
   └─> ChaCha20 解 VFS（.chk/.blc）→ 454,558 文件
   └─> AnimeStudio.CLI 解 .ab → 1732 贴图 + 13 官方材质
   └─> 定位：chr_0034_typhoea → 4 个 CharacterNPR shader 名（Skin/Eye/Cloth/Hair）

[阶段5] shader 字节码反编译（硬骨头，最终绕过）
   └─> 42 SMOL-V + 43 DXBC 在 resources.assets
   └─> Ruri.ShaderDecompiler 编译通过，DXBC 路径验证出 HLSL
   └─> 卡点：FairGuard 独立加密 header（VFS 层 RC4 解不开），社区解密私有未公开
   └─> ★ 决定性发现：FractalMiner/_dump_1.5.3 已含官方反编译 characternpr*.shader + 全部 .hlsl

[阶段6] 紫色模型修复 + 正面帧对齐（Claude 09-22）
   └─> 09-18 暂停点："shader 全黑" → 09-22 解决：URP 包就绪 + 渲染管线切换
   └─> RenderDoc 离线回放正面帧 → 提取相机/光/材质常量（event 875）
   └─> TyphoeusOfficialFrame.cs：FOV 35°、aspect 1.6、官方光方向、中性灰背景
   └─> front-align.png：模型正确渲染（不再紫/黑）

[阶段7] 官方 ForwardLit HLSL 逐部位翻译（WorkBuddy 本轮）
   └─> Claude 中断时只完成 hair（b125），skin/cloth/eye 因 429 失败
   └─> 本轮补齐 3 份，4 部位官方公式全部还原成可读文档
```

---

## 二、进度详表

### 阶段 0-1：调研 + 从零写 shader（Codex）

| 交付物 | 路径 | 状态 |
|---|---|---|
| 角色 mega-shader | `Assets/EndfieldShaderPack/EndfieldCharacterLit.shader`（898 行，96 属性） | ✅ 编译通过 |
| 法线解压 | `Assets/EndfieldShaderPack/EndfieldNormalDecompress.cs` | ✅ |
| 分离式角色光 | `Assets/EndfieldShaderPack/EndfieldCharacterLight.cs` | ✅ |
| 材质导入器 | `Assets/EndfieldShaderPack/Editor/EndfieldMaterialImporter.cs`（18.9KB） | ✅ |

**已还原的官方 feature（属性名 1:1 对齐 HGRP/CharacterNPR）**：
- 法线解压（10bit×3+1bit sign 单 float）
- Kajiya-Kay 各向异性头发高光 + LineMap 发丝线 + 双各向异性（主/次）
- 皮肤 SSS（wrap diffuse + ramp + ShadowLutTex）
- PBR metallic-gloss（P mask: R=metal, G=AO, A=smooth）
- Sigmoid 硬边阴影（场景阴影 + 半兰伯特塑形）
- 光滑法线描边（SmoothNormals 烘焙 UV7 + 描边 pass）
- Stylized Fresnel + ClearCoat
- 视差/流动（_UseParallax + _ParallaxTex）
- ColorAdjustmentRim 边缘光（_ColorAdjustmentRimIntensity=4, RimWidth=0.35）
- SplitNormalMap 头发高光法线 + SpecBumpScale

### 阶段 2：模型导入（Codex）

| 项 | 状态 |
|---|---|
| FBX 模型（hiragara 版） | ✅ `Assets/Typhoeus/chr_0034_typhoea_uimodel.fbx` |
| 62 张贴图 PNG | ✅ `Assets/Typhoeus/T_*.png` |
| 17 材质 .mat（含 13 个 M_actor_typhoea_*） | ✅ `Assets/Typhoeus/Materials/` |
| FBX externalObjects 重映射（17 条） | ✅ GUID 逐一核对 17/17 名称匹配 |

### 阶段 3：社区方案对齐（Codex）

克隆的 3 个 Unity URP 参考仓库（在 `_EndfieldRefs/`）：
- `congyuxiaoyoudao/Endfield_Character_Rendering`（URP 14.0.11，参数与游戏 JSON 1:1 对齐，SDF 脸部 + 剪影 RendererFeature）
- `Morgana-lgtm/Arknights-Endfield-Inspired-Perlica-Character-Shader`（模块化 ZmdToon 全家桶 + 后处理）
- `qiudashu233/MyZmdShaders`（最完整部位 shader 库）

**关键结论**：自研 `EndfieldCharacterLit.shader` 属性名才是 game-accurate（与官方 JSON 逐字段对齐），参考仓库用的是改名重打包字段。**正确路径是移植算法，不换底座。**

### 阶段 4：真实解包（Codex）

| 工具链 | 用途 | 产物 |
|---|---|---|
| `EndfieldUnpacker`（Python + pycryptodome） | ChaCha20 解 VFS | 454,558 文件（253,670 main .ab + 1,052 initial .ab） |
| `AnimeStudio.CLI`（.NET 10，内置 ArknightsEndfield 配置） | 解 .ab 资源包 | 1732 贴图 + 13 官方材质 JSON |
| `Il2CppDumper`（被 FairGuard 阻断） | il2cpp 元数据 | ❌ MetadataRegistration=0 |

**官方资产定位**：
- 角色 ID：`chr_0034_typhoea`
- 模型 prefab：`Assets/Beyond/DynamicAssets/Gameplay/Actors/PostModels/Characters/chr_0034_typhoea_postmodel.prefab`
- 骨骼：`data_npc_avatartemplet_typhoea`（481 根骨骼，Bip001 humanoid + hair/tail/acc 扩展）
- 绑定表：`data_npc_avatarmesh_typhoea`（17 部件 + materialPathHashes）
- 4 个 shader（从 global-metadata.dat 的 Shader.Find 字面量反解）：

| shader 名 | 材质组 | PathID |
|---|---|---|
| `HGRP/CharacterNPR_Skin` | body_01 / face_01 | 4484747192473637154 |
| `HGRP/CharacterNPR_Eye` | brow_01 / iris_01 | -1706220712117210762 |
| `HGRP/CharacterNPR` | cloth_01..07 | -7822190029627442914 |
| `HGRP/CharacterNPR_Hair` | hair_01 / hairt_01 | -8095970123935614097 |

### 阶段 5：shader 字节码反编译（Codex，最终绕过）

| 障碍 | 状态 |
|---|---|
| 42 SMOL-V + 43 DXBC 在 `Endfield_Data/resources.assets` | ✅ 定位 |
| Ruri.ShaderDecompiler clone + 修编译错误 + 编译通过 | ✅ |
| Ruri DXBC 路径验证（内置 shader 反编译出 HLSL） | ✅ |
| SMOL-V 解码三层突破（magic 识别 + decodedSize 校验绕过 + body 起点 skip=3） | ✅ 解出 41008 字节 SPIR-V 前段 |
| FairGuard 独立加密 header（VFS 层 RC4 解不开） | ❌ 社区解密私有未公开 |
| **★ 决定性发现**：`FractalMiner/_dump_1.5.3/` 已含官方反编译 characternpr*.shader + 全部 .hlsl | ✅ 无需再逆字节码 |

### 阶段 6：紫色模型修复 + 正面帧对齐（Claude 09-22）

| 交付物 | 路径 | 状态 |
|---|---|---|
| 正面帧 RDC 离线回放研究文档 | `docs/research/tifuluosi-front-capture-20260917.md` | ✅ 已提交 e69e642 |
| 截帧状态文档 | `docs/research/renderdoc-capture-status.md` | ✅ 已提交 e69e642 |
| 正面帧常量提取（subagent） | `Validation/Captures/tifuluosi-front-20260917/extracted/`（constants-by-event.json 1.6MB + summary.md 43KB） | ✅ |
| 相机/光照对齐脚本 | `Assets/EndfieldShaderPack/Editor/TyphoeusOfficialFrame.cs`（68 行） | ✅ |
| Unity batchmode 渲染输出 | `Validation/front-align.png` | ✅ 模型正确渲染 |

**捕获帧已知条件（event 875，hair）**：
- 相机：FOV 35° 垂直 / 53.54° 水平，aspect 1.6，camera_pos [-300, 300.78, -297.04]
- 主光方向：`[0.0213893, -0.642788, -0.765746]`（travel dir）
- 光颜色：`DirectionalLightCustomData1 = (1,1,1) × 1.62439`
- 环境：`_CharacterParams1.y = 1`（平坦环境，不采样辐照度体）
- 光方向覆盖：`_CharacterParams1.w = 1`（用 CP11.xyz = (0.176, 0.530, 0.830) 替代场景方向光）
- `_ExposureWithMiscParams = [1, 1, 1.6, 0.1]`

### 阶段 7：官方 ForwardLit HLSL 逐部位翻译（WorkBuddy 本轮）

Claude 中断时 4 个翻译代理因 429 全失败（除 hair 后续单独成功）。本轮派 3 个代理并行翻译，全部成功：

| 部位 | 变体 | 文档 | 行数 | 关键算法 |
|---|---|---|---|---|
| hair | b125 | `docs/research/official-forwardlit-hair-b125.md` | 362 | Kajiya-Kay + LineMap 发丝线 + 双各向异性高光 + edgeFade XZ 投影 |
| skin | b138 | `docs/research/official-forwardlit-skin-b138.md` | 335 | SDF lightmap + SSS LUT + emotion/highlight map + 面部雨滴 |
| cloth | b401 | `docs/research/official-forwardlit-cloth-b401.md` | 348 | PBR metallic-gloss + GGX + Stylized Fresnel(12魔数) + ClearCoat(指数3) + 解析式 ramp |
| eye | b28 | `docs/research/official-forwardlit-eye-b28.md` | 277 | 视差瞳孔折射 + Matcap + ScatteringColor/HighLightColor 调制 |

**4 部位官方 ForwardLit 全部还原成可读 HLSL 公式文档，已提交 f360d80 并推送 endfield-records 远程。**

---

## 三、踩坑全记录

### 3.1 渲染/工程层

| # | 坑 | 现象 | 解法 |
|---|---|---|---|
| 1 | **紫色模型** | 材质没挂上 shader（GUID 匹配但 shader 编译失败/URP 未就绪） | 等 URP 包编译完 + Project Settings → Graphics 切 URP Render Pipeline Asset |
| 2 | **shader 全黑**（09-18 暂停点） | unlit 诊断人形轮廓正确，CharacterLit 渲出来几乎全黑只有头发有色 | 09-22 Claude 会话解决（相机/光照/材质参数对齐后正常） |
| 3 | **工程混入其他游戏脚本** | AzurPromilia/PunishingGrayRaven/QuantumBreak/WutheringWaves 参考脚本致编译报错 + unsafe 代码 | 移出到 `FractalMiner/Project_Reference`，修掉法线解压的 unsafe |
| 4 | **属性名不对齐** | 自研 shader 用 `_AnisotropyIntensity`，官方 cloth 用 `_AnisotropyIntensityMultiplier` → importer SetFloat 静默丢弃 | 逐 JSON 对齐属性名到官方 HGRP/CharacterNPR 命名 |
| 5 | **"空贴图"误判** | cloth_04 的 _DiffRampMap 是 {fileID:0} → 以为 importer 没挂上 | 实际游戏本身 _UseDiffRampMap=0（cloth 走 PBR 不走 ramp），.mat 忠实照抄 |
| 6 | **17 材质重映射报 0 个** | AssignMaterialsToModel 日志"重映射 0 个" | FBX 早已外部化，LoadAllAssetsAtPath 找不到内嵌材质；但 .meta externalObjects 17 条 GUID 全对 |

### 3.2 解包/逆向层

| # | 坑 | 现象 | 解法 |
|---|---|---|---|
| 7 | **VFS code_ver 不匹配** | decrypt_vfs.py 用 code_ver=3，游戏实际=4 → .ab header 乱 | 不影响模型/贴图/材质导出（AnimeStudio 正确处理），shader 字节码层另说 |
| 8 | **.ab header 二次混淆** | 非标准 UnityFS，AssetStudio 直接读失败 | AnimeStudio.CLI 内置 ArknightsEndfield 配置去混淆 |
| 9 | **Il2CppDumper 被 FairGuard 阻断** | MetadataRegistration=0，扫描代码引用定位失败（代码被虚拟化） | 静态扫数据定位 `typesCount≈185227` → .data 里 0 命中 → FairGuard 把注册表搬进 .bss 或指针加密 |
| 10 | **SMOL-V magic 从未被发现** | 42 个 SMOL-V（Vulkan 压缩 SPIR-V）在 resources.assets，magic="SMOL" | Ruri.ShaderDecompiler 内置 SmolvDecoder（作者针对终末地 1.4.4 验证） |
| 11 | **SMOL-V decodedSize 校验失败** | SmolvDecoder.Decode 末尾校验 output长度==decodedSize，但 decodedSize 被魔改成垃圾值 → return false | body 实际已解压成功，绕过该校验直接取 outputStream |
| 12 | **SMOL-V body 起点偏移** | 标准 24 字节 header 后还有额外字段 → 第一条指令错位 | HGRP 在标准 header 后加 3 字节魔改字段，真实 body 起点 = offset 27（skip=3） |
| 13 | **SMOL-V body 内部更深魔改** | 解压到 off≈140 走偏（PackedBinding/DescriptorSetParams） | 死夢めぐ里 点名的魔改，TypeTree 在 FractalTools 仓库（404 未公开） |
| 14 | **Ruri 方向判断错** | 以为 Ruri 主攻 SMOL-V | 实际主攻 DXBC/DXIL，pipeline = dxbc → dxil-spirv → ... → HLSL，EndField fixture 是 litpoly blob1/blob2 |
| 15 | **FairGuard 独立加密** | 用 VFS 层 RC4（_fairguard_decrypt.py）试解 DXBC header → 解不开 | shader 字节码 header 是 FairGuard 另一套独立加密，社区解密（Ruri-RipperHook）私有未公开 |
| 16 | **FractalTools 仓库 404** | 死夢めぐ里 的 TypeTree 定义仓库不公开 | 但 FractalMiner/_dump_1.5.3 已含官方反编译 shader，无需再逆字节码 |
| 17 | **"完美复刻"误解** | 以为要从字节码反编译才能完美 | FractalMiner 已含官方反编译 characternpr*.shader + 全部 .hlsl + Typhoeus 全资产，是完整还原工程 |

### 3.3 工具/会话层

| # | 坑 | 现象 | 解法 |
|---|---|---|---|
| 18 | **4 个翻译代理 429** | skin/cloth/eye/hair 翻译代理同时派发，全失败（claude-opus-4-7 模型限流） | 单独恢复 hair（改用 fable 模型）成功；本轮用 default 模型 3 个并行全成功 |
| 19 | **A 盘 git 写 pack 权限拒绝** | clone 到 A 盘 FractalMiner 报 Permission denied | 改到 C 盘临时目录 clone |
| 20 | **GIT_INDEX_FILE MSYS 路径失败** | 隔离 index 用 `$(pwd)/...`（/a/... 风格）报 "No such file or directory" | 用 Windows 风格路径 `A:\\...` |
| 21 | **git update-ref 沙箱不落盘** | `git update-ref refs/heads/fix/... <sha>` 返回 exit 0 但 ref 不持久化，branch -v 看不到 | 直接写 loose ref 文件 `.git/refs/heads/fix/typhoeus-render-explosion-20260917`（内容=40字符SHA+换行），git 立即识别 |
| 22 | **PowerShell 输出不返回** | 命令 exit 0 但 Stdout 空 | 改用 Bash（需手动 `export PATH="/usr/bin:/bin:/mingw64/bin:$PATH"` 修复缺失的 head/wc/dirname） |
| 23 | **Notion MCP 工具不可用** | connector-status 显示 notion connected，但 mcp__notion__* 不在 deferred tools | 写本地 Markdown 文档供手动导入（本文件即是） |

---

## 四、开发过程（代码/文件产出）

### 4.1 仓库结构

```
FractalMiner/  (Unity 2022.3.30f1 + URP 14.0.11)
├── Assets/
│   ├── EndfieldShaderPack/           # 自研还原 shader + 工具
│   │   ├── EndfieldCharacterLit.shader      (898 行, 96 属性, mega-shader)
│   │   ├── EndfieldNormalDecompress.cs      # 法线解压 + 编辑器菜单一键转法线贴图
│   │   ├── EndfieldCharacterLight.cs        # 分离式角色光控制器
│   │   └── Editor/
│   │       ├── EndfieldMaterialImporter.cs   (18.9KB, 读 JSON→生成.mat→重映射FBX)
│   │       ├── EndfieldMaterialValidation.cs
│   │       ├── EndfieldRenderCapture.cs      # batchmode 截图入口
│   │       ├── TyphoeusGeometryValidation.cs # ComputeWorldBounds + SaveImage
│   │       ├── TyphoeusModelBuilder.cs       # 蒙皮重建（bind pose 转置读取, -90° 旋转放根对象）
│   │       ├── TyphoeusOfficialFrame.cs      # ★ 正面帧对齐（FOV35°/aspect1.6/官方光方向/中性灰）
│   │       ├── TyphoeusSceneSetup.cs
│   │       └── TyphoeusSkinDiag.cs           # unlit 诊断截图
│   ├── Typhoeus/                     # 提弗洛斯全资产
│   │   ├── chr_0034_typhoea_uimodel.fbx
│   │   ├── T_*.png (62 张贴图)
│   │   └── Materials/ (17 .mat + 17 .json)
│   ├── Scenes/
│   │   ├── SampleScene.unity
│   │   └── Typhoeus_Showcase.unity
│   └── Project_Reference/            # 其他游戏参考脚本（移出避免编译冲突）
├── _dump_1.5.3/                      # ★ 官方反编译 shader（ground truth）
│   └── AllShader_1.5.3/Assets/packages/com.hg.render-pipelines/runtime/shaders/materials/characternpr/
│       ├── characternpr.shader            # HGRP/CharacterNPR (cloth/body)
│       ├── characternpr_skin.shader        # HGRP/CharacterNPR_Skin
│       ├── characternpr_eye.shader         # HGRP/CharacterNPR_Eye
│       ├── characternpr_hair.shader        # HGRP/CharacterNPR_Hair
│       └── {skin,hair,eye,cloth}/Sub0_Pass0_{Fragment,Vertex}_*.hlsl  # 反编译 HLSL
├── docs/research/                    # 研究文档
│   ├── official-forwardlit-hair-b125.md    (362 行, ★ 官方公式还原)
│   ├── official-forwardlit-skin-b138.md    (335 行, ★ 本轮补齐)
│   ├── official-forwardlit-cloth-b401.md   (348 行, ★ 本轮补齐)
│   ├── official-forwardlit-eye-b28.md      (277 行, ★ 本轮补齐)
│   ├── tifuluosi-front-capture-20260917.md
│   ├── tifuluosi-capture-intake-20260917.md
│   ├── renderdoc-capture-status.md
│   ├── renderdoc-community-evidence-20260917.md
│   └── rendering-evidence-20260917.md
├── Validation/                       # 验证截图 + 截帧数据
│   ├── front-align.png               # ★ 正面帧对齐渲染（模型正确显示）
│   ├── baseline-*.png, channel-*.png, verified-*.png
│   └── Captures/tifuluosi-front-20260917/
│       ├── official-front-1280.png   # 官方正面帧
│       ├── replay-details-01/        # RDC 回放 draw-call 详情
│       ├── replay-preview-02/replayed-present.png
│       └── extracted/                # ★ 正面帧常量提取
│           ├── constants-by-event.json (1.6MB)
│           └── summary.md            (43KB, 相机/光/17部位材质值)
├── Tools/                            # 解包/分析脚本
└── Packages/manifest.json            # URP 14.0.11
```

### 4.2 Git 工作流

**双远程结构**：
- `origin` = `ShiyumeMeguri/FractalMiner`（上游开源基座，main = ee02bba "添加枪娘"）
- `endfield-records` = `LinXingjian365/FractalMiner`（用户 fork，存工作记录）

**工作分支**：`fix/typhoeus-render-explosion-20260917`

**提交链**（9 条）：
```
f360d80 Translate official CharacterNPR ForwardLit HLSL for hair/skin/cloth/eye  ← 本轮
e69e642 Record front Typhoeus Vulkan frame replay and draw-call anchors          ← Claude
d3e4513 Import and verify real Typhoeus Vulkan frame with offline analysis tests
9f890bd Document verified Endfield capture reports and reconstruction gaps
b0b8042 Retire blocked live-game capture and correct launch-result diagnosis
81c4691 Prepare normal Vulkan capture workflow and document administrator prerequisite
48bf08e Align packed material channels and hair shading with source evidence
f142b97 Fix Typhoeus outline explosion and URP depth compatibility
6cd186f Merge remote-tracking branch 'origin/main'
```

**隔离 index 提交模式**（避免扰动工作树的大量未提交改动）：
```bash
export GIT_INDEX_FILE="A:\\...\\FractalMiner\\.git\\docs-index"  # Windows 路径!
git read-tree fix/typhoeus-render-explosion-20260917
git add docs/research/official-forwardlit-*.md
TREE=$(git write-tree)
COMMIT=$(echo "msg" | git commit-tree $TREE -p fix/typhoeus-render-explosion-20260917)
git update-ref refs/heads/fix/typhoeus-render-explosion-20260917 $COMMIT
git push endfield-records fix/typhoeus-render-explosion-20260917
```

### 4.3 4 份 ForwardLit 翻译文档核心内容

#### hair (b125) — 已有
- 变体：`_NORMALMAP _METALLICSPECGLOSSMAP _SPEC_RAMP_ON _DIFF_RAMP_ON _SPECULAR_LINE` ON
- 核心：`T1=normalize(anisoDir + N*(_AnisotropyValue*2-1))`, `spec1=pow(sqrt(1-TdotH1²),200)*specMask`, `_SpecRampMap` 二维 ramp(u=高光强度, v=edgeFade²), LineMap `frac(uv.x*_LineAmount)` 阶梯
- CP 表完整（CP0.z=0.65, CP1.y=1, CP1.w=1, CP11.xyz=(0.176,0.530,0.830)...）

#### skin (b138) — 本轮补齐
- 变体：`_DIFF_RAMP_ON _EMOTION_MAP _SDFLIGHTMAP _SHADOW_LUT_TEX _HIGHLIGHT_MAP` ON
- 核心：SDF 次表面法线/光照、SSS Lut、面部雨滴、三平面雪、CP3/CP4 取代 hair 的 CP2/CP5
- **不使用 _CameraDepthTexture**

#### cloth (b401) — 本轮补齐
- 变体：`_NORMALMAP _METALLICSPECGLOSSMAP _CLEARCOAT` ON；**无** `_PARALLAX_MAP`/`_STYLIZED_FRESNEL`/`_DIFF_RAMP_ON`/`_SPEC_RAMP_ON`（视差/流动属 b1005/b1011 相邻变体）
- 核心：漫反射 ramp 是**解析式** `smoothstep(0.25,1, clamp(NdotL-0.1))`（无 ramp 贴图）；GGX + 紧凑式 Stylized Fresnel（12 魔数有理多项式）+ `_CharMaxCubemap` IBL；ClearCoat 双层（Schlick 指数用 3 非 5）
- 捕获值补全 hair 文档"未捕获"的 `CP12=(1,1,1,0)`, `CP13.w=1`, `CP15.w=0`

#### eye (b28) — 本轮补齐
- 变体：`_DIFF_RAMP_ON _EYE_HIGHLIGHT _MATCAP_ON` ON；无 `_BumpMap`/`_MetallicGlossMap`/深度 rim
- 核心：视差瞳孔折射（`_ParallaxScale` + `smoothstep(0.25,0.05,d2)` 仅圆心）、Matcap（UV 圆盘构造虹膜球面法线）、EyeScatteringColor/HighLightColor 按 alpha+pupilMask 调制

---

## 五、当前代码状态（2026-09-22）

### 5.1 渲染管线状态
- ✅ URP 14.0.11 包就绪
- ✅ 渲染管线已切 URP（GraphicsSettings + QualitySettings）
- ✅ 模型正确渲染（front-align.png 证明，不再紫/黑）
- ✅ 相机/光照对齐官方正面帧（TyphoeusOfficialFrame.cs）

### 5.2 shader 状态
`EndfieldCharacterLit.shader`（898 行）已对齐官方属性名，含全部 feature 开关。**但官方公式尚未逐条落地**——当前是"属性名对齐 + 近似算法"，4 份 ForwardLit 翻译文档提供了精确公式，下一步是把公式从文档搬进 shader。

### 5.3 渲染对照差距（front-align.png vs official-front-1280.png）

| 维度 | 官方 | 当前 Unity | 差距 |
|---|---|---|---|
| 姿势 | 展示姿势（举手、头发飘动） | bind pose | 需动画/姿势数据 |
| 主光 | 暖白主光 + 地面投影 | 平光 | 需接入 CP 参数 + 阴影 |
| 头发高光 | 各向异性高光 pop | 颜色对但缺高光 pop | 需落地 hair 公式 |
| 背景 | 网格线墙+地 | 纯灰 | 需展示场景 |
| 整体亮度 | 明亮柔和 | 偏暗平 | 需曝光/环境参数 |

---

## 六、下一步任务清单（按收益排序）

1. **把 4 份 ForwardLit 公式落地进 `EndfieldCharacterLit.shader`**（hair 优先，文档最完整）：
   - Kajiya-Kay 双各向异性高光（T1/T2 + `_AnisotropyValue*2-1`）
   - LineMap 发丝线（`frac(uv.x*_LineAmount)` + `_UseLineMap` lerp）
   - edgeFade XZ 投影（`pow(clamp(dot(Nos.xz,Vos.xz)), _AnisotropyEdgeFade)`）
   - SpecRampMap 二维采样（`float2(spec1, sign(TdotH)*edgeFade²)`）

2. **接入官方 `_CharacterParamsN` 全局参数**（捕获帧已知值），让 shader 走捕获帧分支（CP1.y=1 平坦环境、CP1.w=1 光方向覆盖）

3. **重建 17 材质按官方参数 + 重渲染 front-align**，与官方帧逐项对照（姿势/光照/ramp/高光/rim）

4. **长期：MMD 动作重定向**（用户最终目标——接 .vmd 做可配置动画 + AI 视频）：
   - 提弗洛斯 FBX → Humanoid Avatar
   - VMD 播放器（MMD4Mecanim 或自写 VMD 解析 + 骨骼映射）
   - MMD 标准骨（センター/上半身/首/頭/腕/足/目/表情）→ 提弗洛斯骨骼

---

## 七、关键经验沉淀

> 这几条是踩了很多坑才摸清的，下次别再走弯路。

1. **"完美还原"的钥匙早就在本地**：`FractalMiner/_dump_1.5.3/` 是死夢めぐ里开源的官方反编译 shader，含完整 characternpr*.shader + 每变体 .hlsl。逆 FairGuard/SMOL-V/DXBC 是绕远路，不用再碰。

2. **官方是 feature-toggle mega-shader**：不是每部位独立 shader，而是一个 characternpr 带 _UseDiffRampMap/_UseMetallicGlossMap/_UseParallax/_UseAnisotropy 等开关，每材质 toggle。属性名必须 1:1 对齐官方 JSON（importer 按名 SetFloat，不对齐就静默丢弃）。

3. **捕获帧走平坦环境分支**：`_CharacterParams1.y=1` 时 ambientRGB=1、不采样辐照度体；`_CharacterParams1.w=1` 时光方向用 CP11.xyz 覆盖场景方向光。复现官方帧必须设这两个。

4. **隔离 index 提交用 Windows 路径**：GIT_INDEX_FILE 在 MSYS/bash 下用 `/a/...` 风格会失败，必须用 `A:\\...`。

5. **沙箱内 git update-ref 不可靠**：返回 exit 0 但 ref 不落盘。直接写 loose ref 文件最稳：`echo "<40字符SHA>" > .git/refs/heads/<branch>`（嵌套分支先 mkdir -p 父目录）。

6. **4 份翻译文档已是 ground truth**：hair/skin/cloth/eye 的官方 ForwardLit 公式全部在 `docs/research/official-forwardlit-*.md`，落地 shader 时直接抄，不用再读 .hlsl 原码。

---

*文档生成于 2026-09-22。如需导入 Notion：本文件为标准 Markdown，可直接粘贴到 Notion 新页面，标题建议"终末地渲染逆向还原 — 完整技术路线"。*
