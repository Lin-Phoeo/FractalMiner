# 复制给下一位接手者（Qoder/Codex）的首条提示词

请在 `A:\Hypergryph Launcher\games\Arknights Endfield\FractalMiner` 接续提弗洛斯官方渲染还原。

首先完整阅读：

1. `QODER-HANDOFF-2026-09-23.md`（第4节已标注"阶段1完成"，不要重做）
2. `RESUME-2026-09-23-captured-pipeline.md`（含 5.1 节阶段1交付与证据）
3. `docs/research/official-source-shading-20260923.md`

把这些文件里的测试结论当作需要复核的当前基线，不要从旧聊天重新推断状态。

## 当前真实状态（2026-09-23 21:00 +08:00 磁盘复验）

- 模型与四族主颜色有基线；captured cube、b354 后处理、17-dispatch 动态 Bloom 在 frame6411 捕获输入上数值通过。
- **阶段1（管线激活隔离）已完成并通过三层门禁**：沙箱 18/18、真工程 9/9、跨重启 4/4。`EndfieldCapturedPipelineScope.cs` 已删除；生成场景不再引用它。
- `QualitySettings.asset`=`E61ECBD3…2163`，Ultra→原管线 `13fa23817c5a2784ebcdc28788b04b05`，两个 ProjectSettings 里生成管线 `f351291399134454680985801f0e93e8` 残留计数为 0；`GraphicsSettings.asset`=`E2EAD59B…52E68`；`Typhoeus_OfficialFrame_Recovered.unity`=`0185EB58…E7FB`；用户 `.git/index`=`C997CED5…A6463`。
- 回归：Python 58/58；capture pipeline 0 FAIL（Bloom relativeL1=0.00027051、post meanByteError=0.120543）；主颜色 11 + 皮肤 21 = 32 项通过。
- 整体官方画面**仍未完成**：`EndfieldCharacterLit.shader:576-578` 仍是 `float selfShadow = 1.0;`。

## 现在可用的管线激活操作方式（阶段1产物，务必按此使用）

```text
菜单 Endfield/Captured Pipeline/Activate generated pipeline (project-wide)
菜单 Endfield/Captured Pipeline/Restore original pipeline (project-wide)
菜单 Endfield/Captured Pipeline/Report activation state
菜单 Endfield/Captured Pipeline/Validate activation isolation (sandbox)
批处理 EndfieldShaderPack.EndfieldCapturedSceneBuilder.Build                    纯生成，不碰 ProjectSettings
批处理 EndfieldShaderPack.EndfieldCapturedSceneBuilder.BuildAndValidate          完整门禁
批处理 EndfieldShaderPack.EndfieldCapturedSceneBuilder.ActivateForRestartCheck   激活后退出，交给新进程
批处理 EndfieldShaderPack.EndfieldCapturedSceneBuilder.VerifyAfterRestartAndRestore
```

激活状态存 `Library/EndfieldCapturedPipelineActivation.json`（gitignore）。**不要**再用场景生命周期或 `ExecuteAlways` 写 `QualitySettings.renderPipeline`；`Build()` 在已激活时会主动拒绝，避免克隆生成管线而不是工程原管线。用完必须 Restore。

## 本轮只做"阶段2：动态角色自阴影 G"

- 先新增 `Tools/capture_character_shadow_evidence.py` 与其单测，导出 atlas/depth/GBuffer/常量/矩阵，fresh 目录 + manifest + hash，限定 frame6411。先写失败测试再写导出器。
- 再做固定捕获输入的 GPU resolve 实验：先 1-tap，验证世界位置重建、角色索引、矩阵方向、atlas rect、深度符号；然后才加 16 次 Poisson/GatherRed 与非线性软化，对固定帧 G 通道逐像素比较。
- 之后才实现当前 SkinnedMeshRenderer 的动态 shadow depth/atlas，验证骨骼、alpha test、bias、剔除。
- 最终通过**一张统一的屏幕空间 shadow 纹理**在 `EndfieldCharacterLit.shader` 采 G，作为参数传给四族函数；不要在 `EndfieldOfficial{Skin,Hair,Cloth,Eye}.hlsl` 里各自复制 resolve。
- 官方参考：`_dump_1.5.3/AllShader_1.5.3/Assets/packages/com.hg.render-pipelines/runtime/shaders/lighting/shadow/screenspaceshadowresolve.shader`。官方是全屏 pixel pass，没有数值证据不要擅自改成 compute 并声称等价。
- 禁止把捕获的固定 screen-shadow EXR 贴到实时角色上冒充动态阴影；必须转动相机/角色/灯光验证。
- 不改阶段1已通过的 Bloom/Post 算法与阈值，不改主颜色四族公式。

已知证据（见 QODER-HANDOFF 第5节）：生产事件 744/748；atlas `ResourceId::32538` 4096×2048 D16；GBuffer0 `58985`、GBuffer1 `58994`、CameraDepth `59000`；screen shadow `58932` 2560×1600 R8G8，R 恒 1，G<.99 共 116890/4096000 像素；`_CharacterShadowParams=(1,1,7,0)`；7 套 light direction / world-to-shadow / atlas rect；16 个旋转 Poisson offset × 4 通道 = 64 次比较。

## 硬约束

- 每次批处理前重新检查是否已有交互式 Unity 打开本工程；不要并行启动同工程 batchmode，也不要擅自关闭用户 Editor。
- checkout 是 main、工作树很脏，记录分支 `fix/typhoeus-render-explosion-20260917`，remote `endfield-records`。禁止 `git add .`、`clean`、`reset --hard`、`checkout -- .`、切分支、强推、删除不认识的 scene/asset/meta。
- `Assets/Codex finishhalf-0923.unity` 是用户文件，不要动。
- 只把本阶段明确拥有的文件用临时 `GIT_INDEX_FILE` 提交到记录分支，提交前后校验用户 `.git/index` 哈希不变；**push 前先征得用户同意**。
- 新增 `.cs` 必须同时新增 `.meta`，GUID 为 32 位十六进制且全工程唯一（可用 `od -An -tx1 -N16 /dev/urandom | tr -d ' \n'` 生成后 grep 校验）。删除脚本会触发一次 Tundra 陈旧文件清单的 `CS2001`，Unity 会自动重跑 DAG 自愈，不要因此回退删除。
- 每次 Unity 运行用新日志名；只看 `PASS` 子串不够，必须确认进程退出码、日志末尾无 `threw exception`、报告文件存在且样本数正确。

先进行只读审计并给我一段不超过 20 行的实施计划，然后直接执行阶段2。如果发现交接事实与磁盘不符，以磁盘证据为准，并在修改前指出差异。
