# 终末地提弗洛斯 MMD 路线交接 — 2026-09-27

## 先读结论

这轮**完成了 Claude 中断的调研与三处关键错误修复**，还把两个未复核的根位移/重复帧问题纳入回归。当前项目可以载入代理 PMX 骨架与 VMD，Unity 2022.3.30f1 的五点烟测通过；但**尚未达到“原版完美跳舞/完全官方渲染”**。严禁把代理骨架间的亚毫米一致误写成终末地角色最终骨架、接触、表情或像素画面的验收结果。

这份文档优先于 `HANDOFF-2026-09-26-mmd-oracle-calibration.md` 和 `docs/research/mmd-integration-research-20260926.md` 中的旧状态语句。无需重做插值诊断，也不要恢复错误的 UMT P1 补丁。

## 已落地及复核

1. `VmdMotion.cs` 依通道所在的 16 字节行读取骨骼贝塞尔；4146 个骨骼键 × 4 通道共 16584 个样本，与**恢复上游读取方式的 UMT**逐值一致。旧读取方式有 8292 个样本不一致。相机曲线按 x1,x2,y1,y2 读取；相机旋转由弧度转角度。重复键改为输入顺序最后一键生效，并且最后帧计入 IK 轨。
2. `MmdRig.cs` 修复未直接写轨的骨仍要通过 `SampleBone` 取 VMD 位姿的腿部 IK 问题；保留 CCD 限制与控制器顺序的校正。无控制器轨的内置标准骨架默认关闭 IK；实际 PMX 则按运动轨与配置处理。共享链重置逻辑有代码，但本轮两套代理 rig 没有共享链，**尚无共享链实测**。
3. `MmdPlayer.cs` 把 profile 局部根位移按捕获的角色根旋转变到世界系，in-place 仅约束世界水平 X/Z，不抹掉下蹲的世界 Y。`Reset` 同时恢复根旋转。`MmdRetarget.cs` 的高度注入改为明确的世界竖直方向。
4. 新的 `MmdFormatRegressionValidation.Run` 在 Unity 2022.3.30f1 批处理中通过：`Logs/mmd-format-regression.log` 的 `[MmdFormatRegression] PASS format, duplicates, root space, IK/camera defaults`。使用 45.5° Y 与 -90° X 的真实角色枢轴组合测试根位移。先写失败用例，修复后变绿。
5. `EndfieldVmdBatchRender.RunSmokeValidation` 使用本地 Typhoeus 354 代理 rig 通过：`Validation/mmd-smoke-claude-audit-354/report.json` 中 `pass=true`、`calibration=true`、`postFrames=5`、时长 37.667 秒；`Logs/mmd-smoke-claude-audit-354.log` 有 PASS。烟测只有五个采样时点，不是整段逐帧渲染或观感验收。

## 三方求值校验的精确范围

输入为 `D:\MmdOracle\OracleProject\Assets\Motion\Motion.vmd` 和两套本地第三方 PMX 派生代理 rig。参考 A：还原正确插值读取的 `UnityMMDTools`（UMT）baked-FK。参考 B：`mmd-anim` v0.5.2 的 **model-aware registered pair**（不能拿它的裸 VMD parser 直接对等比较）。两套各导出 1131 帧；当前 C# 实现也导出 1131 帧。比较都经同一空间/比例变换，绝不把改成相同错误的两个读取器互证。

| 比较 | 匹配骨数 | 位置 P95 | 位置最大 | 旋转 P95 |
| --- | ---: | ---: | ---: | ---: |
| 当前 C# vs UMT，354 | 63 | 0.145 mm | 2.08 mm | 0.109° |
| 当前 C# vs UMT，1182 | 75 | 0.114 mm | 2.14 mm | 0.104° |
| mmd-anim vs UMT，354 | 63 | 0.158 mm | 6.26 mm | 0.102° |
| mmd-anim vs UMT，1182 | 75 | 0.132 mm | 5.13 mm | 0.094° |

完整报告在 `D:\MmdOracle\out\report-{fixed-354-vs-umt,fixed-1182-vs-umt,mmdanim-354-vs-umt,mmdanim-1182-vs-umt}.json`；输出骨姿态在同目录。独立 B 与 A 的膝部极值差约 5–6 mm，说明求值器并非数学完全相同。原始 VMD 的原配 PMX 模型未知；这不是“原作者动作真值”。UMT 克隆保留 P2 稀疏欧拉修复；本地 oracle 文件和第三方模型不进公开库。

## 正确路线（取代继续盲修自研 MMD 求值）

| 层 | 当前决策 | 验收门禁 |
| --- | --- | --- |
| 动作源求值 | 固定当前 Unity 2022.3 / URP 14 基线，UMT **隔离工程中离线 baked-FK** 为主基准；当前 C# 求值器继续保留作对照，`mmd-anim` 为独立第二参照及将来 Unity 6 候选。此时**尚未把 UMT 的 clip 接进生产播放器**。 | 同 VMD、同 PMX 在 1131 帧比较，位置 P95 ≤0.5 mm；膝/足最大差异单列，不用平均值掩盖。新动作重新验。 |
| 目标骨架映射 | 继续自定义 PMX → 提弗洛斯 481 骨角色 retarget；不要用 Unity Humanoid 直接替代，避免手指、twist 和肩部失真。 | 逐骨映射清单、T-pose/bind 复核、关键姿态截图 + 数值探针；角色网格无穿模/断肢。 |
| 根位移与脚部 | 已修根位移空间；下一步做动作全程的地面接触标记、脚锁/释放、足底误差曲线。可评估 Animation Rigging Two Bone IK 作为**目标骨架约束层**，不把它误当 MMD 源 IK 求值器。 | 全片逐帧足底高度与水平滑移曲线；分别验 in-place 开/关，跳跃不被锁死。 |
| 表情和物理 | 官方脸含骨骼偏移，现有 blendshape 别名不足；需先建立具体表情骨映射。头发/裙摆在定稿动作后再加物理，避免它扰乱骨架对照。 | 逐种 VMD morph 动作验收；物理可开关、确定性离线输出。 |
| 镜头与视频 | 相机格式 bug 已修，但还未和 UMT 逐帧数值比对；镜头、舞台、灯光、角色渲染必须分别验。 | VMD camera 的位置/朝向/FOV 逐帧对照，然后全片离线输出且无镜头抖动。 |
| 渲染 | 原捕获 shader/后处理链与 MMD 动作的接合仍未用同姿态官方帧闭环。 | 固定同帧、同视角、同曝光/灯光，以官方 RenderDoc 真值比图；分别记录角色 mask、颜色、细节误差。 |
| Unity 6 | 暂不迁移；待 Unity 2022 基线动作+渲染收敛后再迁。 | 自定义 URP Renderer Feature 改 RenderGraph、包兼容、重跑上述全部门禁。 |

## 许可证与边界

现有 `VmdMotion.cs`、`MmdRig.cs`、`MmdRetarget.cs` 等文件头**明确写着派生自 AGPL-3.0 Endfield-Poser**。即使后续把动作源求值换成 MIT 的 UMT / mmd-anim，其他派生代码的义务也不会自动消失。不要把“技术路线改成 MIT”误写成“整个仓库已经可按 MIT 发布”。公开仓库提交前须逐文件做许可证核查；想摆脱该依赖需要合规重写/替换，不是删注释。第三方 PMX、游戏解包资源、个人录制捕获数据保持本地隔离；本轮只提交自有代码与不含模型数据的文档。

## 可从这里接续

1. 先运行 `MmdFormatRegressionValidation.Run`，再用 354/1182 各跑 1131 帧与 UMT 比对；读取报告，不用旧 P1 报告。检验 `D:\MmdOracle\UnityMMDTools` 的 P1 确实撤销，P2 保留。
2. 把 UMT baked-FK 导出变成正式、可重跑的中间动画数据协议（骨名、帧率、单位、空间、轴、曲线精度、许可证），独立输入当前 retarget，不把 UMT 整套 shader/模型引进游戏工程；对比现有 C# 播放器的骨输出。
3. 完成相机 oracle 数值比较和角色全片地面/穿模探针，再做可重复的完整视频导出。保持 Unity 2022 基线直至各项门禁完成。
4. 渲染另设同帧画面门禁。几何与 MMD 源求值数字漂亮，不代表官方材质和后处理已经匹配；尤其不可再宣称“下一步只是单一增益修正”。

## 上游资料

- [UnityMMDTools (MIT)](https://github.com/CandidumGames/UnityMMDTools)
- [mmd-anim (MIT)](https://github.com/yohawing/mmd-anim) 与 [Unity loader 使用说明](https://github.com/yohawing/unity-mmd-loader/blob/main/docs/HOW_TO_USE.md)
- [Babylon MMD (MIT)](https://github.com/noname0310/babylon-mmd)：第三参考，不直接改写生产管线。
- [Unity Animation Rigging 约束文档](https://docs.unity3d.com/ja/Packages/com.unity.animation.rigging%401.2/manual/ConstraintComponents.html)
- [Unity 6 URP 升级文档](https://docs.unity3d.com/cn/6000.0/Manual/urp/upgrade-guide-unity-6.html)
- [SPCRJointDynamics (MIT)](https://github.com/SPARK-inc/SPCRJointDynamics)：可选次级动态，先验证目标骨骼和性能。
- [EIEM (AGPL)](https://github.com/Sasye/EIEM)：仅作为行为参照，不拷贝代码进入其他许可的模块。
