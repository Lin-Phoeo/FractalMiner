# 官方 Shader 源码转写索引（2026-09-29 状态）

来源：`_dump_1.5.3/AllShader_1.5.3/Assets/packages/com.hg.render-pipelines/runtime/shaders/`，SPIR-V-Cross反编译HLSL + wrapper shader分析。所有文档均为**只读转写**，不含单元测试或参考实现（独立oracle由验收方另写）。

---

## 已完成文档

### 角色NPR着色（characternpr/）

| 文档 | 覆盖范围 | 行数 | 代表变体 | 状态 | 验收修正 |
|---|---|---|---|---|---|
| `official-outline-skin-b273.md` | 描边Pass（skin/hair/cloth共用） | 507 | Sub0_Pass1_Fragment_b273 (catch-all) | ✅ 已验收 | C6核实：平滑法线是2通道切线空间半球编码；FOV atan多项式系数-0.301894.../0.0872929...；宽度公式114.5915679度因子×0.04×0.005 |
| `official-forwardlit-skin-b138.md` | 皮肤ForwardLit（face专用） | 906 | Sub0_Pass0_Fragment_b138 | ✅ 已验收 | 09-28核实：变体专属纹理_ShadowLutTex/_SDFMask/_SDFLightmap/_HighlightMap；无_CameraDepthTexture深度边缘光 |
| `official-forwardlit-hair-b125.md` | 头发ForwardLit | 881 | Sub0_Pass0_Fragment_b125 | ✅ 已验收 | 各向异性发丝高光；_CharacterParams2平坦环境色；深度边缘光用_CameraDepthTexture |
| `official-forwardlit-cloth-b102.md` | 布料ForwardLit | 847 | Sub0_Pass0_Fragment_b102 | ✅ 已验收 | 无SSS；无各向异性；有丝袜_SilkStockings* |
| `official-forwardlit-eye-b61.md` | 眼睛ForwardLit（无outline） | 639 | Sub0_Pass0_Fragment_b61 | ✅ 已验收 | 瞳孔折射_IrisMask/_IrisParallax；无描边pass |
| `official-overlayshadow-b5.md` | 刘海投脸阴影 | 285 | Sub0_Pass0_Fragment_b5 | ✅ 已验收 | C6核实：刘海ShadowCaster→此shader接收；非shadowreceiver |
| `official-shadowreceiver.md` | 地面接收角色投影 | 未统计 | 单pass | ✅ 已验收 | C6核实：脚下地面投影，非刘海 |
| `official-liquidag-wetness-b12.md` | 雨淋湿身效果 | 186 | Sub0_Pass0_Fragment_b12 (catch-all) | ✅ 已验收 | 官方公式在此；工程材质_RainEffectIntensity全0；C#声明_CharacterParams10但未读取 |

**characternpr 完成度**：主要材质（skin/hair/cloth/eye+outline+overlayshadow+shadowreceiver+liquidag）已完整转写。剩余：eye无outline的架构原因（shader wrapper确实无Sub0_Pass1）、各forwardlit的剩余keyword分支（_EMISSION/DITHER/VFX_DISSOLVE等，待实现时按需补）。

---

### 后处理（postprocessing/）

| 文档 | 覆盖范围 | 行数 | 代表Pass/变体 | 状态 | 验收修正 |
|---|---|---|---|---|---|
| `official-postprocess-uberpost.md` | 主后处理链（曝光/LUT/抖动/bloom/vignette/BWFlash等） | 209 | Pass0 b288/b336、Pass1 b726/b727、Pass2 b748/b756 | ✅ 已验收 | 09-28核实：b756关键字是BWFLASHTEX+RADIAL_BLUR_CHROMATIC_ABERRATION（非BWMASKTEX）；极坐标LUT采样在两条路径都出现且槽位不同 |
| `official-postprocess-stack.md` | DOF/TAAU/SMAA/lightshaft/lensflare/anamorphic/frosted/sharpen | 298 | 8个shader各自代表变体 | ✅ 已验收 | GLM-5.3-flash交付，Claude验收通过 |

**待核项**：uberpost的DIRTY_LENS/LENS_DISTORTION/VIGNETTE_MASK/BLOOM_DIRT/USER_LUT/PERFORM_SHARPEN六分支未逐行（常量槽已定位，实现时按需补）；postprocess-stack内标记的⚠待核项（某些变体数/keyword组合）。

---

### 场景雨系统（materials/rain/）

| 文档 | 覆盖范围 | 行数 | shader数 | 状态 | 验收修正 |
|---|---|---|---|---|---|
| `official-rain-scene.md` | farrain/rainsplash/sceneeffectrain/screenraindropfx四shader | 180 | 4 | ✅ 已验收 | 09-28核实：§3 sceneeffectrain的b12行号整体偏低+14~20（frag_main实际起于:214，垂直遮挡SampleCmp在:228-230）；其余三者行号经抽查准确 |

**待核项**：RAIN_WAVE/RAIN_LIGHTING/SNOW_COLLISION/SNOW_FLAKE/HG_ENABLE_MV各分支逐行（变体b7-b13/b13-b27未读）；farrain顶点动画（UV下落/wave）与rainsplash顶点（阶段推进）未逐行（242行级）；ScreenRainDropFX的Distortion消费端（哪个pass读它的输出）不在rain/目录内。

---

## 未转写但已定位

### 其他材质shader

- `materials/character/` 目录：基础character.shader（非NPR，可能是fallback）
- `materials/scene*/` 目录：场景物体着色器（terrain/vegetation/building等）
- `materials/vfx*/` 目录：特效粒子shader
- `materials/ui*/` 目录：UI shader（含uiimageblur）

### 其他后处理

- `postprocessing/bloom/`：bloom.shader（预合成，被uberpost的_BloomTexture消费）
- `postprocessing/lutbuilder2d/`：lutbuilder2d.shader（曝光/分级/tone曲线烘焙进LUT）
- `postprocessing/motionblur/`：运动模糊
- `postprocessing/distortion/`：折射（消费screenraindropfx输出）
- `postprocessing/fog*/`、`postprocessing/volumetricfog/`：雾系统

---

## 转写规则（所有已完成文档均遵循）

1. **只读源码**：不写单元测试、不写参考实现、不写Unity C#集成代码
2. **代表变体选择**：每Pass取编号最小Fragment（catch-all或首个分支）+同号Vertex完整抽取，其余变体只补keyword差异
3. **数值保真**：数字/swizzle/clamp/pow指数逐字保留；mad/位运算改普通算式但不改数值
4. **行号标注**：每个常量和公式后标`file.hlsl:行号`
5. **不确定标记**：不确定标`⚠待核`，禁止编造
6. **中文输出**：所有文档中文撰写，代码/shader术语保留英文

---

## 验收流程

**第一轮**：kimi-k3/deepseek/GLM-5.3-flash批量转写 → Claude对照源码抽查（行号/常量/公式/结构）→ 更正写入文档头部`验收修正`段落 → 接受或退回重做。

**第二轮**（实现时）：根据文档实现Unity shader/C# → 合成已知输入跑shader单测 → RenderDoc捕获新帧逐像素比对 → 反馈文档遗漏/错误 → 增补或修订。

---

## 下一步优先级（按roadmap WP排序）

### WP1.3 网格通道补全 + 官方描边顶点

需要：`official-outline-skin-b273.md` 顶点部分（已有）+ RenderDoc回读官方顶点流（切线/uv1/顶点色） → 重建pmx/FBX导出 → 验证描边法线与官方逐字节一致。

### WP1.4a 描边全打光

需要：`official-outline-skin-b273.md` 片元（已有）→ 实现"缩水ForwardLit"（借GBuffer八面体法线） → 逐部件比色A/B门禁。

### WP1.4b 刘海投脸 + 地面投影

需要：`official-overlayshadow-b5.md`（已有）+ `official-shadowreceiver.md`（已有）→ 新pass/材质 + 场景接线 → 逐部件比色A/B门禁。

### WP1.4c 雨淋湿身

需要：`official-liquidag-wetness-b12.md`（已有）→ 接`_CharacterParams10` + `_SilkStockings*` → C#驱动 → 逐部件比色A/B门禁。

### WP1.4d dither / 透明 / clearcoat矢量化

需要：各forwardlit文档的DITHER/EMISSION关键字分支补全 → 实现 → 门禁。

### WP2 后处理还原

需要：`official-postprocess-uberpost.md`（已有）+ `official-postprocess-stack.md`（已有）+ 待补的bloom/lutbuilder2d/distortion文档 → 实现完整后处理栈 → 与官方截帧后处理输出逐像素比对。

### WP3 雨系统集成

需要：`official-rain-scene.md`（已有）+ 场景雨材质/C#控制器 → 接入展示场景 → 肉眼验收。

---

## 使用建议

1. **实现前先读对应文档**：每个WP开工前读目标shader文档全文，理解结构与数据流，再动手写Unity代码
2. **按文档标注的行号回源码核对**：遇到不确定/⚠待核标记时，回hlsl源码逐字确认
3. **捕获新帧验证**：实现后让用户协同RenderDuck重新捕获，逐像素比对找残差
4. **增量补文档**：发现文档遗漏公式/常量时，增补进原文档并标注补充日期

---

**最后更新**：2026-09-29（Claude Opus 5.5）
**贡献者**：kimi-k3 (C5官方draw标签)、deepseek (C1-C4早期交付)、GLM-5.3-flash (postprocess-stack/uberpost/rain/liquidag)、Claude (全部验收+roadmap)
