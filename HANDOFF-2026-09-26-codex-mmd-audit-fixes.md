# HANDOFF-2026-09-26 — Codex MMD 全链审计与第一轮纠错

## 结论

WorkBuddy 在 `9b418b1` 所称的“全部闭环”不成立。该版本只证明 Unity 能编译，真实功能仍存在校准必败、镜头加载销毁播放器、非 30fps 视频变速、幅度控件失效、上下翻转和项目状态泄漏等确定性错误。

本轮已按上游 `Endfield-Poser` 的实际实现重新核对并修复核心链路，同时新增真实 Unity 场景烟测。不要再使用旧的 `Validation/vmd-unforg/unforgiven.mp4` 作为证据：它是修复前产物，manifest 明确记载校准失败，且 158.5 秒动作被 60fps 错误封装成约 79.27 秒。

## 已修复

1. `MmdRetargetProfile.FromUnity` 为基线绑定骨设置 `calibrated=true`。旧实现从未写入 true，因此 `Valid()` 永远失败。
2. 校准 up 不再硬编码 `Vector3.up`；现在使用 `charRoot.InverseTransformDirection(Vector3.up)`，与上游 `Conj(rootWorldRot) * worldUp` 一致，适配 M5 根节点的 `-90°X`。
3. 增加上游同口径的 T-pose 方向门禁；校准成功时清空旧错误。
4. `LoadCamera` 不再重开场景，避免自动发现 `Camera.vmd` 后销毁刚绑定的 player/Transform。
5. 幅度在同一世界空间插值：以当前父骨下的中性姿态为基准，使用 `SlerpUnclamped` 支持 100%–200%；躯干不再把整体幅度平方。
6. FK 关节位置改为由父骨世界旋转作用于 localPos；根关节位置不再被自身旋转带偏。
7. 通用 IK 的弧度限制显式转换为 Unity 度数；Euler 限制先转有符号弧度再 clamp。
8. `MmdPlayer.Recalibrate` 先 Reset，再从干净 Unity 绑定姿态重建 profile，避免重复校准漂移。
9. Studio 与 Batch 的输出时间轴改为 `t=k/outFps`；完整输出帧数按 `duration*outFps+1` 计算。30fps 与 60fps 保持同一动作时长。
10. 每次渲染进入独立 `run-时间戳` 目录，旧 PNG 尾帧不再混入新视频；ffmpeg 加入明确帧数限制。
11. PNG 读回默认不再二次垂直翻转。旧 `flipY=true` 会在当前 D3D11 路径上把整个人物倒置。
12. `SaveFrame` 使用 `try/finally` 恢复相机 target、活动 RT 并释放资源。
13. MMD Studio 与 Batch 仅恢复自己激活的 CapturedPipeline，仅销毁自己创建的 ShadowCaster；临时 caster 设置为 `DontSaveInEditor`。
14. Anim Studio 修复锁骨角度重复度/弧度转换、Scene 视图辅助线未注册、重复添加/误删已有 caster，并在切换脏场景前要求确认。

## 新增自动门禁

- `Tools/tests/test_mmd_runtime_contract.py`：覆盖镜头不重开场景、校准标志与局部 up、幅度空间、FK、IK 单位、输出 FPS、独立目录、RT 恢复、pipeline 所有权、图像方向和 Anim Studio overlay。
- Python 全套：`126/126 PASS`。
- Unity 全量编译：`Logs/compile-check.log`，桥接 `exit=0`。
- Unity 真实烟测入口：`EndfieldShaderPack.EndfieldVmdBatchRender.RunSmokeValidation`。
- 烟测产物：`Validation/mmd-smoke-01/`。

## 真实烟测结果

`Validation/mmd-smoke-01/report.json`：

- `pass=true`
- `calibration=true`
- 动作时长 `37.666667s`
- 30fps `1131` 帧；60fps `2261` 帧
- `52` 条骨骼轨、`4146` 个关键帧、未映射轨道 `0`
- 五个时间点最大肢体旋转变化 `92.773110°`，证明不是静态假播放
- 五个时间点屏幕 bbox 宽度 `0.336–0.580`，头部均高于骨盆
- 官方自阴影 feature 未跳过
- 五张 PNG 已人工复核为正确朝向；此前倒立来自多余的输出翻转

## 仍未完成，禁止夸大

1. 尚未完成整段 1131 帧 MP4 的重新渲染与 ffprobe 时长验收；当前仅完成五时间点真实场景烟测。
2. 尚未对照原 MMD 模型逐骨比较动作风格；当前证明“链路有效、非静态、坐标与时长正确”，不等于动作艺术效果已经完美。
3. 重建脸没有 blendshape、重建骨架没有眼球骨，所以表情与眼神仍缺失。
4. Batch Render 仍是旧高级入口，虽然核心时间轴已修，但它还没有完整复用 MMD Studio 的全部幅度/IK UI 参数；正式产品化应合并为一个 session/controller，而不是继续复制初始化逻辑。
5. 官方提弗洛斯渲染 M5 的逐像素颜色门禁仍未达到 ≤4 LSB；MMD 修复不能替代渲染复刻主线。

## 下一阶段最优路线

1. 把 MMD Studio、Batch、Smoke 的场景/管线/player 生命周期抽成一个 `MmdSession`，消除三套重复初始化。
2. 为 Retarget 数学建立 Unity EditMode 数值测试（当前新增的是静态契约 + 真实场景烟测），覆盖幅度 0/1/1.5/2、左右腿 IK、重复校准幂等。
3. 用当前 UNFORGIVEN 重新渲染整段 30fps；验收 `1131` 帧、MP4 约 `37.67s`、ffprobe 音视频时长，并保存 manifest。
4. 整段通过后再做动作艺术调整；不得用整体幅度掩盖错误的骨骼映射。
5. MMD 产品线稳定后回到 M5 渲染颜色残差：按头发/布料/装甲/皮肤分材质对照 RenderDoc，不调全局曝光冒充收敛。
