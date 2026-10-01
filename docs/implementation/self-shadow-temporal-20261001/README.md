# 角色自阴影晚一帧：修复与证据（2026-10-01）

范围：用户反馈的**角色身上自阴影无逻辑乱动**。本轮不改光照颜色、曝光、湿身、物理、MMD映射、地面投影或官方渲染公式，不做官方截图像素拟合。修复的是当前 Unity/URP 适配器的参数提交时序，不是宣称整个官方阴影管线已认证。

## 已证实的根因

旧路径在 `CharacterShadowPass.Execute()` 中给 Renderer / material-slot 的 MaterialPropertyBlock 写入本姿态的 `_EndfieldWorldToShadowClip`。但 URP 已经执行 `context.Cull()`；当前绘制使用的渲染器参数快照已经生成。结果：

1. 阴影图集绘制读到了旧矩阵。
2. Compute resolve 已收到本次 CPU 生成的新矩阵。
3. 不改变任何姿态再绘制一次，图集才读到新矩阵，自阴影因此突变。

决定性红测试是 `Validation/shadow-temporal-20261001-06/report.txt`：实际角色 + 真实 VMD + 二次运动，换姿态后立即绘制，再重复绘制相同姿态：

| 时间 | 自阴影变化像素 | 图集变化像素 | 屏幕深度变化 | 索引变化 | resolve矩阵变化 |
| --- | ---: | ---: | ---: | ---: | ---: |
| 2.0 s | 8,410 | 219,905 | 0 | 0 | 0 |
| 0.5 s | 12,496 | 255,618 | 0 | 0 | 0 |
| 1.5 s | 16,398 | 247,888 | 0 | 0 | 0 |

这是自有状态的时序一致性门禁，不是对官方截图做像素调参。01 的冷启动测试不能单独证明持续乱跳；06 使用稳定读回和先前已完成的绘制，排除了首帧 metadata 及读回误差。

## 实施

`EndfieldCharacterShadowFeature.OnCameraPreCull()` 调用 `PrepareShadowBindings()`，在 URP 剔除之前生成并写入图集矩阵 / slot index。每个 caster 只拟合一次 light box；其快照同时供图集 MPB 和 resolve structured buffer 使用，不能在剔除后重新拟合包围盒。光方向也取同一快照。

`Execute()` 不再写这些渲染器参数；缺少 pre-cull 快照时明确跳过，不能回退到已知错误的晚提交。两个不同尺寸的自有目标显式设 viewport，避免继承别的 pass 状态。其余摄像机准入、G通道所有权与清理、防止覆盖现有 material-slot 参数的逻辑保留。

没有改用 `beginCameraRendering` 事件：URP 的 `SingleCameraRequest` 不发该事件，而 `OnCameraPreCull` 在此入口也执行，因此 Studio 预览、离线导出和普通 camera 路径均可覆盖。

本机实际包源码为 URP **14.0.11**：

- `Runtime/UniversalRenderPipeline.cs`：先 renderer pre-cull，随后 `context.Cull`，随后 `AddRenderPasses` / Execute。
- `Runtime/ScriptableRendererFeature.cs`：`OnCameraPreCull` 专用入口。

`EndfieldCharacterLit.shader` 仅更正旧深度解释的**注释**。真实 D3D11 测试表明现有 ShaderLab LEqual + depth clear 1 在两种提交顺序下都选取 authored z=0.8 而不是0.2；这不证明原始 SV_POSITION 深度值必然被改写为1-z。没有据猜测改 ZTest、深度清除、receiver bias、Poisson表或G公式。

## 最终运行门禁

`Validation/shadow-temporal-20261001-09/report.txt`：**64 checks PASS**，没有额外 warmup 渲染掩盖首帧，也没有改阈值：

- 4次显式RT/无显式RT交替，resolve VP 与 URP 矩阵一致；每次绘制后 G 所有权清空。
- 真实生产图集 pass 的重叠深度 / 提交顺序测试通过。
- GPU world-position 独立光栅探针对生产深度反投影：本姿态中位误差约 **4.36e-6 m**；反Y反例约0.536m。后续姿态也通过固定2mm门限。
- 冻结姿态首次及4次重复、3个换姿态点：自阴影完全一致，图集 / 深度 / 索引重复差异均0。
- 30个连续MMD时刻，含实际转灯，交替 `StandardRequest` / `SingleCameraRequest`：首次导出帧与随后同状态重复绘制一致，**不是先重复绘制再保存正确帧**。

测试读回必须按GPU原生格式解码：A2B10G10R10按uint unpack，R32/R32G32按float，RGBAFloat按Color。01/03/04中 ReadPixels 对 packed 格式返回未初始化哨兵；05的转换读回也不能采信。因此早期“100m世界重建错误”已撤回，不能传播成另一根因。06修正工具后世界坐标门禁通过而时序门禁仍失败；07移到pre-cull后通过；08增加共享快照与扩展门禁后通过；09增加只能在独立batch运行的保护后重复通过。02是测试编译错误，日志留在本机 notes，不伪称通过。

回归见 `Validation/shadow-temporal-regression-20261001-01/`：camera生命周期、多相机、关闭 / 提前返回、R/G通道选择、3072个实际PS2261采样边界、实际PS9065 alpha cutout、renderer与material-slot既有数据保留、湿身 / 原始网格恢复。Python474项通过，3个历史skipped，80subtests；2条已有Pillow弃用警告。没有测C#/HLSL整工程覆盖率，不把检查数当覆盖率。

## 使用

等待 Unity 自动编译结束，关闭旧的 MMD Studio 预览会话，再打开 `Endfield / MMD Studio`，初始化人物 → 载入原 VMD → 播放。无需改灯光、bias或物理滑块；不要为了应用修复重建/覆盖官方场景。

直接看 `Validation/shadow-temporal-20261001-09/move-2.0-a.png`。连续30帧在该目录 `frames/`，其中转灯测试在第10、20帧会**有意切换灯方向**，不能把这些输出当固定照明演示。只输出真实Unity画面，没有AI媒体生成。

动作来源：Kimagure / @kimagure_video，UNFORGIVEN CHALLENGE VMD；不再分发 Motion.vmd，不声称动作原创。素材进一步发布/商业用途依其readme许可。

复跑：关闭占用同工程的用户编辑器后，设 `ENDFIELD_SHADOW_TEMPORAL_OUTPUT` 为全新目录、`ENDFIELD_MMD_TEST_MOTION` 为本机VMD路径；Unity batch执行 `EndfieldShaderPack.EndfieldShadowTemporalValidation.RunBatch`。所有验证仅用内存管线副本，不保存 scene / ProjectSettings / 材质资产。禁止运行会重建持久场景的旧RunAll来替代本门禁。

原始日志 / 代码前态 / 用户暂存索引备份：`D:/EndfieldTechLib/notes/shadow-temporal-20261001-01/`。保留官方场景、舞台、设置、sealed研究与主HEAD/用户暂存索引；使用独立记录索引提交。

## 未认证边界

本轮证明当前角色自阴影的晚提交问题已修复，**不是**整套官方延迟管线、D16偏置/打包/stencil/dither、独立R生产链、任意VMD、所有视角/后端的完整认证。当前仍是既有forward适配器；这些既有待办不靠“本轮PASS”自动消失。用户反馈的地面阴影未纳入本轮修改。
