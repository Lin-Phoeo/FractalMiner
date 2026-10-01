# 阴影实际 producer 状态复核与 atlas 采样修复

本增量只认证：frame6411 的实际 744/748 程序身份、原始 CB/资源视图/采样器/显式 Vulkan 状态，以及生产 compute 的 atlas Clamp 修复。不认证整个 live 阴影、最终画面、雨淋或 MMD 已完成。不做截图、IoU、LSB 逐像素拟合，不改曝光、材质参数或后处理。

## 1. 查到并修掉什么

748 实际 PS2261 用 `set3/t7` atlas，`GatherRed` 的 sampler `_11` 对应 `set3/s2`。离线重新解析 sampler descriptor，U/V/W 实际都是 **ClampEdge**，min/mag Linear、mip Point、Normal、bias0。旧 dump 名叫 `sampler_LinearMirror`，不能据名字推断寻址状态。

生产 `EndfieldCharacterShadowResolve.compute` 两个入口共用的 sampler 改成 inline `sampler_LinearClamp`；SampleLevel 单点诊断和 GatherRed 都使用它。没有改变 Poisson/rotation、bias、矩阵、G 软化、曝光或后处理。atlas **整图边界** Clamp 不等于每个角色 cell Clamp：官方没有 cell clamp/inset，邻格跨采样仍须保留。

同一最终合成门禁 3072 checks：旧 Mirror 256 FAIL；Clamp 0 FAIL，误差门限 `2e-4` 未改。验证器调用真正生产 `CSResolve`，CPU 从 hash 固定的实际 PS2261 HLSL 读取两张表，不复制 runtime 表当独立真值。覆盖 8 个中心（整图边缘/内部/格边）、16 个旋转格、capture flip 两态、单点/Gather 模式，以及零遮挡/全遮挡。

正式16-tap模式（Mode1）零遮挡最终 G=1 是本次 D3D11 后端的可观测结果，不是“0/0 不产生 NaN”的普遍保证。Mode0 是现有额外单点诊断，不是官方另一种 G 输出模式；它的 binary step 只验采样。compute 旧注释已更正。

## 2. 两个 resolve pass 不是单纯分写 R/G

| actual event | pipeline / VS / PS | 模板条件 | PS 输出语义 |
| --- | --- | --- | --- |
| 744 | 2416 / 2254 / 2255 | `(stencil & 7) != 4` | 方向 R、G=1 |
| 748 | 2417 / 2260 / 2261 | `(stencil & 7) == 4` | 方向 R + 角色自阴影 G |

两个 pass 都绑定 framebuffer59974：color58932/view58934 `R8G8_UNORM`，depth-stencil58980/view58983 `D32S8`。都 Blend off、writeMask15（不是 R-only/G-only）、Depth test Always、DepthWrite false、Cull none、无 raster bias、MSAA1；viewport/scissor/render-area 都 2560×1600。前后面模板操作均 Keep。

当前捕获 `_DirectionalShadowParams2`（actual ShadowData c35/byte560）=`(0,0,1,1)`。两实际 PS 在 `.w>=0.99` 时短路到 `.z`，后续方向强度（c34.x=1）保持 R=1。这是**本帧状态**，不是所有视角/场景的固定方向阴影算法。748 本身仍保留 CSM、其它 shadow 分支及云阴影路径。

## 3. 实际绑定与原始 CB

748 descriptor set 全为3：

| binding | actual resource / view | storage/view | 消费 |
| --- | --- | --- | --- |
| t4 | 58994 / 58996 | R10G10B10A2_UNORM 2560×1600 | GBuffer normal，integer Load |
| t5 | 58985 / 58987 | 同上 | character index，integer Load |
| t7 | 32538 / 32540 | D16 4096×2048，1 mip / 1 slice | 普通 GatherRed，s2 Linear ClampEdge |
| t8 | 59000 / 59002 | R32_FLOAT 2560×1600 | SampleLevel0，s0 Point ClampEdge，UV=(integerPx+.5)/size |

t6/t9/t10 和 s1/s3 也全部记录，不能因本帧方向短路而删掉它们。s3 实际是 Comparison Greater + Linear ClampEdge，不是普通 atlas sampler，也不能由 dump 的 MirrorOnce 名字推断。

PS CB 描述符来自 actual reflection index→set/binding，不按大小找块、不顺序累加解码变量大小：

| event | binding | offset in resource864 | bytes | SHA256 |
| --- | --- | --- | --- | --- |
| 744 / 748 | b10 / b11 | 549184 | 1312 | `8c08d09f389873fef16b68d2df5050d31114120eb2c26b4b6301679bcc1dd66c` |
| 744 / 748 | b11 / b12 | 502144 | 32864 | `73b2c3111012fc9e38c0272d6e021f5d28cce9022703b9523bbf5ad8a2bd8009` |
| 744 / 748 | b12 / b13 | 610944 | 11440 | `f7ce5d5218607b0ddab46cc1b919f83c3c342dc53f6304eb5e42fe1f26686fb1` |
| 744 / 748 | b13 / b14 | 550528 | 3200 | `6e65fa13c1e8107bbf9a8383179332d78b1e14418b7f9f8aa5ffa3baf115384b` |

实际 PS2261 HLSL：`_21_m15@c448` shadow matrices column_major、`m16@c508` biases、`m17@c523` travel、`m18@c538` atlas rects、`m19@c553` texelSize、`m20@c554` `(1,1,7,0)`。

新 raw b13@8608 的 7 个 rect.xy **按槽顺序**：`(.75,0),(.75,.5),(0,0),(0,.5),(.25,0),(.25,.5),(.5,0)`，每个 zw=`(.25,.5)`。旧研究文档 §5 的槽序不正确，本增量取代它；原封存文档不回写。slot0 bias=`(.003473103,.006946206,.001157701,256)`，travel=`(-.176319,-.5299193,-.8295162,0)`。

## 4. 程序身份 / 导出复现

两 VS 的 SPIR-V hash 都是 `9fb0158d67a31be253954afba3c31d164c160e302fe1a0d62785b8645b871b82`。
PS2255=`508c936ed3c95b75d5effa6529f9909d48d30304144734c63452f3b257fc57a3`。
PS2261=`8c0f0c3bd1dc58c5d4560435dd7ff505662ec7c6870c64065810e3ca2e681685`。
先与旧 archive 的原始 SPIR-V 对照，再离线重放核对实际 shader/pipeline，不能只凭 pass 名或资源大小认证。

本地完整包（原始二进制不上传）：

- `Validation/Captures/shadow-producers-20261001-final/`：4 SPV、8 raw CB、两个 event JSON、atlas usage、complete。
- `Validation/shadow-producer-audit-20261001-01/`：4 个 SPIRV-Cross HLSL。
- `D:/EndfieldTechLib/notes/shadow-producer-20261001-01/`：修改前备份、红/中间失败/最终绿、回归、独立 index。

`Tools/capture_shadow_producers.py` 复用现有 descriptor/sampler helper 和双 Shutdown 成功后才写 complete 的 collector；所有读取只针对已有 RDC，不启动游戏、不注入。

环境：`ENDFIELD_TOOLS_PATH=<project>/Tools`、`ENDFIELD_CAPTURE_PATH=C:/Users/Administrator/Downloads/正面.rdc`、`ENDFIELD_CAPTURE_OUTPUT=<fresh directory>`；用官方 qrenderdoc `--python <tool>`。只认 fresh complete，不认 native exit0。

反编译沿用本地 SPIRV-Cross1.46，args=`input.spv --hlsl --shader-model 51 --output output.hlsl`，tool SHA=`e5b4db9356bb0de3f6b66ccfa2370750e29d8a66b9d4527880c77d2e0325022d`。实际 PS2261 HLSL SHA=`f96c291b3839ec500bda03d1ba5b6d58c3b3d336232e23aded3eb7c8062bf9ad`，GPU fixture读前核对。

GPU入口：`EndfieldShaderPack.EndfieldShadowProducerSamplerValidation.RunBatch`；环境 `ENDFIELD_SHADOW_PRODUCER_REPORT=<fresh absolute txt>`、`ENDFIELD_SHADOW_PRODUCER_HLSL=<actual pinned hlsl>`，Unity D3D11 batch。不保存资产或场景。

## 5. TDD 中途失败也留存

原始 Python exporter 尚不存在时：16 FAIL；最终新增25例通过，新增工具116语句100% coverage（只限 Python 工具，不是 C#/compute/全工程）。

最初 GPU fixture 用非二进制精确 UV，并把 CPU 采样当作理想连续插值：旧代码394 FAIL；改 Clamp 后仍138 FAIL。按照 [D3D11.3 texture sampling specification](https://microsoft.github.io/DirectX-Specs/d3d/archive/D3D11_3_FunctionalSpec.htm) 的子纹素地址精度修正 CPU 后剩16个单点 filter-weight 失败。最终使用二进制精确 quarter-texel 中心（同样保留边缘/内部/格边八类），避免不同合法 filter precision 的歧义，再补零/全遮挡。用**同一最终 fixture**重跑旧 Mirror 256 FAIL、Clamp 0；阈值没改，失败文件全部保留。

显式 pipeline 字段参照 [RenderDoc1.46 Vulkan state](https://github.com/baldurk/renderdoc/blob/v1.46/renderdoc/api/replay/vk_pipestate.h) / [common state](https://github.com/baldurk/renderdoc/blob/v1.46/renderdoc/api/replay/common_pipestate.h)。不序列化 SWIG pointer，不为缺字段填默认正确值。

## 6. 尚未闭合 / 下一轮顺序

1. **官方 atlas writers**：fresh usage 找到 clear260、23个 depth draws（272–376），其中321–376为下一步核查重点；usage 是线索，不自动证明某 draw 已经官方重建。核对 VS/PS、皮肤与实例变换、depth/bias/clear、viewport/scissor/cell、alpha/cull。当前 live square R16 color adapter + 所有 rect=(0,0,1,1) 不等价认证捕获 D16 4×2 的7槽生产。
2. **GBuffer/模板生产与可见域**：官方748只处理 `(s&7)==4`；目前 character-only prepass/全屏 compute 以索引有效性替代域，没有真实 stencil 合约，场景其它物体遮挡/透明对象尚未证明。需要先回查生产者，不是凭 surface family 猜模板。
3. **R producer**：当前 source consumer可读独立R；尚未重建官方 CSM/其它 shadow/cloud 的动态生产。URP fallback仍明确存在；不得把此捕获全白硬编码当通用实现。
4. **重建坐标与最终链路**：actual PS用 integerPx 的 NDC，但 depth在pixel center Point取样；目前 captured/live `_CaptureFlipY` 分支含不同 NDC offset，属于待验证的 adapter，不因 roundtrip 自洽或合成 sampler通过就称官方空间闭合。实际 atlas/GBuffer/source都核实后，再覆盖最终天气/后处理生命周期、解包动作/MMD。

保留用户原始工程 HEAD/9557-entry index/原场景/Quality/Graphics；原v1/v2 manifest不改，79/24 pending不抹掉。更正全部以本增量记录，避免改写封存历史。

## 7. 本轮最终验证

- 生产 sampler GPU：3072/3072，通过；旧 Mirror 的256项失败留存。
- 真实 URP lifecycle：13/13；shadow consumer：238/238；source light selection：688/688，分别 fresh batch exit0。
- 全套 `Tools/tests`：425 passed、3个历史 skipped、80 subtests passed、2个既有 Pillow warning；不是整工程或 MMD 已通过。
- Ruff format/lint、Pyright通过；pip-audit在本轮临时工具+pytest/numpy/pillow环境无已知漏洞，不代表全部Unity依赖审计。
- 旧 lifecycle RunBatch 不主动退出，首次 runner漏了`-quit`，虽写PASS但进程仍存活；只停止身份核实的本轮测试进程，换fresh报告以正确runner重跑exit0。未改运行时来“修”runner。

按 search-first 复用现有离线提取/Shutdown helper；TDD 保留真实失败再修；verification-loop 补真实GPU回归与保存状态校验。改动与完整证据摘要见 `verification.json`，可以独立接续。
