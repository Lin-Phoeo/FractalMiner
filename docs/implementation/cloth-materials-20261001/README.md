# Cloth 原生 D/P/E 与共享 ramp：2026-10-01

本增量按实际捕获的输入、view、sampler 和 shader 消费验收，不做官方截图逐像素拟合，不增加亮度/颜色补偿，不改最高细节模型、原场景、材质资产或质量设置。结果仅覆盖帧 6411 的两套 dry opaque Cloth 变体，不表示全角色、天气、场景或 MMD 已完成。

## 已确认的官方输入

主证据是离线 `正面.rdc` 帧 6411 的 event835/PS22255 和 event850/PS37669。实际反编译程序在 `Validation/draw-program-audit-20260930-01/event-{835,850}-fragment-{22255,37669}.hlsl`，以下编号是 set1 的实际 descriptor binding，不是根据贴图文件名猜测。

| 角色材质 | 输入 | binding | image | 原生 image/view 格式 | 尺寸、mip |
| --- | --- | --- | --- | --- | --- |
| Cloth01 | Base | 5 | 37995 | BC7_SRGB | 2048²、12 |
| Cloth01 | P | 2 | 37971 | BC7_UNORM | 2048²、12 |
| Cloth02 | Base | 6 | 37858 | BC7_SRGB | 2048²、12 |
| Cloth02 | P | 2 | 37868 | BC7_UNORM | 2048²、12 |
| Cloth02 | E | 3 | 37834 | BC7_SRGB | 2048²、12 |
| 两者共享 | DiffRamp | 3 / 4 | 8894 | R8G8B8A8_UNORM | 256×1、1 |
| 两者共享 | SpecRamp | 1 / 1 | 8907 | R8G8B8A8_UNORM | 256²、1 |

两变体都没有 ShadowLUT 贴图分支；Cloth01 没有 E 输入。Cloth02 actual PS 的 `_55` 是 P、`_57` 是 E。旧 `extracted-source-shading-reviewed-20260923/constants-by-event.json` 的 event850 `textures_set1.hlsl_name` 把 b2 错标为 ShadowLutTex、b3 错标为 MetallicGlossMap；这是旧的候选变体语义匹配错误，不是原始捕获发生变化。本表和实际 PS 数据流优先；不能继续复用那两个旧名称，也不能为消除差异重写封存快照。本轮未改旧文件或原 `.mat`；现有 Cloth02 材质的 P/E PNG GUID 名称本身正确。

D/P/N/E 共用 `_25`（set0/b4）的 Bilinear Repeat / nearest mip sampler，以及已经验证的 sourceUV 和捕获 global mip bias=-1。P 的 RGBA 含义仍为 metallic/specularMask/shadowMask/smoothness。ramp 用 `_24`（set0/b6）的 Bilinear ClampEdge / nearest mip，构造坐标、显式 LOD0，无额外 ST。没有重新实现或改写这些公式。

Base/E 的 RGB 由 sRGB view 解码一次，alpha 仍为线性；P/ramp 全通道线性。五张 BC7 各 5,592,432 bytes，保留原 12 mip（含最后的小块）；两 ramp 各 1,024 / 262,144 bytes。没有 PNG 转换、压缩重做、自动生成 mip 或性能降级 fallback。

## 验证中纠正的取样域问题

首次导出的 `replay-01` 用 `PickPixel(..., CompType.UNorm)`，该参数明确覆盖取样类型，不能把它称为 sRGB shader-domain 样本。现已按 actual view 对 Base/E 使用 `CompType.UNormSRGB`，P/ramp 使用 UNorm，重导出为 `replay-02`。见 [RenderDoc v1.46 CompType 官方定义](https://github.com/baldurk/renderdoc/blob/v1.46/renderdoc/api/replay/replay_enums.h)。RGB 转换交给各 GPU 的真实 view，不在 CPU/shader 人工拟合转换；310 个 Unity 原生读取与独立 RenderDoc typed-view 读取的 maxError=0，同时验证整数 Load，alpha 未被 gamma 转换。

两次导出的原生 bytes/SHA 全部相同；只有样本的取样域与相应说明更正。`replay-01` 和 `native-cloth-materials-20261001-01` 留作未批准历史，运行时只接受 `-02` 的 pinned manifest。

## 实现和入口

- `Assets/EndfieldShaderPack/EndfieldCapturedClothMaterials.cs`：七张唯一输入的固定身份、原生 upload/view/sampler 验证；D/P/E/ramp/normal 统一短期 MPB scope。先验证全部纹理与两套目标材质，再写入。常规退出精确恢复原 slot block；遇到外部替换纹理，保留该字段及后来字段，解除其余仍由本 scope 拥有的引用再释放纹理。
- `Assets/EndfieldShaderPack/EndfieldCapturedClothNormals.cs`：仅提取已有检查为可复用 `ValidateTextures`；BC5 工厂、采样和旧 binding 行为不变。
- `Assets/EndfieldShaderPack/Editor/EndfieldCapturedClothMaterialInputs.cs`：pinned 私有证据 loader，复用已经批准的原生 normal bundle；不从 PNG normal 借 sampler，不修改资产。
- `EndfieldPoseApplyValidation.cs`：在 label scope 恢复之后增加 `using var nativeClothMaterials = ...BindIfRequested(charRoot, report)`；开关为 `ENDFIELD_CLOTH_NATIVE_MATERIALS=1`，cube 仍用独立 `ENDFIELD_NATIVE_ENVIRONMENT_INPUTS=1`。新开关已含 BC5 normals，不必另开旧 normals 开关。
- `EndfieldNativeClothMaterialValidation.RunBatch`：真实 D3D11 GPU 输入/consumer/ownership 测试。报告变量 `ENDFIELD_CLOTH_MATERIAL_REPORT` 必须指向不存在的新文件。
- `Tools/capture_cloth_materials.py`：只读离线 RDC，核对 frame/PS/reflection/view/真实 sampler descriptor，exclusive 写入原生完整 mip；仅在 replay controller 和 capture 成功 Shutdown 后写 complete。

私有输入目录为 `Validation/Captures/native-cloth-materials-20261001-02`（ignored，不发布原始游戏数据）。可以通过 `ENDFIELD_CLOTH_MATERIAL_EXPORT` 指定同一批准包的其他位置；新 manifest 不会自动获得信任。manifest SHA 为 `325b1baea5838c66002566a5c2b020f976c3d015a5633d7a4642b6c0be610383`。各原生 payload SHA 固定在工厂 Specs 与本目录 verification.json。

本轮没有执行完整 `FullRunPoseApply`，因为旧入口会激活管线并动质量设置；仅验证编译/入口连接、真实 CharacterLit 消费和实际 recovered scene 的内存绑定。更没有把 Editor 私有输入包装成已可用的 Player 内容。本 scope 是排他的短期渲染 scope，不是长期动画编辑覆盖：没有纹理替换时仍会恢复整个先前 block，不承诺保留同时发生的其他字段写入。最终场景必须另行实现正常生命周期/打包入口，不能把测试开关当成最终产品。

## 结果及边界

真实 GPU 报告见本目录 `gpu-input-report.txt`；可复核记录还在 `D:/EndfieldTechLib/notes/cloth-materials-20261001-01/`。

- 原生采样：7 唯一纹理、62 mip、310 组 RGBA；SampleLevel 和整数 Load 均通过，采样 maxError=0，无 UV 翻转。
- 原生 bytes 与 mip 分区通过；null/损坏 payload 拒绝 14 例；缺少目标 slot、未捕获 ShadowLUT 开关、改变 sampler 均拒绝且不部分绑定。
- 两个 RGBA8 ramp 的 bilinear/Clamp 共4项通过。DiffRamp 的理想 float 四分之一权重插值与硬件差值为 3.814697265625e-6；该独立算术检查界限为 1/65535，不声称 GPU normalized-format filtering 与理想浮点逐位相同，也没有放宽上面的原生采样 gate。
- CharacterLit 生产消费4例：两套 Base debug 与原生 D/P/N/E 对独立 typed-view 解码常量 fixture 的等价性通过；ramp 保持原生输入。此处只证明输入消费，不把生产/helper 自比较算作公式独立正确性的证据。
- 实际 recovered character 两套 slot 绑定通过，scene dirty state 不变，无保存；常规恢复、root/slot merge、外部纹理 owner 保留与释放引用均通过；default shader passes=5。
- 回归：native BC5、native cube、Cloth normal(31 kernel/14 production)、Cloth emission(32/16)、Hair split(18) 五项独立 Unity batch 全部 exit0 / PASS。
- Python 全集 322 passed、3 历史 skipped、77 subtests，2 现有 Pillow deprecation warnings。新 exporter 的 API/IO fixture 行覆盖率96.64%，不是 C#/HLSL 或全项目覆盖率。Ruff、Pyright 通过；临时 pip-audit 环境未发现已知漏洞，未新增工程依赖。

材质参数与 native texture identity 是两回事。Cloth02 捕获 `_BaseColor` 是线性 `(0.94474745,0.93122000,1,1)`，不是白色；已有 Unity `.mat` 的 authored 值 `(0.97530866,0.9691358,1,1)` 不能直接拿来声称漂移或当作亮度补偿。本增量没有改这个参数，测试中的白色只是明示的合成 fixture，不是官方 Cloth02 的替代常量。后续参数审计必须核对 upload 的实际颜色域。

封存状态仍如前：v1严格verify失败仅授权 handover 文档 drift（6771 files/18 anchors/79 pending）；v2失败仅既有 CharacterLit/OfficialHair runtime drift（149/7/24 pending）。不重写 seal，不报全 snapshot PASS。主 HEAD 与索引逐字节未动；索引9557 entries（其中9555 paths 对 HEAD staged 改变），原场景/QualitySettings/GraphicsSettings SHA 未变。

## 下一步

1. 用同样的实际 PS→binding→image/view→原生 bytes→typed-view GPU→生产消费链审计 Skin、Hair、Eye 输入和 LUT，先修旧语义匹配错误，不靠社区候选名或截图调参。
2. 对照封存资料补尚未实现/未认证的材质与全局参数、湿身/覆盖/透明、空间光照/阴影/雾及 native vertex/skin basis 分支。
3. 统一正常演示场景的绑定、全局状态、后处理、停止/切场景恢复与 Player 打包生命周期，再提供直接可看的最终场景。继续最高细节，不加模型LOD或性能档。
4. 接解包动作与 MMD 的骨骼/IK/表情/物理/相机及出片验收。以上并未因两套衣物输入通过而自动完成，不估算虚假的“还差一点百分比”。
