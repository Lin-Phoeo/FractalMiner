# 复制给 Qoder 的首条提示词

请在 `A:\Hypergryph Launcher\games\Arknights Endfield\FractalMiner` 接续提弗洛斯官方渲染还原。

首先完整阅读：

1. `QODER-HANDOFF-2026-09-23.md`
2. `RESUME-2026-09-23-captured-pipeline.md`
3. `docs/research/official-source-shading-20260923.md`

把这些文件里的测试结论当作需要复核的当前基线，不要重新从旧聊天开始。当前真实状态：模型与四族主颜色已有基线；captured cube、b354后处理和17-dispatch动态Bloom在frame6411捕获输入上数值通过；整体官方画面未完成。`EndfieldCharacterLit.shader` 当前仍令 `selfShadow=1`。实验场景可实际执行HDR/post/Bloom，但 `EndfieldCapturedSceneBuilder.BuildAndValidate` 最后发现 `QualitySettings.asset` 被持久化改写，所以实时集成仍是WIP。

本轮只做“阶段1：管线激活隔离”：

- 不要继续用场景中的 `ExecuteAlways EndfieldCapturedPipelineScope` 自动写 `QualitySettings.renderPipeline`。
- 把 `EndfieldCapturedSceneBuilder.Build()` 改成纯生成，不修改项目pipeline设置。
- 设计Editor-only、用户显式调用、可验证恢复的Activate/Restore流程；自动字节不变测试放在独立工程副本。
- 不改已经通过的Bloom/Post算法或阈值，不开始角色自阴影，直到这一门禁完全通过。
- 先检查是否已有交互式Unity打开本工程；不要并行启动同工程batchmode，也不要擅自关闭用户Editor。
- 2026-09-23 20:37复核：Unity已完全退出，可跑batchmode。QualitySettings=E61E…、Ultra仍指向原pipeline GUID 13fa…、无生成管线f351…残留；GraphicsSettings=E2EA…、用户index=C997…均未变。不要在Editor运行中外部覆盖回历史2B7C文件；区分Unity序列化格式升级和真正pipeline污染。
- 当前checkout为main、工作树很脏，记录分支为 `fix/typhoeus-render-explosion-20260917`。禁止 `git add .`、clean、hard reset、切分支和覆盖用户文件。`Assets/Codex finishhalf-0923.unity` 是用户文件，不要动。
- 用测试驱动：先保留/写出失败门禁，再做最小修改；Build两次GUID稳定、feature不重复、Build不改ProjectSettings、显式Activate真实执行动态Bloom、Restore跨重启验证、原场景未覆盖，全部满足才结束。
- 完成后重跑58项Python、capture pipeline和 `EndfieldOfficialShadingValidation.RunAll`，使用新日志名；准确报告外部数据依赖和任何未通过项。
- 只把本阶段拥有的明确文件用临时 `GIT_INDEX_FILE` 提交到记录分支并推送 `endfield-records`，不要改变main或用户index。

先进行只读审计并给我一段不超过20行的实施计划，然后直接执行阶段1。如果发现交接事实与磁盘不符，以磁盘证据为准，在修改前指出差异。
