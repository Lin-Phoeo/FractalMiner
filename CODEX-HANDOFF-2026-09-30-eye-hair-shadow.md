# 接管增量：眼睛/头发根输入与实时阴影集成（2026-09-30）

## 目标和完成边界

沿用用户最新要求：按官方 shader、资源格式、坐标/光照语义、pass 顺序验证，不做截图逐像素优化，不调整曝光或增益来掩盖错误。URP 是适配宿主，不能标注整个官方管线已经完全复刻。

本轮改了转写/适配代码，没有改游戏原文件、捕获文件、源材质 JSON、贴图像素或网格资产。Recovered 基线场景未保存，项目管线设置已恢复。冻结 CapturedPost/Bloom/管线验证模块未修改。

前置文档：`CODEX-HANDOFF-2026-09-30-live-skin-and-motion.md`。本轮将其中 face/body 动态根适配扩展到 iris/hair，并修复这个适配与阴影参数块的集成冲突。不要把旧“几何/颜色全闭合”的总结当作全工程验收。

## 已修正

### 1. 眼睛与头发不应使用网格 ObjectToWorld 代替部件根

实际捕获证据：

- `Validation/face-input-capture-20260930-01/basis.json`：iris flags=49、root base=272595；hair flags=52、root base=272496。bit16 根行与 face 一致。
- 捕获 SPIR-V：`Validation/Captures/tifuluosi-front-20260917/replay-details-01/shader-22259.spv`（iris fragment）/ `shader-22257.spv`（hair fragment）。
- spirv-cross 输出：`Validation/eye-hair-structure-20260930-01/iris-fragment-22259.hlsl`、`hair-fragment-22257.hlsl`。iris 396–404、hair 419–427 行加载 SSBO 部件根，不是 vertex palette base+3，也不是 Unity mesh transform。

新 `EndfieldCharacterBasis.hlsl` 共用显式三行输入；Skin/Hair/Eye 使用该 helper。旧 `_EndfieldSkinBasis*` 属性名保留兼容性，现在适用于四个部件。

`EndfieldSkinBasisDriver`：body -> Spine2；face/iris/hair -> Head 的 native 轴列 `[-Z,-X,+Y]`，在最终骨态后更新，保留平移/尺度。捕获根固定覆盖仍只用于诊断。只验证了 Typhoeus 和已审分支，不推广到所有角色/变体。

### 2. 眼睛投影光方向多做了一次 normalize

实际 iris shader `_1226 -> _1231 -> _1233`：将 L 转入根空间并归一化，去掉 Y，再变回世界空间，**不对结果再次归一化**。旧实现多做最后一步，改变 ramp 的采样输入。本轮删除多余归一化，不调颜色或光强。

三组独立 CPU 四元数推导 + GPU 梯度 ramp 合成测试先失败，修正后通过。测试是公式契约，不是官方图像的逐像素拟合。

### 3. 官方虹膜没有通用倒壳描边 pass

官方 `characternpr_eye.shader` 的 pass 为 ForwardLit/PreGBuffer/RayTracingReflection/ShadowCaster/TextureStreamingFeedback，没有 Outline。当前通用导入器给 iris 留了描边默认值。

修正导入策略，对 family=3 不启用通用描边；Shader Outline fragment 额外拒绝 Eye，防止旧已导入材质仍然开启描边。不批量重导材质，不覆盖资产。

### 4. per-material 参数块遮住了 renderer 级阴影参数

Unity 只使用材质 slot 的参数块（若它和 renderer 级参数块同时存在），不是两层合并。动态根输入建立 slot 块后，旧 ShadowFeature 只写 renderer 块，slot 中缺少 shadow index/clip。

修正 `ApplyPerRendererShadowState`：保留 renderer 块原值，并将阴影参数合并到已存在的 slot 块。没有 slot 块的材质继续继承 renderer 块，不替它建立多余覆盖层。

行为依据：[Unity 2022.3 Renderer.SetPropertyBlock](https://docs.unity3d.com/2022.3/Documentation/ScriptReference/Renderer.SetPropertyBlock.html)。测试验证两个材质 slot、两次不同光方向更新，根行和已有用户值仍保留。

### 5. 验证工具也必须走同样的输入时序

正式 VMD Batch 出片入口已有最终骨态之后的根更新；旧 `RunSmokeValidation` 漏了这一步，本轮补上。不改 VMD parser、retarget 数学、MMD 相机算法。

输入诊断扩展到四部件，按真实 slot 编号遍历（避免同一材质多 slot 时 Array.IndexOf 误报），眼睛允许视差的 sourceShading 条件与 Shader 一致。

## 实际运行结果

| 检查 | 结果/证据 |
| --- | --- |
| 根输入三姿态×四部件、轴/平移/保留值/缺骨拒绝 | PASS，`Logs/eye-hair-basis-green-20260930-01.log` |
| 八种 family/outline 导入状态 | PASS，`Logs/eye-pass-green-20260930-01.log` |
| 衣服/头发/眼睛公式合成检查 | 14 例 PASS，`Logs/eye-projection-green-20260930-01.log` |
| 皮肤公式回归 | 25 例 PASS，`Logs/skin-formula-regression-20260930-02.log` |
| 两材质 slot×两次阴影更新 | PASS，`Logs/shadow-property-green-20260930-01.log` |
| 解包动作 + VMD 实际渲染 | 各三个时刻，共六张图；根输入、实时阴影、动态 Bloom、CapturedPost 每次均接通；`Validation/live-basis-animation-inputs-20260930-03.json`（02为前次成功运行） |
| 当前诊断输入 | 四部件 sourceShading=True、basisEnabled=1、shadow index/clip 存在，shadow gate=1；`Validation/eye-hair-inputs-20260930-01/runtime-inputs.txt` |
| Python 回归 | 无外部 fixture 时 188 PASS / 3 skip；指定本轮 HDR fixture 后 **191 PASS、无 skip**；两条已有 Pillow deprecation 警告 |
| 依赖审计 | 本轮隔离 pytest/numpy/Pillow/pip-audit 环境：No known vulnerabilities found |

注意：没有测量全工程 C#/Shader 测试覆盖率，不声称满足 80% 全量覆盖；公式测试与输入烟测不证明所有官方材质逻辑、MMD 全片保真、防滑、表情或物理已经完成。VMD 此次使用 Standard MMD 源骨架，不冒充真实 PMX oracle 一致性证明。

一次皮肤回归启动命令误写不存在的 `EndfieldSkinFormulaValidation.Run`，产生 `skin-formula-regression-20260930-01.log` 的 method-not-found；随后使用正确 `EndfieldSkinShadingValidation.RunNumerical` 完成回归，见 `...02.log`。不是 shader 编译回归。

## 可看产物和复现

近景诊断：`Validation/eye-hair-live-20260930-01/pose-applied-lit-post.png`。仍有眼周异常/附属物等，不标注官方完整效果。

舞台动态样本在 `Validation/live-basis-animation-inputs-20260930-03-frames/`：`native-0.png`、`native-1.png`、`native-2.png` 和 `vmd-3.png`、`vmd-4.png`、`vmd-5.png`。640×400 是链路烟测尺寸，不是最终视频品质；没有用这些图做颜色拟合。新方法要求报告与 frame 目录均为新路径，避免重复运行覆盖先前图像。

正式用户入口保持原有 Anim Studio / MMD Studio / VMD Batch Render，舞台为 `Assets/Scenes/Typhoeus_MMD_Stage.unity`。

复现六次实际渲染：Unity batch executeMethod `EndfieldShaderPack.EditorTools.EndfieldSkinBasisValidation.RunRenderedAnimationInputs`。设 `ENDFIELD_BASIS_TEST_VMD` 为已有 Motion.vmd，`ENDFIELD_BASIS_TEST_REPORT` 为**不存在的新 JSON 路径**（父目录已存在）。可设 `ENDFIELD_BASIS_TEST_RIG` 指向真实 PMX rig JSON；未设则 Standard MMD。此方法只供 batch，临时切换管线、重开干净场景，finally 恢复。

纯输入检查仍可用 `RunAnimationInputs`，不渲染也不切换管线。诊断复现同前置文档，必须新目录，`ENDFIELD_LIVE_SKIN_BASIS=1`，不同时启用固定 captured basis。

Python（PowerShell）设置 `ENDFIELD_SKIN_DIAGNOSTICS=Validation/eye-hair-inputs-20260930-01` 后执行原 `pytest Tools/tests` 即运行三条 HDR fixture 测试；它们检查浮点编码/通道/有限值，不比较官方图像误差。

## 下一项：覆盖层不是普通衣服——已发现，尚未改

明确的结构证据：

- `M_eyewhiteshadow_common_01.json` / `M_hairshadow_common_04.json` 的源 shader pathID 都为 1962491951764993823，具有 `_UseGrayAsAlpha`、`_ShadowOverIris`、`_EnablePreDepthPass`、`_DisableDrawUnderHair` 等参数。
- 官方 `characternpr_overlayshadow.shader` 同名属性契约：queue Transparent-100；OverlayShadowPreDepth 为 Blend Zero One，stencil readMask20/Equal；OverlayShadow 为 **Blend Zero SrcColor、ZWrite Off、模板测试**。
- 现有两个 .mat 指向通用 CharacterLit，queue2000/RenderType Opaque，导入器将不认识的材质按 cloth family0 渲染，也没有消费以上覆盖层参数。

这足以证明当前实现有未支持的覆盖层契约，**但还不能仅靠 shader pathID 数字宣称每个捕获 draw 已完成映射**。下一步应先核对捕获 draw 的实际 shader/绑定/模板状态，定位官方 PreGBuffer 中 face、hair、iris 的模板写入，以及 overlay 两个 pass 的执行顺序，再做专用 overlay shader/renderer feature 与导入路由。不要直接隐藏覆盖层、改成常规 Alpha Blend，或重建全部材质。

眼周噪点的最终因果仍待隔离验证，不声称覆盖层是唯一原因。VFX/透明衣料也不能按衣服默认公式视为已完成。

继续顺序：覆盖层/模板链 -> 特效与透明材质来源 -> 四族剩余输入和变体 -> 解包 root-motion 与 MMD target rest/root-space 审查 -> 表情、防滑、fixed-step 次级物理。保持官方 CP11 光方向与实际阴影投影语义一致，不凭控件名字推断。

## 保护和 Git 边界

本轮备份：`D:/EndfieldTechLib/notes/eye-hair-20260930-01/`。原主 index/项目设置/场景保护见 `D:/EndfieldTechLib/notes/codex-takeover-20260930-01/`。

本轮完成后 QualitySettings/GraphicsSettings hash 与初始备份相等，Recovered 场景 SHA256 仍为 `4D4D43D5E2990FF0D8B4888FF4775073DB58E3BA15EE96BCC7D07817D2881A7A`；activation state 文件不存在。原主 index 的 9557 条 staged 不改动。已有他人描边差异不混入本轮提交。

记录分支：`fix/typhoeus-render-explosion-20260917`，remote `endfield-records`（Lin-Phoeo/FractalMiner）。父提交 `59cb03f`；本轮只提交源代码/小文档/测试，不提交 RDC、模型贴图、截图和 HDR dump。该记录分支不是包含全部游戏资源的可运行资产快照。
