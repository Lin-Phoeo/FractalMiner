# 提弗洛斯 MMD 舞台与视频链路交接（2026-09-26）

## 本轮可直接使用的产物

- 舞蹈场景：`Assets/Scenes/Typhoeus_MMD_Stage.unity`。独立于官方帧几何校验场景，从本地莱万汀复刻工程已导入的 Floor、Ring、Skybox 材料构建；角色仍用项目自己的捕获衍生材质与后处理。
- 重建入口：Unity 菜单 `Endfield/MMD/Build Typhoeus Dance Stage`，实现位于 `Assets/EndfieldShaderPack/Editor/EndfieldMmdStageBuilder.cs`。重建时会打开恢复基线场景，交互模式下先询问是否保存当前场景。
- 动作入口：`Endfield/MMD Studio` → 初始化人物 → 载入 Motion.vmd / Camera.vmd → 预览/试拍/整段导出。`Endfield/VMD Batch Render` 也从舞蹈场景的干净绑定姿态重新打开，防止旧姿态污染校准。
- 3 秒真实 MP4：`Validation/mmd-stage-preview/run-20260926-150953-274/unforgiven.mp4`，9–12 秒段、90 帧、1280×720、30fps，包含 AAC 音轨。对应 `Validation/mmd-stage-preview/report.json`。菜单 `Endfield/MMD/Validate 3 Second Video` 可重跑。
- 五时点诊断：`Validation/mmd-smoke-01/report.json` 与 `frame_00.png`–`frame_04.png`；检查 T-pose 校准、四肢运动、角色投影、骨骼实际绑定网格、脚骨骼最低点、自阴影、后处理与动态 Bloom。

## 本轮修复与证据

1. 原舞台仅灰色背景；新场景出现环形舞台、纹理地面和渐变天空，并挂载捕获 LUT + 动态 Bloom 的后处理 Profile。
2. VMD 相机原沿世界 +Z 拍到角色侧面；这套提弗洛斯 M5 枢轴下，默认机位偏航改为 -90°，固定预览相机也从 +X 拍正面。用户仍可在面板调偏航。
3. 动作在 9.42 秒把脚骨骼送入地台下约 0.35 米。`MmdPlayer.KeepFeetAboveBindFloor()` 在动作采样后抬根节点，仅在最低脚骨骼低于绑定脚底门限时生效；有开关，可用于有意下潜的动作。鞋底比脚骨约低 5 厘米，Studio 与 Batch 提供 0–0.15 米可调鞋底补偿，默认 0.05 米。五时点采样后双脚均不低于该门限。
4. 编码链已实测：Unity 导出 90 张连续 PNG；ffmpeg 导出 H.264 视频和 AAC 音频，ffprobe 显示 3.000 秒/90 帧。
5. 原有五帧测试只检测骨骼角度，可能出现“骨转了但网格没跟”的假阳性。现在另外检查四肢探针 Transform 属于至少一个 SkinnedMeshRenderer 的 `bones`，并记录手部屏幕坐标。
6. 验证：项目 Python 单测 126/126 通过；Unity 2022.3.30f1 编译退出码 0；五时点烟测退出码 0；三秒视频重跑退出码 0。未做全片 37.7 秒品质验收。

## 明确未完成，不能宣称官方一致

- 2026-09-26 本地 `pose-official-compare-21-postdomain-shadow` 对帧 6411 真值：头部 mean RGB 最大 29.34 LSB、躯干 20.48、腿 24.01；目标均为 ≤4。轮廓 IoU 0.765，也未过 0.85 门禁。舞台资产并不能缩小这些角色渲染残差。
- 9–12 秒三秒视频能看到骨骼/双手位移，但动作读感仍偏弱，穿戴和头发缺乏次级动力学。不能把“可载入 VMD / 可生成 MP4”说成“舞蹈完美”。
- 脚骨骼防穿地不等于鞋网格完美接地；补偿后最后一帧全角色最低顶点 -0.158m，附近脚骨骼网格采样最低 +0.076m，提示低顶点可能来自武器/布料。必须分网格/骨权重排查，不能仅以脚骨骼 PASS 判定没有穿插。
- Bilibili 两个指定页面当前工具无法读取其视频帧，未做逐帧风格对比。需要用户提供视频本地文件/关键帧后才能定义目标镜头、场景和色彩门禁。

## 下一步正确顺序

1. 给 MMD 动作做可见网格的区域运动诊断：源 VMD 关节轨 → retarget 四肢世界坐标 → SMR 局部顶点投影，找出“骨转很多但视频观感少”的具体原因；对照源动作而非盲调幅度。
2. 独立解决鞋底/裙摆/武器与地面接触、角色地面阴影和舞台照明，保留可开关防穿地，不修改官方帧几何基线。
3. 回到 M5 真值颜色主线：按脸、头发、装甲、布料分开核对 RenderDoc 抽取的纹理、常量和 draw call；在 6411 帧同姿态对齐，不用全局曝光硬凑所有材质。每次重跑固定的区域误差门禁。
4. 角色渲染与动作都过门禁后，再做完整 37.7 秒导出及多视角/多动作验证；短片编码通过不代表长片各段质量通过。

开源舞台来源：`_EndfieldRefs/Endfield_Character_Rendering/Assets/Scenes/SampleScene.unity`。上游项目为社区复刻，不是官方渲染器；其仓库许可证与任何游戏原始资产的权利须分别核实。
