# Cloth01/02 原生 BC5 输入接入 — 2026-10-01

本轮完成两张衣物法线的原生压缩块/完整 mip/view/实际 sampler/生产消费验证，并提供可恢复的内存绑定。用户明确只要最高细节模型；没有新增模型 LOD、质量分档、性能适配或重压缩降级。纹理 mip 是官方采样数据，不是模型 LOD，原始 12 级全部保留。

**范围不是整个官方渲染完成认证。** 没有截图拟合、曝光补偿或修改原始游戏；仅离线读取已有 `正面.rdc` 和 ZIP。上一轮公式证据仍见 `../cloth-normal-20261001/README.md`，本轮补的是其尚未闭合的输入/绑定部分。

## 实际捕获证据

帧 6411。PS `_56.SampleBias(_25, _3, _19_m16)` 是法线；必须按每条 shader 的真实 register/reflection 关联。

| 部位 | event / PS | 原 image / view | normal set/binding | ZIP entry | payload SHA-256 |
| --- | --- | --- | --- | --- | --- |
| Cloth01 | 835 / 22255 | 37987 / 37988 | **1/4** | `002959` | `e96d6fd9c9a1850ab0655f8fe42fd156beb992d19008fea1a5ac45e5c6c62841` |
| Cloth02 | 850 / 37669 | 37828 / 37829 | **1/5** | `004532` | `9c7ab3cb6d4c7e85284f4caee838c5dd8978495ed147b38856808758b7db35d8` |

最初把两条都写成 set1/b5 被实际 replay 拒绝；835 的 b5 是另一张纹理。改正的是我们测试/计划里的错误假设，不是修改官方数据以满足假设。

两 image 均为 BC5_UNORM、2048²、depth1/array1、12 mip。两 view 均为 BC5_UNORM、2D、baseMip0/count12、baseSlice0/count1、minLODClamp0、RGBA identity swizzle。每 mip 按 `ceil(w/4)*ceil(h/4)*16` 排布，最后三个各16字节，总 payload **5592432**，不是 inventory 的 GPU allocation size5594624。绘制时 `GetTextureData` 的全部 mip 与 ZIP InitialContents **逐字节相等**，每级与总 SHA 都记录。

实际 Pixel sampler descriptor：

- `_25` / **set0/b4** / Resource155：U/V/W=Wrap，min/mag=Linear，mip=Point，filter=Normal，maxAnisotropy0，mipBias0，minLOD0/maxLOD1000，normalized coordinates，非 comparison。base/P/N/emission 共享它与 BaseMap_ST UV、shader bias=-1。
- `_24` / **set0/b6** / Resource197：ClampEdge，min/mag=Linear，mip=Point，同样 LOD/bias 域。diff/spec ramp 在实际 PS 使用它与显式 LOD0。
- reflection index 关联各自 reflection 列表，**不能**把 descriptor byteOffset 当 binding/index；sampler 从 `GetSamplerDescriptors` 获取，不是通用 image descriptor。

`Tools/capture_cloth_normals.py` 仅生成新目录，以成功 shutdown 后的 `complete.json` 为完成标记；native qrenderdoc exit code 不作通过依据。最终导出 `D:/EndfieldTechLib/notes/bc5-cloth-20261001-01/replay-07/`，manifest SHA **`37b3fb48aaef2eb0d8d6e9359f8e116065fc25ae449d6b2b93471a1f543dde0f`**。记录两个原 SPIR-V SHA、完整 image view、sampler 和每级原生 GPU 通道样本；不提交原块或 RDC。

## 实现与使用

- `EndfieldCapturedClothNormals.CreateTexture`：固定身份/长度/SHA，Texture2D BC5/12 mip/linear，`LoadRawTextureData` → `Apply(false,false)`，Bilinear/Repeat/aniso0/mipMapBias0，`ignoreMipmapLimit=true` 保持原分辨率。不能静默 transcode、生成 mip 或受质量限制丢高 mip；不改项目 QualitySettings。
- `Bind`：只接受两个明确命名的 CharacterLit / Cloth family / bump-enabled 材质槽；完整验证后才写 MPB，保留已有 slot 属性，首次 slot override 继承已有 renderer-root block。再次核验 raw CPU 字节，拒绝创建后被改过的 texture。未知部位/换装/其他 cloth 不自动猜测。
- **短 batch scope** 恢复原 slot block（原空则清空）；**长期菜单**只恢复自有 `_BumpMap`，保留后来更新的 shadow/用户字段。若他人已替换 normal texture，则不覆盖。菜单恢复后可能保留一个显式 normal override/合并 block，这是保留后续状态的选择，不是资产保存。不要把 scope 的 snapshot restore 当通用并发 MPB 合并器。
- `EndfieldCapturedClothInputs`：整个 manifest 固定 SHA，并校验两个 payload。Menu/退出/重载/场景关闭管理临时纹理；没有 SaveAssets/SaveScene/导入改写。
- CharacterLit source Cloth 的 base/N/E 与 Cloth helper 的 P 共享 **texture-bound `sampler_BumpMap`**，由原生 normal texture 提供正确的双线性/mip-point 状态；不是旧 inline LinearClamp。实际 PS 的 diff/spec ramps 改为 Clamp + LOD0。原 PNG fallback 的状态/mip 不因此被认证。
- pose-apply 入口显式可选加载，并保持作用域到 label 诊断之后。label 诊断现在保存/合并/恢复每槽 MPB 和原 label global，不再覆盖/清掉 normal 或实时 basis/shadow overrides。

本机已准备本地私有数据包：

`A:/Hypergryph Launcher/games/Arknights Endfield/FractalMiner/Validation/Captures/native-cloth-inputs-20261001-02/`

只有 `complete.json` / `cloth01.bc5` / `cloth02.bc5`，目录被既有 `/Validation/Captures/` 排除。旧 -01 包和全部失败记录保留，未覆盖。需要迁机时保留这三个文件及固定 SHA；新捕获/不同硬件重新导出不能自动更新 pin。

在 Unity Hierarchy 选提弗洛斯角色根，菜单 **Endfield → Captured Inputs → Bind native cloth normals (selected character, memory only)**。恢复用同目录 **Restore native cloth normals**。现有官方 source globals 仍须正常启用；此菜单只接输入，不代替光照/后处理/动作初始化。仅 Edit 模式预览；切换 Play、换场景或重载会恢复，不能当成完成的独立播放器打包方案。

批处理入口已有：

```powershell
$env:ENDFIELD_CLOTH_NATIVE_INPUTS = '1'
# 可选：指向上述三个文件的目录；缺省为项目内 -02 私有包。
$env:ENDFIELD_CLOTH_NATIVE_EXPORT = 'A:/Hypergryph Launcher/games/Arknights Endfield/FractalMiner/Validation/Captures/native-cloth-inputs-20261001-02'
```

`EndfieldPoseApplyValidation` 会按此绑定并恢复。但它原有整场景/pipeline activation 流程会涉及项目设置，因此**本轮未运行它整条入口**；只验证其编译/接线、独立生产 shader 消费、实际基线场景只读载入的两个槽。不要拿本轮报告声称已经完成整帧出片验收。

重新离线导出时，给 `capture_cloth_normals.py` 设置 `ENDFIELD_CAPTURE_PATH`（已有RDC）、`ENDFIELD_CAPTURE_ZIP`（原ZIP）、`ENDFIELD_CAPTURE_OUTPUT`（全新空目录）、`ENDFIELD_TOOLS_PATH`（项目Tools绝对路径）；以官方 `qrenderdoc --python` 执行。不使用 RenderDuck 注入或启动游戏。导出 hash、程序/view/sampler 变化需独立复审。

## 验证及保留的失败

最终 `EndfieldNativeClothValidation.RunBatch`，Unity2022.3.30f1 / D3D11 / RTX3060 Laptop，独立 batch，报告新文件由 `ENDFIELD_NATIVE_CLOTH_REPORT` 指定。`gpu-probes-09.txt` SHA **`1168fd524e97060384b4ef96dfed40b2c361f1192ee608bded5414c7f6e3a193`**。

- 2纹理 ×12 mip：原数据总 SHA、逐 mip 长度/分区再次验证。
- 每级四角/中心，共 **120 SampleLevel** 与独立离线 RenderDoc `PickPixel` 原生通道比较，maxError=0，门限2e-6；另 **120 integer Load** 同门限通过。小 mip 的重复位置是格式/级别检查，不能声称240个独立 texel。
- BC5 B=0/A=1、无需 UV flip；Repeat 正负越界两项通过。
- 8 项非整数 LOD fixture 分辨 nearest mip 与 trilinear；测试数据是独立合成，不是官方图像调参。source 生产 SampleBias 使用刻意非整数 bias=-0.6，lambda1选择mip0，通过；生产配置仍为官方bias=-1。
- 两个 CharacterLit 实际 native-map 采样→float normal decode 消费通过；CPU source normal 公式的输入来自独立 capture 通道，不是本项目 shader 的输出。
- MPB root 继承/slot 合并/短作用域恢复/长期 later-field 和 foreign-texture 所有权通过；4 payload 拒绝、3 target 拒绝、无部分写入。
- 正式 recovered scene **只读 additive 载入、不渲染、不保存**：两 native cloth 槽都找到并绑定，dirty 状态不变。五个默认 shader pass 通过，无 C#/shader 编译错误。private preview scene 仅用于初始化 URP。
- Cloth normal 回归31 kernel/14 production；emission32/16；Hair18/3 production invariants 均通过，报告 SHA 与前轮相同。Python新增回放模拟器只测API/IO失败边界，不当作原捕获真值；真实 replay 是另一条独立验证。
- Python exporter 的12项测试、22 subtests，仪器化行覆盖率 **97.69%**（127/130）；不冒充 C#/HLSL 或全工程覆盖率。全套304 passed、3 historical skipped、25 subtests、两条既有Pillow警告；Ruff/Pyright通过。
- 本轮 pip-audit 对临时审计环境完成：No known vulnerabilities found；不代表已审计游戏客户端、Unity二进制、全部第三方工具或其他未安装依赖。

过程失败保留在外部 notes：replay01/02 为错误的统一normal binding假设；03为 TextureSwizzle4 不能迭代；04发现 format 的SWIG repr不应作为格式名，05/06改为 `.Name()`/minLOD域及shader SHA，07增加实际原生 GPU 通道证据。Unity01为 runtime/editor跨程序集internal函数不可见，07为误用非公开 OpenPreviewScene；均修正后真实重新编译。GPU02–05中自写理想化BC4 palette在 Cloth01 mip2(511,511)预测R=.5030813，而实际 RenderDoc 与 Unity **均为 .5105364**；它不是可靠硬件解码 oracle，已撤掉该自写算法，未改一个输入块或放宽阈值。暂未认证软件BC4 palette与GPU硬件细节。05同时证实 Unity不支持BC5 compressed AsyncGPUReadback，最终工具不调用此失败接口，也不声称直接读回了压缩GPU内存。原块/CPU上传/原生采样三种证据分开表述。

## 封存与下一项

v1仍6771文件/18 anchors完整性通过、79 pending；v2仍149文件/7 anchors、24 pending，仅原有授权 CharacterLit / OfficialHair 两个 runtime snapshot drift。未重写两个 seal/manifest/源码快照。主 HEAD `fc9d4869803f439ffff83311986190e8a8b5ade3` 和9557 index entries保持，独立record-index增量提交；父记录 `2d7a81942029c24310b785d0f00c5e3f49e653b1`。

下一优先：沿实际PS核验并原生接入 Cloth **D/P/E、ramp 与 IBL cubemap 的格式/sRGB/mip/sampler**。本轮只证明法线原生数据，其他PNG重压缩不因此正确；IBL现有fractional cube LOD的inline sampler仍可能与实际s6 mip-point不一致，必须独立修正/验证，不为它打通过标记。随后才是尚缺的 native vertex/skinning/instance basis、cloth wetness/clearcoat/透明 variants、环境/rim/local lights/fog及完整实时后处理/解包动作/MMD生产场景。不得由局部120样本通过推导最终官方效果已经全量完成。

API依据：原始 mip 上传/不再生遵循 [Unity LoadRawTextureData](https://docs.unity3d.com/2022.3/Documentation/ScriptReference/Texture2D.LoadRawTextureData.html) 和 [Apply](https://docs.unity3d.com/2022.3/Documentation/ScriptReference/Texture2D.Apply.html)；独立保持原分辨率使用 [ignoreMipmapLimit](https://docs.unity3d.com/2022.3/Documentation/ScriptReference/Texture2D-ignoreMipmapLimit.html)。view/sampler 字段与 reflection association 按 [RenderDoc1.46 common_pipestate.h](https://raw.githubusercontent.com/baldurk/renderdoc/v1.46/renderdoc/api/replay/common_pipestate.h) 和 [TextureSwizzle4](https://raw.githubusercontent.com/baldurk/renderdoc/v1.46/renderdoc/api/replay/data_types.h)，实际值来自本机离线 replay，而非文档推测。
