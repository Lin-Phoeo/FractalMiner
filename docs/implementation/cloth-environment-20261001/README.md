# 衣物原生环境反射输入与 s6 采样验证 — 2026-10-01

这是一项有边界的实现增量：帧 6411 的 Cloth01/02 环境立方贴图、实际 view/sampler、原生 BC6H 上传、生产衣物 IBL 消费与可恢复内存绑定。不是全官方渲染、完整角色场景、湿身或 MMD 的完成证明。没有截图拟合、曝光补偿、模型 LOD、质量分档或性能适配；纹理原有 mip 是官方预过滤数据，全部保留。

## 先纠正一条推断

前轮把 Unity 内联 `Linear` 名字推断成跨 mip 插值，这次 GPU 测试证明该推断不成立：当前 D3D11 后端的 `sampler_Endfield_LinearRepeat` 在十个生产衣物粗糙度用例中已经是最近 mip。初次 `gpu-red-01.txt` 实际是**旧 Repeat 路径通过报告**，其中测试说明当时误标“linked sampler”；不能把它引用为旧路径失败或旧路径已经使用 linked sampler 的证据。真正的首次 RED 是 Python 的缺模块、后续缺 source Clamp/pose 入口；另一次真实 GPU RED 是缺少载入后防篡改检查。

本轮把 source IBL 的 Repeat 改成实际 s6 的 Clamp，并独立验证该内联状态，**不声称这一 address-state 修改已经改变正常 cube 画面**。旧 `ImportCube` 使用 `FilterMode.Trilinear` 也是历史事实，但旧 source 路径使用独立内联 sampler，不能据此证明最终反射曾经跨 mip 插值。原导入器、现有持久化 cube asset 均未改写；新 loader 提供严格校验的内存输入，sampler 是 Bilinear/Clamp。

## 实际捕获证据

| 项目 | 实际结果 |
| --- | --- |
| 程序 | event835 PS22255、event850 PS37669；两条各自校验 shader 身份与原 SPIR-V SHA |
| 资源 | set0/b45，image Resource14188，BC6_UFLOAT，128²，depth1，6 slices，8 mips |
| view | TextureCube / BC6_UFLOAT，firstMip0/count8，firstSlice0/count6，minLODClamp0，identity RGBA |
| sampler | set0/b6 / Resource197；ClampEdge UVW，Linear min/mag，Point mip，Normal filter，noncomparison，aniso0、bias0、minLOD0/maxLOD1000、normalized、seamlessCube |
| 程序消费 | PS22255 `_58.SampleLevel(_24, reflect(...), 1.2*log2(max(roughness,.001))+5)`；PS37669 对应 cube 名 `_59` |
| 数据 | 每条程序绘制时全部 48 个压缩 subresource 与原 DDS 对应块逐字节一致；未把 mip0 的 EXR 重生成 mip |

DDS 是 DX10 BC6H_UF16（DXGI95，resourceDimension3、cube flag4、arraySize1），总 131380 bytes；头部148，压缩 payload131232。DDS SHA `3b0aa26b56ede6b780c186add2778d7155931fa9797ee513db6cd7c2a345b223`，payload SHA `898ff663c8d447456666612e55697f7aecde13c03b19b74f9df5b73735e2c9df`。每面按8级 mip依次排列；每级 `ceil(w/4)^2*16`，小 mip 仍占一个压缩块。

离线 exporter `Tools/capture_cloth_environment.py` 只读既有 RDC 和既有 DDS，关联真实 reflection index 与 descriptor 位置；不根据其他 variant 的资源顺序猜 binding。view/sampler 任一约束不符合即失败，只有 controller/capture 成功 shutdown 后才写 complete.json。两个事件每个48级均校验，并各留144项原生 PickPixel 通道；小 mip 中重复坐标**不是144个互异 texel**。

## 输入加载与生产消费

- `EndfieldCapturedEnvironment.CreateTexture`：先验证固定 DDS 长度/SHA/header；native BC6H 支持是硬前提，不能静默转成 LDR。按6面×8级 `SetPixelData`，`Apply(false,false)` 不生成 mip。unsigned/linear format、Bilinear、Clamp、aniso0、bias0、8级均验证；HideAndDontSave，仅内存对象。
- `ValidateTexture`：在创建后及绑定前，重新检查格式/大小/可读性/sampler，并将全部48块拼接重新计算固定 payload SHA；载入后被修改的纹理也不能进入全局。
- `EndfieldCapturedEnvironmentInputs.Load`：complete.json 固定 SHA `ea7b832f6ddbf7a13f1d2004e848ac109b19eddeeebcbd9abaf73360a928e2af`；只读取固定文件名，不按不可信 manifest 路径任意取文件。
- `Bundle.Bind/Dispose`：只改 `_CharMaxCubemap` 与 availability gate，保存前值并在结束时恢复；如果期间另一所有者替换了 cube，就不覆盖它的状态。验证失败先于任何全局写入。没有场景/材质/导入器/资产保存。
- `EndfieldOfficialCloth.hlsl`：环境采样改用 actual s6 对应的内联 `LinearClamp`；原 roughness LOD、BRDF、环境缩放及 IBL 在 direct saturation 之后的顺序不改。显式 LOD不额外套用 Base/P/N/E 的 global bias −1。
- `EndfieldPoseApplyValidation`：在现有捕获全局注入之后接入可选 `using` scope。**这轮未执行整段 pose render**，因为其旧入口会配置其他工程设置；只编译/核查入口接线，并通过独立无场景写入的生产 shader 测试验证消费。

## 重跑方法（只用已有离线捕获）

本机私有包：`Validation/Captures/native-cloth-environment-20261001-01/`，包含 pinned complete.json 与 DDS，遵循已有 ignored Captures 目录，不上传原始游戏/捕获数据。缺少该包时应明确失败；不能自动相信新 manifest。

若要在已有 pose 验证入口额外使用原生 cube，设置 `ENDFIELD_NATIVE_ENVIRONMENT_INPUTS=1`；可用 `ENDFIELD_NATIVE_ENVIRONMENT_EXPORT` 指向同一 reviewed package 的副本。**这不是最终成品开关**，也没有未经验证自动覆盖所有 MMD/播放器入口。

离线重导出：官方 qrenderdoc `--python Tools/capture_cloth_environment.py`，设置 `ENDFIELD_CAPTURE_PATH`、fresh `ENDFIELD_CAPTURE_OUTPUT`、`ENDFIELD_TOOLS_PATH`、`ENDFIELD_ENVIRONMENT_DDS`。成功条件是 complete.json，不是 GUI 程序的退出码。新输出须独立审查后才能更改 pin。

GPU 重跑：Unity2022.3.30f1 `-batchmode -force-d3d11 -projectPath ... -executeMethod EndfieldShaderPack.EndfieldClothEnvironmentValidation.RunBatch -quit -logFile <fresh log>`，设置 `ENDFIELD_CLOTH_ENVIRONMENT_REPORT` 为新文件。工具创建独立 preview scene 与内存 fixtures，不读写原角色场景，不保存 settings。结果文件使用 CreateNew。

## 验证与未通过过程保留

外部完整日志：`D:/EndfieldTechLib/notes/cloth-ibl-20261001-01/`。最终 `gpu-green-05.txt` SHA `51039dc78d44e52910d78ddd074628566b70e1da98f21046b7bd46e560a2ffe9`；对应 Unity log 明确退出0。

- 原生 BC6H：48级 CPU upload blocks 对应完整 DDS；144项 Unity cube GPU 通道与独立捕获 PickPixel 一致，maxError0，门限2e-5不变；所有6面方向验证，没有翻转、转码或 gamma 变换。不声称压缩 GPU memory 的直接 readback。
- Sampler：6面×11 LOD×2状态 =132项；linked Bilinear 与 source inline Clamp 都是 nearest mip；LOD负值/超过末级取边界。Trilinear negative control明确与 mip-point 不同。12项 exact quarter-texel 空间插值排除 nearest texel，point-filter negative control也通过。
- 生产 CharacterLit：10项 roughness-log2 LOD 对照。保持 roughness/BRDF不变，用“每个 mip 各不同常量”的 cube 对比“各 mip 全等于应选一级”的独立 fixture，验证真正生产消费的 mip 选择，不复制整套 shader 公式充当独立证据。另测实际native cube被消费和缺输入 gate。
- 所有权/失败：旧全局恢复、外来所有者不被覆盖、长度/截断/hash拒绝、创建后块内容修改拒绝且不部分绑定；默认5个pass通过编译与 SetPass。
- Python exporter仪器化行覆盖 **96.06%（122/127）**，9项测试/28 subtests；不是 C#/HLSL 或全项目覆盖率。全套313 passed、3历史 skipped、53 subtests，既有Pillow警告2条；Ruff/Pyright通过。pip-audit 临时审计环境未发现已知漏洞，不代表游戏/Unity/全部第三方二进制已审计。
- 回归：cloth normal 31 kernel/14 production、emission32/16、hair18/3 production invariants、native cloth normals120通道/24级和MPB/实际scene只读槽均通过；前三报告SHA与前轮相同。首次emission调用误设成 `ENDFIELD_CLOTH_EMISSION_REPORT`，正确变量应为 `ENDFIELD_CLOTH_PROBE_REPORT`；那次是入口报告路径失败，不是着色失败，改正后重新真实运行并退出0，失败日志同样保留。

中间失败不删除：`unity-mutation-red-02.log` 证实创建后修改的cube曾被接受，已补SHA检查；`unity-green-03.log`/`unity-spatial-diagnostic-04.log` 记录任意UV .4123/.6234 的理想浮点插值与硬件差约1.317e-5（mode0、face0）。**没有放宽2e-6门限，也没有动原生输入**；改用恰好可表示的四分之一/四分之三texel权重，在 controlled synthetic fixture 中严格检验bilinear。它不是任意 UV 理想插值与GPU逐位一致的认证。旧先行报告中误标 sampler 的说明已在本文显式纠正。

## 剩余工作，不按错误旧结论报完成

1. 材质输入：Cloth D/P/E、ShadowLUT、Diff/Spec ramp 的原生格式/sRGB/mip/view；其余族尚缺的同类输入审查。法线/cube通过不能推出其余PNG正确。
2. 特殊/空间分支：native vertex/skinning/instance basis；cloth wetness/clearcoat/透明/dither、眼睛/脸部特殊状态；环境体积、rims、local light、fog及官方shadow/depth相关pass。已有源码/文档需继续核查实际variant，不能直接套旧伪码。
3. 完整场景管线：把已验证子模块接进可重复加载的最终场景/后处理，明确捕获常量与实时输入来源、全局/MPB所有权，验证动态光照与相机，不靠截图曝光补偿。现有资产/旧入口不因本轮被全量认证。
4. 动作和出片：沿已审查的 MMD 源求值/独立参照/retarget路线，验证解包动作、根运动、脚接触、表情/物理、VMD相机及视频导出。还有standalone packaging和多视角/动态状态泛化，不是“再接一个文件就完美”。

v1封存manifest未动、79 pending；**严格verify实际返回1**，6771文件/18 anchors中只有 `changed:project:CODEX-HANDOVER-PROMPT.md`，来自封存后（上轮c96cc6c已经开始）新增阶段指针的授权文档更新，不是原官方源码变动。本轮又更新同一指针，错误名单不增加。不沿用上轮“v1全部integrity通过”的过时表述。v2同样返回1，149文件/7 anchors、24 pending，只列原有 CharacterLit / OfficialHair 两个授权runtime snapshot drift。没有为消除这些drift重写seal，也不将 snapshot mismatch 冒充全量PASS。主HEAD、用户9557项暂存索引、角色scene、Quality/GraphicsSettings与原DDS保持。提交以独立index从记录分支父 `c96cc6c20527502d6fb4c450e38abf1757bee052` 增量生成。

API参考：[Unity Cubemap.SetPixelData](https://docs.unity3d.com/2022.3/Documentation/ScriptReference/Cubemap.SetPixelData.html) 用于逐面逐级原生上传；[Sampler states](https://docs.unity3d.com/2022.3/Documentation/Manual/SL-SamplerStates.html) 解释inline与texture-associated两种绑定；本文mip行为结论来自当前D3D11实际GPU测试，不仅来自API名称。其他后端未认证。
