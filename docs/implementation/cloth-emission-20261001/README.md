# Cloth emission / alpha selection — 2026-10-01

本轮闭合的是捕获帧 6411、event 850（cloth_02）的**发光和关联的直接漫反射选择链**，不是整个 Cloth / HGRP / 官方最终画面的完成证明。没有官方截图逐像素拟合，没有提高亮度、改 LUT、改材质或隐藏 pending。

## 权威来源与数据绑定

- 实际 PS：`Validation/draw-program-audit-20260930-01/event-850-fragment-37669.hlsl`，ResourceId::37669，SHA-256 `d47f4f5dbffcfd2d67c57bc42bbd070448fe0c3ce6413df63037acede06fd87a`。
- 实际 VS：同目录 `event-850-vertex-37668.hlsl`，SHA-256 `5af0f001288615221c58a05307073b4a1ad7673312b1f9b1f0abb95d2b09a205`。
- 实际绑定和常量：`Validation/Captures/tifuluosi-front-20260917/replay-details-01/draw-details.json` 中 event 850 / ShaderStage.Pixel。解包的命名候选 `characternpr/characternpr/Sub0_Pass0_Fragment_b472.hlsl` 帮助命名，不能取代实际捕获身份。

| PS set 1 binding | 实际资源 | 用途 |
| --- | --- | --- |
| 1 | ResourceId::8907 | SpecRamp |
| 2 | ResourceId::37868 | P / MetallicGloss |
| 3 | ResourceId::37834 | E / Emission |
| 4 | ResourceId::8894 | DiffRamp |
| 5 | ResourceId::37828 | Bump |
| 6 | ResourceId::37858 | Base |

不能沿用旧导出摘要的 b1011 命名把 binding 2/3 当作 ShadowLut/Metallic。实际 `set1/b0` 的 `_child6=0` 对应 AlphaPremultiply，`_child7=8` 对应 EmissionBrightness；`set0/b16` 的 `_child16=-1` 对应 GlobalMipBias。候选命名仍不构成实际 sampler/filter/address/image-view 状态证明。

## 实现契约

实际 PS 的 `_491`、`_2265`、`_2267`、`_2424`、`_2452` 给出：

```text
baseAlpha = baseSample.a * BaseColor.a
factor = (1 - AlphaPremultiply) + baseAlpha * AlphaPremultiply
direct = directDiffuse * factor + directSpecular
color = saturation(direct) + capturedRims
color = (color + ((emissionSample.rgb * EmissionColor.rgb) * EmissionBrightness) * factor) + IBL
... local-light processing ...
color = VFX(color)
color = color * outputExposure
... fog/output ...
```

factor 是浮点表达式，不转 bool，不 clamp；不是最终输出 alpha、裁剪 alpha 或 emissionSample.a。高光与 IBL 不乘 factor。发光不参与直接光的饱和度增强，且在 IBL 之前加入。本轮没有新增 local lights、rims 或 fog 的实现。

修改位置：

- `Assets/EndfieldShaderPack/EndfieldOfficialClothEmission.hlsl`：纯 float factor / emission 公式，无色彩空间转换。
- `EndfieldCharacterLit.shader`：增加默认 0 的 `_AlphaPremultiply`；采样 float BaseAlpha；调用 Cloth helper 时传入 factor / emission，移除 helper 返回之后的旧发光加法。
- `EndfieldOfficialCloth.hlsl`：factor 仅作用于直接漫反射；发光插入直接光饱和度之后、IBL 之前；保留旧参数签名兼容 overload。
- Base / P / Bump / E 共享已应用一次 BaseMap_ST 的 sourceUV 与捕获 bias -1；constructed Diff/View/SpecRamp UV 不再额外应用贴图 ST，保持 LOD 0。Bump **采样域**已修正，但其原始插值法线/TBN 算法还未闭合。

实际 `M_actor_typhoea_cloth_02.mat` 已有 UseEmission=1、Brightness=8、白色 EmissionColor 和 E 贴图，不改。E GUID 为 `64b56671e67cb8b41bb15eba1fb48beb`，导入为 Default / sRGB=1；没有把彩色 E 变成 NormalMap 或再次手动 gamma。捕获 AlphaPremultiply=0 与新增默认值一致，未写回材质。

## 验证与复现

全部在单独 Unity 2022.3.30f1 / URP 14 / D3D11 批处理执行，不加载/保存正式场景，不启动游戏；GPU 为 RTX 3060 Laptop。入口 `EndfieldShaderPack.EndfieldClothEmissionValidation.RunBatch`；先将 `ENDFIELD_CLOTH_PROBE_REPORT` 指向一个**不存在**的输出文件，再以 `-batchmode -force-d3d11 -executeMethod ... -quit` 启动 Editor。

- 新结构门禁先 RED（4 failure / 1 missing-helper error / 1 existing-binding pass），实现后六项 GREEN。
- GPU 32 组 kernel：覆盖 alpha 0/.25/1/1.5、selector 0/.25/1/-.5、brightness 0/8；双精度 CPU 参照独立于 HLSL helper。max error `5.9604644775390625e-8`，门限 `3e-6`。
- GPU 16 组实际 CharacterLit：9 组 alpha/selector、非恒等 BaseST 且忽略 EmissionST、BaseSample.a×BaseColor.a、VFX/单次输出曝光、直接漫反射 .25 缩放、高光不缩放、常量 cube IBL 不缩放、skin 隔离、source-off legacy 隔离。发光/UV 最大 error `5.21540641784668e-8`；VFX error `6.3240900738392725e-8`；三个隔离误差均 0。门限保持 `2e-5`（VFX `3e-5`）。
- CharacterLit 默认关键字五个 pass 均可编译/SetPass。没有覆盖所有关键字组合。
- Hair 回归：18 组法线、3 项生产路径隔离仍 PASS，max error `4.059186498039935e-8`，HN 核心/材质未改。
- Python 回归：281 passed、3 historical skipped、3 subtests passed；两条既有 Pillow 废弃警告。Ruff、Pyright 均通过；独立 Python 测试工具环境 pip-audit 无已知漏洞。没有添加 Unity 依赖。

批处理 01/02 的生产测试失败来自测试 fixture：线性工程的 Color 属性上传会做 sRGB 解码，**SetVector 也不能绕开属性元数据**。03 改为 `SetColor(linearFixture.gamma)`，让 GPU 收到预期的线性 fixture 后通过；04 增加 diffuse/spec/IBL 隔离也通过。运行时没有增加 gamma 或修改材质颜色。失败日志保留，未放宽阈值。

独立 GPU 公式比较不属于官方截图逐像素拟合。合成贴图没有真实 mip chain，常量 cube 只测 factor 隔离；不能把这些结果说成真实贴图/mip/IBL 数据等价。HLSL 没有仪器化覆盖率，不虚报 80% 或全模块覆盖。

外部证据：`D:/EndfieldTechLib/notes/cloth-emission-20261001-01/` 的 `gpu-probes-04.txt`、`unity-batch-01..04.log`、`hair-regression-01.txt`。关键数值/哈希见相邻 `verification.json`，源码测试入口也已入库。

## 封存与恢复边界

- v1 6771 文件/18 anchors，原始完整性验证通过，79 个 pending 未改。
- v2 149 文件/7 anchors，原始验证仍仅报两个已授权运行时快照变化：CharacterLit 与上一轮 OfficialHair；没有其他错误。24 个 pending 未改。**不能说 v2 全快照验证通过**；实际 source/inventory/anchors/digest 未变。本轮 OfficialCloth.hlsl 不在 v2 文件清单内，其实现版本通过本轮代码提交留存，而不是虚构为 v2 已封存文件。
- 修改前两个 runtime 文件和主 index 精确副本在上述外部目录。记录分支父提交 `138c2eac519efb826001cf03018270d421d8add1`。使用独立 index / commit-tree / CAS update-ref 发布，不 checkout/reset 用户工作树。
- 用户主 HEAD `fc9d4869803f439ffff83311986190e8a8b5ade3`、主 index 9557 条 entry、Recovered 场景、Quality/Graphics、原始资料/材质均保持不变。没有更新封存 manifest 来掩盖实现变化。

## 下一阶段

优先核对 Cloth PS `_504.._567`：原始插值 N/T、R*A/G 解码、Z 下限、缩放顺序、TBN 和背面符号，不能继续把现有 half / CharTBN 当作官方 float 链。沿用“实际 draw 身份 → 源表达式 → 独立 CPU/GPU 数值 → 生产消费路径”的门禁，不调整官方截图误差阈值。

真实 sampler descriptors/image views/mip fidelity、native vertex-fetch/skinning/part root、屏幕深度 rims/局部灯光/雾、clearcoat、透明输出、wet/weather 等 variant、全局后处理，仍需各自证据与实现闭合。解包动作/MMD 留在其独立工作线上。本轮完成不等于官方渲染全部完成。
