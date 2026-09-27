# 终末地提弗洛斯主线路线图 + 阶段 0 实施计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.
> 本文件 = 主线路线图（§A，规格）+ 阶段 0 的逐步实施计划（§B）。主线横跨三个独立子系统，按 writing-plans 规则**一个子系统一份计划**：阶段 1–3 的逐步计划在各阶段开工时写（每个阶段的第一个工作包是"测量/归因"，它的结果决定后续具体改法，现在写具体 shader/代码改动只能是猜）。

**Goal:** 在 Unity 2022.3.30f1 / URP 14 上让提弗洛斯整帧画面对官方帧 6411 过门禁、MMD（VMD 动作 + 相机）37.7 秒全片可重复离线出片并过动作门禁；然后把收敛后的基线迁到 Unity 6 并重过全部门禁。

**Architecture:** 三条线共用"门禁驱动"：先定量测差距 → 按差距来源拆工作包 → 每个工作包先写会失败的门禁再改实现。渲染真值 = 帧 6411 RenderDoc 捕获 + 官方反编译 shader；动作真值 = UMT（MIT）与 mmd-anim（MIT）双参照；社区项目只作线索不作真值。Unity 6 迁移在 2022 基线全绿后、于工程副本上进行。

**Tech Stack:** Unity 2022.3.30f1 → Unity 6.3 LTS（或届时最新 LTS）、URP 14 → URP 17 RenderGraph、C# / HLSL、Python 3.12（`Tools/tests`、`D:\MmdOracle` 脚本）、RenderDoc / RenderDuck、UMT、mmd-anim（Rust）。

**Spec:** 本文件 §A 即规格。证据：`HANDOFF-2026-09-27-mmd-research-closure.md`（含 09-27 18:00 复验段）、`docs/research/mmd-integration-research-20260926.md`、`../_agent_experience.md`、2026-09-27 只读现状调研（结论已并入 §A.1）、用户提供的 `C:\Users\Administrator\Downloads\整理终末地开发书签.md`（已逐仓库核验，见 §A.7）。

## Global Constraints

- 基线固定 Unity 2022.3.30f1、URP 14.0.12（manifest；PackageCache 实为 14.0.11），直到阶段 3 开工。
- 不重复造轮子：新模块先检索现成方案，在阶段计划或 HANDOFF 写明用 / 不用的理由（`_agent_experience.md` §〇）。
- 冻结模块不改：`EndfieldCapturedBloom`、`EndfieldCapturedPost.shader`、`EndfieldCapturedPostFeature`、`EndfieldCapturePipelineValidation`。唯一例外是阶段 3 的 RenderGraph 移植，且必须逐位复现原门禁。
- 门禁阈值只能收紧，不能放宽。
- 真值数据（`*.rdc`、`Validation/Captures`、`Assets/EndfieldShaderPack/GeneratedCapture`、`D:\MmdOracle`、`Documents\EndfieldMmdSourceRigs`）不进 Git；第三方 PMX / VMD / 游戏资源不提交。
- Git：`main` 工作区不 checkout / reset / clean / `git add .`；提交一律走临时 `GIT_INDEX_FILE` → 记录分支 `fix/typhoeus-render-explosion-20260917` → 远端 `endfield-records`。
- Unity 批处理：交互式 Editor 关闭时才跑；`_unity_bridge.bat`（必须 CRLF）+ `MSYS_NO_PATHCONV=1 schtasks /run /tn EndfieldUnityBridge`；用完恢复为只编译载荷。
- 所有按名字的骨骼查找锚定重建角色根 `chr_0034_typhoea_rebuilt`（场景里停用的 `Typhoeus_SourceFBX` 有同名 Bip001）。
- 许可证：`VmdMotion`、`VmdCamera`、`MmdRig`、`MmdRetarget`、`MmdPlayer` 派生自 AGPL Endfield-Poser；无许可证的社区仓库只作参考，不拷代码。
- subagent 同一时间最多 1 个；当前网关下 WebSearch / WebFetch 不可用，检索用 `ddgs` / `trafilatura` / `gh api`。

## Review Focus

1. 捕获管线仍处于激活状态（`Library/EndfieldCapturedPipelineActivation.json` 存在、Ultra 档指向 `f351…`）时做清理或迁移，会把 ProjectSettings 改坏 → 阶段 3 入口测试：激活状态文件不存在且 QualitySettings 指回原管线，否则拒绝开工。
2. 只用帧 6411 调参会过拟合 → 阶段 1 出口要求至少一个**不参与调参**的验证帧 / 视角，记录其同阈值结果。
3. 按名字查骨误命中停用的 `Typhoeus_SourceFBX` → 阶段 2 的 `MmdSession` 测试：在两套同名骨同时存在的场景里，解析出的每根骨都是重建根的后代。
4. 离线出片不确定（物理步长、帧时间）导致两次渲染不同 → 阶段 2 出口测试：同输入两次出片逐帧像素哈希一致。
5. VMD 相机未加载却通过烟测（当前烟测 loadInfo 为 0 镜头帧） → 阶段 2 WP2.1 测试：烟测断言相机帧数 > 0，且与 UMT 相机逐帧误差在门禁内。

---

# §A 主线路线图

## A.1 现状（2026-09-27 实测 / 调研，数字即起点）

| 线 | 已闭合 | 未闭合（起点数字） |
|---|---|---|
| 渲染 | 后处理（官方 HDR 输入）平均 0.12 色阶、100% 在 1 色阶内；Bloom 相对 L1 2.7e-4；环境 cube mip0 MAE ≤2.1e-4；自阴影 resolve 逐字节 99.84%；M5 几何误差 0 | 帧 6411 整帧：轮廓 IoU **0.765**（门 ≥0.85）；头 / 躯干 / 腿 MAE **29.3 / 20.5 / 24.0** 色阶（门 ≤4）；p95 **111 / 89 / 95**（门 ≤16）；8 色阶内比例 **0.27 / 0.48 / 0.46**（门 ≥0.9）。有符号均值只有 +4 / +2 / +2，是分区域误差，不是全局增益 |
| MMD 源端 | VMD 插值 / 相机格式修复；1131 帧对 UMT 位置 P95 0.145 / 0.114 mm；相机对 UMT 最大 0.25 mm / 0.13° | 共享 IK 链无实测；UMT baked-FK 未接生产 |
| MMD 目标端 | 55 role → Bip001 retarget、腿 IK、5 点烟测 PASS | 接地只有整体抬升（最低顶点 -0.158 m）；脸 0 个 blendshape（85 个脸部关节走 SMC 骨骼偏移，现有 `MmdFace` 无效）；无次级物理；烟测未加载相机；37.7 s 全片从未出片；Studio / Batch / Smoke 初始化三处重复 |
| Unity 6 | — | 3 个 renderer feature 全走 Execute 兼容路径，0 个 RecordRenderGraph；`FindObjectOfType` 31 处；私有字段 `m_RendererDataList`；`camera.Render` 离线出片在 RenderGraph 下行为未知；6.3 起兼容模式被隐藏 |

渲染缺口清单（来源：现状调研）：八面体平滑法线（存于 UV，`character-shadow-evidence-20260923.md` §9.4）未接入——注意这与上游作者（ShiyumeMeguri）B 站简介说的"没有实现法线解码函数"不是一回事，后者指法线贴图解码（X=A·R、Y=G、Z 重建），本工程已于 09-17 修正（`_agent_experience.md` §三.1）；145 根骨停在 bind 姿态；书本道具缺失且官方 mask 在 y≤0.83 截断；描边颜色是简化公式；覆盖层、刘海 / 头发阴影、dither、透明未做；方向阴影未验证（6411 的 R 通道恒为 1）；雾、局部灯、湿润、眼部边缘光未做；烘焙脸发黑、身后多一张脸；M7 多视角未开始。

## A.2 阶段总览

```
阶段 0 环境与数据安全 ──► 阶段 1 渲染整帧过门禁（主线 #1）──┐
                        └► 阶段 2 MMD 全片跑通 ─────────────┴─► 阶段 3 Unity 6 迁移 ──► 阶段 4 Unity 6 终验出片
```

阶段 1 和 2 互不依赖、可交替推进，但同一时间只有一个执行者（Unity 批处理桥也只能串行）。阶段 3 的入口是阶段 1、2 出口全部通过（收尾交接 §正确路线已定：Unity 6 暂不迁，等 2022 基线动作 + 渲染收敛）。

## A.3 阶段 0：环境与数据安全（本文件 §B 给出逐步计划）

- 0.1 网关清洗代理启用（决策 D1），消除"压缩后必死 / 反复重连"。
- 0.2 真值数据备份（决策 D2），当前 gitignore 的真值无任何备份记录。
- 0.3 今日复验与本路线图提交到记录分支（决策 D3）。

出口门禁：新会话手动 `/compact` 后下一轮正常应答，代理日志出现 `dropped` 记录或确认无空 system 消息；备份后 RDC 文件 SHA256 与源一致；记录分支含今日提交且远端同步。

## A.4 阶段 1：渲染整帧过门禁（Unity 2022 基线）

出口门禁（沿用 `Tools/compare_pose_official.py` / `EndfieldPoseApplyValidation` 现有阈值，不放宽）：帧 6411 轮廓 IoU ≥0.85；头 / 躯干 / 腿 MAE ≤4 色阶、p95 ≤16、8 色阶内 ≥0.9；冻结模块逐位门禁不回归；至少一个不参与调参的验证帧 / 视角记录同阈值结果。

| 工作包 | 交付物 | 验证 |
|---|---|---|
| WP1.1 差距归因（先测后改） | 扩展 `Tools/compare_pose_official.py`：①轮廓误差按原因拆（官方 mask y≤0.83 截断区、书本道具像素、145 根未摆姿骨覆盖区）；②颜色误差在**后处理前 HDR 域**按材质区（皮肤 / 头发 / 布料 / 眼）与逐 draw 拆开。输出按误差贡献排序的来源表 | 归因表各项贡献之和与整帧 MAE 对账（残差 < 10%） |
| WP1.2 几何 / 姿态补全 | 145 根 bind 姿态骨按捕获 `pose_apply` 补齐（捕获中有的部分）；书本道具补上或按决策从比较区剔除（D8） | 轮廓 IoU 过门禁 |
| WP1.3 八面体平滑法线解码 | 从模型 UV 解码平滑法线并接入描边与相关着色项 | 解码函数单测（编码→解码往返误差 < 1e-3）；描边宽度 / 颜色对官方 draw 输出做区域比对 |
| WP1.4 未实现着色项 | 按 WP1.1 排序逐项补：描边颜色（官方公式）、刘海 / 头发阴影、覆盖层、dither、透明、眼部边缘光 | 每项先写对官方 draw 输出的区域门禁再实现 |
| WP1.5 A 轨遗留 | 烘焙脸发黑、身后多一张脸 | 截图 + 区域门禁 |
| WP1.6 第二真值 | 先评估已有但未用的 `123.rdc` / `213.rdc`；不够再考虑 RenderDuck 新截（D4，ACE 检测风险） | 作为验证集，不参与调参；方向阴影也在这里验证 |

真值与参考：官方反编译 shader（`_dump_1.5.3/.../com.hg.render-pipelines/runtime/shaders/`，译文 `docs/research/official-forwardlit-*.md`）+ 捕获常量为真值；`ShiyumeMeguri/Ruri.ShaderDecompiler`（上游作者的带符号注入反编译器）用来提高可读性；社区 URP 复刻只作实现提示。

## A.5 阶段 2：MMD 全片跑通（Unity 2022 基线）

出口门禁（数值是**建议值**，在阶段 2 计划里和你确认后写死）：全片最低足部顶点 ≥ -0.5 cm（现 -15.8 cm）；接触期足底水平滑移 P95 ≤0.3 cm/帧；源端判为离地的帧不被锁（接触标签与源端足 IK / 足首高度一致率 ≥99%）；相机对 UMT 位置最大 ≤1 mm、旋转最大 ≤0.2°、FOV 精确；同输入两次出片逐帧哈希一致；inPlace 开 / 关各出一版全片并通过你的观感验收。

| 工作包 | 交付物 | 验证 |
|---|---|---|
| WP2.1 `MmdSession` | 合并 Studio / Batch / Smoke 三处初始化为一个会话对象；烟测加载相机 | Review Focus 3、5 的测试 |
| WP2.2 接地与脚锁 | 源端（足 IK 目标 / 足首高度 + 速度）标记接触；目标骨架用已安装的 Animation Rigging 1.1.1 Two Bone IK 做锁定 / 释放。EIEM 的 FindFloor 只作行为参照（AGPL） | 足底高度与滑移逐帧曲线过门禁 |
| WP2.3 表情 | 方案 A：用 `hakobune67/endfield-facemorph` 把官方表情骨骼动画烘成 blendshape（本地使用，不入库），复用现有 `MmdFace` 别名映射；方案 B：从官方表情动画采样每个 MMD morph 对应的 85 关节偏移并按权重叠加。先做可行性验证再选（D5） | 常用 morph（あ / い / う / え / お / まばたき / 笑い 等）逐个截图 + 偏移数值对官方表情帧 |
| WP2.4 次级物理 | 头发 63 / 布料 66 / 裙摆 28 / 尾巴 8 / 胸 4 骨；固定步长、可开关（D6 选组件） | 两次出片哈希一致；采样帧穿模检查 |
| WP2.5 全片出片 | 37.7 s，VMD 动作 + 相机 + 舞台 + 捕获管线，PNG → H.264 + AAC | 全片无 NaN / 跳变、相机无抖动、上述曲线门禁 |
| WP2.6 共享 IK 链实测 | 构造共享链的合成 rig，对 UMT / mmd-anim | 与单链同量级误差 |
| WP2.7（可选）UMT baked-FK 协议 | 按收尾交接 §可从这里接续 2，作为新 VMD 的回归参照与可选生产源 | 与现 C# 求值器逐骨对照 |

## A.6 阶段 3：Unity 6 迁移（在工程副本上）

入口：阶段 1、2 出口全绿；捕获管线已 Restore（Review Focus 1）；阶段 0 备份完成；在工程**副本**上升级，不原地。

| 工作包 | 交付物 | 验证 |
|---|---|---|
| WP3.1 版本 | Unity 6.3 LTS（或届时最新 LTS）；6.3 起兼容模式被隐藏，默认 RenderGraph，依赖兼容模式的工程升级后会构建失败 | 空升级能编译 |
| WP3.2 RenderGraph 移植 | `EndfieldCapturedPostFeature`（后处理链 + 17 次 Bloom compute、R11G11B10 RTZ 量化）、`EndfieldCharacterShadowFeature`（MRT prepass、compute resolve、`DrawRenderers` → RendererList）改为 `RecordRenderGraph`；ShowcaseRef 的 feature 视需要 | 同一捕获输入下复现原逐位门禁（后处理 ≤0.13 色阶且 100% 在 1 色阶内；自阴影 ≥99.84% 逐字节） |
| WP3.3 API | `FindObjectOfType` 31 处 → `FindFirstObjectByType` / `FindAnyObjectByType`；替换 `m_RendererDataList` 私有字段访问；去掉对 `s_RTHandlePool` 预热的依赖；`EndfieldCharacterLit` 补 DepthOnly / DepthNormals pass；离线出片验证 `camera.Render` 或改 `RenderPipeline.SubmitRenderRequest` | 编译 0 警告级过时 API；出片一致性测试 |
| WP3.4 包 | URP 17；Cinemachine（代码 0 引用，可移除）；Animation Rigging 升级；TextMeshPro 并入 ugui | 包解析无冲突 |
| WP3.5 MMD | C# 求值器重跑 1131 帧对照；UMT 在 6000.x 实测 | 与 2022 结果逐位或同量级一致 |

出口 = 阶段 1、2 全部门禁在 Unity 6 上重过。阶段 4 在 Unity 6 上出最终全片并做你的观感终验。

## A.7 书签档案核验结果与用法

档案共列 33 个仓库 + 1 个 B 站视频，2026-09-27 用 `gh api` 逐个核验：**32 个存在，`White-NX/Endfield-Poser` 已 404**——本工程 MMD 代码实际来自 `OedoSoldier/Endfield-Poser`（本地 `../Endfield-Poser/` 的 origin），档案写错了作者。`ijbolnation/endfieldtools` 是空仓库（只有 README）。档案漏掉、但本地 `_EndfieldRefs/` 已有的：`qiudashu233/MyZmdShaders`、`ZMD`（无 git 来源）。上游 `ShiyumeMeguri/FractalMiner` 比本工程基线多 3 个提交（鸣潮 shader 包、LICENSE），与终末地无关。B 站视频 BV1Eu9BBuExe 的"源码"就是本工程上游。档案的叙述段落有 LLM 填充成分（如按 Android `libil2cpp.so` 描述、"泄露的着色器框架"等），只采信能核实的部分。统一资源库：`D:\EndfieldTechLib\`（分类目录 + `CATALOG.md`）。

| 用途 | 仓库（★ / 许可证 / 最近推送） |
|---|---|
| **真值 / 工具（本地使用）** | `ShiyumeMeguri/FractalMiner`（112 / AGPL / 09-16，上游）；`ShiyumeMeguri/Ruri.ShaderDecompiler`（128 / AGPL / 09-24）；`FractalTools/TypeTree`（AGPL，魔改引擎的 TypeTree 转储）；`hakobune67/endfield-facemorph`（无许可证，只本地用）；`CandidumGames/UnityMMDTools`（MIT）；`yohawing/mmd-anim`（MIT）；`noname0310/babylon-mmd`（254 / MIT，第三参照） |
| **实现参考（不拷代码或按许可证处理）** | `congyuxiaoyoudao/Endfield_Character_Rendering`（18 / MIT，URP 角色管线）；`chris0214/Arknights-Endfield-MME-Shader`（18，SDF 脸）；`Morgana-lgtm/...Perlica-Character-Shader`（无许可证）；`tulu1015/UE5-Endfield-Character-Render`（无许可证）；`kkskaguya/Endfield-Toon-Addon`（GPL，贴图通道语义）；`HongTangChen07/Endfield-Renderer`（无许可证）；`ijbolnation/endfieldtools`、`PaoloESAN/gacha-setup`（GPL）；`Sasye/EIEM`（46 / AGPL，游戏内 VMD 运行时：骨映射、FindFloor、SMC 表情、相机）；`Sp1cHless/...Secondary-bodyphysics`（GPL，次级物理思路）；`SPARK-inc/SPCRJointDynamics`（630 / MIT，但 2023-10 后未更新） |
| **不纳入主线** | VFS / IL2CPP / 元数据转储类（EndfieldStudio、EndfieldUnpacker、Il2CppDumper-end、IL2CPP-Dumper、Endfield-MetadataDumper、endfield-il2dump、EndField-MetadataExtractor）、帧率解锁（已归档）、地图 / 数值导出、EFMI 模组启动器、Redfield ReShade、Tianshi 粒子研究。理由：工程已持有所需真值；这些工具面向在线游戏客户端（ToS / ACE 反作弊风险），不推进 Unity 内的还原 |

上游作者在视频简介里给出的、直接影响"完美还原"的线索：法线贴图解码未实现（本工程 09-17 已修正，无需再做）；终末地魔改 Unity 2021.3.34f1，角色另有 MorphAvatar / CorrectiveBoneData / PoseDriverData（修正骨、姿势驱动）、SkeletonConstrainData（驱动骨 + 球碰撞）、ClothCalculatorType，动画在 UI 用无损、在游戏内用 ACL 有损压缩，四肢疑似运行时程序 IK。其中修正骨 / 姿势驱动决定大幅动作时肩肘的形变质量，阶段 2 做全片验收前要评估是否需要还原（D9）。

## A.8 决策点

| # | 问题 | 我的建议 |
|---|---|---|
| D1 | 启用网关清洗代理（改变所有 CC 会话的网络路径） | 启用：它是"压缩后必死 / 反复重连"唯一实测有效的修法，可随时回滚 |
| D2 | 真值备份到哪（3 个 RDC 共 3.9 GiB + 捕获 1.8 GB + GeneratedCapture 0.35 GB + 反编译 shader 0.97 GB；`Assets/Typhoeus` 24 GB 是否一起） | 另一块物理盘；`Assets/Typhoeus` 一起备 |
| D3 | 今日复验与本路线图提交并推送到 `endfield-records` | 提交并推送 |
| D4 | 第二真值来源 | 先评估现有 `123.rdc` / `213.rdc`，不够再用 RenderDuck |
| D5 | 表情方案 A / B | 先做 A 的可行性验证（现成轮子） |
| D6 | 次级物理组件 | 先试 SPCRJointDynamics（MIT、免费）；不满足再评估 MagicaCloth 2（付费） |
| D7 | 执行方式 | Native（见 §B 末尾） |
| D8 | 书本道具：补上还是从比较区剔除 | 补上（官方帧里有） |
| D9 | 是否还原修正骨 / 姿势驱动 | 阶段 2 全片验收前再定 |

---

# §B 阶段 0 实施计划

### Task 0.1：启用 anyrouter 清洗代理（D1 同意后执行）

**Files:**
- Modify: `C:\Users\Administrator\.claude\scripts\anyrouter-sanitize-proxy.py`（加 `--log`，供无控制台的 `pythonw` 常驻使用）
- Modify: `C:\Users\Administrator\.claude\settings.json`（`env.ANTHROPIC_BASE_URL`、顶层 `autoCompactWindow`）
- Modify: `C:\Users\Administrator\.cc-switch\cc-switch.db`（4 个 anyrouter 档案的 `settings_config.env.ANTHROPIC_BASE_URL`；`settings.common_config_claude` 加 `autoCompactWindow`）
- Test: 探针重放（沿用 `~/.claude/scripts/anyrouter-compact-probe.json`）

**Interfaces:**
- Produces: 常驻代理 `http://127.0.0.1:15722` → `https://anyrouter.top`，计划任务名 `AnyrouterSanitizeProxy`，日志 `C:\Users\Administrator\.claude\scripts\anyrouter-sanitize-proxy.log`

- [ ] **Step 1: 给代理加 `--log`**

在 `anyrouter-sanitize-proxy.py` 的 `if __name__ == "__main__":` 段，`args = ap.parse_args()` 之前加参数，之后重定向输出：

```python
    ap.add_argument("--log", help="append log lines to this file (for pythonw, which has no console)")
    args = ap.parse_args()
    if args.log:
        import sys
        sys.stdout = open(args.log, "a", encoding="utf-8", buffering=1)
```

- [ ] **Step 2: 注册登录自启并立即启动**

```bash
PYW="C:/Users/Administrator/AppData/Local/Programs/Python/Python312/pythonw.exe"
S="C:/Users/Administrator/.claude/scripts/anyrouter-sanitize-proxy.py"
L="C:/Users/Administrator/.claude/scripts/anyrouter-sanitize-proxy.log"
MSYS_NO_PATHCONV=1 schtasks /create /f /tn AnyrouterSanitizeProxy /sc onlogon /rl limited /tr "\"$PYW\" \"$S\" --port 15722 --log \"$L\""
MSYS_NO_PATHCONV=1 schtasks /run /tn AnyrouterSanitizeProxy
sleep 2; tail -1 "$L"
```

Expected: 日志末行 `anyrouter sanitize proxy on 127.0.0.1:15722 -> https://anyrouter.top`

- [ ] **Step 3: 切换前先验证代理（失败就停，不改配置）**

用探针把"带空 system 消息"的请求打到 `http://127.0.0.1:15722`（与 2026-09-27 17:57 的测试脚本相同，只把 base 换成代理）。
Expected: `200 | 200`；日志出现两行 `dropped 1 empty system message(s) -> 200`。

- [ ] **Step 4: 同时改 settings.json 与 CC Switch 的 4 个 anyrouter 档案**

先备份（`cc-switch.db` 用 sqlite 在线备份，`settings.json` 复制为 `.bak-<时间戳>`），再把两处的 `ANTHROPIC_BASE_URL` 由 `https://anyrouter.top` 改为 `http://127.0.0.1:15722`；在 settings.json 顶层和 `common_config_claude` 中加 `"autoCompactWindow": 600000`。只做文本内替换，不打印任何 token。

- [ ] **Step 5: 端到端验证**

新开一个 CC 会话：连续对话 3 轮 → 手动 `/compact` → 再问一句。
Expected: 第 4 轮正常应答，不出现 520 / 429 重试；`/context` 或 `/status` 显示 `Auto-compact window: 600000 tokens (from settings)`；代理日志若出现 `dropped` 行，即证明拦下了原本会导致会话死掉的请求。

- [ ] **Step 6: 记录回滚方法**

在全局 CLAUDE.md §十 第 4 条后补一句：回滚 = 两处 `ANTHROPIC_BASE_URL` 改回 `https://anyrouter.top` + `schtasks /change /tn AnyrouterSanitizeProxy /disable`。

### Task 0.2：真值数据备份（D2 给出目标路径后执行）

**Files:**
- Create: `Tools/backup_truth_data.py`
- Test: 脚本自带 `--dry-run`（只列清单和大小）和备份后的 SHA256 校验

**Interfaces:**
- Produces: `<目标>\FractalMiner-truth-<日期>\` 目录树 + `manifest-sha256.json`

- [ ] **Step 1: 写脚本**

```python
"""Back up git-ignored ground-truth data that cannot be recovered from Git.

Usage: python Tools/backup_truth_data.py <dest_root> [--dry-run] [--with-typhoeus]
"""
import argparse, datetime, hashlib, json, os, subprocess, sys

GAME = r"A:\Hypergryph Launcher\games\Arknights Endfield"
FM = os.path.join(GAME, "FractalMiner")
SOURCES = [
    r"C:\Users\Administrator\Downloads\正面.rdc",
    r"C:\Users\Administrator\Downloads\123.rdc",
    r"C:\Users\Administrator\Downloads\213.rdc",
    os.path.join(FM, r"Validation\Captures"),
    os.path.join(FM, r"Assets\EndfieldShaderPack\GeneratedCapture"),
    os.path.join(FM, "_dump_1.5.3"),
    r"C:\Users\Administrator\Documents\EndfieldMmdSourceRigs",
    r"D:\MmdOracle\out",
    r"D:\MmdOracle\OracleProject\Assets",
]
TYPHOEUS = os.path.join(FM, r"Assets\Typhoeus")


def size_of(path):
    if os.path.isfile(path):
        return os.path.getsize(path)
    return sum(os.path.getsize(os.path.join(r, f)) for r, _, fs in os.walk(path) for f in fs)


def sha256(path):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for block in iter(lambda: f.read(1 << 22), b""):
            h.update(block)
    return h.hexdigest()


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("dest_root")
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--with-typhoeus", action="store_true")
    a = ap.parse_args()
    sources = SOURCES + ([TYPHOEUS] if a.with_typhoeus else [])
    missing = [s for s in sources if not os.path.exists(s)]
    if missing:
        sys.exit("missing sources: " + "; ".join(missing))
    total = 0
    for s in sources:
        n = size_of(s); total += n
        print(f"{n / 2**30:8.2f} GiB  {s}")
    print(f"{total / 2**30:8.2f} GiB  total")
    if a.dry_run:
        return
    dest = os.path.join(a.dest_root, "FractalMiner-truth-" + datetime.date.today().isoformat())
    manifest = {}
    for s in sources:
        target = os.path.join(dest, os.path.splitdrive(s)[1].lstrip("\\"))
        if os.path.isfile(s):
            src_dir, name = os.path.split(s)
            rc = subprocess.run(["robocopy", src_dir, os.path.dirname(target), name, "/COPY:DAT", "/R:1", "/W:1", "/NP"]).returncode
            manifest[s] = sha256(s)
            if sha256(target) != manifest[s]:
                sys.exit("hash mismatch: " + s)
        else:
            rc = subprocess.run(["robocopy", s, target, "/E", "/COPY:DAT", "/R:1", "/W:1", "/NP", "/NFL", "/NDL"]).returncode
        if rc >= 8:
            sys.exit(f"robocopy failed ({rc}) for {s}")
    with open(os.path.join(dest, "manifest-sha256.json"), "w", encoding="utf-8") as f:
        json.dump(manifest, f, ensure_ascii=False, indent=1)
    print("backup ok ->", dest)


if __name__ == "__main__":
    main()
```

- [ ] **Step 2: 试运行看清单**

Run: `python Tools/backup_truth_data.py <D2 目标> --dry-run --with-typhoeus`
Expected: 逐项大小与合计；缺任何一个源则直接报出路径并退出。

- [ ] **Step 3: 正式备份**

Run: `python Tools/backup_truth_data.py <D2 目标> --with-typhoeus`
Expected: `backup ok -> ...`；3 个 RDC 的 SHA256 与源一致（脚本内校验，不一致即退出）；robocopy 返回码 < 8。

- [ ] **Step 4: 把备份位置写进 `_agent_experience.md`**

在"真值数据"相关小节补一行：备份路径、日期、`manifest-sha256.json` 位置。

### Task 0.3：今日记录提交到记录分支（D3 同意后执行）

**Files:**
- Commit: `HANDOFF-2026-09-27-mmd-research-closure.md`（追加了 18:00 复验段）、`docs/superpowers/plans/2026-09-27-mainline-roadmap.md`（本文件）、`Tools/backup_truth_data.py`（若 Task 0.2 已完成）

- [ ] **Step 1: 用临时 index 提交（不碰 main 的 index）**

```bash
cd "A:/Hypergryph Launcher/games/Arknights Endfield/FractalMiner"
export GIT_INDEX_FILE="$TEMP/endfield-records-index-$(date +%s)"
B=fix/typhoeus-render-explosion-20260917
git read-tree "$B"
git add -- HANDOFF-2026-09-27-mmd-research-closure.md docs/superpowers/plans/2026-09-27-mainline-roadmap.md
git diff --cached --stat "$B"
parent=$(git rev-parse "$B"); tree=$(git write-tree)
commit=$(git commit-tree "$tree" -p "$parent" -m "docs: re-verify MMD source evaluation and add mainline roadmap")
git update-ref "refs/heads/$B" "$commit" "$parent"
rm -f "$GIT_INDEX_FILE"; unset GIT_INDEX_FILE
```

Expected: `--stat` 只列出上述文件；`update-ref` 成功（记录分支若已被别人推进，`update-ref` 会因旧值不符而失败，此时停下重新 read-tree）。

- [ ] **Step 2: 推送并核对**

```bash
git push endfield-records "refs/heads/$B:refs/heads/$B"
git ls-remote endfield-records "refs/heads/$B"
git status --short | head -3
```

Expected: 远端哈希等于 `$commit`；`main` 的 `git status` 与提交前相同。

---

**执行方式建议：Native（我在本会话内逐项做，阶段结束时由一个全新 reviewer 审一遍）。** 理由：当前网关下一个 15 分钟的只读 subagent 实际跑了 2 小时 23 分钟；你的规则本来就要求 subagent 串行；各任务都要用同一个 Unity 批处理桥和同一份配置，交给多个执行者只会互相等待。
