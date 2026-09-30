# 官方资料层核查记录（2026-09-30）

> 后续全资料入口：[证据基线v1](../render-baseline/v1/foundation.md)。下文仍保留本日第一批天气/阴影审查范围；随后四族、描边/C6和后处理修订已同步原文，整体状态以v1的范围/缺口为准，不把本页旧“其它尚未审”误当后续工作未发生。

## 范围与结论

用户要求：先确保资料准确，再复用湿身等已有成果；不做官方截图逐像素拟合。

本批核查并修正湿身、场景雨系统文档的关键数学/输入契约，以及 C6 覆盖阴影/地面接收文档的具体错误。**不是全部 shader、全部变体、整个游戏管线已通过审计。** 未完成的生产端/运行时项不能写成“完全无误”。这次没有改 Unity 渲染实现、材质、网格、场景、天气参数或解包原文件。

源码证据来自本机 `_dump_1.5.3` 的反编译文件；它们是该快照的一级证据，不是官方发布的可读源代码，也不自动代表今后游戏版本。变体号必须与 shader/pass/快照绑定，不能跨部件仅凭 b400 等编号套用。

资料入口沿用 [INDEX-shader-sources.md](INDEX-shader-sources.md)，不重复撰写整套 shader 分析。外部 C6 报告在 `D:/EndfieldTechLib/reports/translations/`，原先索引称“未创建”是检索范围错误，已更正。

## 已核实并修正的输入/公式

以下路径相对 `_dump_1.5.3/AllShader_1.5.3/Assets/packages/com.hg.render-pipelines/runtime/shaders/materials/`。

| 项目 | 正确契约 | 一级证据 |
|---|---|---|
| 天气包 | `asuint(float)` 位重解释后按4字节拆包，不是 float→uint 数值转换 | `characternpr/characternpr/Sub0_Pass0_Fragment_b400.hlsl:458-459` |
| 雨/雪 | `_623=byte0` 进入雨分支；`_626=byte3` 进入雪分支；原文把雪标成水位错误 | 同文件 `460-465,669,1019` |
| 局部浸湿 | byte1乘水线高度smoothstep；byte2与其max得 `_636`，再与雨量max得 `_637`；不是雨/湿/雪三者取max | 同文件 `463-465` |
| 选择器 | 掩码用 CP10.x>0.5分支；水线高度用 CP10.x连续lerp，不是同一个布尔门 | 同文件 `458,463` |
| 雨滴时间 | 降雨模式时间=`_Time.x`，phase=`frac`；无雨浸湿模式时间=1，phase=clamp后lerp；原文方向反了 | 同文件 `696-701,742` |
| 静止雨向 | 投影使用 restT/restN 与世界 TBN，不是 restPos；蒙皮位决定 xzy 变换 | 同文件 `675-681` |
| 平面权重 | 贴图权重用三次方，程序雨滴权重用十次方，不共用 | 同文件 `682-684,704-705` |
| 网格数量 | 两组×三平面：32与46×1.4；没有第三组独立1.4网格 | 同文件 `702-703,832` |
| 雨痕平面 | xy/zy竖直平面，另算水平化法线权重；不是xz/zy | 同文件 `947-954` |
| 湿法线 | 雨贴图法线+归一化程序雨滴项+动画雨痕项；方向增益用切线雨滴法线，不是世界湿法线 | 同文件 `954-977` |
| 程序强度 | `_1964.y`控制雨滴类别，`_1968`参与强度测试；不是贴图alpha或半径 | 同文件 `967,986,993` |
| 材质粗糙度 | `_512=1-MetallicGlossMap.a`，湿分支向0.05降低粗糙度；雪向0.9增加粗糙度 | 同文件 `433,640,989,994,1048` |
| 各向异性 | 双轴参数乘 `_2292`，不是 `_2293`；SpecRampMap.y用粗糙度×(1-metal) | 同文件 `1065-1069,1118,1121-1128` |
| 法线分工 | b400无雪时 `_2279=_580`，不可自动替成 `_2138`；不同项独立使用湿/原法线 | 同文件 `1055,1085,1107-1108` |
| LiquidAg范围 | b12读取天气包最高字节做单UV雪覆盖，没有b400雨痕/雨滴/丝袜链 | `characternpr/characternpr_liquidag/Sub0_Pass0_Fragment_b12.hlsl:414-415,587-608` |
| LiquidAg IBL | 第二有理式分母向量为粗糙度幂；多重散射分母为 `_1472+_1477`；反射用几何法线 `_474` | 同文件 `658-666,680-684,693` |
| RTR输出 | hit alpha单独写alpha，不加到RGB；Blend OneMinusSrcAlpha SrcAlpha不是标准预乘混合 | `characternpr/characternpr_liquidag/Sub0_Pass3_Fragment_b61.glsl`末尾；wrapper `398-409` |
| 雨MV | FarRain b6/b7虽有HG_ENABLE_MV，片元Target1仍恒零；声明中存在上帧矩阵不能证明输出真实MV | `rain/farrain/Sub0_Pass0_Fragment_b6.hlsl:2,332`及b7末尾 |
| SceneEffect深度 | 重建必须包含fragCoord.z、齐次除法；遮挡UV翻Y并加scroll，不是任意旋转UV | `rain/sceneeffectrain/Sub0_Pass0_Fragment_b12.hlsl:216-237` |
| 水花公告板 | 第二cross为 `cross(up,axis)`；角点含世界Y方向，不是水平XZ板 | `rain/rainsplash/Sub0_Pass0_Vertex_b3.hlsl:298-304` |
| 覆盖投影 | 指定投影项清零不等于正交相机；保留原透视齐次结构 | `characternpr/characternpr_overlayshadow/Sub0_Pass0_Vertex_b5.hlsl:293-299` |
| 地面bias | fade=1-clamp(N·L,0,0.89999997615814208984375)，比较深度有0.01下限及范围/NaN检查 | `characternpr/characternpr_shadowreceiver/Sub0_Pass0_Fragment_b2.hlsl:306-317` |
| 地面SH | 信号判据是any而非所有分量；迭代用4×4矩阵；0.95约束混合量，不直接约束最终RGB | 同文件 `546,561,576-592` |

中文“雨/浸湿/雪”标签按各分支实际用途确定，不是已经恢复的引擎C++字段名。文档导读中的中文占位公式不是可执行的完整端口；实现时必须继续回对应源码，不得自行补缺失乘数或钳制。

## 覆盖阴影的捕获交叉核实（不是像素对照）

已有离线证据：`Validation/overlay-source-20260930-02/states.json`，`complete.json`为ok、12事件、frame6411。运行时深度比较为GEqual（Vulkan反向Z），不能把wrapper默认LEqual不经平台转换照抄到原生Vulkan状态。

| 事件 | 用途 | Stencil ref/read/compare | 深度写 | RGB / Alpha混合 |
|---|---|---|---|---|
| 968 | 第一眼白叠影 | 4 / 20 / Equal | Off | Zero SrcColor / One One |
| 971 | 第二眼白叠影 | 20 / 20 / Equal | Off | 同上 |
| 993 | 头发叠影预深度 | 4 / 20 / Equal | On | Zero One / Zero One |
| 997 | 头发叠影颜色 | 4 / 20 / Equal | Off | Zero SrcColor / One One |

Skin写36、eye写52，`&20`分别为4和20；两个Ref分类互斥，不能把Ref20解释为同时覆盖脸和虹膜。已有官方叠影网格应复用，不自行造近似网格，不把ReadMask改0称为官方实现。

## 未通过完整验收的部分与接入顺序

1. **天气生产端**：未证实谁写RGBA位包、水线高度、UV比例以及逐对象选择器；NaN等float位模式不可做普通浮点运算后再打包。
2. **天气运行时绑定**：现有角色详情页捕获不能证明湿天气路径实际启用。缺少湿天气帧时，只能声称数学/读取端已核查，不能声称运行时全闭合。
3. **资产契约**：RainEffect/RainStreak/Snow贴图的真实绑定、格式、线性采样与各部件所选变体还须核实；不能直接拿一张近似贴图替代。
4. **代表变体之外**：雨光照、部分雪花、LiquidAg深度淡出/VFX/RT变体和b400后半光照链没有因本批修正自动获得完整验收。
5. **匿名语义**：C6的SH生产端/bias位分配/逐对象dither字段仍待核；推测与可观察公式分开保留。
6. **其它文档**：skin/hair/cloth/eye/描边/后处理已有转写继续复用，但本批没有重新审完它们所有变体。不写“整套文档已完全准确”。

接入顺序：先关闭上述资料缺口 → 保留原资产与解码契约 → 实现源码公式/变体 → 核查pass顺序、深度/模板/混合及色彩空间 → 检查解包动作和VMD驱动时绑定仍成立。此次资料审计不改此前已通过的动作测试结论，也不把它们扩张为完整MMD验收。

## 证据快照SHA256

下列相对路径均以本记录的materials根为基准。文件变化后重新核查，不沿用本次行号。

| 文件 | SHA256 |
|---|---|
| characternpr/characternpr_liquidag.shader | `6C82EFF3E477AFE30262D6E8FF060E28FA8E6490A44ADF5D68F2EBB5271B8440` |
| characternpr/characternpr.shader | `985FC5A27BEE813A28594ED75BF1E50E57EE81D4E2A16E84C6DF549B05923EE5` |
| characternpr/characternpr_liquidag/Sub0_Pass0_Fragment_b12.hlsl | `FE467FC52752C6EC51FBEF1DF2BCE8021842A97422F6EEC6712AC23821359756` |
| characternpr/characternpr/Sub0_Pass0_Fragment_b400.hlsl | `B505BE7571E300F5C7C55651C67C6C46E48422D786493A6668B296429A6350BD` |
| characternpr/characternpr_overlayshadow.shader | `B6C2303D31CA111597E6F6FD48A376E852A5CA58CFCCF0131F467C54AA5D3FCF` |
| rain/farrain/Sub0_Pass0_Fragment_b6.hlsl | `00B2CA41305CD6DFF8317ABC990DDA553887409FA507D685DCA6E55671F8977A` |
| rain/farrain/Sub0_Pass0_Fragment_b7.hlsl | `874AACD07692F35D3FA1AAFC0474C79D5E3C2BC2CBB282B98771F492828DF386` |
| rain/sceneeffectrain/Sub0_Pass0_Fragment_b12.hlsl | `EE0770038A21697F1EF259B34D7F513C264AF6AB21A02E958212CB400441AAD9` |
| rain/rainsplash/Sub0_Pass0_Vertex_b3.hlsl | `5868CE7B61FFDB078CAC7A3CD225DE3B97D739E27C9BAE7FA9127C5F4BDF6EE8` |

## 留存

原文备份和主索引备份：`D:/EndfieldTechLib/notes/source-doc-audit-20260930-01/`。

核查结果：41项检查通过（9个源码SHA256、20个关键表达式锚点、4个已有捕获状态组合、6个文档链接/代码块检查、2个索引检查）。这是防止资料与证据脱节的检查，不是完整shader等价性测试；未运行Unity、未用截图残差拟合。全量未展开变体仍按上文待核处理。

本机可复核脚本：`D:/EndfieldTechLib/notes/source-doc-audit-20260930-01/verify-source-docs.py`（只读文件、无依赖）。运行 `uv run --python 3.13 --no-project python -B D:/EndfieldTechLib/notes/source-doc-audit-20260930-01/verify-source-docs.py`。pip-audit只检查本次隔离工具环境，结果无已知漏洞；没有因此声称整个Unity工程依赖已完成安全审计。

本仓库只提交本批资料修正；外部两份C6文档修正留在原位置，其关键更正已同步于上表，GitHub读者无需依赖外部文件才能知道这些错误。不得把外部文档“不在仓库内”与“没有创建”混为一谈。
