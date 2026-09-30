# 官方 Shader 源码转写索引（2026-09-30 重建）

> 当前资料基石入口：[官方渲染证据基线v1](../render-baseline/v1/foundation.md)。本轮回源修订四族主着色、描边/C6各层和后处理；哈希封存是证据身份，不是全量认证。14模块六维待核见plan，完整规格门禁仍未通过；历史过程报告与社区建议不是官方规范。

来源：`_dump_1.5.3/AllShader_1.5.3/Assets/packages/com.hg.render-pipelines/runtime/shaders/`，SPIR-V-Cross反编译HLSL+wrapper分析。转写与历史实现/测试报告分开使用；独立oracle不能从我方实现循环生成。基线工具仅防来源漂移，不证明shader等价。

> 2026-09-30 核查更正：文档分布在本仓库和 `D:/EndfieldTechLib/`，不能只扫描 `docs/research/` 就断言未创建。C6 覆盖阴影/地面阴影等成果实际存在，见下方外部资料入口。行数只描述某个快照，不代表准确性；本轮审计范围见 [资料审计记录](source-contract-audit-20260930.md)，其它资料没有因此自动获得“完全准确”认证。

---

## 已完成文档（实际存在）

下表保留既有索引的覆盖范围登记；文件存在与内容准确是两回事，未在本批审完的模块不能仅凭这张表标为完整验收。

### 角色 NPR 着色（characternpr/）

| 文档 | 行数 | 覆盖范围 |
|---|---|---|
| `official-outline-skin-b273.md` | 以文件为准 | Skin Sub0 Pass1 b273；hair b306、主CharacterNPR b1088独立派发，不是三族共用b273。顶点VP3×3屏幕偏移和逐分量限制；平滑法线为TS半球xy，不是折叠八面体 |
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

## 外部技术库已有资料及v1版本档（不要重复调研）

| 文档 | 实际入口 | 状态 |
|---|---|---|
| OverlayShadow | [official-overlayshadow-b5.md](../render-baseline/v1/external/reports/translations/official-overlayshadow-b5.md) | 回源修订v1版本档；建议不是官方源码事实，须结合捕获及缺口 |
| 地面 ShadowReceiver | [official-shadowreceiver.md](../render-baseline/v1/external/reports/translations/official-shadowreceiver.md) | 回源修订版；不是刘海投脸通道，SH/bias生产仍待核 |
| C6 描边详解 | [official-outline-skin-b273.md](../render-baseline/v1/external/reports/translations/official-outline-skin-b273.md) | 与research同名文不是一份文本；三份逐行层也收入版本档 |
| C6 汇总 | [HANDOFF-C6.md](../render-baseline/v1/external/reports/translations/HANDOFF-C6.md) | 研究成果，不等同已实现或运行时全认证 |
| C6 抽查验收 | [2026-09-28-c6-acceptance.md](D:/EndfieldTechLib/notes/2026-09-28-c6-acceptance.md) | 抽查接受不代表逐项完整证明；8 项未确认仍须保留 |

原文仍在`D:/EndfieldTechLib/reports/translations/`，原始字节hash与UTF-8 LF版本档hash分别保存。GitHub现在也可读关键译读，不依赖D盘路径；差异证据及官方源文件仍需本地技术库/原dump，不得把未上传文件说成“从未创建”。

> 描边资料已经存在并回源修订，但“文档存在”不等于WP依赖全解除。源文件位于`characternpr_skin/Sub0_Pass1_{Fragment,Vertex}_b273.hlsl`；匿名生产端、完整片元尾链、运行时平滑法线输入仍待核，详见基线及C6更正。

---

## 其他相关文档（非 shader 转写，另行归档）

捕获/几何/MMD/历程类：`tifuluosi-capture-intake-20260917.md`、`tifuluosi-front-capture-20260917.md`、`renderdoc-capture-status.md`、`renderdoc-community-evidence-20260917.md`、`rendering-evidence-20260917.md`、`development-sync-20260923.md`、`endfield-reverse-engineering-full-journey.md`、`mmd-integration-research-20260926.md`。

---

## 转写质量要求（要求不等于已经逐项验收）

1. **只读源码**：不写单元测试、不写参考实现、不写 Unity C# 集成代码
2. **代表变体选择**：按实际draw签名、wrapper完整条件、keyword头选并保留同号Vertex；编号最小不证明catch-all或全OFF。未覆盖组合登记，不把单开diff拼成通用规格
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
