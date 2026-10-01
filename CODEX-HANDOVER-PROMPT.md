> 2026-10-01 最新增量（长发/裙摆物理）：先读 `docs/implementation/secondary-motion-20261001/README.md`。采用MIT UniVRM v0.99.4小型Verlet核心+固定120Hz适配，明确是替代物理，不是官方算法闭合；原生渲染/湿身/曝光/post没改。无权重hair07/skirt04末端不能使用identity bind fallback作物理证据，33关节假设撤回，实际只接24个可靠加权驱动关节（10长发+14裙摆）。MMD Studio加载默认开物理，统一ApplyAt供预览/导出，参数变更/倒拖/循环清历史重放，关闭还原次级locals与17mesh；独立VmdBatch/AnimStudio/解包clip仍未接。最终secondary-motion-20261001-10真实Unity716 checks通过，含37.7秒VMD时间线有限/长度检查、真实面板/出帧一致性、30/60fps采样一致性、非法参数/单球碰撞；61帧960x600/30fps真实湿身物理MP4留存。仅球形代理/安全摆角，未验收全动作无穿模，袖口/飘带/末端/脚滑/完整表情仍待办；Python474 passed/3历史skipped/80subtests，C#覆盖率未测。保留失败03/04/05/07；不碰原场景/设置/seal/main HEAD/index，记录分支独立提交。

> 2026-10-01 最新交付（湿身/MMD测试起点）：先读 `docs/implementation/wetness-mmd-start-20261001/README.md` / `verification.json`。用户最新优先级是先湿身可开启可见，再干净初始姿态供MMD测试。菜单 Endfield/Wetness Studio → ①舞台 → 正面镜头 → ②湿身；cloth01/02 b471/b472湿块逐字符/临时变量同构验证，原生BC7天气20mip/400GPU分量验证，packed RGBA8不能再传普通湿度float。只此两类布料，不是全角色/整套天气完成。修复 URP SingleCameraRequest 不触发相机回调造成wet gate=0，显式scope和正常相机都实测；forceMatrixRecalculationPerRender修同步蒙皮旧缓存。重开舞台不等于clean bind，完整481骨/17mesh用解包bind恢复，再实际写T-pose。新髋-肩横轴门禁抓到pelvis basis det<0反射导致扭腰，已改一致右手基，07旧失败留存。最终 `Validation/wetness-20261001-12/` 513检查/原始Unity预览通过，关闭会话原mesh/管线/骨态恢复；现有UNFORGIVEN 4146key/5时刻实际渲染通过，尚非整段/任意VMD/物理认证。MMD Studio加载与出帧复用此会话，每帧动态SkinBasis。light688/environment/cutout26/uniform225/consumer238/lifecycle13/MMD格式回归通过；Python470 passed/3历史skipped/80subtests，导出器94%合并覆盖，Ruff/Pyright通过。没改曝光/后期/原场景/设置/seal；79/24 pending与真正D16/stencil/其他天气producer等剩余工作仍在。用户主HEAD/index保留，独立记录分支提交。预览期间不要保存舞台或开Unity顶栏Play；使用窗口内播放按钮。

> 2026-10-01 最新增量（atlas writers）：先读 `docs/implementation/shadow-atlas-writers-20261001/README.md` / `verification.json` / `remaining-work.md`，再读前一 shadow-producers。离线核23actual D16 depth draws272–376（46SPV/120raw CB），全在viewport3072,0,1024²，scissor3073,1,1022²；clear260 depth0，GreaterEqual/write=true/CullOff/raster bias=-8（slope-0），旧“caster全无bias”错误已撤回。7槽常量不等于本帧7槽绘制。PS分空fragment /9065普通cutout /9050 sqrt-dither /65356额外dissolve+instance fade，不能通用替换。生产atlas source普通cutout修成float SampleBias alpha×BaseColor.a后clip（BaseST一次），只此功能改动，legacy/opaque保留；旧24例7FAIL→24PASS，补两保护最终26PASS；lifecycle13/sampler3072/consumer238/uniform225分量/light688回归全PASS；Python461 passed/3历史skipped/80subtests，新工具36例/116语句100%行覆盖，非C#/整工程覆盖。下轮优先真实D16/bias/scissor两重叠深度GPU合约、分区/culling，随后模板/遮挡与其他alpha变体/R producer、正式场景天气final与动作/MMD。没调颜色曝光/post、没逐像素拟合、没改原场景/设置/seal/main HEAD/index；完整渲染仍未闭合，剩余清单已明确。

> 2026-10-01 前一接手点：先读 `docs/implementation/shadow-producers-20261001/README.md` / `verification.json`，再读 lifecycle / selection / light 增量。实际744/748 VS2254/2260+PS2255/2261 raw hash、8 CB、资源视图、sampler、VK state离线重提取。重要更正：748 atlas set3/s2实际Linear ClampEdge，不是dump名字Mirror，生产compute改inline LinearClamp；最终同一3072合成门禁旧Mirror256 FAIL、Clamp0，2e-4不变，覆盖边缘/旋转16格/flip两态/零及全遮挡。CPU fixture初期filter精度错误留存，按D3D11子纹素约定+二进制quartertexel修正，没做画面拟合。744/748不是R/G分写：writeMask15，分别stencil!=4 / ==4 (mask7)，748也算R；本帧方向override=(0,0,1,1)才让R全白。旧研究§5 atlas槽序错，新raw正确槽序写在增量；原封存doc/manifest字节未改，旧Mirror/全NaN保证在增量撤回。当前live仍无真实模板域/R producer，square R16适配atlas不等价D16 4×2七槽，live/captured NDC offset也待核实。下一轮先查atlas clear260/23 depth draw272–376（321–376重点）的actual程序/变换/bias/viewport/alpha/cull，再GBuffer模板/遮挡及R producer，随后weather/final与解包动作/MMD。不声称全渲染完成，主HEAD/9557 index/原场景设置保留。

> 2026-10-01 前一接手点：先读 `docs/implementation/shadow-lifecycle-20261001/README.md` / `verification.json`，再读 shadow-selection / light / native inputs 增量。修正 live G 在 skip/setup/cleanup/dispose 的残留：相机期间有效G gate=1，结束后0/白图/零size；独立R owner不碰。缓存光源停用会重新选启用光源，找不到明确skip；owned resize/dispose Release+Destroy，不清其他owner。用提交后才增长的LastRenderSequence与LastRenderedCamera替代旧“结束后gate1”假门禁，pose/SkinBasis/AnimRender三个caller要求fresh提交。旧13场景12 FAIL，最终13/13 PASS（真实URP双相机9请求，AfterOpaques GPU observer验证gate/size及停用/早退/恢复），fixture/CPU-observer中途失败全留存，没有放宽门限。238阴影消费、688光照、MPB两槽两次更新回归PASS；Python416 passed/3历史skipped/80 subtests，Ruff/Pyright通过。未测C#/compute行覆盖率、未跑完整角色pose/MMD视频；不声称整个shadow/渲染已完成。下一步实际744/748 producer的程序身份/atlas-resolve/格式/矩阵bias/render-state，随后weather/final生命周期与解包动作/MMD。未改公式/曝光/post/材质/原场景设置，不做截图拟合；79/24封存pending不抹除；主HEAD/9557 index保留。

> 2026-10-01 前一接手点：先读 `docs/implementation/shadow-selection-20261001/README.md` 和 `verification.json`，再读 light / UPM / native-input 增量。六实际PS重新提取 set0/b15@544、b16@1728、t22 原生R8G8 mask；生产GPU消费验证238/238 PASS（12 float4上传/48分量、216合成选择、4独立R/G所有权、6原生点值），原阈值2e-6。source directional先R强度再CP1.z ignore，G改为整数SV_POSITION Load，不依赖UV/尺寸/过滤；独立R输入不被现有G producer覆盖。旧220例91 FAIL留存；原生测试一度误设R应有变化，实测本帧R全255，纠正测试前提而非放宽阈值。13项GPU回归、Python415 passed/3历史skipped/77 subtests、新增+复用Python37例/146行100%覆盖通过（不等于C#/HLSL/全工程覆盖）。没改曝光/post/材质/场景设置，没做截图拟合。当前live R producer仍未实现，URP fallback明确保留；下一步查实际744/748 producer身份、逐相机/逐帧gate复位及停用清理，再render-state/weather/final生命周期，最后解包动作/MMD。现有G feature可能留有旧gate，尚需排查其他writer，不可宣称已复现或修复。79/24 seal pending不重写；主HEAD/9557 index保留，不声称全官方完成。

> 2026-10-01 前一接手点：先读 `docs/implementation/character-light-selection-20261001/README.md` / `verification.json`，再读 UPM、Hair/Eye、Skin、Cloth 增量。六实际PS set0/b14+b16原始重提取，36 float4/144分量profile→生产GPU上传通过。修掉source从legacy L重复lerp/normalize、遗漏CP12.y颜色选择，以及四族用RGBI除回RGB在零强度丢失ambient的三项错误；source独立从捕获travel/unscaled RGB/强度选择，Skin body/face用CP4，其他族CP5。先652例412 FAIL再修688/688 PASS（新增36捕获上传例），阈值2e-6/2e-4不变；11项GPU回归、Python400 passed/3历史skipped通过，新Python22例/88行100%覆盖。显式200..208诊断正常mode0不走；没调材质/曝光/post，没改legacy A/B。固定捕获profile不等于live C++ light producer，主caller阴影仍需审；下一步ShadowData directional-strength/SSM resolve选择，然后render-state/weather producer/最终生命周期，最后解包动作/MMD。79/24 seal pending不重写，主HEAD/9557 index/原场景设置保留，不声称全官方完成。

> 2026-10-01 前一接手点：先读 `docs/implementation/material-uniforms-20261001/README.md` / `verification.json`，再读 Hair/Eye、Skin、Cloth 增量。本轮重新提取六实际PS的2272字节UPM，按实际byte offset/type+显式named候选标注，不用旧union-name评分；实际生产GPU验证120个active字段+6个BaseST=126字段/225分量。发现Hair _AnisotropyColor2错误加HDR：旧上传仅RGB三项FAIL（文件0.301/0.326/0.635，捕获线性0.0738/0.0869/0.3613）；只删除错误HDR标记，材质不改，225/225及独立Color/HDR八分量PASS，2e-6阈值不变。五相关GPU回归+Eye八态policy、Python378 passed/3历史skipped通过；新导出模块36测试/116行100%覆盖，不是全工程覆盖率。显式100..120参数诊断，正常mode0不走；六个未实现weather selector单独排除，不因捕获值0声称雨已关闭。下一步CP/global/light/environment选择与空间，再render-state/weather producer和最终生命周期，最后正式解包动作/MMD。源seal79/24 pending不重写，主HEAD/9557索引与原场景/设置保留；不声称全部完成。

> 2026-10-01 前一接手点：先读 `docs/implementation/hair-eye-inputs-20261001/README.md` / `verification.json`，再读 Skin/Cloth 增量。Hair/Eye 九张原生图、68 mip、340 typed-view GPU点值通过，独立生产采样11例通过；六实际slot四族并存恢复、默认五pass、Eye八态policy通过。实际PS22259:674及canonical b28:678明确要求投影光在ramp点积前再次归一化，旧“不可再normalize”结论撤回；修独立参照先暴露4/17 FAIL，再修运行时17/17 PASS，原门限不变。修复Hair binding标签错位/Clamp ramp、Eye Repeat/Clamp bias=-1及BaseST只一次；Line仍implicit Sample+自己的ST，无全局bias。八项既有GPU回归、Python342 passed/3历史skipped通过。新opt-in ENDFIELD_HAIR_EYE_NATIVE_MATERIALS=1，独占短期scope不是异步MPB合并器。未跑完整pose/最终场景；未调颜色/曝光/post、未写资产设置。下一步uniform/空间/天气/render-state/producer与场景生命周期，再接解包动作/MMD。v1/v2仍79/24 pending，不重写seal、不声称全官方完成；主HEAD/9557索引entries和原场景/设置保留。

> 2026-10-01 前一实现接手点：先读 `docs/implementation/skin-native-inputs-20261001/README.md` 和 `verification.json`，再读同日 Cloth 三个输入增量。Skin body/face 实际 PS22250/37671 的12绑定/10图/86原始mip、430 typed-view GPU点值通过（maxError=0），两实际slot恢复通过。已修正 Skin 的 bias=-1、s4 Repeat / s6 Clamp、Base ST共享UV、原生BC5 normal消费；LUT/ramp/SDF显式LOD0不变。旧CPU参照Repeat错误被抓出，修成Clamp后原门限不动，新增独立LUT索引3例，28/28公式回归PASS；六项既有GPU回归PASS，Python332 passed/3历史skipped。新增短期opt-in `ENDFIELD_SKIN_NATIVE_MATERIALS=1`，未运行完整pose/最终场景，没有调颜色/曝光/后处理或改材质/模型/场景设置。下一步Hair真实binding语义错位、Eye采样bias，再补uniform/空间/天气/render-state/场景生命周期与解包动作/MMD。只认证bounded dry inputs，不声称全官方渲染闭合。v1仍handover授权文档drift+79 pending；v2仍既有CharacterLit/OfficialHair两runtime drift+24 pending，不重写seal。主HEAD/9557索引entries及原场景/设置必须保留。

> 2026-10-01 前一实现增量：`docs/implementation/cloth-materials-20261001/README.md` 与 `verification.json`。Cloth01/02 原生 D/P/E+共享 Diff/Spec ramp 七张图的62mip、310项 typed-view GPU读取与独立捕获一致（含SampleLevel/Load），生产消费、两套实际slot及恢复通过；已核实 Base/E=BC7_sRGB、P/ramp=线性，并更正 RenderDoc UNorm取样域和旧event850 P/E/ShadowLUT语义错标。原始压缩数据无重做，未改主shader公式/颜色/曝光/材质资产。五项既有GPU回归全PASS，Python322 passed/3历史skipped。新入口是短期scoped pose opt-in，不是最终场景/Player包装；完整pose渲染未运行。

> 2026-09-30 最新优先级：先读`docs/render-baseline/v1/foundation.md`、`plan.json`及封存manifest，再读`docs/research/INDEX-shader-sources.md`。已回源修正四族/描边/C6/后处理多处实质错误，并沿用天气审计；v1是证据与更正基线，14模块六维仍有pending，禁止称全量规格完美闭合。`render_spec_baseline.py verify --require-complete`当前应返回2。先关资料缺口，再按foundation§7对照实现；不要调曝光/截图拟合或按旧伪码接湿身。旧handoff正文仅历史参考，其逐像素/LSB/删垃圾优先级全部失效；不碰用户9557项暂存索引、不改本轮运行时代码。

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
