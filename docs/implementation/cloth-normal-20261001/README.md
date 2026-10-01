# Cloth fragment normals — 2026-10-01

本轮核正捕获帧 6411 的 Cloth01 / Cloth02 **片元法线公式与生产消费路径**。没有截图拟合或亮度调参；没有修改正式场景、材质、N/HN 导入设置或上一轮 emission/Hair helper。整个 Cloth/HGRP/官方最终渲染尚未完成认证。

## 实际来源

- event 835 / PS22255：`Validation/draw-program-audit-20260930-01/event-835-fragment-22255.hlsl`，`_502.._554`。SHA-256 `b2d68a56bc8fa136502b2ae2b08f0e56705f078808a413fbfa8657afa287f1f8`。
- event 850 / PS37669：同目录 `event-850-fragment-37669.hlsl`，`_504.._568`。SHA-256 `d47f4f5dbffcfd2d67c57bc42bbd070448fe0c3ce6413df63037acede06fd87a`。
- VS37668 的 `_13/_15/_16` 确认 BaseMap_ST UV、顶点阶段归一化 world N/T、保留切线 sign；片元使用其普通插值结果，不能再归一化 TBN 的各行。

两条实际 PS 的法线链同构：

```text
xy = float2(sample.r * sample.a, sample.g) * 2 - 1
z = max(1e-16, sqrt(1 - clamp(dot(xy,xy), 0, 1)))
TS = float3(xy * BumpScale, z)
TBN = [rawT, cross(rawN,rawT) * rawSign, rawN]
world = TS * TBN
mapped = world * rsqrt(max(dot(world,world), FLT_MIN)) * faceFactor
geometry = normalize(rawN) * faceFactor
faceFactor = front ? 1 : (-1 + 2 * BackFaceNormalFlip)
```

注意 Z 下限在 sqrt **之后**，不是旧 `sqrt(max(1e-16,...))`；XY 的 scale 在 Z 重建之后且不乘 Z；B 通道无关。mapped 和 geometry 的归一化方式不同。per-part root 矩阵不是这个插值 TBN 的替代品。

## 实现

- 新 `Assets/EndfieldShaderPack/EndfieldOfficialClothNormals.hlsl`：纯 float 解码，保留 raw 插值长度、非正交性、切线 sign 和浮点 faceFactor，不擅自 sanitize 源域。
- `EndfieldCharacterLit.shader` 的 source Cloth 跳过公共 half / CharTBN；float SampleBias → helper → float mapped/geometry/view 直接送 Cloth lighting 与 VFX。共享 sourceUV / bias -1 保持上一轮契约。
- 显式 `_EndfieldDebugValueMode=9/10` 仅在 source Cloth 返回 signed mapped/geometry，供隔离测试。正常 mode=0 不受影响，不是渲染调色开关。
- 未启用 Bump 的路径保留旧 mapped fallback，**不是**本次捕获 bump variant 的认证对象。其他 family / source-off 仍走已有逻辑。
- 修正旧注释中“压缩顶点法线解压生成 RGB 法线贴图”和“旧半精度解码与官方逐行一致”两项错误，区分原生模型法线与材质 N/HN 数据链。

## 验证

入口 `EndfieldShaderPack.EndfieldClothNormalValidation.RunBatch`；在独立 Unity Editor 批处理使用 `-batchmode -force-d3d11 -executeMethod ... -quit`，将 `ENDFIELD_CLOTH_NORMAL_REPORT` 指向不存在的输出文件。初始化临时 preview scene 的 URP，不加载/保存正式场景；报告使用 CreateNew，不覆盖旧证据。

- TDD：修正测试端对既有导入类型的错误假设后，RED 为 1 failure / 4 errors / 1 existing-binding pass，实现后新增六项结构门禁 GREEN。最初测试误假定 N 为 Default，实际为 NormalMap；该发现留存，不拿测试假设改资产。
- GPU 31 项 kernel：15 组 × mapped/geometry，加单独 Z-floor 相对误差测试；覆盖 R×A/G、无关 B、等效 RA、raw 非单位/非正交 basis、fractional sign、圆盘边界/圆外、scale 0/负值/先后顺序、零 world guard、背面/零/小数 factor。独立 double CPU 求值，不调用 HLSL helper；源 float 常量保留其二进制值。
- Kernel max component error `1.3564337875138222e-7`（门限 `2e-5`）。Z-floor GPU 值 `1.0000000168623835e-16`，相对 error `1.6862383489524291e-8`（门限 `1e-5`），能区分旧 `1e-8` 下限。
- GPU 14 项 production：8 项真实 CharacterLit VS→不同顶点 N/T 插值→采样→mapped/geometry，覆盖两种 winding × 两种 BackFaceNormalFlip；B 通道隔离；CPU-decoded 方向通过 unmapped geometry 输入作独立直接漫反射消费参照；改变 normal map 的漫反射响应；normal-sensitive VFX；skin 和 source-off diagnostics 隔离。
- production mapped error `3.198527775971627e-8`、geometry error `4.195806024842597e-8`。直接漫反射参照 difference=0，normal map 响应 `0.01485404372215271`；VFX error `8.282911323487241e-8`。门限保持 `2e-5`，响应要求 ≥`1e-3`。
- 生产参照测试证明 mapped N 确实被消费，**没有**重新认证全部 Cloth 光照公式；8 个 signed diagnostics 也不是最终画面认证。face sign 不硬编码平台 winding，但要求 Flip=1 两侧不翻转、Flip=0 两侧互反。
- CharacterLit 默认关键字五个 pass 可编译/SetPass，无 C#/shader compile error。HLSL 无仪器化覆盖率；不虚报 80% / 全平台覆盖。当前 D3D11 上的 float 行为不证明其他 native16 平台（完整 frag 仍返回 half4）的行为。
- Hair 回归：18 normal + 3 production invariants PASS。Emission 回归：32 kernel + 16 production PASS。Python：287 passed、3 historical skipped、3 subtests passed、两条既有 Pillow 警告；Ruff/Pyright 通过。
- 本轮没有新增项目依赖。pip-audit 已运行，但 PyPI 和备用 OSV 都遭 TLS EOF，**在线依赖漏洞审计未完成**，不能标成 PASS；未关闭 TLS 校验。上一轮审计结果不是本轮在线审计的替代。

三次 normal batch 均通过：01 为 29 kernel / 12 production；02 加入 diffuse 消费与实际导入格式观察（29/14）；03 加入 zero-world guard（31/14）。外部原始记录：`D:/EndfieldTechLib/notes/cloth-normal-20261001-01/`，最终 `gpu-probes-03.txt` 与对应日志；关键数值和哈希见 `verification.json`。

## 关键新发现：贴图还不无损

只读 Unity 观察确认两张 `T_actor_typhoea_cloth_01/02_N.png` 均为 2048²、NormalMap / sRGB=false、实际 `RGBA_DXT5_UNorm`。捕获 Cloth02 Resource37828 的 XML creation 明确是 **BC5_UNORM / 2048² / 12 mip / 单层**，因此当前重压缩不能宣称无损。

本地 Core 14.0.11 `ShaderLibrary/Packing.hlsl::UnpackNormalmapRGorAG` 说明 R×A/G 兼容 BC5 `(x,y,0,1)` 和 DXT5nm `(1,y,0,x)`。所以“NormalMap 一定错/必须 Default”不成立，但结构兼容也不等于字节/mip 等价。本轮保留 type1/sRGB0/convert0/flipGreen0；没有调用旧的全量 `RepairPackedTextureImports()` 或会改场景的 MaterialValidation。

下一阶段已有原块候选，不必从 PNG 再编码：

| 捕获资源 | `C:/Users/Administrator/Downloads/tifuluosi.zip` 条目 | bytes | SHA-256 |
| --- | --- | --- | --- |
| Cloth01 Resource37987 | `002959` | 5592432 | `e96d6fd9c9a1850ab0655f8fe42fd156beb992d19008fea1a5ac45e5c6c62841` |
| Cloth02 Resource37828 | `004532` | 5592432 | `9c7ab3cb6d4c7e85284f4caee838c5dd8978495ed147b38856808758b7db35d8` |

XML Internal::Initial Contents 关联这些 buffer；主 agent 已只读复核 ZIP 条目长度/哈希。**长度正确尚不证明 mip 排布或绘制时资源未变化**。必须用已有离线 RDC replay 的最终 texture data/DDS 交叉核对，再按原块旁路加载（不覆盖旧 PNG/meta），禁止 Apply 重新生成 mip。可参考 `EndfieldCaptureAssets.ImportCube` 的校验/上传设计，但不要调用其整体 ImportAll。

已有行方向线索表明 raw block 首行对应导出 PNG 底行；替换时须验证 Unity raw upload 的 GPU 行序，不能盲目全局翻 UV，破坏已确认的共享 BaseMap_ST 域。实际 sampler descriptors/image-view/mip fidelity 仍需独立门禁；可复用 `capture_pipeline_export.py::save_texture` 和 `capture_bloom_evidence.py::collect_samplers` 的离线设计。

## 封存 / 交接

v1 6771 文件/18 anchors 仍 integrity PASS（79 pending）；v2 149 文件/7 anchors 仅有既有授权的 CharacterLit / OfficialHair runtime snapshot 变化（24 pending），不能说全快照 PASS。source/inventory/anchors/digest 未改，两个 seal 没有重写。

修改前 CharacterLit 与主 index 在上述外部目录；记录分支父提交 `7b1f81e5cd5b7992fce056b5735b9433b4c36bd0`。独立 index/commit-tree/CAS 发布，不 checkout/reset 用户工作树；主 HEAD `fc9d4869803f439ffff83311986190e8a8b5ade3`、9557 index entries、正式场景/Quality/Graphics 保留。

优先下一项：最终捕获 BC5 / 全 mip / sampler / 行序的数据绑定闭环。native fetch/skinning/instance basis、场景光照和屏幕空间 rims/local lights/fog、湿身/clearcoat/透明 variants、全局后处理与解包动作/MMD 仍各有未认证部分，不能据本轮局部法线通过宣布全部官方效果完成。
