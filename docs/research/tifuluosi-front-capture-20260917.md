# 提弗洛斯：正面 3D 展示帧离线回放与分析

日期：2026-09-17。输入由用户自行提供：`C:\Users\Administrator\Downloads\正面.rdc`。
用户报告使用 RenderDuck `_v1.4` 成功抓帧。本轮助手没有运行 RenderDuck、启动/注入游戏、
修改保护组件或改写原始 RDC；只使用官方 RenderDoc 1.46 的 qrenderdoc 离线打开捕获。

## 已验证结果

- RDC：1,410,912,390 字节。
- SHA-256：`A12356A3FDED2197CC542D6AC41226C8FCCFC64E049117033BAA40C8B52B43C1`。
- 官方 RenderDoc 回放控制器成功打开并执行至帧末事件 1521；帧号为 6411。
- 该帧有 246 次绘制、44 次计算调度、4,057 个纹理资源、39 个 buffer。
- 帧末呈现目标已导出为 2560x1600 PNG。人工查看确认它是提弗洛斯正面 3D 展示页面，
  没有角色详情页右侧大 UI 面板遮挡，适合作为角色正面、面部、眼睛、头发、衣服和脚部的
  视觉对齐基准。
- 全量细节导出得到 290 条绘制/调度记录、89,304,134 字节的 `draw-details.json`，
  并导出本帧唯一 VS/PS/CS 的 SPIR-V 与反汇编。采样器、读写资源绑定、完整深度/模板/混合
  状态仍需要后续扩展工具采集。

本地输出全部放在 Git 忽略目录：`Validation/Captures/tifuluosi-front-20260917/`。
其中有效目录为 `replay-preview-02/` 与 `replay-details-01/`。`replay-preview-01/` 是一次
脚本路径未加引号造成的空跑目录，不作为结果使用。

## 角色绘制调用定位

下表使用本地已知提弗洛斯子网格索引数筛选候选。索引数是高可信锚点，但最终语义仍要结合
Shader、材质资源、渲染目标和后续状态采集确认。

| 本地网格候选 | 索引数 | 正面帧事件 | 观察 |
| --- | ---: | --- | --- |
| iris_01 | 618 | 496、776 | 776 是主颜色 pass 候选 |
| brow_big | 1,566 | 272、420、501、781 | 781 是主颜色 pass 候选 |
| body_01 | 4,248 | 277、425、507、786、892 | 786 是主颜色 pass 候选，892 是后续叠加候选 |
| cloth_01 | 94,791 | 326、435、556、835、897 | 835 是主颜色 pass 候选，897 是后续叠加候选 |
| cloth_02 | 36,852 | 341、450、571、850、902 | 850 是主颜色 pass 候选 |
| face_01 | 10,686 | 351、460、581、860、912 | 860 是主颜色 pass 候选，912 是后续叠加候选 |
| brow_small | 420 | 356、465、586、865、917 | 865 是主颜色 pass 候选 |
| hair_01 | 54,816 | 366、475、596、607、875、923、982、987 | 875 是主颜色 pass 候选，982/987 写入另一颜色目标 |

主角色颜色 pass 位于 `vkCmdBeginRenderPass(C=Load, DS=Load)` 之后的事件 768-936。
事件 956 之后进入后续处理/附加写入区间；其中 982、987 再次绘制头发索引数 54,816，
颜色输出从主目标 `ResourceId::55208` 换成 `ResourceId::19414`，不能与 875 的头发主色 pass
混为一谈。

## 主颜色 pass 资源锚点

这些资源名是 RenderDoc 捕获中的资源名，不是游戏资产原始文件名。尺寸和格式对 Unity 还原有
直接约束价值。

| 事件 | 部位候选 | VS | PS | PS 只读资源数 | UnityPerMaterial 大小 |
| ---: | --- | --- | --- | ---: | ---: |
| 776 | iris_01 | `ResourceId::22258` | `ResourceId::22259` | 14 | 400 |
| 786 | body_01 | `ResourceId::22249` | `ResourceId::22250` | 15 | 368 |
| 835 | cloth_01 | `ResourceId::22254` | `ResourceId::22255` | 19 | 336 |
| 860 | face_01 | `ResourceId::37670` | `ResourceId::37671` | 21 | 384 |
| 875 | hair_01 | `ResourceId::22256` | `ResourceId::22257` | 18 | 448 |

面部主色事件 860 的 set1 贴图尺寸：

- `b1`: 1024x32 BC7_SRGB。
- `b2`: 512x512 BC7_UNORM。
- `b3`: 1024x1024 R8G8B8A8_UNORM。
- `b4`: 512x512 BC7_UNORM。
- `b5`: 1024x1024 BC7_SRGB。
- `b6`: 256x1 R8G8B8A8_UNORM。
- `b7`: 1024x1024 BC5_UNORM。
- `b8`: 1024x1024 BC7_SRGB。

头发主色事件 875 的 set1 贴图尺寸：

- `b1`: 2048x2048 BC7_UNORM。
- `b2`: 256x256 R8G8B8A8_UNORM。
- `b3`: 2048x2048 BC7_UNORM。
- `b4`: 512x512 BC7_UNORM。
- `b5`: 256x1 R8G8B8A8_UNORM。
- `b6`: 2048x2048 BC7_SRGB。

衣服主色事件 835 的 set1 贴图尺寸：

- `b1`: 256x256 R8G8B8A8_UNORM。
- `b2`: 2048x2048 BC7_UNORM。
- `b3`: 256x1 R8G8B8A8_UNORM。
- `b4`: 2048x2048 BC5_UNORM。
- `b5`: 2048x2048 BC7_SRGB。

事件 875 还读取 `ResourceId::59000`，尺寸 2560x1600、格式 R32_FLOAT，位于 set0/b46；
事件 982 的后续头发 pass 会额外读取 1x1 D16 和 4096x2048 D16 深度目标。这说明头发效果
不是单个表面着色 pass 就能完整覆盖，后续需要按 pass 分层复原。

## 全局光照与角色参数

对事件 875 的头发主色 pass，与 1.5.3 dump 的 `characternpr_hair/Sub0_Pass0_Fragment_b100.hlsl`
布局交叉验证后，关键常量如下：

- `_TransformVariables_WorldSpaceCameraPos_Internal`：`(-300.0, 300.78, -297.04, 0.0)`。
- `_ScreenSize` / `_BackBufferSize`：`(2560, 1600, 1/2560, 1/1600)`。
- `_ExposureWithMiscParams`：`(1.0, 1.0, 1.6, 0.100001)`。
- `_LightDataBuffer_DirectionalLightDirection`：`(0.0213893, -0.642788, -0.765746, 0.0)`。
- `_LightDataBuffer_DirectionalLightCustomData1`：`(1.0, 1.0, 1.0, 1.62439)`。
- `_CharacterParams0`：`(1.0, 1.0, 0.65, 0.9)`。
- `_CharacterParams1`：`(0.0, 1.0, 0.0, 1.0)`。
- `_CharacterParams2`：`(0.849077, 0.895769, 1.150923, 1.0)`。
- `_CharacterParams5`：`(1.0, 1.0, 1.0, 1.0)`。
- `_CharacterParams6`：`(0.0, 1.0, 0.0, 0.0)`。
- `_CharacterParams7`：`(0.15, 1.5, 0.5, 0.0)`。
- `_CharacterParams8`：`(0.0, 0.0, 0.0, 1.0)`。
- `_CharacterParams9`：`(0.0, -1.0, 0.0, 0.4)`。
- `_CharacterParams10`：`(0.0, bit-pattern-small, 2.25, -100.0)`。
- `_CharacterParams11`：`(0.176319, 0.529919, 0.829516, -0.1)`。
- `_CharacterParams12`：`(1.0, 1.0, 1.0, 0.0)`。
- `_CharacterParams13`：`(0.0, 0.0, 0.0, 1.0)`。
- `_CharacterParams15`：`(0.0, 0.001, -1.0, 0.0)`。

注意：RenderDoc 反射变量中包含数组折叠，不能直接把 JSON 变量序号当成 HLSL `c107` 等
packoffset。上面这些语义值是通过参考 HLSL 布局、已知背面捕获值和连续特征值共同校准得到。

## 对 Unity 还原的影响

- 正面帧应成为当前提弗洛斯角色展示场景的第一基准；背面帧继续用于头发背部、轮廓和衣料验证。
- 当前 Unity shader 如果只用一套单 pass 角色光照，无法覆盖官方的主颜色 pass 加后续头发/边缘写入。
- 下一步应先扩展离线采集工具，记录每个候选事件的 Vulkan 深度、模板、混合、剔除和颜色写入状态。
  这样再拆 Unity URP pass，才能避免凭感觉乱加描边或透明层。
- 材质贴图绑定需要按部位分开：face、hair、cloth 的 set1 数量、尺寸和 ramp 格式都不同，
  不能继续用一个通用贴图槽方案硬塞。

本轮仍未宣称 Unity 工程已经达到官方效果；这里只是把新的正面官方捕获转成可追踪、可复核的
还原依据。
