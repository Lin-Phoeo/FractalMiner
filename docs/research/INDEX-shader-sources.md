# 官方 Shader 源码转写索引（2026-09-30 重建）

来源：`_dump_1.5.3/AllShader_1.5.3/Assets/packages/com.hg.render-pipelines/runtime/shaders/`，SPIR-V-Cross 反编译 HLSL + wrapper shader 分析。所有文档均为**只读转写**，不含单元测试或参考实现（独立 oracle 由验收方另写）。

> 2026-09-30 核查更正：文档分布在本仓库和 `D:/EndfieldTechLib/`，不能只扫描 `docs/research/` 就断言未创建。C6 覆盖阴影/地面阴影等成果实际存在，见下方外部资料入口。行数只描述某个快照，不代表准确性；本轮审计范围见 [资料审计记录](source-contract-audit-20260930.md)，其它资料没有因此自动获得“完全准确”认证。

---

## 已完成文档（实际存在）

下表保留既有索引的覆盖范围登记；文件存在与内容准确是两回事，未在本批审完的模块不能仅凭这张表标为完整验收。

### 角色 NPR 着色（characternpr/）

| 文档 | 行数 | 覆盖范围 |
|---|---|---|
| `official-outline-skin-b273.md` | 240 | 描边 Pass（Sub0 Pass1，skin/hair/cloth 共用 catch-all b273）。本质是"缩水 ForwardLit"：片元跑近乎完整打光后在 `_44_Stripped_48>0.5` 分支做去饱和/描边色/rim 调色；挤出在裁剪空间外扩（屏幕空间偏移 + 逐分量像素钳制），非物体空间挤出。与主体共用 `_BaseMap`，无专用描边贴图 |
| `official-forwardlit-skin-b138.md` | 374 | 皮肤 ForwardLit（Skin family=1，face/body 均走此路径）。CP3 环境色、CP4 光色覆盖、SDF/LUT/HighlightMap |
| `official-forwardlit-hair-b125.md` | 362 | 头发 ForwardLit。CP2 环境色、CP5 光色、各向异性主/次高光 + LineMap |
| `official-forwardlit-cloth-b401.md` | 393 | 布料 ForwardLit（b401 源码转写本体）。环境 BRDF 12 常量、GGX 1e-5、ClearCoat power-3、LOD=1.2·log2(rough)+5。注：文中旧的"b401=body"归属已撤回，body 实走 Skin |
| `official-forwardlit-eye-b28.md` | 313 | 眼睛 ForwardLit（无描边 pass）。CP13.x/y/z 三路虹膜项、matcap 交叉混合、视差瞳孔 |
| `official-source-shading-20260923.md` | 110 | family 分工、SDFMask.g 语义、LUT sRGB 索引、GGX epsilon、IBL 门控。**b401→b114 body 归属的权威更正来源** |
| `character-shadow-evidence-20260923.md` | 265 | 角色阴影证据链快照；独立 C6 文档在外部技术库（见下表）。2026-09-23 点时刻快照，内含 shader 行号已漂移，勿当当前状态 |

### 后处理（postprocessing/）

| 文档 | 行数 | 覆盖范围 |
|---|---|---|
| `official-postprocess-uberpost.md` | 201 | 主后处理链（曝光/LUT/抖动/bloom/vignette 等）。末步为**线性→sRGB 编码(OETF)**，非解码（2026-09-30 已更正方向）|
| `official-postprocess-stack.md` | 242 | DOF/TAAU/SMAA/lightshaft/lensflare/anamorphic/frosted/sharpen 八 shader |
| `official-postprocess-lutbuilder2d.md` | 263 | LUT 烘焙（曝光/分级/tone 曲线）。原"LUT 必须 sRGB 编码/解释 skin 偏暗"结论已作废（方向误判）|
| `official-postprocess-finalpass.md` | 138 | 最终 pass。sRGB 往返方向标注正确（编码 0.0031308 / 1÷2.4，解码 0.04045 / ×2.4）|
| `official-postprocess-bloom.md` | 73 | bloom 预合成（被 uberpost 的 _BloomTexture 消费）。soft-knee、高斯权重、B-spline 上采样 |

### 场景雨系统（materials/rain/ + characternpr liquidag）

| 文档 | 行数 | 覆盖范围 |
|---|---|---|
| `official-rain-scene.md` | 以文件为准 | 四雨 shader 代表变体导读；09-30 修正 MV/行号/公告板等错误。光照与部分雪花分支尚未完整核实 |
| `official-liquidag-wetness-b12.md` | 以文件为准 | LiquidAg b12 雪覆盖与主角色 b400 湿身分开说明；09-30 修正天气通道/动画/粗糙度/IBL。生产端和湿天气实际绑定仍待核 |

---

## 外部技术库已有资料（不要重复调研）

| 文档 | 实际入口 | 状态 |
|---|---|---|
| OverlayShadow | [official-overlayshadow-b5.md](D:/EndfieldTechLib/reports/translations/official-overlayshadow-b5.md) | 已有两 pass 译读；里面的实现建议不是官方源码事实，须结合审计更正与捕获绑定 |
| 地面 ShadowReceiver | [official-shadowreceiver.md](D:/EndfieldTechLib/reports/translations/official-shadowreceiver.md) | 已有译读；不是刘海投脸通道，SH/bias 等匿名语义仍待核 |
| C6 描边详解 | [official-outline-skin-b273.md](D:/EndfieldTechLib/reports/translations/official-outline-skin-b273.md) | 与仓库内同名文档不是同一份文本，逐行层/变体 diff 在外部目录 |
| C6 汇总 | [HANDOFF-C6.md](D:/EndfieldTechLib/reports/translations/HANDOFF-C6.md) | 只读研究成果，不等同已实现或全部运行时验证 |
| C6 抽查验收 | [2026-09-28-c6-acceptance.md](D:/EndfieldTechLib/notes/2026-09-28-c6-acceptance.md) | 抽查接受不代表逐项完整证明；8 项未确认仍须保留 |

外部路径是当前机器入口；GitHub 读者若没有该技术库应明确报资料不可访问，不得把它再次标成“从未创建”。

> 描边 `official-outline-skin-b273.md` 已于 2026-09-30 补齐（见上表），WP1.3/WP1.4a 依赖已解除。源文件位于 `characternpr_skin/Sub0_Pass1_{Fragment,Vertex}_b273.hlsl`（1012+509 行），文档含 7 处 ⚠待核（顶点输入语义疑似错位、参数语义为数学推断、片元法线取自 `_GBufferTexture1` 等）。

---

## 其他相关文档（非 shader 转写，另行归档）

捕获/几何/MMD/历程类：`tifuluosi-capture-intake-20260917.md`、`tifuluosi-front-capture-20260917.md`、`renderdoc-capture-status.md`、`renderdoc-community-evidence-20260917.md`、`rendering-evidence-20260917.md`、`development-sync-20260923.md`、`endfield-reverse-engineering-full-journey.md`、`mmd-integration-research-20260926.md`。

---

## 转写质量要求（要求不等于已经逐项验收）

1. **只读源码**：不写单元测试、不写参考实现、不写 Unity C# 集成代码
2. **代表变体选择**：每 Pass 取编号最小 Fragment（catch-all 或首个分支）+ 同号 Vertex 完整抽取，其余变体只补 keyword 差异
3. **数值保真**：数字/swizzle/clamp/pow 指数逐字保留；mad/位运算改普通算式但不改数值
4. **行号标注**：每个常量和公式后标 `file.hlsl:行号`
5. **不确定标记**：不确定标 `⚠待核`，禁止编造
6. **中文输出**：所有文档中文撰写，代码/shader 术语保留英文

---

## 使用建议

1. **实现前先读对应文档**：每个 WP 开工前读目标 shader 文档全文，理解结构与数据流，再动手写 Unity 代码
2. **按文档标注的行号回源码核对**：遇到 `⚠待核` 或点时刻快照（如 shadow-evidence）时，回 hlsl 源码逐字确认，勿信旧行号
3. **核查结构与绑定**：按用户当前要求，不以官方截图逐像素残差作为目标；查源码、变体、资源格式/色彩空间、常量位布局、坐标空间、pass 顺序及混合/深度/模板状态。仅使用现有捕获离线证据；缺少天气帧时明示限制，不为补证据绕过保护。
4. **增量补文档**：发现遗漏公式/常量时增补进原文档并标注补充日期

---

**最后更新**：2026-09-30（Codex资料审计更正；沿用此前Claude重建的索引，不代表本次全量shader验收）
