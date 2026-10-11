# 官方物理输入链：BoneCloth构建分支与Line代理方向

2026-10-11。接续[初始属性与标志](../official-physics-initial-buffers-20261011/README.md)，确认限定运行时构建分支的优化行为，并把两态11组参考getter导入接到代理绑定方向。**不是完整proxy、约束列表或Unity求解器。**本轮没有启动Unity/游戏，也没有改舞台渲染、湿身、阴影或预览物理。

## 源证据纠正与限定结论

不能以“simpleDistance/shapeDistance=0”推断未改序。本轮从原代码确认更直接的分支：

1. `ClothProcess+<>c__DisplayClass10_1.<RuntimeBuildAsync>b__0` method368612/RVA`0x3ddcec0`，依次调用导入、可能的Reduction、Optimization、选择属性和ConvertProxyMesh。`0x3ddd8c4`检查owner的`<clothType>k__BackingField@0x60`是否为0；不为0跳过Reduction路径。当前metadata的`ClothProcess.ClothType`确认为MeshCloth=0、BoneCloth=1、BoneSpring=10，不能与RenderSetupData的setupType数值混用。
2. `Optimization371522/0x3dd9230`直接调用`RemoveDuplicateTriangles371523/0x3dd9ac0`。后者通过`get_TriangleCount371556/0x3dda7e0`读取triangles包装count，在count<2时跳到只恢复栈/寄存器并ret的尾部，不走三角形重建，更不重排顶点。
3. 本API限定普通BoneCloth=1、Line=0、**零三角形**、custom skinning关闭、normal alignment=None。因而限定路径上的顶点槽和导入方向保持原序。不是所有Optimization都无效，也没有移植MeshCloth减点/triangle路径或PreBuild缓存路线。
4. `ProxyNormalAdjustment371527/0x43f6b10`仍先分配并按调用侧identity契约填充，然后alignmentMode=0返回。复用原有None参考，不把它误当“连数组也不用生成”。**泛型FillJob最终写入及真实allocator/运行状态仍未证明。**

构建callback的11300字节精确unwind范围包含11269字节代码、3字节padding、一张7项/28字节RVA表。整范围线性解码曾失败；本轮分区重新验证全部代码、表加载/分派及7个目标指令边界，没有把表数据当代码。共13个原片段、5个metadata方法身份和17个选定锚点重新认证；不是完整所有CFG/异常路径或游戏实时分派证明。

## 已实现的接线

- `Tools/official_physics_line_frames.py`：严格门控上述路线，复用已核查的`vertex_bindpose_frames`、`vertex_to_transform_rotations`和`default_normal_adjustments`。不重写已有浮点数学，不额外归一化或统一四元数符号。
- `Tools/export_official_physics_line_frames.py`：关联getter导入、fresh属性/flags和保存配置，要求三个显式SHA256、匹配状态/身份/组序/窗口及关闭custom skinning；重新检查属性/flags映射，拒绝覆盖输出。
- 原world rotation由skin快照供给，init inverse render rotation由末尾render快照按已核查inverse规则求得。代理绑定位置为单独的负位置，绑定旋转为inverse(frame)；vertexToTransform严格为`inverse(frame) * (inverseRender * worldBoneRotation)`，不是交换顺序或逆TRS平移。
- `normalAxis=Up`是独立求解参数，不是None对齐开关，也不是在此额外预旋转的理由。此前Spring/Motion中有已核查消费；本单元不宣称其所有全局下游完整、不改官方配置。

## 参考输入与验证

输入沿用已封存的隔离Unity参考树getter导入与初始属性产物。`--zero-triangle-line`声明**参考构建实验的零三角形前提**，不是观测游戏实际proxy。fresh/未改序与空运行时覆盖前提也原样保留。不能把原始保存配置、参考getter或三个文件封印当作游戏build路线、实时字典/allocator的证明。

两个状态各11组/140个skin，产出共280组vertex bindpose、vertexToTransform、None调整旋转；属性/flags和槽序保持。额外render槽只供给render rotation，不混进skin方向输出。

独立NumPy检查280个位置、560个方向矩阵及原槽映射/属性/flags：负位置完全一致；用矩阵basis/inverse/multiply单独验证方向关系，最大代数差`1.6161181166651772e-6`，预定数学检查容差`1e-5`。这不是逐像素拟合，不是native/Burst逐位oracle或角色动态验收；既有方向内核的原库位模式验证见[方向参考](../official-physics-proxy-frames-20261002/README.md)。

33项专项、4029项全量测试及114项subtest通过；3历史skip、2历史Pillow告警保留。新两模块90语句/32分支合并覆盖率96.72%，语句97.78%、分支93.75%；缺口是导出器两个拒绝分支，核心方向模块100%。Ruff/Black/Pyright/compileall通过，临时工具环境48依赖无已知漏洞，不是整个Unity项目安全验收。

## 复现与封存

在FractalMiner根运行，输出必须使用未存在的新文件：

```powershell
uv run --python 3.13 --no-project python -B Tools/export_official_physics_line_frames.py `
  --imports "D:/EndfieldTechLib/notes/official-physics-getter-production-20261011-01/eleven-imports-01.json" `
  --imports-sha256 3b9e2546c12fbe7b2c21e4cad6acf9faba8c1df8b258dad73ef92c12dcde9af7 `
  --buffers "D:/EndfieldTechLib/notes/official-physics-initial-buffers-20261011-01/eleven-buffers-01.json" `
  --buffers-sha256 f6c2a654f254937496bc79a217e2a57748168d107dfe4d3fdaf0f6196f635b57 `
  --config "D:/EndfieldTechLib/notes/official-physics-fingerprint-20261001-01/official-cloth-config-04.json" `
  --config-sha256 ce377a025cc16e68a0382e92d73b0b47c82641550f79f58846dcc68af4ad9b3d `
  --zero-triangle-line `
  --output "D:/EndfieldTechLib/notes/official-physics-proxy-preprocess-20261011-01/eleven-frames-02.json"
```

本地`D:/EndfieldTechLib/notes/official-physics-proxy-preprocess-20261011-01/`：`eleven-frames-01.json`、`verify_frames.py`/`independent-frame-check-01.json`、`inspect_source.py`/`preprocess-source-04.json`、`certify_sources.py`/`source-certificate-02.json`。前序源报告包括整范围解码失败和错误枚举名称查询，保留而不采用为最终证据。

`red-01/02.xml`保留模块缺失RED；`checks-01.json`保留测试路径tuple类型未明确造成的Pyright失败，改成固定三槽tuple后`checks-02.json`全部通过。`green-02.xml`、`coverage-02.json`、`full-suite-01.xml`、`pip-audit-01.json`封存最终验证。原件/完整反汇编/商业源码仅在本地；公开提交通用实现、合成fixture和哈希。没有新subagent或原游戏代码执行。

## 下一步

接11组实际参考实例ID的父子表、baseline、局部姿态与root/depth，再形成约束work-list/Team/生命周期发布。None泛型填充、真实游戏构建状态、恢复角色动态getter和完整候选C#调度仍有缺口，不能把当前参考输出冒充最终BuildProxyMesh。完成候选链后再做MMD/解包动作与reset/seek/暂停恢复的Unity动态验收。
