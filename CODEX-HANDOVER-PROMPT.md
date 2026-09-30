> 2026-09-30 当前优先级更新：用户要求先核实已有资料与解包官方代码一致，再用上湿身等成果。先读 `docs/research/source-contract-audit-20260930.md` 和更新后的 `INDEX-shader-sources.md`。湿身/雨系统/C6文档存在实质错误，已修正本批关键输入与数学，但天气生产端、实际绑定及未展开变体仍待核；不要宣称全部文档/官方渲染已完全准确，不先按旧伪码接湿身。外部C6报告确实存在，不重复调研。旧文档里的逐像素/LSB/清垃圾指令不再执行，不碰用户9557项暂存索引。

> 2026-09-30 已完成实现增量：先读 `CODEX-HANDOFF-2026-09-30-eye-hair-shadow.md`，再读 `CODEX-HANDOFF-2026-09-30-live-skin-and-motion.md` 和 `CODEX-AUDIT-HANDOFF-2026-09-30.md`。用户明确不要逐像素对照；按官方代码、光照、管线/后处理的结构与逻辑验收，然后接解包动作/MMD。动态根已覆盖face/body/iris/hair；眼睛投影光公式、虹膜描边、根参数块遮住阴影参数的问题已修正，解包动作/VMD六个时刻的实时阴影/Bloom/post链路通过。后续实现是官方OverlayShadow模板/乘色pass，不是调曝光，须先完成当前资料优先事项。旧颜色LSB/IoU门禁不再作为主线。仍未宣称全渲染/MMD完成，不按旧垃圾清单删用户资源。

你是这个 Unity 逆向渲染工程的接手者。目标：在 Unity 2022.3.30f1 / URP 14 上，把《明日方舟：终末地》角色提弗洛斯的官方渲染**逐部件还原**（skin/hair/cloth/eye + 描边 + 刘海投脸 + 地面投影 + 雨淋湿身 + 后处理），参数 inspector 可调；再接入 MMD（VMD 动作+相机）离线出片；最终迁 Unity 6 重过验收。

**核心定性：目标是"像不像官方地渲染"，不是复刻捕获帧 6411 的姿态。** 帧 6411 是着色真值（各部件在已知光照下的颜色/质感），不是要对齐的轮廓。逐姿态、整帧轮廓 IoU 门禁、抢救 pose 基线——均已从目标移除。

---

## 一、你接手后的三件事（按顺序）

1. **先读上下文**：`docs/superpowers/plans/2026-09-27-mainline-roadmap.md`（路线图，§A 规格+现状数字+约束）、`Assets/EndfieldShaderPack/EndfieldCharacterLit.shader`（主着色器）、`docs/research/INDEX-shader-sources.md`（逆向转写索引）。
2. **处理未提交文件**（9577 个已 staged，历史累积）：参考 `HANDOFF-2026-09-30-uncommitted-inventory.md` 盘点。你要做——清理垃圾（74 个：`.7z` 8 / `.pyc` 60 / `.log` 6）、排除第三方（218 个 `Assets/[DaisyMeow]Typhoeus Kitty Maid Base Ver/`）、保留核心成果（约 430 文件：核心代码 127 + Python 工具 76 + 文档 71 + 场景/材质/资产 156 + 对应 .meta）。提交方式见 §九 约束 2。
3. **从 §十 的第 1 项开始推进渲染**（拿可信的 face 对比）。

---

## 二、工程根与硬环境

- 工程根：`A:/Hypergryph Launcher/games/Arknights Endfield/FractalMiner`
- Unity：`A:/Unity/Editor/2022.3.30f1/Editor/Unity.exe`
- Python：`../EndfieldUnpacker/.venv/Scripts/python.exe`（系统 Python 无 Pillow/numpy）
- RenderDoc：`C:/Program Files/RenderDoc/qrenderdoc.exe`（离线 rdc 用 `--python`）
- Shell：Git Bash（Windows 用正斜杠路径）

---

## 三、架构：三条线 + 门禁驱动

门禁驱动 = 先定量测差距 → 按差距来源拆工作包 → 每个工作包先写"会失败的门禁"再改实现。渲染真值 = RenderDoc 捕获 + 官方反编译 shader；MMD 动作真值 = UMT（MIT）+ mmd-anim（MIT）双参照；社区项目只作线索。

三条线：① **渲染线**（逐部件还原+描边+阴影+湿润+后处理）② **MMD 线**（VMD 动作+相机出片）③ **Unity 6 迁移**（2022 基线全绿后在副本上迁 URP 17 RenderGraph）。

---

## 四、目录结构

| 路径 | 用途 |
|---|---|
| `Assets/EndfieldShaderPack/` | **核心代码**（着色器+Editor+MMD+验证）|
| `Assets/Typhoeus/` | 导入的网格/材质/贴图（`S_actor_typhoea_*_lod0`、`M_actor_typhoea_*`、`T_actor_*`）|
| `Assets/Scenes/` | `Typhoeus_OfficialFrame_Recovered`（pose-apply 参照，**无版本控制**）、`Typhoeus_Showcase`、`Typhoeus_MMD_Stage`、`Typhoeus_CapturedPipeline` |
| `docs/research/` | 官方 shader 逆向转写（四族 forwardlit、后处理、雨、阴影）|
| `docs/learning/` | 从零自学图谱（5 章）|
| `docs/superpowers/plans/` | 路线图+阶段计划 |
| `Tools/` + `Tools/tests/` | Python 工具 + 单测 |
| `Validation/` | 验证产物（截图/诊断/pose-compare 系列/mmd-smoke）|
| `_dump_1.5.3/`、`Project_Reference/` | 反编译 dump / 上游参考（**不进 Git**）|

---

## 五、核心代码

**着色器**（`Assets/EndfieldShaderPack/`）：
- `EndfieldCharacterLit.shader`（~1331 行）— 主着色器。Pass：`UniversalForward`(509 行)、`Outline`(1035 行，SRPDefaultUnlit，Cull Front)、`EndfieldCharacterShadowAtlas/GBuffer`、`ShadowCaster`。`sourceShading` 真→官方四族函数，假→generic 简化路径。全局变量 `_CharacterParams0-15`、`_CharacterLightDir`、`_EndfieldOfficialFrameEnabled`、`_EndfieldCapturedLightIntensity`、`_ExposureWithMiscParams`。**Material family：Cloth=0/Skin=1/Hair=2/Eye=3**。
- `EndfieldOfficialSkin.hlsl`（face/body 共用，family=1，SDF 公式见 b138 文档 §9-10）、`EndfieldOfficialHair.hlsl`、`EndfieldOfficialCloth.hlsl`、`EndfieldOfficialEye.hlsl`。
- `EndfieldCapturedPost.shader`+`Feature`+`Profile`（后处理栈）、`EndfieldCapturedBloom.compute`+`.cs`（动态 bloom）——**冻结模块不改**。
- `EndfieldCharacterShadow*`（屏幕空间自阴影，G 通道=selfShadow）。

**Editor**：`ImportCapturedVertexAttrsV2.cs`（顶点导入器，Octahedral 法线解码）、`EndfieldPoseApplyValidation.cs`（`RunPoseApply()` 渲染入口）、`EndfieldCapturedSceneBuilder.cs`、`EndfieldSkinInputDiagnostics.cs`（后处理前 HDR 诊断）、`EndfieldOfficialFrameGlobals.cs`、`TyphoeusModelBuilder.cs`、`EndfieldMaterialImporter.cs`、`Mmd/`（10 文件全套）、其余 `*Validation.cs` 门禁。

---

## 六、文档（逆向转写）

入口 `docs/research/INDEX-shader-sources.md`。关键：`official-forwardlit-skin-b138.md`（皮肤，SDF 权威公式 §9-10）、`-hair-b125`、`-cloth-b401`（旧"b401=body"已撤回）、`-eye-b28`、`official-outline-skin-b273.md`（描边）、`official-source-shading-20260923.md`（body 归属权威更正）、`character-shadow-evidence-20260923.md`、后处理 5 篇、雨/湿身 2 篇。**OETF `v*12.92`/`1.055*pow(v,1/2.4)-0.055` 是线性→sRGB 编码，不是解码**。

---

## 七、当前进度（精确数字）

**渲染线**：
- 已闭合：Octahedral 法线解码（29062 顶点，误差<1.5e-7）+ 导入器 V2（6/6 mesh）；后处理栈（官方 HDR 输入平均 0.12 色阶、100% 在 1 色阶内；Bloom 相对 L1 2.7e-4；环境 cube MAE≤2.1e-4；自阴影 resolve 逐字节 99.84%）；M5 几何误差 0；描边 b273 转写。
- 未闭合：轮廓 IoU **0.417**（门≥0.85，曾 0.765 但 09-28 回归不可复现，145 根未摆姿次级骨丢失）；**face 偏暗~48%**（body 基本正确，见 §八）；平滑法线未接描边、覆盖层/刘海阴影/dither/透明/方向阴影/雾/局部灯/湿润/眼边缘光未做；烘焙脸发黑、身后多一张脸。

**MMD 线**：源端闭合（1131 帧对 UMT 位置 P95 0.145/0.114mm，相机最大 0.25mm/0.13°）；目标端部分（55 role→Bip001 retarget、腿 IK、5 点烟测 PASS）；未闭合（共享 IK 无实测、接地整体抬升 -0.158m、脸 0 blendshape、无次级物理、烟测未加载相机、全片未出片、三处初始化重复）。

**Unity 6**：未开始（3 个 feature 走 Execute 兼容路径 0 个 RecordRenderGraph、31 处 FindObjectOfType 等）。

---

## 八、face 偏暗排查结论（重要）

"整体偏暗/缺后处理"是错的，已撤回。正确结论：
1. 后处理早已实现（CapturedPost：官方 LUT+exposure 1.6+动态 bloom+vignette+dither），输出 `pose-applied-lit-post.png`。
2. body 后处理前 HDR 吻合官方 ~99%；face 偏暗 ~48% 是主残差。
3. 干净排除实验（同天只变单变量、读后处理前 HDR）：禁用 SDF 分支→face **零变化**；禁用 selfShadow→face 只 +0.9%。**SDF 和自阴影都不是根因**。
4. 方法论坑：官方 face=1.306 是 09-29 **抱书**数据，本轮是**抱臂**姿势，直接对比被污染。**要可信判断 face 是否真暗，必须用 213（抱臂）官方 face/body 分部件后处理前 HDR 对比。**

三捕获姿势（`Validation/Captures/new-rdcs/`，各 ~1.4GB 真值不进 Git）：**213=抱臂**（与我们渲染同姿势，正确 A/B 参考）、**正面=抱书**（顶点导入来自它 frame 6411）、**123=UI 总览页**（不适合 A/B）。

已从 213 提取（`213-extract/`）：`camera.json`（FOV 35°/aspect 1.6/view-proj 真世界空间）、`official-213-scenecolor-55208.exr/-srgb.png`（后处理前 HDR，R11G11B10_FLOAT，最后写于 ev1081）、`official-213-final-noui.png`（uberpost 输出无 UI）、`postfx-chain.json`/`postfx-probe.json`（链路 55208→uberpost→19599 LDR）、`draws.json`（281 drawcall，**213 事件号与旧 776/786/835/850/860/875 不通用**）。

---

## 九、关键命令 + 硬约束

**命令**：
```bash
cd "A:/Hypergryph Launcher/games/Arknights Endfield/FractalMiner"
# pose-apply 渲染（核心渲染+门禁）
"A:/Unity/Editor/2022.3.30f1/Editor/Unity.exe" -quit -batchmode -projectPath "$(pwd)" \
  -executeMethod EndfieldShaderPack.EditorTools.EndfieldPoseApplyValidation.RunPoseApply -logFile render.log
# 皮肤诊断（输出后处理前 HDR）
ENDFIELD_SKIN_DIAGNOSTICS="Validation/skin-input-NEW" \
  "A:/Unity/Editor/2022.3.30f1/Editor/Unity.exe" -quit -batchmode -projectPath "$(pwd)" \
  -executeMethod EndfieldShaderPack.EditorTools.EndfieldSkinInputDiagnostics.Run -logFile diag.log
# rdc 提取（renderdoc 模块只在 qrenderdoc 内可用，__file__ 未定义需绝对路径）
"C:/Program Files/RenderDoc/qrenderdoc.exe" --python Tools/extract_213_scenecolor.py
```

**硬约束**（务必遵守）：
1. 真值不进 Git：`*.rdc`、`Validation/Captures`、`GeneratedCapture`、`D:\MmdOracle`、`Documents\EndfieldMmdSourceRigs`、`_dump_1.5.3/`、`Project_Reference/`；第三方 PMX/VMD/游戏资源不提交。
2. Git 提交：`main` 不 checkout/reset/clean/`git add .`；走临时 `GIT_INDEX_FILE` → 记录分支 `fix/typhoeus-render-explosion-20260917` → 远端 `endfield-records`（=`github.com/Lin-Phoeo/FractalMiner`，旧文档 `LinXingjian365` 是改名前旧账号）。
3. 参照场景 `Typhoeus_OfficialFrame_Recovered.unity` 无版本控制、被 MMD 工具改坏过一次；跑 OpenScene+SaveScene 前后要备份。
4. `Library/EndfieldCapturedPipelineActivation.json` 用完必须 Restore，遗留会把 QualitySettings Ultra 档改坏。
5. subagent 同一时间最多 1 个。
6. 冻结模块不改：`EndfieldCapturedBloom`、`EndfieldCapturedPost.shader`、`EndfieldCapturedPostFeature`、`EndfieldCapturePipelineValidation`。
7. 门禁阈值只能收紧不能放宽。
8. 网关下 WebSearch/WebFetch 不可用，检索用 `ddgs`/`trafilatura`/`gh api`。
9. 按名字查骨锚定 `chr_0034_typhoea_rebuilt`（停用的 `Typhoeus_SourceFBX` 有同名 Bip001 会误命中）。
10. `VmdMotion/VmdCamera/MmdRig/MmdRetarget/MmdPlayer` 派生自 AGPL Endfield-Poser；无许可证仓库只参考不拷贝。
11. 不重复造轮子：新模块先检索现成方案，写明用/不用的理由。
12. 代码红线：不加超范围改动、不写冗余注释、不留 TODO/半成品、UI 改动自测。

---

## 十、已知坑（踩过的教训）

- 区域均值/带符号偏差不是姿态无关门禁；不能据单帧均值宣称某部件正确/错误。
- 采样先确认落在角色上（label mask B==128 是角色）；之前把背景当角色像素得出"偏暗 bug"假结论。
- label R 值 = renderer index + 1（`EndfieldPoseApplyValidation.cs` 里 `(r+1)/255`）：body=4、face=14、hair=15、cloth_01=6。
- `current-prepost.rgba32f` rowOrder 是 Unity bottom-to-top，读时要翻转行。
- OETF 是编码不是解码，别据反标术语重建 LUT。

---

## 十一、下一步优先级

1. **最高优先**：从 213.rdc 提取官方 face/body 分部件后处理前 HDR（需部件定位，按 shader 签名匹配），与我方抱臂渲染对比，判断 face 是否真暗 48% 还是姿势污染。
2. 若 face 确暗：对照 b138 §9-10 完整 SDF/环境/光能量公式，检查 `EndfieldOfficialSkin.hlsl`（已知我方把 sdfGrad 当最终强度，官方用复杂 NdotL+sdfBack 混合）。
3. 若 face 不暗：转向描边实现（WP1.3/1.4a，b273 已就绪）、刘海投脸/地面投影（WP1.4b）、雨淋湿身（WP1.4c）。
4. MMD：接地修正、blendshape 脸、共享 IK 实测、全片出片。
5. Unity 6：2022 基线全绿后在副本上做。

---

**详细参考**：`HANDOFF-2026-09-30-codex-handover.md`（深入某个领域时查）、`HANDOFF-2026-09-30-uncommitted-inventory.md`（未提交文件盘点）。开始前先读 §一 第 1 项的三个文件，然后按 §一 顺序执行。
