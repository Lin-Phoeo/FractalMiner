# 提弗洛斯角色详情页：还原证据与待补输入

本次目标由用户明确为「提弗洛斯角色详情页」。完成本轮数据检查后，用户提供了该页面截图；
保存在忽略提交的 `Validation/LocalReference`，含账号信息，不上传。尚无同视角同姿势的量化匹配，
所以本报告验证数据与实现，不宣称已达到官方画面一致。历史会话中的命令只作为记录读取。

## 历史过程复核

会话来源：用户提供的 `终末地Unity渲染逆向还原.md`（402,847 字节，保留在用户 Downloads）。
没有将原会话上传到仓库。

- 历史 L943 把社区 `AllShader_1.5.3` dump 称为解包完成；L1006 随即承认「完全复刻/解包已完成」夸大。
  本地四个角色 shader 目录分别存在 2312（cloth）、652（skin）、870（hair）、150（eye）个 HLSL 文件。
  它们是有用的反编译证据，但不能证明本机整款游戏解包完整，也未证明与当前安装版本完全匹配。
- 实际可用的角色数据：481 个骨骼、17 个 LOD0 mesh、17 个材质 JSON/材质。
  原始单网格 JSON 在 `EndfieldUnpacker/AnimeStudio-net10/_all_meshes/.../typhoea/models`。
  合并数据在 `Assets/Typhoeus/_typhoea_model_data.json`。
- 原始导出仅眉毛带显式切线，vfxpart_01 带 UV1；多数网格没有显式切线、顶点颜色或 UV7。
  不能把不存在的 UV7 当作有效平滑法线。当前缺失切线用几何/UV 重算，是重建而非恢复原字节。
- 历史 L5698、L6288、L6377 在 FBX、缩放、旋转等原因间反复切换，并把矩阵检查通过直接解释为不炸模。
  已修复的实际 Shader 问题见上一检查点：世界米制描边、缺失深度预通道、缺失切线。
- 只统计槽位、对齐属性名或编译通过都不足以证明视觉还原。每次修改须保留几何回归、通道输出和最终截图。

## 本轮核对并修正的语义

源码根目录均相对于本工程：
`_dump_1.5.3/AllShader_1.5.3/Assets/packages/com.hg.render-pipelines/runtime/shaders/materials/characternpr/`

| 项目 | 可复核证据 | 本轮处理 |
| --- | --- | --- |
| 材质图通道 | `characternpr.shader` 的 `_MetallicGlossMap` 标签；`characternpr/Sub0_Pass0_Fragment_b1002.hlsl:412`、`:886` | R 金属度、G 高光强度、B 阴影遮罩、A 光滑度；不再把 G 当整体遮蔽 |
| 头发双法线 | `characternpr_hair/Sub0_Pass0_Fragment_b100.hlsl:444` 至 `:465` | HN 的 RG 用于漫反射法线，BA 用于高光法线；保留四通道线性数据 |
| 双高光偏移 | 同文件 `:1047`、`:1054`、`:1055` | 两条切线分别加入 `_AnisotropyValue/Value2` 偏移，接入 G 强度和 A 次高光遮罩；全局灯光混合仍用 URP 近似 |
| 法线缩放顺序 | cloth b1002 `:437` 至 `:445` | 先重建 Z，再缩放 XY |
| 背面法线 | cloth b1002 `:452` | 按 `_BackFaceNormalFlip` 翻转背面，保持源枚举 0=翻转 |
| 颜色 LUT 坐标 | cloth b1002 `:419` 至 `:435` | 线性基色转 sRGB 后索引 32³ LUT |
| 高光图向量 | `characternpr_skin.shader:66`、skin b125 `:764` | `_HighlightMapVector` 改为 Vector，用 XY 偏移 UV；最终高光照度仍依赖未取得的角色全局参数 |
| 序列化旧字段 | 材质 `_ClearCoatMask` 同时有 texture/float；schema 审计脚本 | 按 Shader 声明类型写入，跳过旧类型记录，避免 SetFloat 写纹理属性 |
| 旧重阴影/假菲涅尔 | `Tools/audit_material_schema.py` 的源码属性集合对比 | 默认关闭 `_EnableLegacyShaping`；保留兼容选项，不自动启用未在该 dump 定义中的旧效果 |

20 张数据贴图改为 Default / linear / uncompressed，避免 sRGB 解码或法线重打包破坏通道。
这不是对所有纹理一刀切：颜色贴图、颜色 ramp 和 LUT 输出的颜色空间设置未批量改变。

## 验证结果与真实限制

- `Validation/material-report.txt`：667 个标量、141 个颜色/向量、82 处纹理绑定与源 JSON 一致；
  5 个过期跨类型条目安全跳过。3609 个源条目未被当前统一 shader 声明，名单保留在报告内。
  这个数字包含重复、旧字段和关闭的特性，不等于 3609 个必须实现的效果，也不代表全功能已还原。
- 再次修复贴图时 repaired=0，处理可重复执行。
- 17 个持久化 mesh 重载、静止蒙皮、头骨旋转测试继续通过；shader 编译通过。
- 六张 `Validation/channel-*.png` 分别输出基色、法线、金属/发丝混合、高光遮罩、阴影遮罩、光滑度。
- `Validation/verified-front.png`、`verified-side.png`、`verified-back.png` 是当前 Unity 输出，不是官方截图。

仍缺：角色详情页的实际相机/姿势/曝光、`_CharacterParams*` 与环境全局常量、准确的灯光混合、
SDF 面光完整公式、眼睛视差、角色阴影通道、专用半透明/VFX、后处理链及其顺序。
目前 Shader 是 URP 重建，若无这些输入，不能称作完整管线逆向或像素一致还原。

## RenderDoc 与下一项输入

RenderDoc 可查看事件、管线状态、着色器、绑定资源、纹理和 buffer：
https://renderdoc.org/docs/window/index.html

本机工程中已有 `Assets/Scenes/RenderDocDrawCallAnalyze.py`、`RenderDocVulkanDump.py` 等脚本，
但脚本存在不等于已取得截帧。本次在工作区及 Downloads/Desktop 检查没有发现 `.rdc`。
助手正常启动 Endfield.exe 和 Launcher.exe 时均未暴露可操作窗口；随后用户手动成功启动，
并提供了角色详情页截图。正在检查标准 RenderDoc 截帧条件。

最小对照输入：用户正常打开提弗洛斯角色详情页，保持静止，或提供同页面无二次压缩截图。
若已有可正常打开的 `.rdc`，还需其文件路径、游戏版本和画质设置。先匹配一个确定帧，
再用转角/灯光变化检查；单帧看着相似不足以证明完整还原。
RenderDoc 帧可以补足 GPU 端证据，但不会自动恢复原工程或缺失的 C++ 渲染管线源码。

用户给的 NGA/Zhihu/tajourney 链接本次仍返回 403 或超时，未将未读正文当作论据。
