# 官方角色阴影消费链：2026-10-01 增量

本轮只认证六个实际角色 PS 的屏幕阴影读取、强度与 ignore 选择，以及对应原始输入上传。不是完整官方阴影生产链、动态场景或 MMD 成品认证。继承 [光照选择](../character-light-selection-20261001/README.md) 与 [实际材质参数](../material-uniforms-20261001/README.md) 的程序身份核验；社区说明和旧交接仅作线索。

## 1. 回源结论

离线 `正面.rdc` 帧6411，实际程序来自 `Validation/draw-program-audit-20260930-01/`。实际 SPV/HLSL 与 named 候选哈希沿用材质参数增量的身份表；两套 CB 的完整 offset/type/layout 必须一致，再给选定字段命名，不做 union-name 评分。

| 实际 event / PS | 部件 / named 候选 | 实际 HLSL Load / 强度-ignore 行 |
| --- | --- | --- |
| 776 / 22259 | Eye / b28 | 668（只消费 R） |
| 786 / 22250 | body Skin / b114 | 982 / 984 |
| 835 / 22255 | Cloth01 / b471 | 894 / 896 |
| 850 / 37669 | Cloth02 / b472 | 896 / 898 |
| 860 / 37671 | face Skin / b138 | 728 / 730 |
| 875 / 22257 | Hair / b126 | 1013 / 1015 |

以下是语义命名后的等价表达，不是截图拟合公式：

```hlsl
float2 rawRG = ScreenSpaceShadowMask.Load(int3(int2(SV_POSITION.xy), 0)).rg;
float directional = lerp(lerp(1, rawRG.r, DirectionalShadowParams.x), 1, CP1.z);
float selfShadow = rawRG.g;
```

Hair 的 canonical b126:1017–1019 可交叉核查；Eye 没有 G 的后续消费，不能因共享适配器有 G 诊断就声称 Eye 也使用 G。无 UV、sampler、双线性过滤、导出翻转或额外 clamp。强度先应用，CP1.z 只应用一次。

六 draw 的实际输入一致：set0/b15 共11440字节，`_DirectionalShadowParams` 在 byte544（c34），值 `(1,2,0.0007716049440205097,3600)`；set0/b16 共3200字节，`_CharacterParams1` 在 byte1728，值 `(0,1,0,1)`。本轮消费强度只使用第一字段 x，不扩展认证 y/z/w 的生产用途。

实际 set0/t22 是 `ResourceId::58932` / view `58934`，2560×1600、单 mip、单 slice、identity swizzle 的 `R8G8_UNORM`，8192000字节。原始数据全部 R=255；G 在0…255变化（G!=255共122626个，G<250共113636个）。这只是原始输入分布核验，未进行逐像素画面对照。该帧无方向阴影变化，不能凭它证明通用 R producer 正确；非平凡 R 用独立合成输入验证消费函数。

## 2. 实现修改与边界

- `EndfieldCharacterLit.shader` 的 source directional 调用新 `EndfieldOfficialCharacterShadow.hlsl`，顺序与实际程序一致。正常 mode0 不进入210/211/212诊断。
- `EndfieldCharacterSelfShadow` 从归一化 UV Sample 改为整数 pixel Load 的 G；gate=0 不读未绑定纹理，保留旧 fractional integration gate 的 lerp 契约。
- `_EndfieldDirectionalShadowScreen` / `_EndfieldDirectionalScreenShadow` 独立于现有 G producer 的 texture/gate。没有有效官方 R 输入时明确回退 URP shadowAtten，不把 G producer 写出的 R=1冒充通用官方方向阴影。
- `EndfieldOfficialFrameGlobals` 上传捕获 float4，但不偷偷开启 R gate。固定 profile 不等于 live C++ producer。
- `capture_character_shadows.py` 复用原离线采集器的原始描述符、程序哈希和 Shutdown 生命周期；在两次 Shutdown 成功后才写 fresh complete。共享 lighting.run 增加可选 plan/schema/scope/collector，旧默认不变。
- 原材质、模型、场景、Quality/Graphics 设置、曝光、post 和 legacy 光照链未调整；不进行亮度补偿或整帧截图拟合。

## 3. 先失败、再修复的验证

完整摘要在 [verification.json](verification.json)，实际绿色报告在 [shadow-gpu-report.txt](shadow-gpu-report.txt)，失败记录在 [shadow-red-summary.txt](shadow-red-summary.txt)。

旧消费实现：220例91 FAIL（合成88、独立所有权3）；新实现初步220 PASS。新增原生测试一度误要求 R/G 都应变化，遇到恒定 R 后提前失败，未生成通过报告。核查全体原始 R 字节及已有官方证据后，纠正测试前提；精度阈值一直为2e-6，未调宽。

最终生产 CharacterLit GPU 路径238/238 PASS：

- 六 draw 的12 float4 /48分量原始 CB→profile→GPU 上传。
- 四族×3强度×3ignore×2presence×3整数位置=216合成选择；R/G 使用不同原生 R8G8 maps，并故意污染 legacy Size、使用 Bilinear/Repeat，验证消费不依赖这些输入。
- 四种独立 R/G gate 所有权组合。
- 原生 mask 的四角、中心及首个非平凡 G 点 `(1336,87)` 六点；该点 G=0.956862748，误差2.5711806e-9。读取 raw bytes 不经过图像导出/import flip；不是整帧逐像素门禁。

13项隔离 Unity GPU 回归均通过：light688、uniform225、official17、Skin28、HairSplit18、Cloth native、Hair/Eye native、Skin native、Cloth normal、environment、emission、Eye八态、Shadow MPB两槽两次更新。后两项为 fresh log PASS，其余11项有 fresh text 报告。没有调用会改场景的旧 RunAll/Build 激活入口。

Python `Tools/tests` 加 v2 raw-input tests 共415 passed、3历史 skipped、77 subtests passed、2既有 Pillow 警告。新增 shadow15测试加共享 lighting22测试共37例，两模块146可执行语句覆盖100%；不等于 C#/HLSL 或全工程覆盖率。Ruff/Pyright通过；pip-audit只核查临时工具环境，不认证 Unity 依赖。

原始捕获包保留在本机 `Validation/Captures/shadow-selection-20261001-01/`，格式整理后最终离线重放在 `shadow-selection-20261001-final/`，complete 字节一致，未把原始 mask/捕获数据发布 Git。

## 4. 复验入口

Unity 2022.3.30f1 / D3D11 / Linear，隔离 batch 调用 `EndfieldShaderPack.EndfieldShadowSelectionValidation.RunBatch`；`ENDFIELD_SHADOW_SELECTION_REPORT` 必须是不存在的新绝对文件。需要上述 hash-pinned private capture package。只临时 preview scene、内存 texture/material，finally 恢复保存的全局参数与资源，不保存资产。

Python（uv 已缓存的环境，无新增项目依赖）：

```powershell
uv run --offline --python 3.13 --no-project --with pytest --with numpy --with pillow python -B -m pytest Tools/tests docs/render-baseline/v2/tools/tests -q --tb=short
```

## 5. 下一步与禁止误读

先审实际 event744方向 resolve、748角色 G resolve 的程序/资源身份及管线，然后审逐相机/逐帧 texture/gate 生命周期。当前 `EndfieldCharacterShadowFeature` 的 DispatchResolve 会置 G gate=1，skip/早退/dispose 没有明显的对应复位；仍需检查所有其他 writer 后才可确认风险或根因。本轮未宣称复现、修复这个生命周期问题。

之后完成 render-state、天气 producer/selector、最终原生资产与场景包装，再接解包动作/MMD。现有 v1/v2 seals 仍79/24 pending，仍有已知 runtime/handover drift；不重写 manifest 抹掉缺口。使用独立 Git index 只提交本轮14个文件，保留主HEAD、9557条暂存索引和原场景设置。
