# 角色自阴影生命周期：2026-10-01 增量

本轮修复的是 Unity/URP 适配层的相机边界、停用与资源所有权，不是新的官方阴影公式。继续沿用 [上一轮官方消费链证据](../shadow-selection-20261001/README.md)，没有调整材质、光照数值、曝光、后处理、原场景或模型，也没有做截图拟合。

## 已核实的问题

全代码 writer 搜索显示：正常运行时只有 `CharacterShadowPass.DispatchResolve` 把 G gate 置1，没有 skip/setup/cleanup/dispose 对应复位；归零操作出现在测试/诊断而非运行时。旧 live 验证在禁用角色时手动归零，会掩盖残留。两个验证入口还把“相机结束后 gate=1”当成成功条件；动画入口只检查静态 `LastResolved`，可能接受旧帧。

新隔离测试先对旧实现运行：13个顶层场景中12失败，包含7个 skip guard、queued setup、cleanup、owned disposal 和 resize；唯一通过的是不应清除其他 owner 的 disposal。第13项集成在旧代码缺少新 completion 字段时失败，不把它计作旧 shader 算术错误。

## 运行时修改

- `AddRenderPasses` 清除当前相机 live G 的 texture/gate/size 和旧诊断，然后判断资格；不触碰独立 R owner。
- `OnCameraSetup` 通过 command buffer 按 GPU 执行顺序归零，保证 Execute 提前返回仍不会读旧 G。
- `OnCameraCleanup` 在相机完成后归零并绑定白图/零尺寸；诊断纹理保留供本次结果读取。正常材质渲染期间 gate=1，结束后 gate=0。
- 缓存光源停用时重新找启用的光源；找不到就明确 skip，不继续使用停用组件。未改变光方向或强度。
- resolve command 成功提交后才记录 `LastRenderSequence`、`LastRenderedCamera` 和诊断 targets。Sequence 单调增长、不因清理重置；这是提交证据，不是 GPU fence 或着色正确性证明。
- owned dispose 才清自身绑定/诊断；其他 pass 的绑定保留。resize/dispose 对自产 RT 同时 Release 和 Destroy，不留下释放后的 Unity 对象；重复 dispose 安全。
- pose、SkinBasis 动画和 AnimRender 三个入口改为“渲染前序号→渲染后新序号+相机身份”验收，并要求清理后的 gate=0。没有为保留旧 gate 而绕过 cleanup。

## 验证及测试前提修正

最终隔离 D3D11/Linear batch 的13/13顶层场景通过；其中第13项包含9次真实 URP 请求：A→A→B→A、feature停用、恢复、caster停用、light停用及再次恢复。两个相机尺寸64×48/72×48，验证诊断与当前相机一致。

在真实 `AfterRenderingOpaques` pass 中 dispatch 测试 compute，GPU读取当前 gate、size 和 G 点值；有效帧 gate=1、尺寸正确，停用/早退 gate=0。请求完成后再检查清理结果。不能在 callback 中用 CPU `Shader.GetGlobal*` 代替尚未提交的 GPU globals；初次 CPU observer 的失败保留在日志，没有降低标准。

测试开发中的失败也保留：preview scene 不适用于 registry 全局查找；未保存的 untitled scene 不能 additive 创建；同步 NewScene 会重置管线实例。最终要求空的独立 batch，以临时普通场景和内存克隆管线测试，场景建立后才显式 Prepare，再使用 URP SingleCameraRequest。没有给 production 加反射钩子，也没有因此宣称所有旧 Camera.Render 都有问题。Unity 2022.3 的 Prepare 创建/切换逻辑可查 [Unity 官方 C# reference](https://github.com/Unity-Technologies/UnityCsReference/blob/2022.3/Runtime/Export/RenderPipeline/RenderPipelineManager.cs)；测试钩子不适用于未知引擎版本，缺失则失败。

测试资源均为本轮自产或内存 clone；finally 恢复 Quality/default pipeline、G/R 全局及 fixture 光照全局，销毁资源与临时场景。不调用旧 Build/Activate/SaveAssets，不运行整帧像素比较或完整视频生成。

数值报告与哈希见 [verification.json](verification.json)、[lifecycle-gpu-report.txt](lifecycle-gpu-report.txt)、[red-and-intermediate-summary.txt](red-and-intermediate-summary.txt)。测试目录包括新增结构契约检查；C#/compute 无实测行覆盖率，不能用场景数冒充80%覆盖或全工程认证。

三项新隔离回归也通过：官方阴影消费238例、光照选择688例、MPB两槽两次更新保留root/user数据。Python Tools/tests + v2 raw-input tests 为416 passed、3历史 skipped、80 subtests passed、2既有 Pillow 警告；新增caller结构契约先暴露 AnimRender 未检查fresh sequence，再修复通过。Ruff/Pyright通过（同时修正旧单测正则结果的类型收窄）；pip-audit无已知漏洞仅指临时工具环境，不是整个Unity依赖认证。

## 后续边界

仍未认证：实际 event744/748 的完整生产程序身份与 render states、通用官方 R producer、live C++ light producer、weather producer/selector、最终原生资产/场景与后处理 lifecycle、完整动作/MMD视频。本轮真实请求只用 cube fixture 验证调度和所有权，不认证角色阴影视觉或 MMD 求值精度。

下一步仍是回源实际744/748 shadow producer（含 atlas/resolve、格式、矩阵、bias、资源视图及状态），再 render-state/weather/final binding。旧封存manifest不重写，79/24 pending与已知drift仍明示；主HEAD、9557条暂存索引和原场景设置必须保留。
