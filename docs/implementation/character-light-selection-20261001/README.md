# 官方角色光源选择增量（2026-10-01）

本轮只认证六个实际 PS 的 **dry / opaque / flat-environment 光源选择和颜色传递**。不比较截图，不调材质、曝光、后处理；不是全渲染、阴影生产器、天气或 MMD 完成证书。

## 修正了什么

此前捕获 CP1.w=CP12.y=1，让错误藏在全覆盖端点：

1. source caller 从已被 `GetCharacterLight` 覆盖/归一化的 L 再 lerp 一遍。部分方向权重时，既混合两次又改变向量长度；CP1.w=0 则用了 legacy/URP 光，而非捕获 b14。
2. source caller 直接取 CP4/CP5，跳过 `lerp(CustomData1.rgb, override.rgb, CP12.y)`。
3. 四族 helper 用已乘光强 RGB 除回原色；光强为零时丢掉原色，连本应保留的 ambient tint 一起变黑。

现在 `EFResolveOfficialCharacterLight` 直接从捕获全局输入求三个独立结果，各族同时接收 unscaled RGB 和 intensity-scaled RGB。Skin body/face 均用 CP4，不以是否启用 SDF 判断；Cloth/Hair/Eye 用 CP5。后续各族原有局部归一化（例如 Eye 投影光的 ramp consumer）保留，不把“选择阶段不 normalize”扩大成“所有阶段禁止 normalize”。

`GetCharacterLight` 及 `EndfieldCharacterLight` 的历史 A/B 光照路径未改，source 不再消费其方向/颜色；目前仍借用它的 URP directional shadow attenuation，此项没有被认证为原生 HGRP 阴影。

## 实际源码依据

实际程序来自 `Validation/draw-program-audit-20260930-01`，provenance SHA256：`a6f177b4cfc56a24abd4f4560efe083bee50291181fda27be331e76f43c1a2ec`。对应 named candidate/hash 沿用上一增量的 `material-uniforms-20261001/verification.json`，但本轮另行检查 b14/b16 完整 offset/type/size/count/major layout，不使用旧 union-name、buffer-size 评分或旧文档推断。

| 绘制 / 实际 PS | 实际 HLSL 的三项选择表达式行 | 明确候选 | 颜色覆盖 |
| --- | --- | --- | --- |
| 776 / 22259 | 657 / 659 / 660 | Eye b28:661 / 663 / 664 | CP5 |
| 786 / 22250 | 976 / 978 / 979 | Skin b114:980 / 982 / 983 | CP4 |
| 835 / 22255 | 888 / 890 / 891 | Cloth b471:892 / 894 / 895 | CP5 |
| 850 / 37669 | 890 / 892 / 893 | Cloth b472:894 / 896 / 897 | CP5 |
| 860 / 37671 | 723 / 724 / 725 | Skin b138:727 / 728 / 729 | CP4 |
| 875 / 22257 | 1007 / 1009 / 1010 | Hair b126:1011 / 1013 / 1014 | CP5 |

选择合同（float，lerp 不夹权重，方向不在这里归一化）：

```text
L = lerp(-DirectionalLightDirection.xyz, CP11.xyz, CP1.w)
RGB = lerp(DirectionalLightCustomData1.rgb, skin ? CP4.rgb : CP5.rgb, CP12.y)
RGBI = RGB * lerp(DirectionalLightCustomData1.w, 1, CP12.w)
```

b14 c0 是世界空间 **光行进方向**，需要一次负号成为指向光源方向；不是 object-local 方向。b14 c3.rgb 已是线性原色，不做 sRGB 转换，不从已乘强度的 legacy Color 反推。捕获 b14 c3.w 单独由 `_EndfieldCapturedLightIntensity` 传入。

## 重提取与上传验证

仅用 official qrenderdoc 离线重放已有 `C:/Users/Administrator/Downloads/正面.rdc`，未运行/注入游戏。

`Tools/capture_character_lighting.py` 复用现有 source pinning、packoffset parser 和 replay 打开/新输出契约。读取六实际 PS 的 set0/b14、b16 **descriptor 原始范围**，不使用反射重建游标。完整 block layout 一致只允许明确字段标注，不证明整个程序等价。未使用的另一族 CP4/CP5 在相应候选中被 stripped，故每 draw 只批准其实际用到的一项，不能给 stripped 字段自动补名字。

私有包：`Validation/Captures/character-light-selection-20261001-01`，complete SHA256 `c3d7df8934814579f009f6d67844eee8541a584d17b123346678212b8b591d74`。controller 与 capture 均成功 Shutdown 后才写 complete；单独 GUI exit=0 不算提取成功。六 draw 的全 block 字节一致：

| 字段 | block / byte offset | 捕获值 |
| --- | --- | --- |
| DirectionalLightDirection | b14 / 0 | (0.021389273926615715, -0.6427876353263855, -0.765745997428894, 0) |
| DirectionalLightCustomData1 | b14 / 48 | (1, 1, 1, 1.6243867874145508) |
| CP1 | b16 / 1728 | (0, 1, 0, 1) |
| CP4，Skin 实际消费 | b16 / 1776 | (1, 0.9136825799942017, 0.9113207459449768, 1) |
| CP5，其他三族实际消费 | b16 / 1792 | (1, 1, 1, 1) |
| CP11 | b16 / 1888 | (0.1763191968202591, 0.5299192667007446, 0.8295161724090576, -0.09999999403953552) |
| CP12 | b16 / 1904 | (1, 1, 1, 0) |

`EndfieldOfficialFrameGlobals.ApplyGlobals` 新增两项私有全局：原始 travel direction 和未乘强度的线性 RGB；原有 CP/profile、光强、曝光和环境参数不改。它仍是固定捕获 profile，不是重建官方 C++ 灯光管理器；不能把其他场景的 live producer 也判为完成。

## 先失败、后修复

新 GPU validator 用实际 `Endfield/CharacterLit` 的 source caller 显式 diagnostic 200..208；正常 mode=0 不走诊断。初始化现有 URP 的临时 preview scene，ARGBFloat/Linear 读回，不保存任何场景、材质或设置，结束恢复所有自己写入的全局变量。

先只加 200..202 诊断和独立 CPU straight-line 期望值，保留旧公式：652 例中 **412 FAIL**，其中 408 光源选择错误 + 四族 zero-intensity discontinuity。随后改运行时，原阈值不放宽：

- 六实际 PS、36 float4、144 分量原始字节 → 现有 profile → 生产 GPU 上传检查，2e-6。
- 四族 × 三方向权重 × 三颜色权重 × 三 show-mode 权重 × 两光强 × 三结果 = 648 例；覆盖 0/部分/1、非单位方向、不启用 SDF 的 Skin body、零强度，2e-6。
- 四族完整 mode0 着色的零光强/1e-4 光强连续性检查：原门限 2e-4，修后最大 delta 3.922e-5，环境色非零。
- 合计 **688/688 PASS**。报告见 `light-gpu-report.txt`。测试涵盖上述离散样例，不宣称穷尽所有 float 输入或整个 GPU shader 覆盖率。

11 项既有 GPU 回归通过：UPM、Official numerical 17、Skin numerical 28、Hair split、三族 native material（Cloth/Skin/HairEye）、Cloth normal、native environment、Cloth emission、Eye 八态 policy。Python 400 passed / 3 历史 skipped / 77 subtests，两个既有 Pillow warning；新导出模块 22 测试、88 可执行行 100% 覆盖，仅限该 Python 模块。Ruff/Pyright 通过，临时 pip-audit 工具环境无已知漏洞，不当作整个 Unity 项目依赖审计。

## 复跑与接续

导出：qrenderdoc `--python Tools/capture_character_lighting.py`，设置 ENDFIELD_TOOLS_PATH、ENDFIELD_CAPTURE_PATH、ENDFIELD_CAPTURE_OUTPUT 为新空目录。来源变动必须重新审查，不自动换固定 manifest。

GPU：Unity 2022.3.30f1 `-batchmode -force-d3d11 -executeMethod EndfieldShaderPack.EndfieldCharacterLightingValidation.RunBatch -quit`；ENDFIELD_CHARACTER_LIGHTING_REPORT 必须是新路径。所有 GPU/CPU 比较均是公式/原生数据合同，不是官方截图逐像素门禁。

下一步先核对 ShadowData 的 directional-strength / screen-shadow resolve 与主 caller 的选择合同，再核对 render state、天气 producer 和最终 scene/global/native-input 生命周期。保持已修正的纹理 typed view、全部 mip、UV/sampler 和材料上传。最终 native 包装、解包动作/MMD/出片仍需后续集成验证。

v1/v2 原封存来源不重写，pending 仍为 79/24；verify 仍分别显示已知 handover drift 与 CharacterLit/OfficialHair runtime drift，不能把 integrity=false 或 incomplete 写成全绿。主 HEAD、9557 项主 index、原场景和 Graphics/QualitySettings 保留；以独立 index 沿 endfield-records 记录本增量，不吞掉用户暂存修改。
