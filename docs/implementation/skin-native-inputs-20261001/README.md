# Skin 身体／脸部原生输入与官方采样修正（2026-10-01）

本增量按实际离线捕获的 shader、binding、image/view、sampler 和生产消费验证。不做官方截图拟合，不增加亮度/颜色补偿。范围是帧 6411 的身体与脸部 **dry opaque** 输入，不是全部材质参数、天气、最终场景或 MMD 已完成。

## 1. 证据与接手位置

- 官方离线输入：本机 `C:/Users/Administrator/Downloads/正面.rdc`，frame 6411；没有启动/注入游戏。
- 实际程序：body event786 VS22249 / PS22250；face event860 VS37670 / PS37671。程序文件在 `Validation/draw-program-audit-20260930-01/`；不要把 signature 相同的其它 dump 变体认证成同一个程序。
- 新导出：`Tools/capture_skin_materials.py`，复用 `capture_cloth_materials.py` 的只读原生导出器。显式 Skin plan，不改原 Cloth 默认计划。
- 已核查私有包：`Validation/Captures/native-skin-inputs-20261001-01`，`complete.json` SHA256 = `e5dda0870d25bbe7411e95597ff2835c9086ae82b8612313c668d6ac4eb1840b`。
- 原始导出／失败与成功回归日志：`D:/EndfieldTechLib/notes/skin-inputs-20261001-01/`。complete 只在 replay/capture 成功 Shutdown 后生成，不以 qrenderdoc 退出码代替成功。
- 原始纹理/RDC 不进 Git；代码、固定身份、复核报告与本文件进记录分支。缺少私有包时明确报错，不能静默回退 PNG 或新生成 mip。

## 2. 实际绑定（space1，非按旧导出名称猜测）

| Draw | binding | 输入／Unity property | 原生 view | 宽×高 | mip |
| --- | --- | --- | --- | --- | --- |
| 786 | 1 | ShadowLUT / `_ShadowLutTex` | BC7_SRGB | 1024×32 | 11 |
| 786 | 2 | DiffRamp / `_DiffRampMap` | RGBA8_UNORM | 256×1 | 1 |
| 786 | 3 | Normal / `_BumpMap` | BC5_UNORM | 512×512 | 10 |
| 786 | 4 | Base / `_BaseMap` | BC7_SRGB | 512×512 | 10 |
| 860 | 1 | 同一 ShadowLUT | BC7_SRGB | 1024×32 | 11 |
| 860 | 2 | SDFMask / `_SDFMask` | BC7_UNORM | 512×512 | 10 |
| 860 | 3 | SDF / `_SDFLightmap` | RGBA8_UNORM | 1024×1024 | 1 |
| 860 | 4 | Highlight / `_HighlightMap` | BC7_UNORM | 512×512 | 10 |
| 860 | 5 | Emotion / `_EmotionMap` | BC7_SRGB | 1024×1024 | 11 |
| 860 | 6 | 同一 DiffRamp | RGBA8_UNORM | 256×1 | 1 |
| 860 | 7 | Normal / `_BumpMap` | BC5_UNORM | 1024×1024 | 11 |
| 860 | 8 | Base / `_BaseMap` | BC7_SRGB | 1024×1024 | 11 |

12 个 draw binding、10 张唯一纹理、86 个原始 mip。包括 1024×32 LUT 的非正方形小 mip，不改尺寸/字节/压缩格式、不转 PNG、不做 UV 翻转。SRGB view 的 RGB 由 GPU 解码一次，alpha 保持线性；RenderDoc 参照明确使用 `CompType.UNormSRGB`，其它 view 用 `UNorm`，不能把 UNorm 取样结果冒充 SRGB view。

## 3. 本轮发现并修正的实际错误

1. **Bias**：旧 Skin 注释/实现按 global bias=0；实际 Base/N/Emotion/Highlight 使用 s4 SampleBias，global bias=-1。SDFMask 用 s6 SampleBias 同一 bias。sampler 自身 mipBias=0，不能把 global bias 同时加到 texture.mipMapBias 再加一次。
2. **Sampler**：实际 s4/space0/b4 = resource155，Bilinear Wrap / mip Point；s6/b6 = resource197，Bilinear ClampEdge / mip Point。LUT、DiffRamp、SDF 都是 s6 **显式 LOD0**。不是 Repeat，也不是 Trilinear。
3. **UV**：body VS22249:474 与 face VS37670:453 只应用一次 BaseMap ST。PS 的 Base/N/SDFMask、Emotion 图集、Highlight 偏移与 SDF 左右选择以该共享 UV 为输入。旧实现有辅助图使用 raw mesh UV / 独立 Bump ST 的错误。
4. **Normal**：PS22250:424 起与 PS37671:439 起包含 `(R*A,G)`、平方根后下限、scale-before-TBN、raw 插值 T/N 的叉乘、world normalize 与背面 enum。复用已按同表达式认证的 `EFClothDecodeNormals`，不是旧 generic half normal/TBN 路径。仅认证当前 D3D11，未声称所有平台精度等价。
5. **旧 CPU 参照**：`EndfieldSkinShadingValidation.GradientAlpha` 曾按 Repeat/bilinear。修完官方采样后旧参照 4/25 FAIL，原因直接可见：rampX=1.184/1.017 被旧参照绕回，rampX=0 被旧参照混合两端。改为独立 Clamp 索引，不改 `.003` 原阈值，25/25 恢复 PASS。又增加独立 LUT 索引的 3 例，最终 28/28 PASS。

Skin 主体光照代数、曝光、后处理、材质参数资产未在这轮调整。共享 UV 在 Unity fragment 端计算；当前捕获只认证无 parallax 分支，不据此声称所有 VS/fragment 变体已闭合。

## 4. 接入与生命周期

- `EndfieldCapturedSkinMaterials.cs`：10 张输入固定 hash/format/mip/尺寸/sampler 身份，严格原生 upload 和复验。
- `Editor/EndfieldCapturedSkinMaterialInputs.cs`：固定 manifest 的私有 loader，返回纹理及离线 native sample 证据。
- `Editor/EndfieldPoseApplyValidation.cs`：环境变量 `ENDFIELD_SKIN_NATIVE_MATERIALS=1` 打开短期 `using` scope；默认不启用。可与已经认证的 Cloth 输入和环境 cube scope 并存，不重叠材质槽。
- 先核查全部纹理及 body/face 两类目标，再写 slot MPB。常规退出恢复原 slot（空 slot 回到根 block 继承）。外部替换了本 scope 的纹理时保留该字段与后来字段，解除其它仍归 scope 所有的纹理后再释放。
- 这是**独占短期渲染作用域**，不是长时间播放期间任意 MPB writer 的合并器。仅非纹理字段的后来写入可能被常规恢复覆盖；不得拿它直接做异步动画长期 override。
- 没改材质文件，没有保存场景。读取实际 recovered 场景、绑定 body/face 两个 slot、退出，dirty state 不变。
- 完整 pose 入口仍会触发旧管线/设置操作，所以本轮**没有运行 FullRunPoseApply**。最终场景/Player 资产包装、renderer feature 生命周期与动画并发仍待专门实现验证。

## 5. 验证方法与结果

1. 原生 GPU：10 张图 86 mip 的 bytes/mip 分区不变；430 项 SampleLevel 与独立 RenderDoc typed-view 点值 maxError=0，整数 Load 保持 `<2e-6` 门禁。
2. 严格失败：20 项 null/损坏输入拒绝；缺少目标、错误面部 SDF variant、改 LUT Wrap 均拒绝且没有部分绑定。
3. 生产消费：实际 CharacterLit 的 body/face 各两例对已解码常量 fixture（共享 native LUT/ramp 保留），同时验证 Base ST 一次和 legacy aux ST 不介入，4 例 PASS。它是消费等价测试，不单独证明全部光照公式。
4. 独立 mip 对照：32×32、6 mip 的已知纯色纹理映射到 4×4 target；bias=-1 应选 mip2，bias=0 应选 mip3，两者确实不同。不是只检查代码字符串。
5. 独立 Skin 公式：28 例 GPU/CPU reduction PASS，新增 LUT 仿射 32³ 格点 fixture 用颜色域函数直接推期望，不照抄 shader 的 flattened address；覆盖低值 OETF、不同轴/蓝 slice 插值和高值 clamp。此测试仍是受限 dry reduction，不是全部参数组合证明。
6. 六项既有 GPU 回归 PASS：原生 Cloth 材质、原生 BC5、环境 cube、Cloth normal、Cloth emission、Hair split。生产默认五个 pass 编译/SetPass PASS。
7. Python 全套 332 passed / 3 历史 skipped / 77 subtests，2 个既有 Pillow deprecation 警告。导出 API/IO 线覆盖率 97.08%（Skin wrapper 100%，共享 core 96.75%），**不是 C#/HLSL/全工程覆盖率**。Ruff/Pyright PASS。

复跑（独立 batch、D3D11；报告路径必须是新文件）：

```powershell
$env:ENDFIELD_SKIN_MATERIAL_REPORT='D:/EndfieldTechLib/notes/your-new-run/native-skin.txt'
$env:ENDFIELD_SKIN_NUMERICAL_REPORT='D:/EndfieldTechLib/notes/your-new-run/skin-formula.txt'
# 先创建 your-new-run；依次运行，不能对同一项目并行打开多个 Unity。
# 用 Start-Process -WindowStyle Hidden -Wait，Unity 参数：
# -batchmode -force-d3d11 -projectPath "A:/Hypergryph Launcher/games/Arknights Endfield/FractalMiner"
# -executeMethod EndfieldShaderPack.EndfieldNativeSkinMaterialValidation.RunBatch -quit -logFile "新路径.log"
# 公式单独运行 EndfieldShaderPack.EndfieldSkinShadingValidation.RunNumerical
```

完整数值与 hash 见 `verification.json`、`gpu-input-report.txt`、`skin-numerical-report.txt`。v1/v2 seal 没重写；v1仍6771 files/18 anchors/79 pending，只含既有 handover 文档 drift；v2仍149/7/24 pending，既有 CharacterLit/OfficialHair 两项 runtime drift（本轮 Skin helper 不在该 v2 manifest 内）。全量 seal 不是 PASS，也不能把本输入增量标成全量规格完成。

## 6. 后续正确顺序与已定位线索（未实现）

1. **Hair 输入**：实际 PS22257 资源与旧语义表错位：b1 HN、b2 SpecRamp、b3 P、b4 Line、b5 DiffRamp、b6 Base。旧表 b1=SpecRamp/b2=P/b3=Line/b4=DiffRamp/b5=Bump 错误，不能复用其标签。Line 是 s4 implicit Sample + 自己 LineST，不得一律改为 SampleBias；ramp 的实际 sampler 要新 replay 审查，当前 helper Mirror 值不能当事实。
2. **Eye 输入**：PS22259 的 b1 Matcap / b2 DiffRamp / b3 Base；当前 zero-bias 注释及采样仍待按实际程序/sampler新 replay修正。这轮没有改 Hair/Eye 代码，不称它们已完成。
3. 独立审查所有 material uniforms、空间/特殊/天气分支、render states、官方 shadow/light/post producer 和最终场景生命周期。不要因为原生输入通过就跳过这些。
4. 保留最高细节模型，无模型 LOD/性能适配；待渲染链实际绑定完成，再接解包动作/MMD 全流程与出片。原始 mip 保留是官方纹理采样行为，不是模型 LOD 降级。
